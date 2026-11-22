"""Render an archived development match or infer from a local replay using frozen U191 models."""

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from dota_items.data.awareness_split import is_holdout
from dota_items.storage import read_json

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/acceptance/outcome-values-dev.json"
DOMAINS = {
    "wave": ("兵线", "线上补刀"),
    "jungle": ("打野", "野怪补刀"),
    "support": ("支援", "线上与野怪补刀"),
}
ACTIONS = {
    "farm": "继续收线",
    "retreat": "后撤",
    "continue_jungle": "继续打野",
    "leave_camp": "离开营地",
    "approach": "接近队友",
    "stay": "未明显接近",
}
REASONS = {
    "extreme_propensity": "相似局面中一种动作极少出现",
    "outside_training_common_range": "局面超出两种动作共同覆盖的范围",
    "sparse_training_arm": "至少一种动作的有效样本不足",
}
LABELS = {
    "death": "死亡",
    "gold": "现金净变化（金）",
    "xp": "同等级经验变化",
    "dead_seconds": "死亡占用（秒）",
    "arrival": "队友受击时到场",
}


def match_cases(match, folder, evidence):
    if is_holdout(match):
        raise ValueError("该比赛属于封存的留出集")
    cases = []
    for domain in DOMAINS:
        meta = evidence[domain]
        path = folder / domain / "predictions.jsonl"
        with path.open("rb") as stream:
            digest = hashlib.sha256()
            for line in stream:
                digest.update(line)
                row = json.loads(line)
                if row["match"] != match:
                    continue
                after = None
                if row["overlap_reason"] is None:
                    strata = meta["training_strata_by_fold"][str(row["fold"])]
                    after = strata[str(row["stratum"])]["balance"]["after"]
                cases.append((domain, row, after))
            if digest.hexdigest() != meta["predictions_sha256"]:
                raise ValueError(f"{domain} 折外预测与 U191 登记指纹不符")
    if not cases:
        raise ValueError("三类开发集折外预测中均无该场的可评片段")
    return sorted(cases, key=lambda case: (case[1]["t"], case[1]["hero"], case[0]))


def cell(metric, value, observed):
    if value is None:
        return "缺测"
    if metric in ("death", "arrival"):
        if observed:
            return "是" if value else "否"
        return f"{value:.1%}"
    return str(value) if observed else f"{value:.2f}"


def render(match, cases, names):
    counts = Counter(domain for domain, _, _ in cases)
    lines = [
        f"# 对局 {match} · 一号位行动复盘",
        "",
        " · ".join(f"{label} {counts[domain]} 段" for domain, (label, _) in DOMAINS.items()),
        "",
        "时间为游戏内决策时刻。录像中的前 6 秒用于识别动作，第 7–20 秒用于观察结果。"
        "时间线仅覆盖能识别动作、活过前六秒且结果窗口完整的机会。",
        "",
        "两种动作的估计来自其他开发比赛中相似局面的加权结果。同一分层会共用估计；"
        "单局只能核对实际选择的动作。经验遇到升级等情况记为缺测。"
        "支援到场指目标队友再次受击的同秒，自己在其 400 范围内。",
    ]
    for domain, row, after in cases:
        title, hits = DOMAINS[domain]
        minute, second = divmod(row["t"], 60)
        hero = names.get(row["hero"], row["hero"].removeprefix("npc_dota_hero_"))
        metrics = ["hits", "gold", "xp", "death", "dead_seconds"]
        if domain == "support":
            metrics.append("arrival")
        reason = row["overlap_reason"]
        compare = reason is None and after is not None and after <= 0.25
        lines += [
            "",
            f"## {minute}:{second:02d}　{hero} · {title}",
            "",
            f"观察到的动作：{ACTIONS[row['action']]}。",
        ]
        if reason:
            lines += ["", f"仅列实际结果。{REASONS[reason]}。"]
        elif not compare:
            lines += ["", "仅列实际结果。两种动作的样本加权后仍有明显局势差异。"]
        header = [hits if key == "hits" else LABELS[key] for key in metrics]
        lines += ["", "| 来源 | " + " | ".join(header) + " |", "|" + "---|" * (1 + len(metrics))]
        entries = [("录像实况", row["observed"], True)]
        if compare:
            entries.extend((ACTIONS[a] + "估计", v, False) for a, v in row["values"].items())
        for label, values, observed in entries:
            cells = [cell(key, values[key], observed) for key in metrics]
            lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def from_demo(demo, inputs, expected_id, map_dir):
    from new_replay_inputs import prepare
    from new_replay_outcomes import infer

    if inputs.exists():
        provenance = read_json(inputs / "replay-provenance.json")
        with demo.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != provenance["source_sha256"]:
            raise ValueError("输入目录对应其他录像；请指定新的 --inputs 目录")
    else:
        provenance = prepare(demo, inputs, expected_id)
    mid = provenance["match_id"]
    if expected_id is not None and mid != expected_id:
        raise ValueError("录像内比赛编号与 --match 不符")
    cases, diagnostics = infer(inputs, mid, map_dir)
    return mid, cases, diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--match", type=int, help="development match ID or expected demo ID")
    parser.add_argument("--predictions", type=Path, help="development prediction directories")
    parser.add_argument("--demo", type=Path, help="raw local replay for new-match inference")
    parser.add_argument("--inputs", type=Path, help="private prepared inputs for --demo")
    parser.add_argument("--map-dir", type=Path, help="frozen terrain asset directory for --demo")
    parser.add_argument("--out", required=True, type=Path, help="new local Markdown file")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("choose a new output file")
    if args.demo and (not args.inputs or not args.map_dir or args.predictions):
        parser.error("--demo requires --inputs and --map-dir and cannot use --predictions")
    if not args.demo and (args.match is None or args.inputs or args.map_dir):
        parser.error("use --match for development predictions or --demo for new replays")
    try:
        diagnostics = None
        if args.demo:
            mid, cases, diagnostics = from_demo(args.demo, args.inputs, args.match, args.map_dir)
        else:
            mid = args.match
            cases = match_cases(
                mid, args.predictions or ROOT / "reports/outcome-values", read_json(EVIDENCE)
            )
        from gank_review import names

        report = render(mid, cases, names())
        if diagnostics is not None:
            heading, body = report.split("\n", 1)
            coverage = ["| 场景 | 取样机会 | 可复盘 | 可比较两种动作 |", "|---|---:|---:|---:|"]
            for domain, (label, _) in DOMAINS.items():
                counts = diagnostics["by_domain"][domain]
                coverage.append(
                    f"| {label} | {counts['opportunities']} | {counts['eligible']} |"
                    f" {counts['balanced']} |"
                )
            report = (
                heading + "\n\n本场采用 U191 冻结模型推理。训练比赛有平均段位门槛，"
                "本地录像的对局平均段位未经核实，估计值供探索性复盘使用。\n\n"
                + "\n".join(coverage)
                + "\n"
                + body
            )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=args.out.parent, mode="w", encoding="utf-8") as temp:
            temp.write(report)
            temp.flush()
            os.link(temp.name, args.out)
    except (OSError, ValueError) as err:
        parser.exit(1, f"{err}\n")
    print(f"{args.out} ({len(cases)} 个片段)")
    if diagnostics is not None:
        print(json.dumps(diagnostics, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
