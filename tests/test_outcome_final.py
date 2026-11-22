import importlib
from pathlib import Path

import pytest


@pytest.fixture
def final(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("outcome_final")


def test_one_shot_claim_requires_exact_freeze_and_prevents_second_scoring(final, tmp_path):
    freeze = tmp_path / "freeze.json"
    freeze.write_text("{}")
    marker = tmp_path / "evaluation-started.json"
    digest = final.file_hash(freeze)
    with pytest.raises(ValueError, match="freeze"):
        final.claim_evaluation(marker, freeze, "invalid")
    assert not marker.exists()
    final.claim_evaluation(marker, freeze, digest)
    with pytest.raises(FileExistsError):
        final.claim_evaluation(marker, freeze, digest)


def test_input_integrity_checked_before_scoring(final, tmp_path):
    path = tmp_path / "model"
    path.write_bytes(b"frozen")
    manifest = {"model": final.file_hash(path)}
    final.verify(tmp_path, manifest)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="model"):
        final.verify(tmp_path, manifest)


def test_holdout_rows_reject_development_or_duplicate_cases(final):
    held = next(m for m in range(100) if final.is_holdout(m))
    dev = next(m for m in range(100) if not final.is_holdout(m))
    r = {"match": held, "hero": "h", "t": 900, "fold": final.fold_for(held)}
    final.verify_held_rows([r], {held})
    for values in ([r, r], [{**r, "match": dev}]):
        with pytest.raises(ValueError):
            final.verify_held_rows(values, {held})


def test_end_to_end_scoring_reads_frozen_models_and_claims_once(final, tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    import joblib
    from outcome_values import fit_value

    from scripts.lane_study_baselines import ActionMeans

    monkeypatch.setattr(final, "WORK", tmp_path)
    frozen_path = tmp_path / "freeze.json"
    monkeypatch.setattr(final, "FREEZE", frozen_path)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    mid = next(m for m in range(100) if final.is_holdout(m))
    models, files, dev = {}, {}, {}
    for domain, (arms, targets) in final.DOMAINS.items():
        train = [
            {
                "match": -(i + 1),
                "hero": "h",
                "t": 900,
                "action": arms[i % 2],
                "static": [1],
                "sequence": [[1]] * 3,
                **dict.fromkeys(targets, 0),
            }
            for i in range(40)
        ]
        fitted = fit_value(train, arms, targets)
        name = domain + ".joblib"
        joblib.dump(fitted, tmp_path / name)
        models[name] = final.file_hash(tmp_path / name)
        row = {
            **train[0],
            "hits": 3,
            "match": mid,
            "fold": final.fold_for(mid),
            "behavior_eligible": True,
            "outcome_eligible": True,
        }
        path = prepared / (domain + ".jsonl")
        path.write_text(json.dumps(row) + "\n")
        files[path.name] = final.file_hash(path)
        dev[domain] = {"factual": {key: {"all": {"value": 0.0}} for key in targets}}
    name = "wave-reference.joblib"
    joblib.dump({"action_mean": ActionMeans({"farm": (0, 0)})}, tmp_path / name)
    models[name] = final.file_hash(tmp_path / name)
    frozen_path.write_text(
        json.dumps(
            {
                "sources": {},
                "models": models,
                "map": {},
                "compat": {},
                "versions": final.versions(),
                "development": dev,
            }
        )
    )
    digest = final.file_hash(frozen_path)
    (prepared / "manifest.json").write_text(
        json.dumps(
            {
                "freeze_sha256": digest,
                "files": files,
                "matches": [mid],
                "wave_candidates": [mid],
                "excluded": {},
            }
        )
    )
    args = SimpleNamespace(freeze_sha256=digest, map_dir=tmp_path, compat=tmp_path)
    final.evaluate(args)
    result = json.loads((tmp_path / "results/summary.json").read_text())
    assert result["domains"]["support"]["factual_gap"]["hits"] == 3
    assert result["wave_reference"]["action_mean"]["hits_mae"] == 3
    assert result["domains"]["wave"]["balanced_strata_rankings"] == {"tie": 1}
    with pytest.raises(FileExistsError):
        final.evaluate(args)


def test_enumeration_checks_partition_before_reading_a_receipt(final, tmp_path):
    import json

    held = next(i for i in range(100) if final.is_holdout(i))
    dev = next(i for i in range(100) if not final.is_holdout(i))
    for folder in ("receipts", "meta", "parsed", "state-v3"):
        (tmp_path / folder).mkdir()
    for selected, other, holdout in ((dev, held, False), (held, dev, True)):
        (tmp_path / "receipts" / f"{other}.json").write_text("unreadable opposite partition")
        (tmp_path / "receipts" / f"{selected}.json").write_text(
            json.dumps({"match_id": selected, "status": "parsed", "avg_rank_tier": 65})
        )
        (tmp_path / "meta" / f"{selected}.json").write_text(
            json.dumps(
                {
                    "match_id": selected,
                    "patch": 60,
                    "start_time": 1789455600,
                    "lobby_type": 7,
                    "game_mode": 22,
                    "duration": 900,
                }
            )
        )
        (tmp_path / "parsed" / f"{selected}.normalized.json.gz").touch()
        (tmp_path / "state-v3" / f"{selected}.jsonl.gz").touch()
        assert final.candidates(tmp_path, min_rank=60, holdout=holdout) == ([], [selected])
        assert final.candidates(tmp_path, holdout=holdout) == ([], [])
