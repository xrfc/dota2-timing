"""Exact fixed-source continuity evidence; never a new mechanics interpretation.

Only the registered 7.41f baseline and 7.42 snapshots are eligible. Equality of
complete ability/item records and script blocks preserves existing evidence, not
global rules or gameplay certification. The caller must pin and recheck used_files
before publishing any derived artifact; this module has no workflow dependency.
"""

import hashlib
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path, PurePosixPath

BASE_FACTS = (
    "knowledge/mechanics/extractions/v26/facts-v26.json",
    "391aa4268b6be3714984b48d401c3c966728a750aba0172ab209ca761ce18f95",
)
# Registration is explicit; dates or manifest source_patch:null are not identities.
SNAPSHOTS = (
    (
        "old_heroes",
        "7.41f",
        "heroes",
        "knowledge/hero-capabilities/snapshots/2026-11-06",
        "da8bc4220a5886ea4ef6d169fc8450dd8a449ec91a52c801fb28a4eb88e1aea4",
    ),
    (
        "new_heroes",
        "7.42",
        "heroes",
        "knowledge/hero-capabilities/snapshots/2026-11-19",
        "3a41e553664ba5a1e23164954b5b3692efc33dd1faaf1b1dd33d91859e340dea",
    ),
    (
        "old_items",
        "7.41f",
        "items",
        "knowledge/items/sources/itemdata-english-2026-11-06",
        "fb667c88b37aa7a4862fb66cc2df4ac71992cef53adbb26bc23d06373e9fd96e",
    ),
    (
        "new_items",
        "7.42",
        "items",
        "knowledge/items/sources/itemdata-english-2026-11-19",
        "a34c2a6da78123b701d007a63e3db94161c8d034f163a3375d56a8a50a7a5741",
    ),
    (
        "old_scripts",
        "7.41f",
        "scripts",
        "knowledge/game-files/snapshots/2026-11-02",
        "d6437452619a56bf9d806d31a6730ec4af5f71d4a7cb3bd5d501a819022a3f83",
    ),
    (
        "old_item_scripts",
        "7.41f",
        "scripts",
        "knowledge/game-files/snapshots/2026-11-03-items",
        "61511794a71ba17414f7644d8f946dd6bc2b951a681224b56090c84e0c0d262c",
    ),
    (
        "new_scripts",
        "7.42",
        "scripts",
        "knowledge/game-files/snapshots/2026-11-19",
        "b1a2da35af150e250ed9bed1282d8fac4629da73644d60c8a163d98d1ae4fc20",
    ),
    (
        "new_item_scripts",
        "7.42",
        "scripts",
        "knowledge/game-files/snapshots/2026-11-19-items",
        "dc29cba5da3f18e7c48ee9a5c5c29b86e60ca7e9bb1c3c37d977a911e80d7d5e",
    ),
)
KEY_FIELDS = ("review_id", "subject", "mechanism", "decision", "condition", "basis", "quotes")


def canonical_sha256(value):
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate source JSON key")
        result[key] = value
    return result


def _json(raw):
    value = json.loads(raw, object_pairs_hook=_pairs)
    canonical_sha256(value)  # Also rejects non-finite nested numbers.
    return value


class _Reader:
    def __init__(self, root):
        self.root, self.used = Path(root).resolve(), {}

    def read(self, relative, digest):
        from dota_items.data.source_io import read_source_bytes

        relative = PurePosixPath(relative)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Source path escapes registered repository")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("Source SHA-256 required")
        path = self.root / relative
        if path.is_symlink() or path.resolve() != path or not path.is_file():
            raise ValueError("Source must be a canonical regular file")
        raw = read_source_bytes(path)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Registered source digest mismatch")
        if str(path) in self.used and self.used[str(path)] != digest:
            raise ValueError("Conflicting source digests")
        self.used[str(path)] = digest
        return raw, {"path": str(path), "sha256": digest}


def _tokens(text):
    """Retain duplicate keys, token order, escapes and literal values; discard comments."""
    result, index = [], 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
        elif text.startswith("//", index):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
        elif char in "{}":
            result.append(char)
            index += 1
        elif char == '"':
            end = index + 1
            while end < len(text) and text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            if end >= len(text):
                raise ValueError("Unterminated script string")
            result.append(text[index : end + 1])
            index = end + 1
        else:
            end = index + 1
            while end < len(text) and not text[end].isspace() and text[end] not in '{}"':
                end += 1
            result.append(text[index:end])
            index = end
    return result


def _ends(tokens):
    opened, result = [], {}
    for index, token in enumerate(tokens):
        if token == "{":
            opened.append(index)
        elif token == "}":
            if not opened:
                raise ValueError("Unbalanced script braces")
            result[opened.pop()] = index
    if opened:
        raise ValueError("Unbalanced script braces")
    return result


