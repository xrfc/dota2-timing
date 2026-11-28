"""Project decision-time team-visible unit facts from a separate omniscient capture.

An empty visible list never establishes an empty camp. Ownership, other-team vision,
hidden entities, lifecycle history and future observations do not enter this view.
"""

import math

SCHEMA = "camp-evidence/1"
SOURCE_SCHEMA = "gem-camp-evidence/1"
SAMPLING = "first_tick_start_before_entity_updates"
UNIT_FIELDS = ("unit_name", "team", "x", "y", "health", "max_health", "life_state")


def _integer(value):
    return type(value) is int and value >= 0


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _visible_unit(unit):
    identity = {key: unit.get(key) for key in ("entity_index", "entity_serial")}
    if not all(_integer(value) for value in identity.values()):
        raise ValueError("visible unit lacks a valid entity identity")
    result = dict(identity)
    missing = []
    for key in UNIT_FIELDS:
        value = unit.get(key)
        valid = (
            isinstance(value, str) and bool(value)
            if key == "unit_name"
            else _number(value)
            if key in ("x", "y")
            else type(value) is int
        )
        result[key] = value if valid else None
        if not valid:
            missing.append(("missing_" if value is None else "invalid_") + key)
    result["missing_reasons"] = missing
    return result


def project_frame(frame):
    """Use only an exact visible bit for the validated observer's own team."""
    hero, second, status = frame.get("hero"), frame.get("t"), frame.get("status")
    if not isinstance(hero, str) or not hero or not _integer(second):
        raise ValueError("invalid camp observation identity")
    if status not in ("observed", "missing_observer", "missing_frame"):
        raise ValueError("unsupported camp observation status")
    ticks = {key: frame.get(key) for key in ("tick", "net_tick")}
    observer = frame.get("observer")
    if status == "missing_frame":
        known_ticks = all(_integer(value) for value in ticks.values())
        absent_ticks = all(value is None for value in ticks.values())
        if observer is not None or not (known_ticks or absent_ticks):
            raise ValueError("missing frame contains an observer or inconsistent tick identity")
    elif not all(_integer(value) for value in ticks.values()):
        raise ValueError("observed game second lacks tick identity")
    units, public_observer = [], None
    if status == "observed":
        if (
            not isinstance(observer, dict)
            or type(observer.get("team")) is not int
            or observer["team"] not in (2, 3)
            or not _integer(observer.get("slot"))
            or observer["slot"] > 4
            or not _integer(observer.get("resource_index"))
            or observer["resource_index"] >= 30
        ):
            raise ValueError("invalid camp observer roster identity")
        public_observer = {"team": observer["team"]}
        team_name = {2: "radiant", 3: "dire"}[observer["team"]]
        if not isinstance(frame.get("units"), list):
            raise ValueError("observed camp frame requires a unit list")
        for unit in frame["units"]:
            # No hidden attribute is validated, counted or used to explain missingness.
            visibility = unit.get("visibility") if isinstance(unit, dict) else None
            if isinstance(visibility, dict) and visibility.get(team_name) == "visible":
                units.append(_visible_unit(unit))
        identities = {(u["entity_index"], u["entity_serial"]) for u in units}
        if len(identities) != len(units):
            raise ValueError("duplicate visible entity identity")
        units.sort(key=lambda u: (u["entity_index"], u["entity_serial"]))
    elif observer is not None:
        raise ValueError("missing observer status contains an observer")
    return dict(
        hero=hero,
        t=second,
        **ticks,
        status=status,
        observer=public_observer,
        units=units,
        stock_complete=False,
        empty_confirmed=None,
        camp_id=None,
    )


def project_camp_evidence(captured):
    """Return a whitelist-only payload; source and implementation hashes live outside it."""
    if (
        captured.get("schema") != SOURCE_SCHEMA
        or captured.get("sampling") != SAMPLING
        or not _integer(captured.get("match_id"))
        or captured["match_id"] == 0
    ):
        raise ValueError("unsupported camp capture identity, schema or sampling")
    frames = [project_frame(frame) for frame in captured["frames"]]
    if len({(f["hero"], f["t"]) for f in frames}) != len(frames):
        raise ValueError("duplicate camp observation")
    return dict(
        schema=SCHEMA,
        source_schema=SOURCE_SCHEMA,
        match_id=captured["match_id"],
        sampling=SAMPLING,
        frames=sorted(frames, key=lambda f: (f["hero"], f["t"])),
    )
