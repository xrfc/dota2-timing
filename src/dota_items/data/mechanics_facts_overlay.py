"""Shared builder for reviewed mechanics facts, from version 27 on (U177).

Versions 14-26 each copied a `mechanics_facts_vN.py` module to lay one set of review results
over the previous frozen package. From v27, every new version uses this module instead: the
input is the previous frozen facts plus one overlay file, an ordered list of operations.

Overlay file (`mechanics-overlay-inputs/1`)::

    {"schema": "mechanics-overlay-inputs/1", "version": 27, "note": "...",
     "operations": [{"op": "decision_change", ...}, ...]}

Operations, applied in order; each one checks the row it touches is in the stated old state:

- ``basis_update``: review_id, subject, mechanism, from, to, note_zh. Row must be accepted.
- ``decision_change``: review_id, subject, mechanism, from, to, basis, note_zh.
- ``add_row``: review_id, subject, subject_zh, mechanism, condition, decision, basis,
  notes_zh, quotes; optional origin, claude, codex.
- ``retire``: review_ids, item_status, note_zh. Rows move to ``retired_rows``.
- ``note``: review_id, note_zh. Appends a note.
- ``reword_notes``: old, new. Replaces wording in AI-written notes, not in quoted sources.

A basis is ``user:<decision>`` (the user ruled) or ``two_ai`` (two AIs agreed; for added rows
both ``claude`` and ``codex`` must say ``accept``). New operation types are added here, not in
a new module. Old v2-v26 modules stay unchanged for reproducing their frozen packages.
"""

SCHEMA = "mechanics-overlay-inputs/1"
CONDITIONS = (
    {"context": "base", "requires_scepter": False, "requires_shard": False},
    {"context": "scepter_upgrade", "requires_scepter": True, "requires_shard": False},
    {"context": "shard_upgrade", "requires_scepter": False, "requires_shard": True},
    {"context": "item", "requires_scepter": False, "requires_shard": False},
)
DECISIONS = ("accept", "reject")


def build_reviewed(base, inputs, *, version, vocabulary, terms, known_subjects=frozenset()):
    """Apply an overlay file to a frozen facts document; returns a new document."""
    if inputs.get("schema") != SCHEMA:
        raise ValueError(f"Expected {SCHEMA}")
    if inputs.get("version") != version:
        raise ValueError(f"Overlay is for version {inputs.get('version')}, not {version}")
    doc = {
        **base,
        "rows": [dict(row) for row in base["rows"]],
        "retired_rows": list(base["retired_rows"]),
    }
    for number, operation in enumerate(inputs["operations"]):
        handler = OPERATIONS.get(operation.get("op"))
        if handler is None:
            raise ValueError(f"Operation {number}: unknown op {operation.get('op')!r}")
        try:
            handler(doc, operation, terms=terms, known_subjects=known_subjects)
        except ValueError as error:
            raise ValueError(f"Operation {number} ({operation['op']}): {error}") from None
    rows = sorted(doc["rows"], key=lambda r: (r["mechanism"], r["subject"], r["review_id"]))
    return {
        **doc,
        "schema": f"mechanics-facts/{version}",
        "extractor_version": f"mechanics-reviewed/{version}",
        "vocabulary": vocabulary,
        "rows": rows,
        "counts": {
            **base["counts"],
            "rows": len(rows),
            "decisions": _tally(row["decision"] for row in rows),
            "basis": _tally(row["basis"].split(":")[0] for row in rows),
            "retired_rows": len(doc["retired_rows"]),
            "rows_with_condition_note": sum(bool(r["condition_notes"]) for r in rows),
        },
    }


