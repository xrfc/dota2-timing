"""Blind second review of every claim that changes the knowledge base in 7.42 (U185).

Each claim is "in 7.42, <subject> has <mechanism> under <condition>". The packet holds only
evidence: the 7.42 official text (facet text removed, U184), the 7.41f text for comparison, the
data fields that changed, and the official 7.42 patch notes for that ability or item. It never
contains Codex's or Claude's verdicts. Run from the repo root.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
REV = ROOT / "knowledge/mechanics/reviews"
sys.path.insert(0, str(REV / "recheck-742-001"))
import build_packet as bp  # noqa: E402

NOTES = REV / "patch-update-2026-11-19/notes/datafeed-7.42-english.json"


def clean(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


def patch_notes():
    doc = json.loads(NOTES.read_text(encoding="utf-8"))
    by_id = {}
    for hero in doc["heroes"]:
        for ability in hero.get("abilities") or []:
            by_id.setdefault(ability["ability_id"], []).extend(
                clean(n["note"]) for n in ability.get("ability_notes") or []
            )
    for item in doc["items"]:
        notes = [clean(n["note"]) for n in item.get("ability_notes") or []]
        if item.get("ability_id", -1) >= 0 and notes:
            by_id.setdefault(item["ability_id"], []).extend(notes)
    return by_id


def text(entry):
    return {k: v for k, v in bp.text(entry or {}).items() if k != "facets_loc"}


def main():
    review = json.loads((REV / "recheck-742-001/claude-review.json").read_text())["rows"]
    new_abilities = json.loads((REV / "new-abilities-742-001/results/batch-001.json").read_text())
    recheck = {o["subject"]: o for p in (REV / "recheck-742-001/results").glob("*.json")
               for o in json.loads(p.read_text())["objects"]}  # fmt: skip
    old = {**bp.abilities(bp.OLD_HEROES), **bp.items(bp.OLD_ITEMS)}
    new = {**bp.abilities(bp.NEW_HEROES), **bp.items(bp.NEW_ITEMS)}
    notes = patch_notes()
    claims = []
    send = {"change_two_ai", "user_cat4", "user_cat8", "user_ruled_changed", "user_old_error",
            "user_disagree"}  # fmt: skip
    for row in review:
        if row["lane"] in send:
            claims.append((row["subject"], row["mechanism"], row["condition"], "existing_row"))
    for subject, obj in recheck.items():
        for m in obj["new_mechanisms"]:
            claims.append((subject, m["mechanism"], m["condition"], "proposed_new"))
    for obj in new_abilities["objects"]:
        for m in obj["mechanisms"]:
            if m["decision"] == "accept":
                claims.append((obj["subject"], m["mechanism"], m["condition"], "new_ability"))
    claims.append(("troll_warlord_battle_trance", "status_resistance", "base", "proposed_new"))
    field_only = {"effect_dispellability", "mana_cost", "magical_damage", "pure_damage",
                  "physical_damage", "break_sensitive", "unit_target_spell", "channeled",
                  "pierces_debuff_immunity"}  # fmt: skip
    seen, packet, key = set(), {}, []
    for subject, mechanism, condition, origin in claims:
        if mechanism in field_only or (subject, mechanism, condition) in seen:
            continue
        seen.add((subject, mechanism, condition))
        if subject not in packet:
            entry = new.get(subject, {})
            packet[subject] = {
                "subject": subject,
                "text_742": text(entry),
                "text_741f": text(old.get(subject)),
                "changed_fields": bp.changes(old.get(subject) or {}, entry),
                "patch_notes_742": notes.get(entry.get("id"), []),
                "claims": [],
            }
        claim_id = f"c{len(key) + 1:03d}"
        packet[subject]["claims"].append(
            {"claim_id": claim_id, "mechanism": mechanism, "condition": condition}
        )
        key.append({"claim_id": claim_id, "subject": subject, "mechanism": mechanism,
                    "condition": condition, "origin": origin})  # fmt: skip
    (OUT / "packet.json").write_text(
        json.dumps(list(packet.values()), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    (OUT / "claim-key.json").write_text(
        json.dumps(key, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print({"subjects": len(packet), "claims": len(key)})


if __name__ == "__main__":
    main()
