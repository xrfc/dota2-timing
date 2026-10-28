"""Synthetic-only tests for the approved random development cohort."""

import copy
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from dota_items.data.random_cohort_snapshot import assemble_snapshot, random_split
from dota_items.modeling.batch import adapt_snapshot
from dota_items.storage import json_bytes


def rows():
    return [
        {
            "match_id": mid,
            "group_id": "same-connected-component",
            "role_hint": "unverified",
            "source_sha256": "a" * 64,
            "features": {
                "target_hero_id": 8,
                "ally_hero_ids": [1, 2, 3, 4, 8],
                "enemy_hero_ids": [5, 6, 7, 9, 10],
            },
            "labels": [mid % 2, 0, 1, None, 0],
            "label_mask": [True, True, True, False, True],
        }
        for mid in range(1, 21)
    ]


def test_split_count_order_invariance_and_coverage():
    ids = list(range(1, 1991))
    split = random_split(ids)
    assert split == random_split(ids[::-1])
    assert len(split["train"]) == 1592
    assert len(split["validation"]) == 398
    assert not split["test"]
    assert set(split["train"]).isdisjoint(split["validation"])
    assert sorted(split["train"] + split["validation"]) == ids
    assert split != random_split(ids, seed=43)


@pytest.mark.parametrize(
    "ids", [[1, 2], [1, 2, 3, 4, 4], [True, 2, 3, 4, 5], [0, 2, 3, 4, 5], [1.0, 2, 3, 4, 5]]
)
def test_reject_bad_ids(ids):
    with pytest.raises(ValueError):
        random_split(ids)


@pytest.mark.parametrize("seed", [True, -1, 42.0])
def test_reject_bad_seed(seed):
    with pytest.raises(ValueError):
        random_split(list(range(1, 10)), seed)


def test_label_independence_immutability_and_same_group_allowed():
    original = rows()
    before = json_bytes(original)
    first = assemble_snapshot(original)
    assert json_bytes(original) == before
    changed = copy.deepcopy(original[::-1])
    for row in changed:
        row["labels"][0] = 1 - row["labels"][0]
    second = assemble_snapshot(changed)
    assert first["splits"] == second["splits"]
    assert first["membership_sha256"] == second["membership_sha256"]
    assert first == assemble_snapshot(original[::-1])
    assert len({r["group_id"] for r in first["samples"]}) == 1


def test_train_only_vocabulary_unknown_and_consumer():
    data = rows()
    validation = set(random_split([r["match_id"] for r in data])["validation"])
    for row in data:
        if row["match_id"] in validation:
            row["features"]["enemy_hero_ids"][-1] = 999
    snapshot = assemble_snapshot(data)
    assert 999 not in snapshot["preprocessing"]["vocabulary"]
    train = adapt_snapshot(snapshot, "train")
    valid = adapt_snapshot(snapshot, "validation")
    assert train.x.shape == (16, 22)
    assert valid.x.shape == (4, 22)
    assert np.all(valid.x[:, -1] == 1)
    assert np.all(np.isnan(valid.y[:, 3]))
    assert not np.any(valid.mask[:, 3])
    assert snapshot["support"]["validation"]["black_king_bar"]["unknown"] == 4
    assert snapshot["train_model_items"] == ["bfury"]


@pytest.mark.parametrize("value,mask", [(0, False), (None, True), (True, True), (2, True), (0, 1)])
def test_bad_labels_rejected(value, mask):
    data = rows()
    data[0]["labels"][0] = value
    data[0]["label_mask"][0] = mask
    with pytest.raises(ValueError):
        assemble_snapshot(data)


def test_existing_output_rejected_before_sources(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep"
    marker.write_text("preserve")
    root = Path(__file__).resolve().parents[1]
    args = [sys.executable, str(root / "scripts/prepare_random_cohort.py")]
    for option in ("old-root", "new-root", "summary", "snapshot", "audit"):
        args += ["--" + option, str(tmp_path / "missing")]
    result = subprocess.run(args + ["--output", str(output)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "Refusing to overwrite" in result.stderr
    assert marker.read_text() == "preserve"


def cli_module(monkeypatch):
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "random_cohort_cli", root / "scripts/prepare_random_cohort.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_replay_failure_never_creates_output(tmp_path, monkeypatch):
    cli = cli_module(monkeypatch)
    output = tmp_path / "new-output"
    argv = ["prepare_random_cohort.py"]
    for name in ("old-root", "new-root", "summary", "snapshot", "audit"):
        argv += ["--" + name, str(tmp_path / name)]
    argv += ["--output", str(output)]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(cli, "inventory", lambda: {})

    def fail(_):
        raise ValueError("Source hash mismatch")

    monkeypatch.setattr(cli, "build", fail)
    with pytest.raises(ValueError, match="Source hash mismatch"):
        cli.main()
    assert not output.exists()


def test_protection_rejects_changed_or_missing_file(tmp_path, monkeypatch):
    cli = cli_module(monkeypatch)
    from dota_items.storage import file_hash

    path = tmp_path / "source.json"
    path.write_text("original")
    frozen = {str(path): file_hash(path)}
    cli.unchanged(frozen)
    path.write_text("changed")
    with pytest.raises(ValueError, match="Protected input changed"):
        cli.unchanged(frozen)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        cli.unchanged(frozen)
