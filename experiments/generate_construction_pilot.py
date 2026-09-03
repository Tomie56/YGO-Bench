from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from experiments.freeze_tcg_ocg_snapshots import load_limits
from ygo_bench.contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "construction-pilot-v0.1.json"
DEFAULT_OUTPUT = ROOT / "data" / "benchmark" / "deck" / "pilot-candidates-v0.1.jsonl"
SNAPSHOT_ROOT = ROOT / "snapshots"
DECK_ROOT = ROOT / "data" / "fixed_snapshots"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_zones(zones: dict[str, list[dict[str, Any]]]) -> dict[str, list[int]]:
    flattened: dict[str, list[int]] = {}
    for zone_name in ("main", "extra", "side"):
        flattened[zone_name] = [
            int(item["card_id"])
            for item in zones[zone_name]
            for _ in range(int(item["quantity"]))
        ]
    return flattened


def grouped_zones(
    zones: dict[str, list[int]], names: dict[int, str]
) -> dict[str, list[dict[str, Any]]]:
    return {
        zone_name: [
            {
                "card_id": card_id,
                "name": names[card_id],
                "quantity": quantity,
            }
            for card_id, quantity in Counter(card_ids).items()
        ]
        for zone_name, card_ids in zones.items()
    }


def validate_deck(
    zones: dict[str, list[int]], snapshot: dict[str, Any], limits: dict[int, int]
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for zone_name, bounds in snapshot["deck_rules"].items():
        observed = len(zones[zone_name])
        minimum = int(bounds["min"])
        maximum = int(bounds["max"])
        if observed < minimum or observed > maximum:
            violations.append(
                {
                    "type": "zone_size",
                    "zone": zone_name,
                    "observed": observed,
                    "minimum": minimum,
                    "maximum": maximum,
                }
            )
    counts = Counter(card_id for card_ids in zones.values() for card_id in card_ids)
    for card_id, copies in sorted(counts.items()):
        limit = limits.get(card_id, 3)
        if copies > limit:
            violations.append(
                {
                    "type": "copy_limit",
                    "card_id": card_id,
                    "observed": copies,
                    "limit": limit,
                }
            )
    return violations


def mutate_deck(
    source: dict[str, list[int]],
    snapshot: dict[str, Any],
    forbidden_card_id: int,
) -> tuple[dict[str, list[int]], dict[str, Any], dict[str, Any]]:
    mutated = {zone: list(card_ids) for zone, card_ids in source.items()}
    main_minimum = int(snapshot["deck_rules"]["main"]["min"])
    if len(mutated["main"]) == main_minimum:
        removed_card_id = mutated["main"].pop(0)
        mutation = {
            "kind": "remove_main_card",
            "zone": "main",
            "card_id": removed_card_id,
            "index": 0,
        }
        repair = {
            "op": "add",
            "zone": "main",
            "card_id": removed_card_id,
            "quantity": 1,
            "index": 0,
        }
        return mutated, mutation, repair

    replaced_card_id = mutated["main"][0]
    mutated["main"][0] = forbidden_card_id
    mutation = {
        "kind": "replace_with_forbidden_card",
        "zone": "main",
        "removed_card_id": replaced_card_id,
        "added_card_id": forbidden_card_id,
    }
    repair = {
        "op": "replace",
        "zone": "main",
        "remove_card_id": forbidden_card_id,
        "add_card_id": replaced_card_id,
        "quantity": 1,
    }
    return mutated, mutation, repair


def apply_repair(
    zones: dict[str, list[int]], repair: dict[str, Any]
) -> dict[str, list[int]]:
    repaired = {zone: list(card_ids) for zone, card_ids in zones.items()}
    zone = repaired[repair["zone"]]
    if repair["op"] == "add":
        index = int(repair["index"])
        for offset in range(int(repair["quantity"])):
            zone.insert(index + offset, int(repair["card_id"]))
    elif repair["op"] == "replace":
        index = zone.index(int(repair["remove_card_id"]))
        zone[index] = int(repair["add_card_id"])
    else:
        raise ValueError(f"Unsupported construction repair: {repair['op']}")
    return repaired


def provenance_sources(
    deck_path: Path,
    deck: dict[str, Any],
    snapshot_path: Path,
    snapshot: dict[str, Any],
    created_at: str,
) -> list[dict[str, Any]]:
    lflist_path = ROOT / snapshot["artifacts"]["lflist"]["path"]
    lflist_sha256 = snapshot["artifacts"]["lflist"]["sha256"].lower()
    if sha256_file(lflist_path) != lflist_sha256:
        raise ValueError(f"Frozen lflist hash mismatch: {lflist_path}")
    return [
        {
            "source_id": f"tournament-deck-{deck['deck_id']}",
            "uri": deck_path.relative_to(ROOT).as_posix(),
            "retrieved_at": deck["source"]["retrieved_at"],
            "sha256": sha256_file(deck_path),
            "evidence_level": deck["source"]["evidence_level"],
            "source_type": "curated_tournament_deck",
            "parser_version": "freeze_tcg_ocg_snapshots.py",
        },
        {
            "source_id": f"environment-{deck['snapshot_id']}",
            "uri": snapshot_path.relative_to(ROOT).as_posix(),
            "retrieved_at": created_at,
            "sha256": sha256_file(snapshot_path),
            "evidence_level": "frozen_environment_snapshot",
        },
        {
            "source_id": f"lflist-{deck['snapshot_id']}",
            "uri": lflist_path.relative_to(ROOT).as_posix(),
            "retrieved_at": created_at,
            "sha256": lflist_sha256,
            "evidence_level": "frozen_forbidden_limited_list",
        },
    ]


def deck_input(
    deck: dict[str, Any],
    zones: dict[str, list[int]],
    names: dict[int, str],
    instruction: str,
) -> dict[str, Any]:
    return {
        "instruction": instruction,
        "regulation": deck["regulation"],
        "event_date": deck["event_date"],
        "deck_name": deck["deck_name"],
        "zones": grouped_zones(zones, names),
        "totals": {zone: len(card_ids) for zone, card_ids in zones.items()},
    }


def base_record(
    config: dict[str, Any],
    config_sha256: str,
    deck: dict[str, Any],
    deck_path: Path,
    snapshot: dict[str, Any],
    snapshot_path: Path,
    record_id: str,
    task: str,
    task_type: str,
    input_value: dict[str, Any],
    target: dict[str, Any],
    changed_variables: list[str],
) -> dict[str, Any]:
    record = {
        "schema_version": config["schema_version"],
        "record_id": record_id,
        "group_id": f"deck-{deck['deck_id']}-controlled-corruption",
        "layer": "deck",
        "task": task,
        "snapshot_id": deck["snapshot_id"],
        "split": config["split"],
        "task_type": task_type,
        "input": input_value,
        "target": target,
        "provenance": {
            "created_at": config["created_at"],
            "sources": provenance_sources(
                deck_path,
                deck,
                snapshot_path,
                snapshot,
                config["created_at"],
            ),
            "generator": {
                "name": "generate_construction_pilot",
                "version": "0.1.0",
                "config_sha256": config_sha256,
            },
        },
        "verifier": {
            "kind": "snapshot_validator",
            "name": "construction-pilot-validator",
            "version": "0.1.0",
            "gold_level": "G1",
            "config": {
                "deck_rules": snapshot["deck_rules"],
                "banlist_semantics": snapshot["banlist_semantics"],
            },
        },
        "visibility": {
            "public_fields": ["input", "snapshot_id"],
            "private_fields": ["target", "provenance"],
        },
        "difficulty": {
            "decision_horizon": 1,
            "hidden_information": False,
            "changed_variables": changed_variables,
        },
        "contamination_controls": {
            "card_names_masked": False,
            "private_generator_seed": False,
            "release_cutoff": snapshot["card_pool_cutoff"],
            "held_out_card_pairs": False,
        },
        "metadata": {
            "candidate_status": "machine_generated_pilot",
            "source_deck_id": deck["deck_id"],
            "source_event_id": deck["event_id"],
        },
    }
    validate_document("benchmark-record", record)
    return record


def build_records(config_path: Path) -> list[dict[str, Any]]:
    config = load_json(config_path)
    config_sha256 = sha256_file(config_path)
    forbidden = config["forbidden_substitution"]
    forbidden_card_id = int(forbidden["card_id"])
    records = []
    for deck_path in sorted(DECK_ROOT.glob("*/decks/*.json")):
        deck = load_json(deck_path)
        if deck.get("static_benchmark_ready") is not True:
            raise ValueError(f"Source deck is not static-benchmark ready: {deck_path}")
        snapshot_path = SNAPSHOT_ROOT / f"{deck['snapshot_id']}.json"
        snapshot = load_json(snapshot_path)
        lflist_path = ROOT / snapshot["artifacts"]["lflist"]["path"]
        limits = load_limits(lflist_path)
        if limits.get(forbidden_card_id, 3) != int(forbidden["required_limit"]):
            raise ValueError(
                f"Forbidden substitution does not have the required limit in "
                f"{deck['snapshot_id']}"
            )
        source = flatten_zones(deck["zones"])
        source_violations = validate_deck(source, snapshot, limits)
        if source_violations:
            raise ValueError(f"Source deck is not legal: {deck_path}: {source_violations}")
        names = {
            int(item["card_id"]): str(item["name"])
            for zone in deck["zones"].values()
            for item in zone
        }
        names[forbidden_card_id] = str(forbidden["name"])
        mutated, mutation, repair = mutate_deck(
            source, snapshot, forbidden_card_id
        )
        mutation_violations = validate_deck(mutated, snapshot, limits)
        if len(mutation_violations) != 1:
            raise ValueError(
                f"Controlled mutation must create exactly one violation: "
                f"{deck_path}: {mutation_violations}"
            )
        repaired = apply_repair(mutated, repair)
        if repaired != source:
            raise ValueError(f"Controlled repair does not restore source deck: {deck_path}")
        if validate_deck(repaired, snapshot, limits):
            raise ValueError(f"Controlled repair is not legal: {deck_path}")

        prefix = f"deck-{deck['deck_id']}"
        records.append(
            base_record(
                config,
                config_sha256,
                deck,
                deck_path,
                snapshot,
                snapshot_path,
                f"{prefix}-legality-source",
                "LegalityAudit",
                "source_legality_audit",
                deck_input(
                    deck,
                    source,
                    names,
                    "Audit this deck against the frozen card pool, deck-size rules, "
                    "and Forbidden & Limited List. Return every violation.",
                ),
                {"legal": True, "violations": []},
                [],
            )
        )
        records.append(
            base_record(
                config,
                config_sha256,
                deck,
                deck_path,
                snapshot,
                snapshot_path,
                f"{prefix}-legality-corrupted",
                "LegalityAudit",
                "controlled_corruption_audit",
                deck_input(
                    deck,
                    mutated,
                    names,
                    "Audit this deck against the frozen card pool, deck-size rules, "
                    "and Forbidden & Limited List. Locate every violation.",
                ),
                {
                    "legal": False,
                    "violations": mutation_violations,
                    "controlled_mutation": mutation,
                },
                [mutation["kind"]],
            )
        )
        records.append(
            base_record(
                config,
                config_sha256,
                deck,
                deck_path,
                snapshot,
                snapshot_path,
                f"{prefix}-minimal-repair",
                "MinimalRepair",
                "controlled_corruption_minimal_repair",
                deck_input(
                    deck,
                    mutated,
                    names,
                    "Repair this deck with the minimum number of card edits. Return a "
                    "legal repair and, separately, your best reconstruction of the "
                    "original tournament deck.",
                ),
                {
                    "minimum_edit_count": 1,
                    "legal_repair_constraint": {"legal": True, "violations": []},
                    "strict_source_recovery": {"edits": [repair]},
                    "scoring": {
                        "legality": "Any one-edit repair accepted if snapshot-valid.",
                        "source_recovery": "Exact controlled inverse required.",
                    },
                    "controlled_mutation": mutation,
                },
                [mutation["kind"]],
            )
        )
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic construction pilot records"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Construction pilot output already exists: {output}")
    records = build_records(args.config.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "output": output.relative_to(ROOT).as_posix(),
                "records": len(records),
                "sha256": sha256_file(output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
