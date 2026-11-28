"""Post-hoc camp association and boundary diagnostics over caller-verified captures.

No nearest-camp assignment, summon classification, player knowledge or timer rules
are inferred. Sparse neutral lifecycle states are not spatial occupancy samples.
"""

import copy
import math
import re
from collections import Counter

_INVALID_HANDLES = {0xFFFFFF, 0xFFFFFFFF}
_BOUNDARIES = (900.0, 1800.0)
_WINDOW = 60.0


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _identity(row):
    result = row.get("entity_index"), row.get("entity_serial")
    if any(type(value) is not int or value < 0 for value in result):
        raise ValueError("Invalid captured entity identity")
    return result


def _handle(value):
    if value is None:
        return "missing_handle_value", None
    if type(value) is not int:
        raise ValueError("Spawner handle must be an integer or missing")
    if value in _INVALID_HANDLES:
        return "invalid_handle_sentinel", None
    if value < 0 or value > 0xFFFFFFFF:
        return "handle_out_of_range", None
    return "encoded_entity_handle", (value & 16383, value >> 14)


def _association(row):
    result = row.get("spawner_identity")
    if result is None:
        return None
    _, decoded = _handle(row["raw_fields"].get("m_hNeutralSpawner"))
    if (
        not isinstance(result, list)
        or len(result) != 2
        or any(type(value) is not int or value < 0 for value in result)
        or tuple(result) != decoded
    ):
        raise ValueError("Resolved spawner contradicts original handle identity")
    return tuple(result)


def _state(row):
    if row["active"] is not True or row.get("op") in {"left", "deleted"}:
        return "inactive_or_disappeared"
    raw = row["raw_fields"]
    life, waiting = raw.get("m_lifeState"), raw.get("m_bIsWaitingToSpawn")
    if life is None or waiting is None:
        return "unknown_activation_state"
    if life > 0:
        return "non_alive"
    if waiting:
        return "waiting"
    return "alive" if life == 0 else "unknown_activation_state"


def _validate_captures(captures, match_ids, exact_patch):
    indexed = {}
    for capture in captures:
        mid = capture.get("match_id")
        if (
            capture.get("schema") not in {"map-runtime-capture/1", "map-objective-evidence/1"}
            or capture.get("patch") != exact_patch
            or type(mid) is not int
            or mid <= 0
            or mid in indexed
            or type(capture.get("game_build")) is not int
            or capture["game_build"] <= 0
            or type(capture.get("post_game_tick")) is not int
            or capture["post_game_tick"] < 0
            or capture.get("parse_error") is not None
            or capture.get("truncated_at_tick") is not None
            or capture.get("coordinate_space") != "world"
            or capture.get("omniscient") is not True
            or capture.get("training_allowed") is not False
            or not _number(capture.get("sampling", {}).get("end_game_time"))
        ):
            raise ValueError("Capture identity, purpose or completion mismatch")
        channels = {}
        for channel, kind in (("spawners", "spawner"), ("neutral_units", "neutral_unit")):
            if not isinstance(capture.get(channel), list):
                raise ValueError("Missing captured channel")
            records = {}
            for index, record in enumerate(capture[channel]):
                identity = _identity(record)
                if identity in records or record.get("kind") != kind:
                    raise ValueError("Duplicate or wrong-channel captured entity")
                rows = record.get("observations")
                if not isinstance(rows, list) or not rows:
                    raise ValueError("Captured observations required")
                last_tick = -1
                for row in rows:
                    if (
                        _identity(row) != identity
                        or type(row.get("tick")) is not int
                        or not last_tick <= row["tick"] <= capture["post_game_tick"]
                        or (row.get("game_time") is not None and not _number(row["game_time"]))
                        or type(row.get("active")) is not bool
                        or not isinstance(row.get("raw_fields"), dict)
                        or any(
                            row.get(axis) is not None and not _number(row[axis])
                            for axis in ("x", "y")
                        )
                    ):
                        raise ValueError("Invalid or unordered captured observation")
                    last_tick = row["tick"]
                    raw = row["raw_fields"]
                    for field in ("m_lifeState", "m_Type", "m_iCampType", "m_iTeamNum"):
                        if raw.get(field) is not None and type(raw[field]) is not int:
                            raise ValueError("Invalid integer lifecycle field")
                    waiting = raw.get("m_bIsWaitingToSpawn")
                    if waiting is not None and type(waiting) is not bool:
                        raise ValueError("Invalid waiting state")
                    _handle(raw.get("m_hNeutralSpawner"))
                    _association(row)
                records[identity] = {
                    "record": record,
                    "index": index,
                    "pointer": f"/{channel}/{index}",
                }
            channels[channel] = records
        indexed[mid] = {"capture": capture, **channels}
    if set(indexed) != set(match_ids):
        raise ValueError("Captured match coverage differs from camp assets")
    return indexed


