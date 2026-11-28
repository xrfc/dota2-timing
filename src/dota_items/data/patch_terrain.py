"""Version-bound static navigation/visibility hypotheses, never actual fog of war.

Callers verify the five Workshop documents and their manifest before constructing
StaticTerrain. No file reads, global maps, hero vision constants or decision-model
inputs live here. Workshop navigation was sampled after clearing trees: callers
must explicitly choose whether the initial tree cells block a diagnostic.
"""

import copy
import heapq
import html
import math
import re
from collections import Counter

CELL = 64
OFFSET = 16384
TREE_POLICIES = ("ignore_initial_trees", "block_initial_tree_cells")


def _number(value, label):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{label} must be finite")
    return value


def _point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("position must have two coordinates")
    return tuple(_number(x, "coordinate") for x in value)


def replay_to_world(position):
    return tuple(value - OFFSET for value in _point(position))


def visibility_observations(capture):
    """Audit captured visibility evidence without filling missing LOS assumptions.

    The current capture deliberately has no verified current-range, flight or
    daylight decoder. Consequently observations is empty, not a fabricated LOS
    comparison. Complete raw frames stay in the separately pinned source; this
    summary keeps bounded unknown examples and measured field denominators.
    """
    if (
        not isinstance(capture, dict)
        or capture.get("schema") != "map-visibility-capture/1"
        or capture.get("coordinate_space") != "world"
        or capture.get("parse_error") is not None
        or capture.get("truncated_at_tick") is not None
        or any(
            type(capture.get(key)) is not int or capture[key] <= 0
            for key in ("match_id", "game_build")
        )
        or type(capture.get("post_game_tick")) is not int
        or capture["post_game_tick"] < 0
        or not isinstance(capture.get("frames"), list)
    ):
        raise ValueError("complete world-coordinate visibility capture required")
    counts, fields, reasons, range_values = Counter(), Counter(), Counter(), {}
    examples, previous_second, previous_tick = [], None, None
    for frame in capture["frames"]:
        if (
            not isinstance(frame, dict)
            or type(frame.get("t")) is not int
            or type(frame.get("tick")) is not int
            or not 0 <= frame["tick"] <= capture["post_game_tick"]
            or not isinstance(frame.get("heroes"), list)
        ):
            raise ValueError("invalid visibility frame or post-game tick")
        second, tick = frame["t"], frame["tick"]
        game_time = _number(frame.get("game_time"), "visibility game_time")
        if math.floor(game_time) != second:
            raise ValueError("visibility frame second disagrees with exact clock")
        if previous_second is not None and (second <= previous_second or tick <= previous_tick):
            raise ValueError("duplicate or unordered visibility frame")
        previous_second, previous_tick = second, tick
        counts["frames"] += 1
        pre_game = second < 0
        counts["pre_game_frames" if pre_game else "game_frames"] += 1
        if not pre_game:
            fields["time_of_day_raw"] += frame.get("time_of_day_raw") is not None
            fields["time_of_day_field_present"] += frame.get("time_of_day_field_present") is True
            phase = frame.get("daycycle", {}).get("phase")
            if phase is not None:
                raise ValueError("capture/1 does not certify a time-of-day phase decoder")
            fields["verified_time_phase"] += 0
        ids, identities = set(), set()
        for hero in frame["heroes"]:
            if not isinstance(hero, dict):
                raise ValueError("invalid visibility hero")
            pid, index, serial = (
                hero.get(key) for key in ("player_id", "entity_index", "entity_serial")
            )
            if (
                type(pid) is not int
                or not 0 <= pid < 10
                or pid in ids
                or type(index) is not int
                or not 0 <= index < 16384
                or type(serial) is not int
                or serial < 0
                or (index, serial) in identities
            ):
                raise ValueError("invalid or duplicate canonical hero identity")
            ids.add(pid)
            identities.add((index, serial))
            if (
                hero.get("visibility_word_index") != index >> 6
                or hero.get("visibility_bit_index") != index & 63
                or not isinstance(hero.get("visibility_words"), dict)
                or not isinstance(hero.get("visibility"), dict)
            ):
                raise ValueError("visibility bitset index evidence mismatch")
            visible = {}
            for team in ("radiant", "dire"):
                word = hero["visibility_words"].get(team)
                valid_word = type(word) is int and 0 <= word < 2**64
                expected = bool(word & (1 << (index & 63))) if valid_word else None
                actual = hero["visibility"].get(team)
                if (actual is not None and type(actual) is not bool) or actual is not expected:
                    raise ValueError("recorded visibility disagrees with raw team word")
                visible[team] = expected
            mask = (
                int(visible["radiant"]) | (int(visible["dire"]) << 1)
                if all(value is not None for value in visible.values())
                else None
            )
            actual_mask = hero.get("vismask")
            if (actual_mask is not None and type(actual_mask) is not int) or actual_mask != mask:
                raise ValueError("recorded vismask disagrees with raw team words")
            counts["mask_rows_checked"] += 1
            if pre_game:
                continue
            counts["hero_samples"] += 1
            counts["known_mask_samples" if mask is not None else "unknown_mask_samples"] += 1
            counts["invalid_raw_word_samples"] += bool(hero.get("invalid_visibility_words"))
            fields["vismask"] += mask is not None
            fields["radiant_visibility"] += visible["radiant"] is not None
            fields["dire_visibility"] += visible["dire"] is not None
            fields["world_position"] += hero.get("x") is not None and hero.get("y") is not None
            for label in ("day_vision_range", "night_vision_range", "current_vision_range"):
                value = hero.get(label)
                if value is not None:
                    if _number(value, label) < 0:
                        raise ValueError("negative vision range")
                    fields[label] += 1
                    range_values.setdefault(label, Counter())[str(value)] += 1
            if hero.get("life_state") == 0 and type(hero.get("hp")) in (int, float):
                counts["alive_hero_samples"] += hero["hp"] > 0
            reason = (
                "current_range_unknown"
                if hero.get("current_vision_range") is None
                else "flight_and_modifier_semantics_unverified"
            )
            reasons[reason] += 1
            if len(examples) < 8:
                examples.append(
                    {
                        "t": second,
                        "player_id": pid,
                        "reason": reason,
                        "base_day_range": hero.get("day_vision_range"),
                        "base_night_range": hero.get("night_vision_range"),
                        "time_of_day_raw": frame.get("time_of_day_raw"),
                        "vismask": mask,
                    }
                )
        if not pre_game:
            counts["missing_player_samples"] += 10 - len(ids)
    game_frames, hero_samples = counts["game_frames"], counts["hero_samples"]
    frame_fields = ("time_of_day_raw", "time_of_day_field_present", "verified_time_phase")
    hero_fields = (
        "day_vision_range",
        "night_vision_range",
        "current_vision_range",
        "vismask",
        "radiant_visibility",
        "dire_visibility",
        "world_position",
    )
    return {
        "schema": "patch-visibility-evidence/1",
        "status": "unknown_current_los",
        "observations": [],
        "unknowns": dict(reasons),
        "unknown_examples": examples,
        "summary": {
            **dict(counts),
            "field_coverage": {
                key: {
                    "known": fields[key],
                    "missing": denominator - fields[key],
                    "denominator": denominator,
                }
                for key, denominator in (
                    *((key, game_frames) for key in frame_fields),
                    *((key, hero_samples) for key in hero_fields),
                )
            },
            "observed_base_and_raw_current_ranges": {
                key: dict(sorted(histogram.items()))
                for key, histogram in sorted(range_values.items())
            },
            "recorded_mask_validation": "checked against captured team words, not independent FOW",
        },
        "assumptions": {
            "daycycle_decoded": False,
            "fixed_daynight_cycle": False,
            "current_range_inferred_from_base_ranges": False,
            "flight_or_modifier_state_inferred": False,
        },
        "evidence_use": "retrospective_omniscient_diagnostic_only",
        "actual_fog_of_war": False,
        "accuracy_claimed": False,
        "action_review_allowed": False,
        "training_allowed": False,
    }


