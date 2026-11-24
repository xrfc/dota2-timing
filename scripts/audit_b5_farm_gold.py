"""Reconcile two recorded gold sources on the three B5 replays and existing wave windows."""

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from dota_items.sources.gem_capture import require_complete_parse
from dota_items.sources.gem_capture_v3 import _name

ROOT = Path(__file__).resolve().parents[1]
KINDS = {13: "creep", 14: "neutral"}
FIELDS = (
    "m_iCreepKillGold",
    "m_iNeutralKillGold",
    "m_iIncomeGold",
    "m_iReliableGold",
    "m_iUnreliableGold",
)
COMPAT = "3f6e9ee2c222869adce45c6dfef757e719c9576bfdde82927e76d6868c47403d"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require_hash(path, expected):
    if digest(path) != expected:
        raise ValueError(f"input fingerprint mismatch: {path}")


def capture(path, cases, offsets=(6, 7, 20, 21)):
    import gem
    from gem.extractors.players import PlayerExtractor
    from gem.parser import ReplayParser

    root = Path(gem.__file__).resolve().parent
    manifest = root.parent / "manifest.json"
    require_hash(manifest, COMPAT)
    for name, sha in json.loads(manifest.read_bytes())["patched"].items():
        require_hash(root / name, sha)

    parser = ReplayParser(str(path))
    players = PlayerExtractor()
    players.attach(parser)
    needed = {(hero, t + offset) for hero, t in cases for offset in offsets}
    boundaries, final, recipients, events = {}, {}, {}, []
    types = Counter()
    last = None

    def sample(_tick):
        nonlocal last
        t = parser.game_time_s
        em = parser.entity_manager
        if em is None or t is None or t < 0 or t == last:
            return
        last = t
        teams = {
            2: em.find_by_class_name("CDOTA_DataRadiant"),
            3: em.find_by_class_name("CDOTA_DataDire"),
        }
        names = parser.string_tables.get_by_name("EntityNames")
        for pid in range(10):
            entity = players._canonical_hero_entity(pid)
            if entity is None:
                continue
            hero = _name(entity, names)
            team = entity.get("m_iTeamNum")
            slot = players._player_team_slot.get(pid)
            if not hero or slot is None or teams.get(team) is None:
                continue
            ident = team, slot
            if recipients.setdefault(hero, ident) != ident:
                raise ValueError(f"team slot changed for {hero}")
            row = [teams[team].get(f"m_vecDataTeam.{slot:04d}.{f}") for f in FIELDS]
            final[hero] = row
            if (hero, t) in needed:
                if (hero, t) in boundaries:
                    raise ValueError(f"repeated endpoint {hero} at {t}")
                boundaries[hero, t] = row

    def combat(entry):
        if entry.log_type == "GOLD":
            types[entry.gold_reason] += 1
            if entry.gold_reason in KINDS:
                events.append((entry.tick, entry.target_name, entry.gold_reason, entry.value))

    parser.on_tick_start(sample)
    parser.on_combat_log_entry(combat)
    parser.parse()
    require_complete_parse(parser)
    if len(recipients) != 10 or len(set(recipients.values())) != 10:
        raise ValueError("incomplete gold recipient to team-slot mapping")
    if any(hero not in recipients for _, hero, _, _ in events):
        raise ValueError("unknown farm gold recipient")
    timed = [
        (parser.game_clock.game_seconds_at(tick), tick, hero, reason, amount)
        for tick, hero, reason, amount in events
    ]
    if any(t is None for t, *_ in timed):
        raise ValueError("game clock unavailable for farm event")
    return parser.match_id, types, timed, recipients, boundaries, final


def delta(start, end):
    return end - start if start is not None and end is not None else None


