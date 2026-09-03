from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "question_sources" / "raw" / "stackexchange-boardgames-yu-gi-oh"
API_ROOT = "https://api.stackexchange.com/2.3"
USER_AGENT = "YGO-Bench academic question-source freezer/0.1"


def request_json(url: str) -> tuple[bytes, dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError(f"Stack Exchange returned HTTP {response.status}: {url}")
        body = response.read()
    if not body:
        raise ValueError(f"Stack Exchange returned an empty response: {url}")
    return body, json.loads(body)


def write_atomic(path: Path, body: bytes) -> None:
    if path.exists():
        existing = path.read_bytes()
        if existing != body:
            raise ValueError(f"Existing Stack Exchange page changed: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.part")
    if partial.exists():
        raise FileExistsError(f"Stale partial Stack Exchange download exists: {partial}")
    partial.write_bytes(body)
    partial.replace(path)


def api_url(path: str, query: dict[str, str | int]) -> str:
    return f"{API_ROOT}/{path}?{urllib.parse.urlencode(query)}"


def download_questions() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pages = []
    questions = []
    page = 1
    while True:
        url = api_url(
            "questions",
            {
                "site": "boardgames",
                "tagged": "yu-gi-oh",
                "pagesize": 100,
                "page": page,
                "filter": "withbody",
            },
        )
        body, payload = request_json(url)
        output_path = OUTPUT / f"questions-page-{page:02d}.json"
        write_atomic(output_path, body)
        questions.extend(payload["items"])
        pages.append(
            {
                "url": url,
                "path": output_path.relative_to(ROOT).as_posix(),
                "items": len(payload["items"]),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )
        if not payload["has_more"]:
            break
        page += 1
        if page > 10:
            raise ValueError("Stack Exchange question pagination exceeded 10 pages")
    return pages, questions


def download_answers(questions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    pages = []
    answer_count = 0
    question_ids = [str(question["question_id"]) for question in questions]
    for batch_index, start in enumerate(range(0, len(question_ids), 100), start=1):
        batch = question_ids[start : start + 100]
        page = 1
        while True:
            url = api_url(
                f"questions/{';'.join(batch)}/answers",
                {
                    "site": "boardgames",
                    "pagesize": 100,
                    "page": page,
                    "filter": "withbody",
                },
            )
            body, payload = request_json(url)
            output_path = OUTPUT / (
                f"answers-batch-{batch_index:02d}-page-{page:02d}.json"
            )
            write_atomic(output_path, body)
            answer_count += len(payload["items"])
            pages.append(
                {
                    "url": url,
                    "path": output_path.relative_to(ROOT).as_posix(),
                    "items": len(payload["items"]),
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )
            if not payload["has_more"]:
                break
            page += 1
            if page > 10:
                raise ValueError(
                    f"Stack Exchange answer batch {batch_index} exceeded 10 pages"
                )
    return pages, answer_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze all Board & Card Games Yu-Gi-Oh questions and answers"
    )
    return parser.parse_args()


def main() -> None:
    parse_args()
    question_pages, questions = download_questions()
    answer_pages, answer_count = download_answers(questions)
    manifest = {
        "source_id": "stackexchange-boardgames-yu-gi-oh",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "api": API_ROOT,
        "site": "boardgames",
        "tag": "yu-gi-oh",
        "license_policy": "https://stackoverflow.com/help/licensing",
        "question_count": len(questions),
        "answer_count": answer_count,
        "question_pages": question_pages,
        "answer_pages": answer_pages,
    }
    manifest_path = ROOT / "tmp" / "stackexchange-yu-gi-oh-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