def _geometry(camps, row):
    if any(not _number(row.get(axis)) for axis in ("x", "y")):
        return None
    return [
        camp["camp_id"]
        for camp in camps
        if camp["rectangle"]["min_x"] <= row["x"] <= camp["rectangle"]["max_x"]
        and camp["rectangle"]["min_y"] <= row["y"] <= camp["rectangle"]["max_y"]
    ]


def _spawner_geometry(camps, source):
    rows = source["record"]["observations"]
    memberships = [_geometry(camps, row) for row in rows]
    known = [value for value in memberships if value is not None]
    union = set(camp_id for value in known for camp_id in value)
    unique = len(union) == 1 and all(len(value) == 1 for value in known)
    status = (
        "unique_static_trigger"
        if unique
        else (
            "missing_spawner_coordinates"
            if not known
            else "static_trigger_not_unique"
            if any(len(value) > 1 for value in known)
            else "spawner_crosses_static_triggers"
            if len(union) > 1
            else "spawner_outside_static_triggers"
        )
    )
    return {
        "status": status,
        "camp_id": next(iter(union)) if unique else None,
        "record_pointer": source["pointer"],
        "observations": [
            {
                "pointer": f"{source['pointer']}/observations/{i}",
                "tick": row["tick"],
                "game_time": row["game_time"],
                "x": row.get("x"),
                "y": row.get("y"),
                "containing_camp_ids": memberships[i],
            }
            for i, row in enumerate(rows)
        ],
        "missing_coordinate_observations": len(memberships) - len(known),
    }


def _spawners(camps, indexed):
    result, declared = {}, {}
    for camp in camps:
        for row in camp["runtime_spawners"]:
            key = row["match_id"], tuple(row["identity"])
            if key in declared:
                raise ValueError("Ambiguous declared spawner ownership")
            declared[key] = camp["camp_id"], row["pointer"]
    for mid, capture in indexed.items():
        for identity, source in capture["spawners"].items():
            evidence = _spawner_geometry(camps, source)
            expected = (
                (evidence["camp_id"], source["pointer"])
                if evidence["camp_id"] is not None
                else None
            )
            if declared.get((mid, identity)) != expected:
                raise ValueError("Declared camp spawner differs from original trigger evidence")
            result[mid, identity] = evidence
    if set(declared) - set(result):
        raise ValueError("Declared spawner missing from capture")
    return result


def _validate_asset_observations(camps, indexed, spawners):
    declared_units = set()
    for camp in camps:
        for evidence in camp["runtime_spawners"]:
            source = indexed[evidence["match_id"]]["spawners"][tuple(evidence["identity"])]
            expected = [
                {
                    "tick": row["tick"],
                    "game_time": row["game_time"],
                    "fields": {
                        field: row["raw_fields"].get(field) for field in ("m_Type", "m_iCampType")
                    },
                    "pointer": f"{source['pointer']}/observations/{i}",
                }
                for i, row in enumerate(source["record"]["observations"])
            ]
            if evidence["raw_type_timeline"] != expected:
                raise ValueError("Derived spawner timeline differs from original capture")
        for batch in camp["activation_batches"]:
            mid, tick, time = batch["match_id"], batch["tick"], batch["game_time"]
            if mid not in indexed or type(tick) is not int or not _number(time):
                raise ValueError("Invalid derived activation batch identity/time")
            if not batch["units"]:
                raise ValueError("Empty derived activation batch")
            seen = set()
            for unit in batch["units"]:
                pointer = re.fullmatch(r"/neutral_units/(\d+)/observations/(\d+)", unit["pointer"])
                if pointer is None:
                    raise ValueError("Invalid activation observation pointer")
                try:
                    record = indexed[mid]["capture"]["neutral_units"][int(pointer[1])]
                    actual = record["observations"][int(pointer[2])]
                except (IndexError, KeyError, TypeError) as error:
                    raise ValueError("Activation pointer does not resolve") from error
                identity = _identity(actual)
                if (
                    identity in seen
                    or (mid, identity) in declared_units
                    or tuple(unit["entity"]) != identity
                    or _state(actual) != "alive"
                    or actual["tick"] != tick
                    or actual["game_time"] != time
                    or unit["game_time"] != time
                    or actual.get("npc_name") != unit.get("npc_name")
                    or spawners.get((mid, _association(actual)), {}).get("camp_id")
                    != camp["camp_id"]
                    or any(
                        _state(row) == "alive" for row in record["observations"][: int(pointer[2])]
                    )
                ):
                    raise ValueError("Derived activation batch differs from original capture")
                seen.add(identity)
                declared_units.add((mid, identity))
    actual_units = set()
    for mid, capture in indexed.items():
        for identity, source in capture["neutral_units"].items():
            first = next(
                (row for row in source["record"]["observations"] if _state(row) == "alive"), None
            )
            if first is not None and spawners.get((mid, _association(first)), {}).get("camp_id"):
                actual_units.add((mid, identity))
    if declared_units != actual_units:
        raise ValueError("Derived activation batches omit original linked active units")


