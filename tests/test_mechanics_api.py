"""Knowledge reading API (U124 step 2): fixed meanings, no silent empty results."""

from pathlib import Path

import pytest

from dota_items.data.mechanics_api import API_VERSION, Knowledge, is_confirmed
from dota_items.data.mechanics_current import read_current

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def kb():
    return Knowledge(ROOT)


def test_version_names_every_file_read(kb):
    assert kb.version["api"] == API_VERSION and kb.version["patch"] == "7.41f"
    assert {"facts", "hero_traits", "rules_evaluation"} <= set(kb.version["files"])


def test_trait_counts_match_the_derived_layer(kb):
    raw = read_current("hero_traits", ROOT)["traits"]["disables"]["counts"]
    for count in raw:
        assert kb.trait_count(count["hero_id"], "disables") == count["base"]
        assert (
            kb.trait_count(count["hero_id"], "disables", "with_upgrades") == count["with_upgrades"]
        )
    assert kb.team_trait_sum([8, 30], "disables") == sum(
        kb.trait_count(h, "disables") for h in (8, 30)
    )


def test_unknown_names_raise(kb):
    with pytest.raises(KeyError):
        kb.trait_count(8, "no_such_trait")
    with pytest.raises(KeyError):
        kb.trait_count(9999, "disables")
    with pytest.raises(KeyError):
        kb.heroes_owning(["no_such_ability"])
    with pytest.raises(KeyError):
        kb.rule("R99")
    with pytest.raises(ValueError):
        kb.trait_count(8, "disables", "sometimes")


def test_confirmation_and_mechanisms(kb):
    assert is_confirmed("user:U126") and is_confirmed("field") and is_confirmed("user_spot_check")
    assert not is_confirmed("two_ai") and not is_confirmed("disputed_by_user")
    life_break = {m["mechanism"]: m for m in kb.mechanisms("huskar_life_break")}
    assert "debuff_immunity" not in life_break
    assert life_break["pierces_debuff_immunity"]["confirmed"] is True


def test_relation_conditions_are_three_valued(kb):
    assert kb.rule("R13")["status"] == "candidate"
    assert kb.relation_holds("R13", "tidehunter_gush") is None  # upgrades unknown
    assert kb.relation_holds("R13", "tidehunter_gush", set()) is True
    assert kb.relation_holds("R13", "tidehunter_gush", {"scepter"}) is False
    assert 29 in kb.rule_target_heroes("R13")  # Tidehunter
