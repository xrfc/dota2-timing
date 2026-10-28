"""Synthetic-only whole-log producer, closed registry and model compatibility tests."""

import copy
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from dota_items.contracts.tasks import WHOLE_LOG_ITEMS, WHOLE_LOG_TASK_ID, task_contract
from dota_items.data.purchase_observation import observe_purchases
from dota_items.data.random_cohort_snapshot import assemble_snapshot
from dota_items.data.whole_log_snapshot import (
    BUNDLE_FILES,
    build_whole_log_bundle,
    observe_whole_log,
    relabel_snapshot,
    whole_log_task,
)
from dota_items.modeling.artifacts import load_model, save_model
from dota_items.modeling.batch import adapt_snapshot
from dota_items.modeling.inference import predict_lineup
from dota_items.modeling.training import fit_model
from dota_items.storage import digest, file_hash, json_bytes


def fixture():
    rows, sources, payloads = [], [], {}
    for mid in range(1, 21):
        players = [
            {"hero_id": hero, "player_slot": slot}
            for hero, slot in zip(
                [8, 1, 2, 3, 4, 5, 6, 7, 9, 10],
                [0, 1, 2, 3, 4, 128, 129, 130, 131, 132],
                strict=True,
            )
        ]
        players[0]["purchase_log"] = ([{"key": "bfury", "time": 100}] if mid % 2 else []) + [
            {"key": "blink", "time": -10},
            {"key": "mjollnir", "time": 1800},
            {"key": "skadi", "time": 3000},
        ]
        old = observe_purchases(players[0], task_contract()["labels"]["candidate_items"])
        raw = {"match_id": mid, "players": players}
        sha = digest(raw)
        payloads[mid] = raw
        sources.append({"match_id": mid, "sha256": sha})
        rows.append(
            {
                "match_id": mid,
                "group_id": "synthetic",
                "role_hint": "synthetic",
                "source_sha256": sha,
                "features": {
                    "target_hero_id": 8,
                    "ally_hero_ids": [1, 2, 3, 4, 8],
                    "enemy_hero_ids": [5, 6, 7, 9, 10],
                },
                "labels": [i["log_presence"] for i in old["items"]],
                "label_mask": [True] * 5,
            }
        )
    frozen = assemble_snapshot(rows)
    frozen["synthetic"] = True
    return frozen, sources, payloads


def test_whole_times_and_no_inventory_substitution():
    observation = observe_whole_log(
        {
            "purchase_log": [
                {"key": "blink", "time": -3},
                {"key": "blink", "time": -3},
                {"key": "skadi", "time": 99999},
                {"key": "recipe_manta", "time": 1800},
            ],
            "item_0": "manta",
        }
    )
    assert observation["labels"][6] == observation["labels"][10] == 1
    assert observation["labels"][3] == 0
    assert observation["event_refs"]["blink"] == [0, 1]
    assert observe_whole_log({"purchase_log": []})["labels"] == [0] * 11


@pytest.mark.parametrize(
    "player",
    [
        {},
        {"purchase_log": None},
        {"purchase_log": {}},
        {"purchase_log": [{"key": "blink", "time": True}]},
        {"purchase_log": [{"key": "blink", "time": float("nan")}]},
        {"purchase_log": [{"key": "", "time": 1}]},
        {"purchase_log": [None]},
    ],
)
def test_missing_bad_remain_unknown(player):
    result = observe_whole_log(player)
    assert result["labels"] == [None] * 11
    assert result["label_mask"] == [False] * 11


def test_replay_exact_features_membership_and_model_roundtrip(tmp_path):
    frozen, sources, payloads = fixture()
    before = json_bytes(frozen)
    result = relabel_snapshot(frozen, sources, payloads)
    assert json_bytes(frozen) == before
    for key in ("splits", "membership_sha256", "preprocessing", "split_policy"):
        assert result[key] == frozen[key]
    for split in ("train", "validation"):
        old, new = adapt_snapshot(frozen, split), adapt_snapshot(result, split)
        assert np.array_equal(old.x, new.x)
        assert new.y.shape == (len(old.x), 11)
    assert result["samples"][0]["labels"] == [1, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]
    for family in ("frequency", "logistic"):
        model = fit_model(
            adapt_snapshot(result),
            family=family,
            source_sha256=digest(result),
            code_revision="synthetic",
        )
        path = tmp_path / (family + ".json")
        save_model(path, model)
        loaded = load_model(path, expected_task_contract=task_contract(WHOLE_LOG_TASK_ID))
        prediction = predict_lineup(loaded, result["samples"][0]["features"])
        assert list(prediction["probabilities"]) == list(WHOLE_LOG_ITEMS)
        with pytest.raises(ValueError, match="compatibility"):
            load_model(path, expected_task_contract=task_contract())


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "identity",
        "target",
        "lineup",
        "missing",
        "bad",
        "old_labels",
        "source",
        "membership",
    ],
)
def test_replay_rejects_invalid_sources(fault):
    frozen, sources, payloads = fixture()
    if fault == "duplicate":
        sources.append(copy.deepcopy(sources[0]))
    elif fault == "identity":
        payloads[1]["match_id"] = 2
    elif fault == "target":
        payloads[1]["players"][1]["hero_id"] = 8
    elif fault == "lineup":
        payloads[1]["players"][1]["hero_id"] = 99
    elif fault == "missing":
        del payloads[1]["players"][0]["purchase_log"]
    elif fault == "bad":
        payloads[1]["players"][0]["purchase_log"].append({"key": "blink", "time": True})
    elif fault == "old_labels":
        frozen["samples"][0]["labels"][0] = 0
    elif fault == "source":
        sources[0]["sha256"] = "f" * 64
    else:
        frozen["splits"]["train"].append(1)
    with pytest.raises(ValueError):
        relabel_snapshot(frozen, sources, payloads)


