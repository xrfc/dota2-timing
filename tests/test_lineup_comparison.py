"""Paired explanations, support denominators and web interactions; no fitting."""

import copy
import importlib
import json
import math
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import pytest

from dota_items.modeling.lineup_comparison import compare


@pytest.fixture
def app(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    m = importlib.import_module("lineup_comparison")
    if not (
        m.ROOT / "reports/whole-log-regularization-2026-10-22/logistic_c0_1.model.json"
    ).is_file():
        pytest.skip("Local frozen models unavailable")
    return m, m.load_inputs(), json.loads(m.CASES.read_text())


def test_swap_explanation_and_support_are_exact(app):
    m, inputs, plan = app
    a, b = m.default_pair(plan)
    result = compare(a, b, *inputs[:3])
    assert len(result["changes"]) == 2
    for row in result["items"]:
        assert math.isclose(
            sum(t["difference"] for t in row["contribution_changes"]),
            row["delta_logit"],
            abs_tol=1e-12,
        )
        assert row["delta_pp"] == 100 * (row["b"] - row["a"])
    for g in result["hero_support"]:
        rows = [
            s
            for s in inputs[2]
            if s["split"] == "train" and g["hero_id"] in s["features"][g["side"] + "_hero_ids"]
        ]
        assert g["matches"] == len(rows)
        for index, item in enumerate(m.compare.__globals__["ITEM_NAMES"]):
            known = [s for s in rows if s["label_mask"][index]]
            assert g["items"][item]["positive"] == sum(s["labels"][index] for s in known)
            assert g["items"][item]["observed"] == len(known)


def test_side_order_invariance_and_reversal(app):
    m, inputs, plan = app
    a, b = m.default_pair(plan)
    same = copy.deepcopy(a)
    same["enemy_hero_ids"].reverse()
    invariant = compare(a, same, *inputs[:3])
    assert invariant["changes"] == []
    assert all(r["delta_pp"] == 0 for r in invariant["items"])
    forward = compare(a, b, *inputs[:3])
    backward = compare(b, a, *inputs[:3])
    keyed = {r["item"]: r for r in backward["items"]}
    assert all(
        math.isclose(r["delta_pp"], -keyed[r["item"]]["delta_pp"], abs_tol=1e-12)
        for r in forward["items"]
    )


def test_no_explicit_interaction_in_logit_space(app):
    m, inputs, plan = app
    a, b = m.default_pair(plan)
    first = compare(a, b, *inputs[:3])
    a["ally_hero_ids"][1] = 23
    b["ally_hero_ids"][1] = 23
    second = compare(a, b, *inputs[:3])
    keyed = {r["item"]: r for r in second["items"]}
    assert all(
        math.isclose(r["delta_logit"], keyed[r["item"]]["delta_logit"], abs_tol=1e-12)
        for r in first["items"]
    )


def test_validation_does_not_inflate_support_and_masks_stay_unknown(app):
    m, inputs, plan = app
    a, b = m.default_pair(plan)
    samples = copy.deepcopy(inputs[2])
    row = next(r for r in samples if 12 in r["features"]["enemy_hero_ids"])
    row["label_mask"][0] = False
    validation = dict(row, split="validation")
    result = compare(a, b, inputs[0], inputs[1], samples + [validation])
    g = next(g for g in result["hero_support"] if g["hero_id"] == 12)
    assert g["matches"] == sum(12 in r["features"]["enemy_hero_ids"] for r in samples)
    assert g["items"]["bfury"]["unknown"] == 1
    assert g["items"]["bfury"]["observed"] == g["matches"] - 1


def test_multiple_changes_unknown_and_invalid(app):
    m, inputs, plan = app
    a, b = m.default_pair(plan)
    b["enemy_hero_ids"][1] = 999999
    result = compare(a, b, *inputs[:3])
    assert result["b"]["unknown_counts"]["enemy"] == 1
    assert len(result["changes"]) == 4
    assert "训练词表外" in m.render(result, inputs[3])
    b["enemy_hero_ids"][1] = 8
    with pytest.raises(ValueError):
        compare(a, b, *inputs[:3])


def test_plan_drift_and_overwrite_rejected(app, tmp_path):
    m, inputs, _ = app
    frozen = tmp_path / "cases-before-prediction.json"
    frozen.write_text("{}")
    with pytest.raises(ValueError, match="missing or changed"):
        m.run_cases(tmp_path, inputs)
    frozen.write_bytes(m.CASES.read_bytes())
    result = m.run_cases(tmp_path, inputs)
    seal = json.loads((tmp_path / "complete.json").read_text())
    assert "complete.json" not in seal["sha256"]
    assert all(m.file_hash(tmp_path / name) == sha for name, sha in seal["sha256"].items())
    assert len(result["cases"]) == 6
    assert result["mechanical_checks"] == dict(permutation_invariant=True, unknown_flagged=True)
    with pytest.raises(ValueError, match="already used"):
        m.run_cases(tmp_path, inputs)


def test_http_pair_submission_and_error(app):
    m, inputs, plan = app
    with m.HTTPServer(("127.0.0.1", 0), m.handler(inputs, plan)) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f"http://127.0.0.1:{server.server_port}/"
        try:
            with urlopen(url) as response:
                text = response.read().decode()
                assert text.count("<select ") == 20
                assert "解释与训练支持" in text
            a, b = m.default_pair(plan)
            query = {
                f"{tag}_{side}{i}": h
                for tag, lineup in [("a", a), ("b", b)]
                for side in ("ally", "enemy")
                for i, h in enumerate(lineup[side + "_hero_ids"])
            }
            query["b_enemy0"] = 44
            with urlopen(url + "?" + urlencode(query)) as response:
                assert "幻影刺客" in response.read().decode()
            query["b_enemy0"] = 8
            with pytest.raises(HTTPError) as error:
                urlopen(url + "?" + urlencode(query))
            assert error.value.code == 400
            with pytest.raises(HTTPError) as error:
                urlopen(url + "?a_ally0=8")
            assert error.value.code == 400
        finally:
            server.shutdown()
            worker.join(timeout=2)
