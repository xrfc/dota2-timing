"""Read-only paired resource diagnostics; not a model task or castability gate."""

import copy
import math

MANA_FIELDS = ("m_flMana", "m_flMaxMana")


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _without_metadata(value):
    if isinstance(value, dict):
        return {k: _without_metadata(v) for k, v in value.items() if k != "field_metadata"}
    if isinstance(value, list):
        return [_without_metadata(v) for v in value]
    return value


def _mana_metadata(row, high):
    fields = row["hero"]["field_metadata"]
    for name in MANA_FIELDS:
        matches = [f for f in fields if f["var_name"] == name]
        if len(matches) != 1:
            raise ValueError("Missing or duplicate mana field metadata")
        field = matches[0]
        if (
            field["var_type"] != "float32"
            or field["bit_count"] != 20
            or field["high_value"] != high
            or field["low_value"] is not None
            or field["encode_flags"] is not None
        ):
            raise ValueError("Unaudited mana encoding")


def compare_captures(old, new):
    """Require unchanged identity and non-mana observations at old sample ticks.

    Extra new rows are a fixed diagnostic window, NOT additional training data.
    Shared-source agreement is explicitly not independent gameplay validation.
    """
    for key in ("match_id", "build", "demo_sha256", "decision_tick"):
        if old[key] != new[key]:
            raise ValueError("Capture identity mismatch")
    if new["build"] != 6965:
        raise ValueError("Unaudited capture build")
    old_ticks = [r["tick"] for r in old["rows"]]
    expected = [old["decision_tick"] + offset for offset in (-30, 0, 30)]
    if old_ticks != expected:
        raise ValueError("Unexpected old sample selection")
    rows = new["rows"]
    ticks = [r["tick"] for r in rows]
    if ticks != sorted(set(ticks)) or not set(old_ticks) <= set(ticks):
        raise ValueError("Missing, duplicate or unordered new samples")
    indexed = {r["tick"]: r for r in rows}
    paired = []
    for before in old["rows"]:
        after = indexed[before["tick"]]
        _mana_metadata(before, 8192.0)
        _mana_metadata(after, 65536.0)
        left, right = _without_metadata(before), _without_metadata(after)
        values = []
        for name in MANA_FIELDS:
            a, b = left["hero"]["values"].pop(name), right["hero"]["values"].pop(name)
            if not _number(a) or not _number(b) or a < 0 or b < 0:
                raise ValueError("Nonfinite, missing or negative resource observation")
            # Diagnostic consequence of the audited flag-free quantizer only.
            # New values MUST come from the replay, never from this ratio.
            if not math.isclose(b, a * 8, rel_tol=1e-12, abs_tol=1e-9):
                raise ValueError("Unexpected paired quantizer relationship")
            values.append({"field": name, "old": a, "redecoded": b})
        if left != right:
            raise ValueError("Non-mana observations changed")
        paired.append({"tick": before["tick"], "resources": values})

    identities = set()
    series = []
    for row in rows:
        _mana_metadata(row, 65536.0)
        hero = row["hero"]
        identities.add((row["player_id"], hero["entity_index"], hero["entity_serial"]))
        mana, maximum = (hero["values"][name] for name in MANA_FIELDS)
        clock = row["parser_game_time_s"]
        if not all(_number(v) for v in (mana, maximum, clock)) or not 0 <= mana <= maximum:
            raise ValueError("Invalid resource diagnostic sample")
        series.append(
            {"tick": row["tick"], "game_time_s": clock, "mana": mana, "max_mana": maximum}
        )
    if len(identities) != 1:
        raise ValueError("Diagnostic window entity identity changed")
    changes = []
    for a, b in zip(series, series[1:], strict=False):
        if b["game_time_s"] < a["game_time_s"]:
            raise ValueError("Resource clock moved backwards")
        changes.append(
            {
                "from_tick": a["tick"],
                "to_tick": b["tick"],
                "elapsed_game_s": b["game_time_s"] - a["game_time_s"],
                "mana_delta": b["mana"] - a["mana"],
                "max_mana_delta": b["max_mana"] - a["max_mana"],
            }
        )
    return {
        "schema": "decision-mana-comparison/1",
        "match_id": old["match_id"],
        "decision_tick": old["decision_tick"],
        "paired_samples": paired,
        "non_mana_observations_unchanged": True,
        "series": series,
        "changes": changes,
        "negative_delta_intervals": sum(c["mana_delta"] < 0 for c in changes),
        "positive_delta_intervals": sum(c["mana_delta"] > 0 for c in changes),
        "decoder_range_corrected": True,
        "independent_gameplay_units_certified": False,
        "can_cast": None,
        "training_allowed": False,
        "future_sample_policy": "tick > decision_tick is validation only, never a feature",
    }


def current_resource(comparison):
    """Project one CURRENT diagnostic observation, excluding temporal summaries.

    A future perturbation must not change this projection. No whole-file hashes,
    future deltas or gameplay-readiness claims enter the projected object.
    """
    rows = [r for r in comparison["series"] if r["tick"] == comparison["decision_tick"]]
    if len(rows) != 1:
        raise ValueError("Missing or duplicate current resource")
    return {
        "match_id": comparison["match_id"],
        **copy.deepcopy(rows[0]),
        "status": "redecoded_source_observation_not_independent_gameplay_certification",
        "can_cast": None,
        "training_allowed": False,
    }
