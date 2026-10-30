"""Opt-in offline probe of all ten heroes at the two fixed decision ticks; no future rows."""

import argparse
import json
import sys
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {9056008987: 41048, 9056008877: 38522}
VERSION = "decision-team-probe-plan/1"
REPAIR_PLAN = "reports/decision-mana-repair-2026-10-28-v1/plan.json"
IMPLEMENTATION = (
    "scripts/probe_team_state.py",
    "src/dota_items/sources/decision_mana.py",
    "src/dota_items/sources/decision_state_capture.py",
    "src/dota_items/sources/gem_capture.py",
    "src/dota_items/sources/gem_replay.py",
    "src/dota_items/data/decision_team_state.py",
    "src/dota_items/data/source_io.py",
    "src/dota_items/storage.py",
)


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
    """Reuse the repair plan's frozen parser and recordings, never its old implementation."""
    repair_path = repo / REPAIR_PLAN
    repair = read(repair_path)
    compat = Path(repair["compat"])
    archives = {c["match_id"]: c["archive"] for c in repair["cases"]}
    if set(archives) != set(TARGETS):
        raise ValueError("Unexpected historical selection")
    recordings = {str(Path(a).parent) for a in archives.values()}
    sources = {
        name: expected
        for name, expected in repair["sources"].items()
        if Path(name).is_relative_to(compat) or str(Path(name).parent) in recordings
    }
    sources[str(repair_path)] = file_hash(repair_path)
    verify_sources(sources)
    for name in IMPLEMENTATION:
        sources[str(repo / name)] = file_hash(repo / name)
    cases = [
        {
            "match_id": mid,
            "decision_tick": tick,
            "ticks": [tick - 30, tick],
            "archive": archives[mid],
        }
        for mid, tick in sorted(TARGETS.items())
    ]
    return {
        "schema": VERSION,
        "compat": str(compat),
        "sources": sources,
        "cases": cases,
        "training_allowed": False,
        "scope": "Original two matches; all ten heroes at decision tick and one second before",
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

    from dota_items.data.decision_team_state import PRODUCER
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
                    row = capture(self, snapshot)
                    if row is None:
                        raise ValueError("Missing canonical hero entity")
                    rows.append(row)

    with prepared_demo(Path(case["archive"]), output / "scratch") as demo:
        parser = build_first_parser(ReplayParser)(demo)
        probe = Probe()
        probe.attach(parser)
        parser.parse()
        require_complete_parse(parser)
        keys = sorted((r["tick"], r["player_id"]) for r in rows)
        expected = sorted((t, p) for t in case["ticks"] for p in range(10))
        if parser.match_id != mid or keys != expected:
            raise ValueError("Wrong replay or missing/duplicate selected samples")
        write(
            output / "capture.json",
            {
                "match_id": mid,
                "build": parser.game_build,
                "schema_game_build": parser.schema_game_build,
                "producer": PRODUCER,
                "demo_sha256": file_hash(demo),
                "decision_tick": case["decision_tick"],
                "rows": rows,
                "training_allowed": False,
            },
        )
    verify_sources(sources)
    write(
        output / "complete.json",
        {
            "schema": "decision-team-probe-complete/1",
            "match_id": mid,
            "plan_sha256": file_hash(plan_path),
            "outputs": {p.name: file_hash(p) for p in output.glob("*.json")},
            "source_unchanged": True,
            "samples": len(rows),
            "training_allowed": False,
        },
    )
    print(json.dumps({"match_id": mid, "samples": len(rows), "output": str(output)}), flush=True)


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
