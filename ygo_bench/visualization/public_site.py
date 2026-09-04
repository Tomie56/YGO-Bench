from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

SITE_ASSET_DIR = Path(__file__).with_name("public_site_assets")
REVIEWER_ASSET_DIR = Path(__file__).with_name("reviewer_assets")
TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".txt"}
FORBIDDEN_TEXT = (
    "/mnt/d/" + "Tomie/",
    "D:\\" + "Tomie\\",
    "D:/" + "Tomie/",
)
FORBIDDEN_NAMES = {
    "understanding-candidates.jsonl.gz",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_static_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(catalog)
    result.pop("output_dir", None)
    result.pop("card_image_source_dir", None)
    result["reviews"] = {}
    for item in result["items"]:
        item["image_url"] = item["image_url"].lstrip("/")
        item["thumbnail_url"] = item["thumbnail_url"].lstrip("/")
    return result


def _copy_review_assets(
    catalog: dict[str, Any],
    manifest_dir: Path,
    review_dir: Path,
) -> None:
    asset_output = review_dir / "assets"
    asset_output.mkdir(parents=True)
    for name in ("reviewer.css", "reviewer.js"):
        shutil.copy2(REVIEWER_ASSET_DIR / name, asset_output / name)
    shutil.copy2(REVIEWER_ASSET_DIR / "reviewer.html", review_dir / "index.html")

    copied: set[str] = set()
    for item in catalog["items"]:
        for field in ("image_url", "thumbnail_url"):
            relative = str(item[field]).lstrip("/")
            if relative in copied:
                continue
            source = manifest_dir / relative
            if not source.is_file():
                raise FileNotFoundError(f"Review asset not found: {source}")
            target = review_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.add(relative)


def build_public_site(manifest_path: Path, output_dir: Path) -> Path:
    from .review_app import (
        build_interactive_card_images,
        build_review_catalog,
        build_thumbnails,
    )

    manifest_path = manifest_path.resolve()
    output_dir = output_dir.resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Review manifest not found: {manifest_path}")
    if output_dir.exists():
        raise FileExistsError(f"Public site output already exists: {output_dir}")

    catalog = build_review_catalog(manifest_path)
    build_thumbnails(catalog, manifest_path.parent)
    card_image_source_dir = Path(catalog["card_image_source_dir"])
    static_catalog = make_static_catalog(catalog)

    output_dir.mkdir(parents=True)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir()
    shutil.copy2(SITE_ASSET_DIR / "index.html", output_dir / "index.html")
    shutil.copy2(SITE_ASSET_DIR / "site.css", assets_dir / "site.css")
    (output_dir / ".nojekyll").write_text("", encoding="ascii")

    review_dir = output_dir / "review"
    review_dir.mkdir()
    _copy_review_assets(static_catalog, manifest_path.parent, review_dir)
    build_interactive_card_images(
        static_catalog, card_image_source_dir, review_dir
    )
    (review_dir / "config.json").write_text(
        json.dumps(
            {
                "storage_mode": "local",
                "catalog_url": "catalog.json",
                "dataset_version": static_catalog["dataset_version"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (review_dir / "catalog.json").write_text(
        json.dumps(static_catalog, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    preview = next(
        (item for item in static_catalog["items"] if item["category"] == "puzzles"),
        static_catalog["items"][0],
    )
    shutil.copy2(review_dir / preview["image_url"], assets_dir / "benchmark-preview.png")

    files = sorted(path for path in output_dir.rglob("*") if path.is_file())
    build_manifest = {
        "dataset_version": static_catalog["dataset_version"],
        "review_item_count": len(static_catalog["items"]),
        "source_manifest_sha256": _sha256(manifest_path),
        "files": [
            {
                "path": path.relative_to(output_dir).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in files
        ],
    }
    manifest_output = output_dir / "build-manifest.json"
    manifest_output.write_text(
        json.dumps(build_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_output


def validate_public_site(site_dir: Path) -> dict[str, int]:
    site_dir = site_dir.resolve()
    if not (site_dir / "index.html").is_file():
        raise FileNotFoundError(f"Public site entry point not found: {site_dir / 'index.html'}")
    files = [path for path in site_dir.rglob("*") if path.is_file()]
    violations: list[str] = []
    for path in files:
        relative = path.relative_to(site_dir).as_posix()
        if path.name in FORBIDDEN_NAMES:
            violations.append(f"forbidden file: {relative}")
        if path.stat().st_size > 50 * 1024 * 1024:
            violations.append(f"file exceeds 50 MiB: {relative}")
        if path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            for marker in FORBIDDEN_TEXT:
                if marker in text:
                    violations.append(f"absolute local path in {relative}: {marker}")
    if violations:
        raise ValueError("Public site validation failed:\n" + "\n".join(violations))
    return {
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
    }
