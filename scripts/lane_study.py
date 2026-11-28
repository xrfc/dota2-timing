"""Run a frozen development cohort through one lane study stage."""

import argparse
import hashlib
import importlib
import json
import platform
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
import scipy
import sklearn
from sklearn.metrics import average_precision_score, log_loss
from threadpoolctl import threadpool_limits

from dota_items.data.awareness_split import is_holdout

SEED = 20261122


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def load_rows(path):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    games, identities = {}, set()
    for row in rows:
        mid, fold = row["match"], row["fold"]
        key = mid, row["hero"], row["t"]
        if is_holdout(mid) or fold not in range(5) or games.setdefault(mid, fold) != fold:
            raise ValueError("reserved match or inconsistent fold")
        if key in identities:
            raise ValueError("duplicate sample")
        identities.add(key)
    return rows


def summarize(rows, behavior):
    result = {
        "cases": len(rows),
        "matches": len({r["match"] for r in rows}),
        "actions": Counter(r["action"] for r in rows),
    }
    if not rows:
        return result
    if behavior:
        y = np.array([r["action"] == "farm" for r in rows])
        p = np.array([r["p_farm"] for r in rows])
        result.update(
            log_loss=float(log_loss(y, p, labels=[False, True])),
            farm_recall=float(np.mean(p[y] >= 0.5)) if y.any() else None,
            retreat_recall=float(np.mean(p[~y] < 0.5)) if (~y).any() else None,
        )
    else:
        risk = np.array([r["p_death"] for r in rows])
        died = np.array([r["death"] for r in rows])
        bands = np.minimum((risk * 5).astype(int), 4)
        result.update(
            deaths=int(died.sum()),
            hits_mae=float(np.mean([abs(r["hits"] - r["hits_pred"]) for r in rows])),
            death_brier=float(np.mean((risk - died) ** 2)),
            death_ap=float(average_precision_score(died, risk)) if len(set(died)) == 2 else None,
            false_alerts_per_represented_match=float(
                np.sum((risk >= 0.5) & (died == 0)) / result["matches"]
            ),
            calibration=[
                {
                    "from": int(i) / 5,
                    "count": int((bands == i).sum()),
                    "predicted": float(risk[bands == i].mean()),
                    "observed": float(died[bands == i].mean()),
                }
                for i in sorted(set(bands))
            ],
        )
    return result


def paired(first, second):
    """Macro-average paired match errors; bootstrap entire games."""

    def errors(rows):
        values = {
            (r["match"], r["hero"], r["t"], r["fold"], r["death"], r["hits"]): np.array(
                [abs(r["hits"] - r["hits_pred"]), (r["death"] - r["p_death"]) ** 2]
            )
            for r in rows
        }
        if len(values) != len(rows):
            raise ValueError("duplicate prediction key")
        return values

    a, b = errors(first), errors(second)
    if a.keys() != b.keys() or not a:
        raise ValueError("comparison requires identical nonempty cases")
    by_game = defaultdict(list)
    for key in sorted(a):
        by_game[key[0]].append(a[key] - b[key])
    diff = np.array([np.mean(values, axis=0) for values in by_game.values()])
    rng = np.random.default_rng(SEED)
    boot = np.array(
        [diff[rng.integers(len(diff), size=len(diff))].mean(axis=0) for _ in range(2000)]
    )
    return {
        name: {
            "difference": float(diff[:, i].mean()),
            "ci95": np.quantile(boot[:, i], [0.025, 0.975]).tolist(),
        }
        for i, name in enumerate(("hits_mae", "death_brier"))
    }


