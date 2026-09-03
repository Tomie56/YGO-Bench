from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from ygo_bench.contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "understanding-pilot-v0.1.json"
SOURCE_MANIFEST = (
    ROOT / "data" / "source_samples" / "konami" / "understanding-pilot" / "manifest.json"
)
RULE_MANIFEST = ROOT / "data" / "source_samples" / "official_rules" / "manifest.json"
RUNTIME_SNAPSHOT = ROOT / "snapshots" / "runtime-modern-v1-2026-07-20.json"
DEFAULT_OUTPUT = (
    ROOT / "data" / "benchmark" / "understanding" / "pilot-candidates-v0.1.jsonl"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require_source(path: Path, expected_sha256: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Understanding evidence is missing: {path}")
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256.lower():
        raise ValueError(
            f"Understanding evidence SHA-256 mismatch for {path}: "
            f"expected {expected_sha256.lower()}, got {actual_sha256}"
        )


def official_card_sources() -> dict[tuple[int, str], dict[str, Any]]:
    manifest = load_json(SOURCE_MANIFEST)
    sources: dict[tuple[int, str], dict[str, Any]] = {}
    for artifact in manifest["artifacts"]:
        if artifact["kind"] != "official_card_text":
            continue
        path = ROOT / artifact["path"]
        parsed_path = ROOT / artifact["parsed_path"]
        require_source(path, artifact["sha256"])
        parsed = load_json(parsed_path)
        if parsed["source_sha256"] != artifact["sha256"]:
            raise ValueError(f"Parsed card source has stale hash: {parsed_path}")
        key = (int(artifact["card_id"]), str(artifact["locale"]))
        if key in sources:
            raise ValueError(f"Duplicate official card source: {key}")
        sources[key] = {**artifact, "parsed": parsed}
    if len(sources) != 24:
        raise ValueError(f"Expected 24 official card sources, got {len(sources)}")
    return sources


def official_rule_sources() -> dict[str, dict[str, Any]]:
    pilot_manifest = load_json(SOURCE_MANIFEST)
    sources = {
        artifact["source_id"]: artifact
        for artifact in pilot_manifest["artifacts"]
        if artifact["kind"] == "official_rule"
    }
    base_manifest = load_json(RULE_MANIFEST)
    for artifact in base_manifest["artifacts"]:
        if artifact["kind"] != "official_rulebook_pdf":
            continue
        sources["konami-tcg-rulebook-v9.01"] = {
            "source_id": "konami-tcg-rulebook-v9.01",
            "kind": "official_rule",
            "url": artifact["url"],
            "path": artifact["path"],
            "retrieved_at": base_manifest["retrieved_at"],
            "sha256": artifact["sha256"],
        }
    for source in sources.values():
        require_source(ROOT / source["path"], source["sha256"])
    if set(sources) != {
        "konami-fast-effect-timing-2026-08-26",
        "konami-psct-2026-08-26",
        "konami-tcg-rulebook-v9.01",
    }:
        raise ValueError(f"Unexpected official Understanding rule sources: {sorted(sources)}")
    return sources


def evidence_record(source: dict[str, Any], evidence_level: str) -> dict[str, Any]:
    return {
        "source_id": source["source_id"],
        "uri": source["url"],
        "retrieved_at": source["retrieved_at"],
        "sha256": source["sha256"].lower(),
        "evidence_level": evidence_level,
    }


def cardscript_evidence(card_id: int, retrieved_at: str) -> dict[str, Any]:
    path = ROOT / "references" / "cardscripts" / "official" / f"c{card_id}.lua"
    if not path.is_file():
        raise FileNotFoundError(f"Candidate CardScript is missing: {path}")
    return {
        "source_id": f"cardscript-{card_id}",
        "uri": path.relative_to(ROOT).as_posix(),
        "retrieved_at": retrieved_at,
        "sha256": sha256_file(path),
        "evidence_level": "cardscript_candidate",
    }


def build_records(config_path: Path) -> list[dict[str, Any]]:
    config = load_json(config_path)
    card_sources = official_card_sources()
    rule_sources = official_rule_sources()
    runtime_snapshot = load_json(RUNTIME_SNAPSHOT)
    script_retrieved_at = runtime_snapshot["scripts"]["commit_date"] + "T00:00:00Z"
    records = []
    for candidate in config["candidates"]:
        locale = "en" if candidate["snapshot_id"].startswith("tcg-") else "ae"
        selected_sources = [
            card_sources[(int(card_id), locale)] for card_id in candidate["card_ids"]
        ]
        card_text = "\n\n".join(
            f"{source['parsed']['name']}\n{source['parsed']['card_text']}"
            for source in selected_sources
        )
        evidence = [
            evidence_record(source, "official_card_text")
            for source in selected_sources
        ]
        evidence.append(
            evidence_record(
                rule_sources["konami-psct-2026-08-26"], "official_rule"
            )
        )
        if candidate["task"] == "RuleAndTiming":
            evidence.extend(
                evidence_record(rule_sources[source_id], "official_rule")
                for source_id in (
                    "konami-fast-effect-timing-2026-08-26",
                    "konami-tcg-rulebook-v9.01",
                )
            )
        evidence.extend(
            cardscript_evidence(int(card_id), script_retrieved_at)
            for card_id in candidate["card_ids"]
        )
        source_ids = [item["source_id"] for item in evidence]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError(f"Duplicate evidence in {candidate['record_id']}")
        record = {
            "schema_version": config["schema_version"],
            "record_id": candidate["record_id"],
            "group_id": candidate["group_id"],
            "snapshot_id": candidate["snapshot_id"],
            "task": candidate["task"],
            "candidate_kind": candidate["candidate_kind"],
            "status": "candidate",
            "input": {
                "question": candidate["question"],
                "card_ids": candidate["card_ids"],
                "card_text": card_text,
                "rule_context": candidate["rule_context"],
            },
            "evidence": evidence,
            "annotations": [],
            "gold": None,
            "adjudication": None,
        }
        validate_document("understanding-annotation", record)
        records.append(record)
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate schema-valid Understanding pilot candidate records"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Understanding pilot output already exists: {output}")
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
