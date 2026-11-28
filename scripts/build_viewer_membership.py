"""Publish strictly verified protocol viewer membership, without FOW certification."""

import argparse
import json
import tempfile
from pathlib import Path

from dota_items.data.atomic_directory import publish_directory
from dota_items.data.awareness_split import is_holdout
from dota_items.data.patch_asset_evidence import EvidencePins
from dota_items.data.viewer_membership import project_membership
from dota_items.data.viewer_wire_io import read_viewer_capture
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]


def run(capture_ref, receipt_ref, output):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists")
    pins = EvidencePins()
    capture = read_viewer_capture(
        capture_ref,
        receipt_ref,
        pins=pins,
        repository_root=ROOT,
        match_allowed=lambda mid: not is_holdout(mid),
    )
    for name in ("scripts/build_viewer_membership.py", "src/dota_items/data/viewer_membership.py"):
        pins.track(ROOT / name)
    result = project_membership(capture)
    result.update(
        match_id=capture["match_id"], patch=capture["patch"], game_build=capture["game_build"]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".viewer-members-", dir=output.parent) as tmp:
        staging = Path(tmp) / "result"
        staging.mkdir()
        with (staging / "membership.json").open("w") as stream:
            json.dump(result, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            stream.write("\n")
        receipt = {
            "schema": "viewer-membership-receipt/1",
            "capture": capture_ref,
            "capture_receipt": receipt_ref,
            "used_files": pins.inventory,
            "output_sha256": {"membership.json": file_hash(staging / "membership.json")},
            "training_allowed": False,
            "action_review_allowed": False,
        }
        (staging / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        pins.verify()
        publish_directory(staging, output)
    return {
        k: result[k]
        for k in ("match_id", "entity_identities", "length_writes", "shrinks", "raw_writes")
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("capture", "capture-sha256", "receipt", "receipt-sha256", "output"):
        p.add_argument("--" + name, required=True)
    args = p.parse_args()
    print(
        json.dumps(
            run(
                {"path": args.capture, "sha256": args.capture_sha256},
                {"path": args.receipt, "sha256": args.receipt_sha256},
                args.output,
            )
        )
    )


if __name__ == "__main__":
    main()
