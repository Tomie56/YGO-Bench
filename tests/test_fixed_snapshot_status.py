from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXED_SNAPSHOTS = ROOT / "data" / "fixed_snapshots"
RUNTIME_SNAPSHOT = (
    ROOT / "snapshots" / "runtime-modern-v1-2026-07-20.json"
)


class FixedSnapshotStatusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = json.loads(RUNTIME_SNAPSHOT.read_text(encoding="utf-8"))
        cls.manifest = json.loads(
            (FIXED_SNAPSHOTS / "manifest.json").read_text(encoding="utf-8")
        )

    def test_reset_is_verified_but_followup_gates_remain(self) -> None:
        self.assertEqual(
            self.runtime["status"],
            "adapter_initialized_smoke_pending",
        )
        self.assertEqual(len(self.manifest), 20)
        self.assertEqual(
            Counter(item["snapshot_id"] for item in self.manifest),
            {"tcg-kde-e-2026-05-18": 10, "ocg-jp-2026-07-01": 10},
        )
        self.assertEqual(sum(item["runtime_primary"] for item in self.manifest), 2)
        self.assertEqual(
            Counter(
                item["snapshot_id"]
                for item in self.manifest
                if item["modern_assets_ready"]
            ),
            {"tcg-kde-e-2026-05-18": 8, "ocg-jp-2026-07-01": 10},
        )
        for item in self.manifest:
            self.assertTrue(item["static_benchmark_ready"])
            self.assertEqual(
                item["runtime_status"],
                "reset_smoke_verified_followup_gates_pending",
            )
            self.assertFalse(item["engine_ready"])
            if item["runtime_primary"]:
                self.assertTrue(item["modern_assets_ready"])
                self.assertTrue(item["runtime_adapter_ready"])
                self.assertIsNotNone(item["scenario"])
            else:
                self.assertFalse(item["runtime_adapter_ready"])
                self.assertIsNone(item["scenario"])

    def test_deck_provenance_is_complete(self) -> None:
        for item in self.manifest:
            if not item["runtime_primary"]:
                continue
            deck_path = ROOT / item["deck"]
            deck = json.loads(deck_path.read_text(encoding="utf-8"))
            source = deck["source"]
            self.assertTrue(source["retrieved_at"])
            self.assertEqual(
                source["evidence_level"],
                "curated_deck_with_official_event_crosscheck",
            )

    def test_scenarios_keep_followup_gates_explicit(self) -> None:
        expected = {
            "legal_action_execution",
            "hidden_information_and_identity",
            "trace_replay_state_hash",
            "environment_lifecycle_100",
            "throughput_1000_steps_per_second",
            "random_eval_32",
        }
        for item in self.manifest:
            if not item["runtime_primary"]:
                continue
            scenario_path = ROOT / item["scenario"]
            payload = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario = payload["scenarios"][0]
            self.assertTrue(scenario["runtime_adapter_ready"])
            self.assertFalse(scenario["engine_ready"])
            self.assertIsNone(scenario["blockers"]["runtime_adapter"])
            self.assertEqual(
                set(scenario["blockers"]["pending_runtime_gates"]), expected
            )


if __name__ == "__main__":
    unittest.main()
