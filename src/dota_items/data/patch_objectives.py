"""Candidate camp semantics and observed objective intervals from explicit patch evidence.

These pure builders consume caller-verified documents. They do not verify source files,
admit a patch for reviews, or reinterpret replay omniscience as a player's information.
"""

import copy
import math
import re
from collections import Counter, defaultdict


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _base(exact_patch, source_refs, schema):
    if not isinstance(exact_patch, str) or re.fullmatch(r"\d+\.\d+[a-z]?", exact_patch) is None:
        raise ValueError("Expected exact patch")
    if not isinstance(source_refs, (dict, list)) or not source_refs:
        raise ValueError("Explicit source references required")
    return {
        "schema": schema,
        "exact_patch": exact_patch,
        "status": "candidate",
        "training_allowed": False,
        "action_review_allowed": False,
        "user_approved": False,
        "source_refs": copy.deepcopy(source_refs),
    }


def _captures(captures, exact_patch):
    seen = set()
    for capture in captures:
        mid = capture.get("match_id")
        if (
            capture.get("schema") != "map-runtime-capture/1"
            or capture.get("patch") != exact_patch
            or capture.get("training_allowed") is not False
            or capture.get("omniscient") is not True
            or capture.get("coordinate_space") != "world"
            or type(mid) is not int
            or mid <= 0
            or mid in seen
            or type(capture.get("game_build")) is not int
            or capture["game_build"] <= 0
            or type(capture.get("post_game_tick")) is not int
            or capture["post_game_tick"] < 0
            or capture.get("parse_error") is not None
            or capture.get("truncated_at_tick") is not None
        ):
            raise ValueError("Runtime capture identity, patch, purpose or completeness mismatch")
        seen.add(mid)
        for channel in ("spawners", "neutral_units", "objectives"):
            if not isinstance(capture.get(channel), list):
                raise ValueError("Missing runtime entity channel")
            identities = set()
            for record in capture[channel]:
                expected = {
                    "spawners": {"spawner"},
                    "neutral_units": {"neutral_unit"},
                    "objectives": {"roshan", "tormentor"},
                }[channel]
                if record.get("kind") not in expected:
                    raise ValueError("Runtime entity is in the wrong channel")
                key = _identity(record)
                if key in identities:
                    raise ValueError("Duplicate runtime entity identity")
                identities.add(key)
                last = -1
                if not isinstance(record.get("observations"), list) or not record["observations"]:
                    raise ValueError("Entity observations are missing")
                for row in record["observations"]:
                    _row(row, capture)
                    if _identity(row) != key or row["tick"] < last:
                        raise ValueError("Entity observations unordered or use another identity")
                    last = row["tick"]
        frames = capture.get("objective_frames")
        if not isinstance(frames, list):
            raise ValueError("Missing objective frames")
        last = -1
        for frame in frames:
            if (
                type(frame.get("tick")) is not int
                or not last < frame["tick"] <= capture["post_game_tick"]
                or (frame.get("game_time") is not None and not _number(frame["game_time"]))
            ):
                raise ValueError("Invalid objective frame time")
            last = frame["tick"]
            for kind in ("roshan", "tormentor"):
                if not isinstance(frame.get(kind), list):
                    raise ValueError("Missing objective frame kind")
                identities = set()
                for row in frame[kind]:
                    _row(row, capture)
                    if (
                        row["tick"] != frame["tick"]
                        or _identity(row) in identities
                        or row["game_time"] != frame["game_time"]
                    ):
                        raise ValueError("Objective frame time/identity mismatch")
                    identities.add(_identity(row))
        yield capture


def _identity(row):
    result = row.get("entity_index"), row.get("entity_serial")
    if any(type(value) is not int or value < 0 for value in result):
        raise ValueError("Invalid entity identity")
    return result


