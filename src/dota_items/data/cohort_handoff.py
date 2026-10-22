"""Offline cohort diagnostics and immutable handoff; never assigns new splits."""

import math
from collections import Counter
from pathlib import Path
from statistics import median

from dota_items.data.feasibility_sampling import verify_plan
from dota_items.data.lineup_preflight import verify_preflight
from dota_items.data.player_overlap import audit_player_overlap
from dota_items.data.purchase_observation import observe_purchases
from dota_items.data.purchase_snapshot import verify_snapshot
from dota_items.handoff.bundle import load_handoff_json as load_handoff_json
from dota_items.handoff.bundle import validate_bundle_payloads as validate_bundle_payloads
from dota_items.handoff.bundle import verify_bundle as verify_bundle
from dota_items.sources.collection_history import filter_discovery
from dota_items.storage import file_hash, json_bytes, read_json

RECEIPT = Path("knowledge/evidence/feasibility-2026-10-13/receipt.json")


def checked(path, expected):
    if file_hash(path) != expected:
        raise ValueError(f"Hash mismatch: {path}")


def numeric(values):
    """Count nonnumbers (including bool) as missing; reject nonfinite observations."""
    valid = [v for v in values if type(v) in (int, float)]
    if any(type(v) is float and not math.isfinite(v) for v in valid):
        raise ValueError("Nonfinite numeric observation; denominator was not changed")
    middle = median(valid) if valid else None
    if type(middle) is float and not math.isfinite(middle):
        raise ValueError("Nonfinite numeric median")
    return {
        "observed": len(valid),
        "missing": len(values) - len(valid),
        "min": min(valid) if valid else None,
        "median": middle,
        "max": max(valid) if valid else None,
    }


def component_impact(groups, old_samples, new_ids):
    old = {r["match_id"]: r for r in old_samples}
    new = set(new_ids)
    result = []
    for i, group in enumerate(sorted(groups)):
        members = [old[mid] for mid in group if mid in old]
        splits = sorted({r["split"] for r in members})
        result.append(
            {
                "component": f"combined-{i:04d}",
                "match_ids": group,
                "size": len(group),
                "old_count": len(members),
                "new_count": len(set(group) & new),
                "old_splits": splits,
                "old_group_count": len({r["group_id"] for r in members}),
                "bridges_old_splits": len(splits) > 1,
            }
        )
    return {
        "groups": result,
        "group_count": len(result),
        "largest_group": max((r["size"] for r in result), default=0),
        "mixed_old_new_groups": sum(bool(r["old_count"] and r["new_count"]) for r in result),
        "bridging_group_count": sum(r["bridges_old_splits"] for r in result),
        "new_in_bridging_groups": sum(r["new_count"] for r in result if r["bridges_old_splits"]),
        "new_without_observed_old_connection": sum(
            r["new_count"] for r in result if not r["old_count"]
        ),
    }


def graph(rows, paths, old_samples, new_ids):
    old_ids = {r["match_id"] for r in old_samples}
    # Diagnostic cohort buckets only, NOT an evaluation split.
    overlap = audit_player_overlap(
        rows, paths, {"train": sorted(old_ids), "validation": sorted(new_ids), "test": []}
    )
    return {
        "bucket_meaning": {"train": "old cohort", "validation": "new cohort", "test": "empty"},
        "not_a_model_split": True,
        "identity_coverage_complete": overlap["identity_coverage_complete"],
        "identity_summary": overlap["summary"],
        "direct_shared_known_players": overlap["split_pairs"][0]["shared_known_players"],
        **component_impact(overlap["connected_match_groups"], old_samples, new_ids),
    }


