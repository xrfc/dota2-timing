"""Map knowledge (shared base): draft named regions from the map data (design T2, U145).

    PYTHONPATH=src .venv/bin/python scripts/build_map_knowledge.py draft \
        --out reports/map-regions-draft-2026-11-13

`draft` reads the local map reference (`data/map-reference-2026-10-26-v1/coordinates/data`,
upstream leamare/dota-map-coordinates@f793787e, "7.41") and labels every walkable 64-unit
cell with a region: bases, the river, the two Roshan pits (inside the pit wall only), the
three lanes split by side and tower, and per side the triangle, main jungle and snack
street as the user named them (2026-11-13), plus landmarks (camps with their type,
watchers, outposts, tormentors, cliff platforms and more). It writes `regions-grid.json`
and `draft.png` (regions and landmarks over the map image with their names) for the user
to correct. Everything here is a draft
(`basis: assistant_draft`); nothing reads it yet. See docs/map-knowledge-design.md.
"""

import argparse
import hashlib
import json
import math
import os
import tempfile
from collections import Counter, deque
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = ROOT / "data/map-reference-2026-10-26-v1"
SOURCE = REFERENCE_DIR / "coordinates/data"
MAP_IMAGE = REFERENCE_DIR / "gem/assets/maps/Game_map_7.41.jpg"
FONT = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
FONT_FALLBACK = Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc")
CELL = 64
WORLD_MIN = -10464
SIZE = 327
OFFSET = 16384  # replay cell space = world + OFFSET
LANE_HALF_WIDTH = 700
TOWER_RANGE = 700  # tower attack range
LANE_BAND = 3000  # |y - x| beyond this is the top or bottom part of the river
BASE_LEVEL = 2  # the base plateaus (level 2) and fountains (level 3); low ground is 1, water 0
TEAM = {2: "radiant", 3: "dire"}
TEAM_ZH = {"radiant": "天辉", "dire": "夜魇", "neutral": ""}
LANE_ZH = {"top": "上路", "mid": "中路", "bot": "下路"}


def read(name):
    return json.loads((SOURCE / name).read_text(encoding="utf-8"))


def index(value):
    return round((value - WORLD_MIN) / CELL)


def world(i):
    return i * CELL + WORLD_MIN


def segment_distance(p, a, b):
    ax, ay, bx, by = *a, *b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0 if not length else max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def flood(starts, passable):
    seen = set(starts)
    queue = deque(starts)
    while queue:
        i, j = queue.popleft()
        for cell in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if cell not in seen and passable(cell):
                seen.add(cell)
                queue.append(cell)
    return seen


def walking_steps(start, walkable):
    """{cell: steps on foot from start}, moving between edge-adjacent walkable cells."""
    steps = {start: 0}
    queue = deque([start])
    while queue:
        i, j = queue.popleft()
        for cell in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if cell in walkable and cell not in steps:
                steps[cell] = steps[(i, j)] + 1
                queue.append(cell)
    return steps


def nearest_walkable(point, walkable):
    i, j = index(point[0]), index(point[1])
    return min(walkable, key=lambda c: (c[0] - i) ** 2 + (c[1] - j) ** 2)


SAFE_LANE = {"radiant": "bot", "dire": "top"}
CAMPS = ROOT / "knowledge/awareness/map-zones-v1.json"
CAMP_ZH = {
    "small": "小野", "medium": "中野", "large": "大野", "ancient": "远古",
    "flooded_small": "小野(蛙)", "flooded_medium": "中野(蛙)",
}  # fmt: skip
PIT_WALL_REACH = 1000  # a pit wall is the small blocked patch this close to a pit centre
PIT_CENTRES = ((2831, -2740), (-3000, 2250))  # spawner in the data; Roshan kills in replays
TORMENTORS = ((-7680, 6336, "data"), (7680, -6336, "replay kills and symmetry"))
PLATFORM_LEVEL = 3  # isolated walkable cells this high are cliff platforms


def components(cells):
    seen, result = set(), []
    for cell in cells:
        if cell not in seen:
            part = flood([cell], lambda c: c in cells)
            seen |= part
            result.append(part)
    return result


