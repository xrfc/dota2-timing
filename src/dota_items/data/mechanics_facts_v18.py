"""MK-T5 reviewed facts, version 18: the rows of frozen v17, evaluated with rules v10 (U106)."""

SCHEMA = "mechanics-facts/18"
VERSION = "mechanics-reviewed/18"
VOCABULARY = "knowledge/mechanics/vocabulary-v13.json"


def build_reviewed(base, inputs):
    """Same rows and condition exceptions as v17; only the schema and the version move on."""
    extra = inputs.get("condition_exceptions", [])
    if extra:
        raise ValueError("v18 adds no condition exceptions; put new ones in a later version")
    return {**base, "schema": SCHEMA, "extractor_version": VERSION, "vocabulary": VOCABULARY}
