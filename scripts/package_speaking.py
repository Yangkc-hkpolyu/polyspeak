"""Package the runnable speaking product, excluding original private configuration."""
from pathlib import Path
import argparse
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.speaking.config import load_settings


def main(include_assets=False):
    output = ROOT / "output/COMP4431_PolySpeak_source.zip"
    output.parent.mkdir(exist_ok=True)
    files = ["README.md", "THIRD_PARTY_SPEAKING.md", "requirements-speaking.txt", "speaking.env.example", "run-speaking.py", "start-speaking.bat", "speaking-models/source.json", "frontend/package.json", "frontend/package-lock.json", "frontend/vue.config.js", "frontend/babel.config.js", "frontend/public/speaking.html", "frontend/src/speaking-main.js", "frontend/scripts/speaking.cjs", "speaking-resources/manifest.json", "docs/SPEAKING_RESEARCH.md", "docs/SPEAKING_AVATAR.md", "docs/SPEAKING_TESTING.md"]
    files.extend(["requirements-voice-coach.txt", "scripts/setup_voice_coach.py", "scripts/verify_voice_coach_ui.cjs", "docs/SPEAKING_VOICE_COACH.md"])
    for directory in ("backend/speaking", "frontend/src/speaking", "frontend/dist-speaking", "speaking-tests", "experiments/voice-coach"):
        files.extend(p.relative_to(ROOT).as_posix() for p in (ROOT / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    files.append("docs/SPEAKING_QUESTION_BANK.md")
    files.append("docs/IELTS_ROOM_PROMPT.md")
    files.append("scripts/prepare_exam_room.py")
    files.extend("scripts/" + name for name in ["port_speaking_realtime.py", "verify_realtime_speaking.cjs", "verify_realtime_mock.cjs", "assert_english_ui.cjs", "verify_speaking_stream.py"])
    files.append("docs/SPEAKING_REALTIME.md")
    files.append("start-speaking.sh")
    files.extend("deploy/speaking/" + name for name in ["Dockerfile", "Dockerfile.dockerignore", "start.sh", "compose.yaml", "Caddyfile", "cloud.env.example", "README.md"])
    files.extend("scripts/" + name for name in ["install_speaking_assets.py", "download_speaking_model.py", "download_speaking_sources.py", "verify_speaking_live.py", "verify_question_bank.cjs", "prepare_speaking_avatar.py", "verify_dynamic_avatar.py", "verify_dynamic_avatar_browser.cjs", "package_speaking.py"])
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(set(files)):
            source = ROOT / name
            if not source.is_file():
                raise RuntimeError("Missing source deliverable: " + name)
            archive_name = "README.md" if name == "README.md" else name
            z.write(source, "COMP4431_PolySpeak/" + archive_name)
    with zipfile.ZipFile(output) as z:
        settings = load_settings()
        for name in z.namelist():
            if name.endswith((".pth", ".sqlite3")) or "/recordings/" in name or name.endswith("/backend/.env") or name.endswith("/speaking.env"):
                raise RuntimeError("Unexpected private file: " + name)
            for secret in (settings.api_key, settings.azure_key):
                if secret and secret.encode() in z.read(name):
                    raise RuntimeError("Configured credential in package")
        assert z.testzip() is None
        print(f"Verified source package: {len(z.namelist())} files, {output.stat().st_size / 1024 ** 2:.2f} MB")
    print(output)
    if include_assets:
        settings = load_settings()
        if not settings.model_path.is_file() or not (settings.avatar_directory / "avatar.json").is_file():
            raise RuntimeError("Prepare the model and dynamic avatar before packaging assets")
        archive = ROOT / "output/COMP4431_PolySpeak_model_assets.zip"
        asset_files = [(settings.model_path, "speaking-models/wav2lip.pth")]
        asset_files += [(p, "speaking-models/avatars/nora/" + p.relative_to(settings.avatar_directory).as_posix()) for p in settings.avatar_directory.rglob("*") if p.is_file() and p.suffix in (".json", ".png", ".jpg")]
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as z:
            for source, relative in sorted(asset_files):
                z.write(source, "COMP4431_PolySpeak/" + relative)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            print(f"Verified model/assets package: {len(z.namelist())} files, {archive.stat().st_size / 1024 ** 2:.2f} MB")
        print(archive)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", action="store_true")
    main(parser.parse_args().assets)
