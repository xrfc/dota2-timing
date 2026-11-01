"""Print one mechanism's review groups compactly, in the index order used by decisions/.

python view.py PACKET_DIR MECHANISM [--start N] [--count N] [--width N] [--snippets N]
"""

import argparse
import json
import re
from pathlib import Path


def label(case):
    cond = case["condition"]
    parts = [
        "A杖" if cond.get("requires_scepter") else "",
        "魔晶" if cond.get("requires_shard") else "",
        cond.get("item_ability_type") or "",
    ]
    return ",".join(p for p in parts if p)


def context(evidence, width):
    value = evidence["value"]
    value = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    quote = evidence["quote"]
    quote = quote if isinstance(quote, str) else json.dumps(quote, ensure_ascii=False)
    start = max(value.find(quote[:30]), 0)
    return re.sub(r"\s+", " ", value[max(0, start - width) : start + len(quote) + width])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("mechanism")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=999)
    parser.add_argument("--width", type=int, default=60)
    parser.add_argument("--snippets", type=int, default=1)
    args = parser.parse_args()
    with open(args.packet / "cases.jsonl", encoding="utf-8") as stream:
        cases = [json.loads(line) for line in stream]
    cases = sorted(
        (case for case in cases if case["mechanism"] == args.mechanism),
        key=lambda case: case["review_id"],
    )
    for index, case in enumerate(cases[args.start : args.start + args.count], start=args.start):
        evidence = sorted(
            case["evidence"], key=lambda e: ("_zh" in e["pointer"]["path"], e["pointer"]["path"])
        )
        shown = []
        for item in evidence:
            text = context(item, args.width)
            if any(text[:60] in seen for seen in shown):
                continue
            shown.append(text)
            if len(shown) >= args.snippets:
                break
        name = (case["hero_zh"] + "·" if case["hero_zh"] else "") + case["name_zh"]
        print(f"[{index}] {name} [{label(case)}] n={len(case['evidence'])} || " + " ¦ ".join(shown))


if __name__ == "__main__":
    main()
