"""Resumable, read-only public-match collection. Candidates are never training admission.

Each discovery page is frozen before details. Rejected raw files created by this
run may be deleted only after the complete audit and cleanup receipt are saved.
Historical caches are never touched. No parse jobs or paid services are requested.
"""

import argparse
import json
import time
from pathlib import Path

import httpx

from dota_items.data.feasibility import AuditConfig
from dota_items.data.feasibility_sampling import freeze_plan, verify_plan
from dota_items.data.lineup_preflight import build_preflight
from dota_items.sources.collection_history import filter_discovery
from dota_items.sources.opendota import fetch_match
from dota_items.storage import file_hash, json_bytes, now, read_json


def save_new(path, value):
    with path.open("xb") as stream:
        stream.write(json_bytes(value))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--exclusions", type=Path, required=True)
    parser.add_argument("--target", type=int, default=1000)
    parser.add_argument("--max-batches", type=int, default=100)
    parser.add_argument("--delete-rejected", action="store_true")
    args = parser.parse_args()
    if args.target < 1 or args.max_batches < 1:
        parser.error("positive target and batch limit required")
    history = read_json(args.exclusions)
    excluded = set(history["excluded_match_ids"])
    root = args.root
    root.mkdir(parents=True, exist_ok=True)
    receipt = Path("knowledge/evidence/feasibility-2026-10-13/receipt.json")
    rules = {
        "schema_version": "purchase-candidate-collection/2",
        "target_candidates": args.target,
        "max_batches": args.max_batches,
        "initial_upper_match_id_exclusive": history["initial_upper_match_id_exclusive"],
        "exclusions_sha256": file_hash(args.exclusions),
        "history_implementation_sha256": file_hash(
            Path("src/dota_items/sources/collection_history.py")
        ),
        "lower_match_id_exclusive": 9000000000,
        "query_id_span": 1000000,
        "min_average_rank_hint": 70,
        "lobby_type": 7,
        "game_mode": 22,
        "page_size": 100,
        "audit_config": AuditConfig().model_dump(mode="json"),
        "patch_receipt_sha256": file_hash(receipt),
        "delete_rejected": args.delete_rejected,
        "collector_sha256": file_hash(Path(__file__)),
        "training_allowed": False,
        "limitations": [
            "Rank is a discovery hint, not independently verified player skill or carry role.",
            "Kept means preflight candidate, not verified coverage or admitted labels.",
            "Deleted payloads cannot be replayed; audit, hashes and receipts remain.",
            "Only this run's rejected payloads are eligible for deletion.",
        ],
    }
    config_path = root / "collection.json"
    if config_path.exists():
        if json_bytes(read_json(config_path)) != json_bytes(rules):
            raise ValueError("Collection config/code changed; use a new directory")
    else:
        save_new(config_path, rules)
    cursor = rules["initial_upper_match_id_exclusive"]
    kept, attempted = [], 0
    # Per-client choice only: bypass malformed inherited proxy URLs without editing config.
    with httpx.Client(trust_env=False, timeout=40, follow_redirects=False) as client:
        for number in range(1, args.max_batches + 1):
            batch = root / f"batch-{number:04d}"
            batch.mkdir(exist_ok=True)
            discovery = batch / "discovery.json"
            if not discovery.exists():
                lower = max(rules["lower_match_id_exclusive"], cursor - rules["query_id_span"])
                sql = (
                    "SELECT match_id,start_time,duration,avg_rank_tier,num_rank_tier,"
                    "lobby_type,game_mode FROM public_matches "
                    f"WHERE match_id>{lower} AND match_id<{cursor} "
                    "AND duration>=1800 AND (8=ANY(radiant_team) OR 8=ANY(dire_team)) "
                    "AND lobby_type=7 AND game_mode=22 AND avg_rank_tier>=70 "
                    "ORDER BY match_id DESC LIMIT 100"
                )
                response = client.get("https://api.opendota.com/api/explorer", params={"sql": sql})
                response.raise_for_status()
                result = response.json()
                if result.get("err") or not isinstance(result.get("rows"), list):
                    raise ValueError("Discovery query failed")
                selected = filter_discovery(result["rows"], excluded, lower, cursor)
                with (batch / "response.json").open("xb") as stream:
                    stream.write(response.content)
                save_new(
                    batch / "receipt.json",
                    {
                        "sql": sql,
                        "fetched_at": now(),
                        "source": "https://api.opendota.com/api/explorer",
                        "sha256": file_hash(batch / "response.json"),
                        "representation": "HTTP response body bytes",
                        "next_cursor_if_empty": min(
                            (r["match_id"] for r in result["rows"]), default=lower
                        ),
                        "query_lower": lower,
                        "query_upper": cursor,
                    },
                )
                save_new(discovery, selected)
            rows = read_json(discovery)
            source_receipt = read_json(batch / "receipt.json")
            if file_hash(batch / "response.json") != source_receipt["sha256"]:
                raise ValueError("Discovery response hash changed")
            if json_bytes(
                filter_discovery(
                    read_json(batch / "response.json")["rows"],
                    excluded,
                    source_receipt["query_lower"],
                    source_receipt["query_upper"],
                )
            ) != json_bytes(rows):
                raise ValueError("Discovery rows differ from response")
            if not rows:
                cursor = source_receipt["next_cursor_if_empty"]
                if cursor <= rules["lower_match_id_exclusive"]:
                    break
                continue
            plan_path = batch / "plan.json"
            if not plan_path.exists():
                save_new(
                    plan_path,
                    freeze_plan(discovery, AuditConfig(), skip=0, take=len(rows)).model_dump(
                        mode="json"
                    ),
                )
            plan, _ = verify_plan(plan_path, discovery)
            cursor = min(plan.match_ids)
            cache = batch / "matches"
            done = batch / "complete.json"
            if not done.exists():
                for mid in plan.match_ids:
                    failure = batch / f"failure-{mid}.json"
                    if (cache / f"{mid}.json").exists() or failure.exists():
                        continue
                    started = time.monotonic()
                    try:
                        fetch_match(mid, cache, client=client)
                    except (OSError, ValueError, httpx.HTTPError) as error:
                        save_new(
                            failure,
                            {
                                "match_id": mid,
                                "error_type": type(error).__name__,
                                "training_allowed": False,
                            },
                        )
                    time.sleep(max(0, 1.1 - (time.monotonic() - started)))
                report_path = batch / "preflight.json"
                if not report_path.exists():
                    save_new(report_path, build_preflight(plan_path, discovery, cache, receipt))
                report = read_json(report_path)
                cleanup_path = batch / "cleanup.json"
                if not cleanup_path.exists():
                    removed = []
                    for exclusion in report["exclusions"]:
                        mid = exclusion["requested_match_id"]
                        path = cache / f"{mid}.json"
                        if path.exists():
                            manifest = path.with_suffix(".manifest.json")
                            removed.append(
                                {
                                    "match_id": mid,
                                    "sha256": file_hash(path),
                                    "reasons": exclusion["reasons"],
                                    "manifest": read_json(manifest),
                                }
                            )
                    save_new(
                        cleanup_path,
                        {
                            "authorized": args.delete_rejected,
                            "payloads": removed,
                            "report_sha256": file_hash(report_path),
                        },
                    )
                cleanup = read_json(cleanup_path)
                if cleanup["report_sha256"] != file_hash(report_path):
                    raise ValueError("Cleanup audit changed")
                if args.delete_rejected:
                    for removed in cleanup["payloads"]:
                        path = cache / f"{removed['match_id']}.json"
                        if path.exists():
                            if file_hash(path) != removed["sha256"]:
                                raise ValueError("Rejected payload changed before cleanup")
                            path.unlink()
                        # Keep the small acquisition manifest even after raw deletion.
                save_new(
                    done,
                    {
                        "report_sha256": file_hash(report_path),
                        "cleanup_sha256": file_hash(cleanup_path),
                    },
                )
            report = read_json(batch / "preflight.json")
            completion = read_json(done)
            if completion["report_sha256"] != file_hash(batch / "preflight.json"):
                raise ValueError("Completed report changed")
            if completion["cleanup_sha256"] != file_hash(batch / "cleanup.json"):
                raise ValueError("Completed cleanup receipt changed")
            for sample in report["samples"]:
                path = cache / f"{sample['match_id']}.json"
                if file_hash(path) != sample["source_sha256"]:
                    raise ValueError("Retained source changed")
                kept.append(
                    {
                        "match_id": sample["match_id"],
                        "path": str(path),
                        "sha256": sample["source_sha256"],
                    }
                )
            attempted += len(plan.match_ids)
            summary = {
                "schema_version": "purchase-collection-progress/1",
                "attempted": attempted,
                "retained_candidates": len(kept),
                "target": args.target,
                "training_admitted": 0,
                "training_allowed": False,
                "candidates": kept,
                "last_complete_batch": number,
            }
            temp = root / "progress.tmp"
            temp.write_bytes(json_bytes(summary))
            temp.replace(root / "progress.json")
            print(json.dumps({k: v for k, v in summary.items() if k != "candidates"}), flush=True)
            if len(kept) >= args.target:
                break
    if len(kept) < args.target:
        raise RuntimeError("Search range or batch limit exhausted before target")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
