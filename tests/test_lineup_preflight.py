"""Rehearsal must not leak future fields, fit holdout heroes or invent labels."""

import json

import pytest

from dota_items.data.feasibility import AuditConfig
from dota_items.data.feasibility_cli import main
from dota_items.data.feasibility_sampling import freeze_plan
from dota_items.data.lineup_preflight import (
    PreflightConfig,
    build_preflight,
    encode_lineup,
    fit_vocabulary,
    lineup_features,
    split_matches,
)
from dota_items.data.patch_time import OFFICIAL_PATCH_URL
from dota_items.storage import file_hash, json_bytes


def save(path, data):
    path.write_bytes(json_bytes(data))
    return path


@pytest.fixture
def cohort(tmp_path):
    discovery = save(tmp_path / "discovery.json", [{"match_id": i} for i in range(1, 6)])
    plan = freeze_plan(discovery, AuditConfig(), skip=0, take=5)
    plan_path = save(tmp_path / "plan.json", plan.model_dump(mode="json"))
    patch = save(
        tmp_path / "patch.json", {"patches": [{"patch_number": "7.41f", "patch_timestamp": 10000}]}
    )
    receipt = save(
        tmp_path / "receipt.json",
        {
            "schema_version": "patch-time-evidence/1",
            "source_url": OFFICIAL_PATCH_URL,
            "snapshot": patch.name,
            "sha256": file_hash(patch),
            "retrieved_at": "1970-01-02T00:00:00+00:00",
            "boundary_buffer_seconds": 100,
        },
    )
    for mid in range(1, 6):
        save(
            tmp_path / f"{mid}.json",
            {
                "match_id": mid,
                "duration": 2000,
                "start_time": 11000,
                "players": [
                    {
                        "player_slot": slot,
                        "hero_id": hero,
                        "position_est": 1,
                        "purchase_log": [{"time": 1000, "key": "manta"}],
                    }
                    for slot, hero in zip(
                        [0, 1, 2, 3, 4, 128, 129, 130, 131, 132],
                        [8, 2, 3, 4, 5, 6, 7, 9, 10, 11],
                        strict=True,
                    )
                ],
            },
        )
    return plan_path, discovery, tmp_path, receipt


def test_repeatable_disjoint_and_masked(cohort):
    report = build_preflight(*cohort)
    assert report == build_preflight(*cohort)
    assert report["summary"]["split_counts"] == {"validation": 1, "test": 1, "train": 3}
    assert sorted(mid for ids in report["splits"].values() for mid in ids) == list(range(1, 6))
    for row in report["samples"]:
        assert row["labels"] == [None] * 5
        assert row["label_mask"] == [False] * 5
        assert not row["training_allowed"]
        assert len(row["encoded_features"]) == len(report["preprocessing"]["columns"])
    assert not report["training_allowed"]


def test_future_mutation_cannot_change_features(cohort):
    before = build_preflight(*cohort)
    path = cohort[2] / "1.json"
    raw = json.loads(path.read_text())
    raw.update(radiant_win=False, duration=2200)
    raw["players"][0].update(
        position_est=5, gold_per_min=999, item_0=999, purchase_log=[{"time": 1700, "key": "skadi"}]
    )
    save(path, raw)
    after = build_preflight(*cohort)
    assert before["splits"] == after["splits"]
    for a, b in zip(before["samples"], after["samples"], strict=True):
        assert a["features"] == b["features"]
        assert a["encoded_features"] == b["encoded_features"]
    assert before["samples"][0]["source_sha256"] != after["samples"][0]["source_sha256"]


def test_holdout_hero_does_not_change_training_vocabulary(cohort):
    before = build_preflight(*cohort)
    mid = before["splits"]["test"][0]
    path = cohort[2] / f"{mid}.json"
    raw = json.loads(path.read_text())
    raw["players"][1]["hero_id"] = 999
    save(path, raw)
    after = build_preflight(*cohort)
    assert before["preprocessing"] == after["preprocessing"]
    row = next(r for r in after["samples"] if r["match_id"] == mid)
    unknown_column = after["preprocessing"]["columns"].index("ally_unknown_count")
    assert row["encoded_features"][unknown_column] == 1
    assert 999 not in after["preprocessing"]["hero_vocabulary"]


def test_exclusions_and_missing_files_remain_in_denominator(cohort):
    path = cohort[2] / "1.json"
    raw = json.loads(path.read_text())
    raw["duration"] = 1500
    save(path, raw)
    # Rename only a synthetic temporary fixture, not a project/user file.
    (cohort[2] / "2.json").rename(cohort[2] / "missing.json")
    raw["match_id"] = 999
    save(cohort[2] / "3.json", raw)
    report = build_preflight(*cohort)
    assert report["summary"]["attempted_matches"] == 5
    assert report["summary"]["excluded_matches"] == 3
    assert report["splits"] is None
    assert "insufficient_matches_for_three_splits" in report["blockers"]
    assert all(row["encoded_features"] is None for row in report["samples"])


