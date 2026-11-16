"""Meaning of the hero state bits parser v3 stores raw (`unit_state_raw`, U154).

Parser v3 keeps `m_nUnitState64` undecoded. The bits below were matched to effects on our
own replays (2026-11-13, 14 matches): for each effect, the seconds a hero carried a
modifier known to cause it, and which bits were set in those seconds compared with all
other seconds. Only bits that were set in at least 90% of such seconds and rare otherwise
are listed; the rest stay undecoded rather than guessed from an old enum.
"""

STATE_BITS = {
    0: "rooted",
    1: "disarmed",
    2: "attack_immune",
    3: "silenced",
    4: "muted",
    5: "stunned",
    6: "hexed",
    7: "invisible",
    8: "invulnerable",
    56: "debuff_immune",
}
# What each bit was matched against: share of seconds with the bit set under the effect
# and in all seconds (the base rate).
EVIDENCE = {
    0: ("root modifiers", 0.94, 0.006),
    1: ("disarm and hex modifiers", 1.0, 0.029),
    2: ("ghost and ethereal modifiers", 0.98, 0.026),
    3: ("silence and hex modifiers", 0.95, 0.009),
    4: ("hex modifiers", 0.98, 0.003),
    5: ("stun modifiers", 0.93, 0.016),
    6: ("hex modifiers", 0.98, 0.001),
    7: ("Smoke of Deceit, invisibility items and runes", 0.93, 0.013),
    8: ("cyclone modifiers", 0.96, 0.022),
    56: ("Black King Bar and spell-immunity abilities", 1.0, 0.007),
}


def decode(raw):
    """Names of the known states set in a raw value; None when there is no value."""
    if raw is None:
        return None
    return [name for bit, name in STATE_BITS.items() if raw >> bit & 1]


def has(raw, name):
    """Whether the named state is set; False when there is no value."""
    bit = next(b for b, n in STATE_BITS.items() if n == name)
    return raw is not None and bool(raw >> bit & 1)
