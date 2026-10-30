"""M1 multi-hero match table built from stored OpenDota parsed matches.

Every read goes through source_io and is checked against its sibling
``<id>.manifest.json`` SHA-256; a mismatch or a missing manifest rejects the file.
"""

import collections
import hashlib
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes

DEFAULT_ROOTS = (
    "data/purchase-1000-2026-10-14",
    "data/purchase-additional-1000-2026-10-15",
)
RANK_NAMES = {
    1: "herald",
    2: "guardian",
    3: "crusader",
    4: "archon",
    5: "legend",
    6: "ancient",
    7: "divine",
    8: "immortal",
}
REQUIRED_PLAYER_FIELDS = (
    "purchase_log",
    "lh_t",
    "dn_t",
    "gold_t",
    "xp_t",
    "kills_log",
    "lane_role",
    "lane_efficiency_pct",
)


def match_files(roots):
    """Yield (match_path, manifest_path) for every stored match, sorted by path."""
    for root in roots:
        for path in sorted(Path(root).glob("batch-*/matches/*.json")):
            if not path.name.endswith(".manifest.json"):
                yield path, path.with_name(path.stem + ".manifest.json")


def load_match(path, manifest_path):
    """Return the parsed match after verifying bytes against the manifest."""
    if not manifest_path.exists():
        raise ValueError(f"Missing manifest: {path.name}")
    manifest = parse_source_json(read_source_bytes(manifest_path))
    contents = read_source_bytes(path)
    if hashlib.sha256(contents).hexdigest() != manifest["sha256"]:
        raise ValueError(f"Manifest hash mismatch: {path.name}")
    match = parse_source_json(contents)
    if match.get("match_id") != manifest["match_id"] or path.stem != str(manifest["match_id"]):
        raise ValueError(f"Match identity mismatch: {path.name}")
    return match


