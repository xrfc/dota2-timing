"""MK-T6e: patch update flow for the mechanics knowledge (steps in docs/mechanics-patch-update.md).

    # 1. network: is there a patch newer than current.json says?
    python scripts/patch_update.py status --output <new receipt.json>
    # 2. offline diffs between an old and a new snapshot
    python scripts/patch_update.py item-diff --old <items dir> --new <items dir> --output <json>
    python scripts/patch_update.py game-diff --old <game snapshot> --new <game snapshot> \
        --output <json>
    # 3. offline: which facts, rules and relations the changes touch
    PYTHONPATH=src python scripts/patch_update.py impact --hero-diff <json> \
        [--item-diff <json>] [--game-diff <json>] --output <json>

Nothing is overwritten. The impact report lists what to re-review; it decides nothing.
"""

import argparse
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

PATCH_LIST = "https://www.dota2.com/datafeed/patchnoteslist?language=english"
REGISTRY = "knowledge/hero-capabilities/hero-registry.json"
ITEM_FIELDS = ("desc_loc", "notes_loc", "special_values", "name_loc")


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_new(path, value):
    path = Path(path)
    if path.exists():
        raise SystemExit("Output already exists; choose a new path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def status(patch_list, current_patch):
    """Compare the newest official patch with the one current.json was checked against."""
    latest = max(patch_list["patches"], key=lambda row: row["patch_timestamp"])
    return {
        "schema": "mechanics-patch-status/1",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "source_url": PATCH_LIST,
        "current": current_patch["name"],
        "current_checked_at": current_patch.get("checked_at"),
        "latest": latest["patch_number"],
        "latest_timestamp": latest["patch_timestamp"],
        "update_needed": latest["patch_number"] != current_patch["name"],
    }


def _same(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def item_diff(old, new):
    """Per item subject in either snapshot: added, removed, or which official fields changed."""
    changes = []
    for subject in sorted(set(old) | set(new)):
        if subject not in new:
            changes.append({"subject": subject, "change": "item_removed"})
        elif subject not in old:
            changes.append({"subject": subject, "change": "item_added"})
        else:
            fields = [f for f in ITEM_FIELDS if not _same(old[subject].get(f), new[subject].get(f))]
            if fields:
                changes.append({"subject": subject, "change": "item_changed", "fields": fields})
    return {"schema": "item-datafeed-diff/1", "changes": changes}


def _blocks(snapshot):
    import check_break_against_game_files as game

    files = sorted((Path(snapshot) / "sources/scripts/npc").rglob("*.txt"))
    blocks = {}
    for path in files:
        tree = game.parse_keyvalues(path.read_text(encoding="utf-8", errors="replace"))
        root = tree.get("DOTAAbilities", tree)
        for name, body in root.items():
            if isinstance(body, dict):
                blocks[name] = body
    return blocks


def game_diff(old_snapshot, new_snapshot):
    """Per ability or item block in the game scripts: added, removed or changed."""
    old, new = _blocks(old_snapshot), _blocks(new_snapshot)
    changes = []
    for name in sorted(set(old) | set(new)):
        if name not in new:
            changes.append({"block": name, "change": "removed"})
        elif name not in old:
            changes.append({"block": name, "change": "added"})
        elif not _same(old[name], new[name]):
            keys = sorted(
                k
                for k in set(old[name]) | set(new[name])
                if not _same(old[name].get(k), new[name].get(k))
            )
            changes.append({"block": name, "change": "changed", "keys": keys})
    return {"schema": "game-files-diff/1", "changes": changes}


def _changed_subjects(hero_diff, item_diff_doc, game_diff_doc):
    """subject -> list of reasons, from every diff given."""
    reasons = {}

    def add(subject, reason):
        reasons.setdefault(subject, []).append(reason)

    for language, report in (hero_diff or {}).get("languages", {}).items():
        for change in report["changes"]:
            if "ability" in change:
                fields = change.get("text_fields", []) + change.get("other_fields", [])
                add(change["ability"], f"herodata/{language}: {change['change']} {fields}")
            else:
                add(change["hero"], f"herodata/{language}: {change['change']}")
    for change in (item_diff_doc or {}).get("changes", []):
        add(change["subject"], f"itemdata: {change['change']} {change.get('fields', [])}")
    for change in (game_diff_doc or {}).get("changes", []):
        name = change["block"]
        subject = name[5:] if name.startswith("item_") else name
        add(subject, f"game files: {change['change']} {change.get('keys', [])}")
    return reasons


def impact(hero_diff, item_diff_doc=None, game_diff_doc=None, root=ROOT):
    from dota_items.data.mechanics_current import read_current

    facts = read_current("facts", root)
    evaluation = read_current("rules_evaluation", root)
    graph = read_current("counter_graph", root)
    reasons = _changed_subjects(hero_diff, item_diff_doc, game_diff_doc)
    known = {row["subject"] for row in facts["rows"]}
    known |= {entry["subject"] for entry in facts["numeric_upgrades"]}
    rows = [
        {
            "subject": row["subject"],
            "mechanism": row["mechanism"],
            "decision": row["decision"],
            "basis": row["basis"],
            "condition": row["condition"],
        }
        for row in facts["rows"]
        if row["subject"] in reasons
    ]
    numeric = [e["subject"] for e in facts["numeric_upgrades"] if e["subject"] in reasons]
    rules = sorted(
        {
            entry["id"]
            for entry in evaluation["rules"]
            if reasons.keys() & (set(entry["sources"]) | set(entry["targets"]))
        }
    )
    edges = [
        edge
        for edge in graph["item_to_hero"]
        if edge["item"] in reasons or reasons.keys() & set(edge["abilities"])
    ]
    return {
        "schema": "mechanics-patch-impact/1",
        "note_zh": "需要重新复核的范围；不是判断结果",
        "changed_subjects": {s: reasons[s] for s in sorted(reasons)},
        "changed_but_not_in_facts": sorted(s for s in reasons if s not in known),
        "fact_rows_to_recheck": rows,
        "numeric_upgrades_to_recheck": numeric,
        "rules_touched": rules,
        "item_edges_touched": len(edges),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("status")
    s.add_argument("--output", required=True, type=Path)
    i = sub.add_parser("item-diff")
    g = sub.add_parser("game-diff")
    for p in (i, g):
        p.add_argument("--old", required=True, type=Path)
        p.add_argument("--new", required=True, type=Path)
        p.add_argument("--output", required=True, type=Path)
    m = sub.add_parser("impact")
    m.add_argument("--hero-diff", required=True, type=Path)
    m.add_argument("--item-diff", type=Path)
    m.add_argument("--game-diff", type=Path)
    m.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "status":
        with urllib.request.urlopen(PATCH_LIST, timeout=35) as response:
            patch_list = json.loads(response.read())
        result = status(patch_list, _load(ROOT / "knowledge/mechanics/current.json")["patch"])
    elif args.command == "item-diff":
        result = item_diff(_load(args.old / "items.json"), _load(args.new / "items.json"))
    elif args.command == "game-diff":
        result = game_diff(args.old, args.new)
    else:
        result = impact(
            _load(args.hero_diff),
            _load(args.item_diff) if args.item_diff else None,
            _load(args.game_diff) if args.game_diff else None,
        )
    _write_new(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if not isinstance(v, (list, dict))}))


if __name__ == "__main__":
    main()
