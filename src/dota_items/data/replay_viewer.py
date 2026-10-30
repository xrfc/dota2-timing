"""Read-only, view-isolated replay frames. No training or omniscient observer joins."""

import hashlib
import math
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
from threading import RLock

from dota_items.data.replay_status import position_status
from dota_items.data.source_io import parse_source_json, read_source_bytes

VIEWS = {"radiant", "dire", "omniscient"}
MAX_GAP_TICKS = 45
MAX_SEGMENT_DISTANCE = 1200  # Display break only, not a gameplay speed rule.


def read_json(path):
    return parse_source_json(read_source_bytes(path))


def point(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"x", "y"}:
        raise ValueError("Invalid position")
    if not all(type(value[k]) in (int, float) and math.isfinite(value[k]) for k in ("x", "y")):
        raise ValueError("Invalid coordinate")
    return {k: value[k] for k in ("x", "y")}


def project(row, view):
    """Explicit allowlist; hidden/unknown observer positions fail closed."""
    base = {k: row[k] for k in ("match_id", "player_slot", "hero_id", "source_tick", "time")}
    if view == "omniscient":
        flags = row["quality_flags"]
        reliable = not flags or set(flags) <= {"pause", "repeated_game_second"}
        base.update(
            visibility="omniscient",
            current_position=point({"x": row["x"], "y": row["y"]})
            if reliable and row["life_state"] == 0
            else None,
            life_state=row["life_state"],
            last_seen=None,
            quality_flags=flags,
        )
    else:
        if row["observer_team"] != view or row["visibility"] not in {
            "visible",
            "hidden",
            "unknown",
        }:
            raise ValueError("Observer view mismatch")
        visibility = row["visibility"]
        if visibility != "visible" and (
            row["current_position"] is not None or row["visible_life_state"] is not None
        ):
            raise ValueError("Hidden data in observer input")
        last = row["last_seen"]
        if last is not None:
            if last["source_tick"] > row["source_tick"]:
                raise ValueError("Future last-seen")
            last = {
                "position": point(last["position"]),
                "source_tick": last["source_tick"],
                "time": last["time"],
            }
        base.update(
            visibility=visibility,
            current_position=point(row["current_position"]),
            life_state=row["visible_life_state"],
            last_seen=last,
            quality_flags=[],  # Never disclose omniscient diagnostics in a team view.
        )
    return base


