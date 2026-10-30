"""Case-prototype evidence, not a training contract or an action policy.

Only the selected side's frozen frame supplies positions. Raw state is read for
the selected friendly hero only; visible enemies do not imply visible inventory.
"""

import hashlib
from copy import deepcopy
from pathlib import Path

from dota_items.data.replay_status import position_status
from dota_items.data.source_io import parse_source_json, read_source_bytes


def _inventory(state):
    """Preserve known-empty vs unresolved slots; never infer cooldown from ownership."""
    items = state.get("items", {})
    handles = state.get("inventory_handles")
    empty = state.get("inventory_empty_handle")
    if (
        not isinstance(items, dict)
        or any(k not in {str(i) for i in range(17)} for k in items)
        or not isinstance(handles, dict)
        or type(empty) is not int
    ):
        return {"status": "unknown", "slots": [], "usable_items": None}
    slots = []
    for slot in range(17):
        key = str(slot)
        name, handle = items.get(key), handles.get(key)
        known_name = isinstance(name, str) and name.startswith("item_")
        if type(handle) is not int or handle < 0:
            status = "unknown"
        elif handle == empty:
            status = "unknown" if name is not None else "empty"
        else:
            status = "observed" if known_name else "unknown"
        if slot in state.get("inventory_unknown_slots", []):
            status = "unknown"
        group = (
            "main"
            if slot < 6
            else "backpack"
            if slot < 9
            else "reserve"
            if slot < 15
            else "special_unverified"
        )
        slots.append(
            {
                "slot": slot,
                "group": group,
                "status": status,
                "item": name if status == "observed" else None,
                "usable": None,
                "cooldown": None,
                "charges": None,
            }
        )
    return {
        "status": "observed_slots_not_usability",
        "complete": all(s["status"] != "unknown" for s in slots),
        "slots": slots,
        "usable_items": None,
        "limitations": [
            "Cooldown, charges, delivery and backpack-switch delay unverified.",
            "Slots 15/16 retain native numbers; special-slot semantics unverified.",
        ],
    }


def build_evidence(frame, raw, target_slot):
    """Build a whitelist from a team frame and unique same-tick friendly raw state.

    Provenance hashes live outside decision_input, so raw hidden/future-byte
    changes cannot masquerade as feature changes in leakage regression tests.
    Exact-tick states only: no nearest/future sample, no end-of-match backfill.
    """
    view, tick = frame["view"], frame["tick"]
    if view not in {"radiant", "dire"}:
        raise ValueError("Decision input requires a team view")
    valid_slots = set(range(5)) if view == "radiant" else set(range(128, 133))
    if type(target_slot) is not int or target_slot not in valid_slots:
        raise ValueError("Target must belong to observer team")
    if raw["match_id"] != frame["match_id"]:
        raise ValueError("Raw/frame identity mismatch")
    pid = target_slot if target_slot < 5 else target_slot - 123
    targets = [p for p in frame["players"] if p["player_slot"] == target_slot]
    players = [p for p in raw["players"] if p["player_id"] == pid]
    if len(targets) != 1 or len(players) != 1:
        raise ValueError("Ambiguous target identity")
    target = targets[0]
    player = players[0]
    if player["hero_id"] != target["hero_id"] or player["team"] != (2 if view == "radiant" else 3):
        raise ValueError("Target hero/team mismatch")
    positions = []
    for row in frame["players"]:
        if row["visibility"] in {"hidden", "unknown"} and (
            row["current_position"] is not None or row["life_state"] is not None
        ):
            raise ValueError("Hidden information in frame")
        last = deepcopy(row["last_seen"])
        if last is not None:
            if last["source_tick"] > tick:
                raise ValueError("Future last-seen")
            last["age_ticks"] = tick - last["source_tick"]
            last["age_game_seconds"] = frame["time"] - last["time"]
        positions.append(
            {
                "player_slot": row["player_slot"],
                "hero_id": row["hero_id"],
                "relation": "ally" if row["player_slot"] in valid_slots else "enemy",
                "visibility": row["visibility"],
                "life_state": row["life_state"],
                "position_status": position_status(row),
                "current_position": deepcopy(row["current_position"]),
                "last_seen": last,
            }
        )
    candidates = [
        (i, s)
        for i, s in enumerate(raw.get("coach_state_snapshots", []))
        if s["player_id"] == pid and s["tick"] == tick
    ]
    refs = []
    inventory = {"status": "unknown", "slots": [], "usable_items": None}
    state_status = "missing" if not candidates else "ambiguous"
    if len(candidates) == 1 and target["visibility"] == "visible":
        index, state = candidates[0]
        events = [
            e
            for e in raw.get("hero_visibility_events", [])
            if e["player_id"] == pid and e["tick"] <= tick
        ]
        latest = max((e["tick"] for e in events), default=-1)
        events = [e for e in events if e["tick"] == latest]
        signatures = {
            (e["entity_index"], e["entity_serial"], e.get(view + "_state")) for e in events
        }
        identity = (state.get("entity_index"), state.get("entity_serial"), "visible")
        if (
            None not in identity
            and signatures == {identity}
            and state.get("life_state") == target["life_state"]
        ):
            state_status = "same_tick_identity_matched"
            refs = [f"coach_state_snapshots[{index}]"]
            inventory = _inventory(state)
        else:
            state_status = "identity_or_visibility_unverified"
    decision = {
        "match_id": frame["match_id"],
        "observer_team": view,
        "tick": tick,
        "time": frame["time"],
        "target_slot": target_slot,
        "target_hero_id": target["hero_id"],
        "positions": positions,
        "friendly_state_status": state_status,
        "inventory": inventory,
        "enemy_inventory": None,
        "health_mana": None,
        "ability_readiness": None,
        "lane_and_objectives": None,
        "missing": [
            "Equipment usability/cooldown/charges",
            "Enemy known inventory",
            "Certified health/mana units and ability readiness",
            "Lane/target state",
            "Complete terrain/pathfinding and fog grid",
        ],
    }
    return {
        "schema": "decision-case-evidence/1",
        "training_allowed": False,
        "decision_input": decision,
        "state_refs": refs,
        "limitations": [
            "Case prototype, not a registered ML task.",
            "No causal or optimal-action certification; native distances only.",
        ],
    }


class DecisionEvidenceStore:
    """Read immutable raw pinned by the already verified view manifest."""

    def __init__(self, replay_store, repo_root):
        self.replay = replay_store
        self.repo_root = Path(repo_root)

    def build(self, mid, view, tick, slot):
        frame = self.replay.frame(mid, view, tick, trail=0)
        manifest = self.replay.load(mid, view)["manifest"]
        sources = [
            (p, h) for p, h in manifest["inputs_and_code"].items() if p.endswith("/raw.json")
        ]
        if len(sources) != 1:
            raise ValueError("Ambiguous raw source")
        source, expected = sources[0]
        path = Path(source)
        if not path.is_absolute():
            path = self.repo_root / path
        content = read_source_bytes(path, max_bytes=512 * 1024**2)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Raw hash mismatch")
        raw = parse_source_json(content)
        if raw.get("coach_capture_version") != "gem-state-capture/2":
            raise ValueError("Unsupported state capture")
        result = build_evidence(frame, raw, slot)
        result["provenance"] = {
            "raw": source,
            "raw_sha256": expected,
            "view_sha256": manifest["files"][view + ".jsonl"],
            "manifest_sha256": self.replay.entries[mid]["manifest_sha256"],
            "position_refs": f"{view}.jsonl: source_tick={tick}; player_slot per row",
            "ordering": "Exact tick; same-tick event order unverified; no item-use claim.",
        }
        return result
