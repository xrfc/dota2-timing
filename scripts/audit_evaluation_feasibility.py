"""Offline source/time/availability audit; never collect, train or score new matches."""

import argparse
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from collect_purchase_latest import inspect_match

from dota_items.contracts.tasks import WHOLE_LOG_ITEMS
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

ROOTS = [
    Path("data/purchase-latest-2026-10-22-proxy"),
    Path("data/purchase-until-daily-2026-10-22-proxy"),
    Path("data/purchase-until-daily-2026-10-22-proxy-resume-01"),
]
OLD = Path("reports/cohort-random-v2-2026-10-21")


class CheckedReader:
    def __init__(self):
        self.hashes = {}

    def read(self, path, expected=None):
        path = Path(path)
        data = read_source_bytes(path, max_bytes=512 * 1024 * 1024)
        digest = hashlib.sha256(data).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError(f"Hash mismatch: {path}")
        if str(path) in self.hashes and self.hashes[str(path)] != digest:
            raise ValueError("Input drift during repeated read")
        self.hashes[str(path)] = digest
        return parse_source_json(data)

    def verify(self):
        for name, digest in self.hashes.items():
            if file_hash(Path(name)) != digest:
                raise ValueError(f"Input drift: {name}")


def account(player):
    value = player.get("account_id")
    return value if type(value) is int and 0 < value < 4294967295 else None


def describe(raw):
    mid, start, duration = (raw.get(k) for k in ("match_id", "start_time", "duration"))
    if any(type(v) is not int for v in (mid, start, duration)) or duration < 0:
        raise ValueError("Invalid identity or clock")
    players = raw["players"]
    target = [p for p in players if p.get("hero_id") == 8]
    if len(players) != 10 or len(target) != 1:
        raise ValueError("Invalid player structure")
    log = target[0].get("purchase_log")
    valid = isinstance(log, list) and all(
        isinstance(e, dict)
        and isinstance(e.get("key"), str)
        and bool(e["key"])
        and type(e.get("time")) in (int, float)
        and math.isfinite(e["time"])
        for e in log
    )
    return dict(
        match_id=mid,
        start=start,
        end=start + duration,
        duration=duration,
        accounts=sorted({account(p) for p in players if account(p) is not None}),
        unknown_account_slots=sum(account(p) is None for p in players),
        target_account=account(target[0]),
        log_status="valid" if valid else "missing" if log is None else "invalid",
        log_empty=valid and len(log) == 0,
        replay_url_present=bool(raw.get("replay_url")),
        patch=raw.get("patch"),
    )


def utc(timestamp):
    return datetime.fromtimestamp(timestamp, UTC).isoformat()


def summary(rows, old_rows):
    old_ids = {r["match_id"] for r in old_rows}
    old_accounts = {a for r in old_rows for a in r["accounts"]}
    old_targets = {r["target_account"] for r in old_rows if r["target_account"] is not None}
    max_end = max(r["end"] for r in old_rows)
    return dict(
        matches=len(rows),
        unique_matches=len({r["match_id"] for r in rows}),
        duplicate_old_matches=sum(r["match_id"] in old_ids for r in rows),
        log_status=dict(Counter(r["log_status"] for r in rows)),
        empty_valid_logs=sum(r["log_empty"] for r in rows),
        start_min_utc=utc(min(r["start"] for r in rows)) if rows else None,
        start_max_utc=utc(max(r["start"] for r in rows)) if rows else None,
        duration_min=min((r["duration"] for r in rows), default=None),
        duration_max=max((r["duration"] for r in rows), default=None),
        after_all_old_ends=sum(r["start"] > max_end for r in rows),
        observed_accounts=len({a for r in rows for a in r["accounts"]}),
        shared_accounts=len({a for r in rows for a in r["accounts"]} & old_accounts),
        matches_sharing_any_old_account=sum(bool(set(r["accounts"]) & old_accounts) for r in rows),
        target_account_missing=sum(r["target_account"] is None for r in rows),
        matches_target_seen_as_old_target=sum(r["target_account"] in old_targets for r in rows),
        unknown_account_slots=sum(r["unknown_account_slots"] for r in rows),
        replay_urls=sum(r["replay_url_present"] for r in rows),
        numeric_patches=dict(Counter(str(r["patch"]) for r in rows)),
    )


