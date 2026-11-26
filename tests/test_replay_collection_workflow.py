"""Bounded stage recovery uses full synthetic worker bundles and no network."""

import copy
import gzip
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from test_replay_processing import (
    MID,
    PRODUCER,
    install_fake,
    request_fixture,
    write_json,
)

from dota_items.data.replay_bundle import verify_bundle
from dota_items.data.replay_bundle_quality import verify_quality_bundle
from dota_items.workflow import replay_collection as collection
from dota_items.workflow import replay_processing as processing


def planned(tmp_path, *, count=1, downloaded=True):
    sources = tmp_path / "sources"
    sources.mkdir()
    _path, request, meta = request_fixture(sources)
    rows = []
    for offset in range(count):
        mid = MID + offset
        meta_one = {
            **meta,
            "match_id": mid,
            "replay_url": f"https://replay123.valve.net/{mid}.dem.bz2",
        }
        meta_path = sources / f"meta-{mid}.json"
        write_json(meta_path, meta_one)
        row = {**request["discovery"], "match_id": mid, "metadata_path": str(meta_path)}
        if downloaded:
            demo = sources / f"demo-{mid}.dem"
            demo.write_bytes(Path(request["demo_path"]).read_bytes())
            row["demo_path"] = str(demo)
        rows.append(row)
    root = tmp_path / "collection"
    plan = collection.make_plan(
        root,
        Path(request["snapshot_path"]),
        patch="7.42",
        retrieved_at="2026-11-26T12:00:00+00:00",
        rows=rows,
        exclusion=request["exclusion"],
        expected_patch_code=61,
        bounds=request["identity"]["bounds"],
        min_duration=1,
        boundary_buffer_seconds=0,
    )
    return root, plan, request["exclusion"]


def fake_environment(monkeypatch, tmp_path, *, mode="passed"):
    calls = []
    current = {"producer": copy.deepcopy(PRODUCER), "mode": mode}
    monkeypatch.setattr(collection, "RUNTIME", tmp_path / "runtime")
    monkeypatch.setattr(
        collection, "current_producer", lambda _compat: copy.deepcopy(current["producer"])
    )
    monkeypatch.setattr(
        collection.httpx, "Client", lambda **kwargs: SimpleNamespace(close=lambda: None)
    )
    monkeypatch.setattr(
        collection.shutil, "disk_usage", lambda _path: SimpleNamespace(free=100 * 1024**3)
    )

    def worker(command, **kwargs):
        request_path = Path(command[command.index("--request") + 1])
        output = Path(command[command.index("--output") + 1])
        request = json.loads(request_path.read_text())
        calls.append(request["match_id"])
        if current["mode"] == "failed":
            output.mkdir()
            (output / "partial.gz").write_bytes(b"retained failed attempt")
            raise subprocess.CalledProcessError(2, command)
        meta = json.loads(Path(request["metadata_path"]).read_text())

        def missing(row):
            if current["mode"] == "review_required" and row["t"] == 1:
                row["heroes"][0]["abilities"][0]["cd"] = None

        install_fake(monkeypatch, meta, mutate_state=missing)
        monkeypatch.setattr(
            processing, "producer_identity", lambda *args: copy.deepcopy(current["producer"])
        )
        processing.process_request(request_path, output, tmp_path / "compat")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(collection.subprocess, "run", worker)
    return calls, current


def run(root, exclusion, **kwargs):
    return collection.run_stages(
        root,
        exclusion=exclusion,
        compat=root.parent / "compat",
        stage=kwargs.pop("stage", "parse"),
        target=kwargs.pop("target", 5),
        max_attempts=kwargs.pop("max_attempts", 8),
        max_seconds=60,
        **kwargs,
    )


def events(root, stage):
    values = [json.loads(path.read_text()) for path in (root / "events").glob("*.json")]
    return [value for value in values if value["stage"] == stage]


def test_completed_cache_is_reused_without_recapture_or_uncompressed_intermediates(
    tmp_path, monkeypatch
):
    root, _plan, exclusion = planned(tmp_path)
    calls, _current = fake_environment(monkeypatch, tmp_path)
    first = run(root, exclusion)
    assert first["succeeded"] == 1 and calls == [MID]
    bundle = Path(first["results"][0]["bundle"])
    before = {p.name: p.read_bytes() for p in bundle.iterdir()}
    assert set(before) == {
        "manifest.json",
        "raw-gem.json.gz",
        "normalized.json.gz",
        "state-v3.jsonl.gz",
        "extras-v1.jsonl.gz",
    }
    second = run(root, exclusion, stage="verify")
    assert second["succeeded"] == 1
    assert second["results"][0]["status"] == "verified"
    assert calls == [MID]
    assert before == {p.name: p.read_bytes() for p in bundle.iterdir()}
    assert not list(root.rglob("normalized.json"))
    assert not list(root.rglob("raw-gem.json"))


