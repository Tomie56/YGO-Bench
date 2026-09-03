from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Iterable

import brotli


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "benchmark" / "source-candidates-v0.2"
RAW = ROOT / "data" / "question_sources" / "raw"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", unescape(value))
    return " ".join(text.split())


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def qa_records() -> Iterable[dict[str, Any]]:
    source = RAW / "ocg-ruling-assistant" / "data" / "rag-runtime-v1" / "qa-records.json.br"
    payload = json.loads(brotli.decompress(source.read_bytes()))
    for record in payload:
        yield {
            "candidate_id": f"ruling-qa:{record['id']}",
            "source_id": "ocg-ruling-assistant-qa",
            "source_path": source.relative_to(ROOT).as_posix(),
            "source_url": record.get("sourceUrl"),
            "record_type": record.get("recordType"),
            "question": record.get("question") or record.get("rawQuestion"),
            "answer": record.get("answer"),
            "question_card_ids": record.get("questionCardIds", []),
            "card_ids": record.get("cardIds", []),
            "keywords": record.get("keywords", []),
            "status": record.get("status"),
            "question_locale": record.get("questionLocale"),
            "answer_locale": record.get("answerLocale"),
            "gold_status": "source_answer_unverified",
            "eligibility": "static_understanding_candidate",
        }


def rule_fixture_records() -> Iterable[dict[str, Any]]:
    root = RAW / "ocg-ruling-assistant" / "data" / "test"
    for path in sorted(root.glob("*.json")):
        payload = read_json(path)
        cases = next(
            (
                payload[key]
                for key in ("cases", "questions", "tests", "records")
                if isinstance(payload.get(key), list)
            ),
            None,
        )
        if cases is None:
            continue
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                continue
            yield {
                "candidate_id": f"ruling-fixture:{path.stem}:{index:04d}",
                "source_id": "ocg-ruling-assistant-fixture",
                "source_path": path.relative_to(ROOT).as_posix(),
                "source_url": case.get("sourceUrl") or case.get("officialFaqUrl"),
                "record_type": "fixture_case",
                "question": case.get("question"),
                "answer": case.get("answer") or case.get("expectedVerdictType"),
                "question_card_ids": case.get("questionCardIds", []),
                "card_ids": case.get("cardIds", []),
                "gold_status": "fixture_gold_claim_requires_review",
                "eligibility": "static_understanding_candidate",
            }


def stackexchange_records() -> Iterable[dict[str, Any]]:
    root = RAW / "stackexchange-boardgames-yu-gi-oh"
    for path in sorted(root.glob("questions-page-*.json")):
        for question in read_json(path)["items"]:
            yield {
                "candidate_id": f"stackexchange:{question['question_id']}",
                "source_id": "boardgames-stackexchange-yu-gi-oh",
                "source_path": path.relative_to(ROOT).as_posix(),
                "source_url": question.get("link"),
                "record_type": "community_question",
                "question": question.get("title", "") + "\n" + strip_html(question.get("body", "")),
                "answer": None,
                "tags": question.get("tags", []),
                "score": question.get("score"),
                "answer_count": question.get("answer_count"),
                "is_answered": question.get("is_answered"),
                "content_license": question.get("content_license"),
                "gold_status": "community_question_unverified",
                "eligibility": "static_understanding_candidate_after_review",
            }


def projectignis_records() -> Iterable[dict[str, Any]]:
    root = RAW / "projectignis-puzzles"
    for path in sorted(root.rglob("*.lua")):
        content = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(root)
        category = relative.parts[0] if relative.parts else "unknown"
        yield {
            "candidate_id": f"projectignis-puzzle:{sha256(path)[:16]}",
            "source_id": "projectignis-puzzles",
            "source_path": path.relative_to(ROOT).as_posix(),
            "source_sha256": sha256(path),
            "record_type": "lua_puzzle_script",
            "category": category,
            "script_bytes": path.stat().st_size,
            "contains_begin_puzzle": "aux.BeginPuzzle()" in content,
            "contains_solution_marker": bool(re.search(r"solution", content, re.IGNORECASE)),
            "environment_status": "legacy_or_game_specific_environment_unknown",
            "gold_status": "engine_candidate_unverified_by_our_runtime",
            "eligibility": "dynamic_strategy_candidate_after_loader_audit",
        }


