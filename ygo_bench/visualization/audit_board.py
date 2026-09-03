from __future__ import annotations

import html
import json
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy as np


LOCATION_NAMES = {
    1: "Deck",
    2: "Hand",
    3: "Monster Zone",
    4: "Spell & Trap Zone",
    5: "Graveyard",
    6: "Banished",
    7: "Extra Deck",
}
PHASE_NAMES = {
    1: "Draw",
    2: "Standby",
    3: "Main 1",
    4: "Battle Start",
    5: "Battle Step",
    6: "Damage",
    7: "Damage Calculation",
    8: "Battle",
    9: "Main 2",
    10: "End",
}
MESSAGE_NAMES = {
    1: "Select idle command",
    2: "Select chain",
    3: "Select card",
    4: "Select tribute",
    5: "Select position",
    6: "Confirm effect",
    7: "Select yes/no",
    8: "Select battle command",
    9: "Select/unselect card",
    10: "Select option",
    11: "Select place",
    12: "Select sum",
    13: "Select disable field",
    14: "Announce attribute",
    15: "Announce number",
}
# Mirrors ygoenv/edopro/edopro.h cmd_place2id exactly; IDs are one-based.
PLACE_SPECS = (
    "m1", "m2", "m3", "m4", "m5", "m6", "m7",
    "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8",
    "om1", "om2", "om3", "om4", "om5", "om6", "om7",
    "os1", "os2", "os3", "os4", "os5", "os6", "os7", "os8",
)
VISIBILITY_NAMES = {
    0: "padding",
    1: "hidden_private",
    2: "owner_visible",
    3: "public_field",
    4: "confirmed_reveal",
    5: "selectable_own_deck",
    6: "opponent_facedown",
}
HIDDEN_VISIBILITY_CODES = {1, 6}

# A physical Yu-Gi-Oh! card is 59 x 86 mm. CSS enforces this ratio for every
# displayed card, pile, and Extra Monster Zone.
CARD_WIDTH = 100
CARD_HEIGHT = CARD_WIDTH * 86 / 59
HAND_COLUMNS = 10
MAX_RENDERED_HAND_CARDS = 20
MAX_HISTORY_EVENTS = 12
ROOT = Path(__file__).resolve().parents[2]


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_code_list(path: Path) -> list[int]:
    codes = [int(line) for line in path.read_text(encoding="ascii").splitlines()]
    if not codes:
        raise ValueError(f"Code list is empty: {path}")
    return codes


def _load_card_names(cdb_path: Path, codes: set[int]) -> dict[int, str]:
    connection = sqlite3.connect(f"file:{cdb_path}?mode=ro", uri=True)
    try:
        placeholders = ",".join("?" for _ in codes)
        if not placeholders:
            return {}
        rows = connection.execute(
            f"SELECT id, name FROM texts WHERE id IN ({placeholders})",
            sorted(codes),
        ).fetchall()
    finally:
        connection.close()
    return {int(card_code): str(name) for card_code, name in rows}


