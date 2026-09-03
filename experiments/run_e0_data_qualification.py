from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.freeze_tcg_ocg_snapshots import SOURCE_MANIFEST, parse_deck_html
from ygo_bench.contracts import read_documents, validate_path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ROOT = ROOT / "snapshots"
FIXED_DATA_ROOT = ROOT / "data" / "fixed_snapshots"
DEFAULT_OUTPUT = ROOT / "results" / "e0_data_qualification" / "metrics.json"
SNAPSHOT_IDS = (
    "tcg-kde-e-2026-05-18",
    "ocg-jp-2026-07-01",
)
UNDERSTANDING_ROOT = ROOT / "data" / "benchmark" / "understanding"
SEMANTIC_FIELDS = (
    "activation_condition",
    "cost",
    "target",
    "once_per_turn_scope",
    "resolution_operation",
    "restriction",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def git_dirty() -> bool:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return bool(status.strip())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_zone(zone: list[dict[str, Any]]) -> list[int]:
    cards: list[int] = []
    for item in zone:
        card_id = int(item["card_id"])
        quantity = int(item["quantity"])
        cards.extend([card_id] * quantity)
    return cards


def get_nested(record: dict[str, Any], path: str) -> Any:
    value: Any = record
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def validate_deck_record(
    path: Path,
    record: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    source = record.get("source")
    zones = record.get("zones")
    if record.get("snapshot_id") != snapshot["snapshot_id"]:
        errors.append("snapshot_id_mismatch")
    if record.get("static_benchmark_ready") is not True:
        errors.append("static_benchmark_not_ready")
    if record.get("banlist_violations") != []:
        errors.append("banlist_violations_present")
    if not isinstance(source, dict):
        errors.append("missing_source")
        source = {}
    if not isinstance(zones, dict):
        errors.append("missing_zones")
        zones = {}

    flattened: dict[str, list[int]] = {}
    for zone_name, bounds in snapshot["deck_rules"].items():
        zone = zones.get(zone_name)
        if not isinstance(zone, list):
            errors.append(f"missing_zone:{zone_name}")
            continue
        try:
            flattened[zone_name] = flatten_zone(zone)
        except (KeyError, TypeError, ValueError):
            errors.append(f"invalid_zone_entry:{zone_name}")
            continue
        size = len(flattened[zone_name])
        if not int(bounds["min"]) <= size <= int(bounds["max"]):
            errors.append(f"zone_size:{zone_name}:{size}")
        declared_total = record.get("totals", {}).get(zone_name)
        if declared_total != size:
            errors.append(f"total_mismatch:{zone_name}")
        for item in zone:
            if not isinstance(item.get("card_id"), int) or item["card_id"] <= 0:
                errors.append(f"invalid_card_id:{zone_name}")
            if not isinstance(item.get("quantity"), int) or item["quantity"] <= 0:
                errors.append(f"invalid_quantity:{zone_name}")
            if not isinstance(item.get("name"), str) or not item["name"].strip():
                errors.append(f"missing_card_name:{zone_name}")

    raw_path_value = source.get("local_path")
    raw_path = ROOT / raw_path_value if isinstance(raw_path_value, str) else None
    raw_parse_matches = False
    if raw_path is None or not raw_path.is_file():
        errors.append("missing_raw_source")
    else:
        expected_hash = source.get("sha256")
        if expected_hash != sha256(raw_path):
            errors.append("raw_sha256_mismatch")
        try:
            parsed = parse_deck_html(raw_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"raw_parse_error:{type(error).__name__}")
        else:
            raw_parse_matches = bool(
                all(
                    Counter(parsed["zones"][zone])
                    == Counter(flattened.get(zone, []))
                    for zone in ("main", "extra", "side")
                )
                and parsed["deck_name"] == record.get("deck_name")
                and parsed["category"] == record.get("category")
                and parsed["creator"] == record.get("creator")
                and parsed["tournament"] == record.get("tournament")
                and parsed["placement"] == record.get("placement")
            )
            if not raw_parse_matches:
                errors.append("raw_parse_record_mismatch")

    tournament_path_value = source.get("tournament_local_path")
    tournament_path = (
        ROOT / tournament_path_value
        if isinstance(tournament_path_value, str)
        else None
    )
    if tournament_path is None or not tournament_path.is_file():
        errors.append("missing_tournament_source")
    elif source.get("tournament_sha256") != sha256(tournament_path):
        errors.append("tournament_sha256_mismatch")

    provenance_requirements = (
        "event_date",
        "placement",
        "source.url",
        "source.authority_event_url",
        "source.tournament_url",
        "source.tournament_local_path",
        "source.tournament_sha256",
        "source.local_path",
        "source.sha256",
        "source.retrieved_at",
        "source.evidence_level",
    )
    missing_provenance = [
        field for field in provenance_requirements if get_nested(record, field) in (None, "")
    ]
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "snapshot_id": record.get("snapshot_id"),
        "regulation": record.get("regulation"),
        "deck_id": record.get("deck_id"),
        "structurally_valid": not errors,
        "raw_parse_matches": raw_parse_matches,
        "provenance_complete": not missing_provenance,
        "missing_provenance": missing_provenance,
        "errors": errors,
    }


def audit_decks() -> dict[str, Any]:
    snapshots = {
        snapshot_id: load_json(SNAPSHOT_ROOT / f"{snapshot_id}.json")
        for snapshot_id in SNAPSHOT_IDS
    }
    by_snapshot: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []
    for snapshot_id, snapshot in snapshots.items():
        deck_root = FIXED_DATA_ROOT / snapshot_id / "decks"
        deck_paths = sorted(deck_root.glob("*.json"))
        records: list[dict[str, Any]] = []
        for path in deck_paths:
            try:
                record = load_json(path)
            except (OSError, json.JSONDecodeError) as error:
                records.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "snapshot_id": snapshot_id,
                        "regulation": snapshot["regulation"],
                        "deck_id": None,
                        "structurally_valid": False,
                        "raw_parse_matches": False,
                        "provenance_complete": False,
                        "missing_provenance": [],
                        "errors": [f"record_parse_error:{type(error).__name__}"],
                    }
                )
                continue
            records.append(validate_deck_record(path, record, snapshot))
        all_records.extend(records)
        count = len(records)
        valid = sum(bool(record["structurally_valid"]) for record in records)
        provenance_complete = sum(
            bool(record["provenance_complete"]) for record in records
        )
        by_snapshot.append(
            {
                "snapshot_id": snapshot_id,
                "regulation": snapshot["regulation"],
                "records": count,
                "target_records": 10,
                "record_parse_success_rate": valid / count if count else 0.0,
                "raw_reparse_match_rate": (
                    sum(bool(record["raw_parse_matches"]) for record in records) / count
                    if count
                    else 0.0
                ),
                "provenance_complete_rate": provenance_complete / count if count else 0.0,
                "count_gate_passed": count >= 10,
                "parse_gate_passed": bool(count) and valid / count >= 0.98,
                "provenance_gate_passed": bool(count) and provenance_complete == count,
            }
        )
    return {
        "by_snapshot": by_snapshot,
        "records": all_records,
        "gate_passed": all(
            item["count_gate_passed"]
            and item["parse_gate_passed"]
            and item["provenance_gate_passed"]
            for item in by_snapshot
        ),
    }


