"""Opt-in task-bound snapshots; historical /1 producer remains unchanged."""

from pathlib import Path

from dota_items.contracts.tasks import TASK_ID, task_contract
from dota_items.data.purchase_snapshot import build_snapshot
from dota_items.storage import file_hash, json_bytes, read_json


def build_task_snapshot(summary_path, *, task_id=TASK_ID, allow_producer_migration=False):
    contract = task_contract(task_id)
    before = file_hash(summary_path)
    summary = read_json(summary_path)
    config = summary["audit"]["config"]
    expected = {
        "hero_id": contract["target_hero_id"],
        "requested_role": contract["role"]["requested_position"],
        "requested_patch": contract["patch_scope"]["patches"][0],
        "window_start": contract["window"]["start_seconds"],
        "window_end": contract["window"]["end_seconds"],
        "candidate_items": contract["labels"]["candidate_items"],
    }
    if json_bytes({k: config.get(k) for k in expected}) != json_bytes(expected):
        raise ValueError("Producer configuration differs from registered task")
    snapshot = build_snapshot(summary_path, allow_producer_migration=allow_producer_migration)
    if file_hash(summary_path) != before:
        raise ValueError("Summary changed during task snapshot construction")
    if any(row.get("patch_time_check") != "time_consistent" for row in summary["audit"]["results"]):
        raise ValueError("Task patch scope requires consistent release-time evidence")
    if any(
        row["features"].get("target_hero_id") != contract["target_hero_id"]
        for row in snapshot["samples"]
    ):
        raise ValueError("Sample hero differs from registered task")
    snapshot["schema_version"] = "purchase-log-modeling-snapshot/2"
    snapshot["task"]["contract"] = contract
    package = Path(__file__).resolve().parents[1]
    snapshot["task_implementation_sha256"] = {
        name: file_hash(package / name) for name in ("contracts/tasks.py", "data/task_snapshot.py")
    }
    return snapshot


def verify_task_snapshot(
    snapshot_path, summary_path, *, task_id=TASK_ID, allow_producer_migration=False
):
    saved = read_json(snapshot_path)
    rebuilt = build_task_snapshot(
        summary_path, task_id=task_id, allow_producer_migration=allow_producer_migration
    )
    if json_bytes(saved) != json_bytes(rebuilt):
        raise ValueError("Task snapshot differs from source reconstruction")
    return saved
