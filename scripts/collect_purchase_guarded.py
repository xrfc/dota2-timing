"""Run the frozen collector with a persistent, anonymous-only request budget."""

import fcntl
import os
import runpy
from pathlib import Path

import httpx

from dota_items.sources.opendota_budget import BudgetPaused, RequestBudget


def main():
    if os.environ.get("OPENDOTA_API_KEY"):
        raise RuntimeError("This wrapper is anonymous-only; paid API usage is not authorized")
    directory = Path("reports/collection-runtime")
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "request-budget.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget = RequestBudget(directory / "request-budget.json")
        original_client = httpx.Client

        class GuardedClient(original_client):
            def __init__(self, *args, **kwargs):
                kwargs["event_hooks"] = {"request": [budget.before], "response": [budget.after]}
                super().__init__(*args, **kwargs)

        httpx.Client = GuardedClient
        try:
            runpy.run_path("scripts/collect_purchase_candidates.py", run_name="__main__")
        except BudgetPaused as error:
            print(str(error), flush=True)
            raise SystemExit(75) from None
        finally:
            httpx.Client = original_client


if __name__ == "__main__":
    main()
