"""One bounded anonymous collection of recent matches; never train or resume automatically."""

import argparse
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

from dota_items.data.contracts import SLOTS
from dota_items.data.patch_time import OFFICIAL_PATCH_URL, classify_patch_time, load_patch_window
from dota_items.data.purchase_observation import observe_purchases
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.sources.collection_history import filter_discovery
from dota_items.sources.opendota_budget import BudgetPaused, RequestBudget
from dota_items.storage import file_hash, json_bytes

ITEMS = ["bfury", "maelstrom", "manta", "black_king_bar", "skadi"]


def load(path):
    return parse_source_json(read_source_bytes(path))


def save(path, value):
    with path.open("xb") as stream:
        stream.write(json_bytes(value))


def history(data):
    ids, hashes = set(), {}
    for path in sorted(data.rglob("*.json")):
        stem = path.name.split(".")[0]
        if stem.isdigit():
            ids.add(int(stem))
        elif path.name == "plan.json":
            value = load(path)
            for mid in value.get("match_ids", []):
                if type(mid) is not int or mid <= 0:
                    raise ValueError("Invalid historical plan ID")
                ids.add(mid)
            hashes[str(path)] = file_hash(path)
        elif stem.startswith("failure-") and stem[8:].isdigit():
            ids.add(int(stem[8:]))
    return sorted(ids), hashes


def inspect_match(raw, expected, window):
    if (
        not isinstance(raw, dict)
        or type(raw.get("match_id")) is not int
        or raw["match_id"] != expected
    ):
        raise ValueError("Requested identity mismatch")
    reasons = []
    duration = raw.get("duration")
    if type(duration) is not int or not 1800 <= duration <= 86400:
        reasons.append("duration_not_covered")
    timing = classify_patch_time(raw.get("start_time"), duration, window)
    if timing != "time_consistent":
        reasons.append(timing)
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
    target = [p for p in players if p["hero_id"] == 8]
    if len(target) != 1:
        raise ValueError("Expected one Juggernaut")
    if raw.get("lobby_type") != 7 or raw.get("game_mode") != 22:
        reasons.append("detail_scope_mismatch")
    observed = observe_purchases(target[0], ITEMS)
    if observed["log_status"] != "present":
        reasons.append("purchase_log_" + observed["log_status"])
    return {
        "match_id": expected,
        "reasons": reasons,
        "screened": not reasons,
        "patch_time": timing,
        "numeric_patch": raw.get("patch"),
        "log_status": observed["log_status"],
        "observations": observed["items"],
        "training_allowed": False,
    }


class RunBudget:
    def __init__(self, persistent, output):
        self.persistent, self.output = persistent, output
        self.counts = {"all": 0, "discovery": 0, "detail": 0}

    def before(self, request):
        kind = "discovery" if request.url.path == "/api/explorer" else "detail"
        if request.url.host != "api.opendota.com" or not (
            request.url.path == "/api/explorer" or request.url.path.startswith("/api/matches/")
        ):
            raise ValueError("Unexpected API endpoint")
        if self.counts["all"] >= 220 or self.counts[kind] >= {"discovery": 5, "detail": 200}[kind]:
            raise BudgetPaused("Per-run request cap reached")
        self.persistent.before(request)
        self.counts["all"] += 1
        self.counts[kind] += 1
        temp = self.output / "request-counts.tmp"
        temp.write_bytes(json_bytes(self.counts))
        temp.replace(self.output / "request-counts.json")


