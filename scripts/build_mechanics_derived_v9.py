"""Build the derived layer from facts v19 and rules v11 with declared not-computed fields (U113).

Writes a new directory; earlier derived layers stay reproducible. Profiles call rule matches
"candidate relations" and keep each one's rule, relation, status and pending reason as fields,
so programs never read status from a Chinese title. Heroes include extra abilities (U90).

    PYTHONPATH=src python scripts/build_mechanics_derived_v9.py \\
        --output knowledge/mechanics/profiles/derived-v9
"""

import argparse
import hashlib
import json
from pathlib import Path

from dota_items.data.mechanics_conditions import annotate_graph_conditions
from dota_items.data.mechanics_graph import (
    build_graph,
    build_item_profile,
    node_index,
    render_item_markdown,
)
from dota_items.data.mechanics_graph_v2 import annotate_graph, display_doc
from dota_items.data.mechanics_profiles import build_hero_profile, render_markdown
from dota_items.data.mechanics_profiles_v3 import (
    DRAFT,
    hero_relations,
    item_relations,
    render_hero_relations,
    render_item_relations,
)
from dota_items.data.mechanics_rules_v8 import mark_conditional_edges
from dota_items.data.mechanics_traits_v3 import build_traits_v3

ROOT = Path(__file__).resolve().parents[1]
FACTS = "knowledge/mechanics/extractions/v19/facts-v19.json"
EVALUATION = "knowledge/mechanics/extractions/v19/rules-evaluation.json"
RULES = "knowledge/mechanics/extractions/v19/rules-expanded.json"
VOCABULARY = "knowledge/mechanics/vocabulary-v13.json"
REGISTRY = "knowledge/hero-capabilities/hero-registry.json"
EXTRA_ABILITIES = "knowledge/mechanics/extra-abilities-v1.json"
STATUS = "knowledge/mechanics/retired-items-v2.json"
ITEM_NAMES = "knowledge/items/sources/itemlist-schinese.json"
TRAITS_V1 = "knowledge/hero-traits/hero-traits-v1.json"
MAPPING = "knowledge/hero-traits/trait-mapping-v4.json"
INPUTS = (
    FACTS,
    EVALUATION,
    RULES,
    VOCABULARY,
    REGISTRY,
    EXTRA_ABILITIES,
    STATUS,
    ITEM_NAMES,
    TRAITS_V1,
    MAPPING,
)
IMPLEMENTATION = (
    "src/dota_items/data/mechanics_graph.py",
    "src/dota_items/data/mechanics_graph_v2.py",
    "src/dota_items/data/mechanics_profiles.py",
    "src/dota_items/data/mechanics_profiles_v2.py",
    "src/dota_items/data/mechanics_profiles_v3.py",
    "src/dota_items/data/mechanics_conditions.py",
    "src/dota_items/data/mechanics_rules_v8.py",
    "src/dota_items/data/mechanics_traits_v3.py",
    "scripts/build_mechanics_derived_v9.py",
)


def _digest_all(repo, names):
    return {name: hashlib.sha256((repo / name).read_bytes()).hexdigest() for name in names}


IMPLEMENTATION_AT_IMPORT = _digest_all(ROOT, IMPLEMENTATION)


def _dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def with_extra_abilities(heroes, extra):
    """Registry heroes plus abilities listed under them, without changing the registry."""
    added = {entry["hero_id"]: entry["abilities"] for entry in extra["heroes"]}
    return [
        {**hero, "abilities": [*hero["abilities"], *added.get(hero["hero_id"], [])]}
        for hero in heroes
    ]


