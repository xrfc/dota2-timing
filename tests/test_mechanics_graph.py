"""MK-T5 derived layer: evidence chains, confirmation status and the v1 comparison."""

import json
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_graph import (
    build_graph,
    build_traits,
    compare_with_v1,
    edges_between,
    item_to_hero,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/profiles/derived-v1"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_derived as builder  # noqa: E402
import check_mechanics_recall as recall  # noqa: E402


def _row(subject, mechanism, basis="two_ai", decision="accept"):
    return {
        "subject": subject,
        "mechanism": mechanism,
        "decision": decision,
        "basis": basis,
        "condition": {"context": "base"},
        "quotes": ["q"],
    }


DOC = {
    "rows": [
        _row("sword", "applies_break", "user:U1"),
        _row("a1", "break_sensitive", "two_ai"),
        _row("a2", "break_sensitive", "user:U2"),
        _row("a2", "stun", "two_ai", "reject"),
    ],
    "skill_notes": [],
    "field_observations": [],
}
NODES = {
    "sword": {"kind": "item", "name_zh": "剑"},
    "a1": {"kind": "ability", "hero_id": 1, "hero_zh": "甲", "name_zh": "一"},
    "a2": {"kind": "ability", "hero_id": 2, "hero_zh": "乙", "name_zh": "二"},
}
RULE = {
    "id": "R",
    "zh": "破坏",
    "relation": "disables",
    "decision": "U1",
    "source_mechanisms": ["applies_break"],
    "target_mechanisms": ["break_sensitive"],
}
EVALUATION = {"rules": [{"id": "R", "sources": ["sword"], "targets": ["a1", "a2"]}]}


def test_edge_is_confirmed_only_when_both_ends_are():
    graph = build_graph([RULE], EVALUATION, DOC, NODES)
    edges = {edge["hero_id"]: edge for edge in graph["item_to_hero"]}
    assert edges[1]["confirmed"] is False
    assert edges[2]["confirmed"] is True
    assert graph["rules"][0]["targets"][0]["evidence"][0]["quote"] == "q"


def test_subject_without_evidence_fails_and_unknown_subject_is_reported():
    with pytest.raises(ValueError, match="no evidence"):
        build_graph([RULE], {"rules": [{"id": "R", "sources": ["a2"], "targets": []}]}, DOC, NODES)
    graph = build_graph(
        [RULE], {"rules": [{"id": "R", "sources": ["gone"], "targets": []}]}, DOC, NODES
    )
    assert graph["excluded_subjects"] == ["gone"]
    assert item_to_hero(graph["rules"]) == []


def test_pending_trait_stays_empty_and_comparison_splits_subtypes():
    mapping = {
        "status": "draft",
        "traits": {
            "stunners": {
                "zh": "控",
                "mechanisms": ["break_sensitive"],
                "v1": "x",
                "v1_subtype": "s",
            },
            "later": {"zh": "待", "pending": "等定义"},
        },
    }
    heroes = [
        {"hero_id": 1, "name_zh": "甲", "abilities": [{"name": "a1", "name_zh": "一"}]},
        {"hero_id": 2, "name_zh": "乙", "abilities": [{"name": "a2", "name_zh": "二"}]},
    ]
    traits = build_traits(mapping, DOC, heroes)
    assert traits["traits"]["later"]["heroes"] == []
    assert [h["confirmed"] for h in traits["traits"]["stunners"]["heroes"]] == [False, True]
    v1 = {
        "labels": {
            "x": [
                {"hero": "甲", "subtype": "s"},
                {"hero": "丙", "subtype": "s"},
                {"hero": "乙", "subtype": "t"},
            ]
        }
    }
    assert compare_with_v1(traits, v1, mapping)["stunners"] == {
        "v1": "x",
        "kept": 1,
        "added": ["乙"],
        "dropped": ["丙"],
    }


def test_package_replays_and_never_overwrites(tmp_path):
    builder.run(tmp_path / "out")
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    fresh = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert fresh["output_sha256"] == manifest["output_sha256"]
    with pytest.raises(ValueError, match="exists"):
        builder.run(tmp_path / "out")


def test_real_graph_links_items_and_heroes():
    graph = json.loads((PACKAGE / "counter-graph.json").read_text(encoding="utf-8"))
    assert graph["excluded_subjects"] == []
    rule20 = next(rule for rule in graph["rules"] if rule["id"] == "R20")
    assert "naga_siren_mirror_image" in {t["subject"] for t in rule20["targets"]}
    naga_id = next(
        t["hero_id"] for t in rule20["targets"] if t["subject"] == "naga_siren_mirror_image"
    )
    assert any(
        edge["item"] == "radiance" and edge["hero_id"] == naga_id and edge["rule"] == "R20"
        for edge in graph["item_to_hero"]
    )
    source = next(s["hero_id"] for s in rule20["sources"] if s.get("hero_id"))
    assert any(e["rule"] == "R20" for e in edges_between(graph, source, naga_id))


def test_recall_check_separates_rejected_from_missing():
    doc = {"rows": [_row("a1", "stun"), _row("a2", "self_mobility", "two_ai", "reject")]}
    heroes = [
        {
            "hero_id": 1,
            "name_zh": "甲",
            "abilities": [
                {"name": "a1", "name_zh": "一", "description_en": "Stuns a target."},
                {"name": "a2", "name_zh": "二", "description_en": "Blinks away."},
                {"name": "a3", "name_zh": "三", "description_en": "Stuns an enemy."},
            ],
        }
    ]
    labels = {key: [] for key in recall.LABEL_MECHANISMS}
    labels["mobility"] = [{"hero": "甲", "abilities": ["二", "三"]}]
    result = recall.check(doc, heroes, {"labels": labels})
    assert result["against_traits_v1"]["mobility"] == {
        "accept": 0,
        "reject": ["甲·二"],
        "no_row": ["甲·三"],
    }
    assert result["against_keywords"]["stun"] == {"hits": 2, "no_row": ["甲·三"]}
