from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "understanding-pilot-v0.1.json"
CARD_OUTPUT = ROOT / "data" / "source_samples" / "konami" / "understanding-pilot"
RULE_OUTPUT = ROOT / "data" / "source_samples" / "official_rules"
MANIFEST_PATH = CARD_OUTPUT / "manifest.json"
CARD_URL = (
    "https://www.db.yugioh-card.com/yugiohdb/card_search.action"
    "?ope=2&cid={cid}&request_locale={locale}"
)
RULE_SOURCES = (
    {
        "source_id": "konami-fast-effect-timing-2026-08-26",
        "url": "https://www.yugioh-card.com/en/play/fast-effect-timing/",
        "path": RULE_OUTPUT / "fast_effect_timing_2026-08-26.html",
    },
    {
        "source_id": "konami-psct-2026-08-26",
        "url": "https://www.yugioh-card.com/en/play/psct/",
        "path": RULE_OUTPUT / "psct_2026-08-26.html",
    },
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def download(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "YGO-Bench academic source freezer/0.1"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"Source returned HTTP {response.status}: {url}")
        body = response.read()
    if not body:
        raise ValueError(f"Source returned an empty response: {url}")
    return body


def clean_fragment(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    lines = [" ".join(line.split()) for line in html.unescape(fragment).splitlines()]
    return "\n".join(line for line in lines if line)


def parse_card_page(body: bytes) -> tuple[str, str]:
    source = body.decode("utf-8")
    name_match = re.search(
        r'<div\s+id="cardname"[^>]*>.*?<h1>(.*?)</h1>',
        source,
        flags=re.DOTALL,
    )
    text_match = re.search(
        r'<div\s+class="item_box_text">\s*'
        r'<div\s+class="text_title">\s*Card Text\s*</div>(.*?)</div>',
        source,
        flags=re.DOTALL,
    )
    if not name_match or not text_match:
        raise ValueError("Official card page does not contain the expected card block")
    name = clean_fragment(name_match.group(1))
    name_lines = name.splitlines()
    if name_lines and len(set(name_lines)) == 1:
        name = name_lines[0]
    card_text = clean_fragment(text_match.group(1))
    if not name or not card_text:
        raise ValueError("Official card page has an empty card name or card text")
    return name, card_text


def write_new(path: Path, value: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"Frozen source already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("pilot_id") != "understanding-pilot-v0.1":
        raise ValueError(f"Unexpected Understanding pilot config: {path}")
    if len(payload.get("cards", [])) != 12:
        raise ValueError("Understanding pilot source freezer requires exactly 12 cards")
    return payload


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def collect_card_sources(
    config: dict[str, Any], retrieved_at: str
) -> tuple[list[dict[str, Any]], list[tuple[Path, bytes]]]:
    artifacts = []
    files = []
    for card in config["cards"]:
        card_id = int(card["card_id"])
        cid = int(card["konami_cid"])
        expected_name = str(card["name"])
        for locale, regulation in (("en", "TCG"), ("ae", "OCG")):
            url = CARD_URL.format(cid=cid, locale=locale)
            body = download(url)
            parsed_name, card_text = parse_card_page(body)
            if parsed_name != expected_name:
                raise ValueError(
                    f"KONAMI name mismatch for card {card_id} {locale}: "
                    f"expected {expected_name!r}, got {parsed_name!r}"
                )
            stem = f"card_cid_{cid}_{locale}"
            html_path = CARD_OUTPUT / f"{stem}.html"
            parsed_path = CARD_OUTPUT / f"{stem}.parsed.json"
            parsed = {
                "card_id": card_id,
                "konami_cid": cid,
                "locale": locale,
                "regulation": regulation,
                "name": parsed_name,
                "card_text": card_text,
                "source_url": url,
                "retrieved_at": retrieved_at,
                "source_sha256": sha256_bytes(body),
            }
            parsed_body = (
                json.dumps(parsed, ensure_ascii=False, indent=2) + "\n"
            ).encode(
                "utf-8"
            )
            files.extend(((html_path, body), (parsed_path, parsed_body)))
            artifacts.append(
                {
                    "source_id": f"konami-card-{cid}-{locale}",
                    "kind": "official_card_text",
                    "card_id": card_id,
                    "konami_cid": cid,
                    "locale": locale,
                    "regulation": regulation,
                    "url": url,
                    "path": relative(html_path),
                    "parsed_path": relative(parsed_path),
                    "retrieved_at": retrieved_at,
                    "sha256": sha256_bytes(body),
                }
            )
    return artifacts, files


def collect_rule_sources(
    retrieved_at: str,
) -> tuple[list[dict[str, Any]], list[tuple[Path, bytes]]]:
    artifacts = []
    files = []
    for source in RULE_SOURCES:
        body = download(str(source["url"]))
        path = Path(source["path"])
        files.append((path, body))
        artifacts.append(
            {
                "source_id": source["source_id"],
                "kind": "official_rule",
                "url": source["url"],
                "path": relative(path),
                "retrieved_at": retrieved_at,
                "sha256": sha256_bytes(body),
            }
        )
    return artifacts, files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze official source evidence for Understanding pilot candidates"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if MANIFEST_PATH.exists():
        raise FileExistsError(f"Understanding source manifest already exists: {MANIFEST_PATH}")
    config = load_config(args.config.resolve())
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    card_artifacts, card_files = collect_card_sources(config, retrieved_at)
    rule_artifacts, rule_files = collect_rule_sources(retrieved_at)
    artifacts = [*card_artifacts, *rule_artifacts]
    files = [*card_files, *rule_files]
    duplicate_paths = [
        str(path)
        for path, count in Counter(path for path, _ in files).items()
        if count > 1
    ]
    if duplicate_paths:
        raise ValueError(f"Duplicate frozen source output paths: {duplicate_paths}")
    existing_paths = [str(path) for path, _ in files if path.exists()]
    if existing_paths:
        raise FileExistsError(f"Frozen source outputs already exist: {existing_paths}")
    for path, body in files:
        write_new(path, body)
    manifest = {
        "source_set_id": "understanding-pilot-sources-v0.1",
        "retrieved_at": retrieved_at,
        "config": relative(args.config.resolve()),
        "artifacts": artifacts,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "manifest": relative(MANIFEST_PATH),
                "artifacts": len(artifacts),
                "card_pages": 24,
                "rule_pages": 2,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
