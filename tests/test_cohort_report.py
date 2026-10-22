import copy
import hashlib
import json
import subprocess
import sys

import pytest

from dota_items.data.cohort_report import render_report, write_report


def fixture():
    c = {
        "attempted": 3,
        "retained": 2,
        "excluded": 1,
        "excluded_cache_present": 0,
        "reason_counts": {"missing": 1, "other": 1},
        "exclusions": [
            {
                "requested_match_id": 999999,
                "cache_present": False,
                "evidence_level": "historical_receipt_only",
                "reasons": ["missing", "other"],
            }
        ],
    }
    d = {
        "matches": 2,
        "log_status": {"present": 2},
        "role_hints": {"unknown": 2},
        "patch_time": {"unknown": 2},
        "empty_logs": 0,
        "event_at_or_after_1800": 1,
        "matches_with_exact_duplicate_rows": 0,
        "matches_with_simultaneous_distinct_items": 0,
        "matches_with_recipe_rows": 0,
        "log_observation_support": {
            "item": {"positive": 1, "negative": 1, "unknown": 0, "positive_rate": 0.5}
        },
    }
    for key in (
        "start_time_unix",
        "duration_seconds",
        "discovery_average_rank_hint",
        "discovery_rank_record_count",
    ):
        d[key] = {"observed": 0, "missing": 2, "min": None, "median": None, "max": None}
    g = {
        "not_a_model_split": True,
        "bucket_meaning": {"train": "old cohort", "validation": "new cohort", "test": "empty"},
        "identity_coverage_complete": True,
        "identity_summary": {
            "matches": 4,
            "duplicate_known_slots": 0,
            "invalid_player_slots": 0,
            "unknown_player_slots": 0,
            "known_distinct_players": 38,
        },
        "direct_shared_known_players": 2,
        "groups": [
            {
                "match_ids": [101111, 202222, 303333, 404444],
                "size": 4,
                "old_count": 2,
                "new_count": 2,
                "old_splits": ["train", "test"],
                "old_group_count": 2,
                "bridges_old_splits": True,
            }
        ],
        "group_count": 1,
        "largest_group": 4,
        "bridging_group_count": 1,
        "mixed_old_new_groups": 1,
        "new_in_bridging_groups": 2,
        "new_without_observed_old_connection": 0,
    }
    a = {
        "schema_version": "purchase-cohort-audit/1",
        "training_allowed": False,
        "old_split_changed": False,
        "new_split_assigned": False,
        "collections": {k: copy.deepcopy(c) for k in ("old", "new")},
        "distributions": {
            k: copy.deepcopy(d) for k in ("old_retained", "new_retained", "new_inspectable")
        },
        "graphs": {
            k: copy.deepcopy(g) for k in ("retained_only", "including_new_excluded_inspectable")
        },
        "limitations": ["Synthetic only"],
        "evidence_sha256": {"secret-path": "a" * 64},
    }
    a["collections"]["new"]["exclusions"][0]["evidence_level"] = "offline_replayed"
    return a


def test_normal_and_privacy():
    a = fixture()
    before = copy.deepcopy(a)
    report = render_report(a)
    assert a == before
    for text in ("候选 2", "原因可重叠", "缺日志是未知", "跨旧 split 组 1", "新增用途未授权"):
        assert text in report
    for text in ("999999", "101111", "secret-path"):
        assert text not in report


@pytest.mark.parametrize(
    "path",
    [
        "schema_version",
        "collections.old.attempted",
        "collections.new.reason_counts",
        "distributions.old_retained.matches",
        "distributions.new_inspectable.log_status",
        "graphs.retained_only.groups",
        "graphs.retained_only.identity_summary.matches",
        "training_allowed",
        "limitations",
    ],
)
def test_missing(path):
    a = fixture()
    target = a
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[key]
    del target[keys[-1]]
    with pytest.raises(ValueError):
        render_report(a)


@pytest.mark.parametrize("bad", [True, -1, 1.0, "3", None])
@pytest.mark.parametrize(
    "path",
    [
        "collections.old.attempted",
        "graphs.retained_only.largest_group",
        "distributions.old_retained.matches",
    ],
)
def test_bad_counts(path, bad):
    a = fixture()
    target = a
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = bad
    with pytest.raises(ValueError):
        render_report(a)


