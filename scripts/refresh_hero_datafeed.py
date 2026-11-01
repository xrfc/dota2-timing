"""Fetch a new Valve hero datafeed snapshot and diff it against an older one (U36).

Only for checking which ability texts/fields changed since the 2026-10-09 snapshot.
The endpoints carry no patch id, so a new snapshot is still patch_verified=false.
Nothing is overwritten: `fetch` refuses an existing directory.

    # 1. download (network; user-authorized U36)
    python scripts/refresh_hero_datafeed.py fetch \
        --output knowledge/hero-capabilities/snapshots/2026-11-01
    # 2. compare with the old snapshot (offline)
    python scripts/refresh_hero_datafeed.py diff \
        --old knowledge/hero-capabilities/sources \
        --new knowledge/hero-capabilities/snapshots/2026-11-01/sources \
        --output knowledge/hero-capabilities/snapshots/2026-11-01/diff-vs-2026-10-09.json
"""

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

BASE = "https://www.dota2.com/datafeed"
LANGUAGES = ("english", "schinese")
ABILITY_TEXT = ("name_loc", "desc_loc", "notes_loc", "scepter_loc", "shard_loc", "facets_loc")
ABILITY_FIELDS = (
    "ability_has_scepter",
    "ability_has_shard",
    "ability_is_granted_by_scepter",
    "ability_is_granted_by_shard",
    "ability_is_innate",
    "type",
    "behavior",
    "target_team",
    "target_type",
    "damage",
    "immunity",
    "dispellable",
    "max_level",
    "cooldowns",
    "mana_costs",
    "cast_ranges",
    "channel_times",
    "special_values",
)
HERO_FIELDS = ("name_loc", "facets", "facet_abilities", "talents")


def get(url, attempts=3):
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=35) as response:
                return response.read()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(attempt + 1)


def fetch(output):
    output = Path(output)
    if output.exists():
        raise SystemExit("Output already exists; choose a new directory")
    sources = output / "sources"
    sources.mkdir(parents=True)
    records = []

    def save(name, url, payload):
        (sources / name).write_bytes(payload)
        records.append(
            {
                "file": "sources/" + name,
                "url": url,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "observed_at_utc": datetime.now(UTC).isoformat(),
            }
        )

    ids = None
    for language in LANGUAGES:
        url = f"{BASE}/herolist?language={language}"
        payload = get(url)
        heroes = json.loads(payload)["result"]["data"]["heroes"]
        save(f"herolist-{language}.json", url, payload)
        if ids is None:
            ids = sorted(h["id"] for h in heroes)
        elif ids != sorted(h["id"] for h in heroes):
            raise SystemExit("English and Chinese hero lists differ")
    for hero_id in ids:
        for language in LANGUAGES:
            url = f"{BASE}/herodata?language={language}&hero_id={hero_id}"
            payload = get(url)
            heroes = json.loads(payload)["result"]["data"]["heroes"]
            if len(heroes) != 1 or heroes[0]["id"] != hero_id:
                raise SystemExit(f"Unexpected response identity for hero {hero_id}")
            save(f"hero-{hero_id}-{language}.json", url, payload)
        print(f"hero {hero_id} saved", flush=True)
    manifest = {
        "schema": "hero-source-manifest/2",
        "purpose": "U36 version check against the 2026-10-09 snapshot; not for training",
        "source_patch": None,
        "patch_verified": False,
        "heroes": len(ids),
        "records": records,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
    return manifest


def load(directory, language):
    heroes = {}
    for path in sorted(Path(directory).glob(f"hero-*-{language}.json")):
        hero = json.loads(path.read_bytes())["result"]["data"]["heroes"][0]
        heroes[hero["id"]] = hero
    return heroes


def same(a, b):
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(
        b, sort_keys=True, ensure_ascii=False
    )


def diff(old_dir, new_dir):
    """Per hero and language: added/removed abilities and changed fields."""
    report = {"schema": "hero-datafeed-diff/1", "patch_verified": False, "languages": {}}
    for language in LANGUAGES:
        old, new = load(old_dir, language), load(new_dir, language)
        changes = []
        for hero_id in sorted(set(old) | set(new)):
            if hero_id not in new or hero_id not in old:
                changes.append(
                    {
                        "hero_id": hero_id,
                        "hero": (old.get(hero_id) or new[hero_id])["name"],
                        "change": "hero_removed" if hero_id not in new else "hero_added",
                    }
                )
                continue
            before, after = old[hero_id], new[hero_id]
            hero_fields = [f for f in HERO_FIELDS if not same(before.get(f), after.get(f))]
            if hero_fields:
                changes.append(
                    {
                        "hero_id": hero_id,
                        "hero": after["name"],
                        "change": "hero_fields",
                        "fields": hero_fields,
                    }
                )
            a_old = {a["name"]: a for a in before["abilities"]}
            a_new = {a["name"]: a for a in after["abilities"]}
            for name in sorted(set(a_old) | set(a_new)):
                row = {"hero_id": hero_id, "hero": after["name"], "ability": name}
                if name not in a_new:
                    changes.append({**row, "change": "ability_removed"})
                elif name not in a_old:
                    changes.append({**row, "change": "ability_added"})
                else:
                    a, b = a_old[name], a_new[name]
                    text = [f for f in ABILITY_TEXT if not same(a.get(f), b.get(f))]
                    fields = [f for f in ABILITY_FIELDS if not same(a.get(f), b.get(f))]
                    if text or fields:
                        changes.append(
                            {
                                **row,
                                "change": "ability_changed",
                                "text_fields": text,
                                "other_fields": fields,
                                "before": {f: a.get(f) for f in text},
                                "after": {f: b.get(f) for f in text},
                            }
                        )
        report["languages"][language] = {
            "old_heroes": len(old),
            "new_heroes": len(new),
            "changes": changes,
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--output", required=True, type=Path)
    d = sub.add_parser("diff")
    d.add_argument("--old", required=True, type=Path)
    d.add_argument("--new", required=True, type=Path)
    d.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "fetch":
        print(json.dumps({"heroes": fetch(args.output)["heroes"]}))
        return
    if args.output.exists():
        raise SystemExit("Output already exists; choose a new file")
    report = diff(args.old, args.new)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    summary = {}
    for language, part in report["languages"].items():
        counts = {}
        for change in part["changes"]:
            counts[change["change"]] = counts.get(change["change"], 0) + 1
        summary[language] = counts
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
