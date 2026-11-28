"""Reconcile observed objective cycles; censored samples never certify a timer."""

import math
from collections import Counter

from dota_items.data.patch_objectives import build_objective_observations


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _active(row):
    raw = row["raw_fields"]
    return (
        row["active"]
        and row.get("op") not in {"deleted", "left"}
        and raw.get("m_lifeState") == 0
        and raw.get("m_bIsWaitingToSpawn") is False
    )


def _duration(death, activation):
    bounds = [
        death["lower_game_time"],
        death["upper_game_time"],
        activation["lower_game_time"],
        activation["upper_game_time"],
    ]
    if not all(_number(v) for v in bounds):
        return None
    dl, du, al, au = bounds
    if dl > du or al > au or au < du:
        return None
    return {"lower_seconds": max(0.0, al - du), "upper_seconds": au - dl}


def _lifecycle_overlap(records, end_tick):
    """Include short-lived entities between frames; same-tick ordering is ambiguous."""
    intervals = []
    for record in records:
        start = None
        for row in record["observations"]:
            raw = row["raw_fields"]
            if _active(row) and start is None:
                start = row["tick"]
            elif (
                start is not None
                and row.get("op") not in {"left", "deleted"}
                and (
                    raw.get("m_bIsWaitingToSpawn") is True
                    or (type(raw.get("m_lifeState")) is int and raw["m_lifeState"] > 0)
                )
            ):
                intervals.append(
                    (start, row["tick"], (record["entity_index"], record["entity_serial"]))
                )
                start = None
        if start is not None:
            intervals.append((start, end_tick, (record["entity_index"], record["entity_serial"])))
    intervals.sort()
    return any(
        identity != other_identity and other_start <= end and start <= other_end
        for index, (start, end, identity) in enumerate(intervals)
        for other_start, other_end, other_identity in intervals[index + 1 :]
    )


def _pair_cycles(observation, frames, kind, singleton, records, end_tick):
    activations = observation["activation_observations"]
    deaths = sorted(observation["death_observations"], key=lambda r: r["upper_tick"])
    paired, unresolved, used = [], [], set()
    ambiguous = any(sum(_active(r) for r in f[kind]) > 1 for f in frames) or _lifecycle_overlap(
        records, end_tick
    )
    for i, death in enumerate(deaths):
        following = [
            (index, row)
            for index, row in enumerate(activations)
            if index not in used and row["upper_tick"] > death["upper_tick"]
        ]
        if not following:
            unresolved.append({"death": death, "reason": "right_censored_no_later_activation"})
            continue
        index, activation = min(following, key=lambda pair: pair[1]["upper_tick"])
        if i + 1 < len(deaths) and deaths[i + 1]["upper_tick"] < activation["upper_tick"]:
            unresolved.append({"death": death, "reason": "intervening_death_ambiguous"})
            continue
        same = death["entity"] == activation["entity"]
        gap = [f for f in frames if death["upper_tick"] < f["tick"] < activation["upper_tick"]]
        # Empty or explicit dead/waiting frames are evidence; unknown life is not absence.
        inactive = bool(gap) and all(
            not f[kind]
            or all(
                r["raw_fields"].get("m_bIsWaitingToSpawn") is True
                or (
                    type(r["raw_fields"].get("m_lifeState")) is int
                    and r["raw_fields"]["m_lifeState"] > 0
                )
                for r in f[kind]
            )
            for f in gap
        )
        if not same and (not singleton or ambiguous or not inactive):
            unresolved.append({"death": death, "reason": "replacement_identity_unproven"})
            continue
        if ambiguous:
            unresolved.append({"death": death, "reason": "simultaneous_live_objectives"})
            continue
        if any(_active(row) for frame in gap for row in frame[kind]):
            unresolved.append({"death": death, "reason": "live_frame_before_claimed_activation"})
            continue
        interval = _duration(death, activation)
        if interval is None:
            unresolved.append({"death": death, "reason": "unknown_or_inconsistent_time_bounds"})
            continue
        used.add(index)
        paired.append(
            {
                "death": death,
                "next_activation": activation,
                "duration_interval": interval,
                "association": "same_entity_identity"
                if same
                else "single_map_spawner_and_observed_inactive_gap",
                "inactive_frame_count": len(gap),
                "timer_rule_validated": False,
            }
        )
    return paired, unresolved


