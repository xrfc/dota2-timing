"""Read-only summaries of strictly validated model artifacts, never predictions."""

from .artifacts import load_model
from .provenance import LEGACY_IMPLEMENTATION_FILES


def inspect_model(path):
    """Load one local artifact strictly and return JSON-compatible recorded metadata.

    No dataset, training, prediction, current source comparison or repair is performed.
    Hashes establish internal identity consistency, not authenticity or permission.
    """
    artifact = load_model(path)
    preprocessing = artifact["preprocessing"]
    provenance = artifact["provenance"]
    files = provenance.get("implementation_files_sha256")
    if files is None:
        coverage = "legacy_no_bundle"
    elif set(files) == set(LEGACY_IMPLEMENTATION_FILES):
        coverage = "historical_four_files"
    else:
        coverage = "modular_manifest"
    targets = []
    for model in artifact["models"]:
        support = model["support"]
        targets.append(
            {
                "item": model["item"],
                "status": model["status"],
                "reason": model.get("reason"),
                "support": {
                    "positive": support["positive"],
                    "negative": support["observed"] - support["positive"],
                    "observed": support["observed"],
                    "unknown": support["unknown"],
                    "total": support["observed"] + support["unknown"],
                },
            }
        )
    # Select fields explicitly: do not echo arbitrary extra metadata or raw samples.
    task = artifact["task"]
    return {
        "schema_version": artifact["schema_version"],
        "family": artifact["family"],
        "synthetic": artifact["synthetic"],
        "task": {
            key: task[key]
            for key in (
                "target",
                "candidate_items",
                "window",
                "negative_means",
                "actual_purchase_ground_truth",
            )
        },
        "recorded_meaning": artifact["meaning"],
        "limitations": [
            "Source log presence only; negatives mean absent from valid source logs.",
            "Not complete purchase ground truth or optimal equipment recommendations.",
            "Inspection is not performance evidence or training authorization.",
            "Hashes check identity consistency, not source authenticity.",
            "Recorded implementation hashes are not verified against current source code.",
        ],
        "preprocessing": {
            "vocabulary_size": len(preprocessing["vocabulary"]),
            "feature_dimension": len(preprocessing["columns"]),
            "fit_split": preprocessing["fit_split"],
        },
        "targets": targets,
        "parameters": artifact["parameters"],
        "provenance": {
            "source_sha256": provenance["source_sha256"],
            "code_revision": provenance["code_revision"],
            "python": provenance["python"],
            "dependencies": {
                key: provenance["dependencies"][key] for key in ("numpy", "scikit-learn")
            },
            "implementation": {
                "coverage": coverage,
                "implementation_sha256": provenance["implementation_sha256"],
                "recorded_files_sha256": files,
                "recorded_file_count": len(files) if files is not None else 1,
                "recorded_bundle_sha256": provenance.get("implementation_bundle_sha256"),
                "current_source_verified": False,
            },
        },
    }
