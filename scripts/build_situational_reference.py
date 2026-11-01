"""M2b-T5: baseline 针对装 reference counts on the M1 training split (U20, U21).

Descriptive statistics only (no model is fitted). Writes JSON to a new directory.
"""

import argparse
import hashlib
from pathlib import Path

from dota_items.data.match_snapshot import load_snapshot
from dota_items.data.match_snapshot import write_new_json as write
from dota_items.data.source_io import read_source_bytes
from dota_items.modeling import situational_reference as sr
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = (
    "scripts/build_situational_reference.py",
    "src/dota_items/data/match_snapshot.py",
    "src/dota_items/modeling/situational_items.py",
    "src/dota_items/modeling/situational_reference.py",
)


def run(snapshot, output, repo=ROOT):
    snapshot, output = Path(snapshot), Path(output)
    if output.exists():
        raise ValueError("Output exists")
    implementation = {name: file_hash(repo / name) for name in IMPLEMENTATION}
    _, players, purchases, split = load_snapshot(snapshot)
    # Training split only: the same matches as the M2b baseline priors.
    result = sr.reference(players, purchases, split["train"])
    if {n: file_hash(repo / n) for n in IMPLEMENTATION} != implementation:
        raise ValueError("Inputs changed during build")
    output.mkdir(parents=True)
    write(output / "reference.json", {"schema": "m2b-situational-reference/1", **result})
    write(
        output / "manifest.json",
        {
            "schema": "m2b-situational-reference-run/1",
            "snapshot": str(snapshot),
            "snapshot_manifest_sha256": hashlib.sha256(
                read_source_bytes(snapshot / "manifest.json")
            ).hexdigest(),
            "split": "train",
            "train_matches": len(split["train"]),
            "support_items_decision": "U21",
            "implementation": implementation,
            "outputs": {"reference.json": file_hash(output / "reference.json")},
        },
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(args.snapshot, args.output)
    jugg = result["juggernaut"]
    print(f"juggernaut games={jugg['games']} with_any={jugg['games_with_any']}")
    for s in result["supports"]:
        print(f"support {s['spec']} games={s['games']}")


if __name__ == "__main__":
    main()
