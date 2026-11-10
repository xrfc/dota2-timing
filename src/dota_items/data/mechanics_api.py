"""Knowledge reading API: the one way tracks A and B read mechanics knowledge (U124 step 2).

Callers get plain values with fixed meanings instead of interpreting internal JSON:

- `version`: the patch, whether it was checked, and the path and hash of every file read.
- Trait counts: `base` counts abilities that work without Aghanim's Scepter or Shard (what
  is known before a game); `with_upgrades` also counts upgrade-only abilities.
- Confirmation: a fact counts as confirmed only when its basis is the user's (`user*`) or a
  game data field (`field`); `two_ai` is not confirmed.
- Conditions: `when` is base / scepter / shard / item / any; `unless` lists upgrades that
  switch a relation off. `relation_holds` returns True, False, or None for "not known yet".
- Unknown names raise `KeyError`; nothing silently returns an empty result.

Relations are candidates computed from rules, not verified pairs. Contract and examples:
docs/knowledge-api.md.
"""

import json
from pathlib import Path

from dota_items.data.mechanics_conditions import holds
from dota_items.data.mechanics_current import load_current

API_VERSION = "mechanics-api/1"
CONFIRMED_PREFIXES = ("user", "field")
UPGRADES = ("base", "with_upgrades")
PASSIVE_BIT = 2  # DOTA_ABILITY_BEHAVIOR_PASSIVE


def is_confirmed(basis):
    return basis.split(":")[0].startswith(CONFIRMED_PREFIXES)


