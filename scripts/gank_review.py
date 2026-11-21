"""B0 spot check: 2D playback of the sampled gank episodes, with a judgment form (U134).

    PYTHONPATH=src .venv/bin/python scripts/gank_review.py build \
        --root data/demos-2026-11 --episodes reports/gank-episodes-2026-11-10
    PYTHONPATH=src .venv/bin/python scripts/gank_review.py serve \
        --episodes reports/gank-episodes-2026-11-10

After the rule is frozen (U143) a fresh sample is checked with a blind second opinion:

    ... gank_review.py sample --episodes <frozen round> --exclude <its sample.json> --out <new>
    ... gank_review.py build --root data/demos-2026-11 --episodes <new>
    ... gank_review.py packet --episodes <new>          # text clips for the second reader
    (run <new>/codex/run_all.sh)
    ... gank_review.py compare --episodes <new>         # writes review-list.json
    ... gank_review.py serve --episodes <new>           # shows only the listed clips, blind
    ... gank_review.py score --episodes <new>           # after the user's review

`match --episodes <round> --match-id <id> --out <new>` followed by `build` and `serve`
shows every position 1 death of one match with the rule's class: a first per-match death
report (U139 draft).

`build` keeps what it reads from each sampled match in `<root>/gank-clip-inputs-v1/` and
reuses it while the source files are unchanged (`--no-cache` reads them again).

`build` reads `sample.json` and writes `review-clips.json` next to it (refuses to
overwrite): 30 seconds before each episode to 5 seconds after it. `serve` shows the clips
on the map at http://127.0.0.1:8771 and saves the user's judgments to `judgments.json` in
the same folder. Loopback only; the clips are omniscient review material, not model input.
"""

