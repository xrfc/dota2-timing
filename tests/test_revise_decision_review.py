"""Feedback revision is bounded to text and never mutates sealed evidence/outcomes."""

import importlib.util
import json
from pathlib import Path

import pytest

from dota_items.storage import file_hash


def setup(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "revise", root / "scripts/revise_decision_review.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    repo = tmp_path / "repo"
    base = repo / "reports/base"
    base.mkdir(parents=True)
    package = {
        "cards": [
            {
                "case": {"id": "one"},
                "enhancement": {},
                "evidence": {
                    "decision_input": {
                        "time": 1080,
                        "tick": 41048,
                        "positions": [
                            {
                                "hero_id": 114,
                                "visibility": "hidden",
                                "last_seen": {
                                    "source_tick": 40388,
                                    "time": 1058,
                                    "age_game_seconds": 22,
                                },
                            }
                        ],
                    }
                },
            }
        ]
    }
    (base / "cases.json").write_text(json.dumps(package))
    (base / "one-after.json").write_bytes(b'{"future":123}\n')
    (base / "annotation-draft.json").write_bytes(b'{"training_allowed":false}\n')
    verification = {
        "source_files": {},
        "outputs": {p.name: file_hash(p) for p in base.glob("*.json")},
    }
    (base / "verification.json").write_text(json.dumps(verification))
    for name in [
        "scripts/revise_decision_review.py",
        "scripts/decision_review.py",
        "scripts/decision_review_assets/app.js",
        "scripts/decision_review_assets/index.html",
        "scripts/decision_review_assets/style.css",
    ]:
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fixture")
    update = {
        "case_id": "one",
        "case_fields": {"reason": "最后可见不等于当前位置"},
        "last_seen_claim": {
            "hero_id": 114,
            "source_tick": 40388,
            "time": 1058,
            "age_game_seconds": 22,
        },
        "interpretation": "可能已转移，位置未知",
        "questions": [
            {"axis": a, "prompt": a + " concrete question"}
            for a in ("attention", "action", "stop", "missing")
        ],
    }
    revision = {
        "schema": "decision-review-revision/1",
        "training_allowed": False,
        "source": "user",
        "base_package": "reports/base",
        "base_cases_sha256": file_hash(base / "cases.json"),
        "user_feedback_verbatim": "消失22秒，可能跳树或TP到场",
        "case_updates": [update],
    }
    return module, repo, base, package, revision


def run(module, repo, revision):
    path = repo / "revision.json"
    path.write_text(json.dumps(revision))
    return module.revise(repo / "new", path, repo)


def test_revision_preserves_original_inputs_outcomes_and_draft(tmp_path):
    module, repo, base, original, revision = setup(tmp_path)
    hashes = {p.name: file_hash(p) for p in base.iterdir()}
    run(module, repo, revision)
    revised = json.loads((repo / "new/cases.json").read_text())
    c = revised["cards"][0]
    assert c["evidence"] == original["cards"][0]["evidence"]
    assert c["case"]["reason"] == "最后可见不等于当前位置"
    assert not c["enhancement"]["review_update"]["actual_route_or_current_location_verified"]
    assert c["enhancement"]["review_update"]["training_label"] is None
    for name in ["one-after.json", "annotation-draft.json"]:
        assert (repo / "new" / name).read_bytes() == (base / name).read_bytes()
    assert {p.name: file_hash(p) for p in base.iterdir()} == hashes


@pytest.mark.parametrize("change", ["age", "forbidden_field"])
def test_false_claim_or_unbounded_update_rejected(tmp_path, change):
    module, repo, _, _, revision = setup(tmp_path)
    if change == "age":
        revision["case_updates"][0]["last_seen_claim"]["age_game_seconds"] = 23
    else:
        revision["case_updates"][0]["case_fields"]["tick"] = 41078
    with pytest.raises(ValueError):
        run(module, repo, revision)
    assert not (repo / "new").exists()


def test_changed_base_bytes_rejected(tmp_path):
    module, repo, base, _, revision = setup(tmp_path)
    (base / "one-after.json").write_text('{"future":999}')
    with pytest.raises(ValueError, match="drift"):
        run(module, repo, revision)
    assert not (repo / "new").exists()


def test_existing_output_rejected_before_reading_revision(tmp_path):
    module, repo, _, _, _ = setup(tmp_path)
    with pytest.raises(ValueError, match="exists"):
        module.revise(repo, repo / "absent", repo)
