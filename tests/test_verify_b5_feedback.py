"""Verify the B5 notebook export through the public, offline CLI."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[1] / "scripts" / "verify_b5_feedback.py"
WORDS = "  测试原话：地图？\n🗺️  "


def make_report(directory, match="101", *, heading_match=None, duplicate=False):
    path = directory / match / "match-report.md"
    path.parent.mkdir(parents=True)
    lines = [
        f"# 对局 {heading_match or match} · 一号位行动复盘",
        "",
        "## 15:01　甲 · 兵线",
        "",
        "## 15:01　乙 · 兵线",
        "",
        "## 15:01　甲 · 支援",
    ]
    if duplicate:
        lines.append(lines[2])
    lines.extend(["", "## 逐秒输入覆盖", ""])
    content = "\r\n".join(lines).encode("utf-8")
    path.write_bytes(content)
    return {
        "match": match,
        "report_sha256": hashlib.sha256(content).hexdigest(),
        "time": "15:01",
        "seconds": 901,
        "hero": "甲",
        "domain": "兵线",
        "feedback": WORDS,
    }


def run_cli(directory, data):
    source = directory / "feedback.json"
    source.write_bytes(data)
    return subprocess.run(
        [sys.executable, str(CLI), str(source), "--report-root", str(directory / "reports")],
        capture_output=True,
        cwd=directory,
        encoding="utf-8",
        check=False,
    )


def run_export(directory, records):
    data = {"schema": "b5-trial-feedback/1", "records": records}
    return run_cli(directory, json.dumps(data, ensure_ascii=False).encode("utf-8"))


def assert_rejected(result):
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip()
    assert "测试原话" not in result.stderr
    assert "Traceback" not in result.stderr


def test_verifies_raw_bytes_and_points_to_exact_heading_in_export_order(tmp_path):
    reports = tmp_path / "reports"
    a = make_report(reports)
    b = make_report(reports, "202")
    unrelated = reports / "303" / "match-report.md"
    unrelated.parent.mkdir()
    unrelated.write_bytes(b"\xff")
    notes = [b, a | {"domain": "支援"}, a | {"hero": "乙"}, a]
    result = run_export(tmp_path, notes)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "schema": "b5-verified-feedback/1",
        "records": [
            dict(note, report=f"{note['match']}/match-report.md", line=line)
            for note, line in zip(notes, [3, 7, 5, 3], strict=True)
        ],
    }


def test_empty_export_has_no_verified_records(tmp_path):
    result = run_export(tmp_path, [])
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"schema": "b5-verified-feedback/1", "records": []}


@pytest.mark.parametrize(
    "changes",
    [
        {"match": "303"},
        {"hero": "丙"},
        {"domain": "打野"},
        {"time": "15:02"},
        {"feedback": "\t\n"},
    ],
)
def test_invalid_later_record_yields_no_partial_output(tmp_path, changes):
    first = make_report(tmp_path / "reports")
    other = make_report(tmp_path / "reports", "202")
    assert_rejected(run_export(tmp_path, [first, other | changes]))


def test_duplicate_feedback_is_not_counted_twice(tmp_path):
    note = make_report(tmp_path / "reports")
    assert_rejected(run_export(tmp_path, [note, note | {"feedback": "另一条文字"}]))


def test_match_cannot_reference_an_existing_path_outside_root(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    note = make_report(tmp_path, "outside", heading_match="../outside")
    assert_rejected(run_export(tmp_path, [note | {"match": "../outside"}]))


def test_json_boolean_cannot_stand_for_second_one(tmp_path):
    reports = tmp_path / "reports"
    note = make_report(reports)
    path = reports / "101" / "match-report.md"
    source = path.read_bytes().replace(b"15:01", b"0:01")
    path.write_bytes(source)
    note.update(time="0:01", seconds=True, report_sha256=hashlib.sha256(source).hexdigest())
    assert_rejected(run_export(tmp_path, [note]))


@pytest.mark.parametrize("problem", ["drift", "wrong-title", "ambiguous-heading", "wrong-level"])
def test_report_must_match_version_and_uniquely_identify_a_clip(tmp_path, problem):
    reports = tmp_path / "reports"
    note = make_report(
        reports,
        heading_match="202" if problem == "wrong-title" else None,
        duplicate=problem == "ambiguous-heading",
    )
    path = reports / "101" / "match-report.md"
    content = path.read_bytes()
    if problem == "drift":
        path.write_bytes(content.replace(b"\r\n", b"\n"))
    if problem == "wrong-level":
        content = content.replace(b"## ", b"### ")
        path.write_bytes(content)
        note["report_sha256"] = hashlib.sha256(content).hexdigest()
    assert_rejected(run_export(tmp_path, [note]))


@pytest.mark.parametrize(
    "data",
    [
        b"\xff",
        b"{",
        b'{"schema":"b5-trial-feedback/2","records":[]}',
        b'{"schema":"b5-trial-feedback/1","records":{}}',
        b'{"schema":"b5-trial-feedback/1","records":[{}]}',
    ],
)
def test_malformed_export_reports_cli_error(tmp_path, data):
    assert_rejected(run_cli(tmp_path, data))
