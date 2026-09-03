#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "runtime-modern-v1-2026-07-20.json"
TYPE_MONSTER = 0x1
TYPE_NORMAL = 0x10
TYPE_TOKEN = 0x4000
TYPE_PENDULUM = 0x1000000
STATIC_LOAD_PATTERN = re.compile(r"Duel\.LoadScript\s*\(\s*['\"]([^'\"]+)['\"]")
LOAD_CALL_PATTERN = re.compile(r"Duel\.LoadScript\s*\(")
SPECIAL_SCRIPT_PATHS = {
    "proc_unofficial.lua": Path("unofficial") / "proc_unofficial.lua",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def read_ydk(path: Path) -> list[int]:
    cards = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.isdigit():
            cards.append(int(stripped))
    if not cards:
        raise ValueError(f"Deck contains no card IDs: {path}")
    return cards


def is_scriptless(card_type: int) -> bool:
    normal_monster = (
        card_type & TYPE_MONSTER
        and card_type & TYPE_NORMAL
        and not card_type & TYPE_PENDULUM
    )
    return bool(normal_monster or card_type & TYPE_TOKEN)


def resolve_script_path(
    request: str,
    cardscripts: Path,
    card_rows: dict[int, tuple[int, int]],
) -> Path:
    special = SPECIAL_SCRIPT_PATHS.get(request)
    if special is not None:
        path = cardscripts / special
    elif (
        request.startswith("c")
        and request.endswith(".lua")
        and request[1:-4].isdigit()
    ):
        code = int(request[1:-4])
        path = cardscripts / "official" / request
        if not path.is_file() and code in card_rows:
            alias = card_rows[code][0]
            if alias:
                path = cardscripts / "official" / f"c{alias}.lua"
    else:
        path = cardscripts / request
    if not path.is_file():
        raise FileNotFoundError(
            f"CardScripts request cannot be resolved: {request} -> {path}"
        )
    return path


def audit_script_dependencies(
    cardscripts: Path,
    entrypoints: list[str],
    card_rows: dict[int, tuple[int, int]],
) -> dict[str, Any]:
    pending = sorted(set(entrypoints), reverse=True)
    resolved: dict[str, str] = {}
    static_edges: set[tuple[str, str]] = set()
    dynamic_load_calls = 0
    while pending:
        request = pending.pop()
        if request in resolved:
            continue
        path = resolve_script_path(request, cardscripts, card_rows)
        text = path.read_text(encoding="utf-8")
        targets = STATIC_LOAD_PATTERN.findall(text)
        dynamic_load_calls += len(LOAD_CALL_PATTERN.findall(text)) - len(targets)
        resolved[request] = str(path.relative_to(cardscripts)).replace("\\", "/")
        for target in targets:
            static_edges.add((request, target))
            if target not in resolved:
                pending.append(target)
    return {
        "entrypoint_count": len(set(entrypoints)),
        "resolved_script_count": len(resolved),
        "static_load_edge_count": len(static_edges),
        "dynamic_load_call_count": dynamic_load_calls,
        "special_layout_routes": {
            request: str(path).replace("\\", "/")
            for request, path in SPECIAL_SCRIPT_PATHS.items()
        },
        "resolved_scripts": [
            {"request": request, "path": resolved[request]}
            for request in sorted(resolved)
        ],
    }


def deck_record(
    name: str,
    path: Path,
    card_rows: dict[int, tuple[int, int]],
    official_scripts: Path,
) -> dict[str, Any]:
    unique_cards = sorted(set(read_ydk(path)))
    missing_cdb = [code for code in unique_cards if code not in card_rows]
    if missing_cdb:
        raise ValueError(f"Deck {name} has cards missing from BabelCDB: {missing_cdb}")

    direct_scripts = []
    alias_scripts = []
    scriptless_cards = []
    missing_scripts = []
    for code in unique_cards:
        alias, card_type = card_rows[code]
        if (official_scripts / f"c{code}.lua").is_file():
            direct_scripts.append(code)
        elif alias and (official_scripts / f"c{alias}.lua").is_file():
            alias_scripts.append({"card_id": code, "script_id": alias})
        elif is_scriptless(card_type):
            scriptless_cards.append(code)
        else:
            missing_scripts.append(code)
    if missing_scripts:
        raise ValueError(f"Deck {name} has missing effective scripts: {missing_scripts}")

    return {
        "name": name,
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256_file(path),
        "unique_cards": len(unique_cards),
        "direct_script_cards": len(direct_scripts),
        "alias_script_cards": alias_scripts,
        "scriptless_card_ids": scriptless_cards,
        "missing_script_card_ids": [],
        "script_entrypoints": [
            f"c{code}.lua"
            for code in unique_cards
            if code in direct_scripts
            or any(item["card_id"] == code for item in alias_scripts)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    cdb = resolve_path(config["cdb"]).resolve()
    cardscripts = resolve_path(config["cardscripts"]).resolve()
    code_list = resolve_path(config["code_list"]).resolve()
    manifest_path = resolve_path(config["asset_manifest"]).resolve()
    if not cdb.is_file():
        raise FileNotFoundError(f"BabelCDB not found: {cdb}")
    if not cardscripts.is_dir():
        raise FileNotFoundError(f"CardScripts not found: {cardscripts}")

    with sqlite3.connect(cdb) as connection:
        rows = connection.execute(
            "SELECT id, alias, type FROM datas WHERE id > 0 ORDER BY id"
        ).fetchall()
    if not rows:
        raise ValueError(f"BabelCDB contains no positive card IDs: {cdb}")
    if len(rows) > 65535:
        raise ValueError(f"BabelCDB exceeds uint16 card ID capacity: {len(rows)}")
    card_rows = {int(code): (int(alias), int(card_type)) for code, alias, card_type in rows}
    if len(card_rows) != len(rows):
        raise ValueError("BabelCDB contains duplicate card IDs")

    code_list.parent.mkdir(parents=True, exist_ok=True)
    code_list.write_text(
        "".join(f"{code}\n" for code in card_rows), encoding="ascii"
    )

    root_lua = sorted(path.name for path in cardscripts.glob("*.lua"))
    for required in ("constant.lua", "utility.lua"):
        if required not in root_lua:
            raise FileNotFoundError(f"Required CardScripts file not found: {required}")
    official_scripts = cardscripts / "official"
    if not official_scripts.is_dir():
        raise FileNotFoundError(f"Official CardScripts directory not found: {official_scripts}")

    deck_records = []
    for name, value in config["decks"].items():
        path = resolve_path(value).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Fixed deck not found: {path}")
        deck_records.append(deck_record(name, path, card_rows, official_scripts))

    script_entrypoints = ["constant.lua", "utility.lua"]
    for record in deck_records:
        script_entrypoints.extend(record["script_entrypoints"])
    dependency_audit = audit_script_dependencies(
        cardscripts, script_entrypoints, card_rows
    )

    manifest = {
        "runtime_snapshot_id": config["runtime_snapshot_id"],
        "generator": "scripts/prepare_modern_runtime_assets.py",
        "cdb": {
            "path": str(cdb.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(cdb),
            "card_count": len(card_rows),
            "minimum_card_id": min(card_rows),
            "maximum_card_id": max(card_rows),
        },
        "cardscripts": {
            "path": str(cardscripts.relative_to(ROOT)).replace("\\", "/"),
            "root_lua_files": root_lua,
            "official_script_count": sum(1 for _ in official_scripts.glob("c*.lua")),
            "dependency_audit": dependency_audit,
        },
        "code_list": {
            "path": str(code_list.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(code_list),
            "card_count": len(card_rows),
            "ordering": "BabelCDB datas.id ascending",
            "card_id_base": 1,
            "card_id_storage": "uint16",
        },
        "decks": deck_records,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"code_list={code_list}")
    print(f"cards={len(card_rows)}")
    print(f"manifest={manifest_path}")


if __name__ == "__main__":
    main()
