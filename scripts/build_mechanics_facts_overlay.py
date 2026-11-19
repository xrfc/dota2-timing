"""Build a reviewed facts version from a build spec, with the shared overlay builder (U177).

From v27 on, every new facts version is built by this script instead of a copied
`build_mechanics_facts_vN.py`. The spec names every input, so a new patch only changes paths:

    {"schema": "mechanics-facts-build/1", "version": 27,
     "base": "knowledge/mechanics/extractions/v26/facts-v26.json",
     "inputs": "knowledge/mechanics/reviews/v27-inputs-001.json",
     "vocabulary": "...", "rules": "...", "enums": "...",
     "registry": "knowledge/hero-capabilities/hero-registry.json",
     "item_registry": "knowledge/items/item-registry.json",
     "extra_abilities": "knowledge/mechanics/extra-abilities-v1.json",
     "game_npc": "knowledge/game-files/snapshots/<date>/sources/scripts/npc",
     "items_txt": "knowledge/game-files/snapshots/<date>-items/sources/scripts/npc/items.txt"}

Writes to a new directory only; every file read is hashed before and after.

    PYTHONPATH=src python scripts/build_mechanics_facts_overlay.py \
        --spec knowledge/mechanics/reviews/v27-build.json \
        --output knowledge/mechanics/extractions/v27
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from dota_items.data.mechanics import load_enums, load_vocabulary
from dota_items.data.mechanics_conditions import add_conditions
from dota_items.data.mechanics_facts_overlay import build_reviewed
from dota_items.data.mechanics_facts_v19 import add_not_computed
from dota_items.data.mechanics_graph_v2 import annotate_evaluation
from dota_items.data.mechanics_interactions import evaluate_rule
from dota_items.data.mechanics_rules_v8 import expand_rules
from dota_items.data.mechanics_rules_v11 import load_rules_v11

ROOT = Path(__file__).resolve().parents[1]
SPEC_SCHEMA = "mechanics-facts-build/1"
KEYVALUES = "scripts/check_break_against_game_files.py"
IMPLEMENTATION = (
    "src/dota_items/data/mechanics.py",
    "src/dota_items/data/mechanics_conditions.py",
    "src/dota_items/data/mechanics_facts_overlay.py",
    "src/dota_items/data/mechanics_facts_v19.py",
    "src/dota_items/data/mechanics_graph_v2.py",
    "src/dota_items/data/mechanics_interactions.py",
    "src/dota_items/data/mechanics_rules_v8.py",
    "src/dota_items/data/mechanics_rules_v11.py",
    KEYVALUES,
    "scripts/build_mechanics_facts_overlay.py",
)
OUTPUTS = ("rules-evaluation.json", "rules-expanded.json")


def _digest_all(repo, names):
    return {name: hashlib.sha256((repo / name).read_bytes()).hexdigest() for name in names}


def load_json(repo, name):
    return json.loads((repo / name).read_text(encoding="utf-8"))


def declared_inputs(repo, spec):
    npc = repo / spec["game_npc"]
    heroes = sorted(p.relative_to(repo).as_posix() for p in (npc / "heroes").glob("*.txt"))
    names = [spec[k] for k in ("base", "inputs", "vocabulary", "rules", "enums", "registry")]
    names += [spec[k] for k in ("item_registry", "extra_abilities") if spec.get(k)]
    names += [f"{spec['game_npc']}/npc_abilities.txt", spec["items_txt"], *heroes]
    return tuple(dict.fromkeys(names))


def _keyvalues(repo):
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_file_location("check_break", repo / KEYVALUES)
    )
    module.__spec__.loader.exec_module(module)
    return module


def root_disabled_subjects(repo, spec):
    """Abilities and items whose game script has ROOT_DISABLES, from the spec's snapshot."""
    kv = _keyvalues(repo)
    npc = repo / spec["game_npc"]
    bodies = {}
    for file in [npc / "npc_abilities.txt", *sorted((npc / "heroes").glob("*.txt"))]:
        tree = kv.parse_keyvalues(file.read_text(encoding="utf-8", errors="replace"))
        bodies.update(kv.iter_abilities(tree))
    subjects = {
        name
        for name, body in bodies.items()
        if "ROOT_DISABLES" in str(body.get("AbilityBehavior", ""))
    }
    items = kv.parse_keyvalues(
        (repo / spec["items_txt"]).read_text(encoding="utf-8", errors="replace")
    )
    for name, body in items.get("DOTAAbilities", items).items():
        if isinstance(body, dict) and "ROOT_DISABLES" in str(body.get("AbilityBehavior", "")):
            subjects.add(name.removeprefix("item_"))
    return subjects


