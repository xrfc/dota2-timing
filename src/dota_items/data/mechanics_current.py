"""Single entry point for the current mechanics knowledge (MK-T6, U113).

``knowledge/mechanics/current.json`` names the version of each knowledge file that new code
should read, with its SHA-256. Versioned files are never overwritten, so a hash mismatch
means the pointer is stale or a file was edited in place; both raise. Files produced by a
build are also checked against that build's ``manifest.json``.
"""

import hashlib
import json
from pathlib import Path

CURRENT = "knowledge/mechanics/current.json"
SCHEMA = "mechanics-current/1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_current(root: Path = Path(".")) -> dict:
    """Validate current.json and return it; every entry gains an absolute ``file``."""
    doc = json.loads((root / CURRENT).read_text(encoding="utf-8"))
    if doc.get("schema") != SCHEMA:
        raise ValueError(f"current.json schema must be {SCHEMA}")
    entries = doc.get("entries")
    if not isinstance(entries, dict) or not entries:
        raise ValueError("current.json has no entries")
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
        entry["file"] = path.resolve()
    return doc


def read_current(name: str, root: Path = Path(".")):
    """Parse one validated current knowledge file by entry name."""
    entries = load_current(root)["entries"]
    if name not in entries:
        raise KeyError(f"No current mechanics entry named {name}")
    return json.loads(entries[name]["file"].read_text(encoding="utf-8"))