def _definition_blocks(tokens):
    """Locate definitions by structure, not similarly named facets or numeric values."""
    ends, parents = _ends(tokens), []
    for index, token in enumerate(tokens):
        if token == "}":
            parents.pop()
        elif token == "{":
            if index == 0 or tokens[index - 1] in "{}":
                raise ValueError("Script object without a name")
            name = tokens[index - 1].strip('"')
            parents.append(name)
            if (
                len(parents) == 2
                and parents[0] == "DOTAAbilities"
                or len(parents) == 4
                and parents[0] == "DOTAHeroes"
                and parents[1].startswith("npc_dota_hero_")
                and parents[2] == "AbilityDefinitions"
            ):
                yield name, tokens[index + 1 : ends[index]]


def _field_evidence(blocks):
    """Only one explicit top-level IsBreakable occurrence in one block is unambiguous."""
    values, refs, valid = [], [], len(blocks) == 1
    for block in blocks:
        refs.append(block["ref"])
        tokens, index = block["tokens"], 0
        ends = _ends(tokens)
        while index < len(tokens):
            if index + 1 >= len(tokens) or tokens[index] in "{}":
                valid = False
                break
            name, value = tokens[index].strip('"'), tokens[index + 1]
            if value == "{":
                if name == "IsBreakable":
                    valid = False
                index = ends[index + 1] + 1
                continue
            if value == "}":
                valid = False
                break
            if name == "IsBreakable":
                values.append(value.strip('"'))
            index += 2
    unambiguous = valid and len(values) == 1
    return {
        "IsBreakable": {
            "value": values[0] if unambiguous else None,
            "unambiguous": unambiguous,
            "occurrences": len(values),
            "source_refs": refs,
        }
    }


def _index_facts(document, schema):
    if not isinstance(document, dict) or document.get("schema") != schema:
        raise ValueError("Unexpected mechanics facts schema")
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Facts rows required")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or any(key not in row for key in KEY_FIELDS):
            raise ValueError("Fact identity, condition and original evidence fields required")
        rid = row["review_id"]
        if not isinstance(rid, str) or not rid or rid in result:
            raise ValueError("Missing or duplicate fact review_id")
        if not isinstance(row["subject"], str) or not row["subject"]:
            raise ValueError("Fact subject required")
        result[rid] = row
    return result


def _load_sources(reader, subjects):
    heroes, items, scripts, refs = defaultdict(list), defaultdict(list), defaultdict(list), {}
    for name, patch, kind, root, digest in SNAPSHOTS:
        raw, manifest_ref = reader.read(f"{root}/manifest.json", digest)
        manifest = _json(raw)
        refs[name] = {**manifest_ref, "patch": patch, "kind": kind}
        expected_schema = {
            "heroes": "hero-source-manifest/2",
            "items": "item-sources/1",
            "scripts": "game-files-manifest/1",
        }[kind]
        if manifest.get("schema") != expected_schema:
            raise ValueError("Registered snapshot schema mismatch")
        if kind == "items":
            raw, ref = reader.read(f"{root}/items.json", manifest["sha256"])
            for subject, record in _json(raw).items():
                if subject in subjects:
                    items[(patch, subject)].append(
                        {
                            "record": record,
                            "ref": {
                                **ref,
                                "patch": patch,
                                "language": "english",
                                "subject_sha256": canonical_sha256(record),
                            },
                        }
                    )
            continue
        seen = set()
        for entry in manifest["records"]:
            relative = entry["file"]
            if relative in seen:
                raise ValueError("Duplicate manifest source path")
            seen.add(relative)
            match = re.fullmatch(r"sources/hero-(\d+)-(english|schinese)\.json", relative)
            if kind == "heroes" and match is not None:
                raw, ref = reader.read(f"{root}/{relative}", entry["sha256"])
                payload = _json(raw)["result"]["data"]["heroes"]
                if len(payload) != 1 or payload[0]["id"] != int(match[1]):
                    raise ValueError("Hero source identity differs from registered filename")
                for record in payload[0]["abilities"]:
                    subject = record["name"]
                    if subject in subjects:
                        heroes[(patch, match[2], subject)].append(
                            {
                                "record": record,
                                "ref": {
                                    **ref,
                                    "patch": patch,
                                    "language": match[2],
                                    "subject_sha256": canonical_sha256(record),
                                },
                            }
                        )
            elif kind == "scripts" and relative.startswith("sources/scripts/npc/"):
                if not relative.endswith(".txt"):
                    continue
                raw, ref = reader.read(f"{root}/{relative}", entry["sha256"])
                tokens = _tokens(raw.decode("utf-8"))
                for name, body in _definition_blocks(tokens):
                    subject = name.removeprefix("item_")
                    namespace = "item" if name.startswith("item_") else "hero"
                    if subject in subjects:
                        scripts[(patch, namespace, subject)].append(
                            {
                                "relative": relative,
                                "tokens": body,
                                "ref": {
                                    **ref,
                                    "patch": patch,
                                    "block_sha256": canonical_sha256(body),
                                },
                            }
                        )
    return heroes, items, scripts, refs


