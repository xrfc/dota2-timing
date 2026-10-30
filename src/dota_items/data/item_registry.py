"""Local item registry (U14): official names joined with cost/components.

Valve's datafeed is the authority for ids and Chinese/English names; OpenDota
dotaconstants supplies cost, components and the ``created`` (assembled) flag.
"""

from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes

SCHEMA = "item-registry/1"


def _key(name):
    return name[5:] if name.startswith("item_") else name


def build_registry(valve_doc, odota_doc):
    """Join both sources by item key; ids must agree where both know the item."""
    valve = {_key(i["name"]): i for i in valve_doc["result"]["data"]["itemabilities"]}
    items, id_conflicts = {}, []
    for key in sorted(set(valve) | set(odota_doc)):
        v, o = valve.get(key), odota_doc.get(key)
        if v and o and o.get("id") is not None and o["id"] != v["id"]:
            id_conflicts.append(key)
        components = (o or {}).get("components")
        items[key] = {
            "id": v["id"] if v else (o or {}).get("id"),
            "name_zh": v["name_loc"] if v else None,
            "name_en": v["name_english_loc"] if v else (o or {}).get("dname"),
            "cost": (o or {}).get("cost"),
            "components": list(components) if components else [],
            "completed": bool((o or {}).get("created")),
            "recipe": key.startswith("recipe_"),
            "neutral": bool(v and v.get("neutral_item_tier", -1) >= 0),
            "sources": [s for s, present in (("valve", v), ("dotaconstants", o)) if present],
        }
    if id_conflicts:
        raise ValueError(f"Item id conflicts between sources: {id_conflicts[:5]}")
    return {"schema": SCHEMA, "items": items}


def load_registry(path):
    registry = parse_source_json(read_source_bytes(Path(path)))
    if registry.get("schema") != SCHEMA:
        raise ValueError("Unexpected item registry schema")
    return registry["items"]


def display_name(items, key):
    """Official Chinese name, else English, else the raw key (never a guessed translation)."""
    entry = items.get(key) or {}
    return entry.get("name_zh") or entry.get("name_en") or key
