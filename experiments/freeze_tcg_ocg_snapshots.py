from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "snapshots"
SOURCE_DIR = ROOT / "data" / "source_samples" / "ygoprodeck_tournament"
SOURCE_MANIFEST = SOURCE_DIR / "corpus-v0.1.json"
OUTPUT_DIR = ROOT / "data" / "fixed_snapshots"
RUNTIME_CDB = ROOT / "references" / "ygo-agent" / "assets" / "locale" / "en" / "cards.cdb"
CURRENT_SCRIPTS = ROOT / "references" / "cardscripts" / "official"
RUNTIME_SCRIPTS = ROOT / "references" / "ygo-agent" / "scripts" / "script"
RUNTIME_SNAPSHOT_ID = "runtime-modern-v1-2026-07-20"
RUNTIME_SNAPSHOT = ROOT / "snapshots" / f"{RUNTIME_SNAPSHOT_ID}.json"
RUNTIME_CONFIG = ROOT / "configs" / f"{RUNTIME_SNAPSHOT_ID}.json"
RUNTIME_RESULT_DIR = ROOT / "results" / "runtime_modern_v1"
RESET_VERIFIED_STATUS = "reset_smoke_verified_followup_gates_pending"
PENDING_ENGINE_GATES = (
    "legal_action_execution",
    "hidden_information_and_identity",
    "trace_replay_state_hash",
    "environment_lifecycle_100",
    "throughput_1000_steps_per_second",
    "random_eval_32",
)

TYPE_MONSTER = 0x1
TYPE_NORMAL = 0x10
TYPE_TOKEN = 0x4000
TYPE_PENDULUM = 0x1000000


@dataclass(frozen=True)
class EventSpec:
    event_id: str
    snapshot_id: str
    regulation: str
    event_name: str
    event_date: str
    tournament_url: str
    tournament_local_path: str
    tournament_sha256: str
    authority_event_url: str
    retrieved_at: str

    @property
    def tournament_path(self) -> Path:
        return ROOT / self.tournament_local_path


