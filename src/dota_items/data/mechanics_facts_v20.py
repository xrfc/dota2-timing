"""MK-T6c reviewed facts, version 20: every numeric upgrade says who ruled it (U113).

v6 and v8 moved 69 upgrade groups to `numeric_upgrades` but kept no ruling with them. Each now
gets `ruling`: either the user's ruling row in `user-rulings-001.jsonl` (U65, U66, U72), or
the U65 rule that upgrades which only reduce cooldowns are numbers, not mechanisms. Every
entry must match exactly one source, and every numeric ruling must be used.
"""

SCHEMA = "mechanics-facts/20"
VERSION = "mechanics-reviewed/20"
VOCABULARY = "knowledge/mechanics/vocabulary-v13.json"
RULINGS = "knowledge/mechanics/reviews/user-rulings-001.jsonl"
UPGRADE_CONTEXTS = {"scepter_upgrade", "shard_upgrade"}
COOLDOWN_RULE = {
    "how": "rule",
    "decision": "U65",
    "rule_zh": "A杖、魔晶升级只减冷却时不记机制，移到数值（U65第1条）",
}


def _ruling(row):
    return {
        "how": "user_ruling",
        "decision": row["decision_ref"],
        "review_id": row["review_id"],
        "note_zh": row["note_zh"],
        "date": row["date"],
        "source": RULINGS,
    }


def build_reviewed(base, rulings):
    """Same rows as v19; numeric upgrades gain `ruling`."""
    numeric_rulings = {
        (row["subject"], row["mechanism"]): row for row in rulings if row.get("numeric_upgrade")
    }
    used = set()
    upgrades = []
    for entry in base["numeric_upgrades"]:
        key = (entry["subject"], entry["kind"])
        if key in numeric_rulings:
            ruling = _ruling(numeric_rulings[key])
            used.add(key)
        elif (
            entry["kind"] == "cooldown_reduction"
            and entry["condition"]["context"] in UPGRADE_CONTEXTS
        ):
            ruling = dict(COOLDOWN_RULE)
        else:
            raise ValueError(f"No ruling for numeric upgrade {key}")
        upgrades.append({**entry, "ruling": ruling})
    unused = sorted(set(numeric_rulings) - used)
    if unused:
        raise ValueError(f"Numeric rulings without an upgrade entry: {unused}")
    return {
        **base,
        "schema": SCHEMA,
        "extractor_version": VERSION,
        "vocabulary": VOCABULARY,
        "numeric_upgrades": upgrades,
    }
