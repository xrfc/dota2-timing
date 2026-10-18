"""Same-provider player correlation diagnostics; never export account identifiers."""

import hashlib
from collections import Counter
from itertools import combinations

from dota_items.data.contracts import SLOTS
from dota_items.data.source_io import parse_source_json, read_source_bytes

SPLITS = ("train", "validation", "test")


def account_status(value):
    # OpenDota anonymous sentinel, absent IDs and invalid values are not shared players.
    if value is None or type(value) is int and value in (0, 4294967295):
        return "unknown"
    if type(value) is not int or not 0 < value < 4294967295:
        return "invalid"
    return "known"


def audit_player_overlap(rows, paths, splits):
    """Read original JSON again and require the exact bytes used by the sample audit."""
    if splits is None:
        return {"schema_version": "player-overlap/1", "status": "not_checked_no_split"}
    if set(splits) != set(SPLITS):
        raise ValueError("Expected train/validation/test split keys")
    ids = [mid for name in SPLITS for mid in splits[name]]
    expected = [r["match_id"] for r in rows]
    if (
        len(set(ids)) != len(ids)
        or len(set(expected)) != len(expected)
        or set(ids) != set(expected)
    ):
        raise ValueError("Split matches must exactly cover unique audit matches")
    memberships = {name: set() for name in SPLITS}
    targets = {name: set() for name in SPLITS}
    split_for = {mid: name for name in SPLITS for mid in splits[name]}
    per_match, player_matches = [], {}
    parents = {mid: mid for mid in ids}

    def root(mid):
        while parents[mid] != mid:
            parents[mid] = parents[parents[mid]]
            mid = parents[mid]
        return mid

    for row in sorted(rows, key=lambda r: r["match_id"]):
        mid = row["match_id"]
        contents = read_source_bytes(paths[mid])
        if hashlib.sha256(contents).hexdigest() != row["sha256"]:
            raise ValueError("Player-overlap source changed after feasibility audit")
        raw = parse_source_json(contents)
        players = raw.get("players", [])
        if (
            raw.get("match_id") != mid
            or len(players) != 10
            or {p.get("player_slot") for p in players} != SLOTS
        ):
            raise ValueError("Player-overlap source identity mismatch")
        counts = Counter(account_status(p.get("account_id")) for p in players)
        known = [p["account_id"] for p in players if account_status(p.get("account_id")) == "known"]
        duplicate = len(known) - len(set(known))
        target = next(p for p in players if p["player_slot"] == row["target_slot"])
        target_known = account_status(target.get("account_id")) == "known"
        name = split_for[mid]
        memberships[name].update(known)
        if target_known:
            targets[name].add(target["account_id"])
        for account in set(known):
            previous = player_matches.setdefault(account, [])
            if previous:
                parents[root(mid)] = root(previous[0])
            previous.append(mid)
        per_match.append(
            {
                "match_id": mid,
                "split": name,
                "source_sha256": row["sha256"],
                "known_player_slots": counts["known"],
                "unknown_player_slots": counts["unknown"],
                "invalid_player_slots": counts["invalid"],
                "duplicate_known_slots": duplicate,
                "target_identity_known": target_known,
            }
        )
    components = {}
    for mid in sorted(ids):
        components.setdefault(root(mid), []).append(mid)
    pairs = []
    for a, b in combinations(SPLITS, 2):
        pairs.append(
            {
                "splits": [a, b],
                "shared_known_players": len(memberships[a] & memberships[b]),
                "shared_known_targets": len(targets[a] & targets[b]),
                "target_to_any_shared_players": len(
                    (targets[a] & memberships[b]) | (targets[b] & memberships[a])
                ),
            }
        )
    incomplete = any(r["unknown_player_slots"] or r["invalid_player_slots"] for r in per_match)
    duplicates = any(r["duplicate_known_slots"] for r in per_match)
    overlap = any(p["shared_known_players"] for p in pairs)
    return {
        "schema_version": "player-overlap/1",
        "status": "overlap_detected" if overlap else "no_observed_overlap",
        "identity_coverage_complete": not incomplete and not duplicates,
        "player_disjoint_verified": not (incomplete or duplicates or overlap),
        "summary": {
            "matches": len(rows),
            "known_distinct_players": len(player_matches),
            "repeated_known_players": sum(len(v) > 1 for v in player_matches.values()),
            "unknown_player_slots": sum(r["unknown_player_slots"] for r in per_match),
            "invalid_player_slots": sum(r["invalid_player_slots"] for r in per_match),
            "duplicate_known_slots": sum(r["duplicate_known_slots"] for r in per_match),
        },
        "split_pairs": pairs,
        "matches": per_match,
        "connected_match_groups": sorted(components.values()),
        "limitations": [
            "Identity refers to supplied OpenDota account IDs, not independently verified humans.",
            "Anonymous/invalid IDs never match; zero observed overlap does not prove independence.",
            "Connected groups inform future grouping, but do not replace the frozen split.",
            "No raw or hashed player IDs are exported. No training admission is granted.",
        ],
    }
