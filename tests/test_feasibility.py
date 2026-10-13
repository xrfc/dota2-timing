"""Feasibility must preserve missingness and every attempted input's outcome."""

import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from dota_items.data.feasibility import AuditConfig, audit_paths
from dota_items.data.feasibility_cli import main
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def match():
    return {
        "match_id": 123,
        "duration": 2000,
        "patch": 59,
        "_fixture": "synthetic",
        "players": [
            {"player_slot": slot, "hero_id": hero, "purchase_log": []}
            for slot, hero in zip(
                [0, 1, 2, 3, 4, 128, 129, 130, 131, 132],
                [8, 2, 3, 4, 5, 6, 7, 9, 10, 11],
                strict=True,
            )
        ],
    }


def save(tmp_path, match, name="match.json"):
    path = tmp_path / name
    path.write_text(json.dumps(match), encoding="utf-8")
    return path


def audit(tmp_path, match):
    return audit_paths([save(tmp_path, match)], AuditConfig())


@pytest.mark.parametrize("log", [None, [], "invalid"])
def test_absence_never_becomes_negative_or_completion_label(tmp_path, match, log):
    target = match["players"][0]
    target["purchase_log"] = log
    target.update({f"item_{i}": 147 for i in range(6)})
    result = audit(tmp_path, match)
    row = result["results"][0]
    assert row["status"] == "inspectable"
    assert row["final_inventory_fields_present"] == 6
    assert all(c["observation"] == "unknown" for c in row["candidates"])
    assert not any(c["completion_label_available"] for c in row["candidates"])
    assert not result["training_allowed"]
    assert result["summary"]["training_admitted_matches"] == 0


def test_window_boundary_invalid_events_and_same_second_ambiguity(tmp_path, match):
    match["players"][0]["purchase_log"] = [
        {"time": -10, "key": "manta"},
        {"time": 0, "key": "bfury"},
        {"time": 1200, "key": "manta"},
        {"time": 1200, "key": "maelstrom"},
        {"time": 1200, "key": "recipe_manta"},
        {"time": 1200, "key": "manta"},
        {"time": 1800, "key": "skadi"},
        {"time": 2200, "key": "skadi"},
        {"time": True, "key": "skadi"},
        None,
    ]
    row = audit(tmp_path, match)["results"][0]
    assert row["invalid_purchase_rows"] == 3
    assert row["simultaneous_distinct_item_times"] == [1200.0]
    assert row["exact_duplicate_event_rows"] == 1
    assert row["recipe_rows_in_window"] == 1
    candidates = {c["item_key"]: c for c in row["candidates"]}
    assert candidates["manta"]["event_times"] == [1200, 1200]
    assert candidates["manta"]["event_refs"] == [
        "players[0].purchase_log[2]",
        "players[0].purchase_log[5]",
    ]
    assert candidates["skadi"]["observation"] == "unknown"


def test_short_match_keeps_positive_observation_but_not_full_window(tmp_path, match):
    match["duration"] = 1000
    match["players"][0]["purchase_log"] = [{"time": 500, "key": "manta"}]
    report = audit(tmp_path, match)
    row = report["results"][0]
    assert not row["window_complete_in_duration"]
    assert "right_censored" in row["reasons"]
    assert report["summary"]["candidate_observed_match_counts"]["manta"] == 1
    assert report["summary"]["full_window_matches"] == 0


@pytest.mark.parametrize(
    "mutation", ["slot", "hero", "bool_id", "bool_slot", "duration", "players"]
)
def test_invalid_identities_are_kept_in_attempt_denominator(tmp_path, match, mutation):
    if mutation == "slot":
        match["players"][1]["player_slot"] = 0
    elif mutation == "hero":
        match["players"][1]["hero_id"] = 8
    elif mutation == "bool_id":
        match["match_id"] = True
    elif mutation == "bool_slot":
        match["players"][0]["player_slot"] = False
    elif mutation == "duration":
        match["duration"] = -1
    else:
        match["players"].pop()
    report = audit(tmp_path, match)
    assert report["summary"]["attempted_inputs"] == 1
    assert report["summary"]["status_counts"] == {"invalid": 1}


def test_whitespace_duplicates_count_once_and_conflicts_block_both(tmp_path, match):
    first = save(tmp_path, match)
    other = tmp_path / "other.json"
    other.write_text(json.dumps(match, indent=2))
    report = audit_paths([first, other], AuditConfig())
    assert report["summary"]["inspectable_unique_matches"] == 1
    assert report["summary"]["status_counts"] == {"duplicate": 1, "inspectable": 1}
    match["duration"] = 2100
    save(tmp_path, match, "other.json")
    report = audit_paths([first, other], AuditConfig())
    assert report["summary"]["status_counts"] == {"conflict": 2}
    assert report["summary"]["inspectable_unique_matches"] == 0


