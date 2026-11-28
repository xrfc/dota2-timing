"""Independent objective lifecycle, combat-death and chat evidence from one parse."""

import math
from collections import Counter

from dota_items.sources.map_runtime_capture import RuntimeCollector

TARGETS = {"npc_dota_roshan": "roshan", "npc_dota_miniboss": "tormentor"}


class ObjectiveEvents:
    def __init__(self, parser):
        self.parser = parser
        self.deaths = []
        self.chat = []
        self.coverage = Counter()

    def on_combat(self, entry):
        self.coverage["combat_entries"] += 1
        if entry.log_type != "DEATH":
            return
        self.coverage["death_entries"] += 1
        if entry.target_name not in TARGETS:
            return
        self.deaths.append(
            {
                "kind": TARGETS[entry.target_name],
                "target_name": entry.target_name,
                "delivery_tick": self.parser.tick,
                "entry_tick": entry.tick,
                "timestamp_s": entry.timestamp_s,
                "combat_game_time_s": entry.game_time_s,
                "wire_source": str(entry.source),
                "will_reincarnate": entry.will_reincarnate,
            }
        )

    def on_chat(self, msg, tick):
        self.coverage["chat_entries"] += 1
        # Raw protocol type only; a pickup or disappearance never implies death.
        if msg.type in (8, 51, 53, 117):
            self.chat.append({"delivery_tick": tick, "type": msg.type})

    def result(self):
        end = self.parser.post_game_tick
        deaths, chat = [], []
        for source, target in ((self.deaths, deaths), (self.chat, chat)):
            for row in source:
                if row["delivery_tick"] > end:
                    continue
                value = self.parser.game_clock.game_time_at(row["delivery_tick"])
                target.append(
                    {
                        **row,
                        "delivery_game_time": float(value)
                        if type(value) in (float, int) and math.isfinite(value)
                        else None,
                    }
                )
        return {
            "combat_deaths": deaths,
            "chat_events": chat,
            "message_coverage": dict(self.coverage),
            "time_basis": "Delivery tick is not the timestamp of a batched combat event.",
        }


def capture(path):
    from gem.parser import ReplayParser
    from gem.state.entities import EntityOp

    parser = ReplayParser(path)
    runtime = RuntimeCollector(parser, EntityOp)
    events = ObjectiveEvents(parser)
    parser.on_entity(runtime.on_entity)
    parser.on_tick_start(runtime.on_tick_start)
    parser.on_combat_log_entry(events.on_combat)
    parser.on_chat_event(events.on_chat)
    parser.parse()
    if (
        parser.parse_error is not None
        or parser.truncated_at_tick is not None
        or any(type(x) is not int or x <= 0 for x in (parser.match_id, parser.game_build))
        or type(parser.post_game_tick) is not int
        or parser.post_game_tick < 0
    ):
        raise ValueError("Incomplete objective evidence parse")
    return {
        "schema": "map-objective-evidence/1",
        "match_id": parser.match_id,
        "game_build": parser.game_build,
        "post_game_tick": parser.post_game_tick,
        "parse_error": None,
        "truncated_at_tick": None,
        "coordinate_space": "world",
        **runtime.result(),
        **events.result(),
    }
