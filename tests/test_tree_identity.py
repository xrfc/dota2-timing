from copy import deepcopy

import pytest

from dota_items.data.tree_identity import (
    IncompleteTreeIdentity,
    parse_tree_export,
    reconcile_tree_identity,
)

TREES = [{"x": 1, "y": 2, "z": 3}, {"x": 4, "y": 5, "z": 6}]
EXPORT = (
    "DOTA_TREE_IDENTITY_BEGIN\t1\t7.42\t6993\tdota\n"
    "DOTA_TREE_IDENTITY_ROW\t900\t20\t20\t1\t2\t3\n"
    "DOTA_TREE_IDENTITY_ROW\t7\t19\t19\t4\t5\t6\n"
    "DOTA_TREE_IDENTITY_END\t2\n"
)


def test_complete_mapping_uses_native_id_not_sorted_or_map_order():
    rows = parse_tree_export(EXPORT, exact_patch="7.42", expected_build=6993)
    result = reconcile_tree_identity(TREES, list(reversed(rows)))
    assert [r["native_tree_id"] for r in result["trees"]] == [900, 7]
    assert result["map_coordinate_coverage_complete"]
    assert not result["replay_build_equivalence_verified"]
    assert not result["action_review_allowed"]


@pytest.mark.parametrize(
    "mutation",
    [
        "partial",
        "duplicate_id",
        "duplicate_entity",
        "duplicate_point",
        "roundtrip",
        "nearby",
        "missing_id",
        "boolean_id",
        "nan",
    ],
)
def test_incomplete_or_ambiguous_maps_are_rejected(mutation):
    rows = parse_tree_export(EXPORT, exact_patch="7.42", expected_build=6993)
    if mutation == "partial":
        rows.pop()
    if mutation == "duplicate_id":
        rows[1]["native_tree_id"] = rows[0]["native_tree_id"]
    if mutation == "duplicate_entity":
        rows[1]["entity_index"] = rows[1]["roundtrip_entity_index"] = 20
    if mutation == "duplicate_point":
        rows[1].update(TREES[0])
    if mutation == "roundtrip":
        rows[1]["roundtrip_entity_index"] = 100
    if mutation == "nearby":
        rows[1]["x"] += 0.1
    if mutation == "missing_id":
        rows[1].pop("native_tree_id")
    if mutation == "boolean_id":
        rows[1]["native_tree_id"] = True
    if mutation == "nan":
        rows[1]["x"] = float("nan")
    with pytest.raises(ValueError):
        reconcile_tree_identity(TREES, rows)


@pytest.mark.parametrize(
    "text",
    [
        EXPORT.rsplit("DOTA_TREE_IDENTITY_END", 1)[0],
        EXPORT + EXPORT,
        EXPORT.replace("7.42\t", "7.42a\t"),
        EXPORT.replace("6993", "6989"),
        EXPORT.replace("END\t2", "END\t3"),
    ],
)
def test_export_requires_exact_identity_and_complete_framing(text):
    with pytest.raises(ValueError):
        parse_tree_export(text, exact_patch="7.42", expected_build=6993)


def test_existing_coordinate_only_export_is_not_a_native_identity_table():
    with pytest.raises(ValueError):
        reconcile_tree_identity(TREES, deepcopy(TREES))
    with pytest.raises(IncompleteTreeIdentity):
        reconcile_tree_identity(TREES, [])