def _unit_diagnostic(mid, identity, source, active_index, capture, spawners):
    row = source["record"]["observations"][active_index]
    raw = row["raw_fields"]
    handle_status, target = _handle(raw.get("m_hNeutralSpawner"))
    reason = handle_status if target is None else "referenced_spawner_not_captured"
    if "m_hNeutralSpawner" not in raw:
        reason = "handle_field_missing"
    target_record = capture["spawners"].get(target)
    target_geometry, target_state = None, None
    if target_record is not None:
        target_geometry = spawners[mid, target]
        prior = [r for r in target_record["record"]["observations"] if r["tick"] <= row["tick"]]
        target_state = (
            "not_yet_observed_at_activation"
            if not prior
            else (
                "inactive_or_disappeared"
                if prior[-1]["active"] is not True or prior[-1].get("op") in {"left", "deleted"}
                else "observed_active_entity"
            )
        )
        if target_geometry["camp_id"] is None:
            reason = "no_unique_static_trigger"
        elif row.get("spawner_identity") is None:
            reason = "handle_target_observed_but_unresolved"
        else:
            raise ValueError("A uniquely linked active unit is incorrectly declared unresolved")
    history = []
    for index, observed in enumerate(source["record"]["observations"]):
        fields = observed["raw_fields"]
        history.append(
            {
                "pointer": f"{source['pointer']}/observations/{index}",
                "tick": observed["tick"],
                "game_time": observed["game_time"],
                "state": _state(observed),
                "npc_name": observed.get("npc_name"),
                "npc_name_table": observed.get("npc_name_table"),
                "raw_handle": fields.get("m_hNeutralSpawner"),
                "resolved_spawner_identity": observed.get("spawner_identity"),
                "raw_team": fields.get("m_iTeamNum"),
                "raw_neutral_unit_type": fields.get("m_bIsNeutralUnitType"),
                "player_id_primary": observed.get("player_id_primary"),
                "player_id_secondary": observed.get("player_id_secondary"),
            }
        )
    return {
        "match_id": mid,
        "game_build": capture["capture"]["game_build"],
        "entity": list(identity),
        "reason": reason,
        "first_active_pointer": f"{source['pointer']}/observations/{active_index}",
        "first_active_tick": row["tick"],
        "first_active_game_time": row["game_time"],
        "npc_name": row.get("npc_name"),
        "npc_name_table": row.get("npc_name_table"),
        "handle_field_present": "m_hNeutralSpawner" in raw,
        "raw_handle": raw.get("m_hNeutralSpawner"),
        "handle_status": handle_status,
        "decoded_target": list(target) if target is not None else None,
        "resolved_spawner_identity": row.get("spawner_identity"),
        "same_index_other_serials": [
            list(key)
            for key in capture["spawners"]
            if target is not None and key[0] == target[0] and key != target
        ],
        "referenced_spawner_state_at_activation": target_state,
        "referenced_spawner_geometry": target_geometry,
        "identity_state_observations": history,
        "mechanistic_origin": {
            "status": "unproven",
            "summoned": None,
            "controlled": None,
            "owner_or_summoner": None,
            "missing_evidence": [
                "explicit_runtime_owner_or_summoner_link",
                "exact_creation_mechanism",
            ],
        },
        "disposition": "retain_unresolved_no_automatic_exclusion",
    }


