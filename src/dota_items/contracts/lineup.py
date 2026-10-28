"""Pure lineup encoding compatible with purchase-log-modeling-snapshot/1.

Historical producers are archived for provenance verification. Parity tests
protect the encoding behavior across explicitly versioned producer migrations.
Callers validate hero IDs and fit vocabulary using training rows only.
"""


def fit_vocabulary(rows):
    return sorted(
        {hero for row in rows for key in ("ally_hero_ids", "enemy_hero_ids") for hero in row[key]}
    )


def encode_lineup(features, vocabulary):
    result = []
    for key in ("ally_hero_ids", "enemy_hero_ids"):
        heroes = set(features[key])
        result.extend(int(hero in heroes) for hero in vocabulary)
        result.append(len(heroes - set(vocabulary)))
    return result


def columns(vocabulary):
    return [
        c
        for side in ("ally", "enemy")
        for c in [*[f"{side}_hero_{h}" for h in vocabulary], f"{side}_unknown_count"]
    ]
