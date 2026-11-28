"""Immutable version identities and explicit compatibility decisions, without I/O.

The caller supplies a trusted matrix after verifying its provenance and referenced
evidence. Digest validation here checks spelling only: it does not inspect bytes,
authenticate evidence, load an artifact, or authorize training. No real model is
registered by this module. Low-level numerical functions are not release gates;
artifact/application callers must resolve their requested capability explicitly.
"""

from dataclasses import dataclass
from datetime import datetime

CAPABILITIES = ("historical-reproduction", "research-prediction", "product-advice")
VALIDATION_STATES = ("design-only", "candidate", "validated")
SUPPORT_STATES = ("supported", "reproduction-only", "retired")
VERSION_EVIDENCE_LEVELS = ("build-confirmed", "time-inferred", "unknown")


def _text(value, name):
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{name} must be a nonempty, trimmed string")


def _digest(value, name):
    if (
        type(value) is not str
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _instance(value, expected, name):
    if type(value) is not expected:
        raise ValueError(f"{name} must be {expected.__name__}")


def _choice(value, choices, name):
    if type(value) is not str or value not in choices:
        raise ValueError(f"invalid {name}")


def _aware(value, name):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")


@dataclass(frozen=True, slots=True)
class ContractIdentity:
    """A version name alone is insufficient to identify research/runtime semantics."""

    version: str
    sha256: str

    def __post_init__(self):
        _text(self.version, "contract version")
        _digest(self.sha256, "contract sha256")


@dataclass(frozen=True, slots=True)
class GameContext:
    """Separate actual build evidence from a release-time inference or unknown version."""

    patch: str | None
    build: int | None
    evidence_level: str
    evidence_sha256: str | None
    parser_sha256: str
    map_sha256: str
    mechanics_sha256: str

    def __post_init__(self):
        _choice(self.evidence_level, VERSION_EVIDENCE_LEVELS, "version evidence level")
        for name in ("parser_sha256", "map_sha256", "mechanics_sha256"):
            _digest(getattr(self, name), name)
        if self.patch is not None:
            _text(self.patch, "patch")
        if self.build is not None and (type(self.build) is not int or self.build <= 0):
            raise ValueError("build must be a positive integer or None")
        if self.evidence_sha256 is not None:
            _digest(self.evidence_sha256, "version evidence sha256")
        if self.evidence_level == "unknown":
            if any(x is not None for x in (self.patch, self.build, self.evidence_sha256)):
                raise ValueError("unknown version cannot claim a patch, build or evidence")
        elif self.patch is None or self.evidence_sha256 is None:
            raise ValueError("known/inferred version requires patch and evidence")
        elif self.evidence_level == "build-confirmed" and self.build is None:
            raise ValueError("build-confirmed version requires a build")
        elif self.evidence_level == "time-inferred" and self.build is not None:
            raise ValueError("release time does not confirm a build")


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    """The original artifact/producer identity remains unchanged by a new consumer."""

    schema: str
    manifest_sha256: str
    payload_sha256: str
    model_family: str
    producer_code_sha256: str
    producer_environment_sha256: str
    task: ContractIdentity
    features: ContractIdentity
    labels: ContractIdentity
    split: ContractIdentity
    source_context: GameContext

    def __post_init__(self):
        _text(self.schema, "artifact schema")
        _text(self.model_family, "model family")
        for name in (
            "manifest_sha256",
            "payload_sha256",
            "producer_code_sha256",
            "producer_environment_sha256",
        ):
            _digest(getattr(self, name), name)
        for name in ("task", "features", "labels", "split"):
            _instance(getattr(self, name), ContractIdentity, name)
        _instance(self.source_context, GameContext, "source context")


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    code_sha256: str
    environment_sha256: str
    contract: ContractIdentity

    def __post_init__(self):
        _digest(self.code_sha256, "consumer code sha256")
        _digest(self.environment_sha256, "consumer environment sha256")
        _instance(self.contract, ContractIdentity, "consumer contract")


@dataclass(frozen=True, slots=True)
class CompatibilityRequest:
    artifact: ArtifactIdentity
    runtime: RuntimeIdentity
    target_context: GameContext
    capability: str

    def __post_init__(self):
        _instance(self.artifact, ArtifactIdentity, "artifact")
        _instance(self.runtime, RuntimeIdentity, "runtime")
        _instance(self.target_context, GameContext, "target context")
        _choice(self.capability, CAPABILITIES, "capability")


@dataclass(frozen=True, slots=True)
class CompatibilityRecord:
    """One exact combination and capability; evidence is checked by the caller.

    Support uses the half-open interval [starts_at, review_by). A replacement
    record belongs in a replacement trusted matrix, not a competing/latest row.
    """

    record_id: str
    request: CompatibilityRequest
    validation_state: str
    support_state: str
    evidence_sha256: str | None
    starts_at: datetime
    review_by: datetime
    revoked: bool = False
    target_evidence_sha256: str | None = None

    def __post_init__(self):
        _text(self.record_id, "record id")
        _instance(self.request, CompatibilityRequest, "request")
        _choice(self.validation_state, VALIDATION_STATES, "validation state")
        _choice(self.support_state, SUPPORT_STATES, "support state")
        for name in ("evidence_sha256", "target_evidence_sha256"):
            value = getattr(self, name)
            if value is not None:
                _digest(value, name)
        if self.validation_state == "validated" and self.evidence_sha256 is None:
            raise ValueError("validated record requires evidence digest")
        _aware(self.starts_at, "starts_at")
        _aware(self.review_by, "review_by")
        if self.starts_at >= self.review_by:
            raise ValueError("support interval must have positive duration")
        if type(self.revoked) is not bool:
            raise ValueError("revoked must be bool")


class CompatibilityError(ValueError):
    """Stable rejection reason for callers; no fallback is performed."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


# Deliberately empty. Synthetic examples in tests never register real support.
REAL_COMPATIBILITY_MATRIX: tuple[CompatibilityRecord, ...] = ()


def validate_matrix(matrix):
    """Check immutable structure and ambiguity, not authenticity of any evidence."""
    if type(matrix) is not tuple:
        raise ValueError("compatibility matrix must be an immutable tuple")
    identities, requests = set(), set()
    for record in matrix:
        _instance(record, CompatibilityRecord, "matrix record")
        if record.record_id in identities or record.request in requests:
            raise CompatibilityError("ambiguous_matrix")
        identities.add(record.record_id)
        requests.add(record.request)
    return matrix


def resolve(matrix, request, *, as_of):
    """Resolve exactly one trusted capability registration at an explicit time.

    The caller must validate the artifact/runtime/evidence bytes separately. This
    function never selects a newer model, converts formats, or assumes that an
    artifact readable in one environment remains valid for another game patch.
    """
    _instance(request, CompatibilityRequest, "request")
    _aware(as_of, "as_of")
    records = [record for record in validate_matrix(matrix) if record.request == request]
    if not records:
        raise CompatibilityError("unregistered_combination")
    record = records[0]
    if record.revoked:
        raise CompatibilityError("record_revoked")
    if record.validation_state != "validated":
        raise CompatibilityError("unvalidated_record")
    if record.support_state == "retired":
        raise CompatibilityError("retired_record")
    if not record.starts_at <= as_of < record.review_by:
        raise CompatibilityError("outside_support_window")
    if request.capability == "historical-reproduction":
        if request.target_context != request.artifact.source_context:
            raise CompatibilityError("reproduction_context_changed")
    else:
        if record.support_state == "reproduction-only":
            raise CompatibilityError("reproduction_only")
        if request.target_context.evidence_level == "unknown" or (
            request.capability == "product-advice"
            and request.target_context.evidence_level != "build-confirmed"
        ):
            raise CompatibilityError("target_version_unconfirmed")
    if (
        request.capability != "historical-reproduction"
        or request.target_context != request.artifact.source_context
    ) and record.target_evidence_sha256 is None:
        raise CompatibilityError("missing_target_validation")
    return record
