"""Versioned source-log observations, not ground-truth absence or training approval."""

import math


def observe_purchases(player, candidates, *, start=0, end=1800):
    if not 0 <= start < end or len(candidates) != len(set(candidates)):
        raise ValueError("Invalid window or duplicate candidates")
    log = player.get("purchase_log")
    present = isinstance(log, list)
    valid, invalid = [], []
    for index, event in enumerate(log if present else []):
        if (
            not isinstance(event, dict)
            or not isinstance(event.get("key"), str)
            or not event["key"]
            or type(event.get("time")) not in (int, float)
            or not math.isfinite(event["time"])
        ):
            invalid.append(index)
        else:
            valid.append((index, event["key"], event["time"]))
    usable = present and not invalid
    items = []
    for key in candidates:
        events = [
            (index, time) for index, name, time in valid if name == key and start <= time < end
        ]
        items.append(
            {
                "item_key": key,
                "event_refs": [f"purchase_log[{index}]" for index, _ in events],
                "event_times": [time for _, time in events],
                "log_presence": int(bool(events)) if usable else None,
                "log_presence_mask": usable,
                "behavior_label": None,
                "behavior_label_mask": False,
            }
        )
    return {
        "schema_version": "purchase-log-observation/1",
        "window": [start, end],
        "log_status": "invalid" if invalid else ("present" if present else "missing"),
        "invalid_event_indices": invalid,
        "valid_event_count": len(valid),
        "first_event_time": min((t for _, _, t in valid), default=None),
        "last_event_time": max((t for _, _, t in valid), default=None),
        "has_event_at_or_after_window_end": any(t >= end for _, _, t in valid),
        "coverage_verified": False,
        "training_allowed": False,
        "items": items,
    }
