import pytest

from inference_worker import normalize_metrics, validate_output


def metric(peak=-10, clipped=0):
    return normalize_metrics({"status": "ok", "detection_method": "silero_vad", "speaking_span_seconds": 10,
        "transcript_word_count": 20, "words_per_minute": 120, "pause_count": 0, "pauses": [],
        "recording": {"peak_dbfs": peak, "clipped_fraction": clipped}})


def test_refuses_ungrounded_or_opposite_microphone_advice():
    clipped = metric(0, .04)
    assert not validate_output("The recorded level is low; try moving the microphone closer.", clipped)
    assert not validate_output("Increase the input gain.", clipped)
    assert validate_output("The recording shows clipping; try lowering the input gain.", clipped)
    normal = metric(-10, 0)
    assert not validate_output("The recorded level is low.", normal)
    assert not validate_output("The recording shows clipping.", normal)
    low = metric(-42, 0)
    assert validate_output("The recorded level is low; try moving the microphone closer.", low)


def test_refuses_unsupported_claims_and_numbers():
    data = metric()
    assert not validate_output("Your pronunciation is clear.", data)
    assert not validate_output("The pace is 150 words per minute.", data)
    assert validate_output("The estimated pace is 120 words per minute over 10 seconds.", data)
    assert not validate_output("You have 3 pauses.", data)


def test_metric_whitelist_excludes_private_input():
    source = {"status": "ok", "detection_method": "silero_vad", "speaking_span_seconds": 10,
        "transcript_word_count": 20, "words_per_minute": 120, "pause_count": 0, "pauses": [],
        "recording": {"peak_dbfs": -10, "clipped_fraction": 0}, "transcript": "private words"}
    assert "transcript" not in normalize_metrics(source)
    source["words_per_minute"] = 10
    with pytest.raises(ValueError):
        normalize_metrics(source)
