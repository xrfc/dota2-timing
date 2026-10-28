"""Read-only replay diagnostics. Consistency is not independent gameplay certification."""

import math
import re
from bisect import bisect_right
from collections import Counter, defaultdict

from dota_items.data.observer import ObserverIndex, player_id


def identity(row):
    return row["entity_index"], row["entity_serial"]


class TickIndex:
    """Last event at/before a tick; preserve input order for same-tick terminal/new events."""

    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda r: r["tick"])
        self.ticks = [r["tick"] for r in self.rows]

    def at(self, tick):
        i = bisect_right(self.ticks, tick) - 1
        return self.rows[i] if i >= 0 else None


def make_clock(raw):
    from gem.state.game_clock import GameClock, GamePause

    fields = dict(raw["game_clock"])
    fields["pauses"] = [GamePause(**p) for p in fields.get("pauses", [])]
    return GameClock(**fields)


def warning_audit(raw, quality, clock):
    """Classify every adapter warning by its actual raw tick, not its English wording."""
    rows = []
    for message in quality["adapter_issues"]:
        found = re.fullmatch(r"players\[(\d+)\]\.(position_log|times)\[(\d+)\]: .+", message)
        category, tick, second = "unclassified", None, None
        if found:
            p, field, index = found.groups()
            value = raw["players"][int(p)][field][int(index)]
            tick = value[0] if field == "position_log" else value
            second = clock.game_seconds_at(tick)
            if second is None:
                category = "missing_clock"
            elif second < 0:
                category = "pre_game"
            elif second > raw["duration"]:
                category = "post_duration"
            elif field == "position_log" and not all(
                type(v) in (int, float) and math.isfinite(v) for v in value[1:]
            ):
                category = "invalid_coordinates"
            else:
                category = "in_match_unexplained"
        rows.append(dict(message=message, category=category, source_tick=tick, time=second))
    return {"counts": dict(Counter(r["category"] for r in rows)), "rows": rows}


