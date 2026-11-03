"""Classify item-source entries as obsolete, retired candidates or current (U51)."""

from __future__ import annotations

import csv
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "knowledge/game-files/snapshots"
# Not sold and outside the neutral pool, but reachable another way. Assistant judgment.
OTHER_SOURCE = {
    "aegis": "肉山掉落",
    "cheese": "肉山掉落",
    "refresher_shard": "肉山掉落",
    "aghanims_shard_roshan": "肉山掉落",
    "ultimate_scepter_roshan": "肉山掉落",
    "tango_single": "树之祭祀分享",
    "ward_dispenser": "侦察与岗哨守卫合并",
    "grisgris": "英雄先天给予",
    "eldwurms_edda": "英雄先天给予",
    "black_grimoire": "英雄先天给予",
    "tidehunter_fish": "英雄技能给予",
    "furion_gold_bag": "英雄技能给予",
}


def classify(name: str, body: dict | None, pool: set[str]) -> str:
    if body is None:
        return "not_in_game_files"
    if str(body.get("IsObsolete")) == "1":
        return "obsolete"
    if name in pool:
        return "neutral_pool"
    if str(body.get("ItemPurchasable", "1")) != "0":
        return "purchasable"
    return "other_source" if name in OTHER_SOURCE else "retired_candidate"


def main() -> None:
    spec = importlib.util.spec_from_file_location(
        "check_break", ROOT / "scripts/check_break_against_game_files.py"
    )
    breaks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(breaks)
    items_path = SNAPSHOTS / "2026-11-03-items/sources/scripts/npc/items.txt"
    tree = breaks.parse_keyvalues(items_path.read_text(encoding="utf-8", errors="replace"))
    root = tree.get("DOTAAbilities", tree)
    pool_path = SNAPSHOTS / "2026-11-03-neutral/sources/scripts/npc/neutral_items.txt"
    pool = set(
        re.findall(r'"item_([a-z0-9_]+)"', pool_path.read_text(encoding="utf-8", errors="replace"))
    )
    constants = json.loads(
        (ROOT / "knowledge/items/sources/dotaconstants-items.json").read_text(encoding="utf-8")
    )
    status = {name: classify(name, root.get(f"item_{name}"), pool) for name in sorted(constants)}
    excluded = {"obsolete", "retired_candidate"}
    review_path = ROOT / "knowledge/mechanics/extractions/v3/review.csv"
    evidence = [
        {"review_id": row["review_id"], "subject": row["subject"], "mechanism": row["mechanism"]}
        for row in csv.DictReader(review_path.open(encoding="utf-8-sig"))
        if status.get(row["subject"]) in excluded
    ]
    document = {
        "schema": "retired-items/1",
        "decision": "U51",
        "note": "用户决定退出装备不收。obsolete来自游戏文件；"
        "retired_candidate按不可购买且不在中立池推断；"
        "other_source是助手判断，未在游戏中核实。标记不删除来源记录。",
        "other_source": OTHER_SOURCE,
        "status": status,
        "v3_evidence_groups_marked": evidence,
    }
    path = ROOT / "knowledge/mechanics/retired-items-v1.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print({value: list(status.values()).count(value) for value in sorted(set(status.values()))})
    print("v3 groups marked", len(evidence), sorted({row["subject"] for row in evidence}))


if __name__ == "__main__":
    main()
