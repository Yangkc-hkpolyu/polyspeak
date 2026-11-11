"""Rebuild the supplied dynamic avatar in a generated speaking-test room.

This offline video-asset preparation uses the official RVM TorchScript release.
Serving the resulting frames needs neither RVM nor extra runtime dependencies.
The supplied upstream folder is only read; face inputs and coordinates stay exact.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import cv2
import imageio_ffmpeg
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.speaking.motion import build_motion_cycle


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode_idle(frames, path, cycle=None):
    height, width = frames[0].shape[:2]
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
               "-r", "25", "-i", "pipe:0", "-an", "-c:v", "libx264",
               "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(path)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for index in cycle or build_motion_cycle(len(frames)):
            process.stdin.write(frames[index].tobytes())
        process.stdin.close()
        error = process.stderr.read()
        if process.wait(timeout=60):
            raise RuntimeError(error.decode(errors="replace"))
    except BaseException:
        process.kill()
        process.wait()
        raise


def prepare(model_path, apply=False):
    target = ROOT / "speaking-models/avatars/nora"
    source = ROOT / "backend/livetalking/data/avatars/Lisa"
    assets = ROOT / "backend/speaking/assets"
    work = ROOT / "speaking-runtime/background-preparation"
    work.mkdir(parents=True, exist_ok=True)
    stage = work / "ielts-room"
    (stage / "full_imgs").mkdir(parents=True, exist_ok=True)
    (stage / "lip_masks").mkdir(parents=True, exist_ok=True)
    manifest = json.loads((target / "avatar.json").read_text(encoding="utf-8"))
    background_path = assets / "ielts-room-desk.png"
    background = cv2.imread(str(background_path))
    if background is None:
        raise ValueError("Missing generated room background")
    size = (manifest["width"], manifest["height"])
    background = cv2.resize(background, size, interpolation=cv2.INTER_AREA)
    # The generated background's measured tabletop edge is y=810 / 941.
    # Treat the entire desktop as a foreground layer, in front of the examiner.
    desk_edge_y = round(size[1] * 810 / 941)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.set_num_threads(4)
    model = torch.jit.load(str(model_path), map_location=device).eval()
    states = [None] * 4
    frames, records, source_hashes = [], [], []
    with torch.inference_mode():
        # Warm recurrent states on the first frame rather than resetting each frame.
        for index in [0] * 8 + list(range(len(manifest["frames"]))):
            item = manifest["frames"][index]
            original_path = source / item["full"]
            original = cv2.imread(str(original_path))
            if original is None or original.shape[:2] != size[::-1]:
                raise ValueError("Source video dimensions differ")
            rgb = cv2.cvtColor(original, cv2.COLOR_BGR2RGB)
            tensor = torch.from_numpy(rgb.transpose(2, 0, 1).copy()).float()[None].to(device) / 255
            foreground, alpha, *states = model(tensor, *states, 0.5)
            matte = alpha[0, 0].cpu().numpy()
            foreground = foreground[0].permute(1, 2, 0).cpu().numpy()[..., ::-1] * 255
            y1, y2, x1, x2 = item["coords"]
            # Exclude disconnected foreground mistakes such as the old laptop.
            _, labels = cv2.connectedComponents((matte > 0.08).astype(np.uint8))
            person_label = labels[(y1 + y2) // 2, (x1 + x2) // 2]
            if person_label == 0:
                raise ValueError("Matting did not find the examiner")
            support = cv2.dilate((labels == person_label).astype(np.uint8), np.ones((5, 5), np.uint8))
            matte *= support
            matte[matte < 0.02] = 0
            # Preserve original opaque interior pixels, without forcing background
            # corners of the rectangular face ROI to become foreground.
            foreground[matte > 0.98] = original[matte > 0.98]
            matte[matte > 0.98] = 1
            composite = np.clip(foreground * matte[..., None] + background * (1 - matte[..., None]), 0, 255).round().astype(np.uint8)
            composite[desk_edge_y:] = background[desk_edge_y:]
            # Retain visible attribution when replacing the source room.
            cv2.putText(composite, "LiveTalking", (10, 20), cv2.FONT_HERSHEY_SIMPLEX,
                        0.28, (150, 150, 150), 1, cv2.LINE_AA)
            output = stage / item["full"]
            cv2.imwrite(str(output), composite)
            mask_name = "lip_masks/" + output.name
            cv2.imwrite(str(stage / mask_name), (matte[y1:y2, x1:x2] * 255).round().astype(np.uint8))
            if index == 0:
                cv2.imwrite(str(work / "matte-preview.png"), (matte * 255).astype(np.uint8))
            # Warmup entries overwrite frame zero; collect only the full chronological pass.
            if len(frames) == index:
                frames.append(composite)
                digest = sha(original_path)
                source_hashes.append(digest)
                face_path = source / item["face"]
                if sha(target / item["face"]) != sha(face_path):
                    raise ValueError("Face input changed from the supplied source")
                records.append({**item, "full_sha256": sha(output), "original_full_sha256": digest,
                                "lip_mask": mask_name, "lip_mask_sha256": sha(stage / mask_name)})
            else:
                frames[0] = composite
                records[0] = {**records[0], "full_sha256": sha(output), "lip_mask_sha256": sha(stage / mask_name)}
    # Lisa's source blink occurs around frames 38--49. Keep that movement at
    # its native speed while slowing open-eye head/body motion to one third.
    repeats = [1 if 37 <= index <= 49 else 3 for index in range(len(frames))]
    cycle = build_motion_cycle(len(frames), repeats)
    manifest = {**manifest, "frames": records, "source_frame_repeats": repeats, "scene": {
        "id": "ielts-practice-room-v2-desk", "background_sha256": sha(background_path),
        "foreground_desk_y": desk_edge_y,
        "generation": "built-in imagegen, reference-assisted generation",
        "matting": "offline Robust Video Matting mobilenetv3 fp32, recurrent states retained",
        "matting_model_sha256": sha(model_path),
        "description": "Fictional English speaking-test practice room"}}
    (stage / "avatar.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    encode_idle(frames, stage / "nora-idle.mp4", cycle)
    cv2.imwrite(str(stage / "nora-dynamic.jpg"), frames[0], [cv2.IMWRITE_JPEG_QUALITY, 95])
    tiles = [cv2.resize(frames[i], (638, 360)) for i in (0, 16, 32, 48)]
    cv2.imwrite(str(work / "room-motion-contact.jpg"), np.vstack([np.hstack(tiles[:2]), np.hstack(tiles[2:])]))
    if apply:
        (target / "lip_masks").mkdir(exist_ok=True)
        for item in records:
            shutil.copy2(stage / item["full"], target / item["full"])
            shutil.copy2(stage / item["lip_mask"], target / item["lip_mask"])
        shutil.copy2(stage / "avatar.json", target / "avatar.json")
        for name in ("nora-idle.mp4", "nora-dynamic.jpg"):
            temporary = assets / (name + ".new")
            shutil.copy2(stage / name, temporary)
            temporary.replace(assets / name)
    # Confirm no operation wrote into the protected source asset directory.
    assert source_hashes == [sha(source / item["full"]) for item in records]
    result = {"scene": manifest["scene"], "frames": len(frames), "size": size,
              "cycle_video_frames": len(cycle), "cycle_seconds": len(cycle) / 25,
              "source_unchanged": True, "face_inputs_unchanged": True,
              "applied": apply, "device": device}
    (work / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=ROOT / "speaking-runtime/background-preparation/rvm_mobilenetv3_fp32.torchscript")
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    prepare(arguments.model, arguments.apply)
