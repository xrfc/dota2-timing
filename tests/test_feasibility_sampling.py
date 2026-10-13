"""Frozen cohorts and release-time evidence must fail closed on changed inputs."""

import hashlib
import json

import pytest

from dota_items.data.feasibility import AuditConfig
from dota_items.data.feasibility_cli import main
from dota_items.data.feasibility_sampling import freeze_plan, verify_plan
from dota_items.data.patch_time import OFFICIAL_PATCH_URL, classify_patch_time, load_patch_window


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.fixture
def evidence(tmp_path):
    snapshot = write(
        tmp_path / "patch.json",
        {
            "patches": [
                {"patch_number": "7.41f", "patch_timestamp": 10000},
                {"patch_number": "7.42", "patch_timestamp": 20000},
            ]
        },
    )
    return write(
        tmp_path / "receipt.json",
        {
            "schema_version": "patch-time-evidence/1",
            "source_url": OFFICIAL_PATCH_URL,
            "snapshot": snapshot.name,
            "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            "retrieved_at": "1970-01-01T10:00:00+00:00",
            "boundary_buffer_seconds": 100,
        },
    )


@pytest.mark.parametrize(
    "start,duration,expected",
    [
        (None, 100, "unknown_time"),
        (True, 100, "unknown_time"),
        (9999, 100, "outside_interval"),
        (20000, 100, "outside_interval"),
        (10000, 100, "boundary_uncertain"),
        (10100, 100, "time_consistent"),
        (18000, 1900, "boundary_uncertain"),
        (18000, 2000, "crosses_upper_boundary"),
    ],
)
def test_patch_boundaries(evidence, start, duration, expected):
    assert classify_patch_time(start, duration, load_patch_window(evidence, "7.41f")) == expected


@pytest.mark.parametrize("change", ["hash", "timezone", "escape", "duplicate", "future"])
def test_bad_release_evidence_rejected(evidence, change):
    receipt = json.loads(evidence.read_text())
    if change == "hash":
        receipt["sha256"] = "0" * 64
    elif change == "timezone":
        receipt["retrieved_at"] = "1970-01-01T10:00:00"
    elif change == "escape":
        receipt["snapshot"] = "../patch.json"
    else:
        path = evidence.parent / receipt["snapshot"]
        data = json.loads(path.read_text())
        if change == "duplicate":
            data["patches"].append(data["patches"][0])
        else:
            data["patches"][1]["patch_timestamp"] = 999999
        write(path, data)
        receipt["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    write(evidence, receipt)
    with pytest.raises(ValueError):
        load_patch_window(evidence, "7.41f")


def test_latest_patch_only_valid_through_retrieval(evidence):
    window = load_patch_window(evidence, "7.42")
    assert window["upper_kind"] == "snapshot_retrieval"
    assert classify_patch_time(35000, 999, window) == "time_consistent"
    assert classify_patch_time(35000, 1000, window) == "crosses_upper_boundary"


def test_freeze_verify_and_reject_changed_discovery(tmp_path):
    discovery = write(tmp_path / "discovery.json", [{"match_id": i} for i in range(1, 5)])
    plan = freeze_plan(discovery, AuditConfig(), skip=1, take=2)
    assert plan.match_ids == [2, 3]
    path = write(tmp_path / "plan.json", plan.model_dump(mode="json"))
    assert verify_plan(path, discovery)[0] == plan
    write(discovery, [{"match_id": i} for i in range(4, 0, -1)])
    with pytest.raises(ValueError):
        verify_plan(path, discovery)


@pytest.mark.parametrize(
    "rows", [[{"match_id": 1}, {"match_id": 1}], [{"match_id": True}, {"match_id": 2}], []]
)
def test_invalid_selection_not_replaced(tmp_path, rows):
    with pytest.raises(ValueError):
        freeze_plan(write(tmp_path / "discovery.json", rows), AuditConfig(), skip=0, take=2)


def test_cli_offline_preserves_missing_and_wrong_identity(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("offline must not fetch")

    monkeypatch.setattr("dota_items.sources.opendota.fetch_match", no_network)
    discovery = write(tmp_path / "discovery.json", [{"match_id": 1}, {"match_id": 2}])
    plan, output = tmp_path / "plan.json", tmp_path / "report.json"
    assert main(["--discovery", str(discovery), "--freeze-plan", str(plan), "--take", "2"]) == 0
    write(tmp_path / "1.json", {"match_id": 3})
    assert (
        main(
            [
                "--plan",
                str(plan),
                "--discovery",
                str(discovery),
                "--offline",
                "--cache",
                str(tmp_path),
                "--output",
                str(output),
            ]
        )
        == 3
    )
    report = json.loads(output.read_text())
    assert [r["requested_match_id"] for r in report["results"]] == [1, 2]
    assert report["summary"]["attempted_inputs"] == 2
    assert not report["training_allowed"]
    assert "requested_match_identity_mismatch" in report["results"][0]["reasons"]
    before = plan.read_bytes()
    with pytest.raises(SystemExit) as error:
        main(["--discovery", str(discovery), "--freeze-plan", str(plan), "--take", "2"])
    assert error.value.code == 2
    assert plan.read_bytes() == before


def test_cli_rejects_changed_plan_before_network(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("invalid plan must not fetch")

    monkeypatch.setattr("dota_items.sources.opendota.fetch_match", no_network)
    discovery = write(tmp_path / "d.json", [{"match_id": 1}])
    plan = freeze_plan(discovery, AuditConfig(), skip=0, take=1).model_dump(mode="json")
    plan["match_ids"] = [2]
    path = write(tmp_path / "p.json", plan)
    with pytest.raises(SystemExit) as error:
        main(["--plan", str(path), "--discovery", str(discovery)])
    assert error.value.code == 2


def test_plan_exec_orders_failed_and_successful_fetches(tmp_path, monkeypatch, evidence):
    discovery = write(tmp_path / "d.json", [{"match_id": 1}, {"match_id": 2}])
    plan = freeze_plan(discovery, AuditConfig(), skip=0, take=2)
    plan_path = write(tmp_path / "p.json", plan.model_dump(mode="json"))
    match = {
        "match_id": 2,
        "duration": 2000,
        "start_time": 11000,
        "patch": 60,
        "players": [
            {"player_slot": s, "hero_id": h, "purchase_log": []}
            for s, h in zip(
                [0, 1, 2, 3, 4, 128, 129, 130, 131, 132],
                [8, 2, 3, 4, 5, 6, 7, 9, 10, 11],
                strict=True,
            )
        ],
    }
    source = write(tmp_path / "2.json", match)

    def fetch(mid, cache):
        if mid == 1:
            raise ValueError("unavailable")
        return source

    monkeypatch.setattr("dota_items.sources.opendota.fetch_match", fetch)
    output = tmp_path / "out.json"
    assert (
        main(
            [
                "--plan",
                str(plan_path),
                "--discovery",
                str(discovery),
                "--patch-receipt",
                str(evidence),
                "--output",
                str(output),
            ]
        )
        == 3
    )
    report = json.loads(output.read_text())
    assert [r["match_id"] for r in report["results"]] == [1, 2]
    assert report["summary"]["patch_time_counts"] == {"time_consistent": 1}
    assert report["results"][1]["scope"]["patch"] == "unverified"
    assert "patch_unverified" in report["results"][1]["reasons"]
    assert report["patch_time_evidence"]["method"] == "official_release_time_inference"
    assert not report["training_allowed"]
