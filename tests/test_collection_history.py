from pathlib import Path

import pytest

from dota_items.sources.collection_history import filter_discovery, freeze_history
from dota_items.storage import json_bytes


def test_history_includes_previous_plans_deleted_and_other_caches(tmp_path):
    previous = tmp_path / "old"
    batch = previous / "batch-0001"
    batch.mkdir(parents=True)
    (batch / "plan.json").write_bytes(json_bytes({"match_ids": [900, 800]}))
    (tmp_path / "700.manifest.json").write_text("{}")
    (tmp_path / "600.json").write_text("{}")
    frozen = freeze_history(tmp_path, previous)
    assert frozen["excluded_match_ids"] == [600, 700, 800, 900]
    assert frozen["initial_upper_match_id_exclusive"] == 800
    assert freeze_history(tmp_path, previous) == frozen


def test_discovery_excludes_old_matches_before_detail_requests():
    rows = [{"match_id": 9}, {"match_id": 8}]
    assert filter_discovery(rows, {9}, 0, 10) == [{"match_id": 8}]
    assert filter_discovery(rows, {9, 8}, 0, 10) == []


@pytest.mark.parametrize("ids", [[9, 9], [8, 9], [10], [0], ["9"]])
def test_invalid_discovery_rejected(ids):
    with pytest.raises(ValueError):
        filter_discovery([{"match_id": mid} for mid in ids], set(), 0, 10)


def test_original_collector_is_preserved():
    # Its code identity remains the one frozen into the historical run.
    from dota_items.storage import file_hash, read_json

    historical = Path("data/purchase-1000-2026-10-14/collection.json")
    if not historical.exists():
        pytest.skip("Local historical collection unavailable")
    assert (
        file_hash(Path("scripts/collect_purchase_candidates.py"))
        == read_json(historical)["collector_sha256"]
    )


def test_additional_collection_filters_and_resumes(tmp_path, monkeypatch):
    import importlib.util
    import sys

    import httpx

    from dota_items.storage import file_hash, read_json

    spec = importlib.util.spec_from_file_location(
        "additional", "scripts/collect_purchase_additional.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "new"
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_bytes(
        json_bytes(
            {
                "excluded_match_ids": [9000000002],
                "initial_upper_match_id_exclusive": 9000000003,
            }
        )
    )
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
            "--exclusions",
            str(exclusions),
        ],
    )
    original = httpx.Client
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200, json={"rows": [{"match_id": 9000000002}, {"match_id": 9000000001}]}
        )

    monkeypatch.setattr(
        module.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(respond), trust_env=False),
    )
    downloaded = []

    def fetch(mid, cache, client):
        downloaded.append(mid)
        cache.mkdir(exist_ok=True)
        (cache / f"{mid}.json").write_text("{}")

    monkeypatch.setattr(module, "fetch_match", fetch)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        module,
        "build_preflight",
        lambda plan, discovery, cache, receipt: {
            "samples": [
                {"match_id": 9000000001, "source_sha256": file_hash(cache / "9000000001.json")}
            ],
            "exclusions": [],
        },
    )
    assert module.main() == 0
    assert downloaded == [9000000001]
    assert read_json(root / "progress.json")["retained_candidates"] == 1
    assert module.main() == 0
    assert len(requests) == len(downloaded) == 1
