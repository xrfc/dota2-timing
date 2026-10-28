"""Continue a frozen recent window, wait minute cooldowns, stop at daily limits."""

import argparse
import fcntl
import time
from pathlib import Path

import httpx
from collect_purchase_latest import history, inspect_match, load, save

from dota_items.data.patch_time import load_patch_window
from dota_items.sources.collection_history import filter_discovery
from dota_items.sources.opendota_budget import BudgetPaused, RequestBudget
from dota_items.storage import file_hash, json_bytes


class DailyFinished(BudgetPaused):
    """This invocation must end, not resume tomorrow."""


class MinuteWaitBudget(RequestBudget):
    def __init__(self, path, *, notify=lambda **k: None, clock=time.time, sleep=time.sleep):
        if not path.is_file():
            raise ValueError("Existing route budget required")
        super().__init__(path, clock=clock, sleep=sleep)
        self.started = clock()
        self.allowance = max(0, 1900 - len(self.recent()))
        self.sent = 0
        self.notify = notify

    def recent(self):
        return [t for t in self.state["requests"] if t > self.clock() - 86400]

    def before(self, request):
        if request.url.host != "api.opendota.com":
            raise ValueError("Unexpected API host")
        while True:
            remaining = self.state.get("remaining", {})
            if (
                self.sent >= self.allowance
                or len(self.recent()) >= 1900
                or self.clock() - self.started >= 86400
                or self.state.get("last_status") == 429
                or remaining.get("day", 100) <= 20
            ):
                raise DailyFinished("Daily protection reached; no automatic next-day resume")
            delay = self.state.get("blocked_until", 0) - self.clock()
            if delay <= 0:
                break
            if delay > 66 or remaining.get("minute", 100) > 5:
                raise DailyFinished("Non-minute cooldown; stop")
            self.notify(state="waiting_minute", resume_at=self.state["blocked_until"])
            self.sleep(min(30, delay))
        super().before(request)
        self.sent += 1
        self.notify(state="collecting", api_requests_this_run=self.sent)


def resume_daily(previous, protocol):
    """Recover an interrupted continuation without refunding reserved requests."""
    parent = Path(protocol["previous"])
    if (
        protocol.get("route") != "proxy"
        or protocol.get("training_allowed") is not False
        or file_hash(parent / "protocol.json") != protocol["previous_protocol_sha256"]
        or load(previous / "summary.json")["state"] != "failed"
    ):
        raise ValueError("Invalid interrupted continuation")
    parent_protocol, _, _ = resume_plan(parent)
    for key in ("window", "start_time_min", "start_time_max_exclusive"):
        if protocol[key] != parent_protocol[key]:
            raise ValueError("Continuation window mismatch")
    for name, sha in protocol["historical_plan_sha256"].items():
        if file_hash(Path(name)) != sha:
            raise ValueError("Historical plan hash mismatch")
    cursor = protocol["initial_cursor"]
    ids = []
    batches = sorted(previous.glob("batch-*"))
    for index, batch in enumerate(batches):
        if batch.name != f"batch-{index:04d}":
            raise ValueError("Noncontiguous continuation batches")
        discovery = batch / "discovery.json"
        expected = protocol["initial_remaining_plan"]
        if index:
            if not discovery.exists():
                if index != len(batches) - 1 or (batch / "plan.json").exists():
                    raise ValueError("Missing discovery")
                break  # Network failure before discovery was saved; keep prior cursor.
            receipt = load(discovery)
            import json

            payload = json.loads(receipt["body"])
            if receipt["status"] != 200 or payload.get("err"):
                raise ValueError("Failed discovery needs manual inspection")
            found = filter_discovery(
                payload["rows"], set(protocol["historical_exclusions"]) | set(ids), 0, cursor
            )
            expected = [r["match_id"] for r in found]
            if any(
                not protocol["start_time_min"]
                <= r["start_time"]
                < protocol["start_time_max_exclusive"]
                for r in payload["rows"]
            ):
                raise ValueError("Discovery outside frozen window")
            if payload["rows"]:
                cursor = min(r["match_id"] for r in payload["rows"])
        plan = batch / "plan.json"
        if plan.exists() and load(plan)["match_ids"] != expected:
            raise ValueError("Continuation plan mismatch")
        ids.extend(expected)
    if len(ids) != len(set(ids)) or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError("Invalid continuation IDs")
    saved = set()
    for manifest in (previous / "matches").glob("*.manifest.json"):
        receipt = load(manifest)
        mid = receipt["match_id"]
        if mid not in ids or file_hash(previous / "matches" / f"{mid}.json") != receipt["sha256"]:
            raise ValueError("Continuation cache hash mismatch")
        if receipt["status"] != 200:
            raise ValueError("Failed detail needs manual inspection")
        saved.add(mid)
    summary = load(previous / "summary.json")
    if summary["saved"] != len(saved):
        raise ValueError("Continuation saved count mismatch")
    protocol = dict(protocol)
    protocol["patch_receipt_path"] = parent_protocol.get(
        "patch_receipt_path", str(parent / "patch-receipt.json")
    )
    # A reserved request with no saved response is retried; budget remains untouched.
    return protocol, [i for i in ids if i not in saved], cursor


