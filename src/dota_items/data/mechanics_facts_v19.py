"""MK-T6b reviewed facts, version 19: the rows of frozen v18, evaluated with rules v11 (U113)."""

from dota_items.data.mechanics_rules_v11 import not_computed

SCHEMA = "mechanics-facts/19"
VERSION = "mechanics-reviewed/19"
VOCABULARY = "knowledge/mechanics/vocabulary-v13.json"


def build_reviewed(base, inputs):
    """Same rows and condition exceptions as v18; only the schema and the version move on."""
    if inputs.get("condition_exceptions"):
        raise ValueError("v19 adds no condition exceptions; put new ones in a later version")
    return {**base, "schema": SCHEMA, "extractor_version": VERSION, "vocabulary": VOCABULARY}


def add_not_computed(evaluation, rules):
    """Carry each rule's declared not-computed fields and reason onto its evaluation entry."""
    by_id = {rule["id"]: rule for rule in rules}
    entries = []
    for entry in evaluation["rules"]:
        rule = by_id[entry["id"]]
        if entry["not_evaluated"] != not_computed(rule):
            raise ValueError(f"{rule['id']}: skipped fields differ from the declared ones")
        declared = rule.get("not_computed")
        entries.append({**entry, "not_computed": declared} if declared else entry)
    return {**evaluation, "rules": entries}
