from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
FORBIDDEN_PREFIXES = (
    "docs/internal/",
    "data/card_images/",
    "data/question_sources/raw/",
    "data/source_samples/",
    "data/benchmark/source-candidates-v0.2/",
    "references/babelcdb/",
    "references/cardscripts/",
    "references/ygo-agent/",
    "references/ygopro-core/",
    "tmp/",
)
LOCAL_PATH_MARKERS = (
    "/mnt/d/" + "Tomie/",
    "D:\\" + "Tomie\\",
    "D:/" + "Tomie/",
)
TEXT_SUFFIXES = {
    "",
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def _is_ignored(path: Path) -> bool:
    return bool(IGNORED_PARTS.intersection(path.parts)) or path.suffix in IGNORED_SUFFIXES


def _copy_file(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Public release input not found: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def export_public_release(config_path: Path, output_dir: Path) -> dict[str, int | str]:
    config_path = config_path.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"Public release output already exists: {output_dir}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    excluded = {Path(value).as_posix() for value in config["exclude"]}

    output_dir.mkdir(parents=True)
    for relative_value in config["files"]:
        relative = Path(relative_value)
        _copy_file(ROOT / relative, output_dir / relative)

    for relative_value in config["directories"]:
        directory = ROOT / relative_value
        if not directory.is_dir():
            raise FileNotFoundError(f"Public release directory not found: {directory}")
        for source in directory.rglob("*"):
            if not source.is_file():
                continue
            relative = source.relative_to(ROOT)
            if relative.as_posix() in excluded or _is_ignored(relative):
                continue
            _copy_file(source, output_dir / relative)

    summary = validate_public_release(output_dir)
    summary["release_id"] = str(config["release_id"])
    (output_dir / "PUBLIC_RELEASE.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def validate_public_release(output_dir: Path) -> dict[str, int | str]:
    output_dir = output_dir.resolve()
    if not (output_dir / "README.md").is_file():
        raise FileNotFoundError(f"Public release README not found: {output_dir / 'README.md'}")
    files = [path for path in output_dir.rglob("*") if path.is_file()]
    violations: list[str] = []
    for path in files:
        relative = path.relative_to(output_dir).as_posix()
        if relative.startswith(FORBIDDEN_PREFIXES):
            violations.append(f"forbidden path: {relative}")
        if path.stat().st_size > 50 * 1024 * 1024:
            violations.append(f"file exceeds 50 MiB: {relative}")
        if path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            for marker in LOCAL_PATH_MARKERS:
                if marker in text:
                    violations.append(f"absolute local path in {relative}: {marker}")
    if violations:
        raise ValueError("Public release validation failed:\n" + "\n".join(violations))
    return {
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export an allowlisted public repository tree.")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "public-release-v0.1.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "tmp" / "public-release-v0.1",
    )
    args = parser.parse_args()
    summary = export_public_release(args.config, args.output_dir)
    print(
        f"public release valid: id={summary['release_id']} "
        f"files={summary['file_count']} bytes={summary['total_bytes']}"
    )


if __name__ == "__main__":
    main()
