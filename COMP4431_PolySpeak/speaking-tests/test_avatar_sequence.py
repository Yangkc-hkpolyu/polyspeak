from dataclasses import replace
import json

import numpy as np
import pytest

from backend.speaking.avatar import AvatarRenderer, select_device, apply_scene_face_mask
from backend.speaking.config import Settings
from backend.speaking.motion import build_motion_cycle
from backend.speaking.vendor.livetalking_sequence import mirror_index, paste_back_frame, prepare_face_inputs


def test_dynamic_cycle_and_face_paste_preserve_source_motion():
    assert [mirror_index(3, i) for i in range(9)] == [0, 1, 2, 2, 1, 0, 0, 1, 2]
    frames = [np.full((20, 30, 3), v, np.uint8) for v in (20, 60)]
    prediction = np.full((256, 256, 3), 200, np.float32)
    coords = [(5, 10, 10, 20)] * 2
    rendered = paste_back_frame(prediction, 1, frames, coords)
    assert np.all(rendered[5:10, 10:20] == 200)
    assert np.all(rendered[:5] == 60)
    assert np.all(frames[1] == 60)
    faces = [np.full((256, 256, 3), 100, np.uint8), np.full((256, 256, 3), 150, np.uint8)]
    inputs = prepare_face_inputs(faces)
    assert inputs.shape == (2, 6, 256, 256)
    assert np.all(inputs[:, :3, 128:] == 0)
    assert not np.array_equal(inputs[0], inputs[1])


def test_avatar_frames_cannot_escape_the_asset_directory(tmp_path):
    record = {"full": "../outside.png", "face": "face.png", "coords": [0, 10, 0, 10]}
    (tmp_path / "avatar.json").write_text(json.dumps({"fps": 25, "frames": [record, record]}))
    renderer = AvatarRenderer(replace(Settings(), avatar_directory=tmp_path))
    with pytest.raises(ValueError, match="越界"):
        renderer.load_sequence()


def test_cache_changes_with_avatar_manifest_and_device_selection(monkeypatch, tmp_path):
    path = tmp_path / "avatar.json"
    path.write_text('{"id":"one"}')
    renderer = AvatarRenderer(replace(Settings(), avatar_directory=tmp_path))
    old = renderer.cache_key
    path.write_text('{"id":"two"}')
    assert old != renderer.cache_key
    monkeypatch.setattr("torch.cuda.is_available", lambda: False)
    monkeypatch.setattr("torch.backends.mps.is_available", lambda: True)
    assert select_device("auto") == "mps"
    assert select_device("cpu") == "cpu"
    monkeypatch.setattr("torch.backends.mps.is_available", lambda: False)
    assert select_device("auto") == "cpu"
    with pytest.raises(RuntimeError):
        select_device("cuda")


def test_scene_mask_blocks_office_pixels_without_removing_lip_animation():
    prepared = np.full((10, 12, 3), 180, np.uint8)
    predicted = prepared.copy()
    predicted[2:6, 3:7] = [30, 80, 120]
    mask = np.zeros((4, 4), np.uint8)
    mask[1:3, 1:3] = 255
    rendered = apply_scene_face_mask(predicted, prepared, (2, 6, 3, 7), mask)
    assert np.array_equal(rendered[3:5, 4:6], np.full((2, 2, 3), [30, 80, 120]))
    assert np.array_equal(rendered[2, 3:7], prepared[2, 3:7])
    assert np.array_equal(rendered[:2], prepared[:2])
    assert np.all(prepared == 180)


def test_calm_base_motion_reduces_blinks_without_slowing_each_blink():
    original = build_motion_cycle(64)
    calm = build_motion_cycle(64, [1 if 37 <= i <= 49 else 3 for i in range(64)])
    assert len(original) == 128
    assert len(calm) == 332
    def closures(cycle):
        states = [40 <= cycle[i % len(cycle)] <= 44 for i in range(60 * 25)]
        starts = [i for i, state in enumerate(states) if state and (i == 0 or not states[i - 1])]
        lengths = [next((j - i for j in range(i + 1, len(states)) if not states[j]), len(states) - i) for i in starts]
        return starts, lengths
    old_events, old_lengths = closures(original)
    new_events, new_lengths = closures(calm)
    assert len(new_events) <= len(old_events) / 2
    assert set(new_lengths) == set(old_lengths) == {5}
    assert set(calm) == set(range(64))
    with pytest.raises(ValueError):
        build_motion_cycle(2, [True, 3])
    with pytest.raises(ValueError):
        build_motion_cycle(2, [3])
