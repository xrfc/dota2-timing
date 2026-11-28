"""Verify an explicitly pinned mechanics candidate without promoting it to current.

The overlay builder's input/output and producer inventories are checked independently.
Hash validity proves the identity of a candidate, never acceptance of its semantics.
This reader neither imports the builder CLI nor selects the application's active patch.
"""

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from dota_items.data.source_io import read_source_bytes

PRODUCER_PATHS = (
    "src/dota_items/data/mechanics.py",
    "src/dota_items/data/mechanics_conditions.py",
    "src/dota_items/data/mechanics_facts_overlay.py",
    "src/dota_items/data/mechanics_facts_v12.py",
    "src/dota_items/data/mechanics_facts_v19.py",
    "src/dota_items/data/mechanics_graph_v2.py",
    "src/dota_items/data/mechanics_interactions.py",
    "src/dota_items/data/mechanics_rules_v8.py",
    "src/dota_items/data/mechanics_rules_v11.py",
    "scripts/check_break_against_game_files.py",
    "scripts/build_mechanics_facts_overlay.py",
)
_REQUIRED_SPEC = {
    "schema",
    "version",
    "base",
    "inputs",
    "vocabulary",
    "rules",
    "enums",
    "registry",
    "decision_reviews",
    "game_npc",
    "items_txt",
}
_OPTIONAL_SPEC = {"item_registry", "extra_abilities", "hero_field_corrections"}
_MANIFEST_KEYS = {
    "schema",
    "extractor_version",
    "patch_verified",
    "build_spec",
    "input_sha256",
    "implementation_sha256",
    "output_sha256",
}


def _sha(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected a lowercase SHA-256 digest")
    return value


def _path(root, name):
    if (
        not isinstance(name, str)
        or not name
        or "\\" in name
        or str(PurePosixPath(name)) != name
        or PurePosixPath(name).is_absolute()
        or any(part in (".", "..") for part in PurePosixPath(name).parts)
    ):
        raise ValueError("Expected a canonical relative file path")
    candidate = root
    for part in PurePosixPath(name).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError(f"Symlink is not permitted: {name}")
    return candidate


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_):
    raise ValueError("Non-finite JSON value")


def _json(contents):
    try:
        value = json.loads(contents, object_pairs_hook=_object, parse_constant=_nonfinite)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid candidate JSON") from error
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _read(path, digest, snapshots):
    _sha(digest)
    try:
        contents = read_source_bytes(path)
    except OSError as error:
        raise ValueError(f"Missing or unreadable candidate dependency: {path}") from error
    if hashlib.sha256(contents).hexdigest() != digest:
        raise ValueError(f"Candidate dependency hash mismatch: {path}")
    snapshots[path] = digest
    return contents


def _inventory(value, required, label):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError(f"Incomplete or unexpected {label} inventory")
    for digest in value.values():
        _sha(digest)


def _spec_inputs(spec, repository):
    if not isinstance(spec, dict) or not _REQUIRED_SPEC <= set(spec):
        raise ValueError("Incomplete candidate build_spec")
    if set(spec) - _REQUIRED_SPEC - _OPTIONAL_SPEC:
        raise ValueError("Unknown candidate build_spec fields")
    version = spec["version"]
    if spec["schema"] != "mechanics-facts-build/1" or type(version) is not int or version < 27:
        raise ValueError("Unsupported candidate build_spec")
    names = [spec[key] for key in set(spec) - {"schema", "version", "game_npc"}]
    for name in names:
        _path(repository, name)
    paths = set(names)
    npc = _path(repository, spec["game_npc"])
    heroes = _path(repository, f"{spec['game_npc']}/heroes")
    if not npc.is_dir() or not heroes.is_dir():
        raise ValueError("Candidate game-script source directory is missing")
    hero_files = sorted(heroes.glob("*.txt"))
    if not hero_files:
        raise ValueError("Candidate game-script hero inventory is empty")
    paths.add(f"{spec['game_npc']}/npc_abilities.txt")
    paths.update(path.relative_to(repository).as_posix() for path in hero_files)
    return paths


