from __future__ import annotations

import html
import json
import sqlite3
from collections import Counter
from pathlib import Path

from .audit_board import _file_uri, _sha256_file, render_html_to_png


SECTION_MARKERS = {
    "#main": "main",
    "#extra": "extra",
    "!side": "side",
}
SECTION_TITLES = {
    "main": "Main Deck",
    "extra": "Extra Deck",
    "side": "Side Deck",
}


def load_ydk_sections(path: Path) -> dict[str, list[int]]:
    if not path.is_file():
        raise FileNotFoundError(f"YDK deck not found: {path}")
    sections = {name: [] for name in SECTION_TITLES}
    current_section: str | None = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = line.strip()
        if value in SECTION_MARKERS:
            current_section = SECTION_MARKERS[value]
        elif not value or value.startswith("#"):
            continue
        elif value.isdigit():
            if current_section is None:
                raise ValueError(
                    f"Card passcode appears before a YDK section at {path}:{line_number}"
                )
            sections[current_section].append(int(value))
        else:
            raise ValueError(f"Invalid YDK line at {path}:{line_number}: {value!r}")
    if not sections["main"]:
        raise ValueError(f"YDK Main Deck is empty: {path}")
    return sections


def _load_card_names(cdb_path: Path, passcodes: set[int]) -> dict[int, str]:
    connection = sqlite3.connect(f"file:{cdb_path}?mode=ro", uri=True)
    try:
        placeholders = ",".join("?" for _ in passcodes)
        rows = connection.execute(
            f"SELECT id, name FROM texts WHERE id IN ({placeholders})",
            sorted(passcodes),
        ).fetchall()
    finally:
        connection.close()
    return {int(passcode): str(name) for passcode, name in rows}


def _deck_card_markup(
    passcode: int,
    card_names: dict[int, str],
    card_image_dir: Path,
) -> str:
    name = card_names.get(passcode, f"Card {passcode}")
    image_path = card_image_dir / f"{passcode}.jpg"
    escaped_name = html.escape(name)
    if image_path.is_file():
        card_face = (
            f'<img src="{html.escape(_file_uri(image_path))}" '
            f'alt="{escaped_name}" />'
        )
    else:
        card_face = f'<span class="card-fallback">{escaped_name}</span>'
    return (
        f'<figure class="deck-card" data-card-code="{passcode}" '
        f'title="{escaped_name}">{card_face}</figure>'
    )


def _section_markup(
    section: str,
    passcodes: list[int],
    card_names: dict[int, str],
    card_image_dir: Path,
) -> str:
    cards = "".join(
        _deck_card_markup(passcode, card_names, card_image_dir)
        for passcode in passcodes
    )
    return (
        f'<section class="deck-section deck-section--{section}">'
        f'<header><h2>{SECTION_TITLES[section]}</h2><strong>{len(passcodes)}</strong></header>'
        f'<div class="deck-grid">{cards}</div></section>'
    )


