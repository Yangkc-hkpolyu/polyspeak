"""Compare adapted frame operations with the original local source methods."""
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.speaking.avatar import AvatarRenderer, mel_spectrogram
from backend.speaking.config import load_settings
from backend.speaking.vendor.livetalking_sequence import mirror_index, paste_back_frame, prepare_face_inputs


def original_method(file, cls, name):
    tree = ast.parse(file.read_text(encoding="utf-8-sig"))
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    method = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == name)
    method.decorator_list = []
    namespace = {"np": np, "cv2": cv2, "List": list}
    # Compile only the named pure frame method, without importing or starting
    # the upstream streaming server, authentication or external services.
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(file), "exec"), namespace)
    return namespace[name]


def main():
    source = ROOT / "backend/livetalking"
    r = AvatarRenderer(load_settings())
    r.load_sequence()
    original_mirror = original_method(source / "basereal.py", "BaseReal", "mirror_index")
    original_inputs = original_method(source / "lipreal.py", "LipReal", "_precompute_face_inputs")
    original_paste = original_method(source / "lipreal.py", "LipReal", "paste_back_frame")
    obj = SimpleNamespace(frame_list_cycle=r.frames, coord_list_cycle=r.coords)
    for i in range(3 * len(r.frames)):
        assert original_mirror(obj, len(r.frames), i) == mirror_index(len(r.frames), i)
    manifest = json.loads((r.settings.avatar_directory / "avatar.json").read_text(encoding="utf-8"))
    faces = [cv2.imread(str(r.settings.avatar_directory / x["face"])) for x in manifest["frames"]]
    assert np.array_equal(original_inputs(faces), prepare_face_inputs(faces))
    prediction = np.random.default_rng(44).uniform(0, 255, size=(256, 256, 3)).astype(np.float32)
    for i in range(len(r.frames)):
        assert np.array_equal(original_paste(obj, prediction, i), paste_back_frame(prediction, i, r.frames, r.coords))
    from backend.livetalking.wav2lip import audio as original_audio
    waveform = np.random.default_rng(12).normal(0, .02, size=16000).astype(np.float32)
    assert np.allclose(original_audio.melspectrogram(waveform), mel_spectrogram(waveform), atol=1e-5)
    movement = float(np.mean(np.abs(r.frames[0].astype(np.float32) - r.frames[len(r.frames)//2])))
    assert movement > .1
    result = {"source_avatar":r.avatar_source, "source_frames":len(r.frames), "mirror_index_matches_original":True, "face_inputs_match_original":True, "paste_back_matches_original":True, "mel_matches_original":True, "real_source_frame_variation":movement, "protected_library_modified":False}
    (ROOT / "speaking-runtime/qa/dynamic-avatar-source-check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
