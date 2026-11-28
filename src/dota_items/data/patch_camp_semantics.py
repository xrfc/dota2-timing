"""Current camp-origin evidence and explicitly historical amphibian composition candidates.

Pure computation over caller-verified inputs. Historical labels never become current
patch approvals, and a captured activation cohort is not proof of a complete respawn.
"""

import copy
import json
import math
import re
from collections import Counter

_ORIGIN_NOTE = "Hill Troll (from Dark Troll camp) renamed to Dark Troll Trapper"
_HISTORY_PREFIX = "DOTA_Patch_7_38_Flooded_Camps_"
_HISTORY = {
    "8": "Every 5 minutes one of the creeps in that camp will be forever upgraded to a next tier",
    "9": (
        "Each camp consists of 3 units. As a result, at 15:00 Easy camp completely turns into a "
        "Medium camp, and both Medium camps will become Hard ones. At 30:00 Medium camp will "
        "become a Hard one, and both Hard camps will evolve to Ancient ones"
    ),
    "10": (
        "Each creep can only be upgraded twice, meaning an Easy camp will never reach an "
        "Ancient status (sorry, Pollywogs)"
    ),
    "11": (
        "Units are not upgraded if the camp is blocked. Amount of upgraded units can't be "
        "increased, so if there is only 1 Ancient creep, attempting to stack that camp will "
        "not create another Ancient creep"
    ),
    "13": "Easy camp is three Pollywogs",
    "14": "Medium camp is two Boglets and a Marshmage Apprentice",
    "15": "Hard camp is two Croakers and a Marshmage",
    "16": "Ancient camp is two Ancient Croakers and an Ancient Marshmage",
}
_UNITS = {
    "npc_dota_neutral_tadpole": ("Pollywog", "easy"),
    "npc_dota_neutral_froglet": ("Boglet", "medium"),
    "npc_dota_neutral_froglet_mage": ("Marshmage Apprentice", "medium"),
    "npc_dota_neutral_grown_frog": ("Croaker", "hard"),
    "npc_dota_neutral_grown_frog_mage": ("Marshmage", "hard"),
    "npc_dota_neutral_ancient_frog": ("Ancient Croaker", "ancient"),
    "npc_dota_neutral_ancient_frog_mage": ("Ancient Marshmage", "ancient"),
}
_COMPOSITIONS = {
    "easy": {"npc_dota_neutral_tadpole": 3},
    "medium": {"npc_dota_neutral_froglet": 2, "npc_dota_neutral_froglet_mage": 1},
    "hard": {"npc_dota_neutral_grown_frog": 2, "npc_dota_neutral_grown_frog_mage": 1},
    "ancient": {"npc_dota_neutral_ancient_frog": 2, "npc_dota_neutral_ancient_frog_mage": 1},
}
_LABELS = {"easy": "small", "medium": "medium", "hard": "large", "ancient": "ancient"}
_KEY_VALUE = re.compile(r'^\s*"([^"\\]+)"\s*("(?:\\.|[^"\\])*")\s*(?://.*)?$')


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _identity(row):
    key = row.get("entity_index"), row.get("entity_serial")
    if any(type(value) is not int or value < 0 for value in key):
        raise ValueError("Invalid runtime identity")
    return key


def _flat_evidence(text, wanted):
    if not isinstance(text, str):
        raise ValueError("Fixed source text required")
    found = {}
    for line, content in enumerate(text.splitlines(), 1):
        match = _KEY_VALUE.fullmatch(content)
        if match is None or match[1] not in wanted:
            continue
        key = match[1]
        if key in found:
            raise ValueError("Duplicate requested source token")
        found[key] = {"value": json.loads(match[2]), "line": line, "key": key}
    return found


