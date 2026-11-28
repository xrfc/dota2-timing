"""Bundle selection must not silently enter the legacy cache or unsupported map."""

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
MID = 9081264566


@pytest.fixture
def review(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("lane_decision_review")


def fail(*args, **kwargs):
    raise AssertionError("unexpected source access")


@pytest.mark.parametrize("patch", ["7.42", "7.41e", "7.41", "7.42a"])
def test_exact_patch_gate_precedes_producer_and_payload_access(review, monkeypatch, patch):
    monkeypatch.setattr(review, "load_reference", lambda path: {"match_id": MID, "patch": patch})
    monkeypatch.setattr(review, "current_producer", fail)
    monkeypatch.setattr(review, "open_bundle_input", fail)
    with pytest.raises(ValueError, match="exact patch 7.41f"):
        review.open_review_sources([MID], [Path("reference")], Path("compat"))


def test_holdout_gate_precedes_even_reference_read(review, monkeypatch):
    monkeypatch.setattr(review, "is_holdout", lambda mid: True)
    monkeypatch.setattr(review, "load_reference", fail)
    with pytest.raises(ValueError, match="holdout"):
        review.open_review_sources([MID], [Path("reference")], Path("compat"))


@pytest.mark.parametrize("ids", [[], [MID, MID], [MID + 1]])
def test_no_missing_duplicate_or_implicit_fallback_reference(review, monkeypatch, ids):
    monkeypatch.setattr(review, "load_reference", lambda mid: {"match_id": mid, "patch": "7.41f"})
    monkeypatch.setattr(review, "current_producer", fail)
    with pytest.raises(ValueError, match="exactly one"):
        review.open_review_sources([MID], ids, Path("compat"))


def test_complete_selection_preflight_before_first_payload(review, monkeypatch):
    monkeypatch.setattr(review, "is_holdout", lambda mid: False)
    monkeypatch.setattr(
        review,
        "load_reference",
        lambda mid: {"match_id": mid, "patch": "7.41f" if mid == MID else "7.42"},
    )
    monkeypatch.setattr(review, "open_bundle_input", fail)
    monkeypatch.setattr(review, "current_producer", fail)
    with pytest.raises(ValueError, match="7.41f"):
        review.open_review_sources([MID, MID + 1], [MID, MID + 1], Path("compat"))


def test_selection_injects_expected_producer_and_policy(review, monkeypatch):
    ref = {"match_id": MID, "patch": "7.41f"}
    producer = {"schema": "test/1"}
    monkeypatch.setattr(review, "load_reference", lambda path: ref)
    monkeypatch.setattr(review, "current_producer", lambda compat: producer)
    calls = []

    def opened(reference, **kwargs):
        calls.append((reference, kwargs))
        return "source"

    monkeypatch.setattr(review, "open_bundle_input", opened)
    assert review.open_review_sources([MID], ["ref"], "compat") == ({MID: "source"}, producer)
    assert calls[0][0] == ref
    assert calls[0][1]["expected_producer"] == producer
    assert calls[0][1]["allowed_patches"] == ("7.41f",)
    assert calls[0][1]["match_allowed"](MID) is True


def test_build_match_rejects_other_patch_before_normalized_read(review):
    source = SimpleNamespace(
        metadata=lambda: {"match_id": MID, "patch": 60},
        receipt=lambda: {"reference": {"match_id": MID, "patch": "7.42"}},
        normalized=fail,
    )
    with pytest.raises(ValueError, match="7.41f"):
        list(review.build_match(Path("absent"), MID, {}, source=source))


def test_projected_end_truncates_six_and_twenty_second_observation_windows(review):
    from test_replay_review_input import SOURCE, frame, parsed

    match = review.project_match(parsed(903), (frame(t) for t in range(904)), source_key=SOURCE)
    _, action, outcome = next(
        review.make_jungle_cases(
            match,
            MID,
            "hero0",
            [900],
            {},
            {900: {"unit_state_raw": 0}},
            {},
            [],
            [{"id": 1, "x": 22384, "y": 10384}],
        )
    )
    assert "不完整" in action["detail"]
    assert outcome["complete"] is False
    _, farm = review.farm_comparison(match, "hero0", 900, [], [], [])
    assert farm["next_6s"]["observed_seconds"] == 3
    assert farm["next_20s"]["observed_seconds"] == 3
    assert not review.support_followup({}, "hero1", 900, match["last"])["complete"]


@pytest.fixture
def publication(review, monkeypatch, tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index.html").write_text("review")
    background = tmp_path / "map.jpg"
    background.write_bytes(b"test map")
    out = tmp_path / "result"
    producer = {"schema": "test/1"}
    source = SimpleNamespace(verify=lambda: {"manifest_sha256": "a" * 64})
    monkeypatch.setattr(review, "ASSETS", assets)
    monkeypatch.setattr(review, "MAP", background)
    monkeypatch.setattr(review, "open_review_sources", lambda *args: ({MID: source}, producer))
    monkeypatch.setattr(review, "consumer_identity", lambda: {"sources": {"review": "hash"}})
    monkeypatch.setattr(review, "current_producer", lambda compat: producer)
    monkeypatch.setattr(review, "read_json", lambda path: {"means": {}})
    monkeypatch.setattr(review, "names", lambda: {})
    monkeypatch.setattr(review, "match_inputs", fail)
    calls = []

    def build(root, mid, means, mode, *, source):
        calls.append(source)
        yield {"match": mid, "hero": "hero", "t": 900}, {"action": "farm"}, {"result": "known"}

    monkeypatch.setattr(review, "build_match", build)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lane_decision_review.py",
            "--bundle-reference",
            "ref.json",
            "--matches",
            str(MID),
            "--out",
            str(out),
        ],
    )
    return SimpleNamespace(out=out, source=source, calls=calls, producer=producer)


