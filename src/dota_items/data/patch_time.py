"""Hash-bound official release-time inference, not game-client patch certification."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from dota_items.data.contracts import StrictContract
from dota_items.storage import inside

OFFICIAL_PATCH_URL = "https://www.dota2.com/datafeed/patchnoteslist?language=english"


class PatchReceipt(StrictContract):
    schema_version: Literal["patch-time-evidence/1"]
    source_url: Literal[OFFICIAL_PATCH_URL]
    snapshot: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_at: str
    boundary_buffer_seconds: int = Field(ge=0, le=86400)


def load_patch_window(receipt_path: Path, patch: str) -> dict:
    receipt_bytes = receipt_path.read_bytes()
    receipt = PatchReceipt.model_validate_json(receipt_bytes)
    retrieved = datetime.fromisoformat(receipt.retrieved_at)
    if retrieved.tzinfo is None:
        raise ValueError("patch retrieval timestamp must include timezone")
    upper = int(retrieved.timestamp())
    snapshot = inside(receipt_path.parent.resolve(), receipt.snapshot).read_bytes()
    if hashlib.sha256(snapshot).hexdigest() != receipt.sha256:
        raise ValueError("patch snapshot hash mismatch")
    data = json.loads(snapshot)
    rows = data.get("patches") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("patch list must be nonempty")
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("patch_number"), str)
        or not row["patch_number"]
        or type(row.get("patch_timestamp")) is not int
        or not 0 < row["patch_timestamp"] <= upper
        for row in rows
    ):
        raise ValueError("invalid release record or release after retrieval")
    if len({r["patch_number"] for r in rows}) != len(rows) or len(
        {r["patch_timestamp"] for r in rows}
    ) != len(rows):
        raise ValueError("ambiguous patch release records")
    target = next((r for r in rows if r["patch_number"] == patch), None)
    if target is None:
        raise ValueError("requested patch absent from snapshot")
    lower = target["patch_timestamp"]
    later = [r["patch_timestamp"] for r in rows if r["patch_timestamp"] > lower]
    return {
        "patch": patch,
        "release_timestamp": lower,
        "upper_exclusive": min(later) if later else upper,
        "upper_kind": "next_release" if later else "snapshot_retrieval",
        "boundary_buffer_seconds": receipt.boundary_buffer_seconds,
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "snapshot_sha256": receipt.sha256,
        "source_url": receipt.source_url,
        "retrieved_at": receipt.retrieved_at,
        "method": "official_release_time_inference",
        "limitations": (
            "Release timestamps do not prove server rollout, lobby version or client patch."
        ),
    }


def classify_patch_time(start, duration, window: dict) -> str:
    if type(start) is not int or start <= 0 or type(duration) is not int or duration < 0:
        return "unknown_time"
    lower, upper = window["release_timestamp"], window["upper_exclusive"]
    buffer = window["boundary_buffer_seconds"]
    end = start + duration
    if start < lower or start >= upper:
        return "outside_interval"
    if end >= upper:
        return "crosses_upper_boundary"
    if start < lower + buffer or (window["upper_kind"] == "next_release" and end >= upper - buffer):
        return "boundary_uncertain"
    return "time_consistent"
