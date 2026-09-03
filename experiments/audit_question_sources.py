from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "question_sources" / "raw"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_projectignis() -> dict[str, Any]:
    root = RAW / "projectignis-puzzles"
    scripts = sorted(root.rglob("*.lua"))
    categories = Counter(path.relative_to(root).parts[0] for path in scripts)
    solution_markers = 0
    begin_puzzle = 0
    for path in scripts:
        content = path.read_text(encoding="utf-8", errors="replace")
        solution_markers += bool(re.search(r"solution", content, re.IGNORECASE))
        begin_puzzle += "aux.BeginPuzzle()" in content
    return {
        "script_count": len(scripts),
        "category_counts": dict(sorted(categories.items())),
        "solution_marker_count": solution_markers,
        "begin_puzzle_count": begin_puzzle,
    }


def audit_yugi_bench() -> dict[str, Any]:
    root = RAW / "yugi-bench-v1"
    solution_files = sorted(root.glob("solutions/*.json"))
    tool_calls = 0
    for path in solution_files:
        payload = read_json(path)
        if not isinstance(payload, list):
            raise TypeError(f"Expected a list of tool calls: {path}")
        tool_calls += len(payload)
    return {
        "solution_file_count": len(solution_files),
        "solution_tool_call_count": tool_calls,
    }


def audit_stackexchange() -> dict[str, Any]:
    root = RAW / "stackexchange-boardgames-yu-gi-oh"
    questions = []
    answers = []
    for path in sorted(root.glob("questions-page-*.json")):
        questions.extend(read_json(path)["items"])
    for path in sorted(root.glob("answers-batch-*.json")):
        answers.extend(read_json(path)["items"])
    return {
        "question_count": len(questions),
        "answer_count": len(answers),
        "questions_with_answers": sum(q["answer_count"] > 0 for q in questions),
        "questions_with_accepted_answer": sum(
            "accepted_answer_id" in q for q in questions
        ),
        "questions_score_at_least_5": sum(q["score"] >= 5 for q in questions),
        "closed_question_count": sum("closed_date" in q for q in questions),
        "oldest_creation_date": min(q["creation_date"] for q in questions),
        "newest_creation_date": max(q["creation_date"] for q in questions),
        "content_licenses": sorted(
            {
                item.get("content_license", "missing")
                for item in [*questions, *answers]
            }
        ),
    }


def revision_content(page: dict[str, Any]) -> str:
    return page["revisions"][0]["content"]


def audit_yugipedia() -> dict[str, Any]:
    root = RAW / "yugipedia-puzzles"
    pages_by_title: dict[str, dict[str, Any]] = {}
    snapshot_files = sorted(root.glob("*question-pages*.json"))
    for path in snapshot_files:
        for page in read_json(path)["query"]["pages"]:
            pages_by_title[page["title"]] = page

    pages = []
    for title, page in sorted(pages_by_title.items()):
        content = revision_content(page)
        pages.append(
            {
                "title": title,
                "revision_id": page["revisions"][0]["revid"],
                "characters": len(content),
                "level_2_headings": re.findall(r"^==([^=].*?)==\s*$", content, re.M),
                "wikitable_rows": len(re.findall(r"^\|-\s*$", content, re.M)),
            }
        )
    return {
        "snapshot_file_count": len(snapshot_files),
        "unique_page_count": len(pages_by_title),
        "pages": pages,
    }


