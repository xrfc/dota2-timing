"""Engineering checks for temporal bounds and hidden/future payload independence."""

import copy
import hashlib
import json
from collections import Counter

from dota_items.data.patch_decision_view import VisionDecisionIndex


def _known(index, frame, team, *, time=None, tick=None):
    return index.at(
        game_time=frame["game_time"] if time is None else time,
        replay_tick=frame["tick"] if tick is None else tick,
        observer_team=team,
        max_age_seconds=1,
    )["known_view"]


def _check_rows(capture, frame, known, team):
    """Independent direct word/identity/position arithmetic, not the view implementation."""
    catalog, states = capture["entity_catalog"], capture["states"]
    rows = {
        tuple(
            (catalog[states[s][0]]["entity_index"], catalog[states[s][0]]["entity_serial"])
        ): states[s]
        for s in frame["entity_state_ids"]
    }
    name = "radiant" if team == 2 else "dire"
    ref = frame["team_word_refs"].get(name)
    words = {} if ref is None else dict(capture["team_word_snapshots"][ref["snapshot_id"]])
    canonical = {
        pid: (catalog[eid]["entity_index"], catalog[eid]["entity_serial"])
        for pid, eid, _ in frame["canonical_heroes"]
    }
    checked = Counter()
    for entity in [*known["friendly_heroes"], *known["visible_entities"]]:
        if entity.get("status") == "unknown":
            raise ValueError("Unproven friendly roster slots must not be enumerated")
        ident = entity["identity"]["entity_index"], entity["identity"]["entity_serial"]
        row = rows[ident]
        raw_entity = catalog[row[0]]
        if (
            row[3] is not True
            or row[7] is not False
            or entity.get("team") != row[4]
            or entity.get("class_name") != raw_entity["class_name"]
            or entity.get("npc_name") != raw_entity.get("npc_name_first_seen")
            or raw_entity["class_name"] == "CDOTA_TempTree"
            or capture["field_schemas"]
            .get(raw_entity["class_name"], {})
            .get("is_networked_npc_schema")
            is not True
        ):
            raise ValueError("Projected entity violates original schema/team/spawn evidence")
        word = words.get(ident[0] // 64)
        if word is None or (word // (2 ** (ident[0] % 64))) % 2 != 1:
            raise ValueError("Projected identity lacks this observer's original visible bit")
        if entity.get("position") is not None and entity["position"] != {"x": row[1], "y": row[2]}:
            raise ValueError("Projected coordinate differs from same-packet raw state")
        if "player_id" in entity:
            if canonical.get(entity["player_id"]) != ident or row[4] != team:
                raise ValueError("Friendly canonical identity/team mismatch")
            if entity["observed_state"] != {"life_state": row[5], "health": row[6]}:
                raise ValueError("Friendly raw health/life mismatch")
            if row[5] != 0 and entity["position"] is not None:
                raise ValueError("Dead friendly body location was exposed")
            checked["friendly_raw_state_checks"] += 1
        else:
            if row[5] != 0 or row[7] is not False:
                raise ValueError("Waiting or nonliving entity projected as a live target")
            if any(k in entity for k in ("health", "observed_state", "player_id", "owner_handle")):
                raise ValueError("Nonfriendly projection includes unapproved fields")
            checked["visible_live_entity_checks"] += 1
    return checked


def audit_decision_views(capture, index, *, source_ref, perturbation_time=900):
    frames = [f for f in capture["frames"] if f["game_time"] >= 0]
    counts, digest = Counter(), hashlib.sha256()
    for frame in frames:
        for team in (2, 3):
            known = _known(index, frame, team)
            observation = known["observation"]
            if (
                observation["status"] != "available"
                or observation["tick"] != frame["tick"]
                or observation["game_time"] != frame["game_time"]
            ):
                raise ValueError("Exact packet query did not select its own observation")
            counts.update(_check_rows(capture, frame, known, team))
            counts["exact_packet_queries"] += 1
            digest.update(
                json.dumps(
                    known, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            )
            for time, tick in (
                (frame["game_time"] - 1e-6, frame["tick"]),
                (frame["game_time"], frame["tick"] - 1),
            ):
                if time < 0 or tick < 0:
                    continue
                previous = _known(index, frame, team, time=time, tick=tick)["observation"]
                if previous["status"] == "available" and (
                    previous["game_time"] > time or previous["tick"] > tick
                ):
                    raise ValueError("Later packet crossed a decision cutoff")
                counts["strict_cutoff_queries"] += 1
    if not frames:
        raise ValueError("No game frames for engineering validation")
    cut = max(
        (f for f in frames if f["game_time"] <= perturbation_time),
        key=lambda f: f["game_time"],
        default=frames[0],
    )
    prefix = [f for f in capture["frames"] if f["tick"] <= cut["tick"]]
    used = {sid for f in prefix for sid in f["entity_state_ids"]}
    used.update(e["state_id"] for e in capture["temporary_tree_events"] if e["tick"] <= cut["tick"])
    future = copy.deepcopy(capture)
    future_rows = 0
    for sid, row in enumerate(future["states"]):
        if sid not in used and row[1] is not None:
            row[1] += 123.25
            row[2] -= 81.5
            if row[6] is not None:
                row[6] += 17
            future_rows += 1
    future_index = VisionDecisionIndex(future, exact_patch="7.42", source_ref=source_ref)
    for team in (2, 3):
        if _known(future_index, cut, team) != _known(index, cut, team):
            raise ValueError("Future payload changed prior observer evidence")
    del future_index, future
    hidden_counts = {}
    for team, name in ((2, "radiant"), (3, "dire")):
        altered = copy.deepcopy(capture)
        ref = cut["team_word_refs"].get(name)
        words = {} if ref is None else dict(capture["team_word_snapshots"][ref["snapshot_id"]])
        changed = 0
        for sid in cut["entity_state_ids"]:
            row = altered["states"][sid]
            entity = capture["entity_catalog"][row[0]]
            bit = entity["entity_index"]
            word = words.get(bit // 64)
            if row[4] != team and (word is None or (word // 2 ** (bit % 64)) % 2 == 0):
                row[4] = team
                if row[1] is not None:
                    row[1] += 231.5
                    row[2] -= 97.25
                if row[6] is not None:
                    row[6] += 29
                changed += 1
        other = VisionDecisionIndex(altered, exact_patch="7.42", source_ref=source_ref)
        if _known(other, cut, team) != _known(index, cut, team):
            raise ValueError("Hidden payload changed this observer's evidence")
        hidden_counts[name] = changed
        del other, altered
    return {
        "schema": "patch-decision-view-audit/1",
        "match_id": capture["match_id"],
        "counts": dict(counts),
        "known_views_sha256": digest.hexdigest(),
        "perturbation": {
            "cutoff_game_time": cut["game_time"],
            "cutoff_tick": cut["tick"],
            "future_state_rows_changed": future_rows,
            "hidden_state_rows_changed": hidden_counts,
            "future_and_hidden_known_views_unchanged": True,
        },
        "training_allowed": False,
        "action_review_allowed": False,
        "limits": [
            "Perturbations check this engineering projection, not game FOW or model quality.",
            "Provenance fingerprints change under mutation; compare known views separately.",
        ],
    }