@dataclass(frozen=True)
class DeckSpec:
    event: EventSpec
    snapshot_id: str
    regulation: str
    deck_id: int
    slug: str
    source_url: str
    source_local_path: str
    source_sha256: str
    retrieved_at: str
    expected_category: str
    expected_tournament: str
    runtime_primary: bool
    evidence_level: str

    @property
    def source_path(self) -> Path:
        return ROOT / self.source_local_path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(
            f"{label} keys do not match: missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )


def validate_frozen_source(path: Path, expected_sha256: str, label: str) -> None:
    try:
        path.resolve().relative_to(ROOT)
    except ValueError as error:
        raise ValueError(f"{label} path escapes the repository: {path}") from error
    if not path.is_file():
        raise FileNotFoundError(f"{label} source not found: {path}")
    actual_sha256 = sha256(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"{label} SHA-256 mismatch: expected {expected_sha256}, "
            f"got {actual_sha256}"
        )


def load_corpus() -> tuple[str, tuple[DeckSpec, ...]]:
    payload = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    require_exact_keys(
        payload,
        {"corpus_id", "source_name", "events", "decks", "evidence_level"},
        "Tournament corpus manifest",
    )
    evidence_level = payload["evidence_level"]
    if evidence_level != "curated_deck_with_official_event_crosscheck":
        raise ValueError(f"Unsupported tournament evidence level: {evidence_level}")

    event_keys = {
        "event_id",
        "snapshot_id",
        "regulation",
        "event_name",
        "event_date",
        "tournament_url",
        "tournament_local_path",
        "tournament_sha256",
        "authority_event_url",
        "retrieved_at",
    }
    events: dict[str, EventSpec] = {}
    for index, raw_event in enumerate(payload["events"]):
        require_exact_keys(raw_event, event_keys, f"Event {index}")
        event = EventSpec(**raw_event)
        if event.event_id in events:
            raise ValueError(f"Duplicate tournament event_id: {event.event_id}")
        validate_frozen_source(
            event.tournament_path,
            event.tournament_sha256,
            f"Tournament event {event.event_id}",
        )
        events[event.event_id] = event

    deck_keys = {
        "event_id",
        "snapshot_id",
        "regulation",
        "deck_id",
        "slug",
        "source_url",
        "source_local_path",
        "source_sha256",
        "retrieved_at",
        "expected_category",
        "expected_tournament",
        "runtime_primary",
    }
    specs: list[DeckSpec] = []
    deck_ids: set[int] = set()
    slugs: set[str] = set()
    source_paths: set[str] = set()
    for index, raw_deck in enumerate(payload["decks"]):
        require_exact_keys(raw_deck, deck_keys, f"Deck {index}")
        event_id = raw_deck["event_id"]
        try:
            event = events[event_id]
        except KeyError as error:
            raise ValueError(f"Deck references unknown event_id: {event_id}") from error
        if raw_deck["snapshot_id"] != event.snapshot_id:
            raise ValueError(f"Deck {raw_deck['deck_id']} snapshot does not match event")
        if raw_deck["regulation"] != event.regulation:
            raise ValueError(f"Deck {raw_deck['deck_id']} regulation does not match event")
        spec = DeckSpec(
            event=event,
            evidence_level=evidence_level,
            **{key: value for key, value in raw_deck.items() if key != "event_id"},
        )
        if spec.deck_id in deck_ids:
            raise ValueError(f"Duplicate tournament deck_id: {spec.deck_id}")
        if spec.slug in slugs:
            raise ValueError(f"Duplicate tournament deck slug: {spec.slug}")
        if spec.source_local_path in source_paths:
            raise ValueError(
                f"Duplicate tournament deck source path: {spec.source_local_path}"
            )
        validate_frozen_source(
            spec.source_path,
            spec.source_sha256,
            f"Tournament deck {spec.deck_id}",
        )
        deck_ids.add(spec.deck_id)
        slugs.add(spec.slug)
        source_paths.add(spec.source_local_path)
        specs.append(spec)

    by_snapshot = Counter(spec.snapshot_id for spec in specs)
    primary_by_snapshot = Counter(
        spec.snapshot_id for spec in specs if spec.runtime_primary
    )
    expected_snapshots = {"tcg-kde-e-2026-05-18", "ocg-jp-2026-07-01"}
    if set(by_snapshot) != expected_snapshots:
        raise ValueError(
            f"Tournament corpus snapshots must be {sorted(expected_snapshots)}"
        )
    for snapshot_id in sorted(expected_snapshots):
        if by_snapshot[snapshot_id] < 10:
            raise ValueError(
                f"Tournament corpus requires at least 10 decks for {snapshot_id}"
            )
        if primary_by_snapshot[snapshot_id] != 1:
            raise ValueError(
                f"Tournament corpus requires one runtime primary for {snapshot_id}"
            )
    return payload["corpus_id"], tuple(specs)


def verified_runtime_status() -> str:
    config = json.loads(RUNTIME_CONFIG.read_text(encoding="utf-8"))
    runtime_paths = {
        "config_sha256": RUNTIME_CONFIG,
        "extension_sha256": ROOT / config["extension"],
        "asset_manifest_sha256": ROOT / config["asset_manifest"],
        "runtime_snapshot_sha256": ROOT / config["runtime_snapshot"],
    }
    current_hashes = {name: sha256(path) for name, path in runtime_paths.items()}
    for profile in ("tcg", "ocg"):
        result_path = RUNTIME_RESULT_DIR / f"gate_reset_{profile}.json"
        if not result_path.is_file():
            raise FileNotFoundError(f"Required reset Gate is missing: {result_path}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        expected = {
            "status": "passed",
            "profile": profile,
            "runtime_snapshot_id": RUNTIME_SNAPSHOT_ID,
            "git_dirty": False,
        }
        for key, value in expected.items():
            if result.get(key) != value:
                raise ValueError(
                    f"Reset Gate {profile} has invalid {key}: {result.get(key)!r}"
                )
        for key, value in current_hashes.items():
            if result.get(key) != value:
                raise ValueError(f"Reset Gate {profile} has stale {key}")
        metrics = result.get("metrics", {})
        hidden = metrics.get("hidden_information_reset", {})
        if metrics.get("stage") != "reset" or metrics.get("pool_reset") is not True:
            raise ValueError(f"Reset Gate {profile} did not verify pool reset")
        if metrics.get("pool_destroyed") is not True:
            raise ValueError(f"Reset Gate {profile} did not verify pool destruction")
        if hidden.get("hidden_information_pass") is not True:
            raise ValueError(
                f"Reset Gate {profile} did not pass hidden-information audit"
            )
        if hidden.get("identity_grounding_pass") is not True:
            raise ValueError(f"Reset Gate {profile} did not pass identity grounding")
    return RESET_VERIFIED_STATUS


def extract_one(source: str, pattern: str, label: str) -> str:
    match = re.search(pattern, source, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        raise ValueError(f"Could not extract {label}")
    return html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()


def parse_deck_html(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    zones: dict[str, list[int]] = {}
    for zone, variable in (
        ("main", "maindeckjs"),
        ("extra", "extradeckjs"),
        ("side", "sidedeckjs"),
    ):
        value = extract_one(
            source,
            rf"var\s+{variable}\s*=\s*'([^']+)'",
            variable,
        )
        zones[zone] = [int(card_id) for card_id in json.loads(value)]
    return {
        "deck_name": extract_one(source, r"<h1[^>]*>(.*?)</h1>", "deck name"),
        "category": extract_one(source, r"Category:\s*([^<]+)</p>", "category"),
        "creator": extract_one(source, r"Creator:\s*([^<]+)</p>", "creator"),
        "tournament": extract_one(source, r"Tournament:\s*([^<]+)</p>", "tournament"),
        "placement": extract_one(source, r"Placement:\s*([^<]+)</p>", "placement"),
        "zones": zones,
    }


def load_card_names(database: Path) -> dict[int, str]:
    with sqlite3.connect(database) as connection:
        rows = connection.execute("SELECT id, name FROM texts").fetchall()
    return {int(card_id): str(name) for card_id, name in rows}


def load_card_ids(database: Path) -> set[int]:
    with sqlite3.connect(database) as connection:
        rows = connection.execute("SELECT id FROM datas").fetchall()
    return {int(row[0]) for row in rows}


def load_card_script_metadata(database: Path) -> dict[int, tuple[int, int]]:
    with sqlite3.connect(database) as connection:
        rows = connection.execute("SELECT id, alias, type FROM datas").fetchall()
    return {
        int(card_id): (int(alias), int(card_type))
        for card_id, alias, card_type in rows
    }


def snapshot_artifact_path(artifact: dict[str, str], label: str) -> Path:
    path = ROOT / artifact["path"]
    validate_frozen_source(path, artifact["sha256"].lower(), label)
    return path


def load_snapshot_card_catalog(
    snapshot: dict[str, Any],
) -> tuple[dict[int, str], set[int], dict[int, tuple[int, int]]]:
    artifacts = snapshot["artifacts"]
    cdb_artifacts = [artifacts["cards_cdb"], *artifacts.get("cards_cdb_layers", [])]
    names: dict[int, str] = {}
    metadata: dict[int, tuple[int, int]] = {}
    for index, artifact in enumerate(cdb_artifacts):
        path = snapshot_artifact_path(
            artifact,
            f"Snapshot {snapshot['snapshot_id']} CDB layer {index}",
        )
        names.update(load_card_names(path))
        metadata.update(load_card_script_metadata(path))

    cdb_ids = set(names)
    for index, artifact in enumerate(artifacts.get("card_catalog_supplements", [])):
        path = snapshot_artifact_path(
            artifact,
            f"Snapshot {snapshot['snapshot_id']} card catalog supplement {index}",
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        cards = payload.get("data")
        if not isinstance(cards, list) or not cards:
            raise ValueError(f"Card catalog supplement contains no data: {path}")
        for card in cards:
            card_id = card.get("id")
            name = card.get("name")
            if not isinstance(card_id, int) or card_id <= 0:
                raise ValueError(f"Card catalog supplement has invalid id: {path}")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Card catalog supplement has invalid name: {path}")
            names[card_id] = name
    return names, cdb_ids, metadata


def load_limits(path: Path) -> dict[int, int]:
    limits: dict[int, int] = {}
    active = False
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("!"):
            if active:
                break
            active = True
            continue
        if not active:
            continue
        match = re.match(r"^(\d+)\s+([0123])(?:\s|$)", line)
        if match:
            limits[int(match.group(1))] = int(match.group(2))
    return limits


def grouped_zone(ids: list[int], names: dict[int, str]) -> list[dict[str, Any]]:
    return [
        {
            "card_id": card_id,
            "name": names.get(card_id),
            "quantity": quantity,
        }
        for card_id, quantity in Counter(ids).items()
    ]


def write_ydk(path: Path, zones: dict[str, list[int]]) -> None:
    lines = ["#created by ygo-bench snapshot freezer", "#main"]
    lines.extend(str(card_id) for card_id in zones["main"])
    lines.append("#extra")
    lines.extend(str(card_id) for card_id in zones["extra"])
    lines.append("!side")
    lines.extend(str(card_id) for card_id in zones["side"])
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def coverage(ids: set[int], available: set[int]) -> dict[str, Any]:
    missing = sorted(ids - available)
    return {
        "unique_cards": len(ids),
        "available": len(ids) - len(missing),
        "coverage": (len(ids) - len(missing)) / len(ids),
        "missing_card_ids": missing,
    }


def script_card_ids(directory: Path) -> set[int]:
    return {
        int(match.group(1))
        for path in directory.glob("c*.lua")
        if (match := re.fullmatch(r"c(\d+)", path.stem))
    }


def is_scriptless_card(card_type: int) -> bool:
    is_normal_monster = (
        card_type & TYPE_MONSTER
        and card_type & TYPE_NORMAL
        and not card_type & TYPE_PENDULUM
    )
    return bool(is_normal_monster or card_type & TYPE_TOKEN)


def script_coverage(
    ids: set[int],
    card_metadata: dict[int, tuple[int, int]],
    script_ids: set[int],
) -> dict[str, Any]:
    direct_count = 0
    alias: list[dict[str, int]] = []
    scriptless: list[int] = []
    missing: list[int] = []

    for card_id in sorted(ids):
        metadata = card_metadata.get(card_id)
        if metadata is None:
            missing.append(card_id)
            continue

        alias_id, card_type = metadata
        if card_id in script_ids:
            direct_count += 1
        elif alias_id and alias_id in script_ids:
            alias.append({"card_id": card_id, "script_id": alias_id})
        elif is_scriptless_card(card_type):
            scriptless.append(card_id)
        else:
            missing.append(card_id)

    available = len(ids) - len(missing)
    return {
        "unique_cards": len(ids),
        "available": available,
        "coverage": available / len(ids),
        "direct_script_count": direct_count,
        "alias_script_cards": alias,
        "scriptless_card_ids": scriptless,
        "missing_card_ids": missing,
    }


def main() -> None:
    runtime_snapshot = json.loads(RUNTIME_SNAPSHOT.read_text(encoding="utf-8"))
    if runtime_snapshot.get("runtime_snapshot_id") != RUNTIME_SNAPSHOT_ID:
        raise ValueError("Runtime snapshot ID does not match the fixed deck generator")
    corpus_id, specs = load_corpus()
    runtime_status = verified_runtime_status()
    runtime_config = json.loads(RUNTIME_CONFIG.read_text(encoding="utf-8"))

    snapshots = {
        snapshot_id: json.loads(
            (SNAPSHOT_DIR / f"{snapshot_id}.json").read_text(encoding="utf-8")
        )
        for snapshot_id in sorted({spec.snapshot_id for spec in specs})
    }
    card_catalogs = {
        snapshot_id: load_snapshot_card_catalog(snapshot)
        for snapshot_id, snapshot in snapshots.items()
    }
    runtime_ids = load_card_ids(RUNTIME_CDB)
    runtime_script_metadata = load_card_script_metadata(RUNTIME_CDB)
    current_script_ids = script_card_ids(CURRENT_SCRIPTS)
    runtime_script_ids = script_card_ids(RUNTIME_SCRIPTS)

    manifest: list[dict[str, Any]] = []
    scenarios_by_snapshot: dict[str, list[dict[str, Any]]] = defaultdict(list)
    primary_deck_paths: set[str] = set()
    for spec in specs:
        snapshot = snapshots[spec.snapshot_id]
        catalog_names, snapshot_cdb_ids, snapshot_script_metadata = card_catalogs[
            spec.snapshot_id
        ]
        parsed = parse_deck_html(spec.source_path)
        if parsed["category"] != spec.expected_category:
            raise ValueError(
                f"Deck {spec.deck_id} category mismatch: {parsed['category']!r}"
            )
        if parsed["tournament"] != spec.expected_tournament:
            raise ValueError(
                f"Deck {spec.deck_id} tournament mismatch: "
                f"{parsed['tournament']!r}"
            )
        zones = parsed.pop("zones")
        all_cards = zones["main"] + zones["extra"] + zones["side"]
        unique_ids = set(all_cards)
        counts = Counter(all_cards)
        limits = load_limits(ROOT / snapshot["artifacts"]["lflist"]["path"])
        violations = [
            {
                "card_id": card_id,
                "name": catalog_names.get(card_id),
                "copies": copies,
                "limit": limits.get(card_id, 3),
            }
            for card_id, copies in sorted(counts.items())
            if copies > limits.get(card_id, 3)
        ]

        output = OUTPUT_DIR / spec.snapshot_id
        deck_dir = output / "decks"
        deck_dir.mkdir(parents=True, exist_ok=True)
        ydk_path = deck_dir / f"{spec.slug}.ydk"
        json_path = deck_dir / f"{spec.slug}.json"
        scenario_path = output / "scenarios.json"
        write_ydk(ydk_path, zones)

        checks = {
            "snapshot_card_catalog": coverage(unique_ids, set(catalog_names)),
            "snapshot_cdb": coverage(unique_ids, snapshot_cdb_ids),
            "current_cardscripts": script_coverage(
                unique_ids, snapshot_script_metadata, current_script_ids
            ),
            "ygoenv_runtime_cdb": coverage(unique_ids, runtime_ids),
            "ygoenv_runtime_scripts": script_coverage(
                unique_ids, runtime_script_metadata, runtime_script_ids
            ),
        }
        static_benchmark_ready = (
            not violations
            and not checks["snapshot_card_catalog"]["missing_card_ids"]
        )
        modern_assets_ready = (
            static_benchmark_ready
            and not checks["snapshot_cdb"]["missing_card_ids"]
            and not checks["current_cardscripts"]["missing_card_ids"]
        )
        runtime_adapter_ready = modern_assets_ready and spec.runtime_primary
        engine_ready = False
        deck_record = {
            "corpus_id": corpus_id,
            "snapshot_id": spec.snapshot_id,
            "runtime_snapshot_id": RUNTIME_SNAPSHOT_ID,
            "regulation": spec.regulation,
            "event_id": spec.event.event_id,
            "event_date": spec.event.event_date,
            "deck_id": spec.deck_id,
            "runtime_primary": spec.runtime_primary,
            **parsed,
            "source": {
                "url": spec.source_url,
                "authority_event_url": spec.event.authority_event_url,
                "tournament_url": spec.event.tournament_url,
                "tournament_local_path": spec.event.tournament_local_path,
                "tournament_sha256": spec.event.tournament_sha256,
                "local_path": spec.source_local_path,
                "sha256": spec.source_sha256,
                "retrieved_at": spec.retrieved_at,
                "evidence_level": spec.evidence_level,
            },
            "totals": {zone: len(card_ids) for zone, card_ids in zones.items()},
            "zones": {
                zone: grouped_zone(card_ids, catalog_names)
                for zone, card_ids in zones.items()
            },
            "banlist_violations": violations,
            "coverage": checks,
            "static_benchmark_ready": static_benchmark_ready,
            "modern_assets_ready": modern_assets_ready,
            "runtime_adapter_ready": runtime_adapter_ready,
            "runtime_status": runtime_status,
            "engine_ready": engine_ready,
        }
        json_path.write_text(
            json.dumps(deck_record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        scenario_value: str | None = None
        if spec.runtime_primary:
            relative_ydk = str(ydk_path.relative_to(ROOT)).replace("\\", "/")
            primary_deck_paths.add(relative_ydk)
            scenario = {
                "scenario_id": f"{spec.snapshot_id}-{spec.slug}-seed-1",
                "snapshot_id": spec.snapshot_id,
                "runtime_snapshot_id": RUNTIME_SNAPSHOT_ID,
                "task_family": "strategy",
                "scenario_type": "seeded_full_duel_start",
                "player_deck": relative_ydk,
                "opponent_deck": relative_ydk,
                "requested_seed": 1,
                "engine_seed": 35879119,
                "action_seed": 200001,
                "gold_status": "unlabeled_engine_trace",
                "runtime_adapter_ready": runtime_adapter_ready,
                "runtime_status": runtime_status,
                "engine_ready": engine_ready,
                "blockers": {
                    "banlist_violations": violations,
                    "missing_modern_cdb_ids": checks["snapshot_cdb"][
                        "missing_card_ids"
                    ],
                    "missing_modern_script_ids": checks["current_cardscripts"][
                        "missing_card_ids"
                    ],
                    "missing_runtime_cdb_ids": checks["ygoenv_runtime_cdb"][
                        "missing_card_ids"
                    ],
                    "missing_runtime_script_ids": checks["ygoenv_runtime_scripts"][
                        "missing_card_ids"
                    ],
                    "runtime_adapter": None,
                    "pending_runtime_gates": list(PENDING_ENGINE_GATES),
                },
            }
            scenarios_by_snapshot[spec.snapshot_id].append(scenario)
            scenario_value = str(scenario_path.relative_to(ROOT)).replace("\\", "/")
        manifest.append(
            {
                "corpus_id": corpus_id,
                "snapshot_id": spec.snapshot_id,
                "runtime_snapshot_id": RUNTIME_SNAPSHOT_ID,
                "deck": str(json_path.relative_to(ROOT)).replace("\\", "/"),
                "scenario": scenario_value,
                "runtime_primary": spec.runtime_primary,
                "static_benchmark_ready": static_benchmark_ready,
                "modern_assets_ready": modern_assets_ready,
                "runtime_adapter_ready": runtime_adapter_ready,
                "runtime_status": runtime_status,
                "engine_ready": engine_ready,
                "coverage": checks,
                "banlist_violations": violations,
            }
        )

    configured_deck_paths = set(runtime_config["decks"].values())
    if primary_deck_paths != configured_deck_paths:
        raise ValueError(
            "Runtime-primary corpus decks do not match the modern runtime config: "
            f"corpus={sorted(primary_deck_paths)}, "
            f"config={sorted(configured_deck_paths)}"
        )
    for snapshot_id in sorted(scenarios_by_snapshot):
        scenarios = scenarios_by_snapshot[snapshot_id]
        if len(scenarios) != 1:
            raise ValueError(
                f"Expected one runtime scenario for {snapshot_id}, got {len(scenarios)}"
            )
        scenario_path = OUTPUT_DIR / snapshot_id / "scenarios.json"
        scenario_path.write_text(
            json.dumps({"scenarios": scenarios}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