def centre(cells):
    return (
        sum(world(i) for i, _ in cells) / len(cells),
        sum(world(j) for _, j in cells) / len(cells),
    )


def hull(points):
    """Convex hull (monotone chain) of (x, y) points, counter-clockwise."""
    points = sorted(set(points))

    def half(seq):
        out = []
        for p in seq:
            while (
                len(out) >= 2
                and (
                    (out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                    - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])
                )
                <= 0
            ):
                out.pop()
            out.append(p)
        return out[:-1]

    return half(points) + half(reversed(points))


def inside(point, polygon):
    return all(
        (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0]) >= 0
        for a, b in zip(polygon, polygon[1:] + polygon[:1], strict=True)
    )


def path_distance(point, path):
    return min(segment_distance(point, a, b) for a, b in zip(path, path[1:], strict=False))


def nearest_on_path(point, path):
    best = None
    for a, b in zip(path, path[1:], strict=False):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = dx * dx + dy * dy
        t = max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length))
        q = (a[0] + t * dx, a[1] + t * dy)
        d = math.hypot(point[0] - q[0], point[1] - q[1])
        if best is None or d < best[0]:
            best = (d, q)
    return best[1]


def along(point, path):
    """Distance along `path` (from its first point) of the path point nearest to `point`."""
    best, walked = None, 0.0
    for a, b in zip(path, path[1:], strict=False):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        t = max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length**2))
        d = math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dy)
        if best is None or d < best[0]:
            best = (d, walked + t * length)
        walked += length
    return best[1]


def lane_part(point, side, path, towers, lane):
    """Which stretch of his own side of a lane a point is on (user, U148).

    Under a tower means inside its attack range. The stretches outside tower range are
    their own regions: in front of the tier-1 tower (where the waves meet), between the
    tier-1 and tier-2 towers (where an offlaner cuts the wave), and behind the tier-2.
    """
    spot = {t[2]: (t[3]["x"], t[3]["y"]) for t in towers if t[0] == side and t[1] == lane}
    for tier in "12":
        if math.dist(point, spot[tier]) <= TOWER_RANGE:
            return f"t{tier}"
    # The path runs from the Radiant base to the Dire base; measure from his own base.
    sign = 1 if side == "radiant" else -1
    here, one, two = (sign * along(p, path) for p in (point, spot["1"], spot["2"]))
    return "front" if here > one else "between" if here > two else "behind"