import argparse
import gzip
import hashlib
import json
import pickle
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dota_items.data.awareness_split import is_holdout
from dota_items.data.death_tags import death_tags, primary_reason
from dota_items.data.gank_depth import PARAMS as DEPTH_PARAMS
from dota_items.data.gank_depth import _distance, standing_towers, tower_deaths
from dota_items.data.gank_events import visibility_table
from dota_items.data.gank_review import (
    ACCEPTANCE_QUOTA,
    ANSWERS,
    acceptance_score,
    agreement,
    build_clip,
    clip_text,
    draw_acceptance,
    review_list,
    rule_category,
    validate_judgment,
    ward_spans,
)
from dota_items.data.map_api import MapKnowledge
from dota_items.data.teleports import arrived_near, teleports

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).with_name("gank_review_assets")
MAP = ROOT / "data/map-reference-2026-10-26-v1/gem/assets/maps/Game_map_7.41.jpg"
MAP_DRAFT = ROOT / "reports/map-regions-draft-2026-11-13-v7/regions-grid.json"  # until T3
CALIBRATION = ROOT / "data/replay-quality-2026-10-26-v1/map-calibration.json"
STRATA = (("death", "D"), ("save_escape", "S"), ("near_miss", "N"))
KEEP = ("hero", "team", "player_id", "life_state", "pos", "hp", "max_hp")
CACHE_SCHEMA = "gank-clip-inputs/2"  # 2: adds the wards (U152)
COMBAT_FIELDS = (
    "log_type",
    "attacker_name",
    "target_name",
    "inflictor_name",
    "attacker_is_illusion",
    "target_is_illusion",
    "value",
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    part.replace(path)


def names():
    """Chinese display names for heroes, abilities and items, from the tracked knowledge."""
    result = {}
    for path in (ROOT / "knowledge/hero-capabilities/heroes").glob("*.json"):
        hero = read_json(path)
        result[hero["npc_name"]] = hero["name_zh"]
        for ability in hero["abilities"]:
            result[ability["name"]] = f"{hero['name_zh']}·{ability['name_zh']}"
    items = read_json(ROOT / "knowledge/items/item-registry.json")["items"]
    for key, item in items.items():
        if item.get("name_zh"):
            result[f"item_{key}"] = item["name_zh"]
    return result


def source_key(root, mid):
    files = (
        root / "state-v3" / f"{mid}.jsonl.gz",
        root / "parsed" / f"{mid}.normalized.json.gz",
    )
    return [CACHE_SCHEMA, *([f.name, f.stat().st_size, f.stat().st_mtime_ns] for f in files)]


def read_match(root, mid):
    """What the clips of one match are built from, parsed from the two source files."""
    rows = []
    with gzip.open(root / "state-v3" / f"{mid}.jsonl.gz", "rt", encoding="utf-8") as f:
        f.readline()  # header
        for line in f:
            row = json.loads(line)
            heroes = [{k: h.get(k) for k in KEEP} for h in row["heroes"]]
            rows.append({"t": row["t"], "heroes": heroes})
    with gzip.open(root / "parsed" / f"{mid}.normalized.json.gz", "rt", encoding="utf-8") as f:
        channels = json.load(f)["context"]["channels"]
    names = {h["hero"] for row in rows for h in row["heroes"]}
    combat = []
    for entry in channels["combat_log"]:
        p = entry["payload"]
        kind = p.get("log_type")
        if kind in ("DAMAGE", "MODIFIER_ADD", "MODIFIER_REMOVE"):
            keep = p.get("attacker_name") in names or p.get("target_name") in names
        else:
            keep = kind in ("DEATH", "ABILITY", "ITEM")
        if keep:  # only the entries and fields build_clip and tower_deaths read
            combat.append(
                {"time": entry["time"], "payload": {k: p[k] for k in COMBAT_FIELDS if k in p}}
            )
    return {
        "key": source_key(root, mid),
        "rows": rows,
        "combat": combat,
        "seen": visibility_table(channels["hero_visibility_events"], rows[-1]["t"]),
        "wards": ward_spans(channels.get("wards") or ()),
    }


def match_inputs(root, mid, cache):
    """read_match, kept in `cache`/<id>.pkl until a source file changes (local, not an artifact)."""
    if cache is None:
        return read_match(root, mid)
    path = cache / f"{mid}.pkl"
    if path.exists():
        with path.open("rb") as stream:
            value = pickle.load(stream)  # written by this script, local only
        if value["key"] == source_key(root, mid):
            return value
    value = read_match(root, mid)
    cache.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        pickle.dump(value, stream, protocol=pickle.HIGHEST_PROTOCOL)
    temporary.replace(path)
    return value


def build(args):
    target = args.episodes / "review-clips.json"
    if target.exists():
        raise SystemExit(f"{target} exists; not overwriting")
    sample = read_json(args.episodes / "sample.json")
    zones = read_json(ROOT / "knowledge/awareness/map-zones-v1.json")
    wanted = {}
    blind = "items" in sample and sample.get("blind", True)  # U143: ids hide the class
    if "items" in sample:
        stratum = "acceptance" if blind else "match"
        chosen = [(i["id"], stratum, i["episode"]) for i in sample["items"]]
    else:
        chosen = [
            (f"{letter}{number}", stratum, episode)
            for stratum, letter in STRATA
            for number, episode in enumerate(sample[stratum], 1)
        ]
    for clip_id, stratum, episode in chosen:
        if is_holdout(episode["match_id"]):
            raise SystemExit(f"{episode['match_id']} is in the track B holdout (U133)")
        wanted.setdefault(episode["match_id"], []).append((clip_id, stratum, episode))
    clips = []
    cache = None if args.no_cache else args.root / "gank-clip-inputs-v1"
    for count, (mid, group) in enumerate(sorted(wanted.items()), 1):
        match = match_inputs(args.root, mid, cache)
        rows, combat, seen = match["rows"], match["combat"], match["seen"]
        for clip_id, stratum, episode in group:
            towers = standing_towers(zones, tower_deaths(combat), episode["t0"])
            clips.append(
                build_clip(
                    clip_id, stratum, episode, rows, combat, seen,
                    towers=towers, wards=match["wards"],
                )
            )  # fmt: skip
        print(f"{mid} clips {len(group)} [{count}/{len(wanted)}]", flush=True)
    order = {letter: index for index, (_, letter) in enumerate(STRATA)}
    clips.sort(key=lambda c: (order.get(c["id"][0], 0), int(c["id"][1:])))
    write_json(
        target,
        {
            "schema": "gank-review-clips/1",
            "use": "review_and_label_only",
            "omniscient": True,
            "blind": blind,
            "sample": str(args.episodes / "sample.json"),
            "sample_sha256": hashlib.sha256(
                (args.episodes / "sample.json").read_bytes()
            ).hexdigest(),
            "clips": clips,
        },
    )
    smoked = sum(bool(c["smoked_attackers"]) for c in clips)
    print(f"wrote {target}: {len(clips)} clips, {smoked} with a smoked attacker")


def sample(args):
    """Draw the acceptance sample from a frozen round, outside the matches already reviewed."""
    args.out.mkdir(parents=True, exist_ok=False)
    with (args.episodes / "episodes.jsonl").open(encoding="utf-8") as stream:
        episodes = [json.loads(line) for line in stream]
    earlier = read_json(args.exclude)
    excluded = {
        e["match_id"] for key in ("death", "save_escape", "near_miss") for e in earlier[key]
    }
    items, population = draw_acceptance(episodes, excluded, ACCEPTANCE_QUOTA, args.seed)
    write_json(
        args.out / "sample.json",
        {
            "seed": args.seed,
            "decision": "U143",
            "frozen_round": str(args.episodes),
            "excluded_matches": len(excluded),
            "quota": ACCEPTANCE_QUOTA,
            "population": population,
            "items": items,
        },
    )
    print(f"wrote {args.out / 'sample.json'}: {len(items)} episodes; population {population}")


PROMPT = ASSETS / "second-opinion-prompt.md"  # the user's definitions in words (U143)
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "category", "confidence", "reason"],
                "properties": {
                    "id": {"type": "string"},
                    "category": {"type": "string", "enum": list(ANSWERS)},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "reason": {"type": "string"},
                },
            },
        }
    },
}
RUN_ALL = """#!/usr/bin/env bash
# Blind second opinion: one codex exec per batch, read-only sandbox, empty cwd, no session.
# Usage: EMPTY_CWD=<empty dir> ./run_all.sh   (skips batches that already have a result)
set -u
root="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$root/results"
for batch in "$root"/batches/*.md; do
  name="$(basename "$batch" .md)"; out="$root/results/$name.json"
  [ -s "$out" ] && continue
  cat "$root/prompt.md" "$batch" | {codex} exec --sandbox read-only --skip-git-repo-check \
    --ephemeral -m {model} -c model_reasoning_effort={effort} -C "${{EMPTY_CWD:?}}" \
    --output-schema "$root/schema.json" -o "$out" - > "$root/results/$name.log" 2>&1
  echo "$name exit=$?"
done
"""


