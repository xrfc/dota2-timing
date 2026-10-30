"""Fixed two-match, isolated offline state probe. No network, old cache writes or training."""

import argparse
import json
import sys
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {9056008987: (4, 41048), 9056008877: (0, 38522)}


def write(path, obj):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def read(path):
    return parse_source_json(read_source_bytes(path))


def prepare_plan(output):
    if output.exists():
        raise ValueError("Plan output exists")
    compat = ROOT / "data/replay-pilot-2026-10-22/compat-v1"
    sources = {str(compat / "manifest.json"): file_hash(compat / "manifest.json")}
    for name, expected in read(compat / "manifest.json")["patched"].items():
        path = compat / "gem" / name
        if file_hash(path) != expected:
            raise ValueError("Compatibility drift")
        sources[str(path)] = expected
    from dota_items.sources import decision_state_capture

    for path in [
        Path(__file__),
        Path(decision_state_capture.__file__),
        ROOT / "src/dota_items/sources/gem_replay.py",
        ROOT / "src/dota_items/data/source_io.py",
    ]:
        sources[str(path.resolve())] = file_hash(path)
    cases = []
    for mid, (pid, tick) in TARGETS.items():
        folder = ROOT / "data/replay-expansion-2026-10-26-v1"
        archive, receipt = folder / f"{mid}.dem.bz2", folder / f"{mid}.receipt.json"
        if (
            read(receipt)["match_id"] != mid
            or file_hash(archive) != read(receipt)["archive_sha256"]
        ):
            raise ValueError("Archive identity/hash mismatch")
        sources[str(archive)], sources[str(receipt)] = file_hash(archive), file_hash(receipt)
        cases.append(
            {
                "match_id": mid,
                "player_id": pid,
                "ticks": [tick - 30, tick, tick + 30],
                "decision_tick": tick,
                "archive": str(archive),
            }
        )
    write(
        output,
        {
            "schema": "decision-probe-plan/1",
            "compat": str(compat),
            "cases": cases,
            "sources": sources,
            "training_allowed": False,
            "scope": (
                "Only two frozen demos. Three native sample ticks each; "
                "later tick is validation only."
            ),
        },
    )


def run(plan_path, mid, output):
    if output.exists() or "gem" in sys.modules:
        raise ValueError("Requires new output and fresh parser process")
    plan = read(plan_path)
    if plan["schema"] != "decision-probe-plan/1" or set(TARGETS) != {
        c["match_id"] for c in plan["cases"]
    }:
        raise ValueError("Unsupported fixed plan")
    for path, expected in plan["sources"].items():
        if file_hash(Path(path)) != expected:
            raise ValueError("Plan source drift")
    case = next(c for c in plan["cases"] if c["match_id"] == mid)
    pid, tick = TARGETS[mid]
    if case["player_id"] != pid or case["ticks"] != [tick - 30, tick, tick + 30]:
        raise ValueError("Fixed selection changed")
    sys.path.insert(0, plan["compat"])
    import gem
    from gem.extractors.players import PlayerExtractor
    from gem.parser import ReplayParser

    from dota_items.sources.decision_state_capture import capture
    from dota_items.sources.gem_capture import require_complete_parse
    from dota_items.sources.gem_replay import prepared_demo

    if Path(gem.__file__).resolve().parent != Path(plan["compat"]) / "gem":
        raise ValueError("Wrong parser")
    output.mkdir(parents=True)
    write(output / "started.json", {"plan_sha256": file_hash(plan_path), "case": case})
    rows = []

    class Probe(PlayerExtractor):
        def _sample(self, tick, minute=False):
            start = len(self.snapshots)
            super()._sample(tick, minute=minute)
            if tick in case["ticks"]:
                for snapshot in self.snapshots[start:]:
                    if snapshot.player_id == pid:
                        rows.append(capture(self, snapshot))

    with prepared_demo(Path(case["archive"]), output / "scratch") as demo:
        parser = ReplayParser(demo)
        players = Probe()
        players.attach(parser)
        parser.parse()
        require_complete_parse(parser)
        if parser.match_id != mid or sorted(r["tick"] for r in rows if r) != case["ticks"]:
            raise ValueError("Wrong replay or missing/duplicate selected snapshots")
        write(
            output / "capture.json",
            {
                "match_id": mid,
                "build": parser.game_build,
                "demo_sha256": file_hash(demo),
                "rows": rows,
                "decision_tick": tick,
                "training_allowed": False,
            },
        )
    for path, expected in plan["sources"].items():
        if file_hash(Path(path)) != expected:
            raise ValueError("Source drift during probe")
    write(
        output / "complete.json",
        {
            "plan_sha256": file_hash(plan_path),
            "capture_sha256": file_hash(output / "capture.json"),
            "match_id": mid,
            "rows": len(rows),
            "source_unchanged": True,
        },
    )
    print(json.dumps({"match_id": mid, "rows": len(rows), "output": str(output)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-plan", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--match", type=int, choices=sorted(TARGETS))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.freeze_plan:
        prepare_plan(args.freeze_plan)
    elif args.plan and args.match and args.output:
        run(args.plan, args.match, args.output)
    else:
        parser.error("Choose --freeze-plan FILE or --plan FILE --match ID --output DIR")


if __name__ == "__main__":
    main()
