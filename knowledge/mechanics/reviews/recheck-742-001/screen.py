"""Claude's mechanical screen of the 7.42 recheck, independent of Codex's verdicts.

For each row sent to Codex, flag the changes that could flip a decision without any wording
cue: a value that becomes 0 or disappears, a scepter or shard value removed, the ability losing
its scepter/shard upgrade, a whole text field removed, or a data field (behaviour, targets,
dispel, immunity, damage type) changing. Rows with no flag and a Codex `holds` are the ones the
two reviewers agree on without Claude reading them one by one; everything else is read by Claude.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
TEXT_KEYS = ("desc_loc", "notes_loc", "scepter_loc", "shard_loc", "facets_loc")
DATA_KEYS = {
    "behavior", "target_team", "target_type", "flags", "damage", "immunity", "dispellable",
    "ability_has_scepter", "ability_has_shard",
}  # fmt: skip


def _zeroish(value):
    if value is None:
        return True
    return isinstance(value, list) and (not value or all(v == 0 for v in value))


def flags(obj):
    found = []
    for change in obj["changed_fields"]:
        field, old, new = change["field"], change["old"], change["new"]
        if field in DATA_KEYS:
            found.append(f"data:{field}")
            continue
        if isinstance(old, dict) or isinstance(new, dict):
            old, new = old or {}, new or {}
            for part in ("base", "scepter", "shard"):
                if not _zeroish(old.get(part)) and _zeroish(new.get(part)):
                    found.append(f"value_gone:{field}.{part}")
                if _zeroish(old.get(part)) and not _zeroish(new.get(part)):
                    found.append(f"value_new:{field}.{part}")
        elif not _zeroish(old) and _zeroish(new):
            found.append(f"value_gone:{field}")
    for key in TEXT_KEYS:
        if key in obj["text_741f"] and key not in obj["text_742"]:
            found.append(f"text_removed:{key}")
        if key not in obj["text_741f"] and key in obj["text_742"]:
            found.append(f"text_added:{key}")
    return found


def main():
    screen = {}
    for path in sorted((OUT / "batches").glob("batch-*.json")):
        for obj in json.loads(path.read_text(encoding="utf-8")):
            screen[obj["subject"]] = {"category": obj["category"], "flags": flags(obj)}
    (OUT / "claude-screen.json").write_text(
        json.dumps(screen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    flagged = sum(1 for s in screen.values() if s["flags"])
    print({"objects": len(screen), "flagged": flagged})


if __name__ == "__main__":
    main()
