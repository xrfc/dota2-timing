"""Collection must preserve audit evidence, resume, and restrict raw cleanup."""

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

from dota_items.storage import file_hash, json_bytes, read_json


@pytest.fixture
def collection(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "collector", Path(__file__).parents[1] / "scripts/collect_purchase_candidates.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "collection"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect",
            "--root",
            str(root),
            "--target",
            "1",
            "--max-batches",
            "1",
            "--delete-rejected",
        ],
    )
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    client_class = httpx.Client
    calls = []

    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"rows": [{"match_id": 2}, {"match_id": 1}]})

    monkeypatch.setattr(
        module.httpx,
        "Client",
        lambda **kwargs: client_class(transport=httpx.MockTransport(respond), trust_env=False),
    )

    def fetch(mid, cache, client):
        cache.mkdir(exist_ok=True)
        path = cache / f"{mid}.json"
        path.write_bytes(json_bytes({"match_id": mid}))
        path.with_suffix(".manifest.json").write_bytes(json_bytes({"sha256": file_hash(path)}))
        return path

    monkeypatch.setattr(module, "fetch_match", fetch)

    def preflight(plan, discovery, cache, receipt):
        return {
            "samples": [{"match_id": 1, "source_sha256": file_hash(cache / "1.json")}],
            "exclusions": [{"requested_match_id": 2, "reasons": ["purchase_log_not_present"]}],
        }

    monkeypatch.setattr(module, "build_preflight", preflight)
    return module, root, calls


def test_cleanup_retains_receipts_and_never_touches_other_cache(collection, tmp_path):
    module, root, _ = collection
    old = tmp_path / "old-2.json"
    old.write_text("old historical cache")
    assert module.main() == 0
    batch = root / "batch-0001"
    assert not (batch / "matches/2.json").exists()
    assert (batch / "matches/2.manifest.json").exists()
    assert (batch / "matches/1.json").exists()
    assert old.read_text() == "old historical cache"
    cleanup = read_json(batch / "cleanup.json")
    assert cleanup["payloads"][0]["reasons"] == ["purchase_log_not_present"]
    assert read_json(root / "progress.json")["training_admitted"] == 0


def test_resume_does_not_refetch_or_reaudit_deleted_payload(collection, monkeypatch):
    module, root, calls = collection
    module.main()

    def deny(*args, **kwargs):
        raise AssertionError("completed batch must not re-fetch or re-audit")

    monkeypatch.setattr(module, "fetch_match", deny)
    monkeypatch.setattr(module, "build_preflight", deny)
    module.main()
    assert len(calls) == 1
    assert read_json(root / "progress.json")["retained_candidates"] == 1


@pytest.mark.parametrize("changed", ["matches/1.json", "response.json", "cleanup.json"])
def test_resume_rejects_modified_evidence(collection, changed):
    module, root, _ = collection
    module.main()
    (root / "batch-0001" / changed).write_text("{}")
    with pytest.raises(ValueError):
        module.main()
