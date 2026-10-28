"""Frozen prospective collection; blind screening only, never inference or training."""

import argparse
import fcntl
import math
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from collect_purchase_latest import history, inspect_match, load, save

from dota_items.data.patch_time import OFFICIAL_PATCH_URL, load_patch_window
from dota_items.sources.collection_history import filter_discovery
from dota_items.sources.opendota_budget import BudgetPaused, RequestBudget
from dota_items.storage import file_hash

BUDGET = Path("data/purchase-proxy-trial-2026-10-15/request-budget.json")
LOCK = Path("reports/collection-runtime/request-budget.lock")
MODELS = {
    "reports/whole-log-fixed-baseline-2026-10-21/frequency.model.json": (
        "8fce24ca21ab4a6b20c1ca0f0d118bebe188856c5e7dfa49d515ddf0448799ca"
    ),
    "reports/whole-log-regularization-2026-10-22/logistic_c0_1.model.json": (
        "46262e167a7cd02c68c5edc11708203b9030acb112f162f5d8d61fbc7f0ea5c1"
    ),
}
SOURCES = (
    "scripts/collect_evaluation_cohort.py",
    "scripts/collect_purchase_latest.py",
    "src/dota_items/data/patch_time.py",
    "src/dota_items/data/purchase_observation.py",
    "src/dota_items/data/source_io.py",
    "src/dota_items/data/contracts.py",
    "src/dota_items/contracts/tasks.py",
    "src/dota_items/sources/collection_history.py",
    "src/dota_items/sources/opendota_budget.py",
    "src/dota_items/storage.py",
)
RESUMABLE = {"paused_run", "paused_budget"}
AUDIT = Path("reports/evaluation-feasibility-2026-10-23-v3/audit.json")
DESIGN = Path("docs/evaluation-execution-proposal-2026-10-23.md")


def iso(stamp):
    return datetime.fromtimestamp(stamp, UTC).isoformat()


def manifest(directory):
    return {p.name: file_hash(p) for p in sorted(directory.iterdir()) if p.is_file()}


def check_seal(directory, seal):
    record = load(directory / seal)
    actual = manifest(directory)
    actual.pop(seal)
    if actual != record["sha256"]:
        raise ValueError(f"Evidence changed: {directory}")
    return record


def freeze(root, *, data=Path("data"), now=None):
    """Offline only. Called once after the user's explicit parameter approval."""
    now = datetime.now(UTC) if now is None else now
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    # This approval binds the concrete dates shown to the user, not moving dates.
    if now.astimezone(UTC).date().isoformat() != "2026-10-23":
        raise ValueError("Approval dates expired; display revised dates before freezing")
    if root.exists() or root.is_symlink():
        raise ValueError("New output required")
    for name, digest in MODELS.items():
        if file_hash(Path(name)) != digest:
            raise ValueError("Frozen model changed")
    audit = None
    if AUDIT is not None:
        if file_hash(AUDIT) != load(AUDIT.with_name("complete.json"))["audit_sha256"]:
            raise ValueError("Feasibility audit hash mismatch")
        audit = load(AUDIT)
        if audit["old_source_count"] != 1990:
            raise ValueError("Old cohort count changed")
        for name, digest in audit["inputs"].items():
            if file_hash(Path(name)) != digest:
                raise ValueError(f"Audited input changed: {name}")
    ids, plans = history(data)
    lower = int(datetime(2026, 10, 24, tzinfo=UTC).timestamp())
    upper = lower + 7 * 86400
    if audit is not None and datetime.fromisoformat(audit["old_end_max_utc"]).timestamp() >= lower:
        raise ValueError("Prospective window overlaps old development cohort")
    protocol = dict(
        schema_version="prospective-evaluation-collection/1",
        frozen_at=now.isoformat(),
        approval_source="2026-10-23 user explicit approval",
        start_time_min=lower,
        planned_upper_exclusive=upper,
        deadline=upper + 7 * 86400,
        target_n=500,
        max_http_requests=10000,
        max_non_detail_requests=500,
        max_http_per_run=1000,
        page_size=100,
        patch="7.41f",
        numeric_patch_evidence=60,
        numeric_patch_is_official_mapping=False,
        boundary_buffer_seconds=3600,
        hero_id=8,
        game_mode=22,
        lobby_type=7,
        min_average_rank_hint=70,
        min_duration=1800,
        max_duration=86400,
        order=["start_time", "match_id"],
        retries=0,
        route="proxy",
        budget_path=str(BUDGET),
        model_sha256=MODELS,
        implementation_sha256={name: file_hash(Path(name)) for name in SOURCES},
        training_allowed=False,
        inference_allowed=False,
        formal_split_assigned=False,
        task="juggernaut-source-log-7.41f-whole-11/1",
        collection_not_before=iso(upper),
        deadline_utc=iso(upper + 7 * 86400),
    )
    root.mkdir(parents=True, exist_ok=False)
    if audit is not None:
        (root / "prior-audit.json").write_bytes(AUDIT.read_bytes())
        (root / "approved-design.md").write_bytes(DESIGN.read_bytes())
        protocol["prior_audit_sha256"] = file_hash(root / "prior-audit.json")
        protocol["approved_design_sha256"] = file_hash(root / "approved-design.md")
        protocol["old_end_max_utc"] = audit["old_end_max_utc"]
    save(root / "protocol.json", protocol)
    save(root / "exclusions.json", dict(match_ids=ids, historical_plan_sha256=plans))
    save(root / "freeze.json", dict(sha256=manifest(root)))
    (root / "batches").mkdir()
    return protocol


