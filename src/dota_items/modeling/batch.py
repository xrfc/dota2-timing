"""Snapshot-to-array boundary; never selects models or reads test payloads."""

import copy
from dataclasses import dataclass

import numpy as np

from dota_items.contracts.lineup import encode_lineup, fit_vocabulary
from dota_items.contracts.tasks import validate_task_envelope

from ._validation import _mapping
from .specs import check_lineup, check_preprocessing, check_task, task_items


@dataclass
class Batch:
    x: np.ndarray
    y: np.ndarray
    mask: np.ndarray
    metadata: list
    split: str
    preprocessing: dict
    task: dict
    synthetic: bool


def adapt_snapshot(snapshot, split="train"):
    """Read only the requested development split; test payloads stay opaque."""
    if split not in ("train", "validation"):
        raise ValueError("Only train/validation adaptation is supported")
    _mapping(snapshot, ("task", "preprocessing", "splits", "samples"), "snapshot")
    if "synthetic" in snapshot and type(snapshot["synthetic"]) is not bool:
        raise ValueError("Invalid synthetic marker")
    validate_task_envelope(
        snapshot["task"],
        snapshot.get("schema_version"),
        "purchase-log-modeling-snapshot/1",
        "purchase-log-modeling-snapshot/2",
    )
    if snapshot.get("modeling_ready") is not True:
        raise ValueError("Snapshot not modeling ready")
    check_task(snapshot["task"])
    items = task_items(snapshot["task"])
    prep = snapshot["preprocessing"]
    vocabulary = check_preprocessing(prep)
    splits = snapshot["splits"]
    names = ("train", "validation", "test")
    _mapping(splits, names, "split manifest")
    if any(not isinstance(splits[name], list) for name in names):
        raise ValueError("Split IDs must be lists")
    ids = [mid for name in names for mid in splits[name]]
    if any(type(mid) is not int or mid <= 0 for mid in ids) or len(ids) != len(set(ids)):
        raise ValueError("Invalid or overlapping split IDs")
    if not isinstance(snapshot["samples"], list):
        raise ValueError("Samples must be a list")
    rows = []
    for row in snapshot["samples"]:
        _mapping(row, ("split",), "sample split")
        if row["split"] not in ("train", "validation", "test"):
            raise ValueError("Unknown split")
        if row["split"] == split:
            rows.append(row)
    for row in rows:
        _mapping(
            row,
            (
                "match_id",
                "features",
                "encoded_features",
                "labels",
                "label_mask",
                "group_id",
                "role_hint",
                "source_sha256",
            ),
            "selected sample",
        )
    selected_ids = [r["match_id"] for r in rows]
    if any(type(mid) is not int or mid <= 0 for mid in selected_ids):
        raise ValueError("Invalid selected match ID")
    if not rows or len(set(selected_ids)) != len(rows) or set(selected_ids) != set(splits[split]):
        raise ValueError("Split membership mismatch or empty split")
    x, y, masks, metadata = [], [], [], []
    for row in rows:
        check_lineup(row["features"])
        encoded = encode_lineup(row["features"], vocabulary)
        supplied = row["encoded_features"]
        if (
            not isinstance(supplied, list)
            or len(supplied) != len(encoded)
            or any(type(v) is not int for v in supplied)
            or supplied != encoded
        ):
            raise ValueError("Encoded feature mismatch")
        labels, mask = row["labels"], row["label_mask"]
        if (
            not isinstance(labels, list)
            or not isinstance(mask, list)
            or len(labels) != len(items)
            or len(mask) != len(items)
        ):
            raise ValueError("Label dimension mismatch")
        if any(type(m) is not bool for m in mask):
            raise ValueError("Mask must be boolean")
        for value, observed in zip(labels, mask, strict=True):
            if observed and (type(value) is not int or value not in (0, 1)):
                raise ValueError("Observed labels must be binary integers")
            if not observed and value is not None:
                raise ValueError("Unknown labels must be null")
        x.append(encoded)
        y.append(
            [value if observed else np.nan for value, observed in zip(labels, mask, strict=True)]
        )
        masks.append(mask)
        metadata.append({k: row[k] for k in ("match_id", "group_id", "role_hint", "source_sha256")})
    if split == "train" and fit_vocabulary([r["features"] for r in rows]) != vocabulary:
        raise ValueError("Vocabulary must be fitted only on train")
    return Batch(
        np.asarray(x, dtype=float),
        np.asarray(y, dtype=float),
        np.asarray(masks, dtype=bool),
        metadata,
        split,
        copy.deepcopy(prep),
        copy.deepcopy(snapshot["task"]),
        snapshot.get("synthetic") is True,
    )