def understanding_paths() -> list[Path]:
    if not UNDERSTANDING_ROOT.is_dir():
        return []
    return sorted(
        path
        for path in UNDERSTANDING_ROOT.rglob("*")
        if path.is_file() and path.suffix in {".json", ".jsonl"}
    )


def read_understanding_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    record_ids: set[str] = set()
    for path in understanding_paths():
        validate_path("understanding-annotation", path)
        for record in read_documents(path):
            record_id = record["record_id"]
            if record_id in record_ids:
                raise ValueError(f"Duplicate Understanding record_id: {record_id}")
            record_ids.add(record_id)

            annotator_ids = [
                annotation["annotator_id"]
                for annotation in record["annotations"]
            ]
            if len(annotator_ids) != len(set(annotator_ids)):
                raise ValueError(
                    f"Duplicate annotator_id in Understanding record: {record_id}"
                )
            source_ids = {source["source_id"] for source in record["evidence"]}
            for annotation in record["annotations"]:
                validate_semantic_value(annotation["value"], record_id)
                missing = set(annotation["evidence_source_ids"]) - source_ids
                if missing:
                    raise ValueError(
                        f"Unknown evidence source in {record_id}: {sorted(missing)}"
                    )
            if record["gold"] is not None:
                validate_semantic_value(record["gold"], record_id)
            records.append(record)
    return records


def validate_semantic_value(value: dict[str, Any], record_id: str) -> None:
    for field in SEMANTIC_FIELDS:
        semantic = value[field]
        status = semantic["status"]
        labels = semantic["labels"]
        if status == "present" and not labels:
            raise ValueError(
                f"Present semantic field has no labels in {record_id}: {field}"
            )
        if status != "present" and labels:
            raise ValueError(
                f"Non-present semantic field has labels in {record_id}: {field}"
            )
    once_per_turn = value["once_per_turn_scope"]
    if once_per_turn["status"] == "present" and once_per_turn["scope"] == "none":
        raise ValueError(f"Present once-per-turn field has scope=none: {record_id}")
    if once_per_turn["status"] != "present" and once_per_turn["scope"] != "none":
        raise ValueError(
            f"Non-present once-per-turn field has a non-none scope: {record_id}"
        )


