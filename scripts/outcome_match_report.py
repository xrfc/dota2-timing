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

TRIGGERS = {
    "wave": "需近六秒（含起止秒）无线上补刀，且英雄和己方兵线前沿附近有可见敌兵",
    "jungle": "需记录到该英雄的野怪补刀，并有同秒位置和英雄状态",
    "support": "需过去七秒内（含当秒）有队友受击，决策时距最近受击队友大于 400 且不超过 6000",
}

MISSING_LABELS = {
    "missing_endpoint": "无法核实第 6 秒和第 20 秒的两个端点",
    "unverified_level_transition": "无法确认两个端点处于同一等级",
    "decreasing_same_level": "同等级经验读数下降",
    "missing_life_state": "结果窗口内缺少生命状态",
    "life_state_without_window_death": "生命状态与窗口内死亡记录不一致",
    "missing_hit_positions": "队友受击同秒的位置记录不全",
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
        return "缺测" if observed else "缺估"
    if metric in ("death", "arrival"):
        if observed:
            return "是" if value else "否"
        return f"{value:.1%}"
    return str(value) if observed else f"{value:.2f}"


def replay_coverage(diagnostics, names):
    heroes = diagnostics["observed_heroes"]
    labels = [names.get(hero, hero.removeprefix("npc_dota_hero_")) for hero in heroes]
    lines = [
        "本场按 U191 冻结模型复盘。训练比赛有平均段位门槛；本场录像可核实十人全英雄选择，"
        "天梯类型和对局平均段位未知。估计值供探索性复盘使用。",
        "",
        "录像识别的一号位：" + ("、".join(labels) or "未能识别") + "。",
    ]
    if len(heroes) < 2:
        lines.append("位置识别证据不足，未识别的一方无法取样。")
    lines.extend(
        [
            "",
            "| 场景 | 候选机会 | 可复盘 | 有双动作支持 | 可比较两种动作 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    excluded = []
    for domain, (title, _) in DOMAINS.items():
        stats = diagnostics["by_domain"][domain]
        lines.append(
            f"| {title} | {stats['opportunities']} | {stats['eligible']} |"
            f" {stats['supported']} | {stats['balanced']} |"
        )
        excluded.extend((r["t"], r["hero"], domain, r) for r in stats["excluded"])
    for domain, (title, _) in DOMAINS.items():
        stats = diagnostics["by_domain"][domain]
        if not stats["opportunities"]:
            if heroes:
                lines.append(
                    f"\n{title}：15:00 起按冻结规则取样，{TRIGGERS[domain]}。"
                    "现有输入未识别出候选，无法逐秒判定是未触发还是所需记录缺失。"
                )
            else:
                lines.append(f"\n{title}：未识别出一号位，无法为此场景取样。")
        elif not stats["eligible"]:
            lines.append(f"\n{title}：全部候选均被排除，原因见下表。")
        elif not stats["balanced"]:
            lines.append(f"\n{title}：双动作比较证据不足，各段原因见时间线。")
    if excluded:
        lines.extend(
            [
                "",
                "### 未进入复盘的候选",
                "",
                "| 时间 | 一号位 | 场景 | 动作 | 排除原因 |",
                "|---|---|---|---|---|",
            ]
        )
        for t, hero, domain, row in sorted(excluded, key=lambda x: x[:3]):
            reasons = []
            if row["unknown_action"]:
                reasons.append("前六秒无法按冻结规则识别动作")
            if row["early_death"]:
                reasons.append("前六秒死亡")
            if row["incomplete_window"]:
                reasons.append("录像未覆盖完整的二十秒窗口")
            label = names.get(hero, hero.removeprefix("npc_dota_hero_"))
            lines.append(
                f"| {t // 60}:{t % 60:02d} | {label} | {DOMAINS[domain][0]} |"
                f" {ACTIONS.get(row['action'], '未知')} | {'、'.join(reasons) or '未记录原因'} |"
            )
    return lines


def render(match, cases, names, diagnostics=None):
    counts = Counter(domain for domain, _, _ in cases)
    if diagnostics is None:
        coverage = [" · ".join(f"{label} {counts[d]} 段" for d, (label, _) in DOMAINS.items())]
    else:
        coverage = replay_coverage(diagnostics, names)
    lines = [
        f"# 对局 {match} · 一号位行动复盘",
        "",
        *coverage,
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
            lines += ["", f"双动作比较证据不足。{REASONS[reason]}。"]
        elif after is None:
            lines += ["", "双动作比较证据不足。训练分层缺少加权平衡诊断。"]
        elif not compare:
            lines += ["", f"双动作比较证据不足。加权后最大标准化均值差 {after} 超过 0.25。"]
        header = [hits if key == "hits" else LABELS[key] for key in metrics]
        lines += ["", "| 来源 | " + " | ".join(header) + " |", "|" + "---|" * (1 + len(metrics))]
        entries = [("录像实况", row["observed"], True)]
        if compare:
            entries.extend((ACTIONS[a] + "估计", v, False) for a, v in row["values"].items())
        for label, values, observed in entries:
            cells = [cell(key, values[key], observed) for key in metrics]
            lines.append(f"| {label} | " + " | ".join(cells) + " |")
        if compare and any(None in values.values() for values in row["values"].values()):
            lines.append(
                "\n缺估表示该动作在该指标上，有标签的训练片段数、比赛数或加权有效样本量未达门槛。"
            )
        for key, cause in row.get("label_exclusions", {}).items():
            lines.append(f"\n{LABELS[key]}缺测。{MISSING_LABELS[cause]}。")
    return "\n".join(lines) + "\n"


def from_demo(demo, inputs, expected_id, map_dir):
    from new_replay_inputs import active_compat, prepare, replay_header
    from new_replay_outcomes import infer

    if inputs.exists():
        provenance = read_json(inputs / "replay-provenance.json")
        with demo.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != provenance["source_sha256"]:
            raise ValueError("输入目录对应其他录像；请指定新的 --inputs 目录")
        if active_compat() != provenance.get("compat_manifest_sha256"):
            raise ValueError("缓存与当前冻结解析器不一致")
        header = replay_header(demo)
        if any(key not in provenance or provenance[key] != value for key, value in header.items()):
            raise ValueError("缓存中的比赛身份或时钟与原始录像不符")
    else:
        provenance = prepare(demo, inputs, expected_id)
    mid = provenance["match_id"]
    if expected_id is not None and mid != expected_id:
        raise ValueError("录像内比赛编号与 --match 不符")
    cases, diagnostics = infer(inputs, mid, map_dir)
    return mid, cases, diagnostics


def render_input_coverage(coverage):
    lines = [
        "",
        "## 逐秒输入覆盖",
        "",
        "下列数字统计有通道记录的游戏秒数。记录存在时，个别英雄、字段或小兵仍可能缺测。",
        "",
    ]
    labels = {"state-v3": "英雄状态（三类场景）", "extras-v1": "小兵位置（兵线）"}
    for channel, label in labels.items():
        entry = coverage[channel]
        gaps = entry["missing"]
        expected = entry["end"] - entry["start"] + 1
        absent = sum(stop - start + 1 for start, stop in gaps)
        lines.append(
            f"- {label}：从游戏第 {entry['start']} 秒到 {entry['end']} 秒，"
            f"实有 {expected - absent}/{expected} 个逐秒采样。"
        )
        if absent == expected:
            lines.append("  整个取样期缺少该通道输入；受影响场景的零计数无法说明场上没有机会。")
        elif gaps:
            intervals = "、".join(str(a) if a == b else f"{a}–{b}" for a, b in gaps[:6])
            more = f" 等 {len(gaps)} 处" if len(gaps) > 6 else ""
            lines.append(f"  缺少第 {intervals} 秒{more}；这些时段可能漏计候选或缺少结果观测。")
    return "\n".join(lines) + "\n"


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

        report = render(mid, cases, names(), diagnostics)
        if diagnostics is not None:
            report += render_input_coverage(diagnostics["capture_coverage"])
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