def audit_ocg_rule_tests() -> dict[str, Any]:
    root = RAW / "ocg-rule-documentation" / "docs" / "c05"
    expected = {
        "2018年游戏王OCG规则检定测试.rst": 50,
        "2019年游戏王OCG规则检定测试.rst": 50,
        "2020年游戏王OCG规则检定测试.rst": 50,
        "2021年游戏王OCG规则检定测试.rst": 50,
        "规则测试2017.rst": 9,
        "规则测试2020.rst": 10,
    }
    missing = [name for name in expected if not (root / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing OCG rule test files: {missing}")
    return {
        "document_count": len(expected),
        "question_count": sum(expected.values()),
        "question_counts": expected,
        "asset_file_count": len(list((root.parent / ".static" / "c05").glob("*"))),
    }


def audit_ruling_assistant() -> dict[str, Any]:
    root = RAW / "ocg-ruling-assistant"
    manifest = read_json(root / "data" / "rag-runtime-v1" / "manifest.json")
    fixture_counts = {}
    for path in sorted((root / "data" / "test").glob("*.json")):
        payload = read_json(path)
        case_lists = [
            payload[key]
            for key in ("cases", "questions", "tests", "records")
            if isinstance(payload.get(key), list)
        ]
        if len(case_lists) != 1:
            raise ValueError(f"Could not identify one case list in {path}")
        fixture_counts[path.name] = len(case_lists[0])
    return {
        "data_revision": manifest["dataRevision"],
        "qa_record_count": manifest["counts"]["qaRecords"],
        "record_count": manifest["counts"]["records"],
        "fixture_counts": fixture_counts,
        "fixture_count_before_deduplication": sum(fixture_counts.values()),
    }


def audit_ygo_turns() -> dict[str, Any]:
    import pyarrow.parquet as pq

    path = RAW / "ygo-turns" / "ygo-turns.parquet"
    parquet = pq.ParquetFile(path)
    metadata = parquet.metadata
    columns = parquet.schema_arrow.names
    index_columns = [
        "match_id",
        "duel_number",
        "turn_number",
        "is_p1_turn",
        "p1_won",
    ]
    size_columns = [
        f"{player}_{zone}_size"
        for player in ("p1", "p2")
        for zone in ("hand", "deck", "gy", "banished", "extra")
    ]
    identity_patterns = (
        r"p[12]_monster_zone_\d_name",
        r"p[12]_spell_zone_\d_name",
        r"p[12]_field_spell_zone_name",
        r"p[12]_hand_\d+",
        r"p[12]_deck_top_\d+",
        r"p[12]_gy_\d+",
        r"p[12]_banished_\d+",
        r"p[12]_extra_\d+",
        r"p[12]_monster_zone_\d_equip_\d+",
    )
    identity_columns = [
        name
        for name in columns
        if any(re.fullmatch(pattern, name) for pattern in identity_patterns)
    ]
    table = pq.read_table(
        path, columns=[*index_columns, *size_columns, *identity_columns]
    ).to_pydict()
    duel_results: dict[tuple[int, int], bool] = {}
    turns_by_duel: Counter[tuple[int, int]] = Counter()
    turn_zero_by_duel: Counter[tuple[int, int]] = Counter()
    turn_numbers_by_duel: dict[tuple[int, int], set[int]] = {}
    for match_id, duel_number, turn_number, p1_won in zip(
        table["match_id"],
        table["duel_number"],
        table["turn_number"],
        table["p1_won"],
        strict=True,
    ):
        duel_id = (match_id, duel_number)
        if duel_id in duel_results and duel_results[duel_id] != p1_won:
            raise ValueError(f"Inconsistent winner within duel {duel_id}")
        duel_results[duel_id] = p1_won
        turns_by_duel[duel_id] += 1
        turn_zero_by_duel[duel_id] += turn_number == 0
        turn_numbers_by_duel.setdefault(duel_id, set()).add(turn_number)
        if turn_number < 0:
            raise ValueError(f"Invalid turn number in duel {duel_id}: {turn_number}")
    duplicate_turn_zero = [
        duel_id for duel_id, count in turn_zero_by_duel.items() if count > 1
    ]
    if duplicate_turn_zero:
        raise ValueError(f"Multiple turn-zero rows in duels: {duplicate_turn_zero[:5]}")
    non_contiguous_duels = [
        duel_id
        for duel_id, turns in turn_numbers_by_duel.items()
        if turns != set(range(max(turns) + 1))
    ]
    compression = sorted(
        {
            metadata.row_group(group).column(column).compression
            for group in range(metadata.num_row_groups)
            for column in range(metadata.row_group(group).num_columns)
        }
    )
    primary_keys = list(
        zip(
            table["match_id"],
            table["duel_number"],
            table["turn_number"],
            strict=True,
        )
    )
    primary_key_counts = Counter(primary_keys)
    duplicate_keys = [
        key for key, count in primary_key_counts.items() if count > 1
    ]
    duplicate_details = []
    if duplicate_keys:
        full_table = pq.read_table(path)
        for key in duplicate_keys:
            indices = [index for index, value in enumerate(primary_keys) if value == key]
            first = full_table.slice(indices[0], 1)
            differing_columns = [
                name
                for name in columns
                if not first.select([name]).equals(
                    full_table.slice(indices[1], 1).select([name])
                )
            ]
            duplicate_details.append(
                {
                    "match_id": key[0],
                    "duel_number": key[1],
                    "turn_number": key[2],
                    "row_count": len(indices),
                    "rows_identical": all(
                        first.equals(full_table.slice(index, 1))
                        for index in indices[1:]
                    ),
                    "differing_column_count": len(differing_columns),
                    "differing_columns": differing_columns,
                }
            )
    slot_limits = {"hand": 10, "gy": 15, "banished": 5, "extra": 15}
    overflow_rows = {
        zone: sum(
            table[f"{player}_{zone}_size"][row] > limit
            for row in range(metadata.num_rows)
            for player in ("p1", "p2")
        )
        for zone, limit in slot_limits.items()
    }
    max_zone_sizes = {
        zone: max(
            max(table[f"{player}_{zone}_size"])
            for player in ("p1", "p2")
        )
        for zone in ("hand", "deck", "gy", "banished", "extra")
    }
    card_names = {
        value
        for column in identity_columns
        for value in table[column]
        if isinstance(value, str) and value
    }
    return {
        "revision": "1661a60c2bf1a093e110d81825edcf63acda2611",
        "license": "CC-BY-4.0",
        "ruleset": "pre-Master Rule 1 (before the 2008 revision)",
        "row_count": metadata.num_rows,
        "column_count": metadata.num_columns,
        "row_group_count": metadata.num_row_groups,
        "compression": compression,
        "documented_compression": "ZSTD",
        "compression_matches_documentation": compression == ["ZSTD"],
        "match_count": len(set(table["match_id"])),
        "duel_count": len(duel_results),
        "duplicate_primary_key_count": len(primary_keys) - len(set(primary_keys)),
        "duplicate_primary_key_details": duplicate_details,
        "minimum_turn_number": min(table["turn_number"]),
        "turn_zero_row_count": sum(turn == 0 for turn in table["turn_number"]),
        "max_turn_snapshots_per_duel": max(turns_by_duel.values()),
        "non_contiguous_turn_sequence_count": len(non_contiguous_duels),
        "p1_win_rate_duel_weighted": sum(duel_results.values()) / len(duel_results),
        "p1_win_label_rate_snapshot_weighted": sum(table["p1_won"])
        / len(table["p1_won"]),
        "action_column_count": sum("action" in name for name in columns),
        "replay_column_count": sum("replay" in name for name in columns),
        "date_column_count": sum("date" in name for name in columns),
        "rating_column_count": sum("rating" in name for name in columns),
        "archetype_column_count": sum("archetype" in name for name in columns),
        "card_identifier_column_count": sum(
            "card_id" in name or "passcode" in name or "konami_id" in name
            for name in columns
        ),
        "card_identity_column_count": len(identity_columns),
        "unique_nonempty_card_name_count": len(card_names),
        "opponent_hidden_identity_columns": sum(
            bool(re.fullmatch(r"p2_(hand|deck_top)_\d+", name))
            for name in identity_columns
        ),
        "max_zone_sizes": max_zone_sizes,
        "overflow_slot_observations": overflow_rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit locally frozen Yu-Gi-Oh question sources"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tmp" / "question-source-audit.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audit = {
        "projectignis_puzzles": audit_projectignis(),
        "yugi_bench_v1": audit_yugi_bench(),
        "stackexchange": audit_stackexchange(),
        "yugipedia": audit_yugipedia(),
        "ocg_rule_tests": audit_ocg_rule_tests(),
        "ocg_ruling_assistant": audit_ruling_assistant(),
        "ygo_turns": audit_ygo_turns(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
