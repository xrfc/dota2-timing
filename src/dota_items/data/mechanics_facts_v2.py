"""MK-T3 evidence inventory, version 2. No I/O, training or strategy inference.

v1 (mechanics_facts) stays frozen and replayable. v2 differs only in:
- vocabulary v3 (U33/U35 definitions);
- lexical rules v2 (mechanics_rules_v2), matched with the subject hero's names removed;
- more item attribute keys as field observations (evasion, damage block, heal
  reduction, lifesteal, true sight), keyed by vocabulary v3 evidence kinds;
- passives the user said cannot be broken (U33/U35) are not emitted as
  break candidates.
"""

from dota_items.data.mechanics import load_enums, load_vocabulary, unconfirmed
from dota_items.data.mechanics_facts import (
    HEROES,
    ITEM_TEXT,
    ITEMS,
    USER_EVIDENCE,
    canonical,
    digest,
    eligible,
    escape,
    pointer,
    text_leaves,
)
from dota_items.data.mechanics_rules_v2 import text_hits

ENUMS = "knowledge/mechanics/enums-v1.json"
VOCAB = "knowledge/mechanics/vocabulary-v3.json"
INPUTS = (HEROES, ITEMS, ITEM_TEXT, ENUMS, VOCAB, USER_EVIDENCE)
VERSION = "mechanics-extractor/2"
# U33: Medusa's Mana Shield cannot be broken; U35: neither can Grow or Divided We Stand.
NOT_BREAKABLE = ("medusa_mana_shield", "tiny_grow", "meepo_divided_we_stand")
ITEM_ATTRIBUTES = {
    "status_resistance": "status_resistance",
    "slow_resistance": "slow_resistance",
    "bonus_evasion": "evasion",
    "evasion": "evasion",
    "block_damage_melee": "damage_block",
    "damage_block_melee": "damage_block",
    "barrier_block": "damage_block",
    "heal_reduction": "heal_reduction",
    "lifesteal_percent": "lifesteal",
    "spell_lifesteal": "lifesteal",
    "true_sight_range": "true_sight",
}