def _row(row, capture):
    _identity(row)
    if (
        type(row.get("tick")) is not int
        or not 0 <= row["tick"] <= capture["post_game_tick"]
        or (row.get("game_time") is not None and not _number(row["game_time"]))
        or not isinstance(row.get("raw_fields"), dict)
        or type(row.get("active")) is not bool
    ):
        raise ValueError("Invalid runtime observation")
    for axis in ("x", "y"):
        if row.get(axis) is not None and not _number(row[axis]):
            raise ValueError("Invalid world coordinate")
    for name in ("m_lifeState", "m_Type", "m_iCampType", "m_hNeutralSpawner"):
        value = row["raw_fields"].get(name)
        if value is not None and type(value) is not int:
            raise ValueError("Invalid integer runtime field")
    waiting = row["raw_fields"].get("m_bIsWaitingToSpawn")
    if waiting is not None and type(waiting) is not bool:
        raise ValueError("Invalid waiting-to-spawn field")
    if row.get("npc_name") is not None and not isinstance(row["npc_name"], str):
        raise ValueError("Invalid runtime NPC name")
    association = row.get("spawner_identity")
    if association is not None and (
        not isinstance(association, list)
        or len(association) != 2
        or any(type(value) is not int or value < 0 for value in association)
    ):
        raise ValueError("Invalid resolved spawner identity")
    if association is not None:
        handle = row["raw_fields"].get("m_hNeutralSpawner")
        if (
            type(handle) is not int
            or handle < 0
            or handle in (0xFFFFFF, 0xFFFFFFFF)
            or association != [handle & ((1 << 14) - 1), handle >> 14]
        ):
            raise ValueError("Resolved spawner identity contradicts raw handle")


def _active(row):
    raw = row["raw_fields"]
    return (
        row["active"] is True
        and row.get("op") not in ("deleted", "left")
        and raw.get("m_lifeState") == 0
        and type(raw.get("m_lifeState")) is int
        and raw.get("m_bIsWaitingToSpawn") is False
    )


def _camp_boxes(documents):
    data = documents["mapdata.json"]["data"]
    camps = []
    for index, trigger in enumerate(data.get("trigger_multiple", [])):
        name = trigger.get("name")
        if not isinstance(name, str) or not name.startswith("neutralcamp_"):
            continue
        points = [trigger[str(i)] for i in range(1, 5)]
        if any(not _number(point.get(axis)) for point in points for axis in ("x", "y")):
            raise ValueError("Invalid camp trigger coordinates")
        xs, ys = sorted({point["x"] for point in points}), sorted({point["y"] for point in points})
        if len(xs) != 2 or len(ys) != 2 or len({(p["x"], p["y"]) for p in points}) != 4:
            raise ValueError("Camp trigger must have four rectangular corners")
        match = re.fullmatch(r"neutralcamp_(good|evil)_(\d+)", name)
        camps.append(
            {
                "camp_id": name,
                "rectangle": {"min_x": xs[0], "max_x": xs[1], "min_y": ys[0], "max_y": ys[1]},
                "source_side_token": match[1] if match else None,
                "control_team": None,
                "strategic_region": None,
                "trigger_pointer": f"/data/trigger_multiple/{index}",
                "type": None,
                "type_status": "unknown",
                "type_evidence": [],
                "raw_spawner_types": [],
                "observed_units": {},
                "runtime_spawners": [],
                "activation_batches": [],
                "unit_record_coverage": {},
            }
        )
    if not camps or len({camp["camp_id"] for camp in camps}) != len(camps):
        raise ValueError("Missing or duplicate camp trigger names")
    assigned = set()
    for index, spawner in enumerate(data.get("npc_dota_neutral_spawner", [])):
        matches = _containing(camps, spawner)
        if len(matches) != 1 or matches[0]["camp_id"] in assigned:
            raise ValueError("Map spawner must uniquely match one camp trigger")
        camp = matches[0]
        assigned.add(camp["camp_id"])
        camp["center"] = {axis: spawner[axis] for axis in ("x", "y")}
        camp["spawner_pointer"] = f"/data/npc_dota_neutral_spawner/{index}"
    if len(assigned) != len(camps):
        raise ValueError("Camp trigger lacks a unique map spawner")
    return camps


def _containing(camps, row):
    if any(not _number(row.get(axis)) for axis in ("x", "y")):
        return []
    return [
        camp
        for camp in camps
        if camp["rectangle"]["min_x"] <= row["x"] <= camp["rectangle"]["max_x"]
        and camp["rectangle"]["min_y"] <= row["y"] <= camp["rectangle"]["max_y"]
    ]


def _official(notes, exact_patch):
    if (
        not isinstance(notes, dict)
        or notes.get("success") is not True
        or any(notes.get(field) != exact_patch for field in ("patch_number", "patch_name"))
    ):
        raise ValueError("Official notes do not match exact patch")
    # Interpretation is registered for this exact source structure and patch, never inherited.
    if exact_patch != "7.42":
        raise ValueError("No registered objective interpretation for this exact patch")