def _tree_policy(policy):
    if policy not in TREE_POLICIES:
        raise ValueError("choose an explicit initial-tree policy")


class StaticTerrain:
    """Geometry copied from caller-verified map documents; world coordinates."""

    def __init__(self, map_documents, *, exact_patch, map_manifest_sha256):
        if not isinstance(exact_patch, str) or not re.fullmatch(r"\d+\.\d+[a-z]?", exact_patch):
            raise ValueError("exact patch required")
        if not isinstance(map_manifest_sha256, str) or not re.fullmatch(
            r"[a-f0-9]{64}", map_manifest_sha256
        ):
            raise ValueError("map manifest SHA-256 required")
        self._identity = {"exact_patch": exact_patch, "map_manifest_sha256": map_manifest_sha256}
        try:
            world = map_documents["worlddata.json"]
            self.xmin, self.ymin, self.xmax, self.ymax = (
                _number(world[key], "map bound")
                for key in ("worldMinX", "worldMinY", "worldMaxX", "worldMaxY")
            )
            elevation = map_documents["elevationdata.json"]["data"]
            navigation = map_documents["gridnavdata.json"]["data"]
            entities = map_documents["mapdata.json"]["data"]
            lanes = map_documents["lanedata.json"]["features"]
        except (KeyError, TypeError) as exc:
            raise ValueError("five verified map documents required") from exc
        if (
            self.xmax < self.xmin
            or self.ymax < self.ymin
            or (self.xmax - self.xmin) % CELL
            or (self.ymax - self.ymin) % CELL
        ):
            raise ValueError("bounds must describe the 64-unit sample grid")
        self.width = int((self.xmax - self.xmin) / CELL) + 1
        self.height = int((self.ymax - self.ymin) / CELL) + 1
        if not isinstance(elevation, list) or len(elevation) != self.width:
            raise ValueError("elevation width mismatch")
        if any(not isinstance(column, list) or len(column) != self.height for column in elevation):
            raise ValueError("elevation height mismatch")
        self._elevation = tuple(
            tuple(_number(value, "elevation") for value in column) for column in elevation
        )
        if not isinstance(navigation, list) or not isinstance(entities, dict):
            raise ValueError("map navigation and entity categories required")
        blocked = set()
        for entry in navigation:
            if not isinstance(entry, dict) or "x" not in entry or "y" not in entry:
                raise ValueError("invalid navigation entry")
            point = _point((entry["x"], entry["y"]))
            cell = self.cell(point)
            if cell is None or self.centre(cell) != point or cell in blocked:
                raise ValueError("navigation entries must be unique sample centres")
            blocked.add(cell)
        self._blocked = frozenset(blocked)
        trees = []
        for entry in entities.get("ent_dota_tree", []):
            trees.append(_point((entry["x"], entry["y"])))
        self._trees = tuple(trees)
        self._tree_cells = frozenset(
            cell for point in trees if (cell := self.cell(point)) is not None
        )
        self._entities = copy.deepcopy(entities)
        self._lanes = copy.deepcopy(lanes)

    @property
    def identity(self):
        return dict(self._identity)

    def summary(self):
        return {
            **self.identity,
            "schema": "patch-static-terrain/1",
            "grid_shape": [self.width, self.height],
            "sample_bounds": [self.xmin, self.ymin, self.xmax, self.ymax],
            "grid_step": CELL,
            "blocked_navigation_cells": len(self._blocked),
            "initial_tree_cells": len(self._tree_cells),
            "coordinates": "world coordinates; replay positions require subtracting 16384",
            "tree_policies": list(TREE_POLICIES),
            "source_validation": (
                "caller verified manifest/documents; not re-verified by this pure API"
            ),
            "dynamic_terrain_known": False,
            "actual_fog_of_war": False,
            "action_review_allowed": False,
            "training_allowed": False,
        }

    def cell(self, position):
        x, y = _point(position)
        if not self.xmin <= x <= self.xmax or not self.ymin <= y <= self.ymax:
            return None
        return round((x - self.xmin) / CELL), round((y - self.ymin) / CELL)

    def centre(self, cell):
        return self.xmin + cell[0] * CELL, self.ymin + cell[1] * CELL

    def _blocking(self, cell, policy):
        return cell in self._blocked or (
            policy == "block_initial_tree_cells" and cell in self._tree_cells
        )

    def _crossed_cells(self, start, end):
        """Closed segment supercover, including both edge cells and all corner cells."""
        a = ((start[0] - self.xmin) / CELL, (start[1] - self.ymin) / CELL)
        b = ((end[0] - self.xmin) / CELL, (end[1] - self.ymin) / CELL)
        points = {0.0, 1.0}
        for lo, hi in zip(a, b, strict=True):
            if lo == hi:
                continue
            for integer in range(math.ceil(min(lo, hi) - 0.5), math.floor(max(lo, hi) - 0.5) + 1):
                fraction = (integer + 0.5 - lo) / (hi - lo)
                if 0 < fraction < 1:
                    points.add(fraction)
        crossings = sorted(points)
        samples = crossings + [
            (left + right) / 2 for left, right in zip(crossings, crossings[1:], strict=False)
        ]

        def touched(value):
            lower = math.floor(value)
            if math.isclose(value - lower, 0.5, abs_tol=1e-9, rel_tol=0):
                return lower, lower + 1
            return (round(value),)

        result = set()
        for fraction in samples:
            x, y = (lo + fraction * (hi - lo) for lo, hi in zip(a, b, strict=True))
            result.update(
                (i, j)
                for i in touched(x)
                for j in touched(y)
                if 0 <= i < self.width and 0 <= j < self.height
            )
        return result

    def segment(self, start, end, *, tree_policy):
        """Static navigation cells touched by an observed line, not the player's path."""
        _tree_policy(tree_policy)
        start, end = _point(start), _point(end)
        base = {"tree_policy": tree_policy, "dynamic_terrain_known": False}
        if self.cell(start) is None or self.cell(end) is None:
            return {**base, "status": "unknown", "reason": "endpoint_outside_sample_bounds"}
        cells = self._crossed_cells(start, end)
        blocked = sorted(cell for cell in cells if self._blocking(cell, tree_policy))
        return {
            **base,
            "status": "blocked" if blocked else "clear",
            "reason": "static_cell_intersection" if blocked else "no_static_cell_intersection",
            "tested_cells": len(cells),
            "blocked_cells": [list(cell) for cell in blocked],
            "line_length_world_units": math.dist(start, end),
        }

    def route(self, start, goal, *, tree_policy, max_expansions=100000):
        """8-neighbour A* between nearest cells, with no corner cutting or endpoint repair.

        The reported length joins cell centres. Endpoint offsets are separate: this
        is a grid route hypothesis, not a measured travel distance or arrival time.
        """
        _tree_policy(tree_policy)
        if type(max_expansions) is not int or max_expansions < 1:
            raise ValueError("max_expansions must be a positive integer")
        start, goal = _point(start), _point(goal)
        first, last = self.cell(start), self.cell(goal)
        base = {
            "tree_policy": tree_policy,
            "dynamic_terrain_known": False,
            "diagonal_corner_cutting": False,
            "blocked_endpoints_relocated": False,
        }
        if first is None or last is None:
            return {**base, "status": "unknown", "reason": "endpoint_outside_sample_bounds"}
        base["endpoint_mapping"] = {
            "start_cell": list(first),
            "goal_cell": list(last),
            "start_centre_offset": math.dist(start, self.centre(first)),
            "goal_centre_offset": math.dist(goal, self.centre(last)),
            "rounding": "nearest centre; exact half-grid ties to even index",
        }
        if self._blocking(first, tree_policy) or self._blocking(last, tree_policy):
            return {**base, "status": "blocked", "reason": "endpoint_cell_blocked"}
        distances, parents = {first: 0.0}, {}
        queue = [(math.dist(first, last) * CELL, 0.0, first)]
        expanded = 0
        while queue:
            _, cost, current = heapq.heappop(queue)
            if cost != distances.get(current):
                continue
            if current == last:
                path = [last]
                while path[-1] != first:
                    path.append(parents[path[-1]])
                path.reverse()
                return {
                    **base,
                    "status": "found",
                    "expanded_cells": expanded,
                    "centre_path_length_world_units": cost,
                    "path_cells": [list(cell) for cell in path],
                    "path_world_centres": [list(self.centre(cell)) for cell in path],
                }
            if expanded >= max_expansions:
                return {
                    **base,
                    "status": "unknown",
                    "reason": "search_budget_exhausted",
                    "expanded_cells": expanded,
                }
            expanded += 1
            i, j = current
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == dy == 0:
                        continue
                    next_cell = i + dx, j + dy
                    if not (0 <= next_cell[0] < self.width and 0 <= next_cell[1] < self.height):
                        continue
                    if self._blocking(next_cell, tree_policy):
                        continue
                    if (
                        dx
                        and dy
                        and (
                            self._blocking((i + dx, j), tree_policy)
                            or self._blocking((i, j + dy), tree_policy)
                        )
                    ):
                        continue
                    next_cost = cost + math.hypot(dx, dy) * CELL
                    if next_cost < distances.get(next_cell, math.inf):
                        distances[next_cell], parents[next_cell] = next_cost, current
                        heapq.heappush(
                            queue,
                            (next_cost + math.dist(next_cell, last) * CELL, next_cost, next_cell),
                        )
        return {
            **base,
            "status": "blocked",
            "reason": "no_static_grid_route",
            "expanded_cells": expanded,
        }

    def line_of_sight(
        self,
        source,
        target,
        *,
        sight_range,
        tree_policy,
        flying_vision,
        high_ground_threshold,
    ):
        """One source's static LOS hypothesis; no invisibility, spells or actual team FOW."""
        _tree_policy(tree_policy)
        _number(sight_range, "sight_range")
        _number(high_ground_threshold, "high_ground_threshold")
        if sight_range < 0 or high_ground_threshold < 0 or type(flying_vision) is not bool:
            raise ValueError("nonnegative range and explicit flying_vision boolean required")
        source, target = _point(source), _point(target)
        first, last = self.cell(source), self.cell(target)
        base = {
            "sight_range": sight_range,
            "flying_vision": flying_vision,
            "high_ground_threshold": high_ground_threshold,
            "tree_policy": tree_policy,
            "actual_fog_of_war": False,
        }
        if first is None or last is None:
            return {**base, "status": "unknown", "reason": "endpoint_outside_sample_bounds"}
        if math.dist(source, target) > sight_range:
            return {**base, "status": "out_of_range", "reason": "explicit_range"}
        if flying_vision:
            return {**base, "status": "clear", "reason": "explicit_flying_vision_hypothesis"}
        mine, theirs = self._elevation[first[0]][first[1]], self._elevation[last[0]][last[1]]
        if mine < 0 or theirs < 0:
            return {**base, "status": "unknown", "reason": "missing_height"}
        if theirs > mine and theirs >= high_ground_threshold:
            return {**base, "status": "blocked", "reason": "target_higher_ground"}
        cells = self._crossed_cells(source, target)
        if any(self._elevation[i][j] < 0 for i, j in cells):
            return {**base, "status": "unknown", "reason": "missing_height"}
        if any(self._elevation[i][j] > max(mine, high_ground_threshold - 1) for i, j in cells):
            return {**base, "status": "blocked", "reason": "intermediate_higher_ground"}
        if tree_policy == "block_initial_tree_cells" and cells & self._tree_cells:
            return {**base, "status": "blocked", "reason": "initial_tree_cell"}
        return {**base, "status": "clear", "reason": "static_source_line_clear"}

    def render_svg(self):
        """Deterministic north-up topology from this map; no old background image."""
        lines = [
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {self.width} {self.height + 24}" '
            'role="img">',
            "<title>Version-bound static topology; not game fog of war</title>",
            f"<metadata>{html.escape(str(self.identity))}</metadata>",
            f'<rect width="{self.width}" height="{self.height + 24}" fill="#142126"/>',
        ]
        colours = {0: "#29484b", 1: "#49604f", 2: "#71806b"}
        for j in range(self.height):
            i = 0
            while i < self.width:
                level = self._elevation[i][j]
                colour = (
                    "#17252d"
                    if (i, j) in self._blocked or level < 0
                    else colours.get(level, "#a4ab83")
                )
                end = i + 1
                while end < self.width:
                    other = self._elevation[end][j]
                    next_colour = (
                        "#17252d"
                        if (end, j) in self._blocked or other < 0
                        else colours.get(other, "#a4ab83")
                    )
                    if next_colour != colour:
                        break
                    end += 1
                lines.append(
                    f'<rect x="{i}" y="{self.height - 1 - j}" width="{end - i}" '
                    f'height="1" fill="{colour}"/>'
                )
                i = end

        def point(x, y):
            return (x - self.xmin) / CELL + 0.5, self.height - (y - self.ymin) / CELL - 0.5

        for lane in self._lanes:
            coordinates = lane["geometry"]["coordinates"]
            points = " ".join(f"{x:.4f},{y:.4f}" for x, y in (point(*p[:2]) for p in coordinates))
            lines.append(
                f'<polyline points="{points}" fill="none" stroke="#a9c9c3" '
                'stroke-width="0.35" opacity="0.7"/>'
            )
        for x, y in self._trees:
            px, py = point(x, y)
            lines.append(f'<circle cx="{px:.4f}" cy="{py:.4f}" r="0.33" fill="#172f20"/>')
        for kind, colour in (
            ("npc_dota_tower", "#ffd66b"),
            ("npc_dota_neutral_spawner", "#eeeecc"),
            ("npc_dota_unit_twin_gate", "#56dbe9"),
        ):
            for entry in self._entities.get(kind, []):
                px, py = point(entry["x"], entry["y"])
                title = html.escape(f"{kind}: {entry.get('name', '')}")
                lines.append(
                    f'<circle cx="{px:.4f}" cy="{py:.4f}" r="1.05" fill="{colour}">'
                    f"<title>{title}</title></circle>"
                )
        label = html.escape(
            f"{self._identity['exact_patch']} / CANDIDATE / north up / static topology only"
        )
        lines += [
            f'<text x="2" y="{self.height + 6}" font-size="4" fill="#e1eeee">{label}</text>',
            f'<text x="2" y="{self.height + 12}" font-size="3" fill="#b9c9c9">'
            "Yellow: towers; white: camp spawners; cyan: twin gates. No region labels.</text>",
            f'<text x="2" y="{self.height + 18}" font-size="3" fill="#b9c9c9">'
            f"World x: {self.xmin}..{self.xmax}; y: {self.ymin}..{self.ymax}; "
            f"grid: {CELL}; initial trees only, no game fog.</text>",
            "</svg>",
        ]
        return "\n".join(lines) + "\n"


