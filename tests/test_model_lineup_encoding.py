"""Exercise actual prototype IO with non-UTF-8 defaults, without private models."""

import copy
import importlib
import json
import sys
from pathlib import Path

import pytest

from dota_items.contracts.tasks import WHOLE_LOG_TASK_ID, task_contract
from dota_items.storage import digest


@pytest.fixture
def apps(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    return tuple(importlib.import_module(n) for n in ("lineup_analysis", "lineup_comparison"))


def default_encoding(monkeypatch, encoding):
    """Emulate Path text IO under a legacy locale; explicit UTF-8 must win."""
    original = Path.open

    def open_text(self, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
        if "b" not in mode and encoding in (None, "locale"):
            encoding = legacy
        return original(self, mode, buffering, encoding, errors, newline)

    legacy = encoding
    monkeypatch.setattr(Path, "open", open_text)


@pytest.mark.parametrize("encoding", ["cp1252", "gbk"])
def test_analysis_export_utf8(apps, tmp_path, monkeypatch, encoding):
    app, _ = apps
    lineup = dict(app.DEFAULT, note="主宰·测试")
    source = tmp_path / "lineup.json"
    source.write_text(json.dumps(lineup, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "export"
    monkeypatch.setattr(app, "load_inputs", lambda: (None, None, [], {8: "主宰<script>"}))
    result = {"unknown_counts": {}, "items": [], "cases": [], "note": "中文结果"}

    def analyze(value, *_):
        assert value == lineup
        return result

    monkeypatch.setattr(app, "analyze", analyze)
    monkeypatch.setattr(
        sys, "argv", ["lineup_analysis", "--lineup", str(source), "--output", str(output)]
    )
    default_encoding(monkeypatch, encoding)
    app.main()
    assert json.loads((output / "analysis.json").read_bytes().decode("utf-8")) == result
    page = (output / "index.html").read_bytes().decode("utf-8")
    assert "主宰&lt;script&gt;" in page
    assert '<meta charset="utf-8">' in page


@pytest.mark.parametrize("encoding", ["cp1252", "gbk"])
def test_load_inputs_reads_utf8_heroes_and_snapshot(apps, tmp_path, monkeypatch, encoding):
    app, _ = apps
    contract = task_contract(WHOLE_LOG_TASK_ID)
    snapshot = {
        "preprocessing": {},
        "task": {"contract": contract},
        "samples": [{"split": "train"}] * 1592,
        "note": "中文快照",
    }
    source = tmp_path / "snapshot.json"
    source.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    heroes = tmp_path / "knowledge/hero-capabilities/heroes"
    heroes.mkdir(parents=True)
    (heroes / "8.json").write_text('{"hero_id":8,"name_zh":"主宰"}', encoding="utf-8")
    model = {"preprocessing": {}, "provenance": {"source_sha256": digest(snapshot)}}
    monkeypatch.setattr(app, "ROOT", tmp_path)
    monkeypatch.setattr(app, "SNAPSHOT", source)
    monkeypatch.setattr(app, "HASHES", {})
    monkeypatch.setattr(app, "load_model", lambda *_args, **_kwargs: model)
    default_encoding(monkeypatch, encoding)
    _, _, samples, names = app.load_inputs()
    assert len(samples) == 1592
    assert names == {8: "主宰"}


@pytest.mark.parametrize("encoding", ["cp1252", "gbk"])
def test_comparison_export_utf8(apps, tmp_path, monkeypatch, encoding):
    analysis, app = apps
    plan = {
        "base": analysis.DEFAULT,
        "known_task_gap": "中文范围说明",
        "cases": [
            {
                "with_enemy": 25,
                "replace_enemy": 10,
                "question": "换英雄？",
                "expectation": "探索假设",
            }
        ],
    }
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "export"
    output.mkdir()
    (output / "cases-before-prediction.json").write_bytes(source.read_bytes())
    monkeypatch.setattr(app, "CASES", source)

    def compare(a, b, *_):
        unknown = int(999999 in b["enemy_hero_ids"])
        return {
            "a": {"unknown_counts": {"ally": 0, "enemy": 0}},
            "b": {"unknown_counts": {"ally": 0, "enemy": unknown}},
            "changes": [],
            "exact_lineup_support": {"a": 0, "b": 0},
            "items": [],
        }

    monkeypatch.setattr(app, "compare", compare)
    default_encoding(monkeypatch, encoding)
    inputs = (None, None, [], {8: "主宰<script>"})
    result = app.run_cases(output, inputs)
    assert result["cases"][0]["case"] == plan["cases"][0]
    page = (output / "index.html").read_bytes().decode("utf-8")
    assert "换英雄？" in page and "主宰&lt;script&gt;" in page
    saved = json.loads((output / "results.json").read_bytes().decode("utf-8"))
    assert saved == result
    seal = json.loads((output / "complete.json").read_bytes().decode("utf-8"))
    assert all(app.file_hash(output / n) == h for n, h in seal["sha256"].items())
    assert copy.deepcopy(plan)["base"] == analysis.DEFAULT
