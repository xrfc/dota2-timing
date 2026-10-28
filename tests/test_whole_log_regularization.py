"""Synthetic integration and fail-closed gates; no production training."""

import copy
import warnings

import pytest
from sklearn.exceptions import ConvergenceWarning
from test_whole_log_experiment import experiment as old
from test_whole_log_experiment import snapshot

from dota_items.contracts.tasks import WHOLE_LOG_ITEMS
from dota_items.modeling.artifacts import load_model
from dota_items.modeling.batch import adapt_snapshot
from dota_items.storage import digest, file_hash


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    from dota_items.experiments.whole_log import regularization as m

    s = snapshot()
    cohort, baseline, handoff = [tmp_path / n for n in ("cohort", "baseline", "handoff")]
    for p in (cohort, baseline, handoff):
        p.mkdir()
    m.write(cohort / "snapshot.json", s)
    source_sha = file_hash(cohort / "snapshot.json")
    inputs = {str(cohort / "snapshot.json"): source_sha}
    protocol = {
        "schema_version": "whole-log-fixed-experiment/1",
        "families": ["frequency", "logistic"],
        "candidate_items": list(WHOLE_LOG_ITEMS),
        "task_contract": s["task"]["contract"],
        "split_members": s["splits"],
        "membership_sha256": s["membership_sha256"],
        "input_sha256": inputs,
        "consumer_shapes": {k: list(adapt_snapshot(s, k).x.shape) for k in m.SPLITS},
    }
    m.write(baseline / "protocol.json", protocol)
    report = old.fit_comparison(s, baseline, source_sha256=source_sha, code_revision="synthetic")
    report.update(
        protocol_sha256=file_hash(baseline / "protocol.json"),
        training_executed=True,
        input_sha256_before=inputs,
        input_sha256_after=inputs,
    )
    m.write(baseline / "report.json", report)
    m.write(
        baseline / "complete.json",
        {
            "schema_version": "whole-log-experiment-complete/1",
            "training_executed": True,
            "sha256": {p.name: file_hash(p) for p in baseline.iterdir()},
        },
    )
    protected = {str(p): file_hash(p) for p in baseline.iterdir()}
    protected.update(inputs)
    h = {
        "schema_version": "whole-log-input-handoff/1",
        "training_executed": False,
        "identity": m.input_identity(s),
        "identity_sha256": digest(m.input_identity(s)),
        "protected_sha256": protected,
    }
    m.write(handoff / "handoff.json", h)
    m.write(
        handoff / "complete.json",
        {
            "schema_version": h["schema_version"],
            "training_executed": False,
            "sha256": {"handoff.json": file_hash(handoff / "handoff.json")},
        },
    )

    def synthetic_replay(parent, c, b, *, expected):
        result = m.read_handoff(expected)
        assert c == cohort and b == baseline
        m.verify_baseline(b, c / "snapshot.json")
        return result

    # Replace only real-source replay / approved production shapes, not the downstream gates.
    monkeypatch.setattr(m, "verify_handoff", synthetic_replay)
    from dota_items.experiments.whole_log import baseline as whole_log_experiment

    monkeypatch.setattr(
        whole_log_experiment,
        "implementation_identity",
        lambda: {
            "head": "synthetic",
            "implementation_sha256": {},
        },
    )
    return m, s, ("synthetic-parent", cohort, baseline, handoff), tmp_path / "out"


def test_default_verifies_without_fitting_or_output(prepared, monkeypatch):
    m, _, args, out = prepared
    monkeypatch.setattr(m, "fit_candidates", lambda *a: pytest.fail("fit"))
    result = m.run(*args, out)
    assert result["verified"] and result["training_executed"] is False
    assert not out.exists()


def test_roundtrip_four_candidates_and_read_only_report(prepared, monkeypatch):
    m, _, args, out = prepared
    baseline_before = {p: p.read_bytes() for p in args[2].iterdir()}
    result = m.run(*args, out, execute=True)
    assert set(result["metrics"]) == {"frequency", "logistic", *m.CANDIDATES}
    assert result["selected_model"] is None
    for name, c in m.CANDIDATES.items():
        assert load_model(out / f"{name}.model.json")["parameters"]["C"] == c
        for split in m.SPLITS:
            diag = result["diagnostics"][name][split][WHOLE_LOG_ITEMS[0]]
            assert len(diag["calibration_bins"]) == 10
            assert diag["brier"] == pytest.approx(
                result["metrics"][name][split]["per_item"][WHOLE_LOG_ITEMS[0]]["brier"]
            )
    import dota_items.modeling.training as training

    monkeypatch.setattr(training, "fit_model", lambda *a, **k: pytest.fail("fit during report"))
    recomputed = m.report_run(*args, out, out.parent / "diagnostics")
    assert recomputed["metrics"] == result["metrics"]
    assert all(p.read_bytes() == raw for p, raw in baseline_before.items())


def test_validation_labels_do_not_change_models(prepared):
    m, s, _, out = prepared
    changed = copy.deepcopy(s)
    for row in changed["samples"]:
        if row["split"] == "validation":
            row["labels"] = [1 - v for v in row["labels"]]
    models = []
    for i, value in enumerate((s, changed)):
        folder = out.parent / f"fit-{i}"
        folder.mkdir()
        model, _ = m.fit_candidates(value, folder, "a" * 64, "synthetic", lambda: None)
        models.append(model)
    assert models[0] == models[1]


