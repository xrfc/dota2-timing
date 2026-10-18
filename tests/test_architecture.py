"""Executable boundaries for the two development tracks (no real-data reads)."""

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src/dota_items"


def imports(source, package):
    """Include nested imports and resolve relative imports, without executing code."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = importlib.util.resolve_name("." * node.level + base, package)
            yield base
            yield from (f"{base}.{alias.name}" for alias in node.names)


def module_imports(path):
    parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
    return set(imports(path.read_text(encoding="utf-8"), ".".join(parts[:-1])))


@pytest.mark.parametrize(
    "area", ["data", "sources", "recommendation", "modeling", "contracts", "handoff"]
)
def test_track_boundaries(area):
    forbidden = {
        "data": ("modeling", "workflow", "recommendation"),
        "sources": ("modeling", "data", "workflow", "recommendation"),
        "recommendation": ("modeling", "data", "workflow", "sources"),
        "modeling": ("data", "sources", "workflow", "recommendation"),
        "contracts": ("data", "sources", "workflow", "recommendation", "modeling", "handoff"),
        "handoff": ("data", "sources", "workflow", "recommendation", "modeling"),
    }[area]
    violations = []
    for path in (PACKAGE / area).rglob("*.py"):
        for name in module_imports(path):
            if any(
                name == f"dota_items.{x}" or name.startswith(f"dota_items.{x}.") for x in forbidden
            ):
                violations.append(f"{path.relative_to(ROOT)} -> {name}")
            if area in ("contracts", "handoff") and name.split(".")[0] not in (
                sys.stdlib_module_names | {"dota_items"}
            ):
                violations.append(f"Contract has non-stdlib dependency: {name}")
    assert not violations, "\n".join(violations)


def test_import_scanner_covers_relative_and_nested_imports():
    source = "from .. import data\ndef f():\n    from ..data import pipeline\nimport httpx"
    names = set(imports(source, "dota_items.modeling"))
    assert {"dota_items.data", "dota_items.data.pipeline", "httpx"} <= names


def test_model_import_does_not_load_data_pipeline():
    # A fresh process prevents pytest's earlier data imports hiding a regression.
    code = """
import sys
from dota_items.modeling import foundation, synthetic_foundation
for prefix in ('dota_items.data', 'dota_items.sources', 'dota_items.workflow',
               'dota_items.recommendation'):
    assert not any(n == prefix or n.startswith(prefix + '.') for n in sys.modules), prefix
"""
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


@pytest.mark.parametrize("vocabulary", [[], [1], [1, 2, 8], list(range(1, 127))])
def test_encoding_matches_frozen_producer(vocabulary):
    from dota_items.contracts.lineup import columns, encode_lineup, fit_vocabulary
    from dota_items.data import lineup_preflight as legacy
    from dota_items.modeling.foundation import columns as compatible_columns

    rows = [
        {"ally_hero_ids": [8, 1, 2, 3, 4], "enemy_hero_ids": [5, 6, 7, 9, 10]},
        {"ally_hero_ids": [1, 1, 200], "enemy_hero_ids": [300]},
        {"ally_hero_ids": [], "enemy_hero_ids": []},
    ]
    assert fit_vocabulary(rows) == legacy.fit_vocabulary(rows)
    assert fit_vocabulary([]) == legacy.fit_vocabulary([]) == []
    for row in rows:
        assert encode_lineup(row, vocabulary) == legacy.encode_lineup(row, vocabulary)
        assert len(encode_lineup(row, vocabulary)) == len(columns(vocabulary))
    assert compatible_columns is columns
    assert columns([8, 1]) == [
        "ally_hero_8",
        "ally_hero_1",
        "ally_unknown_count",
        "enemy_hero_8",
        "enemy_hero_1",
        "enemy_unknown_count",
    ]


@pytest.mark.parametrize("module", ["artifacts", "inference", "batch", "specs"])
def test_model_leaf_modules_do_not_depend_on_training_or_historical_runner(module):
    names = module_imports(PACKAGE / "modeling" / f"{module}.py")
    prefixes = (
        "sklearn",
        "dota_items.modeling.training",
        "dota_items.modeling.estimators",
        "dota_items.modeling.foundation",
        "dota_items.modeling.purchase_baseline",
    )
    assert not any(
        name == prefix or name.startswith(prefix + ".") for name in names for prefix in prefixes
    )


def test_no_external_consumers_of_private_feasibility_readers():
    consumers = set()
    for path in PACKAGE.rglob("*.py"):
        names = module_imports(path)
        if names & {
            "dota_items.data.feasibility._parse",
            "dota_items.data.feasibility._read_bytes",
        }:
            consumers.add(path.relative_to(PACKAGE).as_posix())
    assert not consumers
