import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_break", ROOT / "scripts/check_break_against_game_files.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_keyvalues_handles_comments_nesting_and_duplicates():
    module = _load()
    tree = module.parse_keyvalues(
        """
        "DOTAAbilities"
        {
            // "IsBreakable" "1"
            "a" { "AbilityBehavior" "PASSIVE" "IsBreakable" "1" "IsBreakable" "0" }
            "b" { "AbilityBehavior" "ACTIVE" "Text" "say \\"hi\\" {x}" }
            "Version" "1"
        }
        """
    )
    found = dict(module.iter_abilities(tree))
    assert found["a"]["IsBreakable"] == "1"
    assert "IsBreakable" not in found["b"]
    assert set(found) == {"a", "b"}


def test_classify_separates_all_agreement_and_conflict_cases():
    module = _load()
    assert module.classify("accept", "1", True) == "agree_tagged"
    assert module.classify("accept", None, True) == "accept_but_untagged"
    assert module.classify("reject", "1", True) == "reject_but_tagged"
    assert module.classify("reject", None, True) == "agree_untagged"
    assert module.classify("accept", "1", False) == "ability_not_in_game_files"


def test_normalize_ignores_only_markup_and_whitespace():
    module = _load()
    assert module.normalize("Deals damage.<br><br>Slows\\n target") == module.normalize(
        "Deals damage.Slows target"
    )
    assert module.normalize("Deals damage") != module.normalize("Deals healing")


def _load_audit():
    spec = importlib.util.spec_from_file_location(
        "audit_game_files", ROOT / "scripts/audit_mechanics_against_game_files.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_classify_value_separates_base_conditional_and_zero():
    module = _load_audit()
    assert module.classify_value("stun_duration", "1.0 1.5") == "base"
    assert module.classify_value("scepter_crit", "200") == "scepter_shard"
    assert module.classify_value("does_root", {"value": "0", "special_bonus_shard": "1"}) == (
        "scepter_shard"
    )
    assert module.classify_value("can_silence", {"value": "0", "special_bonus_unique_x": "1"}) == (
        "talent"
    )
    assert module.classify_value("stun_duration", "0") == "zero"


def test_audit_compare_group_covers_all_cases():
    module = _load_audit()
    assert module.compare_group("accept", True) == "agree_present"
    assert module.compare_group("accept", False) == "accept_but_absent"
    assert module.compare_group("reject", True) == "reject_but_present"
    assert module.compare_group("reject", False) == "agree_absent"


def test_retired_item_classification_order():
    spec = importlib.util.spec_from_file_location(
        "retired_items", ROOT / "scripts/build_retired_items.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hidden = {"ItemPurchasable": "0"}
    assert module.classify("x", None, set()) == "not_in_game_files"
    assert module.classify("x", {"IsObsolete": "1"}, {"x"}) == "obsolete"
    assert module.classify("x", hidden, {"x"}) == "neutral_pool"
    assert module.classify("x", {}, set()) == "purchasable"
    assert module.classify("aegis", hidden, set()) == "other_source"
    assert module.classify("x", hidden, set()) == "retired_candidate"