def _historical_evidence(history_text, localization_text):
    notes = _flat_evidence(history_text, {_HISTORY_PREFIX + key for key in _HISTORY})
    names = _flat_evidence(localization_text, set(_UNITS))
    accepted = {
        key: notes[_HISTORY_PREFIX + key]
        for key, expected in _HISTORY.items()
        if notes.get(_HISTORY_PREFIX + key, {}).get("value", "").strip() == expected
    }
    units = {
        key: {**names[key], "historical_tier": tier}
        for key, (name, tier) in _UNITS.items()
        if names.get(key, {}).get("value") == name
    }
    return accepted, units


def _origin_evidence(notes):
    rows = notes.get("neutral_creeps", [])
    if len(rows) < 16:
        return None
    unit = rows[15]
    general = rows[0].get("neutral_creep_notes", [])
    origins = unit.get("neutral_creep_notes", [])
    if (
        unit.get("name") != "npc_dota_neutral_dark_troll"
        or unit.get("localized_name") != "Dark Troll Trapper"
        or not origins
        or origins[0].get("note") != _ORIGIN_NOTE
        or len(general) < 15
        or general[14].get("note")
        != ("Large camps: Large Satyr camp; Hellbear camp; Dark Troll camp")
    ):
        return None
    return {
        "npc_name": unit["name"],
        "type": "large",
        "source_patch": "7.42",
        "method": "explicit_unit_origin_then_official_camp_class",
        "unit_pointer": "/neutral_creeps/15",
        "origin_pointer": "/neutral_creeps/15/neutral_creep_notes/0",
        "classification_pointer": "/neutral_creeps/0/neutral_creep_notes/14",
    }


def _alive(row):
    raw = row["raw_fields"]
    return (
        row["active"] is True
        and row.get("op") not in ("left", "deleted")
        and type(raw.get("m_lifeState")) is int
        and raw["m_lifeState"] == 0
        and raw.get("m_bIsWaitingToSpawn") is False
    )


def _association(row):
    value = row.get("spawner_identity")
    if value is None:
        return None
    raw = row["raw_fields"].get("m_hNeutralSpawner")
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(type(v) is not int or v < 0 for v in value)
        or type(raw) is not int
        or raw < 0
        or raw in (0xFFFFFF, 0xFFFFFFFF)
        or value != [raw & ((1 << 14) - 1), raw >> 14]
    ):
        raise ValueError("Resolved spawner differs from original handle")
    return tuple(value)


def _capture_index(captures, match_ids):
    output = {}
    for cap in captures:
        mid = cap.get("match_id")
        if (
            type(mid) is not int
            or mid not in match_ids
            or mid in output
            or cap.get("schema") != "map-runtime-capture/1"
            or cap.get("patch") != "7.42"
            or cap.get("training_allowed") is not False
            or cap.get("omniscient") is not True
            or cap.get("coordinate_space") != "world"
            or cap.get("parse_error") is not None
            or cap.get("truncated_at_tick") is not None
            or type(cap.get("post_game_tick")) is not int
            or cap["post_game_tick"] < 0
            or type(cap.get("game_build")) is not int
            or cap["game_build"] <= 0
        ):
            raise ValueError("Runtime capture identity, purpose or completeness mismatch")
        records, first, ambiguous = {}, {}, []
        for channel in ("spawners", "neutral_units"):
            if not isinstance(cap.get(channel), list):
                raise ValueError("Missing runtime entity channel")
            for index, record in enumerate(cap[channel]):
                identity = _identity(record)
                if channel == "neutral_units" and identity in records:
                    raise ValueError("Duplicate neutral entity identity")
                rows = record.get("observations")
                if not isinstance(rows, list) or not rows:
                    raise ValueError("Missing runtime observations")
                previous = -1
                for row in rows:
                    if (
                        _identity(row) != identity
                        or type(row.get("tick")) is not int
                        or not previous <= row["tick"] <= cap["post_game_tick"]
                        or (row.get("game_time") is not None and not _finite(row["game_time"]))
                        or not isinstance(row.get("raw_fields"), dict)
                        or type(row.get("active")) is not bool
                    ):
                        raise ValueError("Invalid runtime observation")
                    previous = row["tick"]
                    raw = row["raw_fields"]
                    if (
                        (raw.get("m_lifeState") is not None and type(raw["m_lifeState"]) is not int)
                        or (
                            raw.get("m_bIsWaitingToSpawn") is not None
                            and type(raw["m_bIsWaitingToSpawn"]) is not bool
                        )
                        or (
                            row.get("npc_name") is not None and not isinstance(row["npc_name"], str)
                        )
                    ):
                        raise ValueError("Invalid runtime life, waiting or name field")
                    _association(row)
                if channel == "neutral_units":
                    records[identity] = (index, record)
                    active = next(((i, r) for i, r in enumerate(rows) if _alive(r)), None)
                    if active is not None:
                        first[identity] = active
                        if _association(active[1]) is None:
                            ambiguous.append(active[1])
        output[mid] = {
            "capture": cap,
            "records": records,
            "first": first,
            "unassociated_activations": ambiguous,
        }
    if set(output) != set(match_ids):
        raise ValueError("Every declared replay requires its runtime capture")
    return output


