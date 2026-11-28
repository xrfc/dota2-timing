"""Audit immutable B5 farm-income records without parsing replays or changing a batch."""

import argparse
import csv
import hashlib
import json
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import collect_b5_farm_income as batch

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.sources.gem_farm_income import COMPAT_SHA256, SCHEMA
from dota_items.storage import digest, file_hash, inside, write_json, writer_lock

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("creep", "neutral")


def _integer(value, *, minimum=0):
    return type(value) is int and value >= minimum


def validate_capture(capture, match):
    """Check the persisted v2 contract; this does not revalidate raw replay bytes."""
    if (
        type(capture.get("match_id")) is not int
        or capture["match_id"] != match["match"]
        or capture.get("schema") != SCHEMA
        or capture.get("compat_manifest_sha256") != COMPAT_SHA256
        or capture.get("sampling") != "first_tick_start_before_entity_updates"
        or capture.get("ownership") != "player_resource_selected_hero_and_team_slot"
        or capture.get("window_convention") != "integer game seconds [t,t+seconds)"
    ):
        raise ValueError("capture match, schema or compatibility mismatch")
    recipients = capture["recipients"]
    slots, resources = set(), set()
    for identity in recipients.values():
        team, slot, resource = (identity[k] for k in ("team", "slot", "resource_index"))
        if (
            type(team) is not int
            or team not in (2, 3)
            or not _integer(slot)
            or slot > 4
            or not _integer(resource)
            or resource >= 30
        ):
            raise ValueError("invalid capture recipient")
        slots.add((team, slot))
        resources.add(resource)
    if len(recipients) != 10 or len(slots) != 10 or len(resources) != 10:
        raise ValueError("incomplete or ambiguous capture recipients")
    needed = {(r["hero"], r["t"] + n) for r in match["cases"] for n in (0, 20, 30)}
    endpoints = capture["boundaries"]
    if (
        len(endpoints) != len(needed)
        or {(b["hero"], b["t"]) for b in endpoints} != needed
        or any(hero not in recipients for hero, _ in needed)
    ):
        raise ValueError("capture endpoint population mismatch")
    for b in endpoints:
        if b["status"] not in ("observed", "missing_endpoint") or not _integer(b["t"]):
            raise ValueError("invalid capture endpoint status or time")
        if any(b[k] is not None and not _integer(b[k]) for k in KINDS):
            raise ValueError("invalid capture counter")
        if b["status"] == "missing_endpoint":
            if any(b[k] is not None for k in (*KINDS, "tick", "net_tick")):
                raise ValueError("missing endpoint contains observed values")
        elif not all(_integer(b[k]) for k in ("tick", "net_tick")):
            raise ValueError("observed endpoint lacks tick identity")
    events = capture["events"]
    for e in events:
        if (
            e["hero"] not in recipients
            or e["kind"] not in KINDS
            or not _integer(e["value"])
            or not _integer(e["tick"])
            or type(e["t"]) is not int
        ):
            raise ValueError("invalid capture gold event")
    counts = capture["gold_event_counts"]
    if any(not _integer(v) for v in counts.values()) or any(
        counts.get(reason, 0) != sum(e["kind"] == kind for e in events)
        for reason, kind in (("13", "creep"), ("14", "neutral"))
    ):
        raise ValueError("capture event counts mismatch")


def _published(batch_dir, allowed):
    paths = sorted(batch_dir.glob("*.json"))
    if any(p.name not in allowed | {"manifest.json"} for p in paths):
        raise ValueError("unknown extra batch JSON file")
    return [inside(batch_dir, p.name) for p in paths if p.name != "manifest.json"]


