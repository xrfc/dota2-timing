"""Scan game text for mechanics the vocabulary may lack (U61). Run from repo root."""

import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
LOCALIZATION = "knowledge/game-files/snapshots/2026-11-02/sources/resource/localization"
PROPERTY = re.compile(r"MODIFIER_PROPERTY_([A-Z0-9_]+)")
CANDIDATES = {
    "armor_reduction": (
        r"(reduc|lower|decreas|remov|steal)\w*[^.]{0,30}\barmor\b|\barmor (reduction|"
        r"corruption)|negative armor"
    ),
    "armor_bonus": r"(bonus|grant|gain|increas)\w*[^.]{0,20}\barmor\b",
    "magic_resist_reduction": (
        r"(reduc|lower|decreas)\w*[^.]{0,30}magic resist|magic resist\w* (reduction|"
        r"penalty)|more vulnerable to magic|bonus magic damage|magic damage amplif"
    ),
    "magic_resist_bonus": r"(bonus|grant|gain|increas)\w*[^.]{0,20}magic resist",
    "incoming_damage_amp": (
        r"(take|takes|taking|receive)\w*[^.]{0,25}(more|bonus|additional|increased|"
        r"extra) damage|damage amplification|amplif\w* (all )?damage"
    ),
    "attack_damage_reduction": (
        r"(reduc|lower|decreas)\w*[^.]{0,25}attack damage|attack damage reduction"
    ),
    "attack_speed_bonus": r"(bonus|grant|gain|increas)\w*[^.]{0,20}attack speed",
    "move_speed_bonus": (
        r"(bonus|grant|gain|increas)\w*[^.]{0,25}(movement|move) speed|movespeed bonus"
    ),
    "attack_damage_bonus": r"(bonus|grant|gain|increas)\w*[^.]{0,20}(attack )?damage\b(?! to)",
    "spell_amp": r"spell amp|spell damage amp|spell amplification",
    "cast_range_or_attack_range": r"(bonus|increas)\w*[^.]{0,20}(attack range|cast range)",
    "cooldown_reduction": r"cooldown reduction|reduc\w*[^.]{0,25}cooldown",
    "cooldown_reset": r"(reset|refresh)\w*[^.]{0,25}cooldown",
    "phased": r"phas(ed|e) movement|phased",
    "flying": r"\bflying\b",
    "tree_walking": r"tree ?walk|through trees|tree destr|destroy\w*[^.]{0,15}tree",
    "cleave_splash": r"\bcleav|\bsplash",
    "spell_block": r"block\w*[^.]{0,20}(target\w* )?(spell|abilit)",
    "spell_reflect": r"reflect\w*[^.]{0,25}(spell|abilit)",
    "projectile_dodge": r"dodge|disjoint",
    "aura": r"\baura\b",
    "attack_modifier": r"attack modifier|unique attack modifier|orb effect",
    "reveal_vision": r"\breveal|grants? vision|provides? vision|fog of war",
    "reduce_vision": r"(reduc|lower)\w*[^.]{0,20}vision|\bvision reduc",
    "execute_threshold": r"instantly kill|execut|below \S+ health",
    "hp_removal": r"health removal|hp removal|removes? \S* ?health",
    "dot": r"damage over time|per second|every second",
    "stat_steal": r"steal\w*[^.]{0,20}(strength|agility|intelligence|attribute)",
    "gold_xp": r"\bgold\b|experience",
    "spell_steal": r"steal\w*[^.]{0,20}(spell|abilit)",
    "respawn_reincarnate": r"reincarnat|respawn",
    "leash_no_mobility": r"leash|prevent\w*[^.]{0,20}(blink|teleport|moving)",
    "teleport_interrupt": r"interrupt\w*|cancel\w*[^.]{0,20}channel",
    "turn_rate": r"turn rate",
    "cast_while_disabled": r"(can|may) be cast while|castable while",
    "charges": r"\bcharges?\b",
}


def load_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def main():
    registry = load_json("knowledge/hero-capabilities/hero-registry.json")
    constants = load_json("knowledge/items/sources/dotaconstants-items.json")
    status = load_json("knowledge/mechanics/retired-items-v1.json")["status"]
    stale = {
        (row["ability"], {"scepter": "scepter_loc", "shard": "shard_loc"}[row["upgrade"]])
        for row in load_json("knowledge/mechanics/stale-upgrade-text-v1.json")["entries"]
    }
    texts = {}
    names = {}
    for hero in registry["heroes"]:
        for ability in hero["abilities"]:
            upgrades = [
                value.get("en", "")
                for key, value in ability["upgrade_text"].items()
                if (ability["name"], key) not in stale
            ]
            parts = [
                ability.get("description_en") or "",
                *(ability.get("notes_en") or []),
                *upgrades,
            ]
            texts[ability["name"]] = " ".join(parts)
            names[ability["name"]] = f"{hero['name_zh']}·{ability['name_zh']}"
    item_names = {
        row["name"].removeprefix("item_"): row["name_loc"]
        for row in load_json("knowledge/items/sources/itemlist-schinese.json")["result"]["data"][
            "itemabilities"
        ]
    }
    for name, entry in constants.items():
        if status.get(name) != "purchasable" or name.startswith("recipe_"):
            continue
        abilities = entry.get("abilities") or []
        parts = [a.get("description", "") for a in abilities] + [str(entry.get("notes") or "")]
        parts += [str(a.get("key", "")).replace("_", " ") for a in entry.get("attrib") or []]
        texts[name] = " ".join(parts)
        names[name] = item_names.get(name) or entry.get("dname", name)
    hits = {}
    for label, pattern in CANDIDATES.items():
        regex = re.compile(pattern, re.I)
        found = sorted(name for name, text in texts.items() if regex.search(text))
        hits[label] = {
            "count": len(found),
            "heroes": sum(1 for name in found if name not in constants),
            "items": sum(1 for name in found if name in constants),
            "examples": [names[name] for name in found[:8]],
            "subjects": found,
        }
    properties = collections.Counter()
    for path in sorted((ROOT / LOCALIZATION).glob("abilities_english.txt")):
        for match in PROPERTY.finditer(path.read_text(encoding="utf-8", errors="replace")):
            properties[match.group(1)] += 1
    report = {
        "schema": "vocabulary-gap/1",
        "scanned_subjects": len(texts),
        "candidates": hits,
        "modifier_properties": dict(properties.most_common()),
    }
    (OUT / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    for label, row in sorted(hits.items(), key=lambda kv: -kv[1]["count"]):
        print(label, row["count"], row["heroes"], row["items"], row["examples"][:5])
    print(properties.most_common(70))


if __name__ == "__main__":
    main()