def _page_markup(
    title: str,
    sections: dict[str, list[int]],
    card_names: dict[int, str],
    card_image_dir: Path,
) -> str:
    unique_cards = len(set().union(*map(set, sections.values())))
    section_markup = "".join(
        _section_markup(section, sections[section], card_names, card_image_dir)
        for section in ("main", "extra", "side")
    )
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\" />
<title>{html.escape(title)}</title>
<style>
@page {{ margin: 0; size: 1600px 2140px; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; width: 1600px; min-height: 2140px; color: #eaf1ef; background: #091215; font-family: Arial, Helvetica, sans-serif; letter-spacing: 0; }}
.deck-audit {{ width: 1510px; margin: 0 auto; padding: 30px 0 44px; }}
.deck-header {{ display: flex; justify-content: space-between; align-items: end; padding: 0 16px 22px; border-bottom: 2px solid #52646b; }}
.eyebrow {{ margin: 0 0 7px; color: #94a8a8; font-size: 13px; font-weight: 700; text-transform: uppercase; }}
h1 {{ margin: 0; font-size: 30px; line-height: 1.15; }}
.counts {{ display: flex; gap: 25px; color: #afc0bd; font-size: 14px; }} .counts strong {{ margin-left: 7px; color: #f2cf78; font-size: 21px; }}
.deck-section {{ margin-top: 18px; border: 1px solid #46575c; background: #102126; }}
.deck-section > header {{ display: flex; align-items: center; gap: 12px; height: 48px; padding: 0 18px; border-bottom: 1px solid #40545a; background: #172a30; }}
.deck-section h2 {{ margin: 0; font-size: 21px; }} .deck-section header strong {{ color: #f2cf78; font-size: 22px; }}
.deck-grid {{ display: grid; grid-template-columns: repeat(10, 108px); grid-auto-rows: 169px; gap: 10px 15px; align-content: start; min-height: 188px; padding: 17px 18px 22px; }}
.deck-card {{ position: relative; width: 108px; height: 158px; margin: 0; overflow: hidden; background: #30413d; border: 1px solid #8c9a95; box-shadow: 0 3px 7px #0009; }}
.deck-card img {{ display: block; width: 100%; height: 100%; object-fit: cover; }}
.card-fallback {{ display: grid; place-items: center; height: 100%; padding: 8px; color: #dfe8e3; text-align: center; font-size: 12px; font-weight: 700; }}
.deck-section--extra {{ border-color: #506b88; }} .deck-section--extra > header {{ background: #192b3a; }}
.deck-section--side {{ border-color: #746b4c; }} .deck-section--side > header {{ background: #302c1f; }}
</style></head><body><main class=\"deck-audit\">
<header class=\"deck-header\"><div><p class=\"eyebrow\">Construction benchmark review</p><h1>{html.escape(title)}</h1></div>
<div class=\"counts\"><span>Main<strong>{len(sections['main'])}</strong></span><span>Extra<strong>{len(sections['extra'])}</strong></span><span>Side<strong>{len(sections['side'])}</strong></span><span>Unique<strong>{unique_cards}</strong></span></div></header>
{section_markup}</main></body></html>"""


def render_deck_board(
    ydk_path: Path,
    cdb_path: Path,
    card_image_dir: Path,
    output_path: Path,
    title: str | None = None,
    edge_executable: Path | None = None,
) -> dict[str, Path]:
    """Render a frozen YDK deck as static HTML, JSON, and optional Edge PNG."""
    ydk_path = ydk_path.resolve()
    cdb_path = cdb_path.resolve()
    card_image_dir = card_image_dir.resolve()
    output_path = output_path.resolve()
    if output_path.suffix.lower() != ".html":
        raise ValueError(f"Deck renderer output must end in .html: {output_path}")
    if not cdb_path.is_file():
        raise FileNotFoundError(f"Card database not found: {cdb_path}")
    if not card_image_dir.is_dir():
        raise FileNotFoundError(f"Card image directory not found: {card_image_dir}")

    sections = load_ydk_sections(ydk_path)
    passcodes = set().union(*map(set, sections.values()))
    card_names = _load_card_names(cdb_path, passcodes)
    title = title or ydk_path.stem.replace("-", " ").title()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _page_markup(title, sections, card_names, card_image_dir),
        encoding="utf-8",
    )

    manifest_path = output_path.with_suffix(".deck.json")
    manifest = {
        "renderer": "ygo_bench.visualization.deck_board",
        "title": title,
        "ydk": str(ydk_path),
        "ydk_sha256": _sha256_file(ydk_path),
        "cdb": str(cdb_path),
        "cdb_sha256": _sha256_file(cdb_path),
        "card_image_directory": str(card_image_dir),
        "counts": {section: len(cards) for section, cards in sections.items()},
        "unique_card_count": len(passcodes),
        "sections": {
            section: [
                {
                    "index": index,
                    "card_code": passcode,
                    "name": card_names.get(passcode, f"Card {passcode}"),
                    "copy_number": Counter(cards[: index + 1])[passcode],
                    "image_available": (card_image_dir / f"{passcode}.jpg").is_file(),
                }
                for index, passcode in enumerate(cards)
            ]
            for section, cards in sections.items()
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    outputs = {"html": output_path, "manifest": manifest_path}
    if edge_executable is not None:
        png_path = output_path.with_suffix(".png")
        outputs["png"] = render_html_to_png(
            output_path,
            png_path,
            edge_executable.resolve(),
            width=1600,
            height=2140,
        )
    return outputs
