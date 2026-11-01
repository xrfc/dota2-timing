"""MK-T3 v3: upgrade text whose Valve has-upgrade flag is false is excluded."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from dota_items.data import mechanics_facts_v3 as mf3

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v3"
sys.path.insert(0, str(ROOT / "scripts"))

import build_stale_upgrade_text  # noqa: E402


@pytest.fixture(scope="module")
def sources():
    return {
        name: json.loads((ROOT / name).read_text())
        if name.endswith(".json")
        else {"text": (ROOT / name).read_text()}
        for name in mf3.INPUTS
    }


@pytest.fixture(scope="module")
def facts(sources):
    return mf3.build_facts(sources)


def test_stale_list_matches_raw_valve_flags(sources):
    assert build_stale_upgrade_text.build() == sources[mf3.STALE]


def test_flags_decide_exclusion():
    hero = {
        "id": 1,
        "name": "npc_dota_hero_x",
        "abilities": [
            {"name": "old", "scepter_loc": "t", "ability_has_scepter": False},
            {"name": "current", "scepter_loc": "t", "ability_has_scepter": True},
            {"name": "granted", "shard_loc": "t", "ability_is_granted_by_shard": True},
            {"name": "empty", "shard_loc": "", "ability_has_shard": False},
        ],
    }
    assert [(r["ability"], r["upgrade"]) for r in mf3.stale_upgrades([hero])] == [
        ("old", "scepter")
    ]


def test_user_flagged_texts_are_excluded(facts):
    excluded = {(f["subject"], f["condition"]["context"]) for f in facts["excluded_facts"]}
    assert ("obsidian_destroyer_arcane_orb", "scepter_upgrade") in excluded
    assert ("muerta_pierce_the_veil", "shard_upgrade") in excluded
    kept = {(f["subject"], f["condition"]["context"]) for f in facts["facts"]}
    assert not excluded & kept
    # Granted-by-shard abilities keep their text; base descriptions are never excluded.
    assert all("/upgrade_text/" in f["pointer"]["path"] for f in facts["excluded_facts"])
    assert ("muerta_pierce_the_veil", "base") in kept


def test_v3_replays_and_rejects_tampering(sources, facts):
    assert mf3.load_facts(facts, sources)
    changed = json.loads(json.dumps(facts))
    changed["excluded_facts"].pop()
    with pytest.raises(ValueError):
        mf3.load_facts(changed, sources)
    bad = {**sources[mf3.STALE], "entries": [{"ability": "missing", "upgrade": "shard"}]}
    with pytest.raises(ValueError):
        mf3.build_facts({**sources, mf3.STALE: bad})


def test_checked_in_v3_package(sources):
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
    mf3.load_facts(json.loads((PACKAGE / "facts-v3.json").read_text()), sources)
    delta = json.loads((PACKAGE / "delta-vs-v2.json").read_text())
    assert delta["removed_review_groups"] == 19
