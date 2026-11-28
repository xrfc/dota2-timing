import copy

import pytest

from dota_items.data import patch_assets


def binding(tmp_path):
    return {
        "schema": "patch-asset-binding/1",
        "exact_patch": "7.42",
        "status": "candidate",
        "map": {
            "root": str(tmp_path / "map"),
            "manifest_sha256": "a" * 64,
            "patch_series": "7.42",
            "client_version": 6989,
        },
        "mechanics": {"root": str(tmp_path / "mechanics"), "manifest_sha256": "b" * 64},
    }


def test_patch_mismatch_precedes_payload_reads(tmp_path, monkeypatch):
    def no_read(*args, **kwargs):
        pytest.fail("Must reject exact patch before payload loading")

    monkeypatch.setattr(patch_assets, "verify_map_snapshot", no_read)
    with pytest.raises(ValueError, match="Exact patch mismatch"):
        patch_assets.verify_patch_assets(
            binding(tmp_path), exact_patch="7.42a", repository_root=tmp_path
        )


@pytest.mark.parametrize("purpose", ["action_review", "training", "unknown"])
def test_candidate_cannot_self_promote(tmp_path, purpose):
    with pytest.raises(ValueError, match="cannot admit"):
        patch_assets.verify_patch_assets(
            binding(tmp_path), exact_patch="7.42", repository_root=tmp_path, purpose=purpose
        )


@pytest.mark.parametrize(
    "field,value",
    [("status", "verified"), ("action_review_allowed", True), ("exact_patch", "latest")],
)
def test_no_declaration_can_bypass_candidate_policy(tmp_path, field, value):
    doc = binding(tmp_path)
    doc[field] = value
    with pytest.raises(ValueError):
        patch_assets.validate_binding(doc)


def test_old_map_cannot_be_mixed_with_new_mechanics(tmp_path):
    doc = binding(tmp_path)
    doc["map"]["patch_series"] = "7.41"
    with pytest.raises(ValueError, match="Map series"):
        patch_assets.validate_binding(doc)


def test_exact_identity_is_passed_to_independent_verifiers(tmp_path, monkeypatch):
    calls = []

    class Map:
        summary = {"map_build": 6989}

        def verify_again(self):
            calls.append("map-recheck")

    class Mechanics:
        def summary(self):
            return {"status": "candidate", "patch": "7.42"}

        def verify_unchanged(self):
            calls.append("mechanics-recheck")

    def load_map(root, **kwargs):
        calls.append(kwargs)
        return Map()

    def load_mechanics(root, **kwargs):
        calls.append(kwargs)
        return Mechanics()

    monkeypatch.setattr(patch_assets, "verify_map_snapshot", load_map)
    monkeypatch.setattr(patch_assets, "verify_mechanics_candidate", load_mechanics)
    obj = patch_assets.verify_patch_assets(
        binding(tmp_path), exact_patch="7.42", repository_root=tmp_path
    )
    assert calls[0]["expected_client_version"] == 6989
    assert calls[1]["expected_patch"] == "7.42"
    mutated = obj.binding
    mutated["map"]["client_version"] = 6993
    assert obj.binding["map"]["client_version"] == 6989
    assert obj.verify_again()["capabilities"]["action_review"] is False
    assert calls[-2:] == ["map-recheck", "mechanics-recheck"]
    doc = copy.deepcopy(obj.summary())
    doc["capabilities"]["training"] = True
    assert obj.summary()["capabilities"]["training"] is False
