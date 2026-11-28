"""Attach observed post-action resource deltas and dead time to development opportunities."""

import argparse
import gzip
import json
import re
import tempfile
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from lane_study_data import capture, file_hash, fold_for

from dota_items.data.awareness_split import is_holdout
from dota_items.storage import read_json, write_json

TARGETS = ("gold", "xp", "dead_seconds")
METRICS = ("hits", "death", *TARGETS)


def players(path, mid):
    """Decode the normalized players array without materializing the large combat channel."""
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        buf = stream.read(4096)
        start = re.search(r'"players"\s*:\s*\[', buf)
        if start is None:
            raise ValueError(f"{mid}: missing normalized players header")
        header = json.loads(buf[: start.start()].rstrip().removesuffix(",") + "}")
        if header.get("match_id") != mid:
            raise ValueError(f"{mid}: wrong normalized match")
        buf = buf[start.end() :]
        decoder = json.JSONDecoder()
        while True:
            buf = buf.lstrip()
            if not buf:
                buf = stream.read(1024 * 1024)
                if not buf:
                    raise ValueError(f"{mid}: truncated players array")
                continue
            if buf[0] == "]":
                return
            while True:
                try:
                    player, stop = decoder.raw_decode(buf)
                    break
                except json.JSONDecodeError:
                    chunk = stream.read(max(1024 * 1024, len(buf)))
                    if not chunk:
                        raise
                    buf += chunk
            yield player
            buf = buf[stop:].lstrip()
            while not buf:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    raise ValueError(f"{mid}: truncated players array")
                buf = chunk.lstrip()
            if buf[0] == "]":
                return
            if buf[0] != ",":
                raise ValueError(f"{mid}: invalid players array")
            buf = buf[1:]


def xp_endpoints(path, mid, wanted):
    result = {}
    for player in players(path, mid):
        slot = player["player_slot"]
        pid = slot if slot < 128 else slot - 128 + 5
        if pid not in wanted:
            continue
        if pid in result:
            raise ValueError(f"{mid}: duplicate player slot")
        values = result[pid] = {}
        for obs in player.get("economy_log") or ():
            t, value = obs["time"], obs.get("xp_progress")
            if t in wanted[pid]:
                values[t] = value if values.get(t, value) == value else None
    return result


def window_labels(t, death, states, xp):
    start = states.get(t + 6, {})
    end = states.get(t + 20, {})
    values = dict.fromkeys(TARGETS)
    reasons = {}
    if start.get("cash") is None or end.get("cash") is None:
        reasons["gold"] = "missing_endpoint"
    else:
        values["gold"] = end["cash"] - start["cash"]
    pid = start.get("player_id")
    experience = xp.get(pid, {})
    before, after = (experience.get(t + offset) for offset in (6, 20))
    if pid is None or pid != end.get("player_id") or before is None or after is None:
        reasons["xp"] = "missing_endpoint"
    elif not start.get("level") or start["level"] != end.get("level"):
        reasons["xp"] = "unverified_level_transition"
    elif after < before:
        reasons["xp"] = "decreasing_same_level"
    else:
        values["xp"] = after - before
    life = [states.get(t + k, {}).get("life_state") for k in range(7, 21)]
    if any(v not in (0, 1, 2) for v in life):
        reasons["dead_seconds"] = "missing_life_state"
    elif not death and any(life):
        reasons["dead_seconds"] = "life_state_without_window_death"
    else:
        values["dead_seconds"] = sum(v in (1, 2) for v in life)
    return values, reasons


def enrich(rows, states, xp):
    result = []
    for row in rows:
        if row["outcome_eligible"]:
            values, reasons = window_labels(row["t"], row["death"], states.get(row["hero"], {}), xp)
        else:
            values, reasons = dict.fromkeys(TARGETS), {}
        result.append({**row, **values, "label_exclusions": reasons})
    return result


def label_match(root, mid, rows):
    wanted = defaultdict(set)
    for row in rows:
        if row["outcome_eligible"]:
            wanted[row["hero"]].update(range(row["t"] + 6, row["t"] + 21))
    if not wanted:
        return enrich(rows, {}, {})
    states = defaultdict(dict)
    for frame in capture(root, "state-v3", mid, "gem-state-capture/3"):
        sec = frame["t"]
        for hero in frame["heroes"]:
            name = hero["hero"]
            if sec in wanted.get(name, ()):
                states[name][sec] = resource_state(hero)
    return enrich_from_states(root, mid, rows, states)


