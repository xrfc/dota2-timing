"""Check case-level evidence in existing decision reports; emit a retrospective JSON audit."""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from dota_items.data.awareness_split import is_holdout
from dota_items.data.lane_decisions import ACTION_SECONDS, OUTCOME_SECONDS
from dota_items.data.support_arrival import walk_hit_window


class EvidenceIssue(Exception):
    def __init__(self, status, field, reason):
        super().__init__(reason)
        self.status = status
        self.field = field


def require(condition, field, reason):
    if not condition:
        raise EvidenceIssue("failed", field, reason)


def value(row, key, kind):
    if key not in row:
        raise EvidenceIssue("incomplete", key, "missing_field")
    result = row[key]
    require(type(result) is kind, key, "wrong_type")
    return result


def read_object(folder, relative):
    path = folder / relative
    try:
        require(path.resolve().is_relative_to(folder.resolve()), relative, "outside_report")
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvidenceIssue("incomplete", relative, "missing_file") from exc
    except (ValueError, OSError, RuntimeError) as exc:
        raise EvidenceIssue("failed", relative, "unreadable_json") from exc
    require(isinstance(data, dict), relative, "expected_object")
    return data


def checked(result, name, fn, *args):
    try:
        output = fn(*args)
    except EvidenceIssue as exc:
        result["issues"].append({"check": name, "field": exc.field, "reason": str(exc)})
        result["checks"][name] = exc.status
        return None
    result["checks"][name] = "passed"
    return output


def identity(case, mode, duplicates):
    mid = value(case, "match", int)
    require(mid > 0 and not is_holdout(mid), "match", "invalid_or_reserved_match")
    hero = value(case, "hero", str)
    require(re.fullmatch(r"[a-zA-Z0-9_]+", hero), "hero", "invalid_hero")
    t = value(case, "t", int)
    key = value(case, "id", str)
    expected = ("" if mode == "lane" else mode + "-") + f"{mid}-{hero}-{t}"
    require(key == expected and key not in duplicates, "id", "misbound_or_duplicate_case")
    return key


def history(case):
    for key in (
        "action",
        "lean",
        "death_seconds",
        "support_followup",
        "walk_hit_window",
        "observed_approach",
        "match_duration",
        "last_state_second",
    ):
        require(key not in case, key, "post_decision_field_in_evidence")
    if isinstance(case.get("farm_value"), dict):
        require(
            not {"next_6s", "next_20s"} & case["farm_value"].keys(),
            "farm_value",
            "future_counts_in_evidence",
        )
    frames = value(case, "history", list)
    if not frames:
        raise EvidenceIssue("incomplete", "history", "no_frames")
    previous = None
    for frame in frames:
        require(isinstance(frame, dict), "history", "invalid_frame")
        sec = value(frame, "t", int)
        require(
            sec <= case["t"] and (previous is None or sec > previous), "history.t", "frame_time"
        )
        previous = sec
        for enemy in value(frame, "enemies", list):
            require(isinstance(enemy, dict), "history.enemies", "invalid_enemy")
            if "last_seen" not in enemy:
                raise EvidenceIssue("incomplete", "last_seen", "missing_field")
            last = enemy["last_seen"]
            require(last is None or type(last) is int and last <= sec, "last_seen", "sighting_time")
            if enemy.get("distance") is not None:
                require(last == sec, "distance", "hidden_enemy_distance")
            trail = enemy.get("trail", [])
            require(isinstance(trail, list), "trail", "invalid_trail")
            for point in trail:
                require(
                    isinstance(point, list)
                    and len(point) == 3
                    and type(point[0]) is int
                    and last is not None
                    and point[0] <= last,
                    "trail",
                    "trail_after_sighting_or_malformed",
                )
        equipment = frame.get("equipment", [])
        require(isinstance(equipment, list), "equipment", "wrong_type")
        for row in equipment:
            require(isinstance(row, dict), "equipment", "invalid_equipment")
            at = row.get("observed")
            require(at is None or type(at) is int and at <= sec, "observed", "equipment_time")
            require(row.get("items") is None or at is not None, "items", "missing_observation_time")
    if previous != case["t"]:
        raise EvidenceIssue("incomplete", "history", "no_decision_frame")


def action_label(action, mode):
    choices = {"unknown"} if mode == "jungle" else {"farm", "retreat", "unknown"}
    observed = value(action, "action", str)
    require(observed in choices, "action", "unexpected_action")
    require(value(action, "lean", str) in choices, "lean", "unexpected_lean")
    return observed


def nonnegative(row, key):
    number = value(row, key, int)
    require(number >= 0, key, "negative_value")
    return number


