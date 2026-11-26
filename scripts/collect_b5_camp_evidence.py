#!/usr/bin/env python3
"""Resume decision-time camp evidence for the unchanged B5 development population.

Each published match directory separates an omniscient raw diagnostic from its
team-visible evidence. Neither file is a camp stock, action label or training row.
"""

import argparse
import hashlib
import importlib
import json
import sys
import tempfile
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

from dota_items.data.awareness_split import is_holdout
from dota_items.data.camp_evidence import UNIT_FIELDS, project_camp_evidence
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.sources.gem_camp_evidence import (
    COMPAT_SHA256,
    capture_camp_evidence,
    verify_compatibility,
)
from dota_items.sources.gem_replay import prepared_demo
from dota_items.storage import digest, file_hash, inside, write_json, writer_lock

ROOT = Path(__file__).resolve().parents[1]
PLAN_SHA256 = "8ad71d1e60b251360b9e96a4afc0c4a599443ddaa1c88abdb012b060cba7f3ad"
POPULATION_SHA256 = "4909b7905e5d5568831f96ca5cff385302fd28cd9a9228fde2c31c9746a80d42"
ROWS_SHA256 = "f2f1254c33158b6923fa7185dd1454414fc8483baaa7c8f69d5cf88d6eb395ca"
ROUTES_SHA256 = "fcc370fdcedaa19440d5a72bdd90a6743883710495894232ffaacb746415bda2"
MATCHES, OPPORTUNITIES = 1169, 15005
IMPLEMENTATION = (
    "scripts/collect_b5_camp_evidence.py",
    "src/dota_items/data/camp_evidence.py",
    "src/dota_items/data/awareness_split.py",
    "src/dota_items/data/source_io.py",
    "src/dota_items/sources/gem_camp_evidence.py",
    "src/dota_items/sources/gem_capture.py",
    "src/dota_items/sources/gem_replay.py",
    "src/dota_items/sources/gem_observations.py",
    "src/dota_items/normalize.py",
    "src/dota_items/domain.py",
    "src/dota_items/storage.py",
)
BUNDLE_FILES = {"raw.json", "evidence.json", "receipt.json"}


def validate_plan(plan):
    """Bind all original opportunities, metadata and source bytes; never build a new split."""
    if (
        plan.get("schema") != "b5-farm-plan/1"
        or plan.get("rows_sha256") != ROWS_SHA256
        or plan.get("routes_sha256") != ROUTES_SHA256
        or not isinstance(plan.get("matches"), list)
        or len(plan["matches"]) != MATCHES
    ):
        raise ValueError("unsupported fixed B5 plan")
    population, seen = [], set()
    for match in plan["matches"]:
        mid = match.get("match")
        if type(mid) is not int or mid <= 0 or mid in seen or is_holdout(mid):
            raise ValueError("plan has a duplicate, invalid or heldout match")
        seen.add(mid)
        if (
            type(match.get("duration")) is not int
            or match["duration"] <= 0
            or type(match.get("patch")) is not int
            or match["patch"] != 60
            or not isinstance(match.get("cases"), list)
            or not match["cases"]
        ):
            raise ValueError("invalid fixed match metadata")
        for name in ("demo_sha256", "receipt_sha256", "meta_sha256"):
            sha = match.get(name)
            if (
                not isinstance(sha, str)
                or len(sha) != 64
                or any(c not in "0123456789abcdef" for c in sha)
            ):
                raise ValueError("invalid planned source fingerprint")
        fold = int.from_bytes(hashlib.sha256(f"lane-study-v1:{mid}".encode()).digest(), "big") % 5
        identities = set()
        for case in match["cases"]:
            if (
                set(case) != {"match", "hero", "t", "fold", "action"}
                or type(case["match"]) is not int
                or case["match"] != mid
                or not isinstance(case["hero"], str)
                or not case["hero"].startswith("npc_dota_hero_")
                or type(case["t"]) is not int
                or case["t"] < 0
                or type(case["fold"]) is not int
                or case["fold"] != fold
                or case["action"] not in ("stay_lane", "move_to_jungle", "unknown")
            ):
                raise ValueError("invalid fixed opportunity identity, fold or action")
            identity = case["hero"], case["t"]
            if identity in identities:
                raise ValueError("duplicate fixed opportunity")
            identities.add(identity)
            population.append(case)
    population.sort(key=lambda c: (c["match"], c["hero"], c["t"]))
    if len(population) != OPPORTUNITIES or digest(population) != POPULATION_SHA256:
        raise ValueError("fixed B5 opportunity population changed")
    if digest(plan) != PLAN_SHA256:
        raise ValueError("fixed B5 plan source or metadata changed")
    return plan