def packet(args):
    """Write the blind text clips, prompt, schema and runner for the second reader."""
    doc = read_json(args.episodes / "review-clips.json")
    zones = read_json(ROOT / "knowledge/awareness/map-zones-v1.json")
    radius = {}
    for fountain in zones["fountains"]:
        centre = (fountain["x"], fountain["y"])
        reach = max(
            _distance(centre, (t["x"], t["y"]))
            for t in zones["towers"]
            if t["team"] == fountain["team"] and "tower3" in t["name"]
        )
        radius[fountain["team"]] = round(reach + DEPTH_PARAMS["tower_range"])
    folder = args.episodes / "codex"
    (folder / "batches").mkdir(parents=True, exist_ok=False)
    clips = doc["clips"]
    for start in range(0, len(clips), args.batch):
        text = "\n\n".join(clip_text(c, zones, radius) for c in clips[start : start + args.batch])
        name = f"batch-{start // args.batch + 1:03d}.md"
        (folder / "batches" / name).write_text(text + "\n", encoding="utf-8")
    (folder / "prompt.md").write_text(PROMPT.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(folder / "schema.json", SCHEMA)
    runner = folder / "run_all.sh"
    runner.write_text(
        RUN_ALL.format(codex=args.codex, model=args.model, effort=args.effort), encoding="utf-8"
    )
    runner.chmod(0o755)
    write_json(
        folder / "packet.json",
        {
            "decision": "U143",
            "clips": len(clips),
            "batch_size": args.batch,
            "model": args.model,
            "reasoning_effort": args.effort,
            "blind_to": "the rule's flags, signals and label; sees observations only",
        },
    )
    print(f"wrote {folder}: {len(clips)} clips in batches of {args.batch}")


def compare(args):
    """Compare the second reader with the rule and list what the user reviews."""
    folder = args.episodes / "codex"
    items = read_json(args.episodes / "sample.json")["items"]
    opinions = {}
    for path in sorted((folder / "results").glob("batch-*.json")):
        for row in read_json(path)["results"]:
            opinions[row["id"]] = row
    missing = [i["id"] for i in items if i["id"] not in opinions]
    if missing:
        raise SystemExit(f"no second opinion for {len(missing)} clips: {missing[:10]}")
    ids, rows = review_list(
        items, {k: v["category"] for k, v in opinions.items()}, args.agreed_per_class, args.seed
    )
    for row in rows:
        row["confidence"] = opinions[row["id"]]["confidence"]
        row["reason"] = opinions[row["id"]]["reason"]
    agree = sum(r["agree"] for r in rows)
    binary = sum((r["rule"] == "gank") == (r["second"] == "gank") for r in rows)
    write_json(
        args.episodes / "codex-compare.json",
        {
            "decision": "U143",
            "clips": len(rows),
            "same_category": agree,
            "same_gank_or_not": binary,
            "agreed_per_class_for_user": args.agreed_per_class,
            "rows": rows,
        },
    )
    write_json(args.episodes / "review-list.json", {"decision": "U143", "ids": ids})
    print(
        f"{len(rows)} clips: same category {agree}, same gank-or-not {binary}; "
        f"user reviews {len(ids)} ({len(rows) - agree} disagreements + agreed samples)"
    )


def match(args):
    """Every death of the position 1 players in one match, as a non-blind review folder.

    A first look at a per-match death report (U139): each death with the class the frozen
    rule gives it, or the conditions it failed. Deaths in fights longer than the episode
    window are not inside an episode and are missing.
    """
    if is_holdout(args.match_id):
        raise SystemExit(f"{args.match_id} is in the track B holdout (U133)")
    args.out.mkdir(parents=True, exist_ok=False)
    deaths = []
    with (args.episodes / "episodes.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            episode = json.loads(line)
            if episode["match_id"] == args.match_id and episode["outcome"] == "death":
                deaths.append(episode)
    if not deaths:
        raise SystemExit(f"no position 1 death episodes for match {args.match_id}")
    deaths.sort(key=lambda e: (e["victim"], e["t0"]))
    # U155: every feature that holds, as tags, for every death (not only ganks).
    with (args.root / "gank-inputs-v2" / f"{args.match_id}.pkl").open("rb") as stream:
        cached = pickle.load(stream)  # written by detect_ganks.py, local only
    tracks = cached["tracks"]
    tps = teleports(tracks, cached["combat"])
    regions = MapKnowledge(MAP_DRAFT) if MAP_DRAFT.exists() else None
    for episode in deaths:
        place = tracks[episode["victim"]]["pos"].get(episode["t0"])
        came = [
            a
            for a in episode["attackers"]
            if place and arrived_near(tps, a, place, episode["t0"] - 30, episode["t0"] + 5, 3000)
        ]
        region = regions.region_at(*place) if regions is not None and place else None
        episode["tags"] = [list(t) for t in death_tags(episode, came, region)]
        episode["primary_reason"] = list(primary_reason(episode["tags"]))  # U156 draft
        episode["teleported_attackers"] = came
    if args.risk:
        attach_risk(deaths, args.risk, args.match_id, cached["combat"])
    items = [
        {"id": f"M{number:02d}", "stratum": "match", "episode": episode}
        for number, episode in enumerate(deaths, 1)
    ]
    write_json(
        args.out / "sample.json",
        {
            "decision": "U139 draft",
            "risk": str(args.risk) if args.risk else None,
            "blind": False,
            "frozen_round": str(args.episodes),
            "match_id": args.match_id,
            "items": items,
        },
    )
    print(f"wrote {args.out / 'sample.json'}: {len(items)} deaths of match {args.match_id}")


def attach_risk(deaths, folder, match_id, combat, before=30, after=5):
    """Add the death-risk curve (U160) of the victim around each death episode.

    The scores are out-of-fold: the model that scored this match never trained on it.
    They come from what the player could know (data.death_risk), unlike everything else on
    the page, which is omniscient.
    """
    import numpy as np

    from dota_items.data.death_risk import death_times

    report = read_json(folder / "report.json")
    oof = np.load(folder / "out-of-fold.npz")
    here = oof["match_id"] == match_id
    if not here.any():
        raise SystemExit(f"match {match_id} has no out-of-fold risk in {folder}")
    times, heroes = oof["t"][here], oof["hero"][here]
    scores, hits = oof["boosting"][here], oof["hit_recent"][here]
    for episode in deaths:
        mine = (heroes == episode["victim"]) & (times >= episode["t0"] - before)
        mine &= times <= episode["end"] + after
        died = [s for s in death_times(combat, episode["victim"])
                if episode["t0"] <= s <= episode["end"] + 2]  # fmt: skip
        episode["risk"] = {
            "death": died[0] if died else None,
            "horizon": report.get("main_horizon", 20),
            "threshold": report["alerts"]["threshold"],
            "false_alarm_rate": report["alerts"].get(
                "false_alarm_rate_on_samples_not_hit_last_3s",
                report["alerts"].get("false_alarm_rate_on_early_samples"),  # reports of 11-17
            ),
            "points": [
                [int(s), round(float(v), 4), int(h)]
                for s, v, h in sorted(zip(times[mine], scores[mine], hits[mine], strict=True))
            ],
        }


def score(args):
    """After the user's review: how often the frozen rule is right on gank-or-not."""
    rows = read_json(args.episodes / "codex-compare.json")["rows"]
    judgments = read_json(args.episodes / "judgments.json")["judgments"]
    wanted = [r["id"] for r in rows if r["user_reviews"]]
    done = [i for i in wanted if (judgments.get(i) or {}).get("verdict")]
    result = {
        "decision": "U143",
        "user_reviewed": len(done),
        "user_to_review": len(wanted),
        "complete": len(done) == len(wanted),
        "by_rule_category": acceptance_score(rows, judgments),
    }
    if result["complete"]:
        write_json(args.episodes / "acceptance-score.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=1))


def judged_items(folder):
    """[(id, episode, verdict)] of a reviewed folder, either sample layout."""
    sample = read_json(folder / "sample.json")
    judgments = read_json(folder / "judgments.json")["judgments"]
    if "items" in sample:
        items = [(i["id"], i["episode"]) for i in sample["items"]]
    else:
        items = [
            (f"{prefix}{number}", episode)
            for stratum, prefix in STRATA
            for number, episode in enumerate(sample[stratum], 1)
        ]
    return [(i, e, (judgments.get(i) or {}).get("verdict")) for i, e in items]


def rejudge(args):
    """A blind folder of episodes the user already judged, to measure self-agreement.

    How often the user agrees with an earlier self is the ceiling for any rule or model
    scored against these labels. Ids are new and shuffled; the earlier verdicts stay in
    `earlier.json`, which the page never reads.
    """
    import random

    args.out.mkdir(parents=True, exist_ok=False)
    pool = [
        (str(folder), i, episode, verdict)
        for folder in args.judged
        for i, episode, verdict in judged_items(folder)
        if verdict and verdict != "unsure"
    ]
    rng = random.Random(args.seed)
    by_verdict = {}
    for row in pool:
        by_verdict.setdefault(row[3], []).append(row)
    picked = []
    while len(picked) < min(args.count, len(pool)):  # round-robin over the verdicts
        for verdict in sorted(by_verdict):
            rows = by_verdict[verdict]
            if rows and len(picked) < args.count:
                picked.append(rows.pop(rng.randrange(len(rows))))
    rng.shuffle(picked)
    items, earlier = [], {}
    for number, (folder, old_id, episode, verdict) in enumerate(picked, 1):
        new_id = f"R{number:02d}"
        items.append({"id": new_id, "stratum": "rejudge", "episode": episode})
        earlier[new_id] = {"folder": folder, "id": old_id, "verdict": verdict}
    write_json(args.out / "sample.json", {"decision": "label reliability", "blind": True,
                                          "seed": args.seed, "items": items})  # fmt: skip
    write_json(args.out / "earlier.json", earlier)
    print(f"wrote {args.out / 'sample.json'}: {len(items)} episodes to judge again")


def reliability(args):
    """Agreement and kappa: user now vs user earlier (--rejudged), rule and Codex vs user."""
    result = {}
    if args.rejudged:
        earlier = read_json(args.rejudged / "earlier.json")
        now = read_json(args.rejudged / "judgments.json")["judgments"]
        result["user_now_vs_user_earlier"] = agreement(
            (earlier[i]["verdict"], (now.get(i) or {}).get("verdict")) for i in earlier
        )
    for folder in args.judged:
        rows = judged_items(folder)
        entry = {"rule_vs_user": agreement((rule_category(e), v) for _, e, v in rows)}
        compare_path = folder / "codex-compare.json"
        if compare_path.exists():
            second = {r["id"]: r["second"] for r in read_json(compare_path)["rows"]}
            by_id = {i: (e, v) for i, e, v in rows}
            entry["codex_vs_user"] = agreement((second.get(i), v) for i, (_, v) in by_id.items())
            entry["codex_vs_rule"] = agreement(
                (second.get(i), rule_category(e)) for i, (e, _) in by_id.items()
            )
            entry["note"] = (
                "the user saw every rule/Codex disagreement but only a few agreements, so "
                "the pairs with the user under-represent easy cases"
            )
        result[str(folder)] = entry
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if args.out:
        write_json(args.out, result)


def make_handler(folder, clips_doc, display_names, map_bytes):
    listed = folder / "review-list.json"
    if listed.exists():  # U143: the user reviews only the listed clips
        keep = set(read_json(listed)["ids"])
        clips_doc = {**clips_doc, "clips": [c for c in clips_doc["clips"] if c["id"] in keep]}
    clip_ids = {c["id"] for c in clips_doc["clips"]}
    judgments_path = folder / "judgments.json"
    assets = {
        "/": ("text/html; charset=utf-8", (ASSETS / "index.html").read_bytes()),
        "/app.js": ("text/javascript; charset=utf-8", (ASSETS / "app.js").read_bytes()),
        "/style.css": ("text/css; charset=utf-8", (ASSETS / "style.css").read_bytes()),
        "/map.jpg": ("image/jpeg", map_bytes),
    }
    clips_bytes = json.dumps(
        {
            "clips": clips_doc["clips"],
            "names": display_names,
            "blind": bool(clips_doc.get("blind")),
        },
        ensure_ascii=False,
    ).encode()

    def judgments():
        return read_json(judgments_path) if judgments_path.exists() else {"judgments": {}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def local(self):
            port = self.server.server_port
            return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def reply(self, mime, content, status=200):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self'; connect-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if not self.local():
                self.send_error(403)
            elif self.path in assets:
                self.reply(*assets[self.path])
            elif self.path == "/api/clips":
                self.reply("application/json; charset=utf-8", clips_bytes)
            elif self.path == "/api/judgments":
                content = json.dumps(judgments(), ensure_ascii=False).encode()
                self.reply("application/json; charset=utf-8", content)
            else:
                self.send_error(404)

        def do_POST(self):
            port = self.server.server_port
            origin = self.headers.get("Origin")
            if not self.local() or origin not in {
                f"http://127.0.0.1:{port}",
                f"http://localhost:{port}",
            }:
                self.send_error(403)
                return
            if self.path != "/api/judgment":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
                if not 0 < length <= 4096:
                    raise ValueError("bad length")
                judgment = validate_judgment(json.loads(self.rfile.read(length)), clip_ids)
            except (ValueError, TypeError):
                self.send_error(400)
                return
            saved = judgments()
            saved["judgments"][judgment["id"]] = {
                "verdict": judgment["verdict"],
                "note": judgment["note"],
            }
            saved["clips_sample_sha256"] = clips_doc["sample_sha256"]
            write_json(judgments_path, saved)
            self.reply("application/json", b'{"saved":true}')

    return Handler


def serve(args):
    clips_doc = read_json(args.episodes / "review-clips.json")
    map_bytes = MAP.read_bytes()
    if hashlib.sha256(map_bytes).hexdigest() != read_json(CALIBRATION)["image_sha256"]:
        raise SystemExit("Map image hash mismatch")
    handler = make_handler(args.episodes, clips_doc, names(), map_bytes)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Gank review: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)", flush=True)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--root", type=Path, required=True)
    b.add_argument("--episodes", type=Path, required=True)
    b.add_argument("--no-cache", action="store_true", help="read the source files again")
    s = sub.add_parser("serve")
    s.add_argument("--episodes", type=Path, required=True)
    s.add_argument("--port", type=int, default=8771)
    a = sub.add_parser("sample")
    a.add_argument("--episodes", type=Path, required=True, help="the frozen round")
    a.add_argument("--exclude", type=Path, required=True, help="sample.json already reviewed")
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--seed", type=int, default=20261111)
    k = sub.add_parser("packet")
    k.add_argument("--episodes", type=Path, required=True)
    k.add_argument("--batch", type=int, default=5)
    k.add_argument("--codex", default="codex")
    k.add_argument("--model", default="gpt-6.1-sol")
    k.add_argument("--effort", default="high")
    c = sub.add_parser("compare")
    c.add_argument("--episodes", type=Path, required=True)
    c.add_argument("--agreed-per-class", type=int, default=3)
    c.add_argument("--seed", type=int, default=20261111)
    m = sub.add_parser("match")
    m.add_argument("--episodes", type=Path, required=True, help="the frozen round")
    m.add_argument("--match-id", type=int, required=True)
    m.add_argument("--root", type=Path, default=ROOT / "data/demos-2026-11")
    m.add_argument("--out", type=Path, required=True)
    m.add_argument("--risk", type=Path, default=None, help="train_death_risk.py output folder")
    g = sub.add_parser("score")
    g.add_argument("--episodes", type=Path, required=True)
    r = sub.add_parser("rejudge")
    r.add_argument("--judged", type=Path, nargs="+", required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--count", type=int, default=30)
    r.add_argument("--seed", type=int, default=20261117)
    y = sub.add_parser("reliability")
    y.add_argument("--judged", type=Path, nargs="+", required=True)
    y.add_argument("--rejudged", type=Path, default=None)
    y.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    {
        "score": score,
        "rejudge": rejudge,
        "reliability": reliability,
        "match": match,
        "build": build,
        "serve": serve,
        "sample": sample,
        "packet": packet,
        "compare": compare,
    }[args.command](args)


if __name__ == "__main__":
    main()
