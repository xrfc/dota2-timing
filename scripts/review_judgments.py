"""Build the organizer's bounded decision-review queue from blind evidence and portal exports."""

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from friend_review_server import case_sha256

from dota_items.data.awareness_split import is_holdout
from dota_items.storage import json_bytes, read_json

CHOICES = {
    "lane": {"farm", "retreat", "unknown"},
    "wave": {"farm", "retreat", "unknown"},
    "jungle": {"farm", "rotate", "support", "unknown"},
}
PROMPTS = {
    "disagreement": "独立首次判断在可执行动作上有分歧。请核对决定排序的事前证据。",
    "insufficient_evidence": "独立首次判断提出证据不足。请核对缺失因素，可保留证据不足。",
    "changed_evidence": "先前裁定对应的情景或独立首次意见已更新。请复核当前依据。",
    "independent_sample": "请在揭示分析前判断本组的代表片段。",
    "fresh_reviewer": "本组候选已有评审或预览记录。请由未看过该段分析的评审人独立判断。",
}
REVIEW_GROUP_LIMIT = 5


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def scenario(case):
    """Match scenarioFactors in the blind page, including absent versus explicitly null."""
    history = case.get("history") or []
    frame = history[-1] if history else {}
    ally = frame.get("ally")
    distance = ally[0] if ally else None
    ally_kind = "unlocated" if "ally" in frame and ally is None else "unknown"
    if finite(distance):
        ally_kind = "near" if distance <= 1000 else "far" if distance >= 1500 else "middle"
    threat = "unknown"
    if enemies := frame.get("enemies"):
        alive = [enemy for enemy in enemies if not enemy.get("dead")]
        near = any(finite(e.get("distance")) and e["distance"] <= 1600 for e in alive)
        missing = sum(
            ("last_seen" in e and e["last_seen"] is None)
            or (
                finite(e.get("last_seen"))
                and finite(frame.get("t"))
                and frame["t"] - e["last_seen"] >= 10
            )
            for e in alive
        )
        threat = "near" if near else "missing" if missing >= 2 else "other"
    support = "unknown"
    if "support_opportunity" in case:
        support = "none" if case["support_opportunity"] is None else "signal"
    saves = case.get("ready_names")
    save = ("detected" if saves else "none") if isinstance(saves, list) else "unknown"
    return ally_kind, threat, support, save


def selected_groups(cases):
    groups = defaultdict(list)
    for case in cases:
        groups[scenario(case)].append(case["id"])
    remaining = sorted(groups, key=lambda key: -len(groups[key]))
    covered = set()
    for _ in range(min(REVIEW_GROUP_LIMIT, len(remaining))):
        key = max(remaining, key=lambda factors: len(set(enumerate(factors)) - covered))
        remaining.remove(key)
        covered.update(enumerate(key))
        yield groups[key]


def case_id(mode, case):
    if not isinstance(case, dict):
        raise ValueError("expected a case object")
    mid, hero, t = case.get("match"), case.get("hero"), case.get("t")
    if type(mid) is not int or mid <= 0 or is_holdout(mid):
        raise ValueError("invalid or reserved match")
    if type(t) is not int or not isinstance(hero, str) or not re.fullmatch("[a-zA-Z0-9_]+", hero):
        raise ValueError("invalid decision time or hero")
    expected = ("" if mode == "lane" else mode + "-") + f"{mid}-{hero}-{t}"
    if case.get("id") != expected:
        raise ValueError("unexpected case identity")
    return expected