def implementation_hashes():
    for name in IMPLEMENTATION:
        if name.startswith("src/"):
            module = importlib.import_module(name[4:-3].replace("/", "."))
            if Path(module.__file__).resolve() != inside(ROOT, name).resolve():
                raise ValueError("imported producer does not belong to this source archive")
    return {name: file_hash(inside(ROOT, name)) for name in IMPLEMENTATION}


def binding(plan):
    return dict(
        schema="b5-camp-run/1",
        plan_sha256=digest(plan),
        population_sha256=POPULATION_SHA256,
        compat_manifest_sha256=COMPAT_SHA256,
        implementation_sha256=implementation_hashes(),
    )


def verify_runtime(expected, compat=None):
    if implementation_hashes() != expected["implementation_sha256"]:
        raise ValueError("camp producer implementation changed")
    if compat is not None:
        if verify_compatibility(compat) != expected["compat_manifest_sha256"]:
            raise ValueError("camp compatibility binding changed")


def verify_inputs(data, match):
    """Check only this authorized development replay and its two pinned receipts."""
    mid = match["match"]
    if is_holdout(mid):
        raise ValueError("heldout replay access is forbidden")
    sources = {}
    for kind, relative in (
        ("receipt", f"receipts/{mid}.json"),
        ("meta", f"meta/{mid}.json"),
    ):
        contents = read_source_bytes(inside(data, relative))
        sources[kind] = parse_source_json(contents)
        if hashlib.sha256(contents).hexdigest() != match[f"{kind}_sha256"]:
            raise ValueError(f"{mid}: {kind} fingerprint changed")
        if type(sources[kind].get("match_id")) is not int or sources[kind]["match_id"] != mid:
            raise ValueError(f"{mid}: {kind} match identity mismatch")
    if sources["receipt"].get("demo_sha256") != match["demo_sha256"]:
        raise ValueError(f"{mid}: receipt demo fingerprint mismatch")
    meta = sources["meta"]
    if any(type(meta.get(k)) is not int or meta[k] != match[k] for k in ("patch", "duration")):
        raise ValueError(f"{mid}: source metadata disagrees with plan")
    demo = inside(data, f"demos/{mid}.dem.bz2")
    if file_hash(demo) != match["demo_sha256"]:
        raise ValueError(f"{mid}: raw replay fingerprint changed")
    return demo


def validate_capture(captured, match):
    if (
        type(captured.get("match_id")) is not int
        or captured["match_id"] != match["match"]
        or captured.get("compat_manifest_sha256") != COMPAT_SHA256
        or captured.get("omniscient") is not True
        or captured.get("usage") != "audit_only_requires_team_visibility_projection"
        or not isinstance(captured.get("frames"), list)
    ):
        raise ValueError("camp capture identity or compatibility mismatch")
    expected = sorted((case["hero"], case["t"]) for case in match["cases"])
    public = project_camp_evidence(captured)
    if [(frame["hero"], frame["t"]) for frame in public["frames"]] != expected:
        raise ValueError("camp capture changed the fixed opportunity population")
    for frame in captured["frames"]:
        if frame["status"] == "missing_frame":
            if frame.get("units") is not None:
                raise ValueError("missing frame contains a unit collection")
        elif not isinstance(frame.get("units"), list):
            raise ValueError("captured frame lacks its raw unit collection")
    return public


