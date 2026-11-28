import importlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
MID = 9080976703


@pytest.fixture
def queue(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("review_judgments")


def case(mode, t, *, distance=1300, support=None, save=False):
    return {
        "id": ("" if mode == "lane" else mode + "-") + f"{MID}-slark-{t}",
        "match": MID,
        "hero": "slark",
        "t": t,
        "support_opportunity": support,
        "ready_names": ["blink"] if save else [],
        "history": [{"t": t, "ally": [distance, "tusk"], "enemies": [{"distance": 500}]}],
    }


def packet(tmp, mode, rows):
    folder = tmp / mode
    folder.mkdir(exist_ok=True)
    (folder / "cases.json").write_text(
        json.dumps(
            {
                "schema": f"{mode}-decision-review/1",
                "mode": mode,
                "cases": rows,
            }
        )
    )
    return folder


def vote(queue, case, reviewer, first, *, choice=None, previewed=0):
    return dict(
        case_id=case["id"],
        reviewer=reviewer,
        first=first,
        choice=choice or first,
        previewed=previewed,
        note="secret private note",
        case_sha256=queue.case_sha256(case),
    )


def test_independent_cases_and_adjudication_revision(tmp_path, queue):
    a, b = case("lane", 900), case("lane", 970)
    folder = packet(tmp_path, "lane", [a, b])
    reviews = [
        vote(queue, a, "alice", "retreat"),
        vote(queue, a, "bob", "farm", choice="retreat"),
        vote(queue, b, "alice", "unknown"),
        vote(queue, b, "bob", "retreat"),
        vote(queue, b, "friend", "retreat", previewed=1),
    ]
    result = queue.build_queue([folder], reviews, limit=1)
    assert result["counts"]["revised_choices"] == 1
    assert result["counts"]["covered_groups"] == 1
    assert result["counts"]["previewed_records"] == 1
    assert result["deferred"] == 1 and result["queue"][0]["reason"] == "disagreement"
    assert result["queue"][0]["url"] == f"/lane/#{a['id']}"
    template = result["adjudication_template"]
    template["decisions"][0].update(decision="unknown", rationale="private final rationale")
    resolved = queue.build_queue([folder], reviews, adjudications=template)
    assert resolved["counts"]["adjudicated_cases"] == 1
    assert [item["reason"] for item in resolved["queue"]] == ["insufficient_evidence"]
    for text in ("alice", "friend", "secret private note", "private final rationale", "retreat"):
        assert text not in json.dumps(resolved)
    # Updated opinion after the blind first never reopens a decision.
    reviews[1]["choice"] = "farm"
    assert (
        queue.build_queue([folder], reviews, adjudications=template)["counts"]["adjudicated_cases"]
        == 1
    )
    reviews.append(vote(queue, a, "third", "farm"))
    assert (
        queue.build_queue([folder], reviews, adjudications=template)["counts"][
            "stale_adjudications"
        ]
        == 1
    )


def test_versioned_votes_and_future_report_replacement(tmp_path, queue):
    a = case("lane", 900)
    folder = packet(tmp_path, "lane", [a])
    old = [vote(queue, a, "alice", "retreat"), vote(queue, a, "bob", "farm")]
    template = queue.build_queue([folder], old)["adjudication_template"]
    template["decisions"][0]["decision"] = "farm"
    a["mana"] = 70
    packet(tmp_path, "lane", [a])
    new = [vote(queue, a, "alice", "retreat"), vote(queue, a, "bob", "farm")]
    legacy = vote(queue, a, "alice", "unknown")
    legacy["case_sha256"] = None
    out = queue.build_queue([folder], [*old, *new, legacy], adjudications=template)
    assert out["counts"]["unversioned_reviews"] == 1
    assert out["counts"]["other_version_reviews"] == 2
    assert out["counts"]["independent_firsts"] == 2
    assert out["counts"]["stale_adjudications"] == 1
    assert out["queue"][0]["reason"] == "disagreement"
    assert queue.build_queue([folder], old)["queue"][0]["reason"] == "fresh_reviewer"


def test_no_export_sample_budget_and_other_reports_are_not_tasks(tmp_path, queue):
    folders = []
    for mode in ("lane", "jungle", "wave"):
        rows = [
            case(mode, 900 + i, distance=[700, 1300, 2000][i % 3], save=bool(i % 2))
            for i in range(30)
        ]
        folders.append(packet(tmp_path, mode, rows))
    out = queue.build_queue(folders)
    assert out["counts"]["selected_groups"] == 15
    assert out["deferred"] == 10 and len(out["queue"]) == 5
    assert out["tasks_by_reason"] == {"independent_sample": 15}
    assert {row["mode"] for row in out["queue"]} == {"jungle", "lane", "wave"}
    assert out["adjudication_template"]["decisions"] == []
    assert all(row["reason"] == "independent_sample" for row in out["queue"])


def test_eligible_mask_with_invalid_rows_and_replacement_within_same_group(tmp_path, queue):
    a, b, c, d, e = [case("lane", t) for t in (900, 910, 920, 930, 940)]
    e["ready_names"] = ["blink"]
    folder = packet(tmp_path, "lane", [None, a, b, c, d, d, e])
    reviews = [vote(queue, a, "alice", "farm"), vote(queue, b, "alice", "unknown", previewed=True)]
    out = queue.build_queue([folder], reviews, eligible_ids={b["id"], c["id"]})
    assert out["counts"]["invalid_case_records"] == 3
    assert out["counts"]["blocked_groups"] == 1 and out["counts"]["covered_groups"] == 0
    assert [r["case_id"] for r in out["queue"]] == [c["id"]]
    assert all("evidence_sha256" not in r for r in out["queue"])
    with pytest.raises(ValueError):
        queue.build_queue([folder])


def test_duplicate_current_records_fail_closed(tmp_path, queue):
    a = case("lane", 900)
    folder = packet(tmp_path, "lane", [a])
    record = vote(queue, a, "reviewer", "retreat")
    with pytest.raises(ValueError, match="duplicate reviewer"):
        queue.build_queue([folder], [record, record])


@pytest.mark.skipif(not shutil.which("node"), reason="Node unavailable")
def test_selection_matches_browser_on_identical_report_data(queue):
    rows = [
        case(
            "lane",
            900 + i,
            distance=[700, 1300, 2000][i % 3],
            save=bool(i % 2),
            support={} if i % 4 else None,
        )
        for i in range(18)
    ]
    for i, c in enumerate(rows):
        if i % 5 == 0:
            c["history"][0]["enemies"] = [{"distance": None, "last_seen": None}] * 2
    rows.append({"id": "legacy"})
    script = """
const fs=require('node:fs'),vm=require('node:vm');
const c=vm.createContext({document:{getElementById:()=>({})}, location:{pathname:'/lane/'},
    Image:class {},fetch:()=>new Promise(()=>{})});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);
c.casesForTest=JSON.parse(fs.readFileSync(0,'utf8'));
console.log(JSON.stringify(vm.runInContext('selectReviewGroups(casesForTest).map(g=>g.ids)',c)));
"""
    js = subprocess.check_output(
        ["node", "-e", script, str(SCRIPTS / "lane_decision_assets/app.js")],
        input=json.dumps(rows),
        text=True,
    )
    assert list(queue.selected_groups(rows)) == json.loads(js)


def test_replaced_evidence_requests_a_fresh_first_then_an_updated_adjudication(tmp_path, queue):
    a = case("lane", 930)
    folder = packet(tmp_path, "lane", [a])
    first = vote(queue, a, "one", "unknown")
    dissent = vote(queue, a, "other", "retreat")
    template = queue.build_queue([folder], [first, dissent])["adjudication_template"]
    template["decisions"][0]["decision"] = "unknown"
    a["mana"] = 200
    packet(tmp_path, "lane", [a])
    result = queue.build_queue([folder], [first], adjudications=template)
    assert [r["reason"] for r in result["queue"]] == ["fresh_reviewer"]
    assert result["adjudication_template"]["decisions"] == []
    current = vote(queue, a, "two", "unknown")
    result = queue.build_queue([folder], [current], adjudications=template)
    assert [r["reason"] for r in result["queue"]] == ["changed_evidence"]
    revised = result["adjudication_template"]
    revised["decisions"][0]["decision"] = "farm"
    assert queue.build_queue([folder], [current], adjudications=revised)["queue"] == []


def test_filtered_queue_rejects_holdout_and_corrupt_evidence_without_blocking_usable_case(
    tmp_path, queue
):
    good = case("lane", 950)
    bad = {**case("lane", 960), "mana": float("nan")}
    held = next(mid for mid in range(100, 200) if queue.is_holdout(mid))
    held_case = {**good, "match": held, "id": f"{held}-slark-950"}
    folder = packet(tmp_path, "lane", [good, bad, held_case])
    result = queue.build_queue([folder], eligible_ids={c["id"] for c in [good, bad, held_case]})
    assert result["counts"]["invalid_case_records"] == 2
    assert [r["case_id"] for r in result["queue"]] == [good["id"]]


def test_filter_keeps_original_group_budget(tmp_path, queue):
    rows = [
        case("lane", 900 + i, distance=[700, 1200, 1700][i % 3], save=bool(i % 2)) for i in range(6)
    ]
    folder = packet(tmp_path, "lane", rows)
    selected = {key for group in queue.selected_groups(rows) for key in group}
    result = queue.build_queue([folder], eligible_ids={c["id"] for c in rows} - selected)
    assert result["counts"]["blocked_groups"] == 5
    assert result["queue"] == []


@pytest.mark.parametrize("count", [1, 3])
def test_only_unknown_blind_firsts_finish_the_sample_without_another_review(tmp_path, queue, count):
    a = case("lane", 900)
    folder = packet(tmp_path, "lane", [a, case("lane", 920)])
    rows = [vote(queue, a, str(i), "unknown") for i in range(count)]
    rows.append(vote(queue, a, "after-preview", "retreat", previewed=1))
    result = queue.build_queue([folder], rows)
    assert result["queue"] == [] and result["deferred"] == 0
    assert result["counts"]["covered_groups"] == 1
    assert result["counts"]["unranked_cases"] == 1
    assert result["adjudication_template"]["decisions"] == []
    rows.append(vote(queue, a, "new-blind", "farm"))
    updated = queue.build_queue([folder], rows)
    assert updated["counts"]["unranked_cases"] == 0
    assert [task["reason"] for task in updated["queue"]] == ["insufficient_evidence"]


def test_handoff_with_missing_reports_never_declares_the_human_work_complete(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    from decision_review_handoff import prepare

    missing = tmp_path / "not-generated"
    result, folders, eligible, _ = prepare([missing])
    assert result["state"] == "data_required" and not result["judgments"]["queue"]
    assert not folders and not eligible and not missing.exists()
    assert result["material_issues"][0]["reason"] == "missing_file"

    missing.mkdir()
    (missing / "cases.json").write_text("{")
    broken = prepare([missing])[0]
    assert broken["state"] == "repair_required" and not broken["judgments"]["queue"]