def label_cells():
    """({(i, j): region id} for every walkable cell, landmarks)."""
    blocked = {(index(p["x"]), index(p["y"])) for p in read("gridnavdata.json")["data"]}
    elevation = read("elevationdata.json")["data"]  # [x index][y index], checked against cliffs
    entities = read("mapdata.json")["data"]
    on_map = {(i, j) for i in range(SIZE) for j in range(SIZE) if elevation[i][j] != -128}
    walkable = on_map - blocked
    level = lambda c: elevation[c[0]][c[1]]  # noqa: E731
    fountains = {TEAM[f["team"]]: (f["x"], f["y"]) for f in entities["ent_dota_fountain"]}
    towers = [
        (TEAM[t["team"]], t["name"].rsplit("_", 1)[-1], t["name"].split("tower")[1][0], t)
        for t in entities["npc_dota_tower"]
    ]
    lanes = {
        f["properties"]["name"].rsplit("_", 1)[-1]: f["geometry"]["coordinates"]
        for f in read("lanedata.json")["features"]
        if "_good_" in f["properties"]["name"]
    }
    steps = {
        side: walking_steps(nearest_walkable(fountain, walkable), walkable)
        for side, fountain in fountains.items()
    }
    reachable = set(steps["radiant"])

    def side_at(cell):
        near = {side: steps[side].get(cell, 10**9) for side in steps}
        if near["radiant"] == near["dire"]:
            x, y = world(cell[0]), world(cell[1])
            near = {s: math.hypot(x - f[0], y - f[1]) for s, f in fountains.items()}
        return min(near, key=near.get)

    regions = {}
    # 1. Bases: the plateau the fountain stands on.
    # The plateau runs on past the offlane tier-2 tower into a strip of jungle (the
    # offlane snack street, user U149), so the base ends at the user's high-ground circle:
    # the furthest tier-3 tower plus its attack range (U140).
    for side, fountain in fountains.items():
        start = nearest_walkable(fountain, walkable)
        reach = TOWER_RANGE + max(
            math.dist(fountain, (t[3]["x"], t[3]["y"]))
            for t in towers
            if t[0] == side and t[2] == "3"
        )
        for cell in flood([start], lambda c: c in walkable and level(c) >= BASE_LEVEL):
            if math.dist((world(cell[0]), world(cell[1])), fountain) <= reach:
                regions[cell] = f"{side}_base"
    # 2. Roshan pits: only the ground enclosed by the pit wall (user, 2026-11-13).
    walls = [part for part in components(on_map & blocked) if len(part) < 400]
    pits = []
    for pit in PIT_CENTRES:
        wall = min(walls, key=lambda part: math.dist(centre(part), pit))
        if math.dist(centre(wall), pit) > PIT_WALL_REACH:
            raise SystemExit(f"no pit wall near {pit}")
        outline = hull([(world(i), world(j)) for i, j in wall])
        cells = [c for c in walkable if inside((world(c[0]), world(c[1])), outline)]
        name = "roshan_pit_bot" if pit[0] > 0 else "roshan_pit_top"
        for cell in cells:
            regions[cell] = name
        pits.append((name, centre(cells)))
    # 3. The river: the water the power runes float on. Other water is ordinary ground.
    water = {c for c in reachable if level(c) == 0 and c not in regions}
    runes = [(r["x"], r["y"]) for r in entities["dota_item_rune_spawner_powerup"]]
    river = set()
    for part in components(water):
        if any(math.dist(centre([c]), rune) < 600 for c in part for rune in runes):
            river |= part
    for cell in river:
        x, y = world(cell[0]), world(cell[1])
        part = "top" if y - x > LANE_BAND else "bot" if x - y > LANE_BAND else "mid"
        regions[cell] = f"river_{part}"
    # 4. Triangle: the hill the outpost stands on (user: "有传送锅的高坡").
    hills = components({c for c in reachable if level(c) >= BASE_LEVEL and c not in regions})
    for outpost in entities["npc_dota_watch_tower"]:
        spot = (outpost["x"], outpost["y"])
        hill = min(hills, key=lambda part: min(math.dist(centre([c]), spot) for c in part))
        side = side_at(nearest_walkable(spot, hill))
        for cell in hill:
            regions[cell] = f"{side}_triangle"
    # 5. Lanes, then the jungle by side, half and whether it lies outside the lane.
    for cell in reachable:
        if cell in regions:
            continue
        x, y = world(cell[0]), world(cell[1])
        side = side_at(cell)
        lane = min(lanes, key=lambda name: path_distance((x, y), lanes[name]))
        if path_distance((x, y), lanes[lane]) <= LANE_HALF_WIDTH:
            part = lane_part((x, y), side, lanes[lane], towers, lane)
            regions[cell] = f"{side}_{lane}_{part}"
            continue
        half = "top" if y > x else "bot"
        on_lane = nearest_on_path((x, y), lanes[half])
        outer = max(abs(x), abs(y)) > max(abs(on_lane[0]), abs(on_lane[1]))
        if half == SAFE_LANE[side]:
            regions[cell] = f"{side}_snack_street" if outer else f"{side}_main_jungle"
        elif not outer:
            regions[cell] = f"{side}_off_jungle"
        else:
            # Outside the offlane: beside the towers it is the offlane snack street (camps
            # and the wisdom shrine); past the tier-1 tower it is the lotus pool corner.
            past = lane_part((x, y), side, lanes[half], towers, half) == "front"
            regions[cell] = f"{side}_lotus" if past else f"{side}_off_snack_street"
    # 6. Low ground outside the river (user U150: "低洼"). The hollow a tormentor stands
    # in is its own region, the tormentor pit; the other hollows stay part of their region
    # and get a landmark.
    hollows = components(
        {c for c in reachable if level(c) == 0 and not regions[c].startswith(("river", "roshan"))}
    )
    low_marks = []
    for part in hollows:
        owner = [t for t in TORMENTORS if (index(t[0]), index(t[1])) in part]
        if owner:
            side = side_at(nearest_walkable(owner[0][:2], part))
            for cell in part:
                regions[cell] = f"{side}_tormentor_pit"
        elif len(part) >= 60:
            low_marks.append(("low", "低洼", *centre(part)))
            # The hollow around a wisdom shrine belongs to the shrine's snack street as a
            # whole (user U151), not half to the lotus corner.
            shrine = [
                e
                for e in entities["npc_dota_xp_fountain"]
                if nearest_walkable((e["x"], e["y"]), reachable) in part
            ]
            if shrine:
                side = side_at(nearest_walkable((shrine[0]["x"], shrine[0]["y"]), part))
                for cell in part:
                    if regions[cell].endswith(("_lotus", "_off_snack_street")):
                        regions[cell] = f"{side}_off_snack_street"
    # 7. Cells nobody can walk to (cliff platforms, pedestals) take the nearest region.
    labelled = list(regions)
    platforms = []
    for part in components(walkable - reachable):
        spot = centre(part)
        near = min(
            labelled, key=lambda c: (world(c[0]) - spot[0]) ** 2 + (world(c[1]) - spot[1]) ** 2
        )
        for cell in part:
            regions[cell] = regions[near]
        if min(level(c) for c in part) >= PLATFORM_LEVEL and len(part) >= 4:
            platforms.append(spot)
    camps = json.loads(CAMPS.read_text(encoding="utf-8"))["camps"]
    marks = [("camp", CAMP_ZH[c["type"]], c["x"] - OFFSET, c["y"] - OFFSET) for c in camps]
    # High ground outside the bases (user: "高坡"): plateaus of level 2 one can walk onto.
    plateaus = {c for c in reachable if level(c) >= BASE_LEVEL and "base" not in regions[c]}
    marks += [("hill", "高坡", *centre(part)) for part in components(plateaus) if len(part) >= 60]
    marks += [
        ("shop", "神秘商店", e["x"], e["y"])
        for e in entities["ent_dota_shop"]
        if "base" not in regions[nearest_walkable((e["x"], e["y"]), walkable)]
    ]
    marks += [("platform", "高台", x, y) for x, y in platforms] + low_marks
    marks += [("roshan", "肉山", x, y) for _, (x, y) in pits]
    marks += [("tormentor", "魔方", x, y) for x, y, _ in TORMENTORS]
    for kind, key, name in (
        ("watcher", "npc_dota_lantern", "观察者"),
        ("outpost", "npc_dota_watch_tower", "前哨"),
        ("gate", "npc_dota_unit_twin_gate", "传送门"),
        ("lotus", "npc_dota_lotus_pool", "莲花池"),
        ("shrine", "npc_dota_xp_fountain", "智慧神符"),
        ("bounty", "dota_item_rune_spawner_bounty", "赏金符"),
        ("rune", "dota_item_rune_spawner_powerup", "强化符"),
    ):
        marks += [(kind, name, e["x"], e["y"]) for e in entities[key]]
    # 8. What cannot be walked (user U154): cliffs are the blocked cells of the grid;
    # trees are separate entities. Ramps are where one can walk between two height levels,
    # which is the only way onto a plateau.
    cliffs = on_map & blocked
    trees = {(index(t["x"]), index(t["y"])) for t in entities["ent_dota_tree"]}
    ramp_cells = {
        cell
        for cell in reachable
        if level(cell) in (1, 2)
        and any(
            other in reachable and {level(cell), level(other)} == {1, 2}
            for other in (
                (cell[0] + 1, cell[1]),
                (cell[0] - 1, cell[1]),
                (cell[0], cell[1] + 1),
                (cell[0], cell[1] - 1),
            )
        )
    }
    ramps = [part for part in components(ramp_cells) if len(part) >= 4]
    marks += [("ramp", "坡道", *centre(part)) for part in ramps]
    terrain = {
        "cliffs": cliffs,
        "trees": trees - cliffs,
        "ramps": {c for part in ramps for c in part},
    }
    return regions, marks, {cell: level(cell) for cell in regions}, terrain


