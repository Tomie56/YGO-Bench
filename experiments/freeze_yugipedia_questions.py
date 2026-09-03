from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "question_sources" / "raw" / "yugipedia-puzzles"
API_URL = "https://yugipedia.com/api.php"
USER_AGENT = "YGO-Bench academic question-source freezer/0.1"
TITLES = (
    "Duel Puzzle",
    "Duel Puzzle (Ultimate Masters: World Championship Tournament 2006 composition)",
    "Duel Puzzle Solutions (WC10)",
    "Duel Puzzle Solutions (WC11)",
    "Duel Quiz",
    "Duelist Challenges",
)


def api_url(query: dict[str, str | int]) -> str:
    return f"{API_URL}?{urllib.parse.urlencode(query)}"


def request_json(query: dict[str, str | int]) -> tuple[str, bytes, dict[str, Any]]:
    url = api_url(query)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError(f"Yugipedia returned HTTP {response.status}: {url}")
        body = response.read()
    if not body:
        raise ValueError(f"Yugipedia returned an empty response: {url}")
    return url, body, json.loads(body)


def write_atomic(path: Path, body: bytes) -> None:
    if path.exists():
        existing = path.read_bytes()
        if existing != body:
            raise ValueError(f"Existing Yugipedia snapshot changed: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.part")
    if partial.exists():
        raise FileExistsError(f"Stale partial Yugipedia download exists: {partial}")
    partial.write_bytes(body)
    partial.replace(path)


def request_or_existing(
    path: Path, query: dict[str, str | int]
) -> tuple[str, bytes, dict[str, Any]]:
    if path.exists():
        body = path.read_bytes()
        return api_url(query), body, json.loads(body)
    url, body, payload = request_json(query)
    write_atomic(path, body)
    return url, body, payload


def category_members() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    members = []
    artifacts = []
    continuation: str | None = None
    page = 1
    while True:
        query: dict[str, str | int] = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": "Category:Duel Puzzles",
            "cmnamespace": 0,
            "cmlimit": 500,
            "format": "json",
            "formatversion": 2,
        }
        if continuation:
            query["cmcontinue"] = continuation
        output_path = OUTPUT / f"category-members-page-{page:02d}.json"
        url, body, payload = request_or_existing(output_path, query)
        members.extend(payload["query"]["categorymembers"])
        artifacts.append(
            {
                "url": url,
                "path": output_path.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )
        continuation = payload.get("continue", {}).get("cmcontinue")
        if not continuation:
            break
        page += 1
        if page > 10:
            raise ValueError("Yugipedia Duel Puzzles category exceeded 10 pages")
    return members, artifacts


def freeze_pages(
    titles: list[str], output_prefix: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pages = []
    artifacts = []
    for batch_index, start in enumerate(range(0, len(titles), 50), start=1):
        batch = titles[start : start + 50]
        query: dict[str, str | int] = {
            "action": "query",
            "prop": "info|revisions",
            "inprop": "url",
            "rvprop": "ids|timestamp|content",
            "rvslots": "main",
            "titles": "|".join(batch),
            "redirects": 1,
            "format": "json",
            "formatversion": 2,
        }
        output_path = OUTPUT / f"{output_prefix}-batch-{batch_index:02d}.json"
        url, body, payload = request_or_existing(output_path, query)
        resolved = payload["query"]["pages"]
        missing = [page["title"] for page in resolved if page.get("missing")]
        if missing:
            raise FileNotFoundError(f"Yugipedia pages do not exist: {missing}")
        pages.extend(resolved)
        artifacts.append(
            {
                "url": url,
                "path": output_path.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )
    return pages, artifacts


def linked_puzzle_titles(pages: list[dict[str, Any]]) -> list[str]:
    titles = set()
    for page in pages:
        content = page["revisions"][0]["content"]
        for title in re.findall(r"\[\[([^]|#]+)", content):
            title = title.strip()
            if "Duel Puzzle" in title and not title.startswith("Category:"):
                titles.add(title)
    return sorted(titles)


def main() -> None:
    rights_query: dict[str, str | int] = {
        "action": "query",
        "meta": "siteinfo",
        "siprop": "general|rightsinfo",
        "format": "json",
        "formatversion": 2,
    }
    pages_query: dict[str, str | int] = {
        "action": "query",
        "prop": "info|revisions",
        "inprop": "url",
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "titles": "|".join(TITLES),
        "redirects": 1,
        "format": "json",
        "formatversion": 2,
    }
    rights_path = OUTPUT / "siteinfo-rights.json"
    pages_path = OUTPUT / "question-pages.json"
    rights_url, rights_body, rights = request_or_existing(rights_path, rights_query)
    pages_url, pages_body, pages = request_or_existing(pages_path, pages_query)
    resolved_pages = pages["query"]["pages"]
    missing = [page["title"] for page in resolved_pages if page.get("missing")]
    if missing:
        raise FileNotFoundError(f"Yugipedia pages do not exist: {missing}")
    members, category_artifacts = category_members()
    category_titles = sorted({member["title"] for member in members} | set(TITLES))
    category_pages, page_artifacts = freeze_pages(
        category_titles, "category-question-pages"
    )
    linked_titles = linked_puzzle_titles([*resolved_pages, *category_pages])
    linked_pages, linked_artifacts = freeze_pages(
        linked_titles, "linked-question-pages"
    )
    manifest = {
        "source_id": "yugipedia-puzzles",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "page_count": len(resolved_pages),
        "titles": [page["title"] for page in resolved_pages],
        "category_member_count": len(members),
        "frozen_unique_page_count": len(category_pages),
        "linked_puzzle_page_count": len(linked_pages),
        "rights": rights["query"]["rightsinfo"],
        "artifacts": [
            {
                "url": rights_url,
                "path": rights_path.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(rights_body).hexdigest(),
            },
            {
                "url": pages_url,
                "path": pages_path.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(pages_body).hexdigest(),
            },
            *category_artifacts,
            *page_artifacts,
            *linked_artifacts,
        ],
    }
    manifest_path = ROOT / "tmp" / "yugipedia-question-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
