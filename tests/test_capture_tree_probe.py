"""A tree probe reuses one registered replay without widening source permissions."""

import json
import sys
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_capture_map_runtime import runtime_fixture, write

from dota_items.data import map_tree_probe_io as probe_io
from dota_items.data.patch_asset_evidence import EvidencePins, capture_producer_files
from dota_items.storage import file_hash
from scripts import capture_map_runtime as runtime_cli
from scripts import capture_tree_probe as cli

ROOT = Path(__file__).resolve().parents[1]


def fixture(tmp_path, monkeypatch, *, demo_digest=None):
    """Synthetic identity/receipt chain; no real replay or holdout data is opened."""
    runtime_path, runtime_spec, compat = runtime_fixture(tmp_path, monkeypatch)
    archive = tmp_path / "123.dem"
    archive.write_bytes(b"PBDEMS2\x00synthetic tree probe")
    actual_demo_digest = file_hash(archive)
    manifest = json.loads(Path(runtime_spec["replay"]["path"]).read_text())
    for ref in manifest["identity"]["source_references"]:
        if ref["path"] == str(archive):
            ref.update(sha256=actual_demo_digest, size_bytes=archive.stat().st_size)
    runtime_spec["replay"] = write(Path(runtime_spec["replay"]["path"]), manifest)
    landmark_receipt = json.loads(Path(runtime_spec["landmarks"]["receipt"]["path"]).read_text())
    landmark_receipt.update(
        manifest=runtime_spec["replay"], demo_sha256=demo_digest or actual_demo_digest
    )
    landmark_receipt["used_files"][str(archive)] = actual_demo_digest
    runtime_spec["landmarks"]["receipt"] = write(
        Path(runtime_spec["landmarks"]["receipt"]["path"]), landmark_receipt
    )
    runtime_spec["capture_kind"] = "visibility"
    write(runtime_path, runtime_spec)
    pins = EvidencePins()
    _, source, landmark, _, _, _, dependencies = runtime_cli.prepare(runtime_path, pins)
    repository = tmp_path / "repository"
    for name in capture_producer_files("visibility"):
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            (ROOT / name).read_text()
            if name == "scripts/capture_map_runtime.py"
            else "# synthetic fixed producer\n"
        )
        pins.track(path)
    anchor_dir = repository / "anchors/123"
    anchor = write(
        anchor_dir / "capture.json",
        {**landmark, "schema": "map-visibility-capture/1", "omniscient": True},
    )
    old = {
        "schema": "map-visibility-capture-receipt/1",
        "match_id": source.match_id,
        "patch": source.patch,
        "game_build": source.build,
        "manifest": runtime_spec["replay"],
        "landmarks": runtime_spec["landmarks"],
        "spec": pins.track(runtime_path),
        "used_files": pins.inventory,
        "dependencies": dependencies,
        "demo_sha256": demo_digest or actual_demo_digest,
        "output_sha256": {"capture.json": anchor["sha256"]},
        "training_allowed": False,
        "action_review_allowed": False,
    }
    old_ref = write(anchor_dir / "receipt.json", old)
    monkeypatch.setattr(
        probe_io,
        "REGISTERED_ANCHORS",
        {123: {"directory": "anchors/123", "sha256": old_ref["sha256"]}},
    )
    spec = {
        "schema": "map-tree-probe-spec/1",
        "exact_patch": "7.42",
        "anchor": {"capture": anchor, "receipt": old_ref},
    }
    spec_ref = write(tmp_path / "tree-spec.json", spec)
    for name in probe_io.tree_probe_producer_files():
        path = repository / name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# synthetic fixed probe producer\n")
        pins.track(path)
    for ref in (anchor, old_ref, spec_ref):
        pins.add(ref)
    doc = {
        "schema": "map-tree-probe/1",
        "match_id": 123,
        "game_build": 6993,
        "post_game_tick": 300,
        "parse_error": None,
        "truncated_at_tick": None,
        "coordinate_space": "world",
        "patch": "7.42",
        "omniscient": True,
        "training_allowed": False,
        "action_review_allowed": False,
        "packets": [],
        "tree_word_changes": [],
        "raw_tree_cut_events": [],
        "entity_changes": [],
        "entity_events": [],
        "class_schemas": {},
        "sampling": {},
    }
    capture_ref = write(tmp_path / "probe/capture.json", doc)
    receipt = {
        "schema": "map-tree-probe-receipt/1",
        "spec": spec_ref,
        "anchor": spec["anchor"],
        "manifest": old["manifest"],
        "match_id": 123,
        "patch": "7.42",
        "game_build": 6993,
        "demo_sha256": old["demo_sha256"],
        "dependencies": dependencies,
        "used_files": pins.inventory,
        "output_sha256": {"capture.json": capture_ref["sha256"]},
        "training_allowed": False,
        "action_review_allowed": False,
    }
    receipt_ref = write(tmp_path / "probe/receipt.json", receipt)
    return SimpleNamespace(
        spec=spec,
        spec_ref=spec_ref,
        anchor=anchor,
        old=old,
        old_ref=old_ref,
        capture=doc,
        capture_ref=capture_ref,
        receipt=receipt,
        receipt_ref=receipt_ref,
        root=repository,
        compat=compat,
        archive=archive,
    )


