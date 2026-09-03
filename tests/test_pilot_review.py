from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ygo_bench.visualization import parse_puzzle
from ygo_bench.visualization.pilot_review import PuzzleCard, PuzzleState, _puzzle_page


class PilotReviewTest(unittest.TestCase):
    def test_parse_puzzle_reads_literal_initial_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "Example_Puzzle.lua"
            path.write_text(
                """--[[message
Objective: Win this turn.
]]
Debug.SetAIName("Test AI")
Debug.SetPlayerInfo(0,1200,0,0)
Debug.SetPlayerInfo(1,3400,0,0)
Debug.AddCard(14558127,0,0,LOCATION_HAND,0,POS_FACEDOWN)
Debug.AddCard(10045474,1,1,LOCATION_SZONE,2,POS_FACEDOWN)
aux.BeginPuzzle()
""",
                encoding="utf-8",
            )

            state = parse_puzzle(path, root)

        self.assertEqual(state.title, "Example Puzzle")
        self.assertEqual(state.objective, "Win this turn.")
        self.assertEqual(state.ai_name, "Test AI")
        self.assertEqual((state.player_lp, state.opponent_lp), (1200, 3400))
        self.assertEqual(len(state.cards), 2)
        self.assertEqual(state.cards[0].card_id, 14558127)
        self.assertEqual(state.cards[1].location, "LOCATION_SZONE")
        self.assertEqual(state.overlay_call_count, 0)
        self.assertEqual(state.unparsed_add_card_calls, 0)

    def test_parse_puzzle_reports_dynamic_add_card_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "Dynamic.lua"
            path.write_text(
                "Debug.AddCard(code,0,0,LOCATION_DECK,0,POS_FACEDOWN)\n"
                "Duel.Overlay(host,material)\n",
                encoding="utf-8",
            )
            state = parse_puzzle(path, root)

        self.assertEqual(state.cards, ())
        self.assertEqual(state.overlay_call_count, 1)
        self.assertEqual(state.unparsed_add_card_calls, 1)

    def test_puzzle_board_orders_zones_aligns_emz_and_renders_defense(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            card_image_dir = Path(temporary_directory)
            state = PuzzleState(
                relative_path="test/positions.lua",
                title="Position Test",
                objective="Inspect the board.",
                ai_name="Opponent",
                player_lp=8000,
                opponent_lp=8000,
                cards=(
                    PuzzleCard(100, 1, 1, "LOCATION_SZONE", 0, "POS_FACEDOWN"),
                    PuzzleCard(101, 1, 1, "LOCATION_MZONE", 1, "POS_FACEUP_DEFENSE"),
                    PuzzleCard(102, 0, 0, "LOCATION_MZONE", 3, "8"),
                    PuzzleCard(103, 0, 0, "LOCATION_MZONE", 5, "POS_FACEUP_ATTACK"),
                ),
                has_custom_effect=False,
                has_pre_equip=False,
                has_pre_summon=False,
                overlay_call_count=1,
                unparsed_add_card_calls=0,
            )
            markup = _puzzle_page(
                state,
                1,
                1,
                {100: "Set Card", 101: "Defender", 102: "Set Defender", 103: "EMZ Card"},
                card_image_dir,
            )

        opponent_start = markup.index('class="field-half field-half--opponent"')
        opponent_end = markup.index('class="emz"', opponent_start)
        opponent_markup = markup[opponent_start:opponent_end]
        self.assertLess(opponent_markup.index('class="zone-grid spells"'), opponent_markup.index('class="zone-grid monsters"'))
        self.assertIn('.emz-slot--left { grid-column: 2; }', markup)
        self.assertIn('.emz-slot--right { grid-column: 4; }', markup)
        self.assertEqual(markup.count("card-face--defense"), 3)
        self.assertIn("card-face--defense card-back", markup)
        self.assertIn("素材关系未静态解析", markup)


if __name__ == "__main__":
    unittest.main()
