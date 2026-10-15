"""Offline purchase contract diagnostics with verified local item-source receipts."""

import argparse
from collections import Counter
from pathlib import Path

from dota_items.data.purchase_observation import observe_purchases
from dota_items.storage import file_hash, json_bytes, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = read_json(args.summary)
    config = summary["audit"]["config"]
    items = config["candidate_items"]
    package = Path("knowledge/recommendation/7.41f-v1")
    knowledge = read_json(package / "knowledge.json")
    mappings = []
    for key in items:
        receipt = next(s for s in knowledge["sources"] if s["source_id"] == "item-" + key)
        path = package / receipt["file"]
        if file_hash(path) != receipt["sha256"]:
            raise ValueError("Item evidence changed")
        item = read_json(path)["result"]["data"]["items"][0]
        if item["name"] != "item_" + key:
            raise ValueError("Item name mismatch")
        mappings.append(
            {
                "item_key": key,
                "id": item["id"],
                "name": item["name_loc"],
                "source_sha256": receipt["sha256"],
                "source_url": receipt["url"],
            }
        )
    rows, counts, comparisons, conflicts = [], Counter(), Counter(), []
    for source, audit in zip(summary["sources"], summary["audit"]["results"], strict=True):
        path = Path(source["path"])
        if file_hash(path) != source["sha256"] or source["match_id"] != audit["match_id"]:
            raise ValueError("Match source mismatch")
        raw = read_json(path)
        if raw["match_id"] != source["match_id"]:
            raise ValueError("Payload identity mismatch")
        target = next(p for p in raw["players"] if p["player_slot"] == audit["target_slot"])
        observed = observe_purchases(
            target, items, start=config["window_start"], end=config["window_end"]
        )
        counts["matches"] += 1
        counts["log_with_post_window_event"] += observed["has_event_at_or_after_window_end"]
        counts["empty_logs"] += observed["valid_event_count"] == 0
        semantics = audit["semantic_review"]
        counts["role_" + semantics["role_evidence"]["status"]] += 1
        counts["inventory_" + semantics["inventory_log_status"]] += 1
        others_bkb = any(
            any(
                e.get("key") == "black_king_bar"
                and type(e.get("time")) in (int, float)
                and 0 <= e["time"] < 1800
                for e in (p.get("purchase_log") or [])
                if isinstance(e, dict)
            )
            for p in raw["players"]
            if p["player_slot"] != audit["target_slot"]
        )
        counts["other_players_bkb_matches_in_window"] += others_bkb
        for comparison in semantics["aggregate_comparisons"]:
            for field in ("purchase_time", "first_purchase_time", "item_usage"):
                result = comparison[field]
                comparisons[field + ":" + result["status"]] += 1
                if result["status"] == "inconsistent":
                    conflicts.append(
                        {
                            "match_id": raw["match_id"],
                            "item_key": comparison["item_key"],
                            "field": field,
                            **result,
                        }
                    )
        rows.append(
            {
                "match_id": raw["match_id"],
                "source_sha256": source["sha256"],
                "role_hint": semantics["role_evidence"]["status"],
                "observation": observed,
            }
        )
    report = {
        "schema_version": "purchase-observation-audit/1",
        "training_allowed": False,
        "summary_sha256": file_hash(args.summary),
        "knowledge_sha256": file_hash(package / "knowledge.json"),
        "implementation_sha256": {
            "script": file_hash(Path(__file__)),
            "observation": file_hash(Path("src/dota_items/data/purchase_observation.py")),
        },
        "item_mappings": mappings,
        "counts": dict(counts),
        "aggregate_comparisons": dict(comparisons),
        "aggregate_conflicts": conflicts,
        "samples": rows,
        "limitations": [
            "Log absence is not behavior absence; source observation targets are a distinct task.",
            "Post-window events and derived fields do not establish continuous coverage.",
            "Item snapshots identify keys/IDs, not deployed parser or complete versioned recipes.",
            "Role hints remain estimates, never pregame features.",
        ],
    }
    with args.output.open("xb") as stream:
        stream.write(json_bytes(report))
    print(report["counts"])
    print(report["aggregate_comparisons"])


if __name__ == "__main__":
    main()
