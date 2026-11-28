#!/usr/bin/env python3
"""Consume the accepted B5 public handoff as condition evidence, never as camp stock."""

import argparse
import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path

from dota_items import storage
from dota_items.data import awareness_split, camp_conditions, source_io

ROOT = Path(__file__).resolve().parents[1]
PLAN_SHA256 = "8ad71d1e60b251360b9e96a4afc0c4a599443ddaa1c88abdb012b060cba7f3ad"
POPULATION_SHA256 = "4909b7905e5d5568831f96ca5cff385302fd28cd9a9228fde2c31c9746a80d42"
MANIFEST_SHA256 = "7e196e7f1c149d790ebd5132ba6f070f30d4dc2da492019383cf41f62f124318"
SNAPSHOT_SHA256 = "46caa3fff31a0cb0ba5dbcdab921c35a77c27432c024b4e48f2b02eaec391582"
COMPAT_SHA256 = "3f6e9ee2c222869adce45c6dfef757e719c9576bfdde82927e76d6868c47403d"
MATCHES, OPPORTUNITIES = 1169, 15005
ACTIONS = dict(stay_lane=6235, move_to_jungle=1176, unknown=7594)
FACT_FIELDS = (
    "visible_units",
    "alive",
    "not_alive",
    "life_unknown",
    "life_conflict",
    "alive_neutral_team",
    "alive_player_team",
    "alive_other_or_unknown_team",
    "alive_neutral_team_visible_health_sum",
)
CONDITIONS = ("camp_membership", "inventory", "route_traversability", "clearing_capacity")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path, expected, inputs):
    contents = source_io.read_source_bytes(path)
    actual = hashlib.sha256(contents).hexdigest()
    require(actual == expected, f"accepted input fingerprint mismatch: {path}")
    inputs[str(path)] = actual
    return source_io.parse_source_json(contents)


def read_plan(path, inputs):
    plan = load(path, PLAN_SHA256, inputs)
    require(storage.digest(plan) == PLAN_SHA256, "fixed plan canonical fingerprint mismatch")
    require(
        plan.get("schema") == "b5-farm-plan/1" and type(plan.get("matches")) is list,
        "invalid fixed plan",
    )
    require(len(plan["matches"]) == MATCHES, "fixed match population changed")
    matches, population = {}, []
    for match in plan["matches"]:
        mid = match.get("match")
        require(type(mid) is int and mid > 0 and mid not in matches, "invalid or duplicate match")
        require(
            not awareness_split.is_holdout(mid), "heldout match forbidden before evidence reads"
        )
        require(
            type(match.get("duration")) is int
            and match["duration"] > 0
            and type(match.get("patch")) is int
            and match["patch"] == 60,
            "invalid planned metadata",
        )
        require(type(match.get("cases")) is list and match["cases"], "empty planned match")
        fold = int.from_bytes(hashlib.sha256(f"lane-study-v1:{mid}".encode()).digest(), "big") % 5
        seen = set()
        for case in match["cases"]:
            require(
                set(case) == {"match", "hero", "t", "fold", "action"},
                "unexpected opportunity fields",
            )
            require(
                type(case["match"]) is int
                and case["match"] == mid
                and type(case["fold"]) is int
                and case["fold"] == fold,
                "opportunity match/fold mismatch",
            )
            require(
                type(case["hero"]) is str
                and case["hero"].startswith("npc_dota_hero_")
                and type(case["t"]) is int
                and case["t"] >= 0
                and case["action"] in ACTIONS,
                "invalid opportunity identity/action",
            )
            key = case["hero"], case["t"]
            require(key not in seen, "duplicate opportunity")
            seen.add(key)
            population.append(case)
        matches[mid] = match
    population.sort(key=lambda case: (case["match"], case["hero"], case["t"]))
    require(
        len(population) == OPPORTUNITIES and storage.digest(population) == POPULATION_SHA256,
        "fixed opportunity population changed",
    )
    require(
        Counter(case["action"] for case in population) == ACTIONS,
        "original action population changed",
    )
    return matches


