import math
from typing import Dict, Tuple

import librosa
import librosa.filters
import numpy as np
# import tensorflow as tf
from scipy import signal
from scipy.io import wavfile
from .hparams import hparams as hp

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[misc, assignment]

_mel_gpu_modules: Dict[str, object] = {}

def load_wav(path, sr):
    return librosa.core.load(path, sr=sr)[0]

def save_wav(wav, path, sr):
    wav *= 32767 / max(0.01, np.max(np.abs(wav)))
    #proposed by @dsmiller
    wavfile.write(path, sr, wav.astype(np.int16))

def save_wavenet_wav(wav, path, sr):
    librosa.output.write_wav(path, wav, sr=sr)

def preemphasis(wav, k, preemphasize=True):
    if preemphasize:
        return signal.lfilter([1, -k], [1], wav)
    return wav

def inv_preemphasis(wav, k, inv_preemphasize=True):
    if inv_preemphasize:
        return signal.lfilter([1], [1, -k], wav)
    return wav

def get_hop_size():
    hop_size = hp.hop_size
    if hop_size is None:
        assert hp.frame_shift_ms is not None
        hop_size = int(hp.frame_shift_ms / 1000 * hp.sample_rate)
    return hop_size

def linearspectrogram(wav):
    D = _stft(preemphasis(wav, hp.preemphasis, hp.preemphasize))
    S = _amp_to_db(np.abs(D)) - hp.ref_level_db
    
    if hp.signal_normalization:
        return _normalize(S)
    return S

def melspectrogram(wav):
    D = _stft(preemphasis(wav, hp.preemphasis, hp.preemphasize))
    S = _amp_to_db(_linear_to_mel(np.abs(D))) - hp.ref_level_db
    
    if hp.signal_normalization:
        return _normalize(S)
    return S


def _preemphasis_torch(wav_t, k: float, do: bool):
    if torch is None:
        raise RuntimeError("torch 未安装")
    if not do:
        return wav_t
    if wav_t.numel() == 0:
        return wav_t
    return torch.cat((wav_t[:1], wav_t[1:] - k * wav_t[:-1]))


def _amp_to_db_torch(x):
    if torch is None:
        raise RuntimeError("torch 未安装")
    min_level = math.exp(hp.min_level_db / 20.0 * math.log(10.0))
    return 20.0 * torch.log10(torch.clamp(x, min=min_level))


def _normalize_torch(S):
    if torch is None:
        raise RuntimeError("torch 未安装")
    if hp.allow_clipping_in_normalization:
        if hp.symmetric_mels:
            t = (2.0 * hp.max_abs_value) * (
                (S - hp.min_level_db) / (-hp.min_level_db)
            ) - hp.max_abs_value
            return torch.clamp(t, -hp.max_abs_value, hp.max_abs_value)
        t = hp.max_abs_value * ((S - hp.min_level_db) / (-hp.min_level_db))
        return torch.clamp(t, 0.0, hp.max_abs_value)
    raise RuntimeError("melspectrogram_gpu 需要 allow_clipping_in_normalization=True")


def _mel_spectrogram_module_gpu(device):
    if torch is None:
        raise RuntimeError("torch 未安装")
    try:
        import torchaudio
    except ImportError as e:
        raise ImportError(
            "melspectrogram_gpu 需要安装 torchaudio（版本需与 torch 匹配）"
        ) from e
    key = str(device)
    if key not in _mel_gpu_modules:
        hop = get_hop_size()
        mel = torchaudio.transforms.MelSpectrogram(
            sample_rate=hp.sample_rate,
            n_fft=hp.n_fft,
            win_length=hp.win_size,
            hop_length=hop,
            n_mels=hp.num_mels,
            f_min=hp.fmin,
            f_max=hp.fmax,
            power=1.0,
            norm=None,
            mel_scale="slaney",
            center=True,
            pad_mode="reflect",
        )
        _mel_gpu_modules[key] = mel.to(device)
    return _mel_gpu_modules[key]