def match_end(outcome, t):
    duration = nonnegative(outcome, "match_duration")
    last = nonnegative(outcome, "last_state_second")
    end = min(duration, last)
    require(t <= end, "t", "decision_after_match_end")
    return {"match_duration": duration, "last_state_second": last, "effective_end": end}


def farm_windows(outcome, mode, observed_action, expected_stop):
    quantity = "neutral" if mode == "jungle" else "lane"
    hit_key = "jungle_last_hits" if mode == "jungle" else "lane_last_hits"
    total = nonnegative(outcome, hit_key)
    farm = value(outcome, "farm_value", dict)
    short = value(farm, "next_6s", dict)
    long = value(farm, "next_20s", dict)
    stop = nonnegative(long, "observed_seconds")
    require(stop <= OUTCOME_SECONDS, "next_20s.observed_seconds", "outside_window")
    require(
        expected_stop is None or expected_stop == stop,
        "next_20s.observed_seconds",
        "window_beyond_or_short_of_match_end",
    )
    require(
        stop >= ACTION_SECONDS or observed_action in (None, "unknown"),
        "action",
        "action_claim_in_partial_window",
    )
    require(
        value(short, "observed_seconds", int) == min(stop, ACTION_SECONDS),
        "next_6s.observed_seconds",
        "inconsistent_duration",
    )
    require(
        value(outcome, "complete", bool) == (stop == OUTCOME_SECONDS),
        "complete",
        "inconsistent_duration",
    )
    for kind in ("lane", "neutral"):
        n6, n20 = nonnegative(short, kind), nonnegative(long, kind)
        require(n6 <= n20, kind, "non_nested_counts")
        if stop <= ACTION_SECONDS:
            require(n6 == n20, kind, "same_window_different_counts")
    require(total == long[quantity], hit_key, "conflicting_last_hit_count")
    if observed_action == "farm":
        require(short[quantity] > 0, "action", "farm_without_last_hit")
    if observed_action == "retreat":
        require(short[quantity] == 0, "action", "retreat_with_last_hit")
    return stop


def death_window(outcome, t, stop):
    complete = value(outcome, "complete", bool)
    deaths = value(outcome, "death_seconds", list)
    if stop is not None:
        require(complete == (stop == OUTCOME_SECONDS), "complete", "window_mismatch")
    horizon = OUTCOME_SECONDS if stop is None else stop
    require(
        all(type(s) is int and t < s <= t + horizon for s in deaths),
        "death_seconds",
        "death_outside_window",
    )
    return {
        "complete": complete,
        "observed_seconds": stop if stop is not None else OUTCOME_SECONDS if complete else None,
        "death_seconds": deaths,
    }


def approach_window(approach, stop, complete):
    span = nonnegative(approach, "observed_seconds")
    require(
        span <= OUTCOME_SECONDS and (stop is None or span == stop),
        "observed_approach.observed_seconds",
        "window_mismatch",
    )
    require(
        value(approach, "window_complete", bool) == complete == (span == OUTCOME_SECONDS),
        "observed_approach.window_complete",
        "window_mismatch",
    )
    require(
        nonnegative(approach, "missing_samples") <= span + 1,
        "missing_samples",
        "excess_missing_samples",
    )
    seen, entry = approach.get("first_seen_offset"), approach.get("first_entry_offset")
    require(
        seen is None or type(seen) is int and 0 <= seen <= span,
        "first_seen_offset",
        "entry_outside_window",
    )
    require(
        entry is None or type(entry) is int and entry == seen,
        "first_entry_offset",
        "conflicting_entry_offset",
    )
    return span


def support_window(case, outcome, stop):
    if "support_opportunity" not in case:
        raise EvidenceIssue("incomplete", "support_opportunity", "missing_field")
    if case["support_opportunity"] is None:
        require(
            not any(
                k in outcome for k in ("support_followup", "walk_hit_window", "observed_approach")
            ),
            "support_followup",
            "followup_without_target",
        )
        require("arrival" not in case, "arrival", "arrival_without_target")
        return None
    signal = value(case, "support_opportunity", dict)
    target = value(signal, "hero", str)
    require(target and target != case["hero"], "support_opportunity.hero", "invalid_target")
    require(0 <= value(signal, "seconds_ago", int) < 8, "seconds_ago", "outside_signal_window")
    followup = value(outcome, "support_followup", dict)
    complete = value(followup, "complete", bool)
    require(
        complete == value(outcome, "complete", bool), "support_followup.complete", "window_mismatch"
    )
    if stop is not None:
        require(
            complete == (stop == OUTCOME_SECONDS), "support_followup.complete", "window_mismatch"
        )
    offsets = value(followup, "hit_offsets", list)
    if "observed_approach" in outcome:
        stop = approach_window(value(outcome, "observed_approach", dict), stop, complete)
    end = OUTCOME_SECONDS if stop is None else stop
    require(
        all(type(sec) is int and 0 < sec <= end for sec in offsets),
        "hit_offsets",
        "hit_outside_window",
    )
    require(offsets == sorted(set(offsets)), "hit_offsets", "unsorted_or_duplicate_hit")
    routes = value(value(case, "arrival", dict), "routes", dict)
    walk = value(routes, "walk", dict) if "walk" in routes else {}
    if "walk" in routes:
        now = value(walk, "now", list)
        delayed = value(walk, "after_six", list)
        require(
            len(now) == 2 and all(type(s) is int for s in now) and 0 <= now[0] <= now[1],
            "walk.now",
            "invalid_interval",
        )
        require(
            all(type(s) is int for s in delayed) and delayed == [s + 6 for s in now],
            "walk.after_six",
            "invalid_delay",
        )
    computed = walk_hit_window(walk, followup)
    if "walk_hit_window" in outcome:
        # Strict JSON comparison keeps booleans distinct from zero and one.
        stored = value(outcome, "walk_hit_window", dict)
        require(
            json.dumps(computed, sort_keys=True) == json.dumps(stored, sort_keys=True),
            "walk_hit_window",
            "recalculation_mismatch",
        )
    return {"target": target, "route_available": bool(walk), **computed}


