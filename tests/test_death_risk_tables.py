"""Generation guard of the death-risk tables and the alert measure (review of 2026-11-18)."""

import json
import pickle

import numpy as np
import pandas as pd
import pytest

from dota_items.contracts.death_risk import MANIFEST, TABLE_SCHEMA, TableError
from dota_items.data.awareness_split import is_holdout
from dota_items.experiments.awareness import death_risk_tables as tables
from dota_items.modeling.awareness.death_risk_eval import death_alerts, summarize_alerts

PARAMS = {"horizons": (10, 20), "step": 5}
KEPT = next(m for m in range(1000, 2000) if not is_holdout(m))
OTHER = next(m for m in range(KEPT + 1, 3000) if not is_holdout(m))
HELD = next(m for m in range(1000, 2000) if is_holdout(m))


def conditions(tmp_path, positions=(1,), params=PARAMS, producer="v = 1\n"):
    code = tmp_path / "producer.py"
    code.write_text(producer, encoding="utf-8")
    knowledge = tmp_path / "means.json"
    if not knowledge.exists():
        knowledge.write_text("{}", encoding="utf-8")
    return tables.describe_conditions(positions, params, 5, [code], [knowledge], tmp_path)


def write_match(folder, match_id, digest, source=("s", 1), **change):
    value = {
        "schema": TABLE_SCHEMA,
        "match_id": match_id,
        "conditions_digest": digest,
        "source_key": list(source),
        "risk": [{"match_id": match_id, "hero": "h", "t": 60, "hit_recent": 0, "dies_20": 0}],
        "win": [{"match_id": match_id, "t": 0}],
        "deaths": [],
        "hits": [{"match_id": match_id, "hero": "h", "t": 55, "source": "hero", "value": 40}],
    } | change
    with (folder / f"{match_id}.pkl").open("wb") as stream:
        pickle.dump(value, stream)


def test_folder_refuses_other_positions_params_or_producer(tmp_path):
    folder = tmp_path / "table"
    digest = tables.prepare_folder(folder, conditions(tmp_path))
    assert tables.prepare_folder(folder, conditions(tmp_path)) == digest  # same: accepted
    assert json.loads((folder / MANIFEST).read_text())["conditions"]["positions"] == [1]
    for changed in (
        conditions(tmp_path, positions=(1, 5)),
        conditions(tmp_path, params={**PARAMS, "step": 1}),
        conditions(tmp_path, producer="v = 2\n"),
    ):
        with pytest.raises(TableError, match="other conditions"):
            tables.prepare_folder(folder, changed)


def test_folder_with_tables_but_no_manifest_is_not_adopted(tmp_path):
    folder = tmp_path / "death-risk-v3"
    folder.mkdir()
    (folder / f"{KEPT}.pkl").write_bytes(pickle.dumps({"schema": "death-risk-table/3"}))
    with pytest.raises(TableError, match="without a manifest"):
        tables.prepare_folder(folder, conditions(tmp_path))
    assert not (folder / MANIFEST).exists()  # nothing written into an old folder


def test_match_file_reused_only_with_same_digest_and_sources(tmp_path):
    folder = tmp_path / "table"
    digest = tables.prepare_folder(folder, conditions(tmp_path))
    path = folder / f"{KEPT}.pkl"
    assert not tables.reusable(path, digest, ["s", 1])
    write_match(folder, KEPT, digest)
    assert tables.reusable(path, digest, ["s", 1])
    with pytest.raises(TableError, match="source files changed"):
        tables.reusable(path, digest, ["s", 2])
    write_match(folder, KEPT, "another digest")
    with pytest.raises(TableError, match="other conditions"):
        tables.reusable(path, digest, ["s", 1])


def test_loader_checks_every_file(tmp_path):
    folder = tmp_path / "table"
    digest = tables.prepare_folder(folder, conditions(tmp_path))
    write_match(folder, KEPT, digest)
    write_match(folder, OTHER, digest)
    risk, win, deaths, info = tables.load_tables(folder)
    assert info["verified"] and info["matches"] == 2 and len(risk) == 2 and len(win) == 2
    write_match(folder, OTHER, "mixed")
    with pytest.raises(TableError, match="other conditions"):
        tables.load_tables(folder)
    write_match(folder, OTHER, digest, win=[{"match_id": KEPT, "t": 0}])
    with pytest.raises(TableError, match="belongs to"):
        tables.load_tables(folder)
    write_match(folder, OTHER, digest, hits=[{"match_id": KEPT, "t": 1}])
    with pytest.raises(TableError, match="belongs to"):
        tables.load_tables(folder)
    write_match(folder, OTHER, digest, hits=None)
    with pytest.raises(TableError, match="no `hits` list"):
        tables.load_tables(folder)
    write_match(folder, OTHER, digest)
    hits, info = tables.load_hits(folder)
    assert [h["match_id"] for h in hits] == [KEPT, OTHER] and info["verified"]
    write_match(folder, HELD, digest)
    with pytest.raises(TableError, match="holdout"):
        tables.load_tables(folder)


def test_legacy_folder_needs_explicit_flag_and_stays_unverified(tmp_path):
    folder = tmp_path / "death-risk-v1"
    folder.mkdir()
    value = {"schema": "death-risk-table/1", "risk": [], "win": [], "deaths": []}
    (folder / f"{KEPT}.pkl").write_bytes(pickle.dumps(value))
    with pytest.raises(TableError, match="allow_legacy"):
        tables.load_tables(folder)
    *_, info = tables.load_tables(folder, allow_legacy=True)
    assert info["verified"] is False and info["conditions_digest"] is None
    with pytest.raises(TableError, match="no manifest"):
        tables.load_hits(folder)  # old tables kept no damage-taken rows
    write_match(folder, OTHER, "x")  # a new-schema file dropped into an old folder
    with pytest.raises(TableError, match="legacy folder"):
        tables.load_tables(folder, allow_legacy=True)


def test_alert_after_a_pause_in_the_hits_counts_as_not_hit_last_3s():
    """The measure is "alert while not hit in the last 3 s", not "before the first hit".

    Hit at 100, no hit in the 3 s before 105, alert at 105, death at 118: it counts, with
    a lead of 13 s, although he was already hit at 100 (the case found in the review).
    """
    frame = pd.DataFrame(
        {
            "match_id": [7] * 5,
            "hero": ["v"] * 5,
            "t": [95, 100, 105, 110, 115],
            "hit_recent": [0, 1, 0, 1, 1],
        }
    )
    scores = np.array([0.01, 0.5, 0.3, 0.6, 0.7])
    deaths = pd.DataFrame({"match_id": [7], "hero": ["v"], "t": [118]})
    found = death_alerts(frame, deaths, scores, 0.2, 20)
    assert found[0]["alerted"] and found[0]["lead"] == 13 and found[0]["peak"] == 0.7
    summary = summarize_alerts(found)
    assert summary["share_alerted_not_hit_last_3s"] == 1.0
    assert "alerted_before_being_hit" not in summary  # the old, overstated name
    scores[2] = 0.1  # only samples with hit_recent == 1 are high: no alert
    assert not death_alerts(frame, deaths, scores, 0.2, 20)[0]["alerted"]
