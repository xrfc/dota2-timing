"""Publish an engineering audit of observer facts; no action scores or model inputs."""

import argparse
import json
import tempfile
from collections import Counter
from html import escape
from pathlib import Path

from dota_items.data.atomic_directory import publish_directory
from dota_items.data.awareness_split import is_holdout
from dota_items.data.mechanics_engineering_evidence import (
    SOURCE_PATHS,
    build_mechanics_engineering_evidence,
)
from dota_items.data.patch_camp_diagnostics import build_camp_diagnostics
from dota_items.data.patch_decision_context import DecisionContextIndex
from dota_items.data.patch_decision_source import EVIDENCE_PRODUCERS, open_decision_evidence
from dota_items.data.patch_decision_validation import audit_decision_views
from dota_items.data.patch_decision_view import VisionDecisionIndex
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
PRODUCER_FILES = tuple(
    sorted(
        set(EVIDENCE_PRODUCERS)
        | {
            "scripts/build_patch_decision_audit.py",
            "src/dota_items/data/patch_decision_source.py",
            "src/dota_items/data/patch_decision_view.py",
            "src/dota_items/data/patch_decision_context.py",
            "src/dota_items/data/patch_decision_validation.py",
            "src/dota_items/data/patch_camp_diagnostics.py",
            "src/dota_items/data/mechanics_engineering_evidence.py",
        }
    )
)


def render_report(contexts, validations, camps, mechanics, objective_summary):
    """A static local engineering report, with hindsight visibly separated."""
    cards = []
    for entry in contexts["cases"]:
        view = entry["context"]["known_view"]
        team = "天辉" if view["observer_team"] == 2 else "夜魇"
        moment = view["requested_game_time"]
        friendly = []
        for hero in view["friendly_heroes"]:
            state = hero.get("observed_state", {})
            position = hero.get("position")
            friendly.append(
                "<tr>"
                + "".join(
                    f"<td>{escape(str(v))}</td>"
                    for v in (
                        hero["player_id"],
                        hero.get("npc_name") or "未知",
                        state.get("health", "未知"),
                        state.get("life_state", "未知"),
                        position if position is not None else "未知/未提供",
                    )
                )
                + "</tr>"
            )
        visible_camps = [
            row for row in view["camp_observations"] if row["observed_neutral_entities_in_trigger"]
        ]
        camp_text = (
            "；".join(
                f"{escape(row['camp_id'])}：{len(row['observed_neutral_entities_in_trigger'])}个已见单位"
                for row in visible_camps
            )
            or "本采样点未记录区域内可见中立单位；不能认定营地为空。"
        )
        targets = "；".join(
            f"{'肉山' if kind == 'roshan' else '痛苦魔方'}："
            f"{'记录到活体' if row['observed_live_entities'] else '当前状态未知'}"
            for kind, row in view["objectives"].items()
        )
        cards.append(f"""<details>
<summary>比赛 {entry["match_id"]} · {team} · {moment:.3f} 秒</summary>
<p>固定工程探针 {entry["target_game_second"]} 秒之后的首个采样点；
实际 tick {view["requested_replay_tick"]}。不是玩家行动标签。</p>
<table>
<thead>
<tr>
<th>槽位</th>
<th>己方本体</th>
<th>原始生命</th>
<th>原始生命状态</th>
<th>活体位置</th>
</tr>
</thead>
<tbody>{"".join(friendly)}</tbody>
</table>
<p>生命状态是原始字段；
死亡本体位置不提供。完整友方名单尚未认证，
缺字段保持未知。</p>
<p>{camp_text}</p>
<p>{targets}</p>
<p>营地成员、完整存量、封野、阶段条件及目标刷新倒计时均未据此确定。</p>
</details>""")
    totals = validations["summary"]
    posthoc = escape(json.dumps(objective_summary, ensure_ascii=False, indent=2))
    return f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>7.42决策时证据工程核验</title>
