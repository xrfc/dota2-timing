"""Assemble Claude's cross-review JSONL from per-mechanism decision files.

Each file work/decisions/<mechanism>.txt has one line per group: "<index> <A|R|U> <note>".
<index> is the group's position among that mechanism's cases sorted by review_id
(the order shown by view.py). Usage:

    python assemble.py PACKET_DIR DECISIONS_DIR OUTPUT_JSONL
"""

import argparse
import json
import re
from pathlib import Path

LABEL = {"A": "accept", "R": "reject", "U": "uncertain"}
ZH = {"A": "接受", "R": "排除", "U": "不确定"}
ITEM_TYPE = {"active": "装备主动效果", "passive": "装备被动效果"}


def read_jsonl(path):
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def cases_by_mechanism(packet):
    grouped = {}
    for case in read_jsonl(packet / "cases.jsonl"):
        grouped.setdefault(case["mechanism"], []).append(case)
    for cases in grouped.values():
        cases.sort(key=lambda case: case["review_id"])
    return grouped


def condition_zh(case):
    cond = case["condition"]
    if case["subject_type"] == "item":
        part = ITEM_TYPE.get(cond.get("item_ability_type"), "装备说明/附注（未标主动或被动）")
    elif cond.get("requires_scepter"):
        part = "需要阿哈利姆神杖"
    elif cond.get("requires_shard"):
        part = "需要阿哈利姆魔晶"
    else:
        part = "基础技能（不需A杖/魔晶）"
    return part + "；快照未核对补丁"


def text_of(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def snippet(evidence):
    value, quote = text_of(evidence["value"]), text_of(evidence["quote"])
    start = max(value.find(quote[:30]), 0)
    return re.sub(r"\s+", " ", value[max(0, start - 40) : start + len(quote) + 40]).strip()[:220]


def primary(case):
    return sorted(
        case["evidence"], key=lambda e: ("_zh" in e["pointer"]["path"], e["pointer"]["path"])
    )[0]


def decision_row(case, code, note):
    first = primary(case)
    name = (case["hero_zh"] + "·" if case["hero_zh"] else "") + case["name_zh"]
    pointer = first["pointer"]["file"] + first["pointer"]["path"]
    count = len(case["evidence"])
    return {
        "decision": LABEL[code],
        "interpretation_zh": f"{name}／{case['mechanism_zh']}：{note}",
        "conditions_zh": condition_zh(case),
        "reason_zh": (
            f"{ZH[code]}。{note}。依据{first['fact_id']}（{pointer}）原文：“{snippet(first)}”。"
            f"本组共{count}条证据；逐组阅读首条原文（英文优先）及其上下文，存疑组另查完整说明。"
        ),
        "evidence_fact_ids": [e["fact_id"] for e in case["evidence"]],
    }


def load_decisions(packet, decisions_dir):
    grouped = cases_by_mechanism(packet)
    decisions = {}
    for path in sorted(Path(decisions_dir).glob("*.txt")):
        cases = grouped[path.stem]
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            index, code, note = line.split(" ", 2)
            case = cases[int(index)]
            if case["review_id"] in decisions:
                raise SystemExit(f"duplicate decision: {path.stem} {index}")
            decisions[case["review_id"]] = decision_row(case, code, note)
    return decisions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    decisions = load_decisions(args.packet, args.decisions)
    with open(args.output, "w", encoding="utf-8") as out:
        for row in read_jsonl(args.packet / "claude-template.jsonl"):
            row = {**row, **decisions.get(row["review_id"], {})}
            out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"reviewed {len(decisions)} groups")


if __name__ == "__main__":
    main()