def run_diagnostics(terrain, state_rows, *, duration, tree_policy, visibility_observations=None):
    """Describe observed one-second chords and explicitly supplied visibility comparisons.

    Adjacent positions form a chord, not a reconstruction of walking. Blocked chords
    can be movement spells, turns, flying, changed trees or sampling effects. Every
    supplied frame is retrospective omniscient evidence, never a decision feature.
    """
    if not isinstance(terrain, StaticTerrain):
        raise ValueError("StaticTerrain required")
    if type(duration) is not int or duration < 0:
        raise ValueError("nonnegative integer duration required")
    _tree_policy(tree_policy)
    counts, per_hero = Counter(), {}
    previous, identity, expected = {}, None, 0
    for row in state_rows:
        if not isinstance(row, dict) or type(row.get("t")) is not int or row["t"] != expected:
            raise ValueError("state must cover ordered game seconds 0..duration")
        if (
            expected > duration
            or not isinstance(row.get("heroes"), list)
            or len(row["heroes"]) != 10
        ):
            raise ValueError("state must contain ten hero bodies within the game window")
        current, identities = {}, {}
        for hero in row["heroes"]:
            if not isinstance(hero, dict):
                raise ValueError("hero body must be an object")
            player, name, team = hero.get("player_id"), hero.get("hero"), hero.get("team")
            if (
                type(player) is not int
                or not 0 <= player <= 9
                or player in identities
                or not isinstance(name, str)
                or type(team) is not int
                or team not in (2, 3)
            ):
                raise ValueError("invalid hero identity")
            identities[player] = (name, team)
            hp, life = hero.get("hp"), hero.get("life_state")
            _number(hp, "hp")
            if hp < 0 or type(life) is not int or life < 0:
                raise ValueError("invalid hero life state")
            pos = hero.get("pos")
            world = replay_to_world(pos) if pos is not None else None
            counts["body_seconds"] += 1
            if life != 0 or hp == 0:
                counts["nonliving_body_seconds"] += 1
                continue
            if world is None:
                counts["living_missing_position_seconds"] += 1
                continue
            current[player] = (world, hero.get("move_speed"))
            if player not in previous:
                continue
            old, speed = previous[player]
            displacement = math.dist(old, world)
            if displacement == 0:
                counts["stationary_pairs"] += 1
                continue
            counts["moving_pairs"] += 1
            verdict = terrain.segment(old, world, tree_policy=tree_policy)
            counts[f"moving_{verdict['status']}"] += 1
            per_hero.setdefault(name, Counter())[verdict["status"]] += 1
            if speed is None:
                counts["moving_pairs_with_unknown_recorded_speed"] += 1
            else:
                _number(speed, "move_speed")
                if speed < 0:
                    raise ValueError("negative move_speed")
                if displacement > speed:
                    counts["one_second_displacement_over_recorded_start_speed"] += 1
        if identity is not None and identities != identity:
            raise ValueError("hero identity changed")
        identity, previous = identities, current
        expected += 1
    if expected != duration + 1:
        raise ValueError("incomplete state game window")
    visibility = {"status": "not_supplied", "observations": 0}
    if visibility_observations is not None:
        cross = Counter()
        total = 0
        for observation in visibility_observations:
            if (
                not isinstance(observation, dict)
                or type(observation.get("t")) is not int
                or not 0 <= observation["t"] <= duration
            ):
                raise ValueError("visibility observation outside game window")
            if "recorded_visible" not in observation:
                raise ValueError("recorded visibility must be supplied or explicitly unknown")
            truth = observation["recorded_visible"]
            if truth is not None and type(truth) is not bool:
                raise ValueError("recorded visibility must be a boolean or explicit unknown")
            try:
                verdict = terrain.line_of_sight(
                    observation["source"],
                    observation["target"],
                    sight_range=observation["sight_range"],
                    tree_policy=tree_policy,
                    flying_vision=observation["flying_vision"],
                    high_ground_threshold=observation["high_ground_threshold"],
                )
            except KeyError as exc:
                raise ValueError("visibility comparison requires explicit LOS assumptions") from exc
            cross[f"static_{verdict['status']}_recorded_{truth}"] += 1
            total += 1
        visibility = {
            "status": "descriptive_comparison",
            "observations": total,
            "counts": dict(cross),
            "accuracy_claimed": False,
            "note": "A single source's static LOS is not the team's recorded target visibility.",
        }
    return {
        "schema": "patch-terrain-diagnostic/1",
        "terrain": terrain.summary(),
        "window": {"start": 0, "end_inclusive": duration, "seconds": expected},
        "tree_policy": tree_policy,
        "movement": dict(counts),
        "per_hero_moving_chords": {name: dict(value) for name, value in sorted(per_hero.items())},
        "visibility": visibility,
        "evidence_use": "retrospective_omniscient_geometry_diagnostic_only",
        "action_review_allowed": False,
        "training_allowed": False,
        "limits": [
            "One-second chords are not observed navigation paths.",
            "Initial trees, no dynamic blockers, unit hulls or movement mechanics.",
            "Recorded move_speed need not include every effective movement modifier.",
            "Static LOS cannot prove visibility, hidden enemies, or safe routes.",
        ],
    }
