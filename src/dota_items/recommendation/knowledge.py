"""Versioned knowledge and policy values; no file, network or replay dependencies."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from dota_items.recommendation.contracts import Contract, HeroId, Role, Sha256, Text

NonemptyRefs = Annotated[tuple[Text, ...], Field(min_length=1)]


class Source(Contract):
    source_id: Text
    file: Text
    sha256: Sha256
    url: Text


class Fact(Contract):
    fact_id: Text
    hero_id: HeroId | None = None
    item_key: Text | None = None
    tag: Text
    status: Literal["verified", "unknown", "conflict"]
    source_id: Text
    pointer: Text
    quote: Text
    summary: Text
    conditions: NonemptyRefs

    @model_validator(mode="after")
    def check_owner(self) -> Self:
        if (self.hero_id is None) == (self.item_key is None):
            raise ValueError("fact must belong to exactly one hero or item")
        return self


class Hero(Contract):
    hero_id: HeroId
    name: Text
    attack_type: Literal["Melee", "Ranged"]


class Item(Contract):
    item_key: Text
    name: Text
    fact_ids: NonemptyRefs
    enabled: bool
    held_reason: Text | None = None
    melee_only: bool = False
    excluded_hero_ids: tuple[HeroId, ...] = ()
    choice_group: Text | None = None
    conditions: NonemptyRefs
    tradeoffs: NonemptyRefs

    @model_validator(mode="after")
    def check_held(self) -> Self:
        if self.enabled == bool(self.held_reason):
            raise ValueError("disabled items need a held reason; enabled items must not have one")
        return self


class Anchor(Contract):
    source_id: Text
    pointer: Text
    expected: float
    patch_note_pointer: Text
    patch_note_quote: Text


class PatchBinding(Contract):
    method: Literal["official_current_crosscheck"]
    observed_at_utc: Text
    patch_list_source: Text
    patch_notes_source: Text
    catalog_source: Text
    anchors: Annotated[tuple[Anchor, ...], Field(min_length=1)]
    limitations: NonemptyRefs


class Knowledge(Contract):
    schema_version: Literal["coach-recommendation-knowledge/1"]
    patch: Literal["7.41f"]
    version: Text
    binding: PatchBinding
    sources: Annotated[tuple[Source, ...], Field(min_length=1)]
    heroes: Annotated[tuple[Hero, ...], Field(min_length=1)]
    facts: tuple[Fact, ...]
    items: tuple[Item, ...]

    @model_validator(mode="after")
    def check_references(self) -> Self:
        for rows, key in (
            (self.sources, "source_id"),
            (self.heroes, "hero_id"),
            (self.facts, "fact_id"),
            (self.items, "item_key"),
        ):
            if len({getattr(row, key) for row in rows}) != len(rows):
                raise ValueError(f"duplicate {key}")
        heroes = {h.hero_id for h in self.heroes}
        items = {i.item_key for i in self.items}
        sources = {s.source_id for s in self.sources}
        facts = {f.fact_id: f for f in self.facts}
        for fact in self.facts:
            if fact.source_id not in sources:
                raise ValueError("fact source is missing")
            if fact.hero_id is not None and fact.hero_id not in heroes:
                raise ValueError("fact hero is absent from catalog")
            if fact.item_key is not None and fact.item_key not in items:
                raise ValueError("fact item is absent from inventory")
        for item in self.items:
            if any(
                ref not in facts or facts[ref].item_key != item.item_key for ref in item.fact_ids
            ):
                raise ValueError("item fact must belong to that item")
        return self


class Profile(Contract):
    hero_id: HeroId
    role: Role
    required_fact_ids: NonemptyRefs
    item_keys: NonemptyRefs
    item_rule_ids: NonemptyRefs
    rationale: Text


class NeedRule(Contract):
    rule_id: Text
    side: Literal["self", "enemy", "ally"]
    tag: Text
    need_key: Text
    title: Text
    condition: Text


class ItemRule(Contract):
    rule_id: Text
    item_key: Text
    need_key: Text
    weight: Annotated[float, Field(strict=True, gt=0)]
    reason: Text
    category: Literal["core", "situational", "alternative"]
    stage: Literal["early", "mid", "late"]


class Policy(Contract):
    schema_version: Literal["coach-recommendation-policy/1"]
    patch: Literal["7.41f"]
    version: Text
    profiles: Annotated[tuple[Profile, ...], Field(min_length=1)]
    need_rules: tuple[NeedRule, ...]
    item_rules: tuple[ItemRule, ...]
    limitations: NonemptyRefs

    @model_validator(mode="after")
    def check_unique(self) -> Self:
        if len({(p.hero_id, p.role) for p in self.profiles}) != len(self.profiles):
            raise ValueError("duplicate hero/role support profile")
        rules = [r.rule_id for r in (*self.need_rules, *self.item_rules)]
        if len(rules) != len(set(rules)):
            raise ValueError("duplicate rule ID")
        if len({r.need_key for r in self.need_rules}) != len(self.need_rules):
            raise ValueError("need keys must be unique")
        return self


class Bundle(Contract):
    knowledge: Knowledge
    policy: Policy
    knowledge_sha256: Sha256
    rules_sha256: Sha256

    @model_validator(mode="after")
    def check_policy(self) -> Self:
        kb, policy = self.knowledge, self.policy
        if kb.patch != policy.patch:
            raise ValueError("knowledge/policy patch mismatch")
        heroes = {h.hero_id for h in kb.heroes}
        items = {i.item_key for i in kb.items}
        facts = {f.fact_id: f for f in kb.facts}
        for profile in policy.profiles:
            if profile.hero_id not in heroes or not set(profile.item_keys) <= items:
                raise ValueError("profile contains unknown hero or item")
            for ref in profile.required_fact_ids:
                if ref not in facts or facts[ref].hero_id != profile.hero_id:
                    raise ValueError("profile facts must belong to target hero")
        needs = {r.need_key for r in policy.need_rules}
        for rule in policy.item_rules:
            if rule.item_key not in items or rule.need_key not in needs:
                raise ValueError("item rule has unknown item or need")
        rules = {r.rule_id: r for r in policy.item_rules}
        for profile in policy.profiles:
            if len(set(profile.item_rule_ids)) != len(profile.item_rule_ids):
                raise ValueError("profile rule IDs must be unique")
            if any(
                ref not in rules or rules[ref].item_key not in profile.item_keys
                for ref in profile.item_rule_ids
            ):
                raise ValueError("profile rule is missing or outside its item scope")
        return self
