"""Audit mechanism evidence against structured game-file fields (U48)."""

from __future__ import annotations

import argparse
import collections
import csv
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEHAVIOR_PASSIVE = 2
BEHAVIOR_UNIT_TARGET = 8
KEYWORDS = {
    "stun": r"stun(?!_penalty|ned)",
    "hex": r"hex",
    "silence": r"silence",
    "mute": r"mute",
    "disarm": r"disarm",
    "root": r"root|entangle",
    "sleep": r"sleep",
    "slow": r"slow(?!_resist)",
    "evasion": r"evasion",
    "blind": r"blind|miss_rate|miss_chance",
    "debuff_immunity": r"debuff_immun|magic_immun|spell_immun",
    "invulnerable_untargetable": r"invuln",
    "damage_block": r"shield|barrier|damage_block|block_damage",
    "status_resistance": r"status_resist",
    "slow_resistance": r"slow_resist",
    "applies_break": r"break_duration",
    "invisibility": r"invis",
    "true_sight": r"true_sight",
    "healing": r"heal(?!th|_reduc|_amp)",
    "lifesteal": r"lifesteal|life_steal",
    "heal_reduction": r"heal_reduc",
    "mana_burn": r"mana_?burn|mana_break",
    "mana_gain": r"mana_restore|mana_regen|mana_gain",
    "illusions": r"illusion",
    "summons": r"summon",
    "damage_return": r"reflect|return_damage|damage_return",
    "bash": r"bash",
    "pierce_evasion": r"accuracy|true_strike",
    "critical": r"crit",
}
# Key names that mention a keyword without granting the mechanism.
UNRELATED_KEY = re.compile(
    r"self_|castable_while|penalty|creep_lifesteal|reduction_pct|_to_self|_loss|immune_inside"
)
CONDITIONAL_KEY = re.compile(r"scepter|shard|empowered|facet")


