from collections import OrderedDict
from copy import deepcopy
import json

import pytest

from backend.speaking.layered_feedback import LayeredEvaluator, acoustic_features, grounded_polishing
from backend.speaking.streaming_input import transcript_event
from backend.speaking.feedback import DIMENSIONS, normalize_feedback
from backend.speaking.provider import ProviderError


def test_realtime_transcript_preserves_completed_segments_and_does_not_duplicate_partial_prefix():
    finals = OrderedDict()
    first = transcript_event({"type": "conversation.item.input_audio_transcription.text", "item_id": "one", "text": "I like ", "stash": "quiet parks."}, finals)
    assert first["text"] == "I like quiet parks." and not first["final"]
    transcript_event({"type": "conversation.item.input_audio_transcription.completed", "item_id": "one", "transcript": "I like quiet parks."}, finals)
    second = transcript_event({"type": "conversation.item.input_audio_transcription.text", "item_id": "two", "text": "They ", "stash": "They help me relax."}, finals)
    assert second["text"] == "I like quiet parks. They help me relax."
    transcript_event({"type": "conversation.item.input_audio_transcription.completed", "item_id": "one", "transcript": "I like quiet parks."}, finals)
    assert len(finals) == 1


def test_polishing_applies_only_matching_spans_and_rejects_invented_names_numbers_and_experiences():
    answer = "I likes this park. It is quiet."
    value = grounded_polishing(answer, {"corrections": [
        {"original": "I likes this park.", "revised": "I like this park.", "reason": "Subject-verb agreement."},
        {"original": "It is quiet.", "revised": "It is quiet in London.", "reason": "Adds a location."},
        {"original": "It is quiet.", "revised": "It is quiet for 30 years.", "reason": "Adds a number of years."}]})
    assert value["polished_answer"] == "I like this park. It is quiet."
    assert len(value["corrections"]) == 1
    assert grounded_polishing("I learned to bake bread.", {"corrections": [{"original": "bake bread", "revised": "bake sourdough with my aunt"}]})["corrections"] == []
    assert grounded_polishing("English speaking practice", {"corrections": [{"original": "English speaking", "revised": "English-speaking"}]})["corrections"] == []
    sentence = "I am building an English speaking practice application."
    assert grounded_polishing(sentence, {"corrections": [{"original": sentence, "revised": "I'm building an English-speaking practice application."}]})["corrections"] == []


def test_missing_acoustic_evidence_is_unavailable_not_zero_or_guessed_from_transcript():
    missing = acoustic_features({"status": "not_configured"})
    assert all(value["score"] is None for value in missing.values())
    result = acoustic_features({"status": "available", "word_accuracy_mean": 84,
                                "segments": [{"scores": {"FluencyScore": 76, "ProsodyScore": float('nan')}}]})
    assert result["accuracy"]["score"] == 8.4
    assert result["fluency"]["score"] == 7.6
    assert result["prosody"]["score"] is None


def test_non_english_generated_feedback_is_retryable_without_rewriting_user_evidence():
    raw = {"summary": "这次回答很好。", "dimensions": [
        {"key": key, "score": 6, "comment": "Based on the answer."} for key in DIMENSIONS]}
    with pytest.raises(ProviderError, match="feedback in English"):
        normalize_feedback(raw, [], "live")
    answer = "I likes this park. 我的原话。"
    revised = grounded_polishing(answer, {"corrections": [{
        "original": "I likes this park.", "revised": "I like this park.", "reason": "Subject-verb agreement."}]})
    assert revised["original"] == answer
    assert revised["polished_answer"] == "I like this park. 我的原话。"


def test_generated_chinese_correction_is_skipped_without_changing_original_evidence():
    answer = "I likes books. 我的原话。"
    result = grounded_polishing(answer, {"corrections": [{
        "original": "I likes books.", "revised": "我喜欢书。", "reason": "Subject-verb agreement."}]})
    assert result["original"] == answer
    assert result["polished_answer"] == answer
    assert result["corrections"] == []


def test_original_report_aggregation_excludes_unavailable_features_and_counts_real_answers():
    evaluator = LayeredEvaluator(None)
    criteria = {"professional_performance": {"conceptual_accuracy": {"score": 6, "justification": "Observed"}},
                "way_of_expression": {"coherence": {"score": 8}},
                "oral_expression": acoustic_features({"status": "not_configured"}),
                "nonverbal": {"eye_contact": {"score": None, "status": "not_collected"}}}
    evaluation = {"assessment_criteria": criteria, "aspects": {"coherence": {"score": 7, "justification": "Observed"}},
                  "polishing": {"corrections": []}}
    turns = [{"id": "one", "question": "Why?", "evaluation": evaluation},
             {"id": "two", "question": "How?", "evaluation": deepcopy(evaluation)}]
    result = evaluator.aggregate(turns)
    assert result["aspects_summary"]["coherence"]["count"] == 2
    assert result["proficiency"]["practice_score"] == 7
    assert result["features_summary"]["accuracy"]["score"] is None
    assert result["features_summary"]["accuracy"]["count"] == 0
    assert result["features_summary"]["eye_contact"]["score"] is None
