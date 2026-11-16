import pytest

from dota_items.data import unit_state as u


def test_decode_names_only_the_matched_bits():
    assert u.decode(None) is None and u.decode(0) == []
    assert u.decode(1 << 7 | 1 << 5 | 1 << 40) == ["stunned", "invisible"]  # bit 40 unknown
    assert u.decode(1 << 56) == ["debuff_immune"]
    assert u.has(1 << 7, "invisible") and not u.has(1 << 5, "invisible")
    assert not u.has(None, "invisible")
    with pytest.raises(StopIteration):
        u.has(0, "flying")
    assert set(u.EVIDENCE) == set(u.STATE_BITS)
    assert all(under >= 0.9 and base < 0.05 for _, under, base in u.EVIDENCE.values())