def consume(case, *, allowed=True):
    pins = EvidencePins()
    result = probe_io.read_tree_probe(
        case.capture_ref,
        case.receipt_ref,
        pins=pins,
        repository_root=case.root,
        match_allowed=lambda mid: allowed and mid == 123,
    )
    pins.verify()
    return result


def rewrite_receipt(case):
    case.receipt_ref = write(Path(case.receipt_ref["path"]), case.receipt)


def rewrite_capture(case):
    case.capture_ref = write(Path(case.capture_ref["path"]), case.capture)
    case.receipt["output_sha256"] = {"capture.json": case.capture_ref["sha256"]}
    rewrite_receipt(case)


def forbid_probe_payload(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Probe payload opened before the preceding source gate rejected it")

    monkeypatch.setattr(probe_io, "read_source_bytes", forbidden)


def test_registered_anchor_and_complete_probe_receipt_are_readable(tmp_path, monkeypatch):
    case = fixture(tmp_path, monkeypatch)
    assert consume(case) == case.capture


@pytest.mark.parametrize("scope", ["excluded", "claimed_match", "boolean_match"])
def test_identity_and_holdout_gate_precede_any_large_capture_body(tmp_path, monkeypatch, scope):
    case = fixture(tmp_path, monkeypatch)
    forbid_probe_payload(monkeypatch)
    if scope != "excluded":
        case.receipt["match_id"] = 999 if scope == "claimed_match" else True
        rewrite_receipt(case)
    original = EvidencePins.read
    forbidden = {case.anchor["path"], case.capture_ref["path"]}

    def guarded(self, ref):
        if ref["path"] in forbidden:
            pytest.fail("A large capture body was read before identity/exclusion rejection")
        return original(self, ref)

    monkeypatch.setattr(EvidencePins, "read", guarded)
    with pytest.raises(ValueError, match="excluded|identity"):
        consume(case, allowed=scope != "excluded")


@pytest.mark.parametrize(
    "change", ["receipt_digest", "receipt_path", "capture_path", "capture_digest"]
)
def test_anchor_registration_rejects_rebound_sources_before_opening_body(
    tmp_path, monkeypatch, change
):
    case = fixture(tmp_path, monkeypatch)
    spec = deepcopy(case.spec)
    ref = spec["anchor"]["receipt" if change.startswith("receipt") else "capture"]
    if change.endswith("path"):
        ref["path"] = str(tmp_path / "unapproved-private-body.json")
    else:
        ref["sha256"] = "f" * 64
    original = EvidencePins.read

    def guarded(self, current):
        if current["path"] != case.old_ref["path"]:
            pytest.fail("An unregistered body or receipt was opened")
        return original(self, current)

    monkeypatch.setattr(EvidencePins, "read", guarded)
    with pytest.raises(ValueError, match="Unregistered|binding"):
        probe_io.open_tree_anchor(
            spec, pins=EvidencePins(), repository_root=case.root, match_allowed=lambda _: True
        )


@pytest.mark.parametrize("change", ["extra", "producer", "anchor", "archive", "digest"])
def test_exact_inventory_rejects_extra_or_missing_sources_before_probe_body(
    tmp_path, monkeypatch, change
):
    case = fixture(tmp_path, monkeypatch)
    forbid_probe_payload(monkeypatch)
    if change == "extra":
        case.receipt["used_files"][str(tmp_path / "must-not-read.json")] = "f" * 64
    elif change == "producer":
        case.receipt["used_files"].pop(str(case.root / "src/dota_items/sources/map_tree_probe.py"))
    elif change == "anchor":
        case.receipt["used_files"].pop(case.anchor["path"])
    elif change == "archive":
        case.receipt["used_files"].pop(str(case.archive))
    else:
        case.receipt["used_files"][str(case.archive)] = "f" * 64
    rewrite_receipt(case)
    original = EvidencePins.read

    def guarded(self, ref):
        if ref["path"] == case.capture_ref["path"]:
            pytest.fail("Probe body opened before rejecting mismatched source inventory")
        return original(self, ref)

    monkeypatch.setattr(EvidencePins, "read", guarded)
    with pytest.raises(ValueError, match="exact closure"):
        consume(case)


@pytest.mark.parametrize(
    "change", ["game_build", "float_build", "patch", "demo", "dependencies", "purpose", "output"]
)
def test_receipt_mismatches_fail_before_probe_payload(tmp_path, monkeypatch, change):
    case = fixture(tmp_path, monkeypatch)
    forbid_probe_payload(monkeypatch)
    if change == "game_build":
        case.receipt["game_build"] += 1
    elif change == "float_build":
        case.receipt["game_build"] = 6993.0
    elif change == "patch":
        case.receipt["patch"] = "7.42a"
    elif change == "demo":
        case.receipt["demo_sha256"] = "f" * 64
    elif change == "dependencies":
        case.receipt["dependencies"] = {}
    elif change == "purpose":
        case.receipt["action_review_allowed"] = True
    else:
        case.receipt["output_sha256"] = {}
    rewrite_receipt(case)
    original = EvidencePins.read

    def guarded(self, ref):
        if ref["path"] == case.capture_ref["path"]:
            pytest.fail("Probe payload opened before receipt mismatch was rejected")
        return original(self, ref)

    monkeypatch.setattr(EvidencePins, "read", guarded)
    with pytest.raises(ValueError):
        consume(case)


@pytest.mark.parametrize(
    "change",
    [
        "match",
        "float_build",
        "float_end",
        "end",
        "parse",
        "missing_parse",
        "truncated",
        "coordinates",
        "patch",
        "omniscient",
        "training",
        "action_review",
    ],
)
def test_probe_header_requires_complete_strict_identity_and_closed_purpose(
    tmp_path, monkeypatch, change
):
    case = fixture(tmp_path, monkeypatch)
    if change == "match":
        case.capture["match_id"] = 124
    elif change == "float_build":
        case.capture["game_build"] = 6993.0
    elif change == "float_end":
        case.capture["post_game_tick"] = 300.0
    elif change == "end":
        case.capture["post_game_tick"] = 299
    elif change == "parse":
        case.capture["parse_error"] = "incomplete"
    elif change == "missing_parse":
        del case.capture["parse_error"]
    elif change == "truncated":
        case.capture["truncated_at_tick"] = 250
    elif change == "coordinates":
        case.capture["coordinate_space"] = "cell"
    elif change == "patch":
        case.capture["patch"] = "7.42a"
    elif change == "omniscient":
        case.capture["omniscient"] = 1
    elif change == "training":
        case.capture["training_allowed"] = True
    else:
        case.capture["action_review_allowed"] = True
    rewrite_capture(case)
    with pytest.raises(ValueError):
        consume(case)


def test_added_compatibility_resource_cannot_be_accepted_under_old_anchor(tmp_path, monkeypatch):
    case = fixture(tmp_path, monkeypatch)
    write(case.compat / "gem/new-resource.json", {})
    with pytest.raises(ValueError, match="inventory changed"):
        consume(case)


def test_archive_drift_prevents_reuse_of_registered_anchor(tmp_path, monkeypatch):
    case = fixture(tmp_path, monkeypatch)
    case.archive.write_bytes(b"different raw replay")
    with pytest.raises(ValueError):
        consume(case)


def test_probe_payload_uses_explicit_bound_and_fails_closed_on_oversize(tmp_path, monkeypatch):
    case = fixture(tmp_path, monkeypatch)
    assert probe_io.MAX_PROBE_BYTES == 256 * 1024 * 1024
    size = Path(case.capture_ref["path"]).stat().st_size
    monkeypatch.setattr(probe_io, "MAX_PROBE_BYTES", size - 1)
    with pytest.raises(ValueError, match="256 MiB limit"):
        consume(case)
    monkeypatch.setattr(probe_io, "MAX_PROBE_BYTES", size)
    assert consume(case) == case.capture


def test_probe_payload_bytes_digest_is_checked_before_strict_json_decode(tmp_path, monkeypatch):
    case = fixture(tmp_path, monkeypatch)
    Path(case.capture_ref["path"]).write_bytes(b"corrupt-json-and-wrong-digest")
    with pytest.raises(ValueError, match="payload digest mismatch"):
        consume(case)


@pytest.mark.parametrize("payload", [b'{"duplicate":1,"duplicate":2}', b'{"bad":1e999}'])
def test_larger_bounded_reader_preserves_strict_json_validation(tmp_path, monkeypatch, payload):
    case = fixture(tmp_path, monkeypatch)
    path = Path(case.capture_ref["path"])
    path.write_bytes(payload)
    case.capture_ref["sha256"] = file_hash(path)
    case.receipt["output_sha256"] = {"capture.json": case.capture_ref["sha256"]}
    rewrite_receipt(case)
    with pytest.raises(ValueError, match="Duplicate|Non-finite"):
        consume(case)


@contextmanager
def fake_capture(monkeypatch, case, capture):
    monkeypatch.setattr(cli, "ROOT", case.root)
    monkeypatch.setattr(cli, "is_holdout", lambda _: False)
    monkeypatch.setattr("dota_items.data.awareness_split.is_holdout", lambda _: False)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setitem(
        sys.modules, "dota_items.sources.map_tree_probe", SimpleNamespace(capture=capture)
    )
    # Other tests may have imported the optional parser. This fixture simulates
    # the CLI's required fresh process, then restores that exact module cache.
    prior = {
        name: module
        for name, module in sys.modules.items()
        if name == "gem" or name.startswith("gem.")
    }
    for name in prior:
        sys.modules.pop(name)
    try:
        yield
    finally:
        for name in list(sys.modules):
            if name == "gem" or name.startswith("gem."):
                sys.modules.pop(name)
        sys.modules.update(prior)


def test_cli_publishes_complete_probe_from_same_pinned_raw_dem(tmp_path, monkeypatch):
    case = fixture(tmp_path, monkeypatch)
    calls = []
    previously_imported = object()
    monkeypatch.setitem(sys.modules, "gem.test_existing_import", previously_imported)

    def capture(path, **identity):
        assert path == case.archive
        assert identity == {"expected_match_id": 123, "expected_game_build": 6993}
        calls.append(path)
        return deepcopy(case.capture)

    output = tmp_path / "published"
    with fake_capture(monkeypatch, case, capture):
        result = cli.run(Path(case.spec_ref["path"]), output)
    assert sys.modules["gem.test_existing_import"] is previously_imported
    assert len(calls) == 1 and result["match_id"] == 123
    assert {path.name for path in output.iterdir()} == {"capture.json", "receipt.json"}
    receipt = json.loads((output / "receipt.json").read_text())
    assert receipt["demo_sha256"] == file_hash(case.archive)
    assert receipt["output_sha256"] == {"capture.json": file_hash(output / "capture.json")}
    assert all(file_hash(Path(name)) == digest for name, digest in receipt["used_files"].items())


def test_cli_rejects_decompressed_hash_mismatch_before_calling_collector(tmp_path, monkeypatch):
    case = fixture(tmp_path, monkeypatch, demo_digest="f" * 64)
    output = tmp_path / "not-published"

    def capture(*_args, **_kwargs):
        pytest.fail("Collector ran before raw demo SHA agreement")

    with (
        fake_capture(monkeypatch, case, capture),
        pytest.raises(ValueError, match="replay mismatch"),
    ):
        cli.run(Path(case.spec_ref["path"]), output)
    assert not output.exists()


def test_cli_does_not_publish_probe_exceeding_reader_bound(tmp_path, monkeypatch):
    case = fixture(tmp_path, monkeypatch)
    output = tmp_path / "not-published"
    monkeypatch.setattr(cli, "MAX_PROBE_BYTES", 1)
    with (
        fake_capture(monkeypatch, case, lambda *_args, **_kwargs: deepcopy(case.capture)),
        pytest.raises(ValueError, match="256 MiB limit"),
    ):
        cli.run(Path(case.spec_ref["path"]), output)
    assert not output.exists()


def test_capture_stream_limit_counts_utf8_bytes_and_final_newline(tmp_path, monkeypatch):
    payload = {"label": "树", "evidence": [None, True, 1.25]}
    expected = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    output = tmp_path / "capture.json"
    monkeypatch.setattr(cli, "MAX_PROBE_BYTES", len(expected))
    cli._write_bounded_capture(output, payload)
    assert output.read_bytes() == expected
    monkeypatch.setattr(cli, "MAX_PROBE_BYTES", len(expected) - 1)
    with pytest.raises(ValueError, match="256 MiB limit"):
        cli._write_bounded_capture(output, payload)
    assert output.read_bytes() == expected[:-1]
    monkeypatch.setattr(cli, "MAX_PROBE_BYTES", len(expected.decode()))
    with pytest.raises(ValueError, match="256 MiB limit"):
        cli._write_bounded_capture(output, payload)
    assert output.stat().st_size <= cli.MAX_PROBE_BYTES


def test_capture_writer_stops_iterating_immediately_at_size_bound(tmp_path, monkeypatch):
    def pieces(_self, _payload):
        yield "["
        yield '"树"'
        pytest.fail("Encoder continued beyond the payload limit")

    monkeypatch.setattr(cli.json.JSONEncoder, "iterencode", pieces)
    monkeypatch.setattr(cli, "MAX_PROBE_BYTES", 2)
    output = tmp_path / "capture.json"
    with pytest.raises(ValueError, match="256 MiB limit"):
        cli._write_bounded_capture(output, {})
    assert output.read_bytes() == b"["


def test_non_ascii_stream_overflow_does_not_publish_partial_probe(tmp_path, monkeypatch):
    case = fixture(tmp_path, monkeypatch)
    payload = {**case.capture, "label": "临时树"}
    # A character-count limit would pass; the correct UTF-8 byte limit must reject.
    monkeypatch.setattr(
        cli,
        "MAX_PROBE_BYTES",
        len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"),
    )
    output = tmp_path / "not-published"
    with (
        fake_capture(monkeypatch, case, lambda *_args, **_kwargs: deepcopy(payload)),
        pytest.raises(ValueError, match="256 MiB limit"),
    ):
        cli.run(Path(case.spec_ref["path"]), output)
    assert not output.exists()
    assert not list(tmp_path.glob(".tree-probe-*"))


@pytest.mark.parametrize(
    "change", ["raw_dem", "private_parser", "producer", "resource", "identity"]
)
def test_cli_failure_does_not_publish_partial_or_drifted_probe(tmp_path, monkeypatch, change):
    case = fixture(tmp_path, monkeypatch)
    output = tmp_path / "not-published"

    def capture(path, **_identity):
        result = deepcopy(case.capture)
        if change == "raw_dem":
            path.write_bytes(path.read_bytes() + b"changed")
        elif change == "private_parser":
            Path(sys.modules["gem"].__file__).write_text("# changed")
        elif change == "producer":
            (case.root / "src/dota_items/sources/map_tree_probe.py").write_text("# changed")
        elif change == "resource":
            write(case.compat / "gem/late.json", {})
        else:
            result["game_build"] = float(result["game_build"])
        return result

    with fake_capture(monkeypatch, case, capture), pytest.raises(ValueError):
        cli.run(Path(case.spec_ref["path"]), output)
    assert not output.exists()


def test_cli_no_overwrite_and_fresh_process_gates_precede_source_reads(tmp_path, monkeypatch):
    output = tmp_path / "exists"
    output.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        cli.run(tmp_path / "missing.json", output)
    monkeypatch.setitem(sys.modules, "gem.fake_previous_import", object())
    with pytest.raises(ValueError, match="Fresh process"):
        cli.run(tmp_path / "missing.json", tmp_path / "new")