def components(old_rows, new_rows):
    """Observed all-player links only; no isolation gate or effective-N claim."""
    rows = old_rows + new_rows
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for i, row in enumerate(rows):
        for a in row["accounts"]:
            if a in seen:
                parent[find(i)] = find(seen[a])
            else:
                seen[a] = i
    counts = Counter(find(i) for i in range(len(rows)))
    old_roots = {find(i) for i in range(len(old_rows))}
    return dict(
        components=len(counts),
        largest_match_count=max(counts.values()),
        new_matches_connected_to_old=sum(
            find(i) in old_roots for i in range(len(old_rows), len(rows))
        ),
    )


def precision_scenarios(reader, validation_sources):
    """Development-only IID planning approximation, NOT a new evaluation or power claim."""
    validation_ids = set(validation_sources)
    if len(validation_ids) < 2:
        raise ValueError("Planning requires at least two validation matches")
    pairs = []
    for root, filename in [
        (
            Path("reports/whole-log-fixed-baseline-2026-10-21"),
            "frequency.validation.predictions.json",
        ),
        (
            Path("reports/whole-log-regularization-2026-10-22"),
            "logistic_c0_1.validation.predictions.json",
        ),
    ]:
        receipt = reader.read(root / "complete.json")
        rows = reader.read(root / filename, receipt["sha256"][filename])
        by_id = {r["match_id"]: r for r in rows}
        if len(by_id) != len(rows) or set(by_id) != set(validation_ids):
            raise ValueError("Prediction membership mismatch")
        for row in rows:
            if (
                row["split"] != "validation"
                or row["source_sha256"] != validation_sources[row["match_id"]]
            ):
                raise ValueError("Prediction frozen source/split mismatch")
        pairs.append(by_id)
    differences = []
    for mid in sorted(validation_ids):
        f, c = (p[mid] for p in pairs)
        if any(f[k] != c[k] for k in ("labels", "label_mask", "source_sha256", "split")):
            raise ValueError("Prediction alignment mismatch")
        keys = set(f["labels"])
        if keys != set(WHOLE_LOG_ITEMS) or any(
            set(r[k]) != keys for r in (f, c) for k in ("probabilities", "label_mask")
        ):
            raise ValueError("Prediction shape mismatch")
        if not all(value is True for r in (f, c) for value in r["label_mask"].values()):
            raise ValueError("Planning formula requires complete labels")
        for row in (f, c):
            if any(
                type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1
                for p in row["probabilities"].values()
            ):
                raise ValueError("Invalid probability")
            if any(type(y) is not int or y not in (0, 1) for y in row["labels"].values()):
                raise ValueError("Invalid label")
        differences.append(
            statistics.mean(
                (c["probabilities"][k] - c["labels"][k]) ** 2
                - (f["probabilities"][k] - f["labels"][k]) ** 2
                for k in keys
            )
        )
    sd = statistics.stdev(differences)
    return dict(
        development_n=len(differences),
        mean_difference=statistics.mean(differences),
        sd=sd,
        iid_half_widths={str(n): 1.96 * sd / math.sqrt(n) for n in (200, 500, 1000)},
        iid_n_for_half_width_005=math.ceil((1.96 * sd / 0.005) ** 2),
        limitation=(
            "Old selected development sample; IID approximation ignores dependence and drift; "
            "not power or stopping rule."
        ),
    )