def _resolve(row, pointer, capture):
    match = re.fullmatch(r"/(spawners|neutral_units)/(\d+)/observations/(\d+)", pointer or "")
    if match is None:
        raise ValueError("Invalid runtime observation pointer")
    try:
        record = capture[match[1]][int(match[2])]
        observation = record["observations"][int(match[3])]
    except (IndexError, KeyError, TypeError) as error:
        raise ValueError("Runtime pointer does not resolve") from error
    if row is not None and tuple(row["entity"]) != _identity(observation):
        raise ValueError("Runtime pointer identifies another unit")
    return record, observation, int(match[3])


def _spawner_links(camp, capture_index):
    links, transitions, states = {}, [], []
    for evidence in camp["runtime_spawners"]:
        mid = evidence["match_id"]
        cap = capture_index[mid]["capture"]
        identity = tuple(evidence["identity"])
        if mid in links:
            raise ValueError("Ambiguous spawner identity for one camp and replay")
        links[mid] = identity
        previous, previous_tick = None, -1
        for row in evidence["raw_type_timeline"]:
            _, actual, _ = _resolve(None, row["pointer"], cap)
            if (
                not row["pointer"].startswith("/spawners/")
                or _identity(actual) != identity
                or row["tick"] != actual["tick"]
                or row["game_time"] != actual["game_time"]
                or any(actual["raw_fields"].get(k) != v for k, v in row["fields"].items())
                or "m_Type" not in row["fields"]
                or row["tick"] < previous_tick
            ):
                raise ValueError("Spawner timeline differs from original capture")
            value = row["fields"].get("m_Type")
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("Invalid raw spawner type")
            states.append(
                {
                    "match_id": mid,
                    "game_build": cap["game_build"],
                    "identity": list(identity),
                    "tick": row["tick"],
                    "game_time": row["game_time"],
                    "raw_type": value,
                    "pointer": row["pointer"],
                }
            )
            if previous is not None and value is not None and value != previous:
                transitions.append(
                    {
                        "match_id": mid,
                        "tick": row["tick"],
                        "game_time": row["game_time"],
                        "from_raw_type": previous,
                        "to_raw_type": value,
                        "pointer": row["pointer"],
                        "offset_from_historical_15m_seconds": row["game_time"] - 900
                        if _finite(row["game_time"])
                        else None,
                        "type_enum_interpretation_verified": False,
                    }
                )
            previous, previous_tick = value, row["tick"]
    return links, transitions, states


