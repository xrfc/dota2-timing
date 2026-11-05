"""Turn U95-U98 into operations for facts v13. Run from repo root.

Terrain walking comes from three places: old flying rows, rows whose text says so, and jumps or
dashes (the user's general rule, U96, with the sorting done by Codex).
"""

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
AUDIT_006 = ROOT / "knowledge/mechanics/reviews/full-audit-006/results"
TARGET = ROOT / "knowledge/mechanics/reviews/terrain-rulings-001.jsonl"
sys.path.insert(0, str(ROOT / "src"))

from dota_items.data.mechanics_facts_v12 import condition_label  # noqa: E402

FLYING = (
    "batrider_firefly",
    "night_stalker_darkness",
    "rattletrap_jetpack",
    "visage_silent_as_the_grave",
    "winter_wyvern_arctic_burn",
)
# Rows whose own text says they cross terrain; a user ruling where the user named the skill.
STATED = {
    "broodmother_spin_web": None,
    "nyx_assassin_vendetta": None,
    "skeleton_king_vampiric_spirit": None,
    "lina_flame_cloak": None,
    "dragon_knight_elder_dragon_form": None,
    "spirit_breaker_charge_of_darkness": None,
    "pangolier_shield_crash": None,
    "spectre_spectral_dagger": None,
    "spectre_haunt": "U97",
    "wind_waker": "U96",
}
NAMED_DASHES = {
    "mirana_leap": "U96",
    "juggernaut_omni_slash": "U96",
    "sandking_burrowstrike": "U96",
    "phoenix_icarus_dive": "U96",
    "storm_spirit_ball_lightning": "U96",
    "sven_storm_bolt": "U96",
    "earthshaker_enchant_totem": "U96",
    "magnataur_skewer": "U98",
    "dawnbreaker_celestial_hammer": "U98",
    "sniper_concussive_grenade": "U98",
    "hoodwink_sharpshooter": "U98",
}
# The user said this is like a teleport; its text says Gyroshell stops at terrain.
NOT_TERRAIN = {"dawnbreaker_solar_guardian", "pangolier_gyroshell"}
EXTRA_KINDS = {"sniper_concussive_grenade", "hoodwink_sharpshooter"}


def op(subject, mechanism, decision, basis, note, condition=None, quote=""):
    return {
        "op": "set",
        "subject": subject,
        "mechanism": mechanism,
        "decision": decision,
        "basis": basis,
        "note_zh": note,
        "condition": condition,
        "quote": quote,
    }


def _results(folder):
    for path in sorted(glob.glob(str(folder / "batch-*.json"))):
        yield from json.loads(Path(path).read_text(encoding="utf-8"))["objects"]


