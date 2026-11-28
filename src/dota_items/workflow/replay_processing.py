"""Isolated replay worker: one decode, compressed bundle and explicit quality admission."""

import argparse
import gzip
import hashlib
import importlib
import importlib.metadata
import json
import platform
import tempfile
from pathlib import Path

from dota_items.contracts.replay_collection import PatchWindow, validate_match_metadata
from dota_items.data.replay_bundle import BundleWriter, verify_bundle
from dota_items.data.replay_quality import ChannelAudit, inspect_base, quality_result
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.sources.replay_capture_bundle import capture_bundle, parser_identity
from dota_items.storage import file_hash

DEFAULT_COMPAT_SHA = "3f6e9ee2c222869adce45c6dfef757e719c9576bfdde82927e76d6868c47403d"
PRODUCERS = (
    "workflow.replay_processing",
    "data.replay_bundle",
    "data.replay_bundle_quality",
    "data.replay_quality",
    "data.source_io",
    "contracts.replay_collection",
    "sources.replay_capture_bundle",
    "sources.gem_capture",
    "sources.gem_capture_v3",
    "sources.gem_capture_creeps",
    "sources.gem_capture_extras",
    "sources.gem_replay",
    "sources.gem_observations",
    "contracts.replay_context",
    "contracts.numeric",
    "normalize",
    "domain",
    "storage",
)


def match_allowed(mid, exclusion):
    """Apply a caller-supplied partition without importing a product-line policy."""
    if type(mid) is not int or mid <= 0:
        raise ValueError("Match ID must be a positive integer")
    if (
        not isinstance(exclusion, dict)
        or exclusion.get("algorithm") != "sha256-mod100"
        or not isinstance(exclusion.get("salt"), str)
        or not exclusion["salt"]
        or type(exclusion.get("percent")) is not int
        or not 0 <= exclusion["percent"] <= 100
    ):
        raise ValueError("An explicit valid engineering exclusion policy is required")
    digest = hashlib.sha256(f"{exclusion['salt']}:{mid}".encode()).hexdigest()
    return int(digest, 16) % 100 >= exclusion["percent"]


def producer_identity(compat, expected_sha=DEFAULT_COMPAT_SHA):
    files = {}
    for name in PRODUCERS:
        module = importlib.import_module("dota_items." + name)
        path = Path(module.__file__).resolve()
        files[name] = {"path": str(path), "sha256": file_hash(path)}
    return {
        "schema": "replay-processing-producer/1",
        "sources": files,
        "parser": parser_identity(Path(compat), expected_sha),
        "python": platform.python_version(),
        "dependencies": {
            name: importlib.metadata.version(name) for name in ("gem-dota", "protobuf", "zstandard")
        },
    }


