"""Explicit public-reader/1 migration, never a general ignore-hashes option.

Only registered pre-migration source hashes may transition to the actual current
files. Every non-provenance value is compared as canonical bytes (including
order and JSON types). Callers must opt in; strict verification stays default.
"""

import copy
from pathlib import Path

from dota_items.storage import file_hash, json_bytes

MIGRATION = "public-reader/1"
ROOT = Path(__file__).resolve().parents[1]
ADDED = {"data/source_io.py", "data/producer_migration.py"}
LEGACY_SHA256 = {
    "data/feasibility.py": "a0900bc3f20fd16fd83ed26218f4b9feb9ee7da7abf86f6614b9010aa9a716d2",
    "data/feasibility_sampling.py": (
        "37b31a07c318fe36a68adfa6ff3ff91db86e57098d35f358431cae02153b6f69"
    ),
    "data/player_overlap.py": "08ad62bbac5897298731c4b48d7eac679e991da4a4d3a1437bd9a4d4f3ab45b8",
    "data/lineup_preflight.py": "694984dcd615ac0edd164dc73a1e11c7ee53ae635a15d426934a7d6ab027ae7a",
    "data/purchase_snapshot.py": "028b38bb4b0fb4e326e3d716a6b939a26d9db7fdd9e57b5a0b125192aeadd56c",
}


def _relative(name):
    return (
        name
        if "/" in name or name in ("domain.py", "normalize.py", "storage.py")
        else "data/" + name
    )


def compare_replay(saved, rebuilt, *, metadata_paths=(("implementation_sha256",),)):
    """Return a receipt for allowed changes; reject every other difference.

    This proves equivalence to a reconstructed result, not source authenticity or
    research authorization. Never overwrite the saved object or its source file.
    """
    candidate = copy.deepcopy(saved)
    changes = []
    for path in metadata_paths:
        old_parent, new_parent = candidate, rebuilt
        for key in path[:-1]:
            old_parent, new_parent = old_parent[key], new_parent[key]
        old, new = old_parent[path[-1]], new_parent[path[-1]]
        if not isinstance(old, dict) or not isinstance(new, dict):
            raise ValueError("Invalid implementation manifest")
        if set(old) - set(new) or not set(new).difference(old) <= ADDED:
            raise ValueError("Unregistered implementation manifest change")
        for name in sorted(new):
            if name in old and old[name] == new[name]:
                continue
            relative = _relative(name)
            if name in old and (
                relative not in LEGACY_SHA256 or old[name] != LEGACY_SHA256[relative]
            ):
                raise ValueError("Unregistered historical producer hash")
            if relative not in LEGACY_SHA256 and relative not in ADDED:
                raise ValueError("Unregistered producer path")
            if new[name] != file_hash(ROOT / relative):
                raise ValueError("Rebuilt producer hash differs from current implementation")
            changes.append(
                {"path": list(path) + [name], "before": old.get(name), "after": new[name]}
            )
        old_parent[path[-1]] = copy.deepcopy(new)
    if json_bytes(candidate) != json_bytes(rebuilt):
        raise ValueError("Replay differs outside registered producer metadata")
    return {"migration": MIGRATION, "changes": changes, "training_allowed": False}
