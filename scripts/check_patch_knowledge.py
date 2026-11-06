"""MK-T6d: check the current mechanics knowledge against the current game version (U66, U99).

Two steps; nothing is overwritten.

    # 1. network (U99): Valve English item data for every item the facts name
    python scripts/check_patch_knowledge.py fetch-items \
        --output knowledge/items/sources/itemdata-english-2026-11-06
    # 2. offline: compare the current facts with the newest sources
    PYTHONPATH=src python scripts/check_patch_knowledge.py check \
        --heroes knowledge/hero-capabilities/snapshots/2026-11-06/sources \
        --items knowledge/items/sources/itemdata-english-2026-11-06 \
        --output knowledge/mechanics/reviews/patch-check-001/report.json

The check lists candidates for review, not proven errors: an ability or item the facts name
but the current sources lack, an item the game cannot buy, and items whose English text in
dotaconstants (where item quotes came from) reads differently from Valve's current text.
"""

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

ITEM_URL = "https://www.dota2.com/datafeed/itemdata?language=english&item_id={}"
REGISTRY = "knowledge/items/item-registry.json"
DOTACONSTANTS = "knowledge/items/sources/dotaconstants-items.json"
GAME_ITEMS = "knowledge/game-files/snapshots/2026-11-03-items/sources/scripts/npc/items.txt"
MIRROR_CHECK = "knowledge/mechanics/reviews/patch-check-001/mirror-check.json"
TEXT_THRESHOLD = 0.5
QUOTE_THRESHOLD = 0.6
# Valve attribute headings use short placeholders such as "+$hp_regen".
HEADING_WORDS = {
    "hp": "health",
    "regen": "regeneration",
    "int": "intelligence",
    "str": "strength",
    "agi": "agility",
    "all": "all attributes",
    "attack": "attack",
    "spell": "spell",
    "evasion": "evasion",
}


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _item_subjects(facts, registry):
    return sorted({row["subject"] for row in facts["rows"] if row["subject"] in registry})