def resource_state(hero):
    gold = (hero.get("reliable_gold"), hero.get("unreliable_gold"))
    return {
        "cash": None if None in gold else sum(gold),
        **{k: hero.get(k) for k in ("player_id", "life_state", "level")},
    }


def enrich_from_states(root, mid, rows, states):
    times = defaultdict(set)
    for row in rows:
        if row["outcome_eligible"]:
            for sec in (row["t"] + 6, row["t"] + 20):
                pid = states[row["hero"]].get(sec, {}).get("player_id")
                if pid is not None:
                    times[pid].add(sec)
    xp = xp_endpoints(root / "parsed" / f"{mid}.normalized.json.gz", mid, times)
    return enrich(rows, states, xp)


def development_job(job):
    root, mid, rows, hashes = job
    if is_holdout(mid) or any(row["match"] != mid or row["fold"] != fold_for(mid) for row in rows):
        raise ValueError("unexpected development identity")
    for folder, ext in (("parsed", "normalized.json.gz"), ("state-v3", "jsonl.gz")):
        name = f"{folder}/{mid}.{ext}"
        if file_hash(root / name) != hashes[name]:
            raise ValueError(f"{mid}: {folder} changed since lane sample construction")
    return label_match(root, mid, rows)


def describe(rows, targets=METRICS):
    eligible = [r for r in rows if r["outcome_eligible"]]
    actions = sorted({r["action"] for r in eligible})
    by_action = {}
    for action in actions:
        group = [r for r in eligible if r["action"] == action]
        metrics = {}
        for key in targets:
            values = [r[key] for r in group if r[key] is not None]
            metrics[key] = {
                "observed": len(values),
                "mean": sum(values) / len(values) if values else None,
                "missing": len(group) - len(values),
            }
        by_action[action] = metrics
    return {
        "rows": len(rows),
        "matches": len({r["match"] for r in rows}),
        "eligible": len(eligible),
        "actions": dict(Counter(r["action"] for r in rows)),
        "by_action": by_action,
        "label_exclusions": dict(
            Counter(
                f"{key}/{reason}" for r in eligible for key, reason in r["label_exclusions"].items()
            )
        ),
    }


def write_dataset(out, rows, metadata):
    if out.exists():
        raise FileExistsError(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        folder = Path(tmp) / "dataset"
        folder.mkdir()
        path = folder / "rows.jsonl"
        with path.open("x", encoding="utf-8") as stream:
            for row in rows:
                print(json.dumps(row, allow_nan=False), file=stream)
        write_json(folder / "summary.json", {**metadata, "rows_sha256": file_hash(path)})
        folder.rename(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("root", "lane", "out"):
        parser.add_argument("--" + arg, required=True, type=Path)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    manifest = read_json(args.lane / "manifest.json")
    path = args.lane / "rows.jsonl"
    if (
        manifest.get("cohort_mode") != "full"
        or not manifest["supported"]
        or any(is_holdout(mid) for mid in manifest["matches"])
        or file_hash(path) != manifest["rows_sha256"]
        or args.out.exists()
    ):
        parser.error("expected an intact full development dataset and new output")
    by_match = defaultdict(list)
    for line in path.read_text().splitlines():
        row = json.loads(line)
        by_match[row["match"]].append(row)
    jobs = [
        (args.root, mid, rows, manifest["inputs_sha256"][str(mid)])
        for mid, rows in by_match.items()
    ]
    result = []
    with ProcessPoolExecutor(args.workers) as pool:
        for i, part in enumerate(pool.map(development_job, jobs), 1):
            result.extend(part)
            if i % 50 == 0:
                print(i, "matches labeled", flush=True)
    write_dataset(
        args.out,
        result,
        {
            "schema": "outcome-labels/1",
            "domain": "wave",
            "split": "development",
            "lane_manifest_sha256": file_hash(args.lane / "manifest.json"),
            "source_sha256": file_hash(Path(__file__)),
            **describe(result),
        },
    )


if __name__ == "__main__":
    main()
