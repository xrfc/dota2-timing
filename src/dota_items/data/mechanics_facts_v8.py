"""MK-T3 reviewed facts, version 8: v7 logic with vocabulary v8 and aoe_damage."""

from dota_items.data import mechanics_facts_v7 as v7

SCHEMA = "mechanics-facts/8"
VERSION = "mechanics-reviewed/8"
VOCABULARY = "knowledge/mechanics/vocabulary-v8.json"


def build_reviewed(sources):
    """Same precedence as v7; only the identifying fields change."""
    return {
        **v7.build_reviewed(sources),
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "vocabulary": VOCABULARY,
    }