def resume_plan(previous):
    """Verify the previous receipt chain and return only unsent planned matches."""
    protocol = load(previous / "protocol.json")
    if protocol.get("schema_version") == "daily-purchase-continuation/1":
        return resume_daily(previous, protocol)
    plan = load(previous / "plan.json")
    if (
        protocol["route"] != "proxy"
        or protocol["training_allowed"] is not False
        or plan["protocol_sha256"] != file_hash(previous / "protocol.json")
        or file_hash(previous / "exclusions.json") != protocol["exclusions_sha256"]
    ):
        raise ValueError("Previous protocol binding mismatch")
    ids = plan["match_ids"]
    if not ids or len(ids) != len(set(ids)) or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError("Invalid previous plan")
    attempted = set()
    for manifest in (previous / "matches").glob("*.manifest.json"):
        receipt = load(manifest)
        mid = receipt["match_id"]
        if mid not in ids or file_hash(previous / "matches" / f"{mid}.json") != receipt["sha256"]:
            raise ValueError("Previous cache identity/hash mismatch")
        attempted.add(mid)
    for row in load(previous / "results.json")["rows"]:
        if row.get("request_reserved") is True:
            attempted.add(row["match_id"])
    return protocol, [mid for mid in ids if mid not in attempted], min(ids)