@pytest.mark.parametrize("kind", ["file", "dir", "symlink"])
def test_refuse_existing_output_before_read(prepared, monkeypatch, kind):
    m, _, args, out = prepared
    if kind == "file":
        out.write_text("keep")
    elif kind == "dir":
        out.mkdir()
    else:
        out.symlink_to(out.parent / "missing")
    monkeypatch.setattr(m, "prepare", lambda *a: pytest.fail("read"))
    with pytest.raises(ValueError, match="overwrite"):
        m.run(*args, out, execute=True)


def test_bad_input_never_fits(prepared, monkeypatch):
    m, _, args, out = prepared
    (args[1] / "snapshot.json").write_text("{}")
    monkeypatch.setattr(m, "fit_candidates", lambda *a: pytest.fail("fit"))
    with pytest.raises(ValueError, match="changed"):
        m.run(*args, out, execute=True)
    assert not out.exists()


@pytest.mark.parametrize("failure", ["convergence", "drift", "protocol", "exception"])
def test_failures_never_publish_complete(prepared, monkeypatch, failure):
    m, _, args, out = prepared
    import dota_items.modeling.training as training

    original = training.fit_model

    def fail(*a, **k):
        assert (out / "protocol.json").is_file()
        if failure == "convergence":
            warnings.warn("synthetic", ConvergenceWarning, stacklevel=2)
        if failure == "exception":
            raise RuntimeError("synthetic failure")
        result = original(*a, **k)
        if failure == "drift":
            (args[1] / "snapshot.json").write_text("{}")
        if failure == "protocol":
            (out / "protocol.json").write_text("{}")
        return result

    monkeypatch.setattr(training, "fit_model", fail)
    with pytest.raises((ValueError, RuntimeError, ConvergenceWarning)):
        m.run(*args, out, execute=True)
    assert not (out / "complete.json").exists()


@pytest.mark.parametrize("target", ["parameters", "predictions", "metrics", "rules", "receipt"])
def test_tampering_rejected_even_with_rehashed_receipt(prepared, target):
    m, _, args, out = prepared
    m.run(*args, out, execute=True)
    names = {
        "parameters": "logistic_c0_1.model.json",
        "predictions": "logistic_c0_1.validation.predictions.json",
        "metrics": "report.json",
        "rules": "protocol.json",
        "receipt": "complete.json",
    }
    path = out / names[target]
    value = m.load(path)
    if target == "parameters":
        value["artifact"]["parameters"]["C"] = 1.0
        value["sha256"] = digest(value["artifact"])
    elif target == "predictions":
        value[0]["probabilities"][WHOLE_LOG_ITEMS[0]] = 0.123
    elif target == "metrics":
        value["metrics"]["logistic_c0_1"]["validation"]["macro"]["brier"]["value"] = 0.0
    elif target == "rules":
        value["rules"]["candidates"]["logistic_c0_1"] = 10.0
    else:
        value["training_executed"] = False
    path.write_bytes(m.json_bytes(value))
    if target != "receipt":
        receipt = m.load(out / "complete.json")
        receipt["sha256"][path.name] = file_hash(path)
        (out / "complete.json").write_bytes(m.json_bytes(receipt))
    with pytest.raises(ValueError):
        m.report_run(*args, out, out.parent / "invalid-report")
    assert not (out.parent / "invalid-report").exists()


def test_unknown_and_single_class_remain_untrained(prepared):
    m, s, _, out = prepared
    for row in s["samples"]:
        row["labels"][0], row["label_mask"][0] = None, False
        row["labels"][1] = 0
    out.mkdir()
    models, _ = m.fit_candidates(s, out, "a" * 64, "synthetic", lambda: None)
    for model in models.values():
        assert model["models"][0]["reason"] == "no_observations"
        assert model["models"][1]["reason"] == "single_class"
        rows = m.rows_for(model, s, "validation")
        result = m.evaluate(rows)
        assert result["per_item"][WHOLE_LOG_ITEMS[0]]["brier"] is None
        assert result["per_item"][WHOLE_LOG_ITEMS[1]]["unscored_known"] > 0


def test_post_report_input_drift_never_completes(prepared, monkeypatch):
    m, _, args, out = prepared
    original = m.write

    def write(path, value):
        original(path, value)
        if path == out / "report.json":
            (args[1] / "snapshot.json").write_text("{}")

    monkeypatch.setattr(m, "write", write)
    with pytest.raises(ValueError, match="changed"):
        m.run(*args, out, execute=True)
    assert not (out / "complete.json").exists()


def test_changed_output_predictions_never_complete(prepared, monkeypatch):
    m, _, args, out = prepared
    original = m.write

    def write(path, value):
        original(path, value)
        if path == out / "report.json":
            (out / "logistic_c0_1.validation.predictions.json").write_text("[]")

    monkeypatch.setattr(m, "write", write)
    with pytest.raises(ValueError, match="published predictions"):
        m.run(*args, out, execute=True)
    assert not (out / "complete.json").exists()
