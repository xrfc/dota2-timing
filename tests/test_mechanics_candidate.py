"""Candidate identity must not be confused with semantic or patch approval."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from dota_items.data.mechanics_candidate import PRODUCER_PATHS, verify_mechanics_candidate

ROOT = Path(__file__).resolve().parents[1]


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return _hash(path)


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _builder():
    spec = importlib.util.spec_from_file_location(
        "candidate_builder", ROOT / "scripts/build_mechanics_facts_overlay.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def candidate(tmp_path):
    repo, output = tmp_path / "repository", tmp_path / "candidate"
    base = {
        "review_id": "change-1",
        "subject": "ability",
        "mechanism": "slow",
        "decision": "accept",
        "basis": "two_ai",
        "claude": "accept",
        "codex": "accept",
        "quotes": ["Old source"],
    }
    review = {
        **base,
        "codex": "now_wrong",
        "claude": "同意Codex",
        "lane": "change_two_ai",
        "codex_quote": "New source",
    }
    spec = {
        "schema": "mechanics-facts-build/1",
        "version": 27,
        "base": "inputs/base.json",
        "inputs": "inputs/overlay.json",
        "vocabulary": "inputs/vocabulary.json",
        "rules": "inputs/rules.json",
        "enums": "inputs/enums.json",
        "registry": "inputs/registry.json",
        "decision_reviews": "inputs/reviews.json",
        "game_npc": "npc",
        "items_txt": "items.txt",
    }
    overlay = {
        "schema": "mechanics-overlay-inputs/1",
        "version": 27,
        "note": "Partial candidate, remaining rulings pending.",
        "operations": [
            {
                "op": "decision_change",
                "review_id": "change-1",
                "subject": "ability",
                "mechanism": "slow",
                "from": "accept",
                "to": "reject",
                "basis": "two_ai",
            }
        ],
    }
    input_docs = {
        "inputs/base.json": {"schema": "mechanics-facts/26", "rows": [base]},
        "inputs/overlay.json": overlay,
        "inputs/vocabulary.json": {},
        "inputs/rules.json": {},
        "inputs/enums.json": {},
        "inputs/registry.json": {"target_patch": "7.42", "patch_verified": False},
        "inputs/reviews.json": {"schema": "mechanics-recheck-742/1", "rows": [review]},
        "npc/npc_abilities.txt": {},
        "npc/heroes/one.txt": {},
        "items.txt": {},
    }
    input_hashes = {name: _write(repo / name, value) for name, value in input_docs.items()}
    producer_hashes = {name: _write(repo / name, {}) for name in PRODUCER_PATHS}
    row = {
        **base,
        "decision": "reject",
        "claude": "reject",
        "codex": "reject",
        "decision_review": {"source": spec["decision_reviews"], **review},
        "quotes": [review["codex_quote"]],
        "prior_review": {"facts_schema": "mechanics-facts/26", **base},
    }
    facts = {
        "schema": "mechanics-facts/27",
        "extractor_version": "mechanics-reviewed/27",
        "patch_verified": False,
        "vocabulary": spec["vocabulary"],
        "rows": [row],
        "retired_rows": [],
        "counts": {"rows": 1, "decisions": {"reject": 1}, "retired_rows": 0},
    }
    output_docs = {
        "facts-v27.json": facts,
        "rules-expanded.json": {"schema": "mechanics-rules/1", "source": spec["rules"]},
        "rules-evaluation.json": {"schema": "mechanics-rules-evaluation/3"},
    }
    manifest = {
        "schema": "mechanics-extraction-receipt/1",
        "extractor_version": "mechanics-reviewed/27",
        "patch_verified": False,
        "build_spec": spec,
        "input_sha256": input_hashes,
        "implementation_sha256": producer_hashes,
        "output_sha256": {
            name: _write(output / name, value) for name, value in output_docs.items()
        },
    }
    _write(output / "manifest.json", manifest)
    return repo, output, manifest


def _verify(candidate, patch="7.42"):
    repo, output, _ = candidate
    return verify_mechanics_candidate(
        output,
        expected_manifest_sha256=_hash(output / "manifest.json"),
        expected_patch=patch,
        repository_root=repo,
    )


def _update_manifest(candidate):
    _, output, manifest = candidate
    _write(output / "manifest.json", manifest)


def test_candidate_keeps_unknown_status_and_returns_detached_summary(candidate):
    result = _verify(candidate)
    summary = result.summary()
    assert summary["patch"] == "7.42"
    assert summary["pending"]["status"] == "unresolved"
    assert summary["formal_use_allowed"] is summary["training_allowed"] is False
    assert summary["patch_verified"] is False
    summary["evidence"]["outputs"].clear()
    assert result.verify_unchanged()["inventory_counts"]["outputs"] == 3


@pytest.mark.parametrize("patch", ["7.41f", "7.42a", "latest", "7.42 ", None])
def test_patch_must_match_exactly(candidate, patch):
    with pytest.raises(ValueError, match="patch"):
        _verify(candidate, patch)


@pytest.mark.parametrize("group", ["input_sha256", "implementation_sha256", "output_sha256"])
def test_missing_inventory_entry_rejected_even_with_new_manifest_hash(candidate, group):
    candidate[2][group].pop(next(iter(candidate[2][group])))
    _update_manifest(candidate)
    with pytest.raises(ValueError, match="inventory"):
        _verify(candidate)


@pytest.mark.parametrize("group", ["input_sha256", "implementation_sha256", "output_sha256"])
def test_current_dependency_changes_invalidate_candidate(candidate, group):
    repo, output, manifest = candidate
    name = next(iter(manifest[group]))
    path = (output if group == "output_sha256" else repo) / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        _verify(candidate)


@pytest.mark.parametrize(
    "name",
    [
        "../outside.json",
        "/tmp/outside.json",
        "inputs//registry.json",
        "inputs/./registry.json",
        "inputs\\registry.json",
    ],
)
def test_unsafe_spec_path_rejected_before_read(candidate, name):
    candidate[2]["build_spec"]["registry"] = name
    _update_manifest(candidate)
    with pytest.raises(ValueError, match="relative file path"):
        _verify(candidate)


def test_dependency_symlink_rejected(candidate):
    repo, _, _ = candidate
    path = repo / "inputs/registry.json"
    target = repo / "copy.json"
    target.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(target)
    with pytest.raises(ValueError, match="Symlink"):
        _verify(candidate)


def test_publication_recheck_detects_manifest_replacement(candidate):
    result = _verify(candidate)
    candidate[2]["patch_verified"] = True
    _update_manifest(candidate)
    with pytest.raises(ValueError, match="hash mismatch"):
        result.verify_unchanged()


def test_source_file_added_after_verification_is_not_ignored(candidate):
    result = _verify(candidate)
    _write(candidate[0] / "npc/heroes/new.txt", {})
    with pytest.raises(ValueError, match="input inventory"):
        result.verify_unchanged()


def test_manifest_cannot_promote_candidate(candidate):
    candidate[2]["patch_verified"] = True
    _update_manifest(candidate)
    with pytest.raises(ValueError, match="unverified candidates"):
        _verify(candidate)


@pytest.mark.parametrize("field", ["decision_review", "prior_review", "quotes"])
def test_output_requires_linked_review_and_old_evidence(candidate, field):
    _, output, manifest = candidate
    path = output / "facts-v27.json"
    facts = json.loads(path.read_text())
    facts["rows"][0].pop(field)
    manifest["output_sha256"][path.name] = _write(path, facts)
    _update_manifest(candidate)
    with pytest.raises(ValueError, match="evidence|decision_review"):
        _verify(candidate)


def test_missing_review_dependency_rejected(candidate):
    candidate[2]["build_spec"].pop("decision_reviews")
    _update_manifest(candidate)
    with pytest.raises(ValueError, match="build_spec"):
        _verify(candidate)


@pytest.mark.parametrize("digest", ["0" * 63, "G" * 64, "A" * 64, 123, None])
def test_invalid_expected_hash_rejected(candidate, digest):
    repo, output, _ = candidate
    with pytest.raises(ValueError, match="SHA-256"):
        verify_mechanics_candidate(
            output, expected_manifest_sha256=digest, expected_patch="7.42", repository_root=repo
        )


def test_duplicate_json_key_is_rejected(candidate):
    output = candidate[1]
    text = (output / "manifest.json").read_text()
    (output / "manifest.json").write_text(text[:-1] + ', "patch_verified": false}')
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        _verify(candidate)


def test_real_current_builder_receipt_verifies_without_promoting_current(tmp_path):
    builder = _builder()
    assert tuple(builder.IMPLEMENTATION) == PRODUCER_PATHS
    current = ROOT / "knowledge/mechanics/current.json"
    before = _hash(current)
    output = tmp_path / "current-candidate"
    builder.run("knowledge/mechanics/reviews/v27-build-draft-001.json", output)
    result = verify_mechanics_candidate(
        output,
        expected_manifest_sha256=_hash(output / "manifest.json"),
        expected_patch="7.42",
        repository_root=ROOT,
    )
    summary = result.verify_unchanged()
    assert summary["inventory_counts"]["inputs"] == 139
    assert summary["counts"]["rows"] == 3292
    assert summary["counts"]["decisions"] == {"accept": 2582, "reject": 710}
    assert summary["pending"]["status"] == "unresolved"
    assert _hash(current) == before