LANE_PART_ZH = {
    "t1": "一塔下", "t2": "二塔下", "front": "一塔外", "between": "一二塔间", "behind": "二塔后",
}  # fmt: skip
REGION_ZH = {
    "base": ("高地", "high_ground"),
    "triangle": ("三角区", "jungle"),
    "main_jungle": ("主野区", "jungle"),
    "snack_street": ("小吃街", "jungle"),
    "off_jungle": ("神秘商店区", "jungle"),  # no camps, only the secret shop; assistant's name
    "off_snack_street": ("劣势路小吃街", "jungle"),  # user's name (also: 经验神龛小吃街)
    "tormentor_pit": ("魔方坑", "jungle"),  # the hollow the tormentor stands in (user U150)
    "lotus": ("莲花池区", "jungle"),  # the corner past the offlane tier-1 tower; assistant's name
}


def describe(region):
    """Chinese name, owner and kind for a draft region id."""
    if region.startswith("roshan_pit"):
        return ("肉山坑(上)" if region.endswith("top") else "肉山坑(下)"), "neutral", "roshan"
    side, rest = region.split("_", 1)
    if side == "river":
        return f"河道{LANE_ZH[rest][0]}段", "neutral", "river"
    if rest in REGION_ZH:
        name, kind = REGION_ZH[rest]
        return f"{TEAM_ZH[side]}{name}", side, kind
    lane, part = rest.split("_")
    return f"{TEAM_ZH[side]}{LANE_ZH[lane]}{LANE_PART_ZH[part]}", side, "lane"