def published_matches(batch):
    result = set()
    for directory in storage.inside(batch, "matches").iterdir():
        if directory.name.startswith(".stage-"):
            continue
        require(
            directory.name.isdecimal()
            and str(int(directory.name)) == directory.name
            and directory.is_dir()
            and not directory.is_symlink(),
            "unknown published match",
        )
        result.add(int(directory.name))
    return result


def accepted_inputs(plan_path, batch, snapshot_path):
    inputs = {}
    matches = read_plan(plan_path, inputs)
    manifest = load(storage.inside(batch, "manifest.json"), MANIFEST_SHA256, inputs)
    require(
        storage.digest(manifest) == MANIFEST_SHA256,
        "accepted manifest canonical fingerprint mismatch",
    )
    require(
        set(manifest)
        == {
            "schema",
            "plan_sha256",
            "population_sha256",
            "compat_manifest_sha256",
            "implementation_sha256",
        },
        "manifest fields",
    )
    require(
        manifest["schema"] == "b5-camp-run/1"
        and manifest["plan_sha256"] == PLAN_SHA256
        and manifest["population_sha256"] == POPULATION_SHA256
        and manifest["compat_manifest_sha256"] == COMPAT_SHA256,
        "accepted manifest identity mismatch",
    )
    snapshot = load(snapshot_path, SNAPSHOT_SHA256, inputs)
    require(
        storage.digest(snapshot) == SNAPSHOT_SHA256,
        "accepted snapshot canonical fingerprint mismatch",
    )
    require(
        set(snapshot)
        == {"schema", "plan_sha256", "manifest_sha256", "published_matches", "files_sha256"},
        "snapshot fields",
    )
    require(
        snapshot["schema"] == "camp-quality-snapshot/1"
        and snapshot["plan_sha256"] == PLAN_SHA256
        and snapshot["manifest_sha256"] == MANIFEST_SHA256,
        "accepted snapshot binding mismatch",
    )
    require(
        snapshot["published_matches"] == sorted(matches),
        "accepted snapshot lacks complete population",
    )
    require(
        published_matches(batch) == set(matches), "published population is incomplete or unplanned"
    )
    expected = {
        f"matches/{mid}/{name}" for mid in matches for name in ("receipt.json", "evidence.json")
    }
    require(set(snapshot["files_sha256"]) == expected, "accepted snapshot file inventory mismatch")
    return matches, manifest, snapshot, inputs


def read_public(batch, match, manifest, snapshot, inputs):
    mid = match["match"]
    values = {}
    for name in ("receipt.json", "evidence.json"):
        relative = f"matches/{mid}/{name}"
        values[name] = load(
            storage.inside(batch, relative), snapshot["files_sha256"][relative], inputs
        )
    receipt, public = values["receipt.json"], values["evidence.json"]
    require(
        set(receipt)
        == {
            "schema",
            "match_id",
            "source",
            "binding",
            "raw_sha256",
            "evidence_sha256",
            "payload_sha256",
        },
        "receipt fields",
    )
    require(
        receipt["schema"] == "b5-camp-record/1"
        and type(receipt["match_id"]) is int
        and receipt["match_id"] == mid,
        "receipt identity",
    )
    require(
        storage.digest(receipt["source"]) == storage.digest(match)
        and storage.digest(receipt["binding"]) == storage.digest(manifest),
        "receipt source/producer binding mismatch",
    )
    require(
        receipt["payload_sha256"]
        == storage.digest(
            {key: value for key, value in receipt.items() if key != "payload_sha256"}
        ),
        "receipt payload checksum mismatch",
    )
    require(
        receipt["evidence_sha256"] == snapshot["files_sha256"][f"matches/{mid}/evidence.json"],
        "receipt public evidence mismatch",
    )
    require(
        type(public.get("match_id")) is int and public["match_id"] == mid,
        "public evidence match identity",
    )
    return public


def producer_sources():
    """Hash the actual imports and reject a mixed checkout/archive import path."""
    paths = {"scripts/audit_b5_camp_conditions.py": Path(__file__).resolve()}
    for module in (camp_conditions, source_io, awareness_split, storage):
        relative = "src/" + module.__name__.replace(".", "/") + ".py"
        actual = Path(module.__file__).resolve()
        require(
            actual == storage.inside(ROOT, relative).resolve(),
            "imported producer is outside this checkout/archive",
        )
        paths[relative] = actual
    return {str(path): storage.file_hash(path) for path in paths.values()}