def distribution(rows, paths, discovery, items):
    support = {k: Counter() for k in items}
    logs, roles, patches = Counter(), Counter(), Counter()
    ranks, rank_n, starts, durations = [], [], [], []
    heroes = {side: Counter() for side in ("ally", "enemy")}
    after = empty = duplicate = simultaneous = recipes = 0
    for row in rows:
        mid = row["match_id"]
        raw = read_json(paths[mid])
        checked(paths[mid], row["sha256"])
        target = next(p for p in raw["players"] if p["player_slot"] == row["target_slot"])
        obs = observe_purchases(target, items)
        logs[obs["log_status"]] += 1
        empty += target.get("purchase_log") == []
        after += obs["has_event_at_or_after_window_end"]
        duplicate += bool(row["exact_duplicate_event_rows"])
        simultaneous += bool(row["simultaneous_distinct_item_times"])
        recipes += bool(row["recipe_rows_in_window"])
        for value in obs["items"]:
            support[value["item_key"]][
                "unknown"
                if not value["log_presence_mask"]
                else "positive"
                if value["log_presence"]
                else "negative"
            ] += 1
        roles[row["semantic_review"]["role_evidence"]["status"]] += 1
        patches[row["patch_time_check"]] += 1
        d = discovery[mid]
        ranks.append(d.get("avg_rank_tier"))
        rank_n.append(d.get("num_rank_tier"))
        starts.append(raw.get("start_time"))
        durations.append(raw.get("duration"))
        for player in raw["players"]:
            side = (
                "ally"
                if (player["player_slot"] < 128) == (target["player_slot"] < 128)
                else "enemy"
            )
            heroes[side][str(player["hero_id"])] += 1
    return {
        "matches": len(rows),
        "log_status": dict(logs),
        "empty_logs": empty,
        "event_at_or_after_1800": after,
        "matches_with_exact_duplicate_rows": duplicate,
        "matches_with_simultaneous_distinct_items": simultaneous,
        "matches_with_recipe_rows": recipes,
        "role_hints": dict(roles),
        "patch_time": dict(patches),
        "start_time_unix": numeric(starts),
        "duration_seconds": numeric(durations),
        "discovery_average_rank_hint": numeric(ranks),
        "discovery_rank_record_count": numeric(rank_n),
        "hero_counts": {k: dict(v) for k, v in heroes.items()},
        "log_observation_support": {
            k: {
                **{s: v[s] for s in ("positive", "negative", "unknown")},
                "positive_rate": v["positive"] / (v["positive"] + v["negative"])
                if v["positive"] + v["negative"]
                else None,
            }
            for k, v in support.items()
        },
    }


def audit_collection(root, replay, *, allow_producer_migration=False):
    progress = read_json(root / "progress.json")
    rules = read_json(root / "collection.json")
    checked(RECEIPT, rules["patch_receipt_sha256"])
    history = None
    if "exclusions_sha256" in rules:
        checked(root / "exclusions.json", rules["exclusions_sha256"])
        history = set(read_json(root / "exclusions.json")["excluded_match_ids"])
    evidence, rows, discovery, excluded, attempted, candidates = {}, [], {}, [], [], []
    for number in range(1, progress["last_complete_batch"] + 1):
        batch = root / f"batch-{number:04d}"
        plan, _ = verify_plan(batch / "plan.json", batch / "discovery.json")
        if plan.audit_config.model_dump(mode="json") != rules["audit_config"]:
            raise ValueError("Batch audit configuration differs")
        done, cleanup = read_json(batch / "complete.json"), read_json(batch / "cleanup.json")
        checked(batch / "preflight.json", done["report_sha256"])
        checked(batch / "cleanup.json", done["cleanup_sha256"])
        checked(batch / "preflight.json", cleanup["report_sha256"])
        receipt = read_json(batch / "receipt.json")
        checked(batch / "response.json", receipt["sha256"])
        found = read_json(batch / "discovery.json")
        response = read_json(batch / "response.json")["rows"]
        if history is not None:
            response = filter_discovery(
                response, history, receipt["query_lower"], receipt["query_upper"]
            )
        if json_bytes(response) != json_bytes(found):
            raise ValueError("Discovery differs from original response")
        if replay:
            verify_preflight(
                batch / "preflight.json",
                batch / "plan.json",
                batch / "discovery.json",
                batch / "matches",
                RECEIPT,
                **({"allow_producer_migration": True} if allow_producer_migration else {}),
            )
        saved = read_json(batch / "preflight.json")
        if [r["requested_match_id"] for r in saved["audit"]["results"]] != plan.match_ids:
            raise ValueError("Audit order differs from plan")
        attempted.extend(plan.match_ids)
        discovery.update({r["match_id"]: r for r in found})
        rows.extend(saved["audit"]["results"])
        candidates.extend(
            {
                "match_id": s["match_id"],
                "path": str(batch / "matches" / f"{s['match_id']}.json"),
                "sha256": s["source_sha256"],
            }
            for s in saved["samples"]
        )
        for exclusion in saved["exclusions"]:
            mid = exclusion["requested_match_id"]
            path = batch / "matches" / f"{mid}.json"
            failure = batch / f"failure-{mid}.json"
            excluded.append(
                {
                    **exclusion,
                    "batch": batch.name,
                    "cache_present": path.exists(),
                    "evidence_level": "offline_replayed" if replay else "historical_receipt_only",
                    "failure_receipt": read_json(failure) if failure.exists() else None,
                }
            )
        for path in batch.glob("*.json"):
            evidence[str(path)] = file_hash(path)
    if len(attempted) != len(set(attempted)) or len(attempted) != progress["attempted"]:
        raise ValueError("Duplicate attempted ID or wrong denominator")
    if json_bytes(candidates) != json_bytes(progress["candidates"]):
        raise ValueError("Candidate ledger differs from batch evidence")
    if len(candidates) != progress["retained_candidates"]:
        raise ValueError("Candidate count differs")
    for source in candidates:
        Path(source["path"]).resolve().relative_to(root.resolve())
        checked(Path(source["path"]), source["sha256"])
    for path in (root / "progress.json", root / "collection.json", RECEIPT):
        evidence[str(path)] = file_hash(path)
    if history is not None:
        evidence[str(root / "exclusions.json")] = file_hash(root / "exclusions.json")
    return {
        "progress": progress,
        "rows": rows,
        "discovery": discovery,
        "exclusions": excluded,
        "evidence": evidence,
        "attempted_ids": attempted,
    }


