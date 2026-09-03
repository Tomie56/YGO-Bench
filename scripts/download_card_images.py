from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = "runtime-modern-v1-2026-07-20"
DEFAULT_CODE_LIST = ROOT / "data/runtime_snapshots" / DEFAULT_SNAPSHOT / "code_list.txt"
DEFAULT_OUTPUT = ROOT / "data/card_images" / DEFAULT_SNAPSHOT / "full"
IMAGE_SOURCES = (
    ("ygoprodeck", "https://images.ygoprodeck.com/images/cards/{passcode}.jpg"),
    ("ygocdb", "https://cdn.233.momobako.com/ygopro/pics/{passcode}.jpg"),
)


@dataclass(frozen=True)
class DownloadResult:
    passcode: int
    source: str
    url: str
    status: str
    bytes_written: int
    sha256: str | None
    error: str | None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_passcodes(path: Path) -> list[int]:
    if not path.is_file():
        raise FileNotFoundError(f"Code list not found: {path}")
    passcodes = [int(line) for line in path.read_text(encoding="ascii").splitlines()]
    if not passcodes:
        raise ValueError(f"Code list is empty: {path}")
    if len(passcodes) != len(set(passcodes)):
        raise ValueError(f"Code list contains duplicate passcodes: {path}")
    return passcodes


def download_one(passcode: int, output_dir: Path) -> DownloadResult:
    target = output_dir / f"{passcode}.jpg"
    if target.is_file() and target.stat().st_size > 0:
        return DownloadResult(
            passcode,
            "cached",
            "",
            "existing",
            target.stat().st_size,
            sha256_file(target),
            None,
        )

    temporary = target.with_name(
        f".{passcode}.{os.getpid()}.{threading.get_ident()}.jpg.part"
    )
    errors: list[str] = []
    for source, template in IMAGE_SOURCES:
        url = template.format(passcode=passcode)
        request = Request(url, headers={"User-Agent": "ygo-bench-image-cache/0.1"})
        try:
            with urlopen(request, timeout=30) as response:
                content_type = response.headers.get_content_type()
                if content_type != "image/jpeg":
                    raise ValueError(f"Expected image/jpeg, received {content_type}")
                with temporary.open("wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
            temporary.replace(target)
            return DownloadResult(
                passcode,
                source,
                url,
                "downloaded",
                target.stat().st_size,
                sha256_file(target),
                None,
            )
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as error:
            temporary.unlink(missing_ok=True)
            errors.append(f"{source}: {error}")
    return DownloadResult(passcode, "", "", "failed", 0, None, "; ".join(errors))


def scheduled_passcodes(passcodes: Iterable[int], rate: float) -> Iterable[int]:
    interval = 1 / rate
    next_start = time.monotonic()
    for passcode in passcodes:
        delay = next_start - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        yield passcode
        next_start += interval


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download the YGOPRODeck JPEG cache for one frozen runtime code list."
    )
    parser.add_argument("--code-list", type=Path, default=DEFAULT_CODE_LIST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--requests-per-second", type=float, default=10.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Request only passcodes that are absent from the local cache.",
    )
    args = parser.parse_args()
    if not 0 < args.requests_per_second <= 20:
        parser.error("--requests-per-second must be in (0, 20]")
    if args.workers < 1:
        parser.error("--workers must be positive")

    code_list = args.code_list.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    passcodes = load_passcodes(code_list)
    scheduled = passcodes
    if args.missing_only:
        scheduled = [
            passcode
            for passcode in passcodes
            if not (output_dir / f"{passcode}.jpg").is_file()
        ]
    run_manifest = output_dir.parent / "download-manifest.jsonl"
    metadata = {
        "sources": [
            {"name": source, "image_url_template": template}
            for source, template in IMAGE_SOURCES
        ],
        "code_list": str(code_list.relative_to(ROOT)),
        "code_list_sha256": sha256_file(code_list),
        "passcode_count": len(passcodes),
        "scheduled_passcode_count": len(scheduled),
        "requests_per_second": args.requests_per_second,
        "workers": args.workers,
        "started_at_unix": time.time(),
    }
    (output_dir.parent / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    results: list[DownloadResult] = []
    with run_manifest.open("a", encoding="utf-8") as manifest, ThreadPoolExecutor(
        max_workers=args.workers
    ) as executor:
        futures: set[Future[DownloadResult]] = set()

        def record(completed: set[Future[DownloadResult]]) -> None:
            for future in completed:
                result = future.result()
                results.append(result)
                manifest.write(json.dumps(asdict(result)) + "\n")
            manifest.flush()

        for passcode in scheduled_passcodes(scheduled, args.requests_per_second):
            futures.add(executor.submit(download_one, passcode, output_dir))
            done, futures = wait(futures, timeout=0, return_when=FIRST_COMPLETED)
            record(done)
            if len(futures) >= args.workers * 2:
                done, futures = wait(futures, return_when=FIRST_COMPLETED)
                record(done)
        while futures:
            done, futures = wait(futures, return_when=FIRST_COMPLETED)
            record(done)

    summary = {
        "passcode_count": len(passcodes),
        "scheduled_passcode_count": len(scheduled),
        "downloaded": sum(result.status == "downloaded" for result in results),
        "existing": sum(result.status == "existing" for result in results),
        "failed": sum(result.status == "failed" for result in results),
        "cached_file_count": sum(
            (output_dir / f"{passcode}.jpg").is_file() for passcode in passcodes
        ),
    }
    (output_dir.parent / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    if summary["failed"]:
        raise SystemExit("One or more card images failed; inspect download-manifest.jsonl")


if __name__ == "__main__":
    main()
