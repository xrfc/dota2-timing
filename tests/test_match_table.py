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
