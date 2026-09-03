from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np

from ygo_bench.visualization import render_audit_board
from ygo_bench.visualization.audit_board import CARD_HEIGHT, CARD_WIDTH


class AuditBoardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.code_list = self.root / "code_list.txt"
        self.code_list.write_text("100\n200\n", encoding="ascii")
        self.cdb = self.root / "cards.cdb"
        connection = sqlite3.connect(self.cdb)
        connection.execute("CREATE TABLE texts (id INTEGER PRIMARY KEY, name TEXT)")
        connection.executemany(
            "INSERT INTO texts (id, name) VALUES (?, ?)",
            [(100, "Alpha Card"), (200, "Beta Card")],
        )
        connection.commit()
        connection.close()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _state(self) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
        cards = np.zeros((1, 10, 40), dtype=np.uint8)
        visibility = np.zeros((1, 10), dtype=np.uint8)
        cards[0, 0, :4] = (0, 1, 2, 0)
        visibility[0, 0] = 2
        cards[0, 1, :4] = (0, 2, 3, 1)
        visibility[0, 1] = 3
        cards[0, 5, 2] = 1
        cards[0, 5, 4] = 1
        visibility[0, 5] = 1
        cards[0, 6, :6] = (0, 0, 4, 1, 1, 2)
        visibility[0, 6] = 6
        global_features = np.zeros((1, 9), dtype=np.uint8)
        global_features[0, :6] = (31, 64, 31, 64, 1, 3)
        actions = np.zeros((1, 2, 30), dtype=np.uint8)
        actions[0, 0, 1] = 1
        actions[0, 0, 20] = 1
        observation = {
            "cards_": cards,
            "global_": global_features,
            "actions_": actions,
        }
        infos = {
            "card_visibility_": visibility,
            "num_options": np.array([1], dtype=np.int32),
            "to_play": np.array([0], dtype=np.int32),
        }
        return observation, infos

    def test_render_writes_auditable_html_without_hidden_identity(self) -> None:
        observation, infos = self._state()
        output = self.root / "audit.html"
        outputs = render_audit_board(observation, infos, self.code_list, self.cdb, output)
        rendered_html = outputs["html"].read_text(encoding="utf-8")
        manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
        self.assertIn("Alpha Card", rendered_html)
        self.assertIn('aria-label="Hidden card"', rendered_html)
        self.assertIn("Shared Extra Monster Zones", rendered_html)
        self.assertIn("Graveyard", rendered_html)
        self.assertIn("Banished", rendered_html)
        self.assertIn("aspect-ratio: 59 / 86", rendered_html)
        self.assertNotIn("<svg", rendered_html)
        self.assertAlmostEqual(CARD_WIDTH / CARD_HEIGHT, 59 / 86)
        self.assertEqual(manifest["life_points"]["current_player"], 8000)
        self.assertEqual(manifest["phase"], "Main 1")
        hidden_cards = [card for card in manifest["cards"] if card["hidden"]]
        self.assertEqual(len(hidden_cards), 2)
        self.assertTrue(all(card["name"] is None for card in hidden_cards))

    def test_render_rejects_hidden_identity_leak(self) -> None:
        observation, infos = self._state()
        observation["cards_"][0, 5, :3] = (0, 2, 1)
        with self.assertRaisesRegex(ValueError, "Hidden card rows"):
            render_audit_board(
                observation,
                infos,
                self.code_list,
                self.cdb,
                self.root / "audit.html",
            )

    def test_render_uses_two_fixed_size_rows_for_twenty_hand_cards(self) -> None:
        observation, infos = self._state()
        cards = np.zeros((1, 40, 40), dtype=np.uint8)
        visibility = np.zeros((1, 40), dtype=np.uint8)
        for index in range(20):
            cards[0, index, :4] = (0, 1, 2, index)
            visibility[0, index] = 2
        observation["cards_"] = cards
        infos["card_visibility_"] = visibility
        output = self.root / "twenty-hand.html"
        render_audit_board(observation, infos, self.code_list, self.cdb, output)
        rendered_html = output.read_text(encoding="utf-8")
        self.assertIn("Hand <span>20</span>", rendered_html)
        self.assertEqual(rendered_html.count('class="card card--unavailable"'), 20)
        self.assertNotIn("+15", rendered_html)

    def test_render_rejects_missing_required_info(self) -> None:
        observation, infos = self._state()
        del infos["to_play"]
        with self.assertRaisesRegex(ValueError, "missing info fields"):
            render_audit_board(
                observation,
                infos,
                self.code_list,
                self.cdb,
                self.root / "audit.html",
            )

    def test_render_decodes_place_actions_and_numbers_them_once(self) -> None:
        observation, infos = self._state()
        actions = np.zeros((1, 5, 30), dtype=np.uint8)
        actions[0, :, 20] = 11
        actions[0, :, 28] = np.arange(8, 13)
        observation["actions_"] = actions
        infos["num_options"] = np.array([5], dtype=np.int32)
        output = self.root / "place-actions.html"
        outputs = render_audit_board(
            observation,
            infos,
            self.code_list,
            self.cdb,
            output,
        )
        rendered_html = output.read_text(encoding="utf-8")
        manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
        self.assertIn('<ol start="0">', rendered_html)
        self.assertNotIn("0: Select place", rendered_html)
        self.assertEqual(
            manifest["legal_actions"],
            [
                f"Place card in your Spell & Trap Zone {index} [s{index}]"
                for index in range(1, 6)
            ],
        )

    def test_render_rejects_non_html_output(self) -> None:
        observation, infos = self._state()
        with self.assertRaisesRegex(ValueError, "must end in .html"):
            render_audit_board(
                observation,
                infos,
                self.code_list,
                self.cdb,
                self.root / "audit.svg",
            )

    def test_render_places_opponent_hand_above_field_and_aligns_emz(self) -> None:
        observation, infos = self._state()
        output = self.root / "layout.html"
        render_audit_board(observation, infos, self.code_list, self.cdb, output)
        rendered_html = output.read_text(encoding="utf-8")
        opponent_start = rendered_html.index(
            '<section class="player-half player-half--opponent">'
        )
        opponent_end = rendered_html.index('<section class="emz">', opponent_start)
        opponent_markup = rendered_html[opponent_start:opponent_end]
        self.assertLess(opponent_markup.index('class="hand"'), opponent_markup.index('class="player-layout"'))
        self.assertLess(
            opponent_markup.index("Spell &amp; Trap Zone"),
            opponent_markup.index("Main Monster Zone"),
        )
        current_start = rendered_html.index(
            '<section class="player-half player-half--current_player">'
        )
        current_markup = rendered_html[current_start:]
        self.assertLess(
            current_markup.index("Main Monster Zone"),
            current_markup.index("Spell &amp; Trap Zone"),
        )
        self.assertIn('.emz-slot--left { grid-column: 2; }', rendered_html)
        self.assertIn('.emz-slot--right { grid-column: 4; }', rendered_html)
        self.assertIn('card--monster-opponent', rendered_html)
        self.assertIn('card--monster-current', rendered_html)

    def test_render_decodes_defense_positions_and_xyz_materials(self) -> None:
        observation, infos = self._state()
        observation["cards_"][0, 1, 5] = 4
        observation["cards_"][0, 2, :7] = (0, 1, 3, 1, 0, 5, 1)
        infos["card_visibility_"][0, 2] = 3
        observation["cards_"][0, 7, :7] = (0, 0, 3, 4, 1, 6, 0)
        infos["card_visibility_"][0, 7] = 6
        output = self.root / "positions-and-materials.html"

        outputs = render_audit_board(
            observation,
            infos,
            self.code_list,
            self.cdb,
            output,
        )

        rendered_html = output.read_text(encoding="utf-8")
        manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
        host = next(card for card in manifest["cards"] if card["row_index"] == 1)
        material = next(card for card in manifest["cards"] if card["row_index"] == 2)
        self.assertEqual((host["observation_sequence"], host["sequence"]), (1, 0))
        self.assertEqual(host["position"], "face-up defense")
        self.assertEqual(len(host["overlay_materials"]), 1)
        self.assertTrue(material["is_overlay"])
        self.assertEqual(manifest["zone_counts"]["current_player"]["Monster Zone"], 1)
        self.assertIn("card--defense", rendered_html)
        self.assertIn("card--with-materials", rendered_html)
        self.assertIn("1 MAT", rendered_html)

    def test_render_history_limits_entries_and_rejects_hidden_identity(self) -> None:
        observation, infos = self._state()
        events = [
            {"text": f"Event {index}", "card_code": 100, "hidden": False}
            for index in range(15)
        ]
        output = self.root / "history.html"
        outputs = render_audit_board(
            observation,
            infos,
            self.code_list,
            self.cdb,
            output,
            history_events=events,
        )
        rendered_html = output.read_text(encoding="utf-8")
        manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
        self.assertEqual(rendered_html.count('class="history-entry"'), 12)
        self.assertIn("3 older events omitted", rendered_html)
        self.assertEqual(len(manifest["history_events"]), 15)
        with self.assertRaisesRegex(ValueError, "cannot expose card_code"):
            render_audit_board(
                observation,
                infos,
                self.code_list,
                self.cdb,
                self.root / "invalid-history.html",
                history_events=[
                    {"text": "Facedown card set", "card_code": 100, "hidden": True}
                ],
            )


if __name__ == "__main__":
    unittest.main()