def frame_keys(frames):
    require(type(frames) is list, "frame list required")
    keys = set()
    for frame in frames:
        require(
            type(frame) is dict
            and type(frame.get("hero")) is str
            and type(frame.get("t")) is int
            and frame["t"] >= 0,
            "invalid frame identity",
        )
        key = frame["hero"], frame["t"]
        require(key not in keys, "duplicate frame identity")
        keys.add(key)
    return keys


def empty_stats():
    return dict(
        frames=0,
        frame_statuses={},
        facts_available_frames=0,
        facts_unavailable_frames=0,
        observed_zero_visible_frames=0,
        fact_observation_sums=dict.fromkeys(FACT_FIELDS, 0),
        life_evidence_observations={},
        team_relation_observations={},
        condition_statuses={name: {} for name in CONDITIONS},
        condition_missing_evidence={name: {} for name in CONDITIONS},
    )


def increment(counts, key, amount=1):
    counts[key] = counts.get(key, 0) + amount


def add_stats(stats, frame):
    stats["frames"] += 1
    increment(stats["frame_statuses"], frame["status"])
    facts = frame["facts"]
    if facts is None:
        stats["facts_unavailable_frames"] += 1
    else:
        require(
            set(facts) == set(FACT_FIELDS)
            and all(type(value) is int and value >= 0 for value in facts.values()),
            "unexpected condition facts",
        )
        stats["facts_available_frames"] += 1
        stats["observed_zero_visible_frames"] += facts["visible_units"] == 0
        for key, value in facts.items():
            stats["fact_observation_sums"][key] += value
    for unit in frame["units"]:
        increment(stats["life_evidence_observations"], unit["life_evidence"])
        increment(stats["team_relation_observations"], unit["team_relation"])
    require(set(frame["conditions"]) == set(CONDITIONS), "unexpected condition dimensions")
    for name, condition in frame["conditions"].items():
        require(
            condition["status"] == "unconfirmed" and condition["value"] is None,
            "unsupported confirmed condition",
        )
        increment(stats["condition_statuses"][name], condition["status"])
        for reason in condition["missing_evidence"]:
            increment(stats["condition_missing_evidence"][name], reason)


def verify_unchanged(inputs, sources, batch, matches):
    require(published_matches(batch) == set(matches), "published match inventory changed")
    for name, sha in (inputs | sources).items():
        require(
            storage.file_hash(Path(name)) == sha, f"input or producer changed during audit: {name}"
        )
    require(producer_sources() == sources, "actual producer imports changed during audit")


