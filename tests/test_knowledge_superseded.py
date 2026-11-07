"""MK-T6f: superseded knowledge is registered and never current."""

import re
from pathlib import Path

from dota_items.data.knowledge_superseded import load_superseded, superseded_status
from dota_items.data.mechanics_current import load_current

ROOT = Path(__file__).resolve().parents[1]


def test_current_entries_are_never_superseded():
    doc = load_superseded(ROOT)
    for name, entry in load_current(ROOT)["entries"].items():
        assert superseded_status(entry["path"], doc) is None, name


def test_every_older_version_of_a_family_is_superseded():
    doc = load_superseded(ROOT)
    files = [p.relative_to(ROOT).as_posix() for p in (ROOT / "knowledge").rglob("*.json")]
    for family in doc["families"]:
        members = [f for f in files if re.fullmatch(family["pattern"], f)]
        older = [
            f
            for f in members
            if int(re.fullmatch(family["pattern"], f).group(1)) < family["current_version"]
        ]
        assert older, family["pattern"]
        assert all(superseded_status(f, doc) for f in older)


def test_named_items_cover_old_traits_and_recommendation_package():
    doc = load_superseded(ROOT)
    assert superseded_status("knowledge/hero-traits/hero-traits-v1.json", doc)
    assert superseded_status("knowledge/recommendation/7.41f-v1/knowledge.json", doc)
    assert superseded_status("knowledge/mechanics/profiles/heroes-v1/hero-1.md", doc)
    assert superseded_status("knowledge/mechanics/enums-v1.json", doc) is None
