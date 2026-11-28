"""Exact patch, bounded collection and independent identity evidence regressions."""

import hashlib
import json
from copy import deepcopy

import pytest

from dota_items.contracts.replay_collection import (
    OFFICIAL_PATCH_URL,
    PatchWindow,
    validate_match_metadata,
)
from dota_items.data.patch_time import classify_patch_time, load_patch_window


def snapshot():
    return json.dumps(
        {
            "patches": [
                {"patch_number": "7.41f", "patch_timestamp": 10000},
                {"patch_number": "7.42", "patch_timestamp": 20000},
                {"patch_number": "7.42a", "patch_timestamp": 30000},
            ]
        }
    ).encode()


def window(patch="7.41f", source=None):
    return PatchWindow.from_snapshot(
        snapshot() if source is None else source,
        patch=patch,
        retrieved_at="1970-01-01T10:00:00+00:00",
        boundary_buffer_seconds=100,
    )


def records():
    discovery = {
        "match_id": 9_100_000_001,
        "avg_rank_tier": 75,
        "start_time": 12000,
        "duration": 1000,
    }
    meta = {
        **discovery,
        "patch": 61,
        "lobby_type": 7,
        "game_mode": 22,
        "players": [
            {"player_slot": slot, "hero_id": index + 1}
            for index, slot in enumerate([*range(5), *range(128, 133)])
        ],
    }
    return meta, discovery


def test_exact_letter_patch_and_snapshot_bytes_remain_distinct():
    plain, letter = window("7.42"), window("7.42a")
    assert plain.upper_exclusive == letter.release_timestamp == 30000
    assert plain.upper_kind == "next_release"
    assert letter.upper_kind == "snapshot_retrieval"
    assert letter.upper_exclusive == 36000
    assert plain.snapshot_sha256 == hashlib.sha256(snapshot()).hexdigest()
    assert window("7.42", snapshot() + b"\n").snapshot_sha256 != plain.snapshot_sha256
    assert PatchWindow.from_dict(plain.to_dict()) == plain
    assert "opendota_patch" not in plain.to_dict()
    assert "game_build" not in plain.to_dict()
    with pytest.raises(ValueError, match="exact patch absent"):
        window("7.42b")


@pytest.mark.parametrize("change", ["name", "time", "future", "bool", "negative", "empty"])
def test_ambiguous_or_invalid_official_release_records_fail_closed(change):
    document = json.loads(snapshot())
    if change == "name":
        document["patches"][2]["patch_number"] = "7.42"
    elif change == "time":
        document["patches"][2]["patch_timestamp"] = 20000
    elif change == "future":
        document["patches"][2]["patch_timestamp"] = 36001
    elif change == "bool":
        document["patches"][2]["patch_timestamp"] = True
    elif change == "negative":
        document["patches"][2]["patch_timestamp"] = -1
    else:
        document["patches"] = []
    with pytest.raises(ValueError):
        window(source=json.dumps(document).encode())


@pytest.mark.parametrize(
    "source", [b"{}", b"[]", b"null", b"not json", b'{"patches":[],"patches":[]}']
)
def test_malformed_or_duplicate_key_snapshot_rejected(source):
    with pytest.raises(ValueError):
        window(source=source)


@pytest.mark.parametrize(
    "change",
    [
        {"snapshot_sha256": "a" * 63},
        {"snapshot_sha256": "A" * 64},
        {"retrieved_at": "1970-01-01T10:00:00"},
        {"source_url": "https://example.invalid/patches"},
        {"upper_kind": "latest_forever"},
        {"boundary_buffer_seconds": True},
        {"boundary_buffer_seconds": -1},
        {"release_timestamp": 20000},
        {"upper_exclusive": 36001},
        {"extra": "unrecognized"},
    ],
)
def test_stored_contract_rejects_invalid_identity(change):
    saved = window().to_dict()
    saved.update(change)
    with pytest.raises(ValueError):
        PatchWindow.from_dict(saved)


@pytest.mark.parametrize(
    "start,duration",
    [
        (None, 100),
        (True, 100),
        (9999, 100),
        (20000, 100),
        (10000, 100),
        (10100, 100),
        (18000, 1900),
        (18000, 2000),
        (10100, True),
        (10100, -1),
    ],
)
def test_existing_patch_time_semantics_are_preserved(tmp_path, start, duration):
    source = tmp_path / "patches.json"
    source.write_bytes(snapshot())
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "patch-time-evidence/1",
                "source_url": OFFICIAL_PATCH_URL,
                "snapshot": source.name,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "retrieved_at": "1970-01-01T10:00:00+00:00",
                "boundary_buffer_seconds": 100,
            }
        )
    )
    previous = classify_patch_time(start, duration, load_patch_window(receipt, "7.41f"))
    expected = [] if previous == "time_consistent" else [previous]
    assert window().match_time_reasons(start, duration) == expected


