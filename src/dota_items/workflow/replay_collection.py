"""Explicit-version bounded discovery and resumable download/parse/verify stages."""

import fcntl
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx

from dota_items.contracts.replay_collection import (
    OFFICIAL_PATCH_URL,
    PatchWindow,
    validate_match_metadata,
)
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.sources import replay_collection_io as network
from dota_items.sources.opendota_budget import BudgetPaused, RequestBudget
from dota_items.storage import json_bytes
from dota_items.workflow.replay_processing import (
    check_reference,
    load_json,
    match_allowed,
    source_reference,
)

REPO = Path(__file__).resolve().parents[3]
DEFAULT_COMPAT = REPO / "data/replay-pilot-2026-10-22/compat-v1"
RUNTIME = REPO / "reports/collection-runtime"
BUDGETS = {
    "proxy": REPO / "data/purchase-proxy-trial-2026-10-15/request-budget.json",
    "direct": RUNTIME / "request-budget.json",
}
RESERVE = 30 * 1024**3


def write_new(path, value, *, raw=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = value if raw else json_bytes(value)
    if path.exists():
        if path.read_bytes() == content:
            return
        raise FileExistsError("Immutable collection artifact already exists")
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def event(root, stage, **fields):
    value = {
        "schema": "replay-stage-event/1",
        "at": datetime.now(UTC).isoformat(),
        "stage": stage,
        **fields,
    }
    write_new(
        Path(root)
        / "events"
        / (time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex + ".json"),
        value,
    )
    return value


def _diagnostic(error):
    """Keep useful local validation reasons without HTTP URLs or command output."""
    result = {"error_type": type(error).__name__}
    if isinstance(error, httpx.HTTPError):
        if isinstance(error, httpx.HTTPStatusError):
            result["status_code"] = error.response.status_code
    elif isinstance(error, subprocess.TimeoutExpired):
        result["timed_out"] = True
    elif isinstance(error, subprocess.CalledProcessError):
        result["returncode"] = error.returncode
    elif isinstance(error, OSError):
        if isinstance(error, TimeoutError):
            result["timed_out"] = True
        if error.errno is not None:
            result["errno"] = error.errno
    elif isinstance(error, OverflowError):
        result["error_message"] = "numeric overflow"
    elif isinstance(error, ValueError):
        message = re.sub(r"https?://\S+", "[URL omitted]", str(error))
        result["error_message"] = " ".join(message.split())[:500]
    return result


@contextmanager
def collection_lock(root, *, network_access=False):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    paths = [root / ".lock"]
    if network_access:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        paths.append(RUNTIME / "request-budget.lock")
    streams = []
    try:
        for path in paths:
            stream = path.open("a")
            streams.append(stream)
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Collection root or shared network budget is in use") from None
        yield
    finally:
        for stream in reversed(streams):
            stream.close()


def _positive(value, label):
    if type(value) is not int or value <= 0:
        raise ValueError(label + " must be a positive integer")


def make_plan(
    root,
    snapshot,
    *,
    patch,
    retrieved_at,
    rows,
    exclusion,
    expected_patch_code=None,
    bounds=None,
    min_duration=900,
    min_rank=70,
    boundary_buffer_seconds=3600,
):
    """Freeze local input references. Does not copy demos or reinterpret old outputs."""
    root = Path(root).resolve()
    if (root / "plan.json").exists():
        raise FileExistsError("Use a new root for a different collection plan")
    snapshot = Path(snapshot).resolve()
    raw = read_source_bytes(snapshot)
    window = PatchWindow.from_snapshot(
        raw, patch=patch, retrieved_at=retrieved_at, boundary_buffer_seconds=boundary_buffer_seconds
    )
    selected, seen = [], set()
    for row in rows:
        mid = row["match_id"]
        if not match_allowed(mid, exclusion):
            raise ValueError("Reserved match rejected before reading match inputs")
        if mid in seen:
            raise ValueError("Duplicate match in collection plan")
        seen.add(mid)
        meta_path = Path(row["metadata_path"]).resolve()
        meta_ref = source_reference(meta_path)
        meta = load_json(meta_path)
        discovery = {
            key: row[key] for key in ("match_id", "start_time", "duration", "avg_rank_tier")
        }
        reasons = validate_match_metadata(
            meta,
            discovery,
            window,
            expected_patch_code=expected_patch_code,
            bounds=bounds,
            min_duration=min_duration,
            min_rank=min_rank,
        )
        if reasons:
            raise ValueError("Metadata rejected: " + ",".join(reasons))
        item = {"discovery": discovery, "metadata": meta_ref}
        if row.get("demo_path"):
            item["demo"] = source_reference(row["demo_path"])
        elif not network.replay_url_allowed(meta.get("replay_url")):
            raise ValueError("No approved replay URL")
        selected.append(item)
    if not selected:
        raise ValueError("No eligible matches; discovery evidence has been preserved")
    plan = {
        "schema": "replay-collection-plan/2",
        "patch_window": window.to_dict(),
        "snapshot": source_reference(snapshot),
        "bounds": bounds,
        "expected_patch_code": expected_patch_code,
        "min_duration": min_duration,
        "min_rank": min_rank,
        "exclusion": exclusion,
        "purpose": "engineering_qa",
        "training_allowed": False,
        "matches": selected,
    }
    write_new(root / "plan.json", plan)
    return plan


def load_plan(root, exclusion):
    plan = load_json(Path(root) / "plan.json")
    if (
        plan.get("schema") != "replay-collection-plan/2"
        or plan.get("exclusion") != exclusion
        or plan.get("training_allowed") is not False
    ):
        raise ValueError("Collection plan identity/policy mismatch")
    check_reference(plan["snapshot"])
    window = PatchWindow.from_dict(plan["patch_window"])
    rebuilt = PatchWindow.from_snapshot(
        read_source_bytes(Path(plan["snapshot"]["path"])),
        patch=window.patch,
        retrieved_at=window.retrieved_at,
        boundary_buffer_seconds=window.boundary_buffer_seconds,
    )
    if rebuilt != window:
        raise ValueError("Patch window disagrees with official snapshot")
    seen = set()
    for item in plan["matches"]:
        mid = item["discovery"]["match_id"]
        if not match_allowed(mid, exclusion) or mid in seen:
            raise ValueError("Reserved or duplicate planned match")
        seen.add(mid)
        check_reference(item["metadata"])
        reasons = validate_match_metadata(
            load_json(item["metadata"]["path"]),
            item["discovery"],
            window,
            expected_patch_code=plan["expected_patch_code"],
            bounds=plan["bounds"],
            min_duration=plan["min_duration"],
            min_rank=plan["min_rank"],
        )
        if reasons:
            raise ValueError("Plan metadata no longer meets scope")
    return plan


def discover(
    root,
    *,
    patch,
    exclusion,
    route="proxy",
    max_candidates=8,
    max_pages=6,
    max_metadata=12,
    max_seconds=300,
    min_duration=900,
    heroes=(),
    expected_patch_code=None,
):
    for value, label in (
        (max_candidates, "max_candidates"),
        (max_pages, "max_pages"),
        (max_metadata, "max_metadata"),
        (max_seconds, "max_seconds"),
    ):
        _positive(value, label)
    if os.environ.get("OPENDOTA_API_KEY"):
        raise ValueError("Anonymous collection requires OPENDOTA_API_KEY unset")
    root = Path(root).resolve()
    with collection_lock(root, network_access=True):
        if (root / "plan.json").exists() or (root / "discovery-config.json").exists():
            raise FileExistsError("Discovery is immutable; use the saved plan or a new root")
        deadline = time.monotonic() + max_seconds
        write_new(
            root / "discovery-config.json",
            {
                "patch": patch,
                "expected_patch_code": expected_patch_code,
                "route": route,
                "max_candidates": max_candidates,
                "max_pages": max_pages,
                "max_metadata": max_metadata,
                "max_seconds": max_seconds,
                "min_duration": min_duration,
                "hero_filter": list(heroes),
                "exclusion": exclusion,
            },
        )
        api, plain = network.clients(
            RequestBudget(BUDGETS[route]),
            proxy="http://127.0.0.1:7890" if route == "proxy" else None,
        )
        try:
            raw, _ = network.get_json(
                plain, OFFICIAL_PATCH_URL, max_bytes=4 * 1024**2, deadline=deadline
            )
            snapshot = root / "patches.json"
            write_new(snapshot, raw, raw=True)
            retrieved = datetime.now(UTC).isoformat()
            window = PatchWindow.from_snapshot(raw, patch=patch, retrieved_at=retrieved)
            write_new(root / "patch-window.json", window.to_dict())
            bounds = window.discovery_bounds(now=int(time.time()))
            write_new(root / "selection-bounds.json", bounds)
            anchor_raw, anchor = network.explorer(
                api, "SELECT max(match_id) AS max_id FROM public_matches", deadline=deadline
            )
            write_new(root / "discovery/anchor.json", anchor_raw, raw=True)
            if (
                not anchor
                or not isinstance(anchor[0], dict)
                or type(anchor[0].get("max_id")) is not int
                or anchor[0]["max_id"] <= 0
            ):
                raise ValueError("Invalid discovery anchor")
            cursor = anchor[0]["max_id"] - int(
                max(0, time.time() - bounds["start_upper"]) / 3600 * 52_000
            )
            selected, seen, metadata_calls = [], set(), 0
            for page in range(max_pages):
                query = network.discovery_sql(
                    bounds, cursor, min_duration=min_duration, heroes=heroes
                )
                raw, found = network.explorer(api, query, deadline=deadline)
                write_new(
                    root / f"discovery/page-{page}.json",
                    {
                        "query": query,
                        "response_sha256": hashlib.sha256(raw).hexdigest(),
                        "rows": found,
                    },
                )
                if any(
                    not isinstance(row, dict)
                    or type(row.get("match_id")) is not int
                    or row["match_id"] <= 0
                    for row in found
                ):
                    raise ValueError("Invalid discovery match identity")
                for row in found:
                    mid = row["match_id"]
                    if mid in seen or not match_allowed(mid, exclusion):
                        continue
                    seen.add(mid)
                    if window.match_time_reasons(
                        row.get("start_time"), row.get("duration"), bounds
                    ):
                        continue
                    if metadata_calls >= max_metadata or len(selected) >= max_candidates:
                        break
                    metadata_calls += 1
                    event(root, "metadata_requested", match_id=mid, ordinal=metadata_calls)
                    try:
                        raw_meta, meta = network.get_json(
                            api, network.API + f"/matches/{mid}", deadline=deadline
                        )
                        path = root / f"meta/{mid}.json"
                        write_new(path, raw_meta, raw=True)
                        reasons = validate_match_metadata(
                            meta,
                            row,
                            window,
                            expected_patch_code=expected_patch_code,
                            bounds=bounds,
                            min_duration=min_duration,
                        )
                        if not network.replay_url_allowed(meta.get("replay_url")):
                            reasons.append("no_replay_url")
                        if reasons:
                            event(root, "metadata_rejected", match_id=mid, reasons=reasons)
                        else:
                            selected.append({**row, "metadata_path": str(path)})
                    except BudgetPaused:
                        raise
                    except (httpx.HTTPError, OSError, ValueError) as error:
                        event(
                            root, "metadata_failed", match_id=mid, error_type=type(error).__name__
                        )
                if len(selected) >= max_candidates or metadata_calls >= max_metadata:
                    break
                cursor = (
                    min(row["match_id"] for row in found) if found else max(1, cursor - 999_999)
                )
            return make_plan(
                root,
                snapshot,
                patch=patch,
                retrieved_at=retrieved,
                rows=selected,
                exclusion=exclusion,
                bounds=bounds,
                expected_patch_code=expected_patch_code,
                min_duration=min_duration,
            )
        except (BudgetPaused, httpx.HTTPError, OSError, ValueError) as error:
            event(root, "discovery_stopped", error_type=type(error).__name__)
            raise
        finally:
            api.close()
            plain.close()


def worker_command(compat, *arguments):
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join((str(Path(compat).resolve()), str(REPO / "src"))),
    }
    command = [
        sys.executable,
        "-m",
        "dota_items.workflow.replay_processing",
        "--compat",
        str(Path(compat).resolve()),
        *arguments,
    ]
    return command, env