def verify(root):
    check_seal(root, "freeze.json")
    protocol = load(root / "protocol.json")
    for name, digest in (protocol["implementation_sha256"] | protocol["model_sha256"]).items():
        if file_hash(Path(name)) != digest:
            raise ValueError(f"Frozen implementation/model changed: {name}")
    state = dict(
        phase="discovery",
        cursor=2**63 - 1,
        candidates=[],
        results=[],
        next_index=0,
        http_requests=0,
        non_detail_requests=0,
        patch_window=None,
        effective_upper=None,
        state="ready",
        training_allowed=False,
        inference_allowed=False,
        formal_split_assigned=False,
    )
    batches = sorted((root / "batches").iterdir())
    previous = file_hash(root / "freeze.json")
    total = non_detail = 0
    for i, batch in enumerate(batches, 1):
        if batch.name != f"batch-{i:04d}" or not batch.is_dir():
            raise ValueError("Non-contiguous batch history")
        seal = check_seal(batch, "complete.json")
        if seal["previous_sha256"] != previous:
            raise ValueError("Batch chain changed")
        requests = sorted(batch.glob("request-*.json"))
        for j, path in enumerate(requests, 1):
            if path.name != f"request-{j:04d}.json":
                raise ValueError("Non-contiguous request ledger")
            request = load(path)
            total += 1
            non_detail += request["kind"] != "detail"
        state = load(batch / "result.json")
        if state["http_requests"] != total or state["non_detail_requests"] != non_detail:
            raise ValueError("Cumulative ledger mismatch")
        if i < len(batches) and state["state"] not in RESUMABLE:
            raise ValueError("Continued a terminal batch")
        previous = file_hash(batch / "complete.json")
    return protocol, state, len(batches), previous


def discovery_sql(protocol, upper, cursor):
    return (
        "SELECT match_id,start_time,duration,avg_rank_tier,"
        "num_rank_tier,lobby_type,game_mode FROM public_matches WHERE "
        f"match_id>0 AND match_id<{cursor} "
        f"AND start_time>={protocol['start_time_min']} AND start_time<{upper} "
        "AND duration>=1800 AND (8=ANY(radiant_team) OR 8=ANY(dire_team)) "
        "AND lobby_type=7 AND game_mode=22 AND avg_rank_tier>=70 "
        "ORDER BY match_id DESC LIMIT 100"
    )


def validate_discovery(rows, protocol, upper, cursor):
    filter_discovery(rows, set(), 0, cursor)
    for row in rows:
        rank = row.get("avg_rank_tier")
        if (
            type(row.get("start_time")) is not int
            or not protocol["start_time_min"] <= row["start_time"] < upper
            or type(row.get("duration")) is not int
            or row["duration"] < 1800
            or row.get("lobby_type") != 7
            or row.get("game_mode") != 22
            or type(rank) not in (int, float)
            or not math.isfinite(rank)
            or rank < 70
            or type(row.get("num_rank_tier")) is not int
            or not 1 <= row["num_rank_tier"] <= 10
        ):
            raise ValueError("Discovery differs from frozen scope")


