"""Freeze discovery order before fetching details, then verify it on every execution."""

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field

from dota_items.data.contracts import StrictContract
from dota_items.data.feasibility import AuditConfig
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import now


class SamplingPlan(StrictContract):
    schema_version: Literal["purchase-feasibility-plan/1"] = "purchase-feasibility-plan/1"
    created_at: str
    selection: Literal["discovery_order_slice"] = "discovery_order_slice"
    discovery_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    discovery_count: int = Field(ge=1)
    skip: int = Field(ge=0)
    take: int = Field(ge=1, le=100)
    match_ids: list[int]
    audit_config: AuditConfig


def freeze_plan(discovery: Path, config: AuditConfig, *, skip: int, take: int) -> SamplingPlan:
    if type(skip) is not int or skip < 0 or type(take) is not int or not 1 <= take <= 100:
        raise ValueError("invalid sampling slice")
    contents = read_source_bytes(discovery)
    rows = parse_source_json(contents)
    if not isinstance(rows, list) or skip + take > len(rows):
        raise ValueError("discovery has fewer rows than requested slice")
    selected = rows[skip : skip + take]
    if any(
        not isinstance(r, dict) or type(r.get("match_id")) is not int or r["match_id"] <= 0
        for r in selected
    ):
        raise ValueError("invalid match identity in selected discovery rows")
    ids = [r["match_id"] for r in selected]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate match in selected slice; do not silently replace it")
    return SamplingPlan(
        created_at=now(),
        discovery_sha256=hashlib.sha256(contents).hexdigest(),
        discovery_count=len(rows),
        skip=skip,
        take=take,
        match_ids=ids,
        audit_config=config,
    )


def verify_plan(plan_path: Path, discovery: Path) -> tuple[SamplingPlan, str]:
    contents = read_source_bytes(plan_path)
    plan = SamplingPlan.model_validate_json(contents)
    rebuilt = freeze_plan(discovery, plan.audit_config, skip=plan.skip, take=plan.take)
    # Creation time is metadata; selection and every config value remain bound.
    if plan.model_dump(exclude={"created_at"}) != rebuilt.model_dump(exclude={"created_at"}):
        raise ValueError("sampling plan does not match discovery snapshot")
    return plan, hashlib.sha256(contents).hexdigest()
