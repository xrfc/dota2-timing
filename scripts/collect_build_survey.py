"""Bounded anonymous collection of ranked matches for hero build statistics (R08/R15).

Purpose (U108-U111): count which completed items each hero usually buys. Matches are
discovered without any hero filter; ``--hero`` adds a targeted top-up for rare heroes
and is recorded in the protocol. Only matches OpenDota has already parsed carry a
purchase log; this script never requests parses, never uses a paid key, never
trains anything and never resumes on its own.
"""

import argparse
import fcntl
import os
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

from dota_items.data.contracts import SLOTS
from dota_items.data.patch_time import OFFICIAL_PATCH_URL, classify_patch_time, load_patch_window
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.sources.opendota_budget import BudgetPaused, RequestBudget
from dota_items.storage import file_hash, json_bytes

PURPOSE = "mechanics-r08-r15-build-statistics"
MIN_RANK = 60  # 超凡 (Ancient) = rank_tier 6x; avg_rank_tier is the lobby average.
MIN_DURATION = 900  # U111: exclude games under 15 minutes.
LOBBY, MODE = 7, 22  # ranked matchmaking, all pick
MAX_DETAILS = 1700  # per run, below the local 1,900/day rolling budget
PAGE = 100
# Explorer times out on unbounded scans, so each page covers a bounded match_id span,
# as the earlier collectors did. About 52,000 ids/hour (M1 snapshot, 2026-10); the
# start-time filter in SQL keeps results correct when this estimate is off.
ID_SPAN = 1_000_000
ID_RATE_PER_HOUR = 52_000
ANCHOR_SQL = "SELECT max(match_id) AS max_id FROM public_matches"
PROXY = "http://127.0.0.1:7890"
BUDGETS = {
    "proxy": Path("data/purchase-proxy-trial-2026-10-15/request-budget.json"),
    "direct": Path("reports/collection-runtime/request-budget.json"),
}


def load(path):
    return parse_source_json(read_source_bytes(path))


def save(path, value):
    with path.open("xb") as stream:
        stream.write(json_bytes(value))


class RunBudget:
    """Per-run caps layered over the persistent rolling budget."""

    def __init__(self, persistent, max_details, max_discovery):
        self.persistent = persistent
        self.caps = {"discovery": max_discovery, "detail": max_details}
        self.counts = {"all": 0, "discovery": 0, "detail": 0}

    def before(self, request):
        if request.url.host != "api.opendota.com":
            raise ValueError("Unexpected host")
        if request.url.path == "/api/explorer":
            kind = "discovery"
        elif request.url.path.startswith("/api/matches/"):
            kind = "detail"
        else:
            raise ValueError("Unexpected API endpoint")
        if request.method != "GET":
            raise ValueError("Read-only collector")
        if self.counts[kind] >= self.caps[kind]:
            raise BudgetPaused("Per-run request cap reached")
        self.persistent.before(request)
        self.counts["all"] += 1
        self.counts[kind] += 1


def discovery_sql(lower, upper, cursor, heroes):
    """One bounded page: ids in (cursor - ID_SPAN, cursor), newest first."""
    hero_clause = ""
    if heroes:
        parts = [f"{h}=ANY(radiant_team) OR {h}=ANY(dire_team)" for h in heroes]
        hero_clause = " AND (" + " OR ".join(parts) + ")"
    return (
        "SELECT match_id,start_time,duration,avg_rank_tier,num_rank_tier,lobby_type,game_mode "
        f"FROM public_matches WHERE match_id>{cursor - ID_SPAN} AND match_id<{cursor} "
        f"AND start_time>={lower} AND start_time<{upper} "
        f"AND duration>={MIN_DURATION} AND lobby_type={LOBBY} AND game_mode={MODE} "
        f"AND avg_rank_tier>={MIN_RANK}{hero_clause} "
        f"ORDER BY match_id DESC LIMIT {PAGE}"
    )


def inspect_match(raw, expected, window):
    """Screen one detail payload; identity/structure conflicts raise for review."""
    if not isinstance(raw, dict) or raw.get("match_id") != expected:
        raise ValueError("Requested identity mismatch")
    players = raw.get("players")
    if (
        not isinstance(players, list)
        or len(players) != 10
        or any(not isinstance(p, dict) for p in players)
    ):
        raise ValueError("Invalid player structure")
    slots = [p.get("player_slot") for p in players]
    heroes = [p.get("hero_id") for p in players]
    if (
        any(type(s) is not int for s in slots)
        or set(slots) != SLOTS
        or any(type(h) is not int or h <= 0 for h in heroes)
        or len(set(heroes)) != 10
    ):
        raise ValueError("Invalid player identities")
    reasons = []
    duration = raw.get("duration")
    if type(duration) is not int or not MIN_DURATION <= duration <= 86400:
        reasons.append("duration_not_covered")
    timing = classify_patch_time(raw.get("start_time"), duration, window)
    if timing != "time_consistent":
        reasons.append(timing)
    if raw.get("lobby_type") != LOBBY or raw.get("game_mode") != MODE:
        reasons.append("detail_scope_mismatch")
    logs = [p.get("purchase_log") for p in players]
    if all(log is None for log in logs):
        reasons.append("purchase_log_missing")
    elif any(not isinstance(log, list) for log in logs):
        reasons.append("purchase_log_partial")
    return {
        "match_id": expected,
        "heroes": sorted(heroes),
        "duration": duration,
        "patch_time": timing,
        "numeric_patch": raw.get("patch"),
        "reasons": reasons,
        "screened": not reasons,
    }


