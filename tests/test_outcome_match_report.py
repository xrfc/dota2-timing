import hashlib
import json

import pytest

from scripts.outcome_match_report import DOMAINS, match_cases, render


def row(t):
    actual = {"hits": 2, "gold": -30, "xp": None, "death": 0, "dead_seconds": 0}
    return {
        "t": t,
        "match": 9081112126,
        "hero": "npc_dota_hero_drow_ranger",
        "fold": 0,
        "action": "farm",
        "observed": actual,
        "stratum": 1,
        "overlap_reason": None,
        "values": {"farm": {**actual, "death": 0.25}, "retreat": actual},
    }


def test_report_shows_observation_and_only_balanced_estimates():
    r = row(65)
    for after, reason in ((0.25, None), (0.251, None), (None, "sparse_training_arm")):
        text = render(r["match"], [("wave", {**r, "overlap_reason": reason}, after)], {})
        assert "1:05" in text and "录像实况 | 2 | -30 | 缺测 | 否" in text
        assert ("25.0%" in text) == (after == 0.25)
        assert ("后撤估计" in text) == (after == 0.25)


def test_report_filters_and_hash_checks_even_unselected_records(tmp_path):
    evidence = {}
    for domain in DOMAINS:
        folder = tmp_path / domain
        folder.mkdir()
        records = [row(900), {**row(850), "match": 1}, row(800)] if domain == "wave" else []
        payload = "".join(json.dumps(r) + "\n" for r in records).encode()
        path = folder / "predictions.jsonl"
        path.write_bytes(payload)
        evidence[domain] = {
            "predictions_sha256": hashlib.sha256(payload).hexdigest(),
            "training_strata_by_fold": {"0": {"1": {"balance": {"after": 0.25}}}},
        }
    assert [r["t"] for _, r, _ in match_cases(9081112126, tmp_path, evidence)] == [800, 900]
    with pytest.raises(ValueError, match="无该场"):
        match_cases(9081112027, tmp_path, evidence)
    path.write_text(json.dumps({**row(85), "match": 1}))
    with pytest.raises(ValueError, match="指纹"):
        match_cases(9081112126, tmp_path, evidence)


def test_reserved_match_rejected_before_file_access(tmp_path):
    from dota_items.data.awareness_split import is_holdout

    with pytest.raises(ValueError, match="留出集"):
        match_cases(next(n for n in range(100) if is_holdout(n)), tmp_path, {})


def test_existing_inputs_match_exact_demo_and_embedded_id(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from scripts.outcome_match_report import from_demo

    demo = tmp_path / "local.dem"
    demo.write_bytes(b"sample replay")
    cache = tmp_path / "inputs"
    cache.mkdir()
    manifest = cache / "replay-provenance.json"
    manifest.write_text(
        json.dumps(
            {"source_sha256": hashlib.sha256(demo.read_bytes()).hexdigest(), "match_id": 123}
        )
    )
    monkeypatch.setitem(sys.modules, "new_replay_inputs", SimpleNamespace(prepare=None))
    monkeypatch.setitem(
        sys.modules,
        "new_replay_outcomes",
        SimpleNamespace(infer=lambda root, mid, map_dir: ([], {"match": mid})),
    )
    assert from_demo(demo, cache, None, tmp_path) == (123, [], {"match": 123})
    with pytest.raises(ValueError, match="比赛编号"):
        from_demo(demo, cache, 124, tmp_path)
    demo.write_bytes(b"other")
    with pytest.raises(ValueError, match="其他录像"):
        from_demo(demo, cache, None, tmp_path)
