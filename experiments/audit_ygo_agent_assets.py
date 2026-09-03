from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
YGO_AGENT = ROOT / "references" / "ygo-agent"
DECK_DIR = YGO_AGENT / "assets" / "deck"
DB_PATH = YGO_AGENT / "assets" / "locale" / "en" / "cards.cdb"
CODE_LIST_PATH = YGO_AGENT / "scripts" / "code_list.txt"
SCRIPT_DIR = ROOT / "references" / "ygopro-scripts"
RESULT_DIR = ROOT / "results" / "cpu_pilot"


def load_deck(path: Path) -> list[int]:
    return [
        int(line.strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().isdigit()
    ]


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        db_ids = {row[0] for row in connection.execute("SELECT id FROM datas")}

    code_list: dict[int, int] = {}
    for line in CODE_LIST_PATH.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) >= 2:
            code_list[int(fields[0])] = int(fields[1])

    rows: list[dict[str, object]] = []
    for deck_path in sorted(DECK_DIR.glob("*.ydk")):
        cards = load_deck(deck_path)
        unique_cards = sorted(set(cards))
        missing_db = [card for card in unique_cards if card not in db_ids]
        missing_code_list = [card for card in unique_cards if card not in code_list]
        missing_scripts = [
            card
            for card in unique_cards
            if code_list.get(card) == 1 and not (SCRIPT_DIR / f"c{card}.lua").exists()
        ]
        rows.append(
            {
                "deck": deck_path.name,
                "cards": len(cards),
                "unique_cards": len(unique_cards),
                "missing_db_count": len(missing_db),
                "missing_code_list_count": len(missing_code_list),
                "missing_script_count": len(missing_scripts),
                "missing_db": missing_db,
                "missing_code_list": missing_code_list,
                "missing_scripts": missing_scripts,
                "static_compatible": not (
                    missing_db or missing_code_list or missing_scripts
                ),
            }
        )

    json_path = RESULT_DIR / "ygo_agent_asset_compatibility.json"
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    csv_path = RESULT_DIR / "ygo_agent_asset_compatibility.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "deck",
                "cards",
                "unique_cards",
                "missing_db_count",
                "missing_code_list_count",
                "missing_script_count",
                "static_compatible",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in writer.fieldnames})

    compatible = [row["deck"] for row in rows if row["static_compatible"]]
    print(json.dumps({"decks": len(rows), "compatible": compatible}, indent=2))


if __name__ == "__main__":
    main()
