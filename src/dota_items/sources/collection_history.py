"""Frozen historical exclusion IDs and fail-closed discovery filtering."""

from pathlib import Path

from dota_items.storage import file_hash, read_json


def freeze_history(data: Path, previous: Path):
    ids, sources, previous_ids = set(), {}, set()
    for path in sorted(previous.glob("batch-*/plan.json")):
        plan = read_json(path)
        previous_ids.update(plan["match_ids"])
        ids.update(plan["match_ids"])
        sources[str(path)] = file_hash(path)
    if not previous_ids:
        raise ValueError("Previous collection plans required")
    for path in sorted(data.rglob("*.json")):
        # Includes retained raw matches, acquisition manifests and prior rejected IDs.
        stem = path.name.split(".")[0]
        if stem.isdigit() and int(stem) > 0:
            ids.add(int(stem))
    return {
        "schema_version": "purchase-collection-exclusions/1",
        "excluded_match_ids": sorted(ids),
        "initial_upper_match_id_exclusive": min(previous_ids),
        "previous_plans_sha256": sources,
        "scope": "All previous collection plans and numeric JSON cache filenames under data",
    }


def filter_discovery(rows, excluded, lower, upper):
    ids = [row.get("match_id") for row in rows]
    if any(type(mid) is not int or not lower < mid < upper for mid in ids):
        raise ValueError("Discovery match outside requested range")
    if len(ids) > 100 or len(ids) != len(set(ids)) or ids != sorted(ids, reverse=True):
        raise ValueError("Discovery duplicates, order or page size invalid")
    return [row for row in rows if row["match_id"] not in excluded]
