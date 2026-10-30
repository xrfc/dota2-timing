"""M1 match table: manifest-verified loading and coverage inventory."""

import hashlib
import json

import pytest

from dota_items.data.match_table import inventory, load_match, match_files


def player(hero, tier=54, lane_role=1, **extra):
    base = {
        "hero_id": hero,
        "rank_tier": tier,
        "lane_role": lane_role,
        "leaver_status": 0,
        "purchase_log": [],
        "lh_t": [0],
        "dn_t": [0],
        "gold_t": [0],
        "xp_t": [0],
        "kills_log": [],
        "lane_efficiency_pct": 50,
    }
    return base | extra


def store(root, match_id, match, *, tamper=False, manifest=True):
    folder = root / "batch-0001/matches"
    folder.mkdir(parents=True, exist_ok=True)
    data = json.dumps({"match_id": match_id, **match}).encode()
    (folder / f"{match_id}.json").write_bytes(data + (b" " if tamper else b""))
    if manifest:
        meta = {"match_id": match_id, "sha256": hashlib.sha256(data).hexdigest()}
        (folder / f"{match_id}.manifest.json").write_text(json.dumps(meta))


def test_inventory_counts_coverage_without_filtering(tmp_path):
    store(tmp_path, 1, {"patch": 60, "duration": 2400, "players": [player(8), player(5, 82)]})
    store(
        tmp_path, 2, {"patch": 60, "duration": 700, "players": [player(8, None, None, lh_t=None)]}
    )
    matches = [load_match(*pair) for pair in match_files([tmp_path])]
    result = inventory(matches)
    assert result["matches"] == result["unique_matches"] == 2
    assert result["players"] == 3 and result["distinct_heroes"] == 2
    assert result["counts"]["rank"] == {"None": 1, "immortal": 1, "legend": 1}
    assert result["counts"]["duration_bucket_min"] == {"10": 1, "40": 1}
    assert result["missing_player_fields"] == {"lane_role": 1, "lh_t": 1}
    assert result["hero_player_counts"] == {"5": 1, "8": 2}


def test_tampered_or_unmanifested_files_rejected(tmp_path):
    store(tmp_path / "a", 1, {"players": []}, tamper=True)
    store(tmp_path / "b", 2, {"players": []}, manifest=False)
    for root in ("a", "b"):
        ((path, manifest),) = match_files([tmp_path / root])
        with pytest.raises(ValueError):
            load_match(path, manifest)


def test_identity_mismatch_rejected(tmp_path):
    store(tmp_path, 3, {"players": []})
    path = tmp_path / "batch-0001/matches/3.json"
    renamed = path.with_name("4.json")
    path.rename(renamed)
    (path.with_name("3.manifest.json")).rename(path.with_name("4.manifest.json"))
    with pytest.raises(ValueError, match="identity"):
        load_match(renamed, renamed.with_name("4.manifest.json"))


def parsed_match():
    def full(slot, hero, kills=(), deaths=(), purchases=()):
        return player(
            hero,
            player_slot=slot,
            lh_t=list(range(0, 60, 2)),
            dn_t=[0] * 30,
            gold_t=[i * 100 for i in range(30)],
            xp_t=[i * 150 for i in range(30)],
            kills_log=[{"time": t, "key": "x"} for t in kills],
            deaths_log=[{"time": t, "key": "y"} for t in deaths],
            purchase_log=[{"time": t, "key": k} for t, k in purchases],
            win=1 if slot < 128 else 0,
            lane=1,
        )

    players = [full(s, 10 + s) for s in range(1, 5)] + [full(s, 20 + s) for s in range(128, 133)]
    players.insert(
        0,
        full(0, 8, kills=(83, 599, 600), deaths=(300,), purchases=((-89, "tango"), (900, "bfury"))),
    )
    return {"match_id": 9, "start_time": 1, "patch": 60, "duration": 2000, "players": players}


def test_player_rows_lane_window_and_columns():
    from dota_items.data.match_table import FIELD_AVAILABILITY, player_rows, purchase_rows

    rows = player_rows(parsed_match())
    assert len(rows) == 10 and all(set(r) == set(FIELD_AVAILABILITY) for r in rows)
    jug = rows[0]
    # Kills at 599s count, 600s does not: the lane window is [0, 600).
    assert (jug["kills_10"], jug["deaths_10"]) == (2, 1)
    assert (jug["lh_10"], jug["gold_10"], jug["xp_10"]) == (20, 1000, 1500)
    assert jug["is_radiant"] and jug["win"] and not rows[-1]["win"]
    assert jug["avg_rank_tier"] == 54.0
    purchases = purchase_rows(parsed_match())
    assert [(p["time_s"], p["item"]) for p in purchases] == [(-89, "tango"), (900, "bfury")]


def test_unparsed_match_rejected():
    from dota_items.data.match_table import fully_parsed, player_rows

    match = parsed_match()
    match["players"][3]["purchase_log"] = None
    assert not fully_parsed(match)
    with pytest.raises(ValueError):
        player_rows(match)