def _unit_type_evidence(notes, exact_patch):
    if notes is None:
        return {}
    _official(notes, exact_patch)
    rules = (
        (21, "Medium", "Radiant", ("Radigull",), "Added a Radigull camp:"),
        (
            22,
            "Medium",
            "Dire",
            ("Odobenus Frostmage", "Odobenus Footman"),
            "Added an Odobenus camp:",
        ),
        (23, "Large", "Radiant", ("Eimermole Foreman", "Eimermole"), "Added an Eimermole camp:"),
        (
            24,
            "Ancient",
            None,
            ("Ancient Ogre Seal", "Ancient Ogre Seal Pup"),
            "Added an Ancient Ogre Seal camp:",
        ),
    )
    result = {}
    rows = notes["neutral_creeps"][0]["neutral_creep_notes"]
    for index, label, side, names, prefix in rules:
        rule = rows[index]
        if not rule.get("note", "").startswith(prefix) or label not in rule["note"]:
            raise ValueError("Official camp composition statement changed")
        if side is not None and side not in rule["note"]:
            raise ValueError("Official camp home-side statement changed")
        for name in names:
            matches = [
                (i, row)
                for i, row in enumerate(notes["neutral_creeps"])
                if row.get("localized_name") == name
            ]
            composition_name = {"Odobenus Footman": "Odobenus Footmen"}.get(name, name)
            if len(matches) != 1 or composition_name not in rule.get("info", ""):
                raise ValueError("Official camp unit identity/composition is ambiguous")
            unit_index, unit = matches[0]
            npc = unit.get("name")
            if not isinstance(npc, str) or not npc.startswith("npc_dota_neutral_"):
                raise ValueError("Invalid official neutral NPC name")
            result[npc] = {
                "type": label.lower(),
                "home_jungle": side,
                "note_pointer": f"/neutral_creeps/0/neutral_creep_notes/{index}",
                "unit_pointer": f"/neutral_creeps/{unit_index}",
                "method": "explicit_composition_unit",
            }
    for index, label, side in (
        (8, "Small", "Radiant"),
        (9, "Medium", "Radiant"),
        (10, "Large", "Radiant"),
        (12, "Small", "Dire"),
        (13, "Medium", "Dire"),
        (14, "Large", "Dire"),
    ):
        statement = rows[index].get("note", "")
        prefix = f"{label} camps: "
        if not statement.startswith(prefix):
            raise ValueError("Official camp-family statement changed")
        exact_names = set()
        for term in statement.removeprefix(prefix).split("; "):
            term = term.removesuffix(" (new!)").removesuffix(" camp")
            exact_names.update(term.split(" and "))
        for unit_index, unit in enumerate(notes["neutral_creeps"]):
            if unit.get("localized_name") not in exact_names:
                continue
            npc = unit.get("name")
            if not isinstance(npc, str) or not npc.startswith("npc_dota_neutral_"):
                raise ValueError("Invalid exact-name official camp unit")
            if npc in result and result[npc]["type"] != label.lower():
                raise ValueError("Official exact-name camp unit has conflicting types")
            result.setdefault(
                npc,
                {
                    "type": label.lower(),
                    "home_jungle": side,
                    "note_pointer": f"/neutral_creeps/0/neutral_creep_notes/{index}",
                    "unit_pointer": f"/neutral_creeps/{unit_index}",
                    "method": "camp_name_equals_localized_unit_name",
                },
            )
    return result