def test_attempt_limit_bounds_matches_even_when_outputs_are_cached(tmp_path, monkeypatch):
    root, _plan, exclusion = planned(tmp_path, count=3)
    calls, _current = fake_environment(monkeypatch, tmp_path)
    first = run(root, exclusion, target=3, max_attempts=1)
    assert first["attempted"] == first["succeeded"] == 1
    assert calls == [MID]
    second = run(root, exclusion, target=3, max_attempts=2)
    assert second["attempted"] == second["succeeded"] == 2
    assert calls == [MID, MID + 1]


def test_failed_attempt_is_kept_and_only_explicit_retry_creates_new_attempt(tmp_path, monkeypatch):
    root, _plan, exclusion = planned(tmp_path)
    calls, current = fake_environment(monkeypatch, tmp_path, mode="failed")
    first = run(root, exclusion)
    assert first["succeeded"] == 0 and first["results"][0]["status"] == "failed"
    assert first["results"][0]["returncode"] == 2
    partial = next(root.glob("jobs/*/attempts/*/bundle/partial.gz"))
    old_bytes = partial.read_bytes()
    old_attempts = set(root.glob("jobs/*/attempts/*"))
    current["mode"] = "passed"
    blocked = run(root, exclusion)
    assert blocked["succeeded"] == 0 and calls == [MID]
    assert set(root.glob("jobs/*/attempts/*")) == old_attempts
    retried = run(root, exclusion, retry_failed=True)
    assert retried["succeeded"] == 1 and calls == [MID, MID]
    assert len(set(root.glob("jobs/*/attempts/*"))) == 2
    assert partial.read_bytes() == old_bytes


