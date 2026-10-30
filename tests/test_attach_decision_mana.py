"""Redecoded mana enters a NEW package only, at the decision tick, never from the future."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from dota_items.data.decision_mana import attach_current_mana
from dota_items.storage import file_hash

STATUS = "redecoded_source_observation_not_independent_gameplay_certification"


def load():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "attach", root / "scripts/attach_decision_mana.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sources(future_mana=330.0):
    live = {
        "tick": 30,
        "health": {"current": 1313, "max": 1330},
        "mana": {"raw": 70.875, "raw_max": 70.875, "scale_correction_applied": False},
    }
    rows = [
        {"tick": t, "hero": {"values": {"m_iHealth": 1313, "m_iMaxHealth": 1330, **m}}}
        for t, m in (
            (0, {"m_flMana": 300.0, "m_flMaxMana": 567.0}),
            (30, {"m_flMana": 567.0, "m_flMaxMana": 567.0}),
            (60, {"m_flMana": future_mana, "m_flMaxMana": 567.0}),
        )
    ]
    capture = {
        "match_id": 7,
        "decision_tick": 30,
        "producer": "decision-build-first/1",
        "build": 6965,
        "rows": rows,
    }
    comparison = {
        "match_id": 7,
        "decision_tick": 30,
        "paired_samples": [
            {
                "tick": 30,
                "resources": [
                    {"field": "m_flMana", "old": 70.875, "redecoded": 567.0},
                    {"field": "m_flMaxMana", "old": 70.875, "redecoded": 567.0},
                ],
            }
        ],
    }
    resource = {
        "match_id": 7,
        "tick": 30,
        "mana": 567.0,
        "max_mana": 567.0,
        "status": STATUS,
        "training_allowed": False,
    }
    return live, resource, capture, comparison


def test_attach_replaces_only_audited_old_reading_at_decision_tick():
    live, *rest = sources()
    card = attach_current_mana(live, *rest, "ref")
    assert card["mana"]["current"] == card["mana"]["max"] == 567.0
    assert card["mana"]["replaced_reading"]["raw"] == 70.875
    assert card["mana"]["can_cast"] is None
    assert live["mana"]["raw"] == 70.875
    later = attach_current_mana(live, *sources(future_mana=1.0)[1:], "ref")
    assert later == card


@pytest.mark.parametrize(
    "change",
    [
        lambda live, r, c, p: live["health"].update(current=1),
        lambda live, r, c, p: live["mana"].update(raw=71.0),
        lambda live, r, c, p: live["mana"].update(scale_correction_applied=True),
        lambda live, r, c, p: r.update(tick=60),
        lambda live, r, c, p: r.update(mana=500.0),
        lambda live, r, c, p: r.update(training_allowed=True),
        lambda live, r, c, p: c.update(producer="old"),
        lambda live, r, c, p: c["rows"].append(copy.deepcopy(c["rows"][1])),
        lambda live, r, c, p: p.update(paired_samples=[]),
    ],
)
def test_attach_rejects_mismatched_or_unaudited_sources(change):
    parts = sources()
    change(*parts)
    with pytest.raises(ValueError):
        attach_current_mana(*parts, "ref")


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def repo_fixture(tmp_path):
    module = load()
    repo = tmp_path / "repo"
    live, resource, capture, comparison = sources()
    base = repo / "reports/base"
    card = {
        "case": {"id": "one", "match_id": 7, "tick": 30},
        "evidence": {"decision_input": {"tick": 30, "positions": []}},
        "enhancement": {"live_state_card": live},
    }
    dump(base / "cases.json", {"cards": [card, {"case": {"id": "two"}, "evidence": {}}]})
    (base / "one-after.json").write_bytes(b'{"future":123}\n')
    (base / "annotation-draft.json").write_bytes(b'{"training_allowed":false}\n')
    outputs = {p.name: file_hash(p) for p in base.glob("*.json")}
    dump(base / "verification.json", {"source_files": {}, "outputs": outputs})
    repair = repo / "reports/repair"
    match = repair / "7"
    for name, value in (
        ("current-resource.json", resource),
        ("capture.json", capture),
        ("comparison.json", comparison),
    ):
        dump(match / name, value)
    complete = {"match_id": 7, "training_allowed": False, "outputs": {}}
    complete["outputs"] = {p.name: file_hash(p) for p in match.glob("*.json")}
    dump(match / "complete.json", complete)
    dump(repair / "results.json", {"training_allowed": False})
    acceptance = {
        "training_performed": False,
        "outputs": {"results.json": file_hash(repair / "results.json")},
    }
    dump(repair / "acceptance.json", acceptance)
    for name in module.IMPLEMENTATION:
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text("fixture")
    return module, repo, base


def test_new_package_binds_repair_and_keeps_base_bytes(tmp_path):
    module, repo, base = repo_fixture(tmp_path)
    before = {p.name: p.read_bytes() for p in base.iterdir()}
    result = module.attach("reports/new", "reports/base", "reports/repair", repo)
    assert result["attached"] == 1
    assert {p.name: p.read_bytes() for p in base.iterdir()} == before
    new = repo / "reports/new"
    assert (new / "one-after.json").read_bytes() == before["one-after.json"]
    package = json.loads((new / "cases.json").read_text())
    old = json.loads(before["cases.json"])
    assert package["cards"][0]["evidence"] == old["cards"][0]["evidence"]
    mana = package["cards"][0]["enhancement"]["live_state_card"]["mana"]
    assert (
        mana["current"] == 567.0 and mana["source_ref"] == "reports/repair/7/current-resource.json"
    )
    assert package["resource_revision"]["training_allowed"] is False
    verification = json.loads((new / "verification.json").read_text())
    assert all(file_hash(new / n) == h for n, h in verification["outputs"].items())
    assert str(repo / "reports/repair/7/capture.json") in verification["source_files"]
    with pytest.raises(ValueError, match="Output exists"):
        module.attach("reports/new", "reports/base", "reports/repair", repo)


@pytest.mark.parametrize("target", ["reports/base/one-after.json", "reports/repair/7/capture.json"])
def test_source_drift_rejected_without_output(tmp_path, target):
    module, repo, _ = repo_fixture(tmp_path)
    (repo / target).write_bytes(b"{}")
    with pytest.raises(ValueError, match="drift"):
        module.attach("reports/new", "reports/base", "reports/repair", repo)
    assert not (repo / "reports/new").exists()


def test_escaping_paths_rejected(tmp_path):
    module, repo, _ = repo_fixture(tmp_path)
    with pytest.raises(ValueError, match="Invalid"):
        module.attach("../out", "reports/base", "reports/repair", repo)
