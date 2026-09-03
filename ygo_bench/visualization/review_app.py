from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image


ASSET_DIR = Path(__file__).with_name("reviewer_assets")
DECISIONS = {"pass", "revise", "reject"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _image_url(category: str, output: dict[str, str]) -> str:
    filename = output.get("png")
    if not filename:
        raise ValueError(
            f"Review output for {category} has no PNG. Re-run render_pilot_review with --edge."
        )
    return f"/{category}/{filename}"


def _thumbnail_url(category: str, output: dict[str, str]) -> str:
    filename = Path(output["png"]).with_suffix(".jpg").name
    return f"/thumbnails/{category}/{filename}"


def build_review_catalog(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_dir = manifest_path.parent
    card_image_dir = Path(manifest["inputs"]["card_image_dir"])
    understanding = _read_jsonl(Path(manifest["inputs"]["understanding"]))
    construction = _read_jsonl(Path(manifest["inputs"]["construction"]))
    outputs = manifest["outputs"]
    items: list[dict[str, Any]] = []

    if len(understanding) != len(outputs["understanding"]):
        raise ValueError("Understanding records and rendered outputs are misaligned")
    for index, (record, output) in enumerate(
        zip(understanding, outputs["understanding"]), start=1
    ):
        snapshot = str(record["snapshot_id"])
        card_ids = [int(value) for value in record["input"]["card_ids"]]
        missing = [
            card_id
            for card_id in card_ids
            if not (card_image_dir / f"{card_id}.jpg").is_file()
        ]
        items.append(
            {
                "id": str(record["record_id"]),
                "category": "understanding",
                "category_label": "理解",
                "subtype": str(record["candidate_kind"]),
                "title": f"Understanding {index:02d} / {len(understanding):02d}",
                "subtitle": str(record["input"]["question"]),
                "snapshot_id": snapshot,
                "regulation": "TCG" if snapshot.startswith("tcg-") else "OCG",
                "source": str(record["record_id"]),
                "image_url": _image_url("understanding", output),
                "thumbnail_url": _thumbnail_url("understanding", output),
                "asset_issues": [f"missing card image: {value}" for value in missing],
                "core_status": "not_applicable",
            }
        )

    groups: dict[str, list[dict[str, Any]]] = {}
    for record in construction:
        groups.setdefault(str(record["group_id"]), []).append(record)
    sorted_groups = sorted(groups.items())
    if len(sorted_groups) != len(outputs["construction"]):
        raise ValueError("Construction groups and rendered outputs are misaligned")
    for index, ((group_id, records), output) in enumerate(
        zip(sorted_groups, outputs["construction"]), start=1
    ):
        corrupted = next(
            record
            for record in records
            if record["task_type"] == "controlled_corruption_audit"
        )
        payload = corrupted["input"]
        card_names = {
            int(card["card_id"]): str(card["name"])
            for cards in payload["zones"].values()
            for card in cards
        }
        missing = sorted(
            card_id
            for card_id in card_names
            if not (card_image_dir / f"{card_id}.jpg").is_file()
        )
        items.append(
            {
                "id": group_id,
                "category": "construction",
                "category_label": "构筑",
                "subtype": "controlled_corruption_group",
                "title": f"Construction {index:02d} / {len(sorted_groups):02d}",
                "subtitle": str(payload["deck_name"]),
                "snapshot_id": str(corrupted["snapshot_id"]),
                "regulation": str(payload["regulation"]),
                "source": group_id,
                "image_url": _image_url("construction", output),
                "thumbnail_url": _thumbnail_url("construction", output),
                "asset_issues": [
                    f"{card_id} · {card_names[card_id]}" for card_id in missing
                ],
                "core_status": "not_applicable",
            }
        )

    puzzle_states = manifest["puzzle_states"]
    if len(puzzle_states) != len(outputs["puzzles"]):
        raise ValueError("Puzzle states and rendered outputs are misaligned")
    for index, (state, output) in enumerate(
        zip(puzzle_states, outputs["puzzles"]), start=1
    ):
        missing = sorted(
            {
                int(card["card_id"])
                for card in state["cards"]
                if not (card_image_dir / f"{card['card_id']}.jpg").is_file()
            }
        )
        issues = [f"missing card image: {card_id}" for card_id in missing]
        if state["unparsed_add_card_calls"]:
            issues.append(
                f"unparsed AddCard calls: {state['unparsed_add_card_calls']}"
            )
        if state["has_custom_effect"]:
            issues.append("contains custom Effect")
        if state["overlay_call_count"]:
            issues.append(
                f"dynamic Overlay calls not statically resolved: {state['overlay_call_count']}"
            )
        relative_path = str(state["relative_path"])
        items.append(
            {
                "id": f"puzzle:{relative_path}",
                "category": "puzzles",
                "category_label": "策略 Puzzle",
                "subtype": relative_path.split("/", 1)[0],
                "title": f"Puzzle {index:02d} / {len(puzzle_states):02d}",
                "subtitle": str(state["title"]),
                "snapshot_id": "projectignis-1177a180",
                "regulation": "legacy/mixed",
                "source": relative_path,
                "image_url": _image_url("puzzles", output),
                "thumbnail_url": _thumbnail_url("puzzles", output),
                "asset_issues": issues,
                "core_status": "static_only",
            }
        )

    metadata_path = card_image_dir.parent / "metadata.json"
    summary_path = card_image_dir.parent / "summary.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "dataset_version": str(manifest.get("dataset_version", "pilot-review-v0.2")),
        "items": items,
        "counts": manifest["counts"],
        "asset_snapshot": {
            "name": card_image_dir.parent.name,
            "passcode_count": metadata["passcode_count"],
            "cached_file_count": summary["cached_file_count"],
            "failed": summary["failed"],
            "started_at_unix": metadata["started_at_unix"],
            "sources": [source["name"] for source in metadata["sources"]],
        },
        "output_dir": str(output_dir.resolve()),
    }


def build_thumbnails(catalog: dict[str, Any], output_dir: Path) -> None:
    for item in catalog["items"]:
        source = output_dir / item["image_url"].lstrip("/")
        target = output_dir / item["thumbnail_url"].lstrip("/")
        if target.is_file() and target.stat().st_mtime_ns >= source.stat().st_mtime_ns:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            image = image.convert("RGB")
            image.thumbnail((360, 240), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (360, 240), "#e7ebe8")
            position = ((360 - image.width) // 2, (240 - image.height) // 2)
            canvas.paste(image, position)
            canvas.save(target, "JPEG", quality=84, optimize=True)


class ReviewStore:
    def __init__(
        self,
        path: Path,
        item_ids: set[str],
        dataset_version: str = "pilot-review-v0.2",
    ) -> None:
        self.path = path
        self.item_ids = item_ids
        self.dataset_version = dataset_version
        self.lock = threading.Lock()

    def latest(self) -> dict[str, dict[str, Any]]:
        if not self.path.is_file():
            return {}
        reviews: dict[str, dict[str, Any]] = {}
        for record in _read_jsonl(self.path):
            reviews[str(record["item_id"])] = record
        return reviews

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        item_id = payload.get("item_id")
        decision = payload.get("decision")
        note = payload.get("note", "")
        if item_id not in self.item_ids:
            raise ValueError(f"Unknown review item: {item_id}")
        if decision not in DECISIONS:
            raise ValueError(f"Unknown review decision: {decision}")
        if not isinstance(note, str) or len(note) > 4000:
            raise ValueError("Review note must be a string of at most 4000 characters")
        record = {
            "item_id": item_id,
            "dataset_version": self.dataset_version,
            "decision": decision,
            "note": note.strip(),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record


def make_handler(
    output_dir: Path,
    catalog: dict[str, Any],
    store: ReviewStore,
) -> type[SimpleHTTPRequestHandler]:
    class ReviewHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(output_dir), **kwargs)

        def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload: Any, status: int = 200) -> None:
            self._send_bytes(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
                status,
            )

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/":
                self._send_bytes(
                    (ASSET_DIR / "reviewer.html").read_bytes(),
                    "text/html; charset=utf-8",
                )
                return
            if path == "/api/catalog":
                self._send_json({**catalog, "reviews": store.latest()})
                return
            if path == "/config.json":
                self._send_json(
                    {
                        "storage_mode": "server",
                        "catalog_url": "api/catalog",
                        "review_url": "api/reviews",
                        "dataset_version": catalog["dataset_version"],
                    }
                )
                return
            if path.startswith("/assets/"):
                asset_name = path.removeprefix("/assets/")
                if asset_name not in {"reviewer.css", "reviewer.js"}:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                content_type = (
                    "text/css; charset=utf-8"
                    if asset_name.endswith(".css")
                    else "text/javascript; charset=utf-8"
                )
                self._send_bytes((ASSET_DIR / asset_name).read_bytes(), content_type)
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/reviews":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("Review request body must be between 1 and 65536 bytes")
                payload = json.loads(self.rfile.read(length))
                self._send_json(store.save(payload), HTTPStatus.CREATED)
            except (ValueError, json.JSONDecodeError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"{self.address_string()} - {format % args}")

    return ReviewHandler


def serve_review_app(
    manifest_path: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    manifest_path = manifest_path.resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Review manifest not found: {manifest_path}")
    output_dir = manifest_path.parent
    catalog = build_review_catalog(manifest_path)
    build_thumbnails(catalog, output_dir)
    store = ReviewStore(
        output_dir / "reviews.jsonl",
        {str(item["id"]) for item in catalog["items"]},
        dataset_version=catalog["dataset_version"],
    )
    server = ThreadingHTTPServer((host, port), make_handler(output_dir, catalog, store))
    print(f"YGO-Bench reviewer: http://{host}:{port}", flush=True)
    print(f"Review log: {store.path}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
