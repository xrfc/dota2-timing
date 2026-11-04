"""MK-T5 reviewed facts, version 10: v9 plus the illusion rows round 4 skipped (U80)."""

from dota_items.data import mechanics_facts_v9 as v9

SCHEMA = "mechanics-facts/10"
VERSION = "mechanics-reviewed/10"


def build_reviewed(sources):
    """v9 result with the second batch of T5 corrections applied."""
    doc = v9.apply_corrections(
        v9.build_reviewed(sources), sources["t5_corrections_2"], sources["zh_names"]
    )
    status = sources["item_status"]
    rows = [
        {**row, "item_status": row["item_status"] or status.get(row["subject"])}
        for row in doc["rows"]
    ]
    return {**doc, "rows": rows, "schema": SCHEMA, "extractor_version": VERSION}
