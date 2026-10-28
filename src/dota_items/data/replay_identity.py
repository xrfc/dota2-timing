"""Read-only comparisons of direct entity sampling against frozen replay coordinates."""

import math
from collections import defaultdict


def native_position(row):
    values = [row.get(k) for k in ("cell_x", "cell_y", "vec_x", "vec_y")]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        return None
    return [values[0] * 128 + values[2], values[1] * 128 + values[3]]


def compare_positions(raw, captured):
    """Match complete per-player ordered sequences, including duplicate ticks."""
    if raw["match_id"] != captured["match_id"]:
        raise ValueError("Replay match identity mismatch")
    by_player = defaultdict(list)
    for i, row in enumerate(captured["positions"]):
        if type(row["player_id"]) is not int or row["player_id"] not in range(10):
            raise ValueError("Invalid captured player slot")
        by_player[row["player_id"]].append((i, row))
    if len(raw["players"]) != 10 or {p["player_id"] for p in raw["players"]} != set(range(10)):
        raise ValueError("Expected ten unique source players")
    links, stats = [], []
    for p, player in enumerate(raw["players"]):
        pid = player["player_id"]
        rows = by_player[pid]
        if len(rows) != len(player["position_log"]):
            raise ValueError(f"Position count mismatch for slot {pid}")
        identities, fallback = set(), 0
        for j, (old, (index, row)) in enumerate(zip(player["position_log"], rows, strict=True)):
            if old != [row["tick"], row["x"], row["y"]]:
                raise ValueError(f"Position sequence mismatch at slot {pid}, row {j}")
            if native_position(row) != [row["x"], row["y"]]:
                raise ValueError("Coordinate component mismatch")
            if row["hero_name"] != player["hero_name"]:
                raise ValueError("Hero name mismatch")
            identities.add((row["entity_index"], row["entity_serial"]))
            fallback += not row["canonical_for_slot"]
            links.append(
                {"raw_ref": f"players[{p}].position_log[{j}]", "capture_ref": f"positions[{index}]"}
            )
        stats.append(
            {
                "player_id": pid,
                "positions": len(rows),
                "identities": [list(k) for k in sorted(identities)],
                "noncanonical_samples": fallback,
            }
        )
    landmarks = []
    for i, row in enumerate(captured["landmarks"]):
        landmarks.append(
            {**row, "native_xy": native_position(row), "capture_ref": f"landmarks[{i}]"}
        )
    return {
        "match_id": raw["match_id"],
        "game_build": captured["game_build"],
        "positions_compared": len(links),
        "players": stats,
        "links": links,
        "landmarks": landmarks,
        "training_admission": False,
        "map_transform_verified": False,
    }
