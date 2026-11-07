"""Single entry point for the current mechanics knowledge (MK-T6, U113).

``knowledge/mechanics/current.json`` names the version of each knowledge file that new code
should read, with its SHA-256. Versioned files are never overwritten, so a hash mismatch
means the pointer is stale or a file was edited in place; both raise. Files produced by a
build are also checked against that build's ``manifest.json``.
"""

import hashlib
import json
import re
from pathlib import Path

CURRENT = "knowledge/mechanics/current.json"
SCHEMA = "mechanics-current/1"
FAMILIES = "knowledge/superseded.json"  # versioned families: pattern + current entry name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_inputs(name, entry, receipt, entries, families):
    """A build's inputs must be the current version of every family it read (PR #17 review).

    Families of the entries this manifest produced are skipped: a facts build reads the
    previous facts on purpose. An input that is itself a current entry must match its hash.
    """
    produced = {n for n, e in entries.items() if e.get("manifest") == entry["manifest"]}
    by_path = {e["path"]: (n, e) for n, e in entries.items()}
    for path, digest in receipt.get("input_sha256", {}).items():
        if path in by_path and by_path[path][0] not in produced:
            other, other_entry = by_path[path]
            if digest != other_entry["sha256"]:
                raise ValueError(f"{name}: built from a different {other} than current.json")
        for family in families:
            if family["current"] in produced or not re.fullmatch(family["pattern"], path):
                continue
            current_path = entries[family["current"]]["path"]
            if path != current_path:
                raise ValueError(f"{name}: built from {path}, but current.json uses {current_path}")


def load_current(root: Path = Path(".")) -> dict:
    """Validate current.json and return it; every entry gains an absolute ``file``."""
    doc = json.loads((root / CURRENT).read_text(encoding="utf-8"))
    if doc.get("schema") != SCHEMA:
        raise ValueError(f"current.json schema must be {SCHEMA}")
    entries = doc.get("entries")
    if not isinstance(entries, dict) or not entries:
        raise ValueError("current.json has no entries")
    families = json.loads((root / FAMILIES).read_text(encoding="utf-8"))["families"]
    for name, entry in entries.items():
        path = root / entry["path"]
        if not path.is_file():
            raise ValueError(f"{name}: {entry['path']} does not exist")
        if _sha256(path) != entry["sha256"]:
            raise ValueError(f"{name}: {entry['path']} hash differs from current.json")
        manifest = entry.get("manifest")
        if manifest:
            receipt = json.loads((root / manifest).read_text(encoding="utf-8"))
            relative = path.relative_to((root / manifest).parent).as_posix()
            if receipt["output_sha256"].get(relative) != entry["sha256"]:
                raise ValueError(f"{name}: {entry['path']} differs from its build manifest")
            _check_inputs(name, entry, receipt, entries, families)
        entry["file"] = path.resolve()
    return doc


def read_current(name: str, root: Path = Path(".")):
    """Parse one validated current knowledge file by entry name."""
    entries = load_current(root)["entries"]
    if name not in entries:
        raise KeyError(f"No current mechanics entry named {name}")
    return json.loads(entries[name]["file"].read_text(encoding="utf-8"))