def test_no_network_output_collision_and_held_exit(cohort, monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("preflight must be offline")

    monkeypatch.setattr("httpx.Client.send", deny)
    p, d, cache, receipt = cohort
    out = cache / "out.json"
    args = [
        "--preflight",
        "--plan",
        str(p),
        "--discovery",
        str(d),
        "--cache",
        str(cache),
        "--offline",
        "--patch-receipt",
        str(receipt),
        "--output",
        str(out),
    ]
    assert main(args) == 4
    before = out.read_bytes()
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    assert before == out.read_bytes()


def test_tampered_plan_fails_closed(cohort):
    p, *_ = cohort
    data = json.loads(p.read_text())
    data["match_ids"][0] = 888
    save(p, data)
    with pytest.raises(ValueError):
        build_preflight(*cohort)


def test_synthetic_marker_is_excluded(cohort):
    path = cohort[2] / "1.json"
    raw = json.loads(path.read_text())
    raw["_fixture"] = "test"
    save(path, raw)
    report = build_preflight(*cohort)
    assert report["exclusions"][0]["reasons"] == ["synthetic_marker"]


def test_split_order_invariant_and_duplicate_rejected():
    config = PreflightConfig()
    assert split_matches([1, 2, 3], config) == split_matches([3, 2, 1], config)
    with pytest.raises(ValueError):
        split_matches([1, 1, 2], config)


def test_ally_enemy_channels_and_permutation_invariant():
    row = {
        "target_slot": 128,
        "lineup": [
            {"player_slot": s, "hero_id": h} for s, h in [(0, 2), (1, 3), (128, 8), (129, 9)]
        ],
    }
    features = lineup_features(row)
    assert features["ally_hero_ids"] == [8, 9]
    assert features["enemy_hero_ids"] == [2, 3]
    row["lineup"].reverse()
    assert features == lineup_features(row)
    vocab = fit_vocabulary([features])
    assert encode_lineup(features, vocab) == [0, 0, 1, 1, 0, 1, 1, 0, 0, 0]


@pytest.mark.parametrize("args", [["--preflight"], ["--preflight", "--offline"]])
def test_preflight_requires_bound_sources(args):
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2


def test_legacy_training_rejects_preview_before_running_adapter(cohort, monkeypatch):
    from dota_items.workflow.jobs import train
    from dota_items.workflow.workspace import Workspace

    workspace = Workspace(cohort[2] / "workspace")
    workspace.init()
    folder = workspace.root / "datasets" / "preview"
    folder.mkdir()
    save(folder / "manifest.json", build_preflight(*cohort))

    def deny(*args, **kwargs):
        raise AssertionError("held preview must never launch training")

    monkeypatch.setattr("dota_items.workflow.jobs.run_program", deny)
    with pytest.raises(ValueError, match="Unsupported dataset schema"):
        train(workspace, "preview", cohort[2] / "unused.py")


def test_verify_preview_replays_custom_config_without_network(cohort, monkeypatch):
    from dota_items.data.lineup_preflight import verify_preflight

    def deny(*args, **kwargs):
        raise AssertionError("verification must stay offline")

    monkeypatch.setattr("httpx.Client.send", deny)
    report = build_preflight(*cohort, config=PreflightConfig(seed=42))
    path = save(cohort[2] / "preview.json", report)
    result = verify_preflight(path, *cohort)
    assert result["status"] == "reproduced"
    assert result["training_allowed"] is False
    assert result["report_sha256"] == file_hash(path)


@pytest.mark.parametrize(
    "mutation",
    ["label", "mask", "feature", "split", "code", "admission", "bool_as_int", "support", "extra"],
)
def test_verify_preview_rejects_modified_artifact(cohort, mutation):
    from dota_items.data.lineup_preflight import verify_preflight

    report = build_preflight(*cohort)
    row = report["samples"][0]
    if mutation == "label":
        row["labels"][0] = 1
    elif mutation == "mask":
        row["label_mask"][0] = True
    elif mutation == "feature":
        row["encoded_features"][0] += 1
    elif mutation == "split":
        report["splits"]["test"].append(report["splits"]["train"][0])
    elif mutation == "code":
        report["implementation_sha256"]["data/lineup_preflight.py"] = "0" * 64
    elif mutation == "admission":
        report["training_allowed"] = True
    elif mutation == "bool_as_int":
        row["label_mask"][0] = 0
    elif mutation == "support":
        report["purchase_support"]["preview"]["items"][0]["observed_matches"] += 1
    else:
        report["unverified_extra"] = "value"
    path = save(cohort[2] / "preview.json", report)
    with pytest.raises(ValueError, match="differs"):
        verify_preflight(path, *cohort)


def test_verify_preview_rejects_changed_source(cohort):
    from dota_items.data.lineup_preflight import verify_preflight

    path = save(cohort[2] / "preview.json", build_preflight(*cohort))
    source = cohort[2] / "1.json"
    raw = json.loads(source.read_text())
    raw["players"][0]["purchase_log"][0]["time"] += 1
    save(source, raw)
    with pytest.raises(ValueError):
        verify_preflight(path, *cohort)


@pytest.mark.parametrize("saved", [[], {}, {"schema_version": "lineup-preflight/2"}])
def test_verify_preview_rejects_invalid_schema(cohort, saved):
    from dota_items.data.lineup_preflight import verify_preflight

    path = save(cohort[2] / "preview.json", saved)
    with pytest.raises(ValueError):
        verify_preflight(path, *cohort)


def test_verify_cli_held_and_never_overwrites_source(cohort):
    path = save(cohort[2] / "preview.json", build_preflight(*cohort))
    p, d, cache, receipt = cohort
    args = [
        "--verify-preflight",
        str(path),
        "--plan",
        str(p),
        "--discovery",
        str(d),
        "--cache",
        str(cache),
        "--offline",
        "--patch-receipt",
        str(receipt),
    ]
    assert main(args) == 4
    before = path.read_bytes()
    with pytest.raises(SystemExit) as error:
        main([*args, "--output", str(path)])
    assert error.value.code == 2
    assert path.read_bytes() == before
    with pytest.raises(SystemExit):
        main([*args, "--preflight"])


def test_twenty_minute_plan_uses_frozen_half_open_window(cohort):
    p, discovery, cache, _ = cohort
    plan = freeze_plan(discovery, AuditConfig(window_end=1200), skip=0, take=5)
    save(p, plan.model_dump(mode="json"))
    for mid, duration in [(1, 1199), (2, 1200)]:
        path = cache / f"{mid}.json"
        raw = json.loads(path.read_text())
        raw["duration"] = duration
        raw["players"][0]["purchase_log"] = [
            {"time": 1199, "key": "manta"},
            {"time": 1200, "key": "skadi"},
        ]
        if duration < 1200:
            raw["players"][0]["purchase_log"] = [{"time": 1100, "key": "manta"}]
        save(path, raw)
    report = build_preflight(*cohort)
    assert report["audit_config"]["window_end"] == 1200
    assert report["exclusions"] == [{"requested_match_id": 1, "reasons": ["right_censored"]}]
    row = next(r for r in report["audit"]["results"] if r["match_id"] == 2)
    assert row["observed_keys_in_window"] == {"manta": 1}
    assert next(r for r in report["samples"] if r["match_id"] == 2)["labels"] == [None] * 5


def test_support_counts_matches_not_duplicate_events(cohort):
    path = cohort[2] / "1.json"
    raw = json.loads(path.read_text())
    raw["players"][0]["purchase_log"] = [
        {"time": 1000, "key": "manta"},
        {"time": 1000, "key": "manta"},
        {"time": 1100, "key": "manta"},
        {"time": 1800, "key": "skadi"},
    ]
    save(path, raw)
    support = build_preflight(*cohort)["purchase_support"]
    item = next(c for c in support["preview"]["items"] if c["item_key"] == "manta")
    assert item["observed_matches"] == 5
    assert item["source_event_rows"] == 7
    assert item["distinct_match_time_pairs"] == 6
    skadi = next(c for c in support["preview"]["items"] if c["item_key"] == "skadi")
    assert skadi["observed_matches"] == 0
    assert skadi["no_observation_matches"] == 5
    assert skadi["admitted_negative_labels"] == 0
    assert item["admitted_positive_labels"] == 0
    assert sum(s["match_count"] for s in support["by_split"].values()) == 5
    assert (
        sum(
            next(c for c in s["items"] if c["item_key"] == "manta")["observed_matches"]
            for s in support["by_split"].values()
        )
        == 5
    )


def test_support_retains_excluded_observations_without_promoting_them(cohort):
    for mid, duration in [(1, 1100), (2, 1100), (3, 1100)]:
        path = cohort[2] / f"{mid}.json"
        raw = json.loads(path.read_text())
        raw["duration"] = duration
        save(path, raw)
    report = build_preflight(*cohort)
    support = report["purchase_support"]
    assert support["all_inspectable"]["match_count"] == 5
    assert support["preview"]["match_count"] == 2
    assert support["by_split"] == {}
    assert support["split_status"] == "not_available"
    assert report["training_allowed"] is False


def test_support_empty_and_missing_logs_are_not_negatives(cohort):
    for mid, log in [(1, []), (2, None)]:
        path = cohort[2] / f"{mid}.json"
        raw = json.loads(path.read_text())
        raw["players"][0]["purchase_log"] = log
        save(path, raw)
    support = build_preflight(*cohort)["purchase_support"]
    assert support["all_inspectable"]["match_count"] == 5
    assert support["preview"]["match_count"] == 4
    for scope in (support["all_inspectable"], support["preview"]):
        manta = next(c for c in scope["items"] if c["item_key"] == "manta")
        assert manta["observed_matches"] == 3
        assert manta["no_observation_matches"] == scope["match_count"] - 3
        assert manta["admitted_negative_labels"] == 0


def test_support_no_usable_matches_has_explicit_zero_denominators(cohort):
    for mid in range(1, 6):
        save(cohort[2] / f"{mid}.json", {})
    support = build_preflight(*cohort)["purchase_support"]
    assert support["all_inspectable"]["match_count"] == 0
    assert support["preview"]["match_count"] == 0
    assert len(support["preview"]["items"]) == 5
    assert all(c["observed_matches"] == 0 for c in support["preview"]["items"])
