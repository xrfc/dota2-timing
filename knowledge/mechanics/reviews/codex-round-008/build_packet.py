"""Find evidence for aoe_damage and build blind Codex batches (U71). Run from repo root."""

import hashlib
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
MECH = ROOT / "knowledge/mechanics"
BATCH_SIZE = 30
IN_SCOPE = {"purchasable", "other_source"}
AREA_EN = re.compile(
    r"\baoe\b|area|radius|nearby|around|all enem|enemies|enemy units|surrounding|in a line"
    r"|in its path|in a cone|cleav|splash|bounc|chain|multiple|arc\b|path",
    re.I,
)
AREA_ZH = re.compile(
    r"范围|周围|附近|所有敌|敌方单位|敌人|沿途|路径|扇形|弹射|跳跃|分裂|溅射|多个|直线"
)
DAMAGE_EN = re.compile(r"damag|\bburn|deal|strik|hit", re.I)
DAMAGE_ZH = re.compile(r"伤害|灼烧|打击|攻击")
SENTENCE = re.compile(r"[^.。!?！？\n]+[.。!?！？]?")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def quotes(english, chinese):
    found = [s.strip() for s in SENTENCE.findall(chinese or "")]
    found = [s for s in found if AREA_ZH.search(s) and DAMAGE_ZH.search(s)]
    english_found = [s.strip() for s in SENTENCE.findall(english or "")]
    found += [s for s in english_found if AREA_EN.search(s) and DAMAGE_EN.search(s)]
    return list(dict.fromkeys(found))[:6]


def main():
    spec = importlib.util.spec_from_file_location(
        "check_break", ROOT / "scripts/check_break_against_game_files.py"
    )
    breaks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(breaks)
    npc = ROOT / "knowledge/game-files/snapshots/2026-11-02/sources/scripts/npc"
    bodies = {}
    for path in [npc / "npc_abilities.txt", *sorted((npc / "heroes").glob("*.txt"))]:
        tree = breaks.parse_keyvalues(path.read_text(encoding="utf-8", errors="replace"))
        bodies.update(breaks.iter_abilities(tree))
    term = {m["id"]: m for m in load_json(MECH / "vocabulary-v8.json")["mechanisms"]}["aoe_damage"]
    registry = load_json(ROOT / "knowledge/hero-capabilities/hero-registry.json")
    constants = load_json(ROOT / "knowledge/items/sources/dotaconstants-items.json")
    status = load_json(MECH / "retired-items-v1.json")["status"]
    item_names = {
        row["name"].removeprefix("item_"): row["name_loc"]
        for row in load_json(ROOT / "knowledge/items/sources/itemlist-schinese.json")["result"][
            "data"
        ]["itemabilities"]
    }
    stale = {
        (row["ability"], {"scepter": "scepter_loc", "shard": "shard_loc"}[row["upgrade"]])
        for row in load_json(MECH / "stale-upgrade-text-v1.json")["entries"]
    }
    groups = []

    def add(name, zh_name, context, condition, found, body, context_doc):
        key = f"{name}|aoe_damage|{context}|v8"
        groups.append(
            {
                "review_id": hashlib.sha256(key.encode()).hexdigest()[:20],
                "subject": name,
                "subject_zh": zh_name,
                "mechanism": "aoe_damage",
                "mechanism_zh": term["zh"],
                "definition": term["definition"],
                "definition_note": term.get("note", ""),
                "condition": condition,
                "evidence": found,
                "game_file_fields": {
                    k: body[k]
                    for k in ("AbilityBehavior", "AbilityUnitDamageType", "AbilityUnitTargetTeam")
                    if k in body
                },
                "context": context_doc,
            }
        )

    for hero in registry["heroes"]:
        for ability in hero["abilities"]:
            name = ability["name"]
            body = bodies.get(name, {})
            damage_type = str(body.get("AbilityUnitDamageType", ""))
            context_doc = {
                k: ability[k]
                for k in ("description_en", "description_zh", "notes_en", "notes_zh")
                if ability.get(k)
            }
            upgrades = {
                k: v
                for k, v in ability["upgrade_text"].items()
                if (name, k) not in stale and any(v.values())
            }
            if upgrades:
                context_doc["upgrade_text"] = upgrades
            base = quotes(
                " ".join([ability.get("description_en") or "", *(ability.get("notes_en") or [])]),
                " ".join([ability.get("description_zh") or "", *(ability.get("notes_zh") or [])]),
            )
            has_damage = damage_type not in ("", "DAMAGE_TYPE_NONE")
            if base and (has_damage or any("伤害" in q or "damage" in q.lower() for q in base)):
                condition = {
                    "context": "base",
                    "requires_scepter": bool(ability.get("granted_by_scepter")),
                    "requires_shard": bool(ability.get("granted_by_shard")),
                }
                zh_name = f"{hero['name_zh']}·{ability['name_zh']}"
                add(name, zh_name, "base", condition, base, body, context_doc)
            for key, context, flag in (
                ("scepter_loc", "scepter_upgrade", "requires_scepter"),
                ("shard_loc", "shard_upgrade", "requires_shard"),
            ):
                text = upgrades.get(key)
                if text:
                    found = quotes(text.get("en", ""), text.get("zh", ""))
                    if found:
                        condition = {
                            "context": context,
                            "requires_scepter": flag == "requires_scepter",
                            "requires_shard": flag == "requires_shard",
                        }
                        zh_name = f"{hero['name_zh']}·{ability['name_zh']}"
                        add(name, zh_name, context, condition, found, body, context_doc)
    for name, entry in sorted(constants.items()):
        if status.get(name) not in IN_SCOPE or name.startswith("recipe_"):
            continue
        abilities = entry.get("abilities") or []
        english = (
            " ".join(f"{a.get('title', '')}: {a.get('description', '')}" for a in abilities)
            + " "
            + str(entry.get("notes") or "")
        )
        found = quotes(english, "")
        if found:
            condition = {"context": "item", "requires_scepter": False, "requires_shard": False}
            context_doc = {
                k: entry[k] for k in ("dname", "abilities", "notes", "attrib") if entry.get(k)
            }
            zh_name = item_names.get(name) or entry.get("dname", name)
            add(name, zh_name, "item", condition, found, {}, context_doc)
    (OUT / "batches").mkdir(exist_ok=True)
    for old in (OUT / "batches").glob("*.json"):
        old.unlink()
    for index in range(0, len(groups), BATCH_SIZE):
        path = OUT / "batches" / f"batch-{index // BATCH_SIZE + 1:03d}.json"
        path.write_text(
            json.dumps(groups[index : index + BATCH_SIZE], ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
    print("groups", len(groups), "batches", (len(groups) + BATCH_SIZE - 1) // BATCH_SIZE)


if __name__ == "__main__":
    main()
