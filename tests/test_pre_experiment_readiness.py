from __future__ import annotations

import unittest

from experiments.audit_pre_experiment_readiness import (
    DEFAULT_CONFIG,
    audit_data_result,
    audit_required_gate,
    build_report,
)


class PreExperimentReadinessTest(unittest.TestCase):
    def test_missing_data_result_is_explicitly_not_ready(self) -> None:
        result = audit_data_result(
            {"data_qualification_result": "tmp/missing-e0-result.json"}
        )
        self.assertEqual(result["status"], "pending")
        self.assertFalse(result["gate_passed"])
        self.assertEqual(result["input_validation_errors"], ["result_missing"])

    def test_reset_results_complete_runtime_foundation(self) -> None:
        report = build_report(DEFAULT_CONFIG)
        self.assertTrue(report["environment"]["ready"])
        self.assertEqual(report["environment"]["conda_env"], "ygo")
        self.assertTrue(report["contracts"]["status"] == "passed")
        self.assertTrue(report["implementation"]["ready"])
        self.assertTrue(report["runtime"]["foundation_ready"])
        self.assertEqual(
            report["runtime"]["gate_protocol"]["status"], "passed"
        )
        self.assertFalse(report["runtime"]["engine_ready"])
        foundation = {
            gate["gate_id"]: gate["status"]
            for gate in report["runtime"]["foundation_gates"]
        }
        self.assertEqual(foundation["init"], "passed")
        self.assertEqual(foundation["construct_tcg"], "passed")
        self.assertEqual(foundation["construct_ocg"], "passed")
        self.assertEqual(foundation["reset_tcg"], "passed")
        self.assertEqual(foundation["reset_ocg"], "passed")
        self.assertFalse(report["data_qualification"]["gate_passed"])
        self.assertFalse(report["tracks"]["static_model_experiment_ready"])
        self.assertFalse(report["tracks"]["strategy_model_experiment_ready"])
        self.assertIn("runtime_followup_gates_pending", report["blockers"])
        self.assertIn("e0_data_qualification_not_passed", report["blockers"])

    def test_missing_future_gate_is_pending(self) -> None:
        result = audit_required_gate(
            {
                "gate_id": "test",
                "path": "tmp/nonexistent-readiness-gate.json",
                "kind": "step",
                "profile": "tcg",
            },
            {},
        )
        self.assertEqual(result["status"], "pending")


if __name__ == "__main__":
    unittest.main()
