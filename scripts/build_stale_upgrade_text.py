"""List scepter/shard text the Valve datafeed keeps for abilities without that upgrade.

Reads the raw English hero responses (the Chinese ones carry the same flags; checked
here). Writes a new file only:

    PYTHONPATH=src python scripts/build_stale_upgrade_text.py \
        --output knowledge/mechanics/stale-upgrade-text-v1.json
"""

import argparse
import hashlib
import json
from pathlib import Path

from dota_items.data.mechanics_facts_v3 import stale_upgrades

ROOT = Path(__file__).resolve().parents[1]
RAW = "knowledge/hero-capabilities/sources"


def raw_heroes(repo, language):
    files = sorted((repo / RAW).glob(f"hero-*-{language}.json"))
    heroes = [json.loads(p.read_bytes())["result"]["data"]["heroes"][0] for p in files]
    return files, heroes


def build(repo=ROOT):
    files, heroes = raw_heroes(repo, "english")
    _, chinese = raw_heroes(repo, "schinese")
    entries = stale_upgrades(heroes)
    if entries != stale_upgrades(chinese):
        raise ValueError("English and Chinese upgrade flags disagree")
    return {
        "schema": "stale-upgrade-text/1",
        "patch_verified": False,
        "meaning": (
            "Upgrade text present in the 2026-10-09 Valve datafeed snapshot while the "
            "ability's ability_has_scepter/ability_has_shard flag is false. Treated as "
            "not current; abilities granted by the same upgrade are not listed."
        ),
        "source_sha256": {
            str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
        },
        "entries": entries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New file, never overwritten")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output already exists; choose a new file")
    doc = build()
    args.output.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    print(len(doc["entries"]), "entries")


if __name__ == "__main__":
    main()
