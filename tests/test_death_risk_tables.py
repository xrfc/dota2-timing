"""Generation guard of the death-risk tables and the alert measure (review of 2026-11-18)."""

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dota_items.contracts.death_risk import MANIFEST, TABLE_SCHEMA, TableError
from dota_items.data.awareness_split import is_holdout
from dota_items.experiments.awareness import death_risk_tables as tables
from dota_items.modeling.awareness import death_risk_eval
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
        "params": PARAMS,
        "risk": [{"match_id": match_id, "hero": "h", "t": 60, "hit_recent": 0, "dies_20": 0}],
        "win": [{"match_id": match_id, "t": 0}],
        "deaths": [],
        "hits": [{"match_id": match_id, "hero": "h", "t": 55, "source": "hero", "value": 40}],
        "contact": [
            {
                "match_id": match_id,
                "hero": "h",
                "t": [60],
                "seen_by_enemy": [0],
                "visible_enemy_distance": [20000],
                "enemy_distance": [3000],
            }
        ],
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
        conditions(tmp_path, params={"start": 60, "step": 1}),
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
    write_match(folder, OTHER, digest, contact=[{"match_id": KEPT, "t": []}])
    with pytest.raises(TableError, match="belongs to"):
        tables.load_tables(folder)
    write_match(folder, OTHER, digest)
    parts, info = tables.load_parts(folder)
    assert [h["match_id"] for h in parts["hits"]] == [KEPT, OTHER] and info["verified"]
    assert [c["match_id"] for c in parts["contact"]] == [KEPT, OTHER]
    assert info["params"]["step"] == 5
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
        tables.load_parts(folder)  # old tables kept no damage-taken or contact rows
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


def test_fight_level_alert_must_come_before_the_fight_started():
    """U171–U173: hits by enemy heroes (not towers or creeps) and close, mutual sight make
    one fight; the alert must come before it, outside every fight."""
    hits = [{"match_id": 7, "hero": "v", "t": t, "source": "hero"} for t in (100, 110, 115)]
    hits.append({"match_id": 7, "hero": "v", "t": 80, "source": "tower"})  # not contact
    contact = [{
        "match_id": 7, "hero": "v", "t": [93, 94, 95, 96],
        "seen_by_enemy": [1, 1, 0, 1], "visible_enemy_distance": [900, 2000, 500, 1000],
        "enemy_distance": [900, 900, 500, 500],
    }]  # fmt: skip
    fight = {"gap": 10, "contact_distance": 1200, "hit_sources": ("hero",)}
    spans = death_risk_eval.fight_spans(hits, contact, fight)
    assert spans[(7, "v")] == [(93, 115)]  # 93 and 96 seen and close; 96 to 100 within 10 s
    frame = pd.DataFrame(
        {
            "match_id": [7] * 6,
            "hero": ["v"] * 6,
            "t": [85, 90, 95, 100, 105, 110],
            "hit_recent": [0, 0, 0, 1, 0, 1],
        }
    )
    deaths = pd.DataFrame({"match_id": [7], "hero": ["v"], "t": [118]})
    scores = np.array([0.1, 0.1, 0.1, 0.5, 0.3, 0.6])  # high only inside the fight
    found = death_risk_eval.fight_alerts(frame, deaths, scores, 0.2, 30, spans, fight)
    assert found[0]["fight_start"] == 93 and found[0]["fight_seconds"] == 25
    assert found[0]["could_alert"] and not found[0]["alerted"]
    assert death_alerts(frame, deaths, scores, 0.2, 30)[0]["alerted"]  # the old measure: yes
    scores[1] = 0.25  # 90 s: before the fight
    found = death_risk_eval.fight_alerts(frame, deaths, scores, 0.2, 30, spans, fight)
    assert found[0]["alerted"] and found[0]["lead_to_fight"] == 3
    assert found[0]["lead_to_death"] == 28
    summary = death_risk_eval.summarize_fight_alerts(found)
    assert summary["share_of_all_deaths"] == 1.0 and summary["median_fight_seconds"] == 25
    long = death_risk_eval.fight_alerts(frame, deaths, scores, 0.2, 20, spans, fight)
    assert not long[0]["could_alert"]  # fight longer than the 20 s horizon: no sample before
    tight = death_risk_eval.fight_spans(hits, contact)  # the proposal: gap 5, distance 900
    assert tight[(7, "v")] == [(93, 93), (100, 100), (110, 115)]  # 96: 1000 away, not contact