def _calibrate_types(camps, captures):
    """Crosscheck current direct candidates by distinct camp within each exact build."""
    calibrations = []
    for build in sorted({source["capture"]["game_build"] for source in captures.values()}):
        anchors = [
            {
                "camp_id": camp["camp_id"],
                "type_candidate": camp["current_patch_type_candidate"],
                "source_camp_pointer": camp["source_camp_pointer"],
                "type_evidence_pointer": f"/camps/{i}/direct_origin_evidence"
                if camp["direct_origin_evidence"]
                else camp["source_camp_pointer"] + "/type_evidence",
                "type_evidence_document": "camp_semantics"
                if camp["direct_origin_evidence"]
                else "camp_assets",
                **state,
            }
            for i, camp in enumerate(camps)
            if camp["current_patch_type_candidate"] is not None
            for state in camp["raw_type_observations"]
            if state["game_build"] == build and state["raw_type"] is not None
        ]
        values = []
        for raw_type in sorted({row["raw_type"] for row in anchors}):
            rows = [row for row in anchors if row["raw_type"] == raw_type]
            labels = sorted({row["type_candidate"] for row in rows})
            camp_ids = sorted({row["camp_id"] for row in rows})
            # An anchor label spanning raw values is also ambiguous, even if each
            # value has only that label. Never launder a dynamic camp as an enum anchor.
            inverse_conflict = any(
                len({row["raw_type"] for row in anchors if row["type_candidate"] == label}) > 1
                for label in labels
            )
            status = (
                "conflicting_anchor_evidence"
                if len(labels) != 1 or inverse_conflict
                else (
                    "insufficient_distinct_anchor_camps"
                    if len(camp_ids) < 2
                    else "empirical_candidate_with_camp_crosscheck"
                )
            )
            checks = []
            for camp_id in camp_ids:
                others = [row for row in rows if row["camp_id"] != camp_id]
                other_labels = {row["type_candidate"] for row in others}
                own_labels = {row["type_candidate"] for row in rows if row["camp_id"] == camp_id}
                prediction = next(iter(other_labels)) if len(other_labels) == 1 else None
                checks.append(
                    {
                        "excluded_camp_id": camp_id,
                        "remaining_distinct_anchor_camps": len({row["camp_id"] for row in others}),
                        "prediction": prediction,
                        "agrees_with_excluded_camp": prediction is not None
                        and own_labels == {prediction},
                    }
                )
            values.append(
                {
                    "raw_type": raw_type,
                    "status": status,
                    "type_candidate": labels[0]
                    if status == "empirical_candidate_with_camp_crosscheck"
                    else None,
                    "distinct_anchor_camps": len(camp_ids),
                    "camp_ids": camp_ids,
                    "observation_count": len(rows),
                    "anchor_evidence": rows,
                    "leave_one_camp_out": checks,
                }
            )
        calibrations.append(
            {
                "exact_patch": "7.42",
                "game_build": build,
                "values": values,
                "distinct_anchor_camps": len({row["camp_id"] for row in anchors}),
                "authoritative_enum": False,
                "user_approved": False,
                "minimum_distinct_anchor_camps": 2,
                "scope": "current_direct_candidates_same_patch_and_build_only",
            }
        )
    by_build = {row["game_build"]: (i, row) for i, row in enumerate(calibrations)}
    for camp in camps:
        empirical = []
        for state in camp["raw_type_observations"]:
            ci, calibration = by_build[state["game_build"]]
            found = next(
                (
                    (i, row)
                    for i, row in enumerate(calibration["values"])
                    if row["raw_type"] == state["raw_type"]
                ),
                None,
            )
            index, mapping = found if found is not None else (None, {})
            empirical.append(
                {
                    **state,
                    "empirical_type_candidate": mapping.get("type_candidate"),
                    "status": mapping.get("status", "unknown_value_for_build"),
                    "calibration_pointer": f"/observed_enum_calibration/{ci}/values/{index}"
                    if index is not None
                    else None,
                    "composition_or_permanent_type_verified": False,
                }
            )
        camp["empirical_type_timeline"] = empirical
    return calibrations


