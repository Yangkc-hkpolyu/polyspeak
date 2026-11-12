#!/bin/sh
set -eu
mkdir -p "$TEMP"
python -s -c 'from pathlib import Path; import torch; assert torch.cuda.is_available(), "Cloud avatar needs a CUDA GPU visible to PyTorch"; assert Path("/app/speaking-models/wav2lip.pth").is_file(), "Upload wav2lip.pth to speaking-models before starting"'
exec python -s -m uvicorn backend.speaking.app:app --host 0.0.0.0 --port 8008 --workers 1 --proxy-headers --forwarded-allow-ips='*'