def _indexed(rows, label):
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"Invalid {label} rows")
    indexed = {}
    for row in rows:
        key = row.get("review_id")
        if not isinstance(key, str) or not key or key in indexed:
            raise ValueError(f"Missing or duplicate {label} review ID")
        indexed[key] = row
    return indexed


def _check_reviews(spec, inputs, facts):
    overlay = _json(inputs[spec["inputs"]])
    if overlay.get("schema") != "mechanics-overlay-inputs/1" or (
        type(overlay.get("version")) is not int or overlay["version"] != spec["version"]
    ):
        raise ValueError("Overlay identity differs from build_spec")
    note = overlay.get("note")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("Candidate must retain its pending-review note")
    operations = overlay.get("operations")
    if not isinstance(operations, list) or any(not isinstance(op, dict) for op in operations):
        raise ValueError("Invalid overlay operations")
    review_doc = _json(inputs[spec["decision_reviews"]])
    if review_doc.get("schema") != "mechanics-recheck-742/1":
        raise ValueError("Unsupported decision-review schema")
    reviews = _indexed(review_doc.get("rows"), "decision evidence")
    originals = _indexed(_json(inputs[spec["base"]]).get("rows"), "base facts")
    rows = _indexed(facts.get("rows"), "candidate facts")
    for op in operations:
        if op.get("op") != "decision_change":
            continue
        key = op.get("review_id")
        old, row, review = originals.get(key), rows.get(key), reviews.get(key)
        if old is None or row is None or review is None:
            raise ValueError("Decision change lacks original, output or review evidence")
        if any(
            review.get(field) != old.get(field) for field in ("subject", "mechanism", "decision")
        ):
            raise ValueError("Decision evidence differs from the original fact")
        if (
            old.get("decision") != op.get("from")
            or row.get("decision") != op.get("to")
            or op.get("from") == op.get("to")
            or review.get("codex") != "now_wrong"
            or row.get("basis") != op.get("basis")
        ):
            raise ValueError("Decision change is inconsistent with its evidence")
        if op.get("basis") == "two_ai" and (
            review.get("lane") != "change_two_ai" or review.get("claude") != "同意Codex"
        ):
            raise ValueError("Decision change lacks agreement from both reviewers")
        if row.get("decision_review") != {"source": spec["decision_reviews"], **review}:
            raise ValueError("Candidate decision_review is missing or differs from pinned evidence")
        if row.get("quotes") != [review.get("codex_quote")]:
            raise ValueError("Candidate changed quote differs from decision evidence")
        prior = row.get("prior_review")
        if not isinstance(prior, dict) or any(
            prior.get(field) != old.get(field)
            for field in ("decision", "basis", "claude", "codex", "quotes")
        ):
            raise ValueError("Candidate lost the original decision evidence")
    return note


@dataclass(frozen=True)
class VerifiedMechanicsCandidate:
    """A verified candidate reference; callers must reverify immediately before publication."""

    _root: Path
    _repository: Path
    _manifest_sha256: str
    _patch: str
    _summary: dict

    def summary(self):
        return deepcopy(self._summary)

    def verify_unchanged(self):
        current = verify_mechanics_candidate(
            self._root,
            expected_manifest_sha256=self._manifest_sha256,
            expected_patch=self._patch,
            repository_root=self._repository,
        ).summary()
        if current != self._summary:
            raise ValueError("Candidate changed after verification")
        return current


