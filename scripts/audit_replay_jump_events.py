"""Audit frozen jumps against existing combat logs; no replay parse or training."""

import argparse
import hashlib
import json
from pathlib import Path

from dota_items.data.replay_jump_events import inspect_jumps
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash


def run(root, output):
    if output.exists():
        raise ValueError("Output exists; choose a new directory")
    hashes = {}

    def read(path, expected=None):
        data = read_source_bytes(path, max_bytes=512 * 1024 * 1024)
        digest = hashlib.sha256(data).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError(f"Input hash mismatch: {path}")
        hashes[str(path)] = digest
        return parse_source_json(data)

    code_paths = [
        Path(__file__),
        Path("src/dota_items/data/replay_jump_events.py"),
        Path("src/dota_items/data/source_io.py"),
        Path("src/dota_items/data/observer.py"),
        Path("src/dota_items/storage.py"),
    ]
    code = {str(p): file_hash(p) for p in code_paths}
    results = []
    paths = sorted(root.glob("*/audit.json"))
    if not paths:
        raise ValueError("No semantic audits")
    for path in paths:
        receipt = read(path.with_name("receipt.json"))
        audit = read(path, receipt["audit_sha256"])
        prep = Path(audit["provenance"]["preparation"])
        manifest = read(
            prep / "manifest.json", audit["provenance"]["consumed_files"]["manifest.json"]
        )
        raw = read(prep / "raw.json", manifest["files"]["raw.json"])
        if hashes[str(prep / "raw.json")] != audit["provenance"]["consumed_files"]["raw.json"]:
            raise ValueError("Semantic/raw hash mismatch")
        if not (
            receipt["match_id"] == manifest["match_id"] == raw["match_id"] == audit["match_id"]
        ):
            raise ValueError("Manifest/receipt identity mismatch")
        result = inspect_jumps(raw, audit)
        result["semantic_audit"] = str(path)
        results.append(result)
    if len({r["match_id"] for r in results}) != len(results):
        raise ValueError("Duplicate match")
    for path, digest in {**hashes, **code}.items():
        if file_hash(Path(path)) != digest:
            raise ValueError("Input or implementation drift")
    output.mkdir(parents=True, exist_ok=False)
    for result in results:
        (output / f"{result['match_id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
    summary = dict(
        inputs=hashes,
        implementation=code,
        training_admission=False,
        matches=[
            {k: r[k] for k in ("match_id", "counts", "recovery_counts", "multiple_candidate_jumps")}
            for r in results
        ],
        outputs={p.name: file_hash(p) for p in output.glob("*.json")},
    )
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semantics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.semantics, args.output)["matches"], indent=2))
