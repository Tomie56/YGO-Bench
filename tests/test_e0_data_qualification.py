from __future__ import annotations

import unittest
from collections import Counter

from experiments.freeze_tcg_ocg_snapshots import load_corpus
from experiments.run_e0_data_qualification import (
    audit_decks,
    audit_understanding,
    input_artifacts,
    semantic_agreement_value,
    validate_semantic_value,
)


class E0DataQualificationTest(unittest.TestCase):
    def test_current_decks_are_parseable_and_provenance_complete(self) -> None:
        audit = audit_decks()
        self.assertTrue(audit["gate_passed"])
        self.assertEqual(len(audit["by_snapshot"]), 2)
        for snapshot in audit["by_snapshot"]:
            self.assertEqual(snapshot["records"], 10)
            self.assertTrue(snapshot["parse_gate_passed"])
            self.assertTrue(snapshot["provenance_gate_passed"])
            self.assertTrue(snapshot["count_gate_passed"])

    def test_tournament_corpus_is_balanced_and_has_one_runtime_primary(self) -> None:
        corpus_id, specs = load_corpus()
        self.assertEqual(corpus_id, "ygoprodeck-tournament-corpus-v0.1")
        self.assertEqual(Counter(spec.snapshot_id for spec in specs), {
            "tcg-kde-e-2026-05-18": 10,
            "ocg-jp-2026-07-01": 10,
        })
        self.assertEqual(
            Counter(spec.snapshot_id for spec in specs if spec.runtime_primary),
            {
                "tcg-kde-e-2026-05-18": 1,
                "ocg-jp-2026-07-01": 1,
            },
        )

    def test_understanding_gate_remains_unmet(self) -> None:
        audit = audit_understanding()
        self.assertEqual(audit["records"], 0)
        self.assertEqual(audit["total_records"], 0)
        self.assertFalse(audit["gate_passed"])

    def test_agreement_ignores_source_spans(self) -> None:
        first = {
            "cost": {
                "status": "present",
                "labels": ["discard", "lp_payment"],
                "source_spans": ["Discard 1 card"],
            }
        }
        second = {
            "cost": {
                "status": "present",
                "labels": ["lp_payment", "discard"],
                "source_spans": ["pay 1000 LP"],
            }
        }
        self.assertEqual(
            semantic_agreement_value(first, "cost"),
            semantic_agreement_value(second, "cost"),
        )

    def test_present_semantic_field_requires_a_label(self) -> None:
        empty = {"status": "absent", "labels": [], "source_spans": []}
        value = {
            "activation_condition": dict(empty),
            "cost": {"status": "present", "labels": [], "source_spans": []},
            "target": dict(empty),
            "once_per_turn_scope": {
                "status": "absent",
                "scope": "none",
                "labels": [],
                "source_spans": [],
            },
            "resolution_operation": dict(empty),
            "restriction": dict(empty),
        }
        with self.assertRaisesRegex(ValueError, "cost"):
            validate_semantic_value(value, "test-record")

    def test_input_manifest_includes_raw_deck_sources(self) -> None:
        paths = {item["path"] for item in input_artifacts()}
        self.assertIn(
            "data/source_samples/ygoprodeck_tournament/deck_721844.html",
            paths,
        )
        self.assertIn(
            "data/source_samples/ygoprodeck_tournament/deck_722486.html",
            paths,
        )
        self.assertIn(
            "data/source_samples/ygoprodeck_tournament/corpus-v0.1.json",
            paths,
        )
        self.assertIn(
            "data/source_samples/ygoprodeck_tournament/tournament_4747.html",
            paths,
        )
        self.assertIn(
            "data/source_samples/ygoprodeck_tournament/tournament_4756.html",
            paths,
        )


if __name__ == "__main__":
    unittest.main()