def fetch_items(output):
    from dota_items.data.mechanics_current import read_current

    output = Path(output)
    if output.exists():
        raise SystemExit("Output already exists; choose a new directory")
    registry = _load(ROOT / REGISTRY)["items"]
    subjects = _item_subjects(read_current("facts", ROOT), registry)
    items, records = {}, []
    for subject in subjects:
        url = ITEM_URL.format(registry[subject]["id"])
        with urllib.request.urlopen(url, timeout=35) as response:
            payload = response.read()
        data = json.loads(payload)["result"]["data"]["items"]
        if len(data) != 1 or data[0]["id"] != registry[subject]["id"]:
            raise SystemExit(f"Unexpected response identity for {subject}")
        items[subject] = data[0]
        records.append({"subject": subject, "sha256": hashlib.sha256(payload).hexdigest()})
        time.sleep(0.2)
    output.mkdir(parents=True)
    body = json.dumps(items, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    (output / "items.json").write_text(body, encoding="utf-8")
    manifest = {
        "schema": "item-sources/1",
        "fetched_at": datetime.now(UTC).isoformat(),
        "authorization": "U99 (user 2026-11-06: 联网验证知识库是否符合版本)",
        "url": ITEM_URL,
        "publisher": "Valve (official datafeed)",
        "purpose": "MK-T6d version check; not for training",
        "patch_verified": False,
        "items": len(items),
        "records": records,
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


def _words(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"%[^%\s]*%|\$\w+|[\d.]+", " ", text)
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2}


def _similarity(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if a | b else 0.0


def _valve_words(item):
    parts = [item.get("desc_loc", ""), " ".join(item.get("notes_loc") or [])]
    for value in item.get("special_values", []):
        heading = (value.get("heading_loc") or "").replace("$", " ").replace("_", " ")
        parts.append(value.get("name", "").replace("_", " "))
        parts.append(" ".join(HEADING_WORDS.get(w, w) for w in heading.split()))
    return _words(" ".join(parts))


def _numbers(text):
    return {float(n) for n in re.findall(r"\d+(?:\.\d+)?", text or "")}


def _valve_numbers(item):
    found = set()
    for value in item.get("special_values", []):
        for key in ("values_float", "values_int"):
            found |= {float(v) for v in value.get(key) or []}
    return found | _numbers(item.get("desc_loc"))


def quote_support(rows, valve):
    """Per accepted item row quote: how much of it the current Valve text still covers."""
    out = []
    for row in rows:
        item = valve[row["subject"]]
        words, numbers = _valve_words(item), _valve_numbers(item)
        for quote in row["quotes"]:
            quote_words = _words(quote)
            if not quote_words:
                continue
            coverage = len(quote_words & words) / len(quote_words)
            attribute = quote.strip().startswith("+")
            flags = []
            if coverage < QUOTE_THRESHOLD:
                flags.append("quote_not_found")
            if attribute and not _numbers(quote) <= numbers:
                flags.append("number_differs")
            if flags:
                out.append(
                    {
                        "subject": row["subject"],
                        "mechanism": row["mechanism"],
                        "basis": row["basis"],
                        "quote": quote,
                        "coverage": round(coverage, 2),
                        "flags": flags,
                    }
                )
    return out


def _game_items():
    import check_break_against_game_files as game

    tree = game.parse_keyvalues((ROOT / GAME_ITEMS).read_text(encoding="utf-8", errors="replace"))
    root = tree.get("DOTAAbilities", tree)
    return {name[5:]: body for name, body in root.items() if name.startswith("item_")}


def check(heroes_dir, items_dir):
    from dota_items.data.mechanics_current import load_current, read_current

    current = load_current(ROOT)
    facts = read_current("facts", ROOT)
    retired = read_current("retired_items", ROOT)
    extra = read_current("extra_abilities", ROOT)
    registry = _load(ROOT / REGISTRY)["items"]
    accepted = {row["subject"] for row in facts["rows"] if row["decision"] == "accept"}

    abilities = set()
    for path in sorted(Path(heroes_dir).glob("hero-*-english.json")):
        for hero in _load(path)["result"]["data"]["heroes"]:
            abilities |= {a["name"] for a in hero.get("abilities", [])}
    extra_names = {a["name"] for hero in extra["heroes"] for a in hero["abilities"]}
    ability_subjects = sorted(s for s in accepted if s not in registry)
    missing_abilities = [s for s in ability_subjects if s not in abilities | extra_names]

    game = _game_items()
    valve = _load(Path(items_dir) / "items.json")
    constants = _load(ROOT / DOTACONSTANTS)
    status = retired.get("status", {})
    item_rows = []
    for subject in sorted(s for s in accepted if s in registry):
        body = game.get(subject)
        purchasable = None if body is None else body.get("ItemPurchasable", "1") != "0"
        old = " ".join(
            a.get("description", "") for a in (constants.get(subject) or {}).get("abilities", [])
        )
        new = (valve.get(subject) or {}).get("desc_loc", "")
        score = round(_similarity(_words(old), _words(new)), 3)
        flags = []
        if body is None:
            flags.append("not_in_game_files")
        elif not purchasable and subject not in retired.get("other_source", {}):
            flags.append("not_purchasable")
        if subject not in valve:
            flags.append("not_in_valve_itemdata")
        if status.get(subject) == "obsolete":
            flags.append("marked_obsolete")
        if score < TEXT_THRESHOLD:
            flags.append("text_differs")
        item_rows.append(
            {
                "subject": subject,
                "name_zh": registry[subject].get("name_zh"),
                "purchasable": purchasable,
                "text_similarity": score,
                "flags": flags,
            }
        )
    item_facts = [r for r in facts["rows"] if r["decision"] == "accept" and r["subject"] in valve]
    return {
        "schema": "mechanics-patch-check/1",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "current_patch": current["patch"],
        "mirror_check": _load(ROOT / MIRROR_CHECK),
        "note_zh": "候选清单，需要逐条核对；不是已证实的错误",
        "abilities": {
            "accepted_subjects": len(ability_subjects),
            "missing_from_current_valve_data": missing_abilities,
        },
        "items": {
            "accepted_subjects": len(item_rows),
            "text_threshold": TEXT_THRESHOLD,
            "flagged": [row for row in item_rows if row["flags"]],
            "quote_threshold": QUOTE_THRESHOLD,
            "quotes_flagged": quote_support(item_facts, valve),
            "all": item_rows,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch-items")
    f.add_argument("--output", required=True, type=Path)
    c = sub.add_parser("check")
    c.add_argument("--heroes", required=True, type=Path)
    c.add_argument("--items", required=True, type=Path)
    c.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "fetch-items":
        print(json.dumps({"items": fetch_items(args.output)["items"]}))
        return
    if args.output.exists():
        raise SystemExit("Output already exists; choose a new path")
    report = check(args.heroes, args.items)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(
        json.dumps(
            {
                "missing_abilities": len(report["abilities"]["missing_from_current_valve_data"]),
                "flagged_items": len(report["items"]["flagged"]),
                "flagged_quotes": len(report["items"]["quotes_flagged"]),
            }
        )
    )


if __name__ == "__main__":
    main()
