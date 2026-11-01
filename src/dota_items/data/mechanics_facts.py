"""Reproducible MK-T3 evidence inventory. No I/O, training or strategy inference."""

import hashlib
import json
from collections import Counter

from dota_items.data.mechanics import load_enums, load_vocabulary, unconfirmed
from dota_items.data.mechanics_rules import text_hits

HEROES = "knowledge/hero-capabilities/hero-registry.json"
ITEMS = "knowledge/items/item-registry.json"
ITEM_TEXT = "knowledge/items/sources/dotaconstants-items.json"
ENUMS = "knowledge/mechanics/enums-v1.json"
VOCAB = "knowledge/mechanics/vocabulary-v1.json"
USER_EVIDENCE = "docs/decisions/2026-11-01-vocabulary-answers.md"
INPUTS = (HEROES, ITEMS, ITEM_TEXT, ENUMS, VOCAB, USER_EVIDENCE)
VERSION = "mechanics-extractor/1"


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def pointer(document, path):
    """Resolve an RFC 6901 pointer; no filesystem paths are opened."""
    if not path.startswith("/"):
        raise ValueError("Expected absolute JSON pointer")
    value = document
    try:
        for token in path[1:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                if not token.isdecimal() or (len(token) > 1 and token.startswith("0")):
                    raise ValueError("Invalid array index")
                value = value[int(token)]
            else:
                value = value[token]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Invalid source pointer: {path}") from exc
    return value


def escape(key):
    return str(key).replace("~", "~0").replace("/", "~1")


def eligible(item):
    """Frozen registry's inventory proxy, not certification of current shop availability."""
    return not item["neutral"] and not item["recipe"] and (item["cost"] or 0) > 0


def text_leaves(value, path):
    if isinstance(value, str):
        if value.strip():
            yield path, value
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from text_leaves(child, f"{path}/{i}")
    elif isinstance(value, dict):
        for key, child in sorted(value.items()):
            yield from text_leaves(child, f"{path}/{escape(key)}")


def build_facts(sources):
    """Extract all subjects; ambiguous prose and passive flags require review.

    'auto' certifies only a decoded field/attribute observation. Text candidates
    do not establish polarity, effect recipient or application timing.
    """
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
        record["fact_id"] = "mf-" + digest(record)[:20]
        facts.append(record)

    def prose(subject, file, path, value, condition):
        for leaf, text in text_leaves(value, path):
            scanned.append(
                {"subject": subject["subject"], "file": file, "path": leaf, "condition": condition}
            )
            for mid, quote in text_hits(text):
                if "official_text" in terms[mid]["evidence"]:
                    add(
                        subject,
                        mid,
                        "official_text",
                        file,
                        leaf,
                        text,
                        condition,
                        "prose/" + mid,
                        "needs_review",
                        quote,
                    )

    for hi, hero in enumerate(sources[HEROES]["heroes"]):
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
            if int(raw["behavior"]) & 2:
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
                prose(subject, HEROES, base + "/" + field, ability[field], condition)
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
            )
        prose(subject, ITEM_TEXT, f"/{escape(name)}/notes", detail.get("notes", ""), condition)
        for i, attr in enumerate(detail.get("attrib", [])):
            if attr["key"] in ("status_resistance", "slow_resistance"):
                add(
                    subject,
                    attr["key"],
                    "item_attr:" + attr["key"],
                    ITEM_TEXT,
                    f"/{escape(name)}/attrib/{i}/value",
                    attr["value"],
                    condition,
                    "item-attribute/" + attr["key"],
                )

    unique = {f["fact_id"]: f for f in facts}
    return {
        "schema": "mechanics-facts/1",
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
    """Strict v1 verification including source ownership, conditions and full coverage.

    A versioned producer replay rejects forged attribution, altered values, missing
    rows, upgraded auto approvals and extra rows as well as quote/hash tampering.
    Manual review lives separately and cannot silently mutate this frozen inventory.
    """
    if doc.get("schema") != "mechanics-facts/1" or doc.get("extractor_version") != VERSION:
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
        raise ValueError(
            "Facts differ from versioned extraction (identity, rules, conditions or coverage)"
        )
    return doc["facts"]


def coverage(doc, terms):
    facts = doc["facts"]
    by_term = {}
    for mid in terms:
        rows = [f for f in facts if f["mechanism"] == mid]
        by_term[mid] = {
            "hero_abilities": len(
                {f["subject"] for f in rows if f["subject_type"] == "hero_ability"}
            ),
            "items": len({f["subject"] for f in rows if f["subject_type"] == "item"}),
            "observations": len(rows),
            "needs_review": sum(f["review"] == "needs_review" for f in rows),
        }
    present = {f["subject"] for f in facts}
    text_subjects = {s["subject"] for s in doc["scanned_texts"]}
    return {
        "schema": "mechanics-coverage/1",
        "patch_verified": False,
        "subjects": dict(Counter(s["subject_type"] for s in doc["subjects"])),
        "facts": len(facts),
        "review": dict(Counter(f["review"] for f in facts)),
        "scanned_texts": len(doc["scanned_texts"]),
        "mechanisms": by_term,
        "zero_hit_mechanisms": [
            mid for mid, counts in by_term.items() if not counts["observations"]
        ],
        "subjects_without_facts": [
            s["subject"] for s in doc["subjects"] if s["subject"] not in present
        ],
        "subjects_without_text": [
            s["subject"] for s in doc["subjects"] if s["subject"] not in text_subjects
        ],
        "limitations": [
            "No hit means unknown, not absence. Recall and semantic precision are unmeasured.",
            "All prose hits require review of polarity, recipient, timing, facets and upgrades.",
            "Item prose is a community snapshot; shop availability and patch are unverified.",
            "Passivity does not establish a key passive or susceptibility to break.",
            "Unit-target flags do not certify spell-block/reflection interactions.",
            "Basher piercing remains a gap: vocabulary disallows manual evidence for this term.",
            "U28 key-passive examples require review; passive flags alone are insufficient.",
        ],
    }