def build_camp_assets(
    map_documents, runtime_captures, *, exact_patch, source_refs, official_notes=None
):
    """Join unique map boxes to real spawner handles; unsupported camp types remain unknown."""
    result = _base(exact_patch, source_refs, "patch-camp-assets/1")
    camps = _camp_boxes(map_documents)
    semantics = _unit_type_evidence(official_notes, exact_patch)
    unknown, batches, unit_counts, type_refs = [], defaultdict(list), defaultdict(Counter), {}
    inactive_records, record_coverage = [], Counter()
    match_ids = []
    for capture in _captures(runtime_captures, exact_patch):
        mid, associations = capture["match_id"], {}
        match_ids.append(mid)
        for index, record in enumerate(capture["spawners"]):
            matches = {
                camp["camp_id"]: camp
                for row in record["observations"]
                for camp in _containing(camps, row)
            }
            if len(matches) != 1 or any(
                len(_containing(camps, row)) != 1
                for row in record["observations"]
                if all(_number(row.get(axis)) for axis in ("x", "y"))
            ):
                unknown.append(
                    {
                        "match_id": mid,
                        "spawner": list(_identity(record)),
                        "reason": "no_unique_static_trigger",
                    }
                )
                continue
            camp = next(iter(matches.values()))
            associations[_identity(record)] = camp
            camp["runtime_spawners"].append(
                {
                    "match_id": mid,
                    "identity": list(_identity(record)),
                    "pointer": f"/spawners/{index}",
                    "raw_type_timeline": [
                        {
                            "tick": row["tick"],
                            "game_time": row["game_time"],
                            "fields": {
                                name: row["raw_fields"].get(name)
                                for name in ("m_Type", "m_iCampType")
                            },
                            "pointer": f"/spawners/{index}/observations/{row_index}",
                        }
                        for row_index, row in enumerate(record["observations"])
                    ],
                }
            )
            for row in record["observations"]:
                for field in ("m_Type", "m_iCampType"):
                    value = row["raw_fields"].get(field)
                    evidence = {"field": field, "value": value}
                    if value is not None and evidence not in camp["raw_spawner_types"]:
                        camp["raw_spawner_types"].append(evidence)
        for index, record in enumerate(capture["neutral_units"]):
            active_rows = [(i, row) for i, row in enumerate(record["observations"]) if _active(row)]
            if not active_rows:
                status, missing = _inactive_status(record)
                linked = {
                    associations[tuple(row["spawner_identity"])]["camp_id"]: associations[
                        tuple(row["spawner_identity"])
                    ]
                    for row in record["observations"]
                    if row.get("spawner_identity") is not None
                    and tuple(row["spawner_identity"]) in associations
                }
                camp = next(iter(linked.values())) if len(linked) == 1 else None
                if camp is not None:
                    coverage = camp["unit_record_coverage"]
                    coverage[status] = coverage.get(status, 0) + 1
                inactive_records.append(
                    {
                        "match_id": mid,
                        "entity": list(_identity(record)),
                        "status": status,
                        "camp_id": camp["camp_id"] if camp is not None else None,
                        "missing_activation_fields": missing,
                        "pointer": f"/neutral_units/{index}",
                    }
                )
                record_coverage[status] += 1
                continue
            record_coverage["active_observed"] += 1
            row_index, row = active_rows[0]
            association = row.get("spawner_identity")
            camp = associations.get(tuple(association)) if association is not None else None
            if camp is None:
                unknown.append(
                    {
                        "match_id": mid,
                        "unit": list(_identity(record)),
                        "reason": "no_resolved_spawner_trigger",
                    }
                )
                continue
            camp_id, name = camp["camp_id"], row.get("npc_name")
            coverage = camp["unit_record_coverage"]
            coverage["active_observed"] = coverage.get("active_observed", 0) + 1
            if isinstance(name, str):
                unit_counts[camp_id][name] += 1
            previous = record["observations"][:row_index]
            waiting = [r for r in previous if r["raw_fields"].get("m_bIsWaitingToSpawn") is True]
            batches[mid, camp_id, row["tick"]].append(
                {
                    "entity": list(_identity(record)),
                    "npc_name": name,
                    "game_time": row["game_time"],
                    "last_waiting_game_time": waiting[-1]["game_time"] if waiting else None,
                    "last_waiting_tick": waiting[-1]["tick"] if waiting else None,
                    "left_censored": not waiting,
                    "pointer": f"/neutral_units/{index}/observations/{row_index}",
                }
            )
            if name in semantics:
                key = camp_id, name
                if key not in type_refs:
                    evidence = {
                        **semantics[name],
                        "npc_name": name,
                        "match_id": mid,
                        "unit_identity": list(_identity(record)),
                        "runtime_pointer": f"/neutral_units/{index}/observations/{row_index}",
                        "conditions": "alive_nonwaiting_unit; resolved_spawner; unique_trigger",
                    }
                    type_refs[key] = evidence
                    camp["type_evidence"].append(evidence)
    for camp in camps:
        camp_id = camp["camp_id"]
        camp["observed_units"] = dict(sorted(unit_counts[camp_id].items()))
        types = {row["type"] for row in camp["type_evidence"]}
        if len(types) == 1:
            camp.update(type=next(iter(types)), type_status="candidate_from_official_composition")
        elif len(types) > 1:
            camp["type_status"] = "conflicting_evidence"
        camp["activation_batches"] = [
            {
                "match_id": mid,
                "tick": tick,
                "game_time": units[0]["game_time"],
                "units": units,
                "any_left_censored_unit": any(unit["left_censored"] for unit in units),
            }
            for (mid, name, tick), units in sorted(batches.items())
            if name == camp_id
        ]
    return {
        **result,
        "match_ids": match_ids,
        "camps": camps,
        "unresolved_associations": unknown,
        "unit_records_without_active_observation": inactive_records,
        "summary": {
            "camps": len(camps),
            "candidate_typed_camps": sum(c["type"] is not None for c in camps),
            "unknown_or_conflicting_types": sum(c["type"] is None for c in camps),
            "activation_batches": len(batches),
            "resolved_active_units": sum(len(units) for units in batches.values()),
            "unresolved_active_units": sum("unit" in row for row in unknown),
            "observed_unit_records": sum(record_coverage.values()),
            "unit_record_coverage": dict(record_coverage),
        },
        "limits": [
            "good/evil are map source tokens, not control, safety or approved strategic regions.",
            "Numeric spawner types have no registered enum labels and are retained verbatim.",
            "Raw type timelines can change within a replay; one static enum label is not assumed.",
            "Types use explicit compositions or exact camp/unit name equality; no fuzzy families.",
            "Observed activation batches do not establish respawn rules or spawn-block causes.",
            "Unknown and conflicting camp types cannot enter typed action-review features.",
            "Missing activation state, waiting-only and non-alive records are not zero occupancy.",
        ],
    }


