"""Install optional isolated inference packages and a supplied trained adapter."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "speaking-runtime"
MODEL = ROOT / "speaking-models/voice-coach"
BASE_SHA256 = "dd924a11b4c220f385b51ffa522daea7c9f3d850e31b162bb5661df483c6d3ee"
BASE_REVISION = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"


def validate_adapter(folder):
    config = json.loads((folder / "adapter_config.json").read_text(encoding="utf-8"))
    if config.get("base_model_name_or_path") != "Qwen/Qwen2.5-1.5B-Instruct" or config.get("peft_type") != "LORA":
        raise ValueError("Provide the Qwen2.5-1.5B-Instruct LoRA adapter, not base model weights.")
    path = folder / "adapter_model.safetensors"
    with path.open("rb") as stream:
        size = struct.unpack("<Q", stream.read(8))[0]
        if not 0 < size < 1024 * 1024:
            raise ValueError("Invalid adapter header")
        header = json.loads(stream.read(size))
        if not any("lora_A" in name for name in header) or not any("lora_B" in name for name in header):
            raise ValueError("The provided file does not contain LoRA tensors.")
        payload_size = path.stat().st_size - 8 - size
        for name, tensor in header.items():
            if name != "__metadata__" and not 0 <= tensor["data_offsets"][0] < tensor["data_offsets"][1] <= payload_size:
                raise ValueError("The adapter is truncated or malformed.")
    return config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-dir", type=Path, default=ROOT / "experiments/voice-coach/adapter", help="Trained adapter folder; defaults to the adapter included in this repository")
    parser.add_argument("--base-dir", type=Path, help="Use an existing local Qwen base instead of downloading it")
    parser.add_argument("--skip-deps", action="store_true", help="Keep already prepared isolated packages; still check imports")
    parser.add_argument("--deps-only", action="store_true")
    args = parser.parse_args()
    if not args.deps_only:
        if not args.adapter_dir:
            parser.error("Provide --adapter-dir, or use --deps-only to prepare the runtime while waiting for weights.")
        validate_adapter(args.adapter_dir)
    deps = RUNTIME / "voice-coach-deps"
    deps.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "PIP_CACHE_DIR": str(RUNTIME / "pip-cache"),
                   "HF_HOME": str(RUNTIME / "voice-coach-cache"), "PYTHONNOUSERSITE": "1"}
    if not args.skip_deps:
        subprocess.run([sys.executable, "-s", "-m", "pip", "install", "--no-deps", "--upgrade", "--target", str(deps),
                        "-r", str(ROOT / "requirements-voice-coach.txt")], env=environment, check=True)
    code = "import sys; sys.path.insert(0, sys.argv[1]); import torch,transformers,peft,accelerate; print('Isolated voice-coach imports OK')"
    subprocess.run([sys.executable, "-s", "-c", code, str(deps)], env=environment, check=True)
    if args.deps_only:
        return
    def copy_complete(source, destination):
        if source.resolve() == destination.resolve():
            return
        temporary = destination.with_name(destination.name + ".part")
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)

    names = ("config.json", "generation_config.json", "tokenizer.json", "tokenizer_config.json", "merges.txt", "vocab.json", "model.safetensors")
    if args.base_dir:
        for name in names:
            if not (args.base_dir / name).is_file():
                raise ValueError("Missing base model file: " + name)
        with (args.base_dir / "model.safetensors").open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != BASE_SHA256:
                raise ValueError("Unexpected local base model checksum.")
    destination = MODEL / "adapter"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("adapter_config.json", "adapter_model.safetensors"):
        if (args.adapter_dir / name).resolve() != (destination / name).resolve():
            copy_complete(args.adapter_dir / name, destination / name)
    if args.base_dir:
        (MODEL / "base").mkdir(parents=True, exist_ok=True)
        for name in names + ("LICENSE",):
            if (args.base_dir / name).is_file():
                copy_complete(args.base_dir / name, MODEL / "base" / name)
    else:
        sys.path.insert(0, str(deps))
        os.environ["HF_HOME"] = str(RUNTIME / "voice-coach-cache")
        from huggingface_hub import hf_hub_download
        for name in names:
            hf_hub_download("Qwen/Qwen2.5-1.5B-Instruct", name, revision=BASE_REVISION, local_dir=MODEL / "base", cache_dir=RUNTIME / "voice-coach-cache")
    with (MODEL / "base/model.safetensors").open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != BASE_SHA256:
            raise ValueError("Unexpected base model checksum. Review the upstream revision before using it.")
    print("Voice-coach assets installed. Test a completed recording before relying on the advice.")


if __name__ == "__main__":
    main()