def read_deaths(normalized, teams):
    deaths = defaultdict(set)
    rows = normalized["context"]["channels"]["combat_log"]
    for row in rows:
        p = row["payload"]
        a = p.get("attacker_name")
        if p["log_type"] != "DEATH" or a not in teams or p.get("attacker_is_illusion"):
            continue
        target = p.get("target_name") or ""
        enemy = "goodguys" if teams[a][0] == 3 else "badguys"
        if target.startswith("npc_dota_neutral_"):
            deaths[a, row["source_tick"]].add("neutral")
        elif target.startswith((f"npc_dota_creep_{enemy}_", f"npc_dota_{enemy}_siege")):
            deaths[a, row["source_tick"]].add("creep")
    return deaths, sum(r["payload"]["log_type"] == "GOLD" for r in rows)


def window(hero, t, events, boundaries):
    actual = [(s, KINDS[r], v) for s, _, h, r, v in events if h == hero and t + 6 < s <= t + 20]
    totals = Counter()
    for _, kind, amount in actual:
        totals[kind] += amount
    start, end = (boundaries.get((hero, t + d), [None] * len(FIELDS)) for d in (6, 20))
    creep, neutral, income, reliable, unreliable = map(delta, start, end)
    # Tick-start snapshots at the opening of seconds 7 and 21 bracket seconds 7..20.
    opening, closing = (boundaries.get((hero, t + d), [None] * len(FIELDS)) for d in (7, 21))
    return dict(
        aligned_counter_creep=delta(opening[0], closing[0]),
        aligned_counter_neutral=delta(opening[1], closing[1]),
        hero=hero,
        t=t,
        gold_events=actual,
        logged_creep=totals["creep"],
        logged_neutral=totals["neutral"],
        counter_creep=creep,
        counter_neutral=neutral,
        income_counter=income,
        cash_change=None if reliable is None or unreliable is None else reliable + unreliable,
    )


def audit(demo, inputs):
    probes = json.loads((ROOT / "configs/acceptance/b5-gold-probes.json").read_bytes())
    mid = demo.stem
    if mid not in probes:
        raise ValueError("expected one of the three registered B5 replay files")
    config = probes[mid]
    receipt_path = inputs / "replay-provenance.json"
    require_hash(receipt_path, config["provenance_sha256"])
    receipt = json.loads(receipt_path.read_bytes())
    if receipt["match_id"] != int(mid) or receipt["compat_manifest_sha256"] != COMPAT:
        raise ValueError("wrong replay provenance")
    require_hash(demo, receipt["source_sha256"])
    normalized_path = f"parsed/{mid}.normalized.json.gz"
    require_hash(inputs / normalized_path, receipt["inputs_sha256"][normalized_path])
    with gzip.open(inputs / normalized_path) as stream:
        normalized = json.load(stream)
    match_id, types, events, teams, boundaries, final = capture(demo, config["wave_cases"])
    if match_id != int(mid) or normalized["match_id"] != match_id:
        raise ValueError("match identity mismatch")
    deaths, normalized_gold = read_deaths(normalized, teams)
    same_tick = Counter()
    sums = defaultdict(Counter)
    for _, tick, hero, r, value in events:
        kind = KINDS[r]
        sums[hero][kind] += value
        if kind in deaths.get((hero, tick), ()):
            same_tick[kind] += 1
    totals = {}
    for hero, fields in sorted(final.items()):
        totals[hero] = dict(
            logged_creep=sums[hero]["creep"],
            counter_creep=fields[0],
            logged_neutral=sums[hero]["neutral"],
            counter_neutral=fields[1],
        )
    return dict(
        schema="b5-farm-gold-audit/1",
        match=mid,
        source_sha256=receipt["source_sha256"],
        provenance_sha256=config["provenance_sha256"],
        compat_sha256=COMPAT,
        normalized_gold_events=normalized_gold,
        raw_gold_by_reason=dict(sorted(types.items())),
        same_tick_hero_and_unit_class=dict(same_tick),
        players=totals,
        windows=[window(h, t, events, boundaries) for h, t in config["wave_cases"]],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("demo", type=Path)
    parser.add_argument("inputs", type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.demo, args.inputs)
    except (OSError, ValueError, KeyError, ImportError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