def read_reports(folders, filtered):
    by_mode = {}
    versions = {}
    seen = set()
    duplicates = set()
    invalid = 0
    for folder in folders:
        packet = read_json(Path(folder) / "cases.json")
        if not isinstance(packet, dict):
            raise ValueError(f"{folder}: expected a decision report")
        mode = packet.get("mode", "lane")
        if (
            not isinstance(mode, str)
            or mode not in CHOICES
            or packet.get("schema") != f"{mode}-decision-review/1"
        ):
            raise ValueError(f"{folder}: unknown report schema")
        if mode in by_mode:
            raise ValueError(f"provide only one active report for /{mode}/")
        if not isinstance(packet.get("cases"), list):
            raise ValueError(f"{folder}: expected a case list")
        by_mode[mode] = []
        for case in packet["cases"]:
            try:
                key = case_id(mode, case)
                if key in seen:
                    duplicates.add(key)
                    raise ValueError("duplicate case identity")
                seen.add(key)
                versions[key] = case_sha256(case)
                scenario(case)  # malformed frames cannot form a blind selection group
            except (ValueError, TypeError, AttributeError, IndexError, KeyError, OverflowError):
                if not filtered:
                    raise ValueError(f"{folder}: invalid case or duplicated identity") from None
                invalid += 1
                continue
            by_mode[mode].append(case)
    for mode, cases in by_mode.items():
        by_mode[mode] = [case for case in cases if case["id"] not in duplicates]
        invalid += len(cases) - len(by_mode[mode])
    return by_mode, versions, invalid


def collect_reviews(reviews, modes, versions):
    votes = defaultdict(dict)
    exposed = set()
    seen = set()
    counts = Counter()
    if not isinstance(reviews, (list, tuple)):
        raise ValueError("expected an exported review array")
    for row in reviews:
        if not isinstance(row, dict):
            raise ValueError("expected records from friend_review_server.py export")
        key, reviewer = row.get("case_id"), row.get("reviewer")
        if not isinstance(key, str) or not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("review must identify a case and reviewer")
        if key not in modes:
            counts["reviews_outside_reports"] += 1
            continue
        fingerprint = row.get("case_sha256")
        if fingerprint != versions[key]:
            counts["unversioned_reviews" if fingerprint is None else "other_version_reviews"] += 1
            exposed.add(key)
            continue
        identity = (key, reviewer)
        if identity in seen:
            raise ValueError(f"{key}: duplicate reviewer record")
        seen.add(identity)
        flag = row.get("previewed")
        if type(flag) not in (bool, int) or flag not in (0, 1):
            raise ValueError(f"{key}: invalid preview flag")
        first, choice = row.get("first"), row.get("choice")
        options = (*CHOICES[modes[key]], None)
        if first not in options or choice not in options or (first is not None and choice is None):
            raise ValueError(f"{key}: invalid review choices")
        if flag:
            exposed.add(key)
            counts["previewed_records"] += 1
        elif first:
            votes[key][reviewer] = first
            counts["independent_firsts"] += 1
        else:
            counts["records_without_first"] += 1
        if first and choice != first:
            counts["revised_choices"] += 1
    return votes, exposed, counts


def read_adjudications(data, modes):
    if data is None:
        return {}
    if not isinstance(data, dict) or data.get("schema") != "review-adjudications/1":
        raise ValueError("unsupported adjudication file")
    rows = data.get("decisions")
    if not isinstance(rows, list):
        raise ValueError("expected adjudication decisions")
    decisions = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("expected an adjudication record")
        key, decision = row.get("case_id"), row.get("decision")
        if not isinstance(key, str):
            raise ValueError("invalid adjudication identity")
        if key not in modes or decision is None:
            continue
        digest = row.get("evidence_sha256")
        if (
            not isinstance(decision, str)
            or decision not in CHOICES[modes[key]]
            or not isinstance(row.get("rationale", ""), str)
        ):
            raise ValueError(f"{key}: invalid adjudication")
        if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest):
            raise ValueError(f"{key}: expected an evidence fingerprint")
        if key in decisions:
            raise ValueError(f"{key}: duplicated adjudication")
        decisions[key] = digest
    return decisions


def queue_item(key, mode, reason):
    return dict(
        case_id=key, mode=mode, url=f"/{mode}/#{key}", reason=reason, prompt=PROMPTS[reason]
    )


