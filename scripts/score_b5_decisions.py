"""Score sealed B5 decisions or reproduce the frozen U191 development baseline."""

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from dota_items.data.awareness_split import is_holdout
from dota_items.modeling.awareness.decision_score import (
    ARMS,
    VERSION,
    fingerprint,
    judge,
    metrics,
    seal,
)

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "configs/acceptance/b5-u191-development.json"


def verified_bytes(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"frozen input SHA-256 mismatch: {path}")
    return data


def key(row):
    return row["match"], row["hero"], row["t"]


def decision_view(case):
    """Allowlist input fields so revealing the chosen action or outcome cannot alter the seal."""
    return seal(key(case), case["domain"], case["values"], case["balance_after"])


def check_case(case):
    if not isinstance(case, dict) or case.get("schema") != VERSION:
        raise ValueError("unknown decision score schema")
    snapshot, _ = decision_view(case)
    proposal = case["proposal"]
    return {
        "snapshot_sha256": fingerprint(snapshot),
        "decision_sha256": fingerprint([snapshot, proposal]),
        "verdict": judge(snapshot, proposal),
    }


def score_domain(domain, rows, predictions, summary):
    targets = metrics(domain)
    source = {}
    exclusions = Counter()
    for row in rows:
        mid, _, _ = identity = key(row)
        fold = int.from_bytes(hashlib.sha256(f"lane-study-v1:{mid}".encode()).digest(), "big") % 5
        if identity in source or is_holdout(mid) or row["fold"] != fold:
            raise ValueError("duplicate, reserved match, or wrong development fold")
        source[identity] = row
        if row["action"] == "unknown":
            exclusions["unknown_action"] += 1
        if row["early_death"]:
            exclusions["early_death"] += 1
        if not row["window_complete"]:
            exclusions["truncated"] += 1
    eligible = {k for k, r in source.items() if r["outcome_eligible"]}
    if eligible != {key(p) for p in predictions} or len(predictions) != len(eligible):
        raise ValueError("OOF predictions do not cover exactly the eligible population")
    counts, overlaps = Counter(), Counter()
    error = defaultdict(float)
    pairs, missing = Counter(), Counter()
    examples = {}
    seals = hashlib.sha256()
    for pred in predictions:
        identity = key(pred)
        row = source[identity]
        if row["action"] != pred["action"] or row["fold"] != pred["fold"]:
            raise ValueError("OOF action/fold differs from source")
        if pred["observed"] != {m: row[m] for m in targets}:
            raise ValueError("OOF observation differs from source")
        values = pred["values"]
        balance = None
        if values is not None:
            layer = summary["folds"][str(pred["fold"])]["training_strata"][str(pred["stratum"])]
            if values != {a: layer["arms"][a]["values"] for a in ARMS[domain]}:
                raise ValueError("estimate differs from training fold stratum")
            balance = layer["balance"]["after"]
        snapshot, preference = seal(identity, domain, values, balance)
        if (pred["ranking"] or "unsupported") != preference:
            raise ValueError("frozen ranking disagrees with sealed estimates")
        proposal = {"kind": "defer"}
        if preference in ARMS[domain]:
            proposal = {"kind": "recommend", "action": preference}
        verdict = judge(snapshot, proposal)
        counts[verdict] += 1
        seals.update(bytes.fromhex(fingerprint([snapshot, proposal])))
        if verdict not in ("supported", "deferred"):
            examples.setdefault(
                verdict,
                dict(
                    match=identity[0],
                    hero=identity[1],
                    t=identity[2],
                    proposal=proposal,
                    balance_after=balance,
                ),
            )
        if values is None or balance > 0.25:
            overlaps[pred["overlap_reason"] or "insufficient_balance"] += 1
            continue
        for metric in targets:
            forecast = values[pred["action"]][metric]
            actual = row[metric]
            if actual is None or forecast is None:
                missing[metric] += 1
                continue
            delta = forecast - actual
            error[metric] += delta**2 if metric in ("death", "arrival") else abs(delta)
            pairs[metric] += 1
    explicit = len(eligible) - counts["deferred"]
    unsupported = explicit - counts["supported"]
    return dict(
        opportunities=len(source),
        eligible=len(eligible),
        matches=len({k[0] for k in source}),
        exclusion_flags=dict(exclusions),
        comparison_exclusions=dict(overlaps),
        comparable=len(eligible) - sum(overlaps.values()),
        verdicts=dict(counts),
        conditional=0,
        unscored=len(source) - len(eligible),
        evidence_coverage=counts["supported"] / len(source) if source else None,
        explicit=explicit,
        unsupported=unsupported,
        unsupported_rate=unsupported / explicit if explicit else None,
        factual={
            m: {
                "metric": "brier" if m in ("death", "arrival") else "mae",
                "n": pairs[m],
                "missing_among_comparable": missing[m],
                "value": error[m] / pairs[m] if pairs[m] else None,
            }
            for m in targets
        },
        first_failure=examples,
        seals_sha256=seals.hexdigest(),
    )


def baseline(reports, values_root):
    receipt = json.loads(RECEIPT.read_bytes())
    results = {}
    for domain, pin in receipt["domains"].items():
        raw = reports / ("outcome-labels" if domain == "wave" else f"outcome-domains/{domain}")
        fit = values_root / domain
        summary = json.loads(verified_bytes(fit / "summary.json", pin["summary_sha256"]))
        verified_bytes(fit / "development.joblib", pin["model_sha256"])
        rows = verified_bytes(raw / "rows.jsonl", pin["rows_sha256"])
        predictions = verified_bytes(fit / "predictions.jsonl", pin["predictions_sha256"])
        results[domain] = score_domain(
            domain,
            map(json.loads, rows.splitlines()),
            list(map(json.loads, predictions.splitlines())),
            summary,
        )
    files = [
        Path(__file__),
        Path(sys.modules[seal.__module__].__file__),
        Path(sys.modules[is_holdout.__module__].__file__),
    ]
    return dict(
        schema=VERSION,
        frozen=receipt,
        domains=results,
        scorer_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="score a structured B5 case")
    check.add_argument("case", type=Path)
    run = commands.add_parser("baseline", help="verify and score the U191 OOF records")
    run.add_argument("--reports", type=Path, default=ROOT / "reports")
    run.add_argument("--values", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "check":
            case = json.loads(args.case.read_bytes())
            result = check_case(case)
        else:
            result = baseline(args.reports, args.values)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        if args.command == "check" and result["verdict"] not in (
            "supported",
            "conditional",
            "deferred",
        ):
            parser.exit(2)
    except (ValueError, OSError, TypeError, KeyError) as err:
        parser.exit(1, f"{err}\n")


if __name__ == "__main__":
    main()