def test_unknown_mask_and_unregistered_task_rejected():
    frozen, sources, payloads = fixture()
    result = relabel_snapshot(frozen, sources, payloads)
    for row in result["samples"]:
        row["labels"][2] = None
        row["label_mask"][2] = False
    batch = adapt_snapshot(result)
    assert np.isnan(batch.y[:, 2]).all() and not batch.mask[:, 2].any()
    result["task"]["contract"]["task_id"] = "arbitrary/1"
    with pytest.raises(ValueError):
        adapt_snapshot(result)
    assert whole_log_task()["window"] is None


def test_bundle_hash_rejected_before_relabel(tmp_path):
    for name in BUNDLE_FILES:
        (tmp_path / name).write_bytes(b"{}")
    receipt = {
        "schema_version": "random-cohort-complete/1",
        "sha256": {name: file_hash(tmp_path / name) for name in BUNDLE_FILES},
    }
    (tmp_path / "complete.json").write_bytes(json_bytes(receipt))
    (tmp_path / "snapshot.json").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_whole_log_bundle(tmp_path)


def test_cli_refuses_existing_output(tmp_path):
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        str(root / "scripts/prepare_whole_log_cohort.py"),
        "--parent",
        str(tmp_path / "missing"),
        "--output",
        str(tmp_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0 and "Refusing to overwrite" in result.stderr


def test_synthetic_bundle_roundtrip_and_source_tampering(tmp_path, monkeypatch):
    import dota_items.data.whole_log_snapshot as module

    frozen, sources, payloads = fixture()
    # Exercise the production-sized gate with fabricated rows only.
    rows = []
    sources = []
    source_dir = tmp_path / "raw"
    source_dir.mkdir()
    for mid in range(1, 1991):
        row = copy.deepcopy(frozen["samples"][(mid - 1) % 20])
        raw = copy.deepcopy(payloads[(mid - 1) % 20 + 1])
        row["match_id"] = raw["match_id"] = mid
        path = source_dir / f"{mid}.json"
        path.write_bytes(json_bytes(raw))
        row["source_sha256"] = file_hash(path)
        rows.append(row)
        sources.append({"match_id": mid, "path": str(path), "sha256": file_hash(path)})
    frozen = assemble_snapshot(rows)
    frozen["synthetic"] = True
    monkeypatch.setattr(module, "FROZEN_MEMBERSHIP", frozen["membership_sha256"])
    parent = tmp_path / "parent"
    parent.mkdir()
    bundle = {name: {} for name in BUNDLE_FILES}
    bundle.update(
        {
            "snapshot.json": frozen,
            "sources.json": sources,
            "split.json": {
                "policy": frozen["split_policy"],
                "members": frozen["splits"],
                "sha256": frozen["membership_sha256"],
            },
        }
    )
    for name, value in bundle.items():
        (parent / name).write_bytes(json_bytes(value))
    (parent / "complete.json").write_bytes(
        json_bytes(
            {
                "schema_version": "random-cohort-complete/1",
                "sha256": {name: file_hash(parent / name) for name in BUNDLE_FILES},
            }
        )
    )
    result, _, _ = build_whole_log_bundle(parent)
    assert adapt_snapshot(result).y.shape == (1592, 11)
    assert result["splits"] == frozen["splits"]
    (source_dir / "1.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="source hash mismatch"):
        build_whole_log_bundle(parent)


def test_whole_log_synthetic_cli(tmp_path):
    root = Path(__file__).resolve().parents[1]
    path = tmp_path / "whole.json"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/model_foundation.py"),
            "demo",
            "--task-id",
            WHOLE_LOG_TASK_ID,
            "--output",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert len(load_model(path)["models"]) == 11


def test_duplicate_json_keys_rejected(tmp_path):
    from dota_items.data.whole_log_snapshot import load

    path = tmp_path / "ambiguous.json"
    path.write_text('{"match_id":1,"match_id":2}')
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load(path)