def semantic_agreement_value(value: dict[str, Any], field: str) -> dict[str, Any]:
    semantic = value[field]
    projection = {
        "status": semantic["status"],
        "labels": sorted(semantic["labels"]),
    }
    if field == "once_per_turn_scope":
        projection["scope"] = semantic["scope"]
    return projection


def audit_understanding() -> dict[str, Any]:
    records = read_understanding_records()
    double_annotated = 0
    complete_semantics = 0
    agreement_matches = 0
    agreement_comparisons = 0
    for record in records:
        annotations = record.get("annotations", [])
        by_annotator = {
            annotation["annotator_id"]: annotation for annotation in annotations
        }
        if len(by_annotator) >= 2:
            double_annotated += 1
            first_id, second_id = sorted(by_annotator)[:2]
            first_value = by_annotator[first_id]["value"]
            second_value = by_annotator[second_id]["value"]
            for field in SEMANTIC_FIELDS:
                agreement_comparisons += 1
                agreement_matches += semantic_agreement_value(
                    first_value, field
                ) == semantic_agreement_value(second_value, field)
        gold = record.get("gold")
        if (
            record["status"] == "adjudicated"
            and isinstance(gold, dict)
            and all(field in gold for field in SEMANTIC_FIELDS)
        ):
            complete_semantics += 1
    agreement = (
        agreement_matches / agreement_comparisons if agreement_comparisons else None
    )
    return {
        "records": complete_semantics,
        "total_records": len(records),
        "candidate_records": sum(
            record["status"] == "candidate" for record in records
        ),
        "adjudicated_records": complete_semantics,
        "target_records": 30,
        "double_annotated_records": double_annotated,
        "complete_semantic_gold_records": complete_semantics,
        "agreement_available": agreement is not None,
        "field_exact_agreement": agreement,
        "agreement_comparisons": agreement_comparisons,
        "agreement_target": 0.9,
        "gate_passed": bool(
            complete_semantics >= 30
            and double_annotated >= 30
            and complete_semantics >= 30
            and agreement is not None
            and agreement >= 0.9
        ),
        "note": (
            "Only schema-valid adjudicated records count toward the target. Agreement "
            "compares controlled status/labels/scope fields and ignores rationale and "
            "source spans. CardScripts callbacks cannot substitute for human labels."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run YGO-Bench E0 data qualification")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def input_artifacts() -> list[dict[str, str]]:
    paths = {
        SNAPSHOT_ROOT / f"{snapshot_id}.json" for snapshot_id in SNAPSHOT_IDS
    }
    paths.add(SOURCE_MANIFEST)
    for snapshot_id in SNAPSHOT_IDS:
        for deck_path in sorted(
            (FIXED_DATA_ROOT / snapshot_id / "decks").glob("*.json")
        ):
            paths.add(deck_path)
            record = load_json(deck_path)
            source_path = record.get("source", {}).get("local_path")
            if not isinstance(source_path, str) or not source_path:
                raise ValueError(f"Deck record is missing source.local_path: {deck_path}")
            raw_path = ROOT / source_path
            if not raw_path.is_file():
                raise FileNotFoundError(f"Deck raw source does not exist: {raw_path}")
            paths.add(raw_path)
            tournament_source = record.get("source", {}).get(
                "tournament_local_path"
            )
            if not isinstance(tournament_source, str) or not tournament_source:
                raise ValueError(
                    f"Deck record is missing source.tournament_local_path: {deck_path}"
                )
            tournament_path = ROOT / tournament_source
            if not tournament_path.is_file():
                raise FileNotFoundError(
                    f"Tournament raw source does not exist: {tournament_path}"
                )
            paths.add(tournament_path)
    paths.update(understanding_paths())
    return [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256(path),
        }
        for path in sorted(paths)
    ]


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    result = {
        "experiment_id": "E0-data-qualification-v0.1",
        "protocol": "docs/reports/benchmark-experiment-protocol-v0.1.md",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "distro": "Ubuntu-22.04",
            "conda_env": "ygo",
            "python": sys.version.split()[0],
            "git_commit": git_commit(),
            "git_dirty": git_dirty(),
            "script_sha256": sha256(Path(__file__)),
        },
        "configuration": {
            "snapshot_ids": list(SNAPSHOT_IDS),
            "random_seed": None,
            "cpu_only": True,
            "input_artifacts": input_artifacts(),
            "command": (
                "python -m experiments.run_e0_data_qualification "
                "--output results/e0_data_qualification/metrics.json"
            ),
        },
        "understanding": audit_understanding(),
        "deck_data": audit_decks(),
    }
    result["gate_passed"] = bool(
        result["understanding"]["gate_passed"]
        and result["deck_data"]["gate_passed"]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
