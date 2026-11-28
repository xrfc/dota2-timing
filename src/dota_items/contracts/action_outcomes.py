"""U191 decision-time contracts; no data access, fitting or artifact authorization."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

METRICS = ("hits", "death", "gold", "xp", "dead_seconds")
DOMAINS = MappingProxyType(
    {
        "wave": (("farm", "retreat"), METRICS),
        "jungle": (("continue_jungle", "leave_camp"), METRICS),
        "support": (("approach", "stay"), (*METRICS, "arrival")),
    }
)
WAVE_STATIC = (
    "time",
    "front_distance",
    "visible_creeps",
    "hp_fraction",
    "mana",
    "ready_saves",
    "recent_damage",
)
OTHER_STATIC = (
    "time",
    "landmark_distance",
    "signal_age",
    "hp_fraction",
    "mana",
    "ready_saves",
    "recent_damage",
    "move_speed",
    "recent_lane_hits",
    "recent_jungle_hits",
)
SEQUENCE = (
    "visible_enemies",
    "nearest_visible_enemy",
    "nearest_ally",
    "missing_10s",
    "self_x",
    "self_y",
    "wave_front_distance",
)


@dataclass(frozen=True)
class ActionTask:
    domain: str
    task_id: str
    actions: tuple[str, ...]
    targets: tuple[str, ...]
    static_features: tuple[str, ...]
    sequence_features: tuple[str, ...] = SEQUENCE
    history_offsets: tuple[int, ...] = (-10, -5, 0)
    action_window: tuple[int, int] = (0, 6)
    outcome_window: tuple[int, int] = (6, 20)
    interval: str = "(start,end]"
    split_id: str = "lane-study-v1"
    folds: int = 5
    gold_definition: str = "wallet_at_t_plus_20_minus_wallet_at_t_plus_6"


def task_spec(domain):
    """Closed registry: schema/labels do not imply verified patch applicability."""
    if type(domain) is not str or domain not in DOMAINS:
        raise ValueError("unregistered action domain")
    arms, targets = DOMAINS[domain]
    return ActionTask(
        domain,
        f"u191-action-{domain}/1",
        arms,
        targets,
        WAVE_STATIC if domain == "wave" else OTHER_STATIC,
    )


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _number(value):
    # Non-finite decision values preserve the old family-specific missing-value rules.
    if value is not None and type(value) not in (int, float):
        raise ValueError("feature values must be Python numbers or None")
    return value


@dataclass(frozen=True)
class DecisionKey:
    match: int
    hero: str
    t: int
    domain: str

    def __post_init__(self):
        _integer(self.match, "match", 1)
        _integer(self.t, "t")
        if type(self.hero) is not str or not self.hero.strip():
            raise ValueError("hero must be a nonempty string")
        task_spec(self.domain)


@dataclass(frozen=True)
class DecisionInput:
    """Feature container; validate_decision applies the full registered task dimensions."""

    key: DecisionKey
    static: tuple
    sequence: tuple

    def __post_init__(self):
        if type(self.key) is not DecisionKey:
            raise ValueError("decision requires a DecisionKey")
        if not isinstance(self.static, (tuple, list)) or not isinstance(
            self.sequence, (tuple, list)
        ):
            raise ValueError("features must be sequences")
        if any(not isinstance(frame, (tuple, list)) for frame in self.sequence):
            raise ValueError("sequence frames must be sequences")
        object.__setattr__(self, "static", tuple(_number(v) for v in self.static))
        object.__setattr__(
            self, "sequence", tuple(tuple(_number(v) for v in f) for f in self.sequence)
        )

    def to_features(self):
        """Return a detached whitelist; keys, outcomes and observed actions are absent."""
        return {"static": list(self.static), "sequence": [list(f) for f in self.sequence]}


def validate_decision(decision):
    if type(decision) is not DecisionInput:
        raise ValueError("expected DecisionInput")
    spec = task_spec(decision.key.domain)
    width = len(spec.sequence_features)
    if (
        len(decision.static) != len(spec.static_features)
        or len(decision.sequence) != len(spec.history_offsets)
        or len(decision.sequence[-1]) != width
        or any(len(f) not in (0, width) for f in decision.sequence[:-1])
    ):
        raise ValueError("decision dimensions differ from the registered task")
    return decision


@dataclass(frozen=True)
class ObservedOutcome:
    """Post-decision truth, available only to explicit evaluation/training callers."""

    key: DecisionKey
    fold: int
    action: str
    values: Mapping
    rank_band: int | str | None = None
    recent_damage: bool | None = None

    def __post_init__(self):
        if type(self.key) is not DecisionKey:
            raise ValueError("observation requires a DecisionKey")
        spec = task_spec(self.key.domain)
        _integer(self.fold, "fold")
        if self.fold >= spec.folds:
            raise ValueError("fold outside registered range")
        if type(self.action) is not str or self.action not in spec.actions:
            raise ValueError("unknown observed action")
        if not isinstance(self.values, Mapping) or not set(self.values) <= set(spec.targets):
            raise ValueError("unknown observed target")
        for value in self.values.values():
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError("observations must be finite numbers or None")
        if self.rank_band is not None and type(self.rank_band) not in (int, str):
            raise ValueError("invalid rank band")
        if self.recent_damage is not None and type(self.recent_damage) is not bool:
            raise ValueError("recent_damage must be bool or None")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


def validate_observed(observation, *, complete=True):
    if type(observation) is not ObservedOutcome:
        raise ValueError("expected ObservedOutcome")
    if complete and set(observation.values) != set(task_spec(observation.key.domain).targets):
        raise ValueError("incomplete observed targets")
    return observation


def _row_key(row, domain):
    if not isinstance(row, Mapping):
        raise ValueError("expected source row mapping")
    selected = domain if domain is not None else row.get("domain")
    if "domain" in row and row["domain"] != selected:
        raise ValueError("source row domain mismatch")
    return DecisionKey(row["match"], row["hero"], row["t"], selected)


def decision_from_row(row, *, domain=None):
    """Select decision fields only; does not certify row provenance or fold membership."""
    return validate_decision(DecisionInput(_row_key(row, domain), row["static"], row["sequence"]))


def observation_from_row(row, *, domain=None):
    key = _row_key(row, domain)
    return validate_observed(
        ObservedOutcome(
            key,
            row["fold"],
            row["action"],
            {k: row[k] for k in task_spec(key.domain).targets},
            row.get("rank_band"),
            row.get("recent_damage"),
        )
    )