def test_review_required_bundle_is_never_counted_as_passed(tmp_path, monkeypatch):
    root, _plan, exclusion = planned(tmp_path)
    calls, current = fake_environment(monkeypatch, tmp_path, mode="review_required")
    first = run(root, exclusion)
    assert first["succeeded"] == 0
    assert first["results"][0]["status"] == "review_required"
    bundle = Path(first["results"][0]["bundle"])
    before = (bundle / "manifest.json").read_bytes()
    assert run(root, exclusion, stage="verify")["succeeded"] == 0
    assert calls == [MID]
    current["mode"] = "passed"
    assert run(root, exclusion, retry_failed=True)["succeeded"] == 1
    assert (bundle / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("change", ["source", "producer", "artifact"])
def test_changed_input_producer_or_artifact_never_counts_as_a_cached_pass(
    tmp_path, monkeypatch, change
):
    root, plan, exclusion = planned(tmp_path)
    calls, current = fake_environment(monkeypatch, tmp_path)
    first = run(root, exclusion)
    bundle = Path(first["results"][0]["bundle"])
    original_manifest = (bundle / "manifest.json").read_bytes()
    if change == "source":
        Path(plan["matches"][0]["demo"]["path"]).write_bytes(b"source changed")
    elif change == "producer":
        current["producer"]["version"] = 2
    else:
        artifact = bundle / "state-v3.jsonl.gz"
        content = artifact.read_bytes()
        artifact.write_bytes(bytes([content[0] ^ 1]) + content[1:])
    second = run(root, exclusion, stage="verify")
    assert second["succeeded"] == 0 and second["results"][0]["status"] == "failed"
    assert calls == [MID]
    assert (bundle / "manifest.json").read_bytes() == original_manifest
    if change == "source":
        assert second["results"][0]["error_message"] == "Source artifact changed"
    else:
        rejected = events(root, "cache_rejected")
        assert len(rejected) == 1
        expected = {
            "producer": "Bundle producer mismatch",
            "artifact": "Compressed digest changed",
        }
        assert rejected[0]["error_message"] == expected[change]


def test_metadata_changed_after_plan_is_rejected_before_workers(tmp_path, monkeypatch):
    root, plan, exclusion = planned(tmp_path)
    calls, _current = fake_environment(monkeypatch, tmp_path)
    metadata = Path(plan["matches"][0]["metadata"]["path"])
    metadata.write_bytes(metadata.read_bytes() + b" ")
    with pytest.raises(ValueError, match="Source artifact changed"):
        run(root, exclusion)
    assert calls == []


def test_reserved_plan_candidate_rejected_before_missing_match_files_are_read(tmp_path):
    sources = tmp_path / "sources"
    sources.mkdir()
    _path, request, _meta = request_fixture(sources)
    row = {**request["discovery"], "metadata_path": str(tmp_path / "missing-metadata.json")}
    with pytest.raises(ValueError, match="Reserved match"):
        collection.make_plan(
            tmp_path / "collection",
            Path(request["snapshot_path"]),
            patch="7.42",
            retrieved_at="2026-11-26T12:00:00+00:00",
            rows=[row],
            exclusion={**request["exclusion"], "percent": 100},
        )
    assert not (tmp_path / "collection" / "plan.json").exists()


def test_download_stage_can_resume_without_starting_parser(tmp_path, monkeypatch):
    root, _plan, exclusion = planned(tmp_path, count=2, downloaded=False)
    calls, _current = fake_environment(monkeypatch, tmp_path)
    downloaded = []

    def download(_client, url, output, *, max_bytes, deadline):
        assert max_bytes > 0 and deadline > 0
        output.parent.mkdir(parents=True, exist_ok=True)
        content = b"synthetic archive"
        assert len(content) <= max_bytes
        output.write_bytes(content)
        downloaded.append(url)
        return processing.source_reference(output)

    monkeypatch.setattr(collection.network, "download", download)
    first = run(root, exclusion, stage="download", target=1, max_attempts=1)
    assert first["succeeded"] == 1 and first["attempted"] == 1
    assert len(downloaded) == 1 and calls == []
    second = run(root, exclusion, stage="download", target=2, max_attempts=2)
    assert second["succeeded"] == 2 and len(downloaded) == 2 and calls == []


def test_disk_reserve_stops_before_new_parse(tmp_path, monkeypatch):
    root, _plan, exclusion = planned(tmp_path)
    calls, _current = fake_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(collection.shutil, "disk_usage", lambda _path: SimpleNamespace(free=0))
    result = run(root, exclusion)
    assert result["succeeded"] == 0 and calls == []
    assert not list(root.glob("jobs/*/attempts/*"))


def test_wall_clock_limit_stops_before_first_match(tmp_path, monkeypatch):
    root, _plan, exclusion = planned(tmp_path)
    calls, _current = fake_environment(monkeypatch, tmp_path)
    clock = iter([0.0, 61.0])
    monkeypatch.setattr(collection.time, "monotonic", lambda: next(clock))
    result = run(root, exclusion)
    assert result["succeeded"] == result["attempted"] == 0 and calls == []


def test_changing_review_status_alone_cannot_forge_a_cached_pass(tmp_path, monkeypatch):
    root, _plan, exclusion = planned(tmp_path)
    calls, _current = fake_environment(monkeypatch, tmp_path, mode="review_required")
    first = run(root, exclusion)
    assert first["results"][0]["status"] == "review_required"
    manifest_path = Path(first["results"][0]["bundle"]) / "manifest.json"
    value = json.loads(manifest_path.read_text())
    value["quality"]["status"] = "passed"
    write_json(manifest_path, value)
    second = run(root, exclusion, stage="verify")
    assert second["succeeded"] == 0 and second["results"][0]["status"] == "failed"
    assert calls == [MID]
    assert json.loads(manifest_path.read_text())["quality"]["status"] == "passed"


def test_failed_download_partial_counts_against_shared_run_byte_budget(tmp_path, monkeypatch):
    root, _plan, exclusion = planned(tmp_path, count=2, downloaded=False)
    calls, _current = fake_environment(monkeypatch, tmp_path)
    downloads = []

    def download(_client, url, output, *, max_bytes, deadline):
        if max_bytes <= 0:
            raise ValueError("No remaining download byte budget")
        output.parent.mkdir(parents=True, exist_ok=True)
        partial = output.with_name(output.name + ".partial")
        partial.write_bytes(b"x" * max_bytes)
        downloads.append(url)
        raise TimeoutError("synthetic interrupted transfer")

    monkeypatch.setattr(collection.network, "download", download)
    result = run(root, exclusion, stage="download", max_bytes=17)
    assert result["succeeded"] == 0 and result["downloaded_bytes"] == 17
    assert len(downloads) == 1 and calls == []
    partials = list(root.glob("jobs/*/downloads/*.partial"))
    assert len(partials) == 1 and partials[0].read_bytes() == b"x" * 17
    assert not list(root.glob("jobs/*/download.json"))


def test_http_failure_preserves_status_without_request_credentials(tmp_path, monkeypatch):
    root, _plan, exclusion = planned(tmp_path, downloaded=False)
    fake_environment(monkeypatch, tmp_path)
    secret = "private-download-token"
    request = httpx.Request("GET", f"https://user:{secret}@example.test/replay?key={secret}")
    response = httpx.Response(403, request=request)

    def download(*args, **kwargs):
        raise httpx.HTTPStatusError(
            f"Access denied for {request.url}", request=request, response=response
        )

    monkeypatch.setattr(collection.network, "download", download)
    result = run(root, exclusion, stage="download")
    failure = events(root, "stage_failed")[0]
    assert result["results"][0]["status_code"] == failure["status_code"] == 403
    assert failure["error_type"] == "HTTPStatusError"
    assert "error_message" not in failure
    assert secret not in json.dumps(result)
    assert all(secret not in path.read_text() for path in (root / "events").glob("*.json"))


@pytest.mark.parametrize("kind", ["subprocess", "timeout", "os", "overflow"])
def test_worker_failure_does_not_log_command_or_output(tmp_path, monkeypatch, kind):
    root, _plan, exclusion = planned(tmp_path)
    fake_environment(monkeypatch, tmp_path)
    secret = "private-worker-argument-and-output"
    errors = {
        "subprocess": subprocess.CalledProcessError(7, [secret], output=secret, stderr=secret),
        "timeout": subprocess.TimeoutExpired([secret], 0.1, output=secret, stderr=secret),
        "os": OSError(13, secret, secret),
        "overflow": OverflowError(secret),
    }

    def worker(*args, **kwargs):
        raise errors[kind]

    monkeypatch.setattr(collection.subprocess, "run", worker)
    result = run(root, exclusion)
    failure = events(root, "stage_failed")[0]
    key, expected = {
        "subprocess": ("returncode", 7),
        "timeout": ("timed_out", True),
        "os": ("errno", 13),
        "overflow": ("error_message", "numeric overflow"),
    }[kind]
    assert failure[key] == result["results"][0][key] == expected
    if kind != "overflow":
        assert "error_message" not in failure
    assert secret not in json.dumps(result)
    assert all(secret not in path.read_text() for path in (root / "events").glob("*.json"))


def test_validation_reason_is_bounded_and_excludes_urls(tmp_path, monkeypatch):
    root, _plan, exclusion = planned(tmp_path, downloaded=False)
    fake_environment(monkeypatch, tmp_path)
    secret = "private-source-query"

    def download(*args, **kwargs):
        raise ValueError(f"Invalid source https://example.test/?key={secret}\n" + "x" * 1000)

    monkeypatch.setattr(collection.network, "download", download)
    result = run(root, exclusion, stage="download")
    failure = events(root, "stage_failed")[0]
    message = failure["error_message"]
    assert len(message) == 500 and "\n" not in message
    assert message.startswith("Invalid source [URL omitted] ")
    assert secret not in json.dumps(result)
    assert all(secret not in path.read_text() for path in (root / "events").glob("*.json"))


def test_numeric_overflow_cache_is_rejected_before_a_later_valid_attempt(tmp_path, monkeypatch):
    root, _plan, exclusion = planned(tmp_path)
    calls, _current = fake_environment(monkeypatch, tmp_path)
    first = run(root, exclusion)
    valid = Path(first["results"][0]["bundle"])
    before = {path.name: path.read_bytes() for path in valid.iterdir()}
    bad = valid.parent.parent / ("0" * 32) / "bundle"
    shutil.copytree(valid, bad)
    assert bad < valid
    state = bad / "state-v3.jsonl.gz"
    lines = [json.loads(line) for line in gzip.decompress(state.read_bytes()).splitlines()]
    lines[1]["heroes"][0]["hp"] = 10**400
    raw = b"".join(json.dumps(line).encode() + b"\n" for line in lines)
    compressed = gzip.compress(raw, mtime=0)
    state.write_bytes(compressed)
    manifest_path = bad / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"]["state"].update(
        compressed_sha256=hashlib.sha256(compressed).hexdigest(),
        compressed_bytes=len(compressed),
        uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
        uncompressed_bytes=len(raw),
    )
    write_json(manifest_path, manifest)
    # All byte signatures agree; the real semantic verifier encounters the huge integer.
    verify_bundle(bad)
    with pytest.raises(OverflowError):
        verify_quality_bundle(bad)
    second = run(root, exclusion, stage="verify")
    assert second["succeeded"] == 1 and calls == [MID]
    assert second["results"][0]["bundle"] == str(valid)
    rejected = events(root, "cache_rejected")
    assert len(rejected) == 1 and rejected[0]["bundle"] == str(bad)
    assert rejected[0]["error_type"] == "OverflowError"
    assert rejected[0]["error_message"] == "numeric overflow"
    assert str(10**400) not in json.dumps(rejected)
    assert state.read_bytes() == compressed
    assert before == {path.name: path.read_bytes() for path in valid.iterdir()}
