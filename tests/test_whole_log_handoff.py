"""Handoff guards use fabricated inputs; real source replay is exercised separately."""

import copy

import pytest
from test_whole_log_experiment import snapshot

from dota_items.storage import digest, file_hash, json_bytes


def module(monkeypatch):
    from dota_items.experiments.whole_log import baseline
    from dota_items.experiments.whole_log import handoff as result

    # Any accidental invocation of the production fit function must fail.
    monkeypatch.setattr(
        baseline,
        "fit_model",
        lambda *a, **k: pytest.fail("unexpected fit"),
    )
    return result


def fabricated(tmp_path, m, monkeypatch):
    source = tmp_path / "source.json"
    source.write_bytes(json_bytes(snapshot()))
    identity = m.input_identity(snapshot())
    report = {
        "schema_version": m.SCHEMA,
        "training_executed": False,
        "identity": identity,
        "identity_sha256": digest(identity),
        "protected_sha256": {str(source): file_hash(source)},
    }
    monkeypatch.setattr(m, "verify", lambda *a, **k: copy.deepcopy(report))
    return source, report


def test_receipt_and_drift(tmp_path, monkeypatch):
    m = module(monkeypatch)
    source, report = fabricated(tmp_path, m, monkeypatch)
    output = tmp_path / "out"
    m.run("parent", "cohort", "baseline", output)
    assert m.read_handoff(output) == report
    source.write_text("changed")
    with pytest.raises(ValueError, match="input changed"):
        m.read_handoff(output)


@pytest.mark.parametrize("kind", ["directory", "file", "symlink"])
def test_no_overwrite_before_read(tmp_path, monkeypatch, kind):
    m = module(monkeypatch)
    output = tmp_path / "out"
    if kind == "directory":
        output.mkdir()
    elif kind == "file":
        output.write_text("keep")
    else:
        output.symlink_to(tmp_path / "missing")
    monkeypatch.setattr(m, "verify", lambda *a, **k: pytest.fail("read"))
    with pytest.raises(ValueError, match="overwrite"):
        m.run("parent", "cohort", "baseline", output)


def test_failure_has_no_output(tmp_path, monkeypatch):
    m = module(monkeypatch)

    def reject(*a, **k):
        raise ValueError("bad source")

    monkeypatch.setattr(m, "verify", reject)
    with pytest.raises(ValueError, match="bad source"):
        m.run("parent", "cohort", "baseline", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_post_write_drift_never_completes(tmp_path, monkeypatch):
    m = module(monkeypatch)
    source, _ = fabricated(tmp_path, m, monkeypatch)
    original = m.check_unchanged
    calls = []

    def drift(files):
        calls.append(1)
        if len(calls) == 2:
            source.write_text("drift")
        original(files)

    monkeypatch.setattr(m, "check_unchanged", drift)
    with pytest.raises(ValueError, match="input changed"):
        m.run("p", "c", "b", tmp_path / "out")
    assert not (tmp_path / "out" / "complete.json").exists()


@pytest.mark.parametrize("field", ["labels", "mask", "members", "vocabulary", "order"])
def test_identity_change_or_invalid_input_rejected(monkeypatch, field):
    m = module(monkeypatch)
    original = snapshot()
    before = m.input_identity(original)
    changed = copy.deepcopy(original)
    row = changed["samples"][0]
    if field == "labels":
        row["labels"][0] = 1 - row["labels"][0]
    elif field == "mask":
        row["labels"][0], row["label_mask"][0] = None, False
    elif field == "members":
        changed["splits"]["train"][0] = 99999
    elif field == "vocabulary":
        changed["preprocessing"]["vocabulary"].reverse()
    else:
        changed["samples"].reverse()
    try:
        after = m.input_identity(changed)
    except ValueError:
        return
    assert before != after


def test_missing_or_tampered_receipt(tmp_path, monkeypatch):
    m = module(monkeypatch)
    fabricated(tmp_path, m, monkeypatch)
    output = tmp_path / "out"
    m.run("p", "c", "b", output)
    (output / "handoff.json").write_text("{}")
    with pytest.raises(ValueError, match="receipt"):
        m.read_handoff(output)


def test_source_failure_prevents_baseline_check(monkeypatch):
    m = module(monkeypatch)

    def reject(*args):
        raise ValueError("source replay")

    monkeypatch.setattr(m, "verify_inputs", reject)
    monkeypatch.setattr(m, "verify_baseline", lambda *a: pytest.fail("baseline"))
    with pytest.raises(ValueError, match="source replay"):
        m.verify("p", "c", "b")


@pytest.mark.parametrize("change", ["none", "rows", "baseline_parameters"])
def test_expected_identity_and_baseline_parameters(tmp_path, monkeypatch, change):
    m = module(monkeypatch)
    data = snapshot()
    path = tmp_path / "source"
    path.write_text("fixed")
    protected = {str(path): file_hash(path)}
    identity = m.input_identity(data)
    identity["consumer_shapes"] = {
        "train": {"X": [1592, 256], "y": [1592, 11], "mask": [1592, 11]},
        "validation": {"X": [398, 256], "y": [398, 11], "mask": [398, 11]},
    }
    previous = {"identity": copy.deepcopy(identity), "protected_sha256": protected}
    monkeypatch.setattr(m, "read_handoff", lambda directory: previous)
    monkeypatch.setattr(m, "verify_inputs", lambda *a: (data, [], dict(protected)))
    monkeypatch.setattr(m, "input_identity", lambda value: identity)
    monkeypatch.setattr(m, "verify_baseline", lambda *a: ({}, {}))

    def model(path):
        logistic = path.name.startswith("logistic")
        return {
            "parameters": {
                "C": (0.1 if change == "baseline_parameters" else 1.0) if logistic else None,
                "solver": "liblinear" if logistic else None,
                "max_iter": 2000,
                "random_state": 0,
                "class_weight": None,
            }
        }

    monkeypatch.setattr(m, "load_model", model)
    if change == "rows":
        identity["rows_sha256"] = "b" * 64
    if change == "none":
        result = m.verify("p", "c", "b", expected="old")
        assert result["training_executed"] is False
        assert result["identity"] == previous["identity"]
    else:
        with pytest.raises(ValueError, match="identity changed|baseline parameters"):
            m.verify("p", "c", "b", expected="old")