def verify_result(directory, match, expected):
    """Recompute the whitelist view, even if a modified file has a new checksum."""
    if not directory.is_dir() or {p.name for p in directory.iterdir()} != BUNDLE_FILES:
        raise ValueError(f"invalid published camp bundle: {directory.name}")
    files, fingerprints = {}, {}
    for name in sorted(BUNDLE_FILES):
        contents = read_source_bytes(inside(directory, name), max_bytes=256 * 1024**2)
        files[name] = parse_source_json(contents)
        fingerprints[name] = hashlib.sha256(contents).hexdigest()
    receipt = files["receipt.json"]
    payload = {key: value for key, value in receipt.items() if key != "payload_sha256"}
    if receipt.get("payload_sha256") != digest(payload):
        raise ValueError("camp record checksum mismatch")
    if (
        receipt.get("schema") != "b5-camp-record/1"
        or type(receipt.get("match_id")) is not int
        or receipt["match_id"] != match["match"]
        or digest(receipt.get("source")) != digest(match)
        or digest(receipt.get("binding")) != digest(expected)
        or receipt.get("raw_sha256") != fingerprints["raw.json"]
        or receipt.get("evidence_sha256") != fingerprints["evidence.json"]
    ):
        raise ValueError("camp record source, producer or payload mismatch")
    raw = files["raw.json"]
    if (
        raw.get("schema") != "b5-camp-raw/1"
        or raw.get("information_scope") != "omniscient_diagnostic_only"
    ):
        raise ValueError("raw camp evidence is not isolated as omniscient diagnostics")
    projected = validate_capture(raw["capture"], match)
    if digest(files["evidence.json"]) != digest(projected):
        raise ValueError("published camp evidence differs from whitelist projection")
    verify_fingerprints(directory, fingerprints)
    return projected, fingerprints


def verify_fingerprints(directory, fingerprints):
    if {p.name for p in directory.iterdir()} != BUNDLE_FILES:
        raise ValueError("published camp bundle file set changed")
    for name, expected in fingerprints.items():
        if file_hash(inside(directory, name)) != expected:
            raise ValueError("published camp bundle changed during validation")


def execute_match(match, data, out, expected, compat):
    verify_runtime(expected, compat)
    demo = verify_inputs(data, match)
    target = inside(out, f"matches/{match['match']}")
    if target.exists():
        _, fingerprints = verify_result(target, match, expected)
        verify_inputs(data, match)
        verify_runtime(expected, compat)
        verify_fingerprints(target, fingerprints)
        return match["match"], "reused"
    with prepared_demo(demo, out / "scratch") as raw_demo:
        captured = capture_camp_evidence(raw_demo, [(c["hero"], c["t"]) for c in match["cases"]])
    public = validate_capture(captured, match)
    with tempfile.TemporaryDirectory(prefix=".stage-", dir=out / "matches") as temporary:
        staging = Path(temporary) / "bundle"
        write_json(
            staging / "raw.json",
            dict(
                schema="b5-camp-raw/1",
                information_scope="omniscient_diagnostic_only",
                capture=captured,
            ),
        )
        write_json(staging / "evidence.json", public)
        receipt = dict(
            schema="b5-camp-record/1",
            match_id=match["match"],
            source=match,
            binding=expected,
            raw_sha256=file_hash(staging / "raw.json"),
            evidence_sha256=file_hash(staging / "evidence.json"),
        )
        receipt["payload_sha256"] = digest(receipt)
        write_json(staging / "receipt.json", receipt)
        _, fingerprints = verify_result(staging, match, expected)
        verify_inputs(data, match)
        verify_runtime(expected, compat)
        verify_fingerprints(staging, fingerprints)
        if target.exists():
            raise ValueError("refusing to replace a published camp match")
        staging.rename(target)
    return match["match"], "published"


