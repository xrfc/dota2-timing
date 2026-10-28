"""Read-only prototype acceptance with frozen local models (no fitting)."""

import copy
import importlib.util
import math
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import pytest

from dota_items.modeling.lineup_analysis import analyze


@pytest.fixture(scope="module")
def app():
    path = Path(__file__).parents[1] / "scripts/lineup_analysis.py"
    spec = importlib.util.spec_from_file_location("lineup_web", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not module.MODEL.exists():
        pytest.skip("Private frozen model assets are not distributed in git")
    return module, module.load_inputs()


def test_explanation_reconstructs_and_frequency_is_not_intercept(app):
    m, (model, base, samples, _) = app
    result = analyze(m.DEFAULT, model, base, samples)
    assert len(result["items"]) == 11
    assert not result["recommendation_validated"]
    for row in result["items"]:
        z = row["intercept"] + sum(t["contribution"] for t in row["contributions"])
        assert math.isclose(1 / (1 + math.exp(-z)), row["probability"], abs_tol=1e-12)
        assert row["delta_pp"] == 100 * (row["probability"] - row["baseline"])


def test_enemy_swap_changes_model_not_baseline(app):
    m, (model, base, samples, _) = app
    changed = copy.deepcopy(m.DEFAULT)
    changed["enemy_hero_ids"][0] = 25
    a = analyze(m.DEFAULT, model, base, samples)
    b = analyze(changed, model, base, samples)
    keyed_a = {r["item"]: r for r in a["items"]}
    keyed_b = {r["item"]: r for r in b["items"]}
    assert any(keyed_a[k]["probability"] != keyed_b[k]["probability"] for k in keyed_a)
    assert all(keyed_a[k]["baseline"] == keyed_b[k]["baseline"] for k in keyed_a)


def test_cases_train_only_and_do_not_depend_on_labels(app):
    m, (model, base, samples, _) = app
    a = analyze(m.DEFAULT, model, base, samples)
    altered = copy.deepcopy(samples)
    for r in altered:
        r["labels"] = [1 - y for y in r["labels"]]
    fake_validation = dict(altered[0], match_id=1, features=m.DEFAULT, split="validation")
    b = analyze(m.DEFAULT, model, base, [fake_validation] + altered[::-1])
    assert [r["match_id"] for r in a["cases"]] == [r["match_id"] for r in b["cases"]]
    assert all(r["split"] == "train" and r["match_id"] != 1 for r in b["cases"])


@pytest.mark.parametrize("fault", ["duplicate", "missing_target", "wrong_length", "boolean"])
def test_invalid_lineup_rejected(app, fault):
    m, inputs = app
    lineup = copy.deepcopy(m.DEFAULT)
    if fault == "duplicate":
        lineup["enemy_hero_ids"][0] = 8
    elif fault == "missing_target":
        lineup["ally_hero_ids"][0] = 25
    elif fault == "boolean":
        lineup["ally_hero_ids"][1] = True
    else:
        lineup["ally_hero_ids"].pop()
    with pytest.raises(ValueError):
        analyze(lineup, *inputs[:3])


def test_unknown_hero_flag_and_html_escaping(app):
    m, inputs = app
    lineup = copy.deepcopy(m.DEFAULT)
    lineup["enemy_hero_ids"][0] = 999999
    result = analyze(lineup, *inputs[:3])
    assert result["unknown_counts"]["enemy"] == 1
    document = m.page(lineup, result, {999999: "<script>alert(1)</script>"})
    assert "<script>" not in document
    assert "含训练词表外英雄" in document


def test_http_form_valid_invalid_and_no_file_access(app):
    m, inputs = app
    with m.HTTPServer(("127.0.0.1", 0), m.make_handler(inputs)) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(url) as response:
                text = response.read().decode()
                assert text.count("<select ") == 10
                assert "模型购买倾向" in text and "训练集中的相近阵容" in text
            query = {
                f"{side}{i}": hero
                for side in ["ally", "enemy"]
                for i, hero in enumerate(m.DEFAULT[side + "_hero_ids"])
            }
            query["enemy0"] = 25
            with urlopen(url + "/?" + urlencode(query)) as response:
                assert response.status == 200
            query["enemy0"] = 8
            with pytest.raises(HTTPError) as error:
                urlopen(url + "/?" + urlencode(query))
            assert error.value.code == 400
            with pytest.raises(HTTPError) as error:
                urlopen(url + "/reports/snapshot.json")
            assert error.value.code == 404
        finally:
            server.shutdown()
            worker.join(timeout=2)
