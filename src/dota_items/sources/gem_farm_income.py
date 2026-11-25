"""Read actual lane/neutral income at frozen decision endpoints from a raw replay.

This producer is independent of action labels. Its output contains observed income,
not features available at the decision second and not counterfactual rewards.
"""

import json
from collections import Counter
from pathlib import Path

from ..storage import file_hash
from .gem_capture import require_complete_parse
from .gem_capture_v3 import _name

SCHEMA = "gem-farm-income/1"
COMPAT_SHA256 = "3f6e9ee2c222869adce45c6dfef757e719c9576bfdde82927e76d6868c47403d"
OFFSETS = (0, 20, 30)
GOLD_KINDS = {13: "creep", 14: "neutral"}
COUNTER_FIELDS = {"creep": "m_iCreepKillGold", "neutral": "m_iNeutralKillGold"}


def verify_compatibility(root):
    """Check the registered compatibility manifest and every packaged source hash."""
    root = Path(root)
    manifest = root.parent / "manifest.json"
    if file_hash(manifest) != COMPAT_SHA256:
        raise ValueError("farm income requires the registered Gem compatibility manifest")
    for name, expected in json.loads(manifest.read_bytes())["patched"].items():
        if file_hash(root / name) != expected:
            raise ValueError(f"Gem compatibility source fingerprint mismatch: {name}")
    return COMPAT_SHA256


def _runtime():
    import gem
    from gem.extractors.players import PlayerExtractor
    from gem.parser import ReplayParser

    sha = verify_compatibility(Path(gem.__file__).resolve().parent)
    return ReplayParser, PlayerExtractor, sha


def _needed_endpoints(cases):
    seen, needed = set(), set()
    for hero, second in cases:
        if not isinstance(hero, str) or not hero or type(second) is not int or second < 0:
            raise ValueError("each case requires a hero name and a nonnegative integer second")
        if (hero, second) in seen:
            raise ValueError("duplicate farm income case")
        seen.add((hero, second))
        needed.update((hero, second + offset) for offset in OFFSETS)
    if not seen:
        raise ValueError("farm income requires at least one case")
    return needed


def _amount(value):
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError("farm income amounts must be nonnegative integers or null")
    return value


def _collect(parser, players, needed):
    boundaries, recipients, previous, events = {}, {}, {}, []
    event_counts = Counter()
    last = None

    def sample(net_tick):
        nonlocal last
        second = parser.game_time_s
        if second is None or second < 0 or second == last:
            return
        if type(second) is not int:
            raise ValueError("farm income endpoint requires an integer game second")
        if last is not None and second < last:
            raise ValueError("farm income endpoint clock moved backwards")
        last = second
        em = parser.entity_manager
        # Never replace a missing opening sample with a later tick of the same second.
        if em is None:
            return
        teams = {
            2: em.find_by_class_name("CDOTA_DataRadiant"),
            3: em.find_by_class_name("CDOTA_DataDire"),
        }
        names = parser.string_tables.get_by_name("EntityNames")
        if names is None:
            return
        seen = set()
        for pid in range(10):
            entity = players._canonical_hero_entity(pid)
            if entity is None:
                continue
            hero = _name(entity, names)
            team = entity.get("m_iTeamNum")
            slot = players._player_team_slot.get(pid)
            if not hero or slot is None or teams.get(team) is None:
                continue
            if type(slot) is not int or not 0 <= slot < 5 or hero in seen:
                raise ValueError("invalid or duplicate farm income recipient")
            seen.add(hero)
            identity = dict(team=team, slot=slot)
            if recipients.setdefault(hero, identity) != identity:
                raise ValueError("farm income recipient team-slot identity changed")
            values = {
                kind: _amount(teams[team].get(f"m_vecDataTeam.{slot:04d}.{field}"))
                for kind, field in COUNTER_FIELDS.items()
            }
            for kind, value in values.items():
                old = previous.get((hero, kind))
                if old is not None and value is not None and value < old:
                    raise ValueError("cumulative farm income decreased")
                if value is not None:
                    previous[hero, kind] = value
            if (hero, second) in needed:
                boundaries[hero, second] = dict(
                    hero=hero,
                    t=second,
                    tick=parser.tick,
                    net_tick=net_tick,
                    status="observed",
                    **values,
                )

    def combat(entry):
        if entry.log_type != "GOLD":
            return
        event_counts[str(entry.gold_reason)] += 1
        if entry.gold_reason in GOLD_KINDS:
            amount = _amount(entry.value)
            if amount is None:
                raise ValueError("farm gold event has no amount")
            events.append(
                dict(
                    tick=entry.tick,
                    hero=entry.target_name,
                    kind=GOLD_KINDS[entry.gold_reason],
                    value=amount,
                )
            )

    parser.on_tick_start(sample)
    parser.on_combat_log_entry(combat)
    parser.parse()
    require_complete_parse(parser)
    if type(parser.match_id) is not int or parser.match_id <= 0:
        raise ValueError("farm income replay identity is missing")
    identities = {(r["team"], r["slot"]) for r in recipients.values()}
    if len(recipients) != 10 or len(identities) != 10:
        raise ValueError("incomplete gold recipient to team-slot mapping")
    if any(hero not in recipients for hero, _ in needed):
        raise ValueError("requested farm income hero is absent from replay")
    for boundary in boundaries.values():
        second = parser.game_clock.game_seconds_at(boundary["tick"])
        if type(second) is not int or second != boundary["t"]:
            raise ValueError("farm income endpoint game clock mismatch")
    if not events and any(value > 0 for value in previous.values()):
        raise ValueError("missing farm gold events despite positive cumulative income")
    for event in events:
        if event["hero"] not in recipients:
            raise ValueError("unknown farm gold recipient")
        second = parser.game_clock.game_seconds_at(event["tick"])
        if type(second) is not int:
            raise ValueError("game clock unavailable for farm event")
        event["t"] = second
    endpoints = []
    for hero, second in sorted(needed):
        endpoints.append(
            boundaries.get(
                (hero, second),
                dict(
                    hero=hero,
                    t=second,
                    tick=None,
                    net_tick=None,
                    creep=None,
                    neutral=None,
                    status="missing_endpoint",
                ),
            )
        )
    return dict(
        schema=SCHEMA,
        match_id=parser.match_id,
        sampling="first_tick_start_before_entity_updates",
        endpoint_ticks="tick is replay tick; net_tick is engine tick",
        window_convention="integer game seconds [t,t+seconds)",
        last_observed_second=last,
        recipients=dict(sorted(recipients.items())),
        boundaries=endpoints,
        events=events,
        gold_event_counts=dict(sorted(event_counts.items())),
    )


def capture_farm_income(raw_demo_path, cases):
    """Capture requested (hero, second) anchors at offsets 0, 20 and 30.

    ``raw_demo_path`` must be an unpacked .dem. All ten canonical hero recipients
    must map bijectively to team slots. Missing endpoint values remain null.
    ``last_observed_second`` is stream coverage, not the match's actual duration.
    The caller verifies the expected match ID and source file identity.
    """
    needed = _needed_endpoints(cases)
    parser_type, player_type, compat_sha = _runtime()
    parser = parser_type(str(raw_demo_path))
    players = player_type()
    players.attach(parser)
    return {**_collect(parser, players, needed), "compat_manifest_sha256": compat_sha}