def _cohort(camp, batch, batch_index, captures, links):
    mid, tick, time = batch["match_id"], batch["tick"], batch["game_time"]
    source = captures[mid]
    if type(tick) is not int or not _finite(time) or mid not in links:
        raise ValueError("Invalid camp activation batch")
    expected = links[mid]
    units, reasons, seen = [], [], set()
    for unit in batch["units"]:
        record, actual, index = _resolve(unit, unit["pointer"], source["capture"])
        identity = _identity(actual)
        if identity in seen:
            raise ValueError("Repeated entity in an activation batch")
        seen.add(identity)
        if (
            not unit["pointer"].startswith("/neutral_units/")
            or not _alive(actual)
            or _association(actual) != expected
            or actual["tick"] != tick
            or actual["game_time"] != time
            or unit.get("game_time") != time
            or actual.get("npc_name") != unit.get("npc_name")
            or actual.get("npc_name_table") != "UnitNames"
            or source["first"].get(identity, (None,))[0] != index
        ):
            raise ValueError("Activation batch differs from original alive association")
        prior = record["observations"][index - 1] if index else None
        waiting = (
            prior is not None
            and prior["raw_fields"].get("m_bIsWaitingToSpawn") is True
            and prior["raw_fields"].get("m_lifeState") == 0
            and prior["active"] is True
            and prior.get("op") not in ("left", "deleted")
            and _association(prior) == expected
            and type(record.get("created_tick")) is int
            and record["created_tick"] <= prior["tick"] < tick
        )
        if not waiting or unit.get("left_censored") is not False:
            reasons.append("missing_observed_precreation_waiting_to_active_transition")
        if waiting and (
            unit.get("last_waiting_tick") != prior["tick"]
            or unit.get("last_waiting_game_time") != prior["game_time"]
        ):
            raise ValueError("Claimed prior waiting state differs from capture")
        units.append(
            {
                "entity": list(identity),
                "npc_name": unit["npc_name"],
                "pointer": unit["pointer"],
                "waiting_to_active_observed": bool(waiting),
            }
        )
        if unit["npc_name"] is None:
            reasons.append("missing_unit_name")
    original = {
        identity
        for identity, (_, row) in source["first"].items()
        if row["tick"] == tick and _association(row) == expected
    }
    if seen != original:
        reasons.append("activation_batch_omits_or_adds_original_entities")
    if len(units) != 3:
        reasons.append("not_three_distinct_observed_activations")
    same_second = [
        row
        for _, row in source["first"].values()
        if _association(row) == expected
        and _finite(row["game_time"])
        and math.floor(row["game_time"]) == math.floor(time)
    ]
    if len({row["tick"] for row in same_second}) != 1:
        reasons.append("same_second_activations_span_multiple_raw_ticks")
    if any(
        _finite(row["game_time"]) and math.floor(row["game_time"]) == math.floor(time)
        for row in source["unassociated_activations"]
    ):
        reasons.append("unassociated_activation_in_same_game_second")
    for identity, (_, record) in source["records"].items():
        if identity in seen:
            continue
        prior = [row for row in record["observations"] if row["tick"] < tick]
        if not prior or _association(prior[-1]) != expected:
            continue
        last = prior[-1]
        if _alive(last):
            reasons.append("preexisting_live_units_or_same_tick_clear_order_unknown")
        elif last["raw_fields"].get("m_lifeState") is None or (
            last["raw_fields"].get("m_bIsWaitingToSpawn") is None
        ):
            reasons.append("preexisting_unit_activation_state_unknown")
    return {
        "match_id": mid,
        "tick": tick,
        "game_time": time,
        "units": units,
        "camp_asset_pointer": f"/camps/{camp['_index']}/activation_batches/{batch_index}",
        "composition": dict(
            sorted(
                Counter(unit["npc_name"] for unit in units if unit["npc_name"] is not None).items()
            )
        ),
        "unknown_name_count": sum(unit["npc_name"] is None for unit in units),
        "cohort_status": "fully_observed_activation_cohort"
        if not reasons
        else "incomplete_or_ambiguous",
        "limitations": sorted(set(reasons)),
        "spawn_completeness_verified": False,
    }


