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


def safelane_rows(radiant_lh, dire_lh=((100, 50), (10, 5))):
    rows = []
    for radiant, pair in ((True, radiant_lh), (False, dire_lh)):
        for i, (lh15, lh10) in enumerate(pair):
            rows.append(
                {
                    "match_id": 1,
                    "is_radiant": radiant,
                    "player_slot": i if radiant else 128 + i,
                    "lane_role": 1,
                    "lh_15": lh15,
                    "lh_10": lh10,
                }
            )
    rows.append(
        {
            "match_id": 1,
            "is_radiant": True,
            "player_slot": 2,
            "lane_role": 2,
            "lh_15": 150,
            "lh_10": 80,
        }
    )
    return rows


def test_positions_by_15_minute_last_hits_with_gap_and_collapse():
    from dota_items.data.match_table import assign_positions

    rows = assign_positions(safelane_rows([(10, 5), (95, 34)], [(60, 40), (36, 20)]))
    got = {r["player_slot"]: (r["position"], r["collapsed_carry"]) for r in rows}
    assert got[1] == (1, True)  # 34 < 35 at minute 10: collapsed but still position 1
    assert got[0] == (5, False)
    assert got[128] == got[129] == (None, False)  # gap 24 < 25 -> unknown
    assert got[2] == (None, False)  # mid is out of scope


def test_non_pair_safelane_is_unknown_and_input_untouched():
    from dota_items.data.match_table import assign_positions

    rows = safelane_rows([(100, 50), (10, 5)])
    rows.append({**rows[0], "player_slot": 3})
    before = [dict(r) for r in rows]
    result = assign_positions(rows)
    assert all(r["position"] is None for r in result if r["is_radiant"])
    assert rows == before


def test_every_column_has_availability_and_pre_game_view_ignores_later_fields():
    from dota_items.data.match_table import (
        assign_positions,
        availability,
        player_rows,
        pre_game_view,
    )

    rows = assign_positions(player_rows(parsed_match()))
    for row in rows:
        for column in row:
            assert availability(column) in {
                "identifier",
                "pre_game",
                "lane_end",
                "minute_15",
                "post_game",
            }
    original = pre_game_view(rows[0])
    later = {k: v for k, v in rows[0].items() if k not in original}
    assert {"lh_10", "win", "position", "duration_s"} <= set(later)
    perturbed = {**rows[0], **{k: "changed" for k in later}}
    assert pre_game_view(perturbed) == original


def test_time_split_is_by_whole_match_and_newest_validate():
    from dota_items.data.match_table import time_split

    starts = {10: 500, 11: 100, 12: 300, 13: 300, 14: 900}
    split = time_split(starts, 0.4)
    assert split["validation"] == [10, 14]
    assert split["train"] == [11, 12, 13]
    assert split["train_last_start"] < split["validation_first_start"]
    assert not set(split["train"]) & set(split["validation"])


def snapshot_repo(tmp_path):
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("bmt", root / "scripts/build_match_table.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    repo = tmp_path / "repo"
    data = repo / "data/src"
    for match_id, start in ((21, 300), (22, 100), (23, 200), (24, 400), (25, 500)):
        match = parsed_match()
        match.pop("match_id")
        store(data, match_id, {**match, "start_time": start})
    store(data, 26, {"start_time": 50, "players": [player(1, purchase_log=None)] * 10})
    for name in module.IMPLEMENTATION:
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text("fixture")
    return module, repo


def test_snapshot_verify_roundtrip_and_drift_detection(tmp_path):
    module, repo = snapshot_repo(tmp_path)
    out = repo / "reports/snap"
    result = module.run_snapshot(out, ("data/src",), repo)
    assert result == {
        "matches": 5,
        "player_rows": 50,
        "purchase_rows": 10,
        "train": 4,
        "validation": 1,
    }
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["excluded_unparsed_match_ids"] == [26]
    assert json.loads((out / "split.json").read_text())["validation"] == [25]
    header = (out / "players.csv").read_text().splitlines()[0].split(",")
    assert {"position", "collapsed_carry", "lh_15"} <= set(header)
    assert module.run_verify(out, repo) == {"snapshot": str(out), "ok": True, "problems": []}
    (out / "split.json").write_text("{}")
    extra = {k: v for k, v in parsed_match().items() if k != "match_id"}
    store(repo / "data/src", 27, {**extra, "start_time": 600})
    problems = module.run_verify(out, repo)["problems"]
    assert "stored_output_changed:split.json" in problems
    assert "inputs_changed" in problems
    with pytest.raises(ValueError, match="exists"):
        module.run_snapshot(out, ("data/src",), repo)
