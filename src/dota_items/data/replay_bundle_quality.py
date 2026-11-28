"""Recompute replay quality before cache admission, independently of stored claims.

Byte integrity is provided by ``replay_bundle``. This layer checks the actual
normalized/state/extras contents against the hash-bound metadata and parser
observations. It does not decode the original replay again or authenticate a
jointly rewritten manifest. Callers should supply the frozen identity/producer.
An honest ``review_required`` bundle may be returned, but only ``passed`` is
eligible for a successful cache entry. Original full-range/excluded row counts
are retained provenance: only their nonnegative arithmetic can be rechecked
after out-of-game rows were deliberately omitted from the stored channels.
"""

import json
from pathlib import Path

from dota_items.data.replay_bundle import iter_channel, read_json_artifact, verify_bundle
from dota_items.data.replay_quality import (
    QUALITY_SCHEMA,
    ChannelAudit,
    inspect_base,
    quality_result,
)
from dota_items.data.source_io import parse_source_json, read_source_bytes

_ROLES = {"raw", "normalized", "state", "extras"}
_SLOTS = set(range(5)) | set(range(128, 133))
_CHANNEL_SCHEMAS = {"state": "gem-state-capture/3", "extras": "gem-extras-capture/1"}
_RECOMPUTABLE = (
    "kind",
    "in_game_rows",
    "ten_hero_rows",
    "errors",
    "field_observations",
    "field_missing",
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _equal(actual, expected, label):
    """Keep JSON types distinct: e.g. True is not the integer one."""
    try:
        left = json.dumps(actual, sort_keys=True, allow_nan=False)
        right = json.dumps(expected, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {label}") from error
    _require(left == right, f"{label} differs from revalidated content")


def _metadata(identity):
    mid = identity.get("match_id")
    _require(type(mid) is int and mid > 0, "Invalid bundle match identity")
    _require(identity.get("training_allowed") is False, "Unexpected training authorization")
    references = identity.get("source_references")
    _require(type(references) is list and len(references) == 3, "Expected three ordered references")
    paths = [reference["path"] for reference in references]
    _require(len(set(paths)) == 3, "Source references must be distinct")
    # The worker freezes this order: official patch snapshot, metadata, demo.
    meta = parse_source_json(read_source_bytes(Path(paths[1])))
    _require(type(meta) is dict, "Metadata must be an object")
    _require(
        type(meta.get("match_id")) is int and meta["match_id"] == mid, "Metadata identity mismatch"
    )
    duration = meta.get("duration")
    _require(type(duration) is int and 0 < duration <= 86400, "Invalid metadata duration")
    players = meta.get("players")
    _require(type(players) is list and len(players) == 10, "Metadata requires ten players")
    _require(
        all(
            type(player) is dict
            and type(player.get("player_slot")) is int
            and type(player.get("hero_id")) is int
            and player["hero_id"] > 0
            for player in players
        ),
        "Invalid metadata player identity",
    )
    _require(
        {player["player_slot"] for player in players} == _SLOTS, "Metadata player slots mismatch"
    )
    _require(
        len({player["hero_id"] for player in players}) == 10, "Metadata heroes are not distinct"
    )
    return meta


def _channel(root, name, manifest, meta):
    values = iter(iter_channel(root, name))
    header = next(values, None)
    _require(type(header) is dict, "Missing channel header")
    _require(header.get("schema") == _CHANNEL_SCHEMAS[name], f"Unexpected {name} schema")
    _require(
        type(header.get("match_id")) is int and header["match_id"] == meta["match_id"],
        f"{name} header match identity mismatch",
    )
    _equal(
        header.get("window"),
        {"start": 0, "end_inclusive": meta["duration"]},
        name + " window",
    )
    _equal(header.get("producer_schema"), manifest["producer"].get("schema"), name + " producer")
    audit = ChannelAudit(name, meta["duration"])
    for row in values:
        _require(audit.accept(row), f"Stored {name} contains an out-of-game row")
    observed = audit.finish()
    _equal(header["seconds"], observed["in_game_rows"], name + " header row count")
    claimed = manifest["quality"].get(name)
    _require(type(claimed) is dict, f"Missing {name} quality summary")
    for field in _RECOMPUTABLE:
        _require(field in claimed, f"Missing {name} quality field: {field}")
        _equal(claimed[field], observed[field], f"{name} {field}")
    for field in ("total_rows", "excluded_rows"):
        _require(type(claimed.get(field)) is int and claimed[field] >= 0, f"Invalid {name} {field}")
    _require(
        claimed["total_rows"] == observed["in_game_rows"] + claimed["excluded_rows"],
        f"{name} original row accounting mismatch",
    )
    return observed


def verify_quality_bundle(root, *, expected_identity=None, expected_producer=None):
    """Verify bytes/sources and recompute quality; never trust a stored success flag.

    Return the verified manifest with its original status. ``review_required``
    is a verified diagnostic result, not approval for successful cache reuse.
    Source reference order is snapshot, metadata, demo, as frozen by the worker.
    """
    root = Path(root)
    manifest = verify_bundle(
        root, expected_identity=expected_identity, expected_producer=expected_producer
    )
    artifacts = manifest["artifacts"]
    _require(
        set(artifacts) == _ROLES, "Quality bundle requires exactly raw/normalized/state/extras"
    )
    for name in _ROLES:
        expected = "jsonl" if name in _CHANNEL_SCHEMAS else "json"
        _require(artifacts[name]["format"] == expected, f"Unexpected {name} artifact format")
    quality = manifest["quality"]
    _require(quality.get("schema") == QUALITY_SCHEMA, "Unexpected replay quality schema")
    _require(quality.get("training_allowed") is False, "Unexpected quality training authorization")
    parser = quality.get("parser")
    _require(type(parser) is dict, "Missing observed parser evidence")
    meta = _metadata(manifest["identity"])
    normalized = read_json_artifact(root, "normalized")
    _require(type(normalized) is dict, "Normalized artifact must be an object")
    _require(
        normalized.get("evidence_sha256") == artifacts["raw"]["uncompressed_sha256"],
        "Normalized raw evidence digest mismatch",
    )
    _require(
        normalized.get("evidence_source") == artifacts["raw"]["path"],
        "Normalized raw evidence source mismatch",
    )
    base = inspect_base(normalized, parser, meta)
    _equal(quality.get("base"), base, "Base quality")
    del normalized
    state, extras = (_channel(root, name, manifest, meta) for name in ("state", "extras"))
    derived = quality_result(base, state, extras)
    _equal(quality.get("errors"), derived["errors"], "Combined quality errors")
    _equal(quality.get("status"), derived["status"], "Quality status")
    # Recheck references and manifest after streaming; ordinary source, artifact
    # or declaration drift during verification must not leave an approved cache.
    after = verify_bundle(
        root,
        expected_identity=manifest["identity"],
        expected_producer=manifest["producer"],
    )
    _equal(after, manifest, "Manifest after quality verification")
    return manifest
