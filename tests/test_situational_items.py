"""M2b: first situational item labels, registry features, and the frozen pass rule."""

import random

import numpy as np

from dota_items.modeling import situational_items as si

REGISTRY = [
    {
        "hero_id": 50,
        "published_role_labels": ["Support"],
        "capability_review_signals": [{"dimension": "healing"}],
    },
    {
        "hero_id": 51,
        "published_role_labels": ["Carry", "Escape"],
        "capability_review_signals": [{"dimension": "invisibility"}],
    },
    {"hero_id": 52, "published_role_labels": ["Nuker"], "capability_review_signals": []},
    {
        "hero_id": 53,
        "published_role_labels": ["Disabler"],
        "capability_review_signals": [{"dimension": "stun"}],
    },
    {"hero_id": 54, "published_role_labels": ["Carry"], "capability_review_signals": []},
    {
        "hero_id": 55,
        "published_role_labels": ["Support"],
        "capability_review_signals": [{"dimension": "healing"}, {"dimension": "dispel"}],
    },
]


def players_for(match_id, enemies, collapsed=False):
    rows = [
        {
            "match_id": match_id,
            "player_slot": 0,
            "hero_id": 8,
            "position": 1,
            "collapsed_carry": collapsed,
            "is_radiant": True,
        },
    ]
    rows += [
        {
            "match_id": match_id,
            "player_slot": i,
            "hero_id": 60 + i,
            "position": None,
            "collapsed_carry": False,
            "is_radiant": True,
        }
        for i in range(1, 5)
    ]
    rows += [
        {
            "match_id": match_id,
            "player_slot": 128 + i,
            "hero_id": h,
            "position": None,
            "collapsed_carry": False,
            "is_radiant": False,
        }
        for i, h in enumerate(enemies)
    ]
    return rows


def buy(match_id, item, t):
    return {"match_id": match_id, "player_slot": 0, "item": item, "time_s": t}


def test_first_item_with_tie_order_disperser_mapping_and_exclusions():
    players = players_for(1, [50, 51, 52, 53, 54]) + players_for(2, [50, 51, 52, 53, 54])
    players += players_for(3, [50, 51, 52, 53, 54], collapsed=True) + players_for(
        4, [50, 51, 52, 53, 54]
    )
    purchases = [
        buy(1, "skadi", 1900),
        buy(1, "basher", 1900),
        buy(1, "monkey_king_bar", 2000),
        buy(2, "disperser", 1500),
        buy(2, "skadi", 1600),
        buy(3, "skadi", 1000),  # collapsed carry excluded
        buy(4, "bfury", 800),  # no situational item -> not a sample
    ]
    samples = si.build_samples(players, purchases)
    assert [(s["match_id"], s["label"]) for s in samples] == [(1, "skadi"), (2, "diffusal")]
    assert samples[0]["enemies"] == [50, 51, 52, 53, 54]
    assert set(samples[0]) == {"match_id", "enemies", "label", "first_time_s"}


def test_features_count_enemy_roles_and_mechanics_from_registry():
    spec = si.feature_spec(REGISTRY)
    x = si.features([{"enemies": [50, 55, 51, 99]}], spec)
    got = dict(zip(spec["names"], x[0].tolist(), strict=True))
    assert got["role:Support"] == 2 and got["role:Carry"] == 1
    assert got["mech:healing"] == 2 and got["mech:dispel"] == 1 and got["mech:stun"] == 0
    assert got["unknown_heroes"] == 1


def dataset(n, signal, seed=3):
    rng = random.Random(seed)
    players, purchases = [], []
    pool = [50, 51, 52, 53, 54, 55]
    for m in range(n):
        enemies = rng.sample(pool, 5)
        players += players_for(m, enemies)
        healers = sum(h in (50, 55) for h in enemies)
        if signal:
            item = "skadi" if healers == 2 else "monkey_king_bar" if 51 in enemies else "basher"
            if rng.random() < 0.15:
                item = rng.choice(["skadi", "monkey_king_bar", "basher", "nullifier"])
        else:
            item = rng.choice(["skadi", "monkey_king_bar", "basher", "nullifier"])
        purchases.append(buy(m, item, 1800))
    return players, purchases


def run(signal):
    players, purchases = dataset(700, signal)
    samples = si.build_samples(players, purchases)
    spec = si.feature_spec(REGISTRY)
    model = si.fit([s for s in samples if s["match_id"] < 500], spec)
    return model, si.evaluate(model, [s for s in samples if s["match_id"] >= 500], spec)


def test_signal_passes_and_noise_fails_the_frozen_rule():
    model, result = run(True)
    assert result["passed"] and result["log_loss_improvement_ci95"][0] > 0
    top = si.top_coefficients(model)["skadi"]["more_likely"][0][0]
    assert top in ("mech:healing", "role:Support")
    _, noise = run(False)
    assert not noise["passed"]
    assert noise["log_loss_improvement"] < si.MIN_IMPROVEMENT


def test_probabilities_cover_all_classes_even_if_absent_in_training():
    model, _ = run(True)
    p = si.predict(model, np.zeros((2, len(model["feature_names"]))))
    assert p.shape == (2, len(si.CLASSES)) and np.allclose(p.sum(axis=1), 1)
    assert p[0, si.CLASSES.index("sange_and_yasha")] < 1e-6  # never seen in training