def yugi_solution_records() -> Iterable[dict[str, Any]]:
    root = RAW / "yugi-bench-v1" / "solutions"
    for path in sorted(root.glob("yugioh_puzzle_*.json")):
        solution = read_json(path)
        if not isinstance(solution, list):
            raise TypeError(f"Expected action list: {path}")
        yield {
            "candidate_id": f"yugi-bench-v1:{path.stem.removeprefix('yugioh_puzzle_')}",
            "source_id": "yugi-bench-v1",
            "source_path": path.relative_to(ROOT).as_posix(),
            "source_sha256": sha256(path),
            "record_type": "upstream_solution_trace",
            "action_count": len(solution),
            "tool_names": sorted({item.get("tool") for item in solution if isinstance(item, dict)}),
            "gold_status": "upstream_engine_verified_claim_requires_replay",
            "eligibility": "dynamic_strategy_candidate_after_loader_audit",
        }


def write_gzip_jsonl(path: Path, records: list[dict[str, Any]]) -> tuple[int, int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Fix the gzip header timestamp so identical source inputs produce identical bytes.
    with path.open("wb") as binary:
        compressed = gzip.GzipFile(fileobj=binary, mode="wb", mtime=0)
        handle = io.TextIOWrapper(compressed, encoding="utf-8", newline="\n")
        try:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        finally:
            handle.close()
    return len(records), path.stat().st_size, sha256(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build versioned source candidate inventories")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    understanding = [*qa_records(), *rule_fixture_records(), *stackexchange_records()]
    # Keep upstream solution traces archived in raw sources, but exclude them from
    # the active dynamic candidate inventory until our action-schema replay audit.
    dynamic = list(projectignis_records())
    understanding_count, understanding_bytes, understanding_sha = write_gzip_jsonl(
        output / "understanding-candidates.jsonl.gz", understanding
    )
    dynamic_count, dynamic_bytes, dynamic_sha = write_gzip_jsonl(
        output / "dynamic-candidates.jsonl.gz", dynamic
    )
    manifest = {
        "dataset_id": "source-candidates-v0.2",
        "retrieved_at": retrieved_at,
        "gold_policy": "All records are candidate inventory only; expert or engine verification is required before Gold.",
        "understanding": {
            "path": (output / "understanding-candidates.jsonl.gz").relative_to(ROOT).as_posix(),
            "count": understanding_count,
            "bytes": understanding_bytes,
            "sha256": understanding_sha,
            "record_type_counts": dict(Counter(item["record_type"] for item in understanding)),
            "source_ids": sorted({item["source_id"] for item in understanding}),
        },
        "dynamic": {
            "path": (output / "dynamic-candidates.jsonl.gz").relative_to(ROOT).as_posix(),
            "count": dynamic_count,
            "bytes": dynamic_bytes,
            "sha256": dynamic_sha,
            "record_type_counts": dict(Counter(item["record_type"] for item in dynamic)),
            "source_ids": sorted({item["source_id"] for item in dynamic}),
        },
        "notes": [
            "The ruling QA source is largely official FAQ content mirrored by an MIT-licensed project, but source answers are not our expert Gold.",
            "StackExchange content carries CC BY-SA 4.0 and is community candidate material only.",
            "ProjectIgnis puzzles span legacy games and rule environments; each script needs loader/version audit before modern dynamic use.",
            "Yugi-bench solution traces remain archived in raw sources and are deferred until action-schema replay compatibility is audited.",
        ],
    }
    manifest_path = output / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "manifest": manifest_path.relative_to(ROOT).as_posix(), "understanding": understanding_count, "dynamic": dynamic_count}, ensure_ascii=False))


if __name__ == "__main__":
    main()