class Knowledge:
    """A validated, read-only view of the current knowledge."""

    def __init__(self, root=Path("."), registry="knowledge/hero-capabilities/hero-registry.json"):
        root = Path(root)
        current = load_current(root)
        self._entries = current["entries"]
        self.version = {
            "api": API_VERSION,
            "patch": current["patch"]["name"],
            "patch_checked": current["patch"]["verified"],
            "files": {
                n: {"path": e["path"], "sha256": e["sha256"]} for n, e in self._entries.items()
            },
        }
        heroes = json.loads((root / registry).read_text(encoding="utf-8"))["heroes"]
        self._owner = {a["name"]: h["hero_id"] for h in heroes for a in h["abilities"]}
        self._ability_zh = {a["name"]: a["name_zh"] for h in heroes for a in h["abilities"]}
        self._raw = {
            a["name"]: a.get("raw_mechanics") or {} for h in heroes for a in h["abilities"]
        }
        self._hero_names = {h["hero_id"]: h["name_zh"] for h in heroes}
        traits = self._read("hero_traits")["traits"]
        self._traits = {
            trait: {c["hero_id"]: {u: c[u] for u in UPGRADES} for c in spec["counts"]}
            for trait, spec in traits.items()
            if not spec.get("pending")
        }
        self._trait_zh = {trait: spec["zh"] for trait, spec in traits.items()}
        self._rules = {r["id"]: r for r in self._read("rules_evaluation")["rules"]}
        self._facts = self._read("facts")["rows"]
        self._mechanism_ids = {m["id"] for m in self._read("vocabulary")["mechanisms"]}

    def _read(self, name):
        return json.loads(self._entries[name]["file"].read_text(encoding="utf-8"))

    # Heroes and traits -------------------------------------------------------------------
    def hero_ids(self):
        return sorted(self._hero_names)

    def hero_name(self, hero_id):
        if hero_id not in self._hero_names:
            raise KeyError(f"Unknown hero {hero_id}")
        return self._hero_names[hero_id]

    def ability_name(self, ability):
        if ability not in self._ability_zh:
            raise KeyError(f"Unknown ability {ability}")
        return self._ability_zh[ability]

    def ability_owner(self, ability):
        if ability not in self._owner:
            raise KeyError(f"Unknown ability {ability}")
        return self._owner[ability]

    def traits(self):
        """{trait id: Chinese name} for settled traits."""
        return {t: self._trait_zh[t] for t in self._traits}

    def trait_count(self, hero_id, trait, upgrades="base"):
        if upgrades not in UPGRADES:
            raise ValueError(f"upgrades must be one of {UPGRADES}")
        if trait not in self._traits:
            raise KeyError(f"Unknown or pending trait {trait}")
        if hero_id not in self._traits[trait]:
            raise KeyError(f"Unknown hero {hero_id}")
        return self._traits[trait][hero_id][upgrades]

    def team_trait_sum(self, hero_ids, trait, upgrades="base"):
        return sum(self.trait_count(h, trait, upgrades) for h in hero_ids)

    def heroes_owning(self, abilities):
        """Hero ids that own any of these abilities; unknown ability names raise."""
        unknown = [a for a in abilities if a not in self._owner]
        if unknown:
            raise KeyError(f"Unknown abilities {unknown}")
        return {self._owner[a] for a in abilities}

    # Facts --------------------------------------------------------------------------------
    def mechanisms(self, subject):
        """Accepted mechanisms of one ability or item, with condition and confirmation."""
        rows = [r for r in self._facts if r["subject"] == subject]
        if not rows and subject not in self._owner:
            raise KeyError(f"Unknown subject {subject}")
        return [
            {
                "mechanism": r["mechanism"],
                "condition": r["condition"]["context"],
                "confirmed": is_confirmed(r["basis"]),
                "basis": r["basis"],
            }
            for r in rows
            if r["decision"] == "accept"
        ]

    def subjects_with(self, mechanism):
        """Abilities and items with an accepted fact for this mechanism (B0 save means)."""
        if mechanism not in self._mechanism_ids:
            raise KeyError(f"Unknown mechanism {mechanism}")
        return [
            {
                "subject": r["subject"],
                "subject_zh": r.get("subject_zh"),
                "is_ability": r["subject"] in self._owner,
                "condition": r["condition"]["context"],
                "confirmed": is_confirmed(r["basis"]),
                "basis": r["basis"],
            }
            for r in self._facts
            if r["mechanism"] == mechanism and r["decision"] == "accept"
        ]

    def trait_subject_filter(self, trait):
        """{mechanism: [subjects]} limits a trait applies (e.g. U121 escape haste skills)."""
        traits = self._read("trait_mapping")["traits"]
        if trait not in traits:
            raise KeyError(f"Unknown trait {trait}")
        return {m: list(s) for m, s in (traits[trait].get("only_subjects") or {}).items()}

    def ability_targeting(self, ability):
        """Game-file targeting of a hero ability: passive or not, and target_team
        (0 none/self, 1 friendly, 2 enemy, 3 both). Unknown abilities raise."""
        if ability not in self._raw:
            raise KeyError(f"Unknown ability {ability}")
        raw = self._raw[ability]
        behavior = int(raw.get("behavior") or 0)
        return {"passive": bool(behavior & PASSIVE_BIT), "target_team": raw.get("target_team")}

    # Rules --------------------------------------------------------------------------------
    def rule(self, rule_id):
        if rule_id not in self._rules:
            raise KeyError(f"Unknown rule {rule_id}")
        r = self._rules[rule_id]
        return {
            "id": r["id"],
            "zh": r["zh"],
            "relation": r["relation"],
            "status": r["status"],
            "not_computed": r.get("not_evaluated", []),
        }

    def rule_target_heroes(self, rule_id):
        """Heroes owning a target ability of the rule (candidate relation, not verified)."""
        self.rule(rule_id)
        return {self._owner[t] for t in self._rules[rule_id]["targets"] if t in self._owner}

    def relation_holds(self, rule_id, target, upgrades=None):
        """Does the rule reach this target under the known upgrades? True, False or None."""
        self.rule(rule_id)
        conditions = self._rules[rule_id].get("target_conditions", {})
        if target not in conditions:
            raise KeyError(f"{target} is not a target of {rule_id}")
        return holds(conditions[target], upgrades)
