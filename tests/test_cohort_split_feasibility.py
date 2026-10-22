import copy
import importlib.util
import sys
from pathlib import Path

import pytest

from dota_items.data.cohort_split_feasibility import analyze


def rows():
    return [
        {
            "match_id": i,
            "cohort": "old" if i < 4 else "new",
            "labels": [i % 2, None],
            "mask": [True, False],
        }
        for i in range(1, 11)
    ]


def groups():
    return [[1, 2, 3, 4, 99], [5, 6], [7], [8], [9], [10], [100, 101]]


def test_projection_keeps_excluded_bridges_but_not_labels():
    public, private = analyze(groups(), rows(), ["a", "b"])
    assert public["graph_match_count"] == 13
    assert public["identity_only_count"] == 3
    assert public["projected_components"] == 6
    assert public["identity_only_components"] == 1
    assert public["largest_candidate_component"] == 4
    assert public["support"]["a"] == {
        "positive": 5,
        "negative": 5,
        "unknown": 0,
        "positive_rate": 0.5,
    }
    assert public["support"]["b"]["unknown"] == 10
    for proposal in private.values():
        assert {1, 2, 3, 4} <= set(proposal["train"])
        assert set(proposal["train"]) | set(proposal["validation"]) == set(range(1, 11))
        assert not set(proposal["train"]) & set(proposal["validation"])
        assert not {99, 100, 101} & (set(proposal["train"]) | set(proposal["validation"]))
    assert all(p["whole_groups_verified"] for p in public["proposals"])
    assert public["formal_split_assigned"] is False
    assert public["training_executed"] is False
    assert "match_ids" not in str(public) and "account_id" not in str(public)


def test_no_label_search_and_order_invariant_and_no_mutation():
    original_rows, original_groups = rows(), groups()
    before = copy.deepcopy((original_rows, original_groups))
    public, private = analyze(original_groups, original_rows, ["a", "b"])
    changed = copy.deepcopy(original_rows)
    for row in changed:
        row["labels"][0] = 1 - row["labels"][0]
    altered, assignments = analyze(
        list(reversed(original_groups)), list(reversed(changed)), ["a", "b"]
    )
    assert assignments == private
    assert [p["membership_sha256"] for p in public["proposals"]] == [
        p["membership_sha256"] for p in altered["proposals"]
    ]
    assert (original_rows, original_groups) == before


def test_infeasible_single_component_not_split_to_force_ratio():
    public, private = analyze([list(range(1, 11))], rows(), ["a", "b"])
    assert all(not p["nonempty_sides"] for p in public["proposals"])
    assert all(not p["validation"] for p in private.values())
    assert public["proposals"][0]["validation_target_count_error"] == -2


def test_all_rest_and_support_conservation():
    public, private = analyze(groups(), rows(), ["a", "b"])
    assert private["all_rest"] == {"train": [1, 2, 3, 4], "validation": [5, 6, 7, 8, 9, 10]}
    for proposal in public["proposals"]:
        assert sum(s["matches"] for s in proposal["splits"].values()) == 10
        for item in ("a", "b"):
            for status in ("positive", "negative", "unknown"):
                assert (
                    sum(s["support"][item][status] for s in proposal["splits"].values())
                    == public["support"][item][status]
                )


@pytest.mark.parametrize(
    "damage",
    [
        "duplicate",
        "missing",
        "empty",
        "overlap",
        "invalid_id",
        "bool_id",
        "mask",
        "label",
        "dimension",
        "null",
        "cohort",
    ],
)
def test_bad_inputs_rejected(damage):
    r, g = rows(), groups()
    if damage == "duplicate":
        r.append(r[0])
    elif damage == "missing":
        g[0].remove(1)
    elif damage == "empty":
        r = []
    elif damage == "overlap":
        g.append([1])
    elif damage == "invalid_id":
        g.append([-1])
    elif damage == "bool_id":
        r[0]["match_id"] = True
    elif damage == "mask":
        r[0]["mask"][0] = 1
    elif damage == "label":
        r[0]["labels"][0] = 0.5
    elif damage == "dimension":
        r[0]["labels"] = []
    elif damage == "null":
        r[0]["labels"][1] = 0
    else:
        r[0]["cohort"] = "other"
    with pytest.raises(ValueError):
        analyze(g, r, ["a", "b"])


def cli_module():
    path = Path(__file__).resolve().parents[1] / "scripts/analyze_cohort_splits.py"
    spec = importlib.util.spec_from_file_location("split_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cli_args(output):
    return [
        "analyze",
        "--old-root",
        "old",
        "--new-root",
        "new",
        "--summary",
        "summary",
        "--snapshot",
        "snapshot",
        "--audit",
        "audit",
        "--output",
        str(output),
    ]


def test_cli_failed_verification_creates_no_output(tmp_path, monkeypatch):
    cli = cli_module()
    output = tmp_path / "out"

    def reject(*args):
        raise ValueError("Evidence changed")

    monkeypatch.setattr(cli, "build_report", reject)
    monkeypatch.setattr(sys, "argv", cli_args(output))
    with pytest.raises(ValueError):
        cli.main()
    assert not output.exists()


def test_cli_completes_proposal_only_and_refuses_overwrite(tmp_path, monkeypatch):
    cli = cli_module()
    output = tmp_path / "out"
    public, private = analyze(groups(), rows(), ["a", "b"])
    monkeypatch.setattr(cli, "build_report", lambda *args: (public, private))
    monkeypatch.setattr(sys, "argv", cli_args(output))
    cli.main()
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    assert set(before) == {"aggregate.json", "private-proposals.json", "complete.json"}
    with pytest.raises(SystemExit):
        cli.main()
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


@pytest.mark.parametrize("damage", [None, "raw", "graph", "unknown_hash"])
def test_registered_audit_migration_only_changes_known_implementation(damage):
    from dota_items.data.producer_migration import COMPATIBLE_SHA256, ROOT
    from dota_items.storage import file_hash

    cli = cli_module()
    key = str(ROOT / "data/producer_migration.py")
    saved = {
        "evidence_sha256": {
            key: next(iter(COMPATIBLE_SHA256["data/producer_migration.py"])),
            "raw.json": "unchanged",
        },
        "graphs": {"count": 1},
    }
    rebuilt = copy.deepcopy(saved)
    rebuilt["evidence_sha256"][key] = file_hash(Path(key))
    with pytest.raises(ValueError):
        cli.compare_audit(saved, rebuilt)
    if damage == "raw":
        rebuilt["evidence_sha256"]["raw.json"] = "changed"
    elif damage == "graph":
        rebuilt["graphs"]["count"] = 2
    elif damage == "unknown_hash":
        saved["evidence_sha256"][key] = "0" * 64
    if damage:
        with pytest.raises(ValueError):
            cli.compare_audit(saved, rebuilt, allow=True)
    else:
        result = cli.compare_audit(saved, rebuilt, allow=True)
        assert result["mode"] == "registered-producer-compatible"
        assert len(result["changes"]) == 1
        assert result["changes"][0]["path"] == [
            "implementation_sha256",
            "data/producer_migration.py",
        ]