def published_matches(out, plan):
    allowed = {str(match["match"]) for match in plan["matches"]}
    root = inside(out, "matches")
    if not root.exists():
        return []
    published = []
    for path in sorted(root.iterdir()):
        if path.name.startswith(".stage-"):
            continue  # Private staging directories are never published evidence.
        if path.name not in allowed or path.is_symlink() or not path.is_dir():
            raise ValueError("unknown or unsafe published camp match")
        published.append(path)
    return published


def report(plan, data, out, expected):
    validate_plan(plan)
    verify_runtime(expected)
    if digest(expected) != digest(binding(plan)):
        raise ValueError("camp report binding differs from the fixed plan")
    manifest_path = inside(out, "manifest.json")
    manifest_bytes = read_source_bytes(manifest_path)
    if digest(parse_source_json(manifest_bytes)) != digest(expected):
        raise ValueError("camp manifest does not match this producer and plan")
    # Fixed list: a concurrent atomic publication belongs to the next report.
    published = published_matches(out, plan)
    matches = {match["match"]: match for match in plan["matches"]}
    status, reasons = Counter(), Counter()
    fields = {name: dict(present=0, missing=0) for name in UNIT_FIELDS}
    fingerprints, completed, unit_count, without_visible = {}, 0, 0, 0
    for directory in published:
        match = matches[int(directory.name)]
        verify_inputs(data, match)
        public, fingerprints[directory] = verify_result(directory, match, expected)
        for frame in public["frames"]:
            completed += 1
            status[frame["status"]] += 1
            unit_count += len(frame["units"])
            without_visible += frame["status"] == "observed" and not frame["units"]
            for unit in frame["units"]:
                reasons.update(unit["missing_reasons"])
                for name in UNIT_FIELDS:
                    fields[name]["missing" if unit[name] is None else "present"] += 1
    for directory, values in fingerprints.items():
        verify_inputs(data, matches[int(directory.name)])
        verify_fingerprints(directory, values)
    if read_source_bytes(manifest_path) != manifest_bytes:
        raise ValueError("camp manifest changed during report")
    verify_runtime(expected)
    pending = sorted(set(matches) - {int(path.name) for path in published})
    return dict(
        schema="b5-camp-progress/1",
        binding=expected,
        planned_matches=len(matches),
        planned_opportunities=sum(len(m["cases"]) for m in matches.values()),
        completed_matches=len(published),
        completed_opportunities=completed,
        pending_matches=pending,
        pending_opportunities=sum(len(matches[mid]["cases"]) for mid in pending),
        complete=not pending,
        frame_statuses=dict(sorted(status.items())),
        visible_unit_observations=unit_count,
        observed_frames_without_visible_units=without_visible,
        visible_field_coverage=fields,
        visible_missing_reasons=dict(sorted(reasons.items())),
        stock_complete=False,
        empty_confirmed=None,
        camp_id=None,
    )