def test_tampered_receipt_does_not_mask_valid_duplicate(tmp_path, match):
    bad = save(tmp_path, match)
    good = save(tmp_path, match, "good.json")
    bad.with_suffix(".manifest.json").write_text(json.dumps({"match_id": 123, "sha256": "0" * 64}))
    report = audit_paths([bad, good], AuditConfig())
    assert report["summary"]["status_counts"] == {"inspectable": 1, "invalid": 1}
    bad.with_suffix(".manifest.json").write_text(
        json.dumps(
            {"match_id": 123, "sha256": file_hash(bad), "source": "test", "fetched_at": "test"}
        )
    )
    row = audit_paths([bad], AuditConfig())["results"][0]
    assert row["source_receipt"]["source"] == "test"
    assert row["scope"] == report["results"][1]["scope"]


def test_bad_json_missing_file_and_nonfinite_values_still_report(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"match_id": NaN}')
    report = audit_paths([bad, tmp_path / "absent.json"], AuditConfig())
    assert report["summary"]["attempted_inputs"] == 2
    assert report["summary"]["status_counts"] == {"invalid": 2}
    assert report["results"][0]["sha256"] == file_hash(bad)
    assert "sha256" not in report["results"][1]


def test_lane_and_rank_hints_never_certify_requested_scope(tmp_path, match):
    match["players"][0].update(lane_role=1, rank_tier=80)
    match["leagueid"] = 1234
    row = audit(tmp_path, match)["results"][0]
    assert row["scope"]["role"] == row["scope"]["patch"] == "unverified"
    assert row["scope"]["high_skill"] == "unverified"
    assert row["synthetic_marker_present"]


def test_absent_target_is_explicit_exclusion(tmp_path, match):
    match["players"][0]["hero_id"] = 12
    report = audit(tmp_path, match)
    assert report["summary"]["status_counts"] == {"out_of_scope": 1}
    assert report["summary"]["inspectable_unique_matches"] == 0


def test_cli_fetch_failure_keeps_other_rows_and_never_leaks_error_text(
    tmp_path, match, monkeypatch
):
    def fail(*args, **kwargs):
        raise httpx.InvalidURL("https://example.invalid/?api_key=secret")

    monkeypatch.setattr("dota_items.sources.opendota.fetch_match", fail)
    output = tmp_path / "report.json"
    assert main([str(save(tmp_path, match)), "--match-id", "456", "--output", str(output)]) == 3
    report = json.loads(output.read_text())
    assert report["summary"]["attempted_inputs"] == 2
    assert report["summary"]["status_counts"] == {"inspectable": 1, "unavailable": 1}
    assert "secret" not in output.read_text()


def test_launcher_and_output_collision_preserve_inputs(tmp_path, match):
    path = save(tmp_path, match)
    original = path.read_bytes()
    command = [sys.executable, str(ROOT / "audit_data.py"), str(path)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert not json.loads(result.stdout)["training_allowed"]
    result = subprocess.run([*command, "--output", str(path)], capture_output=True, check=False)
    assert result.returncode == 2
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "values",
    [
        {"window_start": 1800},
        {"candidate_items": ["recipe_manta"]},
        {"candidate_items": ["manta", "manta"]},
    ],
)
def test_invalid_config_rejected(values):
    with pytest.raises(ValueError):
        AuditConfig(**values)


def test_resource_limits_are_reported_not_silently_skipped(tmp_path, match, monkeypatch):
    path = save(tmp_path, match)
    monkeypatch.setattr("dota_items.data.feasibility.MAX_BYTES", 10)
    report = audit_paths([path], AuditConfig())
    assert report["summary"]["status_counts"] == {"invalid": 1}
    assert "limit" in report["results"][0]["diagnostic"]


def test_local_audit_never_fetches_or_changes_input(tmp_path, match, monkeypatch):
    path = save(tmp_path, match)
    before = path.read_bytes()

    def fail(*args, **kwargs):
        raise AssertionError("local audit must not use the network")

    monkeypatch.setattr("httpx.Client.send", fail)
    report = audit_paths([path], AuditConfig())
    assert report["implementation_sha256"]["normalize.py"] == file_hash(
        ROOT / "src/dota_items/normalize.py"
    )
    assert path.read_bytes() == before
    assert report["summary"]["inspectable_unique_matches"] == 1