class ReplayStore:
    """Pinned summary + per-view hashes. A team request never opens omniscient.jsonl."""

    def __init__(self, root: Path, events=None):
        self.root = root.resolve()
        self.events = events
        summary = read_json(self.root / "summary.json")
        self.entries = {m["match_id"]: m for m in summary["matches"]}
        if len(self.entries) != len(summary["matches"]):
            raise ValueError("Duplicate matches")
        self.cache = {}
        self.lock = RLock()

    def catalog(self):
        return sorted(self.entries, reverse=True)

    def load(self, mid, view):
        if mid not in self.entries or view not in VIEWS:
            raise ValueError("Unknown match or view")
        with self.lock:
            key = (mid, view)
            if key in self.cache:
                return self.cache[key]
            folder = self.root / "aligned" / str(mid)
            content = read_source_bytes(folder / "manifest.json")
            if hashlib.sha256(content).hexdigest() != self.entries[mid]["manifest_sha256"]:
                raise ValueError("Manifest hash mismatch")
            manifest = parse_source_json(content)
            if manifest["match_id"] != mid:
                raise ValueError("Match identity mismatch")
            content = read_source_bytes(folder / f"{view}.jsonl", max_bytes=128 * 1024**2)
            if hashlib.sha256(content).hexdigest() != manifest["files"][f"{view}.jsonl"]:
                raise ValueError("View hash mismatch")
            players = defaultdict(list)
            clock = {}
            row_count = 0
            for line in content.splitlines():
                row_count += 1
                row = parse_source_json(line)
                if row["match_id"] != mid:
                    raise ValueError("Row match mismatch")
                # Exclude omniscient pre/post match records, matching team time scope.
                if view == "omniscient" and row["time_scope"] != "in_match":
                    continue
                if type(row["source_tick"]) is not int or row["source_tick"] < 0:
                    raise ValueError("Invalid tick")
                if type(row["time"]) not in (int, float) or not math.isfinite(row["time"]):
                    raise ValueError("Invalid time")
                p = project(row, view)
                tick = p["source_tick"]
                if tick in clock and clock[tick] != p["time"]:
                    raise ValueError("Conflicting tick clock")
                clock[tick] = p["time"]
                players[p["player_slot"]].append(p)
            if row_count != manifest["counts"][view] or not players:
                raise ValueError("View count mismatch")
            indexed = {}
            for slot, rows in players.items():
                rows.sort(key=lambda r: r["source_tick"])
                if len({r["hero_id"] for r in rows}) != 1:
                    raise ValueError("Hero identity changed")
                grouped = defaultdict(list)
                for row in rows:
                    grouped[row["source_tick"]].append(row)
                unique = []
                for group in grouped.values():
                    row = dict(group[0])
                    if len(group) > 1:
                        # Keep the frame, withhold coordinates; never choose a duplicate.
                        row.update(current_position=None, life_state=None, last_seen=None)
                        row["display_issue"] = "duplicate_tick"
                    unique.append(row)
                indexed[slot] = ([r["source_tick"] for r in unique], unique)
            timeline = [{"tick": t, "time": clock[t]} for t in sorted(clock)]
            result = {"players": indexed, "timeline": timeline, "manifest": manifest}
            # Keep one view in memory; switching does not merge data from other views.
            self.cache = {key: result}
            return result

    def timeline(self, mid, view):
        data = self.load(mid, view)
        result = {
            "match_id": mid,
            "view": view,
            "frames": data["timeline"],
            "heroes": [
                {"slot": s, "hero_id": rows[0]["hero_id"]}
                for s, (_, rows) in sorted(data["players"].items())
            ],
        }

        if self.events is not None and view == "omniscient":
            evidence = self.events.load(mid, data["manifest"])
            valid = {f["tick"] for f in data["timeline"]}
            result["event_ticks"] = (
                sorted({t for _, t in evidence["groups"] if t in valid}) if evidence else []
            )
        return result

    def frame(self, mid, view, tick, trail=15):
        if not 0 <= trail <= 60:
            raise ValueError("Trail out of range")
        data = self.load(mid, view)
        if tick not in {f["tick"] for f in data["timeline"]}:
            raise ValueError("Unknown frame tick")
        now = next(f["time"] for f in data["timeline"] if f["tick"] == tick)
        output = []
        for slot, (ticks, rows) in sorted(data["players"].items()):
            i = bisect_right(ticks, tick) - 1
            if i < 0:
                output.append(
                    {
                        "player_slot": slot,
                        "hero_id": rows[0]["hero_id"],
                        "visibility": "unknown",
                        "current_position": None,
                        "last_seen": None,
                        "life_state": None,
                        "quality_flags": [],
                        "display_issue": "no_sample",
                        "position_status": "no_sample",
                        "segments": [],
                    }
                )
                continue
            row = dict(rows[i])
            if row["source_tick"] != tick:
                row.update(
                    current_position=None,
                    life_state=None,
                    visibility="unknown",
                    quality_flags=[],
                    display_issue="no_sample",
                )
            transitions = []
            if i > 0 and row["source_tick"] == tick and not row.get("display_issue"):
                prior = rows[i - 1]
                if tick - prior["source_tick"] <= MAX_GAP_TICKS:
                    old, new = prior["visibility"], row["visibility"]
                    if old == "visible" and new == "hidden":
                        transitions.append("disappeared")
                    elif old in {"hidden", "unknown"} and new == "visible":
                        transitions.append("appeared")
                    elif old != "unknown" and new == "unknown":
                        transitions.append("became_unknown")
                    if prior["life_state"] == 0 and row["life_state"] in (1, 2):
                        transitions.append("visible_death_state")
            row["position_status"] = position_status(row)
            row["transitions"] = transitions
            segments, segment = [], []
            previous = None
            breaks = 0
            reasons = Counter()
            # Fixed recent source-frame window, not a fabricated continuous path.
            for r in rows[max(0, i - trail) : i + 1] if trail else []:
                pos = r["current_position"]
                discontinuity = previous is not None and (
                    r["source_tick"] - previous["source_tick"] > MAX_GAP_TICKS
                    or r["time"] - previous["time"] > 1
                    or (
                        pos is not None
                        and previous["current_position"] is not None
                        and math.hypot(
                            pos["x"] - previous["current_position"]["x"],
                            pos["y"] - previous["current_position"]["y"],
                        )
                        > MAX_SEGMENT_DISTANCE
                    )
                )
                if pos is None:
                    # Legacy aggregate retained for existing API consumers.
                    reasons["observation_unavailable"] += 1
                    reasons[position_status(r)] += 1
                if previous is not None:
                    if (
                        r["source_tick"] - previous["source_tick"] > MAX_GAP_TICKS
                        or r["time"] - previous["time"] > 1
                    ):
                        reasons["sampling_gap"] += 1
                    if (
                        pos is not None
                        and previous["current_position"] is not None
                        and math.hypot(
                            pos["x"] - previous["current_position"]["x"],
                            pos["y"] - previous["current_position"]["y"],
                        )
                        > MAX_SEGMENT_DISTANCE
                    ):
                        reasons["position_jump"] += 1
                if pos is None or discontinuity:
                    if len(segment) > 1:
                        segments.append(segment)
                    segment = []
                    breaks += 1
                if pos is not None:
                    segment.append(pos)
                previous = r
            if len(segment) > 1:
                segments.append(segment)
            row.update(segments=segments, trail_breaks=breaks, break_reasons=dict(reasons))
            output.append(row)
        frame = {"match_id": mid, "view": view, "tick": tick, "time": now, "players": output}
        if self.events is not None and view == "omniscient":
            return self.events.attach(frame, data["manifest"])
        return frame