def test_risk_frame_keeps_one_row_every_n_seconds(tmp_path):
    folder = tmp_path / "table"
    digest = tables.prepare_folder(folder, conditions(tmp_path, params={"start": 60, "step": 1}))
    rows = [{"match_id": KEPT, "hero": "h", "t": t, "hit_recent": 0} for t in range(60, 76)]
    write_match(folder, KEPT, digest, risk=rows, params={"start": 60, "step": 1})
    frame, _, info = tables.load_risk_frame(folder, every=5)
    assert frame["t"].tolist() == [60, 65, 70, 75] and info["every_seconds"] == 5
    assert tables.load_risk_frame(folder, every=3)[0]["t"].tolist() == [60, 63, 66, 69, 72, 75]
    write_match(folder, KEPT, digest, risk=rows, params={"start": 60, "step": 2})
    with pytest.raises(TableError, match="parameters differ"):
        tables.load_risk_frame(folder, every=3)


def test_false_alarms_are_counted_per_hour_not_per_sample():
    """A finer step checks more often: the same scores give more alarms per hour."""
    frame = pd.DataFrame({"match_id": [7] * 12, "hero": ["v"] * 12, "t": range(60, 120, 5)})
    scores = np.array([0.0, 0.5, 0.5, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.5])
    y = np.array([0] * 10 + [1, 1])  # the last two precede a death: not false alarms
    mask = np.ones(12, dtype=bool)
    onsets, share = death_risk_eval.false_alarm_rate(frame, scores, y, mask, 0.2, 5)
    assert onsets == 2 / (60 / 3600) and share == 3 / 12  # two runs in one minute
    threshold = death_risk_eval.threshold_for_rate(frame, scores, y, mask, 5, 0.0)
    assert threshold > 0.5  # no false alarm at all


def test_threshold_handles_split_alarm_runs():
    frame = pd.DataFrame({"match_id": [7] * 3, "hero": ["v"] * 3, "t": [0, 1, 2]})
    assert (
        death_risk_eval.threshold_for_rate(
            frame, np.array([0.9, 0.45, 0.9]), np.zeros(3), np.ones(3, dtype=bool), 1, 1200
        )
        == 0
    )


def test_manifest_rejects_an_edited_step(tmp_path):
    folder = tmp_path / "tables"
    tables.prepare_folder(folder, conditions(tmp_path))
    path = folder / MANIFEST
    manifest = json.loads(path.read_text())
    manifest["conditions"]["params"]["step"] = 1
    with pytest.raises(TableError, match="digest"):
        tables.check_manifest(manifest)


def test_fight_coverage_includes_unsampled_target_deaths_once():
    frame = pd.DataFrame({"match_id": [7], "hero": ["v"], "t": [60]})
    deaths = pd.DataFrame(
        {"match_id": [7] * 5, "hero": ["v", "v", "v", "w", "other"], "t": [40, 69, 69, 43, 43]}
    )
    found = death_risk_eval.fight_alerts(frame, deaths, np.array([0.9]), 0.5, 20, {(7, "w"): []})
    summary = death_risk_eval.summarize_fight_alerts(found)
    assert summary["deaths"] == 3 and summary["deaths_with_samples"] == 1
    assert summary["alerted_before_fight"] == 1 and summary["share_of_all_deaths"] == 0.3333
    assert found[0]["peak"] is None


def test_time_budget_rejects_a_continuous_hour_of_false_alarms():
    frame = pd.DataFrame({"match_id": 7, "hero": "v", "t": range(3600)})
    scores = np.full(3600, 0.1)
    scores[[100, 200]] = 0.9
    y, mask = np.zeros(3600), np.ones(3600, dtype=bool)
    threshold = death_risk_eval.threshold_for_rate(frame, scores, y, mask, 1, 2, max_share=2 / 3600)
    assert death_risk_eval.false_alarm_rate(frame, scores, y, mask, threshold, 1) == (2, 2 / 3600)


def test_legacy_reason_report_checks_digest_and_sample_identity(tmp_path):
    import runpy

    run = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/death_risk_by_reason.py")
    )["main"]
    folder = tmp_path / "table"
    identity = tables.prepare_folder(folder, conditions(tmp_path))
    write_match(folder, KEPT, identity)
    path = tmp_path / "report.json"
    args = [
        "--root",
        str(tmp_path),
        "--table",
        "table",
        "--episodes",
        str(tmp_path),
        "--risk",
        str(tmp_path),
        "--out",
        str(tmp_path / "out"),
    ]
    path.write_text(
        json.dumps({"input": {"conditions_digest": "other"}, "alerts": {"threshold": 0.2}})
    )
    with pytest.raises(ValueError, match="conditions differ"):
        run(args)
    path.write_text(json.dumps({"alerts": {"threshold": 0.2}}))
    np.savez(tmp_path / "out-of-fold.npz", match_id=[OTHER], hero=["h"], t=[60], hit_recent=[0])
    with pytest.raises(ValueError, match="keys differ"):
        run(args)
