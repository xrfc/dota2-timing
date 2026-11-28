"""Conservative projections of revised evidence, without inventing rule interactions."""

import json
from collections import Counter, defaultdict
from copy import deepcopy

from dota_items.data.mechanics_evidence_admission import build_evidence_admission

BASE_SCHEMAS = {
    "profiles": "mechanics-action-profiles/1",
    "counter_graph": "candidate-counter-graph/1",
    "hero_traits": "candidate-hero-traits/1",
    "save_means": "candidate-save-means/1",
    "mobility": "candidate-hero-mobility/1",
}
POLICY = "mechanics-evidence-projection/7.42-v1"


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _index(rows):
    result = {}
    for row in rows:
        key = row.get("review_id")
        if not isinstance(key, str) or not key or key in result:
            raise ValueError("Missing or duplicate fact identity")
        result[key] = row
    return result


def _revised(value, before, after, seen):
    if isinstance(value, dict):
        if "review_id" in value and "candidate_usable" in value:
            key = value["review_id"]
            if key not in before or _canonical(value) != _canonical(before[key]):
                raise ValueError("Derived fact copy differs from baseline admission")
            seen.add(key)
            return deepcopy(after[key])
        return {key: _revised(item, before, after, seen) for key, item in value.items()}
    if isinstance(value, list):
        return [_revised(item, before, after, seen) for item in value]
    return value


def _constraints(ids, rows):
    if not isinstance(ids, list) or len(set(ids)) != len(ids) or set(ids) - rows.keys():
        raise ValueError("Invalid derived fact references")
    return [
        {
            "review_id": key,
            "condition": deepcopy(rows[key]["condition"]),
            "engineering_admission": deepcopy(rows[key]["engineering_admission"]),
        }
        for key in ids
        if "engineering_admission" in rows[key]
    ]


def _guard(value, rows):
    if type(value.get("candidate_usable")) is not bool:
        raise ValueError("Candidate eligibility must be a JSON boolean")
    ids = value.get("fact_ids", [])
    constraints = _constraints(ids, rows)
    blocked = [key for key in ids if not rows[key]["candidate_usable"]]
    if constraints:
        value["evidence_constraints"] = constraints
        value["constraint_evaluator_verified"] = False
        value["projection_blockers"] = ["structured_conditions_or_interactions_not_evaluated"]
        value["candidate_usable"] = False
    if blocked:
        value["candidate_usable"] = False
    value["blocked_fact_ids"] = blocked
    return bool(constraints)


