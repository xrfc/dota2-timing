"""Describe what visible neutral-class units establish, without certifying a camp.

Consumes the frozen public camp-evidence/1 interchange, independently of its
producer. Counts are observations, not stock, targets, labels or training features.
"""

import math

SCHEMA = "camp-conditions/1"
SAMPLING = "first_tick_start_before_entity_updates"
FACT_FIELDS = ("unit_name", "team", "x", "y", "health", "max_health", "life_state")
FRAME_FIELDS = {
    "hero",
    "t",
    "tick",
    "net_tick",
    "status",
    "observer",
    "units",
    "stock_complete",
    "empty_confirmed",
    "camp_id",
}
CONDITION_GAPS = {
    "camp_membership": ("unit_to_camp_membership_unverified",),
    "inventory": (
        "camp_membership_unconfirmed",
        "spawn_area_bounds_unavailable",
        "camp_area_visibility_unavailable",
    ),
    "route_traversability": (
        "origin_destination_route_not_supplied",
        "dynamic_collision_and_mobility_unavailable",
    ),
    "clearing_capacity": (
        "camp_stock_unconfirmed",
        "hero_attack_defence_resources_unavailable",
        "neutral_combat_properties_unavailable",
    ),
}


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _uint(value):
    return type(value) is int and value >= 0


def _keys(value, expected, kind):
    _require(type(value) is dict and set(value) == set(expected), f"unexpected {kind} fields")


def _validate_unit(unit):
    _keys(unit, {*FACT_FIELDS, "entity_index", "entity_serial", "missing_reasons"}, "public unit")
    _require(_uint(unit["entity_index"]) and _uint(unit["entity_serial"]), "invalid unit identity")
    absent = set()
    for field in FACT_FIELDS:
        value = unit[field]
        if value is None:
            absent.add(field)
            continue
        valid = (
            type(value) is str and bool(value)
            if field == "unit_name"
            else type(value) in (int, float) and math.isfinite(value)
            if field in ("x", "y")
            else type(value) is int
        )
        _require(valid, f"invalid public {field}")
    reasons = unit["missing_reasons"]
    _require(type(reasons) is list, "invalid public missing reasons")
    fields = []
    for reason in reasons:
        _require(
            type(reason) is str and reason.startswith(("missing_", "invalid_")),
            "nonpublic missing reason",
        )
        fields.append(reason.split("_", 1)[1])
    _require(len(fields) == len(set(fields)) and set(fields) == absent, "inexact missing reasons")


def _life(unit):
    state, health = unit["life_state"], unit["health"]
    if state is None:
        return "unknown", ["life_state_unavailable"]
    if state in (1, 2):
        return "not_alive", []
    if state != 0:
        return "unknown", ["unsupported_life_state"]
    if health is None:
        return "unknown", ["health_unavailable"]
    if health <= 0:
        return "conflict", ["alive_state_without_positive_health"]
    return "alive", []


def _team_relation(team, observer_team):
    if team == 4:
        return "neutral"
    if team in (2, 3):
        return "own" if team == observer_team else "opponent"
    return "other_or_unknown"


def _frame(frame):
    _keys(frame, FRAME_FIELDS, "public frame")
    _require(type(frame["hero"]) is str and frame["hero"] and _uint(frame["t"]), "frame identity")
    _require(
        frame["stock_complete"] is False
        and frame["empty_confirmed"] is None
        and frame["camp_id"] is None,
        "camp-evidence/1 cannot certify stock or membership",
    )
    status = frame["status"]
    _require(status in ("observed", "missing_observer", "missing_frame"), "frame status")
    ticks_known = _uint(frame["tick"]) and _uint(frame["net_tick"])
    ticks_absent = frame["tick"] is None and frame["net_tick"] is None
    _require(ticks_known or (status == "missing_frame" and ticks_absent), "frame tick identity")
    source_units, observer = frame["units"], frame["observer"]
    _require(type(source_units) is list, "public units required")
    team = None
    if status == "observed":
        _keys(observer, {"team"}, "public observer")
        team = observer["team"]
        _require(type(team) is int and team in (2, 3), "invalid observer team")
    else:
        _require(observer is None and not source_units, "unavailable frame exposes evidence")

    facts = None
    units, indices = [], set()
    if status == "observed":
        facts = dict(
            visible_units=len(source_units),
            alive=0,
            not_alive=0,
            life_unknown=0,
            life_conflict=0,
            alive_neutral_team=0,
            alive_player_team=0,
            alive_other_or_unknown_team=0,
            alive_neutral_team_visible_health_sum=0,
        )
        for unit in source_units:
            _validate_unit(unit)
            identity = unit["entity_index"], unit["entity_serial"]
            _require(identity[0] not in indices, "duplicate unit index in frame")
            indices.add(identity[0])
            life, issues = _life(unit)
            relation = _team_relation(unit["team"], team)
            key = {"unknown": "life_unknown", "conflict": "life_conflict"}.get(life, life)
            facts[key] += 1
            if life == "alive":
                if relation == "neutral":
                    facts["alive_neutral_team"] += 1
                    facts["alive_neutral_team_visible_health_sum"] += unit["health"]
                elif relation in ("own", "opponent"):
                    facts["alive_player_team"] += 1
                else:
                    facts["alive_other_or_unknown_team"] += 1
            units.append(
                dict(
                    entity_index=identity[0],
                    entity_serial=identity[1],
                    life_evidence=life,
                    team_relation=relation,
                    issues=issues,
                )
            )
    conditions = {
        name: dict(
            status="unconfirmed",
            value=None,
            missing_evidence=([] if status == "observed" else ["observation_unavailable"])
            + list(gaps),
        )
        for name, gaps in CONDITION_GAPS.items()
    }
    return dict(
        **{key: frame[key] for key in ("hero", "t", "tick", "net_tick", "status")},
        observer_team=team,
        units=sorted(units, key=lambda u: (u["entity_index"], u["entity_serial"])),
        facts=facts,
        conditions=conditions,
        stock_complete=False,
        empty_confirmed=None,
        camp_id=None,
    )


def summarize_camp_evidence(document):
    """Validate the exact public schema and describe each frame independently.

    Life state 0 with positive HP supports observed life, 1/2 means non-alive;
    missing/other states and contradictory state-0 HP stay explicit. Neutral
    team membership does not establish natural spawning, hostility or farmability.
    """
    _keys(
        document, {"schema", "source_schema", "match_id", "sampling", "frames"}, "public document"
    )
    _require(
        document["schema"] == "camp-evidence/1"
        and document["source_schema"] == "gem-camp-evidence/1"
        and document["sampling"] == SAMPLING,
        "unsupported public schema or sampling",
    )
    _require(_uint(document["match_id"]) and document["match_id"] > 0, "invalid match identity")
    _require(type(document["frames"]) is list, "public frames required")
    frames = [_frame(frame) for frame in document["frames"]]
    _require(len({(f["hero"], f["t"]) for f in frames}) == len(frames), "duplicate opportunity")
    return dict(
        schema=SCHEMA,
        source_schema=document["schema"],
        match_id=document["match_id"],
        sampling=SAMPLING,
        usage="evidence_audit_only",
        frames=sorted(frames, key=lambda f: (f["hero"], f["t"])),
    )
