import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from dota_items.data.awareness_split import is_holdout

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_decision_reports.py"
spec = importlib.util.spec_from_file_location("audit_decision_reports", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
MID = 9080976703


def report_data(mode="lane"):
    case = {
        "id": f"{'' if mode == 'lane' else mode + '-'}{MID}-slark-900",
        "match": MID,
        "hero": "slark",
        "t": 900,
        "history": [{"t": 900, "enemies": [{"hero": "axe", "last_seen": 899, "distance": None}]}],
        "support_opportunity": {"hero": "rubick", "seconds_ago": 7},
        "arrival": {"routes": {"walk": {"now": [5, 7], "after_six": [11, 13]}}},
    }
    action = {"action": "unknown" if mode == "jungle" else "farm", "lean": "unknown"}
    hit_key = "jungle_last_hits" if mode == "jungle" else "lane_last_hits"
    outcome = {
        hit_key: 2,
        "complete": True,
        "death_seconds": [920],
        "farm_value": {
            "next_6s": {"lane": 1, "neutral": 1, "observed_seconds": 6},
            "next_20s": {"lane": 2, "neutral": 2, "observed_seconds": 20},
        },
        "support_followup": {"hit_offsets": [1, 7], "complete": True},
    }
    return case, action, outcome


def write_packet(folder, case, action, outcome, mode="lane"):
    folder.mkdir(exist_ok=True)
    manifest = {"schema": f"{mode}-decision-review/1", "mode": mode, "cases": [case]}
    (folder / "cases.json").write_text(json.dumps(manifest))
    for name, data in (("actions", action), ("outcomes", outcome)):
        (folder / name).mkdir(exist_ok=True)
        if data is not None:
            (folder / name / f"{case['id']}.json").write_text(json.dumps(data))


def audited(folder):
    return audit.audit_reports([folder])["reports"][0]["cases"][0]


@pytest.mark.parametrize("mode", ["lane", "wave", "jungle"])
def test_recomputes_walk_for_complete_and_censored_reports(tmp_path, mode):
    case, action, outcome = report_data(mode)
    write_packet(tmp_path, case, action, outcome, mode)
    result = audited(tmp_path)
    assert result["status"] == "passed"
    assert (result["support"]["now"], result["support"]["after_six"]) == (
        "both_before_hit",
        "after_observed_hits",
    )
    outcome["complete"] = outcome["support_followup"]["complete"] = False
    outcome["death_seconds"] = [907]
    outcome["farm_value"]["next_20s"]["observed_seconds"] = 7
    write_packet(tmp_path, case, action, outcome, mode)
    result = audited(tmp_path)
    assert result["status"] == "passed" and result["outcome_window"]["observed_seconds"] == 7
    assert result["support"]["after_six"] == "unknown"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda c, a, o: c["history"][0].update(t=901), "frame_time"),
        (lambda c, a, o: c["history"][0]["enemies"][0].update(distance=1), "hidden_enemy_distance"),
        (lambda c, a, o: c.update(walk_hit_window={}), "post_decision_field_in_evidence"),
        (lambda c, a, o: a.update(action="retreat"), "retreat_with_last_hit"),
        (lambda c, a, o: o.update(lane_last_hits=3), "conflicting_last_hit_count"),
        (lambda c, a, o: o.update(death_seconds=[900]), "death_outside_window"),
        (
            lambda c, a, o: o["support_followup"].update(hit_offsets=[1, 2, 2]),
            "unsorted_or_duplicate_hit",
        ),
        (lambda c, a, o: o["support_followup"].update(hit_offsets=[True]), "hit_outside_window"),
        (
            lambda c, a, o: c["arrival"]["routes"]["walk"].update(after_six=[10, 12]),
            "invalid_delay",
        ),
        (
            lambda c, a, o: o.update(walk_hit_window={"now": "after_observed_hits"}),
            "recalculation_mismatch",
        ),
        (lambda c, a, o: c.update(support_opportunity=None), "followup_without_target"),
    ],
)
def test_contradictions_are_evidence_errors(tmp_path, mutation, expected):
    case, action, outcome = report_data()
    mutation(case, action, outcome)
    write_packet(tmp_path, case, action, outcome)
    row = audited(tmp_path)
    assert row["status"] == "failed"
    assert expected in {issue["reason"] for issue in row["issues"]}