def draw(regions, marks, levels, terrain, path, scale=0.22):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.open(MAP_IMAGE).convert("RGB")
    k = 8356 / 18322
    image = image.resize((round(image.width * scale), round(image.height * scale)))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    pen = ImageDraw.Draw(overlay)
    names = sorted(set(regions.values()))
    # One colour family per kind and side, so the picture reads at a glance; the white
    # borders, not the shades, separate neighbouring regions of one family.
    family = {
        ("lane", "radiant"): (255, 200, 60), ("lane", "dire"): (255, 120, 40),
        ("jungle", "radiant"): (70, 210, 110), ("jungle", "dire"): (190, 90, 220),
        ("river", "neutral"): (60, 130, 255),
        ("high_ground", "radiant"): (40, 230, 230), ("high_ground", "dire"): (240, 50, 70),
        ("roshan", "neutral"): (255, 255, 255),
    }  # fmt: skip
    palette = {}
    for name in names:
        _, owner, kind = describe(name)
        palette[name] = (*family[(kind, owner)], 85)

    def pixel(x, y):
        return (261 + (x + OFFSET - 7487) * k) * scale, ((26015 - (y + OFFSET)) * k) * scale

    half = CELL / 2
    sums = {}
    for (i, j), name in regions.items():
        x, y = world(i), world(j)
        left, top = pixel(x - half, y + half)
        right, bottom = pixel(x + half, y - half)
        pen.rectangle([left, top, right, bottom], fill=palette[name])
        total = sums.setdefault(name, [0, 0, 0])
        total[0] += x
        total[1] += y
        total[2] += 1
    for kind, colour in (
        ("cliffs", (20, 20, 20, 150)),
        ("trees", (0, 70, 20, 150)),
        ("ramps", (255, 60, 200, 220)),
    ):
        for i, j in terrain[kind]:
            x, y = world(i), world(j)
            left, top = pixel(x - half, y + half)
            right, bottom = pixel(x + half, y - half)
            pen.rectangle([left, top, right, bottom], fill=colour)
    for (i, j), name in regions.items():  # white line wherever two regions meet
        x, y = world(i), world(j)
        if regions.get((i + 1, j), name) != name:
            pen.line([pixel(x + half, y - half), pixel(x + half, y + half)], fill="white", width=2)
        if regions.get((i, j + 1), name) != name:
            pen.line([pixel(x - half, y + half), pixel(x + half, y + half)], fill="white", width=2)
    for (i, j), height in levels.items():  # yellow line around high ground
        if height < BASE_LEVEL:
            continue
        x, y = world(i), world(j)
        for di, dj, a, b in (
            (1, 0, (x + half, y - half), (x + half, y + half)),
            (-1, 0, (x - half, y - half), (x - half, y + half)),
            (0, 1, (x - half, y + half), (x + half, y + half)),
            (0, -1, (x - half, y - half), (x + half, y - half)),
        ):
            if levels.get((i + di, j + dj), 0) < BASE_LEVEL:
                pen.line([pixel(*a), pixel(*b)], fill=(255, 235, 0, 255), width=2)
    for (i, j), height in levels.items():  # light blue line around low ground off the river
        if height != 0 or regions[(i, j)].startswith(("river", "roshan")):
            continue
        x, y = world(i), world(j)
        for di, dj, a, b in (
            (1, 0, (x + half, y - half), (x + half, y + half)),
            (-1, 0, (x - half, y - half), (x - half, y + half)),
            (0, 1, (x - half, y + half), (x + half, y + half)),
            (0, -1, (x - half, y - half), (x + half, y - half)),
        ):
            if levels.get((i + di, j + dj), 1) != 0:
                pen.line([pixel(*a), pixel(*b)], fill=(120, 230, 255, 255), width=2)
    image = Image.alpha_composite(image.convert("RGBA"), overlay)
    pen = ImageDraw.Draw(image)
    font_path = FONT if FONT.exists() else FONT_FALLBACK
    font = ImageFont.truetype(str(font_path), 20)
    for name, (sx, sy, count) in sums.items():
        centre = (sx / count, sy / count)
        # put the label on the region cell closest to the centroid, so it sits inside
        cell = min(
            (c for c, n in regions.items() if n == name),
            key=lambda c: (world(c[0]) - centre[0]) ** 2 + (world(c[1]) - centre[1]) ** 2,
        )
        px, py = pixel(world(cell[0]), world(cell[1]))
        text = describe(name)[0]
        box = pen.textbbox((px, py), text, font=font, anchor="mm")
        pen.rectangle([box[0] - 3, box[1] - 2, box[2] + 3, box[3] + 2], fill=(0, 0, 0, 190))
        pen.text((px, py), text, font=font, anchor="mm", fill=(255, 255, 255, 255))
    small = ImageFont.truetype(str(font_path), 14)
    dot = {
        "camp": (255, 230, 80), "platform": (255, 255, 255), "roshan": (255, 90, 90),
        "tormentor": (255, 90, 255), "watcher": (90, 255, 255), "outpost": (255, 160, 60),
        "hill": (255, 235, 0), "shop": (255, 255, 255), "low": (120, 230, 255),
        "ramp": (255, 60, 200),
    }  # fmt: skip
    for kind, text, x, y in marks:
        px, py = pixel(x, y)
        colour = dot.get(kind, (200, 200, 200))
        pen.ellipse([px - 5, py - 5, px + 5, py + 5], fill=colour, outline=(0, 0, 0))
        pen.text((px + 7, py - 9), text, font=small, fill=colour, stroke_width=2,
                 stroke_fill=(0, 0, 0))  # fmt: skip
    image.convert("RGB").save(path, quality=88)


