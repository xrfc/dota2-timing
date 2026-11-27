"""Pure 7.42 candidate projections with row-level evidence admission.

Policy ``mechanics-action-assets/7.42-v1`` retains prior user decisions, current
two-AI evidence and mechanically copied registry fields as distinct categories.
It never promotes a partial facts package to formal knowledge. Callers verify all
source bytes before calling and again before publishing these diagnostic payloads.
"""

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from copy import deepcopy

from dota_items.data.mechanics_conditions import annotate_graph_conditions
from dota_items.data.mechanics_graph import build_graph, node_index
from dota_items.data.mechanics_graph_v2 import annotate_graph
from dota_items.data.mechanics_rules_v8 import mark_conditional_edges
from dota_items.data.mechanics_traits_v4 import build_traits_v4

POLICY = "mechanics-action-assets/7.42-v1"
BASE_FACTS_SHA256 = "391aa4268b6be3714984b48d401c3c966728a750aba0172ab209ca761ce18f95"
SOURCE_KEYS = frozenset(
    {
        "facts",
        "rules",
        "vocabulary",
        "reviews",
        "registry",
        "overlay",
        "patch_decisions",
        "patch_impact",
        "save_decisions",
        "haste_policy",
        "evaluation",
        "item_names",
        "retired_items",
        "extra_abilities",
    }
)
SAVE_MECHANISMS = {
    "self_mobility": "A",
    "invisibility": "A",
    "invulnerable_untargetable": "A",
    "cyclone_banish": "A",
    "debuff_immunity": "A",
    "death_prevention": "A",
    "ethereal": "A",
    "applies_strong_dispel": "A",
    "haste": "B-a",
    "applies_basic_dispel": "B-b",
    "illusions": "B-c",
    "spell_block": "B-e",
}
# U121/U131 selection policy, not an assertion that these abilities still have haste.
# Every actual selected fact must independently pass the 7.42 row admission below.
HASTE_ABILITIES = frozenset(
    {
        "mirana_leap",
        "phantom_lancer_phantom_edge",
        "windrunner_windrun",
        "windrunner_tailwind",
        "slardar_sprint",
        "rattletrap_jetpack",
        "spectre_spectral_dagger",
        "spirit_breaker_bulldoze",
        "tusk_drinking_buddies",
        "legion_commander_press_the_attack",
        "techies_reactive_tazer",
        "grimstroke_spirit_walk",
        "hoodwink_decoy",
        "ringmaster_the_box",
        "leshrac_greater_lightning_storm",
        "dark_seer_surge",
    }
)
ACTIVE_HASTE_ITEMS = frozenset(
    {
        "ancient_janggo",
        "boots_of_bearing",
        "crellas_crozier",
        "disperser",
        "glimmer_cape",
        "invis_sword",
        "mask_of_madness",
        "phase_boots",
        "silver_edge",
        "solar_crest",
        "swift_blink",
    }
)
# Only the exact operations actually authorized in U182/U183/U187/U188 clear a ruling.
# (basis, subject, mechanism, condition context, decision, overlay operation)
RULINGS = {
    "48a7f0b307b18016e002": (
        "user:U182",
        "sandking_epicenter",
        "aoe_damage",
        "scepter_upgrade",
        "reject",
        "decision_change",
    ),
    "799443581e85b1792948": (
        "user:U182",
        "dazzle_innate_weave",
        "healing",
        "shard_upgrade",
        "reject",
        "decision_change",
    ),
    "audit:death_prophet_spirit_siphon:lifesteal:base": (
        "user:U187",
        "death_prophet_spirit_siphon",
        "lifesteal",
        "base",
        "reject",
        "decision_change",
    ),
    "62613f1350de1228dd41": (
        "user:U183",
        "troll_warlord_battle_trance",
        "slow_resistance",
        "base",
        "reject",
        "decision_change",
    ),
    "7.42:c079": (
        "user:U183",
        "troll_warlord_battle_trance",
        "status_resistance",
        "base",
        "accept",
        "add_row",
    ),
    "7.42:c108": (
        "user:U188",
        "undying_bite",
        "self_mobility",
        "shard_upgrade",
        "accept",
        "add_row",
    ),
}
# U182 explicitly retained these two unchanged accepted claims. A retention needs
# no overlay mutation; the pinned decision record supplies the new patch approval.
RETENTION_RULINGS = {
    "7c2911cf7844f3051597": ("pugna_life_drain", "channeled", "user:U182"),
    "fe8476a622f929db996e": ("death_prophet_witchcraft", "haste", "user:U182"),
}
GRANT_CORRECTIONS = {
    "1ded141b4ca97ab1b964": "applies_basic_dispel",
    "audit:meepo_petrify:healing:shard": "healing",
    "4d75fdf84cc7416548d4": "invulnerable_untargetable",
}
PENDING_SELECTORS = {
    ("dazzle_innate_weave", "break_sensitive"): "A1_partial_break_scope",
    ("windrunner_tailwind", "break_sensitive"): "A1_partial_break_scope",
    ("nyx_assassin_burrow", "mana_gain"): "A8.2_burrow_mana",
    ("meepo_divided_we_stand", "damage_block"): "A8.3_shared_damage",
    ("meepo_fling_release", "damage_block"): "A8.3_shared_damage",
    ("meepo_fling_release", "grant_vision"): "A8.5_throw_vision",
    ("kez_falcon_rush", "terrain_walk"): "A8.6_terrain_traversal",
    **{
        (subject, "break_sensitive"): "U47_break_field_conflict"
        for subject in (
            "centaur_horsepower",
            "keeper_of_the_light_bright_speed",
            "morphling_ebb_and_flow",
            "terrorblade_dark_unity",
            "tusk_bitter_chill",
            "wisp_equilibrium",
        )
    },
}
PENDING_TOPICS = (
    "A1_global_rules_and_vocabulary",
    "A2_changed_behavior",
    "A4_prior_user_rulings_changed",
    "A6_new_ability_classification",
    "A8.2_burrow_mana",
    "A8.3_shared_damage",
    "A8.5_throw_vision",
    "A8.6_terrain_traversal",
    "U47_break_field_conflict",
    "A1_partial_break_scope",
    "item_fields_break_fields_and_numeric_upgrades_not_fully_rebuilt",
    "counter_graph_pairs_traits_and_legacy_catalog_policy_not_patch_certified",
)
PENDING_RULES = {
    "R06": "A1_true_sight_exception",
    "R18": "A1_leash",
    "R20": "A1_illusion_item_efficacy",
}
DISTANCE = re.compile(r"range|distance|dist|leap|jump|blink|hop|charge", re.IGNORECASE)
NOT_DISTANCE = re.compile(
    r"speed|duration|time|height|attack|radius|bonus|pct|percent|threshold", re.IGNORECASE
)


