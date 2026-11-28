"""A self-consistent storage checksum is not sufficient for quality cache admission."""

import copy
import gzip
import hashlib
import json

import pytest

from dota_items.data.replay_bundle import BundleWriter, verify_bundle
from dota_items.data.replay_bundle_quality import verify_quality_bundle
from dota_items.data.replay_quality import ChannelAudit, inspect_base, quality_result

MID = 9_103_408_009
PRODUCER = {"schema": "synthetic-quality-producer/1"}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def reference(path):
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def state_row(t):
    return {
        "t": t,
        "heroes": [
            {
                "player_id": pid,
                "hp": 100,
                "max_hp": 100,
                "mana": 50,
                "max_mana": 50,
                "level": 1,
                "pos": [100, 200],
                "abilities": [{"name": "ability", "cd": 0, "cd_len": 10}],
                "items": {"0": {"name": "item", "cd": 0, "cd_len": 30}},
            }
            for pid in range(10)
        ],
    }


def extras_row(t):
    return {"t": t, "creeps": [], "watchers": [], "outposts": [], "scan": {}}


def make_bundle(tmp_path, *, state_change=None, parser_change=None):
    players = [
        {"player_slot": slot, "hero_id": n + 1}
        for n, slot in enumerate([*range(5), *range(128, 133)])
    ]
    meta = {"match_id": MID, "duration": 2, "players": players}
    snapshot, metadata, demo = (tmp_path / name for name in ("patches.json", "meta.json", "m.dem"))
    write_json(snapshot, {"patches": []})
    write_json(metadata, meta)
    demo.write_bytes(b"synthetic demo")
    identity = {
        "match_id": MID,
        "training_allowed": False,
        "source_references": [reference(path) for path in (snapshot, metadata, demo)],
    }
    channels = {
        name: [] for name in ("wards", "hero_visibility_events", "entity_visibility_events")
    }
    channels.update(coach_state_snapshots=[{"time": 0}], combat_log=[{"time": 1}])
    normalized = {**copy.deepcopy(meta), "context": {"channels": channels}}
    parser = {
        "match_id": MID,
        "game_build": 6993,
        "game_start_tick": 10,
        "post_game_tick": 70,
        "post_game_seconds": 2,
        "parse_error": None,
        "truncated_at_tick": None,
    }
    if parser_change:
        parser_change(parser)
    rows = {"state": [state_row(t) for t in range(3)], "extras": [extras_row(t) for t in range(3)]}
    if state_change:
        state_change(rows["state"])
    summaries = {}
    for name in rows:
        audit = ChannelAudit(name, 2)
        for row in [{"t": -1}, *rows[name], {"t": 3}]:
            audit.accept(row)
        summaries[name] = audit.finish()
    quality = quality_result(inspect_base(normalized, parser, meta), **summaries)
    quality.update(parser=parser, adapter_issues=[], unpacked_demo_sha256="a" * 64)
    root = tmp_path / "bundle"
    writer = BundleWriter(root, identity=identity, producer=PRODUCER)
    raw = writer.add_json("raw", {"match_id": MID, "post_game_tick": 70})
    normalized.update(evidence_source=raw["path"], evidence_sha256=raw["uncompressed_sha256"])
    writer.add_json("normalized", normalized)
    for name, schema in (("state", "gem-state-capture/3"), ("extras", "gem-extras-capture/1")):
        header = {
            "schema": schema,
            "match_id": MID,
            "seconds": len(rows[name]),
            "window": {"start": 0, "end_inclusive": 2},
            "producer_schema": PRODUCER["schema"],
        }
        writer.add_channel(name, header, rows[name])
    return root, writer.finish(quality)


def save_manifest(root, value):
    write_json(root / "manifest.json", value)


def change_artifact(root, manifest, role, change):
    """Resign a modified artifact to isolate semantic checks from byte checks."""
    descriptor = manifest["artifacts"][role]
    path = root / descriptor["path"]
    raw = gzip.decompress(path.read_bytes())
    if descriptor["format"] == "jsonl":
        value = [json.loads(line) for line in raw.splitlines()]
        change(value)
        raw = b"".join((json.dumps(row) + "\n").encode() for row in value)
    else:
        value = json.loads(raw)
        change(value)
        raw = json.dumps(value).encode()
    compressed = gzip.compress(raw, mtime=0)
    path.write_bytes(compressed)
    descriptor.update(
        compressed_sha256=hashlib.sha256(compressed).hexdigest(),
        uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
        compressed_bytes=len(compressed),
        uncompressed_bytes=len(raw),
    )
    save_manifest(root, manifest)
    # The attack intentionally passes the storage-only integrity check.
    verify_bundle(root)


def test_recomputed_quality_accepts_complete_clipped_bundle(tmp_path):
    root, manifest = make_bundle(tmp_path)
    actual = verify_quality_bundle(
        root, expected_identity=manifest["identity"], expected_producer=PRODUCER
    )
    assert actual == manifest
    assert actual["quality"]["status"] == "passed"
    assert actual["quality"]["state"]["total_rows"] == 5
    assert actual["quality"]["state"]["excluded_rows"] == 2


def test_honest_review_result_is_preserved_but_forged_success_rejected(tmp_path):
    root, manifest = make_bundle(
        tmp_path, state_change=lambda rows: rows[1]["heroes"][0].update(hp=None)
    )
    assert verify_quality_bundle(root)["quality"]["status"] == "review_required"
    manifest["quality"]["status"] = "passed"
    save_manifest(root, manifest)
    verify_bundle(root)
    with pytest.raises(ValueError, match="Quality status"):
        verify_quality_bundle(root)


