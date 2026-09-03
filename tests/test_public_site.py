from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ygo_bench.visualization.public_site import make_static_catalog, validate_public_site


class PublicSiteTest(unittest.TestCase):
    def test_static_catalog_removes_local_output_and_uses_relative_assets(self) -> None:
        source = {
            "dataset_version": "pilot-v1",
            "output_dir": "/private/output",
            "items": [
                {
                    "id": "item-1",
                    "image_url": "/understanding/one.png",
                    "thumbnail_url": "/thumbnails/understanding/one.jpg",
                }
            ],
        }

        result = make_static_catalog(source)

        self.assertNotIn("output_dir", result)
        self.assertEqual(result["reviews"], {})
        self.assertEqual(result["items"][0]["image_url"], "understanding/one.png")
        self.assertEqual(
            result["items"][0]["thumbnail_url"],
            "thumbnails/understanding/one.jpg",
        )
        self.assertEqual(source["items"][0]["image_url"], "/understanding/one.png")

    def test_validation_rejects_absolute_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            site = Path(temporary_directory)
            (site / "index.html").write_text(
                '<a href="D:/' + 'Tomie/private">private</a>', encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "absolute local path"):
                validate_public_site(site)

    def test_validation_accepts_minimal_static_site(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            site = Path(temporary_directory)
            (site / "index.html").write_text("<h1>YGO-Bench</h1>", encoding="utf-8")
            summary = validate_public_site(site)

        self.assertEqual(summary["file_count"], 1)
        self.assertGreater(summary["total_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
