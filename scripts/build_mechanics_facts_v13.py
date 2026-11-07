"""Build reviewed facts v13 and evaluate rules v5 on them (U90, U92).

Writes to a new directory only. Every file the build reads is declared and hashed before and
after the build, so an input that changes mid-build stops it.

    PYTHONPATH=src python scripts/build_mechanics_facts_v13.py \
        --output knowledge/mechanics/extractions/v13
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_mechanics_facts_v4 as v4script  # noqa: E402
import build_mechanics_facts_v6 as v6script  # noqa: E402
import build_mechanics_facts_v7 as v7script  # noqa: E402
import build_mechanics_facts_v8 as v8script  # noqa: E402
import build_mechanics_facts_v12 as v12script  # noqa: E402

from dota_items.data.mechanics import load_enums, load_vocabulary  # noqa: E402
from dota_items.data.mechanics_facts_v13 import build_reviewed  # noqa: E402
from dota_items.data.mechanics_graph_v2 import annotate_evaluation  # noqa: E402
from dota_items.data.mechanics_interactions import evaluate_rule, load_rules  # noqa: E402

ROOT = v4script.ROOT
VOCABULARY = f"{v4script.MECH}/vocabulary-v13.json"
RULES = f"{v4script.MECH}/rules-v7.json"
CORRECTIONS = v12script.CORRECTIONS
CORRECTIONS_2 = v12script.CORRECTIONS_2
ADOPTIONS = v12script.ADOPTIONS
RULINGS = v12script.RULINGS
ITEM_NAMES = v12script.ITEM_NAMES
REGISTRY = "knowledge/hero-capabilities/hero-registry.json"
ENUMS = f"{v4script.MECH}/enums-v1.json"
V13_INPUTS = f"{v4script.REVIEWS}/v13-inputs-001.json"
SLOW_RULINGS = f"{v4script.REVIEWS}/slow-rulings-001.jsonl"
TERRAIN_RULINGS = f"{v4script.REVIEWS}/terrain-rulings-001.jsonl"
FEEDBACK = (
    f"{v4script.REVIEWS}/u5-verdicts-2026-11-03.jsonl",
    f"{v4script.REVIEWS}/u5-spot-check-002/verdicts-2026-11-05.jsonl",
)
CONDITION_ROUNDS = tuple(
    (number, f"{v4script.REVIEWS}/codex-round-00{number}/codex-review.jsonl")
    for number in range(2, 9)
)
GAME_FILES = (
    "knowledge/game-files/snapshots/2026-11-02/sources/scripts/npc/npc_abilities.txt",
    "knowledge/game-files/snapshots/2026-11-03-items/sources/scripts/npc/items.txt",
)
HERO_SCRIPTS = "knowledge/game-files/snapshots/2026-11-02/sources/scripts/npc/heroes"
IMPLEMENTATION = (
    *v12script.IMPLEMENTATION,
    "src/dota_items/data/mechanics_facts_v13.py",
    "src/dota_items/data/mechanics_graph_v2.py",
    "src/dota_items/data/mechanics.py",
    "src/dota_items/data/mechanics_interactions.py",
    "scripts/build_mechanics_facts_v13.py",
)


def digest_implementation(repo=ROOT):
    return {name: hashlib.sha256((repo / name).read_bytes()).hexdigest() for name in IMPLEMENTATION}


IMPLEMENTATION_AT_IMPORT = digest_implementation()


def declared_inputs(repo=ROOT):
    """Every file a build reads, including the per-hero scripts a helper walks."""
    heroes = sorted(
        path.relative_to(repo).as_posix() for path in (repo / HERO_SCRIPTS).glob("*.txt")
    )
    return tuple(
        dict.fromkeys(
            (
                *(n for n in v12script.INPUTS if n not in (v12script.VOCABULARY, v12script.RULES)),
                VOCABULARY,
                RULES,
                SLOW_RULINGS,
                TERRAIN_RULINGS,
                REGISTRY,
                ENUMS,
                V13_INPUTS,
                *FEEDBACK,
                *(path for _, path in CONDITION_ROUNDS),
                *GAME_FILES,
                *heroes,
            )
        )
    )


def digest_inputs(repo=ROOT):
    return {
        name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
        for name in declared_inputs(repo)
    }


def _changed(before, after):
    """Names that differ, including files that appeared or were deleted."""
    return sorted(
        name for name in before.keys() | after.keys() if before.get(name) != after.get(name)
    )


def load_json(repo, name):
    return json.loads((repo / name).read_text(encoding="utf-8"))


def run(output, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    before = digest_inputs(repo)
    sources = v6script.load_sources(repo)
    sources["skill_notes"] = load_json(repo, v7script.NOTES)["notes"]
    sources["audit"].extend(v4script.read_jsonl(repo, v8script.ROUND8))
    sources["t5_corrections"] = v4script.read_jsonl(repo, CORRECTIONS)
    sources["t5_corrections_2"] = v4script.read_jsonl(repo, CORRECTIONS_2)
    sources["audit_adoptions"] = v4script.read_jsonl(repo, ADOPTIONS)
    sources["recheck_rulings"] = v4script.read_jsonl(repo, RULINGS)
    extra = load_json(repo, V13_INPUTS)
    sources["v13_rulings"] = [
        *extra["rulings"],
        *v4script.read_jsonl(repo, SLOW_RULINGS),
        *v4script.read_jsonl(repo, TERRAIN_RULINGS),
    ]
    sources["v13_notes"] = extra["notes"]
    sources["feedback_corrections"] = extra["corrections"]
    sources["user_feedback"] = [
        {**row, "file": name} for name in FEEDBACK for row in v4script.read_jsonl(repo, name)
    ]
    sources["condition_reviews"] = [
        {**row, "round": number, "reviewer": "codex"}
        for number, name in CONDITION_ROUNDS
        for row in v4script.read_jsonl(repo, name)
    ]
    registry = load_json(repo, "knowledge/hero-capabilities/hero-registry.json")
    sources["zh_names"] = {
        ability["name"]: f"{hero['name_zh']}·{ability['name_zh']}"
        for hero in registry["heroes"]
        for ability in hero["abilities"]
    }
    for row in load_json(repo, ITEM_NAMES)["result"]["data"]["itemabilities"]:
        if row["name_loc"]:
            sources["zh_names"][row["name"].removeprefix("item_")] = row["name_loc"]
    doc = build_reviewed(sources)
    enums = load_enums(load_json(repo, f"{v4script.MECH}/enums-v1.json"), registry["heroes"])
    terms = load_vocabulary(load_json(repo, VOCABULARY), enums)
    rules = load_rules(load_json(repo, RULES), terms)
    fields = {"ROOT_DISABLES": v7script.root_disabled_subjects(repo)}
    evaluation = annotate_evaluation(
        {
            "schema": "mechanics-rules-evaluation/1",
            "rules": [
                {"id": rule["id"], "zh": rule["zh"], **evaluate_rule(rule, doc, fields)}
                for rule in rules
            ],
        },
        rules,
    )
    changed = _changed(before, digest_inputs(repo))
    changed += _changed(IMPLEMENTATION_AT_IMPORT, digest_implementation(repo))
    if changed:
        raise ValueError(f"Inputs changed during the build: {changed}")
    output.mkdir(parents=True)
    for name, value in (
        ("facts-v13.json", doc),
        ("delta-vs-v3.json", v4script.delta_of(doc)),
        ("rules-evaluation.json", evaluation),
    ):
        (output / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {
        "schema": "mechanics-extraction-receipt/1",
        "extractor_version": doc["extractor_version"],
        "patch_verified": False,
        "input_sha256": before,
        "implementation_sha256": {name: digest(repo / name) for name in IMPLEMENTATION},
        "output_sha256": {path.name: digest(path) for path in sorted(output.iterdir())},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return doc, evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory")
    args = parser.parse_args()
    print(json.dumps(run(args.output)[0]["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
