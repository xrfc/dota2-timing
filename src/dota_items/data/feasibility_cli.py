"""Audit local match JSON, optionally fetching explicitly requested public matches."""

import argparse
import json
from pathlib import Path

import httpx

from dota_items.data.feasibility import AuditConfig, audit_paths
from dota_items.data.feasibility_sampling import freeze_plan, verify_plan
from dota_items.data.patch_time import load_patch_window
from dota_items.storage import json_bytes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path)
    parser.add_argument("--match-id", action="append", type=int, default=[])
    parser.add_argument("--cache", type=Path, default=Path("data/feasibility/matches"))
    parser.add_argument("--window-start", type=int, default=0)
    parser.add_argument("--window-end", type=int, default=1800)
    parser.add_argument("--candidate", action="append")
    parser.add_argument("--discovery", type=Path, help="saved discovery JSON for plan verification")
    parser.add_argument(
        "--freeze-plan", type=Path, help="write a new plan without fetching details"
    )
    parser.add_argument("--plan", type=Path, help="execute a frozen plan; requires --discovery")
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--take", type=int, default=10)
    parser.add_argument("--offline", action="store_true", help="plan execution uses cache only")
    parser.add_argument("--patch-receipt", type=Path, help="hash-bound official release snapshot")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="offline, masked sample rehearsal; exits 4 when held",
    )
    parser.add_argument("--output", type=Path, help="new JSON file only; default stdout")
    parser.add_argument(
        "--verify-preflight", type=Path, help="replay a saved preview offline; remains held"
    )
    args = parser.parse_args(argv)
    if args.verify_preflight:
        if args.preflight or not (args.plan and args.offline and args.patch_receipt):
            parser.error("verification requires plan/offline/patch-receipt, without --preflight")
    if args.preflight and not (args.plan and args.offline and args.patch_receipt):
        parser.error("preflight requires --plan, --offline and --patch-receipt")
    if not args.inputs and not args.match_id and not args.plan and not args.freeze_plan:
        parser.error("supply local inputs or --match-id")
    if args.plan or args.freeze_plan:
        if not args.discovery or args.inputs or args.match_id or (args.plan and args.freeze_plan):
            parser.error("plan mode requires discovery and cannot mix other input modes")
        if args.plan and (
            args.candidate
            or args.window_start != 0
            or args.window_end != 1800
            or args.skip != 0
            or args.take != 10
        ):
            parser.error("execution uses the frozen config; do not override plan parameters")
    elif args.discovery or args.offline or args.skip != 0 or args.take != 10:
        parser.error("discovery, offline and slice options require plan mode")
    if args.freeze_plan and (args.output or args.offline or args.patch_receipt):
        parser.error("freeze mode writes only the sampling plan")
    if any(mid <= 0 for mid in args.match_id):
        parser.error("match IDs must be positive")
    try:
        values = {"window_start": args.window_start, "window_end": args.window_end}
        if args.candidate is not None:
            values["candidate_items"] = args.candidate
        config = AuditConfig(**values)
        if args.freeze_plan:
            plan = freeze_plan(args.discovery, config, skip=args.skip, take=args.take)
            args.freeze_plan.parent.mkdir(parents=True, exist_ok=True)
            with args.freeze_plan.open("xb") as stream:
                stream.write(json_bytes(plan.model_dump(mode="json")))
            return 0
        plan_hash = None
        if args.plan:
            plan, plan_hash = verify_plan(args.plan, args.discovery)
            config = plan.audit_config
            args.match_id = plan.match_ids
        patch_window = (
            load_patch_window(args.patch_receipt, config.requested_patch)
            if args.patch_receipt
            else None
        )
        if args.output and args.output.exists():
            raise ValueError("output exists; choose a new path")
    except (ValueError, OSError):
        parser.error(
            "invalid config, plan, evidence or existing output; check input files and paths"
        )
    if args.preflight or args.verify_preflight:
        from dota_items.data.lineup_preflight import build_preflight, verify_preflight

        try:
            sources = (args.plan, args.discovery, args.cache, args.patch_receipt)
            report = (
                verify_preflight(args.verify_preflight, *sources)
                if args.verify_preflight
                else build_preflight(*sources)
            )
            _emit(report, args.output)
        except (OSError, ValueError):
            parser.error("preflight failed; check evidence and choose a new output path")
        return 4  # Preparation preview remains held, never training admission.
    paths, failures, expected_ids = list(args.inputs), [], {}
    for mid in args.match_id:
        from dota_items.sources.opendota import fetch_match

        try:
            path = args.cache / f"{mid}.json" if args.offline else fetch_match(mid, args.cache)
            paths.append(path)
            expected_ids[path] = mid
        except (OSError, ValueError, httpx.HTTPError, httpx.InvalidURL) as error:
            failures.append(
                {
                    "input": f"opendota:{mid}",
                    "match_id": mid,
                    "status": "unavailable",
                    "training_allowed": False,
                    "reasons": ["fetch_failed"],
                    "error_type": type(error).__name__,
                }
            )
    report = audit_paths(
        paths, config, failures=failures, patch_window=patch_window, expected_ids=expected_ids
    )
    if args.plan:
        report["sampling"] = {"plan_sha256": plan_hash, **plan.model_dump(mode="json")}
        order = {mid: i for i, mid in enumerate(plan.match_ids)}
        report["results"].sort(
            key=lambda row: order[row.get("requested_match_id", row["match_id"])]
        )
    try:
        _emit(report, args.output)
    except OSError:
        parser.error("could not write report; existing files are never overwritten")
    # A held report is successful diagnostics, not successful training admission.
    return (
        3
        if any(r["status"] in {"invalid", "unavailable", "conflict"} for r in report["results"])
        else 0
    )


def _emit(report, output):
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as stream:
            stream.write(json_bytes(report))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
