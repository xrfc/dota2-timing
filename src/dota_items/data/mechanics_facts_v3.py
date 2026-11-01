"""MK-T3 evidence inventory, version 3: v2 minus upgrade text Valve no longer applies.

The Valve datafeed keeps `scepter_loc`/`shard_loc` strings for some abilities whose
`ability_has_scepter`/`ability_has_shard` flag is false, i.e. the ability currently has
no such upgrade (user U5 spot-check: Outworld Destroyer Arcane Orb scepter, Muerta
Pierce the Veil shard). The hero registry did not keep those flags, so v1/v2 treated
every upgrade string as current. v3 reads a list derived from the raw responses
(`knowledge/mechanics/stale-upgrade-text-v1.json`) and moves facts from that text into
`excluded_facts` with a reason. Everything else is exactly v2; v1/v2 stay frozen.
"""

from dota_items.data import mechanics_facts_v2 as v2
from dota_items.data.mechanics_facts import canonical, digest

STALE = "knowledge/mechanics/stale-upgrade-text-v1.json"
INPUTS = v2.INPUTS + (STALE,)
VERSION = "mechanics-extractor/3"
VOCAB = v2.VOCAB
group_key = v2.group_key
UPGRADES = {
    "scepter": ("scepter_loc", "ability_has_scepter", "ability_is_granted_by_scepter"),
    "shard": ("shard_loc", "ability_has_shard", "ability_is_granted_by_shard"),
}


def stale_upgrades(raw_heroes):
    """Upgrade strings present while the ability's has-upgrade flag is false.

    Abilities granted by that same upgrade are skipped: their text describes the
    granted ability itself (e.g. Sniper Concussive Grenade from shard).
    """
    rows = []
    for hero in raw_heroes:
        for ability in hero["abilities"]:
            for upgrade, (text, has, granted) in UPGRADES.items():
                if ability.get(text) and not ability.get(has) and not ability.get(granted):
                    rows.append(
                        {
                            "hero_id": hero["id"],
                            "hero": hero["name"],
                            "ability": ability["name"],
                            "upgrade": upgrade,
                            "flag": has,
                            "flag_value": ability.get(has),
                        }
                    )
    return sorted(rows, key=lambda r: (r["hero_id"], r["ability"], r["upgrade"]))


def load_stale(doc, registry):
    if doc.get("schema") != "stale-upgrade-text/1" or doc.get("patch_verified") is not False:
        raise ValueError("Unsupported stale upgrade list")
    texts = {
        ability["name"]: ability["upgrade_text"]
        for hero in registry["heroes"]
        for ability in hero["abilities"]
    }
    pairs = set()
    for row in doc["entries"]:
        key = UPGRADES[row["upgrade"]][0]
        if not any(texts.get(row["ability"], {}).get(key, {}).values()):
            raise ValueError(f"No registry upgrade text for {row['ability']} {row['upgrade']}")
        pairs.add((row["ability"], row["upgrade"] + "_upgrade"))
    return pairs


def stale_fact(fact, pairs):
    return (
        fact["subject_type"] == "hero_ability"
        and (fact["subject"], fact["condition"]["context"]) in pairs
        and "/upgrade_text/" in fact["pointer"]["path"]
    )


def build_facts(sources):
    doc = v2.build_facts(sources)
    pairs = load_stale(sources[STALE], sources[v2.HEROES])
    kept = [f for f in doc["facts"] if not stale_fact(f, pairs)]
    excluded = [
        {**f, "excluded_reason": "upgrade_flag_false"} for f in doc["facts"] if stale_fact(f, pairs)
    ]
    return {
        **doc,
        "schema": "mechanics-facts/3",
        "extractor_version": VERSION,
        "source_hashes": {name: digest(sources[name]) for name in INPUTS},
        "facts": kept,
        "excluded_facts": excluded,
    }


def load_facts(doc, sources):
    """Strict v3 verification: v2 checks on kept facts, then an exact replay."""
    if doc.get("schema") != "mechanics-facts/3" or doc.get("extractor_version") != VERSION:
        raise ValueError("Unsupported facts schema or extractor")
    if doc.get("source_hashes") != {name: digest(sources[name]) for name in INPUTS}:
        raise ValueError("Source hash mismatch")
    if canonical(doc) != canonical(build_facts(sources)):
        raise ValueError("Facts differ from versioned extraction (rules, conditions or coverage)")
    return doc["facts"]