def run(output, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    before = {name: _digest(repo / name) for name in INPUTS}
    load = lambda name: json.loads((repo / name).read_text(encoding="utf-8"))  # noqa: E731
    doc, evaluation = load(FACTS), load(EVALUATION)
    rules = load(RULES)["rules"]
    terms = {term["id"]: term for term in load(VOCABULARY)["mechanisms"]}
    heroes = with_extra_abilities(load(REGISTRY)["heroes"], load(EXTRA_ABILITIES))
    status = load(STATUS)["status"]
    names = {
        row["name"].removeprefix("item_"): row["name_loc"]
        for row in load(ITEM_NAMES)["result"]["data"]["itemabilities"]
        if row["name_loc"]
    }
    active_names = {
        subject: name
        for subject, name in names.items()
        if status.get(subject) in ("purchasable", "other_source")
    }
    graph = annotate_graph_conditions(
        mark_conditional_edges(
            annotate_graph(
                build_graph(rules, evaluation, doc, node_index(heroes, names, status)), rules, doc
            ),
            rules,
        ),
        evaluation,
    )
    shown_doc = display_doc(doc)

    hero_dir, item_dir = output / "heroes", output / "items"
    hero_dir.mkdir(parents=True)
    item_dir.mkdir()
    hero_profiles = []
    for hero in sorted(heroes, key=lambda h: h["hero_id"]):
        profile = build_hero_profile(hero, shown_doc, evaluation, terms, active_names)
        page = render_markdown(profile).splitlines()
        relations = hero_relations(hero, graph, active_names)
        profile = {
            **{k: v for k, v in profile.items() if k not in ("countered_by", "can_counter")},
            "candidate_relations": relations,
        }
        hero_profiles.append(profile)
        (hero_dir / f"hero-{hero['hero_id']}.md").write_text(
            render_hero_relations(page, relations), encoding="utf-8"
        )
    item_subjects = sorted(
        {row["subject"] for row in doc["rows"] if row["decision"] == "accept"} & set(active_names)
    )
    item_profiles = []
    for subject in item_subjects:
        profile = build_item_profile(
            subject, active_names[subject], status[subject], shown_doc, graph, terms
        )
        page = render_item_markdown(profile).splitlines()
        relations = item_relations(subject, graph)
        profile = {
            **{k: v for k, v in profile.items() if k not in ("countered_by", "can_counter")},
            "candidate_relations": relations,
        }
        item_profiles.append(profile)
        (item_dir / f"{subject}.md").write_text(
            render_item_relations(page, relations), encoding="utf-8"
        )
    mapping = load(MAPPING)
    traits = build_traits_v3(mapping, doc, heroes, rules)

    _dump(
        output / "hero-profiles.json",
        {
            "schema": "mechanics-hero-profiles/3",
            **DRAFT,
            "sources": {"facts": FACTS, "evaluation": EVALUATION, "rules": RULES},
            "profiles": hero_profiles,
        },
    )
    _dump(
        output / "item-profiles.json",
        {
            "schema": "mechanics-item-profiles/3",
            **DRAFT,
            "sources": {"facts": FACTS, "evaluation": EVALUATION, "rules": RULES},
            "profiles": item_profiles,
        },
    )
    _dump(output / "counter-graph.json", graph)
    _dump(output / "hero-traits-v3.json", traits)
    changed = sorted(name for name in INPUTS if _digest(repo / name) != before[name])
    current = _digest_all(repo, IMPLEMENTATION)
    changed += sorted(
        name for name in IMPLEMENTATION if current[name] != IMPLEMENTATION_AT_IMPORT[name]
    )
    if changed:
        raise ValueError(f"Inputs changed during the build: {changed}")
    files = sorted(path for path in output.rglob("*") if path.is_file())
    _dump(
        output / "manifest.json",
        {
            "schema": "mechanics-derived-receipt/2",
            **DRAFT,
            "patch_verified": False,
            "semantics": graph["semantics"],
            "input_sha256": before,
            "implementation_sha256": {name: _digest(repo / name) for name in IMPLEMENTATION},
            "output_sha256": {str(p.relative_to(output)): _digest(p) for p in files},
        },
    )
    return {"heroes": hero_profiles, "items": item_profiles, "graph": graph, "traits": traits}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory")
    args = parser.parse_args()
    result = run(args.output)
    print(len(result["heroes"]), "heroes", len(result["items"]), "items")


if __name__ == "__main__":
    main()