def _validate_inputs(observation: dict[str, np.ndarray], infos: dict[str, np.ndarray]) -> None:
    required_observation = {"cards_", "global_", "actions_"}
    missing_observation = sorted(required_observation.difference(observation))
    if missing_observation:
        raise ValueError(f"Audit renderer is missing observation fields: {missing_observation}")
    required_info = {"card_visibility_", "num_options", "to_play"}
    missing_info = sorted(required_info.difference(infos))
    if missing_info:
        raise ValueError(f"Audit renderer is missing info fields: {missing_info}")
    cards = np.asarray(observation["cards_"])
    visibility = np.asarray(infos["card_visibility_"])
    if cards.ndim != 3 or cards.shape[0] != 1 or cards.shape[2] != 40:
        raise ValueError(
            "Audit renderer requires cards_ with shape [1, 2*max_cards, 40]; "
            f"got {cards.shape}"
        )
    if cards.shape[1] % 2:
        raise ValueError(f"cards_ player dimension must be even; got {cards.shape[1]}")
    if visibility.shape != cards.shape[:2]:
        raise ValueError(
            "card_visibility_ must align with cards_ rows; "
            f"got {visibility.shape} and {cards.shape[:2]}"
        )
    if np.any((visibility < 0) | (visibility > max(VISIBILITY_NAMES))):
        raise ValueError("card_visibility_ contains an unknown provenance code")
    for name in ("num_options", "to_play"):
        value = np.asarray(infos[name])
        if value.shape != (1,):
            raise ValueError(f"infos[{name!r}] must have shape (1,), got {value.shape}")
    card_ids = (cards[..., 0].astype(np.uint16) << 8) + cards[..., 1]
    hidden = np.isin(visibility, tuple(HIDDEN_VISIBILITY_CODES))
    if np.any(hidden & (card_ids != 0)):
        raise ValueError("Hidden card rows contain a non-zero card ID")


def _decode_card_id(row: np.ndarray) -> int:
    return int((int(row[0]) << 8) + int(row[1]))


def _lp(global_features: np.ndarray, offset: int) -> int:
    return int((int(global_features[offset]) << 8) + int(global_features[offset + 1]))


def _truncate(value: str, width: int = 19) -> str:
    return value if len(value) <= width else f"{value[: width - 1]}..."


def _card_label(card: dict[str, Any]) -> str:
    if card["hidden"]:
        return "CARD BACK"
    return _truncate(card["name"])


def _place_label(place_id: int) -> str:
    if not 1 <= place_id <= len(PLACE_SPECS):
        raise ValueError(f"Unknown action place ID: {place_id}")
    spec = PLACE_SPECS[place_id - 1]
    opponent = spec.startswith("o")
    if opponent:
        spec = spec[1:]
    owner = "opponent's" if opponent else "your"
    sequence = int(spec[1:])
    if spec[0] == "m":
        zone = (
            f"Main Monster Zone {sequence}"
            if sequence <= 5
            else f"Extra Monster Zone {sequence - 5}"
        )
    elif sequence <= 5:
        zone = f"Spell & Trap Zone {sequence}"
    elif sequence == 6:
        zone = "Field Zone"
    elif sequence == 7:
        zone = "Left Pendulum Zone"
    else:
        zone = "Right Pendulum Zone"
    return f"{owner} {zone} [{PLACE_SPECS[place_id - 1]}]"


def _action_summary(
    actions: np.ndarray,
    num_options: int,
    cards_by_row: dict[int, dict[str, Any]],
) -> list[str]:
    if actions.ndim != 3 or actions.shape[0] != 1:
        raise ValueError(f"actions_ must have shape [1, max_options, features]; got {actions.shape}")
    max_options = actions.shape[1]
    if not 0 <= num_options <= max_options:
        raise ValueError(f"num_options {num_options} is outside action capacity {max_options}")
    feature_offset = actions.shape[2] - 10
    if feature_offset < 0 or feature_offset % 2:
        raise ValueError(f"Unexpected action feature width: {actions.shape[2]}")
    summaries: list[str] = []
    for index in range(num_options):
        features = actions[0, index]
        message_id = int(features[feature_offset])
        if message_id in {11, 13}:
            place = _place_label(int(features[feature_offset + 8]))
            verb = "Place card in" if message_id == 11 else "Disable"
            summaries.append(f"{verb} {place}")
            continue
        target_index = int((int(features[0]) << 8) + features[1])
        target = cards_by_row.get(target_index - 1)
        target_label = _card_label(target) if target else None
        message = MESSAGE_NAMES.get(message_id, f"message#{message_id}")
        suffix = f" | {target_label}" if target_label else ""
        summaries.append(f"{message}{suffix}")
    return summaries