def melspectrogram_gpu(wav: np.ndarray, device) -> np.ndarray:
    """
    与 melspectrogram 语义对齐的 GPU 路径：preemphasis + MelSpectrogram(magnitude) + dB + normalize。
    需 torchaudio；不支持 hp.use_lws=True。
    """
    if hp.use_lws:
        raise RuntimeError("melspectrogram_gpu 不支持 use_lws=True")
    if torch is None:
        raise RuntimeError("torch 未安装")
    wav_np = np.ascontiguousarray(wav, dtype=np.float32)
    wav_t = torch.from_numpy(wav_np).to(device)
    wav_t = _preemphasis_torch(wav_t, hp.preemphasis, hp.preemphasize)
    mel_xform = _mel_spectrogram_module_gpu(device)
    wav_batched = wav_t.unsqueeze(0)
    spec = mel_xform(wav_batched)
    spec = spec.squeeze(0)
    S = _amp_to_db_torch(spec) - hp.ref_level_db
    if hp.signal_normalization:
        S = _normalize_torch(S)
    return S.detach().cpu().numpy()


def melspectrogram_compare_gpu_cpu(wav: np.ndarray, device) -> Tuple[float, float]:
    """A/B：返回 (max_abs_diff, mean_abs_diff)。"""
    a = melspectrogram(wav)
    b = melspectrogram_gpu(wav, device)
    d = np.abs(a.astype(np.float64) - b.astype(np.float64))
    return float(d.max()), float(d.mean())

def _lws_processor():
    import lws
    return lws.lws(hp.n_fft, get_hop_size(), fftsize=hp.win_size, mode="speech")

def _stft(y):
    if hp.use_lws:
        return _lws_processor(hp).stft(y).T
    else:
        return librosa.stft(y=y, n_fft=hp.n_fft, hop_length=get_hop_size(), win_length=hp.win_size)

##########################################################
#Those are only correct when using lws!!! (This was messing with Wavenet quality for a long time!)
def num_frames(length, fsize, fshift):
    """Compute number of time frames of spectrogram
    """
    pad = (fsize - fshift)
    if length % fshift == 0:
        M = (length + pad * 2 - fsize) // fshift + 1
    else:
        M = (length + pad * 2 - fsize) // fshift + 2
    return M


def pad_lr(x, fsize, fshift):
    """Compute left and right padding
    """
    M = num_frames(len(x), fsize, fshift)
    pad = (fsize - fshift)
    T = len(x) + 2 * pad
    r = (M - 1) * fshift + fsize - T
    return pad, pad + r
##########################################################
#Librosa correct padding
def librosa_pad_lr(x, fsize, fshift):
    return 0, (x.shape[0] // fshift + 1) * fshift - x.shape[0]

# Conversions
_mel_basis = None

def _linear_to_mel(spectogram):
    global _mel_basis
    if _mel_basis is None:
        _mel_basis = _build_mel_basis()
    return np.dot(_mel_basis, spectogram)

def _build_mel_basis():
    assert hp.fmax <= hp.sample_rate // 2
    return librosa.filters.mel(sr=float(hp.sample_rate), n_fft=hp.n_fft, n_mels=hp.num_mels,
                               fmin=hp.fmin, fmax=hp.fmax)

def _amp_to_db(x):
    min_level = np.exp(hp.min_level_db / 20 * np.log(10))
    return 20 * np.log10(np.maximum(min_level, x))

def _db_to_amp(x):
    return np.power(10.0, (x) * 0.05)

def _normalize(S):
    if hp.allow_clipping_in_normalization:
        if hp.symmetric_mels:
            return np.clip((2 * hp.max_abs_value) * ((S - hp.min_level_db) / (-hp.min_level_db)) - hp.max_abs_value,
                           -hp.max_abs_value, hp.max_abs_value)
        else:
            return np.clip(hp.max_abs_value * ((S - hp.min_level_db) / (-hp.min_level_db)), 0, hp.max_abs_value)
    
    assert S.max() <= 0 and S.min() - hp.min_level_db >= 0
    if hp.symmetric_mels:
        return (2 * hp.max_abs_value) * ((S - hp.min_level_db) / (-hp.min_level_db)) - hp.max_abs_value
    else:
        return hp.max_abs_value * ((S - hp.min_level_db) / (-hp.min_level_db))

def _denormalize(D):
    if hp.allow_clipping_in_normalization:
        if hp.symmetric_mels:
            return (((np.clip(D, -hp.max_abs_value,
                              hp.max_abs_value) + hp.max_abs_value) * -hp.min_level_db / (2 * hp.max_abs_value))
                    + hp.min_level_db)
        else:
            return ((np.clip(D, 0, hp.max_abs_value) * -hp.min_level_db / hp.max_abs_value) + hp.min_level_db)
    
    if hp.symmetric_mels:
        return (((D + hp.max_abs_value) * -hp.min_level_db / (2 * hp.max_abs_value)) + hp.min_level_db)
    else:
        return ((D * -hp.min_level_db / hp.max_abs_value) + hp.min_level_db)
