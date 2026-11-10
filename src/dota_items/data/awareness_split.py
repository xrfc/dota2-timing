"""Track B evaluation holdout (U133, 2026-11-10).

20% of matches, picked by a salted SHA-256 of the match ID, are held out for the final
evaluation of track B (B0 label checks, later B2/B5 models). Threshold tuning, sample
reviews and model development use only the rest. The rule depends on nothing but the
match ID, so every future match falls on a fixed side without a list to maintain.
"""

import hashlib

SCHEMA = "awareness-holdout/1"
SALT = "dota2-timing:track-b-holdout:u133"
HOLDOUT_PERCENT = 20


def is_holdout(match_id):
    digest = hashlib.sha256(f"{SALT}:{int(match_id)}".encode()).hexdigest()
    return int(digest, 16) % 100 < HOLDOUT_PERCENT


def describe():
    return {"schema": SCHEMA, "salt": SALT, "holdout_percent": HOLDOUT_PERCENT, "decision": "U133"}