def draft(args):
    args.out.mkdir(parents=True, exist_ok=False)
    regions, marks, levels, terrain = label_cells()
    counts = Counter(regions.values())
    table = [
        {"id": name, "name_zh": describe(name)[0], "owner": describe(name)[1],
         "kind": describe(name)[2], "cells": counts[name], "basis": "assistant_draft"}
        for name in sorted(counts)
    ]  # fmt: skip
    value = {
        "schema": "map-regions-draft/1",
        "patch": "7.41 (upstream statement; grid checked against 7.41f replays)",
        "coordinates": "world units; replay cell space = world + 16384; cells are 64 units",
        "source": "leamare/dota-map-coordinates@f793787ecf402f52c9e698da260b02f041256898",
        "regions": table,
        "landmarks": [
            {"kind": kind, "name_zh": name, "x": round(x), "y": round(y)}
            for kind, name, x, y in marks
        ],
        "elevation": "level per cell: 0 water, 1 low ground, 2 high ground, 3+ fountain, platform",
        "cells": [[i, j, name, levels[(i, j)]] for (i, j), name in sorted(regions.items())],
        "not_walkable": "cliffs are blocked grid cells; trees are tree entities, which the "
        "grid does not block, so a cell may be both walkable and hold a tree",
        "cliffs": sorted(terrain["cliffs"]),
        "trees": sorted(terrain["trees"]),
        "ramps": sorted(terrain["ramps"]),
    }
    (args.out / "regions-grid.json").write_text(
        json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    draw(regions, marks, levels, terrain, args.out / "draft.png")
    print(f"{len(regions)} walkable cells in {len(table)} regions -> {args.out}")
    print("landmarks", dict(Counter(kind for kind, *_ in marks)))
    print("terrain", {kind: len(cells) for kind, cells in terrain.items()})
    for row in table:
        print(f"  {row['id']:24} {row['name_zh']:12} {row['cells']}")


# SHA-256 of the raw blobs at the repository's two original map reference commits.
COORDINATES_SOURCE = (
    "https://raw.githubusercontent.com/leamare/dota-map-coordinates/"
    "f793787ecf402f52c9e698da260b02f041256898"
)
GEM_MAP_SOURCE = (
    "https://raw.githubusercontent.com/whanyu1212/gem-dota/25fb97dd90973b92e53fcbf05880a4cfe469f329"
)
REVIEW_MAP_FILES = {
    "coordinates/data/mapdata.json": (
        f"{COORDINATES_SOURCE}/data/mapdata.json",
        111925,
        "33d7ce9109cb940e0a72e1d96235b315b63a05879f4c7e224413f48375a59076",
    ),
    "coordinates/data/elevationdata.json": (
        f"{COORDINATES_SOURCE}/data/elevationdata.json",
        251406,
        "01b7898deba8a5ff2d853a721765372d847d9cfdd24604aed38be564816182fc",
    ),
    "gem/assets/maps/Game_map_7.41.jpg": (
        f"{GEM_MAP_SOURCE}/assets/maps/Game_map_7.41.jpg",
        9298474,
        "9fb56fc131acc161fb904f6c7189c6f37c57705bac752ccf9a47e01b1b079764",
    ),
}


def verify_map_file(path, size, expected):
    if not path.is_file() or path.stat().st_size != size:
        raise ValueError(f"unexpected 7.41 map file or size: {path}")
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError(f"7.41 map SHA-256 mismatch: {path}")


def prepare_741_map(reference_dir=REFERENCE_DIR, *, fetch=False):
    """Verify the three review-map originals; fetch missing files only when requested."""
    missing = []
    for relative, (_, size, expected) in REVIEW_MAP_FILES.items():
        path = reference_dir / relative
        if path.exists() or path.is_symlink():
            verify_map_file(path, size, expected)
        else:
            missing.append(relative)
    if missing and not fetch:
        raise FileNotFoundError("missing 7.41 review map files: " + ", ".join(missing))
    for relative in missing:
        url, size, expected = REVIEW_MAP_FILES[relative]
        with urlopen(url, timeout=60) as source:
            data = source.read(size + 1)
        if len(data) != size or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"download differs from fixed 7.41 map source: {url}")
        path = reference_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=path.parent) as staging:
            verified = Path(staging) / "verified"
            verified.write_bytes(data)
            try:
                os.link(
                    verified, path
                )  # Publish a complete file without replacing a concurrent writer.
            except FileExistsError:
                verify_map_file(path, size, expected)
    return {relative: sha for relative, (_, _, sha) in REVIEW_MAP_FILES.items()}


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("draft")
    d.add_argument("--out", type=Path, required=True)
    maps = sub.add_parser(
        "prepare-review-map", help="verify or retrieve the pinned 7.41 review map files"
    )
    maps.add_argument("--reference-dir", type=Path, default=REFERENCE_DIR)
    maps.add_argument(
        "--fetch-741-map",
        action="store_true",
        help="retrieve missing map files from pinned upstream commits",
    )
    args = parser.parse_args()
    if args.command == "draft":
        draft(args)
        return
    try:
        verified = prepare_741_map(args.reference_dir, fetch=args.fetch_741_map)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"7.41 map preparation failed: {exc}\n")
    print(json.dumps(verified, indent=2))


if __name__ == "__main__":
    main()
