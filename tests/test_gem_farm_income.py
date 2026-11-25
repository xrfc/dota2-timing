"""Frozen raw-gold extraction: endpoint timing, unknowns, and source integrity."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from dota_items.sources import gem_farm_income as farm


def handle(pid, serial=1):
    return (serial << 14) | (pid + 100)


class Entity(dict):
    def __init__(self, pid, fields):
        super().__init__(
            {
                "m_pEntity.m_nameStringTableIndex": fields.get((pid, "name"), pid),
                "m_iTeamNum": fields.get((pid, "team"), 2 if pid < 5 else 3),
            }
        )
        self.pid, self.fields = pid, fields

    def get_index(self):
        return self.pid + 100

    def get_serial(self):
        return self.fields.get((self.pid, "serial"), 1)

    def get_class_name(self):
        return "CDOTA_Unit_Hero_Test"


class Parser:
    def __init__(self, frames, events=None, clock=None):
        self.frames = frames
        self.events = [gold(0)] if events is None else events
        self.match_id, self.parse_error, self.truncated_at_tick = 123, None, None
        self.clock = {frame[1]: frame[0] for frame in frames}
        self.clock.update({e.tick: e.tick // 10 for e in self.events})
        if clock is not None:
            self.clock.update(clock)
        self.game_clock = SimpleNamespace(game_seconds_at=lambda tick: self.clock.get(tick))
        self.names = SimpleNamespace(items={i: (f"hero_{i}", None) for i in range(10)})
        self.string_tables = SimpleNamespace(get_by_name=lambda _: self.names)
        self.players = Players()
        self.paths = []

    def on_tick_start(self, callback):
        self.sample = callback

    def on_combat_log_entry(self, callback):
        self.combat = callback

    def parse(self):
        for frame in self.frames:
            self.game_time_s, self.tick, net_tick = frame[:3]
            fields = frame[3] if len(frame) > 3 else {}
            self.players.frame = fields
            teams = {
                team: {
                    f"m_vecDataTeam.{slot:04d}.{name}": fields.get(
                        (team, slot, kind), self.game_time_s + offset
                    )
                    for slot in range(5)
                    for kind, name, offset in (
                        ("creep", "m_iCreepKillGold", 100),
                        ("neutral", "m_iNeutralKillGold", 200),
                    )
                }
                for team in (2, 3)
            }
            resource = {}
            entities = {}
            for pid in range(10):
                index = pid + fields.get("resource_offset", 0)
                resource[f"m_vecPlayerData.{index:04d}.m_iPlayerTeam"] = fields.get(
                    (pid, "roster_team"), 2 if pid < 5 else 3
                )
                resource[f"m_vecPlayerTeamData.{index:04d}.m_iTeamSlot"] = fields.get(
                    (pid, "slot"), pid % 5
                )
                resource[f"m_vecPlayerTeamData.{index:04d}.m_hSelectedHero"] = fields.get(
                    (pid, "selected_handle"), handle(pid)
                )
                if pid not in fields.get("missing_players", ()):
                    entities[handle(pid)] = Entity(pid, fields)
            classes = {
                "CDOTA_DataRadiant": teams[2],
                "CDOTA_DataDire": teams[3],
                "CDOTA_PlayerResource": None if fields.get("no_resource") else resource,
            }
            self.entity_manager = SimpleNamespace(
                find_by_class_name=classes.get,
                find_by_handle=entities.get,
            )
            if fields.get("no_entities"):
                self.entity_manager = None
            self.sample(net_tick)
        for event in self.events:
            self.combat(event)


class Players:
    def __init__(self):
        self._player_team_slot = {pid: pid % 5 for pid in range(10)}
        self.frame = {}

    def attach(self, parser):
        parser.players = self

    def _canonical_hero_entity(self, pid):
        if pid in self.frame.get("missing_players", ()):
            return None
        return {
            "m_pEntity.m_nameStringTableIndex": self.frame.get((pid, "name"), pid),
            "m_iTeamNum": self.frame.get((pid, "team"), 2 if pid < 5 else 3),
        }


def gold(tick, reason=13, value=10, hero="hero_0", log_type="GOLD"):
    return SimpleNamespace(
        tick=tick, gold_reason=reason, value=value, target_name=hero, log_type=log_type
    )


def capture(monkeypatch, parser, cases=(("hero_0", 0),)):
    def parser_type(path):
        parser.paths.append(path)
        return parser

    monkeypatch.setattr(farm, "_runtime", lambda: (parser_type, Players, farm.COMPAT_SHA256))
    return farm.capture_farm_income("/tmp/example.dem", cases)


def test_first_tick_endpoints_and_event_clock_are_distinct(monkeypatch):
    parser = Parser(
        [(0, 1, 101), (0, 2, 102, {(2, 0, "creep"): 999}), (20, 201, 301), (30, 301, 401)],
        [gold(200), gold(200, value=11), gold(300, reason=14), gold(400, reason=1)],
        clock={200: 20, 300: 30},
    )
    result = capture(monkeypatch, parser)
    assert parser.paths == ["/tmp/example.dem"]
    assert [(r["t"], r["tick"], r["net_tick"], r["creep"]) for r in result["boundaries"]] == [
        (0, 1, 101, 100),
        (20, 201, 301, 120),
        (30, 301, 401, 130),
    ]
    assert result["events"] == [
        {"tick": 200, "hero": "hero_0", "kind": "creep", "value": 10, "t": 20},
        {"tick": 200, "hero": "hero_0", "kind": "creep", "value": 11, "t": 20},
        {"tick": 300, "hero": "hero_0", "kind": "neutral", "value": 10, "t": 30},
    ]
    assert result["gold_event_counts"] == {"1": 1, "13": 2, "14": 1}
    assert result["last_observed_second"] == 30
    assert result["compat_manifest_sha256"] == farm.COMPAT_SHA256
    assert result["schema"] == "gem-farm-income/2"
    assert result["ownership"] == "player_resource_selected_hero_and_team_slot"
    assert result["recipients"]["hero_9"] == {"team": 3, "slot": 4, "resource_index": 9}
    assert json.loads(json.dumps(result)) == result


def test_missing_fields_and_missing_endpoints_never_become_zero(monkeypatch):
    parser = Parser([(0, 1, 101, {(2, 0, "creep"): None}), (20, 201, 301)])
    result = capture(monkeypatch, parser)
    start, middle, end = result["boundaries"]
    assert start["status"] == "observed" and start["creep"] is None
    assert start["neutral"] == 200
    assert middle["creep"] == 120
    assert end == {
        "hero": "hero_0",
        "t": 30,
        "tick": None,
        "net_tick": None,
        "creep": None,
        "neutral": None,
        "status": "missing_endpoint",
    }


@pytest.mark.parametrize("slot", [None, -1])
def test_unassigned_roster_slot_keeps_missing_endpoint_until_resolved(monkeypatch, slot):
    parser = Parser([(0, 1, 101, {(0, "slot"): slot}), (20, 201, 301), (30, 301, 401)])
    result = capture(monkeypatch, parser)
    start, middle, end = result["boundaries"]
    assert start["status"] == "missing_endpoint"
    assert start["creep"] is None and start["neutral"] is None
    assert middle["status"] == end["status"] == "observed"
    assert result["recipients"]["hero_0"] == dict(team=2, slot=0, resource_index=0)


def test_missing_opening_tick_is_not_replaced_by_later_same_second(monkeypatch):
    parser = Parser([(0, 1, 101, {"no_entities": True}), (0, 2, 102), (20, 201, 301)])
    result = capture(monkeypatch, parser)
    assert result["boundaries"][0]["status"] == "missing_endpoint"
    assert result["boundaries"][0]["tick"] is None


def test_controller_reassigned_to_teammate_does_not_change_gold_ownership(monkeypatch):
    # Reconnect left Gem cache[0] and cache[1] pointing at player 1's controller.
    monkeypatch.setattr(Players, "_canonical_hero_entity", lambda self, pid: Entity(1, {}))
    parser = Parser(
        [
            (0, 1, 101, {(2, 0, "creep"): 10, (2, 1, "creep"): 1000}),
            (20, 201, 301, {(2, 0, "creep"): 15, (2, 1, "creep"): 1005}),
        ]
    )
    result = capture(monkeypatch, parser)
    assert [r["creep"] for r in result["boundaries"]] == [10, 15, None]
    assert result["recipients"]["hero_0"] == {"team": 2, "slot": 0, "resource_index": 0}


@pytest.mark.parametrize("selection", [None, farm.NULL_HANDLE, handle(0, serial=2)])
def test_missing_or_stale_selection_keeps_endpoint_null_without_controller_fallback(
    monkeypatch, selection
):
    parser = Parser([(0, 1, 101, {(0, "selected_handle"): selection}), (20, 201, 301)])
    result = capture(monkeypatch, parser)
    assert result["boundaries"][0]["status"] == "missing_endpoint"
    assert result["boundaries"][0]["creep"] is None
    assert result["boundaries"][1]["creep"] == 120


def test_resolver_returning_reused_index_with_wrong_serial_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match="selected hero handle identity mismatch"):
        capture(monkeypatch, Parser([(0, 1, 101, {(0, "serial"): 2})]))


def test_missing_player_resource_is_not_replaced_by_controller(monkeypatch):
    result = capture(monkeypatch, Parser([(0, 1, 101, {"no_resource": True}), (20, 201, 301)]))
    assert result["boundaries"][0]["status"] == "missing_endpoint"


def test_resource_indices_need_not_equal_logical_player_ids(monkeypatch):
    result = capture(monkeypatch, Parser([(0, 1, 101, {"resource_offset": 1})]))
    assert result["recipients"]["hero_0"]["resource_index"] == 1
    assert result["recipients"]["hero_9"]["resource_index"] == 10


def test_duplicate_roster_slot_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match="duplicate farm income roster team-slot"):
        capture(monkeypatch, Parser([(0, 1, 101, {(1, "slot"): 0})]))


def test_actual_roster_slot_change_is_rejected(monkeypatch):
    parser = Parser([(0, 1, 101), (20, 201, 301, {(0, "slot"): 1, (1, "slot"): 0})])
    with pytest.raises(ValueError, match="team-slot identity changed"):
        capture(monkeypatch, parser)


def test_actual_selected_hero_change_is_rejected(monkeypatch):
    parser = Parser([(0, 1, 101), (20, 201, 301, {(0, "name"): 10})])
    parser.names.items[10] = ("replacement_hero", None)
    with pytest.raises(ValueError, match="selected hero roster identity changed"):
        capture(monkeypatch, parser)


@pytest.mark.parametrize("second", [None, 1, False, 0.0])
def test_endpoint_must_match_final_replay_tick_clock(monkeypatch, second):
    parser = Parser([(0, 1, 101)], clock={1: second})
    with pytest.raises(ValueError, match="endpoint game clock mismatch"):
        capture(monkeypatch, parser)


def test_empty_farm_events_with_positive_counter_is_rejected(monkeypatch):
    parser = Parser([(0, 1, 101)], events=[gold(100, reason=1)])
    with pytest.raises(ValueError, match="missing farm gold events"):
        capture(monkeypatch, parser)


def test_zero_counters_with_empty_events_remain_valid(monkeypatch):
    zero = {
        (team, slot, kind): 0
        for team in (2, 3)
        for slot in range(5)
        for kind in ("creep", "neutral")
    }
    parser = Parser([(0, 1, 101, zero), (20, 201, 301, zero)], events=[])
    result = capture(monkeypatch, parser)
    assert result["events"] == [] and result["gold_event_counts"] == {}
    assert result["boundaries"][0]["creep"] == 0


def test_shared_endpoint_is_sampled_once(monkeypatch):
    parser = Parser([(0, 1, 101), (20, 201, 301), (30, 301, 401), (40, 401, 501), (50, 501, 601)])
    result = capture(monkeypatch, parser, (("hero_0", 0), ("hero_0", 20)))
    assert [r["t"] for r in result["boundaries"]] == [0, 20, 30, 40, 50]


def test_truncated_parser_cannot_produce_apparently_complete_capture(monkeypatch):
    parser = Parser([(0, 1, 101)])
    parser.parse_error, parser.truncated_at_tick = RuntimeError("broken packet"), 777
    with pytest.raises(ValueError, match="Incomplete Gem parse at tick 777"):
        capture(monkeypatch, parser)


@pytest.mark.parametrize("match_id", [None, 0, -1, True, "123"])
def test_missing_match_identity_is_rejected(monkeypatch, match_id):
    parser = Parser([(0, 1, 101)])
    parser.match_id = match_id
    with pytest.raises(ValueError, match="replay identity"):
        capture(monkeypatch, parser)


@pytest.mark.parametrize(
    ("frames", "message"),
    [
        ([(0, 1, 101, {"missing_players": [9]})], "incomplete gold recipient"),
        ([(0, 1, 101, {(9, "team"): 2})], "disagrees with roster team"),
        ([(0, 1, 101, {(9, "name"): 8})], "duplicate farm income recipient"),
        ([(0, 1, 101), (20, 201, 301, {(0, "team"): 3})], "disagrees with roster team"),
        ([(0, 1, 101), (20, 201, 301, {(2, 0, "creep"): 90})], "cumulative farm income decreased"),
        ([(20, 201, 301), (19, 202, 302)], "clock moved backwards"),
    ],
)
def test_invalid_recipient_or_counter_sequence_is_rejected(monkeypatch, frames, message):
    with pytest.raises(ValueError, match=message):
        capture(monkeypatch, Parser(frames))


def test_requested_hero_must_be_in_replay(monkeypatch):
    with pytest.raises(ValueError, match="hero is absent"):
        capture(monkeypatch, Parser([(0, 1, 101)]), (("missing_hero", 0),))


@pytest.mark.parametrize(
    ("event", "clock", "message"),
    [
        (gold(200, hero="missing_hero"), {200: 20}, "unknown farm gold recipient"),
        (gold(200), {200: None}, "game clock unavailable"),
        (gold(200, value=None), {200: 20}, "has no amount"),
        (gold(200, value=-10), {200: 20}, "nonnegative integers"),
    ],
)
def test_unreliable_events_are_rejected(monkeypatch, event, clock, message):
    with pytest.raises(ValueError, match=message):
        capture(monkeypatch, Parser([(0, 1, 101)], [event], clock=clock))


@pytest.mark.parametrize(
    "cases", [[], [("hero_0", -1)], [("", 0)], [("hero_0", True)], [("hero_0", 0)] * 2]
)
def test_invalid_cases_fail_before_loading_parser(monkeypatch, cases):
    def unexpected_runtime():
        pytest.fail("invalid cases must not load the parser")

    monkeypatch.setattr(farm, "_runtime", unexpected_runtime)
    with pytest.raises(ValueError):
        farm.capture_farm_income("/tmp/example.dem", cases)


def test_manifest_and_each_source_file_are_checked(tmp_path, monkeypatch):
    root = tmp_path / "gem"
    root.mkdir()
    (root / "a.py").write_bytes(b"a")
    (root / "b.py").write_bytes(b"b")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "patched": {
                    name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                    for name in ("a.py", "b.py")
                }
            }
        )
    )
    pinned = hashlib.sha256(manifest.read_bytes()).hexdigest()
    monkeypatch.setattr(farm, "COMPAT_SHA256", pinned)
    assert farm.verify_compatibility(root) == pinned
    (root / "b.py").write_bytes(b"changed")
    with pytest.raises(ValueError, match="source fingerprint mismatch: b.py"):
        farm.verify_compatibility(root)
    manifest.write_text("{}")
    with pytest.raises(ValueError, match="registered Gem compatibility manifest"):
        farm.verify_compatibility(root)
