"""Which knowledge files are superseded (MK-T6f, U113).

`knowledge/superseded.json` lists single superseded files or directories, and versioned
families where every version older than the one in `knowledge/mechanics/current.json` is
superseded. Frozen files are never edited to say so; this registry is the one place to ask.
"""

import json
import re
from pathlib import Path

REGISTRY = "knowledge/superseded.json"
SCHEMA = "knowledge-superseded/1"


def load_superseded(root: Path = Path(".")) -> dict:
    doc = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    if doc.get("schema") != SCHEMA:
        raise ValueError(f"{REGISTRY} schema must be {SCHEMA}")
    current = json.loads((root / "knowledge/mechanics/current.json").read_text(encoding="utf-8"))
    for family in doc["families"]:
        entry = current["entries"].get(family["current"])
        if entry is None:
            raise ValueError(f"No current entry {family['current']} for {family['pattern']}")
        match = re.fullmatch(family["pattern"], entry["path"])
        if not match:
            raise ValueError(f"Current {family['current']} does not match {family['pattern']}")
        family["current_version"] = int(match.group(1))
    for item in doc["items"]:
        if not (root / item["path"]).exists():
            raise ValueError(f"Superseded path does not exist: {item['path']}")
    return doc


def superseded_status(path: str, doc: dict):
    """The registry entry that makes `path` superseded, or None when it is current."""
    path = Path(path).as_posix()
    for item in doc["items"]:
        target = item["path"]
        if path == target.rstrip("/") or (target.endswith("/") and path.startswith(target)):
            return item
    for family in doc["families"]:
        match = re.fullmatch(family["pattern"], path)
        if match and int(match.group(1)) < family["current_version"]:
            newest = f"v{family['current_version']}"
            return {
                "path": path,
                "zh": f"{family['zh']}旧版本v{match.group(1)}",
                "superseded_by": f"current.json的{family['current']}（{newest}）",
            }
    return None