def _decode_cards(
    cards: np.ndarray,
    visibility: np.ndarray,
    code_list: list[int],
    card_names: dict[int, str],
) -> list[dict[str, Any]]:
    max_cards = cards.shape[0] // 2
    decoded: list[dict[str, Any]] = []
    for row_index, row in enumerate(cards):
        location_id = int(row[2])
        if location_id == 0:
            continue
        side = "current_player" if row_index < max_cards else "opponent"
        card_id = _decode_card_id(row)
        visibility_code = int(visibility[row_index])
        hidden = visibility_code in HIDDEN_VISIBILITY_CODES or card_id == 0
        if card_id > len(code_list):
            raise ValueError(
                f"Observation card ID {card_id} exceeds code list length {len(code_list)}"
            )
        card_code = code_list[card_id - 1] if card_id else None
        name = card_names.get(card_code, f"Card {card_code}") if card_code else None
        decoded.append(
            {
                "row_index": row_index,
                "side": side,
                "location_id": location_id,
                "location": LOCATION_NAMES.get(location_id, f"Location {location_id}"),
                "sequence": int(row[3]),
                "position_id": int(row[5]),
                "controller_is_opponent": bool(row[4]),
                "visibility_code": visibility_code,
                "visibility": VISIBILITY_NAMES[visibility_code],
                "hidden": hidden,
                "observation_card_id": card_id or None,
                "card_code": card_code,
                "name": name,
            }
        )
    return decoded


def _zone_counts(cards: list[dict[str, Any]], side: str) -> Counter[str]:
    return Counter(card["location"] for card in cards if card["side"] == side)


def _field_cards(cards: list[dict[str, Any]], side: str, location: str) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for card in cards:
        if card["side"] == side and card["location"] == location:
            result[card["sequence"]] = card
    return result


def _zone_cards(cards: list[dict[str, Any]], side: str, location: str) -> list[dict[str, Any]]:
    return sorted(
        (card for card in cards if card["side"] == side and card["location"] == location),
        key=lambda card: card["sequence"],
    )


def _card_image_uri(card: dict[str, Any], card_image_dir: Path | None) -> str | None:
    if card["hidden"] or card_image_dir is None or card["card_code"] is None:
        return None
    image_path = card_image_dir / f"{card['card_code']}.jpg"
    return _file_uri(image_path) if image_path.is_file() else None


def _file_uri(path: Path) -> str:
    """Return a URI usable by Edge launched from WSL or by a native browser."""
    resolved = path.resolve()
    parts = resolved.parts
    if len(parts) >= 4 and parts[1:3] == ("mnt", parts[2]) and len(parts[2]) == 1:
        windows_path = f"{parts[2].upper()}:/{'/'.join(parts[3:])}"
        return f"file:///{quote(windows_path, safe='/:')}"
    return resolved.as_uri()


def _browser_path(path: Path) -> str:
    resolved = path.resolve()
    parts = resolved.parts
    if len(parts) >= 4 and parts[1] == "mnt" and len(parts[2]) == 1:
        return f"{parts[2].upper()}:\\" + "\\".join(parts[3:])
    return str(resolved)


def _card_markup(
    card: dict[str, Any] | None,
    card_image_dir: Path | None,
    empty_label: str,
    monster: bool = False,
) -> str:
    if card is None:
        return f'<div class="card card--empty"><span>{html.escape(empty_label)}</span></div>'
    ownership_class = ""
    if monster:
        ownership_class = (
            " card--monster-opponent"
            if card["side"] == "opponent"
            else " card--monster-current"
        )
    if card["hidden"]:
        return (
            f'<div class="card card--back{ownership_class}" '
            'aria-label="Hidden card"><span>HIDDEN</span></div>'
        )
    image_uri = _card_image_uri(card, card_image_dir)
    label = html.escape(_card_label(card))
    if image_uri:
        return (
            f'<div class="card{ownership_class}">'
            f'<img src="{html.escape(image_uri)}" alt="{label}" /></div>'
        )
    return (
        f'<div class="card card--unavailable{ownership_class}"><span>{label}</span></div>'
    )