def current_producer(compat):
    command, env = worker_command(compat, "--identity")
    result = subprocess.run(
        command, env=env, capture_output=True, text=True, check=True, timeout=60, cwd=REPO
    )
    return parse_source_json(result.stdout.encode())


def _identity(plan, item, demo):
    return {
        "schema": "replay-input-identity/1",
        "match_id": item["discovery"]["match_id"],
        "discovery": item["discovery"],
        "exclusion": plan["exclusion"],
        "patch_window": plan["patch_window"],
        "expected_patch_code": plan["expected_patch_code"],
        "bounds": plan["bounds"],
        "min_duration": plan["min_duration"],
        "min_rank": plan["min_rank"],
        "source_references": [plan["snapshot"], item["metadata"], demo],
        "parameters": {
            "capture_start": -90,
            "output_window": "0..metadata.duration",
            "codec": "gzip",
            "quality_schema": "replay-quality/1",
        },
        "training_allowed": False,
    }


def run_stages(
    root,
    *,
    exclusion,
    stage="all",
    compat=DEFAULT_COMPAT,
    route="proxy",
    target=5,
    max_attempts=8,
    max_bytes=1024**3,
    max_seconds=1800,
    retry_failed=False,
):
    from dota_items.data.replay_bundle_quality import verify_quality_bundle

    if stage not in ("download", "parse", "verify", "all"):
        raise ValueError("Unknown collection stage")
    for value, label in (
        (target, "target"),
        (max_attempts, "max_attempts"),
        (max_bytes, "max_bytes"),
        (max_seconds, "max_seconds"),
    ):
        _positive(value, label)
    root = Path(root).resolve()
    with collection_lock(root, network_access=stage in ("download", "all")):
        plan = load_plan(root, exclusion)
        deadline = time.monotonic() + max_seconds
        producer = current_producer(compat) if stage != "download" else None
        plain = httpx.Client(
            trust_env=False,
            follow_redirects=False,
            timeout=60,
            proxy="http://127.0.0.1:7890" if route == "proxy" else None,
        )
        attempted, succeeded, downloaded_bytes = 0, 0, 0
        results = []
        try:
            for item in plan["matches"]:
                if succeeded >= target or attempted >= max_attempts or time.monotonic() >= deadline:
                    break
                attempted += 1
                mid = item["discovery"]["match_id"]
                job = root / "jobs" / str(mid)
                job.mkdir(parents=True, exist_ok=True)
                downloaded = job / "download.json"
                try:
                    if downloaded.exists():
                        demo = load_json(downloaded)
                        check_reference(demo)
                    elif item.get("demo"):
                        demo = item["demo"]
                        check_reference(demo)
                        write_new(downloaded, demo)
                    elif stage in ("download", "all"):
                        if shutil.disk_usage(root).free < RESERVE:
                            raise ValueError("Disk reserve below 30 GiB")
                        meta = load_json(item["metadata"]["path"])
                        path = job / "downloads" / (uuid.uuid4().hex + ".dem.bz2")
                        event(
                            root,
                            "download_started",
                            match_id=mid,
                            attempt=str(path.relative_to(root)),
                        )
                        try:
                            result = network.download(
                                plain,
                                meta["replay_url"],
                                path,
                                max_bytes=min(512 * 1024**2, max_bytes - downloaded_bytes),
                                deadline=deadline,
                            )
                        finally:
                            for p in (path, path.with_name(path.name + ".partial")):
                                if p.exists():
                                    downloaded_bytes += p.stat().st_size
                        demo = {key: result[key] for key in ("path", "sha256", "size_bytes")}
                        write_new(downloaded, demo)
                        event(root, "downloaded", match_id=mid, source=demo)
                    else:
                        raise ValueError("Download stage has not completed")
                    if stage == "download":
                        succeeded += 1
                        results.append({"match_id": mid, "status": "downloaded"})
                        continue
                    identity = _identity(plan, item, demo)
                    attempts = sorted((job / "attempts").glob("*/bundle"))
                    complete = [p for p in attempts if (p / "manifest.json").exists()]
                    passed = None
                    for path in complete:
                        try:
                            manifest = verify_quality_bundle(
                                path, expected_identity=identity, expected_producer=producer
                            )
                        except (OSError, ValueError, OverflowError) as error:
                            event(
                                root,
                                "cache_rejected",
                                match_id=mid,
                                bundle=str(path),
                                **_diagnostic(error),
                            )
                            continue
                        if manifest["quality"].get("status") == "passed":
                            passed = path
                            break
                    if passed is not None:
                        event(root, "verified_cache", match_id=mid, bundle=str(passed))
                        succeeded += 1
                        results.append(
                            {"match_id": mid, "status": "verified", "bundle": str(passed)}
                        )
                        continue
                    if stage == "verify":
                        raise ValueError("No quality-approved completed parse exists")
                    prior = list((job / "attempts").glob("*"))
                    if prior and not retry_failed:
                        raise ValueError(
                            "Previous attempt retained; explicit --retry-failed required"
                        )
                    if shutil.disk_usage(root).free < RESERVE:
                        break
                    attempt = job / "attempts" / uuid.uuid4().hex
                    request = {
                        "match_id": mid,
                        "exclusion": exclusion,
                        "identity": identity,
                        "producer": producer,
                        "metadata_path": item["metadata"]["path"],
                        "snapshot_path": plan["snapshot"]["path"],
                        "demo_path": demo["path"],
                        "discovery": item["discovery"],
                    }
                    write_new(attempt / "request.json", request)
                    output = attempt / "bundle"
                    command, env = worker_command(
                        compat, "--request", str(attempt / "request.json"), "--output", str(output)
                    )
                    event(
                        root, "parse_started", match_id=mid, attempt=str(attempt.relative_to(root))
                    )
                    with (attempt / "worker.log").open("xb") as stream:
                        subprocess.run(
                            command,
                            env=env,
                            cwd=REPO,
                            stdout=stream,
                            stderr=subprocess.STDOUT,
                            check=True,
                            timeout=min(900, max(0.01, deadline - time.monotonic())),
                        )
                    manifest = verify_quality_bundle(
                        output, expected_identity=identity, expected_producer=producer
                    )
                    status = manifest["quality"]["status"]
                    event(
                        root,
                        "verified" if status == "passed" else "quality_review_required",
                        match_id=mid,
                        bundle=str(output),
                    )
                    succeeded += status == "passed"
                    results.append({"match_id": mid, "status": status, "bundle": str(output)})
                except (
                    OSError,
                    ValueError,
                    OverflowError,
                    httpx.HTTPError,
                    subprocess.SubprocessError,
                ) as error:
                    diagnostic = _diagnostic(error)
                    event(
                        root,
                        "stage_failed",
                        match_id=mid,
                        requested_stage=stage,
                        **diagnostic,
                    )
                    results.append({"match_id": mid, "status": "failed", **diagnostic})
            return event(
                root,
                "run_complete",
                requested_stage=stage,
                succeeded=succeeded,
                attempted=attempted,
                downloaded_bytes=downloaded_bytes,
                results=results,
            )
        finally:
            plain.close()