def _inactive_status(record):
    rows = record["observations"]
    missing = sorted(
        {
            field
            for row in rows
            for field in ("m_lifeState", "m_bIsWaitingToSpawn")
            if row["raw_fields"].get(field) is None
        }
    )
    if missing:
        return "unknown_activation_state", missing
    if all(row["raw_fields"]["m_bIsWaitingToSpawn"] is True for row in rows):
        return "waiting_only", []
    if all(row["raw_fields"]["m_lifeState"] > 0 for row in rows):
        return "non_alive_only", []
    return "inactive_or_disappeared", []


def _interval(row, previous):
    return {
        "lower_game_time": previous.get("game_time") if previous else None,
        "upper_game_time": row.get("game_time"),
        "lower_tick": previous.get("tick") if previous else None,
        "upper_tick": row["tick"],
        "left_censored": previous is None,
        "lower_observation_boundary": previous.get("boundary", "after_entity_delta")
        if previous
        else None,
        "upper_observation_boundary": "after_entity_delta",
    }


def _latest_frame_bound(frames, kind, row, previous, *, death=False):
    """A pre-update sample at the event tick precedes that tick's entity delta."""
    lower = previous
    for frame in frames:
        if frame["tick"] > row["tick"]:
            break
        if lower is not None and frame["tick"] <= lower["tick"]:
            continue
        same = [sample for sample in frame[kind] if _identity(sample) == _identity(row)]
        if death:
            usable = any(_active(sample) for sample in same)
        else:
            usable = (previous is None and not frame[kind]) or any(
                sample["raw_fields"].get("m_bIsWaitingToSpawn") is True
                or (
                    type(sample["raw_fields"].get("m_lifeState")) is int
                    and sample["raw_fields"]["m_lifeState"] > 0
                )
                for sample in same
            )
        if usable:
            lower = {
                "tick": frame["tick"],
                "game_time": frame["game_time"],
                "boundary": "before_current_tick_entity_deltas",
            }
    return lower


