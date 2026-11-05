"""Draw the U5 spot check from AI-only rows of facts v12. Run from repo root.

Per mechanism, one row in three is drawn by a fixed hash. Rows new in the full audit and rows
renamed by the control split are drawn more often, because no person has read them.
"""

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
SEED = "u5-spot-check-002"
NEW = {"full_audit_both", "full_audit_sequential", "full_audit_round2", "control_audit"}
TEXT_LIMIT = 700
PRIORITY = {"改名", "没再提到"}
FIRST_SHARE = 1 / 6
ITEM_TEXT = "knowledge/items/sources/itemdata-schinese-2026-11-05/items.json"
STAT_NAMES = {
    "$damage": "攻击力",
    "$mana_regen": "魔法恢复",
    "$int": "智力",
    "$armor": "护甲",
    "$health": "生命值",
    "$str": "力量",
    "$all": "全属性",
    "$hp_regen": "生命恢复",
    "$mana": "魔法值",
    "$attack_range_melee": "攻击距离（近战）",
    "$attack_range": "攻击距离",
    "$attack_pct": "基础攻击速度",
    "$attack": "攻击速度",
    "$agi": "敏捷",
    "$move_speed": "移动速度",
    "$cast_range": "施法距离",
    "$spell_resist": "魔法抗性",
    "$restoration_amp": "恢复增强",
    "$spell_lifesteal": "技能吸血",
    "$evasion": "闪避",
    "$aoe_bonus": "作用范围",
    "$lifesteal": "吸血",
    "$projectile_speed": "弹道速度",
    "$max_mana_percentage": "最大魔法值",
    "$cooldown_reduction": "冷却缩减",
    "$selected_attrib": "所选属性",
}
# Already compared with game fields in the recheck (U85), so no person needs to re-read them.
FIELD_CHECKED = {"unit_target_spell", "channeled"}


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def rank(row):
    return hashlib.sha256(f"{SEED}:{row['review_id']}".encode()).hexdigest()


def label(condition):
    if condition.get("context") == "item":
        return "装备"
    if condition.get("requires_scepter"):
        return "A杖"
    if condition.get("requires_shard"):
        return "魔晶"
    return "基础"


def _strip(text):
    text = re.sub(r"<br\s*/?>", "\n", text or "")
    text = re.sub(r"</h1>", "\n", text)
    return re.sub(r"<[^>]+>", "", text).strip()


def _number(value):
    return f"{value:g}"


def item_text(item):
    """Official Chinese text with its numbers filled in; attribute lines use Chinese names."""
    values = {}
    lines = []
    for special in item.get("special_values") or []:
        numbers = "/".join(_number(v) for v in special["values_float"])
        values[special["name"]] = numbers
        heading = _strip(special["heading_loc"])
        if not heading or not numbers:
            continue
        if "$" in heading:
            for token in sorted(STAT_NAMES, key=len, reverse=True):
                heading = heading.replace(token, STAT_NAMES[token])
        suffix = "%" if special["is_percentage"] else ""
        if heading.startswith("+"):
            lines.append(f"+{numbers}{suffix} {heading[1:]}")
        else:
            lines.append(f"{heading}{numbers}{suffix}")

    def fill(text):
        text = re.sub(r"%(\w+)%", lambda m: values.get(m[1], m[0]), text)
        return text.replace("%%", "%")

    parts = [fill(_strip(item.get("desc_loc")))]
    parts += [fill(_strip(note)) for note in item.get("notes_loc") or []]
    return "\n".join(p for p in [*parts, *lines] if p)


def text_for(obj, condition):
    upgrades = obj.get("upgrades") or {}
    parts = []
    key = "scepter" if condition == "A杖" else "shard" if condition == "魔晶" else None
    if key and key in upgrades:
        parts.append(upgrades[key].get("zh") or upgrades[key].get("en") or "")
    parts.append(obj.get("description_zh") or obj.get("description_en") or "")
    notes = obj.get("notes_zh") or obj.get("notes_en") or []
    parts += notes if isinstance(notes, list) else [notes]
    parts += obj.get("attributes") or []
    return "\n".join(p for p in parts if p)[:TEXT_LIMIT]


