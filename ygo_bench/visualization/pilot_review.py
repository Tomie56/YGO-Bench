from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .audit_board import _file_uri, render_html_to_png


PAGE_WIDTH = 1600
UNDERSTANDING_HEIGHT = 1400
CONSTRUCTION_HEIGHT = 2200
PUZZLE_HEIGHT = 1600

LOCATION_NAMES = {
    "LOCATION_DECK": "Deck",
    "LOCATION_HAND": "Hand",
    "LOCATION_MZONE": "Monster Zone",
    "LOCATION_SZONE": "Spell & Trap Zone",
    "LOCATION_GRAVE": "Graveyard",
    "LOCATION_REMOVED": "Banished",
    "LOCATION_EXTRA": "Extra Deck",
}

ADD_CARD_CALL = re.compile(r"Debug\.AddCard\(([^)\n]+)\)")
PLAYER_INFO_CALL = re.compile(
    r"Debug\.SetPlayerInfo\(\s*([01])\s*,\s*([0-9]+)\s*,\s*([0-9]+)\s*,\s*([0-9]+)\s*\)"
)
AI_NAME_CALL = re.compile(r'Debug\.SetAIName\("([^"]+)"\)')
OBJECTIVE_LINE = re.compile(r"Objective:\s*([^\r\n]+)", re.IGNORECASE)
SHOW_HINT_CALL = re.compile(r'Debug\.ShowHint\("([^"]+)"\)')


@dataclass(frozen=True)
class PuzzleCard:
    card_id: int
    owner: int
    controller: int
    location: str
    sequence: int
    position: str


@dataclass(frozen=True)
class PuzzleState:
    relative_path: str
    title: str
    objective: str
    ai_name: str | None
    player_lp: int
    opponent_lp: int
    cards: tuple[PuzzleCard, ...]
    has_custom_effect: bool
    has_pre_equip: bool
    has_pre_summon: bool
    unparsed_add_card_calls: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Benchmark JSONL not found: {path}")
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON at {path}:{line_number}: {error}") from error
    if not records:
        raise ValueError(f"Benchmark JSONL is empty: {path}")
    return records


def _write_html(path: Path, markup: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markup, encoding="utf-8")
    return path


def _card_image(card_id: int, card_image_dir: Path) -> str:
    path = card_image_dir / f"{card_id}.jpg"
    if not path.is_file():
        return ""
    return _file_uri(path)


def _card_face(
    card_id: int,
    name: str,
    card_image_dir: Path,
    *,
    class_name: str = "",
    hidden: bool = False,
) -> str:
    classes = "card-face"
    if class_name:
        classes += f" {class_name}"
    if hidden:
        return f'<div class="{classes} card-back" aria-label="hidden card"></div>'
    image_uri = _card_image(card_id, card_image_dir)
    if image_uri:
        content = f'<img src="{html.escape(image_uri)}" alt="{html.escape(name)}" />'
    else:
        content = (
            '<div class="missing-art"><strong>NO IMAGE</strong>'
            f'<span>{html.escape(name)}</span><small>{card_id}</small></div>'
        )
    return (
        f'<div class="{classes}" data-card-id="{card_id}" title="{html.escape(name)}">'
        f"{content}</div>"
    )


