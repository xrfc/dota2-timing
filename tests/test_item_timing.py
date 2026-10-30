"""M2 item timing: sample building, class floor, frozen evaluation and display rule."""

import random

import numpy as np

from dota_items.modeling import item_timing as it


def match_rows(match_id, jug_enemy, collapsed=False, wd=True):
    """Radiant: Juggernaut pos1 + 4 others; Dire includes ``jug_enemy``."""
    radiant = [8, 30 if wd else 31, 2, 3, 4]
    dire = [jug_enemy, 51, 52, 53, 54]
    rows = []
    for i, hero in enumerate(radiant + dire):
        rows.append(
            {
                "match_id": match_id,
                "player_slot": i if i < 5 else 123 + i,
                "is_radiant": i < 5,
                "hero_id": hero,
                "position": 1 if hero == 8 else 5 if hero == 30 else None,
                "collapsed_carry": collapsed and hero == 8,
                "lh_10": 99,
                "win": True,
            }
        )
    return rows


def dataset(n, signal, seed=1):
    rng = random.Random(seed)
    players, purchases = [], []
    for m in range(n):
        enemy = 50 if rng.random() < 0.5 else 49
        players += match_rows(m, enemy)
        # bfury before 14 min mostly when enemy 50 is present (if signal).
        early = (enemy == 50) if signal else rng.random() < 0.5
        t = 700 if early else 1000
        if rng.random() < 0.1:
            t = 1700 - t
        purchases.append({"match_id": m, "player_slot": 0, "item": "bfury", "time_s": t})
        purchases.append({"match_id": m, "player_slot": 0, "item": "bfury", "time_s": 2500})
    return players, purchases


def test_samples_use_only_lineup_and_first_purchase():
    players = match_rows(1, 50) + match_rows(2, 50, collapsed=True)
    purchases = [
        {"match_id": 1, "player_slot": 0, "item": "bfury", "time_s": 900},
        {"match_id": 1, "player_slot": 0, "item": "bfury", "time_s": 100},
    ]
    samples = it.build_samples(players, purchases)
    specs = sorted((s["match_id"], s["spec"]) for s in samples)
    assert specs == [(1, (8, 1)), (1, (30, 5)), (2, (30, 5))]  # collapsed carry excluded
    jug = next(s for s in samples if s["spec"] == (8, 1))
    assert set(jug["inputs"]) == {"allies", "enemies", "is_radiant"}
    assert jug["inputs"]["allies"] == [2, 3, 4, 30]
    assert jug["first_purchase_s"]["bfury"] == 900  # first logged purchase
    assert it.label(jug, "bfury", 16) == 1 and it.label(jug, "bfury", 15) == 0


def test_label_boundary_is_strict():
    sample = {"first_purchase_s": {"blink": 600}}
    assert it.label(sample, "blink", 10) == 0
    assert it.label(sample, "blink", 11) == 1


def test_unknown_heroes_are_counted_not_dropped():
    vocab = {"heroes": [2, 3]}
    x = it.features(
        [{"inputs": {"allies": [2, 99], "enemies": [98, 97], "is_radiant": True}}], vocab
    )
    assert x.tolist() == [[1, 0, 0, 0, 1, 2, 1]]


def test_lineup_signal_beats_baseline_and_noise_does_not():
    for signal, expected in ((True, "model"), (False, "baseline")):
        players, purchases = dataset(600, signal)
        samples = it.build_samples(players, purchases)
        train = [s for s in samples if s["match_id"] < 450]
        valid = [s for s in samples if s["match_id"] >= 450]
        vocab = it.fit_vocab(train)
        models = it.fit(train, vocab)
        row = next(
            r
            for r in it.evaluate(models, valid, vocab)
            if r["hero_id"] == 8 and r["item"] == "bfury" and r["minute"] == 15
        )
        assert row["modeled"]
        assert row["display"] == expected, row["brier_improvement_ci95"]


def test_class_floor_falls_back_to_baseline():
    players, purchases = dataset(40, True)
    samples = it.build_samples(players, purchases)
    models = it.fit(samples, it.fit_vocab(samples))
    never = models[((8, 1), "blink", 30)]
    assert never["model"] is None and never["positives"] == 0
    assert np.allclose(it.predict(never, np.zeros((3, 1))), 0.0)


def test_monotone_display():
    assert it.monotone([0.1, 0.4, 0.3, 0.8]) == [0.1, 0.4, 0.4, 0.8]
