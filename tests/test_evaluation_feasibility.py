"""Offline audit regressions; fixtures do not fetch or fit models."""

import importlib.util
import json
from pathlib import Path

import pytest


def module(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "evaluation_audit", scripts / "audit_evaluation_feasibility.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def raw(log=None):
    return dict(
        match_id=1,
        start_time=100,
        duration=1800,
        players=[
            dict(hero_id=8 if i == 0 else 20 + i, account_id=i + 1, purchase_log=log)
            for i in range(10)
        ],
    )


@pytest.mark.parametrize(
    ("log", "status", "empty"),
    [
        (None, "missing", False),
        ([], "valid", True),
        ([{"key": "blink", "time": -1}], "valid", False),
        ([{"key": "blink", "time": float("inf")}], "invalid", False),
    ],
)
def test_log_semantics(monkeypatch, log, status, empty):
    m = module(monkeypatch)
    row = m.describe(raw(log))
    assert row["log_status"] == status
    assert row["log_empty"] is empty
    assert "labels" not in row


def test_anonymous_is_unknown_not_new_player(monkeypatch):
    m = module(monkeypatch)
    value = raw()
    value["players"][0]["account_id"] = 4294967295
    row = m.describe(value)
    assert row["target_account"] is None
    assert row["unknown_account_slots"] == 1


def test_strict_time_boundary_and_overlap(monkeypatch):
    m = module(monkeypatch)
    old = m.describe(raw())
    new = {**old, "match_id": 2, "start": old["end"]}
    result = m.summary([new], [old])
    assert result["after_all_old_ends"] == 0
    assert result["duplicate_old_matches"] == 0
    assert result["matches_sharing_any_old_account"] == 1


def test_transitive_links_do_not_imply_direct_overlap(monkeypatch):
    m = module(monkeypatch)
    result = m.components([{"accounts": [1]}], [{"accounts": [1, 2]}, {"accounts": [2, 3]}])
    assert result == dict(components=1, largest_match_count=3, new_matches_connected_to_old=2)


def test_hash_mismatch_and_drift(monkeypatch, tmp_path):
    m = module(monkeypatch)
    p = tmp_path / "input.json"
    p.write_text("{}")
    reader = m.CheckedReader()
    with pytest.raises(ValueError, match="Hash mismatch"):
        reader.read(p, "wrong")
    reader.read(p)
    p.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="drift"):
        reader.verify()


def test_output_refusal(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="Output exists"):
        module(monkeypatch).run(tmp_path)


def test_invalid_old_time_rejected(monkeypatch):
    value = raw()
    value["duration"] = None
    with pytest.raises(ValueError, match="clock"):
        module(monkeypatch).describe(value)


@pytest.mark.parametrize(
    "fault",
    ["one_source", "both_sources", "split", "targets", "mask", "probability", "label"],
)
def test_precision_is_paired_and_requires_same_identity(monkeypatch, fault):
    m = module(monkeypatch)
    labels = {key: i % 2 for i, key in enumerate(m.WHOLE_LOG_ITEMS)}
    rows = [
        dict(
            match_id=i,
            labels=labels,
            label_mask={k: True for k in labels},
            source_sha256=str(i),
            split="validation",
            probabilities={k: 0.5 for k in labels},
        )
        for i in (1, 2)
    ]

    class Reader:
        wrong = False

        def read(self, path, expected=None):
            if path.name == "complete.json":
                return {
                    "sha256": {
                        "frequency.validation.predictions.json": "hash",
                        "logistic_c0_1.validation.predictions.json": "hash",
                    }
                }
            result = json.loads(json.dumps(rows))
            if self.wrong:
                if fault == "one_source" and path.name.startswith("logistic"):
                    result[0]["source_sha256"] = "other"
                elif fault == "both_sources":
                    result[0]["source_sha256"] = "other"
                elif fault == "split":
                    result[0]["split"] = "train"
                elif fault == "targets":
                    for field in ("labels", "label_mask", "probabilities"):
                        result[0][field]["wrong_item"] = result[0][field].pop("bfury")
                elif fault == "mask":
                    result[0]["label_mask"]["bfury"] = "true"
                elif fault == "probability":
                    result[0]["probabilities"]["bfury"] = True
                elif fault == "label":
                    result[0]["labels"]["bfury"] = False
            return result

    reader = Reader()
    result = m.precision_scenarios(reader, {1: "1", 2: "2"})
    assert result["mean_difference"] == 0
    reader.wrong = True
    with pytest.raises(ValueError):
        m.precision_scenarios(reader, {1: "1", 2: "2"})