def inspect_match(raw, match, quality, jump_threshold=1200):
    """Join preserved state/visibility/position evidence; never interpolate or relabel."""
    if raw["match_id"] != match["match_id"]:
        raise ValueError("Match identity mismatch")
    if len(match["players"]) != 10 or len({p["player_slot"] for p in match["players"]}) != 10:
        raise ValueError("Expected ten unique players")
    clock = make_clock(raw)
    channels = match["context"]["channels"]
    states, visible, entities = defaultdict(list), defaultdict(list), defaultdict(list)
    for name, grouped, key in (
        ("coach_state_snapshots", states, lambda p: p["player_id"]),
        ("hero_visibility_events", visible, lambda p: p["player_id"]),
        ("entity_visibility_events", entities, identity),
    ):
        if channels.get(name) is None:
            raise ValueError(f"Required channel unavailable: {name}")
        for row in channels[name]:
            grouped[key(row["payload"])].append({**row["payload"], "source_ref": row["source_ref"]})
    state_ticks = {pid: defaultdict(list) for pid in states}
    for pid, rows in states.items():
        for row in rows:
            state_ticks[pid][row["tick"]].append(row)
    vis_index = {pid: TickIndex(rows) for pid, rows in visible.items()}
    entity_index = {key: TickIndex(rows) for key, rows in entities.items()}
    transitions, jumps, players = [], [], []
    hero_entity = Counter()
    hero_entity_examples = []
    for pid, events in visible.items():
        for row in events:
            entity = entity_index.get(identity(row), TickIndex([])).at(row["tick"])
            if entity is None:
                outcome = "missing_entity"
            elif all(row[k] == entity[k] for k in ("radiant_state", "dire_state")):
                outcome = "consistent"
            else:
                outcome = "state_mismatch"
            hero_entity[outcome] += 1
            if outcome != "consistent":
                hero_entity_examples.append(dict(player_id=pid, hero=row, entity=entity))
    for player in match["players"]:
        pid = player_id(player["player_slot"])
        positions = player["position_log"]
        coverage, life_counts, vis_counts = Counter(), Counter(), Counter()
        identities = set()
        rows = sorted(states.get(pid, []), key=lambda r: r["tick"])
        for previous, current in zip(rows, rows[1:], strict=False):
            if (previous["life_state"], identity(previous)) != (
                current["life_state"],
                identity(current),
            ):
                transitions.append(
                    dict(
                        player_slot=player["player_slot"],
                        time=clock.game_seconds_at(current["tick"]),
                        previous=previous,
                        current=current,
                        kind="identity_change"
                        if identity(previous) != identity(current)
                        else "life_state_change",
                    )
                )
        for pos in positions:
            tick = pos["source_tick"]
            linked = state_ticks.get(pid, {}).get(tick, [])
            coverage["position_rows"] += 1
            coverage["clock_mismatches"] += clock.game_seconds_at(tick) != pos["time"]
            # Verify the exported position against the referenced raw row as well.
            ref = re.fullmatch(r"players\[(\d+)\].position_log\[(\d+)\]", pos["source_ref"])
            if not ref:
                raise ValueError("Unexpected position source reference")
            p, i = map(int, ref.groups())
            source = raw["players"][p]["position_log"][i]
            coverage["position_source_mismatches"] += (
                source != [tick, pos["x"], pos["y"]] or raw["players"][p]["player_id"] != pid
            )
            if len(linked) != 1:
                coverage["state_join_not_unique"] += 1
                continue
            state = linked[0]
            identities.add(identity(state))
            life_counts[str(state["life_state"])] += 1
            event = vis_index.get(pid, TickIndex([])).at(tick)
            if event is None:
                coverage["visibility_missing"] += 1
            else:
                coverage["state_visibility_identity_mismatches"] += identity(state) != identity(
                    event
                )
                for team in ("radiant", "dire"):
                    vis_counts[team + ":" + event[team + "_state"]] += 1
        for previous, current in zip(positions, positions[1:], strict=False):
            distance = math.hypot(current["x"] - previous["x"], current["y"] - previous["y"])
            if distance >= jump_threshold:
                jumps.append(
                    dict(
                        player_slot=player["player_slot"],
                        distance_native_units=distance,
                        previous=previous,
                        current=current,
                        previous_states=state_ticks.get(pid, {}).get(previous["source_tick"], []),
                        current_states=state_ticks.get(pid, {}).get(current["source_tick"], []),
                        interpretation="unclassified_jump_not_automatically_teleport",
                    )
                )
        players.append(
            dict(
                player_slot=player["player_slot"],
                hero_id=player["hero_id"],
                counts=dict(coverage),
                identities=[list(v) for v in sorted(identities)],
                life_state_counts=dict(life_counts),
                visibility_at_positions=dict(vis_counts),
                x_range=[min(p["x"] for p in positions), max(p["x"] for p in positions)],
                y_range=[min(p["y"] for p in positions), max(p["y"] for p in positions)],
            )
        )
    return dict(
        schema_version="replay-semantics/1",
        match_id=match["match_id"],
        training_admission=False,
        independent_gameplay_verification=False,
        clock=raw["game_clock"],
        game_start_tick=raw["game_start_tick"],
        post_game_tick=raw.get("post_game_tick"),
        game_end_tick=raw["game_end_tick"],
        duration=raw["duration"],
        players=players,
        hero_entity_visibility=dict(hero_entity),
        hero_entity_exceptions=hero_entity_examples,
        life_transitions=transitions,
        jump_threshold_native_units=jump_threshold,
        jumps=jumps,
        adapter_warnings=warning_audit(raw, quality, clock),
        cleaning_actions=dict(Counter(r["action"] for r in quality["issues"])),
        quarantined_records=[r for r in quality["issues"] if r["action"] == "quarantine"],
        limitations=[
            "Position logs lack entity IDs; state joins are consistency, not identity proof.",
            "Hero/entity visibility share bitsets; agreement is not independent verification.",
            "Native coordinates have no certified map transform; jumps are not teleport labels.",
            "Life-state values are raw codes; semantic death/respawn mapping needs corroboration.",
        ],
    )


