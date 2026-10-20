"""Projected component proposals, not formal splits or training permission."""

import hashlib
from collections import Counter

from dota_items.storage import json_bytes

SEED = "cohort-v2-20261018-remote-01"


def support(rows, items):
    result = {}
    for j, item in enumerate(items):
        positive = sum(r["labels"][j] == 1 for r in rows if r["mask"][j])
        observed = sum(r["mask"][j] for r in rows)
        result[item] = {
            "positive": positive,
            "negative": observed - positive,
            "unknown": len(rows) - observed,
            "positive_rate": positive / observed if observed else None,
        }
    return result


def project(groups, rows, items):
    if not items or len(set(items)) != len(items):
        raise ValueError("Unique nonempty item order required")
    candidates = {}
    for row in rows:
        mid = row["match_id"]
        if type(mid) is not int or mid <= 0 or mid in candidates:
            raise ValueError("Duplicate or invalid candidate ID")
        if row["cohort"] not in ("old", "new"):
            raise ValueError("Invalid cohort")
        if len(row["labels"]) != len(items) or len(row["mask"]) != len(items):
            raise ValueError("Label/mask dimension mismatch")
        for label, mask in zip(row["labels"], row["mask"], strict=True):
            if type(mask) is not bool:
                raise ValueError("Mask must be boolean")
            if (mask and (type(label) is not int or label not in (0, 1))) or (
                not mask and label is not None
            ):
                raise ValueError("Unknown labels must remain masked null")
        candidates[mid] = row
    if not candidates:
        raise ValueError("Empty candidate pool")
    seen, projected = set(), []
    for group in groups:
        if not group or any(type(mid) is not int or mid <= 0 for mid in group):
            raise ValueError("Invalid graph group")
        if len(set(group)) != len(group) or seen.intersection(group):
            raise ValueError("Graph membership is not disjoint")
        seen.update(group)
        kept = sorted(set(group) & candidates.keys())
        if kept:
            projected.append(kept)
    if not candidates.keys() <= seen:
        raise ValueError("Graph does not cover candidates")
    return sorted(projected, key=lambda g: (-len(g), tuple(g))), candidates, len(seen)


def analyze(groups, rows, items):
    projected, by_id, graph_count = project(groups, rows, items)
    largest = projected[0]
    all_ids = set(by_id)
    total = len(all_ids)
    # This ordering uses only component identities, never labels or model scores.
    rest = sorted(
        projected[1:],
        key=lambda g: (hashlib.sha256(json_bytes([SEED, g])).hexdigest(), tuple(g)),
    )
    rules = (("target20", 0.20), ("target25", 0.25), ("all_rest", None))
    proposals, private = [], {}
    for name, fraction in rules:
        target = total * fraction if fraction is not None else total - len(largest)
        validation, validation_groups = [], 0
        for group in rest:
            if fraction is None or abs(len(validation) + len(group) - target) < abs(
                len(validation) - target
            ):
                validation.extend(group)
                validation_groups += 1
        val_set = set(validation)
        train_set = all_ids - val_set
        assert not val_set.intersection(largest)
        partition = {"train": sorted(train_set), "validation": sorted(val_set)}
        private[name] = partition
        stats = {}
        for split, ids in partition.items():
            selected = [by_id[mid] for mid in ids]
            stats[split] = {
                "matches": len(ids),
                "components": validation_groups
                if split == "validation"
                else len(projected) - validation_groups,
                "cohorts": dict(Counter(r["cohort"] for r in selected)),
                "historical_membership": dict(Counter(r.get("old_split", "new") for r in selected)),
                "support": support(selected, items),
            }
        bias = {}
        for item in items:
            a = stats["train"]["support"][item]["positive_rate"]
            b = stats["validation"]["support"][item]["positive_rate"]
            bias[item] = None if a is None or b is None else 100 * (b - a)
        proposals.append(
            {
                "name": name,
                "target_validation_fraction": fraction,
                "actual_validation_fraction": len(validation) / total,
                "validation_target_count_error": len(validation) - target,
                "nonempty_sides": bool(train_set and val_set),
                "whole_groups_verified": all(
                    set(g) <= train_set or set(g) <= val_set for g in projected
                ),
                "membership_sha256": hashlib.sha256(json_bytes(partition)).hexdigest(),
                "train_largest_component_fraction": len(largest) / len(train_set),
                "splits": stats,
                "validation_minus_train_positive_rate_pp": bias,
            }
        )
    histogram = Counter(map(len, projected))
    return {
        "schema_version": "cohort-split-feasibility/1",
        "analysis_id": SEED,
        "formal_split_assigned": False,
        "training_executed": False,
        "rules": (
            "Largest projected group in train; fixed SHA256 order; "
            "strict count-distance improvement; no label search"
        ),
        "candidate_count": total,
        "graph_match_count": graph_count,
        "identity_only_count": graph_count - total,
        "graph_components": len(groups),
        "projected_components": len(projected),
        "identity_only_components": len(groups) - len(projected),
        "component_size_histogram": {str(k): histogram[k] for k in sorted(histogram)},
        "largest_candidate_component": len(largest),
        "largest_candidate_fraction": len(largest) / total,
        "largest_component_support": support([by_id[mid] for mid in largest], items),
        "largest_component_cohorts": dict(Counter(by_id[mid]["cohort"] for mid in largest)),
        "support": support(rows, items),
        "proposals": proposals,
        "limitations": [
            "Development validation only; old holdouts were already viewed.",
            "New collection is chronologically earlier, not a future test set.",
            "Identity-only excluded matches create edges, never training labels.",
            "Known-account connectivity is not verified real-person independence.",
            "Label rates are diagnostics after assignment, not assignment objectives.",
        ],
    }, private