def inventory(matches):
    """Coverage counts used to write the M1 data card; no filtering happens here."""
    counts = collections.defaultdict(collections.Counter)
    missing = collections.Counter()
    match_ids = []
    players = 0
    for match in matches:
        match_ids.append(match["match_id"])
        counts["patch"][match.get("patch")] += 1
        counts["game_mode"][match.get("game_mode")] += 1
        counts["lobby_type"][match.get("lobby_type")] += 1
        counts["duration_bucket_min"][min(int(match.get("duration") or 0) // 600 * 10, 60)] += 1
        counts["player_count"][len(match.get("players") or [])] += 1
        for player in match.get("players") or []:
            players += 1
            tier = player.get("rank_tier")
            counts["rank"][RANK_NAMES.get(tier // 10, "other") if tier else None] += 1
            counts["lane_role"][player.get("lane_role")] += 1
            counts["leaver_status"][player.get("leaver_status")] += 1
            counts["hero_id"][player.get("hero_id")] += 1
            for field in REQUIRED_PLAYER_FIELDS:
                if player.get(field) is None:
                    missing[field] += 1
    duplicates = [m for m, n in collections.Counter(match_ids).items() if n > 1]
    return {
        "schema": "m1-inventory/1",
        "matches": len(match_ids),
        "unique_matches": len(set(match_ids)),
        "duplicate_match_ids": sorted(duplicates),
        "players": players,
        "distinct_heroes": len(counts["hero_id"]),
        "counts": {
            name: {str(k): v for k, v in sorted(c.items(), key=lambda kv: str(kv[0]))}
            for name, c in counts.items()
            if name != "hero_id"
        },
        "hero_player_counts": {str(k): v for k, v in sorted(counts["hero_id"].items())},
        "missing_player_fields": dict(sorted(missing.items())),
    }


LANE_MINUTE = 10
POSITION_MINUTE = 15
POSITION_MIN_GAP = 25  # U8: last-hit gap below this -> position unknown
COLLAPSED_CARRY_LH_10 = 35  # U8: user-chosen threshold

# When each column is knowable. Pre-game products (A/B) may only consume
# "pre_game" inputs; "lane_end" columns are labels or post-lane context.
FIELD_AVAILABILITY = {
    "match_id": "identifier",
    "start_time": "pre_game",
    "patch": "pre_game",
    "avg_rank_tier": "pre_game",
    "player_slot": "pre_game",
    "is_radiant": "pre_game",
    "hero_id": "pre_game",
    "rank_tier": "pre_game",
    "lane": "lane_end",
    "lane_role": "lane_end",
    "is_roaming": "lane_end",
    "lh_10": "lane_end",
    "lh_15": "minute_15",
    "dn_10": "lane_end",
    "gold_10": "lane_end",
    "xp_10": "lane_end",
    "kills_10": "lane_end",
    "deaths_10": "lane_end",
    "lane_efficiency_pct": "lane_end",
    "duration_s": "post_game",
    "win": "post_game",
}


def fully_parsed(match):
    players = match.get("players") or []
    return len(players) == 10 and all(p.get("purchase_log") is not None for p in players)


def _at_minute(series, minute):
    return series[minute] if isinstance(series, list) and len(series) > minute else None


def _count_before(log, seconds):
    return None if log is None else sum(1 for e in log if e["time"] < seconds)


def player_rows(match):
    """One row per player; columns are exactly FIELD_AVAILABILITY's keys."""
    if not fully_parsed(match):
        raise ValueError("Match is not fully parsed")
    tiers = [p["rank_tier"] for p in match["players"] if p.get("rank_tier")]
    avg_tier = round(sum(tiers) / len(tiers), 1) if tiers else None
    seconds = LANE_MINUTE * 60
    rows = []
    for p in match["players"]:
        rows.append(
            {
                "match_id": match["match_id"],
                "start_time": match["start_time"],
                "patch": match["patch"],
                "avg_rank_tier": avg_tier,
                "player_slot": p["player_slot"],
                "is_radiant": p["player_slot"] < 128,
                "hero_id": p["hero_id"],
                "rank_tier": p.get("rank_tier"),
                "lane": p.get("lane"),
                "lane_role": p.get("lane_role"),
                "is_roaming": p.get("is_roaming"),
                "lh_10": _at_minute(p.get("lh_t"), LANE_MINUTE),
                "lh_15": _at_minute(p.get("lh_t"), POSITION_MINUTE),
                "dn_10": _at_minute(p.get("dn_t"), LANE_MINUTE),
                "gold_10": _at_minute(p.get("gold_t"), LANE_MINUTE),
                "xp_10": _at_minute(p.get("xp_t"), LANE_MINUTE),
                "kills_10": _count_before(p.get("kills_log"), seconds),
                "deaths_10": _count_before(p.get("deaths_log"), seconds),
                "lane_efficiency_pct": p.get("lane_efficiency_pct"),
                "duration_s": match["duration"],
                "win": bool(p.get("win")),
            }
        )
    return rows


def purchase_rows(match):
    """Every logged purchase (including pre-horn negative times) in log order."""
    if not fully_parsed(match):
        raise ValueError("Match is not fully parsed")
    return [
        {
            "match_id": match["match_id"],
            "player_slot": p["player_slot"],
            "hero_id": p["hero_id"],
            "time_s": e["time"],
            "item": e["key"],
        }
        for p in match["players"]
        for e in p["purchase_log"]
    ]


def assign_positions(rows):
    """U8 safelane rule. Adds ``position`` (1, 5 or None) and ``collapsed_carry``.

    Position comes from 15-minute last hits, i.e. the role actually played;
    it is a lane_end-or-later fact, not pre-game data. Rows are not mutated.
    """
    teams = {}
    for row in rows:
        if row["lane_role"] == 1:
            teams.setdefault((row["match_id"], row["is_radiant"]), []).append(row)
    positions = {}
    for safelane in teams.values():
        if len(safelane) != 2 or any(r["lh_15"] is None for r in safelane):
            continue
        high, low = sorted(safelane, key=lambda r: -r["lh_15"])
        if high["lh_15"] - low["lh_15"] >= POSITION_MIN_GAP:
            positions[(high["match_id"], high["player_slot"])] = 1
            positions[(low["match_id"], low["player_slot"])] = 5
    result = []
    for row in rows:
        position = positions.get((row["match_id"], row["player_slot"]))
        collapsed = (
            position == 1 and row["lh_10"] is not None and row["lh_10"] < COLLAPSED_CARRY_LH_10
        )
        result.append({**row, "position": position, "collapsed_carry": collapsed})
    return result
