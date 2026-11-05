"""Fetch official Simplified Chinese item text for the spot check page (U90). Run from repo root.

Display only: the facts still rest on the sources they were reviewed from.
"""

import hashlib
import json
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "knowledge/items/sources/itemdata-schinese-2026-11-05"
URL = "https://www.dota2.com/datafeed/itemdata?language=schinese&item_id={}"
RETRY_WAITS = (5, 20, 60)
CACHE = Path(sys.argv[1]) if len(sys.argv) > 1 else None
KEEP = ("id", "name", "name_loc", "desc_loc", "notes_loc", "special_values")


def fetch(item_id):
    request = urllib.request.Request(URL.format(item_id), headers={"User-Agent": "Mozilla/5.0"})
    for wait in RETRY_WAITS:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)["result"]["data"]["items"][0]
        except OSError as error:
            print("retry", item_id, error, flush=True)
            time.sleep(wait)
    raise RuntimeError(f"Could not fetch item {item_id}")


def main():
    listing = json.loads(
        (ROOT / "knowledge/items/sources/itemlist-schinese.json").read_text(encoding="utf-8")
    )["result"]["data"]["itemabilities"]
    ids = {row["name"].removeprefix("item_"): row["id"] for row in listing}
    objects = json.loads(
        (ROOT / "knowledge/mechanics/reviews/full-audit-001/objects.json").read_text(
            encoding="utf-8"
        )
    )
    wanted = sorted(o["subject"] for o in objects if o.get("is_item"))
    items, missing = {}, []
    for subject in wanted:
        if subject not in ids:
            missing.append(subject)
            continue
        cached = CACHE / f"{subject}.json" if CACHE else None
        if cached and cached.exists():
            items[subject] = json.loads(cached.read_text(encoding="utf-8"))
            continue
        row = fetch(ids[subject])
        items[subject] = {key: row.get(key) for key in KEEP}
        if cached:
            cached.write_text(json.dumps(items[subject], ensure_ascii=False), encoding="utf-8")
        time.sleep(1)
    OUT.mkdir(parents=True, exist_ok=False)
    body = json.dumps(items, ensure_ascii=False, indent=0) + "\n"
    (OUT / "items.json").write_text(body, encoding="utf-8")
    manifest = {
        "schema": "item-sources/1",
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "authorization": "U90 (user 2026-11-05)",
        "url": URL,
        "publisher": "Valve (official datafeed)",
        "purpose": "spot check page display only; not for training",
        "patch_verified": False,
        "items": len(items),
        "missing": missing,
        "sha256": hashlib.sha256(body.encode()).hexdigest(),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(len(items), "items; missing", missing)


if __name__ == "__main__":
    main()
