"""Turn the audits and the U83 rulings into one adoption list for facts v11. Run from repo root."""

import glob
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
A1 = OUT.parent / "full-audit-001"
TARGET = OUT.parent / "audit-adoptions-001.jsonl"
FACTS = OUT.parents[1] / "extractions/v10/facts-v10.json"
CONTEXT = {"base": "base", "item": "item", "scepter_upgrade": "scepter", "shard_upgrade": "shard"}
REF = "U83"
U = f"user:{REF}"

# (subject, mechanism, condition, decision, note)
RULINGS = [
    ("naga_siren_song_of_the_siren", "sleep", "base", "accept", "用户裁定：算睡眠"),
    ("naga_siren_song_of_the_siren", "healing", "shard", "accept", "用户裁定：算回复"),
    ("naga_siren_song_of_the_siren", "cyclone_banish", "base", "reject", "用户裁定：不算吹风/放逐"),
    ("rattletrap_power_cogs", "displace_other", "base", "accept", "用户裁定：是强制位移"),
    ("rattletrap_power_cogs", "mobility_lock", "base", "reject", "用户裁定：不限制位移"),
    ("troll_warlord_battle_trance", "forced_action", "base", "accept", "用户确认：强迫自身攻击"),
    ("troll_warlord_battle_trance", "death_prevention", "base", "accept", "用户裁定：还有免死"),
    ("bounty_hunter_track", "reveal", "base", "accept", "用户裁定：算显形"),
    ("broodmother_spin_web", "phased", "base", "accept", "用户裁定：算相位移动"),
    ("spirit_breaker_planar_pocket", "spell_block", "shard", "reject", "用户裁定：不算格挡"),
    ("shadow_demon_disseminate", "damage_return", "base", "accept", "用户裁定：算反伤"),
    ("warlock_fatal_bonds", "damage_return", "base", "reject", "用户裁定：不算反伤"),
    ("monkey_king_wukongs_command", "summons", "base", "reject", "用户裁定：不算召唤物"),
    ("tinker_deploy_turrets", "summons", "base", "reject", "用户裁定：不算召唤物"),
    ("invoker_ice_wall", "ground_zone", "base", "accept", "用户确认的例子"),
    ("ringmaster_whoopee_cushion", "ground_zone", "base", "accept", "用户确认的例子"),
    ("riki_smoke_screen", "ground_zone", "base", "accept", "用户确认的例子"),
]
# Claude-only proposals the user did not object to. Not user confirmation.
NO_OBJECTION = {
    ("arc_warden_tempest_double", "summons", "base"),
    ("crystal_maiden_freezing_field", "root", "scepter"),
    ("death_prophet_exorcism", "aoe_damage", "base"),
    ("faceless_void_chronosphere", "stun", "base"),
    ("faceless_void_time_lock", "bash", "base"),
    ("furion_sprout", "mobility_lock", "base"),
    ("life_stealer_infest", "invulnerable_untargetable", "base"),
    ("medusa_cold_blooded", "stun", "shard"),
    ("monkey_king_wukongs_command", "aoe_damage", "base"),
    ("necrolyte_sadist", "healing", "base"),
    ("storm_spirit_ball_lightning", "aoe_damage", "base"),
    ("tidehunter_dead_in_the_water", "root", "shard"),
    ("travel_boots", "self_mobility", "base"),
    ("tusk_ice_shards", "mobility_lock", "base"),
    ("tusk_walrus_punch", "stun", "base"),
    ("viper_nose_dive", "aoe_damage", "scepter"),
    ("void_spirit_dissimilate", "invulnerable_untargetable", "base"),
    ("winter_wyvern_winters_curse", "applies_basic_dispel", "base"),
    ("winter_wyvern_winters_curse", "invulnerable_untargetable", "base"),
    ("winter_wyvern_winters_curse", "stun", "base"),
}
# Codex round 2 flagged these as ground_zone; Claude does not accept them.
ZONE_REJECT = {
    "disruptor_kinetic_field",
    "disruptor_kinetic_fence",
    "earthshaker_fissure",
    "rattletrap_power_cogs",
    "furion_sprout",  # blocking only; asked separately
    "invoker_emp",
    "leshrac_split_earth",
    "undying_tombstone",
    "void_spirit_aether_remnant",
    "winter_wyvern_winters_curse",
    "zuus_cloud",
}
# Uncertain in Codex round 2, accepted after Claude read the text.
ZONE_UNCERTAIN_OK = {"enigma_midnight_pulse", "viper_nose_dive"}
# Codex round 2 attack_modifier rows Claude accepts beyond round 1.
ATTACK_OK = {
    "batrider_sticky_napalm",
    "dawnbreaker_luminosity",
    "drow_ranger_marksmanship",
    "echo_sabre",
    "hoodwink_acorn_shot",
    "invis_sword",
    "invoker_forge_spirit",
    "jakiro_double_trouble",
    "kez_shodo_sai",
    "kez_switch_weapons",
    "marci_unleash",
    "phantom_lancer_juxtapose",
    "riki_blink_strike",
    "riki_innate_backstab",
    "silver_edge",
    "sniper_headshot",
    "sniper_keen_scope",
    "specialists_array",
    "templar_assassin_meld",
    "troll_warlord_berserkers_rage",
    "drow_ranger_frost_arrows",
    "viper_poison_attack",
    "zuus_lightning_hands",
}
AURA_TO_ZONE = {
    "ancient_apparition_ice_vortex",
    "arc_warden_magnetic_field",
    "broodmother_spin_web",
    "dark_seer_surge",
    "drow_ranger_glacier",
    "dust",
    "invoker_ice_wall",
    "lich_ice_spire",
    "muerta_the_calling",
    "oracle_rain_of_destiny",
    "riki_smoke_screen",
    "ringmaster_spotlight",
    "ringmaster_wheel",
    "ringmaster_whoopee_cushion",
    "slark_depth_shroud",
    "techies_minefield_sign",
}