def build_facts(sources):
    """Extract all subjects with v2 rules; prose and passive flags still need review."""
    enums = load_enums(sources[ENUMS], sources[HEROES]["heroes"])
    terms = load_vocabulary(sources[VOCAB], enums)
    if unconfirmed(enums):
        raise ValueError("Enums must be confirmed before extraction")
    facts, subjects, scanned = [], [], []

    def add(
        subject, mechanism, kind, file, path, value, condition, rule, review="auto", quote=None
    ):
        if kind not in terms[mechanism]["evidence"]:
            raise ValueError(f"Evidence not allowed for {mechanism}: {kind}")
        record = {
            "subject_type": subject["subject_type"],
            "subject": subject["subject"],
            "mechanism": mechanism,
            "evidence_kind": kind,
            "pointer": {"file": file, "path": path},
            "value": value,
            "quote": canonical(value) if quote is None else quote,
            "quote_encoding": "json" if quote is None else "text",
            "condition": condition,
            "extractor": rule,
            "review": review,
            "assertion": "candidate" if review == "needs_review" else "field_observation",
            "publisher": "OpenDota dotaconstants (community)"
            if file == ITEM_TEXT
            else "User decision U28"
            if file == USER_EVIDENCE
            else "Valve via hero registry",
        }
        record["fact_id"] = "mf2-" + digest(record)[:20]
        facts.append(record)

    def prose(subject, file, path, value, condition, names):
        for leaf, text in text_leaves(value, path):
            scanned.append(
                {"subject": subject["subject"], "file": file, "path": leaf, "condition": condition}
            )
            for mid, quote in text_hits(text, names):
                if "official_text" in terms[mid]["evidence"]:
                    add(
                        subject,
                        mid,
                        "official_text",
                        file,
                        leaf,
                        text,
                        condition,
                        "prose2/" + mid,
                        "needs_review",
                        quote,
                    )

    for hi, hero in enumerate(sources[HEROES]["heroes"]):
        names = (hero["name_zh"], hero["name_en"])
        for ai, ability in enumerate(hero["abilities"]):
            base = f"/heroes/{hi}/abilities/{ai}"
            condition = {
                "requires_scepter": bool(ability["granted_by_scepter"]),
                "requires_shard": bool(ability["granted_by_shard"]),
                "context": "base",
            }
            subject = {
                "subject_type": "hero_ability",
                "subject": ability["name"],
                "name_zh": ability["name_zh"],
                "hero": hero["npc_name"],
                "hero_name_zh": hero["name_zh"],
                "pointer": base,
                "condition": condition,
            }
            subjects.append(subject)
            if ability["name"] in ("antimage_mana_break", "tidehunter_kraken_shell"):
                quote = "可以破坏的技能有特点的比如敌法师的法力损毁，潮汐猎人的外壳这类"
                add(
                    subject,
                    "break_sensitive",
                    "manual",
                    USER_EVIDENCE,
                    "/text",
                    sources[USER_EVIDENCE]["text"],
                    condition,
                    "user-key-passive-example/U28",
                    "needs_review",
                    quote,
                )
            raw = ability["raw_mechanics"]
            observations = [("effect_dispellability", "dispellable")]
            damage = {1: "physical_damage", 2: "magical_damage", 4: "pure_damage"}
            if int(raw["damage"]) in damage:
                observations.append((damage[int(raw["damage"])], "damage"))
            if int(raw["immunity"]) == 3:
                observations.append(("pierces_debuff_immunity", "immunity"))
            for mid, field in observations:
                add(
                    subject,
                    mid,
                    "enum:" + field,
                    HEROES,
                    base + "/raw_mechanics/" + field,
                    raw[field],
                    condition,
                    "enum/" + field,
                )
            add(
                subject,
                "mana_cost",
                "field:mana_costs",
                HEROES,
                base + "/mana_costs",
                ability["mana_costs"],
                condition,
                "field/mana_costs",
            )
            if int(raw["behavior"]) & 2 and ability["name"] not in NOT_BREAKABLE:
                add(
                    subject,
                    "break_sensitive",
                    "field:behavior",
                    HEROES,
                    base + "/raw_mechanics/behavior",
                    raw["behavior"],
                    condition,
                    "passive-candidate",
                    "needs_review",
                )
            if int(raw["behavior"]) & 8 and int(raw["target_team"]) in (2, 3):
                for field, kind in [
                    ("behavior", "field:behavior"),
                    ("target_team", "enum:target_team"),
                ]:
                    add(
                        subject,
                        "unit_target_spell",
                        kind,
                        HEROES,
                        base + "/raw_mechanics/" + field,
                        raw[field],
                        condition,
                        "enemy-unit-target-candidate",
                        "needs_review",
                    )
            for field in ("description_zh", "description_en", "notes_zh", "notes_en"):
                prose(subject, HEROES, base + "/" + field, ability[field], condition, names)
            for upgrade, key in (("scepter", "scepter_loc"), ("shard", "shard_loc")):
                upgraded = {
                    **condition,
                    "requires_" + upgrade: True,
                    "context": upgrade + "_upgrade",
                }
                prose(
                    subject,
                    HEROES,
                    base + "/upgrade_text/" + key,
                    ability["upgrade_text"][key],
                    upgraded,
                    names,
                )

    for name, item in sorted(sources[ITEMS]["items"].items()):
        if not eligible(item):
            continue
        subject = {
            "subject_type": "item",
            "subject": name,
            "name_zh": item["name_zh"],
            "pointer": "/items/" + escape(name),
            "inventory_status": "registry_candidate",
        }
        subjects.append(subject)
        detail = sources[ITEM_TEXT].get(name, {})
        condition = {"context": "item", "requires_scepter": False, "requires_shard": False}
        for i, ability in enumerate(detail.get("abilities", [])):
            prose(
                subject,
                ITEM_TEXT,
                f"/{escape(name)}/abilities/{i}/description",
                ability.get("description", ""),
                {**condition, "item_ability_type": ability.get("type")},
                (),
            )
        prose(subject, ITEM_TEXT, f"/{escape(name)}/notes", detail.get("notes", ""), condition, ())
        for i, attr in enumerate(detail.get("attrib", [])):
            mechanism = ITEM_ATTRIBUTES.get(attr["key"])
            if mechanism:
                add(
                    subject,
                    mechanism,
                    "item_attr:" + attr["key"],
                    ITEM_TEXT,
                    f"/{escape(name)}/attrib/{i}/value",
                    attr["value"],
                    condition,
                    "item-attribute/" + attr["key"],
                )

    unique = {f["fact_id"]: f for f in facts}
    return {
        "schema": "mechanics-facts/2",
        "extractor_version": VERSION,
        "patch_verified": False,
        "status": "pending_semantic_review",
        "source_hashes": {name: digest(sources[name]) for name in INPUTS},
        "scope": (
            "all registry abilities incl scepter/shard; positive-cost non-neutral non-recipe items"
        ),
        "subjects": subjects,
        "scanned_texts": scanned,
        "facts": sorted(
            unique.values(), key=lambda f: (f["subject"], f["mechanism"], f["fact_id"])
        ),
    }


def load_facts(doc, sources):
    """Strict v2 verification: sources, quotes, and an exact replay of build_facts."""
    if doc.get("schema") != "mechanics-facts/2" or doc.get("extractor_version") != VERSION:
        raise ValueError("Unsupported facts schema or extractor")
    if doc.get("patch_verified") is not False:
        raise ValueError("Patch has not been verified")
    if doc.get("source_hashes") != {name: digest(sources[name]) for name in INPUTS}:
        raise ValueError("Source hash mismatch")
    ids = set()
    for fact in doc["facts"]:
        if fact["fact_id"] in ids:
            raise ValueError("Duplicate fact")
        ids.add(fact["fact_id"])
        ref = fact["pointer"]
        if ref["file"] not in INPUTS:
            raise ValueError("Unknown source")
        value = pointer(sources[ref["file"]], ref["path"])
        if canonical(value) != canonical(fact["value"]):
            raise ValueError("Source value mismatch")
        if fact["quote_encoding"] == "text":
            if not fact["quote"] or not isinstance(value, str) or fact["quote"] not in value:
                raise ValueError("Quote absent from source")
        elif fact["quote_encoding"] != "json" or fact["quote"] != canonical(value):
            raise ValueError("Invalid structured quote")
    if canonical(doc) != canonical(build_facts(sources)):
        raise ValueError("Facts differ from versioned extraction (rules, conditions or coverage)")
    return doc["facts"]


def group_key(fact):
    """Same grouping as v1 review queues, so v1 and v2 groups line up by review_id."""
    return digest([fact["subject_type"], fact["subject"], fact["mechanism"], fact["condition"]])[
        :20
    ]
