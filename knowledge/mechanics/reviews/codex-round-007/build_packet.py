"""Find evidence for vocabulary v6 additions and build blind Codex batches (U63)."""

import hashlib
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
MECH = ROOT / "knowledge/mechanics"
BATCH_SIZE = 30
STATUS_IN_SCOPE = {"purchasable", "other_source"}
PATTERNS = {
    "armor_reduction": (
        r"(reduc|lower|decreas|remov|steal|strip|corrupt)\w*[^.]{0,30}\barmor\b"
        r"|\barmor (reduction|corruption|loss)|negative armor",
        r"(降低|减少|削减|削弱|偷取|窃取)[^。]{0,12}护甲|护甲(降低|削减|减少)",
    ),
    "magic_resist_reduction": (
        r"(reduc|lower|decreas)\w*[^.]{0,30}magic resist|magic resist\w* (reduc|penalty)"
        r"|vulnerable to magic|(more|bonus|additional|increased|extra) magic(al)? damage"
        r"|amplif\w*[^.]{0,15}magic",
        r"(降低|减少|削减)[^。]{0,10}魔法抗性|魔抗(降低|减)|额外魔法伤害|魔法伤害(增加|提升)"
        r"|承受的魔法伤害",
    ),
    "incoming_damage_amp": (
        r"(take|takes|taking|receive|receives|suffer)\w*[^.]{0,25}"
        r"(more|bonus|additional|increased|extra) (physical |pure )?damage"
        r"|damage amplif|amplif\w* (all |physical )?damage",
        r"(受到|承受)[^。]{0,10}(额外|更多)[^。]{0,4}伤害|伤害加深|承受[^。]{0,6}伤害[^。]{0,4}增加",
    ),
    "attack_damage_reduction": (
        r"(reduc|lower|decreas|weaken)\w*[^.]{0,25}attack damage|attack damage reduction",
        r"(降低|减少|削弱)[^。]{0,8}攻击力",
    ),
    "spell_block": (
        r"block\w*[^.]{0,25}(spell|abilit)|spell block|spell shield"
        r"|negat\w*[^.]{0,20}(spell|abilit)",
        r"(抵挡|格挡)[^。]{0,10}(技能|法术)|技能抵挡",
    ),
    "spell_reflect": (
        r"reflect\w*[^.]{0,30}(spell|abilit|target)|(spell|abilit)\w*[^.]{0,20}reflect"
        r"|re-?cast\w*[^.]{0,30}back to",
        r"(反弹|反射)[^。]{0,12}(技能|法术)|(法术|技能)反弹",
    ),
    "projectile_dodge": (r"dodg|disjoint", r"躲避"),
    "channel_interrupt": (r"interrupt|cancel\w*[^.]{0,20}channel", r"打断"),
    "mobility_lock": (
        r"leash|(prevent|disabl|stop)\w*[^.]{0,25}(blink|teleport)|cannot (blink|teleport)",
        r"束缚|牵制|无法(闪烁|传送)|阻止[^。]{0,8}(闪烁|传送|位移)|禁用闪烁",
    ),
    "cleave": (r"\bcleav|\bsplash", r"分裂|溅射"),
    "attack_modifier": (r"attack modifier|orb effect", r"攻击特效|法球"),
    "spell_amp": (r"spell amp|spell damage|spell amplification", r"技能增强|法术增强|技能伤害"),
    "aura": (r"\baura\b", r"光环"),
    "reveal": (r"\breveal", r"显形|显现"),
    "grant_vision": (
        r"(grant|provid|give|gain|share)\w*[^.]{0,20}vision|vision of|flying vision",
        r"(提供|获得|共享|给予)[^。]{0,10}视野",
    ),
    "reduce_vision": (
        r"(reduc|lower|decreas)\w*[^.]{0,20}vision",
        r"(削弱|降低|减少)[^。]{0,6}视野",
    ),
    "phased": (r"phas(ed|e) movement|\bphased\b", r"相位"),
    "flying": (r"\bflying\b|\bflies\b|levitat", r"飞行"),
    "tree_walk": (r"tree ?walk|(through|over) trees", r"穿(行|过|越)[^。]{0,4}树"),
    "tree_destroy": (
        r"(destroy|cut|chop|fell)\w*[^.]{0,20}tree|tree[^.]{0,10}destroy",
        r"(砍|摧毁|破坏)[^。]{0,8}树",
    ),
    "respawn": (r"reincarnat|respawn|revive|resurrect", r"重生|复活"),
    "execute": (
        r"instantly kill|\bexecut|\bcull|kills? (the )?(target|unit) (if|when|below)",
        r"斩杀|直接杀死|立即杀死|瞬间击杀|低于[^。]{0,14}(杀死|击杀)",
    ),
    "hp_removal": (
        r"health removal|hp removal|remov\w*[^.]{0,12}health",
        r"生命移除|移除[^。]{0,6}生命",
    ),
    "spell_steal": (r"steal\w*[^.]{0,20}(spell|abilit)", r"(窃取|偷取)[^。]{0,8}(技能|法术)"),
    "stat_steal": (
        r"steal\w*[^.]{0,25}(strength|agility|intelligence|attribute|stat)",
        r"(窃取|偷取|夺取)[^。]{0,8}(力量|敏捷|智力|属性)",
    ),
    "cooldown_reduction": (
        r"cooldown reduction|(reduc|lower|decreas|shorten)\w*[^.]{0,30}cooldown"
        r"|cooldown[^.]{0,15}(reduc|lower)",
        r"(减少|降低|缩短)[^。]{0,10}冷却|冷却(时间)?(减少|缩短|降低)",
    ),
    "cooldown_reset": (r"(reset|refresh)\w*[^.]{0,30}cooldown", r"(重置|刷新)[^。]{0,8}冷却"),
    "economy": (r"\bgold\b|\bexperience\b|\bxp\b|\bbounty\b", r"金钱|经验|赏金"),
    "charges": (r"\bcharges?\b", r"充能"),
}
FIELD_LEADS = {
    "attack_modifier": ("AbilityBehavior", "DOTA_ABILITY_BEHAVIOR_ATTACK"),
    "aura": ("AbilityBehavior", "DOTA_ABILITY_BEHAVIOR_AURA"),
    "charges": ("AbilityCharges", ""),
}
NEGATIVE_DODGE = re.compile(r"cannot|can't|can not|not be|un(dodge|avoid)|无法|不能|不可")
SENTENCE = re.compile(r"[^.。!?！？\n]+[.。!?！？]?")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sentences(text, regex):
    return [s.strip() for s in SENTENCE.findall(text or "") if regex.search(s)]