def project_evidence_assets(
    baseline, admission, assets, *, exact_patch, source_refs, engineering_evidence, documents
):
    """Replace fact copies and tighten affected legacy rules; never open new edges.

    Byte verification belongs to the caller. Rebuild the entire admission here so
    adding forged metadata cannot promote an unrelated pending fact.
    """
    if (
        exact_patch != "7.42"
        or baseline.get("schema") != "mechanics-action-admission/1"
        or admission.get("schema") != "mechanics-evidence-admission/1"
        or admission.get("patch") != exact_patch
        or admission.get("formal_use_allowed") is not False
        or admission.get("training_allowed") is not False
        or admission.get("action_review_allowed") is not False
        or set(assets) != set(BASE_SCHEMAS)
    ):
        raise ValueError("Closed exact-patch evidence admission and complete baseline required")
    rebuilt = build_evidence_admission(
        baseline,
        engineering_evidence,
        documents,
        exact_patch=exact_patch,
        source_refs=admission.get("source_refs"),
    )
    if _canonical(admission) != _canonical(rebuilt):
        raise ValueError("Admission differs from complete registered evidence reconstruction")
    before, after = _index(baseline["rows"]), _index(admission["rows"])
    if before.keys() != after.keys():
        raise ValueError("Evidence projection cannot add or remove facts")
    for key, row in after.items():
        original = before[key]
        for field in ("subject", "mechanism", "decision", "basis", "user_approved_for_patch"):
            if row[field] != original[field]:
                raise ValueError("Evidence projection cannot change identity, decision or approval")
        if row != original and "engineering_admission" not in row:
            raise ValueError("Changed fact lacks explicit engineering evidence")
    output, observed, counts = {}, set(), Counter()
    for name, payload in assets.items():
        if (
            payload.get("schema") != BASE_SCHEMAS[name]
            or payload.get("policy") != "mechanics-action-assets/7.42-v1"
            or payload.get("patch") != exact_patch
            or payload.get("formal_use_allowed") is not False
            or payload.get("training_allowed") is not False
            or payload.get("source_refs") != baseline.get("source_refs")
        ):
            raise ValueError("Derived baseline identity or sources differ")
        output[name] = _revised(payload, before, after, observed)
    profiles = output["profiles"]
    profile_ids, owners, hero_ids = [], {}, set()
    for hero in profiles["heroes"].values():
        hero_id = hero["hero_id"]
        if type(hero_id) is not int or hero_id <= 0 or hero_id in hero_ids:
            raise ValueError("Invalid or duplicate profile hero identity")
        hero_ids.add(hero_id)
        for ability in hero["abilities"]:
            if ability["ability"] in owners:
                raise ValueError("Ambiguous profile ability ownership")
            owners[ability["ability"]] = hero_id
            for fact in ability["facts"]:
                if fact["subject"] != ability["ability"]:
                    raise ValueError("Profile fact placed under wrong ability")
                profile_ids.append(fact["review_id"])
    for subject, facts in profiles["other_subjects"].items():
        for fact in facts:
            if fact["subject"] != subject:
                raise ValueError("Other profile fact placed under wrong subject")
            profile_ids.append(fact["review_id"])
    if len(profile_ids) != len(set(profile_ids)) or set(profile_ids) != after.keys():
        raise ValueError("Profiles must cover every admission row exactly once")
    graph = output["counter_graph"]
    graph_rules = {}
    for rule in graph["rules"]:
        if rule["id"] in graph_rules:
            raise ValueError("Duplicate graph rule identity")
        graph_rules[rule["id"]] = rule
        for side in ("sources", "targets"):
            subjects = set()
            for node in rule[side]:
                if node["subject"] in subjects:
                    raise ValueError("Duplicate graph node")
                subjects.add(node["subject"])
                if node.get("kind") == "ability":
                    owner = owners.get(node["subject"])
                    if (
                        type(node.get("hero_id")) is not int
                        or node.get("hero_id") not in hero_ids
                        or (owner is not None and owner != node.get("hero_id"))
                    ):
                        raise ValueError("Graph node hero ownership mismatch")
                    if owner is None and node["candidate_usable"]:
                        raise ValueError("Unknown registry ability cannot be usable")
                    if owner is None:
                        if (
                            node["subject"] not in profiles["other_subjects"]
                            or not node["fact_ids"]
                        ):
                            raise ValueError("Unknown registry ability lacks baseline facts")
                        node["owner_registry_verified"] = False
                        node["legacy_declared_owner_id"] = node["hero_id"]
                if any(after[key]["subject"] != node["subject"] for key in node["fact_ids"]):
                    raise ValueError("Graph node fact identity mismatch")
                previous = node["candidate_usable"]
                affected = _guard(node, after)
                counts["affected_graph_nodes"] += affected
                counts["newly_blocked_graph_nodes"] += previous and not node["candidate_usable"]
    for edge in graph["item_to_hero"]:
        rule = graph_rules[edge["rule"]]
        source = [node for node in rule["sources"] if node["subject"] == edge["item"]]
        targets = [node for node in rule["targets"] if node["subject"] in edge["abilities"]]
        if len(source) != 1 or {node["subject"] for node in targets} != set(edge["abilities"]):
            raise ValueError("Graph edge references missing endpoints")
        nodes = source + targets
        if type(edge.get("hero_id")) is not int or any(
            node.get("hero_id") != edge.get("hero_id") for node in targets
        ):
            raise ValueError("Graph edge hero ownership mismatch")
        ids = sorted({key for node in nodes for key in node["fact_ids"]})
        if edge["fact_ids"] != ids:
            raise ValueError("Graph edge dependency closure differs from its nodes")
        previous = edge["candidate_usable"]
        affected = _guard(edge, after)
        if not all(node["candidate_usable"] for node in nodes) or rule.get("pending"):
            edge["candidate_usable"] = False
        if not edge["candidate_usable"]:
            edge["status"] = "pending"
        edge["pairs_verified"] = False
        counts["affected_graph_edges"] += affected
        counts["newly_blocked_graph_edges"] += previous and not edge["candidate_usable"]
    for trait in output["hero_traits"]["traits"].values():
        count_by_hero = {}
        for row in trait["counts"]:
            hero_id = row["hero_id"]
            if type(hero_id) is not int or hero_id not in hero_ids or hero_id in count_by_hero:
                raise ValueError("Trait count hero identity mismatch")
            count_by_hero[hero_id] = row
            if any(
                owners.get(after[key]["subject"]) not in (None, hero_id) for key in row["fact_ids"]
            ):
                raise ValueError("Trait count fact belongs to another hero")
            previous = row["candidate_usable"]
            affected = _guard(row, after)
            if affected or not row["candidate_usable"]:
                row["base"] = row["with_upgrades"] = None
            counts["affected_trait_counts"] += affected
            counts["newly_blocked_trait_counts"] += previous and not row["candidate_usable"]
        seen_heroes = set()
        for hero in trait["heroes"]:
            hero_id = hero["hero_id"]
            if type(hero_id) is not int or hero_id not in count_by_hero or hero_id in seen_heroes:
                raise ValueError("Trait detail hero identity mismatch")
            seen_heroes.add(hero_id)
            parent = count_by_hero[hero_id]
            affected_hero = False
            for ability in hero["abilities"]:
                if owners.get(ability["subject"]) != hero_id:
                    raise ValueError("Trait detail ability belongs to another hero")
                ids = [
                    key for key in parent["fact_ids"] if after[key]["subject"] == ability["subject"]
                ]
                ability.update(
                    fact_ids=ids,
                    candidate_usable=parent["candidate_usable"],
                    baseline_evidence_only=True,
                )
                affected = _guard(ability, after)
                affected_hero = affected_hero or affected
                counts["affected_trait_abilities"] += affected
            hero["candidate_usable"] = parent["candidate_usable"] and not affected_hero
            if not hero["candidate_usable"]:
                hero["baseline_ability_count"] = hero["ability_count"]
                hero["ability_count"] = None
    # No evidence in this revision changes the pre-existing save or movement inventory.
    for name in ("save_means", "mobility"):
        if output[name] != assets[name]:
            raise ValueError("Unexpected save/mobility change needs a separate verified projection")
    effects = defaultdict(list)
    for row in after.values():
        if not row["candidate_usable"]:
            continue
        engineering = row.get("engineering_admission", {})
        effect = engineering.get("effect_identity") or "fact:" + row["review_id"]
        effects[(row["subject"], effect)].append(row)
    output["capabilities"] = {
        "groups": [
            {
                "subject": subject,
                "effect_identity": identity,
                "mechanisms": sorted({row["mechanism"] for row in rows}),
                "facts": deepcopy(rows),
                "event_count_inferred": False,
                "conditions_evaluated": False,
                "interaction_outcomes_verified": False,
            }
            for (subject, identity), rows in sorted(effects.items())
        ],
        "limits": "Effect grouping prevents duplicate labels; it does not count executed events.",
    }
    for name, payload in output.items():
        if "source_refs" in payload:
            payload["baseline_source_refs"] = payload.pop("source_refs")
        payload.update(
            schema=f"mechanics-evidence-{name.replace('_', '-')}/1",
            policy=POLICY,
            patch=exact_patch,
            patch_verified=False,
            status="candidate",
            formal_use_allowed=False,
            training_allowed=False,
            action_review_allowed=False,
            source_refs=deepcopy(source_refs),
            source_integrity_checked_here=False,
        )
    output["summary"] = {
        **dict(counts),
        "fact_rows": len(after),
        "candidate_usable_rows": sum(row["candidate_usable"] for row in after.values()),
        "capability_groups": len(effects),
        "newly_usable_graph_edges": 0,
        "save_and_mobility_content_unchanged": True,
        "baseline_topology_preserved": True,
        "formal_use_allowed": False,
        "training_allowed": False,
        "action_review_allowed": False,
    }
    return deepcopy(output)
