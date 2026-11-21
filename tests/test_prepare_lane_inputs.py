import bz2
import gzip
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def prep(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import prepare_lane_inputs

    return prepare_lane_inputs


def metadata(root, mid, patch=60):
    folder = root / "meta"
    folder.mkdir(exist_ok=True)
    (folder / f"{mid}.json").write_text(json.dumps({"match_id": mid, "patch": patch}))


def archive(root, mid):
    folder = root / "demos"
    folder.mkdir(exist_ok=True)
    source = folder / f"{mid}.dem.bz2"
    source.write_bytes(bz2.compress(b"PBDEMS2\x00fixture"))
    return source


def records(mid, kind):
    if kind == "parsed":
        return [
            {
                "match_id": mid,
                "duration": 1000,
                "context": {
                    "channels": {"hero_visibility_events": [], "combat_log": [], "wards": []}
                },
            }
        ]
    schema = {"state-v3": "gem-state-capture/3", "extras-v1": "gem-extras-capture/1"}[kind]
    data = {"heroes": [], "world": {}} if kind == "state-v3" else {"creeps": [], "watchers": []}
    return [{"schema": schema, "match_id": mid, "seconds": 1}, {"t": 0, **data}]


def write_artifact(prep, root, mid, kind, rows=None):
    path = prep._target(root, mid, kind)
    path.parent.mkdir(exist_ok=True, parents=True)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in records(mid, kind) if rows is None else rows:
            stream.write(json.dumps(row) + "\n")
    return path


def test_complete_legacy_inputs_need_no_demo_or_gem(prep, tmp_path, monkeypatch):
    mid = prep.MATCHES[0]
    metadata(tmp_path, mid)
    for kind in prep.KINDS:
        write_artifact(prep, tmp_path, mid, kind)
    monkeypatch.setattr(prep, "build", lambda _: pytest.fail("unexpected Gem build"))
    assert prep.prepare_inputs(tmp_path, [mid, mid]) == {
        str(mid): {"reused": list(prep.KINDS), "created": []}
    }


def test_wrong_inputs_are_preserved_and_rejected_before_any_work(prep, tmp_path, monkeypatch):
    monkeypatch.setattr(prep, "build", lambda _: pytest.fail("unexpected Gem build"))
    mid = prep.MATCHES[0]
    with pytest.raises(ValueError, match="outside"):
        prep.prepare_inputs(tmp_path, [1])
    metadata(tmp_path, mid, 61)
    with pytest.raises(ValueError, match="patch"):
        prep.prepare_inputs(tmp_path, [mid])
    metadata(tmp_path, mid)
    with pytest.raises(FileNotFoundError, match="missing compressed replay"):
        prep.prepare_inputs(tmp_path, [mid])
    rows = records(mid + 1, "extras-v1")
    path = write_artifact(prep, tmp_path, mid, "extras-v1", rows)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="header"):
        prep.prepare_inputs(tmp_path, [mid])
    assert path.read_bytes() == before
    path = write_artifact(prep, tmp_path, mid, "extras-v1", records(mid, "extras-v1")[:1])
    with pytest.raises(ValueError, match="incomplete"):
        prep.prepare_inputs(tmp_path, [mid])


