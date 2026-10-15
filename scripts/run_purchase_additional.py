"""Single local worker: wait through persisted cooldown, resume only budget pauses."""

import fcntl
import os
import runpy
import time
from pathlib import Path

import httpx

from dota_items.sources.opendota_budget import BudgetPaused, RequestBudget
from dota_items.storage import json_bytes


def main():
    if os.environ.get("OPENDOTA_API_KEY"):
        raise RuntimeError("Anonymous collection only; no paid API requests")
    directory = Path("reports/collection-runtime")
    directory.mkdir(parents=True, exist_ok=True)
    status = directory / "additional-status.json"
    route = os.environ.get("DOTA_COLLECTION_ROUTE", "direct")
    if route not in ("direct", "proxy"):
        raise ValueError("Unknown collection route")
    # Keep the proxy trial's existing accounting; never reset it on handoff.
    budget_path = (
        Path("data/purchase-proxy-trial-2026-10-15/request-budget.json")
        if route == "proxy"
        else directory / "request-budget.json"
    )
    if route == "proxy" and not budget_path.exists():
        raise ValueError("Existing proxy budget required")

    def record(state, **details):
        value = dict(state=state, route=route, pid=os.getpid(), updated_at=time.time(), **details)
        temp = status.with_suffix(".tmp")
        temp.write_bytes(json_bytes(value))
        temp.replace(status)
        print(value, flush=True)

    with (directory / "request-budget.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget = RequestBudget(budget_path)
        original = httpx.Client

        class GuardedClient(original):
            def __init__(self, *args, **kwargs):
                kwargs["event_hooks"] = {"request": [budget.before], "response": [budget.after]}
                kwargs["trust_env"] = False
                if route == "proxy":
                    kwargs["proxy"] = "http://127.0.0.1:7890"
                super().__init__(*args, **kwargs)

        httpx.Client = GuardedClient
        try:
            while True:
                resume = budget.state.get("blocked_until", 0)
                if resume > time.time():
                    record("waiting_for_budget", resume_at=resume)
                    while time.time() < resume:
                        time.sleep(min(30, resume - time.time()))
                record("collecting")
                try:
                    runpy.run_path("scripts/collect_purchase_additional.py", run_name="__main__")
                except BudgetPaused:
                    if budget.state.get("blocked_until", 0) <= time.time():
                        raise RuntimeError("Budget pause without future resume time") from None
                    continue
                except SystemExit as result:
                    if result.code not in (None, 0):
                        raise
                record("done")
                return
        except BaseException as error:
            record("stopped", error_type=type(error).__name__)
            raise
        finally:
            httpx.Client = original


if __name__ == "__main__":
    main()
