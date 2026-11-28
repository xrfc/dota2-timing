"""Length loss, migration equivalence and unknown-safe viewer projections."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_capture_tree_probe import fixture, write

from dota_items.data import viewer_wire_io as io
from dota_items.data.map_capture_environment import prepare_capture_environment
from dota_items.data.patch_asset_evidence import EvidencePins
from dota_items.data.viewer_membership import FIELDS, ViewerVector, project_membership
from dota_items.sources.viewer_wire_capture import VECTOR, VIEWER_CLASS, observe_vector_writes
from scripts.capture_map_runtime import prepare


def test_preparation_extraction_is_equivalent_and_policy_is_injected(tmp_path, monkeypatch):
    case = fixture(tmp_path, monkeypatch)
    spec = Path(case.old["spec"]["path"])
    a, b = EvidencePins(), EvidencePins()
    legacy = prepare(spec, a)
    current = prepare_capture_environment(spec, b, match_allowed=lambda mid: mid == 123)
    assert legacy[0] == current[0]
    assert legacy[1].receipt() == current[1].receipt()
    assert legacy[2:] == current[2:]
    assert a.inventory == b.inventory
    with pytest.raises(ValueError, match="excluded"):
        prepare_capture_environment(spec, EvidencePins(), match_allowed=lambda _: False)


def test_hook_retains_length_writes_and_restores_on_exception():
    class State:
        def __init__(self):
            self.values = {}

        def _set_compact(self, path, value):
            # Simulate the frozen parser retaining a child in place of later length.
            if path == (0,) and any(len(p) > 1 for p in self.values):
                return
            self.values[path] = value

    def read(reader, serializer, state):
        for path, value in reader:
            state._set_compact(path, value)

    child = SimpleNamespace(fields=[SimpleNamespace(var_name="m_bValid")])
    schema = SimpleNamespace(
        name=VIEWER_CLASS, fields=[SimpleNamespace(var_name=VECTOR, serializer=child)]
    )
    entities = SimpleNamespace(read_fields=read)
    original = State._set_compact
    observed = []
    state = State()
    with pytest.raises(RuntimeError):
        with observe_vector_writes(entities, State, lambda *args: observed.append(args[1:])):
            entities.read_fields([((0,), 1), ((0, 0, 0), True), ((0,), 0)], schema, state)
            raise RuntimeError("parse fails")
    assert [r[-1] for r in observed] == [1, True, 0]
    assert state.values[(0,)] == 1
    assert observed[1][1] == [VECTOR, 0, "m_bValid"]
    assert entities.read_fields is read and State._set_compact is original


def test_shrink_regrow_does_not_resurrect_stale_members():
    v = ViewerVector()
    v.apply([VECTOR], 2)
    for index in range(2):
        for name in FIELDS:
            v.apply([VECTOR, index, name], True if name.startswith("m_b") else 4)
    assert (
        sum(r["protocol_active_candidate"] for r in v.snapshot(active=True, team=2)["members"]) == 2
    )
    v.apply([VECTOR], 0)
    assert v.snapshot(active=True, team=2)["members"] == []
    v.apply([VECTOR], 2)
    assert all(
        r["raw"] == {} and not r["protocol_active_candidate"]
        for r in v.snapshot(active=True, team=2)["members"]
    )
    assert v.shrinks == 1


@pytest.mark.parametrize("length", [None, True, -1, 4097, 1.5, "1"])
def test_invalid_lengths_are_not_capacity(length):
    with pytest.raises(ValueError):
        ViewerVector().apply([VECTOR], length)


def example_capture():
    writes = [{"write_sequence": 1, "path": [0], "names": [VECTOR], "value": 1}]
    for number, field in enumerate(FIELDS, 2):
        writes.append(
            {
                "write_sequence": number,
                "path": [0, 0, number - 2],
                "names": [VECTOR, 0, field],
                "value": True if field.startswith("m_b") else 3,
            }
        )
    row = dict(
        packet_ordinal=1,
        tick=0,
        game_time=-1.0,
        entity_index=1,
        entity_serial=2,
        team_raw=2,
        version_raw=1,
        active_raw=True,
        created=True,
        entered=True,
        left=False,
        deleted=False,
        writes=writes,
    )
    return dict(
        schema="viewer-wire-capture/1",
        omniscient=True,
        training_allowed=False,
        action_review_allowed=False,
        events=[row],
        writes=len(writes),
        terminal_packet_ordinal=2,
        post_game_tick=10,
    )


def test_packet_projection_filters_invalid_and_departed_slots():
    capture = example_capture()
    row = deepcopy(capture["events"][0])
    row.update(
        packet_ordinal=2, tick=10, game_time=0, created=False, entered=False, left=True, writes=[]
    )
    capture["events"].append(row)
    result = project_membership(capture)
    assert result["member_states"][result["frames"][0]["member_state_ids"][0]][
        "protocol_active_candidate"
    ]
    assert not result["member_states"][result["frames"][1]["member_state_ids"][0]][
        "protocol_active_candidate"
    ]
    assert not result["effective_vision_certified"]


@pytest.mark.parametrize(
    "mutation", ["sequence", "order", "future", "clock", "creation", "training"]
)
def test_invalid_wire_sequences_fail_closed(mutation):
    d = example_capture()
    if mutation == "sequence":
        d["events"][0]["writes"][0]["write_sequence"] = 2
    if mutation == "order":
        d["events"][0]["packet_ordinal"] = 0
    if mutation == "future":
        d["events"][0]["tick"] = 11
    if mutation == "clock":
        d["events"][0]["game_time"] = float("nan")
    if mutation == "creation":
        d["events"][0]["created"] = False
    if mutation == "training":
        d["training_allowed"] = True
    with pytest.raises(ValueError):
        project_membership(d)


def viewer_fixture(tmp_path, monkeypatch):
    case = fixture(tmp_path, monkeypatch)
    case.spec["schema"] = "viewer-wire-spec/1"
    case.spec_ref = write(Path(case.spec_ref["path"]), case.spec)
    expected = {**case.old["used_files"], case.spec_ref["path"]: case.spec_ref["sha256"]}
    for ref in case.spec["anchor"].values():
        expected[ref["path"]] = ref["sha256"]
    pins = EvidencePins()
    for name in io.viewer_producer_files():
        p = case.root / name
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# new producer\n")
        ref = pins.track(p)
        expected[ref["path"]] = ref["sha256"]
    case.capture.update(
        schema="viewer-wire-capture/1",
        coordinate_space="raw_uninterpreted",
        terminal_packet_ordinal=2,
    )
    case.capture_ref = write(Path(case.capture_ref["path"]), case.capture)
    case.receipt.update(
        schema="viewer-wire-receipt/1",
        migration=io.MIGRATION,
        spec=case.spec_ref,
        used_files=expected,
        output_sha256={"capture.json": case.capture_ref["sha256"]},
    )
    case.receipt_ref = write(Path(case.receipt_ref["path"]), case.receipt)
    return case


def consume(case, allowed=True):
    return io.read_viewer_capture(
        case.capture_ref,
        case.receipt_ref,
        pins=EvidencePins(),
        repository_root=case.root,
        match_allowed=lambda mid: allowed,
    )


def test_reader_closes_new_producer_and_registered_migration(tmp_path, monkeypatch):
    case = viewer_fixture(tmp_path, monkeypatch)
    assert consume(case) == case.capture


@pytest.mark.parametrize("mutation", ["missing", "extra", "migration", "claimed", "excluded"])
def test_receipt_rejection_precedes_payload(tmp_path, monkeypatch, mutation):
    case = viewer_fixture(tmp_path, monkeypatch)
    if mutation == "missing":
        case.receipt["used_files"].pop(
            str(case.root / "src/dota_items/data/map_capture_environment.py")
        )
    if mutation == "extra":
        case.receipt["used_files"]["/unapproved"] = "f" * 64
    if mutation == "migration":
        case.receipt["migration"] = {**io.MIGRATION, "mode": "ignore-hashes"}
    if mutation == "claimed":
        case.receipt["match_id"] = 999
    case.receipt_ref = write(Path(case.receipt_ref["path"]), case.receipt)
    monkeypatch.setattr(io, "read_source_bytes", lambda *a, **k: pytest.fail("body read too early"))
    with pytest.raises(ValueError):
        consume(case, mutation != "excluded")


def test_team_and_version_only_changes_are_not_dropped():
    from enum import IntFlag

    from dota_items.sources.viewer_wire_capture import ViewerWireCollector

    class Op(IntFlag):
        CREATED = 1
        ENTERED = 2
        LEFT = 4
        DELETED = 8
        UPDATED = 16

        def has(self, flag):
            return bool(self & flag)

    parser = SimpleNamespace(post_game_tick=None, tick=1)
    fields = {"m_iTeamNum": 2, "m_FoWTempViewerVersion": 1}
    e = SimpleNamespace(
        active=True,
        _field_state=object(),
        get=fields.get,
        get_class_name=lambda: VIEWER_CLASS,
        get_index=lambda: 5,
        get_serial=lambda: 7,
    )
    c = ViewerWireCollector(parser, Op)
    c.schema = {"already": "observed"}
    c.on_entity(e, Op.CREATED)
    c.on_entity(e, Op.UPDATED)
    fields["m_iTeamNum"] = 3
    c.on_entity(e, Op.UPDATED)
    fields["m_FoWTempViewerVersion"] = 2
    c.on_entity(e, Op.UPDATED)
    assert len(c.rows) == 3
    assert [r["team_raw"] for r in c.rows] == [2, 3, 3]
    assert c.rows[-1]["version_raw"] == 2


def test_orchestrator_publishes_using_service_not_dynamic_cli(tmp_path, monkeypatch):
    import sys

    from dota_items.experiments.awareness import viewer_capture as runner

    case = viewer_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "ROOT", case.root)
    monkeypatch.setattr(runner, "is_holdout", lambda _: False)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setitem(
        sys.modules,
        "dota_items.sources.viewer_wire_capture",
        SimpleNamespace(capture=lambda *a, **kw: deepcopy(case.capture)),
    )
    prior = {n: m for n, m in sys.modules.items() if n == "gem" or n.startswith("gem.")}
    for n in prior:
        sys.modules.pop(n)
    try:
        output = tmp_path / "published"
        assert runner.run(Path(case.spec_ref["path"]), output)["match_id"] == 123
        import json

        r = json.loads((output / "receipt.json").read_text())
        assert r["migration"] == io.MIGRATION
        assert "importlib" not in Path(runner.__file__).read_text()
        with pytest.raises(ValueError, match="already exists"):
            runner.run(Path(case.spec_ref["path"]), output)
    finally:
        for n in list(sys.modules):
            if n == "gem" or n.startswith("gem."):
                sys.modules.pop(n)
        sys.modules.update(prior)


def test_reader_rejects_wrong_digest_and_bounded_body(tmp_path, monkeypatch):
    from dota_items.data.source_io import AuditInputError

    case = viewer_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(io, "MAX_PROBE_BYTES", 1)
    with pytest.raises(AuditInputError):
        consume(case)
    monkeypatch.setattr(io, "MAX_PROBE_BYTES", 256 * 1024 * 1024)
    Path(case.capture_ref["path"]).write_text("corrupted")
    with pytest.raises(ValueError, match="digest"):
        consume(case)
