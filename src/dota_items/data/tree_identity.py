"""Complete native tree identity requires explicit IDs, never map array ordinals."""

import math


class IncompleteTreeIdentity(ValueError):
    pass


def _integer(value):
    return type(value) is int and value >= 0


def _xyz(row):
    values = tuple(row.get(k) for k in ("x", "y", "z"))
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("Tree coordinates must be explicit finite XYZ")
    return values


def parse_tree_export(text, *, exact_patch, expected_build):
    """Read delimited console records; require one complete header and trailer."""
    if (
        not isinstance(exact_patch, str)
        or not exact_patch
        or not _integer(expected_build)
        or expected_build == 0
    ):
        raise ValueError("Explicit patch/build required")
    header, finished, rows = None, False, []
    for line in text.splitlines():
        if not line.startswith("DOTA_TREE_IDENTITY_"):
            continue
        parts = line.split("\t")
        if finished:
            raise ValueError("Records after tree export end marker")
        if parts[0] == "DOTA_TREE_IDENTITY_BEGIN" and len(parts) == 5:
            if header is not None or parts[1] != "1" or parts[2] != exact_patch:
                raise ValueError("Duplicate or mismatched tree export header")
            if parts[3] != str(expected_build) or parts[4] != "dota":
                raise ValueError("Tree export declared build/map mismatch")
            header = parts
        elif parts[0] == "DOTA_TREE_IDENTITY_ROW" and len(parts) == 7 and header:
            rows.append(
                dict(
                    native_tree_id=int(parts[1]),
                    entity_index=int(parts[2]),
                    roundtrip_entity_index=int(parts[3]),
                    x=float(parts[4]),
                    y=float(parts[5]),
                    z=float(parts[6]),
                )
            )
        elif parts[0] == "DOTA_TREE_IDENTITY_END" and len(parts) == 2 and header:
            if int(parts[1]) != len(rows):
                raise ValueError("Tree export count mismatch")
            finished = True
        else:
            raise ValueError("Malformed tree export record")
    if header is None or not finished or not rows:
        raise IncompleteTreeIdentity("Complete native tree identity export is missing")
    return rows


def reconcile_tree_identity(map_trees, native_rows):
    """Require an XYZ bijection and engine ID round trip, with no nearest-point fill."""
    if not map_trees or not native_rows:
        raise IncompleteTreeIdentity("Tree identity rows are missing")
    points = {_xyz(row): index for index, row in enumerate(map_trees)}
    if len(points) != len(map_trees):
        raise ValueError("Ambiguous duplicate map tree coordinates")
    ids, entities, matched, result = set(), set(), set(), []
    for row in native_rows:
        tree_id, entity = row.get("native_tree_id"), row.get("entity_index")
        if (
            not _integer(tree_id)
            or not _integer(entity)
            or not _integer(row.get("roundtrip_entity_index"))
            or row["roundtrip_entity_index"] != entity
        ):
            raise ValueError("Invalid native tree ID/entity round trip")
        point = _xyz(row)
        if tree_id in ids or entity in entities or point in matched or point not in points:
            raise ValueError("Duplicate or unmatched tree identity")
        ids.add(tree_id)
        entities.add(entity)
        matched.add(point)
        result.append(
            {
                "map_row": points[point],
                "native_tree_id": tree_id,
                "entity_index": entity,
                "x": point[0],
                "y": point[1],
                "z": point[2],
            }
        )
    if matched != set(points):
        raise IncompleteTreeIdentity(
            f"Native identity covers {len(matched)}/{len(points)} map trees"
        )
    return {
        "schema": "native-tree-identity-candidate/1",
        "trees": sorted(result, key=lambda r: r["map_row"]),
        "map_coordinate_coverage_complete": True,
        "replay_build_equivalence_verified": False,
        "observer_bitplane_semantics_verified": False,
        "action_review_allowed": False,
        "training_allowed": False,
    }