def source_reference(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError("Source artifact is missing")
    return {"path": str(path), "sha256": file_hash(path), "size_bytes": path.stat().st_size}


def check_reference(reference):
    actual = source_reference(reference["path"])
    if any(actual[key] != reference.get(key) for key in actual):
        raise ValueError("Source artifact changed")


def load_json(path):
    return parse_source_json(read_source_bytes(Path(path)))


def process_request(request_path, output, compat, expected_sha=DEFAULT_COMPAT_SHA):
    request = load_json(request_path)
    mid = request["match_id"]
    if not match_allowed(mid, request["exclusion"]):
        raise ValueError("Reserved match rejected before reading match inputs")
    identity = request["identity"]
    if identity.get("match_id") != mid or identity.get("training_allowed") is not False:
        raise ValueError("Invalid engineering identity")
    if (
        identity.get("discovery") != request["discovery"]
        or identity.get("exclusion") != request["exclusion"]
        or type(request["discovery"].get("match_id")) is not int
        or request["discovery"]["match_id"] != mid
    ):
        raise ValueError("Request selection differs from its frozen identity")
    if identity.get("parameters") != {
        "capture_start": -90,
        "output_window": "0..metadata.duration",
        "codec": "gzip",
        "quality_schema": "replay-quality/1",
    }:
        raise ValueError("Unrecognized processing parameters")
    paths = [
        str(Path(request[key]).resolve()) for key in ("snapshot_path", "metadata_path", "demo_path")
    ]
    references = identity["source_references"]
    if (
        len(set(paths)) != 3
        or len(references) != 3
        or [str(Path(ref["path"]).resolve()) for ref in references] != paths
    ):
        raise ValueError("Actual inputs must match the three frozen source references")
    producer = producer_identity(compat, expected_sha)
    if producer != request["producer"]:
        raise ValueError("Worker producer differs from requested producer")
    for reference in identity["source_references"]:
        check_reference(reference)
    meta = load_json(request["metadata_path"])
    if type(meta.get("match_id")) is not int or meta["match_id"] != mid:
        raise ValueError("Metadata belongs to another match")
    window = PatchWindow.from_dict(identity["patch_window"])
    snapshot = read_source_bytes(Path(request["snapshot_path"]))
    actual_window = PatchWindow.from_snapshot(
        snapshot,
        patch=window.patch,
        retrieved_at=window.retrieved_at,
        boundary_buffer_seconds=window.boundary_buffer_seconds,
    )
    if actual_window != window:
        raise ValueError("Official patch evidence changed")
    reasons = validate_match_metadata(
        meta,
        request["discovery"],
        window,
        expected_patch_code=identity["expected_patch_code"],
        bounds=identity["bounds"],
        min_duration=identity["min_duration"],
        min_rank=identity["min_rank"],
    )
    if reasons:
        raise ValueError("Metadata rejected: " + ",".join(reasons))
    output = Path(output)
    if output.exists():
        raise FileExistsError("Parse output already exists; use a new attempt")
    output.parent.mkdir(parents=True, exist_ok=True)
    from dota_items.sources.gem_replay import prepared_demo

    with tempfile.TemporaryDirectory(prefix=".replay-spool-", dir=output.parent) as temporary:
        scratch = Path(temporary)
        audits = {name: ChannelAudit(name, meta["duration"]) for name in ("state", "extras")}
        spools = {name: scratch / f"{name}.jsonl.gz" for name in audits}
        with (
            gzip.open(spools["state"], "wt", encoding="utf-8") as state_file,
            gzip.open(spools["extras"], "wt", encoding="utf-8") as extra_file,
        ):

            def sink(name, stream):
                def append(row):
                    if audits[name].accept(row):
                        stream.write(
                            json.dumps(
                                row, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                            )
                            + "\n"
                        )

                return append

            with prepared_demo(Path(request["demo_path"]), scratch) as replay:
                replay_sha = file_hash(replay)
                result = capture_bundle(
                    replay,
                    emit_state=sink("state", state_file),
                    emit_extras=sink("extras", extra_file),
                )
        summaries = {name: audit.finish() for name, audit in audits.items()}
        if any(
            type(value.get("match_id")) is not int or value["match_id"] != mid
            for value in (result["parser"], result["normalized"])
        ):
            raise ValueError("Observed parser or normalized identity mismatch")
        base = inspect_base(result["normalized"], result["parser"], meta)
        quality = quality_result(base, summaries["state"], summaries["extras"])
        quality["parser"] = result["parser"]
        quality["unpacked_demo_sha256"] = replay_sha
        quality["adapter_issues"] = result["issues"]
        for reference in identity["source_references"]:
            check_reference(reference)
        if producer_identity(compat, expected_sha) != producer:
            raise ValueError("Producer changed during parsing")
        writer = BundleWriter(output, identity=identity, producer=producer)
        raw = writer.add_json("raw", result["raw"], filename="raw-gem.json.gz")
        result["normalized"]["evidence_source"] = raw["path"]
        result["normalized"]["evidence_sha256"] = raw["uncompressed_sha256"]
        writer.add_json("normalized", result["normalized"], filename="normalized.json.gz")
        for name, schema in (("state", "state-v3"), ("extras", "extras-v1")):
            header = {
                **result["headers"][name],
                "seconds": summaries[name]["in_game_rows"],
                "match_id": mid,
                "window": {"start": 0, "end_inclusive": meta["duration"]},
                "producer_schema": producer["schema"],
            }

            def rows(path=spools[name]):
                with gzip.open(path, "rb") as stream:
                    for line in stream:
                        yield parse_source_json(line)

            writer.add_channel(name, header, rows(), filename=schema + ".jsonl.gz")
        if producer_identity(compat, expected_sha) != producer:
            raise ValueError("Producer changed before bundle publication")
        manifest = writer.finish(quality)
        verify_bundle(output, expected_identity=identity, expected_producer=producer)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compat", type=Path, required=True)
    parser.add_argument("--compat-sha", default=DEFAULT_COMPAT_SHA)
    parser.add_argument("--identity", action="store_true")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.identity:
        print(json.dumps(producer_identity(args.compat, args.compat_sha)))
    elif args.request is not None and args.output is not None:
        manifest = process_request(args.request, args.output, args.compat, args.compat_sha)
        print(json.dumps({"status": manifest["quality"]["status"], "output": str(args.output)}))
    else:
        parser.error("--identity or both --request and --output are required")


if __name__ == "__main__":
    main()
