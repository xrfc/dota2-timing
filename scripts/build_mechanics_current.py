"""Write knowledge/mechanics/current.json from the version list below (MK-T6, U113).

To move the knowledge base to a new version: build and commit the new versioned files,
change ENTRIES here, rerun this script, and update the docs listed in
knowledge/mechanics/README.md. current.json is the only knowledge file that is rewritten.
"""

import argparse
import hashlib
import json
from pathlib import Path

E = "knowledge/mechanics/extractions/v20"
D = "knowledge/mechanics/profiles/derived-v11"

# name -> (path, build manifest or None, what it is)
ENTRIES = {
    "enums": ("knowledge/mechanics/enums-v1.json", None, "官方枚举含义"),
    "vocabulary": ("knowledge/mechanics/vocabulary-v13.json", None, "机制词表"),
    "rules": ("knowledge/mechanics/rules-v11.json", None, "机制规则"),
    "extra_abilities": ("knowledge/mechanics/extra-abilities-v1.json", None, "注册表外技能"),
    "retired_items": ("knowledge/mechanics/retired-items-v2.json", None, "已退出装备"),
    "trait_mapping": ("knowledge/hero-traits/trait-mapping-v4.json", None, "英雄特性映射"),
    "facts": (f"{E}/facts-v20.json", f"{E}/manifest.json", "复核后事实"),
    "rules_evaluation": (f"{E}/rules-evaluation.json", f"{E}/manifest.json", "规则求值"),
    "rules_expanded": (f"{E}/rules-expanded.json", f"{E}/manifest.json", "规则展开"),
    "counter_graph": (f"{D}/counter-graph.json", f"{D}/manifest.json", "候选克制关系"),
    "hero_profiles": (f"{D}/hero-profiles.json", f"{D}/manifest.json", "英雄机制档案"),
    "item_profiles": (f"{D}/item-profiles.json", f"{D}/manifest.json", "装备机制档案"),
    "hero_traits": (f"{D}/hero-traits-v3.json", f"{D}/manifest.json", "英雄特性"),
}
PATCH = {
    "name": "7.41f",
    "verified": True,
    "checked_at": "2026-11-06",
    "evidence": "knowledge/mechanics/reviews/patch-check-001/README.md",
    "note_zh": (
        "MK-T6d（U99、U113）：官方补丁列表最新仍是7.41f；游戏脚本自固定版本起未变；"
        "Valve英雄数据与11-01相同；142件装备的引用原文和属性数值都有当前官方依据，"
        "4处标记经逐条核对为误报。只核对了文字和数据，没有在游戏里实测"
    ),
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root):
    entries = {}
    for name, (path, manifest, zh) in ENTRIES.items():
        entry = {"path": path, "sha256": sha256(root / path), "zh": zh}
        if manifest:
            entry["manifest"] = manifest
        entries[name] = entry
    return {
        "schema": "mechanics-current/1",
        "decision": "U113",
        "status_zh": "推导层是草稿；克制关系是候选，未逐对核对（见各manifest）",
        "patch": PATCH,
        "entries": entries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--check", action="store_true", help="fail if current.json is stale")
    args = parser.parse_args()
    text = json.dumps(build(args.root), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    target = args.root / "knowledge/mechanics/current.json"
    if args.check:
        if target.read_text(encoding="utf-8") != text:
            raise SystemExit("current.json is stale; rerun scripts/build_mechanics_current.py")
        return
    target.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
