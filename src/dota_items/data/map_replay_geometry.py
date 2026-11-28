"""Pure geometry diagnostics for a verified Workshop map and replay observations.

The caller owns source verification, match selection and patch/build binding. This
module consumes documents, not paths; its output is never a compatibility grant.
State-v3 buildings carry health and entity IDs, NOT coordinates. Static landmark
coordinates must come from a separately identified observation source.
"""

import math
import re
from collections import Counter, defaultdict

CELL = 64
REPLAY_OFFSET = 16384


def _number(value, label):
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{label}: expected finite number")
    return value


def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label}: expected integer >= {minimum}")
    return value


def _point(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label}: expected two coordinates")
    return tuple(_number(v, label) for v in value)


def _map_parts(documents):
    """Check the consumed shape; complete source validation belongs to map_snapshot."""
    try:
        world = documents["worlddata.json"]
        bounds = tuple(
            _number(world[k], "world bounds")
            for k in ("worldMinX", "worldMinY", "worldMaxX", "worldMaxY")
        )
        elevation = documents["elevationdata.json"]["data"]
        blocked_rows = documents["gridnavdata.json"]["data"]
        landmarks = documents["mapdata.json"]["data"]
        lanes = documents["lanedata.json"]
    except (KeyError, TypeError) as exc:
        raise ValueError("expected all five verified map documents") from exc
    xmin, ymin, xmax, ymax = bounds
    if xmax < xmin or ymax < ymin or (xmax - xmin) % CELL or (ymax - ymin) % CELL:
        raise ValueError("map bounds must describe the 64-unit sampling grid")
    width, height = int((xmax - xmin) / CELL) + 1, int((ymax - ymin) / CELL) + 1
    if (
        not isinstance(elevation, list)
        or len(elevation) != width
        or any(not isinstance(row, list) or len(row) != height for row in elevation)
    ):
        raise ValueError("elevation shape does not match world bounds")
    for row in elevation:
        for value in row:
            _number(value, "elevation")
    if not isinstance(blocked_rows, list) or not isinstance(landmarks, dict):
        raise ValueError("expected blocked points and landmark categories")
    blocked = set()
    for value in blocked_rows:
        if not isinstance(value, dict) or "x" not in value or "y" not in value:
            raise ValueError("invalid blocked grid point")
        x, y = _point([value["x"], value["y"]], "blocked grid")
        if (
            not xmin <= x <= xmax
            or not ymin <= y <= ymax
            or (x - xmin) % CELL
            or (y - ymin) % CELL
            or (x, y) in blocked
        ):
            raise ValueError("invalid or duplicate blocked grid point")
        blocked.add((x, y))
    for category, entries in landmarks.items():
        if not isinstance(category, str) or not isinstance(entries, list):
            raise ValueError("invalid map landmark category")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("invalid map landmark entry")
            # Unconsumed categories can contain polygons (trigger_multiple), not
            # point entities. map_snapshot validates their source-specific shape.
    if not isinstance(lanes, dict) or lanes.get("type") != "FeatureCollection":
        raise ValueError("invalid lane document")
    return bounds, blocked, landmarks


