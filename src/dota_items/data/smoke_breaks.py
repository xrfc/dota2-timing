"""When and how Smoke of Deceit ended (shared base, gap list item 8, U154).

The combat log records when each hero's smoke modifier was added and removed. Smoke lasts
`DURATION` seconds and ends early when its holder comes within `BREAK_RANGE` of an enemy
hero or tower (common guides; the figure is checked here against our own replays: see
docs/game-understanding-gaps.md). For each smoked hero this module reports how long the
smoke lasted, and at the second it ended the nearest enemy hero and the nearest enemy
standing building.
"""

import math

SMOKE_MODIFIER = "modifier_smoke_of_deceit"
DURATION = 45
BREAK_RANGE = 1025


def smoke_spans(combat):
    """[{hero, team, start, end}] for each smoke a hero carried (illusions left out)."""
    open_at, result = {}, []
    for entry in sorted(combat, key=lambda e: e["time"]):
        p = entry["payload"]
        if p.get("inflictor_name") != SMOKE_MODIFIER or p.get("target_is_illusion"):
            continue
        hero = p.get("target_name")
        if p.get("log_type") == "MODIFIER_ADD":
            open_at.setdefault(hero, entry["time"])
        elif p.get("log_type") == "MODIFIER_REMOVE" and hero in open_at:
            result.append({"hero": hero, "start": open_at.pop(hero), "end": entry["time"]})
    return result


def describe_breaks(spans, tracks, buildings_at):
    """Add `lasted`, `nearest_enemy_hero` and `nearest_enemy_building` to each span.

    `buildings_at(second)` returns the standing buildings [{team, x, y, name}].
    Distances are None when a position is missing.
    """
    for span in spans:
        hero, end = span["hero"], span["end"]
        span["lasted"] = end - span["start"]
        if hero not in tracks:
            span["nearest_enemy_hero"] = span["nearest_enemy_building"] = None
            continue
        team = tracks[hero]["team"]
        here = tracks[hero]["pos"].get(end) or tracks[hero]["pos"].get(end - 1)
        if here is None:
            span["nearest_enemy_hero"] = span["nearest_enemy_building"] = None
            continue
        enemies = [
            (math.dist(here, track["pos"][end]), name)
            for name, track in tracks.items()
            if track["team"] != team and end in track["pos"]
        ]
        span["nearest_enemy_hero"] = (
            {"hero": min(enemies)[1], "distance": round(min(enemies)[0])} if enemies else None
        )
        buildings = [
            (math.dist(here, (b["x"], b["y"])), b.get("name"))
            for b in buildings_at(end)
            if b["team"] != team
        ]
        span["nearest_enemy_building"] = (
            {"name": min(buildings)[1], "distance": round(min(buildings)[0])} if buildings else None
        )
    return spans


def broke_near_enemy(span, margin=150):
    """Ended early with an enemy hero or building within BREAK_RANGE plus `margin`."""
    if span["lasted"] >= DURATION - 1:
        return False
    near = [span.get("nearest_enemy_hero"), span.get("nearest_enemy_building")]
    return any(n and n["distance"] <= BREAK_RANGE + margin for n in near)
