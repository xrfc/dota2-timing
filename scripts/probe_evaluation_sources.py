"""Three-request source probe; no retries, collection expansion, labels or training."""

import argparse
import fcntl
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
from collect_purchase_latest import load, save

from dota_items.data.patch_time import OFFICIAL_PATCH_URL, load_patch_window
from dota_items.sources.opendota_budget import BudgetPaused, RequestBudget
from dota_items.storage import file_hash

FAILED = Path("data/purchase-until-daily-2026-10-22-proxy-resume-01/batch-0001/discovery.json")
BUDGET = Path("data/purchase-proxy-trial-2026-10-15/request-budget.json")
MATCH_ID = 9056009571
LOCK = Path("reports/collection-runtime/request-budget.lock")


def run(output, *, failed=FAILED, budget_path=BUDGET, transport=None):
    """Caller holds the shared collection lock; transport injection is for offline tests."""
    if os.environ.get("OPENDOTA_API_KEY"):
        raise ValueError("Anonymous only")
    if output.exists() or output.is_symlink():
        raise ValueError("New output required")
    if not budget_path.is_file():
        raise ValueError("Existing route budget required")
    source = load(failed)
    if source["status"] != 400 or not source["sql"].startswith("SELECT "):
        raise ValueError("Expected saved failed discovery query")
    requests = [
        dict(name="patch", url=OFFICIAL_PATCH_URL, params={}),
        dict(
            name="discovery",
            url="https://api.opendota.com/api/explorer",
            params={"sql": source["sql"]},
        ),
        dict(name="detail", url=f"https://api.opendota.com/api/matches/{MATCH_ID}", params={}),
    ]
    output.mkdir(parents=True, exist_ok=False)
    (output / "budget-before.json").write_bytes(budget_path.read_bytes())
    save(
        output / "plan.json",
        dict(
            schema_version="evaluation-source-probe/1",
            requests=requests,
            failed_source=str(failed),
            failed_sha256=file_hash(failed),
            budget_path=str(budget_path),
            budget_before_sha256=file_hash(budget_path),
            route="proxy",
            max_http_requests=3,
            max_opendota_requests=2,
            retries=0,
            implementation={
                str(p): file_hash(p)
                for p in (
                    Path(__file__),
                    Path("scripts/collect_purchase_latest.py"),
                    Path("src/dota_items/sources/opendota_budget.py"),
                    Path("src/dota_items/data/patch_time.py"),
                )
            },
            training_allowed=False,
            formal_split_assigned=False,
            created_at=datetime.now(UTC).isoformat(),
        ),
    )
    budget = RequestBudget(budget_path)
    result = dict(state="starting", rows=[], training_allowed=False, formal_split_assigned=False)
    try:
        with httpx.Client(
            proxy="http://127.0.0.1:7890" if transport is None else None,
            transport=transport,
            trust_env=False,
            timeout=40,
            follow_redirects=False,
        ) as client:
            for entry in requests:
                row = dict(name=entry["name"], request_reserved=False, response_saved=False)
                result["rows"].append(row)
                request = client.build_request("GET", entry["url"], params=entry["params"])
                budget.before(request)
                row["request_reserved"] = request.url.host == "api.opendota.com"
                response = client.send(request)
                name = entry["name"] + ".response.json"
                (output / name).write_bytes(response.content)
                row.update(
                    status=response.status_code,
                    response_saved=True,
                    response=name,
                    sha256=file_hash(output / name),
                    retrieved_at=datetime.now(UTC).isoformat(),
                    rate_headers={
                        k: v
                        for k, v in response.headers.items()
                        if k.startswith("x-rate-limit") or k == "retry-after"
                    },
                )
                # Save response evidence before the budget hook can stop on a 429.
                save(output / (entry["name"] + ".receipt.json"), row)
                budget.after(response)
                response.raise_for_status()
                payload = load(output / name)
                if entry["name"] == "patch":
                    save(
                        output / "patch-receipt.json",
                        dict(
                            schema_version="patch-time-evidence/1",
                            source_url=OFFICIAL_PATCH_URL,
                            snapshot=name,
                            sha256=row["sha256"],
                            retrieved_at=row["retrieved_at"],
                            boundary_buffer_seconds=3600,
                        ),
                    )
                    result["target_patch_window"] = load_patch_window(
                        output / "patch-receipt.json", "7.41f"
                    )
                    result["latest_patch"] = max(
                        payload["patches"], key=lambda r: r["patch_timestamp"]
                    )["patch_number"]
                elif entry["name"] == "discovery":
                    if payload.get("err") or not isinstance(payload.get("rows"), list):
                        raise ValueError("Discovery application error or invalid rows")
                    row["returned_rows"] = len(payload["rows"])
                elif type(payload.get("match_id")) is not int or payload["match_id"] != MATCH_ID:
                    raise ValueError("Detail identity mismatch")
                if budget.clock() < budget.state.get("blocked_until", 0):
                    raise BudgetPaused("Response triggered budget protection; no next request")
        result["state"] = "completed"
    except (httpx.HTTPError, ValueError, KeyError, TypeError, BudgetPaused) as exc:
        result.update(
            state="paused_budget" if isinstance(exc, BudgetPaused) else "failed",
            error_type=type(exc).__name__,
            error=str(exc),
        )
    finally:
        result["finished_at"] = datetime.now(UTC).isoformat()
        (output / "budget-after.json").write_bytes(budget_path.read_bytes())
        save(output / "result.json", result)
        save(
            output / "complete.json",
            dict(
                sha256={p.name: file_hash(p) for p in sorted(output.iterdir()) if p.is_file()},
                state=result["state"],
                training_allowed=False,
            ),
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with LOCK.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run(args.output)
    print(result)
    return 0 if result["state"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
