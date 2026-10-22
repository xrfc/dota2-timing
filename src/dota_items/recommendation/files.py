"""Offline knowledge adapter: immutable bytes, JSON pointers and patch binding."""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from dota_items.recommendation.knowledge import Bundle, Knowledge, Policy
from dota_items.storage import inside


def pointer(document: object, path: str) -> object:
    if not path.startswith("/"):
        raise ValueError("source pointer must be an absolute JSON pointer")
    value = document
    try:
        for token in path[1:].split("/"):
            key = token.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
    except (KeyError, IndexError, ValueError, TypeError) as error:
        raise ValueError(f"source pointer does not resolve: {path}") from error
    return value


def load_bundle(root: Path) -> Bundle:
    """Verify all frozen sources before any rule may use them. Never downloads."""
    kb_bytes = inside(root, "knowledge.json").read_bytes()
    policy_bytes = inside(root, "policy.json").read_bytes()
    kb = Knowledge.model_validate_json(kb_bytes)
    policy = Policy.model_validate_json(policy_bytes)
    sources = {}
    for source in kb.sources:
        content = inside(root, source.file).read_bytes()
        if hashlib.sha256(content).hexdigest() != source.sha256:
            raise ValueError(f"source hash mismatch: {source.source_id}")
        sources[source.source_id] = json.loads(content)
    binding = kb.binding
    try:
        patches = sources[binding.patch_list_source]["patches"]
        latest = max(patches, key=lambda patch: patch["patch_timestamp"])
        notes = sources[binding.patch_notes_source]
        observed = datetime.fromisoformat(binding.observed_at_utc)
        if observed.tzinfo is None:
            raise ValueError("patch observation timestamp requires a timezone")
        if (
            latest["patch_number"] != kb.patch
            or notes["patch_number"] != kb.patch
            or latest["patch_timestamp"] != notes["patch_timestamp"]
            or observed.timestamp() < latest["patch_timestamp"]
        ):
            raise ValueError("official patch identity/timestamp mismatch")
        for anchor in binding.anchors:
            actual = pointer(sources[anchor.source_id], anchor.pointer)
            if type(actual) not in (int, float) or actual != anchor.expected:
                raise ValueError(f"patch anchor mismatch: {anchor.source_id}")
            if pointer(notes, anchor.patch_note_pointer) != anchor.patch_note_quote:
                raise ValueError("patch anchor note mismatch")
        catalog = sources[binding.catalog_source]
        expected = {row["id"]: row["attack_type"] for row in catalog.values()}
        if {hero.hero_id: hero.attack_type for hero in kb.heroes} != expected:
            raise ValueError("hero catalog identity mismatch")
        for fact in kb.facts:
            document = sources[fact.source_id]
            if pointer(document, fact.pointer) != fact.quote:
                raise ValueError(f"fact quote mismatch: {fact.fact_id}")
            if fact.hero_id is not None:
                owner = document["result"]["data"]["heroes"][0]
                if owner["id"] != fact.hero_id or not fact.pointer.startswith(
                    "/result/data/heroes/0/"
                ):
                    raise ValueError(f"hero source identity mismatch: {fact.fact_id}")
            else:
                owner = document["result"]["data"]["items"][0]
                if owner["name"] != f"item_{fact.item_key}" or not fact.pointer.startswith(
                    "/result/data/items/0/"
                ):
                    raise ValueError(f"item source identity mismatch: {fact.fact_id}")
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError("incomplete source or patch binding") from error
    return Bundle(
        knowledge=kb,
        policy=policy,
        knowledge_sha256=hashlib.sha256(kb_bytes).hexdigest(),
        rules_sha256=hashlib.sha256(policy_bytes).hexdigest(),
    )