def _indexed(rows, key, name):
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"Invalid {name} rows")
    result = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value or value in result:
            raise ValueError(f"Missing or duplicate {name} identity")
        result[value] = row
    return result


def required_pending_review_ids(facts_doc, review_doc):
    """Known unresolved rows, including rows later clearable by an exact applied ruling."""
    facts = _indexed(facts_doc.get("rows"), "review_id", "facts")
    reviews = _indexed(review_doc.get("rows"), "review_id", "reviews")
    return sorted(
        key
        for key, row in facts.items()
        if (row.get("subject"), row.get("mechanism")) in PENDING_SELECTORS
        or reviews.get(key, {}).get("lane", "").startswith("user_")
    )


def _condition(value):
    if (
        not isinstance(value, dict)
        or value.get("context")
        not in (
            "base",
            "item",
            "scepter_upgrade",
            "shard_upgrade",
        )
        or any(type(value.get(key)) is not bool for key in ("requires_scepter", "requires_shard"))
    ):
        raise ValueError("Invalid fact condition")
    return deepcopy(value)


def _applied_ruling(row, operations):
    expected = RULINGS.get(row["review_id"])
    if expected is None:
        return False
    basis, subject, mechanism, context, decision, operation = expected
    if (
        (
            row["basis"],
            row["subject"],
            row["mechanism"],
            row["condition"]["context"],
            row["decision"],
        )
        != (basis, subject, mechanism, context, decision)
        or row["condition"]["requires_scepter"] != (context == "scepter_upgrade")
        or row["condition"]["requires_shard"] != (context == "shard_upgrade")
    ):
        return False
    for op in operations.get(row["review_id"], []):
        if op.get("op") != operation or op.get("basis") != basis:
            continue
        if operation == "add_row":
            if all(
                op.get(key) == row[key] for key in ("subject", "mechanism", "condition", "decision")
            ):
                return True
        elif op.get("to") == decision and op.get("from") != decision:
            if all(op.get(key, row[key]) == row[key] for key in ("subject", "mechanism")):
                return True
    return False


def _two_ai_operation(row, operations):
    for op in operations.get(row["review_id"], []):
        if op.get("basis") != "two_ai" or row["basis"] != "two_ai":
            continue
        if op.get("op") == "add_row" and op.get("claude") == op.get("codex") == "accept":
            if all(
                op.get(key) == row[key] for key in ("subject", "mechanism", "condition", "decision")
            ):
                return True
        if op.get("op") == "condition_change" and op.get("to") == row["condition"]:
            if all(op.get(key) == row[key] for key in ("subject", "mechanism")):
                return True
    return False