def compare_landmark_positions(map_documents, observations):
    """Compare world-space points without inventing entity identities or a pass cutoff.

    Each observation has ``kind`` (mapdata category), ``x`` and ``y``. Optional
    entity_index/entity_serial/class_name/team are retained for provenance only.
    Exact pairs are one-to-one by coordinates; nearest matches can collide and do
    not count as exact coverage. Repeated observations do not multiply coverage.
    """
    _, _, landmarks = _map_parts(map_documents)
    grouped = defaultdict(list)
    for observation in observations:
        if not isinstance(observation, dict):
            raise ValueError("landmark observation must be an object")
        kind = observation.get("kind")
        if not isinstance(kind, str) or not kind:
            raise ValueError("landmark observation requires kind")
        if "x" not in observation or "y" not in observation:
            raise ValueError("landmark observation requires world coordinates")
        xy = _point([observation["x"], observation["y"]], "landmark observation")
        record = {"kind": kind, "x": xy[0], "y": xy[1]}
        for field in ("entity_index", "entity_serial", "team"):
            if field in observation:
                record[field] = (
                    None
                    if field == "team" and observation[field] is None
                    else _integer(observation[field], field)
                )
        if "class_name" in observation:
            if not isinstance(observation["class_name"], str):
                raise ValueError("class_name must be a string")
            record["class_name"] = observation["class_name"]
        grouped[kind].append(record)
    categories = {}
    for kind, records in sorted(grouped.items()):
        targets = landmarks.get(kind, [])
        for target in targets:
            if "x" not in target or "y" not in target:
                raise ValueError(f"{kind}: requested point comparison for a non-point landmark")
            _point([target["x"], target["y"]], "map landmark")
        used = set()
        used_observation_points = set()
        nearest_counts = Counter()
        pairs, details, distances = [], [], []
        for index, record in enumerate(records):
            point = (record["x"], record["y"])
            options = sorted(
                (math.dist(point, (target["x"], target["y"])), i)
                for i, target in enumerate(targets)
            )
            detail = {"observation_index": index, **record}
            if options:
                distance, nearest = options[0]
                nearest_counts[nearest] += 1
                distances.append(distance)
                detail.update(
                    nearest_map_index=nearest,
                    nearest_map_name=targets[nearest].get("name"),
                    distance_world_units=round(distance, 6),
                    equally_near_map_indices=[i for d, i in options if d == distance],
                )
                exact = (
                    next((i for d, i in options if d == 0 and i not in used), None)
                    if point not in used_observation_points
                    else None
                )
                if exact is not None:
                    used.add(exact)
                    used_observation_points.add(point)
                    pairs.append({"observation_index": index, "map_index": exact})
            else:
                detail.update(nearest_map_index=None, distance_world_units=None)
            details.append(detail)
        categories[kind] = {
            "map_entries": len(targets),
            "observations": len(records),
            "unique_observation_positions": len({(r["x"], r["y"]) for r in records}),
            "exact_one_to_one_pairs": pairs,
            "exact_map_entries_covered": len(used),
            "map_entries_without_exact_observation": len(targets) - len(used),
            "nearest_map_entries": len(nearest_counts),
            "nearest_collisions": sum(n - 1 for n in nearest_counts.values()),
            "max_nearest_distance_world_units": round(max(distances), 6) if distances else None,
            "details": details,
        }
    return {
        "schema": "map-landmark-comparison/1",
        "coordinates": "world coordinates; no offset applied by this function",
        "categories": categories,
        "entity_identity_verified": False,
        "compatibility_granted": False,
        "note": "Coordinate pairs are spatial evidence, not proof of entity identity or semantics.",
    }


def _frames(rows, duration, label):
    expected = 0
    for row in rows:
        if not isinstance(row, dict) or type(row.get("t")) is not int:
            raise ValueError(f"{label}: expected a state row with integer t (not a header)")
        if row["t"] != expected or expected > duration:
            raise ValueError(
                f"{label}: expected exactly one ordered row per game second 0..duration"
            )
        yield row
        expected += 1
    if expected != duration + 1:
        raise ValueError(f"{label}: incomplete game window")


