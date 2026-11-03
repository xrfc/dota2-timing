"""Compare break_sensitive decisions with IsBreakable in a game-files snapshot (U46)."""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWS = ROOT / "knowledge/mechanics/reviews"
NOTE_KEY = re.compile(r"^DOTA_Tooltip_ability_(.+)_Note\d+$")
LOCALIZATION_LINE = re.compile(r'^\s*"([^"]+)"\s+"(.*)"\s*(?://.*)?$')
BREAK_WORD = re.compile(r"(?<!Mana )\bBreak\b|\bbroken\b")


def tokenize(text: str) -> list[str]:
    tokens, index = [], 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
        elif text.startswith("//", index):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
        elif char in "{}":
            tokens.append(char)
            index += 1
        elif char == '"':
            end = index + 1
            while end < len(text) and text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            tokens.append(text[index : end + 1])
            index = end + 1
        else:
            end = index
            while end < len(text) and not text[end].isspace() and text[end] not in '{}"':
                end += 1
            tokens.append(text[index:end])
            index = end
    return tokens


def parse_keyvalues(text: str) -> dict:
    """Parse Valve KeyValues; the first occurrence of a duplicate key wins."""
    root: dict = {}
    stack = [root]
    key = None
    for token in tokenize(text):
        if token == "{":
            child: dict = {}
            stack[-1].setdefault(key, child)
            stack.append(child)
            key = None
        elif token == "}":
            stack.pop()
        else:
            value = token.strip('"')
            if key is None:
                key = value
            else:
                stack[-1].setdefault(key, value)
                key = None
    return root


def iter_abilities(node: dict):
    """Yield (name, body) for blocks that look like ability definitions."""
    for name, body in node.items():
        if isinstance(body, dict):
            if "AbilityBehavior" in body or "IsBreakable" in body:
                yield name, body
            else:
                yield from iter_abilities(body)


def load_tags(snapshot: Path) -> dict[str, str | None]:
    tags: dict[str, str | None] = {}
    paths = sorted((snapshot / "sources/scripts/npc/heroes").glob("*.txt"))
    for path in [snapshot / "sources/scripts/npc/npc_abilities.txt", *paths]:
        tree = parse_keyvalues(path.read_text(encoding="utf-8", errors="replace"))
        for name, body in iter_abilities(tree):
            tags[name] = body.get("IsBreakable")
    return tags


def load_localization(snapshot: Path) -> dict[str, str]:
    path = snapshot / "sources/resource/localization/abilities_english.txt"
    entries = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = LOCALIZATION_LINE.match(line)
        if match:
            entries.setdefault(match.group(1), match.group(2))
    return entries


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def effective_decisions() -> dict[str, tuple[str, str]]:
    decisions = {}
    for name in ("claude-round-001/claude-review.jsonl", "claude-round-002/new-in-v2.jsonl"):
        for row in read_jsonl(REVIEWS / name):
            decisions[row["review_id"]] = (row["decision"], "claude")
    for row in read_jsonl(REVIEWS / "user-rulings-001.jsonl"):
        decisions[row["review_id"]] = (row["decision"], row["decision_ref"])
    return decisions


def classify(decision: str, tag: str | None, known: bool) -> str:
    if not known:
        return "ability_not_in_game_files"
    if decision == "accept":
        return "agree_tagged" if tag == "1" else "accept_but_untagged"
    return "reject_but_tagged" if tag == "1" else "agree_untagged"


def normalize(text: str) -> str:
    """Drop markup and whitespace, which the datafeed removes from tooltips."""
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", text.replace("\\n", "")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    snapshot = args.snapshot if args.snapshot.is_absolute() else ROOT / args.snapshot
    out = args.out if args.out.is_absolute() else ROOT / args.out

    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    for record in manifest["records"]:
        digest = hashlib.sha256((snapshot / record["file"]).read_bytes()).hexdigest()
        if digest != record["sha256"]:
            raise SystemExit(f"hash mismatch: {record['file']}")

    tags = load_tags(snapshot)
    localization = load_localization(snapshot)
    notes = collections.defaultdict(list)
    for key, value in localization.items():
        match = NOTE_KEY.match(key)
        if match and BREAK_WORD.search(value):
            notes[match.group(1)].append(value)

    decisions = effective_decisions()
    review_path = ROOT / "knowledge/mechanics/extractions/v3/review.csv"
    groups = [
        row
        for row in csv.DictReader(review_path.open(encoding="utf-8-sig"))
        if row["mechanism"] == "break_sensitive"
    ]
    registry = json.loads(
        (ROOT / "knowledge/hero-capabilities/hero-registry.json").read_text(encoding="utf-8")
    )
    abilities = {
        ability["name"]: (hero, ability)
        for hero in registry["heroes"]
        for ability in hero["abilities"]
    }

    rows = []
    for group in groups:
        subject = group["subject"]
        decision, source = decisions.get(group["review_id"], ("missing", "none"))
        rows.append(
            {
                "review_id": group["review_id"],
                "subject": subject,
                "subject_zh": f"{group['hero_zh']}·{group['name_zh']}",
                "condition": json.loads(group["condition"]),
                "effective_decision": decision,
                "decision_source": source,
                "is_breakable": tags.get(subject),
                "in_game_files": subject in tags,
                "break_notes_en": notes.get(subject, []),
                "result": classify(decision, tags.get(subject), subject in tags),
            }
        )
    out.mkdir(parents=True, exist_ok=True)
    with (out / "comparison.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    accepted = {row["subject"] for row in rows if row["effective_decision"] == "accept"}
    grouped = {row["subject"] for row in rows}
    uncovered = [
        {
            "subject": name,
            "subject_zh": f"{abilities[name][0]['name_zh']}·{abilities[name][1]['name_zh']}",
            "has_group": name in grouped,
            "innate": abilities[name][1]["innate"],
            "break_notes_en": notes.get(name, []),
        }
        for name, tag in sorted(tags.items())
        if tag == "1" and name in abilities and name not in accepted
    ]
    version = collections.Counter()
    version_diffs = []
    for name, (_, ability) in sorted(abilities.items()):
        text = localization.get(f"DOTA_Tooltip_ability_{name}_Description")
        if text is None or not ability.get("description_en"):
            version["not_comparable"] += 1
        elif normalize(text) == normalize(ability["description_en"]):
            version["identical"] += 1
        else:
            version["different"] += 1
            version_diffs.append(
                {"subject": name, "game_files": text, "valve_datafeed": ability["description_en"]}
            )
    summary = {
        "snapshot_commit": manifest["commit"],
        "groups": len(rows),
        "results": dict(collections.Counter(row["result"] for row in rows)),
        "effective_decisions": dict(collections.Counter(r["effective_decision"] for r in rows)),
        "tag_values": dict(collections.Counter(str(value) for value in tags.values())),
        "registry_abilities": len(abilities),
        "registry_abilities_tagged": sum(1 for n in abilities if tags.get(n) == "1"),
        "abilities_with_break_notes": len(notes),
        "description_compare": dict(version),
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    (out / "tagged-without-accepted-group.json").write_text(
        json.dumps(uncovered, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    (out / "description-differences.json").write_text(
        json.dumps(version_diffs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
