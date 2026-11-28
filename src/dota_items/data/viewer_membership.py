"""Replay vector length and lifetime evidence without inventing vision geometry."""

import copy
import json
import math

FIELDS = ("m_nGridX", "m_nGridY", "m_nRadius", "m_nViewerType", "m_bObstructedVision", "m_bValid")
MAX_LENGTH = 4096


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


class ViewerVector:
    """Logical membership is distinct from retained parser capacity and source identity."""

    def __init__(self):
        self.length = None
        self.rows = {}
        self.shrinks = 0
        self.length_writes = 0

    def apply(self, names, value):
        if not isinstance(names, list) or not names or names[0] != "m_TempViewerInfo":
            raise ValueError("Unexpected viewer field")
        if len(names) == 1:
            if not _integer(value) or value > MAX_LENGTH:
                raise ValueError("Invalid viewer logical length")
            self.length_writes += 1
            if self.length is not None and value < self.length:
                self.shrinks += 1
            self.length = value
            self.rows = {index: row for index, row in self.rows.items() if index < value}
        elif len(names) == 3:
            index, field = names[1:]
            if not _integer(index) or index >= MAX_LENGTH or field not in FIELDS:
                raise ValueError("Unsupported viewer member")
            if field in FIELDS[-2:]:
                valid = type(value) is bool
            else:
                valid = type(value) is int
            if not valid:
                raise ValueError("Invalid viewer member value")
            self.rows.setdefault(index, {})[field] = value
        else:
            # In the pinned model4 schema a write at the element layer has no
            # established membership meaning. Do not silently treat it as length.
            raise ValueError("Uninterpreted viewer element-layer write")

    def snapshot(self, *, active, team):
        members = []
        if self.length is not None:
            for index in range(self.length):
                values = copy.deepcopy(self.rows.get(index, {}))
                complete = all(field in values for field in FIELDS)
                members.append(
                    {
                        "storage_index": index,
                        "raw": values,
                        "all_fields_observed": complete,
                        "protocol_valid": values.get("m_bValid"),
                        "protocol_active_candidate": (
                            active is True
                            and team in (2, 3)
                            and complete
                            and values.get("m_bValid") is True
                        ),
                    }
                )
        return {"logical_length": self.length, "members": members}


def project_membership(capture):
    if (
        capture.get("schema") != "viewer-wire-capture/1"
        or capture.get("training_allowed") is not False
        or capture.get("action_review_allowed") is not False
        or capture.get("omniscient") is not True
    ):
        raise ValueError("Only unadmitted wire evidence is accepted")
    states, metadata, dirty, frames = {}, {}, set(), []
    previous, sequence, packet_time = None, 0, None
    last_snapshots = {}
    member_states, member_ids = [], {}

    def flush():
        for key in sorted(dirty):
            meta = metadata[key]
            state = states[key].snapshot(active=meta["active"], team=meta["team_raw"])
            ids = []
            for member in state.pop("members"):
                token = json.dumps(member, sort_keys=True, separators=(",", ":"))
                if token not in member_ids:
                    member_ids[token] = len(member_states)
                    member_states.append(member)
                ids.append(member_ids[token])
            body = {**meta, **state, "member_state_ids": ids}
            if body != last_snapshots.get(key):
                frames.append(
                    {
                        "packet_ordinal": previous[0],
                        "tick": previous[1],
                        "game_time": packet_time,
                        **body,
                    }
                )
                last_snapshots[key] = body
        dirty.clear()

    for row in capture["events"]:
        stamp = row["packet_ordinal"], row["tick"]
        if (
            not all(_integer(v) for v in stamp)
            or stamp[0] <= 0
            or stamp[0] > capture["terminal_packet_ordinal"]
            or stamp[1] > capture["post_game_tick"]
            or (previous is not None and (stamp[0] < previous[0] or stamp[1] < previous[1]))
        ):
            raise ValueError("Viewer events are outside ordered completed packets")
        time = row["game_time"]
        if type(time) not in (float, int) or not math.isfinite(time):
            raise ValueError("Unknown viewer clock")
        if previous is not None:
            if time < packet_time or (
                stamp[0] == previous[0] and (stamp != previous or time != packet_time)
            ):
                raise ValueError("Inconsistent viewer packet clock")
            if stamp[0] != previous[0]:
                flush()
        previous, packet_time = stamp, time
        key = row["entity_index"], row["entity_serial"]
        if not all(_integer(v) for v in key):
            raise ValueError("Invalid viewer identity")
        if row["created"]:
            if key in states:
                raise ValueError("Duplicate viewer creation")
            states[key] = ViewerVector()
        if key not in states:
            raise ValueError("Viewer update without creation baseline")
        for write in row["writes"]:
            if not _integer(write["write_sequence"], 1) or write["write_sequence"] != sequence + 1:
                raise ValueError("Missing or reordered viewer writes")
            sequence = write["write_sequence"]
            states[key].apply(write["names"], write["value"])
        metadata[key] = {
            "entity_index": key[0],
            "entity_serial": key[1],
            "team_raw": row["team_raw"],
            "version_raw": row["version_raw"],
            "active": row["active_raw"] is True and not row["left"] and not row["deleted"],
            "deleted": row["deleted"],
        }
        dirty.add(key)
    if previous is not None:
        flush()
    if sequence != capture["writes"]:
        raise ValueError("Viewer total write count mismatch")
    return {
        "schema": "viewer-membership-evidence/1",
        "frames": frames,
        "member_states": member_states,
        "encoding": "frame member_state_ids index the immutable member_states table",
        "length_writes": sum(s.length_writes for s in states.values()),
        "shrinks": sum(s.shrinks for s in states.values()),
        "entity_identities": len(states),
        "raw_writes": sequence,
        "training_allowed": False,
        "action_review_allowed": False,
        "effective_vision_certified": False,
        "limits": [
            "Protocol-valid slots are not individually identified spell sources.",
            "Grid/radius units and viewer-type semantics remain unverified.",
            "This is an omniscient diagnostic, not an observer feature query.",
        ],
    }
