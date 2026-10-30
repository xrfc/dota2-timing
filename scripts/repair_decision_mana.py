"""Opt-in offline re-decode of the original two recordings; no cache replacement."""

import argparse
import json
import sys
from pathlib import Path

from dota_items.data.decision_mana import compare_captures, current_resource
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {9056008987: (4, 41048), 9056008877: (0, 38522)}
VERSION = "decision-mana-repair-plan/1"


def read(path):
    return parse_source_json(read_source_bytes(path))


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def verify_sources(sources):
    for name, expected in sources.items():
        if file_hash(Path(name)) != expected:
            raise ValueError(f"Frozen source drift: {name}")


def assemble_plan(repo=ROOT):
    """Reconstruct the exact source allowlist, not a caller-editable source subset."""
    probes = repo / "reports/decision-live-probe-2026-10-27-v2"
    old_plan_path = probes / "plan.json"
    old_plan = read(old_plan_path)
    verify_sources(old_plan["sources"])
    compat = Path(old_plan["compat"])
    manifest = read(compat / "manifest.json")
    sources = dict(old_plan["sources"])
    sources[str(old_plan_path)] = file_hash(old_plan_path)
    for name, expected in manifest["patched"].items():
        path = compat / "gem" / name
        if path.resolve().is_relative_to((compat / "gem").resolve()) is False:
            raise ValueError("Invalid compatibility manifest path")
        sources[str(path)] = expected
    verify_sources(sources)
    expected_files = {str((compat / "gem" / name).resolve()) for name in manifest["patched"]}
    actual_files = {str(p.resolve()) for p in (compat / "gem").rglob("*.py")}
    if actual_files != expected_files:
        raise ValueError("Unexpected compatibility parser file set")
    for name in (
        "scripts/repair_decision_mana.py",
        "src/dota_items/sources/decision_mana.py",
        "src/dota_items/data/decision_mana.py",
        "src/dota_items/sources/decision_state_capture.py",
        "src/dota_items/sources/gem_capture.py",
        "src/dota_items/sources/gem_replay.py",
        "src/dota_items/data/source_io.py",
        "src/dota_items/storage.py",
    ):
        path = repo / name
        sources[str(path)] = file_hash(path)
    cases = []
    if len(old_plan["cases"]) != 2:
        raise ValueError("Unexpected historical selection")
    for old_case in old_plan["cases"]:
        mid = old_case["match_id"]
        if mid not in TARGETS:
            raise ValueError("Unexpected historical match")
        player_id, tick = TARGETS[mid]
        if old_case["player_id"] != player_id or old_case["decision_tick"] != tick:
            raise ValueError("Historical target changed")
        folder = probes / str(mid)
        old_capture, complete_path = folder / "capture.json", folder / "complete.json"
        complete = read(complete_path)
        if (
            complete["plan_sha256"] != file_hash(old_plan_path)
            or complete["capture_sha256"] != file_hash(old_capture)
            or complete["match_id"] != mid
            or complete["source_unchanged"] is not True
        ):
            raise ValueError("Invalid historical completion receipt")
        for path in (old_capture, complete_path):
            sources[str(path)] = file_hash(path)
        cases.append(
            {
                "match_id": mid,
                "player_id": player_id,
                "decision_tick": tick,
                "ticks": list(range(tick - 1800, tick + 31, 30)),
                "archive": old_case["archive"],
                "old_capture": str(old_capture),
            }
        )
    if len({c["match_id"] for c in cases}) != 2:
        raise ValueError("Duplicate historical match")
    return {
        "schema": VERSION,
        "compat": str(compat),
        "sources": sources,
        "cases": cases,
        "training_allowed": False,
        "scope": "Original two matches; fixed past-60s/current/+1s diagnostic window only",
    }


def prepare_plan(output):
    if output.exists():
        raise ValueError("Plan output exists")
    plan = assemble_plan()
    output.parent.mkdir(parents=True, exist_ok=True)
    write(output, plan)
    print(json.dumps({"plan": str(output), "matches": len(plan["cases"])}), flush=True)