def main():
    spec = importlib.util.spec_from_file_location(
        "check_break", ROOT / "scripts/check_break_against_game_files.py"
    )
    breaks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(breaks)
    snapshot = ROOT / "knowledge/game-files/snapshots/2026-11-02/sources/scripts/npc"
    bodies = {}
    for path in [snapshot / "npc_abilities.txt", *sorted((snapshot / "heroes").glob("*.txt"))]:
        tree = breaks.parse_keyvalues(path.read_text(encoding="utf-8", errors="replace"))
        bodies.update(breaks.iter_abilities(tree))
    item_path = (
        ROOT / "knowledge/game-files/snapshots/2026-11-03-items/sources/scripts/npc/items.txt"
    )
    tree = breaks.parse_keyvalues(item_path.read_text(encoding="utf-8", errors="replace"))
    item_root = tree.get("DOTAAbilities", tree)

    vocabulary = {m["id"]: m for m in load_json(MECH / "vocabulary-v6.json")["mechanisms"]}
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

    def base_condition(ability):
        return {
            "context": "base",
            "requires_scepter": bool(ability.get("granted_by_scepter")),
            "requires_shard": bool(ability.get("granted_by_shard")),
        }

    subjects = []
    for hero in registry["heroes"]:
        for ability in hero["abilities"]:
            name = ability["name"]
            notes = (ability.get("notes_en") or [], ability.get("notes_zh") or [])
            text = {
                "base": (
                    " ".join([ability.get("description_en") or "", *notes[0]]),
                    " ".join([ability.get("description_zh") or "", *notes[1]]),
                    base_condition(ability),
                )
            }
            for key, context, flag in (
                ("scepter_loc", "scepter_upgrade", "requires_scepter"),
                ("shard_loc", "shard_upgrade", "requires_shard"),
            ):
                upgrade = ability["upgrade_text"].get(key) or {}
                if (name, key) not in stale and any(upgrade.values()):
                    condition = {"context": context, "requires_scepter": False}
                    condition["requires_shard"] = False
                    condition[flag] = True
                    text[context] = (upgrade.get("en", ""), upgrade.get("zh", ""), condition)
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
            subjects.append(
                (
                    name,
                    f"{hero['name_zh']}·{ability['name_zh']}",
                    text,
                    context_doc,
                    bodies.get(name, {}),
                )
            )
    for name, entry in sorted(constants.items()):
        if status.get(name) not in STATUS_IN_SCOPE or name.startswith("recipe_"):
            continue
        abilities = entry.get("abilities") or []
        english = " ".join(
            [f"{a.get('title', '')}: {a.get('description', '')}." for a in abilities]
            + [str(entry.get("notes") or "")]
        )
        attributes = " ".join(
            f"{a.get('key', '').replace('_', ' ')}={a.get('value')}."
            for a in entry.get("attrib") or []
        )
        condition = {"context": "item", "requires_scepter": False, "requires_shard": False}
        context_doc = {
            k: entry[k] for k in ("dname", "abilities", "notes", "attrib") if entry.get(k)
        }
        subjects.append(
            (
                name,
                item_names.get(name) or entry.get("dname", name),
                {"item": (f"{english} {attributes}", "", condition)},
                context_doc,
                item_root.get(f"item_{name}", {}),
            )
        )

    groups = []
    for mechanism, (english, chinese) in PATTERNS.items():
        en_regex, zh_regex = re.compile(english, re.I), re.compile(chinese)
        for name, zh_name, contexts, context_doc, body in subjects:
            field = FIELD_LEADS.get(mechanism)
            field_hit = False
            if field:
                value = str(body.get(field[0], ""))
                field_hit = bool(value) and field[1] in value
            for context, (en_text, zh_text, condition) in contexts.items():
                quotes = sentences(en_text, en_regex) + sentences(zh_text, zh_regex)
                if mechanism == "projectile_dodge":
                    quotes = [q for q in quotes if not NEGATIVE_DODGE.search(q)]
                lead = "text"
                if not quotes and field_hit and context in ("base", "item"):
                    quotes, lead = [f"{field[0]}={body.get(field[0])}"], "field"
                if not quotes:
                    continue
                term = vocabulary[mechanism]
                key = f"{name}|{mechanism}|{context}|v6"
                groups.append(
                    {
                        "review_id": hashlib.sha256(key.encode()).hexdigest()[:20],
                        "subject": name,
                        "subject_zh": zh_name,
                        "mechanism": mechanism,
                        "mechanism_zh": term["zh"],
                        "definition": term["definition"],
                        "condition": condition,
                        "lead": lead,
                        "evidence": list(dict.fromkeys(quotes))[:6],
                        "game_file_fields": {
                            k: body[k]
                            for k in ("AbilityBehavior", "AbilityUnitTargetTeam", "AbilityCharges")
                            if k in body
                        },
                        "context": context_doc,
                    }
                )
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
