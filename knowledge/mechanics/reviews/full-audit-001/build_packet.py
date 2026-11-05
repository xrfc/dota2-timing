"""Build blind per-object batches for the full recall audit (U81). Run from repo root.

Every ability and current item is read against the vocabulary, without keyword screening.
Mechanisms read straight from game fields are left out because no reading can improve them.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
MECH = ROOT / "knowledge/mechanics"
BATCH_SIZE = 25
FIELD_ONLY = {
    "effect_dispellability",
    "mana_cost",
    "magical_damage",
    "pure_damage",
    "physical_damage",
    "break_sensitive",
    "unit_target_spell",
    "channeled",
}
ITEM_DESC = re.compile(r'"DOTA_Tooltip_[Aa]bility_item_(\w+?)_Description"\s+"(.*)"')
ITEM_NOTE = re.compile(r'"DOTA_Tooltip_[Aa]bility_item_(\w+?)_Note\d+"\s+"(.*)"')


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def clean(text):
    return re.sub(r"<[^>]+>", " ", text or "").replace("\\n", " ").strip()


def main():
    registry = load(ROOT / "knowledge/hero-capabilities/hero-registry.json")
    stale = {
        (row["ability"], row["upgrade"])
        for row in load(MECH / "stale-upgrade-text-v1.json")["entries"]
    }
    objects = []
    for hero in registry["heroes"]:
        for ability in hero["abilities"]:
            upgrades = {}
            for key, label in (("scepter", "scepter_loc"), ("shard", "shard_loc")):
                text = (ability.get("upgrade_text") or {}).get(label, {})
                if (text.get("en") or text.get("zh")) and (ability["name"], key) not in stale:
                    upgrades[key] = {"zh": text.get("zh", ""), "en": text.get("en", "")}
            raw = ability.get("raw_mechanics") or {}
            objects.append(
                {
                    "subject": ability["name"],
                    "name_zh": f"{hero['name_zh']}·{ability['name_zh']}",
                    "name_en": ability["name_en"],
                    "description_zh": clean(ability["description_zh"]),
                    "description_en": clean(ability["description_en"]),
                    "notes_zh": [clean(n) for n in ability["notes_zh"]],
                    "granted_by": "scepter"
                    if ability["granted_by_scepter"]
                    else "shard"
                    if ability["granted_by_shard"]
                    else "",
                    "upgrades": upgrades,
                    "is_passive": bool(int(raw.get("behavior") or 0) & 2),
                    "value_names": [v["name"] for v in ability.get("special_values") or []][:15],
                }
            )
    status = load(MECH / "retired-items-v1.json")["status"]
    names = {
        row["name"].removeprefix("item_"): row["name_loc"]
        for row in load(ROOT / "knowledge/items/sources/itemlist-schinese.json")["result"]["data"][
            "itemabilities"
        ]
    }
    constants = load(ROOT / "knowledge/items/sources/dotaconstants-items.json")
    local = (
        ROOT / "knowledge/game-files/snapshots/2026-11-02/sources/resource/localization/"
        "abilities_english.txt"
    ).read_text(encoding="utf-8", errors="replace")
    descriptions = {m[1]: clean(m[2]) for m in ITEM_DESC.finditer(local)}
    notes = {}
    for match in ITEM_NOTE.finditer(local):
        notes.setdefault(match[1], []).append(clean(match[2]))
    for subject in sorted(status):
        if status[subject] not in ("purchasable", "other_source") or subject.startswith("recipe"):
            continue
        detail = constants.get(subject, {})
        text = descriptions.get(subject) or " ".join(
            clean(part.get("description", "")) for part in detail.get("abilities", []) or []
        )
        objects.append(
            {
                "subject": subject,
                "name_zh": names.get(subject) or subject,
                "name_en": detail.get("dname", ""),
                "description_en": text,
                "notes_en": notes.get(subject, []),
                "attributes": [
                    a["display"].replace("{value}", str(a.get("value", "")))
                    for a in detail.get("attrib", []) or []
                    if isinstance(a, dict) and a.get("display")
                ],
                "is_item": True,
            }
        )
    vocabulary = [
        {"id": term["id"], "zh": term["zh"], "definition": term["definition"]}
        for term in load(MECH / "vocabulary-v9.json")["mechanisms"]
        if term["id"] not in FIELD_ONLY
    ]
    (OUT / "vocabulary.json").write_text(
        json.dumps(vocabulary, ensure_ascii=False, indent=0), encoding="utf-8"
    )
    (OUT / "objects.json").write_text(
        json.dumps(objects, ensure_ascii=False, indent=0), encoding="utf-8"
    )
    for index in range(0, len(objects), BATCH_SIZE):
        name = f"batch-{index // BATCH_SIZE + 1:03d}.json"
        (OUT / "batches" / name).write_text(
            json.dumps(objects[index : index + BATCH_SIZE], ensure_ascii=False), encoding="utf-8"
        )
    print(len(objects), "objects", len(vocabulary), "terms")


if __name__ == "__main__":
    main()