def _base_css(height: int) -> str:
    return f"""
@page {{ margin: 0; size: {PAGE_WIDTH}px {height}px; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; width: {PAGE_WIDTH}px; min-height: {height}px; }}
body {{ color: #182221; background: #edf0ec; font-family: Arial, "Microsoft YaHei", sans-serif; letter-spacing: 0; }}
.page {{ width: 1512px; min-height: {height}px; margin: 0 auto; padding: 34px 0 40px; }}
.topline {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 28px; padding-bottom: 20px; border-bottom: 3px solid #243b38; }}
.eyebrow {{ margin: 0 0 8px; color: #526a66; font-size: 14px; font-weight: 700; text-transform: uppercase; }}
h1 {{ margin: 0; font-size: 34px; line-height: 1.15; }}
.badges {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; max-width: 620px; }}
.badge {{ padding: 7px 10px; color: #273a37; background: #d8dfdb; border: 1px solid #9eaaa5; font-size: 13px; font-weight: 700; }}
.badge--warn {{ color: #6d350d; background: #f4ddc7; border-color: #cf9c70; }}
.badge--ok {{ color: #174a36; background: #d4e6db; border-color: #80a88f; }}
.panel {{ background: #fff; border: 1px solid #aeb8b4; box-shadow: 0 2px 6px #22332d18; }}
.card-face {{ position: relative; flex: 0 0 auto; overflow: hidden; background: #384640; border: 2px solid #68766f; aspect-ratio: 59 / 86; box-shadow: 0 3px 8px #18241f55; }}
.card-face img {{ display: block; width: 100%; height: 100%; object-fit: cover; }}
.card-back {{ background: radial-gradient(ellipse at center, #130b07 0 13%, #713816 14% 18%, #1d0d08 19% 28%, #a65824 29% 33%, #1a0b07 34% 44%, #733717 45% 50%, #0c0807 51% 100%); border: 5px solid #171310; box-shadow: inset 0 0 0 2px #9c6a3d, 0 3px 8px #18241f55; }}
.missing-art {{ display: flex; flex-direction: column; justify-content: center; align-items: center; width: 100%; height: 100%; padding: 9px; color: #eef3ef; text-align: center; }}
.missing-art strong {{ margin-bottom: 10px; font-size: 11px; }} .missing-art span {{ font-size: 12px; font-weight: 700; }} .missing-art small {{ margin-top: 7px; color: #c3d0c9; }}
"""


def _split_card_text(value: str, card_ids: list[int]) -> list[tuple[str, str]]:
    blocks = [block.strip() for block in value.split("\n\n") if block.strip()]
    if len(card_ids) == 1:
        lines = value.splitlines()
        return [(lines[0].strip(), "\n".join(lines[1:]).strip())]
    if len(blocks) != len(card_ids):
        return [(f"Card {index + 1}", block) for index, block in enumerate(blocks)]
    result = []
    for block in blocks:
        lines = block.splitlines()
        result.append((lines[0].strip(), "\n".join(lines[1:]).strip()))
    return result


def _understanding_page(
    record: dict[str, Any],
    index: int,
    total: int,
    card_image_dir: Path,
) -> str:
    payload = record["input"]
    card_ids = [int(value) for value in payload["card_ids"]]
    card_blocks = _split_card_text(str(payload["card_text"]), card_ids)
    if len(card_blocks) != len(card_ids):
        raise ValueError(f"Cannot align card text and IDs for {record['record_id']}")
    cards = []
    for card_id, (name, description) in zip(card_ids, card_blocks):
        cards.append(
            '<article class="reference-card">'
            f'{_card_face(card_id, name, card_image_dir)}'
            '<div class="reference-text">'
            f'<h3>{html.escape(name)}</h3><p class="passcode">PASSCODE {card_id}</p>'
            f'<p>{html.escape(description)}</p></div></article>'
        )
    evidence = "".join(
        f'<li><strong>{html.escape(str(item["evidence_level"]))}</strong>'
        f'<span>{html.escape(str(item["source_id"]))}</span></li>'
        for item in record["evidence"]
    )
    snapshot = str(record["snapshot_id"])
    regulation = "TCG" if snapshot.startswith("tcg-") else "OCG"
    kind = str(record["candidate_kind"])
    kind_label = {
        "card_semantics": "Card Semantics",
        "rule_and_timing": "Rule & Timing",
        "counterfactual": "Counterfactual Pair",
    }.get(kind, kind)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8" />
