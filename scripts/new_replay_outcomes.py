"""Apply the frozen U191 action-value models to a newly prepared, independent replay."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import outcome_domains as domains
from lane_study_data import PATCH_WINDOW, file_hash, match_rows, normalized_end
from outcome_final import FREEZE, REPORTS, ROOT, WORK, verify, versions
from outcome_labels import label_match, players
from outcome_values import DOMAINS, score

from dota_items.data.awareness_split import is_holdout
from dota_items.storage import read_json

FREEZE_SHA256 = "ed7655af753a2e8fe4fbb99646fec649837433587aea4708bc60d26776487720"


def _frozen(mid, map_dir):
    if type(mid) is not int or mid <= 0 or is_holdout(mid):
        raise ValueError("requires a new non-reserved match")
    if file_hash(FREEZE) != FREEZE_SHA256:
        raise ValueError("U191 freeze fingerprint changed")
    frozen = read_json(FREEZE)
    verify(ROOT, frozen["sources"])
    verify(map_dir, frozen["map"])
    verify(WORK, frozen["models"])
    if versions() != frozen["versions"]:
        raise ValueError("frozen runtime versions changed")
    # The frozen dataset digest binds the full development rows, including excluded opportunities.
    for domain in DOMAINS:
        directory = REPORTS / (
            "outcome-labels" if domain == "wave" else f"outcome-domains/{domain}"
        )
        digest = hashlib.sha256()
        with (directory / "rows.jsonl").open("rb") as stream:
            for line in stream:
                digest.update(line)
                if json.loads(line)["match"] == mid:
                    raise ValueError("match previously appeared in development")
        if digest.hexdigest() != frozen["development"][domain]["rows_sha256"]:
            raise ValueError(f"cannot establish independence from {domain} development")
    return frozen


def _input_info(root, mid):
    meta = read_json(root / "replay-provenance.json")
    paths = {
        f"parsed/{mid}.normalized.json.gz",
        f"state-v3/{mid}.jsonl.gz",
        f"extras-v1/{mid}.jsonl.gz",
    }
    if meta.get("match_id") != mid or set(meta["inputs_sha256"]) != paths:
        raise ValueError("wrong replay identity or prepared input file list")
    if (root / "gank-inputs-v2" / f"{mid}.pkl").exists():
        raise ValueError("new replay inference requires uncached normalized inputs")
    verify(root, meta["inputs_sha256"])
    norm = root / "parsed" / f"{mid}.normalized.json.gz"
    duration = normalized_end(norm, mid)
    start, end = meta["estimated_start_time"], meta["end_time"]
    if not (
        meta["patch_window"] == "7.41f"
        and PATCH_WINDOW[0] <= start <= end < PATCH_WINDOW[1]
        and meta["game_mode"] == 22
        and duration >= 900
        and meta["duration"] == duration
        and end - start == duration
    ):
        raise ValueError("unsupported patch, game mode, duration or clock")
    slots = sorted(player["player_slot"] for player in players(norm, mid))
    if slots != [0, 1, 2, 3, 4, 128, 129, 130, 131, 132]:
        raise ValueError("expected ten standard player slots")
    return meta


def _other_rows(root, mid):
    """Run the frozen jungle/support builders on a new input without a collection receipt."""
    match = domains.readonly_match(root, mid)
    end = min(match["last"], normalized_end(root / "parsed" / f"{mid}.normalized.json.gz", mid))
    heroes = sorted(h for h, role in match["positions"].items() if role == 1)
    visibility = {k: sorted(v) for k, v in match["seen"].items()}
    damage = domains.hero_hits_by_second(match)
    lane = {h: domains.farm_seconds(match["combat"], h, match["tracks"][h]["team"]) for h in heroes}
    jungle = {h: domains.jungle_seconds(match["combat"], h) for h in heroes}
    signals = {h: domains.support_anchors(match["tracks"], damage, h) for h in heroes}
    wanted = {h: set(jungle[h]) | set(signals[h]) for h in heroes}
    resources, states = defaultdict(dict), defaultdict(dict)
    match["dead_at"] = defaultdict(set)
    for frame in domains.capture(root, "state-v3", mid, "gem-state-capture/3"):
        t = frame["t"]
        for hero in frame["heroes"]:
            name = hero["hero"]
            if hero.get("life_state") in (1, 2):
                match["dead_at"][t].add(name)
            if name in wanted:
                resources[name][t] = domains.resource_state(hero)
                if t in wanted[name]:
                    states[name][t] = hero

    camps, means = domains.knowledge()
    points = {c["id"]: (c["x"], c["y"]) for c in camps}
    rows = []
    for h in heroes:
        own = match["tracks"][h]["pos"]
        deaths = domains.death_times(match["combat"], h)
        for evidence, _, _ in domains.make_jungle_cases(
            match, mid, h, jungle[h], visibility, states[h], means, deaths, camps
        ):
            t = evidence["t"]
            if t > end:
                continue
            action = domains.jungle_action(own, t, points[evidence["camp_id"]], jungle[h])
            rows.append(
                domains.record(
                    evidence,
                    "jungle",
                    states[h][t],
                    evidence["camp_distance"],
                    None,
                    action,
                    jungle[h],
                    deaths,
                    end,
                    damage,
                    lane[h],
                    jungle[h],
                )
            )
        all_hits = sorted(lane[h] + jungle[h])
        for t, signal in signals[h].items():
            if t > end or t not in states[h]:
                continue
            ally = signal["hero"]
            ally_pos = match["tracks"][ally]["pos"]
            evidence = domains._context(match, mid, h, t, visibility, states[h][t], means)
            action = domains.support_action(own, t, ally_pos[t])
            row = domains.record(
                evidence,
                "support",
                states[h][t],
                signal["distance"],
                signal["seconds_ago"],
                action,
                all_hits,
                deaths,
                end,
                damage,
                lane[h],
                jungle[h],
            )
            seconds = [s for s in range(t + 7, t + 21) if ally in damage.get(s, ())]
            row["arrival"] = (
                domains.arrived(own, ally_pos, t, seconds, resources[h])
                if row["outcome_eligible"]
                else None
            )
            row["target_hit_again"] = bool(seconds) if row["outcome_eligible"] else None
            rows.append(row)
    return domains.enrich_from_states(root, mid, rows, resources) if rows else [], heroes


def infer(root, mid, map_dir):
    """Return (domain, scored row, post-weight imbalance) cases and JSON-safe diagnostics."""
    root, map_dir = Path(root), Path(map_dir)
    frozen = _frozen(mid, map_dir)
    meta = _input_info(root, mid)
    if (
        meta.get("schema") != "new-replay-inputs/1"
        or meta.get("compat_manifest_sha256") != frozen["compat"]["manifest.json"]
        or meta.get("parser_version") != frozen["versions"]["gem-dota"]
        or meta.get("player_count") != 10
    ):
        raise ValueError("prepared replay lacks verified U191 parser or player provenance")
    wave = label_match(root, mid, match_rows((mid, root, map_dir, root)))
    other, heroes = _other_rows(root, mid)
    cases = []
    stats = {}
    for domain in DOMAINS:
        rows = wave if domain == "wave" else [r for r in other if r["domain"] == domain]
        eligible = [r for r in rows if r["outcome_eligible"]]
        model = joblib.load(WORK / f"{domain}.joblib")
        supported = balanced = 0
        for row in score(model, eligible):
            after = None
            if row["overlap_reason"] is None:
                after = model["strata"][row["stratum"]]["balance"]["after"]
                supported += 1
                balanced += int(after is not None and after <= 0.25)
            cases.append((domain, row, after))
        stats[domain] = dict(
            opportunities=len(rows),
            eligible=len(eligible),
            balanced=balanced,
            supported=supported,
            actions=dict(Counter(r["action"] for r in rows)),
            early_deaths=sum(r["early_death"] for r in rows),
            incomplete_windows=sum(not r["window_complete"] for r in rows),
        )
    cases.sort(key=lambda item: (item[1]["t"], item[1]["hero"], item[0]))
    diagnostics = dict(
        match_id=mid,
        observed_heroes=heroes,
        by_domain=stats,
        freeze_sha256=FREEZE_SHA256,
        models=frozen["models"],
        data_source=meta["source_sha256"],
        prepared_inputs=meta["inputs_sha256"],
        rank_tier=meta.get("rank_tier"),
        lobby_type=meta.get("lobby_type"),
        patch_window=meta["patch_window"],
        game_mode=meta["game_mode"],
        population_verified=False,
    )
    return cases, diagnostics