def _snapshot(camp_id, mid, game_time, indexed, spawners):
    source = indexed[mid]
    end = source["capture"]["sampling"]["end_game_time"]
    if game_time > end:
        return {
            "query_game_time": game_time,
            "status": "beyond_replay_end",
            "lifecycle_state_counts": None,
            "observations": [],
        }
    observations, unknown_time = [], []
    for identity, unit in source["neutral_units"].items():
        rows = unit["record"]["observations"]
        relevant = any(
            spawners.get((mid, _association(row)), {}).get("camp_id") == camp_id for row in rows
        )
        if not relevant:
            continue
        prior = [
            (i, row)
            for i, row in enumerate(rows)
            if _number(row["game_time"]) and row["game_time"] <= game_time
        ]
        missing = [
            f"{unit['pointer']}/observations/{i}"
            for i, row in enumerate(rows)
            if row["game_time"] is None
        ]
        unknown_time.extend(missing)
        if not prior:
            continue
        index, row = prior[-1]
        linked = spawners.get((mid, _association(row)), {}).get("camp_id") == camp_id
        # A future association is not backfilled into an earlier unknown identity.
        earlier_link = any(
            spawners.get((mid, _association(r)), {}).get("camp_id") == camp_id for _, r in prior
        )
        if not linked and not earlier_link:
            continue
        uncertain_time = any(r["game_time"] is None for r in rows[index + 1 :])
        observations.append(
            {
                "entity": list(identity),
                "pointer": f"{unit['pointer']}/observations/{index}",
                "last_observed_tick": row["tick"],
                "last_observed_game_time": row["game_time"],
                "age_seconds": game_time - row["game_time"],
                "state": "unknown_boundary_state_time"
                if uncertain_time
                else (_state(row) if linked else "association_lost"),
                "npc_name": row.get("npc_name"),
                "npc_name_table": row.get("npc_name_table"),
                "association_identity": row.get("spawner_identity"),
            }
        )
    return {
        "query_game_time": game_time,
        "status": "last_observed_lifecycle_state_only",
        "lifecycle_state_counts": dict(Counter(row["state"] for row in observations)),
        "alive_name_counts": dict(
            Counter(
                row["npc_name"]
                for row in observations
                if row["state"] == "alive" and row["npc_name"]
            )
        ),
        "waiting_name_counts": dict(
            Counter(
                row["npc_name"]
                for row in observations
                if row["state"] == "waiting" and row["npc_name"]
            )
        ),
        "unknown_name_observations": sum(row["npc_name"] is None for row in observations),
        "unknown_time_pointers": unknown_time,
        "observations": observations,
        "continuous_occupancy_or_spawn_block_verified": False,
    }


