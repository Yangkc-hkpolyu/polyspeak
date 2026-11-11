import os
os.environ.setdefault("LT_MEL_USE_GPU", "0")  # Original CPU mel path; CUDA Wav2Lip stays enabled.
import uvicorn
from backend.speaking.config import load_settings

if __name__ == "__main__":
    settings = load_settings()
    print(f"PolySpeak: http://127.0.0.1:{settings.port}")
    uvicorn.run("backend.speaking.app:app", host="127.0.0.1", port=settings.port, workers=1)
