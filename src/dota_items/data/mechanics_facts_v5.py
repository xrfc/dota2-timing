"""MK-T3 reviewed facts, version 5: v4 logic with vocabulary v5 and later reviews."""

from dota_items.data import mechanics_facts_v4 as v4

SCHEMA = "mechanics-facts/5"
VERSION = "mechanics-reviewed/5"
VOCABULARY = "knowledge/mechanics/vocabulary-v5.json"


def build_reviewed(sources):
    """Same precedence as v4; only the identifying fields change."""
    return {
        **v4.build_reviewed(sources),
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "vocabulary": VOCABULARY,
    }
