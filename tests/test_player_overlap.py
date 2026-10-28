"""Cross-match identity diagnostics preserve unknowns, frozen splits and privacy."""

import json

import pytest

from dota_items.data.player_overlap import account_status, audit_player_overlap
from dota_items.storage import file_hash


def fixture(tmp_path, accounts):
    paths, rows = {}, []
    for mid, ids in enumerate(accounts, 1):
        path = tmp_path / f"{mid}.json"
        path.write_text(
            json.dumps(
                {
                    "match_id": mid,
                    "players": [
                        {"player_slot": slot, "account_id": account}
                        for slot, account in zip(
                            [0, 1, 2, 3, 4, 128, 129, 130, 131, 132], ids, strict=True
                        )
                    ],
                }
            )
        )
        paths[mid] = path
        rows.append({"match_id": mid, "target_slot": 0, "sha256": file_hash(path)})
    return rows, paths


def test_overlap_and_transitive_groups_do_not_expose_accounts(tmp_path):
    accounts = [
        list(range(111111111, 111111121)),
        list(range(222222221, 222222231)),
        list(range(333333331, 333333341)),
    ]
    accounts[1][1] = accounts[0][0]
    accounts[2][2] = accounts[1][2]
    rows, paths = fixture(tmp_path, accounts)
    splits = {"train": [1], "validation": [2], "test": [3]}
    result = audit_player_overlap(rows, paths, splits)
    assert result["status"] == "overlap_detected"
    assert result["connected_match_groups"] == [[1, 2, 3]]
    assert result["split_pairs"][0]["shared_known_players"] == 1
    assert result["split_pairs"][0]["target_to_any_shared_players"] == 1
    assert result["summary"]["repeated_known_players"] == 2
    assert not result["player_disjoint_verified"]
    assert splits == {"train": [1], "validation": [2], "test": [3]}
    for ids in accounts:
        assert all(str(account) not in json.dumps(result) for account in ids)


def test_unknown_accounts_never_create_overlap(tmp_path):
    rows, paths = fixture(
        tmp_path, [[None, 0, 4294967295, True, -1, "123", None, 0, None, None]] * 3
    )
    result = audit_player_overlap(rows, paths, {"train": [1], "validation": [2], "test": [3]})
    assert result["status"] == "no_observed_overlap"
    assert not result["identity_coverage_complete"]
    assert not result["player_disjoint_verified"]
    assert result["connected_match_groups"] == [[1], [2], [3]]
    assert result["summary"]["invalid_player_slots"] == 9


def test_complete_disjoint_ids_and_within_match_duplicate(tmp_path):
    accounts = [list(range(i * 10 + 1, i * 10 + 11)) for i in range(3)]
    rows, paths = fixture(tmp_path, accounts)
    splits = {"train": [1], "validation": [2], "test": [3]}
    assert audit_player_overlap(rows, paths, splits)["player_disjoint_verified"]
    accounts[0][1] = accounts[0][0]
    rows, paths = fixture(tmp_path, accounts)
    result = audit_player_overlap(rows, paths, splits)
    assert result["summary"]["duplicate_known_slots"] == 1
    assert not result["player_disjoint_verified"]


def test_source_mutation_rejected(tmp_path):
    rows, paths = fixture(tmp_path, [list(range(1, 11))] * 3)
    paths[1].write_text(paths[1].read_text() + " ")
    with pytest.raises(ValueError, match="source changed"):
        audit_player_overlap(rows, paths, {"train": [1], "validation": [2], "test": [3]})


@pytest.mark.parametrize(
    "splits",
    [
        {"train": [1], "validation": [1], "test": [3]},
        {"train": [1], "validation": [2], "test": []},
        {"train": [1, 2, 3]},
    ],
)
def test_bad_split_coverage_rejected(tmp_path, splits):
    rows, paths = fixture(tmp_path, [list(range(1, 11))] * 3)
    with pytest.raises(ValueError):
        audit_player_overlap(rows, paths, splits)


def test_no_split_is_explicitly_not_checked():
    assert audit_player_overlap([], {}, None)["status"] == "not_checked_no_split"


@pytest.mark.parametrize(
    "value,status",
    [(4294967294, "known"), (4294967296, "invalid"), (1.0, "invalid"), (False, "invalid")],
)
def test_account_boundaries(value, status):
    assert account_status(value) == status