def _load_break_module():
    spec = importlib.util.spec_from_file_location(
        "check_break", ROOT / "scripts/check_break_against_game_files.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def field_tokens(value: object) -> set[str]:
    return {part.strip() for part in str(value or "").split("|") if part.strip()}


def has_behavior(body: dict, name: str) -> bool:
    return f"DOTA_ABILITY_BEHAVIOR_{name}" in field_tokens(body.get("AbilityBehavior"))


def value_keys(body: dict) -> set[str]:
    values = body.get("AbilityValues")
    return set(values) if isinstance(values, dict) else set()


def classify_value(key: str, value: object) -> str:
    """Return base, scepter_shard, talent or zero for one AbilityValues entry."""
    if CONDITIONAL_KEY.search(key.lower()):
        return "scepter_shard"
    if isinstance(value, dict):
        base = str(value.get("value", ""))
        bonuses = {name.lower() for name in value if name != "value"}
    else:
        base, bonuses = str(value), set()
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", base)]
    if any(numbers):
        return "base"
    if any("scepter" in name or "shard" in name for name in bonuses):
        return "scepter_shard"
    if any(name.startswith("special_bonus") for name in bonuses):
        return "talent"
    return "zero"


def compare_group(decision: str, in_field: bool) -> str:
    if decision == "accept":
        return "agree_present" if in_field else "accept_but_absent"
    return "reject_but_present" if in_field else "agree_absent"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heroes-snapshot", type=Path, required=True)
    parser.add_argument("--items-snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    breaks = _load_break_module()
    out = args.out if args.out.is_absolute() else ROOT / args.out

    bodies: dict[str, dict] = {}
    hero_dir = ROOT / args.heroes_snapshot / "sources/scripts/npc"
    for path in [hero_dir / "npc_abilities.txt", *sorted((hero_dir / "heroes").glob("*.txt"))]:
        tree = breaks.parse_keyvalues(path.read_text(encoding="utf-8", errors="replace"))
        bodies.update(breaks.iter_abilities(tree))
    item_path = ROOT / args.items_snapshot / "sources/scripts/npc/items.txt"
    item_tree = breaks.parse_keyvalues(item_path.read_text(encoding="utf-8", errors="replace"))
    item_root = item_tree.get("DOTAAbilities", item_tree)
    items = {
        name.removeprefix("item_"): body
        for name, body in item_root.items()
        if name.startswith("item_") and isinstance(body, dict)
    }

    registry = json.loads(
        (ROOT / "knowledge/hero-capabilities/hero-registry.json").read_text(encoding="utf-8")
    )
    abilities = {a["name"]: (h, a) for h in registry["heroes"] for a in h["abilities"]}
    enums = json.loads((ROOT / "knowledge/mechanics/enums-v1.json").read_text(encoding="utf-8"))
    enum_fields = {
        "immunity": "SpellImmunityType",
        "dispellable": "SpellDispellableType",
        "damage": "AbilityUnitDamageType",
    }
    feed_vs_files: dict[str, collections.Counter] = {}
    feed_examples: dict[str, list] = collections.defaultdict(list)
    for field, game_key in enum_fields.items():
        values = enums["fields"][field]["values"]
        counter: collections.Counter = collections.Counter()
        for name, (_, ability) in abilities.items():
            if name not in bodies:
                counter["not_in_game_files"] += 1
                continue
            feed = values.get(str(ability["raw_mechanics"].get(field)), {}).get("valve")
            game = bodies[name].get(game_key)
            same = feed == game or (game is None and str(feed).endswith(("NONE", "_0")))
            counter["same" if same else "different"] += 1
            if not same:
                feed_examples[field].append({"subject": name, "feed": feed, "game_files": game})
        feed_vs_files[field] = counter
    for label, bit, game_name in (
        ("behavior_passive", BEHAVIOR_PASSIVE, "PASSIVE"),
        ("behavior_unit_target", BEHAVIOR_UNIT_TARGET, "UNIT_TARGET"),
    ):
        counter = collections.Counter()
        for name, (_, ability) in abilities.items():
            if name in bodies:
                feed = bool(int(ability["raw_mechanics"]["behavior"]) & bit)
                same = feed == has_behavior(bodies[name], game_name)
                counter["same" if same else "different"] += 1
                if not same:
                    feed_examples[label].append({"subject": name, "feed": feed})
        feed_vs_files[label] = counter

    decisions = breaks.effective_decisions()
    review_path = ROOT / "knowledge/mechanics/extractions/v3/review.csv"
    rows = list(csv.DictReader(review_path.open(encoding="utf-8-sig")))
    by_mechanism: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        row["effective"] = decisions.get(row["review_id"], ("missing",))[0]
        by_mechanism[row["mechanism"]].append(row)

    facts_path = ROOT / "knowledge/mechanics/extractions/v3/facts-v3.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8"))["facts"]
    field_facts = {
        (fact["subject"], fact["mechanism"])
        for fact in facts
        if str(fact.get("evidence_kind", "")).startswith("item_attr:")
    }

    def body_for(subject: str) -> dict | None:
        return bodies.get(subject) or items.get(subject)

    def is_channeled(body: dict) -> bool:
        return has_behavior(body, "CHANNELLED")

    def is_unit_target(body: dict) -> bool:
        return has_behavior(body, "UNIT_TARGET")

    strict = {}
    for mechanism, predicate in (
        ("channeled", is_channeled),
        ("unit_target_spell", is_unit_target),
    ):
        results = []
        for row in by_mechanism[mechanism]:
            body = body_for(row["subject"])
            results.append(
                {
                    "review_id": row["review_id"],
                    "subject": row["subject"],
                    "subject_zh": f"{row['hero_zh']}·{row['name_zh']}".strip("·"),
                    "condition": json.loads(row["condition"]),
                    "effective_decision": row["effective"],
                    "result": "not_in_game_files"
                    if body is None
                    else compare_group(row["effective"], predicate(body)),
                }
            )
        accepted = {r["subject"] for r in results if r["effective_decision"] == "accept"}
        missing = [
            {"subject": name, "subject_zh": f"{hero['name_zh']}·{ability['name_zh']}"}
            for name, (hero, ability) in sorted(abilities.items())
            if name in bodies and predicate(bodies[name]) and name not in accepted
        ]
        strict[mechanism] = {"groups": results, "present_without_accepted_group": missing}

    def listing(hits, names):
        return [
            {
                "subject": name,
                "subject_zh": zh_name(name),
                "is_item": name not in abilities,
                "keys": hits[name],
                "has_base_value": "base" in hits[name].values(),
            }
            for name in sorted(names)
        ]

    keyword_rows = {}
    constants_path = ROOT / "knowledge/items/sources/dotaconstants-items.json"
    constants = json.loads(constants_path.read_text(encoding="utf-8"))
    catalog = {name: body for name, body in bodies.items() if name in abilities} | {
        name: body for name, body in items.items() if name in constants
    }

    def zh_name(name: str) -> str:
        if name in abilities:
            hero, ability = abilities[name]
            return f"{hero['name_zh']}·{ability['name_zh']}"
        return constants[name].get("dname", name)

    for mechanism, pattern in KEYWORDS.items():
        regex = re.compile(pattern)
        states = {subject: "field_fact" for subject, mech in field_facts if mech == mechanism}
        for row in by_mechanism[mechanism]:
            if states.get(row["subject"]) != "accept":
                states[row["subject"]] = row["effective"]
        hits = {}
        for name, body in catalog.items():
            values = body.get("AbilityValues")
            if not isinstance(values, dict):
                continue
            found = {
                key: classify_value(key, value)
                for key, value in values.items()
                if regex.search(key.lower()) and not UNRELATED_KEY.search(key.lower())
            }
            found = {key: kind for key, kind in found.items() if kind != "zero"}
            if found:
                hits[name] = found

        keyword_rows[mechanism] = {
            "accepted_subjects": sum(1 for s in states.values() if s == "accept"),
            "keyword_subjects": len(hits),
            "keyword_and_accepted": sum(1 for n in hits if states.get(n) == "accept"),
            "keyword_and_field_fact": sum(1 for n in hits if states.get(n) == "field_fact"),
            "keyword_rejected": listing(hits, (n for n in hits if states.get(n) == "reject")),
            "keyword_no_group": listing(hits, (n for n in hits if n not in states)),
        }

    item_compare = collections.Counter()
    item_diffs = []
    for name, entry in sorted(constants.items()):
        body = items.get(name)
        if body is None:
            item_compare["not_in_items_txt"] += 1
            continue
        game_cost = body.get("ItemCost")
        if entry.get("cost") is None or game_cost is None:
            item_compare["cost_not_comparable"] += 1
        elif str(entry["cost"]) == str(game_cost):
            item_compare["cost_same"] += 1
        else:
            item_compare["cost_different"] += 1
            item_diffs.append({"item": name, "dotaconstants": entry["cost"], "game": game_cost})

    summary = {
        "feed_vs_game_files": {key: dict(value) for key, value in feed_vs_files.items()},
        "strict": {
            key: {
                **collections.Counter(r["result"] for r in value["groups"]),
                "present_without_accepted_group": len(value["present_without_accepted_group"]),
            }
            for key, value in strict.items()
        },
        "keyword": {
            key: {
                "accepted_subjects": value["accepted_subjects"],
                "keyword_subjects": value["keyword_subjects"],
                "keyword_and_accepted": value["keyword_and_accepted"],
                "keyword_and_field_fact": value["keyword_and_field_fact"],
                "keyword_rejected": len(value["keyword_rejected"]),
                "keyword_no_group": len(value["keyword_no_group"]),
                "no_group_base_value": sum(
                    1 for row in value["keyword_no_group"] if row["has_base_value"]
                ),
            }
            for key, value in keyword_rows.items()
        },
        "items_vs_dotaconstants": dict(item_compare),
    }
    out.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("summary.json", summary),
        ("strict-field-checks.json", strict),
        ("keyword-triage.json", keyword_rows),
        ("feed-differences.json", feed_examples),
        ("item-cost-differences.json", item_diffs),
    ):
        (out / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