<title>{html.escape(record['record_id'])}</title><style>{_base_css(UNDERSTANDING_HEIGHT)}
.question {{ margin-top: 22px; padding: 23px 27px; border-left: 7px solid #c33f35; }}
.question h2 {{ margin: 0 0 10px; color: #536662; font-size: 14px; text-transform: uppercase; }}
.question p {{ margin: 0; font-size: 24px; font-weight: 700; line-height: 1.42; }}
.references {{ display: grid; grid-template-columns: repeat({len(card_ids)}, minmax(0, 1fr)); gap: 18px; margin-top: 20px; }}
.reference-card {{ display: grid; grid-template-columns: 205px 1fr; gap: 18px; min-height: 330px; padding: 18px; background: #fff; border: 1px solid #aeb8b4; }}
.reference-card .card-face {{ width: 205px; }}
.reference-text {{ min-width: 0; }} .reference-text h3 {{ margin: 3px 0 2px; font-size: 20px; line-height: 1.2; }}
.passcode {{ margin: 0 0 13px !important; color: #687a75; font-size: 11px !important; font-weight: 700; }}
.reference-text p:last-child {{ margin: 0; white-space: pre-line; font-size: 14px; line-height: 1.46; }}
.context-grid {{ display: grid; grid-template-columns: 1.3fr .7fr; gap: 18px; margin-top: 20px; }}
.context-grid section {{ padding: 20px 23px; }} .context-grid h2 {{ margin: 0 0 10px; font-size: 17px; }}
.context-grid p {{ margin: 0; font-size: 15px; line-height: 1.5; }}
.evidence {{ margin: 0; padding: 0; list-style: none; }} .evidence li {{ display: flex; justify-content: space-between; gap: 12px; padding: 7px 0; border-bottom: 1px solid #d8dfdc; font-size: 12px; }}
.review {{ margin-top: 20px; padding: 16px 22px; border: 2px dashed #8b9a94; color: #50635e; }}
.review strong {{ margin-right: 24px; color: #243834; }} .review span {{ margin-right: 24px; }}
</style></head><body><main class="page">
<header class="topline"><div><p class="eyebrow">YGO-Bench · Understanding Pilot · 人工题面审阅</p><h1>题目 {index:02d} / {total:02d}</h1></div>
<div class="badges"><span class="badge">{html.escape(kind_label)}</span><span class="badge">{regulation}</span><span class="badge">{html.escape(snapshot)}</span><span class="badge badge--warn">候选题 · 尚无 Gold</span></div></header>
<section class="panel question"><h2>Question</h2><p>{html.escape(str(payload['question']))}</p></section>
<section class="references">{''.join(cards)}</section>
<div class="context-grid"><section class="panel"><h2>规则上下文</h2><p>{html.escape(str(payload['rule_context']))}</p></section>
<section class="panel"><h2>证据状态</h2><ul class="evidence">{evidence}</ul></section></div>
<footer class="review"><strong>审阅结论</strong><span>□ 保留</span><span>□ 修改</span><span>□ 删除</span><span>记录 ID：{html.escape(record['record_id'])}</span></footer>
</main></body></html>"""


def _expanded_zone_cards(zones: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    expanded: dict[str, list[dict[str, Any]]] = {}
    for zone, entries in zones.items():
        cards = []
        for entry in entries:
            quantity = int(entry["quantity"])
            if quantity < 1:
                raise ValueError(f"Invalid quantity {quantity} for card {entry['card_id']}")
            cards.extend([entry] * quantity)
        expanded[zone] = cards
    return expanded


def _deck_zone(
    zone: str,
    entries: list[dict[str, Any]],
    card_image_dir: Path,
    highlighted: set[int],
) -> str:
    title = {"main": "Main Deck", "extra": "Extra Deck", "side": "Side Deck"}[zone]
    cards = "".join(
        _card_face(
            int(entry["card_id"]),
            str(entry["name"]),
            card_image_dir,
            class_name="card-face--changed" if int(entry["card_id"]) in highlighted else "",
        )
        for entry in entries
    )
    return (
        f'<section class="deck-zone deck-zone--{zone}"><header><h2>{title}</h2>'
        f'<strong>{len(entries)}</strong></header><div class="deck-grid">{cards}</div></section>'
    )


def _construction_page(
    records: list[dict[str, Any]],
    index: int,
    total: int,
    card_image_dir: Path,
) -> str:
    by_type = {record["task_type"]: record for record in records}
    required = {
        "source_legality_audit",
        "controlled_corruption_audit",
        "controlled_corruption_minimal_repair",
    }
    if set(by_type) != required:
        raise ValueError(f"Construction group does not contain the expected task types: {set(by_type)}")
    source = by_type["source_legality_audit"]
    corrupted = by_type["controlled_corruption_audit"]
    payload = corrupted["input"]
    mutation = corrupted["target"]["controlled_mutation"]
    highlighted = (
        {int(mutation["added_card_id"])} if "added_card_id" in mutation else set()
    )
    if mutation["kind"] == "replace_with_forbidden_card":
        mutation_text = (
            f"Main Deck: {mutation['removed_card_id']} -> {mutation['added_card_id']}"
        )
    elif mutation["kind"] == "remove_main_card":
        mutation_text = f"Main Deck: removed {mutation['card_id']}"
    else:
        raise ValueError(f"Unknown controlled mutation: {mutation['kind']}")
    expanded = _expanded_zone_cards(payload["zones"])
    task_rows = "".join(
        f'<li><span>{number}</span><div><strong>{html.escape(record["task"])}</strong>'
        f'<p>{html.escape(str(record["input"]["instruction"]))}</p></div></li>'
        for number, record in enumerate((source, corrupted, by_type["controlled_corruption_minimal_repair"]), start=1)
    )
    zones = "".join(
        _deck_zone(zone, expanded[zone], card_image_dir, highlighted)
        for zone in ("main", "extra", "side")
    )
    missing = sorted(
        {
            int(entry["card_id"])
            for entries in expanded.values()
            for entry in entries
            if not _card_image(int(entry["card_id"]), card_image_dir)
        }
    )
    missing_text = ", ".join(map(str, missing)) if missing else "无"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8" />
<title>{html.escape(records[0]['group_id'])}</title><style>{_base_css(CONSTRUCTION_HEIGHT)}
.deck-meta {{ margin-top: 18px; padding: 17px 21px; display: flex; justify-content: space-between; gap: 25px; }}
.deck-meta strong {{ font-size: 22px; }} .deck-meta span {{ color: #5d706b; font-size: 14px; }}
.tasks {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 16px 0 0; padding: 0; list-style: none; }}
.tasks li {{ display: grid; grid-template-columns: 38px 1fr; gap: 12px; min-height: 112px; padding: 14px; background: #fff; border: 1px solid #adb8b3; }}
.tasks li > span {{ display: grid; place-items: center; width: 34px; height: 34px; color: #fff; background: #29443e; font-size: 18px; font-weight: 700; }}
.tasks strong {{ font-size: 15px; }} .tasks p {{ margin: 6px 0 0; color: #435651; font-size: 12px; line-height: 1.38; }}
.deck-zone {{ margin-top: 14px; background: #fff; border: 1px solid #aeb8b4; }}
.deck-zone > header {{ display: flex; align-items: center; gap: 10px; height: 42px; padding: 0 15px; background: #dfe5e1; border-bottom: 1px solid #b6c0bb; }}
.deck-zone h2 {{ margin: 0; font-size: 18px; }} .deck-zone header strong {{ color: #8c2f28; font-size: 18px; }}
.deck-grid {{ display: grid; grid-template-columns: repeat(10, 104px); grid-auto-rows: 152px; gap: 9px 14px; padding: 14px; }}
.deck-grid .card-face {{ width: 104px; height: 152px; }} .card-face--changed {{ border: 5px solid #d34134; box-shadow: 0 0 0 3px #f0b4ae, 0 3px 8px #18241f55; }}
.deck-zone--extra > header {{ background: #dbe4eb; }} .deck-zone--side > header {{ background: #ebe5d3; }}
.legend {{ margin-top: 14px; padding: 13px 17px; color: #4c5f59; font-size: 13px; }} .legend strong {{ color: #b23229; }}
</style></head><body><main class="page">
<header class="topline"><div><p class="eyebrow">YGO-Bench · Construction Pilot · 组级审阅</p><h1>构筑组 {index:02d} / {total:02d}</h1></div>
<div class="badges"><span class="badge">{html.escape(payload['regulation'])}</span><span class="badge">{html.escape(records[0]['snapshot_id'])}</span><span class="badge badge--ok">3 道题共用一副牌组</span><span class="badge badge--warn">题面模式 · Target 隐藏</span></div></header>
<section class="panel deck-meta"><strong>{html.escape(payload['deck_name'])}</strong><span>赛事日期 {html.escape(payload['event_date'])}</span><span>组 ID {html.escape(records[0]['group_id'])}</span></section>
<ol class="tasks">{task_rows}</ol>{zones}
<footer class="panel legend"><strong>受控变异</strong>：{html.escape(mutation_text)}。红框表示损坏后新出现的卡；纯删除题没有可在损坏牌组中加框的卡。卡面不叠加数量。缺失卡图 ID：{html.escape(missing_text)}</footer>
</main></body></html>"""


def _parse_int(value: str) -> int | None:
    value = value.strip()
    return int(value, 10) if re.fullmatch(r"[0-9]+", value) else None


def parse_puzzle(path: Path, puzzle_root: Path) -> PuzzleState:
    source = path.read_text(encoding="utf-8-sig", errors="strict")
    cards = []
    unparsed = 0
    for match in ADD_CARD_CALL.finditer(source):
        arguments = [value.strip() for value in match.group(1).split(",")]
        if len(arguments) < 6:
            unparsed += 1
            continue
        card_id = _parse_int(arguments[0])
        owner = _parse_int(arguments[1])
        controller = _parse_int(arguments[2])
        sequence = _parse_int(arguments[4])
        if (
            card_id is None
            or owner not in {0, 1}
            or controller not in {0, 1}
            or sequence is None
            or arguments[3] not in LOCATION_NAMES
        ):
            unparsed += 1
            continue
        cards.append(
            PuzzleCard(
                card_id=card_id,
                owner=owner,
                controller=controller,
                location=arguments[3],
                sequence=sequence,
                position=arguments[5],
            )
        )
    player_info = {int(player): int(lp) for player, lp, _, _ in PLAYER_INFO_CALL.findall(source)}
    objective_match = OBJECTIVE_LINE.search(source)
    hints = SHOW_HINT_CALL.findall(source)
    objective = objective_match.group(1).strip() if objective_match else (hints[-1] if hints else "Objective not stated")
    ai_match = AI_NAME_CALL.search(source)
    title = path.stem.replace("_", " ")
    return PuzzleState(
        relative_path=path.relative_to(puzzle_root).as_posix(),
        title=title,
        objective=objective,
        ai_name=ai_match.group(1) if ai_match else None,
        player_lp=player_info.get(0, 8000),
        opponent_lp=player_info.get(1, 8000),
        cards=tuple(cards),
        has_custom_effect="Effect.CreateEffect" in source,
        has_pre_equip="Debug.PreEquip" in source,
        has_pre_summon="Debug.PreSummon" in source,
        unparsed_add_card_calls=unparsed,
    )


def _load_card_names(cdb_paths: Iterable[Path]) -> dict[int, str]:
    names: dict[int, str] = {}
    for path in cdb_paths:
        if not path.is_file():
            raise FileNotFoundError(f"Card database not found: {path}")
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
            for card_id, name in connection.execute("SELECT id, name FROM texts"):
                names[int(card_id)] = str(name)
    return names


def select_static_puzzles(
    puzzle_root: Path,
    card_names: dict[int, str],
    card_script_dir: Path,
) -> list[Path]:
    selected = []
    for path in sorted(puzzle_root.rglob("*.lua")):
        if path.relative_to(puzzle_root).parts[0].startswith("RUSH DUEL"):
            continue
        source = path.read_text(encoding="utf-8-sig", errors="strict")
        if "aux.BeginPuzzle()" not in source:
            continue
        card_ids = {int(value.lstrip("0") or "0") for value in re.findall(r"Debug\.AddCard\(\s*([0-9]+)", source)}
        if all(card_id in card_names for card_id in card_ids) and all(
            (card_script_dir / f"c{card_id}.lua").is_file() for card_id in card_ids
        ):
            selected.append(path)
    return selected


def _is_hidden(card: PuzzleCard) -> bool:
    if card.location == "LOCATION_HAND":
        return card.controller == 1
    if card.location in {"LOCATION_DECK", "LOCATION_EXTRA"}:
        return card.controller == 1 or card.location == "LOCATION_DECK"
    return "FACEDOWN" in card.position


def _zone_card(
    card: PuzzleCard | None,
    card_names: dict[int, str],
    card_image_dir: Path,
    label: str,
) -> str:
    if card is None:
        return f'<div class="field-card field-card--empty"><span>{html.escape(label)}</span></div>'
    name = card_names.get(card.card_id, f"Card {card.card_id}")
    ownership_class = ""
    if card.location == "LOCATION_MZONE":
        ownership_class = (
            "card-face--monster-player"
            if card.controller == 0
            else "card-face--monster-opponent"
        )
    return _card_face(
        card.card_id,
        name,
        card_image_dir,
        class_name=ownership_class,
        hidden=_is_hidden(card),
    )


def _hand_markup(
    cards: list[PuzzleCard],
    card_names: dict[int, str],
    card_image_dir: Path,
) -> str:
    overlap = min(68, max(20, 930 // max(1, len(cards))))
    markup = "".join(
        _zone_card(card, card_names, card_image_dir, "Hand") for card in cards[:20]
    )
    omitted = f'<span class="omitted">+{len(cards) - 20}</span>' if len(cards) > 20 else ""
    return f'<div class="hand" style="--advance:{overlap}px">{markup}{omitted}</div>'


def _pile_markup(
    label: str,
    cards: list[PuzzleCard],
    card_names: dict[int, str],
    card_image_dir: Path,
) -> str:
    top = cards[-1] if cards else None
    return (
        '<div class="pile"><span class="pile-label">'
        f'{html.escape(label)}</span>{_zone_card(top, card_names, card_image_dir, label)}'
        f'<strong>{len(cards)}</strong></div>'
    )


def _player_field(
    controller: int,
    cards: list[PuzzleCard],
    card_names: dict[int, str],
    card_image_dir: Path,
) -> str:
    by_location: dict[str, list[PuzzleCard]] = defaultdict(list)
    for card in cards:
        if card.controller == controller:
            by_location[card.location].append(card)
    monster_by_sequence = {card.sequence: card for card in by_location["LOCATION_MZONE"]}
    spell_by_sequence = {card.sequence: card for card in by_location["LOCATION_SZONE"]}
    zones = []
    for sequence in range(5):
        zones.append(_zone_card(monster_by_sequence.get(sequence), card_names, card_image_dir, f"M{sequence + 1}"))
    monsters = "".join(zones)
    spells = "".join(
        _zone_card(spell_by_sequence.get(sequence), card_names, card_image_dir, f"S{sequence + 1}")
        for sequence in range(5)
    )
    piles = "".join(
        _pile_markup(label, by_location[location], card_names, card_image_dir)
        for label, location in (
            ("Deck", "LOCATION_DECK"),
            ("GY", "LOCATION_GRAVE"),
            ("Banished", "LOCATION_REMOVED"),
            ("Extra", "LOCATION_EXTRA"),
        )
    )
    return f'<div class="field-half"><div class="zone-grid monsters">{monsters}</div><div class="zone-grid spells">{spells}</div><aside class="piles">{piles}</aside></div>'


def _puzzle_page(
    state: PuzzleState,
    index: int,
    total: int,
    card_names: dict[int, str],
    card_image_dir: Path,
) -> str:
    cards = list(state.cards)
    opponent_hand = [card for card in cards if card.controller == 1 and card.location == "LOCATION_HAND"]
    player_hand = [card for card in cards if card.controller == 0 and card.location == "LOCATION_HAND"]
    extra_monsters = [
        card
        for card in cards
        if card.location == "LOCATION_MZONE" and card.sequence in {5, 6}
    ]
    emz = "".join(
        _zone_card(
            next((card for card in extra_monsters if card.sequence == sequence), None),
            card_names,
            card_image_dir,
            f"EMZ {sequence - 4}",
        )
        for sequence in (5, 6)
    )
    warnings = []
    if state.has_custom_effect:
        warnings.append("含自定义 Effect")
    if state.unparsed_add_card_calls:
        warnings.append(f"{state.unparsed_add_card_calls} 个 AddCard 未解析")
    warning_badges = "".join(f'<span class="badge badge--warn">{html.escape(value)}</span>' for value in warnings)
    flags = []
    if state.has_pre_equip:
        flags.append("PreEquip")
    if state.has_pre_summon:
        flags.append("PreSummon")
    flag_text = "、".join(flags) if flags else "无额外预处理标记"
    missing_images = sorted(
        {card.card_id for card in cards if not _card_image(card.card_id, card_image_dir)}
    )
    missing_text = ", ".join(map(str, missing_images)) if missing_images else "无"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8" />
<title>{html.escape(state.title)}</title><style>{_base_css(PUZZLE_HEIGHT)}
.objective {{ margin-top: 17px; padding: 16px 21px; display: flex; align-items: center; gap: 18px; border-left: 7px solid #c23d33; }}
.objective strong {{ flex: 0 0 auto; font-size: 14px; text-transform: uppercase; }} .objective span {{ font-size: 21px; font-weight: 700; }}
.duel {{ position: relative; margin-top: 16px; height: 1160px; overflow: hidden; color: #edf4ef; background: #193d35; border: 8px solid #26342f; box-shadow: inset 0 0 0 2px #6f8178; }}
.duel::before {{ content: ""; position: absolute; inset: 0; background-image: linear-gradient(#ffffff0b 1px, transparent 1px), linear-gradient(90deg, #ffffff0b 1px, transparent 1px); background-size: 46px 46px; }}
.lp-row {{ position: absolute; z-index: 3; left: 28px; right: 28px; display: flex; justify-content: space-between; align-items: center; height: 54px; padding: 0 18px; background: #102923dd; border: 1px solid #6a8177; }}
.lp-row--opponent {{ top: 18px; }} .lp-row--player {{ bottom: 18px; }} .lp-row strong {{ color: #f0ce76; font-size: 27px; }}
.hand-wrap {{ position: absolute; z-index: 4; left: 250px; width: 1000px; height: 145px; display: flex; align-items: center; justify-content: center; }}
.hand-wrap--opponent {{ top: 80px; }} .hand-wrap--player {{ bottom: 80px; }}
.hand {{ position: relative; display: flex; justify-content: center; height: 132px; }} .hand .card-face {{ width: 90px; height: 131px; margin-left: calc((90px - var(--advance)) * -1); }} .hand .card-face:first-child {{ margin-left: 0; }}
.omitted {{ align-self: center; margin-left: 9px; padding: 8px; background: #102923; font-weight: 700; }}
.board-core {{ position: absolute; z-index: 2; left: 50%; top: 230px; width: 1180px; height: 700px; transform: translateX(-50%); }}
.field-half {{ position: absolute; left: 160px; width: 700px; height: 285px; }} .field-half:nth-of-type(1) {{ top: 0; }} .field-half:nth-of-type(3) {{ bottom: 0; }}
.zone-grid {{ position: absolute; left: 0; display: grid; grid-template-columns: repeat(5, 92px); gap: 16px; }} .monsters {{ top: 0; }} .spells {{ top: 150px; }}
.field-card, .field-half .card-face, .emz .card-face {{ width: 92px; height: 134px; }}
.card-face--monster-player {{ border: 4px solid #2e8dd2; }} .card-face--monster-opponent {{ border: 4px solid #d64a43; }}
.field-card--empty {{ display: grid; place-items: center; color: #9bb3a9; border: 2px solid #87a09677; font-size: 12px; font-weight: 700; }}
.piles {{ position: absolute; left: 570px; top: 0; display: grid; grid-template-columns: repeat(2, 92px); gap: 16px 18px; }}
.pile {{ position: relative; width: 92px; height: 134px; }} .pile .card-face, .pile .field-card {{ width: 92px; height: 134px; }} .pile-label {{ position: absolute; z-index: 5; left: 3px; top: 3px; padding: 3px 5px; color: #fff; background: #102923dd; font-size: 10px; }}
.pile > strong {{ position: absolute; z-index: 5; right: 4px; bottom: 4px; min-width: 25px; padding: 3px; color: #102923; background: #f0ce76; text-align: center; font-size: 13px; }}
.emz {{ position: absolute; z-index: 4; left: 321px; top: 282px; display: grid; grid-template-columns: repeat(2, 92px); gap: 32px; }}
.audit-note {{ margin-top: 14px; padding: 13px 17px; color: #4d615b; font-size: 13px; line-height: 1.45; }}
</style></head><body><main class="page">
<header class="topline"><div><p class="eyebrow">YGO-Bench · Project Ignis Puzzle · 初始局面审阅</p><h1>{index:02d} / {total:02d} · {html.escape(state.title)}</h1></div>
<div class="badges"><span class="badge badge--warn">仅静态解析</span><span class="badge">尚未 core 验证</span>{warning_badges}</div></header>
<section class="panel objective"><strong>Objective</strong><span>{html.escape(state.objective)}</span></section>
<section class="duel"><div class="lp-row lp-row--opponent"><span>Opponent · {html.escape(state.ai_name or 'AI')}</span><strong>{state.opponent_lp} LP</strong></div>
<div class="hand-wrap hand-wrap--opponent">{_hand_markup(opponent_hand, card_names, card_image_dir)}</div>
<div class="board-core">{_player_field(1, cards, card_names, card_image_dir)}<div class="emz">{emz}</div>{_player_field(0, cards, card_names, card_image_dir)}</div>
<div class="hand-wrap hand-wrap--player">{_hand_markup(player_hand, card_names, card_image_dir)}</div>
<div class="lp-row lp-row--player"><span>Player 0 · 当前解题者</span><strong>{state.player_lp} LP</strong></div></section>
<footer class="panel audit-note">来源：{html.escape(state.relative_path)} · 已解析 {len(cards)} 张初始卡 · {html.escape(flag_text)} · 缺失卡图 ID：{html.escape(missing_text)}。该图片只证明 Lua 初始状态可以被静态读取，不证明合法动作、连锁、结算或解答轨迹已由 ygopro-core 验证。</footer>
</main></body></html>"""


def _render_pages(
    pages: list[tuple[str, str, int]],
    output_dir: Path,
    edge_executable: Path | None,
) -> list[dict[str, str]]:
    outputs = []
    for stem, markup, height in pages:
        html_path = _write_html(output_dir / f"{stem}.html", markup)
        record = {"html": html_path.name}
        if edge_executable is not None:
            png_path = render_html_to_png(
                html_path,
                html_path.with_suffix(".png"),
                edge_executable,
                width=PAGE_WIDTH,
                height=height,
            )
            record["png"] = png_path.name
        outputs.append(record)
    return outputs


def render_pilot_review_bundle(
    understanding_path: Path,
    construction_path: Path,
    puzzle_root: Path,
    card_image_dir: Path,
    cdb_paths: Iterable[Path],
    card_script_dir: Path,
    output_dir: Path,
    edge_executable: Path | None = None,
) -> Path:
    """Render current static pilots and statically eligible puzzles for human review."""
    card_image_dir = card_image_dir.resolve()
    if not card_image_dir.is_dir():
        raise FileNotFoundError(f"Card image directory not found: {card_image_dir}")
    if not puzzle_root.is_dir():
        raise FileNotFoundError(f"Puzzle directory not found: {puzzle_root}")
    if not card_script_dir.is_dir():
        raise FileNotFoundError(f"CardScript directory not found: {card_script_dir}")
    if edge_executable is not None and not edge_executable.is_file():
        raise FileNotFoundError(f"Edge executable not found: {edge_executable}")

    understanding = _read_jsonl(understanding_path)
    construction = _read_jsonl(construction_path)
    card_names = _load_card_names(cdb_paths)
    output_dir.mkdir(parents=True, exist_ok=True)

    understanding_pages = [
        (
            f"{index:02d}-{record['record_id']}",
            _understanding_page(record, index, len(understanding), card_image_dir),
            UNDERSTANDING_HEIGHT,
        )
        for index, record in enumerate(understanding, start=1)
    ]

    construction_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in construction:
        construction_groups[str(record["group_id"])].append(record)
    sorted_groups = sorted(construction_groups.items())
    construction_pages = [
        (
            f"{index:02d}-{group_id}",
            _construction_page(records, index, len(sorted_groups), card_image_dir),
            CONSTRUCTION_HEIGHT,
        )
        for index, (group_id, records) in enumerate(sorted_groups, start=1)
    ]

    puzzle_paths = select_static_puzzles(puzzle_root, card_names, card_script_dir)
    puzzle_states = [parse_puzzle(path, puzzle_root) for path in puzzle_paths]
    puzzle_pages = [
        (
            f"{index:02d}-{re.sub(r'[^a-zA-Z0-9_-]+', '-', state.title).strip('-')}",
            _puzzle_page(state, index, len(puzzle_states), card_names, card_image_dir),
            PUZZLE_HEIGHT,
        )
        for index, state in enumerate(puzzle_states, start=1)
    ]

    rendered = {
        "understanding": _render_pages(
            understanding_pages, output_dir / "understanding", edge_executable
        ),
        "construction": _render_pages(
            construction_pages, output_dir / "construction", edge_executable
        ),
        "puzzles": _render_pages(puzzle_pages, output_dir / "puzzles", edge_executable),
    }
    manifest = {
        "renderer": "ygo_bench.visualization.pilot_review",
        "inputs": {
            "understanding": str(understanding_path.resolve()),
            "understanding_sha256": _sha256(understanding_path),
            "construction": str(construction_path.resolve()),
            "construction_sha256": _sha256(construction_path),
            "puzzle_root": str(puzzle_root.resolve()),
            "card_image_dir": str(card_image_dir),
        },
        "counts": {
            "understanding_questions": len(understanding),
            "construction_questions": len(construction),
            "construction_review_pages": len(sorted_groups),
            "static_puzzle_candidates": len(puzzle_states),
        },
        "puzzle_status": {
            "static_initial_state_rendered": True,
            "core_executed": False,
            "legal_actions_verified": False,
            "solution_trace_verified": False,
            "states_with_custom_effects": sum(state.has_custom_effect for state in puzzle_states),
            "states_with_unparsed_add_card_calls": sum(
                bool(state.unparsed_add_card_calls) for state in puzzle_states
            ),
        },
        "puzzle_states": [asdict(state) for state in puzzle_states],
        "outputs": rendered,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path