def collect(output, data, budget_path, *, transport=None, route="direct"):
    if os.environ.get("OPENDOTA_API_KEY"):
        raise ValueError("Anonymous only; no paid key allowed")
    if output.exists() or output.is_symlink():
        raise ValueError("New output directory required")
    if route not in ("direct", "proxy"):
        raise ValueError("Unknown route")
    if route == "proxy" and not budget_path.is_file():
        raise ValueError("Existing proxy budget required; never reset usage")
    proxy = "http://127.0.0.1:7890" if route == "proxy" else None
    excluded, evidence = history(data)
    output.mkdir(parents=False, exist_ok=False)
    save(output / "exclusions.json", {"match_ids": excluded, "plan_sha256": evidence})
    budget = RunBudget(RequestBudget(budget_path), output)
    results, selected, state = [], [], "failed"
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
        lower = max(window["release_timestamp"] + 3600, int(retrieved.timestamp()) - 72 * 3600)
        upper = window["upper_exclusive"] - 3600
        if lower >= upper:
            raise ValueError("No recent interval outside release boundary")
        save(
            output / "protocol.json",
            {
                "schema_version": "latest-purchase-collection/1",
                "window": window,
                "start_time_min": lower,
                "start_time_max_exclusive": upper,
                "min_average_rank_hint": 70,
                "game_mode": 22,
                "lobby_type": 7,
                "hero_id": 8,
                "max_details": 200,
                "max_discovery": 5,
                "max_requests": 220,
                "route": route,
                "retries": 0,
                "training_allowed": False,
                "formal_split_assigned": False,
                "source_log_window": [0, 1800],
                "collector_sha256": file_hash(Path(__file__)),
                "exclusions_sha256": file_hash(output / "exclusions.json"),
            },
        )
        cursor = 2**63 - 1
        seen = set(excluded)
        with httpx.Client(
            trust_env=False,
            timeout=40,
            follow_redirects=False,
            transport=transport,
            proxy=proxy,
            event_hooks={"request": [budget.before], "response": [budget.persistent.after]},
        ) as client:
            for page in range(5):
                sql = (
                    "SELECT match_id,start_time,duration,avg_rank_tier,"
                    "num_rank_tier,lobby_type,game_mode "
                    "FROM public_matches WHERE "
                    f"match_id>0 AND match_id<{cursor} "
                    f"AND start_time>={lower} AND start_time<{upper} "
                    "AND duration>=1800 AND (8=ANY(radiant_team) OR 8=ANY(dire_team)) "
                    "AND lobby_type=7 AND game_mode=22 AND avg_rank_tier>=70 "
                    "ORDER BY match_id DESC LIMIT 100"
                )
                response = client.get("https://api.opendota.com/api/explorer", params={"sql": sql})
                with (output / f"discovery-{page}.json").open("xb") as stream:
                    stream.write(response.content)
                response.raise_for_status()
                payload = response.json()
                if payload.get("err") or not isinstance(payload.get("rows"), list):
                    raise ValueError("Discovery failed")
                found = filter_discovery(payload["rows"], seen, 0, cursor)
                for row in payload["rows"]:
                    if (
                        type(row.get("start_time")) is not int
                        or not lower <= row["start_time"] < upper
                    ):
                        raise ValueError("Discovery time differs from frozen query")
                save(
                    output / f"discovery-{page}-receipt.json",
                    {
                        "sql": sql,
                        "sha256": file_hash(output / f"discovery-{page}.json"),
                        "fetched_at": datetime.now(UTC).isoformat(),
                    },
                )
                selected.extend(r["match_id"] for r in found[: 200 - len(selected)])
                seen.update(selected)
                if len(selected) == 200 or not payload["rows"]:
                    break
                cursor = min(r["match_id"] for r in payload["rows"])
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
                before = budget.counts["detail"]
                try:
                    response = client.get(f"https://api.opendota.com/api/matches/{mid}")
                except (BudgetPaused, httpx.HTTPError) as error:
                    results.append(
                        {
                            "match_id": mid,
                            "screened": False,
                            "request_reserved": budget.counts["detail"] > before,
                            "error_type": type(error).__name__,
                        }
                    )
                    raise
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
                        {
                            "match_id": mid,
                            "screened": False,
                            "request_reserved": True,
                            "status": response.status_code,
                            "error_type": "HTTPStatusError",
                        }
                    )
                    raise ValueError("Service failure; stop without retry")
                try:
                    response.raise_for_status()
                    result = inspect_match(response.json(), mid, window)
                except (ValueError, httpx.HTTPStatusError) as error:
                    results.append(
                        {"match_id": mid, "screened": False, "error_type": type(error).__name__}
                    )
                    # Identity/structure conflicts require explicit review, not silent replacement.
                    if isinstance(error, ValueError):
                        raise
                else:
                    results.append(result)
        state = "completed"
    except BudgetPaused:
        state = "paused_budget"
    finally:
        save(
            output / "results.json",
            {
                "state": state,
                "selected": len(selected),
                "attempted_results": len(results),
                "screened": sum(r["screened"] for r in results),
                "requests": budget.counts,
                "rows": results,
                "training_allowed": False,
            },
        )
        save(
            output / "summary.json",
            {
                "state": state,
                "selected": len(selected),
                "attempted_results": len(results),
                "screened": sum(r["screened"] for r in results),
                "requests": budget.counts,
                "reason_counts": dict(
                    Counter(reason for r in results for reason in r.get("reasons", []))
                ),
                "training_allowed": False,
            },
        )
    return state


def main():
    import fcntl

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--route", choices=("direct", "proxy"), default="direct")
    args = parser.parse_args()
    runtime = Path("reports/collection-runtime")
    runtime.mkdir(exist_ok=True)
    with (runtime / "request-budget.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget_path = (
            Path("data/purchase-proxy-trial-2026-10-15/request-budget.json")
            if args.route == "proxy"
            else runtime / "request-budget.json"
        )
        state = collect(args.output, Path("data"), budget_path, route=args.route)
    print(state)
    return 0 if state == "completed" else 75


if __name__ == "__main__":
    raise SystemExit(main())
