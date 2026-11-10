"""U8 safelane position rule, shared by track A (OpenDota rows) and track B (replays).

Of the two heroes a team had in its safelane, the one with more last hits at 15 minutes
is position 1 and the other position 5; when the gap is under 25 the positions are
unknown. Each track decides who was in the safelane from its own data; this module only
holds the rule, so the two cannot drift apart.
"""

POSITION_MIN_GAP = 25  # U8: 15-minute last-hit gap below this -> position unknown


def split_safelane(last_hits_15):
    """{key: last hits at 15 min} for exactly two safelane heroes -> {key: 1 or 5}, or {}."""
    if len(last_hits_15) != 2 or any(v is None for v in last_hits_15.values()):
        return {}
    high, low = sorted(last_hits_15, key=lambda k: -last_hits_15[k])
    if last_hits_15[high] - last_hits_15[low] < POSITION_MIN_GAP:
        return {}
    return {high: 1, low: 5}