def build_audit(old_root, new_root, summary_path, snapshot_path, *, allow_producer_migration=False):
    options = {"allow_producer_migration": True} if allow_producer_migration else {}
    snapshot = verify_snapshot(snapshot_path, summary_path, **options)
    old, new = (
        audit_collection(old_root, False, **options),
        audit_collection(new_root, True, **options),
    )
    if set(old["attempted_ids"]) & set(new["attempted_ids"]):
        raise ValueError("Old/new attempted IDs overlap")
    old_sources, new_sources = old["progress"]["candidates"], new["progress"]["candidates"]
    old_ids, new_ids = {s["match_id"] for s in old_sources}, {s["match_id"] for s in new_sources}
    if old_ids != {s["match_id"] for s in snapshot["samples"]}:
        raise ValueError("Old candidates differ from frozen snapshot")
    old_rows = read_json(summary_path)["audit"]["results"]
    new_rows = [r for r in new["rows"] if r["match_id"] in new_ids]
    all_new = [r for r in new["rows"] if r["status"] == "inspectable"]
    paths = {s["match_id"]: Path(s["path"]) for s in old_sources + new_sources}
    paths.update({r["match_id"]: Path(r["input"]) for r in all_new})
    items = snapshot["task"]["candidate_items"]
    distributions = {
        "old_retained": distribution(old_rows, paths, old["discovery"], items),
        "new_retained": distribution(new_rows, paths, new["discovery"], items),
        "new_inspectable": distribution(all_new, paths, new["discovery"], items),
    }
    graphs = {
        "retained_only": graph(old_rows + new_rows, paths, snapshot["samples"], new_ids),
        "including_new_excluded_inspectable": graph(
            old_rows + all_new, paths, snapshot["samples"], {r["match_id"] for r in all_new}
        ),
    }
    # Bind all surviving source bytes and acquisition manifests, including rejected inputs.
    evidence = {**old["evidence"], **new["evidence"]}
    for path in paths.values():
        evidence[str(path)] = file_hash(path)
        manifest = path.with_suffix(".manifest.json")
        evidence[str(manifest)] = file_hash(manifest)
    for path in (summary_path, snapshot_path, Path(__file__)):
        evidence[str(path)] = file_hash(path)
    if allow_producer_migration:
        from dota_items.data.producer_migration import ADDED, LEGACY_SHA256, ROOT

        for relative in sorted(set(LEGACY_SHA256) | ADDED):
            path = ROOT / relative
            evidence[str(path)] = file_hash(path)
    return {
        "schema_version": "purchase-cohort-audit/1",
        **({"producer_migration": "public-reader/1"} if allow_producer_migration else {}),
        "training_allowed": False,
        "new_split_assigned": False,
        "old_split_changed": False,
        "distributions": distributions,
        "graphs": graphs,
        "collections": {
            name: {
                "attempted": c["progress"]["attempted"],
                "retained": c["progress"]["retained_candidates"],
                "excluded": len(c["exclusions"]),
                "reason_counts": dict(
                    Counter(reason for r in c["exclusions"] for reason in r["reasons"])
                ),
                "excluded_cache_present": sum(r["cache_present"] for r in c["exclusions"]),
                "exclusions": c["exclusions"],
            }
            for name, c in (("old", old), ("new", new))
        },
        "evidence_sha256": evidence,
        "limitations": [
            "Descriptive audit, not model evaluation or admission.",
            "Old rejected raw files may be absent: "
            "historical receipts cannot independently replay them.",
            "Known account connectivity is not verified human identity; "
            "missing accounts hide edges.",
            "Expanded graph does not change the original split or imply direct old split overlap.",
            "Rank and role are hints; patch time consistency is not client-version certification.",
            "Source-log absence is not actual nonpurchase; new cohort usage needs owner decision.",
        ],
    }