def build_queue(folders, reviews=(), limit=5, eligible_ids=None, adjudications=None):
    """Pool submitted independent firsts per case; never infer an opinion for another case."""
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    by_mode, versions, invalid = read_reports(folders, filtered=eligible_ids is not None)
    modes = {case["id"]: mode for mode, cases in by_mode.items() for case in cases}
    eligible = set(modes) if eligible_ids is None else set(eligible_ids).intersection(modes)
    votes, exposed, counts = collect_reviews(reviews, modes, versions)
    decisions = read_adjudications(adjudications, modes)
    tasks = []
    groups_covered = blocked_groups = group_count = adjudicated = stale = 0
    for mode, cases in by_mode.items():
        needs_current_first = set()
        for case in cases:
            key = case["id"]
            if key not in eligible:
                continue
            firsts = votes.get(key, {})
            choices = set(firsts.values())
            if len(choices - {"unknown"}) >= 2:
                reason = "disagreement"
            elif "unknown" in choices:
                reason = "insufficient_evidence"
            elif key in decisions:
                if not firsts:
                    stale += 1
                    needs_current_first.add(key)
                    tasks.append((1, 0, queue_item(key, mode, "fresh_reviewer")))
                    continue
                reason = "changed_evidence"
            else:
                continue
            fingerprint = hashlib.sha256(
                json_bytes([versions[key], sorted(firsts.items())])
            ).hexdigest()
            if decisions.get(key) == fingerprint:
                adjudicated += 1
                continue
            if key in decisions:
                stale += 1
            item = queue_item(key, mode, reason)
            item["evidence_sha256"] = fingerprint
            tasks.append((0 if reason == "disagreement" else 1, 0, item))
        for rank, group in enumerate(selected_groups(cases)):
            group_count += 1
            candidates = [key for key in group if key in eligible]
            if not candidates:
                blocked_groups += 1
                continue
            if any(votes.get(key) for key in candidates):
                groups_covered += 1
                continue
            if needs_current_first.intersection(candidates):
                continue
            unseen = next((key for key in candidates if key not in exposed), None)
            reason = "independent_sample" if unseen else "fresh_reviewer"
            tasks.append((2, rank, queue_item(unseen or candidates[0], mode, reason)))
    tasks.sort(key=lambda task: (task[0], task[1], task[2]["mode"], task[2]["case_id"]))
    queue = [item for _, _, item in tasks[:limit]]
    return {
        "schema": "review-judgments/1",
        "counts": {
            "cases": len(modes),
            "eligible_cases": len(eligible),
            "invalid_case_records": invalid,
            **{
                k: counts[k]
                for k in (
                    "independent_firsts",
                    "previewed_records",
                    "records_without_first",
                    "revised_choices",
                    "reviews_outside_reports",
                    "unversioned_reviews",
                    "other_version_reviews",
                )
            },
            "selected_groups": group_count,
            "covered_groups": groups_covered,
            "blocked_groups": blocked_groups,
            "adjudicated_cases": adjudicated,
            "stale_adjudications": stale,
        },
        "tasks_by_reason": dict(Counter(item["reason"] for _, _, item in tasks)),
        "queue": queue,
        "deferred": len(tasks) - len(queue),
        "adjudication_template": {
            "schema": "review-adjudications/1",
            "decisions": [
                dict(
                    case_id=item["case_id"],
                    evidence_sha256=item["evidence_sha256"],
                    decision=None,
                    rationale="",
                )
                for item in queue
                if "evidence_sha256" in item
            ],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-dir", type=Path, nargs="+", required=True)
    parser.add_argument("--reviews", type=Path, help="JSON from friend_review_server.py export")
    parser.add_argument(
        "--adjudications", type=Path, help="private, completed adjudication template"
    )
    parser.add_argument(
        "--limit", type=int, default=5, help="maximum number of tasks across reports"
    )
    args = parser.parse_args()
    try:
        result = build_queue(
            args.review_dir,
            read_json(args.reviews) if args.reviews else (),
            args.limit,
            adjudications=read_json(args.adjudications) if args.adjudications else None,
        )
    except (ValueError, OSError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