def audit(plan_path, batch_dir, producer, output):
    """Publish one deterministic snapshot; --producer is hashed, never imported."""
    plan_path, batch_dir, producer = (Path(p).resolve() for p in (plan_path, batch_dir, producer))
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("audit output already exists")
    output = output.resolve()
    if output.is_relative_to(batch_dir) or output.is_relative_to(producer):
        raise ValueError("audit output must be outside batch and producer")
    input_hashes = {}

    def read(path):
        raw = read_source_bytes(path)
        input_hashes[path] = hashlib.sha256(raw).hexdigest()
        return parse_source_json(raw)

    plan = read(plan_path)
    batch.validate_plan(plan)
    manifest_path = inside(batch_dir, "manifest.json")
    manifest = read(manifest_path)
    producer_paths = {name: inside(producer, name) for name in batch.IMPLEMENTATION}
    producer_hashes = {name: file_hash(path) for name, path in producer_paths.items()}
    bound = dict(
        schema="b5-farm-run/1",
        plan_sha256=digest(plan),
        implementation_sha256=producer_hashes,
    )
    if manifest != bound:
        raise ValueError("producer or plan does not match batch manifest")
    runtime_paths = [ROOT / name for name in batch.IMPLEMENTATION] + [Path(__file__).resolve()]
    runtime_hashes = {str(p.relative_to(ROOT)): file_hash(p) for p in runtime_paths}
    matches = {m["match"]: m for m in plan["matches"]}
    allowed = {f"{mid}.json" for mid in matches}
    paths = _published(batch_dir, allowed)  # Freeze once; later valid publications are pending.
    rows, cells, discrepancies = [], [], []
    grouped = defaultdict(Counter)
    for path in paths:
        if not re.fullmatch(r"[0-9]+\.json", path.name):
            raise ValueError("invalid match filename")
        match = matches[int(path.stem)]
        record = read(path)
        batch.verify_result(record, match, bound)
        if digest(record["source"]) != digest(match):
            raise ValueError("saved source differs from plan")
        validate_capture(record["capture"], match)
        expected = batch.score_windows(match["cases"], record["capture"], match["duration"])
        if digest(record["rows"]) != digest(expected):
            raise ValueError("saved rows do not exactly match rescored cases")
        rows.extend(record["rows"])
        for row in record["rows"]:
            for n in (20, 30):
                window = row["windows"][str(n)]
                for kind in KINDS:
                    amount = window[kind]
                    delta = amount["difference"]
                    category = (
                        "unobserved" if delta is None else "equal" if delta == 0 else "nonzero"
                    )
                    cell = dict(
                        **{k: row[k] for k in ("match", "hero", "t", "fold", "action")},
                        window=n,
                        kind=kind,
                        status=window["status"],
                        category=category,
                        **amount,
                    )
                    cells.append(cell)
                    if category == "nonzero":
                        discrepancies.append(cell)
                    for dimension in ("match", "hero", "action"):
                        counts = grouped[(dimension, str(row[dimension]), n, kind)]
                        counts["amount_cells"] += 1
                        counts[category] += 1
                        counts["status_" + window["status"]] += 1
                        if delta is not None:
                            counts["counter_zero"] += amount["counter"] == 0
                            counts["positive"] += delta > 0
                            counts["negative"] += delta < 0
    pending = sorted(set(matches) - {int(p.stem) for p in paths})
    windows = {
        str(n): dict(
            statuses=dict(sorted(Counter(r["windows"][str(n)]["status"] for r in rows).items())),
            amounts={
                kind: dict(
                    sorted(
                        Counter(
                            c["category"] for c in cells if c["window"] == n and c["kind"] == kind
                        ).items()
                    )
                )
                for kind in KINDS
            },
        )
        for n in (20, 30)
    }
    summary = dict(
        schema="b5-farm-income-audit/1",
        matches_planned=len(matches),
        matches_complete=len(paths),
        matches_pending=len(pending),
        opportunities_planned=sum(len(m["cases"]) for m in matches.values()),
        opportunities_complete=len(rows),
        opportunities_pending=sum(len(matches[mid]["cases"]) for mid in pending),
        actions=dict(sorted(Counter(r["action"] for r in rows).items())),
        windows=windows,
        amount_cells=len(cells),
        amount_categories=dict(sorted(Counter(c["category"] for c in cells).items())),
        counter_zero_cells=sum(c["counter"] == 0 for c in cells),
        negative_difference_cells=sum(c["difference"] < 0 for c in discrepancies),
        nonzero_matches=len({c["match"] for c in discrepancies}),
        nonzero_opportunities=len({(c["match"], c["hero"], c["t"]) for c in discrepancies}),
        extraction_complete=not pending,
        unexplained_difference_cells=len(discrepancies),
        scope="Saved records only; no raw replay reparse. Nonzero differences require separate "
        "evidence review. A complete window does not imply reconciliation; absent matches and "
        "unobserved amounts are not zero. No discrepancy is exempted by this audit.",
    )
    provenance = dict(
        plan_sha256=input_hashes[plan_path],
        manifest_sha256=input_hashes[manifest_path],
        records_sha256={p.name: input_hashes[p] for p in paths},
        producer_sha256=producer_hashes,
        audit_implementation_sha256=runtime_hashes,
        completed_matches=sorted(int(p.stem) for p in paths),
        pending_matches=pending,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".farm-audit-", dir=output.parent) as temporary:
        staging = Path(temporary) / "result"
        staging.mkdir()
        write_json(staging / "summary.json", summary)
        write_json(staging / "provenance.json", provenance)
        write_json(
            staging / "groups.json",
            [
                dict(dimension=k[0], value=k[1], window=k[2], kind=k[3], **v)
                for k, v in sorted(grouped.items())
            ],
        )
        fields = (
            "match",
            "hero",
            "t",
            "fold",
            "action",
            "window",
            "kind",
            "status",
            "category",
            "counter",
            "event",
            "difference",
        )
        for name, table in (("amount-cells.csv", cells), ("discrepancies.csv", discrepancies)):
            with (staging / name).open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(table)
        # A separate lock avoids touching the live batch's lock or files.
        with writer_lock(output.parent):
            if output.exists() or output.is_symlink():
                raise ValueError("audit output already exists")
            _published(batch_dir, allowed)  # Reject foreign additions, allow planned new matches.
            if any(file_hash(p) != sha for p, sha in input_hashes.items()):
                raise ValueError("audit input changed during verification")
            if any(file_hash(producer_paths[k]) != sha for k, sha in producer_hashes.items()):
                raise ValueError("producer changed during verification")
            if any(file_hash(ROOT / k) != sha for k, sha in runtime_hashes.items()):
                raise ValueError("audit implementation changed during verification")
            staging.rename(output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "batch", "producer", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.plan, args.batch, args.producer, args.out), indent=2))


if __name__ == "__main__":
    main()
