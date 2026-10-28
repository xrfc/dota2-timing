"""Source probe uses synthetic HTTP only; real budget never touched."""

import importlib.util
import json
import time
from pathlib import Path

import httpx
import pytest


def setup_probe(monkeypatch, tmp_path):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    monkeypatch.delenv("OPENDOTA_API_KEY", raising=False)
    spec = importlib.util.spec_from_file_location(
        "probe_sources", scripts / "probe_evaluation_sources.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    failed, budget = tmp_path / "failed.json", tmp_path / "budget.json"
    failed.write_text(json.dumps(dict(status=400, sql="SELECT match_id FROM public_matches")))
    budget.write_text(json.dumps(dict(requests=[time.time() - 100], blocked_until=0)))
    return m, failed, budget


@pytest.mark.parametrize(
    "fault", ["none", "400", "429", "disconnect", "wrong_id", "minute", "app_error", "patch"]
)
def test_bounded_probe_and_failure_evidence(monkeypatch, tmp_path, fault):
    m, failed, budget = setup_probe(monkeypatch, tmp_path)
    # Keep the real budget logic; avoid actual inter-request waiting in mock tests.
    monkeypatch.setattr(m.RequestBudget, "__init__", _no_sleep_init(m.RequestBudget.__init__))
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "www.dota2.com":
            return httpx.Response(
                200,
                json={
                    "patches": [
                        {
                            "patch_number": "7.41f" if fault != "patch" else "7.41e",
                            "patch_timestamp": 100,
                        }
                    ]
                },
            )
        if request.url.path.endswith("explorer"):
            assert request.url.params["sql"] == "SELECT match_id FROM public_matches"
            if fault == "disconnect":
                raise httpx.ReadError("mock disconnect", request=request)
            if fault in ("400", "429"):
                return httpx.Response(int(fault), json={"err": "Query read timeout"})
            return httpx.Response(
                200,
                json={"rows": [], "err": "error" if fault == "app_error" else None},
                headers={"X-Rate-Limit-Remaining-Minute": "5"} if fault == "minute" else {},
            )
        return httpx.Response(200, json={"match_id": 1 if fault == "wrong_id" else m.MATCH_ID})

    output = tmp_path / "out"
    result = m.run(
        output, failed=failed, budget_path=budget, transport=httpx.MockTransport(handler)
    )
    assert len(calls) == (1 if fault == "patch" else 3 if fault in ("none", "wrong_id") else 2)
    assert result["state"] == (
        "completed"
        if fault == "none"
        else "paused_budget"
        if fault in ("429", "minute")
        else "failed"
    )
    assert result["training_allowed"] is False
    assert result["formal_split_assigned"] is False
    assert len(json.loads(budget.read_text())["requests"]) == len(calls)
    if fault in ("400", "429"):
        assert json.loads((output / "discovery.response.json").read_text())["err"]
        assert result["rows"][-1]["response_saved"] is True
    if fault == "disconnect":
        assert result["rows"][-1]["request_reserved"] is True
        assert result["rows"][-1]["response_saved"] is False
    receipt = json.loads((output / "complete.json").read_text())
    assert all(m.file_hash(output / name) == digest for name, digest in receipt["sha256"].items())
    assert json.loads((output / "plan.json").read_text())["max_http_requests"] == 3


def _no_sleep_init(original):
    def init(self, path):
        original(self, path, sleep=lambda _: None)

    return init


def test_existing_cooldown_preserved(monkeypatch, tmp_path):
    m, failed, budget = setup_probe(monkeypatch, tmp_path)
    initial = dict(requests=[time.time() - 100], blocked_until=time.time() + 3600)
    budget.write_text(json.dumps(initial))
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json={"patches": [{"patch_number": "7.41f", "patch_timestamp": 100}]}
        )

    result = m.run(
        tmp_path / "out", failed=failed, budget_path=budget, transport=httpx.MockTransport(handler)
    )
    assert len(calls) == 1  # Official patch source is not OpenDota quota.
    assert result["state"] == "paused_budget"
    assert json.loads(budget.read_text()) == initial
    assert result["rows"][-1]["request_reserved"] is False


def test_missing_budget_and_existing_output_refused(monkeypatch, tmp_path):
    m, failed, budget = setup_probe(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="Existing route budget"):
        m.run(tmp_path / "out", failed=failed, budget_path=tmp_path / "absent")
    with pytest.raises(ValueError, match="New output"):
        m.run(tmp_path, failed=failed, budget_path=budget)
