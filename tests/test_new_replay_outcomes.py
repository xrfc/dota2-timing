import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("new_replay_outcomes")


def test_holdout_refused_before_opening_input_or_model(adapter, tmp_path):
    mid = next(i for i in range(1, 100) if adapter.is_holdout(i))
    with pytest.raises(ValueError, match="non-reserved"):
        adapter.infer(tmp_path, mid, tmp_path)


def test_provenance_must_cover_exact_paths_and_disallow_cached_pickle(adapter, tmp_path):
    meta = tmp_path / "replay-provenance.json"
    mid = 12
    meta.write_text(json.dumps({"match_id": mid, "inputs_sha256": {"unrelated": "bad"}}))
    with pytest.raises(ValueError, match="input file list"):
        adapter._input_info(tmp_path, mid)
    paths = [
        f"{kind}/{mid}.{suffix}.gz"
        for kind, suffix in (
            ("parsed", "normalized.json"),
            ("state-v3", "jsonl"),
            ("extras-v1", "jsonl"),
        )
    ]
    meta.write_text(json.dumps({"match_id": mid, "inputs_sha256": dict.fromkeys(paths, "bad")}))
    (tmp_path / "gank-inputs-v2").mkdir()
    (tmp_path / "gank-inputs-v2" / "12.pkl").write_bytes(b"untrusted")
    with pytest.raises(ValueError, match="uncached"):
        adapter._input_info(tmp_path, mid)


def test_independent_domain_scores_preserve_support_and_unknown_rank(
    adapter, tmp_path, monkeypatch
):
    mid = 12
    monkeypatch.setattr(
        adapter,
        "_frozen",
        lambda *args: {
            "models": {},
            "compat": {"manifest.json": "verified"},
            "versions": {"gem-dota": "test"},
        },
    )
    monkeypatch.setattr(
        adapter,
        "_input_info",
        lambda *args: {
            "schema": "new-replay-inputs/1",
            "player_count": 10,
            "parser_version": "test",
            "compat_manifest_sha256": "verified",
            "source_sha256": "x",
            "inputs_sha256": {},
            "patch_window": "7.41f",
            "game_mode": 22,
        },
    )

    def row(t):
        return dict(
            hero="hero",
            t=t,
            match=mid,
            action="farm",
            outcome_eligible=t != 5,
            early_death=False,
            window_complete=True,
        )

    monkeypatch.setattr(adapter, "match_rows", lambda job: [row(8), row(5)])
    monkeypatch.setattr(adapter, "label_match", lambda root, mid, rows: rows)
    monkeypatch.setattr(
        adapter,
        "_other_rows",
        lambda root, mid: ([{**row(7), "domain": "support", "action": "stay"}], ["hero"]),
    )
    monkeypatch.setattr(
        adapter.joblib, "load", lambda path: {"strata": {1: {"balance": {"after": 0.25}}}}
    )
    monkeypatch.setattr(
        adapter,
        "score",
        lambda model, rows: [
            {**r, "stratum": 1, "overlap_reason": None if r["t"] == 8 else "sparse_training_arm"}
            for r in rows
        ],
    )
    cases, info = adapter.infer(tmp_path, mid, tmp_path)
    assert [(d, after) for d, _, after in cases] == [("support", None), ("wave", 0.25)]
    assert info["observed_heroes"] == ["hero"]
    assert info["rank_tier"] is None
    assert not info["population_verified"]
    assert info["by_domain"]["wave"]["opportunities"] == 2
    assert info["by_domain"]["wave"]["balanced"] == 1
    assert info["by_domain"]["support"]["balanced"] == 0
    assert info["by_domain"]["jungle"]["eligible"] == 0