@pytest.mark.parametrize(
    "path,value",
    [
        ("schema_version", "purchase-cohort-audit/2"),
        ("training_allowed", True),
        ("old_split_changed", 0),
        ("new_split_assigned", None),
        ("producer_migration", "unknown"),
        ("collections.old.attempted", 4),
        ("collections.new.excluded_cache_present", 1),
        ("collections.old.reason_counts.missing", 2),
        ("graphs.retained_only.not_a_model_split", False),
        ("graphs.retained_only.bucket_meaning.train", "training"),
        ("graphs.retained_only.bridging_group_count", 0),
        ("graphs.retained_only.identity_coverage_complete", False),
        ("distributions.old_retained.log_status.present", 1),
        ("distributions.old_retained.log_observation_support.item.positive_rate", 0.6),
        ("distributions.old_retained.duration_seconds.median", 0),
    ],
)
def test_contradictions(path, value):
    a = fixture()
    target = a
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    with pytest.raises(ValueError):
        render_report(a)


def test_escape():
    a = fixture()
    a["limitations"] = ["<script>x</script>\n# title | [link](url) &"]
    report = render_report(a)
    assert "<script>" not in report and "[link]" not in report and "\n# title" not in report
    assert "&#60;script&#62;" in report and "&#124;" in report


@pytest.mark.parametrize("raw", [b"{}", b'{"a":1,"a":2}', b"null", b"[]", b"broken"])
def test_invalid_no_output(tmp_path, raw):
    source = tmp_path / "audit.json"
    source.write_bytes(raw)
    with pytest.raises(ValueError):
        write_report(source, tmp_path / "report.md")
    assert [p.name for p in tmp_path.iterdir()] == ["audit.json"]


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_nonfinite_unused(tmp_path, token):
    source = tmp_path / "audit.json"
    source.write_text(json.dumps(fixture())[:-1] + ', "extra":' + token + "}")
    with pytest.raises(ValueError):
        write_report(source, tmp_path / "report.md")
    assert not (tmp_path / "report.md").exists()


@pytest.mark.parametrize("kind", ["file", "directory", "dangling", "link"])
def test_no_overwrite(tmp_path, kind):
    source, output = tmp_path / "audit.json", tmp_path / "report.md"
    source.write_text(json.dumps(fixture()))
    if kind == "file":
        output.write_text("keep")
    elif kind == "directory":
        output.mkdir()
    else:
        output.symlink_to(tmp_path / "missing" if kind == "dangling" else source)
    before = source.read_bytes()
    with pytest.raises(FileExistsError):
        write_report(source, output)
    assert source.read_bytes() == before
    if kind == "file":
        assert output.read_text() == "keep"
    if kind == "dangling":
        assert not (tmp_path / "missing").exists()


def test_publish_failure(tmp_path, monkeypatch):
    source = tmp_path / "audit.json"
    source.write_text(json.dumps(fixture()))

    def fail(*args):
        raise OSError("injected failure")

    monkeypatch.setattr("dota_items.data.cohort_report.os.link", fail)
    with pytest.raises(OSError):
        write_report(source, tmp_path / "report.md")
    assert [p.name for p in tmp_path.iterdir()] == ["audit.json"]


def test_cli(tmp_path):
    source, output = tmp_path / "audit.json", tmp_path / "report.md"
    source.write_text(json.dumps(fixture()))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cmd = [
        sys.executable,
        "scripts/report_purchase_cohorts.py",
        "--input",
        str(source),
        "--output",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert digest in output.read_text()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    assert subprocess.run(cmd, capture_output=True).returncode == 1
    source.write_text("{}")
    cmd[-1] = str(tmp_path / "invalid.md")
    assert subprocess.run(cmd, capture_output=True).returncode == 1
    assert not (tmp_path / "invalid.md").exists()


def test_duplicate_valid_boundary_key_rejected(tmp_path):
    source = tmp_path / "audit.json"
    source.write_text(json.dumps(fixture())[:-1] + ', "training_allowed": false}')
    with pytest.raises(ValueError):
        write_report(source, tmp_path / "report.md")
    assert not (tmp_path / "report.md").exists()


def test_publish_race_preserves_competing_file(tmp_path, monkeypatch):
    import os

    source, output = tmp_path / "audit.json", tmp_path / "report.md"
    source.write_text(json.dumps(fixture()))
    original = os.link

    def race(src, dst):
        output.write_text("competitor")
        return original(src, dst)

    monkeypatch.setattr("dota_items.data.cohort_report.os.link", race)
    with pytest.raises(FileExistsError):
        write_report(source, output)
    assert output.read_text() == "competitor"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["audit.json", "report.md"]
