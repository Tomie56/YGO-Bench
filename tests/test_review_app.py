from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ygo_bench.visualization.review_app import ReviewStore


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


if __name__ == "__main__":
    unittest.main()
