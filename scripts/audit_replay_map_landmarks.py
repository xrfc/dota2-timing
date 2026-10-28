"""Read-only landmark capture from a verified local replay; no player samples or training."""

import argparse
import json
import sys
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.sources.replay_identity import entity_evidence
from dota_items.storage import file_hash


def read(path):
    return parse_source_json(read_source_bytes(path))


def run(root, mid, compat, output):
    if output.exists():
        raise ValueError("Output exists")
    receipt = root / f"{mid}.receipt.json"
    archive = root / f"{mid}.dem.bz2"
    cm = compat / "manifest.json"
    expected = read(cm)["patched"]
    paths = [
        receipt,
        archive,
        cm,
        Path(__file__),
        Path("src/dota_items/sources/replay_identity.py"),
        Path("src/dota_items/sources/gem_replay.py"),
    ]
    for name, h in expected.items():
        p = compat / "gem" / name
        if file_hash(p) != h:
            raise ValueError("Compatibility hash mismatch")
        paths.append(p)
    before = {str(p): file_hash(p) for p in paths}
    if before[str(archive)] != read(receipt)["archive_sha256"]:
        raise ValueError("Archive hash mismatch")
    if "gem" in sys.modules:
        raise ValueError("Fresh process required")
    sys.path.insert(0, str(compat.resolve()))
    import gem
    from gem.parser import ReplayParser
    from gem.state.entities import EntityOp

    from dota_items.sources.gem_replay import prepared_demo

    if Path(gem.__file__).resolve().parent != (compat / "gem").resolve():
        raise ValueError("Wrong Gem")
    output.mkdir(parents=True)
    (output / "execution.json").write_text(json.dumps(before, indent=2))
    landmarks = {}
    with prepared_demo(archive, output / "scratch") as demo:
        demo_hash = file_hash(demo)
        parser = ReplayParser(demo)

        def collect(entity, op):
            if entity.get_class_name() not in {
                "CDOTA_BaseNPC_Tower",
                "CDOTA_BaseNPC_Barracks",
                "CDOTA_BaseNPC_Fort",
                "CDOTA_Unit_Fountain",
            } or op.has(EntityOp.DELETED):
                return
            row = entity_evidence(entity)
            key = tuple(
                row[k]
                for k in (
                    "entity_index",
                    "entity_serial",
                    "class_name",
                    "team",
                    "cell_x",
                    "cell_y",
                    "vec_x",
                    "vec_y",
                )
            )
            if key not in landmarks:
                landmarks[key] = {
                    **row,
                    "first_tick": parser.tick,
                    "last_tick": parser.tick,
                    "observations": 0,
                }
            landmarks[key]["last_tick"] = parser.tick
            landmarks[key]["observations"] += 1

        parser.on_entity(collect)
        parser.parse()
        if parser.parse_error is not None or parser.match_id != mid:
            raise ValueError("Incomplete or wrong replay")
        result = {
            "match_id": mid,
            "game_build": parser.game_build,
            "demo_sha256": demo_hash,
            "landmarks": list(landmarks.values()),
        }
    if before != {str(p): file_hash(p) for p in paths}:
        raise ValueError("Input/code drift")
    path = output / "capture.json"
    path.write_text(json.dumps(result, indent=2, allow_nan=False))
    (output / "receipt.json").write_text(
        json.dumps(
            {
                "capture_sha256": file_hash(path),
                "execution_sha256": file_hash(output / "execution.json"),
            }
        )
    )
    print(
        json.dumps({"match_id": mid, "build": result["game_build"], "records": len(landmarks)}),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--mid", type=int, required=True)
    p.add_argument("--compat", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    run(**vars(p.parse_args()))
