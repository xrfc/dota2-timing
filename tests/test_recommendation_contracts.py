"""Synthetic protocol cases, not mechanism review or recommendation quality evidence."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from dota_items.recommendation.contracts import (
    LineupRequest,
    Recommendation,
    UnknownHeroError,
    validate_lineup,
)


@pytest.fixture
def payload():
    return {
        "patch": "7.41f",
        "radiant": [8, 1, 2, 3, 4],
        "dire": [5, 6, 7, 9, 10],
        "target_team": "radiant",
        "target_hero_id": 8,
        "role": 1,
    }


@pytest.fixture
def result(payload):
    request = validate_lineup(payload, known_hero_ids=range(1, 11))
    # These assertions are fixture-only. No real 7.41f mechanism is certified here.
    return {
        "request": request.model_dump(mode="json"),
        "input_fingerprint": request.fingerprint(),
        "knowledge_version": "synthetic-test/1",
        "knowledge_sha256": "a" * 64,
        "rules_version": "synthetic-test/1",
        "rules_sha256": "b" * 64,
        "engine_version": "synthetic-test/1",
        "status": "supported",
        "coverage": [
            {
                "hero_id": hero,
                "status": "verified",
                "fact_ids": [f"fixture-{hero}"],
                "notes": "Synthetic contract fixture, not a verified game mechanism.",
            }
            for hero in range(1, 11)
        ],
        "evidence": [
            {
                "fact_id": f"fixture-{hero}",
                "source_ref": f"synthetic-fixture:hero/{hero}",
                "source_sha256": "c" * 64,
                "source_patch": "7.41f",
                "review_status": "verified",
                "hero_id": hero,
            }
            for hero in range(1, 11)
        ],
        "candidates": [
            {
                "item_key": "fixture_equipment",
                "category": "alternative",
                "stage": "mid",
                "reason": "Protocol fixture only; this is not advice.",
                "conditions": ["Synthetic test only"],
                "tradeoffs": ["No game quality evidence"],
                "rule_ids": ["fixture-rule"],
                "fact_ids": ["fixture-8"],
                "score_components": [
                    {"name": "fixture-score", "value": -2.5, "reason": "Not a probability"}
                ],
            }
        ],
        "limitations": ["No current economy, inventory or purchase timing is known."],
    }


def test_known_catalog_and_json_roundtrip(payload):
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads(
        (root / "knowledge/hero-capabilities/sources/opendota-heroes.json").read_text()
    )
    request = validate_lineup(payload, known_hero_ids={row["id"] for row in catalog.values()})
    assert request.target_hero_id == 8
    assert request == LineupRequest.model_validate_json(request.model_dump_json())
    assert request.radiant == (1, 2, 3, 4, 8)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("radiant", [8, 1, 2, 3]),
        ("dire", [5, 6, 7, 9, 10, 11]),
        ("radiant", [8, 1, 2, 3, 3]),
        ("dire", [8, 6, 7, 9, 10]),
        ("radiant", [True, 1, 2, 3, 8]),
        ("radiant", [0, 1, 2, 3, 8]),
        ("radiant", ["4", 1, 2, 3, 8]),
        ("target_hero_id", 5),
        ("target_hero_id", 99),
        ("target_hero_id", 8.0),
        ("target_team", "dire"),
        ("target_team", "unknown"),
        ("patch", "latest"),
        ("patch", "7.41e"),
        ("role", 0),
        ("role", 6),
        ("role", "1"),
        ("role", True),
        ("role", None),
        ("facets", {}),
        ("inventory", []),
        ("schema_version", "coach-lineup-request/2"),
    ],
)
def test_invalid_requests_are_not_silent_empty_recommendations(payload, field, value):
    payload[field] = value
    with pytest.raises(ValidationError):
        validate_lineup(payload, known_hero_ids=range(1, 11))


@pytest.mark.parametrize("field", ["patch", "role", "target_team", "target_hero_id"])
def test_required_scope_is_never_assumed(payload, field):
    del payload[field]
    with pytest.raises(ValidationError):
        validate_lineup(payload, known_hero_ids=range(1, 11))


def test_unknown_hero_is_distinct_from_missing_mechanism_coverage(payload):
    payload["dire"][-1] = 9999
    with pytest.raises(UnknownHeroError) as error:
        validate_lineup(payload, known_hero_ids=range(1, 11))
    assert error.value.code == "unknown_hero"
    assert error.value.hero_ids == (9999,)


@pytest.mark.parametrize("catalog", [[], [True], ["8"], [0], [-1]])
def test_invalid_catalog_fails_closed(payload, catalog):
    with pytest.raises(ValueError, match="catalog"):
        validate_lineup(payload, known_hero_ids=catalog)


def test_input_identity_ignores_team_order_but_tracks_meaning(payload):
    request = LineupRequest.model_validate(payload)
    payload["radiant"].reverse()
    payload["dire"].reverse()
    assert LineupRequest.model_validate(payload).fingerprint() == request.fingerprint()
    payload["role"] = 2
    assert LineupRequest.model_validate(payload).fingerprint() != request.fingerprint()
    payload["role"] = 1
    payload["target_hero_id"] = 1
    assert LineupRequest.model_validate(payload).fingerprint() != request.fingerprint()
    payload["target_hero_id"] = 8
    payload["radiant"], payload["dire"] = payload["dire"], payload["radiant"]
    payload["target_team"] = "dire"
    assert LineupRequest.model_validate(payload).fingerprint() != request.fingerprint()


def test_result_roundtrip_and_rule_score_is_not_probability(result):
    validated = Recommendation.model_validate(result)
    assert validated == Recommendation.model_validate_json(validated.model_dump_json())
    assert validated.candidates[0].score_components[0].value == -2.5


def remove_coverage(result, hero, status="unknown"):
    row = next(row for row in result["coverage"] if row["hero_id"] == hero)
    row.update(status=status, fact_ids=[], notes="Mechanism evidence unavailable or conflicting")
    result["evidence"] = [fact for fact in result["evidence"] if fact["hero_id"] != hero]


@pytest.mark.parametrize("status", ["unknown", "conflict"])
def test_partial_coverage_retains_uncertainty_without_discarding_known_identity(result, status):
    remove_coverage(result, 10, status)
    with pytest.raises(ValidationError, match="all ten"):
        Recommendation.model_validate(result)
    result["status"] = "partial"
    validated = Recommendation.model_validate(result)
    assert validated.coverage[-1].status == status
    assert validated.request.dire[-1] == 10


def test_unknown_target_cannot_receive_advice(result):
    remove_coverage(result, 8)
    result["status"] = "partial"
    with pytest.raises(ValidationError, match="target hero coverage"):
        Recommendation.model_validate(result)


def test_empty_result_requires_a_reason_and_can_be_honestly_unsupported(result):
    result["candidates"] = []
    with pytest.raises(ValidationError, match="empty_reason"):
        Recommendation.model_validate(result)
    result["empty_reason"] = "No admissible candidates for the declared scope"
    assert Recommendation.model_validate(result).candidates == ()
    for hero in range(1, 11):
        remove_coverage(result, hero)
    result["status"] = "unsupported"
    assert Recommendation.model_validate(result).status == "unsupported"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("input_fingerprint",), "0" * 64),
        (("knowledge_sha256",), "not-a-hash"),
        (("rules_version",), "  "),
        (("limitations",), []),
        (("status",), "unsupported"),
        (("status",), "partial"),
        (("coverage", 0, "hero_id"), 2),
        (("coverage", 0, "fact_ids"), ["fixture-2"]),
        (("coverage", 0, "fact_ids"), []),
        (("evidence", 0, "source_patch"), "unknown"),
        (("evidence", 0, "review_status"), "candidate_not_training_admitted"),
        (("evidence", 0, "fact_id"), "fixture-2"),
        (("evidence", 0, "hero_id"), 9999),
        (("candidates", 0, "fact_ids"), ["missing-fact"]),
        (("candidates", 0, "rule_ids"), []),
        (("candidates", 0, "tradeoffs"), []),
        (("candidates", 0, "score_components", 0, "value"), float("nan")),
        (("candidates", 0, "score_components", 0, "value"), float("inf")),
        (("candidates", 0, "score_components", 0, "value"), True),
        (("empty_reason",), "Inconsistent nonempty result"),
        (("win_probability",), 0.9),
    ],
)
def test_inconsistent_or_untraceable_results_are_rejected(result, path, value):
    target = result
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        Recommendation.model_validate(result)


def test_same_equipment_cannot_appear_as_two_distinct_recommendations(result):
    duplicate = copy.deepcopy(result["candidates"][0])
    duplicate["category"] = "core"
    result["candidates"].append(duplicate)
    with pytest.raises(ValidationError, match="unique across categories"):
        Recommendation.model_validate(result)


def test_models_are_frozen_and_nested_instances_are_revalidated(payload, result):
    request = LineupRequest.model_validate(payload)
    with pytest.raises(ValidationError, match="frozen"):
        request.role = 2
    # Pydantic model_copy bypasses validation; boundaries must not trust such instances.
    forged = request.model_copy(update={"role": 0})
    with pytest.raises(ValidationError):
        validate_lineup(forged, known_hero_ids=range(1, 11))
    result["request"] = forged
    with pytest.raises(ValidationError):
        Recommendation.model_validate(result)


def test_contracts_import_without_replay_workflow_or_training_frameworks():
    code = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(('gem', 'dota_items.sources', 'dota_items.workflow',
                        'dota_items.data', 'knowledge', 'learning', 'torch', 'sklearn')):
        raise AssertionError(f'Forbidden dependency: {name}')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from dota_items.recommendation.contracts import LineupRequest, Recommendation
assert LineupRequest.model_json_schema()['additionalProperties'] is False
assert Recommendation.model_json_schema()['additionalProperties'] is False
"""
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
