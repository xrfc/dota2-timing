"""Bind candidate map and mechanics evidence without admitting a review or training run.

The binding is an explicit diagnostic input, not a compatibility approval. Consumers
must request a capability: this schema deliberately cannot grant action_review.
"""

import copy
import re
from pathlib import Path

from dota_items.data.map_snapshot import verify_map_snapshot
from dota_items.data.mechanics_candidate import verify_mechanics_candidate
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

SCHEMA = "patch-asset-binding/1"
PATCH = re.compile(r"[0-9]+\.[0-9]+[a-z]?")
SHA = re.compile(r"[0-9a-f]{64}")
MISSING_REVIEW_ASSETS = (
    "accepted_mechanics_and_derived_profiles",
    "patch_bound_save_means",
    "patch_bound_hero_mobility",
    "accepted_camp_types_and_regions",
    "patch_bound_map_background",
    "replay_build_geometry_and_gameplay_validation",
)


def _keys(value, keys, name):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"Invalid {name} fields")


def _sha(value):
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise ValueError("Expected lowercase SHA-256")
    return value


def _root(value):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError("Asset root must be an absolute path")
    return Path(value)


def validate_binding(spec):
    """Validate an immutable binding shape, without trusting any on-disk payload."""
    _keys(spec, ("schema", "exact_patch", "status", "map", "mechanics"), "binding")
    if spec["schema"] != SCHEMA or spec["status"] != "candidate":
        raise ValueError("Only candidate asset bindings are supported")
    patch = spec["exact_patch"]
    if not isinstance(patch, str) or PATCH.fullmatch(patch) is None:
        raise ValueError("Expected exact patch identity")
    _keys(spec["map"], ("root", "manifest_sha256", "patch_series", "client_version"), "map")
    _keys(spec["mechanics"], ("root", "manifest_sha256"), "mechanics")
    for ref in (spec["map"], spec["mechanics"]):
        _root(ref["root"])
        _sha(ref["manifest_sha256"])
    series = re.sub(r"[a-z]$", "", patch)
    if spec["map"]["patch_series"] != series:
        raise ValueError("Map series differs from requested patch")
    build = spec["map"]["client_version"]
    if type(build) is not int or build <= 0:
        raise ValueError("Map client version must be a positive integer")
    return copy.deepcopy(spec)


def read_binding(path):
    """Read via the shared bounded source interface; this is not asset verification."""
    return validate_binding(parse_source_json(read_source_bytes(Path(path))))


def make_binding(map_root, mechanics_root, *, exact_patch, map_client_version):
    """Capture explicit identities; callers must verify before publishing the binding."""
    return validate_binding(
        {
            "schema": SCHEMA,
            "exact_patch": exact_patch,
            "status": "candidate",
            "map": {
                "root": str(Path(map_root).resolve()),
                "manifest_sha256": file_hash(Path(map_root) / "manifest.json"),
                "patch_series": re.sub(r"[a-z]$", "", exact_patch),
                "client_version": map_client_version,
            },
            "mechanics": {
                "root": str(Path(mechanics_root).resolve()),
                "manifest_sha256": file_hash(Path(mechanics_root) / "manifest.json"),
            },
        }
    )


def verify_patch_assets(spec, *, exact_patch, repository_root, purpose="diagnostic"):
    """Verify pinned sources for the exact caller patch; never promote candidates."""
    spec = validate_binding(spec)
    if exact_patch != spec["exact_patch"]:
        raise ValueError("Exact patch mismatch; letter patches do not inherit support")
    if purpose != "diagnostic":
        raise ValueError("Candidate assets cannot admit action_review or training")
    map_ref, mechanics_ref = spec["map"], spec["mechanics"]
    map_snapshot = verify_map_snapshot(
        _root(map_ref["root"]),
        expected_manifest_sha256=map_ref["manifest_sha256"],
        expected_patch_series=map_ref["patch_series"],
        expected_client_version=map_ref["client_version"],
    )
    mechanics = verify_mechanics_candidate(
        _root(mechanics_ref["root"]),
        expected_manifest_sha256=mechanics_ref["manifest_sha256"],
        expected_patch=exact_patch,
        repository_root=Path(repository_root),
    )
    return _VerifiedPatchAssets(spec, map_snapshot, mechanics)


class _VerifiedPatchAssets:
    def __init__(self, spec, map_snapshot, mechanics):
        self._spec = copy.deepcopy(spec)
        self.map = map_snapshot
        self._mechanics = mechanics

    @property
    def binding(self):
        return copy.deepcopy(self._spec)

    def summary(self):
        return {
            "schema": "patch-assets-verification/1",
            "exact_patch": self._spec["exact_patch"],
            "status": "candidate",
            "map": self.map.summary,
            "mechanics": self._mechanics.summary(),
            "capabilities": {
                "source_integrity_inspection": True,
                "geometry_diagnostic": True,
                "action_review": False,
                "training": False,
            },
            "unresolved_review_assets": list(MISSING_REVIEW_ASSETS),
            "limits": "Source identity and structure do not establish gameplay compatibility.",
        }

    def verify_again(self):
        self.map.verify_again()
        self._mechanics.verify_unchanged()
        return self.summary()
