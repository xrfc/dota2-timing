"""MK-T3 reviewed facts, version 7: v6 logic with vocabulary v7 and skill notes."""

from dota_items.data import mechanics_facts_v6 as v6

SCHEMA = "mechanics-facts/7"
VERSION = "mechanics-reviewed/7"
VOCABULARY = "knowledge/mechanics/vocabulary-v7.json"


def build_reviewed(sources):
    """Same precedence as v6; adds notes that are not mechanisms."""
    return {
        **v6.build_reviewed(sources),
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "vocabulary": VOCABULARY,
        "skill_notes": sources["skill_notes"],
    }
