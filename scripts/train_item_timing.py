"""M2-T3/T4: train item-timing models on the M1 snapshot and run the frozen evaluation.

Writes JSON only (coefficients, metrics); never pickles. Output directory must be new.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.modeling import item_timing
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = ("scripts/train_item_timing.py", "src/dota_items/modeling/item_timing.py")


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _value(text):
    if text == "":
        return None
    if text in ("true", "false"):
        return text == "true"
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return [{k: _value(v) for k, v in row.items()} for row in csv.DictReader(stream)]


def load_snapshot(snapshot):
    manifest = parse_source_json(read_source_bytes(snapshot / "manifest.json"))
    for name, expected in manifest["outputs"].items():
        if file_hash(snapshot / name) != expected:
            raise ValueError(f"Snapshot file changed: {name}")
    players = read_csv(snapshot / "players.csv")
    purchases = [{**p, "item": str(p["item"])} for p in read_csv(snapshot / "purchases.csv")]
    split = parse_source_json(read_source_bytes(snapshot / "split.json"))
    return manifest, players, purchases, split


def summarize(results):
    heroes = {}
    for r in results:
        h = heroes.setdefault(r["hero_id"], {"rows": 0, "model_better": 0, "modeled": 0})
        h["rows"] += 1
        h["modeled"] += r["modeled"]
        h["model_better"] += r["display"] == "model"
        for key in ("brier_baseline", "brier_model"):
            h.setdefault(key + "_sum", 0.0)
            h[key + "_sum"] += r[key]
    for h in heroes.values():
        for key in ("brier_baseline", "brier_model"):
            h["macro_" + key] = h.pop(key + "_sum") / h["rows"]
    return heroes


def run(snapshot, output, revision=1, repo=ROOT):
    snapshot, output = Path(snapshot), Path(output)
    if output.exists():
        raise ValueError("Output exists")
    implementation = {name: file_hash(repo / name) for name in IMPLEMENTATION}
    manifest, players, purchases, split = load_snapshot(snapshot)
    samples = item_timing.build_samples(players, purchases)
    train_ids, valid_ids = set(split["train"]), set(split["validation"])
    train = [s for s in samples if s["match_id"] in train_ids]
    valid = [s for s in samples if s["match_id"] in valid_ids]
    if revision == 1:
        vocab = item_timing.fit_vocab(train)
        models = item_timing.fit(train, vocab)
    elif revision == 2:
        r2 = item_timing.REVISION_2
        vocab = item_timing.fit_vocab(train, sides=r2["sides"], min_count=r2["min_count"])
        models = item_timing.fit(train, vocab, c_grid=r2["c_grid"], folds=r2["folds"])
    else:
        raise ValueError("Unknown protocol revision")
    results = item_timing.evaluate(models, valid, vocab)
    if {name: file_hash(repo / name) for name in IMPLEMENTATION} != implementation:
        raise ValueError("Implementation changed during training")
    output.mkdir(parents=True)
    write(
        output / "model.json",
        {
            "schema": "m2-item-timing-model/1",
            "vocab": vocab,
            "hero_items": {f"{h}:{p}": list(v) for (h, p), v in item_timing.HERO_ITEMS.items()},
            "minutes": list(item_timing.MINUTES),
            "entries": {f"{s[0]}:{s[1]}|{i}|{m}": e for (s, i, m), e in models.items()},
        },
    )
    write(output / "results.json", {"rows": results, "by_hero": summarize(results)})
    outputs = {p.name: file_hash(p) for p in output.glob("*.json")}
    write(
        output / "manifest.json",
        {
            "schema": "m2-item-timing-run/1",
            "snapshot": str(snapshot),
            "snapshot_manifest_sha256": hashlib.sha256(
                read_source_bytes(snapshot / "manifest.json")
            ).hexdigest(),
            "train_samples": len(train),
            "validation_samples": len(valid),
            "protocol_revision": revision,
            "protocol": "docs/m2-design.md"
            + (
                " §7 revision 2: second look after validation results (U12)"
                if revision == 2
                else ""
            ),
            "settings": {
                "C": item_timing.C,
                "min_class_count": item_timing.MIN_CLASS_COUNT,
                "bootstrap": item_timing.BOOTSTRAP,
                "seed": item_timing.SEED,
                "revision_2": item_timing.REVISION_2 if revision == 2 else None,
            },
            "implementation": implementation,
            "outputs": outputs,
            "authorization": {1: "U11", 2: "U12"}[revision] + " (user 2026-10-30): this run only",
        },
    )
    return {"train": len(train), "validation": len(valid), "entries": len(models)}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--snapshot", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--revision", type=int, choices=(1, 2), default=1)
    args = cli.parse_args()
    print(json.dumps(run(args.snapshot, args.output, args.revision)))