def _retained_ruling(row):
    ruling = RETENTION_RULINGS.get(row["review_id"])
    return bool(
        ruling
        and (row["subject"], row["mechanism"]) == ruling[:2]
        and row["decision"] == "accept"
        and row["condition"]
        == {"context": "base", "requires_scepter": False, "requires_shard": False}
    )


def _grant_correction(row, operations, abilities):
    ability = abilities.get("meepo_petrify", {})
    return (
        row["review_id"] in GRANT_CORRECTIONS
        and row["subject"] == "meepo_petrify"
        and row["mechanism"] == GRANT_CORRECTIONS[row["review_id"]]
        and row["decision"] == "accept"
        and row["condition"]
        == {"context": "scepter_upgrade", "requires_scepter": True, "requires_shard": False}
        and ability.get("granted_by_scepter") is True
        and ability.get("granted_by_shard") is False
        and _two_ai_operation(row, operations)
    )


def _admit(row, review, operations, pending, field_evidence, equivalent):
    retained = _retained_ruling(row)
    approved = _applied_ruling(row, operations) or retained
    if retained:
        status, usable = "user_retention_ruling_applied", True
    elif approved:
        status, usable = "user_ruling_applied", row["decision"] == "accept"
    elif row["review_id"] in pending:
        status, usable = "pending_ruling", False
    elif row["decision"] != "accept":
        status, usable = "excluded_fact", False
    elif _two_ai_operation(row, operations):
        status, usable = "two_ai_overlay", True
    elif review.get("lane") == "keep_two_ai" and review.get("codex") == "holds":
        status, usable = "two_ai_unchanged", True
    elif review.get("lane") == "keep_user":
        status, usable = "prior_user_ruling_retained", True
    elif row["review_id"] in field_evidence:
        status, usable = "current_fields_verified", True
    elif row["review_id"] in equivalent:
        status, usable = "source_equivalent", True
    elif review.get("lane") == "field_rebuild":
        status, usable = "fact_field_rebuild_unproven", False
    else:
        status, usable = "unreviewed_or_uncertain_for_patch", False
    return {
        **{
            key: deepcopy(row[key])
            for key in ("review_id", "subject", "mechanism", "basis", "decision", "condition")
        },
        "patch_evidence_status": status,
        "candidate_usable": usable,
        "user_approved_for_patch": approved,
        "applied_user_decision": (
            RETENTION_RULINGS[row["review_id"]][2]
            if retained
            else RULINGS[row["review_id"]][0]
            if approved
            else None
        ),
        "patch_approval_evidence": (
            "existing_user_retention_decision"
            if retained
            else "exact_user_overlay_operation"
            if approved
            else None
        ),
        "original_user_basis": row["basis"].startswith("user"),
        "original_field_basis": row["basis"].startswith("field"),
        "review_lane": review.get("lane"),
        "review_conclusion": review.get("codex"),
        "pending_topic": PENDING_SELECTORS.get((row["subject"], row["mechanism"])),
        "quotes": deepcopy(row.get("quotes", [])),
        "condition_notes": deepcopy(row.get("condition_notes", [])),
        "notes_zh": deepcopy(row.get("notes_zh", [])),
        "break_conditions_en": deepcopy(row.get("break_conditions_en", [])),
        "current_field_evidence": deepcopy(field_evidence.get(row["review_id"])),
        "source_equivalence_evidence": deepcopy(equivalent.get(row["review_id"])),
    }


def _numeric(values):
    if not isinstance(values, list) or any(
        type(value) not in (int, float) or not math.isfinite(value) for value in values
    ):
        raise ValueError("Invalid registry numeric values")
    return list(values)


def _source_refs(refs, *, with_equivalence=False):
    expected = SOURCE_KEYS | ({"equivalence"} if with_equivalence else set())
    if not isinstance(refs, dict) or set(refs) != expected:
        raise ValueError("Incomplete action-asset source references")
    for ref in refs.values():
        if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
            raise ValueError("Invalid source reference")
        if not isinstance(ref["path"], str) or not ref["path"]:
            raise ValueError("Missing source path")
        if (
            not isinstance(ref["sha256"], str)
            or re.fullmatch(r"[a-f0-9]{64}", ref["sha256"]) is None
        ):
            raise ValueError("Invalid source SHA-256")


