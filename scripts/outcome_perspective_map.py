"""Build decision-time map frames for the heroes in a B5 local replay report."""

import argparse
import gzip
import json
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

from detect_ganks import last_hits_at
from gank_review import names
from lane_decision_review import ROOT, vision_grid
from lane_study_data import capture, file_hash
from new_replay_outcomes import FREEZE, FREEZE_SHA256, _input_info
from outcome_final import verify
from outcome_viewer import parse_report

from dota_items.data.awareness_split import is_holdout
from dota_items.data.gank_depth import standing_towers, tower_deaths
from dota_items.data.gank_events import hero_tracks, infer_positions, visibility_table
from dota_items.data.gank_review import ward_spans
from dota_items.data.lane_decisions import visible_trail
from dota_items.data.vision_sim import extra_sources, team_sources
from dota_items.storage import read_json, write_json

TEAM_NAMES = {2: "天辉", 3: "夜魇"}
OFFSETS = (-10, -5, 0)


def game_seconds(time):
    minute, second = map(int, time.split(":"))
    return minute * 60 + second


def project(tracks, seen, states, deaths, wards, hero, second, labels):
    """Project a single instant before sending any positions or inventories to a client."""
    team = tracks[hero]["team"]
    sampled = states.get(second, {})
    life = {h: info["life_state"] for h, info in sampled.items()}
    frame_wards = [
        {"type": w["type"], "pos": [w["x"], w["y"]]}
        for w in wards
        if w["team"] == team and w["start"] <= second <= w["end"]
    ]
    frame = dict(t=second, markers=[], enemies=[], wards=frame_wards, equipment=[])
    if second not in states:
        frame["unavailable"] = "该秒缺少英雄状态采样。"
        return frame
    if life.get(hero) in (1, 2):
        frame["self_status"] = "已阵亡"
    elif second not in tracks[hero]["pos"]:
        frame["self_status"] = "位置缺失"

    observed = {}
    for h, track in sorted(tracks.items()):
        ally = track["team"] == team
        if ally:
            at = second
        else:
            times = seen.get((h, team), ())
            index = bisect_right(times, second)
            at = times[index - 1] if index else None
            death_seconds = deaths.get(h, ())
            n = bisect_right(death_seconds, second)
            cutoff = death_seconds[n - 1] if n else None
            dead = life.get(h) in (1, 2)
            if dead or (cutoff is not None and at is not None and at <= cutoff):
                at = None
            trail = visible_trail(track["pos"], times, at) if at is not None else []
            frame["enemies"].append(
                dict(
                    hero=labels[h],
                    last_seen=at,
                    dead=dead if life.get(h) is not None else None,
                    trail=[point for point in trail if cutoff is None or point[0] > cutoff],
                )
            )
        observed[h] = at
        if at == second and second in track["pos"] and life.get(h) == 0:
            side = "self" if h == hero else "ally" if ally else "enemy"
            frame["markers"].append({"hero": labels[h], "side": side, "pos": track["pos"][second]})
    for h, track in sorted(tracks.items()):
        ally = track["team"] == team
        at = second if ally else observed[h]
        snapshot = states.get(at, {}).get(h, {})
        frame["equipment"].append(
            dict(hero=labels[h], ally=ally, observed=at, items=snapshot.get("items"))
        )
    return frame


