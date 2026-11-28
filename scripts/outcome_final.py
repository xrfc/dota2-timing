"""Freeze full-development models, prepare U133 held games, and score the U191 holdout once."""

import argparse
import json
import platform
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
from pathlib import Path

import joblib
from lane_study import SEED, load_rows, summarize
from lane_study_data import candidates, derive_batch, file_hash, fold_for, match_rows
from outcome_domains import domain_match
from outcome_labels import label_match
from outcome_values import DOMAINS, population_summary, read_dataset, score
from threadpoolctl import threadpool_limits

from dota_items.data.awareness_split import is_holdout
from dota_items.storage import now, read_json, write_json
from scripts.lane_study_baselines import fit_behavior, fit_outcomes
from scripts.lane_study_sequence import fit_predict

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
WORK = REPORTS / "outcome-final-u191"
FREEZE = ROOT / "docs/acceptance/outcome-u191-freeze.json"
SOURCES = (
    "scripts/outcome_final.py",
    "scripts/outcome_values.py",
    "scripts/outcome_labels.py",
    "scripts/outcome_domains.py",
    "scripts/lane_study.py",
    "scripts/lane_study_data.py",
    "scripts/lane_study_baselines.py",
    "scripts/lane_study_sequence.py",
    "scripts/detect_ganks.py",
    "scripts/extract_creeps.py",
    "scripts/lane_decision_review.py",
    "src/dota_items/data/awareness_split.py",
    "src/dota_items/data/death_risk.py",
    "src/dota_items/data/gank_depth.py",
    "src/dota_items/data/gank_events.py",
    "src/dota_items/data/lane_decisions.py",
    "src/dota_items/data/vision_sim.py",
    "src/dota_items/data/unit_state.py",
    "src/dota_items/storage.py",
    "src/dota_items/sources/gem_capture_creeps.py",
    "src/dota_items/sources/gem_capture_extras.py",
    "src/dota_items/sources/gem_capture_v3.py",
    "src/dota_items/sources/gem_capture.py",
    "src/dota_items/sources/gem_replay.py",
    "knowledge/awareness/map-zones-v1.json",
    "knowledge/awareness/save-means-v2.json",
)


def verify(root, hashes):
    for name, expected in hashes.items():
        if file_hash(root / name) != expected:
            raise ValueError(f"frozen input changed: {name}")


def versions():
    return {
        "python": platform.python_version(),
        **{k: version(k) for k in ("numpy", "scipy", "scikit-learn", "joblib", "gem-dota")},
    }


def check_freeze(args):
    if file_hash(FREEZE) != args.freeze_sha256:
        raise ValueError("wrong freeze digest")
    frozen = read_json(FREEZE)
    verify(ROOT, frozen["sources"])
    verify(WORK, frozen["models"])
    verify(args.map_dir, frozen["map"])
    verify(args.compat, frozen["compat"])
    if versions() != frozen["versions"]:
        raise ValueError("changed inference environment")
    return frozen


def balanced_rankings(records, balance_at):
    """Descriptive sensitivity subgroup fixed on development covariates."""
    return dict(
        Counter(
            r["ranking"]
            for r in records
            if r["overlap_reason"] is None and balance_at(r)["after"] <= 0.25
        )
    )