def run(root, stage, dest):
    rows_path, manifest = root / "rows.jsonl", root / "manifest.json"
    inputs = {p.name: digest(p) for p in (rows_path, manifest)}
    behavior = stage == "behavior"
    module = importlib.import_module(
        "scripts.lane_study_sequence" if stage == "sequence" else "scripts.lane_study_baselines"
    )
    fit = getattr(
        module,
        {"baseline": "fit_outcomes", "behavior": "fit_behavior", "sequence": "fit_predict"}[stage],
    )
    rows = load_rows(rows_path)
    freeze = json.loads(manifest.read_text())
    folds = {int(k): v for k, v in freeze["folds"].items()}
    if (
        len(rows) != freeze["rows"]
        or any(is_holdout(m) for m in folds)
        or any(folds.get(r["match"]) != r["fold"] for r in rows)
        or freeze.get("rows_sha256", inputs["rows.jsonl"]) != inputs["rows.jsonl"]
    ):
        raise ValueError("manifest and sample rows disagree")
    eligible = [r for r in rows if r["behavior_eligible" if behavior else "outcome_eligible"]]
    results = defaultdict(list)
    unsupported = Counter()
    models = {}
    for fold in range(5):
        train = [r for r in eligible if r["fold"] != fold]
        test = [r for r in eligible if r["fold"] == fold]
        if not behavior:
            supported = {r["action"] for r in train}
            unsupported.update(r["action"] for r in test if r["action"] not in supported)
            test = [r for r in test if r["action"] in supported]
        if not test:
            continue
        if not train:
            raise ValueError("training fold is empty")
        preds, artifacts = fit(train, test, SEED + fold)
        for name, predictions in preds.items():
            path = dest / f"{name}-fold{fold}.joblib"
            joblib.dump(artifacts[name], path)
            np.testing.assert_allclose(joblib.load(path).predict(test), predictions)
            models[path.name] = digest(path)
            for i, r in enumerate(test):
                rec = {k: r[k] for k in ("match", "hero", "t", "fold", "action", "recent_damage")}
                if behavior:
                    rec["p_farm"] = float(predictions[i])
                else:
                    rec.update(
                        hits=r["hits"],
                        death=r["death"],
                        hits_pred=float(predictions[0][i]),
                        p_death=float(predictions[1][i]),
                    )
                results[name].append(rec)
    if not results:
        raise ValueError("no eligible cases")
    metrics = {}
    for name, records in results.items():
        metrics[name] = {
            group: summarize(part, behavior)
            for group, part in {
                "all": records,
                "farm": [r for r in records if r["action"] == "farm"],
                "retreat": [r for r in records if r["action"] == "retreat"],
                "no_recent_damage": [r for r in records if not r["recent_damage"]],
            }.items()
        }
    comparisons = {}
    if stage == "sequence":
        baseline = root / "baseline"
        if json.loads((baseline / "summary.json").read_text())["inputs"] != inputs:
            raise ValueError("baseline used different inputs")
        refs = {**json.loads((baseline / "predictions.json").read_text()), **results}
        for name, against in [
            ("temporal_nn", "last_frame_nn"),
            ("temporal_nn", "three_frame_tree"),
            ("temporal_nn", "last_frame_tree"),
            ("three_frame_tree", "last_frame_tree"),
            ("last_frame_tree", "action_mean"),
        ]:
            comparisons[f"{name} minus {against}"] = paired(refs[name], refs[against])
    save(dest / "predictions.json", results)
    save(
        dest / "summary.json",
        {
            "inputs": inputs,
            "metrics": metrics,
            "paired": comparisons,
            "seed": SEED,
            "models": models,
            "unsupported": unsupported,
            "versions": {
                "python": platform.python_version(),
                "sklearn": sklearn.__version__,
                "numpy": np.__version__,
                "scipy": scipy.__version__,
            },
            "sources": {
                p.name: digest(p)
                for p in (
                    Path(__file__),
                    Path(module.__file__),
                    Path(__file__).with_name("lane_study_baselines.py"),
                )
            },
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("baseline", "behavior", "sequence"))
    parser.add_argument("--root", type=Path, default=Path("reports/lane-study"))
    args = parser.parse_args()
    target = args.root / args.stage
    if target.exists():
        parser.error(f"output exists: {target}")
    with tempfile.TemporaryDirectory(dir=args.root) as tmp, threadpool_limits(limits=1):
        folder = Path(tmp) / args.stage
        folder.mkdir()
        run(args.root, args.stage, folder)
        folder.rename(target)


if __name__ == "__main__":
    main()
