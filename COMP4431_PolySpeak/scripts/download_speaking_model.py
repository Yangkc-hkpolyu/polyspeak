"""Fetch the reference project's exact Wav2Lip checkpoint with checksum verification."""
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.parse
import urllib.request
import http.cookiejar

ROOT = Path(__file__).resolve().parent.parent
SOURCE = json.loads((ROOT / "speaking-models" / "source.json").read_text(encoding="utf-8"))
SHARE_URL = SOURCE["share_url"]
TAR_SHA256 = SOURCE["archive_sha256"]


def main():
    target = ROOT / "speaking-models" / "wav2lip.pth"
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != SOURCE["file_sha256"]:
            raise RuntimeError("Existing model checksum differs from the source manifest; no file was replaced.")
        print("Model already exists:", target, flush=True)
        return
    archive = ROOT / "speaking-models" / "wav2lip-model.tar.part"
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    parts = urllib.parse.urlsplit(SHARE_URL)
    query = urllib.parse.parse_qs(parts.query)
    query["download"] = ["1"]
    url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query, doseq=True)))
    print("Downloading verified reference-project model...", flush=True)
    digest = hashlib.sha256()
    with opener.open(url, timeout=90) as response, archive.open("wb") as output:
        count = 0
        last_print = 0
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
            count += len(chunk)
            if count - last_print >= 20 * 1024 * 1024:
                print(f"Downloaded {count / 1024 / 1024:.0f} MB", flush=True)
                last_print = count
    if digest.hexdigest() != TAR_SHA256:
        raise RuntimeError("Downloaded asset failed SHA-256 verification. No model installed.")
    with tarfile.open(archive) as tar:
        members = [m for m in tar.getmembers() if Path(m.name).name == "wav2lip.pth" and m.isfile()]
        if len(members) != 1:
            raise RuntimeError("Archive does not contain exactly one wav2lip.pth.")
        # Copy one verified regular file; never extract arbitrary archive paths.
        source = tar.extractfile(members[0])
        with target.open("wb") as out:
            while chunk := source.read(1024 * 1024):
                out.write(chunk)
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    if checksum != SOURCE["file_sha256"]:
        raise RuntimeError("Extracted checkpoint checksum differs from the verified manifest.")
    (ROOT / "speaking-models" / "installed.json").write_text(
        json.dumps({"file": target.name, "sha256": checksum, "archive_sha256": TAR_SHA256}, indent=2),
        encoding="utf-8",
    )
    archive.unlink()
    print("Installed model:", target, flush=True)


if __name__ == "__main__":
    main()

