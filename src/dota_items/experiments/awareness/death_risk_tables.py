"""Write-guard and reader of the death-risk table folders (track B, U160).

Added 2026-11-18 after a review found that the builder reused any existing `<match>.pkl`
whatever positions, parameters, sources or code produced it, and that the readers took
every file of a folder without checks.

Producer side (`prepare_folder`, `reusable`): a folder holds one `manifest.json` with
the generation conditions (positions, parameters, producer source hashes, knowledge file
hashes) and their digest. A folder built under other conditions is refused, so a change
needs a new folder; nothing is overwritten. A match file is reused only when it carries
the same digest and the same source-file key.

Consumer side (`load_tables`): every file must carry the folder's digest and schema, the
match in its name, rows of that match only, and no match of the track B holdout (U133),
checked again here rather than trusted to the producer.

Folders written before this guard (death-risk-v1 to v3, 2026-11-17) have no manifest.
They are read only with `allow_legacy=True`; the result is then marked unverified and
nothing is written back into them.
"""

import json
import pickle
from pathlib import Path

from dota_items.contracts.death_risk import (
    CONDITION_KEYS,
    LEGACY_SCHEMAS,
    MANIFEST,
    MANIFEST_SCHEMA,
    TABLE_SCHEMA,
    TableError,
    check_manifest,
    check_table,
)
from dota_items.data.awareness_split import is_holdout
from dota_items.storage import digest, file_hash


def describe_conditions(positions, params, win_step, producer_files, knowledge_files, base):
    """The generation conditions of a table folder; file paths are relative to `base`."""

    def hashed(paths):
        return {Path(p).resolve().relative_to(base).as_posix(): file_hash(Path(p)) for p in paths}

    conditions = {
        "positions": sorted(int(p) for p in positions),
        "params": {k: list(v) if isinstance(v, tuple) else v for k, v in params.items()},
        "win_step": win_step,
        "producer": hashed(producer_files),
        "knowledge": hashed(knowledge_files),
    }
    assert set(conditions) == set(CONDITION_KEYS)
    return conditions


def manifest_of(conditions):
    return {
        "schema": MANIFEST_SCHEMA,
        "table_schema": TABLE_SCHEMA,
        "conditions": conditions,
        "conditions_digest": digest(conditions),
    }


def prepare_folder(folder, conditions):
    """Create or accept `folder` for these conditions; return the conditions digest.

    Raises TableError when the folder was built under other conditions or holds files
    without a manifest (legacy or foreign): write to a new folder instead.
    """
    folder = Path(folder)
    wanted = manifest_of(conditions)
    path = folder / MANIFEST
    if path.exists():
        found = json.loads(path.read_text(encoding="utf-8"))
        check_manifest(found)
        if found["conditions_digest"] != wanted["conditions_digest"]:
            changed = sorted(
                key
                for key in CONDITION_KEYS
                if found["conditions"].get(key) != wanted["conditions"][key]
            )
            raise TableError(
                f"{folder} was built under other conditions ({changed}); use a new folder"
            )
        return found["conditions_digest"]
    if folder.exists() and any(folder.glob("*.pkl")):
        raise TableError(f"{folder} holds tables without a manifest; use a new folder")
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(wanted, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return wanted["conditions_digest"]


def reusable(path, conditions_digest, source_key):
    """True when an existing match file was built under these conditions from these sources.

    Raises TableError when it exists but differs: the folder is then inconsistent.
    """
    path = Path(path)
    if not path.exists():
        return False
    with path.open("rb") as stream:
        value = pickle.load(stream)  # written by build_death_risk_table.py, local only
    match_id = int(path.name.split(".")[0])
    check_table(value, match_id, conditions_digest)
    if value.get("source_key") != source_key:
        raise TableError(f"{path}: source files changed since it was built; use a new folder")
    return True


def _checked_files(folder, allow_legacy, holdout, info):
    """Yield each match file's contents after every check, one at a time (the tables are
    large); fill `info` with the folder description once all files passed."""
    folder = Path(folder)
    paths = sorted(folder.glob("*.pkl"))
    if not paths:
        raise TableError(f"{folder} holds no tables")
    manifest_path = folder / MANIFEST
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        check_manifest(manifest)
        expected, verified = manifest["conditions_digest"], True
        params = manifest["conditions"]["params"]
    elif allow_legacy:
        expected, verified, params = None, False, None
    else:
        raise TableError(f"{folder} has no {MANIFEST}; pass allow_legacy for an old folder")
    schemas = set()
    for path in paths:
        match_id = int(path.name.split(".")[0])
        if holdout(match_id):
            raise TableError(f"{path}: match {match_id} is in the track B holdout (U133)")
        with path.open("rb") as stream:
            value = pickle.load(stream)  # written by build_death_risk_table.py, local only
        if verified:
            check_table(value, match_id, expected)
        else:
            if value.get("schema") not in LEGACY_SCHEMAS:
                raise TableError(f"{path}: schema {value.get('schema')} in a legacy folder")
            for key in ("risk", "win", "deaths"):
                if any(row.get("match_id") != match_id for row in value.get(key, ())):
                    raise TableError(f"{path}: a {key} row belongs to another match")
        schemas.add(value["schema"])
        yield value
    if len(schemas) > 1:
        raise TableError(f"{folder} mixes schemas {sorted(schemas)}")
    info |= {
        "folder": str(folder),
        "schema": schemas.pop(),
        "conditions_digest": expected,
        "verified": verified,
        "params": params,
        "matches": len(paths),
        "note": None
        if verified
        else "legacy folder without generation conditions: contents not verified",
    }


def load_tables(folder, allow_legacy=False, holdout=is_holdout):
    """(risk rows, win rows, deaths, info) of a table folder, after every check.

    `info` records the folder, schema, digest, match count and whether it was verified.
    """
    info, risk, win, deaths = {}, [], [], []
    for value in _checked_files(folder, allow_legacy, holdout, info):
        risk += value["risk"]
        win += value["win"]
        deaths += value["deaths"]
    return risk, win, deaths, info


def load_parts(folder, parts=("hits", "contact"), holdout=is_holdout):
    """({part: rows}, info) for the evaluation-only parts of a table: `hits` (damage taken
    by second and source) and `contact` (per-second sight and distances).

    Only folders built with generation conditions carry them (from 2026-11-18 on); the
    legacy folders death-risk-v1 to v3 do not, so they are refused.
    """
    info, out = {}, {part: [] for part in parts}
    for value in _checked_files(folder, False, holdout, info):
        for part in parts:
            out[part] += value[part]
    return out, info
