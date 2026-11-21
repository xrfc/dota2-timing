"""Prepare missing inputs offline for the three existing 7.41f decision-review matches."""

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
from importlib.metadata import PackageNotFoundError
from pathlib import Path

from build_replay_compat import build
from check_support_travel import MATCHES

REPO = Path(__file__).resolve().parents[1]
CAPTURE_SCHEMAS = {"state-v3": "gem-state-capture/3", "extras-v1": "gem-extras-capture/1"}
KINDS = ("parsed", *CAPTURE_SCHEMAS)


def _target(root, mid, kind):
    suffix = "normalized.json.gz" if kind == "parsed" else "jsonl.gz"
    return root / kind / f"{mid}.{suffix}"


def _check_match(root, mid):
    if mid not in MATCHES:
        raise ValueError(f"{mid}: outside the three 7.41f review matches")
    meta = json.loads((root / "meta" / f"{mid}.json").read_text(encoding="utf-8"))
    if meta.get("match_id") != mid or meta.get("patch") != 60:
        raise ValueError(f"{mid}: unexpected metadata match or patch")


def _validate(path, kind, mid):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        if kind == "parsed":
            parsed = json.load(stream)
            if (
                parsed.get("match_id") != mid
                or type(parsed.get("duration")) is not int
                or parsed["duration"] < 0
            ):
                raise ValueError(f"{path}: unexpected normalized match or duration")
            channels = parsed.get("context", {}).get("channels", {})
            if not all(
                isinstance(channels.get(key), list)
                for key in ("combat_log", "wards", "hero_visibility_events")
            ):
                raise ValueError(f"{path}: missing normalized review channels")
            return
        header = json.loads(stream.readline())
        if header.get("match_id") != mid or header.get("schema") != CAPTURE_SCHEMAS[kind]:
            raise ValueError(f"{path}: unexpected {kind} header")
        seconds = set()
        field = "heroes" if kind == "state-v3" else "creeps"
        for line in stream:
            row = json.loads(line)
            t = row.get("t")
            if type(t) is not int or t in seconds or not isinstance(row.get(field), list):
                raise ValueError(f"{path}: invalid {kind} sample at {t}")
            seconds.add(t)
        if not seconds or header.get("seconds", len(seconds)) != len(seconds):
            raise ValueError(f"{path}: incomplete {kind} capture")


def _archive(root, mid):
    for suffix in ("dem.bz2", "dem.zst"):
        path = root / "demos" / f"{mid}.{suffix}"
        if path.is_file():
            return path
    raise FileNotFoundError(f"{mid}: missing compressed replay in {root / 'demos'}")


def _derive(root, stage, mid, kinds):
    # Load producer dependencies only in the worker with the isolated Gem on its path.
    from collect_demos import compress
    from extract_creeps import extract as extract_extras
    from extract_state_v3 import extract as extract_state

    from dota_items.sources.gem_replay import ingest_demo

    _check_match(root, mid)
    source = _archive(root, mid)
    staged_demo = stage / "demos" / f"{mid}.dem.bz2"
    staged_demo.parent.mkdir(parents=True)
    # Both accepted archive suffixes are decoded by magic bytes in prepared_demo.
    try:
        os.link(source, staged_demo)
    except OSError:
        shutil.copyfile(source, staged_demo)
    created = []
    for kind in kinds:
        target = _target(root, mid, kind)
        if target.exists():
            _validate(target, kind, mid)
            continue
        staged = _target(stage, mid, kind)
        if kind == "parsed":
            imported = ingest_demo(staged_demo, stage / "cache")
            if imported["match_id"] != mid:
                raise ValueError(f"{mid}: archive contains match {imported['match_id']}")
            staged.parent.mkdir(exist_ok=True)
            compress(Path(imported["normalized_json"]), staged)
        elif kind == "state-v3":
            extract_state(stage, mid)
        elif kind == "extras-v1":
            extract_extras(stage, mid, kind="extras")
        else:
            raise ValueError(f"unknown decision input {kind}")
        _validate(staged, kind, mid)
        target.parent.mkdir(exist_ok=True)
        try:
            os.link(staged, target)
        except FileExistsError:
            # A concurrent worker published first. Keep and verify its complete file.
            _validate(target, kind, mid)
        else:
            created.append(kind)
    return created


def prepare_inputs(root, matches):
    """Validate existing inputs, publishing only missing artifacts in the local dataset."""
    root = Path(root).resolve()
    result, jobs = {}, {}
    for mid in dict.fromkeys(matches):
        _check_match(root, mid)
        row = result[str(mid)] = {"reused": [], "created": []}
        for kind in KINDS:
            path = _target(root, mid, kind)
            if path.exists():
                _validate(path, kind, mid)
                row["reused"].append(kind)
            else:
                jobs.setdefault(mid, []).append(kind)
        if mid in jobs:
            _archive(root, mid)
    if not jobs:
        return result

    with tempfile.TemporaryDirectory(prefix=".prepare-lane-", dir=root) as temp:
        stage = Path(temp)
        compat = stage / "compat"
        try:
            build(compat)
        except PackageNotFoundError as error:
            raise ValueError(
                "local replay preparation requires the project's gem-dota==0.10.0 replay dependency"
            ) from error
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join(map(str, (compat, REPO / "src", REPO / "scripts"))),
        }
        for mid, kinds in jobs.items():
            with tempfile.TemporaryDirectory(dir=stage, prefix=f"{mid}-") as match_temp:
                workspace = Path(match_temp)
                run = subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--worker",
                        str(workspace),
                        "--root",
                        str(root),
                        "--matches",
                        str(mid),
                        "--kinds",
                        *kinds,
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                )
                if run.returncode:
                    raise ValueError(
                        f"{mid}: local input preparation failed: {run.stderr.strip()[-1200:]}"
                    )
                created = json.loads(run.stdout)
            result[str(mid)]["created"] = created
            result[str(mid)]["reused"].extend(kind for kind in kinds if kind not in created)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--matches", type=int, nargs="+", default=MATCHES)
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--kinds", choices=KINDS, nargs="+", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        [mid] = args.matches
        created = _derive(args.root, args.worker, mid, args.kinds)
        print(json.dumps(created))
        return
    print(json.dumps(prepare_inputs(args.root, args.matches), indent=2))


if __name__ == "__main__":
    main()
