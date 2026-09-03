from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ygo_bench.visualization import load_ydk_sections, render_deck_board


class DeckBoardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.ydk = self.root / "pilot.ydk"
        self.ydk.write_text(
            "#created by test\n#main\n100\n100\n200\n#extra\n300\n!side\n200\n",
            encoding="utf-8",
        )
        self.cdb = self.root / "cards.cdb"
        connection = sqlite3.connect(self.cdb)
        connection.execute("CREATE TABLE texts (id INTEGER PRIMARY KEY, name TEXT)")
        connection.executemany(
            "INSERT INTO texts (id, name) VALUES (?, ?)",
            [(100, "Alpha"), (200, "Beta"), (300, "Gamma")],
        )
        connection.commit()
        connection.close()
        self.card_images = self.root / "images"
        self.card_images.mkdir()
        (self.card_images / "100.jpg").write_bytes(b"image")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_load_ydk_sections_preserves_order_and_copies(self) -> None:
        sections = load_ydk_sections(self.ydk)
        self.assertEqual(sections["main"], [100, 100, 200])
        self.assertEqual(sections["extra"], [300])
        self.assertEqual(sections["side"], [200])

    def test_render_writes_all_deck_sections_and_manifest(self) -> None:
        output = self.root / "deck.html"
        outputs = render_deck_board(
            self.ydk,
            self.cdb,
            self.card_images,
            output,
            title="Pilot Deck",
        )
        rendered_html = outputs["html"].read_text(encoding="utf-8")
        manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
        self.assertIn("Main Deck", rendered_html)
        self.assertIn("Extra Deck", rendered_html)
        self.assertIn("Side Deck", rendered_html)
        self.assertEqual(rendered_html.count('data-card-code="100"'), 2)
        self.assertNotIn("<figcaption>", rendered_html)
        self.assertNotIn("<svg", rendered_html)
        self.assertEqual(manifest["counts"], {"main": 3, "extra": 1, "side": 1})
        self.assertEqual(manifest["sections"]["main"][1]["copy_number"], 2)
        self.assertTrue(manifest["sections"]["main"][0]["image_available"])
        self.assertFalse(manifest["sections"]["extra"][0]["image_available"])

    def test_load_rejects_card_before_section(self) -> None:
        invalid = self.root / "invalid.ydk"
        invalid.write_text("100\n#main\n200\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "before a YDK section"):
            load_ydk_sections(invalid)


if __name__ == "__main__":
    unittest.main()
