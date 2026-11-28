"""Individually valid captures must still refer to one common replay source."""

from copy import deepcopy

import pytest

from scripts.build_patch_evidence import _add_capture


def fixture():
    doc = {
        "schema": "map-objective-evidence/1",
        "match_id": 123,
        "patch": "7.42",
        "game_build": 6993,
        "post_game_tick": 90000,
    }
    receipt = {
        "manifest": {"path": "/bundle/manifest.json", "sha256": "a" * 64},
        "demo_sha256": "b" * 64,
    }
    manifest = {"quality": {"base": {"metadata_duration": 2700}}}
    captures = {"map-objective-evidence/1": {}, "map-vision-evidence/1": {}}
    identities = {}
    _add_capture(captures, identities, doc, receipt, manifest)
    return (
        captures,
        identities,
        {**doc, "schema": "map-vision-evidence/1"},
        deepcopy(receipt),
        manifest,
    )


def test_matching_source_accepts_distinct_channels_and_rejects_duplicate():
    captures, identities, doc, receipt, manifest = fixture()
    _add_capture(captures, identities, doc, receipt, manifest)
    assert all(set(channel) == {123} for channel in captures.values())
    with pytest.raises(ValueError, match="Duplicate"):
        _add_capture(captures, identities, doc, receipt, manifest)


@pytest.mark.parametrize(
    "changed",
    [
        "patch",
        "game_build",
        "post_game_tick",
        "manifest_path",
        "manifest_sha",
        "demo_sha",
        "duration",
    ],
)
def test_independently_valid_but_different_sources_cannot_be_combined(changed):
    captures, identities, doc, receipt, manifest = fixture()
    if changed in {"patch", "game_build", "post_game_tick"}:
        doc[changed] = {"patch": "7.42a", "game_build": 6994, "post_game_tick": 90001}[changed]
    elif changed.startswith("manifest_"):
        receipt["manifest"]["path" if changed == "manifest_path" else "sha256"] = "different"
    elif changed == "demo_sha":
        receipt["demo_sha256"] = "c" * 64
    else:
        manifest["quality"]["base"]["metadata_duration"] = 2701
    before = deepcopy((captures, identities))
    with pytest.raises(ValueError, match="cross-channel replay identity"):
        _add_capture(captures, identities, doc, receipt, manifest)
    assert (captures, identities) == before
