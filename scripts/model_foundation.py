"""Synthetic-only demo, existing-artifact prediction and read-only inspection."""

import argparse
import json
import subprocess
from pathlib import Path

from dota_items.contracts.tasks import TASK_ID, WHOLE_LOG_TASK_ID, task_contract
from dota_items.modeling.inspection import inspect_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Fabricated data only; no real-data training input")
    demo.add_argument("--output", type=Path, required=True)
    demo.add_argument("--family", choices=["frequency", "logistic"], default="frequency")
    demo.add_argument(
        "--task-id", choices=[TASK_ID, WHOLE_LOG_TASK_ID], help="Synthetic task-bound /2 demo"
    )
    predict = commands.add_parser("predict")
    predict.add_argument("--model", type=Path, required=True)
    predict.add_argument("--lineup", type=Path, required=True)
    predict.add_argument(
        "--task-id", choices=[TASK_ID, WHOLE_LOG_TASK_ID], help="Require matching task-bound model"
    )
    inspect = commands.add_parser("inspect", help="Read-only validated metadata; no prediction")
    inspect.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "inspect":
        print(json.dumps(inspect_model(args.model), indent=2))
        return

    from dota_items.modeling.foundation import (
        adapt_snapshot,
        fit_model,
        load_model,
        predict_lineup,
        save_model,
    )
    from dota_items.modeling.synthetic_foundation import synthetic_snapshot
    from dota_items.storage import digest

    if args.command == "demo":
        if args.output.exists():
            parser.error("Output already exists")
        snapshot = synthetic_snapshot()
        if args.task_id:
            snapshot["schema_version"] = "purchase-log-modeling-snapshot/2"
            contract = task_contract(args.task_id)
            snapshot["task"]["contract"] = contract
            if args.task_id == WHOLE_LOG_TASK_ID:
                snapshot["task"].update(
                    window=None,
                    scope="whole_available_source_log",
                    candidate_items=contract["labels"]["candidate_items"],
                )
                for row in snapshot["samples"]:
                    row["labels"] = [row["match_id"] % 2] * 11
                    row["label_mask"] = [True] * 11
        root = Path(__file__).resolve().parents[1]
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)
        artifact = fit_model(
            adapt_snapshot(snapshot),
            family=args.family,
            source_sha256=digest(snapshot),
            code_revision=revision + ("-dirty" if dirty else ""),
        )
        save_model(args.output, artifact)
        loaded = load_model(args.output, expected_preprocessing=snapshot["preprocessing"])
        result = predict_lineup(loaded, snapshot["samples"][0]["features"])
        print(json.dumps({"synthetic": True, "performance_evidence": False, **result}, indent=2))
    else:
        expected = task_contract(args.task_id) if args.task_id else None
        print(
            json.dumps(
                predict_lineup(
                    load_model(args.model, expected_task_contract=expected),
                    json.loads(args.lineup.read_text(encoding="utf-8")),
                    expected_task_contract=expected,
                ),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