def summarize(state, selected, discovered, results, counts):
    screened = [r for r in results if r.get("screened")]
    ranks = Counter(int(row["avg_rank_tier"]) // 10 for row in discovered)
    return {
        "state": state,
        "purpose": PURPOSE,
        "selected": len(selected),
        "attempted_results": len(results),
        "screened": len(screened),
        "screened_rate": round(len(screened) / len(results), 4) if results else None,
        "reason_counts": dict(Counter(x for r in results for x in r.get("reasons", []))),
        "discovered_avg_rank_tier_bands": {str(k): v for k, v in sorted(ranks.items())},
        "screened_hero_games": dict(
            sorted(Counter(h for r in screened for h in r["heroes"]).items())
        ),
        "requests": counts,
        "training_allowed": False,
    }


def collect(
    output,
    budget_path,
    *,
    max_details,
    heroes=(),
    min_age_hours=24,
    transport=None,
    route="proxy",
    clock=time.time,
):
    if os.environ.get("OPENDOTA_API_KEY"):
        raise ValueError("Anonymous only; no paid key allowed")
    if output.exists() or output.is_symlink():
        raise ValueError("New output directory required")
    if not 0 < max_details <= MAX_DETAILS:
        raise ValueError(f"max_details must be 1..{MAX_DETAILS}")
    if any(type(h) is not int or h <= 0 for h in heroes):
        raise ValueError("Hero ids must be positive integers")
    # httpx routes through a proxy instead of a supplied transport, so tests never proxy.
    proxy = PROXY if route == "proxy" and transport is None else None
    output.mkdir(parents=False, exist_ok=False)
    max_discovery = max(3, (max_details + PAGE - 1) // PAGE * 3)
    budget = RunBudget(RequestBudget(budget_path), max_details, max_discovery)
    results, selected, discovered, state = [], [], [], "failed"
    try:
        with httpx.Client(
            trust_env=False, timeout=40, follow_redirects=False, transport=transport, proxy=proxy
        ) as official:
            response = official.get(OFFICIAL_PATCH_URL)
            response.raise_for_status()
            with (output / "patch-list.json").open("xb") as stream:
                stream.write(response.content)
        retrieved = datetime.now(UTC)
        save(
            output / "patch-receipt.json",
            {
                "schema_version": "patch-time-evidence/1",
                "source_url": OFFICIAL_PATCH_URL,
                "snapshot": "patch-list.json",
                "sha256": file_hash(output / "patch-list.json"),
                "retrieved_at": retrieved.isoformat(),
                "boundary_buffer_seconds": 3600,
            },
        )
        releases = load(output / "patch-list.json")["patches"]
        patch = max(releases, key=lambda r: r["patch_timestamp"])["patch_number"]
        window = load_patch_window(output / "patch-receipt.json", patch)
        lower = window["release_timestamp"] + 3600
        upper = min(window["upper_exclusive"] - 3600, int(clock()) - min_age_hours * 3600)
        if lower >= upper:
            raise ValueError("No interval inside the current patch")
        save(
            output / "protocol.json",
            {
                "schema_version": "build-survey-collection/1",
                "purpose": PURPOSE,
                "decisions": "U108-U111",
                "patch": patch,
                "window": window,
                "start_time_min": lower,
                "start_time_max_exclusive": upper,
                "min_age_hours": min_age_hours,
                "min_avg_rank_tier": MIN_RANK,
                "min_duration_s": MIN_DURATION,
                "lobby_type": LOBBY,
                "game_mode": MODE,
                "hero_filter": sorted(heroes),
                "order": "match_id DESC (newest first, no hero filter unless hero_filter)",
                "max_details": max_details,
                "max_discovery": max_discovery,
                "route": route,
                "parse_requests": False,
                "training_allowed": False,
                "collector_sha256": file_hash(Path(__file__)),
            },
        )
        seen, empty = set(), 0
        with httpx.Client(
            trust_env=False,
            timeout=40,
            follow_redirects=False,
            transport=transport,
            proxy=proxy,
            event_hooks={"request": [budget.before], "response": [budget.persistent.after]},
        ) as client:
            response = client.get(
                "https://api.opendota.com/api/explorer", params={"sql": ANCHOR_SQL}
            )
            with (output / "discovery-anchor.json").open("xb") as stream:
                stream.write(response.content)
            response.raise_for_status()
            anchor = response.json().get("rows") or [{}]
            max_id = anchor[0].get("max_id")
            if type(max_id) is not int or max_id <= 0:
                raise ValueError("Anchor query failed")
            cursor = max_id - ID_RATE_PER_HOUR * min_age_hours
            save(
                output / "discovery-anchor-receipt.json",
                {
                    "sql": ANCHOR_SQL,
                    "max_id": max_id,
                    "initial_cursor": cursor,
                    "sha256": file_hash(output / "discovery-anchor.json"),
                    "fetched_at": datetime.now(UTC).isoformat(),
                },
            )
            for page in range(max_discovery - 1):
                sql = discovery_sql(lower, upper, cursor, sorted(heroes))
                response = client.get("https://api.opendota.com/api/explorer", params={"sql": sql})
                with (output / f"discovery-{page}.json").open("xb") as stream:
                    stream.write(response.content)
                response.raise_for_status()
                payload = response.json()
                rows = payload.get("rows") if isinstance(payload, dict) else None
                if payload.get("err") or not isinstance(rows, list):
                    raise ValueError("Discovery failed")
                save(
                    output / f"discovery-{page}-receipt.json",
                    {
                        "sql": sql,
                        "sha256": file_hash(output / f"discovery-{page}.json"),
                        "fetched_at": datetime.now(UTC).isoformat(),
                    },
                )
                for row in rows:
                    mid = row.get("match_id")
                    if type(mid) is not int or not cursor - ID_SPAN < mid < cursor:
                        raise ValueError("Discovery row outside the frozen cursor")
                    if type(row.get("start_time")) is not int or not (
                        lower <= row["start_time"] < upper
                    ):
                        raise ValueError("Discovery time differs from frozen query")
                    if mid not in seen and len(selected) < max_details:
                        seen.add(mid)
                        selected.append(mid)
                        discovered.append(row)
                if len(selected) >= max_details:
                    break
                empty = 0 if rows else empty + 1
                if empty == 3:
                    break
                cursor = min(r["match_id"] for r in rows) if rows else cursor - ID_SPAN + 1
            save(
                output / "plan.json",
                {
                    "match_ids": selected,
                    "protocol_sha256": file_hash(output / "protocol.json"),
                    "training_allowed": False,
                },
            )
            cache = output / "matches"
            cache.mkdir()
            for mid in selected:
                response = client.get(f"https://api.opendota.com/api/matches/{mid}")
                with (cache / f"{mid}.json").open("xb") as stream:
                    stream.write(response.content)
                save(
                    cache / f"{mid}.manifest.json",
                    {
                        "match_id": mid,
                        "source": "opendota",
                        "status": response.status_code,
                        "fetched_at": datetime.now(UTC).isoformat(),
                        "sha256": file_hash(cache / f"{mid}.json"),
                    },
                )
                if response.status_code >= 500 or response.status_code in (401, 403):
                    results.append(
                        {"match_id": mid, "screened": False, "status": response.status_code}
                    )
                    raise ValueError("Service failure; stop without retry")
                if response.status_code != 200:
                    results.append(
                        {
                            "match_id": mid,
                            "screened": False,
                            "status": response.status_code,
                            "reasons": [f"http_{response.status_code}"],
                        }
                    )
                    continue
                results.append(inspect_match(response.json(), mid, window))
        state = "completed"
    except BudgetPaused:
        state = "paused_budget"
    finally:
        save(output / "results.json", {"state": state, "rows": results, "training_allowed": False})
        save(
            output / "summary.json",
            summarize(state, selected, discovered, results, budget.counts),
        )
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-details", type=int, default=100)
    parser.add_argument("--hero", type=int, action="append", default=[])
    parser.add_argument("--min-age-hours", type=int, default=24)
    parser.add_argument("--route", choices=("direct", "proxy"), default="proxy")
    args = parser.parse_args()
    budget_path = BUDGETS[args.route]
    if args.route == "proxy" and not budget_path.is_file():
        raise ValueError("Existing proxy budget required; never reset usage")
    runtime = Path("reports/collection-runtime")
    runtime.mkdir(exist_ok=True)
    with (runtime / "request-budget.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = collect(
            args.output,
            budget_path,
            max_details=args.max_details,
            heroes=tuple(args.hero),
            min_age_hours=args.min_age_hours,
            route=args.route,
        )
    print(state)
    return 0 if state == "completed" else 75


if __name__ == "__main__":
    raise SystemExit(main())
