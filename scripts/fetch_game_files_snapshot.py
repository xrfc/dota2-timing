"""Snapshot Dota 2 game text files from a pinned GameTracking-Dota2 commit (U46)."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = "SteamDatabase/GameTracking-Dota2"
PREFIX = "game/dota/pak01_dir/"
SINGLE_FILES = (
    "scripts/npc/npc_abilities.txt",
    "resource/localization/abilities_english.txt",
)
ROOT = Path(__file__).resolve().parents[1]
ATTEMPTS = 4


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "dota2-timing-snapshot"})
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError:
            raise
        except OSError:
            if attempt == ATTEMPTS - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True, help="full mirror commit SHA")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only", nargs="+", help="fetch only these pak01_dir paths")
    args = parser.parse_args()
    out = args.out if args.out.is_absolute() else ROOT / args.out
    if out.exists():
        raise SystemExit(f"snapshot exists, not overwriting: {out}")

    registry = json.loads(
        (ROOT / "knowledge/hero-capabilities/hero-registry.json").read_text(encoding="utf-8")
    )
    heroes = sorted(f"scripts/npc/heroes/{hero['npc_name']}.txt" for hero in registry["heroes"])
    partial = out.with_name(out.name + ".partial")
    shutil.rmtree(partial, ignore_errors=True)
    records = []
    for relative in args.only or [*SINGLE_FILES, "steam.inf", *heroes]:
        source = "game/dota/steam.inf" if relative == "steam.inf" else PREFIX + relative
        url = f"https://raw.githubusercontent.com/{REPO}/{args.commit}/{source}"
        content = fetch(url)
        target = partial / "sources" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        records.append(
            {
                "file": f"sources/{relative}",
                "url": url,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    manifest = {
        "schema": "game-files-manifest/1",
        "purpose": "U46 check of mechanics evidence against game files; not for training",
        "mirror": REPO,
        "mirror_is_third_party": True,
        "commit": args.commit,
        "observed_at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "records": records,
    }
    (partial / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    partial.rename(out)
    print(f"files {len(records)} -> {out}")


if __name__ == "__main__":
    main()
