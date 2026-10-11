"""Pure rule recommendation, with data-driven hero/role support and diagnostics."""

from collections import defaultdict
from typing import Literal

from dota_items.recommendation.contracts import (
    Contract,
    EquipmentCandidate,
    EvidenceReference,
    HeroCoverage,
    LineupRequest,
    Recommendation,
    ScoreComponent,
    Text,
    validate_lineup,
)
from dota_items.recommendation.knowledge import Bundle

ENGINE_VERSION = "lineup-rules/1"


class Need(Contract):
    need_key: Text
    title: Text
    side: Literal["self", "enemy", "ally"]
    fact_ids: tuple[Text, ...]
    rule_id: Text
    conditions: tuple[Text, ...]


class Exclusion(Contract):
    item_key: Text
    reason: Text


class Analysis(Contract):
    schema_version: Literal["coach-lineup-analysis/1"] = "coach-lineup-analysis/1"
    recommendation: Recommendation
    needs: tuple[Need, ...]
    exclusions: tuple[Exclusion, ...]


def recommend(request: LineupRequest, bundle: Bundle) -> Analysis:
    """Use a source-verified bundle from load_bundle at the application boundary.

    Structural revalidation protects against unchecked Pydantic copies; physical
    source verification belongs to the file adapter, not this pure function.
    """
    bundle = Bundle.model_validate(bundle)
    kb, policy = bundle.knowledge, bundle.policy
    request = validate_lineup(request, known_hero_ids=[h.hero_id for h in kb.heroes])
    heroes = set(request.radiant + request.dire)
    ally = set(getattr(request, request.target_team)) - {request.target_hero_id}
    enemy = heroes - ally - {request.target_hero_id}
    facts = {f.fact_id: f for f in kb.facts}
    sources = {s.source_id: s for s in kb.sources}
    coverage = []
    usable = {}
    for hero in sorted(heroes):
        owned = sorted((f for f in kb.facts if f.hero_id == hero), key=lambda f: f.fact_id)
        # A known conflicting entry blocks this hero's claims until reconciled.
        conflict = any(f.status == "conflict" for f in owned)
        accepted = tuple(f.fact_id for f in owned if f.status == "verified")
        status = "conflict" if conflict else "verified" if accepted else "unknown"
        refs = accepted if status == "verified" else ()
        usable.update({ref: facts[ref] for ref in refs})
        coverage.append(
            HeroCoverage(
                hero_id=hero,
                status=status,
                fact_ids=refs,
                notes="仅覆盖首批规则引用的摘录，不代表英雄全部机制；未知不等于没有威胁。",
            )
        )
    profile = next(
        (
            p
            for p in policy.profiles
            if (p.hero_id, p.role) == (request.target_hero_id, request.role)
        ),
        None,
    )
    reason = None
    if profile is None:
        reason = "该英雄/位置组合尚未验收支持；不会自动改成其他英雄或位置。"
    elif not set(profile.required_fact_ids) <= usable.keys():
        reason = "目标英雄必需机制证据缺失或冲突，拒绝产生装备建议。"
    needs = []
    if reason is None:
        sides = {"self": {request.target_hero_id}, "ally": ally, "enemy": enemy}
        for rule in sorted(policy.need_rules, key=lambda row: row.rule_id):
            matches = sorted(
                f.fact_id
                for f in usable.values()
                if f.hero_id in sides[rule.side] and f.tag == rule.tag
            )
            if matches:
                conditions = sorted(
                    {rule.condition, *(c for ref in matches for c in facts[ref].conditions)}
                )
                needs.append(
                    Need(
                        need_key=rule.need_key,
                        title=rule.title,
                        side=rule.side,
                        fact_ids=tuple(matches),
                        rule_id=rule.rule_id,
                        conditions=tuple(conditions),
                    )
                )
    needs_by_key = {n.need_key: n for n in needs}
    candidates, exclusions = [], []
    items = {item.item_key: item for item in kb.items}
    target = next(h for h in kb.heroes if h.hero_id == request.target_hero_id)
    if reason is None:
        for key in sorted(set(profile.item_keys)):
            item = items[key]
            blocked = None
            if not item.enabled:
                blocked = item.held_reason
            elif any(facts[ref].status != "verified" for ref in item.fact_ids):
                blocked = "装备事实未知或冲突，不能参与排序。"
            elif item.melee_only and target.attack_type != "Melee":
                blocked = "候选依赖近战限定效果，与目标攻击类型不符。"
            elif target.hero_id in item.excluded_hero_ids:
                blocked = "目标属于该装备效果的禁用或待核验英雄范围。"
            rules = sorted(
                (
                    r
                    for r in policy.item_rules
                    if r.item_key == key
                    and r.need_key in needs_by_key
                    and r.rule_id in profile.item_rule_ids
                ),
                key=lambda r: r.rule_id,
            )
            if blocked or not rules:
                exclusions.append(
                    Exclusion(
                        item_key=key,
                        reason=blocked or "当前已核验事实没有触发适用需求。",
                    )
                )
                continue
            refs = set(item.fact_ids) | set(profile.required_fact_ids)
            conditions = set(item.conditions)
            rule_ids, components = set(), []
            for rule in rules:
                need = needs_by_key[rule.need_key]
                refs.update(need.fact_ids)
                conditions.update(need.conditions)
                rule_ids.update((need.rule_id, rule.rule_id))
                components.append(
                    ScoreComponent(
                        name=rule.rule_id,
                        value=rule.weight,
                        reason=rule.reason,
                    )
                )
            # Baseline vs matchup category is explicit; stages are policy hints,
            # not elapsed minutes, purchase order or inventory completion.
            strongest = max(rules, key=lambda r: (r.weight, r.rule_id))
            candidates.append(
                EquipmentCandidate(
                    item_key=key,
                    category=strongest.category,
                    stage=strongest.stage,
                    reason="；".join(r.reason for r in rules),
                    conditions=tuple(sorted(conditions)),
                    tradeoffs=item.tradeoffs,
                    rule_ids=tuple(sorted(rule_ids)),
                    fact_ids=tuple(sorted(refs)),
                    score_components=tuple(components),
                )
            )
    candidates.sort(key=lambda c: (-sum(x.value for x in c.score_components), c.item_key))
    groups = defaultdict(list)
    for i, candidate in enumerate(candidates):
        group = items[candidate.item_key].choice_group
        if group:
            groups[group].append(i)
    for group, indexes in groups.items():
        if len(indexes) < 2:
            continue
        preferred = candidates[indexes[0]].item_key
        for i in indexes:
            candidate = candidates[i]
            data = candidate.model_dump()
            data["conditions"] = (
                *candidate.conditions,
                f"{group}为选择组而非连购清单；当前规则优先候选：{preferred}。",
            )
            if i != indexes[0]:
                data["category"] = "alternative"
            candidates[i] = EquipmentCandidate.model_validate(data)
    refs = set(usable) | {ref for c in candidates for ref in c.fact_ids}
    evidence = []
    for ref in sorted(refs):
        fact = facts[ref]
        source = sources[fact.source_id]
        evidence.append(
            EvidenceReference(
                fact_id=ref,
                source_ref=f"{source.file}#{fact.pointer}",
                source_sha256=source.sha256,
                source_patch=kb.patch,
                review_status="verified",
                hero_id=fact.hero_id,
            )
        )
    count = sum(row.status == "verified" for row in coverage)
    status = "unsupported" if reason or count == 0 else "supported" if count == 10 else "partial"
    if not candidates and reason is None:
        reason = "已核验范围内无满足条件的候选；请查看过滤原因和覆盖缺口。"
    result = Recommendation(
        request=request,
        input_fingerprint=request.fingerprint(),
        knowledge_version=kb.version,
        knowledge_sha256=bundle.knowledge_sha256,
        rules_version=policy.version,
        rules_sha256=bundle.rules_sha256,
        engine_version=ENGINE_VERSION,
        status=status,
        coverage=tuple(coverage),
        evidence=tuple(evidence),
        candidates=tuple(candidates),
        empty_reason=reason,
        limitations=(*kb.binding.limitations, *policy.limitations),
    )
    return Analysis(recommendation=result, needs=tuple(needs), exclusions=tuple(exclusions))
