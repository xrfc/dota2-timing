"""Project an already verified replay bundle into track-B review inputs.

This module does not admit bundles, select patches, load caches or grant model use.
The caller verifies provenance and quality before supplying parsed data and a
single-use stream of state rows. Only the game window is accepted; historical
full-range channels must be explicitly clipped by their caller for comparisons.
"""

import math
from collections.abc import Iterable
from copy import deepcopy

from dota_items.data.gank_events import hero_tracks, infer_positions, visibility_table
from dota_items.data.gank_review import SMOKE_MODIFIER

_SLOTS = (*range(5), *range(128, 133))
_COMBAT_FIELDS = (
    "log_type",
    "attacker_name",
    "target_name",
    "inflictor_name",
    "attacker_is_hero",
    "attacker_is_illusion",
    "target_is_illusion",
    "value",
    "tick",
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _point(value):
    return type(value) in (list, tuple) and len(value) == 2 and all(map(_number, value))


def _last_hits(parsed, duration):
    players = parsed.get("players")
    _require(type(players) is list and len(players) == 10, "Expected ten normalized players")
    slots, result = set(), {}
    for player in players:
        _require(type(player) is dict, "Invalid normalized player")
        slot = player.get("player_slot")
        _require(type(slot) is int and slot in _SLOTS and slot not in slots, "Invalid player slot")
        slots.add(slot)
        pid = slot if slot < 128 else slot - 128 + 5
        events = player.get("economy_log")
        _require(events is None or type(events) is list, "Invalid economy log")
        previous = -1
        for event in events or ():
            _require(type(event) is dict, "Invalid economy event")
            second, hits = event.get("time"), event.get("last_hits")
            _require(
                type(second) is int and previous <= second <= duration and second >= 0,
                "Invalid economy event time",
            )
            _require(hits is None or (_number(hits) and hits >= 0), "Invalid last-hit count")
            previous = second
            if second <= 900:
                result[pid] = hits
    return result


def _fronts(world):
    _require(world is None or type(world) is dict, "Invalid state world")
    fronts = (world or {}).get("lane_fronts")
    _require(fronts is None or type(fronts) is dict, "Invalid lane fronts")
    if fronts is None:
        return None
    result = {}
    for name, wave in fronts.items():
        _require(type(name) is str and type(wave) is dict, "Invalid lane front")
        count, front = wave.get("count"), wave.get("front")
        _require(type(count) is int and count >= 0 and _point(front), "Invalid lane front values")
        result[name] = {"count": count, "front": list(front)}
    return result


def _state_rows(rows, duration, fronts):
    expected, identities = 0, None
    for row in rows:
        _require(type(row) is dict, "Invalid state row")
        second = row.get("t")
        _require(
            type(second) is int and second == expected and second <= duration,
            "State rows must cover exactly 0..duration in order",
        )
        heroes = row.get("heroes")
        _require(type(heroes) is list and len(heroes) == 10, "Expected ten heroes per state row")
        frame, names, slim = {}, set(), []
        for hero in heroes:
            _require(type(hero) is dict, "Invalid state hero")
            pid, name, team = hero.get("player_id"), hero.get("hero"), hero.get("team")
            life, point = hero.get("life_state"), hero.get("pos")
            _require(
                type(pid) is int and 0 <= pid < 10 and pid not in frame,
                "Invalid state player identity",
            )
            _require(
                type(name) is str and bool(name) and name not in names,
                "Invalid state hero identity",
            )
            _require(type(team) is int and team == (2 if pid < 5 else 3), "Invalid state team")
            _require(type(life) is int and life in (0, 1, 2), "Invalid state life state")
            _require(point is None or _point(point), "Invalid state coordinates")
            frame[pid] = (name, team)
            names.add(name)
            slim.append(
                {"player_id": pid, "hero": name, "team": team, "life_state": life, "pos": point}
            )
        if identities is None:
            identities = frame
        _require(frame == identities, "State hero identity changed during the match")
        fronts[second] = _fronts(row.get("world"))
        expected += 1
        yield {"t": second, "heroes": slim}
    _require(expected == duration + 1, "State rows must cover exactly 0..duration in order")


def _event(entry):
    _require(type(entry) is dict, "Invalid context event")
    second, payload = entry.get("time"), entry.get("payload")
    _require(type(second) is int and type(payload) is dict, "Invalid context event time/payload")
    return second, payload


def _seen(events, tracks, duration):
    selected = []
    for entry in events:
        second, payload = _event(entry)
        if second > duration:
            continue
        _require(second >= -3600, "Visibility initialization precedes the context window")
        hero = payload.get("hero_name")
        _require(type(hero) is str and hero in tracks, "Invalid visibility hero")
        _require(
            all(
                payload.get(key) in ("visible", "hidden", "unknown")
                for key in ("radiant_state", "dire_state")
            ),
            "Invalid visibility state",
        )
        selected.append(
            {
                "time": second,
                "payload": {
                    key: payload[key] for key in ("hero_name", "radiant_state", "dire_state")
                },
            }
        )
    # Negative events seed the state at zero. Filtering them before expansion
    # would forget heroes already visible when the game window begins.
    return {
        key: game_seconds
        for key, seconds in visibility_table(selected, duration).items()
        if (game_seconds := {second for second in seconds if second >= 0})
    }


def _combat(events, tracks, duration):
    result = []
    for entry in events:
        second, payload = _event(entry)
        if not 0 <= second <= duration:
            continue
        kind = payload.get("log_type")
        _require(type(kind) is str and bool(kind), "Invalid combat event type")
        for key in ("attacker_name", "target_name", "inflictor_name"):
            _require(payload.get(key) is None or type(payload[key]) is str, "Invalid combat name")
        if kind == "DAMAGE":
            keep = payload.get("attacker_name") in tracks or payload.get("target_name") in tracks
        elif kind in ("MODIFIER_ADD", "MODIFIER_REMOVE"):
            keep = payload.get("inflictor_name") == SMOKE_MODIFIER
        else:
            keep = kind in ("DEATH", "ABILITY", "ITEM")
        if not keep:
            continue
        for key in ("attacker_is_hero", "attacker_is_illusion", "target_is_illusion"):
            _require(payload.get(key) is None or type(payload[key]) is bool, "Invalid combat flag")
        _require(payload.get("value") is None or _number(payload["value"]), "Invalid combat value")
        _require(
            payload.get("tick") is None or (type(payload["tick"]) is int and payload["tick"] >= 0),
            "Invalid combat tick",
        )
        result.append(
            {
                "time": second,
                "payload": {key: payload[key] for key in _COMBAT_FIELDS if key in payload},
            }
        )
    return result


def project_match(parsed: dict, state_rows: Iterable[dict], *, source_key: dict) -> dict:
    """Return the established track/visibility/combat shape without reading files.

    The projection retains only review inputs, not complete state frames. It is
    still omniscient review material, not an observer-safe training table. The
    caller owns provenance, holdout exclusion and patch/map compatibility.
    """
    _require(
        type(parsed) is dict and type(source_key) is dict, "Expected parsed data and source key"
    )
    duration = parsed.get("duration")
    _require(type(duration) is int and 0 < duration <= 86400, "Invalid match duration")
    by_player = _last_hits(parsed, duration)
    context = parsed.get("context")
    channels = context.get("channels") if type(context) is dict else None
    _require(type(channels) is dict, "Missing normalized context channels")
    _require(
        all(type(channels.get(name)) is list for name in ("hero_visibility_events", "combat_log")),
        "Missing normalized review channels",
    )
    fronts = {}
    tracks = hero_tracks(_state_rows(state_rows, duration, fronts))
    hits = {hero: by_player.get(track["player_id"]) for hero, track in tracks.items()}
    return {
        "key": deepcopy(source_key),
        "tracks": tracks,
        "seen": _seen(channels["hero_visibility_events"], tracks, duration),
        "positions": infer_positions(tracks, hits),
        "combat": _combat(channels["combat_log"], tracks, duration),
        "fronts": fronts,
        "last": duration,
    }
