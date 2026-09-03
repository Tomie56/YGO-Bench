from __future__ import annotations

import argparse
import base64
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "question-source-census-v0.1.json"
USER_AGENT = "YGO-Bench academic question-source freezer/0.1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError(f"Source returned HTTP {response.status}: {url}")
        body = response.read()
    if not body:
        raise ValueError(f"Source returned an empty response: {url}")
    return body


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("source_set_id") != "question-source-census-v0.1":
        raise ValueError(f"Unexpected question source config: {path}")
    source_ids = [source["source_id"] for source in config.get("sources", [])]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Question source config contains duplicate source_id values")
    return config


def github_tree(repository: str, revision: str) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repository}/git/trees/{revision}?recursive=1"
    payload = json.loads(request_bytes(url))
    if payload.get("truncated"):
        raise ValueError(f"GitHub returned a truncated tree for {repository}@{revision}")
    return payload["tree"]


def select_blobs(
    tree: list[dict[str, Any]],
    include_paths: list[str],
    include_prefixes: list[str],
) -> list[dict[str, Any]]:
    exact = set(include_paths)
    selected = [
        entry
        for entry in tree
        if entry["type"] == "blob"
        and (
            entry["path"] in exact
            or any(entry["path"].startswith(prefix) for prefix in include_prefixes)
        )
    ]
    selected_paths = {entry["path"] for entry in selected}
    missing = sorted(exact - selected_paths)
    if missing:
        raise FileNotFoundError(f"Configured GitHub paths do not exist: {missing}")
    if not selected:
        raise ValueError("GitHub source selector produced no files")
    return sorted(selected, key=lambda entry: (int(entry["size"]), entry["path"]))


def raw_url(repository: str, revision: str, path: str) -> str:
    encoded_path = urllib.parse.quote(path)
    return f"https://raw.githubusercontent.com/{repository}/{revision}/{encoded_path}"


def github_blob(repository: str, sha: str) -> bytes:
    url = f"https://api.github.com/repos/{repository}/git/blobs/{sha}"
    payload = json.loads(request_bytes(url))
    if payload.get("encoding") != "base64":
        raise ValueError(f"Unexpected GitHub blob encoding for {repository}@{sha}")
    return base64.b64decode(payload["content"])


def download_blob(
    repository: str,
    sha: str,
    output_path: Path,
    expected_size: int,
) -> None:
    if output_path.exists():
        actual_size = output_path.stat().st_size
        if actual_size != expected_size:
            raise ValueError(
                f"Existing source has wrong size: {output_path} "
                f"(expected {expected_size}, got {actual_size})"
            )
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(f"{output_path.name}.part")
    if partial.exists():
        raise FileExistsError(f"Stale partial source download exists: {partial}")
    body = github_blob(repository, sha)
    if len(body) != expected_size:
        raise ValueError(
            f"Downloaded source has wrong size: {repository}@{sha} "
            f"(expected {expected_size}, got {len(body)})"
        )
    partial.write_bytes(body)
    partial.replace(output_path)


def freeze_source(source: dict[str, Any], output_root: Path) -> dict[str, Any]:
    source_id = source["source_id"]
    repository = source["repository"]
    revision = source["revision"]
    tree = github_tree(repository, revision)
    blobs = select_blobs(
        tree,
        list(source.get("include_paths", [])),
        list(source.get("include_prefixes", [])),
    )
    artifacts = []
    for blob in blobs:
        path = blob["path"]
        url = raw_url(repository, revision, path)
        output_path = output_root / source_id / path
        download_blob(repository, blob["sha"], output_path, int(blob["size"]))
        artifacts.append(
            {
                "path": output_path.relative_to(ROOT).as_posix(),
                "source_path": path,
                "url": url,
                "blob_sha": blob["sha"],
                "bytes": output_path.stat().st_size,
                "sha256": sha256_file(output_path),
            }
        )
    return {
        "source_id": source_id,
        "repository": repository,
        "revision": revision,
        "artifact_count": len(artifacts),
        "total_bytes": sum(item["bytes"] for item in artifacts),
        "artifacts": artifacts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze fixed GitHub question sources for the source census"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--source", action="append", default=[])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    config = load_config(config_path)
    requested = set(args.source)
    sources = [
        source
        for source in config["sources"]
        if not requested or source["source_id"] in requested
    ]
    available = {source["source_id"] for source in config["sources"]}
    unknown = sorted(requested - available)
    if unknown:
        raise ValueError(f"Unknown question source_id values: {unknown}")
    output_root = ROOT / config["output_root"]
    output_root.mkdir(parents=True, exist_ok=True)
    frozen = [freeze_source(source, output_root) for source in sources]
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = {
        "source_set_id": config["source_set_id"],
        "retrieved_at": retrieved_at,
        "config": config_path.relative_to(ROOT).as_posix(),
        "sources": frozen,
    }
    manifest_path = ROOT / "tmp" / "question-source-github-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "manifest": manifest_path.relative_to(ROOT).as_posix(),
                "sources": len(frozen),
                "artifacts": sum(item["artifact_count"] for item in frozen),
                "bytes": sum(item["total_bytes"] for item in frozen),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