def test_failed_step_is_retried_without_replacing_published_inputs(prep, tmp_path, monkeypatch):
    import extract_creeps
    import extract_state_v3

    from dota_items.sources import gem_replay

    mid = prep.MATCHES[0]
    metadata(tmp_path, mid)
    raw = archive(tmp_path, mid)
    original = raw.read_bytes()
    builds = []
    calls = []

    def build(path):
        path.mkdir()
        builds.append(path)

    def ingest(demo, cache):
        assert demo.read_bytes() == original
        cache.mkdir()
        normalized = cache / "normalized.json"
        normalized.write_text(json.dumps(records(mid, "parsed")[0]))
        return {"match_id": mid, "normalized_json": str(normalized)}

    def run(cmd, env, **kwargs):
        stage = Path(cmd[cmd.index("--worker") + 1])
        kinds = cmd[cmd.index("--kinds") + 1 :]
        calls.append(kinds)
        assert Path(env["PYTHONPATH"].split(os.pathsep)[0]) == builds[-1]
        try:
            created = prep._derive(tmp_path, stage, mid, kinds)
        except ValueError as error:
            return SimpleNamespace(returncode=1, stderr=str(error))
        return SimpleNamespace(returncode=0, stdout=json.dumps(created))

    monkeypatch.setattr(prep, "build", build)
    monkeypatch.setattr(prep.subprocess, "run", run)
    monkeypatch.setattr(gem_replay, "ingest_demo", ingest)
    monkeypatch.setattr(
        extract_state_v3, "extract", lambda root, mid: write_artifact(prep, root, mid, "state-v3")
    )
    monkeypatch.setattr(
        extract_creeps,
        "extract",
        lambda root, mid, kind: write_artifact(
            prep, root, mid, "extras-v1", records(mid + 1, "extras-v1")
        ),
    )
    with pytest.raises(ValueError, match="extras-v1 header"):
        prep.prepare_inputs(tmp_path, [mid])
    parsed = prep._target(tmp_path, mid, "parsed")
    first = parsed.stat()
    assert not prep._target(tmp_path, mid, "extras-v1").exists()
    monkeypatch.setattr(
        extract_creeps,
        "extract",
        lambda root, mid, kind: write_artifact(prep, root, mid, "extras-v1"),
    )
    assert prep.prepare_inputs(tmp_path, [mid])[str(mid)] == {
        "reused": ["parsed", "state-v3"],
        "created": ["extras-v1"],
    }
    assert (parsed.stat().st_ino, parsed.stat().st_mtime_ns) == (first.st_ino, first.st_mtime_ns)
    assert calls == [list(prep.KINDS), ["extras-v1"]]
    assert raw.read_bytes() == original and not list(tmp_path.glob(".prepare-lane-*"))


def test_extraction_refuses_filename_mismatched_with_decoded_replay_id(prep, tmp_path, monkeypatch):
    import extract_creeps
    import extract_state_v3

    mid = prep.MATCHES[0]
    archive(tmp_path, mid)

    def other(_):
        return {"match_id": mid + 1}, []

    with pytest.raises(ValueError, match="belongs to match"):
        extract_state_v3.extract(tmp_path, mid, capture=other)
    monkeypatch.setitem(
        extract_creeps.KINDS, "extras", ("extras-v1", "gem-extras-capture/1", other)
    )
    with pytest.raises(ValueError, match="belongs to match"):
        extract_creeps.extract(tmp_path, mid, kind="extras")
    for kind in prep.CAPTURE_SCHEMAS:
        assert not prep._target(tmp_path, mid, kind).exists()


def test_public_cohort_can_use_raw_only_but_never_overrides_contradictory_metadata(prep, tmp_path):
    mid = prep.MATCHES[0]
    prep.check_review_metadata(tmp_path, mid)
    with pytest.raises(FileNotFoundError):
        prep.check_review_metadata(tmp_path, 12345)
    metadata(tmp_path, mid)
    path = tmp_path / "meta" / f"{mid}.json"
    path.write_text(json.dumps({"match_id": mid, "patch": 60, "start_time": 1794988801}))
    with pytest.raises(ValueError, match="outside"):
        prep.check_review_metadata(tmp_path, mid)


def test_handoff_generates_missing_modes_and_reuses_existing_reports(prep, tmp_path, monkeypatch):
    import build_map_knowledge
    import decision_review_handoff as handoff

    folders = [tmp_path / mode for mode in handoff.MODES]
    folders[1].mkdir()
    existing = folders[1] / "cases.json"
    existing.write_text("original")
    maps, preparations, calls = [], [], []
    monkeypatch.setattr(
        build_map_knowledge, "prepare_741_map", lambda path, *, fetch: maps.append(fetch)
    )
    monkeypatch.setattr(prep, "prepare_inputs", lambda root, ids: preparations.append((root, ids)))

    def generate(command, **kwargs):
        mode = command[command.index("--mode") + 1]
        assert command[command.index("--matches") + 1 : command.index("--out")] == [
            str(mid) for mid in prep.MATCHES
        ]
        folder = Path(command[-1])
        assert folder.name == mode
        folder.mkdir()
        calls.append(mode)

    monkeypatch.setattr(handoff.subprocess, "run", generate)
    handoff.generate_missing(tmp_path, folders)
    handoff.generate_missing(tmp_path, folders, fetch_map=True)
    assert maps == [False] and preparations == [(tmp_path, prep.MATCHES)]
    assert calls == [handoff.MODES[0], handoff.MODES[2]]
    assert existing.read_text() == "original"
