from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from ygo_bench.contracts import validate_path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "source_samples" / "official_rules" / "manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SnapshotAuthorityTest(unittest.TestCase):
    def assert_card_catalog_artifacts(self, snapshot: dict) -> None:
        artifacts = snapshot["artifacts"]
        card_artifacts = [
            artifacts["cards_cdb"],
            *artifacts.get("cards_cdb_layers", []),
            *artifacts.get("card_catalog_supplements", []),
        ]
        for artifact in card_artifacts:
            path = ROOT / artifact["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(sha256_file(path), artifact["sha256"].lower())

    def test_official_rule_artifacts_match_manifest(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["artifacts"]), 5)
        for artifact in manifest["artifacts"]:
            path = ROOT / artifact["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(sha256_file(path), artifact["sha256"])

    def test_tcg_ruleset_is_frozen(self) -> None:
        path = ROOT / "snapshots" / "tcg-kde-e-2026-05-18.json"
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        validate_path("environment-snapshot", path)
        self.assertEqual(snapshot["open_fields"], [])
        self.assertEqual(snapshot["authority"]["tournament_policy_version"], "2.5")
        self.assertIn("v9.01", snapshot["master_rule"])
        self.assert_card_catalog_artifacts(snapshot)

    def test_ocg_static_authority_and_cutoff_are_frozen(self) -> None:
        path = ROOT / "snapshots" / "ocg-jp-2026-07-01.json"
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        validate_path("environment-snapshot", path)
        self.assertEqual(snapshot["open_fields"], [])
        self.assertEqual(snapshot["card_pool_cutoff"], "2026-07-17")
        self.assertIn("list=202607", snapshot["authority"]["banlist_url"])
        self.assert_card_catalog_artifacts(snapshot)


if __name__ == "__main__":
    unittest.main()
