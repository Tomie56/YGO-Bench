from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ygo_bench.visualization import parse_puzzle


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
        self.assertEqual(state.unparsed_add_card_calls, 0)

    def test_parse_puzzle_reports_dynamic_add_card_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "Dynamic.lua"
            path.write_text(
                "Debug.AddCard(code,0,0,LOCATION_DECK,0,POS_FACEDOWN)\n",
                encoding="utf-8",
            )
            state = parse_puzzle(path, root)

        self.assertEqual(state.cards, ())
        self.assertEqual(state.unparsed_add_card_calls, 1)


if __name__ == "__main__":
    unittest.main()