def test_absent_source_damaged_source_and_legitimate_unknowns(tmp_path):
    case, action, outcome = report_data()
    case["arrival"]["routes"] = {}
    write_packet(tmp_path, case, action, outcome)
    assert audited(tmp_path)["support"]["route_available"] is False
    assert audited(tmp_path)["status"] == "passed"
    case["support_opportunity"] = None
    del case["arrival"], outcome["support_followup"]
    write_packet(tmp_path, case, action, outcome)
    assert audited(tmp_path)["checks"]["support"] == "not_applicable"
    file = tmp_path / "actions" / f"{case['id']}.json"
    file.unlink()
    assert audited(tmp_path)["status"] == "incomplete"
    file.write_text("{")
    assert audited(tmp_path)["status"] == "failed"
    assert audited(tmp_path)["checks"]["farm"] == "passed"


def test_reserved_and_duplicate_cases_do_not_open_sidecars(tmp_path):
    case, action, outcome = report_data()
    write_packet(tmp_path, case, action, outcome)
    reserved = next(n for n in range(1, 200) if is_holdout(n))
    reserved_case = dict(case, id=f"{reserved}-rubick-900", match=reserved, hero="rubick")
    (tmp_path / "cases.json").write_text(
        json.dumps({"schema": "lane-decision-review/1", "cases": [case, case, reserved_case]})
    )
    result = audit.audit_reports([tmp_path])
    assert result["counts"] == {"passed": 0, "incomplete": 0, "failed": 3}
    assert all(row["checks"] == {"identity": "failed"} for row in result["reports"][0]["cases"])


def test_cli_reports_incomplete_folder_and_fails_on_corrupt_manifest(tmp_path):
    cmd = [sys.executable, str(SCRIPT), "--review-dir", str(tmp_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["reports"][0]["status"] == "incomplete"
    (tmp_path / "cases.json").write_text("[]")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 1 and json.loads(result.stdout)["reports"][0]["status"] == "failed"


def test_certified_end_bounds_action_deaths_farm_and_hits_independently(tmp_path):
    case, action, outcome = report_data()
    outcome.update(match_duration=904, last_state_second=938)
    write_packet(tmp_path, case, action, outcome)
    row = audited(tmp_path)
    assert row["match_end"]["effective_end"] == 904
    assert [row["checks"][name] for name in ("farm", "deaths", "support")] == ["failed"] * 3
    outcome["complete"] = outcome["support_followup"]["complete"] = False
    outcome["death_seconds"] = [904]
    outcome["support_followup"]["hit_offsets"] = [4]
    outcome["farm_value"] = {
        "next_6s": {"lane": 2, "neutral": 1, "observed_seconds": 4},
        "next_20s": {"lane": 2, "neutral": 1, "observed_seconds": 4},
    }
    write_packet(tmp_path, case, action, outcome)
    assert "action_claim_in_partial_window" in {i["reason"] for i in audited(tmp_path)["issues"]}
    action["action"] = "unknown"
    write_packet(tmp_path, case, action, outcome)
    assert audited(tmp_path)["status"] == "passed"
    outcome.update(match_duration=950, last_state_second=904)
    write_packet(tmp_path, case, action, outcome)
    assert audited(tmp_path)["match_end"]["effective_end"] == 904
    outcome["last_state_second"] = 899
    write_packet(tmp_path, case, action, outcome)
    assert audited(tmp_path)["checks"]["match_end"] == "failed"


def test_legacy_bounds_approach_and_missing_positions(tmp_path):
    case, action, outcome = report_data()
    case["history"][0]["enemies"][0].update(last_seen=None, distance=None)
    outcome["observed_approach"] = {
        "observed_seconds": 20,
        "window_complete": True,
        "missing_samples": 21,
        "first_seen_offset": None,
        "first_entry_offset": None,
    }
    write_packet(tmp_path, case, action, outcome)
    row = audited(tmp_path)
    assert row["checks"]["match_end"] == "unverified_legacy" and row["status"] == "passed"
    outcome["observed_approach"]["first_seen_offset"] = 21
    write_packet(tmp_path, case, action, outcome)
    assert "entry_outside_window" in {i["reason"] for i in audited(tmp_path)["issues"]}
    del outcome["observed_approach"]
    outcome["match_duration"] = 950
    write_packet(tmp_path, case, action, outcome)
    assert audited(tmp_path)["checks"]["match_end"] == "incomplete"
