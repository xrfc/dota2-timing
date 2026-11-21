"""Approximate team vision from what a replay records (shared base, exploratory, U152).

A replay does not store the fog of war. This module rebuilds an approximation: every
vision source of a team (heroes, observer wards, standing towers, the ancient, the fountain,
the front of each creep wave or every lane creep) sees a circle, minus what terrain
hides. Three models, each adding one rule, so the
check against the replay's own "was this hero visible to the other team" record shows what
each rule is worth:

* radius   inside the source's range
* height   and the target does not stand on higher ground than the source
* sight    and nothing on the straight line hides it: a tree, or ground higher than the source

Known gaps: creeps other than the wave front unless the creep side file is given,
summons, outposts, watchers, vision from
spells and items, flying vision, trees that were cut, heroes with unusual vision ranges
and invisibility. Nothing here is model input yet.
"""

import gzip
import json
import math

CELL = 64
WORLD_MIN = -10464
SIZE = 327
OFFSET = 16384  # replay cell space = world + OFFSET
STEP = 32  # ray-march step along the line of sight
DAY_SECONDS = 300  # a day half and a night half of five minutes each, day first
MODELS = ("radius", "height", "sight")
# (day, night) ranges. Heroes vary a little; these are the common values.
RANGE = {
    "hero": (1800, 800),
    "observer": (1600, 1600),
    "creep": (750, 750),
    # Buildings, from the map data (checked 2026-11-13): tier-1 towers see less at night.
    "tower1": (1900, 800),
    "tower": (1900, 1100),
    "fort": (2600, 2600),
    "fountain": (1800, 1800),
    "watcher": (800, 450),  # a Watcher gives its holder vision (map data)
    "illusion": (1800, 800),  # sees like its hero
    "summon": (800, 800),  # a guess: summons differ by unit and are not looked up
}


def read_creep_samples(path, match_id, schema):
    """Yield checked per-second records from a creep-only or extras capture."""
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        header = json.loads(stream.readline())
        if not isinstance(header, dict) or (header.get("schema"), header.get("match_id")) != (
            schema,
            match_id,
        ):
            raise ValueError(f"{path}: unexpected creep capture schema or match")
        seconds = set()
        for row in map(json.loads, stream):
            second = row.get("t") if isinstance(row, dict) else None
            if (
                type(second) is not int
                or second in seconds
                or not isinstance(row.get("creeps"), list)
            ):
                raise ValueError(f"{path}: invalid creep sample at {second}")
            seconds.add(second)
            yield row


def read_creep_positions(path, match_id):
    """An absent second has unknown creep positions."""
    return {
        row["t"]: row["creeps"] for row in read_creep_samples(path, match_id, "gem-creep-capture/1")
    }


def is_day(second):
    return second < 0 or (second // DAY_SECONDS) % 2 == 0


def cell_of(x, y):
    """Grid cell of a replay position."""
    return round((x - OFFSET - WORLD_MIN) / CELL), round((y - OFFSET - WORLD_MIN) / CELL)


class Terrain:
    """Height level and trees per 64-unit cell (map reference data, checked 2026-11-13)."""

    def __init__(self, elevation, trees):
        self.elevation = elevation  # [x index][y index]
        self.trees = {cell_of(x + OFFSET, y + OFFSET) for x, y in trees}

    def level(self, x, y):
        i, j = cell_of(x, y)
        if 0 <= i < SIZE and 0 <= j < SIZE:
            return self.elevation[i][j]
        return -128

    def clear(self, source, target, height):
        """No tree and no ground above `height` strictly between source and target."""
        distance = math.dist(source, target)
        steps = int(distance // STEP)
        first, last = cell_of(*source), cell_of(*target)
        for n in range(1, steps):
            share = n / steps
            x = source[0] + (target[0] - source[0]) * share
            y = source[1] + (target[1] - source[1]) * share
            cell = cell_of(x, y)
            if cell in (first, last):
                continue
            if cell in self.trees or self.elevation[cell[0]][cell[1]] > height:
                return False
        return True


def sees(source, target, kind, second, terrain, model, high_from=1):
    """Whether one source at `source` sees a ground target at `target` under `model`.

    `high_from` is the lowest level that counts as higher ground: with 1 the river (level
    0) cannot see the banks, with 2 only real high ground hides.
    """
    reach = RANGE[kind][0 if is_day(second) else 1]
    if math.dist(source, target) > reach:
        return False
    if model == "radius":
        return True
    mine, theirs = terrain.level(*source), terrain.level(*target)
    if theirs > mine and theirs >= high_from:
        return False
    if model == "height":
        return True
    return terrain.clear(source, target, max(mine, high_from - 1))


def building_kind(building):
    """Vision class of a standing building from map-zones (towers, forts) or a fountain."""
    name = building.get("name") or "fountain"
    if "tower1" in name:
        return "tower1"
    return "tower" if "tower" in name else "fort" if "fort" in name else "fountain"


def extra_sources(team, watchers=(), summons=()):
    """[(kind, (x, y))] from the extras side file and state v3 (U154).

    `watchers` is [[x, y, holder team or 0], ...], `summons` the parser-v3 world summons.
    """
    sources = [("watcher", (x, y)) for x, y, holder in watchers if holder == team]
    sources += [
        ("illusion" if s.get("illusion") else "summon", tuple(s["pos"]))
        for s in summons
        if s.get("team") == team and s.get("pos")
    ]
    return sources


def team_sources(team, second, tracks, wards, towers, fronts, creeps=None):
    """[(kind, (x, y))] of what gives `team` vision at `second`.

    `tracks` is gank_events.hero_tracks, `wards` gank_review.ward_spans, `towers` the
    standing buildings [{team, x, y, name}] (towers, the ancients, the fountains),
    `fronts` the parser-v3 lane fronts of that second.
    `creeps`, when given, is every lane creep of that second as [team, x, y] (the creep
    side file, U153) and replaces the wave fronts.
    """
    sources = [
        ("hero", track["pos"][second])
        for track in tracks.values()
        if track["team"] == team and second in track["pos"]
    ]
    sources += [
        ("observer", (w["x"], w["y"]))
        for w in wards
        if w["team"] == team and w["type"] == "observer" and w["start"] <= second <= w["end"]
    ]
    sources += [(building_kind(t), (t["x"], t["y"])) for t in towers if t["team"] == team]
    if creeps is not None:
        return sources + [("creep", (x, y)) for side, x, y in creeps if side == team]
    prefix = "radiant_" if team == 2 else "dire_"
    sources += [
        ("creep", tuple(wave["front"]))
        for lane, wave in (fronts or {}).items()
        if lane.startswith(prefix) and wave and wave.get("front")
    ]
    return sources


def visible(target, sources, second, terrain, model, high_from=1):
    return any(
        sees(spot, target, kind, second, terrain, model, high_from) for kind, spot in sources
    )
