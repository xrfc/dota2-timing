"""Rules v11 (MK-T6b, U92, U113): every rule field is either computed or declared not computed.

Before v11, `pairs`, `target_exempt_mechanisms` and `parameters` were skipped silently and
only listed in `not_evaluated`. Now a rule must say so in `not_computed`, with the fields,
the reason and the user decision behind it. A field the engine does not know, or a
recorded-only field without that declaration, raises instead of being skipped.
"""

from dota_items.data.mechanics_interactions import load_rules

SCHEMA = "mechanics-rules/2"
TEXT_FIELDS = {"id", "zh", "relation", "decision", "note", "pending", "not_computed"}
COMPUTED_FIELDS = {
    "source_mechanisms",
    "source_subjects",
    "source_note_kinds",
    "target_mechanisms",
    "target_subjects",
    "target_enum",
    "target_game_field",
    "target_exclude",
    "target_exclude_note_kinds",
    "target_heroes",
}
RECORDED_ONLY_FIELDS = {"pairs", "target_exempt_mechanisms", "parameters"}


def check_rule_fields(rule):
    """Raise unless every field of one rule is computed, text, or declared not computed."""
    rule_id = rule.get("id", "?")
    unknown = set(rule) - TEXT_FIELDS - COMPUTED_FIELDS - RECORDED_ONLY_FIELDS
    if unknown:
        raise ValueError(f"{rule_id}: fields the rule engine does not know: {sorted(unknown)}")
    recorded = set(rule) & RECORDED_ONLY_FIELDS
    declared = rule.get("not_computed")
    if declared is None:
        if recorded:
            raise ValueError(
                f"{rule_id}: {sorted(recorded)} are not computed; declare them in not_computed"
            )
        return
    if (
        not isinstance(declared, dict)
        or not declared.get("reason_zh")
        or not declared.get("decision")
    ):
        raise ValueError(f"{rule_id}: not_computed needs fields, reason_zh and decision")
    fields = declared.get("fields")
    if not isinstance(fields, list) or set(fields) != recorded:
        raise ValueError(
            f"{rule_id}: not_computed fields {fields} must equal the recorded-only fields "
            f"{sorted(recorded)}"
        )


def load_rules_v11(doc, terms):
    """Validate rules v11 (field check first) and return the rules."""
    if doc.get("schema") != SCHEMA:
        raise ValueError(f"Rules v11 need schema {SCHEMA}")
    for rule in doc["rules"]:
        check_rule_fields(rule)
    return load_rules({**doc, "schema": "mechanics-rules/1"}, terms)


def not_computed(rule):
    """The declared not-computed fields of a rule, empty when everything is computed."""
    return list(rule.get("not_computed", {}).get("fields", []))