def freeze(args):
    if FREEZE.exists() or WORK.exists():
        raise FileExistsError("U191 freeze already exists")
    WORK.mkdir(parents=True)
    models = {}
    dev = {}
    for domain in DOMAINS:
        run = REPORTS / "outcome-values" / domain
        ds = (
            REPORTS / "outcome-labels" if domain == "wave" else REPORTS / "outcome-domains" / domain
        )
        _, digest = read_dataset(ds, domain)
        result = read_json(run / "summary.json")
        baseline = run / "development.joblib"
        if (
            digest != result["rows_sha256"]
            or result["model_sha256"] != file_hash(baseline)
            or result["source_sha256"] != file_hash(ROOT / "scripts/outcome_values.py")
        ):
            raise ValueError(f"development evidence changed for {domain}")
        name = domain + ".joblib"
        (WORK / name).write_bytes(baseline.read_bytes())
        models[name] = file_hash(WORK / name)
        dev[domain] = {
            k: result[k]
            for k in (
                "eligible",
                "matches",
                "unsupported_fraction",
                "expected",
                "factual",
                "rows_sha256",
            )
        }
        predictions = run / "predictions.jsonl"
        if file_hash(predictions) != result["predictions_sha256"]:
            raise ValueError(f"development predictions changed for {domain}")
        with predictions.open() as stream:
            dev[domain]["balanced_strata_rankings"] = balanced_rankings(
                map(json.loads, stream),
                lambda r, folds=result["folds"]: folds[str(r["fold"])]["training_strata"][
                    str(r["stratum"])
                ]["balance"],
            )
    lane = REPORTS / "outcome-dev"
    rows = load_rows(lane / "rows.jsonl")
    if read_json(lane / "manifest.json")["rows_sha256"] != file_hash(lane / "rows.jsonl"):
        raise ValueError("wave rows changed")
    outcomes = [r for r in rows if r["outcome_eligible"]]
    behavior = [r for r in rows if r["behavior_eligible"]]
    challengers = {}
    refs = {}
    for stage, fn, data in (
        ("baseline", fit_outcomes, outcomes),
        ("behavior", fit_behavior, behavior),
        ("sequence", fit_predict, outcomes),
    ):
        _, fitted = fn(data, data[:8], SEED)
        challengers.update(fitted)
        result = read_json(lane / stage / "summary.json")
        refs.update({k: v["all"] for k, v in result["metrics"].items()})
    joblib.dump(challengers, WORK / "wave-reference.joblib")
    models["wave-reference.joblib"] = file_hash(WORK / "wave-reference.joblib")
    compat_files = [
        "manifest.json",
        *(str(p.relative_to(args.compat)) for p in sorted((args.compat / "gem").rglob("*.py"))),
    ]
    write_json(
        FREEZE,
        {
            "schema": "u191-final/1",
            "frozen_at_utc": now(),
            "decision": "U191",
            "versions": versions(),
            "sources": {k: file_hash(ROOT / k) for k in SOURCES},
            "map": {k: file_hash(args.map_dir / k) for k in ("mapdata.json", "elevationdata.json")},
            "compat": {k: file_hash(args.compat / k) for k in compat_files},
            "models": models,
            "development": dev,
            "development_wave_reference": refs,
            "metrics": {
                "overlap": "unsupported / outcome-eligible opportunities",
                "balanced_strata": "rank counts at max absolute postweight training SMD <= 0.25",
                "factual": "Brier for death and arrival; MAE otherwise, on supported observations",
                "comparison": "held minus development OOF, same domain, target and estimator",
                "behavior": "log loss and per-action recall",
                "reference": "hits MAE, death Brier/AP",
            },
            "holdout": {
                "split": "U133",
                "parsed_games": 337,
                "wave_min_rank": 70,
                "jungle_support_min_rank": 60,
                "once_marker": "reports/outcome-final-u191/evaluation-started.json",
            },
        },
    )
    print("frozen", file_hash(FREEZE), flush=True)


def replay_exclusion(exc, mid):
    msg = str(exc)
    if isinstance(exc, EOFError):
        return "unexpected end of replay input"
    if msg.startswith((f"{mid}: non-increasing", f"{mid}: incomplete")):
        return msg
    raise exc


def held_job(job):
    mid, root, map_dir, extras = job
    if not is_holdout(mid):
        raise ValueError("development match supplied to final preparation")
    by_domain = {k: [] for k in DOMAINS}
    excluded = {}
    try:
        extra_domains = domain_match(root, mid, holdout=True)
        for r in extra_domains:
            by_domain[r["domain"]].append(r)
    except (ValueError, EOFError) as exc:
        excluded["jungle"] = excluded["support"] = replay_exclusion(exc, mid)
    if extras is not None:
        try:
            wave = match_rows((mid, root, map_dir, extras), holdout=True)
            by_domain["wave"] = label_match(root, mid, wave)
        except (ValueError, EOFError) as exc:
            excluded["wave"] = replay_exclusion(exc, mid)
    return mid, by_domain, excluded


def prepare(args):
    frozen = check_freeze(args)
    target = WORK / "prepared"
    if target.exists() or (WORK / "evaluation-started.json").exists():
        raise FileExistsError("held samples already published or evaluated")
    ready, missing = candidates(args.root, holdout=True)
    all_ready, all_missing = candidates(args.root, min_rank=60, holdout=True)
    ids = sorted(all_ready + all_missing)
    if len(ids) != frozen["holdout"]["parsed_games"] or not all(map(is_holdout, ids)):
        raise ValueError("unexpected U133 cohort")
    # Keep extraction separate from scoring. A failed preparation never opens the models.
    with tempfile.TemporaryDirectory(dir=WORK) as tmp:
        tmp = Path(tmp)
        extras = {m: args.root for m in ready}
        errors = {}
        if missing:
            expanded, reject = derive_batch(
                args.root, tmp / "expanded", missing, args.extract_workers, args.compat
            )
            extras.update({m: tmp / "expanded" for m in expanded})
            errors.update({m: {"wave": e} for m, e in reject.items()})
        rows = {k: [] for k in DOMAINS}
        with ProcessPoolExecutor(args.workers) as pool:
            jobs = ((m, args.root, args.map_dir, extras.get(m)) for m in ids)
            for i, (mid, domains, excluded) in enumerate(pool.map(held_job, jobs), 1):
                if excluded:
                    errors.setdefault(mid, {}).update(excluded)
                for domain, part in domains.items():
                    rows[domain].extend(part)
                if i % 50 == 0:
                    print(i, "held games prepared", flush=True)
        folder = tmp / "prepared"
        folder.mkdir()
        files = {}
        for name, part in rows.items():
            verify_held_rows(part, set(ids))
            path = folder / (name + ".jsonl")
            with path.open("x") as stream:
                for row in part:
                    print(json.dumps(row, allow_nan=False), file=stream)
            files[path.name] = file_hash(path)
        write_json(
            folder / "manifest.json",
            {
                "matches": ids,
                "wave_candidates": sorted(ready + missing),
                "excluded": errors,
                "files": files,
                "freeze_sha256": args.freeze_sha256,
            },
        )
        folder.rename(target)