def _canonical_sha(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _equivalence_rows(document, facts_doc, registry_abilities):
    if document is None:
        return {}, {}
    base, candidate = document.get("base", {}), document.get("candidate", {})
    base_path = base.get("path")
    registered_base = "knowledge/mechanics/extractions/v26/facts-v26.json"
    base_path_matches = (
        isinstance(base_path, str)
        and ".." not in base_path.split("/")
        and (base_path == registered_base or base_path.endswith("/" + registered_base))
    )
    if (
        document.get("schema") != "mechanics-source-equivalence/1"
        or document.get("patch") != "7.42"
        or document.get("baseline_patch") != "7.41f"
        or base.get("schema") != "mechanics-facts/26"
        or not base_path_matches
        or base.get("sha256") != BASE_FACTS_SHA256
        or not _sha(base.get("document_sha256"))
        or candidate.get("schema") != facts_doc["schema"]
        or candidate.get("document_sha256") != _canonical_sha(facts_doc)
    ):
        raise ValueError("Source equivalence patch/base/candidate identity mismatch")
    rows = _indexed(document.get("rows"), "review_id", "source equivalence")
    facts = {row["review_id"]: row for row in facts_doc["rows"]}
    proven, field_rows = {}, {}
    for key, row in rows.items():
        fact = facts.get(key)
        if (
            fact is None
            or any(
                row.get(name) != fact[name]
                for name in ("subject", "mechanism", "decision", "condition", "basis")
            )
            or row.get("fact_sha256") != _canonical_sha(fact)
        ):
            raise ValueError("Source equivalence row identity differs from current fact")
        unchanged_fact = row.get("base_fact_sha256") == row["fact_sha256"]
        raw, script = row.get("raw_source_refs", []), row.get("script_source_refs", [])
        for refs, digest in ((raw, "subject_sha256"), (script, "block_sha256")):
            if not isinstance(refs, list) or any(
                not isinstance(ref, dict)
                or ref.get("patch") not in ("7.41f", "7.42")
                or not isinstance(ref.get("path"), str)
                or not ref["path"]
                or not _sha(ref.get("sha256"))
                or not _sha(ref.get(digest))
                for ref in refs
            ):
                raise ValueError("Invalid source equivalence evidence reference")
        if row.get("source_equivalent") is True:
            if not unchanged_fact or row.get("status") != "source_identical":
                raise ValueError("Equivalent claim changed its original fact")
            if any(ref.get("language") not in ("english", "schinese") for ref in raw):
                raise ValueError("Invalid equivalent raw-source language")
            languages = (
                {"english", "schinese"} if fact["subject"] in registry_abilities else {"english"}
            )
            for patch in ("7.41f", "7.42"):
                found = [ref["language"] for ref in raw if ref["patch"] == patch]
                if set(found) != languages or len(found) != len(languages):
                    raise ValueError("Incomplete equivalent raw-source language inventory")
            for refs, digest in ((raw, "subject_sha256"), (script, "block_sha256")):
                old = Counter(
                    (ref.get("language"), ref[digest]) for ref in refs if ref["patch"] == "7.41f"
                )
                new = Counter(
                    (ref.get("language"), ref[digest]) for ref in refs if ref["patch"] == "7.42"
                )
                if not old or old != new:
                    raise ValueError("Incomplete or unequal source equivalence proof")
            proven[key] = {
                "fact_sha256": row["fact_sha256"],
                "base_fact_sha256": row["base_fact_sha256"],
                "raw_source_refs": deepcopy(raw),
                "script_source_refs": deepcopy(script),
                "new_user_approval": False,
            }
        field = row.get("current_script_fields", {}).get("IsBreakable", {})
        if (
            unchanged_fact
            and field.get("value") == "1"
            and field.get("unambiguous") is True
            and field.get("occurrences") == 1
        ):
            refs = field.get("source_refs")
            if (
                not isinstance(refs, list)
                or len(refs) != 1
                or any(
                    not isinstance(ref, dict)
                    or ref.get("patch") != "7.42"
                    or not isinstance(ref.get("path"), str)
                    or not ref["path"]
                    or not _sha(ref.get("sha256"))
                    or not _sha(ref.get("block_sha256"))
                    for ref in refs
                )
            ):
                raise ValueError("Invalid current IsBreakable evidence")
            field_rows[key] = deepcopy(field)
    return proven, field_rows


def _current_field_evidence(facts, reviews, registry, break_fields, source_refs):
    fields = {}
    for hi, hero in enumerate(registry["heroes"]):
        for ai, ability in enumerate(hero["abilities"]):
            fields[ability["name"]] = (ability, f"/heroes/{hi}/abilities/{ai}")
    output = {}
    for key, fact in facts.items():
        if fact["decision"] != "accept" or fact["subject"] not in fields:
            continue
        mechanism = fact["mechanism"]
        if mechanism == "break_sensitive" and key in break_fields:
            output[key] = {"method": "existing_accept_and_current_IsBreakable", **break_fields[key]}
        if reviews.get(key, {}).get("lane") != "field_rebuild":
            continue
        ability, pointer = fields[fact["subject"]]
        raw = ability.get("raw_mechanics", {})
        behavior = raw.get("behavior")
        if isinstance(behavior, str) and re.fullmatch(r"[0-9]+", behavior):
            behavior = int(behavior)
        if type(behavior) is not int or behavior < 0:
            continue
        matched = (
            mechanism == "unit_target_spell"
            and bool(behavior & 8)
            and type(raw.get("target_team")) is int
            and raw["target_team"] in (2, 3)
        ) or (mechanism == "channeled" and bool(behavior & 128))
        if matched:
            output[key] = {
                "method": "existing_accept_and_current_behavior_fields",
                "registry_ref": deepcopy(source_refs["registry"]),
                "pointer": pointer + "/raw_mechanics",
                "raw_fields": deepcopy(raw),
                "preserved_condition": deepcopy(fact["condition"]),
                "rule": "behavior & 8; target_team in (2,3)"
                if mechanism == "unit_target_spell"
                else "behavior & 128",
            }
    return output


def _save_filter(fact, ability):
    if fact["subject"] == "smoke_of_deceit":
        return "U136_smoke_is_not_a_save"
    if ability is not None:
        raw = ability.get("raw_mechanics", {})
        behavior = raw.get("behavior")
        if isinstance(behavior, str) and re.fullmatch(r"[0-9]+", behavior):
            behavior = int(behavior)
        if type(behavior) is not int or type(raw.get("target_team")) is not int:
            return "missing_current_targeting_fields"
        if behavior & 2 or raw["target_team"] == 2:
            return "passive_or_enemy_only"
    elif fact["condition"]["context"] != "item":
        return "subject_not_in_patch_registry_or_item_context"
    if fact["mechanism"] == "haste":
        allowed = HASTE_ABILITIES if ability is not None else ACTIVE_HASTE_ITEMS
        if fact["subject"] not in allowed:
            return "outside_U121_U131_haste_selection"
    return None


def _unconfirm(value):
    """Legacy helper confirmation is about the old basis, not 7.42 approval."""
    if isinstance(value, dict):
        return {
            key: False if key == "confirmed" else _unconfirm(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_unconfirm(item) for item in value]
    return value


def _derive_graph_traits(
    facts,
    rules,
    evaluation,
    mapping,
    heroes,
    abilities,
    admitted,
    item_names_doc,
    retired_items_doc,
    extra_abilities_doc,
):
    extra = {entry["hero_id"]: entry["abilities"] for entry in extra_abilities_doc["heroes"]}
    hero_inputs = [
        {**hero, "abilities": [*hero["abilities"], *extra.get(hero["hero_id"], [])]}
        for hero in heroes
    ]
    names = {
        row["name"].removeprefix("item_"): row["name_loc"]
        for row in item_names_doc["result"]["data"]["itemabilities"]
        if row.get("name_loc")
    }
    updated_rules = [
        {**rule, **({"pending": PENDING_RULES[rule["id"]]} if rule["id"] in PENDING_RULES else {})}
        for rule in rules
    ]
    graph = annotate_graph_conditions(
        mark_conditional_edges(
            annotate_graph(
                build_graph(
                    updated_rules,
                    evaluation,
                    facts,
                    node_index(hero_inputs, names, retired_items_doc["status"]),
                ),
                updated_rules,
                facts,
            ),
            updated_rules,
        ),
        evaluation,
    )
    graph = _unconfirm(graph)
    by_subject = defaultdict(list)
    for fact in admitted.values():
        if fact["decision"] == "accept":
            by_subject[fact["subject"]].append(fact)
    rules_by_id = {rule["id"]: rule for rule in updated_rules}
    for rule in graph["rules"]:
        definition = rules_by_id[rule["id"]]
        for side in ("sources", "targets"):
            mechanisms = definition.get(f"{side[:-1]}_mechanisms", [])
            for node in rule[side]:
                rows = [
                    row for row in by_subject[node["subject"]] if row["mechanism"] in mechanisms
                ]
                field_only = bool(node["evidence"]) and all(
                    evidence["via"].startswith("enum:") for evidence in node["evidence"]
                )
                fields_match = field_only and node["subject"] in abilities
                for evidence in node["evidence"] if field_only else []:
                    field, expected = evidence["via"].removeprefix("enum:").split("=", 1)
                    fields_match = fields_match and (
                        abilities[node["subject"]].get("raw_mechanics", {}).get(field)
                        == int(expected)
                    )
                listed = any(
                    evidence["via"] == "rule_list" or evidence["via"].startswith("note:")
                    for evidence in node["evidence"]
                )
                usable = (
                    bool(rows) and all(row["candidate_usable"] for row in rows) and not listed
                ) or fields_match
                if node["kind"] == "ability" and node["subject"] not in abilities:
                    usable = False
                node.update(
                    candidate_usable=usable,
                    fact_ids=[row["review_id"] for row in rows],
                    blocked_fact_ids=[
                        row["review_id"] for row in rows if not row["candidate_usable"]
                    ],
                    mechanical_field_evidence=fields_match,
                    user_approved_for_patch=bool(rows)
                    and all(row["user_approved_for_patch"] for row in rows),
                    legacy_catalog_policy_verified_for_patch=False,
                )
    graph_rules = {rule["id"]: rule for rule in graph["rules"]}
    for edge in graph["item_to_hero"]:
        rule = graph_rules[edge["rule"]]
        source = next(node for node in rule["sources"] if node["subject"] == edge["item"])
        targets = [node for node in rule["targets"] if node["subject"] in edge["abilities"]]
        usable = (
            not rule.get("pending")
            and source["candidate_usable"]
            and all(node["candidate_usable"] for node in targets)
        )
        edge.update(
            status="candidate" if usable else "pending",
            candidate_usable=usable,
            fact_ids=sorted({key for node in [source, *targets] for key in node["fact_ids"]}),
            blocked_fact_ids=sorted(
                {key for node in [source, *targets] for key in node["blocked_fact_ids"]}
            ),
            pairs_verified=False,
        )
    traits = _unconfirm(build_traits_v4(mapping, facts, hero_inputs, updated_rules))
    hero_subjects = {
        hero["hero_id"]: {a["name"] for a in hero["abilities"]} for hero in hero_inputs
    }
    for trait_id, trait in traits["traits"].items():
        spec = mapping["traits"][trait_id]
        mechanisms = set(spec.get("mechanisms", [])) | set(spec.get("only_subjects", {}))
        for count in trait["counts"]:
            rows = [
                fact
                for name in hero_subjects[count["hero_id"]]
                for fact in by_subject[name]
                if fact["mechanism"] in mechanisms
                and (
                    fact["mechanism"] not in spec.get("only_subjects", {})
                    or name in spec["only_subjects"][fact["mechanism"]]
                )
            ]
            blocked = [row["review_id"] for row in rows if not row["candidate_usable"]]
            unknown_subjects = sorted(
                {row["subject"] for row in rows if row["subject"] not in abilities}
            )
            inherited_policy = bool(spec.get("from_rule") or spec.get("from_heroes"))
            count.update(
                candidate_base=count["base"],
                candidate_with_upgrades=count["with_upgrades"],
                fact_ids=sorted(row["review_id"] for row in rows),
                blocked_fact_ids=sorted(blocked),
                unknown_registry_subjects=unknown_subjects,
                candidate_usable=not blocked and not inherited_policy and not unknown_subjects,
                absence_verified=False,
                inherited_named_policy_unverified=inherited_policy,
            )
            if blocked or inherited_policy or unknown_subjects:
                count["base"] = count["with_upgrades"] = None
    graph["schema"] = "candidate-counter-graph/1"
    graph["pairs_verified"] = False
    graph["item_status_and_extra_ability_catalog_patch_verified"] = False
    traits["schema"] = "candidate-hero-traits/1"
    traits["counts_are_candidate_evidence_not_complete_patch_inventory"] = True
    return graph, traits


def build_action_assets(
    facts_doc,
    rules_doc,
    vocabulary_doc,
    review_doc,
    patch_registry,
    *,
    exact_patch,
    source_refs,
    pending_review_ids,
    overlay_doc,
    evaluation_doc,
    trait_mapping_doc,
    item_names_doc,
    retired_items_doc,
    extra_abilities_doc,
    source_equivalence_doc=None,
):
    """Return six candidate payloads; inputs remain unchanged.

    References are syntax checked here, not read or verified. The outer publication
    layer must verify the pinned candidate, all other references and consumer code.
    This 7.42 policy deliberately rejects every other patch, including 7.42a.
    """
    if exact_patch != "7.42" or patch_registry.get("target_patch") != exact_patch:
        raise ValueError("Action-asset policy requires exact patch 7.42")
    if (
        facts_doc.get("schema") != "mechanics-facts/27"
        or facts_doc.get("patch_verified") is not False
    ):
        raise ValueError("Expected unverified version-27 candidate facts")
    if (
        overlay_doc.get("schema") != "mechanics-overlay-inputs/1"
        or overlay_doc.get("version") != 27
    ):
        raise ValueError("Expected version-27 overlay")
    if (
        review_doc.get("schema") != "mechanics-recheck-742/1"
        or rules_doc.get("schema") != "mechanics-rules/1"
    ):
        raise ValueError("Invalid review/rule identity")
    _source_refs(source_refs, with_equivalence=source_equivalence_doc is not None)
    facts = _indexed(facts_doc.get("rows"), "review_id", "facts")
    reviews = _indexed(review_doc.get("rows"), "review_id", "reviews")
    rules = _indexed(rules_doc.get("rules"), "id", "rules")
    evaluated = _indexed(evaluation_doc.get("rules"), "id", "evaluated rules")
    if (
        set(evaluated) != set(rules)
        or evaluation_doc.get("schema") != "mechanics-rules-evaluation/3"
    ):
        raise ValueError("Rule evaluation inventory differs from definitions")
    vocabulary = _indexed(vocabulary_doc.get("mechanisms"), "id", "vocabulary")
    operations = defaultdict(list)
    for op in overlay_doc.get("operations", []):
        if not isinstance(op, dict):
            raise ValueError("Invalid overlay operation")
        if op.get("review_id"):
            operations[op["review_id"]].append(op)
    if not isinstance(pending_review_ids, (list, tuple, set, frozenset)) or any(
        not isinstance(key, str) for key in pending_review_ids
    ):
        raise ValueError("Invalid pending review IDs")
    pending = set(pending_review_ids)
    if pending - facts.keys():
        raise ValueError("Pending review ID absent from candidate facts")
    for row in facts.values():
        if (
            row.get("decision") not in ("accept", "reject")
            or row.get("mechanism") not in vocabulary
        ):
            raise ValueError("Invalid fact decision or mechanism")
        if not isinstance(row.get("basis"), str) or not isinstance(row.get("subject"), str):
            raise ValueError("Invalid fact basis or subject")
        _condition(row.get("condition"))
        review = reviews.get(row["review_id"])
        if review is not None and any(
            review.get(key) != row[key] for key in ("subject", "mechanism")
        ):
            raise ValueError("Review identity does not match candidate fact")
    registry_abilities = {
        ability["name"]: ability
        for hero in patch_registry.get("heroes", [])
        for ability in hero["abilities"]
    }
    cleared = {
        key
        for key, row in facts.items()
        if _applied_ruling(row, operations)
        or _retained_ruling(row)
        or _grant_correction(row, operations, registry_abilities)
    }
    unresolved = {
        key for key in required_pending_review_ids(facts_doc, review_doc) if key not in cleared
    }
    if not unresolved <= pending:
        raise ValueError("Known pending decisions cannot be omitted")
    equivalent, break_fields = _equivalence_rows(
        source_equivalence_doc, facts_doc, registry_abilities
    )
    field_evidence = _current_field_evidence(
        facts, reviews, patch_registry, break_fields, source_refs
    )
    # A complete unchanged source block does not by itself decode partial break scope.
    equivalent = {
        key: proof
        for key, proof in equivalent.items()
        if facts[key]["mechanism"] != "break_sensitive" or key in field_evidence
    }
    admitted = {
        key: _admit(
            row, reviews.get(key, {}), operations, pending - cleared, field_evidence, equivalent
        )
        for key, row in facts.items()
    }
    owners, abilities, profiles = {}, {}, {}
    for hero in patch_registry.get("heroes", []):
        npc = hero["npc_name"]
        if npc in profiles:
            raise ValueError("Duplicate hero registry identity")
        profiles[npc] = {"hero_id": hero["hero_id"], "name_zh": hero["name_zh"], "abilities": []}
        for ability in hero["abilities"]:
            name = ability["name"]
            if name in abilities:
                raise ValueError("Duplicate ability registry identity")
            owners[name], abilities[name] = npc, ability
    by_subject = defaultdict(list)
    for fact in admitted.values():
        by_subject[fact["subject"]].append(fact)
    for name, ability in abilities.items():
        profiles[owners[name]]["abilities"].append(
            {
                "ability": name,
                "name_zh": ability["name_zh"],
                "facts": by_subject[name],
                "registry_fields": {
                    "status": "source_fields_only",
                    "user_approved_for_patch": False,
                    "raw_mechanics": deepcopy(ability.get("raw_mechanics", {})),
                    "cooldowns": _numeric(ability.get("cooldowns", [])),
                    "cast_ranges": _numeric(ability.get("cast_ranges", [])),
                },
            }
        )
    means, blocked_saves, mobile_heroes, mobile_items, blocked_mobility = {}, [], {}, [], []
    for key, fact in admitted.items():
        if fact["decision"] != "accept":
            continue
        subject, mechanism = fact["subject"], fact["mechanism"]
        ability = abilities.get(subject)
        if mechanism in SAVE_MECHANISMS:
            reason = None if fact["candidate_usable"] else fact["patch_evidence_status"]
            reason = reason or _save_filter(fact, ability)
            if reason:
                blocked_saves.append(
                    {"review_id": key, "subject": subject, "mechanism": mechanism, "reason": reason}
                )
            else:
                name = subject if ability is not None else f"item_{subject}"
                entry = means.setdefault(
                    name,
                    {
                        "name": name,
                        "kind": "ability" if ability is not None else "item",
                        "facts": [],
                    },
                )
                entry["facts"].append(deepcopy(fact))
        if mechanism != "self_mobility":
            continue
        if not fact["candidate_usable"]:
            blocked_mobility.append(
                {"review_id": key, "subject": subject, "reason": fact["patch_evidence_status"]}
            )
        elif ability is not None:
            hero = mobile_heroes.setdefault(owners[subject], {"abilities": []})
            ranges = {
                value["name"]: _numeric(value["values_float"])
                for value in ability.get("special_values", [])
                if DISTANCE.search(value["name"])
                and not NOT_DISTANCE.search(value["name"])
                and value.get("values_float")
            }
            hero["abilities"].append(
                {
                    "ability": subject,
                    "name_zh": ability["name_zh"],
                    "fact": deepcopy(fact),
                    "cooldowns": _numeric(ability.get("cooldowns", [])),
                    "cast_ranges": _numeric(ability.get("cast_ranges", [])),
                    "distance_values": ranges,
                    "distance_interpretation_verified": False,
                }
            )
        elif fact["condition"]["context"] == "item":
            mobile_items.append({"item": subject, "fact": deepcopy(fact), "distance_values": None})
        else:
            blocked_mobility.append(
                {"review_id": key, "subject": subject, "reason": "subject_not_in_patch_registry"}
            )
    common = {
        "patch": exact_patch,
        "patch_verified": False,
        "status": "candidate",
        "policy": POLICY,
        "formal_use_allowed": False,
        "training_allowed": False,
        "source_integrity_checked_here": False,
        "source_refs": deepcopy(source_refs),
    }
    result = {
        "profiles": {
            **common,
            "schema": "mechanics-action-profiles/1",
            "heroes": profiles,
            "other_subjects": {
                name: rows for name, rows in by_subject.items() if name not in abilities
            },
            "rules": [
                {
                    "id": key,
                    "status": "pending"
                    if rule.get("pending") or key in PENDING_RULES
                    else "candidate",
                    "pending": rule.get("pending") or PENDING_RULES.get(key),
                    "pairs_verified": False,
                }
                for key, rule in rules.items()
            ],
            "full_counter_graph_and_traits_generated": True,
        },
        "save_means": {
            **common,
            "schema": "candidate-save-means/1",
            "means": means,
            "blocked": blocked_saves,
            "selection_policy": "U131/U136; U121 haste selection plus current-patch fact admission",
            "mechanism_groups": dict(SAVE_MECHANISMS),
            "conditions_must_be_checked_at_use": True,
        },
        "mobility": {
            **common,
            "schema": "candidate-hero-mobility/1",
            "heroes": mobile_heroes,
            "items": mobile_items,
            "blocked": blocked_mobility,
            "limits": (
                "Distance-like field names are copied evidence, not validated movement distances."
            ),
        },
        "admission": {
            **common,
            "schema": "mechanics-action-admission/1",
            "rows": list(admitted.values()),
            "counts": dict(Counter(row["patch_evidence_status"] for row in admitted.values())),
            "candidate_usable_rows": sum(row["candidate_usable"] for row in admitted.values()),
            "user_approved_for_patch_rows": sum(
                row["user_approved_for_patch"] for row in admitted.values()
            ),
            "pending_review_ids": sorted(pending - cleared),
            "resolved_pending_review_ids": sorted(pending & cleared),
            "pending_topics": list(PENDING_TOPICS),
        },
    }
    graph, traits = _derive_graph_traits(
        facts_doc,
        list(rules.values()),
        evaluation_doc,
        trait_mapping_doc,
        patch_registry["heroes"],
        abilities,
        admitted,
        item_names_doc,
        retired_items_doc,
        extra_abilities_doc,
    )
    result["counter_graph"] = {**graph, **common}
    result["hero_traits"] = {**traits, **common}
    # Prevent mutations in one returned artifact from altering another artifact or an input.
    return {name: deepcopy(payload) for name, payload in result.items()}
