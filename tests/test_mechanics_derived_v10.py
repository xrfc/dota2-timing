"""Derived v10 and the public readers on the current graph (review of PR #17)."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_current import load_current, read_current
from dota_items.data.mechanics_graph_v2 import hero_relations, usable_edges
from dota_items.data.mechanics_profiles_v4 import item_relations

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "knowledge/mechanics/profiles/derived-v10"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived_v10 as derived  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_derived_v10_replays_every_output_file(tmp_path):
    manifest = _load(DERIVED / "manifest.json")
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((DERIVED / name).read_bytes()).hexdigest() == expected
    derived.run(tmp_path / "derived")
    assert _load(tmp_path / "derived/manifest.json")["output_sha256"] == manifest["output_sha256"]


def test_public_readers_accept_the_current_graph():
    graph = read_current("counter_graph", ROOT)
    assert graph["schema"] == "mechanics-counter-graph/3"
    edges = usable_edges(graph)
    assert edges and all(edge["status"] != "pending" for edge in edges)
    assert len(usable_edges(graph, include_pending=True)) >= len(edges)
    assert all(edge["confirmed"] for edge in usable_edges(graph, confirmed_only=True))
    found = hero_relations(graph, 1, 29)  # Anti-Mage's abilities acting on Tidehunter
    assert {"R12", "R13"} <= {f["rule"] for f in found}
    assert all({"rule", "relation", "status", "sources", "targets"} <= set(f) for f in found)
    with pytest.raises(ValueError):
        usable_edges({"schema": "mechanics-counter-graph/1"})


def test_item_profiles_keep_upgrade_conditions():
    profiles = read_current("item_profiles", ROOT)["profiles"]
    sphere = next(p for p in profiles if p["subject"] == "sphere")
    r13 = next(e for e in sphere["candidate_relations"]["targeting"] if e["rule"] == "R13")
    assert r13["target_conditions"]["tidehunter_gush"] == [{"when": "base", "unless": ["scepter"]}]
    assert "tidehunter_gush" in r13["conditional_targets"]
    page = (DERIVED / "items/sphere.md").read_text(encoding="utf-8")
    assert "有条件的目标：" in page and "有A杖时不成立" in page


def test_item_relations_match_the_graph_for_every_item():
    graph = read_current("counter_graph", ROOT)
    for profile in read_current("item_profiles", ROOT)["profiles"]:
        assert profile["candidate_relations"] == item_relations(profile["subject"], graph)


def test_current_entry_is_derived_v10_or_later():
    path = load_current(ROOT)["entries"]["item_profiles"]["path"]
    assert int(path.split("derived-v", 1)[1].split("/", 1)[0]) >= 10