def _subject_evidence(subject, heroes, items, scripts):
    reasons, raw_refs, script_refs = [], [], []
    hero_present = any(
        heroes[(patch, lang, subject)]
        for patch in ("7.41f", "7.42")
        for lang in ("english", "schinese")
    )
    item_present = any(items[(patch, subject)] for patch in ("7.41f", "7.42"))
    kind = "hero" if hero_present or not item_present else "item"
    pairs = (
        [
            (heroes[("7.41f", lang, subject)], heroes[("7.42", lang, subject)])
            for lang in ("english", "schinese")
        ]
        if hero_present
        else [(items[("7.41f", subject)], items[("7.42", subject)])]
    )
    for old, new in pairs:
        raw_refs.extend(entry["ref"] for entry in old + new)
        if len(old) != 1 or len(new) != 1:
            reasons.append("raw_record_missing_or_ambiguous")
        elif canonical_sha256(old[0]["record"]) != canonical_sha256(new[0]["record"]):
            reasons.append("raw_record_changed")
    old, new = scripts[("7.41f", kind, subject)], scripts[("7.42", kind, subject)]
    script_refs.extend(block["ref"] for block in old + new)
    if len(old) != 1 or len(new) != 1:
        reasons.append("script_block_missing_or_ambiguous")
    elif (old[0]["relative"], old[0]["tokens"]) != (new[0]["relative"], new[0]["tokens"]):
        reasons.append("script_block_changed")
    return {
        "kind": kind,
        "reasons": sorted(set(reasons)),
        "raw_source_refs": raw_refs,
        "script_source_refs": script_refs,
        "current_script_fields": _field_evidence(new),
    }


def verify_source_equivalence(facts_doc, base_facts_doc, *, repository_root, exact_patch):
    """Return source equality proofs plus all immutable inputs for caller revalidation."""
    if exact_patch != "7.42":
        raise ValueError("No registered source equivalence policy for this exact patch")
    candidate = _index_facts(facts_doc, "mechanics-facts/27")
    baseline = _index_facts(base_facts_doc, "mechanics-facts/26")
    reader = _Reader(repository_root)
    base_raw, base_ref = reader.read(*BASE_FACTS)
    if canonical_sha256(_json(base_raw)) != canonical_sha256(base_facts_doc):
        raise ValueError("Baseline facts differ from registered 7.41f source")
    subjects = {row["subject"] for row in candidate.values()}
    heroes, items, scripts, source_refs = _load_sources(reader, subjects)
    evidence = {subject: _subject_evidence(subject, heroes, items, scripts) for subject in subjects}
    rows, counts, reasons_count = [], Counter(), Counter()
    for rid, fact in candidate.items():
        previous, proof = baseline.get(rid), evidence[fact["subject"]]
        reasons = list(proof["reasons"])
        if previous is None:
            reasons.append("no_baseline_fact")
        elif canonical_sha256(previous) != canonical_sha256(fact):
            reasons.append("baseline_fact_fields_changed")
        equivalent = not reasons
        row = {
            **{key: deepcopy(fact[key]) for key in KEY_FIELDS if key != "quotes"},
            "fact_sha256": canonical_sha256(fact),
            "base_fact_sha256": canonical_sha256(previous) if previous is not None else None,
            **deepcopy(proof),
            "reasons": reasons,
            "source_equivalent": equivalent,
            "status": "source_identical" if equivalent else "unknown",
        }
        rows.append(row)
        counts[row["status"]] += 1
        counts[f"{proof['kind']}_{row['status']}"] += 1
        reasons_count.update(reasons)
    return {
        "schema": "mechanics-source-equivalence/1",
        "patch": exact_patch,
        "baseline_patch": "7.41f",
        "base": {
            **base_ref,
            "schema": base_facts_doc["schema"],
            "document_sha256": canonical_sha256(base_facts_doc),
        },
        "candidate": {
            "schema": facts_doc["schema"],
            "document_sha256": canonical_sha256(facts_doc),
        },
        "source_refs": source_refs,
        "used_files": dict(sorted(reader.used.items())),
        "rows": rows,
        "summary": {
            "rows": len(rows),
            "counts": dict(counts),
            "unknown_reasons": dict(reasons_count),
            "verified_files": len(reader.used),
        },
        "identity_basis": "registered fixed manifest SHA-256 pairs, not a latest-version lookup",
        "comparison": {
            "facts": "complete original fact row; no fields ignored",
            "hero_raw": "complete English and Chinese ability objects",
            "item_raw": "complete English item object",
            "scripts": "one complete token block per version; duplicates/order/values retained",
            "whitespace_and_comments": "ignored only in script token comparison",
        },
        "patch_verified": False,
        "formal_use_allowed": False,
        "training_allowed": False,
        "limits": [
            "Identical source evidence does not certify unchanged global mechanics or behavior.",
            "Existing fact decisions and conditions are preserved without reinterpretation.",
            "Pending rulings, global rules and source conflicts need independent admission gates.",
            "Caller must add every used_file to publication pins and recheck before publication.",
        ],
    }
