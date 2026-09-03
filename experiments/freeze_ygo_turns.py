from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "question_sources" / "raw" / "ygo-turns"
REVISION = "1661a60c2bf1a093e110d81825edcf63acda2611"
FILES = {
    "README.md": {
        "size": 2786,
        "git_blob_sha1": "2842f7ca1f20c964bf13d0c3786f7c0d900858b0",
    },
    "ygo-turns.parquet": {
        "size": 1740463,
        "sha256": "9c5a79931336e854f87d63cdcd62357d80c77a15c5e25edfdbed986d551b3077",
    },
}
USER_AGENT = "YGO-Bench academic question-source freezer/0.1"


def git_blob_sha1(body: bytes) -> str:
    header = f"blob {len(body)}\0".encode()
    return hashlib.sha1(header + body).hexdigest()


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError(f"Hugging Face mirror returned HTTP {response.status}")
        return response.read()


def verify(name: str, body: bytes) -> dict[str, str | int]:
    expected = FILES[name]
    if len(body) != expected["size"]:
        raise ValueError(
            f"Unexpected size for {name}: {len(body)} != {expected['size']}"
        )
    sha256 = hashlib.sha256(body).hexdigest()
    if "sha256" in expected and sha256 != expected["sha256"]:
        raise ValueError(f"Unexpected SHA-256 for {name}: {sha256}")
    blob_sha1 = git_blob_sha1(body)
    if "git_blob_sha1" in expected and blob_sha1 != expected["git_blob_sha1"]:
        raise ValueError(f"Unexpected Git blob SHA-1 for {name}: {blob_sha1}")
    return {
        "bytes": len(body),
        "sha256": sha256,
        "git_blob_sha1": blob_sha1,
    }


def write_atomic(path: Path, body: bytes) -> None:
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError(f"Existing snapshot differs from source: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.part")
    if partial.exists():
        raise FileExistsError(f"Stale partial download exists: {partial}")
    partial.write_bytes(body)
    partial.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze the YGO-Turns dataset")
    parser.add_argument("--endpoint", default="https://hf-mirror.com")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = []
    for name in FILES:
        url = (
            f"{args.endpoint}/datasets/Rifa456/YGO-Turns/resolve/"
            f"{REVISION}/{name}"
        )
        body = download(url)
        checksums = verify(name, body)
        path = OUTPUT / name
        write_atomic(path, body)
        artifacts.append(
            {"url": url, "path": path.relative_to(ROOT).as_posix(), **checksums}
        )
    manifest = {
        "source_id": "ygo-turns",
        "repository": "Rifa456/YGO-Turns",
        "revision": REVISION,
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "license": "CC-BY-4.0",
        "artifacts": artifacts,
    }
    manifest_path = ROOT / "tmp" / "ygo-turns-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
