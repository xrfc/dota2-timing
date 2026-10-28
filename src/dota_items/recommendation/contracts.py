"""Pure, versioned lineup contracts. Validation is not semantic admission."""

import hashlib
import json
from collections.abc import Collection, Mapping
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HeroId = Annotated[int, Field(strict=True, gt=0)]
Role = Annotated[int, Field(strict=True, ge=1, le=5)]
Text = Annotated[str, Field(strict=True, min_length=1, pattern=r"\S")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Team = Literal["radiant", "dire"]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, allow_inf_nan=False, revalidate_instances="always"
    )


class LineupRequest(Contract):
    """Structural validation only; use validate_lineup at an application boundary."""

    schema_version: Literal["coach-lineup-request/1"] = "coach-lineup-request/1"
    patch: Literal["7.41f"]
    radiant: Annotated[tuple[HeroId, ...], Field(min_length=5, max_length=5)]
    dire: Annotated[tuple[HeroId, ...], Field(min_length=5, max_length=5)]
    target_team: Team
    target_hero_id: HeroId
    role: Role

    @field_validator("radiant", "dire")
    @classmethod
    def canonical_order(cls, heroes: tuple[int, ...]) -> tuple[int, ...]:
        # Input order is not a lane assignment. Only the target's role is known.
        return tuple(sorted(heroes))

    @model_validator(mode="after")
    def check_lineup(self) -> Self:
        if len(set(self.radiant + self.dire)) != 10:
            raise ValueError("heroes must be unique across both teams")
        if self.target_hero_id not in getattr(self, self.target_team):
            raise ValueError("target hero must belong to target_team")
        return self

    def fingerprint(self) -> str:
        """Stable for team permutations, distinct for roles, sides and targets."""
        encoded = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class UnknownHeroError(ValueError):
    code = "unknown_hero"

    def __init__(self, hero_ids: Collection[int]):
        self.hero_ids = tuple(sorted(hero_ids))
        super().__init__(f"unknown hero IDs: {self.hero_ids}")


def validate_lineup(
    payload: Mapping[str, object] | LineupRequest, *, known_hero_ids: Collection[int]
) -> LineupRequest:
    """Validate identity against an explicitly supplied catalog, without I/O.

    Catalog membership is not patch-mechanic or recommendation coverage approval.
    The caller loads the catalog; no knowledge script or Gem import is needed.
    """
    if not known_hero_ids or any(type(hero) is not int or hero <= 0 for hero in known_hero_ids):
        raise ValueError("known_hero_ids must be a nonempty catalog of positive integers")
    request = LineupRequest.model_validate(payload)
    unknown = set(request.radiant + request.dire) - set(known_hero_ids)
    if unknown:
        raise UnknownHeroError(unknown)
    return request


class EvidenceReference(Contract):
    """Required provenance assertions, not a proof that a human reviewed the source."""

    fact_id: Text
    source_ref: Text
    source_sha256: Sha256
    source_patch: Literal["7.41f"]
    review_status: Literal["verified"]
    hero_id: HeroId | None = None


class HeroCoverage(Contract):
    hero_id: HeroId
    status: Literal["verified", "unknown", "conflict"]
    fact_ids: tuple[Text, ...] = ()
    notes: Text

    @model_validator(mode="after")
    def check_facts(self) -> Self:
        if (self.status == "verified") != bool(self.fact_ids):
            raise ValueError("only verified coverage must have fact_ids")
        if len(set(self.fact_ids)) != len(self.fact_ids):
            raise ValueError("coverage fact_ids must be unique")
        return self


class ScoreComponent(Contract):
    """Uncalibrated rule score, never a probability or estimated win rate."""

    name: Text
    value: Annotated[float, Field(strict=True)]
    reason: Text


class EquipmentCandidate(Contract):
    # Item existence/category/recipe semantics are checked by the future M02/M04 layer.
    item_key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    category: Literal["core", "situational", "alternative"]
    stage: Literal["early", "mid", "late"]
    reason: Text
    conditions: tuple[Text, ...] = ()
    tradeoffs: Annotated[tuple[Text, ...], Field(min_length=1)]
    rule_ids: Annotated[tuple[Text, ...], Field(min_length=1)]
    fact_ids: Annotated[tuple[Text, ...], Field(min_length=1)]
    score_components: tuple[ScoreComponent, ...] = ()

    @model_validator(mode="after")
    def check_references(self) -> Self:
        for field in ("rule_ids", "fact_ids"):
            refs = getattr(self, field)
            if len(set(refs)) != len(refs):
                raise ValueError(f"candidate {field} must be unique")
        names = [component.name for component in self.score_components]
        if len(set(names)) != len(names):
            raise ValueError("score component names must be unique")
        return self


class Recommendation(Contract):
    """Result envelope for a future engine; this module never produces advice."""

    schema_version: Literal["coach-lineup-recommendation/1"] = "coach-lineup-recommendation/1"
    request: LineupRequest
    input_fingerprint: Sha256
    knowledge_version: Text
    knowledge_sha256: Sha256
    rules_version: Text
    rules_sha256: Sha256
    engine_version: Text
    status: Literal["supported", "partial", "unsupported"]
    coverage: Annotated[tuple[HeroCoverage, ...], Field(min_length=10, max_length=10)]
    evidence: tuple[EvidenceReference, ...] = ()
    candidates: tuple[EquipmentCandidate, ...] = ()
    empty_reason: Text | None = None
    limitations: Annotated[tuple[Text, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def check_result(self) -> Self:
        if self.input_fingerprint != self.request.fingerprint():
            raise ValueError("input_fingerprint does not match request")
        heroes = set(self.request.radiant + self.request.dire)
        by_hero = {row.hero_id: row for row in self.coverage}
        if len(by_hero) != 10 or set(by_hero) != heroes:
            raise ValueError("coverage must contain each lineup hero exactly once")
        verified = {hero for hero, row in by_hero.items() if row.status == "verified"}
        if self.status == "supported" and len(verified) != 10:
            raise ValueError("supported requires verified coverage of all ten heroes")
        if self.status == "partial" and not 0 < len(verified) < 10:
            raise ValueError("partial requires both verified and missing/conflicting coverage")
        if self.status == "unsupported" and self.candidates:
            raise ValueError("unsupported cannot contain candidates")
        if self.candidates and self.request.target_hero_id not in verified:
            raise ValueError("candidates require verified target hero coverage")
        if bool(self.candidates) == bool(self.empty_reason):
            raise ValueError("empty_reason is required exactly when candidates are empty")
        facts = {fact.fact_id: fact for fact in self.evidence}
        if len(facts) != len(self.evidence):
            raise ValueError("evidence fact_ids must be unique")
        for fact in self.evidence:
            if fact.hero_id is not None and fact.hero_id not in verified:
                raise ValueError("hero evidence must refer to verified lineup coverage")
        for row in self.coverage:
            for fact_id in row.fact_ids:
                if fact_id not in facts or facts[fact_id].hero_id != row.hero_id:
                    raise ValueError("coverage fact must resolve to evidence for the same hero")
        item_keys = [candidate.item_key for candidate in self.candidates]
        if len(set(item_keys)) != len(item_keys):
            raise ValueError("candidate item keys must be unique across categories")
        for candidate in self.candidates:
            if any(fact_id not in facts for fact_id in candidate.fact_ids):
                raise ValueError("candidate fact_ids must resolve to evidence")
        return self
