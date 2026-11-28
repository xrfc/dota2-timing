"""Fixed source continuity must not manufacture new patch interpretations."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from dota_items.data import mechanics_source_equivalence as module


def fact(subject="alpha"):
    return {
        "review_id": subject + ":claim",
        "subject": subject,
        "mechanism": "aoe_damage",
        "condition": {"context": "base", "requires_scepter": False, "requires_shard": False},
        "decision": "accept",
        "basis": "two_ai",
        "quotes": ["Original source meaning."],
        "condition_notes": [{"text": "Existing prerequisite."}],
        "claude": "accept",
        "codex": "accept",
    }


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    def make(
        *,
        new_hero=None,
        old_script=None,
        new_script=None,
        missing_chinese=False,
        extra_definition="",
        new_item=None,
    ):
        def write(relative, value):
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = value.encode() if isinstance(value, str) else json.dumps(value).encode()
            path.write_bytes(raw)
            return hashlib.sha256(raw).hexdigest()

        base = {"schema": "mechanics-facts/26", "rows": [fact(), fact("orb")]}
        baseline_path = "knowledge/mechanics/extractions/v26/facts-v26.json"
        monkeypatch.setattr(module, "BASE_FACTS", (baseline_path, write(baseline_path, base)))
        candidate = {"schema": "mechanics-facts/27", "rows": deepcopy(base["rows"])}
        registrations = []
        default_script = '"AbilityBehavior" "1" "IsBreakable" "1"'
        hero_record = {"name": "alpha", "desc_loc": "Multiple enemies.", "notes_loc": []}
        for patch, prefix in [("7.41f", "old"), ("7.42", "new")]:
            for kind in ("heroes", "items", "scripts", "item_scripts"):
                root = f"fixtures/{prefix}_{kind}"
                records = []
                if kind == "heroes":
                    for lang in ("english", "schinese"):
                        if patch == "7.42" and lang == "schinese" and missing_chinese:
                            continue
                        record = hero_record | (new_hero or {}) if patch == "7.42" else hero_record
                        name = f"sources/hero-1-{lang}.json"
                        digest = write(
                            f"{root}/{name}",
                            {"result": {"data": {"heroes": [{"id": 1, "abilities": [record]}]}}},
                        )
                        records.append({"file": name, "sha256": digest})
                    manifest = {"schema": "hero-source-manifest/2", "records": records}
                elif kind == "items":
                    item = {"name": "item_orb", "desc_loc": "An orb."}
                    if patch == "7.42":
                        item.update(new_item or {})
                    digest = write(f"{root}/items.json", {"orb": item})
                    manifest = {"schema": "item-sources/1", "sha256": digest}
                else:
                    if kind == "scripts":
                        body = old_script if patch == "7.41f" else new_script
                        body = default_script if body is None else body
                        name = "sources/scripts/npc/heroes/npc_dota_hero_test.txt"
                        text = (
                            '"DOTAHeroes" { "npc_dota_hero_test" {'
                            '"Facets" { "alpha" { "IsBreakable" "0" } } '
                            f'"AbilityDefinitions" {{ "alpha" {{ {body} }} {extra_definition} }}'
                            "} }"
                        )
                    else:
                        name = "sources/scripts/npc/items.txt"
                        text = '"DOTAAbilities" { "item_orb" { "AbilityBehavior" "2" } }'
                    records.append({"file": name, "sha256": write(f"{root}/{name}", text)})
                    manifest = {"schema": "game-files-manifest/1", "records": records}
                digest = write(f"{root}/manifest.json", manifest)
                registrations.append(
                    (
                        prefix + "_" + kind,
                        patch,
                        "scripts" if kind == "item_scripts" else kind,
                        root,
                        digest,
                    )
                )
        monkeypatch.setattr(module, "SNAPSHOTS", tuple(registrations))
        return tmp_path, candidate, base

    return make


def verify(case):
    root, current, baseline = case
    return module.verify_source_equivalence(
        current, baseline, repository_root=root, exact_patch="7.42"
    )


def test_complete_original_rows_and_full_sources_match_with_reproducible_pins(scenario):
    case = scenario()
    result = verify(case)
    assert result["summary"]["counts"]["source_identical"] == 2
    assert result["base"]["schema"] == "mechanics-facts/26"
    assert result["candidate"]["document_sha256"] == module.canonical_sha256(case[1])
    assert len(result["used_files"]) == 19  # eight manifests, ten raw files, one base facts
    for path, digest in result["used_files"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    hero = result["rows"][0]
    assert hero["fact_sha256"] == hero["base_fact_sha256"]
    assert {ref["language"] for ref in hero["raw_source_refs"]} == {"english", "schinese"}
    field = hero["current_script_fields"]["IsBreakable"]
    assert (field["value"], field["unambiguous"], field["occurrences"]) == ("1", True, 1)
    assert field["source_refs"][0]["patch"] == "7.42"
    assert result["patch_verified"] is result["formal_use_allowed"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("condition_notes", [{"text": "Different free text prerequisite."}]),
        ("claude", "reject"),
        ("codex", "reject"),
        ("quotes", ["Changed justification."]),
        ("basis", "user:invented"),
        ("decision", "reject"),
        ("condition", {"context": "shard_upgrade"}),
        ("unrecognized_new_condition", True),
    ],
)
def test_any_fact_field_change_blocks_continuity_including_free_text(scenario, field, value):
    case = scenario()
    case[1]["rows"][0][field] = value
    row = verify(case)["rows"][0]
    assert row["source_equivalent"] is False
    assert "baseline_fact_fields_changed" in row["reasons"]
    assert row["fact_sha256"] != row["base_fact_sha256"]


def test_raw_fields_beyond_old_diff_whitelist_are_compared(scenario):
    row = verify(scenario(new_hero={"unlisted_behavior_flag": True}))["rows"][0]
    assert "raw_record_changed" in row["reasons"]


def test_changed_item_raw_data_cannot_inherit(scenario):
    row = verify(scenario(new_item={"hidden_flag": 7}))["rows"][1]
    assert "raw_record_changed" in row["reasons"]


def test_missing_chinese_is_unknown_not_same_as_english(scenario):
    row = verify(scenario(missing_chinese=True))["rows"][0]
    assert row["source_equivalent"] is False
    assert "raw_record_missing_or_ambiguous" in row["reasons"]


def test_duplicate_script_keys_are_not_collapsed_by_first_wins(scenario):
    old = '"AbilityBehavior" "1" "AbilityBehavior" "2" "IsBreakable" "1"'
    new = '"AbilityBehavior" "1" "AbilityBehavior" "3" "IsBreakable" "1"'
    row = verify(scenario(old_script=old, new_script=new))["rows"][0]
    assert row["source_equivalent"] is False
    assert "script_block_changed" in row["reasons"]
    # Independent current-field evidence remains available even when the block changed.
    assert row["current_script_fields"]["IsBreakable"]["value"] == "1"


@pytest.mark.parametrize("second", ["0", "1"])
def test_duplicate_break_fields_never_certify_a_single_value(scenario, second):
    text = f'"IsBreakable" "1" "IsBreakable" "{second}"'
    field = verify(scenario(old_script=text, new_script=text))["rows"][0]["current_script_fields"]
    assert field["IsBreakable"]["unambiguous"] is False
    assert field["IsBreakable"]["value"] is None
    assert field["IsBreakable"]["occurrences"] == 2


def test_nested_numeric_key_is_not_a_top_level_field_or_ability(scenario):
    text = '"AbilityValues" { "IsBreakable" "1" "alpha" { "value" "7" } }'
    row = verify(scenario(old_script=text, new_script=text))["rows"][0]
    assert row["source_equivalent"] is True
    assert row["current_script_fields"]["IsBreakable"]["unambiguous"] is False
    assert len(row["script_source_refs"]) == 2


def test_multiple_actual_definition_blocks_are_unknown(scenario):
    row = verify(scenario(extra_definition='"alpha" { "IsBreakable" "0" }'))["rows"][0]
    assert "script_block_missing_or_ambiguous" in row["reasons"]
    assert row["current_script_fields"]["IsBreakable"]["unambiguous"] is False


def test_script_comments_and_spacing_are_ignored_but_literals_preserved(scenario):
    old = '"IsBreakable" "1" // an old note\n "Text" "a // b"'
    new = ' "IsBreakable"  "1"  // another note\n "Text"  "a // b" '
    assert verify(scenario(old_script=old, new_script=new))["rows"][0]["source_equivalent"] is True


@pytest.mark.parametrize("text", ['"IsBreakable" "1', '"IsBreakable" "1" }'])
def test_malformed_registered_scripts_are_rejected(scenario, text):
    with pytest.raises(ValueError, match="Unterminated|Unbalanced"):
        verify(scenario(new_script=text))


def test_source_drift_does_not_get_implicitly_reregistered(scenario):
    case = scenario()
    source = case[0] / "fixtures/new_heroes/sources/hero-1-english.json"
    source.write_text(source.read_text().replace("Multiple enemies.", "Different."))
    with pytest.raises(ValueError, match="digest"):
        verify(case)


def test_manifest_drift_and_wrong_baseline_cannot_use_same_file_shortcuts(scenario):
    case = scenario()
    case[2]["rows"][0]["quotes"] = ["Tampered old approval."]
    with pytest.raises(ValueError, match="Baseline facts"):
        verify(case)
    case = scenario()
    manifest = case[0] / "fixtures/new_heroes/manifest.json"
    manifest.write_text(manifest.read_text() + "\n")
    with pytest.raises(ValueError, match="digest"):
        verify(case)


def test_only_registered_exact_patch_and_fact_versions_are_supported(scenario):
    root, current, base = scenario()
    with pytest.raises(ValueError, match="exact patch"):
        module.verify_source_equivalence(current, base, repository_root=root, exact_patch="7.42a")
    current["schema"] = "mechanics-facts/28"
    with pytest.raises(ValueError, match="schema"):
        module.verify_source_equivalence(current, base, repository_root=root, exact_patch="7.42")


def test_new_fact_has_no_baseline_and_duplicate_ids_are_rejected(scenario):
    case = scenario()
    case[1]["rows"][0]["review_id"] = "new:claim"
    row = verify(case)["rows"][0]
    assert row["base_fact_sha256"] is None
    assert "no_baseline_fact" in row["reasons"]
    case[1]["rows"].append(deepcopy(case[1]["rows"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        verify(case)


def test_source_symlinks_are_rejected(scenario):
    case = scenario()
    source = case[0] / "fixtures/new_heroes/sources/hero-1-english.json"
    target = source.with_suffix(".copy")
    source.rename(target)
    source.symlink_to(target)
    with pytest.raises(ValueError, match="canonical"):
        verify(case)
