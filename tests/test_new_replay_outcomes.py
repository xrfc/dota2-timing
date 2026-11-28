import gzip
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


def test_independence_checks_the_full_roster_and_both_dataset_receipts(
    adapter, tmp_path, monkeypatch
):
    monkeypatch.setattr(adapter, "ROOT", tmp_path)
    monkeypatch.setattr(adapter, "REPORTS", tmp_path / "reports")
    ids = [i for i in range(1, 100) if not adapter.is_holdout(i)][:3]
    folder = adapter.REPORTS / "outcome-domains"
    folder.mkdir(parents=True)
    acceptance = tmp_path / "docs/acceptance"
    acceptance.mkdir(parents=True)
    (acceptance / "outcome-full-lane.json").write_text(json.dumps({"flow": {"development": 2}}))
    manifest = {
        "matches": ids[:2],
        "inputs_sha256": {str(m): {} for m in ids[:2]},
        "source_sha256": "a" * 64,  # Synthetic provenance of the earlier dataset build.
        "rejected_matches": {str(ids[1]): "incomplete input"},
    }
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest))
    frozen = json.loads(adapter.FREEZE.read_text(encoding="utf-8"))
    assert manifest["source_sha256"] != frozen["sources"]["scripts/outcome_domains.py"]
    for domain in ("jungle", "support"):
        (folder / domain).mkdir()
        (folder / domain / "summary.json").write_text(
            json.dumps(
                {
                    "domain": domain,
                    "split": "development",
                    "rows_sha256": frozen["development"][domain]["rows_sha256"],
                    "cohort_sha256": adapter.file_hash(path),
                }
            )
        )

    for mid in ids[:2]:  # Zero opportunities and input rejection both exclude the game.
        with pytest.raises(ValueError, match="previously appeared"):
            adapter._check_development_cohort(mid, frozen)
    adapter._check_development_cohort(ids[2], frozen)
    receipt = folder / "support/summary.json"
    receipt.write_text(json.dumps({**json.loads(receipt.read_text()), "cohort_sha256": "stale"}))
    with pytest.raises(ValueError, match="support development cohort"):
        adapter._check_development_cohort(ids[2], frozen)


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


def test_cache_rejects_inconsistent_normalized_mode(adapter, tmp_path):
    mid = 12
    start = adapter.PATCH_WINDOW[0]
    paths = {}
    channels = (("parsed", "normalized.json"), ("state-v3", "jsonl"), ("extras-v1", "jsonl"))
    for name, suffix in channels:
        folder = tmp_path / name
        folder.mkdir()
        path = folder / f"{mid}.{suffix}.gz"
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            json.dump(dict(match_id=mid, game_mode=23, duration=1000, players=[]), stream)
        paths[path.relative_to(tmp_path).as_posix()] = adapter.file_hash(path)
    meta = dict(
        match_id=mid,
        patch_window="7.41f",
        estimated_start_time=start,
        end_time=start + 1000,
        duration=1000,
        game_mode=22,
        inputs_sha256=paths,
    )
    (tmp_path / "replay-provenance.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="game mode"):
        adapter._input_info(tmp_path, mid)


def test_capture_coverage_discloses_gaps_without_changing_sampling(adapter, tmp_path):
    from scripts.outcome_match_report import render_input_coverage

    mid = 12
    channels = (
        ("state-v3", "gem-state-capture/3", "heroes", [899, 900, 902, 903, 905]),
        ("extras-v1", "gem-extras-capture/1", "creeps", [898, 899]),
    )
    coverage = {}
    for channel, schema, field, seconds in channels:
        folder = tmp_path / channel
        folder.mkdir()
        with gzip.open(folder / f"{mid}.jsonl.gz", "wt", encoding="utf-8") as stream:
            print(json.dumps(dict(match_id=mid, schema=schema, seconds=len(seconds))), file=stream)
            for second in seconds:
                print(json.dumps({"t": second, field: []}), file=stream)
        coverage[channel] = adapter._capture_coverage(tmp_path, mid, channel, schema, field, 904)
    assert coverage["state-v3"]["missing"] == [(901, 901), (904, 904)]
    assert coverage["extras-v1"]["missing"] == [(900, 904)]
    report = render_input_coverage(coverage)
    assert "个别英雄、字段或小兵仍可能缺测" in report
    assert "实有 3/5" in report and "实有 0/5" in report and "整个取样期缺少" in report


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
            "capture_coverage": {},
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