def test_success_publishes_receipt_with_explicit_source(review, publication):
    review.main()
    receipt = json.loads((publication.out / "input-receipt.json").read_text())
    assert receipt["inputs"] == [{"manifest_sha256": "a" * 64}]
    assert receipt["training_allowed"] is False
    assert publication.calls == [publication.source]
    assert (publication.out / "cases.json").exists()
    assert receipt["outputs"]["cases.json"] == review.file_hash(publication.out / "cases.json")
    assert "input-receipt.json" not in receipt["outputs"]


def test_consumer_identity_includes_indirect_control_and_contract_code(review, monkeypatch):
    monkeypatch.setattr(review, "file_hash", lambda path: "hash")
    identity = review.consumer_identity()
    assert "src/dota_items/data/unit_state.py" in identity["sources"]
    assert "src/dota_items/contracts/death_risk.py" in identity["sources"]


@pytest.mark.parametrize("change", ["source", "producer", "consumer"])
def test_drift_prevents_report_publication(review, publication, monkeypatch, change):
    if change == "source":

        def changed():
            raise ValueError("Pinned manifest changed")

        publication.source.verify = changed
    elif change == "producer":
        monkeypatch.setattr(review, "current_producer", lambda compat: {"schema": "changed"})
    else:
        values = iter([{"sources": "old"}, {"sources": "new"}])
        monkeypatch.setattr(review, "consumer_identity", lambda: next(values))
    with pytest.raises(ValueError, match="changed"):
        review.main()
    assert not publication.out.exists()


def test_legacy_root_and_bundle_mode_are_mutually_exclusive(review, monkeypatch, tmp_path):
    monkeypatch.setattr(review, "open_review_sources", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lane_decision_review.py",
            "--root",
            "old",
            "--bundle-reference",
            "ref",
            "--matches",
            str(MID),
            "--out",
            str(tmp_path / "out"),
        ],
    )
    with pytest.raises(SystemExit):
        review.main()