<style>body{{font:16px/1.65 system-ui,sans-serif;
max-width:1100px;
margin:36px auto;
padding:0 20px;
color:#172338;
background:#f7f9fc}}
h1,h2{{line-height:1.3}}
details,section{{background:white;border:1px solid #d8e0eb;border-radius:8px;
padding:16px;
margin:12px 0}}
summary{{cursor:pointer;font-weight:600}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{text-align:left;
padding:8px;border-bottom:1px solid #e3e8ef}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
a{{color:#155a9c}}
.note{{border-left:4px solid #bf7b18;
padding:12px;
background:#fff8e8}}</style>
<h1>7.42 · 决策时可知证据工程核验</h1>
<p class="note">候选工程报告。没有行动优劣评分，
没有训练或最终留出评估；
正式7.42完整复盘仍未开放。</p>
<p>{len(validations["matches"])}场录像；
{totals.get("exact_packet_queries", 0)}次双队精确采样查询，

{totals.get("strict_cutoff_queries", 0)}次更早时间/tick边界检查通过。
来源与完整回执见 <a href="receipt.json">receipt.json</a>。</p>
<p>生成{len(contexts["cases"])}张双队观察卡片；
{len(contexts.get("skipped_targets", []))}个比赛/目标秒未生成卡片，
具体时间范围与原因见上下文数据中的skipped_targets。</p>
<h2>当时可知的观察</h2>
<p>只提供在查询时间和tick之前、满足可见位与身份条件的观察。看不见不等于不存在；
基础视距、全知目标事件及未来刷新未进入此处。</p>
<p>
<a href="decision-contexts.json">只含观察上下文的数据</a> ·
<a href="decision-validation.json">时序及扰动核验</a>
</p>{"".join(cards)}
<h2>事后工程核对</h2>
<section>
<p>以下使用整局信息，
只用于解释提取结果，
不能作为上方时刻的决策依据。</p>
<p>营地未关联活体：{camps["summary"]["unresolved_active_units"]}条；
已按原句柄和身份逐项分类，
不自动排除或就近填补。<a href="camp-diagnostics.json">营地诊断</a>
</p>
<details>
<summary>目标死亡与复活覆盖（事后）</summary>
<pre>{posthoc}</pre>
</details>
<p>机制工程补证{mechanics["summary"]["rows"]}行，
旧候选和用户裁定未改动。<a href="mechanics-engineering.json">具体来源与未证明项</a>
</p>
</section>
<h2>仍缺的证据</h2>
<p>当前有效视距、树位空间映射、视野来源归因、痛苦魔方复活、完整目标计时规则、动态营地阶段条件和战术区域语义仍需验证或裁定。完整坐标FOW没有被此报告认证。</p>
</html>"""


def run(spec_path, output, *, repository_root=ROOT):
    from dota_items.data.patch_asset_evidence import EvidencePins

    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists")
    initial = EvidencePins()
    spec_ref = initial.track(Path(spec_path).absolute())
    spec = initial.read(spec_ref)
    required = {
        "schema",
        "exact_patch",
        "evidence_receipt",
        "allowed_match_ids",
        "target_game_seconds",
        "max_age_seconds",
        "mechanics_admission",
    }
    if (
        set(spec) != required
        or spec["schema"] != "patch-decision-audit-spec/1"
        or spec["exact_patch"] != "7.42"
        or not isinstance(spec["allowed_match_ids"], list)
        or not spec["allowed_match_ids"]
        or any(type(mid) is not int or mid <= 0 for mid in spec["allowed_match_ids"])
        or len(set(spec["allowed_match_ids"])) != len(spec["allowed_match_ids"])
        or not isinstance(spec["target_game_seconds"], list)
        or not spec["target_game_seconds"]
        or any(type(t) is not int or t < 0 for t in spec["target_game_seconds"])
        or sorted(set(spec["target_game_seconds"])) != spec["target_game_seconds"]
        or type(spec["max_age_seconds"]) not in (int, float)
        or not 0 <= spec["max_age_seconds"] <= 60
    ):
        raise ValueError("Invalid explicit engineering audit specification")
    allowed = set(spec["allowed_match_ids"])
    source = open_decision_evidence(
        spec["evidence_receipt"],
        repository_root=repository_root,
        match_allowed=lambda mid: mid in allowed and not is_holdout(mid),
    )
    if set(source.match_ids) != allowed:
        raise ValueError("Published match set must match the explicit engineering scope")
    pins = source.pins
    pins.add(spec_ref)
    for name in PRODUCER_FILES:
        pins.track(repository_root / name)
    assets = source.assets
    cases, skipped_targets, validation_rows, runtime = [], [], [], []
    for mid in source.match_ids:
        docs = source.read_match(mid)
        capture = docs["vision"]
        ref = source.capture_refs[mid, "vision"]["capture"]
        index = VisionDecisionIndex(capture, exact_patch="7.42", source_ref=ref)
        context = DecisionContextIndex(
            index,
            assets["camp-observations.json"],
            exact_patch="7.42",
            map_source_ref=source.asset_refs["camp-observations.json"],
        )
        for second in spec["target_game_seconds"]:
            frame = next(
                (f for f in capture["frames"] if second <= f["game_time"] < second + 1), None
            )
            if frame is None:
                times = [f["game_time"] for f in capture["frames"]]
                outside = not times or second > max(times) or second + 1 <= min(times)
                skipped_targets.append(
                    {
                        "match_id": mid,
                        "target_game_second": second,
                        "reason": (
                            "outside_captured_game_time_range"
                            if outside
                            else "no_sample_in_target_second"
                        ),
                        "captured_game_time_range": [min(times), max(times)] if times else None,
                    }
                )
                continue
            for team in (2, 3):
                cases.append(
                    {
                        "match_id": mid,
                        "target_game_second": second,
                        "context": context.at(
                            game_time=frame["game_time"],
                            replay_tick=frame["tick"],
                            observer_team=team,
                            max_age_seconds=spec["max_age_seconds"],
                        ),
                    }
                )
        audit = audit_decision_views(capture, index, source_ref=ref)
        validation_rows.append(audit)
        runtime.append(docs["objectives"])
        print(json.dumps({"match_id": mid, "validation": audit["counts"]}), flush=True)
        del context, index, docs, capture
    totals = Counter()
    for row in validation_rows:
        totals.update(row["counts"])
    refs = {"evidence_receipt": spec["evidence_receipt"], **source.asset_refs}
    camps = build_camp_diagnostics(
        assets["camp-observations.json"],
        assets["camp-semantics.json"],
        runtime,
        exact_patch="7.42",
        source_refs=refs,
    )
    documents, mechanics_refs = {}, {"admission": spec["mechanics_admission"]}
    admission_path = str(
        Path(assets["camp-observations.json"]["source_refs"]["base"]["path"]).parent
        / "mechanics-admission.json"
    )
    if spec["mechanics_admission"] != {
        "path": admission_path,
        "sha256": pins.inventory.get(admission_path),
    }:
        raise ValueError("Mechanics proof must use this evidence bundle's baseline admission")
    admission = pins.read(spec["mechanics_admission"])
    for key, name in SOURCE_PATHS.items():
        ref = pins.track(repository_root / name)
        mechanics_refs[key], documents[key] = ref, pins.read(ref)
    mechanics = build_mechanics_engineering_evidence(
        admission, documents, exact_patch="7.42", source_refs=mechanics_refs
    )
    contexts = {
        "schema": "patch-decision-context-batch/1",
        "patch": "7.42",
        "cases": cases,
        "skipped_targets": skipped_targets,
        "training_allowed": False,
        "action_review_allowed": False,
    }
    validations = {
        "schema": "patch-decision-validation-batch/1",
        "matches": validation_rows,
        "summary": dict(totals),
        "training_allowed": False,
        "action_review_allowed": False,
    }
    objectives = [
        {
            "match_id": m["match_id"],
            "objectives": {
                k: {
                    "deaths": len(v["entity_observations"]["death_observations"]),
                    "cycles": [r["duration_interval"] for r in v["observed_cycles"]],
                }
                for k, v in m["objectives"].items()
            },
        }
        for m in assets["objective-cycles.json"]["matches"]
    ]
    payloads = {
        "decision-contexts.json": contexts,
        "decision-validation.json": validations,
        "camp-diagnostics.json": camps,
        "mechanics-engineering.json": mechanics,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".patch-decision-audit-", dir=output.parent
    ) as temporary:
        staging = Path(temporary) / "result"
        staging.mkdir()
        for name, payload in payloads.items():
            (staging / name).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            )
        (staging / "report.html").write_text(
            render_report(contexts, validations, camps, mechanics, objectives)
        )
        source.verify()
        receipt = {
            "schema": "patch-decision-audit-receipt/1",
            "patch": "7.42",
            "spec": spec_ref,
            "used_files": pins.inventory,
            "output_sha256": {p.name: file_hash(p) for p in sorted(staging.iterdir())},
            "training_allowed": False,
            "action_review_allowed": False,
        }
        (staging / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        publish_directory(staging, output)
    return {
        "matches": len(validation_rows),
        "cases": len(cases),
        "source_files": len(pins.inventory),
        "outputs": len(payloads) + 1,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.spec, args.output)))


if __name__ == "__main__":
    main()
