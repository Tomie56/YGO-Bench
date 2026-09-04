from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ygo_bench.visualization.review_app import (
    ReviewStore,
    build_interactive_card_images,
    _interactive_puzzle_state,
    _load_card_details,
)


class ReviewStoreTest(unittest.TestCase):
    def test_save_appends_review_and_latest_returns_last_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "reviews.jsonl"
            store = ReviewStore(path, {"item-1"})
            store.save({"item_id": "item-1", "decision": "revise", "note": "fix"})
            store.save({"item_id": "item-1", "decision": "pass", "note": "done"})

            latest = store.latest()
            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 2)
        self.assertEqual(latest["item-1"]["decision"], "pass")
        self.assertEqual(latest["item-1"]["note"], "done")
        self.assertIn("reviewed_at", json.loads(lines[0]))

    def test_save_rejects_unknown_item_and_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ReviewStore(Path(temporary_directory) / "reviews.jsonl", {"item-1"})
            with self.assertRaisesRegex(ValueError, "Unknown review item"):
                store.save({"item_id": "missing", "decision": "pass"})
            with self.assertRaisesRegex(ValueError, "Unknown review decision"):
                store.save({"item_id": "item-1", "decision": "maybe"})

    def test_interactive_state_masks_private_opponent_cards(self) -> None:
        state = {
            "objective": "Win this turn.",
            "ai_name": "Opponent",
            "player_lp": 4000,
            "opponent_lp": 2500,
            "overlay_call_count": 2,
            "cards": [
                {"card_id": 100, "owner": 0, "controller": 0, "location": "LOCATION_SZONE", "sequence": 0, "position": "POS_FACEDOWN"},
                {"card_id": 101, "owner": 1, "controller": 1, "location": "LOCATION_SZONE", "sequence": 1, "position": "POS_FACEDOWN"},
                {"card_id": 102, "owner": 1, "controller": 1, "location": "LOCATION_GRAVE", "sequence": 0, "position": "POS_FACEUP"},
                {"card_id": 103, "owner": 0, "controller": 0, "location": "LOCATION_DECK", "sequence": 0, "position": "POS_FACEDOWN"},
                {"card_id": 104, "owner": 1, "controller": 1, "location": "LOCATION_MZONE", "sequence": 2, "position": "POS_FACEUP_DEFENSE"},
            ],
        }

        result = _interactive_puzzle_state(state)
        cards = result["cards"]

        self.assertEqual(cards[0]["card_id"], 100)
        self.assertIsNone(cards[1]["card_id"])
        self.assertEqual(cards[2]["card_id"], 102)
        self.assertIsNone(cards[3]["card_id"])
        self.assertTrue(cards[4]["defense"])
        self.assertEqual(cards[4]["position"], "表侧守备")
        self.assertEqual(result["overlay"]["unresolved_calls"], 2)

    def test_load_card_details_reads_machine_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "cards.cdb"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "CREATE TABLE datas (id INTEGER PRIMARY KEY, type INTEGER, atk INTEGER, def INTEGER, level INTEGER, race INTEGER, attribute INTEGER)"
                )
                connection.execute(
                    "CREATE TABLE texts (id INTEGER PRIMARY KEY, name TEXT, desc TEXT)"
                )
                connection.execute(
                    "INSERT INTO datas VALUES (100, 33, 1500, 1200, 4, 1, 16)"
                )
                connection.execute(
                    "INSERT INTO texts VALUES (100, 'Test Card', 'Test effect.')"
                )

            details = _load_card_details([path], {100})

        self.assertEqual(details["100"]["name"], "Test Card")
        self.assertEqual(details["100"]["attack"], 1500)
        self.assertEqual(details["100"]["attribute"], 16)

    def test_build_interactive_card_images_exports_only_catalog_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            Image.new("RGB", (421, 614), "red").save(source / "100.jpg")
            Image.new("RGB", (421, 614), "blue").save(source / "999.jpg")
            summary = build_interactive_card_images(
                {"card_catalog": {"100": {}, "101": {}}}, source, output
            )

            with Image.open(output / "card-images/100.jpg") as exported:
                exported_width = exported.width

        self.assertEqual(summary, {"written": 1, "missing": 1})
        self.assertLessEqual(exported_width, 180)
        self.assertFalse((output / "card-images/999.jpg").exists())


if __name__ == "__main__":
    unittest.main()
