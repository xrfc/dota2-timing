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