def _classify_composition(cohort, history, units):
    result = {
        **cohort,
        "historical_tier_candidate": None,
        "normalized_type_candidate": None,
        "historical_status": "historical_unverified_for_patch",
        "tier_counts": {},
        "historical_composition_pointer": None,
    }
    counts = cohort["composition"]
    if cohort["unknown_name_count"] or not counts or not set(counts) <= units.keys():
        result["composition_status"] = "unknown_unit_or_localization"
        return result
    result["tier_counts"] = dict(
        Counter(
            {
                tier: sum(n for name, n in counts.items() if units[name]["historical_tier"] == tier)
                for tier in sorted({units[name]["historical_tier"] for name in counts})
            }
        )
    )
    if cohort["cohort_status"] != "fully_observed_activation_cohort":
        result["composition_status"] = "insufficient_cohort_evidence"
        return result
    for tier, expected in _COMPOSITIONS.items():
        key = str(13 + list(_COMPOSITIONS).index(tier))
        if counts == expected and key in history:
            result.update(
                composition_status="matches_historical_complete_composition",
                historical_tier_candidate=tier,
                normalized_type_candidate=_LABELS[tier],
                historical_composition_pointer=history[key],
            )
            return result
    result["composition_status"] = (
        "mixed_historical_tiers" if len(result["tier_counts"]) > 1 else ("unrecognized_composition")
    )
    return result


