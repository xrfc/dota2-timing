"""Deterministic fabricated fixtures; not performance evidence."""

from dota_items.contracts.lineup import columns, encode_lineup, fit_vocabulary
from dota_items.modeling.foundation import ITEMS


def synthetic_snapshot():
    rows = []
    for split, count in (("train", 12), ("validation", 4), ("test", 2)):
        for i in range(count):
            features = {
                "target_hero_id": 8,
                "ally_hero_ids": [8, 1, 2, 3, 4 + i % 2],
                "enemy_hero_ids": [10, 11, 12, 13, 14],
            }
            rows.append(
                {
                    "match_id": len(rows) + 1,
                    "split": split,
                    "features": features,
                    "labels": [i % 2, (i // 2) % 2, 1 - i % 2, 0, i % 2],
                    "label_mask": [True] * 5,
                    "group_id": f"synthetic-{len(rows)}",
                    "role_hint": "synthetic",
                    "source_sha256": "0" * 64,
                }
            )
    vocabulary = fit_vocabulary([r["features"] for r in rows if r["split"] == "train"])
    for row in rows:
        row["encoded_features"] = encode_lineup(row["features"], vocabulary)
    return {
        "schema_version": "purchase-log-modeling-snapshot/1",
        "modeling_ready": True,
        "synthetic": True,
        "task": {
            "target": "source_purchase_log_key_presence",
            "candidate_items": list(ITEMS),
            "window": [0, 1800],
            "negative_means": "absent_from_valid_source_log_only",
            "actual_purchase_ground_truth": False,
        },
        "preprocessing": {
            "fit_split": "train",
            "vocabulary": vocabulary,
            "columns": columns(vocabulary),
        },
        "splits": {
            s: [r["match_id"] for r in rows if r["split"] == s]
            for s in ("train", "validation", "test")
        },
        "samples": rows,
    }