def verify_held_rows(rows, ids):
    seen = set()
    for r in rows:
        key = (r["match"], r["hero"], r["t"])
        if (
            key[0] not in ids
            or not is_holdout(key[0])
            or r["fold"] != fold_for(key[0])
            or key in seen
        ):
            raise ValueError("unexpected or duplicate held sample")
        seen.add(key)


def claim_evaluation(path, freeze_path, digest):
    if file_hash(freeze_path) != digest:
        raise ValueError("changed freeze at scoring")
    with path.open("x") as stream:
        print(json.dumps({"freeze_sha256": digest, "started_at_utc": now()}), file=stream)


def reference_scores(models, wave):
    results = {}
    for name, model in models.items():
        behavior = name in ("logistic", "frequency")
        part = [r for r in wave if r["behavior_eligible" if behavior else "outcome_eligible"]]
        predicted = model.predict(part)
        rec = []
        for i, r in enumerate(part):
            fields = {"action": r["action"], "match": r["match"]}
            if behavior:
                fields["p_farm"] = float(predicted[i])
            else:
                fields.update(
                    hits_pred=float(predicted[0][i]),
                    p_death=float(predicted[1][i]),
                    hits=r["hits"],
                    death=r["death"],
                )
            rec.append(fields)
        results[name] = summarize(rec, behavior)
    return results


def evaluate(args):
    frozen = check_freeze(args)
    prepared = WORK / "prepared"
    manifest = read_json(prepared / "manifest.json")
    if manifest["freeze_sha256"] != args.freeze_sha256:
        raise ValueError("prepared dataset belongs to another freeze")
    verify(prepared, manifest["files"])
    datasets = {}
    for domain in DOMAINS:
        rows = [
            json.loads(line) for line in (prepared / (domain + ".jsonl")).read_text().splitlines()
        ]
        ids = manifest["wave_candidates" if domain == "wave" else "matches"]
        verify_held_rows(rows, set(ids))
        datasets[domain] = rows
    claim_evaluation(WORK / "evaluation-started.json", FREEZE, args.freeze_sha256)
    with tempfile.TemporaryDirectory(dir=WORK) as tmp:
        results = {}
        folder = Path(tmp) / "results"
        folder.mkdir()
        for domain, (arms, targets) in DOMAINS.items():
            rows = datasets[domain]
            eligible = [r for r in rows if r["outcome_eligible"]]
            model = joblib.load(WORK / (domain + ".joblib"))
            preds = score(model, eligible)
            with (folder / (domain + ".jsonl")).open("x") as stream:
                for row in preds:
                    print(json.dumps(row, allow_nan=False), file=stream)
            stats = population_summary(preds, arms, targets)
            dev = frozen["development"][domain]
            differences = {}
            for key in targets:
                held = stats["factual"][key]["all"]["value"]
                oof = dev["factual"][key]["all"]["value"]
                differences[key] = None if None in (held, oof) else held - oof
            results[domain] = {
                "opportunities": len(rows),
                "actions": dict(Counter(r["action"] for r in rows)),
                **stats,
                "factual_gap": differences,
                "balanced_strata_rankings": balanced_rankings(
                    preds, lambda r, strata=model["strata"]: strata[r["stratum"]]["balance"]
                ),
            }
        result = {
            "schema": "u191-held-result/1",
            "evaluation": read_json(WORK / "evaluation-started.json"),
            "freeze_sha256": args.freeze_sha256,
            "cohort_sha256": file_hash(prepared / "manifest.json"),
            "held_games": len(manifest["matches"]),
            "wave_candidates": len(manifest["wave_candidates"]),
            "exclusions": dict(Counter(k for d in manifest["excluded"].values() for k in d)),
            "domains": results,
            "wave_reference": reference_scores(
                joblib.load(WORK / "wave-reference.joblib"), datasets["wave"]
            ),
        }
        write_json(folder / "summary.json", result)
        folder.rename(WORK / "results")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("freeze", "prepare", "evaluate"))
    for k in ("root", "map-dir", "compat"):
        ap.add_argument("--" + k, type=Path, required=True)
    ap.add_argument("--freeze-sha256")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--extract-workers", type=int, default=8)
    args = ap.parse_args()
    if args.command != "freeze" and not args.freeze_sha256:
        ap.error("pass the recorded pre-evaluation freeze digest")
    with threadpool_limits(limits=1):
        {"freeze": freeze, "prepare": prepare, "evaluate": evaluate}[args.command](args)


if __name__ == "__main__":
    main()
