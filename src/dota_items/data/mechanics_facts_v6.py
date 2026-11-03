"""MK-T3 reviewed facts, version 6: vocabulary v6 additions and the upgrade-number rule."""

from dota_items.data import mechanics_facts_v5 as v5

SCHEMA = "mechanics-facts/6"
VERSION = "mechanics-reviewed/6"
VOCABULARY = "knowledge/mechanics/vocabulary-v6.json"
UPGRADE_CONTEXTS = {"scepter_upgrade", "shard_upgrade"}
UPGRADE_NUMERIC = {"cooldown_reduction"}  # U65: upgrades changing only numbers are not mechanisms.


def _is_numeric_upgrade(row, numeric_ids):
    if row["review_id"] in numeric_ids:
        return True
    return row["mechanism"] in UPGRADE_NUMERIC and row["condition"]["context"] in UPGRADE_CONTEXTS


def build_reviewed(sources):
    """Same precedence as v5; numeric upgrades leave the mechanism rows with their field values."""
    doc = v5.build_reviewed(sources)
    fields = sources["numeric_fields"]
    numeric_ids = sources["numeric_ids"]
    active = [*doc["rows"], *sources["extra_rows"]]
    numeric = [
        {
            "subject": row["subject"],
            "subject_zh": row["subject_zh"],
            "kind": row["mechanism"],
            "condition": row["condition"],
            "field_values": fields.get((row["subject"], row["condition"]["context"]))
            if row["mechanism"] in UPGRADE_NUMERIC
            else None,
            "quotes": row["quotes"],
        }
        for row in active
        if _is_numeric_upgrade(row, numeric_ids)
    ]
    rows = [row for row in active if not _is_numeric_upgrade(row, numeric_ids)]
    rows.sort(key=lambda row: (row["mechanism"], row["subject"], row["review_id"]))
    decisions = {}
    basis = {}
    for row in rows:
        decisions[row["decision"]] = decisions.get(row["decision"], 0) + 1
        key = row["basis"].split(":")[0]
        basis[key] = basis.get(key, 0) + 1
    return {
        **doc,
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "vocabulary": VOCABULARY,
        "rows": rows,
        "numeric_upgrades": numeric,
        "counts": {
            **doc["counts"],
            "rows": len(rows),
            "decisions": decisions,
            "basis": basis,
            "numeric_upgrades": len(numeric),
        },
    }