def build_camp_semantics(
    camp_assets,
    runtime_captures,
    official_notes,
    historical_patchnotes_text,
    localization_text,
    *,
    exact_patch,
    source_refs,
):
    """Add direct 7.42 origin evidence and historical, sample-bounded dynamic descriptions.

    ``source_refs`` is a nonempty caller-verified provenance object. Input hashes,
    holdout exclusion and replay receipt verification belong to the outer producer.
    """
    if (
        exact_patch != "7.42"
        or camp_assets.get("exact_patch") != exact_patch
        or camp_assets.get("schema") != "patch-camp-assets/1"
        or camp_assets.get("training_allowed") is not False
        or camp_assets.get("action_review_allowed") is not False
        or official_notes.get("patch_number") != exact_patch
        or official_notes.get("patch_name") != exact_patch
        or official_notes.get("success") is not True
        or not isinstance(source_refs, dict)
        or not source_refs
    ):
        raise ValueError("Expected verified candidate inputs for exact patch 7.42")
    original = camp_assets.get("camps")
    if not isinstance(original, list) or not original:
        raise ValueError("Camp assets required")
    ids = [camp.get("camp_id") for camp in original]
    if any(not isinstance(key, str) or not key for key in ids) or len(set(ids)) != len(ids):
        raise ValueError("Camp identities must be unique")
    match_ids = camp_assets.get("match_ids")
    if not isinstance(match_ids, list) or len(set(match_ids)) != len(match_ids):
        raise ValueError("Unique replay identities required")
    captures = _capture_index(runtime_captures, match_ids)
    history, localization = _historical_evidence(historical_patchnotes_text, localization_text)
    origin = _origin_evidence(official_notes)
    camps, claimed_spawners = [], set()
    for ci, original_camp in enumerate(original):
        camp = {**original_camp, "_index": ci}
        links, transitions, states = _spawner_links(camp, captures)
        for mid, identity in links.items():
            if (mid, identity) in claimed_spawners:
                raise ValueError("One replay spawner cannot identify two camps")
            claimed_spawners.add((mid, identity))
        observations, origin_matches = [], []
        for bi, batch in enumerate(camp["activation_batches"]):
            cohort = _cohort(camp, batch, bi, captures, links)
            if origin is not None:
                origin_matches.extend(
                    {
                        "match_id": cohort["match_id"],
                        "tick": cohort["tick"],
                        "game_time": cohort["game_time"],
                        **unit,
                    }
                    for unit in cohort["units"]
                    if unit["npc_name"] == origin["npc_name"] and unit["waiting_to_active_observed"]
                )
            if set(cohort["composition"]) & _UNITS.keys():
                observations.append(_classify_composition(cohort, history, localization))
        prior_type = camp.get("type")
        if prior_type is not None and prior_type not in {"small", "medium", "large", "ancient"}:
            raise ValueError("Unsupported source camp type")
        direct_type = "large" if origin_matches else None
        conflict = bool(prior_type and direct_type and prior_type != direct_type)
        current_type = None if conflict else prior_type or direct_type
        early = {
            row["historical_tier_candidate"]
            for row in observations
            if 0 <= row["game_time"] < 300 and row["historical_tier_candidate"] is not None
        }
        complete_compositions = {
            tuple(row["composition"].items())
            for row in observations
            if row["cohort_status"] == "fully_observed_activation_cohort"
        }
        dynamic = bool(transitions and len(complete_compositions) > 1)
        camps.append(
            {
                "camp_id": camp["camp_id"],
                "current_patch_type_candidate": current_type,
                "current_patch_type_status": "conflicting_direct_evidence"
                if conflict
                else (
                    "new_direct_official_origin_candidate"
                    if direct_type and not prior_type
                    else "existing_direct_candidate"
                    if prior_type
                    else "unknown"
                ),
                "source_camp_pointer": f"/camps/{ci}",
                "direct_origin_evidence": {**origin, "observations": origin_matches}
                if origin_matches
                else None,
                "dynamic_composition_candidate": dynamic,
                "historical_initial_tier_candidate": next(iter(early)) if len(early) == 1 else None,
                "historical_status": "historical_unverified_for_patch" if observations else None,
                "historical_composition_observations": observations,
                "raw_type_transitions": transitions,
                "raw_type_observations": states,
                "strategic_region": None,
                "control_team": None,
                "full_742_evolution_rule_verified": False,
            }
        )
    calibration = _calibrate_types(camps, captures)
    statuses = Counter(
        row["cohort_status"] for c in camps for row in c["historical_composition_observations"]
    )
    return {
        "schema": "patch-camp-semantics/1",
        "exact_patch": exact_patch,
        "status": "candidate",
        "source_refs": copy.deepcopy(source_refs),
        "match_ids": list(match_ids),
        "camps": camps,
        "training_allowed": False,
        "action_review_allowed": False,
        "user_approved": False,
        "observed_enum_calibration": calibration,
        "historical_rules": {
            "source_patch": "7.38",
            "status": "historical_unverified_for_patch",
            "statements": history,
            "current_localization_evidence": localization,
            "normalized_labels": _LABELS.copy(),
            "label_normalization_is_policy_not_a_current_patch_enum": True,
            "thirty_minute_evolution_verified": False,
            "blocking_rule_verified": False,
        },
        "summary": {
            "camps": len(camps),
            "previous_current_patch_type_candidates": sum(
                c.get("type") is not None for c in original
            ),
            "new_direct_current_patch_type_candidates": sum(
                c["current_patch_type_status"] == "new_direct_official_origin_candidate"
                for c in camps
            ),
            "current_patch_type_candidates": sum(
                c["current_patch_type_candidate"] is not None for c in camps
            ),
            "current_patch_type_unknown": sum(
                c["current_patch_type_candidate"] is None for c in camps
            ),
            "dynamic_composition_candidates": sum(
                c["dynamic_composition_candidate"] for c in camps
            ),
            "unknown_static_type_with_empirical_phase_candidates": sum(
                c["current_patch_type_candidate"] is None
                and any(
                    row["empirical_type_candidate"] is not None
                    for row in c["empirical_type_timeline"]
                )
                for c in camps
            ),
            "composition_cohort_statuses": dict(statuses),
            "historical_labels_counted_as_current_patch_verified": False,
            "formal_type_approved_camps": 0,
        },
        "limits": [
            "Official unit origin and complete spawn composition are distinct evidence.",
            "Exact identities, raw ticks and original spawner handles join activation cohorts.",
            "Waiting states, missing links, partial batches and existing live units are audited.",
            "Three matched activations do not prove complete respawns or absence of other units.",
            "7.38 labels and schedules remain historical hypotheses when observed in 7.42 samples.",
            "Dynamic camps have no static type, control team or approved strategic region.",
            "Empirical type timelines describe observed spawner fields within one game build.",
            "Calibration uses distinct camps; repeated matches do not add independent anchors.",
        ],
    }
