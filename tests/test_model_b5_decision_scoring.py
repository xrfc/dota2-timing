"""Contract and population regressions for the frozen B5 decision scorer."""

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from dota_items.modeling.awareness.decision_score import historical_preference

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/score_b5_decisions.py"
spec = importlib.util.spec_from_file_location("score_b5_decisions", CLI)
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


@pytest.fixture
def windrunner():
    return json.loads((ROOT / "examples/b5-wave-decision.json").read_bytes())


def test_condition_and_seal_do_not_leak_later_events(windrunner):
    result = scorer.check_case(windrunner)
    assert result["verdict"] == "conditional"
    assert scorer.check_case(dict(windrunner, action="farm", observed={"gold": 139})) == result
    wrong = dict(windrunner, proposal={"kind": "recommend", "action": "rotate_to_jungle"})
    failure = scorer.check_case(wrong)
    assert failure["verdict"] == "action_not_estimated"
    assert failure["snapshot_sha256"] == result["snapshot_sha256"]
    assert failure["decision_sha256"] != result["decision_sha256"]


@pytest.mark.parametrize("action", ["farm", "retreat"])
def test_tradeoff_needs_value_judgment(windrunner, action):
    windrunner["proposal"] = {"kind": "recommend", "action": action}
    assert scorer.check_case(windrunner)["verdict"] == "no_dominance"


def test_balance_threshold_and_missing_balance(windrunner):
    v = windrunner["values"]
    v["retreat"] = dict(v["farm"], gold=v["farm"]["gold"] - 1)
    windrunner["proposal"] = {"kind": "recommend", "action": "farm"}
    for balance, verdict in [
        (0.25, "supported"),
        (0.25001, "insufficient_balance"),
        (None, "insufficient_balance"),
    ]:
        assert scorer.check_case(dict(windrunner, balance_after=balance))["verdict"] == verdict
    assert scorer.check_case(dict(windrunner, values=None))["verdict"] == "no_joint_support"
    v["farm"]["xp"] = None
    assert scorer.check_case(windrunner)["verdict"] == "no_dominance"


def test_missing_metric_and_unknown_condition_fail(windrunner):
    del windrunner["values"]["farm"]["death"]
    with pytest.raises(ValueError, match="metric set"):
        scorer.check_case(windrunner)


def test_invalid_condition_and_schema(windrunner):
    windrunner["proposal"]["condition"] = "higher_cash_in_retreat_group"
    with pytest.raises(ValueError, match="condition"):
        scorer.check_case(windrunner)
    with pytest.raises(ValueError, match="schema"):
        scorer.check_case(dict(windrunner, schema="unknown"))


def test_cli_returns_failure_for_an_unsupported_claim(tmp_path, windrunner):
    case = tmp_path / "case.json"
    for proposal, code in [
        (windrunner["proposal"], 0),
        ({"kind": "recommend", "action": "rotate_to_jungle"}, 2),
    ]:
        case.write_text(json.dumps(dict(windrunner, proposal=proposal)))
        result = subprocess.run(
            [sys.executable, str(CLI), "check", str(case)], capture_output=True, check=False
        )
        assert result.returncode == code
        assert json.loads(result.stdout)["decision_sha256"]


def test_only_measured_factual_pairs_and_all_opportunities_count(windrunner):
    values = windrunner["values"]
    obs = dict(hits=1, death=0, gold=100, xp=None, dead_seconds=0)
    row = dict(
        match=9081112126,
        hero="a",
        t=913,
        fold=0,
        action="farm",
        outcome_eligible=True,
        early_death=False,
        window_complete=True,
        **obs,
    )
    excluded = dict(row, t=928, action="unknown", outcome_eligible=False, early_death=True)
    pred = dict(
        row, observed=obs, values=values, ranking="tradeoff", stratum=1, overlap_reason=None
    )
    summary = {
        "folds": {
            "0": {
                "training_strata": {
                    "1": {
                        "arms": {a: {"values": v} for a, v in values.items()},
                        "balance": {"after": 0.15},
                    }
                }
            }
        }
    }
    out = scorer.score_domain("wave", [row, excluded], [pred], summary)
    assert (out["opportunities"], out["eligible"], out["comparable"], out["unscored"]) == (
        2,
        1,
        1,
        1,
    )
    assert out["exclusion_flags"] == {"unknown_action": 1, "early_death": 1}
    assert out["unsupported_rate"] is None
    assert out["factual"]["gold"]["value"] == pytest.approx(121.76)
    assert out["factual"]["xp"]["value"] is None
    assert out["factual"]["death"]["value"] == pytest.approx(0.033**2)
    for bad, why in [
        ([], "cover"),
        ([pred, pred], "cover"),
        ([dict(pred, fold=1)], "fold"),
        ([dict(pred, observed=dict(obs, gold=101))], "observation"),
    ]:
        with pytest.raises(ValueError, match=why):
            scorer.score_domain("wave", [row, excluded], bad, summary)
    changed = deepcopy(summary)
    changed["folds"]["0"]["training_strata"]["1"]["arms"]["farm"]["values"]["gold"] = 0
    with pytest.raises(ValueError, match="stratum"):
        scorer.score_domain("wave", [row], [pred], changed)
    with pytest.raises(ValueError, match="reserved match, or wrong"):
        scorer.score_domain("wave", [dict(row, fold=1)], [], summary)


def test_unknown_values_cannot_win(windrunner):
    values = windrunner["values"]
    values["farm"]["arrival"] = 1
    with pytest.raises(ValueError):
        historical_preference("wave", values)


def test_changed_frozen_input_fails(tmp_path):
    f = tmp_path / "predictions.jsonl"
    f.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256"):
        scorer.verified_bytes(f, "0" * 64)


@pytest.mark.parametrize("proposal", [None, [], {"kind": "recommend", "action": None}])
def test_malformed_proposals_are_contract_errors(windrunner, proposal):
    with pytest.raises(ValueError, match="proposal"):
        scorer.check_case(dict(windrunner, proposal=proposal))