def main():
    data = json.loads((A1 / "comparison.json").read_text(encoding="utf-8"))["buckets"]
    triage = json.loads((A1 / "triage.json").read_text(encoding="utf-8"))
    items = {
        o["subject"]
        for o in json.loads((A1 / "objects.json").read_text(encoding="utf-8"))
        if o.get("is_item")
    }
    quotes = {}
    for bucket in data.values():
        for row in bucket:
            key = (row["subject"], row["mechanism"], row["condition"])
            quotes[key] = row["claude_quote"] or row["codex_quote"] or ""
    existing = {
        (row["subject"], row["mechanism"], CONTEXT[row["condition"]["context"]])
        for row in json.loads(FACTS.read_text(encoding="utf-8"))["rows"]
    }
    entries = {}

    def put(subject, mechanism, condition, decision, basis, origin, note, quote):
        if subject in items and condition == "base":
            condition = "item"
        key = (subject, mechanism, condition)
        if not basis.startswith("user:") and (key in entries or key in existing):
            return
        entries[key] = {
            "kind": "row",
            "subject": subject,
            "mechanism": mechanism,
            "condition": condition,
            "decision": decision,
            "basis": basis,
            "origin": origin,
            "note_zh": note,
            "quote": quote,
            "date": "2026-11-04",
        }

    for subject, mechanism, condition, decision, note in RULINGS:
        put(
            subject,
            mechanism,
            condition,
            decision,
            U,
            "user_ruling",
            note,
            quotes.get((subject, mechanism, condition), ""),
        )
    both = "两边各自读说明都提出（U81）"
    sequential = "Codex提出，Claude看过其依据后认同，不是盲审（U81）"
    for row in data["new_both"]:
        put(
            row["subject"],
            row["mechanism"],
            row["condition"],
            "accept",
            "two_ai",
            "full_audit_both",
            both,
            row["claude_quote"] or row["codex_quote"],
        )
    groups = [triage["agree"], *triage["hold"].values()]
    for group in groups:
        for row in group:
            mechanism = row["mechanism"]
            if mechanism == "aura" and row["subject"] in AURA_TO_ZONE:
                mechanism = "ground_zone"
            put(
                row["subject"],
                mechanism,
                row["condition"],
                "accept",
                "two_ai",
                "full_audit_sequential",
                sequential,
                row["codex_quote"],
            )
    for subject, mechanism, condition in sorted(NO_OBJECTION):
        put(
            subject,
            mechanism,
            condition,
            "accept",
            f"assistant_no_objection:{REF}",
            "assistant_proposal",
            "助手提议，用户未提出异议，不算用户确认",
            quotes[(subject, mechanism, condition)],
        )
    round2 = "第二轮：Codex提出，Claude看过其依据后认同，不是盲审（U83）"
    for path in sorted(glob.glob(str(OUT / "results/batch-*.json"))):
        for obj in json.loads(Path(path).read_text(encoding="utf-8"))["objects"]:
            subject = obj["subject"]
            for found in obj["mechanisms"]:
                condition = "base" if found["condition"] == "item" else found["condition"]
                if found["mechanism"] == "ground_zone":
                    keep = subject not in ZONE_REJECT and (
                        not found["uncertain"] or subject in ZONE_UNCERTAIN_OK
                    )
                else:
                    keep = subject in ATTACK_OK and not found["uncertain"]
                if keep:
                    put(
                        subject,
                        found["mechanism"],
                        condition,
                        "accept",
                        "two_ai",
                        "full_audit_round2",
                        round2,
                        found["quote"],
                    )
    note = {
        "kind": "note",
        "subject": "spirit_breaker_planar_pocket",
        "mechanism": "spell_redirect",
        "note_zh": "让指向性技能转向裂魂人，类似抵消技能的效果，不算格挡",
        "decision_ref": REF,
    }
    lines = [json.dumps(e, ensure_ascii=False) for _, e in sorted(entries.items())]
    lines.append(json.dumps(note, ensure_ascii=False))
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(len(entries))


if __name__ == "__main__":
    main()
