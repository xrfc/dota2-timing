import importlib
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def values(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("outcome_values")


def test_weighted_arm_uses_observation_probability_and_label_specific_support(values):
    rows = [{"match": i, "gold": i * 2, "xp": None} for i in range(12)]
    prob = np.linspace(0.3, 0.48, len(rows))
    out = values.weighted_arm(rows, prob, ("gold", "xp"))
    assert out["values"]["gold"] == pytest.approx(
        np.average([r["gold"] for r in rows], weights=1 / prob)
    )
    assert out["values"]["xp"] is None
    assert 10 < out["effective_n"]["gold"] <= 12
    repeated = [{**r, "match": 1} for r in rows]
    assert not values.weighted_arm(repeated, prob, ("gold",))["supported"]


def test_prediction_uses_only_predecision_state_and_abstains_without_overlap(values):
    arms = ("farm", "retreat")
    train = [
        {
            "match": i,
            "static": [1.0],
            "sequence": [[1.0]] * 3,
            "action": arms[i % 2],
            "gold": 10 + i % 2,
            "death": 0,
        }
        for i in range(100)
    ]
    model = values.fit_value(train, arms, ("gold", "death"))
    query = {"static": [1.0], "sequence": [[1.0]] * 3}
    a, b = values.estimate(model, [query, {**query, "action": "unknown", "gold": -999}])
    assert a == b
    assert a["values"]["farm"]["gold"] == 10 and a["values"]["retreat"]["gold"] == 11
    assert a["ranking"] == "retreat"
    single = values.fit_value(train[::2], arms, ("gold", "death"))
    record = values.estimate(single, [query])[0]
    assert record["overlap_reason"] and record["values"] is None


def test_conflicting_endpoints_remain_a_tradeoff(values):
    preds = {"farm": {"gold": 10, "death": 0.2}, "retreat": {"gold": 3, "death": 0.1}}
    assert values.pareto(preds, ("gold", "death")) == "tradeoff"
    preds["farm"]["gold"] = None
    assert values.pareto(preds, ("gold", "death")) == "incomplete"


def test_development_reader_validates_schema_digest_split_and_unique_cases(values, tmp_path):
    import json

    data = tmp_path / "rows.jsonl"
    meta = tmp_path / "summary.json"
    dev = next(i for i in range(100) if not values.is_holdout(i))
    reserved = next(i for i in range(100) if values.is_holdout(i))
    row = {
        "match": dev,
        "hero": "h",
        "t": 900,
        "fold": values.fold_for(dev),
        "outcome_eligible": True,
    }
    for records, schema, valid in (
        ([row], "wrong", False),
        ([row, row], "outcome-labels/1", False),
        ([{**row, "match": reserved}], "outcome-labels/1", False),
        ([row], "outcome-labels/1", True),
    ):
        data.write_text("".join(json.dumps(r) + "\n" for r in records))
        meta.write_text(
            json.dumps(
                {
                    "schema": schema,
                    "split": "development",
                    "domain": "wave",
                    "rows_sha256": values.file_hash(data),
                    "rows": len(records),
                    "eligible": len(records),
                }
            )
        )
        if valid:
            assert values.read_dataset(tmp_path, "wave")[0] == records
        else:
            with pytest.raises(ValueError):
                values.read_dataset(tmp_path, "wave")
    data.write_text("{}\n")
    with pytest.raises(ValueError):
        values.read_dataset(tmp_path, "wave")