def known_subjects(repo, spec, registry):
    known = {a["name"] for h in registry["heroes"] for a in h["abilities"]}
    if spec.get("item_registry"):
        known |= set(load_json(repo, spec["item_registry"])["items"])
    if spec.get("extra_abilities"):
        extra = load_json(repo, spec["extra_abilities"])
        known |= {a["name"] for h in extra["heroes"] for a in h["abilities"]}
    return known


def run(spec_path, output, repo=ROOT):
    repo, output = Path(repo), Path(output)
    spec = (
        load_json(repo, spec_path)
        if not Path(spec_path).is_absolute()
        else json.loads(Path(spec_path).read_text(encoding="utf-8"))
    )
    if spec.get("schema") != SPEC_SCHEMA:
        raise ValueError(f"Expected {SPEC_SCHEMA}")
    if output.exists():
        raise ValueError("Output already exists; choose a new directory")
    version = spec["version"]
    names = declared_inputs(repo, spec)
    implementation = _digest_all(repo, IMPLEMENTATION)
    before = _digest_all(repo, names)
    registry = load_json(repo, spec["registry"])
    enums = load_enums(load_json(repo, spec["enums"]), registry["heroes"])
    terms = load_vocabulary(load_json(repo, spec["vocabulary"]), enums)
    doc = build_reviewed(
        load_json(repo, spec["base"]),
        load_json(repo, spec["inputs"]),
        version=version,
        vocabulary=spec["vocabulary"],
        terms=terms,
        known_subjects=known_subjects(repo, spec, registry),
    )
    rules = expand_rules(
        load_rules_v11(load_json(repo, spec["rules"]), terms), registry["heroes"], doc
    )
    fields = {"ROOT_DISABLES": root_disabled_subjects(repo, spec)}
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
    evaluation = add_conditions(evaluation, rules, doc, registry["heroes"])
    evaluation = add_not_computed(evaluation, rules)
    changed = sorted(
        name
        for old, new in (
            (before, _digest_all(repo, names)),
            (implementation, _digest_all(repo, IMPLEMENTATION)),
        )
        for name in old.keys() | new.keys()
        if old.get(name) != new.get(name)
    )
    if changed:
        raise ValueError(f"Inputs changed during the build: {changed}")
    output.mkdir(parents=True)
    facts_name = f"facts-v{version}.json"
    expanded = {"schema": "mechanics-rules/1", "source": spec["rules"], "rules": rules}
    for name, value in ((facts_name, doc), (OUTPUTS[0], evaluation), (OUTPUTS[1], expanded)):
        (output / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    manifest = {
        "schema": "mechanics-extraction-receipt/1",
        "extractor_version": doc["extractor_version"],
        "patch_verified": False,
        "build_spec": spec,
        "input_sha256": before,
        "implementation_sha256": implementation,
        "output_sha256": _digest_all(output, (facts_name, *OUTPUTS)),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return doc, evaluation


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--spec", required=True, help="Build spec JSON (repo-relative)")
    parser.add_argument("--output", required=True, type=Path, help="New directory")
    args = parser.parse_args()
    print(json.dumps(run(args.spec, args.output)[0]["counts"], ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
