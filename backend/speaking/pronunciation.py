"""Optional acoustic evidence from Azure; never substitute transcript guesses."""
import asyncio
import json
from pathlib import Path
import threading

from .config import Settings


class PronunciationService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def assess(self, audio_path: Path, reference: str = ""):
        if not self.settings.azure_key:
            return {"status": "not_configured", "message": "未配置 Azure 语音凭据，发音暂未评测。"}
        try:
            return await asyncio.to_thread(self._continuous, audio_path, reference)
        except Exception:
            # SDK errors may include service internals; keep credentials and paths private.
            return {"status": "unavailable", "message": "发音服务本次未完成；录音和文字仍已保存。"}

    def _continuous(self, path, reference):
        import azure.cognitiveservices.speech as sdk
        config = sdk.SpeechConfig(subscription=self.settings.azure_key, region=self.settings.azure_region)
        config.speech_recognition_language = "en-US"
        recognizer = sdk.SpeechRecognizer(speech_config=config, audio_config=sdk.audio.AudioConfig(filename=str(path)))
        assessment = sdk.PronunciationAssessmentConfig(
            reference_text=reference,
            grading_system=sdk.PronunciationAssessmentGradingSystem.HundredMark,
            granularity=sdk.PronunciationAssessmentGranularity.Phoneme,
            enable_miscue=False,  # Not supported in continuous mode, including >30s.
        )
        assessment.enable_prosody_assessment()
        assessment.apply_to(recognizer)
        complete = threading.Event()
        segments, errors = [], []

        def recognized(event):
            if event.result.reason == sdk.ResultReason.RecognizedSpeech:
                try:
                    value = event.result.properties.get(sdk.PropertyId.SpeechServiceResponse_JsonResult)
                    raw = json.loads(value)
                    best = raw.get("NBest", [{}])[0]
                    segments.append({"text": best.get("Display", event.result.text), "scores": best.get("PronunciationAssessment", {}), "words": best.get("Words", [])})
                except (ValueError, TypeError, IndexError):
                    errors.append("invalid_result")

        recognizer.recognized.connect(recognized)
        recognizer.session_stopped.connect(lambda _event: complete.set())
        def cancelled(_event):
            errors.append("cancelled")
            complete.set()
        recognizer.canceled.connect(cancelled)
        recognizer.start_continuous_recognition_async().get()
        try:
            if not complete.wait(160):
                raise TimeoutError("Pronunciation assessment timed out")
        finally:
            recognizer.stop_continuous_recognition_async().get()
        if errors or not segments:
            raise RuntimeError("Pronunciation assessment incomplete")
        words = []
        for segment in segments:
            for item in segment["words"]:
                details = item.get("PronunciationAssessment", {})
                words.append({"word": item.get("Word", ""), "accuracy": details.get("AccuracyScore"), "error_type": details.get("ErrorType"), "offset_seconds": item.get("Offset", 0) / 10_000_000, "duration_seconds": item.get("Duration", 0) / 10_000_000, "phonemes": [{"phoneme": p.get("Phoneme", ""), "accuracy": p.get("PronunciationAssessment", {}).get("AccuracyScore")} for p in item.get("Phonemes", [])]})
        values = [x["accuracy"] for x in words if isinstance(x.get("accuracy"), (float, int))]
        return {"status": "available", "provider": "Azure Pronunciation Assessment", "locale": "en-US", "word_accuracy_mean": round(sum(values) / len(values), 1) if values else None, "words": words, "segments": [{"text": x["text"], "scores": x["scores"]} for x in segments], "scope": "Azure 音频诊断；均值为本应用的逐词平均，不是官方考试分数。低分音素仅是复听线索，不据此推断具体错读成了哪个音。"}