def audit(plan_path, batch, snapshot_path, out):
    out = storage.inside(out.parent, out.name)
    require(not out.exists(), "refusing existing condition audit output")
    require(
        not out.resolve().is_relative_to(batch.resolve())
        and out.resolve() != ROOT
        and not any(out.resolve().is_relative_to(ROOT / part) for part in ("src", "scripts")),
        "output must be outside batch and producer source",
    )
    sources = producer_sources()
    matches, manifest, snapshot, inputs = accepted_inputs(plan_path, batch, snapshot_path)
    overall, groups, boundary = empty_stats(), {}, []
    population = []
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".camp-conditions-", dir=out.parent) as temporary:
        staging = Path(temporary) / "audit"
        staging.mkdir()
        with (staging / "frames.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
            for mid, match in sorted(matches.items()):
                public = read_public(batch, match, manifest, snapshot, inputs)
                cases = {(case["hero"], case["t"]): case for case in match["cases"]}
                require(
                    frame_keys(public.get("frames")) == set(cases),
                    "public frame population differs from fixed plan",
                )
                result = camp_conditions.summarize_camp_evidence(public)
                require(
                    result.get("schema") == "camp-conditions/1"
                    and result.get("source_schema") == "camp-evidence/1"
                    and type(result.get("match_id")) is int
                    and result["match_id"] == mid
                    and result.get("sampling") == public["sampling"]
                    and result.get("usage") == "evidence_audit_only",
                    "condition API identity changed",
                )
                require(
                    frame_keys(result.get("frames")) == set(cases),
                    "condition output omitted or changed an opportunity",
                )
                for frame in sorted(
                    result["frames"], key=lambda value: (value["hero"], value["t"])
                ):
                    case = cases[frame["hero"], frame["t"]]
                    population.append(case)
                    metadata = dict(action=case["action"], fold=case["fold"])
                    row = dict(match_id=mid, audit_metadata=metadata, frame=frame)
                    stream.write(
                        json.dumps(
                            row,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                        + "\n"
                    )
                    add_stats(overall, frame)
                    team = frame["observer_team"]
                    for kind, values in (
                        ("action", (case["action"],)),
                        ("fold", (case["fold"],)),
                        ("observer_team", (team,)),
                        ("action_fold_observer_team", (case["action"], case["fold"], team)),
                    ):
                        add_stats(groups.setdefault((kind, values), empty_stats()), frame)
                    if case["t"] >= match["duration"]:
                        boundary.append(
                            dict(
                                **case,
                                duration=match["duration"],
                                status=frame["status"],
                                observer_team=team,
                                facts=frame["facts"],
                            )
                        )
        require(
            len(population) == OPPORTUNITIES and storage.digest(population) == POPULATION_SHA256,
            "output changed fixed population",
        )
        group_names = dict(
            action=("action",),
            fold=("fold",),
            observer_team=("observer_team",),
            action_fold_observer_team=("action", "fold", "observer_team"),
        )
        grouped = {}
        for (kind, values), stats in sorted(groups.items(), key=lambda item: json.dumps(item[0])):
            grouped.setdefault(kind, []).append(
                dict(zip(group_names[kind], values, strict=True), statistics=stats)
            )
        summary = dict(
            schema="b5-camp-conditions-audit/1",
            usage="evidence_audit_only",
            complete_population=True,
            matches=len(matches),
            opportunities=len(population),
            action_population=dict(Counter(case["action"] for case in population)),
            population_sha256=POPULATION_SHA256,
            overall=overall,
            groups=grouped,
            duration_boundary_cases=boundary,
            planned_at_duration=sum(c["t"] == c["duration"] for c in boundary),
            planned_after_duration=sum(c["t"] > c["duration"] for c in boundary),
            stock_complete=False,
            empty_confirmed=None,
            camp_id=None,
            limitations=[
                "Counts and health sums are repeated visible observations, not camp stock.",
                "Unavailable facts remain null in each frame; their frames are counted separately.",
                "Action and fold are original audit metadata, "
                "not condition evidence or model input.",
                "This consumes the accepted public handoff; "
                "no replay, omniscient capture, outcome or holdout is read.",
            ],
        )
        storage.write_json(staging / "summary.json", summary)
        verify_unchanged(inputs, sources, batch, matches)
        provenance = dict(
            schema="b5-camp-conditions-provenance/1",
            plan=str(plan_path),
            batch=str(batch),
            accepted_snapshot=str(snapshot_path),
            plan_sha256=PLAN_SHA256,
            manifest_sha256=MANIFEST_SHA256,
            snapshot_sha256=SNAPSHOT_SHA256,
            inputs_sha256_before=inputs,
            inputs_sha256_after=inputs,
            producer_sha256_before=sources,
            producer_sha256_after=sources,
            outputs_sha256={
                name: storage.file_hash(staging / name) for name in ("frames.jsonl", "summary.json")
            },
        )
        storage.write_json(staging / "provenance.json", provenance)
        with storage.writer_lock(out.parent):
            require(not out.exists(), "refusing existing condition audit output")
            verify_unchanged(inputs, sources, batch, matches)
            staging.rename(out)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan", type=Path, default=Path("reports/b5-farm-income-20261125/plan.json")
    )
    parser.add_argument(
        "--batch", type=Path, default=Path("reports/b5-camp-evidence-20261126/batch-v1")
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path("reports/b5-camp-evidence-quality-20261126/final/snapshot.json"),
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = audit(
        args.plan.resolve(), args.batch.resolve(), args.snapshot.resolve(), args.out.absolute()
    )
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "complete_population",
                    "matches",
                    "opportunities",
                    "action_population",
                    "overall",
                )
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