def run(output):
    if output.exists():
        raise ValueError("Output exists")
    reader = CheckedReader()
    # Include reused helpers and all current data modules in the implementation fingerprint.
    code_paths = [
        Path(__file__),
        Path("scripts/collect_purchase_latest.py"),
        Path("src/dota_items/storage.py"),
        Path("src/dota_items/contracts/tasks.py"),
        *Path("src/dota_items/data").glob("*.py"),
    ]
    code = {str(p): file_hash(p) for p in code_paths}
    complete = reader.read(OLD / "complete.json")
    sources = reader.read(OLD / "sources.json", complete["sha256"]["sources.json"])
    split = reader.read(OLD / "split.json", complete["sha256"]["split.json"])["members"]
    old_rows = []
    for source in sources:
        raw = reader.read(source["path"], source["sha256"])
        if raw["match_id"] != source["match_id"]:
            raise ValueError("Old source identity mismatch")
        old_rows.append(describe(raw))
    old_ids = {r["match_id"] for r in old_rows}
    if (
        len(old_ids) != 1990
        or len(old_rows) != 1990
        or old_ids != set(split["train"] + split["validation"])
        or set(split["train"]) & set(split["validation"])
        or split["test"]
        or len(split["train"]) != 1592
        or len(split["validation"]) != 398
    ):
        raise ValueError("Old cohort membership mismatch")
    all_rows, batches, failures, discoveries = [], [], [], {}
    metadata_sets = {}
    successful_sql = []
    for root in ROOTS:
        files = sorted(p for p in root.rglob("*.json") if p.parent.name != "matches")
        metadata_sets[str(root)] = [str(p) for p in files]
        meta = {str(p.relative_to(root)): reader.read(p) for p in files}
        protocol = meta["protocol.json"]
        if "previous" in protocol:
            reader.read(
                Path(protocol["previous"]) / "protocol.json", protocol["previous_protocol_sha256"]
            )
        plans = [v["match_ids"] for k, v in meta.items() if k.endswith("plan.json")]
        planned = [mid for plan in plans for mid in plan]
        if len(planned) != len(set(planned)):
            raise ValueError("Duplicate planned IDs")
        if root == ROOTS[0]:
            if meta["plan.json"]["protocol_sha256"] != reader.hashes[str(root / "protocol.json")]:
                raise ValueError("Plan protocol mismatch")
            reader.read(root / "exclusions.json", protocol["exclusions_sha256"])
        for k, entry in meta.items():
            if "discovery" not in k or k.endswith("-receipt.json"):
                continue
            if "body" in entry:
                payload = parse_source_json(entry["body"].encode())
                status = entry["status"]
                sql = entry["sql"]
            else:
                payload = entry
                rec = meta[k.replace(".json", "-receipt.json")]
                reader.read(root / k, rec["sha256"])
                sql, status = rec["sql"], 200
            if status != 200 or payload.get("err"):
                failures.append(
                    dict(path=str(root / k), status=status, error=payload.get("err"), sql=sql)
                )
            else:
                successful_sql.append(sql)
                for r in payload["rows"]:
                    discoveries[r["match_id"]] = r
        existing = {r["match_id"]: r for r in meta["results.json"]["rows"] if "log_status" in r}
        paths = sorted(p for p in (root / "matches").glob("*.json") if p.stem.isdigit())
        rows = []
        for path in paths:
            mid = int(path.stem)
            receipt = reader.read(path.with_suffix(".manifest.json"))
            if receipt["match_id"] != mid or receipt["status"] != 200 or mid not in planned:
                raise ValueError("Detail receipt/plan mismatch")
            raw = reader.read(path, receipt["sha256"])
            checked = inspect_match(raw, mid, protocol["window"])
            if checked != existing[mid]:
                raise ValueError("Historical screening replay mismatch")
            row = describe(raw)
            row.update(
                screened=checked["screened"],
                reasons=checked["reasons"],
                source=str(path),
                within_collection_window=protocol["start_time_min"]
                <= row["start"]
                < protocol["start_time_max_exclusive"],
            )
            rows.append(row)
        if set(existing) != {r["match_id"] for r in rows}:
            raise ValueError("Saved results/cache membership mismatch")
        if "saved" in meta["summary.json"] and meta["summary.json"]["saved"] != len(rows):
            raise ValueError("Saved denominator mismatch")
        batches.append(
            dict(
                root=str(root),
                saved=len(rows),
                planned=len(planned),
                summary=meta["summary.json"],
                recorded_unsaved_attempts=[
                    r for r in meta["results.json"]["rows"] if "log_status" not in r
                ],
                counts=summary(rows, old_rows),
                reason_counts=dict(Counter(reason for r in rows for reason in r["reasons"])),
            )
        )
        all_rows.extend(rows)
    if len({r["match_id"] for r in all_rows}) != len(all_rows):
        raise ValueError("Duplicate new match; reconcile versions before analysis")
    for row in all_rows:
        d = discoveries.get(row["match_id"])
        row["discovery_rank"] = d.get("avg_rank_tier") if d else None
        row["discovery_rank_count"] = d.get("num_rank_tier") if d else None
        row["discovery_present"] = d is not None
    candidates = [r for r in all_rows if r["screened"]]
    for failure in failures:
        template = re.sub(r"match_id<\d+", "match_id<CURSOR", failure["sql"])
        failure["successful_same_template_pages"] = sum(
            re.sub(r"match_id<\d+", "match_id<CURSOR", sql) == template for sql in successful_sql
        )
    result = dict(
        schema_version="evaluation-feasibility/1",
        training_admission=False,
        formal_split_assigned=False,
        new_predictions_computed=False,
        old_source_count=len(old_rows),
        old_start_min_utc=utc(min(r["start"] for r in old_rows)),
        old_start_max_utc=utc(max(r["start"] for r in old_rows)),
        old_end_max_utc=utc(max(r["end"] for r in old_rows)),
        new_counts=summary(all_rows, old_rows),
        screened_counts=summary(candidates, old_rows),
        overlap_by_old_split={
            k: summary(all_rows, [r for r in old_rows if r["match_id"] in set(v)])
            for k, v in split.items()
            if v
        },
        components_all=components(old_rows, all_rows),
        components_screened=components(old_rows, candidates),
        discovery_missing=sum(not r["discovery_present"] for r in all_rows),
        discovery_rank_counts=dict(Counter(str(r["discovery_rank_count"]) for r in all_rows)),
        discovery_rank_below_70=sum(
            r["discovery_rank"] is not None and r["discovery_rank"] < 70 for r in all_rows
        ),
        collection_window_violations=sum(not r["within_collection_window"] for r in all_rows),
        batches=batches,
        discovery_failures=failures,
        rows=all_rows,
        development_precision=precision_scenarios(
            reader,
            {s["match_id"]: s["sha256"] for s in sources if s["match_id"] in split["validation"]},
        ),
    )
    reader.verify()
    for root in ROOTS:
        current = sorted(str(p) for p in root.rglob("*.json") if p.parent.name != "matches")
        if current != metadata_sets[str(root)]:
            raise ValueError("Metadata file set drift")
        expected = {
            r["source"] for r in all_rows if str(Path(r["source"]).parent.parent) == str(root)
        }
        if {str(p) for p in (root / "matches").glob("*.json") if p.stem.isdigit()} != expected:
            raise ValueError("Detail file set drift")
    for path, digest in code.items():
        if file_hash(Path(path)) != digest:
            raise ValueError("Code drift")
    result["inputs"] = reader.hashes
    result["implementation"] = code
    output.mkdir(parents=True, exist_ok=False)
    path = output / "audit.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    (output / "complete.json").write_text(
        json.dumps(dict(audit_sha256=file_hash(path), training_admission=False), indent=2) + "\n"
    )
    return {
        k: result[k]
        for k in (
            "old_end_max_utc",
            "new_counts",
            "screened_counts",
            "development_precision",
            "discovery_failures",
        )
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
