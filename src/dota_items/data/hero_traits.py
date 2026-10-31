"""U23 hero trait candidates from the official ability snapshot (hero registry).

Candidates only: every hit carries the ability that triggered it. Final labels are
reviewed by the assistant and spot-checked by the user (knowledge/hero-traits/).
Raw enums used (Valve ability data): behavior bit 2 = passive, bit 8 = unit target;
target_team 2 = enemy, 3 = both, 4 = custom; damage 2 = magical, 4 = pure; type 1 = ultimate.
"""

import re

TRAITS = {
    "evasion": "闪避/致盲",
    "sustain": "治疗/吸血/高回复",
    "mobility": "高机动/逃生",
    "disables": "控制多",
    "dispellable_save": "依赖可驱散保命效果",
    "illusions_summons": "幻象/召唤物",
    "mana_dependent": "法力依赖",
    "magic_burst": "魔法爆发",
    "targeted_spells": "依赖指向技能",
}
PASSIVE, UNIT_TARGET = 2, 8
ENEMY_TEAMS = {2, 3, 4}
BURST_TYPES = {2, 4}
TEXT_PATTERNS = {
    "evasion": r"evasion|miss chance|chance to miss|blind",
    "sustain": r"lifesteal|heal|health regen|restores? .{0,20}health",
    "mobility": (
        r"blink|teleport|leap|dash|jump|charge|invisib|fade|phase|burrow|surge"
        r"|movement speed bonus"
    ),
    "disables": r"\bstun|silence|root|hex|fear|taunt|sleep|cyclone|banish|disable",
    "dispellable_save": r"invulnerab|untargetable|damage reduction|shield|barrier|absorb|immune to",
    "illusions_summons": r"illusion|summon|spawn|ward|creates? .{0,30}(unit|copy|copies)",
    "mana_dependent": r"mana",
}
TARGETED_MIN = 2
BURST_MIN = 700.0


def _base_kit(abilities):
    """Abilities available without Aghanim's upgrades."""
    return [a for a in abilities if not a["granted_by_scepter"] and not a["granted_by_shard"]]


def _mech(a):
    raw = a.get("raw_mechanics") or {}
    return int(raw.get("behavior") or 0), raw.get("target_team"), raw.get("damage"), raw.get("type")


def _text(a):
    parts = [a.get("description_en") or "", *(a.get("notes_en") or [])]
    parts += [s["name"].replace("_", " ") for s in a.get("special_values") or []]
    return " ".join(parts)


def _max_damage(a):
    best = 0.0
    for s in a.get("special_values") or []:
        name = s["name"]
        if "damage" in name and not re.search(r"pct|per|percent|reduction|bonus|tooltip", name):
            best = max([best, *(s.get("values_float") or [])])
    return best


def targeted(abilities):
    """Active enemy unit-target abilities in the base kit."""
    out = []
    for a in _base_kit(abilities):
        behavior, team, _, kind = _mech(a)
        if behavior & UNIT_TARGET and not behavior & PASSIVE and team in ENEMY_TEAMS:
            out.append((a["name_zh"], kind == 1))
    return out


def burst(abilities):
    """Active magical/pure abilities with a max damage value (summed per hero)."""
    out = []
    for a in _base_kit(abilities):
        behavior, _, damage, _ = _mech(a)
        if not behavior & PASSIVE and damage in BURST_TYPES and _max_damage(a) > 0:
            out.append((a["name_zh"], _max_damage(a)))
    return out


def candidates(hero):
    """Trait -> {"candidate": bool, "evidence": [...], "rule": str} for one hero."""
    out = {}
    for trait, pattern in TEXT_PATTERNS.items():
        hits = [a["name_zh"] for a in hero["abilities"] if re.search(pattern, _text(a), re.I)]
        out[trait] = {"candidate": bool(hits), "evidence": hits, "rule": f"text:{pattern}"}
    spells = targeted(hero["abilities"])
    out["targeted_spells"] = {
        "candidate": len(spells) >= TARGETED_MIN or any(ult for _, ult in spells),
        "evidence": [f"{n}{'（大招）' if ult else ''}" for n, ult in spells],
        "rule": f"enemy unit-target actives >= {TARGETED_MIN} or ultimate",
    }
    nukes = burst(hero["abilities"])
    total = sum(v for _, v in nukes)
    out["magic_burst"] = {
        "candidate": total >= BURST_MIN,
        "evidence": [f"{n} {v:g}" for n, v in nukes],
        "rule": f"sum of max magical/pure damage >= {BURST_MIN:g} (total {total:g})",
    }
    return out


def load_traits(doc, registry_heroes):
    """Validate labels against the registry; return {trait: {hero_id: entry}}.

    targeted_spells is computed by rule, never hand-labeled.
    """
    by_name = {h["name_zh"]: h for h in registry_heroes}
    if set(doc["traits"]) != set(TRAITS):
        raise ValueError("Trait list differs from TRAITS")
    out = {trait: {} for trait in TRAITS}
    for trait, entries in doc["labels"].items():
        if trait == "targeted_spells" or trait not in TRAITS:
            raise ValueError(f"Unexpected labeled trait: {trait}")
        for entry in entries:
            hero = by_name.get(entry["hero"])
            if hero is None:
                raise ValueError(f"Unknown hero: {entry['hero']}")
            names = {a["name_zh"] for a in hero["abilities"]}
            missing = [a for a in entry["abilities"] if a not in names]
            if missing or entry["confidence"] not in {"high", "medium", "low"}:
                raise ValueError(f"Bad evidence for {entry['hero']}/{trait}: {missing}")
            if hero["hero_id"] in out[trait]:
                raise ValueError(f"Duplicate label: {entry['hero']}/{trait}")
            out[trait][hero["hero_id"]] = entry
    for hero in registry_heroes:
        spells = targeted(hero["abilities"])
        if len(spells) >= TARGETED_MIN or any(ult for _, ult in spells):
            out["targeted_spells"][hero["hero_id"]] = {
                "hero": hero["name_zh"],
                "abilities": [n for n, _ in spells],
                "confidence": "rule",
            }
    return out