def _field_row_markup(
    label: str,
    cards: dict[int, dict[str, Any]],
    card_image_dir: Path | None,
    prefix: str,
    monster: bool = False,
) -> str:
    slots = "".join(
        _card_markup(
            cards.get(index),
            card_image_dir,
            f"{prefix} {index + 1}",
            monster=monster,
        )
        for index in range(5)
    )
    return f'<section class="zone-row"><h3>{html.escape(label)}</h3><div class="zone-slots">{slots}</div></section>'


def _resource_markup(
    location: str,
    cards: list[dict[str, Any]],
    card_image_dir: Path | None,
) -> str:
    display_card = next((card for card in cards if not card["hidden"]), None)
    if display_card is None and cards:
        display_card = cards[0]
    return (
        f'<section class="resource"><h3>{html.escape(location)}</h3>'
        f'<div class="pile">{_card_markup(display_card, card_image_dir, "EMPTY")}</div>'
        f'<p>{len(cards)} cards</p></section>'
    )


def _hand_markup(cards: list[dict[str, Any]], card_image_dir: Path | None) -> str:
    rendered = cards[:MAX_RENDERED_HAND_CARDS]
    slots = "".join(
        _card_markup(card, card_image_dir, f"H {index + 1}")
        for index, card in enumerate(rendered)
    )
    overflow = ""
    if len(cards) > len(rendered):
        overflow = f'<span class="hand-overflow">+{len(cards) - len(rendered)}</span>'
    return (
        f'<section class="hand"><h3>Hand <span>{len(cards)}</span></h3>'
        f'<div class="hand-slots">{slots}{overflow}</div></section>'
    )


def _player_half_markup(
    side: str,
    title: str,
    cards: list[dict[str, Any]],
    card_image_dir: Path | None,
) -> str:
    resources = "".join(
        _resource_markup(location, _zone_cards(cards, side, location), card_image_dir)
        for location in ("Deck", "Extra Deck", "Graveyard", "Banished")
    )
    spell_row = _field_row_markup(
        "Spell & Trap Zone",
        _field_cards(cards, side, "Spell & Trap Zone"),
        card_image_dir,
        "S/T",
    )
    monster_row = _field_row_markup(
        "Main Monster Zone",
        _field_cards(cards, side, "Monster Zone"),
        card_image_dir,
        "M",
        monster=True,
    )
    field_rows = f"{spell_row}{monster_row}" if side == "opponent" else f"{monster_row}{spell_row}"
    player_layout = f"""
      <div class=\"player-layout\">
        <div class=\"resources\">{resources}</div>
        <div class=\"field\">{field_rows}</div>
      </div>
    """
    hand = _hand_markup(_zone_cards(cards, side, "Hand"), card_image_dir)
    content = f"{hand}{player_layout}" if side == "opponent" else f"{player_layout}{hand}"
    return f"""
    <section class=\"player-half player-half--{side}\">
      <h2>{html.escape(title)}</h2>
      {content}
    </section>
    """


def _extra_monster_zone_markup(cards: list[dict[str, Any]], card_image_dir: Path | None) -> str:
    slots: list[str] = []
    for slot_index, sequence in enumerate((5, 6)):
        card = next(
            (
                item
                for item in cards
                if item["location"] == "Monster Zone" and item["sequence"] == sequence
            ),
            None,
        )
        alignment = "left" if slot_index == 0 else "right"
        slots.append(
            f'<div class="emz-slot emz-slot--{alignment}">'
            f'{_card_markup(card, card_image_dir, f"EMZ {sequence - 4}", monster=True)}'
            "</div>"
        )
    return (
        '<section class="emz"><h2>Shared Extra Monster Zones</h2>'
        f'<div class="emz-grid">{"".join(slots)}</div></section>'
    )


