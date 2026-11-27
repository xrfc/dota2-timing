"""Engineering replay CLI: explicit patches, bounded stages, immutable gzip bundles."""

import argparse
import json
from collections import Counter
from pathlib import Path

from dota_items.data.awareness_split import describe, is_holdout
from dota_items.data.replay_bundle import pack_files
from dota_items.data.replay_bundle_input import create_reference
from dota_items.storage import file_hash
from dota_items.workflow.replay_collection import (
    DEFAULT_COMPAT,
    current_producer,
    discover,
    load_json,
    make_plan,
    run_stages,
    write_new,
)


def engineering_exclusion():
    policy = describe()
    return {
        "algorithm": "sha256-mod100",
        "salt": policy["salt"],
        "percent": policy["holdout_percent"],
        "source": policy["schema"],
    }


def space_inventory(root):
    """Stat only: never opens replay content or changes existing artifacts."""
    root = Path(root).resolve()
    logical, allocated, seen = Counter(), Counter(), set()
    files = 0
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        info = path.stat()
        group = path.relative_to(root).parts[0]
        logical[group] += info.st_size
        files += 1
        inode = (info.st_dev, info.st_ino)
        if inode not in seen:
            allocated[group] += info.st_blocks * 512
            seen.add(inode)
    return {
        "root": str(root),
        "files": files,
        "logical_bytes": sum(logical.values()),
        "unique_allocated_bytes": sum(allocated.values()),
        "by_directory": dict(logical),
        "limits": "Stat only; each inode allocated once; no content deduplication claim",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("discover", help="Freeze an exact patch's bounded candidate plan")
    d.add_argument("--root", type=Path, required=True)
    d.add_argument("--patch", required=True)
    d.add_argument("--patch-code", type=int)
    d.add_argument("--route", choices=("proxy", "direct"), default="proxy")
    d.add_argument("--max-candidates", type=int, default=8)
    d.add_argument("--max-pages", type=int, default=6)
    d.add_argument("--max-metadata", type=int, default=12)
    d.add_argument("--max-seconds", type=int, default=300)
    d.add_argument("--min-duration", type=int, default=900)
    d.add_argument("--hero", type=int, action="append", default=[])
    s = sub.add_parser(
        "seed", help="Freeze explicit local metadata/demo references without downloading"
    )
    s.add_argument("--root", type=Path, required=True)
    s.add_argument("--patch", required=True)
    s.add_argument("--patch-code", type=int)
    s.add_argument("--snapshot", type=Path, required=True)
    s.add_argument("--retrieved-at", required=True)
    s.add_argument("--selection", type=Path, required=True)
    r = sub.add_parser("run", help="Run download/parse/verify separately or together, then stop")
    r.add_argument("--root", type=Path, required=True)
    r.add_argument("--stage", choices=("download", "parse", "verify", "all"), default="all")
    r.add_argument("--route", choices=("proxy", "direct"), default="proxy")
    r.add_argument("--compat", type=Path, default=DEFAULT_COMPAT)
    r.add_argument("--target", type=int, default=5)
    r.add_argument("--max-attempts", type=int, default=8)
    r.add_argument("--max-bytes", type=int, default=1024**3)
    r.add_argument("--max-seconds", type=int, default=1800)
    r.add_argument("--retry-failed", action="store_true")
    p = sub.add_parser(
        "pack", help="Losslessly compress explicit old files to a NEW archive; delete nothing"
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--match", type=int, required=True)
    p.add_argument("--files", type=Path, required=True, help="JSON object role -> source path")
    space = sub.add_parser("space", help="Read-only directory space inventory")
    space.add_argument("--root", type=Path, required=True)
    reference = sub.add_parser("reference", help="Verify a bundle and pin it for a consumer")
    reference.add_argument("--bundle", type=Path, required=True)
    reference.add_argument("--match", type=int, required=True)
    reference.add_argument("--output", type=Path, required=True)
    reference.add_argument("--compat", type=Path, default=DEFAULT_COMPAT)
    args = parser.parse_args(argv)
    exclusion = engineering_exclusion()
    if args.command == "discover":
        result = discover(
            args.root,
            patch=args.patch,
            exclusion=exclusion,
            route=args.route,
            expected_patch_code=args.patch_code,
            max_candidates=args.max_candidates,
            max_pages=args.max_pages,
            max_metadata=args.max_metadata,
            max_seconds=args.max_seconds,
            min_duration=args.min_duration,
            heroes=args.hero,
        )
        print(json.dumps({"plan": str(args.root / "plan.json"), "matches": len(result["matches"])}))
    elif args.command == "seed":
        result = make_plan(
            args.root,
            args.snapshot,
            patch=args.patch,
            retrieved_at=args.retrieved_at,
            rows=load_json(args.selection),
            exclusion=exclusion,
            expected_patch_code=args.patch_code,
        )
        print(json.dumps({"plan": str(args.root / "plan.json"), "matches": len(result["matches"])}))
    elif args.command == "run":
        result = run_stages(
            args.root,
            exclusion=exclusion,
            stage=args.stage,
            compat=args.compat,
            route=args.route,
            target=args.target,
            max_attempts=args.max_attempts,
            max_bytes=args.max_bytes,
            max_seconds=args.max_seconds,
            retry_failed=args.retry_failed,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["succeeded"] >= args.target else 2
    elif args.command == "pack":
        if args.match <= 0 or is_holdout(args.match):
            raise ValueError("Reserved/invalid match rejected before reading the file selection")
        sources = {name: Path(path) for name, path in load_json(args.files).items()}
        result = pack_files(
            args.output,
            sources,
            {"match_id": args.match, "purpose": "lossless_archive", "training_allowed": False},
            {"cli_sha256": file_hash(Path(__file__))},
        )
        print(json.dumps({"output": str(args.output), "quality": result["quality"]}))
    elif args.command == "reference":
        if args.match <= 0 or is_holdout(args.match):
            raise ValueError("Reserved/invalid match rejected before bundle access")
        value = create_reference(
            args.bundle,
            match_id=args.match,
            expected_producer=current_producer(args.compat),
            match_allowed=lambda mid: not is_holdout(mid),
        )
        write_new(args.output, value)
        print(json.dumps({"reference": str(args.output), "match_id": args.match}))
    else:
        print(json.dumps(space_inventory(args.root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