def run(plan, data, out, expected, compat, *, workers=1, limit=None, match_ids=None):
    validate_plan(plan)
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("camp workers must be between 1 and 4")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("camp limit must be positive")
    selected = sorted(plan["matches"], key=lambda match: match["match"])
    if match_ids:
        if not set(match_ids) <= {m["match"] for m in selected}:
            raise ValueError("requested match is outside the fixed development plan")
        selected = [match for match in selected if match["match"] in match_ids]
    if limit:
        selected = selected[:limit]
    if out.resolve() == ROOT or out.resolve().is_relative_to(data.resolve()):
        raise ValueError("camp output must be separate from source data")
    if any(out.resolve().is_relative_to(ROOT / part) for part in ("src", "scripts")):
        raise ValueError("camp output must be separate from producer source")
    verify_runtime(expected, compat)
    if digest(expected) != digest(binding(plan)):
        raise ValueError("camp run binding differs from the fixed plan")
    out.mkdir(parents=True, exist_ok=True)
    with writer_lock(out):
        manifest_path = inside(out, "manifest.json")
        if manifest_path.exists():
            if digest(parse_source_json(read_source_bytes(manifest_path))) != digest(expected):
                raise ValueError("camp resume producer or plan drift")
        else:
            if any(p.name != ".writer.lock" for p in out.iterdir()):
                raise ValueError("refusing an unbound nonempty camp output")
            write_json(manifest_path, expected)
        inside(out, "matches").mkdir(exist_ok=True)
        published_matches(out, plan)
        errors, done = [], []

        def record(mid, result=None, error=None):
            if error is not None:
                errors.append(dict(match=mid, error=f"{type(error).__name__}: {error}"))
            else:
                done.append(dict(match=result[0], status=result[1]))
            write_json(
                out / "progress.json",
                dict(
                    selected_matches=len(selected),
                    finished=sorted(done, key=lambda x: x["match"]),
                    errors=sorted(errors, key=lambda x: x["match"]),
                ),
            )
            print(
                json.dumps(
                    dict(finished=len(done), failed=len(errors), selected=len(selected), match=mid)
                ),
                flush=True,
            )

        if workers == 1:
            for match in selected:
                try:
                    result = execute_match(match, data, out, expected, compat)
                except Exception as error:
                    record(match["match"], error=error)
                else:
                    record(match["match"], result=result)
        else:
            # At most four submitted replay tasks; no unbounded queue of decompressions.
            with ProcessPoolExecutor(max_workers=workers) as pool:
                iterator, pending = iter(selected), {}
                while True:
                    while len(pending) < workers and (match := next(iterator, None)) is not None:
                        future = pool.submit(execute_match, match, data, out, expected, compat)
                        pending[future] = match["match"]
                    if not pending:
                        break
                    finished, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in finished:
                        mid = pending.pop(future)
                        try:
                            result = future.result()
                        except Exception as error:
                            record(mid, error=error)
                        else:
                            record(mid, result=result)
        result = report(plan, data, out, expected)
        result["run_errors"] = sorted(errors, key=lambda x: x["match"])
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("run", "report"):
        sub = commands.add_parser(command)
        sub.add_argument(
            "--plan", type=Path, default=Path("reports/b5-farm-income-20261125/plan.json")
        )
        sub.add_argument("--data", type=Path, default=Path("data/demos-2026-11"))
        sub.add_argument("--out", type=Path, required=True)
        if command == "run":
            sub.add_argument(
                "--compat", type=Path, required=True, help="Pinned Gem package directory"
            )
            sub.add_argument("--workers", type=int, choices=range(1, 5), default=1)
            sub.add_argument(
                "--limit",
                type=int,
                help="First N planned matches, including already completed matches",
            )
            sub.add_argument("--match", dest="match_ids", type=int, action="append")
    args = parser.parse_args(argv)
    plan_bytes = read_source_bytes(args.plan)
    if hashlib.sha256(plan_bytes).hexdigest() != PLAN_SHA256:
        raise ValueError("fixed B5 plan bytes changed")
    plan = validate_plan(parse_source_json(plan_bytes))
    expected = binding(plan)
    if args.command == "run":
        # The capture imports Gem lazily. Pin its import directory to the requested archive.
        sys.path.insert(0, str(args.compat.resolve().parent))
        gem = importlib.import_module("gem")
        if Path(gem.__file__).resolve().parent != args.compat.resolve():
            raise ValueError("imported Gem does not match --compat")
        result = run(
            plan,
            args.data.resolve(),
            args.out.resolve(),
            expected,
            args.compat.resolve(),
            workers=args.workers,
            limit=args.limit,
            match_ids=args.match_ids,
        )
    else:
        result = report(plan, args.data.resolve(), args.out.resolve(), expected)
    if read_source_bytes(args.plan) != plan_bytes:
        raise ValueError("camp plan changed while running")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 1 if result.get("run_errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