def generate(report, inputs):
    mid = int(report.parent.name)
    if is_holdout(mid):
        raise ValueError("保留比赛不能用于地图试用")
    digest = file_hash(report)
    data = parse_report(report)
    meta = _input_info(inputs, mid)
    if file_hash(FREEZE) != FREEZE_SHA256:
        raise ValueError("U191 冻结清单指纹不符")
    frozen = read_json(FREEZE)
    if (
        meta.get("schema") != "new-replay-inputs/1"
        or meta.get("compat_manifest_sha256") != frozen["compat"]["manifest.json"]
        or meta.get("parser_version") != frozen["versions"]["gem-dota"]
        or meta.get("player_count") != 10
    ):
        raise ValueError("解析来源与冻结报告不符")
    verify(ROOT / "data/map-reference-2026-10-26-v1/coordinates/data", frozen["map"])
    # When the original CLI receipt is available, also bind the exact inputs used for this report.
    log = report.with_name("run.log")
    if log.is_file():
        receipt = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
        if (
            receipt["match_id"] != mid
            or receipt["data_source"] != meta["source_sha256"]
            or receipt["prepared_inputs"] != meta["inputs_sha256"]
        ):
            raise ValueError("报告运行记录与录像来源不一致")

    duration = meta["duration"]
    requested = {game_seconds(c["time"]) + d for c in data["clips"] for d in OFFSETS}
    if any(not 0 <= sec <= duration for sec in requested):
        raise ValueError("片段超出录像游戏时间")
    labels = names()
    states = {}
    deaths = defaultdict(list)
    world = {}
    tracks = {}
    for row in capture(inputs, "state-v3", mid, "gem-state-capture/3"):
        t = row["t"]
        if t in requested:
            world[t] = row["world"]
        partial = hero_tracks([row])
        for h, track in partial.items():
            if h not in tracks:
                tracks[h] = track
            else:
                tracks[h]["pos"].update(track["pos"])
        sample = states[t] = {}
        for h in row["heroes"]:
            name = h["hero"]
            if h.get("life_state") in (1, 2):
                deaths[name].append(t)
            items = h.get("items")
            if items is not None:
                items = {
                    slot: labels.get(item["name"], item["name"])
                    for slot, item in items.items()
                    if int(slot) in (*range(9), 15, 16) and item.get("name")
                }
            sample[name] = dict(life_state=h.get("life_state"), items=items)
    for name in tracks:
        labels.setdefault(name, name.removeprefix("npc_dota_hero_"))
    extras = {
        r["t"]: r
        for r in capture(inputs, "extras-v1", mid, "gem-extras-capture/1")
        if r["t"] in requested
    }
    with gzip.open(
        inputs / "parsed" / f"{mid}.normalized.json.gz", "rt", encoding="utf-8"
    ) as stream:
        parsed = json.load(stream)
    channels = parsed["context"]["channels"]
    positions = infer_positions(tracks, last_hits_at(parsed, tracks))
    carries = {labels[h]: h for h, pos in positions.items() if pos == 1}
    if set(carries) != set(data["heroes"]):
        raise ValueError("报告的一号位与录像位置识别不一致")
    seen = {
        k: sorted(v)
        for k, v in visibility_table(channels["hero_visibility_events"], duration).items()
    }
    wards = ward_spans(channels["wards"])
    fallen = tower_deaths(channels["combat_log"])
    zones = read_json(ROOT / "knowledge/awareness/map-zones-v1.json")
    del parsed, channels

    clips = []
    cache = {}
    for c in data["clips"]:
        hero = carries[c["hero"]]
        team = tracks[hero]["team"]
        frames = []
        for offset in OFFSETS:
            sec = game_seconds(c["time"]) + offset
            key = hero, sec
            if key not in cache:
                frame = project(tracks, seen, states, deaths, wards, hero, sec, labels)
                if "unavailable" not in frame and sec in world and sec in extras:
                    buildings = standing_towers(zones, fallen, sec) + zones["fountains"]
                    src = team_sources(
                        team,
                        sec,
                        tracks,
                        wards,
                        buildings,
                        world[sec].get("lane_fronts"),
                        extras[sec].get("creeps"),
                    )
                    src += extra_sources(
                        team, extras[sec].get("watchers") or (), world[sec].get("summons") or ()
                    )
                    frame["vision"] = vision_grid(src, sec)
                cache[key] = frame
            frames.append(cache[key])
        clips.append(
            dict(
                time=c["time"],
                hero=c["hero"],
                domain=c["domain"],
                team=TEAM_NAMES[team],
                frames=frames,
            )
        )
    if file_hash(report) != digest:
        raise ValueError("生成过程中报告发生变更")
    return dict(schema="b5-perspective-map/1", match=str(mid), report_sha256=digest, clips=clips)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--inputs", required=True, type=Path)
    args = parser.parse_args()
    output = args.report.with_name("perspective-map.json")
    try:
        result = generate(args.report, args.inputs)
        write_json(output, result)
    except (KeyError, ValueError, OSError) as err:
        parser.exit(1, f"{err}\n")
    print(f"{output} ({len(result['clips'])} 个片段)")


if __name__ == "__main__":
    main()
