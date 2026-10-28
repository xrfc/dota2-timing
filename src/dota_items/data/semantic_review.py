"""Same-payload consistency checks; never independent completion/role certification."""

import math
from collections import defaultdict


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _comparison(player, field, key, expected, complete):
    values = player.get(field)
    if values is None:
        return {"status": "missing"}
    if not isinstance(values, dict):
        return {"status": "invalid"}
    if key not in values:
        return {"status": "missing"}
    value = values[key]
    if not _number(value):
        return {"status": "invalid"}
    return {
        "reported": value,
        "recomputed": expected,
        "status": "unverifiable"
        if not complete
        else ("consistent" if value == expected else "inconsistent"),
    }


def review_semantics(raw, target, timeline, candidate_items):
    """Caller has checked ten unique player identities; events reuse normalization."""
    index = raw["players"].index(target)
    prefix = f"players[{index}]"
    team = [p for p in raw["players"] if (p["player_slot"] < 128) == (target["player_slot"] < 128)]
    position = target.get("position_est")
    position_valid = type(position) is int and 1 <= position <= 5
    role = {
        "status": "estimated_carry"
        if position_valid and position == 1
        else ("estimated_other" if position_valid else "unknown"),
        "position_est": position if position_valid else None,
        "position_est_ref": prefix + ".position_est",
        "lane_role": target.get("lane_role") if type(target.get("lane_role")) is int else None,
        "same_lane_team_slots": [
            p["player_slot"]
            for p in team
            if type(target.get("lane_role")) is int
            and type(p.get("lane_role")) is int
            and p["lane_role"] == target["lane_role"]
        ],
        "team": [
            {
                "player_slot": p["player_slot"],
                "hero_id": p["hero_id"],
                "lane_role": p.get("lane_role") if type(p.get("lane_role")) is int else None,
                "position_est": p.get("position_est")
                if type(p.get("position_est")) is int and 1 <= p["position_est"] <= 5
                else None,
            }
            for p in sorted(team, key=lambda p: p["player_slot"])
        ],
        "verified_position": False,
        "usable_as_pregame_feature": False,
        "reason": "position_est uses minutes 10-12 farm and wards; lane_role means lane only.",
    }
    grouped = defaultdict(list)
    # Match upstream compute's projection; recipe omission is not evidence of parser loss.
    for event in timeline.events:
        if not event.item_key.startswith("recipe_") and event.item_key != "ward_dispenser":
            grouped[event.item_key].append(event)
    complete = timeline.purchase_log_status == "present" and not any(
        flag.startswith("invalid_event:") for flag in timeline.quality_flags
    )
    rows = []
    for key, events in sorted(grouped.items()):
        times = [e.time_seconds for e in events]
        rows.append(
            {
                "item_key": key,
                "event_count": len(events),
                "event_refs": [e.source_event_ref for e in events],
                "earliest_observed_time": min(times),
                "sum_observed_times": sum(times),
                "purchase_time": _comparison(target, "purchase_time", key, sum(times), complete),
                "first_purchase_time": _comparison(
                    target, "first_purchase_time", key, min(times), complete
                ),
                "item_usage": _comparison(target, "item_usage", key, 1, complete),
            }
        )
    observed = {row["item_key"] for row in rows}
    orphan_keys = {
        field: sorted(key for key in target[field] if key not in observed)
        if isinstance(target.get(field), dict)
        else []
        for field in ("purchase_time", "first_purchase_time", "item_usage")
    }
    return {
        "schema_version": "purchase-semantics/1",
        "role_evidence": role,
        "aggregate_comparisons": rows,
        "aggregate_keys_without_valid_event": orphan_keys,
        "comparisons_complete_for_valid_log": complete,
        "inventory_log_status": "missing"
        if target.get("inventory_log") is None
        else ("present_unverified" if isinstance(target["inventory_log"], list) else "invalid"),
        "candidate_label_decisions": [
            {
                "item_key": key,
                "observed_event_count_all_match": len(grouped.get(key, [])),
                "completion_time_available": False,
                "negative_label_available": False,
                "reason": "Derived summaries do not verify completion, delivery or coverage.",
            }
            for key in candidate_items
        ],
        "independent_evidence": False,
        "training_allowed": False,
        "limitations": [
            "purchase_time is a time sum, not a first/last/completion timestamp.",
            "item_usage is a presence indicator derived from purchases, not active item_uses.",
            "Current source does not prove the deployed parser version for these matches.",
            "Final inventory and summaries cannot prove historical completion or absence.",
        ],
    }
