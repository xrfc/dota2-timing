"""MK-T5 reviewed facts, version 17: frozen v16 plus condition exceptions (U102, U104).

A condition exception says an upgrade switches a mechanism off, such as Gush with Aghanim's
Scepter no longer being a unit-target spell. It is kept apart from rows, because a rejected
upgrade row only says the upgrade adds nothing.
"""

from dota_items.data import mechanics_facts_v13 as v13

SCHEMA = "mechanics-facts/17"
VERSION = "mechanics-reviewed/17"
VOCABULARY = v13.VOCABULARY


def build_reviewed(base, inputs):
    known = {
        (row["subject"], row["mechanism"]) for row in base["rows"] if row["decision"] == "accept"
    }
    for entry in inputs["condition_exceptions"]:
        if (entry["subject"], entry["mechanism"]) not in known:
            raise ValueError(f"Exception for a fact that is not accepted: {entry}")
    return {
        **base,
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "condition_exceptions": inputs["condition_exceptions"],
        "counts": {**base["counts"], "condition_exceptions": len(inputs["condition_exceptions"])},
    }