def _boundaries(camps, semantics, indexed, spawners):
    reports = []
    originals = {camp["camp_id"]: camp for camp in camps}
    for semantic in semantics:
        if semantic.get("dynamic_composition_candidate") is not True:
            continue
        camp_id = semantic["camp_id"]
        camp = originals[camp_id]
        by_match = {}
        for evidence in camp["runtime_spawners"]:
            mid = evidence["match_id"]
            if mid in by_match:
                raise ValueError("Dynamic camp has multiple spawners in one replay")
            by_match[mid] = indexed[mid]["spawners"][tuple(evidence["identity"])]
        for mid, source in indexed.items():
            spawner = by_match.get(mid)
            rows = spawner["record"]["observations"] if spawner else []
            transitions = []
            for index in range(1, len(rows)):
                before, after = rows[index - 1], rows[index]
                old, new = before["raw_fields"].get("m_Type"), after["raw_fields"].get("m_Type")
                if old is not None and new is not None and old != new:
                    transitions.append(
                        {
                            "tick": after["tick"],
                            "game_time": after["game_time"],
                            "from_raw_type": old,
                            "to_raw_type": new,
                            "before_pointer": f"{spawner['pointer']}/observations/{index - 1}",
                            "after_pointer": f"{spawner['pointer']}/observations/{index}",
                        }
                    )
            end = source["capture"]["sampling"]["end_game_time"]
            for boundary in _BOUNDARIES:
                start, stop = boundary - _WINDOW, boundary + _WINDOW
                seen = [
                    r
                    for r in transitions
                    if _number(r["game_time"]) and start <= r["game_time"] <= stop
                ]
                coverage = (
                    "not_reached"
                    if end < start
                    else ("right_censored" if end < stop else "window_reached")
                )
                unknown_time = [i for i, row in enumerate(rows) if row["game_time"] is None]
                prior = [r for r in rows if _number(r["game_time"]) and r["game_time"] <= start]
                unknown_type = any(
                    row["raw_fields"].get("m_Type") is None
                    for row in rows
                    if row["game_time"] is None or start <= row["game_time"] <= min(stop, end)
                ) or (prior and prior[-1]["raw_fields"].get("m_Type") is None)
                raw_status = (
                    "transition_observed"
                    if seen
                    else (
                        "window_not_reached"
                        if coverage == "not_reached"
                        else "insufficient_spawner_observation"
                        if not prior or unknown_time or unknown_type
                        else "no_transition_observed_in_window"
                        if coverage == "window_reached"
                        else "window_not_fully_observed"
                    )
                )
                batches = []
                for index, batch in enumerate(camp["activation_batches"]):
                    if batch["match_id"] != mid or not _number(batch["game_time"]):
                        continue
                    if start <= batch["game_time"] <= min(stop, end):
                        batches.append(
                            {
                                "pointer": f"/camps/{camps.index(camp)}/activation_batches/{index}",
                                "tick": batch["tick"],
                                "game_time": batch["game_time"],
                                "unit_count": len(batch["units"]),
                                "name_counts": dict(
                                    Counter(u["npc_name"] for u in batch["units"] if u["npc_name"])
                                ),
                                "unknown_name_count": sum(
                                    u["npc_name"] is None for u in batch["units"]
                                ),
                                "complete_spawn_verified": False,
                            }
                        )
                reports.append(
                    {
                        "camp_id": camp_id,
                        "match_id": mid,
                        "game_build": source["capture"]["game_build"],
                        "boundary_seconds": boundary,
                        "window_start": start,
                        "window_end": stop,
                        "replay_end_game_time": end,
                        "window_coverage": coverage,
                        "raw_transition_status": raw_status,
                        "raw_transitions": seen,
                        "spawner_unknown_time_observations": unknown_time,
                        "before": _snapshot(camp_id, mid, boundary - 1, indexed, spawners),
                        "after": _snapshot(camp_id, mid, boundary + 1, indexed, spawners),
                        "activation_batches_in_window": batches,
                        "cause_status": "unproven",
                        "spawn_blocked": None,
                        "permanent_stage_rule_verified": False,
                        "player_prior_knowledge": False,
                    }
                )
    return reports


