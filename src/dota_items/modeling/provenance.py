"""Explicit implementation manifests; old /1 bundles remain readable."""

SCHEMA = "purchase-foundation-model/1"
LEGACY_IMPLEMENTATION_FILES = (
    "src/dota_items/modeling/foundation.py",
    "src/dota_items/contracts/lineup.py",
    "src/dota_items/modeling/purchase_baseline.py",
    "src/dota_items/storage.py",
)
IMPLEMENTATION_FILES = (
    "src/dota_items/modeling/foundation.py",
    "src/dota_items/contracts/lineup.py",
    "src/dota_items/storage.py",
    "src/dota_items/modeling/_validation.py",
    "src/dota_items/modeling/specs.py",
    "src/dota_items/modeling/batch.py",
    "src/dota_items/modeling/training.py",
    "src/dota_items/modeling/artifacts.py",
    "src/dota_items/modeling/inference.py",
    "src/dota_items/modeling/provenance.py",
    "src/dota_items/modeling/estimators/__init__.py",
    "src/dota_items/modeling/estimators/frequency.py",
    "src/dota_items/modeling/estimators/logistic.py",
)