def build_objective_observations(runtime_captures, *, exact_patch, source_refs):
    """Report observed activation/death bounds; absence and deletion never imply death."""
    result = _base(exact_patch, source_refs, "patch-objective-observations/1")
    matches = []
    for capture in _captures(runtime_captures, exact_patch):
        objectives = {}
        frames = capture["objective_frames"]
        for kind in ("roshan", "tormentor"):
            activations, deaths = [], []
            entities = [r for r in capture["objectives"] if r.get("kind") == kind]
            for record in entities:
                previous = None
                was_active = False
                for row in record["observations"]:
                    active = _active(row)
                    if (
                        active
                        and not was_active
                        and (
                            previous is None
                            or previous["raw_fields"].get("m_bIsWaitingToSpawn") is True
                            or (
                                type(previous["raw_fields"].get("m_lifeState")) is int
                                and previous["raw_fields"]["m_lifeState"] > 0
                            )
                        )
                    ):
                        lower = _latest_frame_bound(frames, kind, row, previous)
                        activations.append(
                            {
                                "entity": list(_identity(record)),
                                **_interval(row, lower),
                                "position": [row["x"], row["y"]],
                            }
                        )
                    life = row["raw_fields"].get("m_lifeState")
                    if (
                        was_active
                        and type(life) is int
                        and life > 0
                        and row.get("op") not in ("left", "deleted")
                    ):
                        deaths.append(
                            {
                                "entity": list(_identity(record)),
                                **_interval(
                                    row,
                                    _latest_frame_bound(frames, kind, row, previous, death=True),
                                ),
                            }
                        )
                    previous, was_active = row, active
            coverage = Counter()
            for frame in frames:
                rows = frame[kind]
                status = (
                    "absent"
                    if not rows
                    else "alive"
                    if any(_active(row) for row in rows)
                    else "waiting"
                    if any(row["raw_fields"].get("m_bIsWaitingToSpawn") is True for row in rows)
                    else "non_alive"
                    if all(
                        type(row["raw_fields"].get("m_lifeState")) is int
                        and row["raw_fields"]["m_lifeState"] > 0
                        for row in rows
                    )
                    else "unknown"
                )
                coverage[status] += 1
            activations.sort(key=lambda row: row["upper_tick"])
            respawns = []
            for death in sorted(deaths, key=lambda row: row["upper_tick"]):
                following = [
                    row
                    for row in activations
                    if row["upper_tick"] > death["upper_tick"] and row["entity"] == death["entity"]
                ]
                if following:
                    respawns.append({"death": death, "next_observed_activation": following[0]})
            objectives[kind] = {
                "entities": len(entities),
                "frame_coverage": dict(coverage),
                "activation_observations": activations,
                "death_observations": deaths,
                "death_to_next_activation_observations": respawns,
                "respawn_status": "observed_interval" if respawns else "no_positive_sample",
                "end_status": "right_censored_at_replay_end",
                "end_game_time": capture.get("sampling", {}).get("end_game_time"),
            }
        matches.append(
            {
                "match_id": capture["match_id"],
                "game_build": capture["game_build"],
                "objectives": objectives,
            }
        )
    return {
        **result,
        "matches": matches,
        "limits": [
            "Observed empty frames bound presence only; they do not explain disappearance.",
            "Activation requires life_state=0 and waiting_to_spawn=False, never a first kill.",
            "Intervals carry raw replay ticks and pause-aware unrounded seconds.",
            "No positive respawn sample does not validate or invalidate an official timer rule.",
            "Replacement identities need further association evidence before respawn pairing.",
        ],
    }


def build_objective_rules(notes, *, exact_patch, source_refs):
    """Interpret two explicit 7.42 timer changes, retaining unspecified timer inputs."""
    result = _base(exact_patch, source_refs, "patch-objective-rules/1")
    _official(notes, exact_patch)
    section = notes["general_notes"][2]
    rows = section["generic"]
    if (
        section.get("title") != "Map Objectives"
        or rows[1].get("note") != "Initial spawn time decreased from 20:00 to 15:00"
        or rows[11].get("note")
        != (
            "Base respawn timer now decreases by 1 minute every time Roshan is defeated, "
            "to a minimum of 5 minutes"
        )
    ):
        raise ValueError("Official objective timer statements changed")
    return {
        **result,
        "rules": [
            {
                "objective": "tormentor",
                "property": "initial_spawn_game_seconds",
                "value": 900,
                "source_pointer": "/general_notes/2/generic/1",
            },
            {
                "objective": "roshan",
                "property": "base_respawn_seconds",
                "decrease_per_defeat_seconds": 60,
                "minimum_seconds": 300,
                "initial_base_seconds": None,
                "random_extra_seconds": None,
                "source_pointer": "/general_notes/2/generic/11",
            },
        ],
        "limits": [
            "Changes in official notes are candidate facts, not a complete objective scheduler.",
            "Tormentor repeat timer and Roshan initial base/random component remain unspecified.",
            "No previous patch timer is inherited; replay observations do not grant approval.",
        ],
    }
