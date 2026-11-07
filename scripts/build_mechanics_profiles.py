"""Build MK-T5 hero mechanism profiles from facts v9 and rules v3.

    PYTHONPATH=src python scripts/build_mechanics_profiles.py --all \
        --output knowledge/mechanics/profiles/heroes-v1
"""

import argparse
import json
from pathlib import Path

from dota_items.data.mechanics_profiles import build_hero_profile, render_markdown

ROOT = Path(__file__).resolve().parents[1]
MECH = ROOT / "knowledge/mechanics"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(hero_ids, output, repo_root=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    package = repo_root / "knowledge/mechanics/extractions/v9"
    doc = load_json(package / "facts-v9.json")
    evaluation = load_json(package / "rules-evaluation.json")
    vocabulary = load_json(repo_root / "knowledge/mechanics/vocabulary-v9.json")
    terms = {term["id"]: term for term in vocabulary["mechanisms"]}
    registry = load_json(repo_root / "knowledge/hero-capabilities/hero-registry.json")
    status = load_json(repo_root / "knowledge/mechanics/retired-items-v1.json")["status"]
    item_list = load_json(repo_root / "knowledge/items/sources/itemlist-schinese.json")
    item_names = {
        row["name"].removeprefix("item_"): row["name_loc"]
        for row in item_list["result"]["data"]["itemabilities"]
        if status.get(row["name"].removeprefix("item_")) in ("purchasable", "other_source")
        and row["name_loc"]
    }
    heroes = {hero["hero_id"]: hero for hero in registry["heroes"]}
    hero_ids = list(hero_ids) if hero_ids else sorted(heroes)
    output.mkdir(parents=True)
    profiles = []
    for hero_id in hero_ids:
        profile = build_hero_profile(heroes[hero_id], doc, evaluation, terms, item_names)
        profiles.append(profile)
        (output / f"hero-{hero_id}.md").write_text(render_markdown(profile), encoding="utf-8")
    (output / "profiles.json").write_text(
        json.dumps(
            {
                "schema": "mechanics-hero-profiles/1",
                "facts": "extractions/v9",
                "profiles": profiles,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    return profiles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heroes", nargs="+", type=int)
    parser.add_argument("--all", action="store_true", help="Build every registry hero")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if bool(args.heroes) == args.all:
        parser.error("Pass exactly one of --heroes or --all")
    print(len(run(args.heroes, args.output)), "profiles")


if __name__ == "__main__":
    main()
