"""Bounded, on-demand CPU subprocess: never loads an LLM in the avatar server."""
import asyncio
import json
import os
from pathlib import Path
import sys

from .worker import normalize_metrics, validate_output


REASONS = {
    "adapter_missing": "Fine-tuned advice is not enabled: the trained adapter weights are missing.",
    "base_missing": "Fine-tuned advice is not enabled: the base model files are missing.",
    "dependencies_missing": "Fine-tuned advice is not enabled: its local runtime needs setup.",
    "busy": "Another voice review is running. Please try again shortly.",
    "timeout": "The local voice review took too long. Your recording and report are saved.",
    "rejected": "The generated advice could not be verified against the measurements.",
    "failed": "Local advice could not be generated. Your recording and report are saved.",
}


class VoiceCoach:
    def __init__(self, model_root, runtime, timeout=120):
        self.root, self.runtime, self.timeout = Path(model_root), Path(runtime), timeout
        self.lock = asyncio.Lock()
        self.processes = set()

    def status(self):
        adapter, base = self.root / "adapter", self.root / "base"
        reason = None
        if not (adapter / "adapter_config.json").is_file() or not (adapter / "adapter_model.safetensors").is_file():
            reason = "adapter_missing"
        elif not all((base / name).is_file() for name in ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json")):
            reason = "base_missing"
        elif not all((self.runtime / "voice-coach-deps" / name / "__init__.py").is_file() for name in ("peft", "transformers", "accelerate")):
            reason = "dependencies_missing"
        return {"ready": reason is None, "reason": reason,
                "message": REASONS.get(reason, "Fine-tuned recording feedback is ready."),
                "model": "Qwen2.5-1.5B-Instruct + LoRA", "scope": "Pace, pauses and recording level only; no pronunciation or exam scores."}

    async def close(self):
        processes = list(self.processes)
        for process in processes:
            if process.returncode is None:
                process.kill()
        await asyncio.gather(*(process.wait() for process in processes), return_exceptions=True)

    async def advise(self, metrics):
        metrics = normalize_metrics(metrics)
        def failure(reason):
            return {"status": "unavailable", "advice": None, "reason": reason, "message": REASONS[reason]}
        status = self.status()
        if not status["ready"]:
            return failure(status["reason"])
        if self.lock.locked():
            return failure("busy")
        async with self.lock:
            process = None
            try:
                environment = {**os.environ, "CUDA_VISIBLE_DEVICES": "-1", "OMP_NUM_THREADS": "2",
                               "MKL_NUM_THREADS": "2", "PYTHONNOUSERSITE": "1",
                               "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                               "VOICE_COACH_DEPS": str(self.runtime / "voice-coach-deps"),
                               "HF_HOME": str(self.runtime / "voice-coach-cache")}
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-s", str(Path(__file__).with_name("worker.py")),
                    "--base", str(self.root / "base"), "--adapter", str(self.root / "adapter"),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    env=environment, **({"creationflags": 0x08000000} if os.name == "nt" else {}))
                self.processes.add(process)
                stdout, _ = await asyncio.wait_for(process.communicate(json.dumps(metrics).encode()), self.timeout)
                result = json.loads(stdout)
                advice = result.get("advice") if isinstance(result, dict) else None
                if process.returncode != 0:
                    return failure("failed")
                if result.get("status") == "ok" and isinstance(advice, str) and not any('\u3400' <= c <= '\u9fff' for c in advice) and validate_output(advice, metrics):
                    return {"status": "ok", "advice": advice, "model": "local_lora", "reason": None}
                return failure("rejected" if result.get("status") in ("ok", "rejected") else "failed")
            except asyncio.TimeoutError:
                return failure("timeout")
            except (OSError, ValueError, TypeError, AttributeError):
                return failure("failed")
            finally:
                if process is not None:
                    if process.returncode is None:
                        process.kill()
                    await process.wait()
                    self.processes.discard(process)