def status(result):
    states = result["checks"].values()
    return next((s for s in ("failed", "incomplete") if s in states), "passed")


def audit_case(folder, case, mode, duplicates):
    result = {
        "case_id": case["id"]
        if isinstance(case, dict) and isinstance(case.get("id"), str)
        else None,
        "checks": {},
        "issues": [],
    }
    if not isinstance(case, dict):
        case = {}
        result["checks"]["case"] = "failed"
        result["issues"].append({"check": "case", "field": "cases", "reason": "expected_object"})
    key = checked(result, "identity", identity, case, mode, duplicates)
    if key:
        checked(result, "history", history, case)
        action = checked(result, "action_file", read_object, folder, f"actions/{key}.json")
        observed = (
            checked(result, "action", action_label, action, mode) if action is not None else None
        )
        outcome = checked(result, "outcome_file", read_object, folder, f"outcomes/{key}.json")
        if outcome is not None:
            expected_stop = None
            if "match_duration" in outcome or "last_state_second" in outcome:
                end = checked(result, "match_end", match_end, outcome, case["t"])
                if end is not None:
                    result["match_end"] = end
                    expected_stop = min(end["effective_end"] - case["t"], OUTCOME_SECONDS)
            else:
                result["checks"]["match_end"] = "unverified_legacy"
            stop = checked(result, "farm", farm_windows, outcome, mode, observed, expected_stop)
            if expected_stop is not None:
                stop = expected_stop
            result["outcome_window"] = checked(
                result, "deaths", death_window, outcome, case["t"], stop
            )
            result["support"] = checked(result, "support", support_window, case, outcome, stop)
            if result["support"] is None and result["checks"]["support"] == "passed":
                result["checks"]["support"] = "not_applicable"
    result["status"] = status(result)
    return result


def report_cases(folder):
    packet = read_object(folder, "cases.json")
    mode = packet.get("mode", "lane")
    require(
        mode in ("lane", "wave", "jungle") and packet.get("schema") == f"{mode}-decision-review/1",
        "schema",
        "unexpected_report_type",
    )
    cases = value(packet, "cases", list)
    if not cases:
        raise EvidenceIssue("incomplete", "cases", "no_cases")
    return mode, cases


def audit_reports(folders):
    reports = []
    counts = Counter()
    for folder in folders:
        folder = Path(folder)
        report = {"folder": str(folder), "mode": None, "cases": [], "issues": [], "checks": {}}
        loaded = checked(report, "report", report_cases, folder)
        if loaded:
            mode, cases = loaded
            report["mode"] = mode
            ids = Counter(
                c["id"] for c in cases if isinstance(c, dict) and isinstance(c.get("id"), str)
            )
            duplicates = {key for key, count in ids.items() if count > 1}
            report["cases"] = [audit_case(folder, case, mode, duplicates) for case in cases]
            counts.update(case["status"] for case in report["cases"])
            states = {case["status"] for case in report["cases"]}
            report["checks"]["cases"] = next(
                (s for s in ("failed", "incomplete") if s in states), "passed"
            )
        report["status"] = status(report)
        reports.append(report)
    return {
        "schema": "decision-report-audit/1",
        "reports": reports,
        "counts": {state: counts[state] for state in ("passed", "incomplete", "failed")},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-dir", type=Path, nargs="+", required=True)
    audit = audit_reports(parser.parse_args().review_dir)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return int(any(report["status"] == "failed" for report in audit["reports"]))


if __name__ == "__main__":
    raise SystemExit(main())
