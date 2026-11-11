"""Download publicly released official study documents; preserve their originals."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import httpx
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.speaking.bank import SOURCES


def fetch(source):
    folder = ROOT / "speaking-resources/official"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / source["filename"]
    if not target.exists():
        response = httpx.get(source["url"], follow_redirects=True, timeout=90)
        response.raise_for_status()
        if not response.content.startswith(b"%PDF"):
            raise ValueError("Not a PDF: " + source["id"])
        target.write_bytes(response.content)
    reader = PdfReader(target)
    return {**source, "downloaded_on": "2026-10-24", "page_count": len(reader.pages), "bytes": target.stat().st_size, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch, item): item for item in SOURCES}
        for future, source in futures.items():
            try:
                result = future.result()
                results.append(result)
                print(source["id"], result["page_count"], "pages")
            except Exception as exc:
                results.append({**source, "download_error": str(exc)})
                print(source["id"], "DOWNLOAD FAILED:", str(exc))
    (ROOT / "speaking-resources/manifest.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