def merge_patch(state, window, protocol):
    upper = min(protocol["planned_upper_exclusive"], window["upper_exclusive"])
    if (
        window["release_timestamp"] > protocol["start_time_min"]
        or upper <= protocol["start_time_min"]
    ):
        raise ValueError("Approved patch unavailable for prospective window")
    if (
        window["upper_kind"] == "snapshot_retrieval"
        and window["upper_exclusive"] < protocol["planned_upper_exclusive"]
    ):
        raise ValueError("Patch evidence does not cover sealed window")
    old = state["patch_window"]
    if old is not None and (
        old["release_timestamp"] != window["release_timestamp"]
        or state["effective_upper"] != upper
        or (
            old["upper_kind"] == "snapshot_retrieval"
            and window["upper_kind"] == "next_release"
            and window["upper_exclusive"] < old["upper_exclusive"]
        )
        or (
            old["upper_kind"] == "next_release"
            and (
                window["upper_kind"] != "next_release"
                or old["upper_exclusive"] != window["upper_exclusive"]
            )
        )
    ):
        raise ValueError("Patch evidence changed; quarantine earlier candidates")
    state.update(patch_window=window, effective_upper=upper)


class StopRun(Exception):
    pass


class Sender:
    def __init__(self, client, budget, batch, protocol, state, clock, sleep):
        self.client, self.budget, self.batch = client, budget, batch
        self.protocol, self.state, self.clock, self.sleep = protocol, state, clock, sleep
        self.count = 0

    def send(self, kind, url, params=None):
        p, s = self.protocol, self.state
        if self.clock() >= p["deadline"]:
            raise StopRun("stopped_deadline")
        if s["http_requests"] >= p["max_http_requests"]:
            raise StopRun("stopped_total_budget")
        if self.count >= p["max_http_per_run"]:
            raise StopRun("paused_run")
        if kind != "detail" and s["non_detail_requests"] >= p["max_non_detail_requests"]:
            raise StopRun("stopped_discovery_budget")
        request = self.client.build_request("GET", url, params=params)
        # Shared budget reserves before send; no total-budget refund on a failed send.
        self.budget.before(request)
        # Shared pacing may have crossed the collection deadline; do not send then.
        if self.clock() >= p["deadline"]:
            raise StopRun("stopped_deadline")
        self.count += 1
        s["http_requests"] += 1
        s["non_detail_requests"] += kind != "detail"
        stem = f"{self.count:04d}"
        save(
            self.batch / f"request-{stem}.json",
            dict(
                kind=kind,
                url=str(request.url),
                reserved_at=iso(self.clock()),
                cumulative_http=s["http_requests"],
                retry=0,
            ),
        )
        response = self.client.send(request)
        name = f"response-{stem}.json"
        (self.batch / name).write_bytes(response.content)
        save(
            self.batch / f"receipt-{stem}.json",
            dict(
                status=response.status_code,
                sha256=file_hash(self.batch / name),
                retrieved_at=iso(self.clock()),
                source_url=str(request.url),
                rate_headers={
                    k: v
                    for k, v in response.headers.items()
                    if k.startswith("x-rate-limit") or k == "retry-after"
                },
            ),
        )
        self.budget.after(response)
        response.raise_for_status()
        payload = load(self.batch / name)
        # A completed response is processed before any next-request cooldown check.
        return payload, name

    def patch(self):
        _, name = self.send("patch", OFFICIAL_PATCH_URL)
        receipt = self.batch / f"patch-{self.count:04d}.json"
        source = load(self.batch / f"receipt-{self.count:04d}.json")
        save(
            receipt,
            dict(
                schema_version="patch-time-evidence/1",
                source_url=OFFICIAL_PATCH_URL,
                snapshot=name,
                sha256=source["sha256"],
                retrieved_at=source["retrieved_at"],
                boundary_buffer_seconds=self.protocol["boundary_buffer_seconds"],
            ),
        )
        merge_patch(self.state, load_patch_window(receipt, self.protocol["patch"]), self.protocol)

    def cooldown(self):
        delay = self.budget.state.get("blocked_until", 0) - self.clock()
        if delay <= 0:
            return
        minute = self.budget.state.get("remaining", {}).get("minute", 100)
        day = self.budget.state.get("remaining", {}).get("day", 100)
        if delay > 65.1 or minute > 5 or day <= 20 or self.budget.state.get("last_status") == 429:
            raise BudgetPaused("Shared daily/cooldown protection; stop")
        if self.clock() + delay >= self.protocol["deadline"]:
            raise StopRun("stopped_deadline")
        while delay > 0:
            self.sleep(min(delay, 60))
            delay = self.budget.state.get("blocked_until", 0) - self.clock()

    def room(self):
        # Reserve one request for a final official patch check in this batch.
        return (
            self.count < self.protocol["max_http_per_run"] - 1
            and self.state["http_requests"] < self.protocol["max_http_requests"] - 1
            and self.state["non_detail_requests"] < self.protocol["max_non_detail_requests"] - 1
        )


