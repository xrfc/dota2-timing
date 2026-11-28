"""Build an explicit candidate bundle for map diagnostics and conditional action assets."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from dota_items.data.atomic_directory import publish_directory
from dota_items.data.awareness_split import is_holdout
from dota_items.data.map_replay_geometry import audit_replay_geometry
from dota_items.data.map_replay_source import open_geometry_source
from dota_items.data.map_snapshot import FILES
from dota_items.data.patch_asset_evidence import (
    EvidencePins,
    read_fresh_capture,
    read_runtime_capture,
)
from dota_items.data.patch_assets import verify_patch_assets
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
PRODUCER_FILES = (
    "src/dota_items/__init__.py",
    "src/dota_items/data/__init__.py",
    "scripts/build_patch_review_assets.py",
    "src/dota_items/data/patch_asset_evidence.py",
    "src/dota_items/data/patch_objectives.py",
    "src/dota_items/data/patch_terrain.py",
    "src/dota_items/data/mechanics_action_assets.py",
    "src/dota_items/data/mechanics_source_equivalence.py",
    "src/dota_items/data/mechanics_graph.py",
    "src/dota_items/data/mechanics_profiles.py",
    "src/dota_items/data/mechanics_traits_v4.py",
    "src/dota_items/data/mechanics_traits_v3.py",
    "src/dota_items/data/mechanics_conditions.py",
    "src/dota_items/data/mechanics_graph_v2.py",
    "src/dota_items/data/mechanics_rules_v8.py",
    *(f"src/dota_items/data/mechanics_facts_v{number}.py" for number in range(4, 13)),
    "src/dota_items/data/patch_assets.py",
    "src/dota_items/data/map_snapshot.py",
    "src/dota_items/data/mechanics_candidate.py",
    "src/dota_items/data/map_replay_source.py",
    "src/dota_items/data/map_replay_geometry.py",
    "src/dota_items/data/source_io.py",
    "src/dota_items/data/awareness_split.py",
    "src/dota_items/data/atomic_directory.py",
    "src/dota_items/storage.py",
)


def _mechanics_sources(binding, pins, repository_root):
    root = Path(binding["mechanics"]["root"])
    manifest = pins.read(
        {
            "path": str(root / "manifest.json"),
            "sha256": binding["mechanics"]["manifest_sha256"],
        }
    )
    for field, base in (
        ("input_sha256", repository_root),
        ("implementation_sha256", repository_root),
        ("output_sha256", root),
    ):
        for name, digest in manifest[field].items():
            pins.add({"path": str(base / name), "sha256": digest})
    spec = manifest["build_spec"]
    paths = {
        "facts": root / f"facts-v{spec['version']}.json",
        "rules": root / "rules-expanded.json",
        "vocabulary": repository_root / spec["vocabulary"],
        "reviews": repository_root / spec["decision_reviews"],
        "registry": repository_root / spec["registry"],
        "overlay": repository_root / spec["inputs"],
        "patch_decisions": repository_root / "docs/decisions/2026-11-19-patch-7.42.md",
        "patch_impact": repository_root / "docs/patch-7.42-impact.md",
        "save_decisions": repository_root / "docs/decisions/2026-11-09-b0-gank-rules.md",
        "haste_policy": repository_root / "knowledge/hero-traits/trait-mapping-v6.json",
        "evaluation": root / "rules-evaluation.json",
        "item_names": repository_root / "knowledge/items/sources/itemlist-schinese.json",
        "retired_items": repository_root / "knowledge/mechanics/retired-items-v2.json",
        "extra_abilities": repository_root / "knowledge/mechanics/extra-abilities-v1.json",
    }
    refs = {key: pins.track(path) for key, path in paths.items()}
    documents = {
        key: pins.read(ref)
        for key, ref in refs.items()
        if key not in {"patch_decisions", "patch_impact", "save_decisions"}
    }
    documents["base_facts"] = pins.read(pins.track(repository_root / spec["base"]))
    return refs, documents


def _json_bytes(payload):
    return (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def _write(path, payload):
    path.write_bytes(_json_bytes(payload))


def run(spec_path, output, *, repository_root=ROOT):
    from dota_items.data.mechanics_action_assets import (
        build_action_assets,
        required_pending_review_ids,
    )
    from dota_items.data.mechanics_source_equivalence import verify_source_equivalence
    from dota_items.data.patch_objectives import (
        build_camp_assets,
        build_objective_observations,
        build_objective_rules,
    )
    from dota_items.data.patch_terrain import (
        StaticTerrain,
        run_diagnostics,
        visibility_observations,
    )

    repository_root, output = Path(repository_root).resolve(), Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists")
    pins = EvidencePins()
    for name in PRODUCER_FILES:
        pins.track(repository_root / name)
    spec_ref = pins.track(Path(spec_path).absolute())
    spec = pins.read(spec_ref)
    if (
        not isinstance(spec, dict)
        or set(spec) != {"schema", "exact_patch", "binding", "replays"}
        or spec["schema"] != "patch-review-assets-spec/1"
    ):
        raise ValueError("Invalid patch review asset specification")
    patch = spec["exact_patch"]
    binding_doc = pins.read(spec["binding"])
    binding = verify_patch_assets(binding_doc, exact_patch=patch, repository_root=repository_root)
    # The review/admission policy below references the explicit 7.42 review, never a letter patch.
    if patch != "7.42":
        raise ValueError("No registered action-asset review policy for this exact patch")
    map_root = Path(binding_doc["map"]["root"])
    map_ref = {
        "path": str(map_root / "manifest.json"),
        "sha256": binding_doc["map"]["manifest_sha256"],
    }
    map_manifest = pins.read(map_ref)
    for name, digest in map_manifest["output_sha256"].items():
        pins.add({"path": str(map_root / name), "sha256": digest})
    documents = {name: binding.map.read(name) for name in FILES}
    references, mechanics = _mechanics_sources(binding_doc, pins, repository_root)
    if not isinstance(spec["replays"], list) or not spec["replays"]:
        raise ValueError("At least one pinned non-holdout replay is required")
    sources = []
    for item in spec["replays"]:
        if not isinstance(item, dict) or set(item) != {
            "manifest",
            "capture",
            "receipt",
            "visibility",
        }:
            raise ValueError("Replay requires manifest and runtime capture/receipt references")
        ref = item["manifest"]
        sources.append(
            open_geometry_source(
                ref["path"],
                expected_sha256=ref["sha256"],
                exact_patch=patch,
                match_allowed=lambda mid: not is_holdout(mid),
            )
        )
    if len({source.match_id for source in sources}) != len(sources):
        raise ValueError("Duplicate replay match")
    captures, diagnostics, geometry = [], [], []
    terrain = StaticTerrain(documents, exact_patch=patch, map_manifest_sha256=map_ref["sha256"])
    for item, source in zip(spec["replays"], sources, strict=True):
        captures.append(
            read_runtime_capture(
                item["capture"],
                item["receipt"],
                source=source,
                pins=pins,
                repository_root=repository_root,
            )
        )
        ref = item["visibility"]
        if not isinstance(ref, dict) or set(ref) != {"capture", "receipt"}:
            raise ValueError("Visibility requires its capture and receipt")
        visibility = read_fresh_capture(
            ref["capture"],
            ref["receipt"],
            source=source,
            pins=pins,
            kind="visibility",
            repository_root=repository_root,
        )
        observed = visibility_observations(visibility)
        states, extras = list(source.rows("state")), list(source.rows("extras"))
        geometry.append(
            audit_replay_geometry(
                documents,
                iter(states),
                match_id=source.match_id,
                patch=patch,
                replay_build=source.build,
                duration=source.duration,
                extras_rows=iter(extras),
            )
        )
        diagnostics.append(
            {
                "match_id": source.match_id,
                "replay_build": source.build,
                "diagnostics": run_diagnostics(
                    terrain,
                    iter(states),
                    duration=source.duration,
                    tree_policy="block_initial_tree_cells",
                    visibility_observations=observed["observations"] or None,
                ),
                "visibility_evidence": {k: v for k, v in observed.items() if k != "observations"},
            }
        )
        for name, digest in source.verify_again()["used_files"].items():
            pins.add({"path": name, "sha256": digest})
    source_refs = {"binding": spec["binding"], "map_manifest": map_ref, "replays": spec["replays"]}
    notes_ref = pins.track(
        repository_root
        / ("knowledge/mechanics/reviews/patch-update-2026-11-19/notes/datafeed-7.42-english.json")
    )
    notes = pins.read(notes_ref)
    source_refs["official_notes"] = notes_ref
    camps = build_camp_assets(
        documents, captures, exact_patch=patch, source_refs=source_refs, official_notes=notes
    )
    objectives = build_objective_observations(captures, exact_patch=patch, source_refs=source_refs)
    objective_rules = build_objective_rules(notes, exact_patch=patch, source_refs=source_refs)
    route_probes = []
    entities = documents["mapdata.json"]["data"]
    forts = entities["npc_dota_fort"]
    for camp in entities["npc_dota_neutral_spawner"]:
        # A deterministic geometry exercise, not a safe-retreat recommendation.
        target = min(
            forts, key=lambda fort: (fort["x"] - camp["x"]) ** 2 + (fort["y"] - camp["y"]) ** 2
        )
        start, goal = (camp["x"], camp["y"]), (target["x"], target["y"])
        route_probes.append(
            {
                "start": start,
                "goal": goal,
                "selection": "nearest_fort_by_straight_distance_diagnostic_only",
                "policies": {
                    policy: terrain.route(start, goal, tree_policy=policy)
                    for policy in ("ignore_initial_trees", "block_initial_tree_cells")
                },
            }
        )
    equivalence = verify_source_equivalence(
        mechanics["facts"],
        mechanics["base_facts"],
        repository_root=repository_root,
        exact_patch=patch,
    )
    for name, digest in equivalence["used_files"].items():
        pins.add({"path": name, "sha256": digest})
    references["equivalence"] = {
        "path": str(output / "mechanics-source-equivalence.json"),
        "sha256": hashlib.sha256(_json_bytes(equivalence)).hexdigest(),
    }
    action = build_action_assets(
        mechanics["facts"],
        mechanics["rules"],
        mechanics["vocabulary"],
        mechanics["reviews"],
        mechanics["registry"],
        exact_patch=patch,
        source_refs=references,
        pending_review_ids=required_pending_review_ids(mechanics["facts"], mechanics["reviews"]),
        overlay_doc=mechanics["overlay"],
        evaluation_doc=mechanics["evaluation"],
        trait_mapping_doc=mechanics["haste_policy"],
        item_names_doc=mechanics["item_names"],
        retired_items_doc=mechanics["retired_items"],
        extra_abilities_doc=mechanics["extra_abilities"],
        source_equivalence_doc=equivalence,
    )
    payloads = {
        "camps.json": camps,
        "mechanics-source-equivalence.json": equivalence,
        "objectives.json": objectives,
        "objective-rules.json": objective_rules,
        "route-probes.json": {
            "schema": "patch-route-probes/1",
            "exact_patch": patch,
            "source_refs": source_refs,
            "pairs": route_probes,
            "action_review_allowed": False,
            "training_allowed": False,
        },
        "terrain-diagnostics.json": {
            "schema": "patch-terrain-diagnostics/1",
            "exact_patch": patch,
            "sources": source_refs,
            "matches": diagnostics,
            "geometry": geometry,
            "training_allowed": False,
            "action_review_allowed": False,
        },
        **{f"mechanics-{key}.json": value for key, value in action.items()},
        "readiness.json": {
            "schema": "patch-review-assets-readiness/1",
            "exact_patch": patch,
            "status": "candidate",
            "generated": [
                "camp_spatial_identity",
                "runtime_objective_observations",
                "static_terrain",
                "map_background",
                "conditional_profiles",
                "save_means",
                "mobility",
                "counter_graph",
                "hero_traits",
                "source_equivalence",
            ],
            "requires_review": [
                "camp_type_and_region_semantics",
                "dynamic_spawn_rule_validation",
                "path_and_visibility_gameplay_validation",
                "pending_mechanics_and_rules",
            ],
            "source_integrity_checked": True,
            "compatibility_approved": False,
            "action_review_allowed": False,
            "training_allowed": False,
            "limits": "Candidate generation does not approve semantic definitions or model use.",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".patch-review-assets-", dir=output.parent) as temp:
        staging = Path(temp) / "result"
        staging.mkdir()
        for name, payload in payloads.items():
            _write(staging / name, payload)
        (staging / "map-background.svg").write_text(terrain.render_svg())
        binding.verify_again()
        for source in sources:
            source.verify_again()
        pins.verify()
        receipt = {
            "schema": "patch-review-assets-receipt/1",
            "spec": spec_ref,
            "exact_patch": patch,
            "binding": binding_doc,
            "used_files": pins.inventory,
            "output_sha256": {path.name: file_hash(path) for path in sorted(staging.iterdir())},
            "action_review_allowed": False,
            "training_allowed": False,
        }
        _write(staging / "receipt.json", receipt)
        publish_directory(staging, output)
    return payloads["readiness.json"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.spec, args.output)))


if __name__ == "__main__":
    main()