def main():
    rows = json.loads(
        (ROOT / "knowledge/mechanics/extractions/v12/facts-v12.json").read_text(encoding="utf-8")
    )["rows"]
    self_moves = {}
    for row in rows:
        if row["mechanism"] == "self_mobility" and row["decision"] == "accept":
            self_moves.setdefault(row["subject"], set()).add(condition_label(row["condition"]))
    stated_quotes = {}
    for obj in _results(AUDIT_006):
        for item in obj["mechanisms"]:
            if item["mechanism"] == "terrain_walk":
                stated_quotes.setdefault(obj["subject"], []).append(item)
    ops = [
        {
            "op": "move",
            "subject": s,
            "mechanism": "flying",
            "new": "terrain_walk",
            "condition": None,
        }
        for s in FLYING
    ]
    done = {(s, condition_label(r["condition"])) for r in rows for s in FLYING if r["subject"] == s}
    for subject, ref in STATED.items():
        for item in stated_quotes[subject]:
            key = (subject, item["condition"])
            if key in done:
                continue
            done.add(key)
            basis = f"user:{ref}" if ref else "two_ai"
            note = "作用对象是幻象" if subject == "spectre_haunt" else "说明写明能越过地形"
            ops.append(
                op(subject, "terrain_walk", "accept", basis, note, item["condition"], item["quote"])
            )
    for obj in _results(OUT / "results"):
        subject = obj["subject"]
        if subject in NOT_TERRAIN:
            continue
        if "jump_dash" not in obj["kinds"] and subject not in EXTRA_KINDS:
            continue
        for condition in sorted(self_moves[subject]):
            key = (subject, condition)
            if key in done:
                continue
            done.add(key)
            ref = NAMED_DASHES.get(subject)
            basis = f"user:{ref}" if ref else "two_ai"
            ops.append(
                op(
                    subject,
                    "terrain_walk",
                    "accept",
                    basis,
                    "用户规则：跳跃和冲刺都无视地形（U96）；分类由Codex读说明完成",
                    condition,
                    obj["quote"],
                )
            )
    for subject in ("batrider_firefly", "spirit_breaker_charge_of_darkness"):
        ops.append(op(subject, "tree_walk", "reject", "user:U95", "能越过悬崖的归无视地形"))
    vision = (
        ("night_stalker_darkness", "base", "accept", "U95", "用户举的例子"),
        ("zuus_lightning_bolt", "base", "accept", "U97", ""),
        ("static_remnant", "base", "reject", "U97", "用户：残影没有高空视野"),
        ("puck_illusory_orb", "base", "accept", "U98", ""),
        ("treant_eyes_in_the_forest", "shard", "accept", "U98", ""),
        ("zuus_heavenly_jump", "base", "accept", "U98", ""),
        ("drow_ranger_glacier", "shard", "reject", "U98", "用户：冰川不算"),
    )
    quotes = {}
    for obj in _results(AUDIT_006):
        for item in obj["mechanisms"]:
            if item["mechanism"] == "high_ground_vision":
                quotes[obj["subject"]] = item["quote"]
    for subject, condition, decision, ref, note in vision:
        name = "storm_spirit_static_remnant" if subject == "static_remnant" else subject
        ops.append(
            op(
                name,
                "high_ground_vision",
                decision,
                f"user:{ref}",
                note or "用户确认算高空视野",
                condition,
                quotes.get(name, ""),
            )
        )
    ops.append(
        op(
            "rattletrap_jetpack",
            "high_ground_vision",
            "accept",
            "two_ai",
            "Codex读出，说明写了飞行视野；用户未单独确认",
            "shard",
            quotes["rattletrap_jetpack"],
        )
    )
    for subject in ("invoker_invoke", "nevermore_shadowraze1", "tusk_walrus_kick"):
        ops.append(
            op(subject, "cooldown_reduction", "reject", "user:U97", "只减这个技能自身，不算减冷却")
        )
    field_quote = "创造一个敌人无法通过的环形动能屏障"
    fence_quote = "创造一面敌人无法通过的动能墙壁"
    arena_quote = "战士们将阻挡敌人的攻击和动向"
    ops += [
        op("disruptor_kinetic_field", "terrain", "reject", "user:U97", "更像场地魔法"),
        op("disruptor_kinetic_fence", "terrain", "reject", "user:U98", "更像场地魔法"),
        op("mars_arena_of_blood", "terrain", "reject", "user:U97", "更像场地魔法"),
        op(
            "disruptor_kinetic_field",
            "ground_zone",
            "accept",
            "user:U98",
            "用户：减速圈",
            "base",
            field_quote,
        ),
        op(
            "disruptor_kinetic_fence",
            "ground_zone",
            "accept",
            "user:U98",
            "用户：记场地魔法",
            "shard",
            fence_quote,
        ),
        op("mars_arena_of_blood", "ground_zone", "accept", "user:U98", "用户：减速圈"),
        op(
            "disruptor_kinetic_field",
            "slow",
            "accept",
            "user:U98",
            "用户：减速圈；说明文字没写减速",
            "base",
            field_quote,
        ),
        op(
            "mars_arena_of_blood",
            "slow",
            "accept",
            "user:U98",
            "用户：减速圈；说明文字没写减速",
            "base",
            arena_quote,
        ),
        op(
            "bounty_hunter_wind_walk",
            "channel_interrupt",
            "reject",
            "user:U97",
            "算眩晕；所有眩晕都能打断施法",
        ),
        op("ringmaster_the_box", "mute", "reject", "user:U97", "本质是救人技能"),
        op("ringmaster_the_box", "disarm", "reject", "user:U97", "本质是救人技能"),
        op("tiny_toss", "displace_other", "accept", "user:U98", "投掷算强制位移"),
    ]
    TARGET.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in ops), encoding="utf-8"
    )
    print(len(ops), "operations")


if __name__ == "__main__":
    main()
