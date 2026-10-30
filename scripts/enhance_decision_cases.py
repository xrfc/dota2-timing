"""Read-only, post-feedback enhancement of two sealed cases; never a new blind review."""

import argparse
import hashlib
import inspect
import json
from copy import deepcopy
from pathlib import Path

from dota_items.data.decision_context import source_context
from dota_items.data.decision_evidence import DecisionEvidenceStore
from dota_items.data.replay_semantics import make_clock
from dota_items.data.replay_viewer import ReplayStore
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def enhance(output, repo=ROOT):
    if output.exists():
        raise ValueError("Output exists; use a new directory")
    old_root = repo / "reports/decision-review-2026-10-27-v2"
    old = parse_source_json(read_source_bytes(old_root / "cases.json"))
    if [c["case"]["id"] for c in old["cards"][:2]] != ["map-attention", "conservative"]:
        raise ValueError("Unexpected original case selection")
    verified = parse_source_json(read_source_bytes(old_root / "verification.json"))
    protected = {}
    for name, expected in verified["outputs"].items():
        path = old_root / name
        if Path(name).name != name or file_hash(path) != expected:
            raise ValueError("Sealed case output mismatch")
        protected[path] = expected
    protected[old_root / "verification.json"] = file_hash(old_root / "verification.json")
    store = DecisionEvidenceStore(ReplayStore(repo / "data/replay-quality-2026-10-26-v1"), repo)
    cards = []
    for card in old["cards"][:2]:
        revised = deepcopy(card)
        case = revised["case"]
        number = 1 if case["id"] == "map-attention" else 2
        feedback_path = (
            repo / f"reports/decision-case-user-feedback-2026-10-27-v1/case-{number}.json"
        )
        feedback_bytes = read_source_bytes(feedback_path)
        feedback = parse_source_json(feedback_bytes)
        if feedback["case_id"] != case["id"]:
            raise ValueError("Feedback identity mismatch")
        protected[feedback_path] = hashlib.sha256(feedback_bytes).hexdigest()
        current = store.build(case["match_id"], case["view"], case["tick"], case["slot"])
        if current["decision_input"] != card["evidence"]["decision_input"]:
            raise ValueError("Original decision input changed")
        provenance = current["provenance"]
        raw_path = Path(provenance["raw"])
        if not raw_path.is_absolute():
            raw_path = repo / raw_path
        raw_bytes = read_source_bytes(raw_path, max_bytes=512 * 1024**2)
        if hashlib.sha256(raw_bytes).hexdigest() != provenance["raw_sha256"]:
            raise ValueError("Raw hash mismatch")
        protected[raw_path] = provenance["raw_sha256"]
        aligned = repo / "data/replay-quality-2026-10-26-v1/aligned" / str(case["match_id"])
        protected[aligned / "manifest.json"] = provenance["manifest_sha256"]
        protected[aligned / "radiant.jsonl"] = provenance["view_sha256"]
        raw = parse_source_json(raw_bytes)
        clock = make_clock(raw)
        clock_source = Path(inspect.getfile(type(clock)))
        pinned = repo / "data/replay-pilot-2026-10-22/compat-v1/gem/state/game_clock.py"
        if file_hash(clock_source) != file_hash(pinned):
            raise ValueError("Clock implementation differs from frozen compatibility source")
        protected[clock_source] = file_hash(clock_source)
        protected[pinned] = file_hash(pinned)
        context = source_context(raw, current["decision_input"], clock.game_seconds_at)
        timeline = store.replay.timeline(case["match_id"], case["view"])["frames"]
        recent = []
        for seconds_ago in (30, 20, 10, 5):
            past = [
                f
                for f in timeline
                if f["tick"] < case["tick"]
                and f["time"] <= current["decision_input"]["time"] - seconds_ago
            ]
            if past:
                f = max(past, key=lambda r: r["tick"])
                recent.append(store.replay.frame(case["match_id"], case["view"], f["tick"], 0))
        revised["past_frames"] = recent
        revised["enhancement"] = {
            "user_feedback": feedback["user_feedback_verbatim"],
            "source_context": context,
            "review_stage": "post_feedback_not_blind_not_training_label",
            "alternatives": [
                {
                    "name": "参团／支援",
                    "conditions": (
                        "确认战斗目标、TP就绪与落点、落地后路程、关键技能和到场价值；"
                        "未知则不发立即TP指令。"
                    ),
                    "opportunity_cost": "放弃当前区域的兵线／野区收益，可能到场过晚。",
                    "stop": "战斗已结束、落点不安全、到场无价值或关键状态不足时取消。",
                },
                {
                    "name": "继续发育",
                    "conditions": (
                        "结合远处交战与当地可知威胁，选择有退路的兵线／野区活动；"
                        "先确认资源实际存在。"
                    ),
                    "opportunity_cost": "无法贡献远处团战，可能放弃可争取目标。",
                    "stop": "敌方消失向本区转移、视野不足且退路受限或出现新威胁时换区。",
                },
                {
                    "name": "换区／避险",
                    "conditions": (
                        "当局部威胁和信息缺口足以影响安全时考虑；不能仅凭单敌距离下结论。"
                    ),
                    "opportunity_cost": "可能放弃本来安全的资源和发育时间。",
                    "stop": "新的可靠信息表明当地可继续活动时重新比较，不机械一直撤退。",
                },
            ],
            "unresolved": [
                "TP冷却／充能和精确到场时间",
                "兵线及营地当前存量",
                "双方关键技能就绪与经认证的血蓝",
                "完整地形及动态眼位覆盖",
            ],
        }
        case["title"] = "18:00：参团还是继续发育——结合全局战况，而不是只看近身距离"
        case["action_axis"] = "参团／发育／换区的条件比较（复审候选）"
        case["status"] = "依据用户反馈修订；不是盲评、模型输出或训练真值"
        case["attention"] = "观察远处交战、敌方转移与本地资源，同时检查支援到场价值。"
        case["action"] = (
            "不因失踪或单个敌人贴近就自动撤退；先比较参团与继续发育，遇到明确局部威胁再换区。TP条件未核实，不直接要求传送。"
        )
        case["reason"] = (
            "用户指出上方团战、当地最多一名大圣；这是需结合阵营历史证据核对的游戏解释。主槽狂战斧、夜叉为持有观测，并非主动就绪认证。"
            if number == 1
            else (
                "用户指出18分钟一号位仍需发育，敌方多人在中路，此时潮汐不构成其判断中的威胁。"
                "原建议仅由距离与队友远近推出保守，依据不足。"
            )
        )
        case["stop_condition"] = (
            "支援价值消失、局部威胁变化、视野或退路条件不成立时重新比较行动，不固定追击／撤退。"
        )
        case["counterevidence"] = (
            "用户意见不是隐藏位置真值。原生距离不等于路径；近期战斗记录不证明当前仍在团战，也不证明双方技能就绪。"
        )
        revised["evidence"] = current
        cards.append(revised)
    if any(file_hash(p) != h for p, h in protected.items()):
        raise ValueError("Protected input changed")
    output.mkdir(parents=True)
    revision = {
        "schema": "post-feedback-case-revision/1",
        "training_allowed": False,
        "blind_review": False,
        "original_advice_sha256": old["advice_sha256"],
        "cases": [c["case"] for c in cards],
    }
    write(output / "revision.json", revision)
    write(
        output / "field-availability.json",
        {
            "scope": "Only two 18:00 case sources; not all 13 matches or training admission.",
            "fields": [
                {
                    "field": "observer_positions_and_last_seen",
                    "status": "usable_limited",
                    "next": (
                        "Use native ticks and age; no hidden coordinate "
                        "backfill or path interpolation."
                    ),
                },
                {
                    "field": "target_inventory_slots",
                    "status": "usable_limited",
                    "next": "Possession/slot only; distinguish backpack, empty and unresolved.",
                },
                {
                    "field": "combat_log_side_flags",
                    "status": "present_unverified",
                    "next": (
                        "Audit event meanings/visibility; past-only source "
                        "appendix, not current fight truth."
                    ),
                },
                {
                    "field": "own_health_mana_level",
                    "status": "present_unverified",
                    "next": (
                        "Retain raw values separately; verify scalar "
                        "decoding/units and identity before admission."
                    ),
                },
                {
                    "field": "ability_levels",
                    "status": "present_unverified",
                    "next": (
                        "Levels exist; missing cooldown, charges and cast "
                        "conditions cannot be inferred."
                    ),
                },
                {
                    "field": "active_item_tp_readiness",
                    "status": "absent_export",
                    "next": (
                        "Check minimum extractor change separately; no "
                        "cooldown/charges currently retained."
                    ),
                },
                {
                    "field": "friendly_ward_smoke_events",
                    "status": "present_unverified",
                    "next": (
                        "Past placement/application only; no future endpoints "
                        "or effective vision inference."
                    ),
                },
                {
                    "field": "enemy_hidden_inventory_wards_smoke",
                    "status": "observer_unknown",
                    "next": "Keep unknown; do not substitute omniscient raw truth.",
                },
                {
                    "field": "current_lane_camp_stock",
                    "status": "absent_export",
                    "next": "Past creep damage is not a snapshot of remaining resources.",
                },
                {
                    "field": "tp_landing_legality_path_arrival",
                    "status": "unverified_or_absent",
                    "next": (
                        "Need legal live destinations, channel state and "
                        "traversable route; no straight-line ETA."
                    ),
                },
                {
                    "field": "finished_teamfight_summary",
                    "status": "excluded_future_risk",
                    "next": (
                        "Do not use whole-fight outcomes/centroids/participants as current inputs."
                    ),
                },
            ],
            "case_source_counts": {
                c["case"]["id"]: c["enhancement"]["source_context"]["raw_channel_counts"]
                for c in cards
            },
            "training_allowed": False,
        },
    )
    write(
        output / "cases.json",
        {
            "schema": "manual-decision-review/1",
            "names": old["names"],
            "review_stage": "用户反馈后的增强复审，非盲评",
            "advice_sha256": file_hash(output / "revision.json"),
            "original_advice_sha256": old["advice_sha256"],
            "cards": cards,
        },
    )
    for card in cards:
        name = card["case"]["id"] + "-after.json"
        # Copy historical future context, never regenerate or relabel it.
        with (output / name).open("xb") as stream:
            stream.write(read_source_bytes(old_root / name))
    write(
        output / "verification.json",
        {
            "cases": len(cards),
            "training_allowed": False,
            "blind_review": False,
            "protected_unchanged": True,
            "source_files": {str(p): h for p, h in protected.items()},
            "outputs": {p.name: file_hash(p) for p in output.glob("*.json")},
            "implementation": {
                str(p.relative_to(repo)): file_hash(p)
                for p in [
                    repo / "scripts/enhance_decision_cases.py",
                    repo / "src/dota_items/data/decision_context.py",
                    repo / "src/dota_items/data/decision_evidence.py",
                    repo / "src/dota_items/data/source_io.py",
                    repo / "src/dota_items/data/replay_viewer.py",
                    repo / "src/dota_items/data/replay_status.py",
                    repo / "src/dota_items/data/replay_semantics.py",
                    repo / "scripts/decision_review.py",
                    repo / "scripts/decision_review_assets/index.html",
                    repo / "scripts/decision_review_assets/app.js",
                    repo / "scripts/decision_review_assets/style.css",
                ]
            },
        },
    )
    return {"cases": len(cards), "protected_files": len(protected), "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(enhance(args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
