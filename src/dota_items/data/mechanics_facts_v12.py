"""MK-T5 reviewed facts, version 12: v11 plus U85-U89 and the split of control terms."""

from dota_items.data import mechanics_facts_v11 as v11

SCHEMA = "mechanics-facts/12"
VERSION = "mechanics-reviewed/12"
VOCABULARY = "knowledge/mechanics/vocabulary-v11.json"
RETIRED_TERMS = {"forced_action", "mobility_lock"}


def condition_label(condition):
    """Name a row condition the way reviews and rulings write it."""
    if condition.get("context") == "item":
        return "item"
    if condition.get("requires_scepter"):
        return "scepter"
    if condition.get("requires_shard"):
        return "shard"
    return "base"


def _matches(rows, entry):
    return [
        row
        for row in rows
        if row["subject"] == entry["subject"]
        and row["mechanism"] == entry["mechanism"]
        and entry.get("condition") in (None, condition_label(row["condition"]))
    ]


def _add(rows, entry, zh_names, status):
    if not entry.get("condition"):
        raise ValueError(f"New row needs a condition: {entry}")
    origin = "user_ruling" if entry["basis"].startswith("user:") else "control_audit"
    row = v11._new_row({**entry, "origin": origin, "kind": "row"}, zh_names, status)
    if origin == "control_audit":
        row["codex"] = "accept"
    rows.append(row)


def _set(rows, entry, zh_names, status):
    found = _matches(rows, entry)
    if not found:
        _add(rows, entry, zh_names, status)
    elif not entry["basis"].startswith("user:"):
        raise ValueError(f"Only a user ruling may change a row: {entry}")
    for row in found:
        row["decision"] = entry["decision"]
        row["basis"] = entry["basis"]
        row["notes_zh"] = [entry["note_zh"], *row["notes_zh"]]


def _move(rows, entry):
    moved = [row for row in _matches(rows, entry) if row["decision"] == "accept"]
    if not moved:
        raise ValueError(f"Nothing to move: {entry}")
    for row in moved:
        row["mechanism"] = entry["new"]
        row["renamed_from"] = entry["mechanism"]


def apply_rulings(doc, operations, zh_names, status):
    """Apply operations in order, then set aside rows left under retired terms."""
    rows = [{**row, "notes_zh": list(row["notes_zh"])} for row in doc["rows"]]
    for entry in operations:
        if entry["op"] == "set":
            _set(rows, entry, zh_names, status)
        elif entry["op"] == "move":
            _move(rows, entry)
        else:
            raise ValueError(f"Unknown operation: {entry}")
    retired = [row for row in rows if row["mechanism"] in RETIRED_TERMS]
    unmapped = [row for row in retired if row["decision"] == "accept" and not _replaced(row, rows)]
    if unmapped:
        raise ValueError(f"Accepted row has no new term: {unmapped}")
    kept = [row for row in rows if row["mechanism"] not in RETIRED_TERMS]
    kept.sort(key=lambda row: (row["mechanism"], row["subject"], row["review_id"]))
    decisions, basis = {}, {}
    for row in kept:
        decisions[row["decision"]] = decisions.get(row["decision"], 0) + 1
        name = row["basis"].split(":")[0]
        basis[name] = basis.get(name, 0) + 1
    counts = {
        **doc["counts"],
        "rows": len(kept),
        "decisions": decisions,
        "basis": basis,
        "retired_term_rows": len(retired),
    }
    return {**doc, "rows": kept, "retired_term_rows": retired, "counts": counts}


def _replaced(row, rows):
    """A blink lock row is covered when the subject now has root or bind."""
    return row["mechanism"] == "mobility_lock" and any(
        other["subject"] == row["subject"]
        and other["mechanism"] in {"root", "bind"}
        and other["decision"] == "accept"
        for other in rows
    )


def build_reviewed(sources):
    """v11 result with the rulings and the control split applied."""
    doc = apply_rulings(
        v11.build_reviewed(sources),
        sources["recheck_rulings"],
        sources["zh_names"],
        sources["item_status"],
    )
    return {**doc, "schema": SCHEMA, "extractor_version": VERSION, "vocabulary": VOCABULARY}
