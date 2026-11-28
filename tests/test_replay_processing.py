"""Synthetic worker integration: one capture, identity binding and compressed outputs."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from dota_items.contracts.replay_collection import PatchWindow
from dota_items.data.replay_bundle import iter_channel, read_json_artifact, verify_bundle
from dota_items.workflow import replay_processing as processing

MID = 9000000000
PRODUCER = {"schema": "synthetic-producer/1", "sources": {"capture": "a" * 64}}


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def reference(path):
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def request_fixture(tmp_path):
    snapshot = tmp_path / "patches.json"
    raw = json.dumps(
        {
            "patches": [
                {"patch_number": "7.42", "patch_timestamp": 1700000000},
                {"patch_number": "7.42a", "patch_timestamp": 1701000000},
            ]
        }
    ).encode()
    snapshot.write_bytes(raw)
    window = PatchWindow.from_snapshot(
        raw,
        patch="7.42",
        retrieved_at="2026-11-26T12:00:00+00:00",
        boundary_buffer_seconds=0,
    )
    players = [
        {"player_slot": slot, "hero_id": n + 1}
        for n, slot in enumerate([*range(5), *range(128, 133)])
    ]
    meta = {
        "match_id": MID,
        "patch": 61,
        "start_time": 1700001000,
        "duration": 3,
        "lobby_type": 7,
        "game_mode": 22,
        "players": players,
    }
    metadata = tmp_path / "metadata.json"
    write_json(metadata, meta)
    demo = tmp_path / "source.dem"
    demo.write_bytes(b"PBDEMS2\x00" + b"\x00" * 8)
    identity = {
        "match_id": MID,
        "training_allowed": False,
        "source_references": [reference(path) for path in (snapshot, metadata, demo)],
        "patch_window": window.to_dict(),
        "expected_patch_code": 61,
        "bounds": {"start_lower": 1700000100, "start_upper": 1700010000, "end_upper": 1700020000},
        "min_duration": 1,
        "min_rank": 70,
    }
    request = {
        "match_id": MID,
        "identity": identity,
        "exclusion": {"algorithm": "sha256-mod100", "salt": "synthetic-test", "percent": 0},
        "producer": copy.deepcopy(PRODUCER),
        "metadata_path": str(metadata),
        "snapshot_path": str(snapshot),
        "demo_path": str(demo),
        "discovery": {
            "match_id": MID,
            "start_time": meta["start_time"],
            "duration": meta["duration"],
            "avg_rank_tier": 75,
        },
    }
    request["identity"].update(
        discovery=copy.deepcopy(request["discovery"]),
        exclusion=copy.deepcopy(request["exclusion"]),
        parameters={
            "capture_start": -90,
            "output_window": "0..metadata.duration",
            "codec": "gzip",
            "quality_schema": "replay-quality/1",
        },
    )
    path = tmp_path / "request.json"
    write_json(path, request)
    return path, request, meta


def hero(pid):
    return {
        "player_id": pid,
        "hp": 100,
        "max_hp": 100,
        "mana": 50,
        "max_mana": 50,
        "level": 1,
        "pos": [1.0, 2.0],
        "abilities": [{"name": "synthetic_spell", "cd": 0.0, "cd_len": 3.0}],
        "items": {"0": {"name": "synthetic_item", "cd": 0.0, "cd_len": 1.0}},
    }


def capture_result(meta):
    channels = {key: [] for key in ("hero_visibility_events", "entity_visibility_events", "wards")}
    channels.update(
        coach_state_snapshots=[{"time": 0, "payload": {"player_id": 0}}],
        combat_log=[{"time": 0, "event": "synthetic"}],
    )
    return {
        "normalized": {
            "match_id": meta["match_id"],
            "duration": meta["duration"],
            "players": copy.deepcopy(meta["players"]),
            "context": {"channels": channels},
        },
        "raw": {"match_id": meta["match_id"], "test": "无真实训练数据", "post_game_tick": 200},
        "parser": {
            "match_id": meta["match_id"],
            "game_build": 6993,
            "game_start_tick": 100,
            "post_game_tick": 200,
            "post_game_seconds": meta["duration"],
            "parse_error": None,
            "truncated_at_tick": None,
        },
        "headers": {
            "state": {"schema": "gem-state-capture/3", "seconds": 6},
            "extras": {"schema": "gem-extras-capture/1", "seconds": 6},
        },
        "issues": [],
    }


def install_fake(monkeypatch, meta, *, mutate_state=None, after_capture=None, result=None):
    calls = []
    result = capture_result(meta) if result is None else result
    monkeypatch.setattr(processing, "producer_identity", lambda *args: copy.deepcopy(PRODUCER))

    def capture(path, *, emit_state, emit_extras):
        calls.append(path)
        assert path.read_bytes().startswith(b"PBDEMS2\x00")
        for t in range(-1, meta["duration"] + 2):
            state = {"t": t, "heroes": [hero(pid) for pid in range(10)]}
            if mutate_state:
                mutate_state(state)
            emit_state(state)
            emit_extras({"t": t, "creeps": [], "watchers": [], "outposts": [], "scan": {}})
        if after_capture:
            after_capture()
        return copy.deepcopy(result)

    monkeypatch.setattr(processing, "capture_bundle", capture)
    return calls


def test_worker_decodes_once_clips_channels_and_binds_raw_bytes(tmp_path, monkeypatch):
    path, request, meta = request_fixture(tmp_path)
    calls = install_fake(monkeypatch, meta)
    root = tmp_path / "bundle"
    manifest = processing.process_request(path, root, tmp_path / "compat")
    assert len(calls) == 1
    assert manifest["quality"]["status"] == "passed"
    assert manifest["quality"]["parser"]["match_id"] == MID
    assert manifest["quality"]["parser"]["game_build"] == 6993
    assert (
        verify_bundle(root, expected_identity=request["identity"], expected_producer=PRODUCER)
        == manifest
    )
    raw = manifest["artifacts"]["raw"]
    normalized = read_json_artifact(root, "normalized")
    assert normalized["evidence_sha256"] == raw["uncompressed_sha256"]
    assert normalized["evidence_source"] == raw["path"] == "raw-gem.json.gz"
    original_raw = capture_result(meta)["raw"]
    expected_raw = json.dumps(original_raw, ensure_ascii=False, allow_nan=False).encode()
    assert raw["uncompressed_sha256"] == hashlib.sha256(expected_raw).hexdigest()
    assert read_json_artifact(root, "raw") == original_raw
    for role in ("state", "extras"):
        records = list(iter_channel(root, role))
        assert records[0]["match_id"] == MID
        assert records[0]["seconds"] == meta["duration"] + 1
        assert records[0]["window"] == {"start": 0, "end_inclusive": meta["duration"]}
        assert [row["t"] for row in records[1:]] == list(range(meta["duration"] + 1))
        assert manifest["quality"][role]["excluded_rows"] == 2
    assert set(p.name for p in root.iterdir()) == {
        "manifest.json",
        "raw-gem.json.gz",
        "normalized.json.gz",
        "state-v3.jsonl.gz",
        "extras-v1.jsonl.gz",
    }
    assert not list(tmp_path.glob(".replay-spool-*"))
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(FileExistsError, match="already exists"):
        processing.process_request(path, root, tmp_path / "compat")
    assert len(calls) == 1
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


def test_reserved_id_is_rejected_before_source_reads_or_producer_probe(tmp_path, monkeypatch):
    path, request, _meta = request_fixture(tmp_path)
    request["exclusion"]["percent"] = 100
    write_json(path, request)
    for key in ("metadata_path", "snapshot_path", "demo_path"):
        Path(request[key]).unlink()

    def forbidden(*args, **kwargs):
        raise AssertionError("reserved inputs must not be inspected")

    monkeypatch.setattr(processing, "producer_identity", forbidden)
    monkeypatch.setattr(processing, "check_reference", forbidden)
    monkeypatch.setattr(processing, "capture_bundle", forbidden)
    with pytest.raises(ValueError, match="Reserved match"):
        processing.process_request(path, tmp_path / "out", tmp_path / "compat")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("field", ["demo_path", "metadata_path", "snapshot_path"])
def test_source_change_before_worker_never_invokes_capture(tmp_path, monkeypatch, field):
    path, request, meta = request_fixture(tmp_path)
    calls = install_fake(monkeypatch, meta)
    source = Path(request[field])
    source.write_bytes(source.read_bytes() + b" ")
    with pytest.raises(ValueError, match="Source artifact changed"):
        processing.process_request(path, tmp_path / "out", tmp_path / "compat")
    assert calls == []
    assert not (tmp_path / "out").exists()


def test_source_change_during_capture_prevents_bundle_publication(tmp_path, monkeypatch):
    path, request, meta = request_fixture(tmp_path)
    demo = Path(request["demo_path"])
    calls = install_fake(monkeypatch, meta, after_capture=lambda: demo.write_bytes(b"changed"))
    with pytest.raises(ValueError, match="Source artifact changed"):
        processing.process_request(path, tmp_path / "out", tmp_path / "compat")
    assert len(calls) == 1
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("when", ["before", "during"])
def test_producer_change_prevents_acceptance(tmp_path, monkeypatch, when):
    path, _request, meta = request_fixture(tmp_path)
    calls = install_fake(monkeypatch, meta)
    probes = []

    def producer(*args):
        probes.append(True)
        if when == "before" or len(probes) > 1:
            return {**PRODUCER, "changed": True}
        return copy.deepcopy(PRODUCER)

    monkeypatch.setattr(processing, "producer_identity", producer)
    with pytest.raises(ValueError, match="producer|Producer"):
        processing.process_request(path, tmp_path / "out", tmp_path / "compat")
    assert len(calls) == (0 if when == "before" else 1)
    assert not (tmp_path / "out").exists()


def test_missing_core_field_is_review_required_not_passed(tmp_path, monkeypatch):
    path, _request, meta = request_fixture(tmp_path)

    def missing(row):
        if row["t"] == 1:
            row["heroes"][0]["abilities"][0]["cd"] = None

    install_fake(monkeypatch, meta, mutate_state=missing)
    result = processing.process_request(path, tmp_path / "out", tmp_path / "compat")
    assert result["quality"]["status"] == "review_required"
    assert "missing_core_field:ability.cd" in result["quality"]["errors"]
    assert result["quality"]["training_allowed"] is False


def test_parser_identity_cannot_be_manufactured_from_requested_id(tmp_path, monkeypatch):
    path, _request, meta = request_fixture(tmp_path)
    result = capture_result(meta)
    result["parser"]["match_id"] = MID + 1
    calls = install_fake(monkeypatch, meta, result=result)
    try:
        manifest = processing.process_request(path, tmp_path / "out", tmp_path / "compat")
    except ValueError:
        assert len(calls) == 1
        assert not (tmp_path / "out").exists()
    else:
        assert manifest["quality"]["status"] != "passed"
        assert manifest["quality"]["parser"]["match_id"] == MID + 1
        assert "match_identity_mismatch" in manifest["quality"]["errors"]


def test_capture_failure_never_leaves_a_passed_manifest(tmp_path, monkeypatch):
    path, request, meta = request_fixture(tmp_path)
    install_fake(monkeypatch, meta)

    def failed(*args, **kwargs):
        raise ValueError("synthetic decode failure")

    monkeypatch.setattr(processing, "capture_bundle", failed)
    with pytest.raises(ValueError, match="decode failure"):
        processing.process_request(path, tmp_path / "out", tmp_path / "compat")
    assert not (tmp_path / "out").exists()
    assert Path(request["demo_path"]).read_bytes().startswith(b"PBDEMS2\x00")
    assert not list(tmp_path.glob(".replay-spool-*"))


@pytest.mark.parametrize(
    "mutate", ["omit_demo_ref", "substitute_meta_path", "different_discovery_id"]
)
def test_request_inputs_must_be_bound_to_the_requested_identity(tmp_path, monkeypatch, mutate):
    path, request, meta = request_fixture(tmp_path)
    if mutate == "omit_demo_ref":
        request["identity"]["source_references"] = request["identity"]["source_references"][:-1]
    elif mutate == "substitute_meta_path":
        alternative = tmp_path / "alternative.json"
        write_json(alternative, meta)
        request["metadata_path"] = str(alternative)
    else:
        meta["match_id"] = MID + 1
        write_json(Path(request["metadata_path"]), meta)
        request["discovery"]["match_id"] = MID + 1
        request["identity"]["discovery"] = copy.deepcopy(request["discovery"])
        request["identity"]["source_references"] = [
            reference(Path(request[key])) for key in ("snapshot_path", "metadata_path", "demo_path")
        ]
    write_json(path, request)
    calls = install_fake(monkeypatch, meta)
    with pytest.raises(ValueError):
        processing.process_request(path, tmp_path / "out", tmp_path / "compat")
    assert calls == []
    assert not (tmp_path / "out").exists()


def test_generic_exclusion_matches_u133_without_importing_policy_into_worker():
    from dota_items.data.awareness_split import HOLDOUT_PERCENT, SALT, is_holdout

    exclusion = {"algorithm": "sha256-mod100", "salt": SALT, "percent": HOLDOUT_PERCENT}
    for mid in range(MID, MID + 100):
        assert processing.match_allowed(mid, exclusion) is not is_holdout(mid)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"game_build": None}, "missing_observed_build"),
        ({"post_game_tick": None}, "missing_game_end"),
        ({"parse_error": "synthetic truncation"}, "parser_incomplete"),
    ],
)
def test_parser_end_and_build_uncertainty_cannot_be_passed(tmp_path, monkeypatch, changes, reason):
    path, _request, meta = request_fixture(tmp_path)
    result = capture_result(meta)
    result["parser"].update(changes)
    install_fake(monkeypatch, meta, result=result)
    try:
        manifest = processing.process_request(path, tmp_path / "out", tmp_path / "compat")
    except ValueError:
        assert not (tmp_path / "out").exists()
    else:
        assert manifest["quality"]["status"] == "review_required"
        assert reason in manifest["quality"]["errors"]


@pytest.mark.parametrize("field", ["hp", "pos", "ability_cd", "item_cd", "ability_name"])
def test_wrong_core_value_types_never_pass_quality(tmp_path, monkeypatch, field):
    path, _request, meta = request_fixture(tmp_path)

    def invalid(row):
        if row["t"] != 1:
            return
        unit = row["heroes"][0]
        if field == "hp":
            unit["hp"] = "unknown"
        elif field == "pos":
            unit["pos"] = ["wrong", 1]
        elif field == "ability_cd":
            unit["abilities"][0]["cd"] = "ready"
        elif field == "item_cd":
            unit["items"]["0"]["cd"] = True
        else:
            unit["abilities"][0]["name"] = ""

    install_fake(monkeypatch, meta, mutate_state=invalid)
    result = processing.process_request(path, tmp_path / "out", tmp_path / "compat")
    assert result["quality"]["status"] == "review_required"
    assert any(error.startswith("invalid_core_field:") for error in result["quality"]["errors"])