def verify_mechanics_candidate(root, *, expected_manifest_sha256, expected_patch, repository_root):
    """Check the pinned candidate and all current dependencies; never authorize formal use.

    ``expected_patch`` is an exact patch, checked against the versioned registry. A valid
    receipt may still contain unresolved rulings; ``patch_verified`` remains false.
    """
    if (
        not isinstance(expected_patch, str)
        or re.fullmatch(r"[0-9]+\.[0-9]+[a-z]?", expected_patch) is None
    ):
        raise ValueError("Expected an exact patch name")
    root, repository = Path(root).absolute(), Path(repository_root).absolute()
    if root.is_symlink() or repository.is_symlink():
        raise ValueError("Candidate/repository roots cannot be symlinks")
    root, repository = root.resolve(), repository.resolve()
    snapshots = {}
    manifest_path = _path(root, "manifest.json")
    manifest = _json(_read(manifest_path, expected_manifest_sha256, snapshots))
    if (
        set(manifest) != _MANIFEST_KEYS
        or manifest.get("schema") != "mechanics-extraction-receipt/1"
    ):
        raise ValueError("Unsupported candidate manifest")
    if manifest.get("patch_verified") is not False:
        raise ValueError("This reader only admits unverified candidates")
    spec = manifest["build_spec"]
    required_inputs = _spec_inputs(spec, repository)
    version = spec["version"]
    if manifest["extractor_version"] != f"mechanics-reviewed/{version}":
        raise ValueError("Candidate version differs from build_spec")
    outputs = {f"facts-v{version}.json", "rules-expanded.json", "rules-evaluation.json"}
    _inventory(manifest["input_sha256"], required_inputs, "input")
    _inventory(manifest["implementation_sha256"], PRODUCER_PATHS, "producer")
    _inventory(manifest["output_sha256"], outputs, "output")
    if {p.name for p in root.iterdir()} != outputs | {"manifest.json"}:
        raise ValueError("Unexpected files in candidate directory")
    inputs = {
        name: _read(_path(repository, name), digest, snapshots)
        for name, digest in manifest["input_sha256"].items()
    }
    for name, digest in manifest["implementation_sha256"].items():
        _read(_path(repository, name), digest, snapshots)
    products = {
        name: _json(_read(_path(root, name), digest, snapshots))
        for name, digest in manifest["output_sha256"].items()
    }
    registry = _json(inputs[spec["registry"]])
    if registry.get("target_patch") != expected_patch:
        raise ValueError("Candidate registry target patch differs from requested patch")
    facts = products[f"facts-v{version}.json"]
    if (
        facts.get("schema") != f"mechanics-facts/{version}"
        or facts.get("extractor_version") != manifest["extractor_version"]
        or facts.get("patch_verified") is not False
        or facts.get("vocabulary") != spec["vocabulary"]
    ):
        raise ValueError("Candidate facts identity differs from manifest")
    note = _check_reviews(spec, inputs, facts)
    counts = facts.get("counts", {})
    if (
        not isinstance(counts, dict)
        or type(counts.get("rows")) is not int
        or counts.get("rows") != len(facts["rows"])
        or any(row.get("decision") not in ("accept", "reject") for row in facts["rows"])
        or counts.get("decisions") != dict(Counter(row["decision"] for row in facts["rows"]))
        or not isinstance(facts.get("retired_rows"), list)
        or counts.get("retired_rows") != len(facts["retired_rows"])
    ):
        raise ValueError("Candidate counts do not match rows")
    if (
        products["rules-expanded.json"].get("source") != spec["rules"]
        or products["rules-expanded.json"].get("schema") != "mechanics-rules/1"
        or products["rules-evaluation.json"].get("schema") != "mechanics-rules-evaluation/3"
    ):
        raise ValueError("Expanded rules differ from build_spec")
    # Check for writes that occurred between the first input read and the last output read.
    for path, digest in tuple(snapshots.items()):
        _read(path, digest, snapshots)
    if _spec_inputs(spec, repository) != required_inputs:
        raise ValueError("Candidate source inventory changed during verification")
    summary = {
        "schema": "mechanics-candidate-verification/1",
        "patch": expected_patch,
        "status": "candidate",
        "patch_verified": False,
        "formal_use_allowed": False,
        "training_allowed": False,
        "manifest": {"path": str(manifest_path), "sha256": expected_manifest_sha256},
        "build": {
            "version": version,
            "registry": spec["registry"],
            "decision_reviews": spec["decision_reviews"],
        },
        "counts": counts,
        "inventory_counts": {
            "inputs": len(inputs),
            "producer": len(PRODUCER_PATHS),
            "outputs": len(outputs),
        },
        "pending": {"status": "unresolved", "note": note},
        "evidence": {
            "inputs": manifest["input_sha256"],
            "producer": manifest["implementation_sha256"],
            "outputs": manifest["output_sha256"],
        },
    }
    return VerifiedMechanicsCandidate(
        root, repository, expected_manifest_sha256, expected_patch, summary
    )