def analyze_objective_evidence(captures, *, map_documents, exact_patch, source_refs):
    if exact_patch != "7.42":
        raise ValueError("Exact 7.42 evidence required")
    entities = map_documents["mapdata.json"]["data"]
    counts = {
        "roshan": len(entities.get("npc_dota_roshan_spawner", [])),
        "tormentor": len(entities.get("npc_dota_miniboss_spawner", [])),
    }
    matches, seen = [], set()
    for capture in captures:
        if capture.get("schema") != "map-objective-evidence/1":
            raise ValueError("Objective evidence schema mismatch")
        if capture["match_id"] in seen:
            raise ValueError("Duplicate objective match")
        seen.add(capture["match_id"])
        runtime = {**capture, "schema": "map-runtime-capture/1"}
        observations = build_objective_observations(
            [runtime], exact_patch=exact_patch, source_refs=source_refs
        )["matches"][0]
        deaths = capture.get("combat_deaths")
        if not isinstance(deaths, list) or not isinstance(capture.get("chat_events"), list):
            raise ValueError("Missing independent objective event channels")
        for event in deaths:
            expected_name = {"roshan": "npc_dota_roshan", "tormentor": "npc_dota_miniboss"}
            if (
                event.get("kind") not in expected_name
                or event.get("target_name") != expected_name[event["kind"]]
                or type(event.get("delivery_tick")) is not int
                or not 0 <= event["delivery_tick"] <= capture["post_game_tick"]
                or type(event.get("will_reincarnate")) is not bool
                or any(
                    event.get(k) is not None and not _number(event[k])
                    for k in ("timestamp_s", "combat_game_time_s", "delivery_game_time")
                )
            ):
                raise ValueError("Invalid independent objective death evidence")
        objectives = {}
        for kind, observation in observations["objectives"].items():
            cycles, unresolved = _pair_cycles(
                observation,
                capture["objective_frames"],
                kind,
                counts[kind] == 1,
                [r for r in capture["objectives"] if r["kind"] == kind],
                capture["post_game_tick"],
            )
            events = [e for e in deaths if e["kind"] == kind and not e["will_reincarnate"]]
            n_deaths = len(observation["death_observations"])
            status = (
                "both_channels_observed_no_death"
                if not n_deaths and not events
                else "counts_agree_event_alignment_not_certified"
                if n_deaths == len(events)
                else "channel_disagreement_requires_review"
            )
            objectives[kind] = {
                "map_spawners": counts[kind],
                "entity_observations": observation,
                "combat_deaths": events,
                "death_channel_status": status,
                "observed_cycles": cycles,
                "unresolved_deaths": unresolved,
                "respawn_status": "observed_intervals" if cycles else "no_positive_sample",
                "timer_rule_validated": False,
            }
        matches.append(
            {
                "match_id": capture["match_id"],
                "game_build": capture["game_build"],
                "end_game_time": capture["sampling"]["end_game_time"],
                "objectives": objectives,
                "chat_type_counts": dict(Counter(str(e["type"]) for e in capture["chat_events"])),
                "message_coverage": capture["message_coverage"],
            }
        )
    return {
        "schema": "patch-objective-cycle-evidence/1",
        "patch": exact_patch,
        "source_refs": source_refs,
        "matches": matches,
        "training_allowed": False,
        "action_review_allowed": False,
        "limits": [
            "Combat delivery can lag event time; matching counts does not prove event alignment.",
            "Aegis pickups/chat hints are not death or respawn evidence.",
            "Cross-serial pairing needs one map spawner and an observed inactive interval.",
            "An observed interval does not prove the complete random/base respawn schedule.",
            "No positive sample is a coverage gap, not a disproved game mechanic.",
        ],
    }
