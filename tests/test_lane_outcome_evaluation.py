import json

from scripts.lane_outcome_evaluation import evaluate, samples


def test_action_window_and_unsupported_action(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.lane_outcome_evaluation.is_holdout", lambda mid: False)
    for name in ("actions", "outcomes"):
        (tmp_path / name).mkdir()
    cases = []
    for mid, act in enumerate(("retreat", "farm", "farm", "farm"), start=1):
        key = str(mid)
        cases.append(
            dict(
                match=mid,
                id=key,
                hero="hero",
                t=100,
                history=[dict(t=100, enemies=[], ally=None)],
                hp=[None, None],
                mana=None,
                ready_names=[],
                recent_hero_damage=False,
                front_distance=300,
                nearby_creeps=2,
            )
        )
        (tmp_path / "actions" / f"{key}.json").write_text(json.dumps({"action": act}))
        (tmp_path / "outcomes" / f"{key}.json").write_text(
            json.dumps(
                dict(
                    complete=True,
                    lane_last_hits=3,
                    action_window_hits=2,
                    death_seconds={1: [], 4: [106]}.get(mid, [107]),
                )
            )
        )
    (tmp_path / "cases.json").write_text(
        json.dumps(dict(schema="wave-decision-review/1", cases=cases))
    )
    rows, excluded = samples(tmp_path)
    assert excluded == {"death_in_action_window": 1}
    assert [r[3:] for r in rows] == [(1, 0), (1, 1), (1, 1)]
    result = evaluate(rows)
    assert result["metrics"]["farm"]["action_mean"]["calibration"][0]["observed"] == 1
    assert result["unsupported"] == {"retreat": 1}
    assert result["metrics"]["no_recent_damage"]["cases"] == 2
