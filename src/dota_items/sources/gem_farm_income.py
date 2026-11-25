"""Read actual creep/neutral income at frozen decision endpoints from a raw replay.

This producer is independent of action labels. Its output contains observed income,
not features available at the decision second and not counterfactual rewards.
The game's creep category can include summoned units; it is not pure lane income.
"""

import json
from collections import Counter
from pathlib import Path

from ..storage import file_hash
from .gem_capture import require_complete_parse
from .gem_capture_v3 import _name

SCHEMA = "gem-farm-income/2"
COMPAT_SHA256 = "3f6e9ee2c222869adce45c6dfef757e719c9576bfdde82927e76d6868c47403d"
OFFSETS = (0, 20, 30)
GOLD_KINDS = {13: "creep", 14: "neutral"}
COUNTER_FIELDS = {"creep": "m_iCreepKillGold", "neutral": "m_iNeutralKillGold"}
HANDLE_INDEX_BITS = 14
NULL_HANDLE = 0xFFFFFF


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


def _selected_heroes(em):
    """Read ownership from PlayerResource, independent of controller reconnects.

    Gem's registered schema uses 14 entity-index bits and the remaining handle
    bits for the entity serial. A missing/stale selection is unavailable; it must
    never fall back to a controller that may temporarily belong to another PID.
    """
    resource = em.find_by_class_name("CDOTA_PlayerResource")
    if resource is None:
        return
    slots = set()
    for index in range(30):  # Same PlayerResource scan range as registered Gem.
        team = resource.get(f"m_vecPlayerData.{index:04d}.m_iPlayerTeam")
        slot = resource.get(f"m_vecPlayerTeamData.{index:04d}.m_iTeamSlot")
        # Registered Gem treats negative slots as unassigned resource rows.
        if team not in (2, 3) or slot is None or (type(slot) is int and slot < 0):
            continue
        if type(team) is not int or type(slot) is not int or not 0 <= slot < 5:
            raise ValueError("invalid farm income roster team-slot")
        if (team, slot) in slots:
            raise ValueError("duplicate farm income roster team-slot")
        slots.add((team, slot))
        handle = resource.get(f"m_vecPlayerTeamData.{index:04d}.m_hSelectedHero")
        if handle is None or handle == NULL_HANDLE:
            continue
        if type(handle) is not int or not 0 <= handle <= 0xFFFFFFFF:
            raise ValueError("invalid farm income selected hero handle")
        entity = em.find_by_handle(handle)
        if entity is None:
            continue
        if (
            entity.get_index() != handle & ((1 << HANDLE_INDEX_BITS) - 1)
            or entity.get_serial() != handle >> HANDLE_INDEX_BITS
        ):
            raise ValueError("farm income selected hero handle identity mismatch")
        if not entity.get_class_name().startswith("CDOTA_Unit_Hero_"):
            raise ValueError("farm income selected entity is not a hero")
        entity_team = entity.get("m_iTeamNum")
        if entity_team is None:
            continue
        if entity_team != team:
            raise ValueError("farm income selected hero disagrees with roster team")
        yield index, entity, team, slot


def _collect(parser, _players, needed):
    boundaries, recipients, previous, events = {}, {}, {}, []
    roster_history = {}
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
        for resource_index, entity, team, slot in _selected_heroes(em):
            hero = _name(entity, names)
            if not hero or teams.get(team) is None:
                continue
            if hero in seen:
                raise ValueError("invalid or duplicate farm income recipient")
            seen.add(hero)
            identity = dict(team=team, slot=slot, resource_index=resource_index)
            if recipients.setdefault(hero, identity) != identity:
                raise ValueError("farm income recipient team-slot identity changed")
            roster_entry = dict(hero=hero, team=team, slot=slot)
            if roster_history.setdefault(resource_index, roster_entry) != roster_entry:
                raise ValueError("farm income selected hero roster identity changed")
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
        ownership="player_resource_selected_hero_and_team_slot",
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

    ``raw_demo_path`` must be an unpacked .dem. All ten PlayerResource-selected
    hero recipients must map bijectively to roster team slots. Missing or stale
    selected-hero handles leave endpoint values null; controllers are not used.
    ``last_observed_second`` is stream coverage, not the match's actual duration.
    The caller verifies the expected match ID and source file identity.
    """
    needed = _needed_endpoints(cases)
    parser_type, player_type, compat_sha = _runtime()
    parser = parser_type(str(raw_demo_path))
    players = player_type()
    players.attach(parser)
    return {**_collect(parser, players, needed), "compat_manifest_sha256": compat_sha}