def run(root, *, transport=None, clock=time.time, sleep=time.sleep):
    """Caller must hold the shared lock. Mock transport is only for offline tests."""
    if os.environ.get("OPENDOTA_API_KEY"):
        raise ValueError("Anonymous only")
    p, state, batch_count, previous = verify(root)
    if state["state"] not in RESUMABLE | {"ready"}:
        return state
    if clock() < p["planned_upper_exclusive"]:
        return dict(
            state="waiting_window",
            not_before=iso(p["planned_upper_exclusive"]),
            http_requests=state["http_requests"],
            training_allowed=False,
        )
    if clock() >= p["deadline"]:
        return dict(
            state="stopped_deadline", http_requests=state["http_requests"], training_allowed=False
        )
    budget_path = Path(p["budget_path"])
    if not budget_path.is_file():
        raise ValueError("Existing shared budget required")
    excluded = set(load(root / "exclusions.json")["match_ids"])
    # New concurrent caches cannot silently be used or fetched twice.
    live_ids, _ = history(Path("data")) if transport is None else ([], {})
    new_history = set(live_ids) - excluded
    if any(r["match_id"] in new_history for r in state["candidates"]):
        raise ValueError("New external cache overlaps frozen candidates; review required")
    batch = root / "batches" / f"batch-{batch_count + 1:04d}"
    batch.mkdir()
    (batch / "budget-before.json").write_bytes(budget_path.read_bytes())
    budget = RequestBudget(budget_path, clock=clock, sleep=sleep)
    state["state"] = "running"
    state["batch_patch_verified"] = False
    state["error"] = None
    client = None
    try:
        client = httpx.Client(
            proxy="http://127.0.0.1:7890" if transport is None else None,
            transport=transport,
            trust_env=False,
            timeout=40,
            follow_redirects=False,
        )
        sender = Sender(client, budget, batch, p, state, clock, sleep)
        sender.cooldown()
        sender.patch()
        while sender.room():
            sender.cooldown()
            if state["phase"] == "discovery":
                payload, name = sender.send(
                    "discovery",
                    "https://api.opendota.com/api/explorer",
                    {"sql": discovery_sql(p, state["effective_upper"], state["cursor"])},
                )
                if (
                    not isinstance(payload, dict)
                    or payload.get("err")
                    or not isinstance(payload.get("rows"), list)
                ):
                    raise ValueError("Discovery application error")
                rows = payload["rows"]
                validate_discovery(rows, p, state["effective_upper"], state["cursor"])
                for row in rows:
                    if row["match_id"] in new_history:
                        raise ValueError("New external history overlaps discovery")
                    state["candidates"].append(
                        dict(
                            row,
                            excluded=row["match_id"] in excluded,
                            discovery_source=f"batches/{batch.name}/{name}",
                        )
                    )
                if rows:
                    state["cursor"] = min(r["match_id"] for r in rows)
                    continue
                state["candidates"].sort(key=lambda r: (r["start_time"], r["match_id"]))
                state["phase"] = "details"
                save(
                    batch / "candidates.json",
                    dict(
                        rows=state["candidates"],
                        source_scope="actual discovered range; not a population census",
                        protocol_sha256=file_hash(root / "protocol.json"),
                    ),
                )
                continue
            if state["phase"] == "details":
                if sum(r["screened"] for r in state["results"]) >= p["target_n"]:
                    state["state"] = "target_reached"
                    break
                if state["next_index"] >= len(state["candidates"]):
                    state["state"] = "candidates_exhausted"
                    break
                row = state["candidates"][state["next_index"]]
                mid = row["match_id"]
                if row["excluded"]:
                    result = dict(
                        match_id=mid,
                        screened=False,
                        reasons=["historical_id"],
                        request_sent=False,
                    )
                else:
                    raw, name = sender.send("detail", f"https://api.opendota.com/api/matches/{mid}")
                    result = inspect_match(raw, mid, state["patch_window"])
                    # inspect_match validates the entire log, but its old five-item,
                    # 30-minute observations are NOT this whole-log experiment's labels.
                    result.pop("observations")
                    if (
                        raw.get("start_time") != row["start_time"]
                        or raw.get("duration") != row["duration"]
                    ):
                        raise ValueError("Discovery/detail time conflict")
                    if (
                        type(raw.get("patch")) is not int
                        or raw["patch"] != p["numeric_patch_evidence"]
                    ):
                        raise ValueError("Numeric patch missing/conflicting; not official mapping")
                    result.update(
                        source=f"batches/{batch.name}/{name}",
                        source_sha256=file_hash(batch / name),
                        request_sent=True,
                    )
                state["results"].append(result)
                state["next_index"] += 1
        # Refresh even when selection/total budget was reached. Failure keeps
        # the batch unverified and is never silently resumed.
        sender.patch()
        state["batch_patch_verified"] = True
        if state["state"] == "running":
            if sum(r["screened"] for r in state["results"]) >= p["target_n"]:
                state["state"] = "target_reached"
            elif state["next_index"] == len(state["candidates"]) and state["phase"] == "details":
                state["state"] = "candidates_exhausted"
            elif state["http_requests"] >= p["max_http_requests"] - 1:
                state["state"] = "stopped_total_budget"
            elif state["non_detail_requests"] >= p["max_non_detail_requests"] - 1:
                state["state"] = "stopped_discovery_budget"
            else:
                state["state"] = "paused_run"
    except BudgetPaused as exc:
        active = bool(list(batch.glob("request-*.json")))
        state.update(state="paused_budget", error=str(exc))
        if active:
            if budget.state.get("last_status") == 429:
                state["state"] = "blocked_review"
            else:
                # An unsent daily-cap pause is resumable, provided the completed
                # work can still be checked against fresh official evidence.
                try:
                    sender.patch()
                    state["batch_patch_verified"] = True
                except (
                    BudgetPaused,
                    StopRun,
                    httpx.HTTPError,
                    ValueError,
                    TypeError,
                    KeyError,
                ) as closing:
                    state.update(state="blocked_review", error=f"Closing check failed: {closing}")
    except StopRun as exc:
        state.update(
            state="blocked_review" if str(exc) == "paused_run" else str(exc),
            error="Batch stopped before closing patch verification",
        )
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        state.update(state="blocked_review", error=f"{type(exc).__name__}: {exc}")
    finally:
        if client is not None:
            client.close()
        # Never seal a successful batch under code/protocol that changed mid-run.
        try:
            check_seal(root, "freeze.json")
            for name, digest in (p["implementation_sha256"] | p["model_sha256"]).items():
                if file_hash(Path(name)) != digest:
                    raise ValueError(f"Frozen dependency changed: {name}")
        except (ValueError, OSError) as drift:
            state.update(state="blocked_review", error=str(drift), batch_patch_verified=False)
        (batch / "budget-after.json").write_bytes(budget_path.read_bytes())
        state["finished_at"] = iso(clock())
        state["screened_count"] = sum(r["screened"] for r in state["results"])
        save(batch / "result.json", state)
        save(
            batch / "complete.json",
            dict(
                sha256=manifest(batch),
                previous_sha256=previous,
                state=state["state"],
                training_allowed=False,
                formal_split_assigned=False,
            ),
        )
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "status", "run"))
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "freeze":
            p = freeze(args.root)
            print(
                {
                    "state": "frozen",
                    "not_before": p["collection_not_before"],
                    "protocol_sha256": file_hash(args.root / "protocol.json"),
                }
            )
            return 0
        if args.action == "status":
            p, state, batches, _ = verify(args.root)
            print(
                {
                    "state": state["state"],
                    "batches": batches,
                    "http_requests": state["http_requests"],
                    "not_before": p["collection_not_before"],
                }
            )
            return 0
        result = run(args.root)
        print(
            {
                key: result.get(key)
                for key in ("state", "http_requests", "screened_count", "not_before", "error")
            }
        )
        return (
            0
            if result["state"] in {"target_reached", "candidates_exhausted", "waiting_window"}
            else 75
        )


if __name__ == "__main__":
    raise SystemExit(main())