def test_selection_checks_start_and_end_before_metadata_enrichment():
    value = window()
    bounds = value.discovery_bounds(now=36000)
    assert bounds == {"start_lower": 10100, "start_upper": 19900, "end_upper": 19900}
    assert value.match_time_reasons(18000, 1899, bounds) == []
    assert "outside_selection_window" in value.match_time_reasons(18000, 1900, bounds)
    assert "outside_selection_window" in value.match_time_reasons(10099, 900, bounds)
    with pytest.raises(ValueError, match="empty or widened"):
        value.discovery_bounds(now=500000)
    with pytest.raises(ValueError, match="empty or widened"):
        value.match_time_reasons(12000, 1000, {**bounds, "end_upper": 20000})


def test_age_limit_does_not_become_a_match_end_limit():
    document = json.loads(snapshot())
    document["patches"].pop()
    value = window("7.42", json.dumps(document).encode())
    bounds = value.discovery_bounds(now=36000)
    assert bounds["start_upper"] == 28800
    assert bounds["end_upper"] == 36000
    # Starts more than two hours ago, finishes more recently, still on this snapshot.
    assert value.match_time_reasons(28000, 3000, bounds) == []
    assert value.match_time_reasons(28000, 8000, bounds) == ["crosses_upper_boundary"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"now": True},
        {"now": 35999},
        {"now": 36000, "min_age_hours": True},
        {"now": 36000, "max_age_hours": float("inf")},
        {"now": 36000, "max_age_hours": 1e308},
        {"now": 36000, "max_age_hours": 10**400},
        {"now": 36000, "min_age_hours": -1},
        {"now": 36000, "min_age_hours": 96},
    ],
)
def test_invalid_selection_policy_rejected(kwargs):
    with pytest.raises(ValueError):
        window().discovery_bounds(**kwargs)


def test_metadata_keeps_numeric_patch_independent_and_allows_unknown_metadata_rank():
    meta, discovery = records()
    meta["avg_rank_tier"] = None
    # A label/code mapping is never invented from the requested patch's spelling.
    assert validate_match_metadata(meta, discovery, window()) == []
    assert validate_match_metadata(meta, discovery, window(), expected_patch_code=61) == []
    assert validate_match_metadata(meta, discovery, window(), expected_patch_code=60) == [
        "metadata_patch_mismatch"
    ]


@pytest.mark.parametrize(
    "key,value,reason",
    [
        ("match_id", 9_100_000_002, "match_id_mismatch"),
        ("match_id", True, "invalid_match_id"),
        ("patch", None, "metadata_patch_missing_or_invalid"),
        ("patch", True, "metadata_patch_missing_or_invalid"),
        ("patch", -61, "metadata_patch_missing_or_invalid"),
        ("duration", 500, "duration_missing_or_below_threshold"),
        ("duration", True, "unknown_time"),
        ("start_time", 12001, "discovery_metadata_time_mismatch"),
        ("start_time", None, "unknown_time"),
        ("avg_rank_tier", 69, "metadata_rank_below_threshold_or_invalid"),
        ("lobby_type", 0, "not_ranked_all_pick"),
        ("game_mode", 1, "not_ranked_all_pick"),
        ("game_mode", 22.0, "not_ranked_all_pick"),
    ],
)
def test_metadata_mismatch_is_not_silently_accepted(key, value, reason):
    meta, discovery = records()
    meta[key] = value
    assert reason in validate_match_metadata(meta, discovery, window())


@pytest.mark.parametrize("rank", [None, True, float("nan"), "75", 69])
def test_discovery_rank_must_supply_finite_threshold_evidence(rank):
    meta, discovery = records()
    discovery["avg_rank_tier"] = rank
    assert "discovery_rank_missing_or_below_threshold" in validate_match_metadata(
        meta, discovery, window()
    )


@pytest.mark.parametrize("change", ["short", "slot", "hero", "nonobject", "badhero"])
def test_ten_distinct_heroes_and_slots_are_required(change):
    meta, discovery = records()
    if change == "short":
        meta["players"].pop()
    elif change == "slot":
        meta["players"][-1]["player_slot"] = 128
    elif change == "hero":
        meta["players"][-1]["hero_id"] = 1
    elif change == "nonobject":
        meta["players"][-1] = None
    else:
        meta["players"][-1]["hero_id"] = {}
    assert validate_match_metadata(meta, discovery, window())


def test_validation_has_no_mutation_or_hidden_holdout_policy():
    meta, discovery = records()
    original = deepcopy((meta, discovery))
    assert (
        validate_match_metadata(
            meta, discovery, window(), bounds=window().discovery_bounds(now=36000)
        )
        == []
    )
    assert (meta, discovery) == original
    assert not hasattr(window(), "supports_model")
