"""Offline exploratory lineup features; observations are not admitted labels."""

import argparse
from pathlib import Path

from dota_items.data.lineup_preflight import encode_lineup, fit_vocabulary, lineup_features
from dota_items.storage import file_hash, json_bytes, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = read_json(args.summary)
    if report["schema_version"] != "purchase-collection-summary/1":
        raise ValueError("Expected collection summary")
    sources = {s["match_id"]: s for s in report["sources"]}
    rows = report["audit"]["results"]
    if len(sources) != len(rows) or {r["match_id"] for r in rows} != set(sources):
        raise ValueError("Source / audit identity mismatch")
    for row in rows:
        source = sources[row["match_id"]]
        if file_hash(Path(source["path"])) != source["sha256"] or row["sha256"] != source["sha256"]:
            raise ValueError("Source hash mismatch")
    split_for = {mid: name for name, ids in report["splits"].items() for mid in ids}
    if sum(map(len, report["splits"].values())) != len(rows) or set(split_for) != set(sources):
        raise ValueError("Invalid split membership")
    features = {row["match_id"]: lineup_features(row) for row in rows}
    vocabulary = fit_vocabulary([features[mid] for mid in report["splits"]["train"]])
    items = report["audit"]["config"]["candidate_items"]
    samples = [
        {
            "match_id": row["match_id"],
            "source_sha256": row["sha256"],
            "split": split_for[row["match_id"]],
            "features": features[row["match_id"]],
            "encoded_features": encode_lineup(features[row["match_id"]], vocabulary),
            "observations": row["candidates"],
            "labels": [None] * len(items),
            "label_mask": [False] * len(items),
            "training_allowed": False,
        }
        for row in rows
    ]
    output = {
        "schema_version": "purchase-collection-preview/1",
        "training_allowed": False,
        "summary_sha256": file_hash(args.summary),
        "implementation_sha256": {
            "exporter": file_hash(Path(__file__)),
            "lineup_preflight": file_hash(Path("src/dota_items/data/lineup_preflight.py")),
        },
        "candidate_items": items,
        "vocabulary_fit_split": "train",
        "hero_vocabulary": vocabulary,
        "columns": [
            column
            for side in ("ally", "enemy")
            for column in [*[f"{side}_hero_{h}" for h in vocabulary], f"{side}_unknown_count"]
        ],
        "splits": report["splits"],
        "samples": samples,
        "limitations": [
            "Exploratory splits have known player overlap; not independent evaluation.",
            "Purchase observations are not verified labels; absent events remain unknown.",
            "Role, patch, rank and log coverage evidence remains incomplete.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(json_bytes(output))
    print({"samples": len(samples), "columns": len(output["columns"]), "training_allowed": False})


if __name__ == "__main__":
    main()