def run(previous, output):
    import os

    if os.environ.get("OPENDOTA_API_KEY"):
        raise ValueError("Anonymous only")
    if output.exists() or output.is_symlink():
        raise ValueError("New output required")
    protocol, pending, cursor = resume_plan(previous)
    window = load_patch_window(
        Path(protocol.get("patch_receipt_path", previous / "patch-receipt.json")),
        protocol["window"]["patch"],
    )
    if window != protocol["window"]:
        raise ValueError("Previous patch window changed")
    excluded, history_hashes = history(Path("data"))
    seen = set(excluded)
    output.mkdir(parents=False)
    cache = output / "matches"
    cache.mkdir()
    rows = []
    counts = {"discovery": 0, "detail": 0}
    state = {"state": "starting", "saved": 0, "screened": 0, "training_allowed": False}

    def record(**changes):
        state.update(changes, updated_at=time.time(), pid=os.getpid())
        temp = output / "status.tmp"
        temp.write_bytes(json_bytes(state))
        temp.replace(output / "status.json")

    budget = MinuteWaitBudget(
        Path("data/purchase-proxy-trial-2026-10-15/request-budget.json"), notify=record
    )
    save(
        output / "protocol.json",
        {
            "schema_version": "daily-purchase-continuation/1",
            "previous": str(previous),
            "previous_protocol_sha256": file_hash(previous / "protocol.json"),
            "window": window,
            "start_time_min": protocol["start_time_min"],
            "start_time_max_exclusive": protocol["start_time_max_exclusive"],
            "initial_remaining_plan": pending,
            "initial_cursor": cursor,
            "historical_exclusions": excluded,
            "historical_plan_sha256": history_hashes,
            "max_api_requests_this_run": budget.allowance,
            "rolling_daily_cap": 1900,
            "minute_wait": True,
            "next_day_resume": False,
            "route": "proxy",
            "training_allowed": False,
            "collector_sha256": file_hash(Path(__file__)),
        },
    )
    page = 0
    terminal = "failed"
    try:
        with httpx.Client(
            proxy="http://127.0.0.1:7890",
            trust_env=False,
            timeout=40,
            follow_redirects=False,
            event_hooks={"request": [budget.before], "response": [budget.after]},
        ) as client:
            while True:
                # Complete each frozen page before discovering another page.
                batch = output / f"batch-{page:04d}"
                batch.mkdir()
                if page:
                    lower, upper = protocol["start_time_min"], protocol["start_time_max_exclusive"]
                    sql = (
                        "SELECT match_id,start_time,duration,avg_rank_tier,num_rank_tier,"
                        "lobby_type,game_mode FROM public_matches WHERE "
                        f"match_id>0 AND match_id<{cursor} AND start_time>={lower} "
                        f"AND start_time<{upper} AND duration>=1800 "
                        "AND (8=ANY(radiant_team) OR 8=ANY(dire_team)) "
                        "AND lobby_type=7 AND game_mode=22 AND avg_rank_tier>=70 "
                        "ORDER BY match_id DESC LIMIT 100"
                    )
                    response = client.get(
                        "https://api.opendota.com/api/explorer", params={"sql": sql}
                    )
                    counts["discovery"] += 1
                    save(
                        batch / "discovery.json",
                        {"sql": sql, "status": response.status_code, "body": response.text},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("err") or not isinstance(payload.get("rows"), list):
                        raise ValueError("Invalid discovery response")
                    found = filter_discovery(payload["rows"], seen, 0, cursor)
                    if any(
                        type(r.get("start_time")) is not int or not lower <= r["start_time"] < upper
                        for r in payload["rows"]
                    ):
                        raise ValueError("Discovery outside frozen window")
                    if not payload["rows"]:
                        terminal = "window_exhausted"
                        break
                    cursor = min(r["match_id"] for r in payload["rows"])
                    pending = [r["match_id"] for r in found]
                save(batch / "plan.json", {"match_ids": pending, "training_allowed": False})
                seen.update(pending)
                for mid in pending:
                    before = budget.sent
                    try:
                        response = client.get(f"https://api.opendota.com/api/matches/{mid}")
                    except (BudgetPaused, httpx.HTTPError):
                        rows.append(
                            {
                                "match_id": mid,
                                "screened": False,
                                "request_reserved": budget.sent > before,
                                "error": "request_stopped",
                            }
                        )
                        raise
                    counts["detail"] += 1
                    rawpath = cache / f"{mid}.json"
                    with rawpath.open("xb") as stream:
                        stream.write(response.content)
                    save(
                        cache / f"{mid}.manifest.json",
                        {
                            "match_id": mid,
                            "status": response.status_code,
                            "sha256": file_hash(rawpath),
                            "fetched_at": time.time(),
                        },
                    )
                    response.raise_for_status()
                    raw = response.json()
                    if (
                        not protocol["start_time_min"]
                        <= raw["start_time"]
                        < protocol["start_time_max_exclusive"]
                    ):
                        raise ValueError("Detail outside frozen window")
                    result = inspect_match(raw, mid, window)
                    rows.append(result)
                    with (output / "results.jsonl").open("ab") as stream:
                        stream.write(json_bytes(result).replace(b"\n", b" ") + b"\n")
                    record(saved=counts["detail"], screened=sum(r["screened"] for r in rows))
                page += 1
    except BudgetPaused as error:
        terminal = "stopped_daily_limit"
        record(stop_reason=str(error))
    except Exception as error:
        record(error_type=type(error).__name__, error=str(error))
        raise
    finally:
        save(output / "results.json", {"rows": rows, "training_allowed": False})
        save(
            output / "summary.json",
            {
                "state": terminal,
                "api_requests_this_run": budget.sent,
                "responses": counts,
                "saved": counts["detail"],
                "screened": sum(r["screened"] for r in rows),
                "training_allowed": False,
            },
        )
        record(state=terminal, api_requests_this_run=budget.sent)
    return terminal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with Path("reports/collection-runtime/request-budget.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(run(args.previous, args.output), flush=True)


if __name__ == "__main__":
    main()