def run(plan_path, mid, output):
    if output.exists() or any(n == "gem" or n.startswith("gem.") for n in sys.modules):
        raise ValueError("Requires new output and fresh parser process")
    plan = read(plan_path)
    if plan != assemble_plan():
        raise ValueError("Plan differs from fixed selection or current implementation")
    sources = {**plan["sources"], str(plan_path.resolve()): file_hash(plan_path)}
    verify_sources(sources)
    case = next((c for c in plan["cases"] if c["match_id"] == mid), None)
    if case is None:
        raise ValueError("Match outside fixed plan")
    sys.dont_write_bytecode = True
    sys.path.insert(0, plan["compat"])
    import gem
    from gem.extractors.players import PlayerExtractor
    from gem.parser import ReplayParser

    from dota_items.sources.decision_mana import VERSION as PRODUCER_VERSION
    from dota_items.sources.decision_mana import build_first_parser
    from dota_items.sources.decision_state_capture import capture
    from dota_items.sources.gem_capture import require_complete_parse
    from dota_items.sources.gem_replay import prepared_demo

    if Path(gem.__file__).resolve().parent != (Path(plan["compat"]) / "gem").resolve():
        raise ValueError("Wrong isolated parser import")
    output.mkdir(parents=True)
    write(output / "started.json", {"plan_sha256": file_hash(plan_path), "case": case})
    selected_ticks = set(case["ticks"])
    rows = []

    class Probe(PlayerExtractor):
        def _sample(self, tick, minute=False):
            start = len(self.snapshots)
            super()._sample(tick, minute=minute)
            if tick in selected_ticks:
                for snapshot in self.snapshots[start:]:
                    if snapshot.player_id == case["player_id"]:
                        row = capture(self, snapshot)
                        if row is None:
                            raise ValueError("Missing target canonical entity")
                        rows.append(row)

    parser_type = build_first_parser(ReplayParser)
    with prepared_demo(Path(case["archive"]), output / "scratch") as demo:
        parser = parser_type(demo)
        probe = Probe()
        probe.attach(parser)
        parser.parse()
        require_complete_parse(parser)
        if parser.match_id != mid or [r["tick"] for r in rows] != case["ticks"]:
            raise ValueError("Wrong replay or missing/duplicate selected samples")
        result = {
            "match_id": mid,
            "build": parser.game_build,
            "schema_game_build": parser.schema_game_build,
            "producer": PRODUCER_VERSION,
            "demo_sha256": file_hash(demo),
            "decision_tick": case["decision_tick"],
            "rows": rows,
            "training_allowed": False,
        }
        # Retain failed attempts as well; complete.json is published only on success.
        write(output / "capture.json", result)
        comparison = compare_captures(read(Path(case["old_capture"])), result)
        write(output / "comparison.json", comparison)
        write(output / "current-resource.json", current_resource(comparison))
    verify_sources(sources)
    write(
        output / "complete.json",
        {
            "schema": "decision-mana-repair-complete/1",
            "match_id": mid,
            "plan_sha256": file_hash(plan_path),
            "outputs": {p.name: file_hash(p) for p in output.glob("*.json")},
            "source_unchanged": True,
            "samples": len(rows),
            "paired_samples": len(comparison["paired_samples"]),
            "training_allowed": False,
            "independent_gameplay_units_certified": False,
        },
    )
    print(
        json.dumps(
            {
                "match_id": mid,
                "samples": len(rows),
                "negative_delta_intervals": comparison["negative_delta_intervals"],
                "positive_delta_intervals": comparison["positive_delta_intervals"],
                "output": str(output),
            }
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-plan", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--match", type=int, choices=sorted(TARGETS))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.freeze_plan and not any((args.plan, args.match, args.output)):
        prepare_plan(args.freeze_plan)
    elif args.plan and args.match and args.output and not args.freeze_plan:
        run(args.plan, args.match, args.output)
    else:
        parser.error("Choose --freeze-plan FILE or --plan FILE --match ID --output DIR")


if __name__ == "__main__":
    main()
