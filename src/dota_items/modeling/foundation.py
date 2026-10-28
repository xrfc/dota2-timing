"""Backward-compatible public facade. New code can import individual modules.

Importing this facade never imports sklearn; training is lazy and explicit.
"""

from dota_items.contracts.lineup import columns as columns

from .artifacts import load_model as load_model
from .artifacts import save_model as save_model
from .artifacts import validate_model as validate_model
from .batch import Batch as Batch
from .batch import adapt_snapshot as adapt_snapshot
from .inference import predict_lineup as predict_lineup
from .provenance import IMPLEMENTATION_FILES as IMPLEMENTATION_FILES
from .provenance import SCHEMA as SCHEMA
from .specs import C_GRID as C_GRID
from .specs import ITEMS as ITEMS
from .specs import check_lineup as check_lineup
from .specs import check_preprocessing as check_preprocessing
from .specs import check_task as check_task


def fit_model(
    batch, *, family="frequency", c=1.0, solver="liblinear", source_sha256, code_revision
):
    """Compatibility call; no implicit selection or test evaluation."""
    from .training import fit_model as fit

    return fit(
        batch,
        family=family,
        c=c,
        solver=solver,
        source_sha256=source_sha256,
        code_revision=code_revision,
    )