def first_batch(sample):
    """Priority rows, plus about one in six of the rest, with every mechanism represented."""
    groups = defaultdict(list)
    for row in sample:
        if row["why"] in PRIORITY:
            row["b"] = 1
        else:
            row["b"] = 2
            groups[(row["m"], row["why"])].append(row)
    for rows in groups.values():
        for row in rows[: round(len(rows) * FIRST_SHARE)]:
            row["b"] = 1
    for mechanism in {row["m"] for row in sample}:
        rows = [row for row in sample if row["m"] == mechanism]
        if not any(row["b"] == 1 for row in rows):
            rows[0]["b"] = 1


def not_refound():
    data = load("knowledge/mechanics/reviews/full-audit-001/comparison.json")
    return {(r["subject"], r["mechanism"]) for r in data["two_ai_accept_not_found_by_codex"]}


def main():
    doc = load("knowledge/mechanics/extractions/v12/facts-v12.json")
    vocabulary = load(doc["vocabulary"])["mechanisms"]
    terms = {m["id"]: m for m in vocabulary}
    objects = {
        o["subject"]: o for o in load("knowledge/mechanics/reviews/full-audit-001/objects.json")
    }
    missed = not_refound()
    items_zh = load(ITEM_TEXT)
    by_term = defaultdict(list)
    for row in doc["rows"]:
        if row["basis"] == "two_ai" and row["mechanism"] not in FIELD_CHECKED:
            by_term[row["mechanism"]].append(row)
    picked = []
    for rows in by_term.values():
        rows.sort(key=rank)
        must = [
            r for r in rows if r.get("renamed_from") or (r["subject"], r["mechanism"]) in missed
        ]
        new = [r for r in rows if r["origin"] in NEW and r not in must]
        old = [r for r in rows if r not in must and r not in new]
        picked += must + new[: math.ceil(len(new) / 2)]
        room = max(math.ceil(len(rows) / 3) - len(must) - math.ceil(len(new) / 2), 0)
        picked += old[:room]
    sample = []
    for row in sorted(picked, key=rank):
        if row["subject"] not in objects:
            continue
        condition = label(row["condition"])
        reason = (
            "改名"
            if row.get("renamed_from")
            else "没再提到"
            if (row["subject"], row["mechanism"]) in missed
            else "新增"
            if row["origin"] in NEW
            else "旧记录"
        )
        term = terms[row["mechanism"]]
        sample.append(
            {
                "id": hashlib.sha256(row["review_id"].encode()).hexdigest()[:20],
                "review_id": row["review_id"],
                "subject": row["subject"],
                "n": (items_zh.get(row["subject"]) or {}).get("name_loc")
                or row["subject_zh"]
                or objects[row["subject"]]["name_zh"],
                "m": row["mechanism"],
                "mz": term["zh"],
                "c": condition,
                "d": "有" if row["decision"] == "accept" else "没有",
                "why": reason,
                "t": item_text(items_zh[row["subject"]])[:TEXT_LIMIT]
                if row["subject"] in items_zh
                else text_for(objects[row["subject"]], condition),
            }
        )
    first_batch(sample)
    defs = {m: terms[m]["definition"] for m in {s["m"] for s in sample}}
    payload = {"defs": defs, "rows": sample}
    (OUT / "sample.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=0) + "\n", encoding="utf-8"
    )
    print(len(sample), Counter(s["why"] for s in sample), Counter(s["d"] for s in sample))
    print("first batch", Counter(s["why"] for s in sample if s["b"] == 1))
    print("frame", sum(len(v) for v in by_term.values()), "terms", len(by_term))


if __name__ == "__main__":
    main()
