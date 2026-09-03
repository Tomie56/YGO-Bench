from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class PublicBenchmarkDataTest(unittest.TestCase):
    def test_understanding_pilot_distribution(self) -> None:
        records = _read_jsonl(
            ROOT / "data/benchmark/understanding/pilot-candidates-v0.1.jsonl"
        )

        self.assertEqual(len(records), 30)
        self.assertEqual(
            Counter(record["candidate_kind"] for record in records),
            {"card_semantics": 12, "rule_and_timing": 10, "counterfactual": 8},
        )
        self.assertEqual(
            Counter(record["snapshot_id"] for record in records),
            {"tcg-kde-e-2026-05-18": 15, "ocg-jp-2026-07-01": 15},
        )

    def test_construction_pilot_distribution(self) -> None:
        records = _read_jsonl(
            ROOT / "data/benchmark/deck/pilot-candidates-v0.1.jsonl"
        )

        self.assertEqual(len(records), 60)
        self.assertEqual(
            Counter(record["task_type"] for record in records),
            {
                "source_legality_audit": 20,
                "controlled_corruption_audit": 20,
                "controlled_corruption_minimal_repair": 20,
            },
        )
        self.assertEqual(
            Counter(record["snapshot_id"] for record in records),
            {"tcg-kde-e-2026-05-18": 30, "ocg-jp-2026-07-01": 30},
        )


if __name__ == "__main__":
    unittest.main()