def mutate_positions(match, predicate):
    """Copy only changed coordinate rows; never mutate frozen inputs or other channels."""
    changed, count = {**match, "players": []}, 0
    for player in match["players"]:
        positions = []
        for row in player["position_log"]:
            if predicate(player, row):
                positions.append({**row, "x": row["x"] + 999999, "y": row["y"] - 999999})
                count += 1
            else:
                positions.append(row)
        changed["players"].append({**player, "position_log": positions})
    return changed, count


def check_observer_leakage(match):
    """All integer cutoffs/slots for hidden+unknown coordinates; selected future cutoffs."""
    baseline = ObserverIndex(match)
    results = []
    for team in ("radiant", "dire"):

        def should_change(player, row, team=team):
            if (player["player_slot"] < 5) == (team == "radiant"):
                return False
            timeline = baseline.visibility.get(player_id(player["player_slot"]))
            event = timeline.at_tick(row["time"], row["source_tick"]) if timeline else None
            return event is None or event["payload"][team + "_state"] != "visible"

        changed, count = mutate_positions(match, should_change)
        altered = ObserverIndex(changed)
        comparisons, failures = 0, []
        for player in match["players"]:
            slot = player["player_slot"]
            if (slot < 5) != (team == "radiant"):
                continue
            for cutoff in range(match["duration"] + 1):
                comparisons += 1
                if baseline.sample(slot, cutoff) != altered.sample(slot, cutoff):
                    failures.append(dict(slot=slot, cutoff=cutoff))
        results.append(
            dict(
                kind="hidden_and_unknown_coordinates",
                team=team,
                mutated_rows=count,
                comparisons=comparisons,
                failures=failures,
            )
        )
    cutoffs = sorted({0, 1, 30, match["duration"] // 2, match["duration"] - 1, match["duration"]})
    for cutoff in cutoffs:
        if not 0 <= cutoff <= match["duration"]:
            continue
        changed, count = mutate_positions(match, lambda p, r, cutoff=cutoff: r["time"] >= cutoff)
        altered = ObserverIndex(changed)
        failures = []
        for player in match["players"]:
            slot = player["player_slot"]
            if baseline.sample(slot, cutoff) != altered.sample(slot, cutoff):
                failures.append(dict(slot=slot, cutoff=cutoff))
        results.append(
            dict(
                kind="cutoff_bucket_and_future_coordinates",
                cutoff=cutoff,
                mutated_rows=count,
                comparisons=len(match["players"]),
                failures=failures,
            )
        )
    return dict(
        checks=results,
        passed=not any(r["failures"] for r in results),
        comparisons=sum(r["comparisons"] for r in results),
        scope="Coordinate perturbation only, not every field or independent visibility semantics.",
    )


def corroborate_deaths(raw, transitions, max_tick_distance=60):
    """Compare independent channels of ONE parser, not independent ground truth."""
    clock = make_clock(raw)
    names = {p["player_id"]: p["hero_name"].replace("_", "") for p in raw["players"]}
    deaths = []
    for i, row in enumerate(raw["combat_log"]):
        time = clock.game_seconds_at(row["tick"])
        if (
            row["log_type"] == "DEATH"
            and row.get("target_is_hero") is True
            and row.get("target_is_illusion") is False
            and time is not None
            and 0 <= time <= raw["duration"]
        ):
            deaths.append({**row, "source_ref": f"combat_log[{i}]"})
    entries = []
    used = Counter()
    for transition in transitions:
        previous, current = transition["previous"], transition["current"]
        if transition["kind"] != "life_state_change" or not (
            previous["life_state"] == 0 and current["life_state"] in (1, 2)
        ):
            continue
        pid = player_id(transition["player_slot"])
        candidates = [
            d
            for d in deaths
            if d["target_name"].replace("_", "") == names[pid]
            and abs(d["tick"] - current["tick"]) <= max_tick_distance
        ]
        # Do not silently choose one of multiple combat events.
        for candidate in candidates:
            used[candidate["source_ref"]] += 1
        entries.append(
            dict(
                player_slot=transition["player_slot"],
                time=transition["time"],
                state_ref=current["source_ref"],
                state_tick=current["tick"],
                candidates=candidates,
                candidate_count=len(candidates),
            )
        )
    return dict(
        max_tick_distance=max_tick_distance,
        method="0->1/2 candidate death; hero-name underscore alias; +/-60 ticks, no forced matches",
        candidate_transitions=len(entries),
        combat_hero_deaths=len(deaths),
        matched_once=sum(r["candidate_count"] == 1 for r in entries),
        unmatched=sum(r["candidate_count"] == 0 for r in entries),
        ambiguous=sum(r["candidate_count"] > 1 for r in entries),
        combat_deaths_unmatched=[d for d in deaths if not used[d["source_ref"]]],
        combat_deaths_reused=[ref for ref, count in used.items() if count > 1],
        entries=entries,
        independent_gameplay_verification=False,
    )


def run_audit(preparation, compat, output):
    """Validate consumed bytes against frozen manifests, audit, then publish new files."""
    import hashlib
    import inspect
    import json
    from pathlib import Path

    from gem.state.game_clock import GameClock

    from dota_items.data.context import validate_context
    from dota_items.data.source_io import parse_source_json, read_source_bytes
    from dota_items.data.validation import resolve_ref
    from dota_items.storage import file_hash

    if output.exists():
        raise ValueError("Output already exists; choose a new directory")

    # Raw/cleaned pilot files exceed the default 64 MiB, bounded explicitly at 512 MiB.
    def read(path):
        contents = read_source_bytes(path, max_bytes=512 * 1024 * 1024)
        return parse_source_json(contents), hashlib.sha256(contents).hexdigest()

    manifest, manifest_hash = read(preparation / "manifest.json")
    values, hashes = {}, {"manifest.json": manifest_hash}
    for name in ("raw.json", "cleaned.json", "quality.json"):
        values[name], hashes[name] = read(preparation / name)
        if hashes[name] != manifest["files"][name]:
            raise ValueError(f"Frozen input hash mismatch: {name}")
    compat_manifest, compat_hash = read(compat / "manifest.json")
    source_paths = [
        Path(__file__),
        Path(__file__).with_name("observer.py"),
        Path(__file__).with_name("context.py"),
        Path(__file__).with_name("validation.py"),
        Path(__file__).with_name("source_io.py"),
        Path(__file__).parents[1] / "contracts/replay_context.py",
        Path(inspect.getfile(GameClock)),
    ]
    code_hashes = {str(p): file_hash(p) for p in source_paths}
    if code_hashes[str(source_paths[-1])] != compat_manifest["patched"]["state/game_clock.py"]:
        raise ValueError("Loaded clock implementation differs from frozen compatibility copy")
    raw, match, quality = (values[n] for n in ("raw.json", "cleaned.json", "quality.json"))
    if manifest["match_id"] != match["match_id"]:
        raise ValueError("Manifest identity mismatch")
    validate_context(match, raw, True, resolve_ref)
    result = inspect_match(raw, match, quality)
    result["death_corroboration"] = corroborate_deaths(raw, result["life_transitions"])
    result["observer_leakage"] = check_observer_leakage(match)
    for name, digest in hashes.items():
        if file_hash(preparation / name) != digest:
            raise ValueError("Input changed during audit")
    if file_hash(compat / "manifest.json") != compat_hash:
        raise ValueError("Compatibility manifest changed during audit")
    for path, digest in code_hashes.items():
        if file_hash(Path(path)) != digest:
            raise ValueError("Implementation changed during audit")
    result["provenance"] = dict(
        preparation=str(preparation),
        preparation_id=manifest["preparation_id"],
        consumed_files=hashes,
        implementation=code_hashes,
        compatibility_manifest=str(compat / "manifest.json"),
        compatibility_sha256=compat_hash,
        validation="Consumed hashes and context payload/time refs; not a full bundle audit",
    )
    output.mkdir(parents=True, exist_ok=False)
    path = output / "audit.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    (output / "receipt.json").write_text(
        json.dumps(
            dict(
                match_id=match["match_id"],
                audit_sha256=file_hash(path),
                training_admission=False,
                leakage_passed=result["observer_leakage"]["passed"],
            ),
            indent=2,
        )
        + "\n"
    )
    return result