def _tally(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _check_basis(basis):
    if not (basis.startswith("user:") or basis == "two_ai"):
        raise ValueError(f"Basis must be user:<decision> or two_ai, not {basis!r}")


def _find(doc, operation):
    matches = [i for i, row in enumerate(doc["rows"]) if row["review_id"] == operation["review_id"]]
    if len(matches) != 1:
        raise ValueError(f"{operation['review_id']}: no single matching row")
    index = matches[0]
    row = doc["rows"][index]
    for key in ("subject", "mechanism"):
        if key in operation and row[key] != operation[key]:
            raise ValueError(f"{operation['review_id']}: {key} is {row[key]!r}")
    return index, row


def _basis_update(doc, operation, **_):
    index, row = _find(doc, operation)
    if row["decision"] != "accept" or row["basis"] != operation["from"]:
        raise ValueError(f"{row['review_id']}: expected an accepted {operation['from']} row")
    _check_basis(operation["to"])
    doc["rows"][index] = {
        **row,
        "basis": operation["to"],
        "notes_zh": [*row["notes_zh"], operation["note_zh"]],
    }


def _decision_change(doc, operation, **_):
    index, row = _find(doc, operation)
    if row["decision"] != operation["from"] or operation["to"] not in DECISIONS:
        raise ValueError(f"{row['review_id']}: row does not match the change")
    _check_basis(operation["basis"])
    doc["rows"][index] = {
        **row,
        "decision": operation["to"],
        "basis": operation["basis"],
        "notes_zh": [*row["notes_zh"], operation["note_zh"]],
    }


def _condition_change(doc, operation, **_):
    index, row = _find(doc, operation)
    if row["condition"] != operation["from"] or operation["to"] not in CONDITIONS:
        raise ValueError(f"{row['review_id']}: unexpected condition")
    if any(
        other is not row
        and other["subject"] == row["subject"]
        and other["mechanism"] == row["mechanism"]
        and other["condition"] == operation["to"]
        for other in doc["rows"]
    ):
        raise ValueError("Duplicate condition after change")
    _check_basis(operation["basis"])
    doc["rows"][index] = {
        **row,
        "condition": dict(operation["to"]),
        "condition_notes": operation["condition_notes"],
        "basis": operation["basis"],
        "notes_zh": [*row["notes_zh"], operation["note_zh"]],
    }


def _add_row(doc, spec, *, terms, known_subjects):
    if spec["mechanism"] not in terms:
        raise ValueError(f"Unknown mechanism {spec['mechanism']}")
    subjects = {row["subject"] for row in doc["rows"]}
    if spec["subject"] not in subjects and spec["subject"] not in known_subjects:
        raise ValueError(f"Unknown subject {spec['subject']}")
    if spec["condition"] not in CONDITIONS:
        raise ValueError(f"{spec['subject']}: unexpected condition")
    if spec["decision"] not in DECISIONS:
        raise ValueError(f"Unknown decision {spec['decision']}")
    _check_basis(spec["basis"])
    if spec["basis"] == "two_ai" and (spec.get("claude"), spec.get("codex")) != ("accept",) * 2:
        raise ValueError("A two_ai row needs claude and codex to accept")
    key = (spec["subject"], spec["mechanism"], spec["condition"]["context"])
    for row in doc["rows"]:
        if row["review_id"] == spec["review_id"] or (
            (row["subject"], row["mechanism"], row["condition"]["context"]) == key
        ):
            raise ValueError(f"Row already exists: {key}")
    doc["rows"].append(
        {
            "review_id": spec["review_id"],
            "origin": spec.get("origin", "user_added"),
            "subject": spec["subject"],
            "subject_zh": spec["subject_zh"],
            "mechanism": spec["mechanism"],
            "condition": dict(spec["condition"]),
            "decision": spec["decision"],
            "basis": spec["basis"],
            "claude": spec.get("claude"),
            "codex": spec.get("codex"),
            "notes_zh": list(spec["notes_zh"]),
            "break_conditions_en": [],
            "quotes": list(spec["quotes"]),
            "item_status": None,
            "condition_notes": [],
            "condition_review": "none",
        }
    )


def _retire(doc, operation, **_):
    wanted = set(operation["review_ids"])
    if len(wanted) != len(operation["review_ids"]):
        raise ValueError("Duplicate review_id")
    keep, moved = [], []
    for row in doc["rows"]:
        if row["review_id"] in wanted:
            moved.append(
                {
                    **row,
                    "item_status": operation["item_status"],
                    "notes_zh": [*row["notes_zh"], operation["note_zh"]],
                }
            )
        else:
            keep.append(row)
    missing = sorted(wanted - {row["review_id"] for row in moved})
    if missing:
        raise ValueError(f"Rows not found: {missing}")
    doc["rows"] = keep
    doc["retired_rows"] = [*doc["retired_rows"], *moved]


def _note(doc, operation, **_):
    index, row = _find(doc, operation)
    doc["rows"][index] = {**row, "notes_zh": [*row["notes_zh"], operation["note_zh"]]}


def _reword_notes(doc, operation, **_):
    old, new = operation["old"], operation["new"]
    if not old or old == new:
        raise ValueError("reword_notes needs two different non-empty strings")
    doc["rows"] = [
        {
            **row,
            "notes_zh": [n.replace(old, new) for n in row["notes_zh"]],
            "condition_notes": [
                {**note, "text": note["text"].replace(old, new)} for note in row["condition_notes"]
            ],
        }
        for row in doc["rows"]
    ]


OPERATIONS = {
    "basis_update": _basis_update,
    "decision_change": _decision_change,
    "condition_change": _condition_change,
    "add_row": _add_row,
    "retire": _retire,
    "note": _note,
    "reword_notes": _reword_notes,
}
