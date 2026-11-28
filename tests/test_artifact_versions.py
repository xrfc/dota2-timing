"""Synthetic compatibility claims, never a registry of supported real models."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from dota_items.contracts.artifact_versions import (
    REAL_COMPATIBILITY_MATRIX,
    ArtifactIdentity,
    CompatibilityError,
    CompatibilityRecord,
    CompatibilityRequest,
    ContractIdentity,
    GameContext,
    RuntimeIdentity,
    resolve,
    validate_matrix,
)

NOW = datetime(2026, 1, 2, tzinfo=UTC)
START = NOW - timedelta(days=1)
END = NOW + timedelta(days=1)
DIGEST = "a" * 64
OTHER = "b" * 64


def context(**changes):
    values = dict(
        patch="synthetic-patch-1",
        build=1,
        evidence_level="build-confirmed",
        evidence_sha256=DIGEST,
        parser_sha256=DIGEST,
        map_sha256=DIGEST,
        mechanics_sha256=DIGEST,
    )
    return GameContext(**(values | changes))


def request(**changes):
    artifact = ArtifactIdentity(
        schema="synthetic-model/1",
        manifest_sha256=DIGEST,
        payload_sha256=DIGEST,
        model_family="synthetic-only",
        producer_code_sha256=DIGEST,
        producer_environment_sha256=DIGEST,
        task=ContractIdentity("synthetic-task/1", DIGEST),
        features=ContractIdentity("synthetic-features/1", DIGEST),
        labels=ContractIdentity("synthetic-labels/1", DIGEST),
        split=ContractIdentity("synthetic-split/1", DIGEST),
        source_context=context(),
    )
    runtime = RuntimeIdentity(OTHER, DIGEST, ContractIdentity("synthetic-consumer/1", DIGEST))
    return CompatibilityRequest(
        **(
            dict(
                artifact=artifact,
                runtime=runtime,
                target_context=context(),
                capability="historical-reproduction",
            )
            | changes
        )
    )


def record(query=None, **changes):
    values = dict(
        record_id="synthetic-record-1",
        request=query or request(),
        validation_state="validated",
        support_state="supported",
        evidence_sha256=DIGEST,
        starts_at=START,
        review_by=END,
    )
    return CompatibilityRecord(**(values | changes))


def rejected(matrix, query, reason, *, as_of=NOW):
    with pytest.raises(CompatibilityError) as error:
        resolve(matrix, query, as_of=as_of)
    assert error.value.reason == reason


def test_empty_real_registry_and_unregistered_combinations_fail_closed():
    assert REAL_COMPATIBILITY_MATRIX == ()
    assert validate_matrix(()) == ()
    rejected(REAL_COMPATIBILITY_MATRIX, request(), "unregistered_combination")


def test_multiple_versions_require_explicit_selection_without_mutating_old_identity():
    first = request()
    second = replace(
        first,
        artifact=replace(first.artifact, schema="synthetic-model/2", manifest_sha256=OTHER),
        runtime=replace(first.runtime, environment_sha256=OTHER),
    )
    a, b = record(first), record(second, record_id="synthetic-record-2")
    matrix = a, b
    assert resolve(matrix, first, as_of=NOW) is a
    assert resolve(matrix, second, as_of=NOW) is b
    assert first.artifact.producer_code_sha256 == DIGEST
    assert first.runtime.code_sha256 == OTHER
    assert first.artifact.producer_code_sha256 != first.runtime.code_sha256
    rejected((b,), first, "unregistered_combination")


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "synthetic-model/2"),
        ("manifest_sha256", OTHER),
        ("payload_sha256", OTHER),
        ("model_family", "different-family"),
        ("producer_code_sha256", OTHER),
        ("producer_environment_sha256", OTHER),
        ("task", ContractIdentity("synthetic-task/1", OTHER)),
        ("features", ContractIdentity("synthetic-features/2", DIGEST)),
        ("labels", ContractIdentity("synthetic-labels/1", OTHER)),
        ("split", ContractIdentity("synthetic-split/1", OTHER)),
        ("source_context", context(map_sha256=OTHER)),
    ],
)
def test_same_schema_does_not_mask_changed_artifact_identity(field, value):
    original = request()
    changed = replace(original, artifact=replace(original.artifact, **{field: value}))
    rejected((record(original),), changed, "unregistered_combination")


@pytest.mark.parametrize(
    "field,value",
    [
        ("code_sha256", DIGEST),
        ("environment_sha256", OTHER),
        ("contract", ContractIdentity("synthetic-consumer/1", OTHER)),
    ],
)
def test_new_consumer_requires_new_record_instead_of_rewriting_producer(field, value):
    original = request()
    changed = replace(original, runtime=replace(original.runtime, **{field: value}))
    rejected((record(original),), changed, "unregistered_combination")
    registered = record(changed, record_id="synthetic-new-consumer")
    assert resolve((record(original), registered), changed, as_of=NOW) == registered
    assert changed.artifact is original.artifact


def test_capabilities_are_independent_and_never_inferred_from_readability():
    original = request()
    matrix = (record(original),)
    for capability in ("research-prediction", "product-advice"):
        query = replace(original, capability=capability)
        rejected(matrix, query, "unregistered_combination")
        own = record(query, target_evidence_sha256=OTHER)
        assert resolve((own,), query, as_of=NOW) is own


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"validation_state": "design-only", "evidence_sha256": None}, "unvalidated_record"),
        ({"validation_state": "candidate"}, "unvalidated_record"),
        ({"revoked": True}, "record_revoked"),
        ({"support_state": "retired"}, "retired_record"),
    ],
)
def test_lifecycle_validation_and_revocation_are_enforced(change, reason):
    query = request()
    rejected((record(query, **change),), query, reason)


def test_reproduction_only_support_never_expands_to_prediction_or_advice():
    query = request()
    historical = record(query, support_state="reproduction-only")
    assert resolve((historical,), query, as_of=NOW) is historical
    for capability in ("research-prediction", "product-advice"):
        other = replace(query, capability=capability)
        restricted = record(other, support_state="reproduction-only", target_evidence_sha256=OTHER)
        rejected((restricted,), other, "reproduction_only")


def test_explicit_support_interval_is_half_open_and_timezone_aware():
    query = request()
    row = record(query)
    assert resolve((row,), query, as_of=START) is row
    assert resolve((row,), query, as_of=END - timedelta(microseconds=1)) is row
    shifted = NOW.astimezone(timezone(timedelta(hours=8)))
    assert resolve((row,), query, as_of=shifted) is row
    for now in (START - timedelta(microseconds=1), END, END + timedelta(days=100)):
        rejected((row,), query, "outside_support_window", as_of=now)
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve((row,), query, as_of=NOW.replace(tzinfo=None))


def test_duplicate_records_or_claims_are_rejected_even_when_only_one_is_active():
    query = request()
    a = record(query)
    b = replace(a, record_id="synthetic-duplicate-claim", revoked=True)
    rejected((a, a), query, "ambiguous_matrix")
    rejected((a, b), query, "ambiguous_matrix")
    changed = replace(query, capability="research-prediction")
    rejected((a, record(changed)), query, "ambiguous_matrix")


@pytest.mark.parametrize(
    "field", ["patch", "build", "parser_sha256", "map_sha256", "mechanics_sha256"]
)
def test_target_context_is_exact_not_just_the_patch_name(field):
    query = request(capability="research-prediction")
    value = 2 if field == "build" else "synthetic-patch-2" if field == "patch" else OTHER
    changed = replace(query, target_context=replace(query.target_context, **{field: value}))
    rejected((record(query, target_evidence_sha256=OTHER),), changed, "unregistered_combination")
    rejected((record(changed),), changed, "missing_target_validation")
    own = record(changed, target_evidence_sha256=OTHER)
    assert resolve((own,), changed, as_of=NOW) is own


def test_historical_reproduction_cannot_relabel_a_changed_context():
    query = request(target_context=context(patch="synthetic-patch-2", build=2))
    rejected((record(query, target_evidence_sha256=OTHER),), query, "reproduction_context_changed")


def test_time_inferred_research_requires_evidence_and_retains_uncertainty():
    inferred = context(build=None, evidence_level="time-inferred")
    query = request(capability="research-prediction", target_context=inferred)
    rejected((record(query),), query, "missing_target_validation")
    approved = record(query, target_evidence_sha256=OTHER)
    result = resolve((approved,), query, as_of=NOW)
    assert result.request.target_context.build is None
    assert result.request.target_context.evidence_level == "time-inferred"
    advice = replace(query, capability="product-advice")
    rejected((record(advice, target_evidence_sha256=OTHER),), advice, "target_version_unconfirmed")


@pytest.mark.parametrize("capability", ["research-prediction", "product-advice"])
def test_predictions_on_same_context_still_need_target_effectiveness_evidence(capability):
    query = request(capability=capability)
    assert query.target_context == query.artifact.source_context
    rejected((record(query),), query, "missing_target_validation")


def test_unknown_game_version_permits_only_exact_historical_reproduction():
    unknown = context(patch=None, build=None, evidence_level="unknown", evidence_sha256=None)
    original = request()
    historical = replace(
        original,
        artifact=replace(original.artifact, source_context=unknown),
        target_context=unknown,
    )
    own = record(historical)
    assert resolve((own,), historical, as_of=NOW) is own
    for capability in ("research-prediction", "product-advice"):
        query = replace(historical, capability=capability)
        rejected(
            (record(query, target_evidence_sha256=OTHER),), query, "target_version_unconfirmed"
        )


@pytest.mark.parametrize("invalid", [True, 3, [], {}, "", "A" * 64, "a" * 63, "z" * 64])
def test_digest_validation_is_strict(invalid):
    with pytest.raises(ValueError, match="SHA-256"):
        ContractIdentity("synthetic-contract/1", invalid)


@pytest.mark.parametrize(
    "changes",
    [
        {"build": True},
        {"build": 0},
        {"build": None},
        {"patch": None},
        {"evidence_sha256": None},
        {"evidence_level": "time-inferred"},
        {"evidence_level": "unknown"},
        {"evidence_level": "assumed"},
    ],
)
def test_version_claims_cannot_upgrade_time_or_unknown_to_a_confirmed_build(changes):
    with pytest.raises(ValueError):
        context(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"evidence_sha256": None},
        {"starts_at": START.replace(tzinfo=None)},
        {"review_by": START},
        {"review_by": START - timedelta(seconds=1)},
        {"revoked": 1},
        {"validation_state": "accepted"},
        {"support_state": "forever"},
    ],
)
def test_record_structure_rejects_incomplete_or_ambiguous_claims(changes):
    with pytest.raises(ValueError):
        record(**changes)


def test_identities_and_matrix_are_immutable_and_accept_only_typed_records():
    query = request()
    with pytest.raises(FrozenInstanceError):
        query.artifact.payload_sha256 = OTHER
    with pytest.raises(ValueError, match="ArtifactIdentity"):
        replace(query, artifact={"schema": "synthetic-model/1"})
    with pytest.raises(ValueError, match="immutable tuple"):
        validate_matrix([record(query)])
    with pytest.raises(ValueError, match="CompatibilityRecord"):
        validate_matrix(({},))


def test_valid_digest_spelling_is_not_presented_as_evidence_authentication():
    # No I/O occurs here; the caller is responsible for establishing that this
    # trusted registration and its referenced bytes are genuine and validated.
    row = record(evidence_sha256="0" * 64)
    assert resolve((row,), row.request, as_of=NOW) is row
