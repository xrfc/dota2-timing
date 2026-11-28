"""Build movement and actual income evidence for all wave candidates in a pinned B5 report."""

import argparse
import gzip
import json
import re
from itertools import pairwise
from math import dist
from pathlib import Path

from audit_b5_farm_gold import COMPAT, ROOT, capture, require_hash

REPORT_HASHES = {
    "9021358613": "0615f0feba7b49dab6853ab6ec2be0b92372b2a314dec7e8e8fbee5ce99fa974",
    "9031383523": "174de50cf89e4ef8d048967a3c76fdf64b28c6c1aa7d810eb618bf71b951a259",
    "9093024638": "e3c00fa8aacb33e77e07b376a3bf66ceb2905b31113f50fc8007ac8207d22e71",
}
LANE = "继续收线"
JUNGLE = "离线朝野区移动"
UNKNOWN = "去向不清"


def candidates(report):
    cases = []
    for m, s, name, old in re.findall(
        r"^\| (\d+):(\d\d) \| ([^|]+) \| 兵线 \| ([^|]+) \|", report, re.M
    ):
        cases.append((int(m) * 60 + int(s), name, old))
    for block in re.split(r"^## ", report, flags=re.M)[1:]:
        header = re.match(r"(\d+):(\d\d)　(.+) · 兵线\n", block)
        if header:
            m, s, name = header.groups()
            cases.append(
                (int(m) * 60 + int(s), name, re.search(r"观察到的动作：(.*?)。", block)[1])
            )
    count = int(re.search(r"^\| 兵线 \| (\d+) \|", report, re.M)[1])
    if len(cases) != count or len({(t, h) for t, h, _ in cases}) != count:
        raise ValueError("wave candidate census mismatch")
    return sorted(cases)


def movement(path, front, camps):
    """Only t..t+6 positions are visible here. Keep an early committed departure."""
    start = path[0]
    if not start or front is None:
        return UNKNOWN, "缺少起点或己方兵线前沿"
    lane_gap = dist(start, front)
    for second, (prev, pos) in enumerate(pairwise(path), 1):
        if not pos or dist(prev, pos) > 700:
            return UNKNOWN, "轨迹中断或跳位，尚未观察到明确去向"
        if second < 3 or dist(pos, front) - lane_gap < 350:
            continue
        for camp in camps:
            centre = camp["x"], camp["y"]
            gaps = [dist(p, centre) for p in path[: second + 1]]
            if (
                gaps[-1] <= 1200
                and gaps[0] - gaps[-1] >= 450
                and sum(b < a for a, b in pairwise(gaps)) >= 3
                and dist(pos, front) >= 850
            ):
                return JUNGLE, f"第 {second} 秒已离开兵线并持续接近 {camp['id']} 号营地"
    near = [dist(p, front) for p in path]
    if sum(gap <= 800 for gap in near) >= 4 and near[-1] <= 800 and near[-1] - lane_gap <= 150:
        return LANE, "前六秒持续留在或接近决策时的兵线前沿"
    return UNKNOWN, "走位未达到留线或朝营地移动的条件"


def income(hero, t, seconds, duration, events, boundaries):
    end = t + seconds
    if end > duration:
        return None
    opening = boundaries.get((hero, t))
    closing = boundaries.get((hero, end))
    amounts = []
    for idx, reason in enumerate((13, 14)):
        logged = sum(v for s, _, h, r, v in events if h == hero and r == reason and t <= s < end)
        counter = None
        if opening and closing and opening[idx] is not None and closing[idx] is not None:
            counter = closing[idx] - opening[idx]
            if counter < 0:
                raise ValueError("decreasing cumulative gold")
        amounts.append(
            dict(
                counter=counter,
                event=logged,
                difference=None if counter is None else counter - logged,
            )
        )
    return dict(zip(("creep", "neutral"), amounts, strict=True))


def collect(demo, inputs, report):
    mid = demo.stem
    require_hash(report, REPORT_HASHES[mid])
    pins = json.loads((ROOT / "configs/acceptance/b5-gold-probes.json").read_bytes())
    provenance = inputs / "replay-provenance.json"
    require_hash(provenance, pins[mid]["provenance_sha256"])
    receipt = json.loads(provenance.read_bytes())
    if receipt["match_id"] != int(mid) or receipt["compat_manifest_sha256"] != COMPAT:
        raise ValueError("replay provenance mismatch")
    require_hash(demo, receipt["source_sha256"])
    cases = candidates(report.read_text())
    names = {}
    for file in (ROOT / "knowledge/hero-capabilities/heroes").glob("*.json"):
        profile = json.loads(file.read_bytes())
        names[profile["name_zh"]] = profile["npc_name"]
    state = f"state-v3/{mid}.jsonl.gz"
    require_hash(inputs / state, receipt["inputs_sha256"][state])
    needed = {t + offset for t, _, _ in cases for offset in range(7)}
    frames = {}
    with gzip.open(inputs / state) as stream:
        if json.loads(next(stream))["match_id"] != int(mid):
            raise ValueError("state identity mismatch")
        for frame in map(json.loads, stream):
            if frame["t"] in needed:
                frames[frame["t"]] = frame
    camps = json.loads((ROOT / "knowledge/awareness/map-zones-v1.json").read_bytes())["camps"]
    replay, _, events, teams, boundaries, _ = capture(
        demo, [(names[name], t) for t, name, _ in cases], offsets=(0, 20, 30)
    )
    if replay != int(mid):
        raise ValueError("demo identity mismatch")
    rows = []
    for t, name, old in cases:
        hero = names[name]
        path = []
        for s in range(t, t + 7):
            sample = next((h for h in frames.get(s, {}).get("heroes", []) if h["hero"] == hero), {})
            path.append(sample.get("pos") if sample.get("life_state") == 0 else None)
        prefix = "radiant_" if teams[hero][0] == 2 else "dire_"
        fronts = frames.get(t, {}).get("world", {}).get("lane_fronts", {})
        points = [
            v["front"]
            for k, v in fronts.items()
            if k.startswith(prefix) and v and v.get("count") and v.get("front")
        ]
        front = min(points, key=lambda p: dist(path[0], p)) if points and path[0] else None
        action, why = movement(path, front, camps)
        windows = {
            str(n): income(hero, t, n, receipt["duration"], events, boundaries) for n in (30, 20)
        }
        rows.append(dict(t=t, name=name, previous=old, action=action, reason=why, windows=windows))
    return dict(schema="b5-wave-route/1", match=mid, report_sha256=REPORT_HASHES[mid], rows=rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("demo", "inputs", "report"):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    print(json.dumps(collect(args.demo, args.inputs, args.report), ensure_ascii=False, indent=2))