def build_camp_diagnostics(
    camp_assets, camp_semantics, runtime_captures, *, exact_patch, source_refs
):
    """Diagnose original unresolved records and fixed ±60s post-hoc boundary windows.

    The caller verifies file hashes, source receipts and authorized match scope.
    Both runtime and objective evidence captures are supported without schema rewriting.
    """
    if (
        exact_patch != "7.42"
        or camp_assets.get("schema") != "patch-camp-assets/1"
        or camp_semantics.get("schema") != "patch-camp-semantics/1"
        or any(
            doc.get("exact_patch") != exact_patch
            or doc.get("training_allowed") is not False
            or doc.get("action_review_allowed") is not False
            for doc in (camp_assets, camp_semantics)
        )
        or not isinstance(source_refs, dict)
        or not source_refs
    ):
        raise ValueError("Exact candidate patch assets and explicit source references required")
    camps = camp_assets.get("camps")
    match_ids = camp_assets.get("match_ids")
    if not isinstance(camps, list) or not camps or not isinstance(match_ids, list) or not match_ids:
        raise ValueError("Camp and match coverage required")
    if len(set(match_ids)) != len(match_ids) or camp_semantics.get("match_ids") != match_ids:
        raise ValueError("Camp/semantic match coverage mismatch")
    ids = [camp["camp_id"] for camp in camps]
    semantic_ids = [camp["camp_id"] for camp in camp_semantics["camps"]]
    if (
        len(set(ids)) != len(ids)
        or len(set(semantic_ids)) != len(semantic_ids)
        or set(semantic_ids) != set(ids)
        or any(not isinstance(value, str) or not value for value in ids)
    ):
        raise ValueError("Camp/semantic identities differ")
    for camp in camps:
        rectangle = camp["rectangle"]
        if (
            set(rectangle) != {"min_x", "max_x", "min_y", "max_y"}
            or any(not _number(value) for value in rectangle.values())
            or any(rectangle[f"min_{axis}"] >= rectangle[f"max_{axis}"] for axis in ("x", "y"))
        ):
            raise ValueError("Invalid static camp rectangle")
    indexed = _validate_captures(runtime_captures, match_ids, exact_patch)
    spawners = _spawners(camps, indexed)
    _validate_asset_observations(camps, indexed, spawners)
    declared = {}
    for index, row in enumerate(camp_assets["unresolved_associations"]):
        key = row["match_id"], tuple(row.get("unit", row.get("spawner", [])))
        tag = "unit" if "unit" in row else "spawner"
        if (tag, key) in declared:
            raise ValueError("Duplicate unresolved association")
        declared[tag, key] = index
    found, diagnostics = set(), []
    for mid, capture in indexed.items():
        for identity, source in capture["neutral_units"].items():
            first = next(
                (
                    i
                    for i, row in enumerate(source["record"]["observations"])
                    if _state(row) == "alive"
                ),
                None,
            )
            if first is None:
                continue
            row = source["record"]["observations"][first]
            linked = spawners.get((mid, _association(row)), {}).get("camp_id")
            if linked is not None:
                continue
            key = "unit", (mid, identity)
            if key not in declared:
                raise ValueError("Original unresolved active unit is omitted from camp assets")
            found.add(key)
            diagnosis = _unit_diagnostic(mid, identity, source, first, capture, spawners)
            diagnosis["camp_asset_pointer"] = f"/unresolved_associations/{declared[key]}"
            diagnostics.append(diagnosis)
    spawner_diagnostics = []
    for (mid, identity), evidence in spawners.items():
        if evidence["camp_id"] is None:
            key = "spawner", (mid, identity)
            if key not in declared:
                raise ValueError("Unresolved spawner omitted from camp assets")
            found.add(key)
            spawner_diagnostics.append(
                {
                    "match_id": mid,
                    "identity": list(identity),
                    **evidence,
                    "camp_asset_pointer": f"/unresolved_associations/{declared[key]}",
                }
            )
    if set(declared) != found:
        raise ValueError("Declared unresolved evidence does not match original captures")
    boundaries = _boundaries(camps, camp_semantics["camps"], indexed, spawners)
    return {
        "schema": "patch-camp-diagnostics/1",
        "exact_patch": exact_patch,
        "status": "posthoc_candidate_diagnostics",
        "source_refs": copy.deepcopy(source_refs),
        "match_ids": list(match_ids),
        "unresolved_unit_diagnostics": diagnostics,
        "unresolved_spawner_diagnostics": spawner_diagnostics,
        "dynamic_boundary_diagnostics": boundaries,
        "summary": {
            "unresolved_active_units": len(diagnostics),
            "association_reasons": dict(Counter(row["reason"] for row in diagnostics)),
            "unit_names": dict(Counter(row["npc_name"] or "<missing>" for row in diagnostics)),
            "unresolved_spawners": len(spawner_diagnostics),
            "boundary_windows": len(boundaries),
            "raw_transition_statuses": dict(
                Counter(row["raw_transition_status"] for row in boundaries)
            ),
            "confirmed_creation_mechanisms": 0,
            "automatically_excluded_units": 0,
        },
        "policy": {
            "window_radius_seconds": _WINDOW,
            "state_offsets_seconds": [-1.0, 1.0],
            "snapshot_basis": "last observed lifecycle state, not sampled physical occupancy",
        },
        "training_allowed": False,
        "action_review_allowed": False,
        "player_prior_knowledge": False,
        "limits": [
            "Invalid handles explain failed direct association, not an invalid or illegal unit.",
            "Names, teams and neutral-type flags do not prove creation or control mechanisms.",
            "No nearby camp assignment or automatic exclusion is performed.",
            "Sparse lifecycle coordinates and carried states do not prove occupancy or blocking.",
            "Changes, missing observations and unproven causes remain separate.",
            "Boundary observations are post-hoc omniscient evidence, not player prior knowledge.",
        ],
    }