@pytest.mark.parametrize("role", ["raw", "normalized", "state", "extras"])
def test_missing_role_cannot_be_a_completed_quality_bundle(tmp_path, role):
    root, manifest = make_bundle(tmp_path)
    descriptor = manifest["artifacts"].pop(role)
    (root / descriptor["path"]).unlink()
    save_manifest(root, manifest)
    verify_bundle(root)
    with pytest.raises(ValueError, match="requires exactly"):
        verify_quality_bundle(root)


@pytest.mark.parametrize(
    "field,value",
    [
        ("in_game_rows", 4),
        ("ten_hero_rows", 2),
        ("errors", ["invented"]),
        ("field_observations", {}),
        ("field_missing", {}),
        ("total_rows", 6),
        ("excluded_rows", -1),
        ("total_rows", 5.0),
    ],
)
def test_claimed_channel_counts_and_errors_must_match_real_rows(tmp_path, field, value):
    root, manifest = make_bundle(tmp_path)
    manifest["quality"]["state"][field] = value
    save_manifest(root, manifest)
    with pytest.raises(ValueError):
        verify_quality_bundle(root)


def test_boolean_missing_counter_does_not_equal_integer_zero(tmp_path):
    root, manifest = make_bundle(tmp_path)
    manifest["quality"]["state"]["field_missing"]["hero.hp"] = False
    save_manifest(root, manifest)
    with pytest.raises(ValueError, match="field_missing"):
        verify_quality_bundle(root)


@pytest.mark.parametrize("change", ["hp", "hero", "gap", "backward", "extras"])
def test_bad_actual_channel_cannot_pass_by_resigning_storage(tmp_path, change):
    root, manifest = make_bundle(tmp_path)

    def mutate(values):
        if change == "hp":
            values[2]["heroes"][0]["hp"] = None
        elif change == "hero":
            values[2]["heroes"].pop()
        elif change == "gap":
            del values[2]
            values[0]["seconds"] -= 1
        elif change == "backward":
            values[2]["t"] = 0
        else:
            values[2]["scan"] = None

    change_artifact(root, manifest, "extras" if change == "extras" else "state", mutate)
    with pytest.raises(ValueError):
        verify_quality_bundle(root)


@pytest.mark.parametrize(
    "field,value",
    [
        ("match_id", MID + 1),
        ("match_id", str(MID)),
        ("schema", "gem-extra-capture/1"),
        ("window", {"start": -1, "end_inclusive": 2}),
        ("seconds", 4),
        ("producer_schema", "different/1"),
    ],
)
def test_channel_header_identity_schema_window_and_count_are_checked(tmp_path, field, value):
    root, manifest = make_bundle(tmp_path)
    change_artifact(root, manifest, "state", lambda values: values[0].update({field: value}))
    with pytest.raises(ValueError):
        verify_quality_bundle(root)


def test_stored_postgame_row_is_rejected_even_with_consistent_summary(tmp_path):
    root, manifest = make_bundle(tmp_path)

    def append_postgame(values):
        values.append(state_row(3))
        values[0]["seconds"] += 1

    change_artifact(root, manifest, "state", append_postgame)
    with pytest.raises(ValueError, match="out-of-game"):
        verify_quality_bundle(root)


@pytest.mark.parametrize("change", ["raw", "binding", "source_name", "normalized_id", "duration"])
def test_raw_binding_and_base_identity_are_recomputed(tmp_path, change):
    root, manifest = make_bundle(tmp_path)
    if change == "raw":
        change_artifact(root, manifest, "raw", lambda value: value.update(changed=True))
    else:
        updates = {
            "binding": {"evidence_sha256": "b" * 64},
            "source_name": {"evidence_source": "other.json.gz"},
            "normalized_id": {"match_id": MID + 1},
            "duration": {"duration": 3},
        }
        change_artifact(root, manifest, "normalized", lambda value: value.update(updates[change]))
    with pytest.raises(ValueError):
        verify_quality_bundle(root)


@pytest.mark.parametrize(
    "field,value", [("post_game_tick", None), ("match_id", MID + 1), ("game_build", 0)]
)
def test_missing_end_or_wrong_parser_identity_cannot_keep_old_success(tmp_path, field, value):
    root, manifest = make_bundle(tmp_path)
    manifest["quality"]["parser"][field] = value
    save_manifest(root, manifest)
    with pytest.raises(ValueError, match="Base quality"):
        verify_quality_bundle(root)


def test_missing_end_honestly_recorded_is_diagnostic_not_success(tmp_path):
    root, manifest = make_bundle(
        tmp_path, parser_change=lambda parser: parser.update(post_game_tick=None)
    )
    assert manifest["quality"]["status"] == "review_required"
    assert verify_quality_bundle(root)["quality"]["status"] == "review_required"


def test_metadata_reference_order_and_identity_are_required(tmp_path):
    root, manifest = make_bundle(tmp_path)
    refs = manifest["identity"]["source_references"]
    refs[0], refs[1] = refs[1], refs[0]
    save_manifest(root, manifest)
    with pytest.raises(ValueError, match="Metadata identity"):
        verify_quality_bundle(root)


def test_frozen_identity_producer_and_external_reference_are_checked(tmp_path):
    root, manifest = make_bundle(tmp_path)
    with pytest.raises(ValueError, match="producer mismatch"):
        verify_quality_bundle(root, expected_producer={"schema": "different/1"})
    with pytest.raises(ValueError, match="identity mismatch"):
        verify_quality_bundle(root, expected_identity={**manifest["identity"], "match_id": MID + 1})
    (tmp_path / "m.dem").write_bytes(b"changed")
    with pytest.raises(ValueError, match="reference"):
        verify_quality_bundle(root)