def audit_replay_geometry(
    map_documents,
    state_rows,
    *,
    match_id,
    patch,
    replay_build,
    duration,
    extras_rows=None,
):
    """Inspect v3 body positions and optional extras for every game second.

    ``state_rows`` and ``extras_rows`` exclude their JSONL headers. Both iterables,
    if supplied, must cover exactly 0..duration in order: no automatic trimming,
    interpolation, accepting partial streams, or inferring missing coordinates.
    Heroes are the ten stable player bodies in state-v3, not world.summons.
    """
    _integer(match_id, "match_id", 1)
    _integer(replay_build, "replay_build", 1)
    _integer(duration, "duration")
    if not isinstance(patch, str) or not re.fullmatch(r"[0-9]+\.[0-9]+[a-z]?", patch):
        raise ValueError("patch must be an exact patch identifier")
    bounds, blocked, landmarks = _map_parts(map_documents)
    xmin, ymin, xmax, ymax = bounds
    counts = Counter()
    identities = None
    by_hero = defaultdict(Counter)
    tower_ids = set()
    tower_seconds = Counter()
    rows_with_towers = 0
    for row in _frames(state_rows, duration, "state"):
        heroes, world = row.get("heroes"), row.get("world")
        if not isinstance(heroes, list) or len(heroes) != 10 or not isinstance(world, dict):
            raise ValueError("state requires ten hero bodies and world object")
        current = {}
        for hero in heroes:
            if not isinstance(hero, dict):
                raise ValueError("hero body must be an object")
            player = _integer(hero.get("player_id"), "player_id")
            name, team = hero.get("hero"), hero.get("team")
            if (
                player > 9
                or player in current
                or not isinstance(name, str)
                or not name.startswith("npc_dota_hero_")
                or type(team) is not int
                or team not in (2, 3)
            ):
                raise ValueError("invalid or duplicate hero body identity")
            current[player] = (name, team)
            life = _integer(hero.get("life_state"), "life_state")
            hp = _number(hero.get("hp"), "hp")
            if hp < 0:
                raise ValueError("hp cannot be negative")
            pos = hero.get("pos")
            if pos is not None:
                pos = _point(pos, "hero pos")
            counts["all_body_seconds"] += 1
            if life != 0 or hp == 0:
                counts["nonliving_body_seconds"] += 1
                continue
            counts["living_body_seconds"] += 1
            bucket = "missing_position"
            if pos is not None:
                x, y = pos[0] - REPLAY_OFFSET, pos[1] - REPLAY_OFFSET
                bucket = "outside_sample_bounds"
                if xmin <= x <= xmax and ymin <= y <= ymax:
                    # Same nearest-centre/ties-to-even convention as map_api.cell_of.
                    grid = (
                        xmin + round((x - xmin) / CELL) * CELL,
                        ymin + round((y - ymin) / CELL) * CELL,
                    )
                    bucket = "nearest_blocked_cell" if grid in blocked else "nearest_walkable_cell"
            counts[bucket] += 1
            by_hero[name][bucket] += 1
            by_hero[name]["living_body_seconds"] += 1
        if len(set(current.values())) != 10:
            raise ValueError("hero bodies must be distinct within this normal-match schema")
        if identities is not None and identities != current:
            raise ValueError("hero body identity changed during the game window")
        identities = current
        buildings = world.get("buildings")
        if buildings is None:
            counts["seconds_without_building_channel"] += 1
            continue
        if not isinstance(buildings, list):
            raise ValueError("world.buildings must be a list")
        entity_ids = set()
        has_tower = False
        for building in buildings:
            if not isinstance(building, list) or len(building) != 5:
                raise ValueError("state-v3 building is [entity_index, class, team, hp, max_hp]")
            entity, kind, team, hp, max_hp = building
            _integer(entity, "building entity")
            if entity in entity_ids or not isinstance(kind, str):
                raise ValueError("invalid or repeated building entity")
            entity_ids.add(entity)
            if type(team) is not int or team not in (2, 3):
                raise ValueError("invalid building team")
            if _number(hp, "building hp") < 0 or _number(max_hp, "building max_hp") < 0:
                raise ValueError("building health cannot be negative")
            if kind == "Tower":
                tower_ids.add((entity, team))
                tower_seconds[str(team)] += 1
                has_tower = True
        rows_with_towers += has_tower
    fields = (
        "all_body_seconds",
        "nonliving_body_seconds",
        "living_body_seconds",
        "missing_position",
        "outside_sample_bounds",
        "nearest_blocked_cell",
        "nearest_walkable_cell",
        "seconds_without_building_channel",
    )
    hero_counts = {field: counts[field] for field in fields}
    coordinate_denominator = counts["nearest_blocked_cell"] + counts["nearest_walkable_cell"]
    hero_counts["blocked_fraction_of_in_bounds_living_positions"] = (
        counts["nearest_blocked_cell"] / coordinate_denominator if coordinate_denominator else None
    )
    extra_report = None
    if extras_rows is not None:
        extra_points = defaultdict(set)
        extra_observations = Counter()
        for row in _frames(extras_rows, duration, "extras"):
            for field, kind in (
                ("watchers", "npc_dota_lantern"),
                ("outposts", "npc_dota_watch_tower"),
            ):
                entries = row.get(field)
                if not isinstance(entries, list):
                    raise ValueError(f"extras.{field} must be an observed list")
                for entry in entries:
                    if not isinstance(entry, list) or len(entry) != 3:
                        raise ValueError(f"extras.{field}: expected [x, y, current_team]")
                    x, y = _point(entry[:2], f"extras.{field}")
                    if type(entry[2]) is not int or entry[2] not in (0, 2, 3):
                        raise ValueError("invalid observed watcher/outpost team")
                    extra_points[kind].add((x - REPLAY_OFFSET, y - REPLAY_OFFSET))
                    extra_observations[kind] += 1
        observations = [
            {"kind": kind, "x": x, "y": y}
            for kind, points in sorted(extra_points.items())
            for x, y in sorted(points)
        ]
        extra_report = compare_landmark_positions(map_documents, observations)
        extra_report["observation_seconds"] = {
            kind: extra_observations[kind] for kind in ("npc_dota_lantern", "npc_dota_watch_tower")
        }
        extra_report["observed_channels"] = {
            kind: {
                "seconds": duration + 1,
                "entity_seconds": extra_observations[kind],
                "unique_positions": len(extra_points[kind]),
                "map_entries": len(landmarks.get(kind, [])),
            }
            for kind in ("npc_dota_lantern", "npc_dota_watch_tower")
        }
        extra_report["sampling"] = (
            "All game seconds; positions deduplicated per class. Current holder/team is state, "
            "not a stable identity or Workshop ownership certification."
        )
    return {
        "schema": "map-replay-geometry/1",
        "match_id": match_id,
        "patch": patch,
        "replay_build": replay_build,
        "window": {"start": 0, "end_inclusive": duration, "seconds": duration + 1},
        "coordinate_policy": {
            "replay_to_world_offset": REPLAY_OFFSET,
            "sample_bounds": dict(zip(("xmin", "ymin", "xmax", "ymax"), bounds, strict=True)),
            "grid_step": CELL,
            "rounding": "nearest sample centre; exact half-grid ties to even index",
            "outside_bounds": "counted separately, not clamped",
        },
        "hero_positions": hero_counts,
        "living_body_definition": "state-v3 primary player body; life_state == 0 and hp > 0",
        "per_hero": {hero: dict(values) for hero, values in sorted(by_hero.items())},
        "tower_channel": {
            "map_towers": len(landmarks.get("npc_dota_tower", [])),
            "unique_replay_entity_ids": len(tower_ids),
            "tower_entity_seconds_by_team": dict(tower_seconds),
            "rows_with_towers": rows_with_towers,
            "coordinate_coverage": "unavailable_in_state_v3_building_rows",
            "note": (
                "Building columns 4/5 are hp/max_hp, never x/y; IDs do not map to Workshop names."
            ),
        },
        "extras_landmarks": extra_report,
        "not_covered": [
            "tower_coordinates",
            "twin_gate_coordinates",
            "camp_coordinates_and_types",
            "dynamic_terrain",
            "region_semantics",
            "mechanics",
            "action_correctness",
        ],
        "compatibility_granted": False,
        "training_allowed": False,
        "note": (
            "Blocked nearest cells are descriptive: flying, movement abilities, trees, "
            "sampling and snapshot/build differences may contribute. "
            "No accuracy verdict is inferred."
        ),
    }
