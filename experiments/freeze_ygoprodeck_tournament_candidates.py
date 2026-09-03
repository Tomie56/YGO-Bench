from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT / "data" / "source_samples" / "ygoprodeck_tournament" / "api-candidates-v0.2"
)
API_URL = "https://ygoprodeck.com/api/decks/getDecks.php"
PAGE_LIMIT = 21
USER_AGENT = "YGO-Bench academic data freezer/0.2"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def request_page(offset: int) -> tuple[bytes, list[dict[str, Any]]]:
    query = urllib.parse.urlencode(
        {"limit": PAGE_LIMIT, "offset": offset, "tournament": "1"}
    )
    url = f"{API_URL}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"YGOPRODeck returned HTTP {response.status}: {url}")
        payload = response.read()
    if not payload:
        raise ValueError(f"YGOPRODeck returned an empty response: {url}")
    decoded = json.loads(payload)
    if isinstance(decoded, dict) and decoded.get("error"):
        return payload, []
    if not isinstance(decoded, list):
        raise TypeError(f"Expected a JSON list from YGOPRODeck: {url}")
    return payload, decoded


def card_ids(value: Any, field: str, deck_num: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, str):
        raise TypeError(f"Deck {deck_num} field {field} is not a JSON string")
    decoded = json.loads(value)
    if not isinstance(decoded, list) or not all(
        isinstance(card_id, str) and card_id.isdigit() for card_id in decoded
    ):
        raise ValueError(f"Deck {deck_num} field {field} is not a card-id list")
    return decoded


def normalize_record(
    record: dict[str, Any], source_page: str, retrieved_at: str
) -> dict[str, Any]:
    deck_num = record.get("deckNum")
    if not isinstance(deck_num, int):
        raise ValueError(f"Missing integer deckNum in {source_page}")
    main = card_ids(record.get("main_deck"), "main_deck", deck_num)
    extra = card_ids(record.get("extra_deck"), "extra_deck", deck_num)
    side = card_ids(record.get("side_deck"), "side_deck", deck_num)
    required = ("tournamentName", "tournamentPlacement", "tournamentPlayerName")
    if not all(record.get(key) for key in required):
        raise ValueError(f"Candidate record {deck_num} lacks tournament provenance")
    return {
        "candidate_id": f"ygoprodeck-deck-{deck_num}",
        "source_id": "ygoprodeck-tournament-api",
        "source_page": source_page,
        "retrieved_at": retrieved_at,
        "deck_num": deck_num,
        "deck_name": record.get("deck_name"),
        "username": record.get("username"),
        "tournament_name": record["tournamentName"],
        "tournament_placement": record["tournamentPlacement"],
        "tournament_player_name": record["tournamentPlayerName"],
        "tournament_player_count": record.get("tournamentPlayerCount"),
        "tournament_player_count_is_approximate": record.get(
            "tournamentPlayerCountIsApproximate"
        ),
        "format": record.get("format"),
        "submit_date_display": record.get("submit_date"),
        "main_deck": main,
        "extra_deck": extra,
        "side_deck": side,
        "deck_sizes": {"main": len(main), "extra": len(extra), "side": len(side)},
        "pretty_url": record.get("pretty_url"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze YGOPRODeck tournament deck candidates"
    )
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--delay-seconds", type=float, default=0.25)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_pages <= 0:
        raise ValueError("--max-pages must be positive")
    if args.delay_seconds < 0:
        raise ValueError("--delay-seconds cannot be negative")
    output = args.output.resolve()
    raw_dir = output / "raw_pages"
    raw_dir.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    records: dict[int, dict[str, Any]] = {}
    pages: list[dict[str, Any]] = []
    raw_hashes: list[str] = []

    for page_index in range(args.max_pages):
        offset = page_index * 20
        payload, raw_records = request_page(offset)
        raw_path = raw_dir / f"page-{offset:06d}.json"
        raw_path.write_bytes(payload)
        raw_hash = sha256_bytes(payload)
        raw_hashes.append(raw_hash)
        page_info = {
            "offset": offset,
            "limit": PAGE_LIMIT,
            "path": raw_path.relative_to(ROOT).as_posix(),
            "sha256": raw_hash,
            "bytes": len(payload),
            "record_count": len(raw_records),
            "tournament_record_count": sum(
                all(record.get(key) for key in (
                    "tournamentName",
                    "tournamentPlacement",
                    "tournamentPlayerName",
                ))
                for record in raw_records
            ),
        }
        pages.append(page_info)
        for record in raw_records:
            if not all(
                record.get(key)
                for key in (
                    "tournamentName",
                    "tournamentPlacement",
                    "tournamentPlayerName",
                )
            ):
                continue
            deck_num = record.get("deckNum")
            if not isinstance(deck_num, int):
                raise ValueError(f"Candidate record has invalid deckNum at offset {offset}")
            page_url = f"https://ygoprodeck.com/deck/{record.get('pretty_url', deck_num)}"
            normalized = normalize_record(record, page_url, retrieved_at)
            previous = records.get(deck_num)
            if previous is not None and previous != normalized:
                raise ValueError(f"Conflicting duplicate deckNum: {deck_num}")
            records[deck_num] = normalized
        if not raw_records:
            break
        if args.delay_seconds:
            time.sleep(args.delay_seconds)

    candidates_path = output / "tournament-candidates.jsonl"
    with candidates_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in sorted(records.values(), key=lambda item: item["deck_num"], reverse=True):
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    manifest = {
        "dataset_id": "ygoprodeck-tournament-candidates-v0.2",
        "source": "YGOPRODeck public tournament-filter API",
        "api_url": API_URL,
        "request": {
            "limit": PAGE_LIMIT,
            "offset_step": 20,
            "tournament": "1",
            "max_pages": args.max_pages,
            "delay_seconds": args.delay_seconds,
        },
        "retrieved_at": retrieved_at,
        "license_status": "candidate_only_license_review_required",
        "gold_status": "not_gold",
        "eligibility": "static_construction_candidate",
        "pages": pages,
        "candidate_count": len(records),
        "candidate_path": candidates_path.relative_to(ROOT).as_posix(),
        "candidate_sha256": sha256_bytes(candidates_path.read_bytes()),
        "raw_page_count": len(pages),
        "raw_total_bytes": sum(page["bytes"] for page in pages),
        "raw_sha256_set_sha256": sha256_bytes("\n".join(sorted(raw_hashes)).encode()),
        "event_counts": dict(
            Counter(record["tournament_name"] for record in records.values())
        ),
        "placement_counts": dict(
            Counter(record["tournament_placement"] for record in records.values())
        ),
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "pages": len(pages),
                "candidate_count": len(records),
                "raw_total_bytes": manifest["raw_total_bytes"],
                "manifest": manifest_path.relative_to(ROOT).as_posix(),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
