"""Audio-conditioned lip sync on PolyInterview-compatible dynamic frame cycles."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import threading
from typing import Callable

import cv2
import imageio_ffmpeg
import librosa
import numpy as np
from scipy import signal
import soundfile as sf
import torch

from .config import Settings
from .motion import build_motion_cycle
from .vendor.wav2lip import Wav2Lip
from .vendor.livetalking_sequence import paste_back_frame, prepare_face_inputs

AVATAR_RENDER_VERSION = "nora-v5-desk-calm-motion"


def apply_scene_face_mask(frame, prepared, box, mask):
    """Keep old room pixels in predicted face-crop corners out of the new scene."""
    if mask is not None:
        y1, y2, x1, x2 = box
        alpha = mask[..., None].astype(np.float32) / 255
        face = frame[y1:y2, x1:x2] * alpha + prepared[y1:y2, x1:x2] * (1 - alpha)
        frame[y1:y2, x1:x2] = np.clip(face, 0, 255).round().astype(np.uint8)
    return frame


def select_device(requested):
    mps = getattr(torch.backends, "mps", None)
    mps_available = bool(mps and mps.is_available())
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "mps" if mps_available else "cpu"
    if requested.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("当前环境无法使用 CUDA，请检查 PyTorch 和显卡驱动。")
    if requested == "mps" and not mps_available:
        raise RuntimeError("当前环境无法使用 Apple MPS，请检查 Mac、macOS 和 PyTorch。")
    if requested not in ("cpu", "mps") and not requested.startswith("cuda"):
        raise ValueError("数字人设备应为 auto、cpu、mps 或 cuda。")
    return requested


def mel_spectrogram(wav: np.ndarray) -> np.ndarray:
    emphasized = signal.lfilter([1, -0.97], [1], wav)
    spectrum = np.abs(librosa.stft(emphasized, n_fft=800, hop_length=200, win_length=800))
    basis = librosa.filters.mel(sr=16000, n_fft=800, n_mels=80, fmin=55, fmax=7600)
    mel = basis @ spectrum
    db = 20 * np.log10(np.maximum(1e-5, mel)) - 20
    normalized = np.clip(8 * ((db + 100) / 100) - 4, -4, 4).astype(np.float32)
    if normalized.shape[1] < 16:
        normalized = np.pad(normalized, ((0, 0), (0, 16 - normalized.shape[1])), mode="edge")
    return normalized


class AvatarRenderer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = None
        self.device = "cpu"
        self.lock = threading.Lock()
        self.frames, self.coords = [], []

    @property
    def cache_key(self):
        path = self.settings.avatar_directory / "avatar.json"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else "missing-avatar"
        return AVATAR_RENDER_VERSION + "|" + digest + "|" + str(self.settings.avatar_fps)

    def load_sequence(self):
        root = self.settings.avatar_directory.resolve()
        manifest_path = root / "avatar.json"
        if not manifest_path.is_file():
            raise RuntimeError("缺少动态人物素材，请解压头像素材包或运行 prepare_speaking_avatar.py。")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest.get("frames", [])
        if len(entries) < 2 or manifest.get("fps") != self.settings.avatar_fps:
            raise ValueError("动态人物素材需要多帧且帧率须与渲染配置一致。")
        frames, faces, coords, masks = [], [], [], []
        for item in entries:
            paths = [(root / item[key]).resolve() for key in ("full", "face")]
            if not all(path.is_relative_to(root) for path in paths):
                raise ValueError("人物素材路径越界。")
            frame, face = [cv2.imread(str(path)) for path in paths]
            if frame is None or face is None or face.shape != (256, 256, 3):
                raise ValueError("动态人物帧或 256 像素人脸帧损坏。")
            if frame.shape[:2] != (manifest["height"], manifest["width"]):
                raise ValueError("动态人物完整帧的尺寸不一致。")
            y1, y2, x1, x2 = item["coords"]
            if not 0 <= y1 < y2 <= frame.shape[0] or not 0 <= x1 < x2 <= frame.shape[1]:
                raise ValueError("人物逐帧坐标无效。")
            mask = None
            if "lip_mask" in item:
                path = (root / item["lip_mask"]).resolve()
                if not path.is_relative_to(root):
                    raise ValueError("人物素材路径越界。")
                mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                if mask is None or mask.shape != (y2 - y1, x2 - x1):
                    raise ValueError("人物场景遮罩损坏或尺寸不一致。")
            frames.append(frame); faces.append(face); coords.append((y1, y2, x1, x2))
            masks.append(mask)
        self.frames, self.coords = frames, coords
        self.scene_masks = masks
        self.playback_cycle = build_motion_cycle(len(frames), manifest.get("source_frame_repeats"))
        self.face_inputs = prepare_face_inputs(faces)
        self.face_frames = faces
        self.height, self.width = frames[0].shape[:2]
        if self.width % 2 or self.height % 2:
            raise ValueError("视频尺寸必须为偶数。")
        self.avatar_source = manifest.get("source_avatar", "custom")

    def load(self):
        if self.model is not None:
            return
        if not self.settings.model_path.is_file():
            raise RuntimeError("缺少口型模型，请按 README-SPEAKING.md 下载或放入 speaking-models。")
        torch.set_num_threads(self.settings.torch_threads)
        self.device = select_device(self.settings.avatar_device)
        self.load_sequence()
        checkpoint = torch.load(self.settings.model_path, map_location="cpu", weights_only=True)
        model = Wav2Lip()
        model.load_state_dict({key.removeprefix("module."): value for key, value in checkpoint["state_dict"].items()})
        model = model.eval().to(self.device)
        # PolyInterview's native load_model/inference path uses float32.
        self.model = model

    def render(self, audio_file: Path, target: Path, progress: Callable[[int], None] = lambda _: None):
        with self.lock, torch.inference_mode():
            self.load()
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            wav_path = target.with_suffix(".wav")
            staging = target.with_name(target.stem + ".rendering.mp4")
            subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(audio_file), "-ar", "16000", "-ac", "1", str(wav_path)], check=True, capture_output=True)
            wav, _ = sf.read(wav_path, dtype="float32")
            mel = mel_spectrogram(wav)
            fps = self.settings.avatar_fps
            frames = max(1, math.ceil(len(wav) / 16000 * fps))
            command = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{self.width}x{self.height}", "-r", str(fps), "-i", "pipe:0", "-i", str(audio_file), "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-threads", "2", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", "-shortest", str(staging)]
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            batch_size = self.settings.avatar_batch_size
            try:
                for offset in range(0, frames, batch_size):
                    count = min(batch_size, frames - offset)
                    chunks = []
                    for index in range(offset, offset + count):
                        start = min(int(index * 80 / fps), mel.shape[1] - 16)
                        chunks.append(mel[:, start:start + 16])
                    audio = torch.from_numpy(np.stack(chunks)[:, None]).to(self.device)
                    indices = [self.playback_cycle[i % len(self.playback_cycle)] for i in range(offset, offset + count)]
                    face = torch.from_numpy(np.ascontiguousarray(self.face_inputs[indices])).to(self.device)
                    predictions = self.model(audio, face).float().cpu().numpy().transpose(0, 2, 3, 1) * 255
                    for prediction, index in zip(predictions, indices):
                        frame = paste_back_frame(prediction, index, self.frames, self.coords)
                        frame = apply_scene_face_mask(frame, self.frames[index], self.coords[index], self.scene_masks[index])
                        process.stdin.write(frame.tobytes())
                    progress(int(100 * (offset + count) / frames))
                process.stdin.close()
                stderr = process.stderr.read()
                code = process.wait(timeout=30)
                if code:
                    raise RuntimeError("视频编码失败：" + stderr.decode("utf-8", errors="replace")[-300:])
                staging.replace(target)
            except Exception:
                process.kill()
                process.wait()
                raise
            finally:
                wav_path.unlink(missing_ok=True)
                staging.unlink(missing_ok=True)
            return {"duration": round(len(wav) / 16000, 2), "frames": frames, "device": self.device, "avatar_source": self.avatar_source, "source_frames": len(self.frames), "width": self.width, "height": self.height, "fps": fps, "render_version": AVATAR_RENDER_VERSION}

