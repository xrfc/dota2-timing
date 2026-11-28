"""Prepare one raw Source 2 replay for offline decision review."""

import argparse
import gzip
import hashlib
import json
import shutil
import tempfile
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
from pathlib import Path

from dota_items.data.awareness_split import is_holdout
from dota_items.sources.gem_capture_extras import capture_extras
from dota_items.sources.gem_capture_v3 import capture_state_v3
from dota_items.sources.gem_replay import ingest_demo

PATCH_741F = (1789455600, 1794988800)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_compat(package, frozen):
    """Verify the imported package against the trained U191 parser file set."""
    directory = package.resolve()
    expected = frozen["compat"]
    actual = {
        "manifest.json",
        *("gem/" + p.relative_to(directory).as_posix() for p in directory.rglob("*.py")),
    }
    if actual != set(expected):
        raise ValueError("Active Gem source files differ from the U191 compatibility freeze")
    for name, signature in expected.items():
        if digest(directory.parent / name) != signature:
            raise ValueError(f"Active Gem differs from the U191 freeze at {name}")
    return expected["manifest.json"]


def active_compat():
    import gem

    freeze = Path(__file__).resolve().parents[1] / "docs/acceptance/outcome-u191-freeze.json"
    return verify_compat(Path(gem.__file__).parent, json.loads(freeze.read_text(encoding="utf-8")))


def replay_header(path):
    from gem.binary.stream import DemoStream
    from gem.proto.demo_pb2 import CDemoFileHeader, CDemoFileInfo

    game = header = None
    with DemoStream(path) as stream:
        for _, kind, payload in stream:
            if kind == 1:
                header = CDemoFileHeader.FromString(payload)
            if kind == 2:
                game = CDemoFileInfo.FromString(payload).game_info.dota
    if game is None or game.match_id <= 0 or header is None:
        raise ValueError("Replay is missing its Source 2 file header or embedded match ID")
    return {
        "match_id": game.match_id,
        "player_count": len(game.player_info),
        "game_mode": game.game_mode if game.HasField("game_mode") else None,
        "end_time": game.end_time if game.HasField("end_time") and game.end_time > 0 else None,
        "build_num": header.build_num if header.HasField("build_num") else None,
    }


def events(demo, result, scratch, mid):
    imported = ingest_demo(demo, scratch)
    if imported["match_id"] != mid:
        raise ValueError("Embedded match ID disagrees with normalized replay")
    path = Path(imported["normalized_json"])
    with path.open(encoding="utf-8") as stream:
        parsed = json.load(stream)
    if (
        parsed.get("match_id") != mid
        or type(parsed.get("duration")) is not int
        or parsed["duration"] <= 0
    ):
        raise ValueError("Normalized replay identity or duration missing")
    duration, game_mode = parsed["duration"], parsed.get("game_mode")
    del parsed
    target = result / "parsed" / f"{mid}.normalized.json.gz"
    target.parent.mkdir()
    with path.open("rb") as source, gzip.open(target, "wb", compresslevel=3) as out:
        shutil.copyfileobj(source, out, 1024 * 1024)
    return duration, game_mode, imported["issues"]


def states(demo, result, mid, name):
    capture = capture_state_v3 if name == "state-v3" else capture_extras
    header, rows = capture(demo)
    if not rows or len(rows) != header["seconds"]:
        raise ValueError(f"Incomplete {name} capture")
    folder = result / name
    folder.mkdir()
    with gzip.open(folder / f"{mid}.jsonl.gz", "wt", encoding="utf-8", compresslevel=3) as stream:
        print(json.dumps({**header, "match_id": mid}), file=stream)
        for row in rows:
            print(json.dumps(row, separators=(",", ":")), file=stream)
    return dict(samples=len(rows), schema=header["schema"])


def patch_window(end_time, duration):
    start = end_time - duration if end_time is not None else None
    patch = (
        "7.41f"
        if start is not None and PATCH_741F[0] <= start <= end_time < PATCH_741F[1]
        else None
    )
    return start, patch


def prepare(demo: Path, out: Path, expected_id: int | None = None):
    """Read a raw demo; publish all three outputs atomically to a fresh directory."""
    demo, out = Path(demo).resolve(), Path(out).resolve()
    if out.exists() or demo.suffix.lower() != ".dem":
        raise ValueError("Supply a raw .dem and a fresh output directory")
    compat_sha = active_compat()
    source_sha = digest(demo)
    info = replay_header(demo)
    mid = info["match_id"]
    if expected_id is not None and mid != expected_id:
        raise ValueError(f"Embedded match ID {mid} differs from requested {expected_id}")
    if is_holdout(mid):
        raise ValueError("Replay belongs to the reserved U133 partition")
    end_time = info["end_time"]
    if (
        info["game_mode"] != 22
        or info["player_count"] != 10
        or end_time is None
        or not PATCH_741F[0] <= end_time < PATCH_741F[1]
    ):
        raise ValueError("Expected a ten-player all-pick replay ending in the 7.41f window")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as staging:
        stage = Path(staging)
        result = stage / "inputs"
        result.mkdir()
        with ProcessPoolExecutor(max_workers=3) as pool:
            normalized = pool.submit(events, demo, result, stage / "ingest", mid)
            captures = [
                (name, pool.submit(states, demo, result, mid, name))
                for name in ("state-v3", "extras-v1")
            ]
            duration, mode, issues = normalized.result()
            details = {name: future.result() for name, future in captures}
        if mode != info["game_mode"] or source_sha != digest(demo):
            raise ValueError("Game-mode mismatch or replay changed during extraction")
        if active_compat() != compat_sha:
            raise ValueError("Parser compatibility files changed during extraction")
        start, patch = patch_window(info["end_time"], duration)
        names = sorted(result.glob("*/*.gz"))
        provenance = {
            "schema": "new-replay-inputs/1",
            "compat_manifest_sha256": compat_sha,
            **info,
            "duration": duration,
            "estimated_start_time": start,
            "patch_window": patch,
            "patch_741f_utc_bounds": list(PATCH_741F),
            "clock_source": "CDemoFileInfo.game_info.dota.end_time minus normalized match duration",
            "lobby_type": None,
            "rank_tier": None,
            "source_sha256": source_sha,
            "source_bytes": demo.stat().st_size,
            "inputs_sha256": {str(p.relative_to(result)): digest(p) for p in names},
            "parser_version": version("gem-dota"),
            "captures": details,
            "normalization_issues": issues,
        }
        (result / "replay-provenance.json").write_text(
            json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
        )
        result.rename(out)
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("demo", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--expected-id", type=int)
    args = parser.parse_args()
    provenance = prepare(args.demo, args.out, args.expected_id)
    print(f"Prepared match {provenance['match_id']} in {args.out}")


if __name__ == "__main__":
    main()