def _validate_history_events(history_events: list[dict[str, Any]]) -> None:
    for index, event in enumerate(history_events):
        if not isinstance(event, dict):
            raise ValueError(f"history_events[{index}] must be an object")
        text = event.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"history_events[{index}].text must be a non-empty string")
        card_code = event.get("card_code")
        if card_code is not None and (not isinstance(card_code, int) or card_code <= 0):
            raise ValueError(f"history_events[{index}].card_code must be a positive integer or null")
        hidden = event.get("hidden", card_code is None)
        if not isinstance(hidden, bool):
            raise ValueError(f"history_events[{index}].hidden must be boolean")
        if hidden and card_code is not None:
            raise ValueError(
                f"history_events[{index}] cannot expose card_code for a hidden event"
            )


def _normalize_history_events(
    history_events: list[dict[str, Any]],
    card_names: dict[int, str],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for event in history_events:
        card_code = event.get("card_code")
        hidden = event.get("hidden", card_code is None)
        normalized.append(
            {
                "text": event["text"].strip(),
                "card_code": card_code,
                "hidden": hidden,
                "name": None if hidden else card_names.get(card_code, f"Card {card_code}"),
                "side": event.get("side", "opponent" if hidden else "current_player"),
            }
        )
    return normalized


def _history_markup(
    history_events: list[dict[str, Any]],
    card_image_dir: Path | None,
) -> str:
    visible_events = history_events[-MAX_HISTORY_EVENTS:]
    if not visible_events:
        entries = '<p class="history-empty">No recorded events in this state.</p>'
    else:
        entries = "".join(
            '<article class="history-entry">'
            f'<div class="history-thumb">{_card_markup(event, card_image_dir, "EVENT")}</div>'
            f'<p>{html.escape(event["text"])}</p></article>'
            for event in visible_events
        )
    omitted = len(history_events) - len(visible_events)
    omitted_label = f'<p class="history-omitted">{omitted} older events omitted</p>' if omitted else ""
    return (
        '<aside class="history"><h2>Event history</h2>'
        f'<div class="history-list">{entries}</div>{omitted_label}</aside>'
    )


def _page_markup(
    title: str,
    cards: list[dict[str, Any]],
    card_image_dir: Path | None,
    turn: int,
    phase: str,
    to_play: int,
    current_lp: int,
    opponent_lp: int,
    actions_summary: list[str],
    history_events: list[dict[str, Any]],
) -> str:
    actions = "".join(f"<li>{html.escape(action)}</li>" for action in actions_summary[:8])
    extra_actions = ""
    if len(actions_summary) > 8:
        extra_actions = f'<p class="more-actions">+{len(actions_summary) - 8} more legal actions</p>'
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\" />
<title>{html.escape(title)}</title>
<style>
@page {{ margin: 0; size: 1800px 1920px; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; width: 1800px; min-height: 1920px; color: #eaf2ef; background: #0b1617; font-family: Arial, Helvetica, sans-serif; letter-spacing: 0; }}
.audit {{ width: 1704px; margin: 0 auto; padding: 34px 0 48px; }}
.topbar {{ display: flex; justify-content: space-between; align-items: end; border-bottom: 2px solid #49645a; padding: 0 10px 24px; }}
.eyebrow, h3, .resource p, .hand h3 {{ margin: 0; color: #9fb9ac; font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 0; }}
h1 {{ margin: 8px 0 0; font-size: 31px; line-height: 1.15; }}
.meta {{ color: #c8d5ce; font-size: 17px; }}
.score {{ display: grid; grid-template-columns: repeat(2, auto); gap: 12px 36px; text-align: right; }}
.score strong {{ color: #f4d68b; font-size: 25px; }}
.workspace {{ display: grid; grid-template-columns: minmax(0, 1fr) 286px; gap: 22px; margin-top: 26px; align-items: stretch; }}
.board {{ background: #16332f; border: 2px solid #456d60; padding: 24px 34px; }}
.player-half {{ padding: 18px 0 24px; }}
.player-half h2, .emz h2 {{ margin: 0 0 16px; font-size: 21px; letter-spacing: 0; }}
.player-half--opponent h2 {{ color: #f1c0bc; }} .player-half--current_player h2 {{ color: #b9ead0; }}
.player-layout {{ display: grid; grid-template-columns: 456px 1fr; gap: 56px; align-items: end; }}
.resources {{ display: grid; grid-template-columns: repeat(4, 100px); gap: 18px; align-items: end; }}
.resource {{ min-width: 0; }} .resource h3 {{ color: #d4e2da; height: 33px; line-height: 1.15; }}
.resource p {{ margin-top: 9px; font-size: 12px; text-transform: none; color: #b7c7be; }}
.pile {{ position: relative; width: 100px; }} .pile::before {{ content: \"\"; position: absolute; inset: -6px 6px 6px -6px; background: #10251f; border: 1px solid #638073; z-index: 0; }}
.card {{ position: relative; z-index: 1; width: 100px; aspect-ratio: 59 / 86; overflow: hidden; background: #273d36; border: 1px solid #819387; box-shadow: 0 2px 5px #0008; }}
.card img {{ display: block; width: 100%; height: 100%; object-fit: cover; }}
.card--empty {{ display: grid; place-items: center; color: #6f8980; background: #1b302b; border-style: dashed; box-shadow: none; font-size: 11px; }}
.card--back {{ display: grid; place-items: end center; padding-bottom: 9px; color: #ead9b8; background: radial-gradient(ellipse at center, #130b07 0 13%, #713816 14% 18%, #1d0d08 19% 28%, #a65824 29% 33%, #1a0b07 34% 44%, #733717 45% 50%, #0c0807 51% 100%); border: 4px solid #171310; box-shadow: inset 0 0 0 2px #9c6a3d, 0 2px 5px #0008; font-size: 10px; font-weight: 700; }}
.card--back span {{ padding: 3px 6px; background: #0c0908d9; }}
.card--monster-opponent {{ border: 4px solid #e45d5d; box-shadow: 0 0 0 2px #5c1717, 0 3px 8px #000a; }}
.card--monster-current {{ border: 4px solid #4d9fff; box-shadow: 0 0 0 2px #164a80, 0 3px 8px #000a; }}
.card--unavailable {{ display: grid; place-items: center; padding: 8px; color: #e9eee9; background: #405a51; text-align: center; font-size: 11px; font-weight: 700; }}
.field {{ min-width: 0; }} .zone-row + .zone-row {{ margin-top: 24px; }}
.zone-row h3 {{ margin-bottom: 9px; color: #cce3d5; }} .zone-slots {{ display: grid; grid-template-columns: repeat(5, 100px); gap: 16px; }}
.hand {{ margin: 25px 0 0 512px; }} .player-half--opponent .hand {{ margin-top: 0; margin-bottom: 25px; }} .hand h3 {{ display: flex; gap: 8px; align-items: center; margin-bottom: 10px; color: #d8e7df; }} .hand h3 span {{ color: #f4d68b; font-size: 18px; }}
.hand-slots {{ display: grid; grid-template-columns: repeat(10, 72px); grid-auto-rows: 146px; align-items: start; width: 748px; }}
.hand-slots .card {{ width: 100px; }} .hand-overflow {{ align-self: center; color: #f4d68b; font-size: 19px; font-weight: 700; }}
.emz {{ padding: 20px 0; border-top: 2px solid #bf9e48; border-bottom: 2px solid #bf9e48; }}
.emz h2 {{ margin-left: 512px; color: #f4d68b; font-size: 16px; text-transform: uppercase; }}
.emz-grid {{ display: grid; grid-template-columns: repeat(5, 100px); gap: 16px; margin-left: 512px; }}
.emz-slot {{ position: relative; }} .emz-slot--left {{ grid-column: 2; }} .emz-slot--right {{ grid-column: 4; }}
.history {{ min-width: 0; height: 100%; max-height: 1510px; overflow: hidden; background: #111f20; border: 2px solid #3a5550; padding: 20px 17px; }}
.history h2 {{ margin: 0 0 14px; padding-bottom: 12px; border-bottom: 1px solid #48605b; font-size: 19px; }}
.history-list {{ display: flex; flex-direction: column; gap: 10px; overflow: hidden; }}
.history-entry {{ display: grid; grid-template-columns: 50px 1fr; gap: 11px; align-items: center; min-height: 71px; border-bottom: 1px solid #2f4440; padding-bottom: 10px; }}
.history-thumb {{ width: 50px; height: 71px; overflow: hidden; }} .history-thumb .card {{ width: 50px; height: 71px; box-shadow: none; }}
.history-entry p, .history-empty, .history-omitted {{ margin: 0; color: #d3dfd9; font-size: 13px; line-height: 1.35; }}
.history-empty, .history-omitted {{ color: #91a69c; }} .history-omitted {{ margin-top: 12px; }}
.actions {{ margin-top: 24px; border-top: 2px solid #49645a; padding: 20px 10px 0; }} .actions h2 {{ margin: 0 0 11px; font-size: 19px; }}
.actions ol {{ columns: 2; margin: 0; padding-left: 24px; color: #cfdbd5; line-height: 1.65; font-size: 15px; }} .more-actions {{ color: #9fb9ac; }}
.privacy {{ margin: 24px 10px 0; color: #9fb9ac; font-size: 13px; }}
</style></head><body><main class=\"audit\">
<header class=\"topbar\"><div><p class=\"eyebrow\">Static review terminal</p><h1>{html.escape(title)}</h1><p class=\"meta\">Turn {turn}{'+' if turn == 8 else ''} · {html.escape(phase)} · current decision: P{to_play}</p></div>
<div class=\"score\"><span>Current Player <strong>{current_lp}</strong></span><span>Opponent <strong>{opponent_lp}</strong></span></div></header>
<div class=\"workspace\"><section class=\"board\">{_player_half_markup('opponent', 'Opponent', cards, card_image_dir)}{_extra_monster_zone_markup(cards, card_image_dir)}{_player_half_markup('current_player', 'Current Player', cards, card_image_dir)}</section>{_history_markup(history_events, card_image_dir)}</div>
<section class=\"actions\"><h2>Legal actions visible to the current player ({len(actions_summary)})</h2><ol start=\"0\">{actions}</ol>{extra_actions}</section>
<p class=\"privacy\">Hidden private cards and opponent facedown cards render as card backs. Their identity is not placed in this HTML or its audit manifest.</p>
</main></body></html>"""


def render_html_to_png(
    html_path: Path,
    png_path: Path,
    edge_executable: Path,
    width: int = 1800,
    height: int = 1920,
) -> Path:
    """Use a supplied Microsoft Edge executable to capture a local static audit page."""
    if not html_path.is_file():
        raise FileNotFoundError(f"Audit HTML not found: {html_path}")
    if not edge_executable.is_file():
        raise FileNotFoundError(f"Microsoft Edge executable not found: {edge_executable}")
    png_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(edge_executable.resolve()),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        f"--screenshot={_browser_path(png_path)}",
        _file_uri(html_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "Edge failed to capture the audit board: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    if not png_path.is_file() or png_path.stat().st_size == 0:
        raise RuntimeError(f"Edge did not create audit PNG: {png_path}")
    return png_path


def render_audit_board(
    observation: dict[str, np.ndarray],
    infos: dict[str, np.ndarray],
    code_list_path: Path,
    cdb_path: Path,
    output_path: Path,
    title: str = "YGO-Bench Runtime Audit",
    card_image_dir: Path | None = None,
    edge_executable: Path | None = None,
    history_events: list[dict[str, Any]] | None = None,
) -> dict[str, Path]:
    """Render one agent-visible runtime state as static HTML, JSON, and optional PNG."""
    _validate_inputs(observation, infos)
    code_list_path = code_list_path.resolve()
    cdb_path = cdb_path.resolve()
    output_path = output_path.resolve()
    if output_path.suffix.lower() != ".html":
        raise ValueError(f"Audit renderer output must end in .html: {output_path}")
    if not cdb_path.is_file():
        raise FileNotFoundError(f"Card database not found: {cdb_path}")
    if not code_list_path.is_file():
        raise FileNotFoundError(f"Code list not found: {code_list_path}")
    if card_image_dir is None:
        candidate = ROOT / "data" / "card_images" / code_list_path.parent.name / "full"
        card_image_dir = candidate if candidate.is_dir() else None
    elif not card_image_dir.is_dir():
        raise FileNotFoundError(f"Card image directory not found: {card_image_dir}")
    elif card_image_dir is not None:
        card_image_dir = card_image_dir.resolve()
    history_events = [] if history_events is None else history_events
    _validate_history_events(history_events)

    cards_array = np.asarray(observation["cards_"], dtype=np.uint8)[0]
    global_features = np.asarray(observation["global_"], dtype=np.uint8)[0]
    actions = np.asarray(observation["actions_"], dtype=np.uint8)
    visibility = np.asarray(infos["card_visibility_"], dtype=np.uint8)[0]
    code_list = _load_code_list(code_list_path)
    observation_ids = {
        _decode_card_id(row) for row in cards_array if _decode_card_id(row)
    }
    codes = {code_list[card_id - 1] for card_id in observation_ids if card_id <= len(code_list)}
    codes.update(
        event["card_code"]
        for event in history_events
        if event.get("card_code") is not None
    )
    card_names = _load_card_names(cdb_path, codes)
    cards = _decode_cards(cards_array, visibility, code_list, card_names)
    normalized_history = _normalize_history_events(history_events, card_names)
    cards_by_row = {card["row_index"]: card for card in cards}
    num_options = int(np.asarray(infos["num_options"])[0])
    to_play = int(np.asarray(infos["to_play"])[0])
    actions_summary = _action_summary(actions, num_options, cards_by_row)

    current_counts = _zone_counts(cards, "current_player")
    opponent_counts = _zone_counts(cards, "opponent")
    turn = int(global_features[4])
    phase = PHASE_NAMES.get(int(global_features[5]), f"Phase {int(global_features[5])}")
    current_lp = _lp(global_features, 0)
    opponent_lp = _lp(global_features, 2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _page_markup(
            title,
            cards,
            card_image_dir,
            turn,
            phase,
            to_play,
            current_lp,
            opponent_lp,
            actions_summary,
            normalized_history,
        ),
        encoding="utf-8",
    )
    manifest_path = output_path.with_suffix(".audit.json")
    manifest = {
        "renderer": "ygo_bench.visualization.audit_board",
        "title": title,
        "code_list": str(code_list_path),
        "code_list_sha256": _sha256_file(code_list_path),
        "cdb": str(cdb_path),
        "cdb_sha256": _sha256_file(cdb_path),
        "current_player": f"P{to_play}",
        "turn": turn,
        "phase": phase,
        "life_points": {"current_player": current_lp, "opponent": opponent_lp},
        "zone_counts": {
            "current_player": dict(current_counts),
            "opponent": dict(opponent_counts),
        },
        "legal_actions": actions_summary,
        "history_events": normalized_history,
        "cards": cards,
        "card_images": {
            "directory": str(card_image_dir) if card_image_dir else None,
            "visible_cards_with_local_images": sum(
                _card_image_uri(card, card_image_dir) is not None for card in cards
            ),
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    outputs = {"html": output_path, "manifest": manifest_path}
    if edge_executable is not None:
        png_path = output_path.with_suffix(".png")
        outputs["png"] = render_html_to_png(output_path, png_path, edge_executable.resolve())
    return outputs
