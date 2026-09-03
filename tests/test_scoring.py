from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from ygo_bench.scoring import (
    score_record,
    score_semantic_fields,
    set_metrics,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "schemas" / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class ScoringTest(unittest.TestCase):
    def test_set_metrics(self) -> None:
        metrics = set_metrics([1, 2], [2, 3])
        self.assertEqual(metrics["set_precision"], 0.5)
        self.assertEqual(metrics["set_recall"], 0.5)
        self.assertEqual(metrics["set_f1"], 0.5)
        self.assertEqual(metrics["exact_set"], 0.0)

    def test_semantic_field_macro_f1(self) -> None:
        target = {
            "activation_condition": "open",
            "cost": ["discard"],
            "target": ["monster"],
            "once_per_turn_scope": "hard",
            "resolution_operation": ["destroy"],
            "restriction": None,
        }
        answer = copy.deepcopy(target)
        answer["target"] = ["spell"]
        metrics = score_semantic_fields(target, answer)
        self.assertAlmostEqual(metrics["field_macro_f1"], 5 / 6)

    def test_exact_record_builds_valid_evaluation_result(self) -> None:
        record = load_example("benchmark-record.json")
        output = load_example("model-output.json")
        output["answer"] = copy.deepcopy(record["target"])
        result = score_record(record, output, scorer_name="exact")
        self.assertEqual(result["status"], "scored")
        self.assertEqual(result["primary"]["value"], 1.0)

    def test_provider_failure_is_unscorable(self) -> None:
        record = load_example("benchmark-record.json")
        output = load_example("model-output.json")
        output["status"] = "timeout"
        output.pop("answer")
        output["error"] = "deadline exceeded"
        result = score_record(record, output)
        self.assertEqual(result["status"], "unscorable")
        self.assertEqual(result["errors"], ["timeout"])

    def test_unsupported_task_fails_explicitly(self) -> None:
        record = load_example("benchmark-record.json")
        record["layer"] = "deck"
        record["task"] = "MinimalRepair"
        output = load_example("model-output.json")
        with self.assertRaisesRegex(ValueError, "No deterministic scorer"):
            score_record(record, output)


if __name__ == "__main__":
    unittest.main()
