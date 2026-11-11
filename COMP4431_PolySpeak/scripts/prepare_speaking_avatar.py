"""Prepare a dynamic avatar from the local E: PolyInterview asset copy.

The upstream folder is read-only. JSON coordinates replace its trusted pickle
in the portable product, and source frame hashes retain asset provenance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pickle
import shutil
import subprocess
import sys

import cv2
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.speaking.vendor.livetalking_sequence import mirror_index


def prepare(source, target, assets):
    source, target = source.resolve(), target.resolve()
    if source == target:
        raise ValueError("Source assets must remain unchanged")
    full = sorted((source / "full_imgs").glob("*.png"), key=lambda p: int(p.stem))
    faces = sorted((source / "face_imgs").glob("*.png"), key=lambda p: int(p.stem))
    # Only the project's pre-existing local avatar pickle is accepted here;
    # the runtime loader uses JSON and never unpickles uploaded material.
    with (source / "coords.pkl").open("rb") as stream:
        coords = pickle.load(stream)
    if not len(full) == len(faces) == len(coords) or len(full) < 2:
        raise ValueError("Avatar needs matching video frames, face frames and coordinates")
    records = []
    shape = cv2.imread(str(full[0])).shape
    for i, (frame, face, box) in enumerate(zip(full, faces, coords)):
        if frame.stem != face.stem:
            raise ValueError("Frame identities do not match")
        if cv2.imread(str(frame)).shape != shape or cv2.imread(str(face)).shape != (256, 256, 3):
            raise ValueError("Unexpected source dimensions")
        paths = []
        for folder, path in [("full_imgs", frame), ("face_imgs", face)]:
            dest = target / folder / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            paths.append(dest.relative_to(target).as_posix())
        records.append({"full": paths[0], "face": paths[1], "coords": [int(v) for v in box], "full_sha256": hashlib.sha256(frame.read_bytes()).hexdigest(), "face_sha256": hashlib.sha256(face.read_bytes()).hexdigest()})
    manifest = {"source": "User-provided PolyInterview / LiveTalking", "source_avatar": source.name, "display_name": "Nora", "fps": 25, "width": shape[1], "height": shape[0], "frames": records}
    (target / "avatar.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    assets.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(assets / "nora-dynamic.jpg"), cv2.imread(str(full[0])), [cv2.IMWRITE_JPEG_QUALITY, 95])
    video = assets / "nora-idle.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{shape[1]}x{shape[0]}", "-r", "25", "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(video)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(2 * len(full)):
            process.stdin.write(cv2.imread(str(full[mirror_index(len(full), i)])).tobytes())
        process.stdin.close()
        error = process.stderr.read()
        if process.wait(timeout=60):
            raise RuntimeError(error.decode(errors="replace"))
    except BaseException:
        process.kill()
        process.wait()
        raise
    print(json.dumps({"source_avatar": source.name, "frames": len(records), "size": [shape[1], shape[0]], "target": str(target), "idle_video": str(video)}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "backend/livetalking/data/avatars/Lisa")
    parser.add_argument("--target", type=Path, default=ROOT / "speaking-models/avatars/nora")
    args = parser.parse_args()
    prepare(args.source, args.target, ROOT / "backend/speaking/assets")
