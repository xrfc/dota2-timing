"""Pure release-time and acquisition contracts; no implicit model compatibility.

The official window is time evidence, not a game-server rollout certificate.
OpenDota's numeric patch and an observed parser build are separate identities.
This module deliberately neither maps one to another nor reads source files.
"""

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime

OFFICIAL_PATCH_URL = "https://www.dota2.com/datafeed/patchnoteslist?language=english"
_PLAYER_SLOTS = frozenset(range(5)) | frozenset(range(128, 133))


def _integer(value, *, minimum=0):
    return type(value) is int and value >= minimum


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _retrieved_timestamp(value):
    if type(value) is not str:
        raise ValueError("patch retrieval time must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("invalid patch retrieval timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("patch retrieval timestamp must include timezone")
    timestamp = int(parsed.timestamp())
    if timestamp <= 0:
        raise ValueError("patch retrieval timestamp must be positive")
    return timestamp


def _patch_name(value):
    return (
        type(value) is str
        and 0 < len(value) <= 64
        and value.strip() == value
        and all(ord(character) >= 32 for character in value)
    )


def _unique_json_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate JSON key: {name}")
        result[name] = value
    return result


@dataclass(frozen=True, slots=True)
class PatchWindow:
    """An exact patch name and hash-bound, conservative observation interval."""

    patch: str
    release_timestamp: int
    upper_exclusive: int
    upper_kind: str
    boundary_buffer_seconds: int
    snapshot_sha256: str
    source_url: str
    retrieved_at: str

    def __post_init__(self):
        retrieved = _retrieved_timestamp(self.retrieved_at)
        if not _patch_name(self.patch):
            raise ValueError("patch must be an explicit nonempty name")
        if not (
            _integer(self.release_timestamp, minimum=1)
            and _integer(self.upper_exclusive, minimum=1)
            and self.release_timestamp < self.upper_exclusive <= retrieved
        ):
            raise ValueError("invalid patch interval or release after retrieval")
        if self.upper_kind not in ("next_release", "snapshot_retrieval"):
            raise ValueError("unknown patch upper-bound evidence")
        if self.upper_kind == "snapshot_retrieval" and self.upper_exclusive != retrieved:
            raise ValueError("latest patch must stop at snapshot retrieval")
        if not _integer(self.boundary_buffer_seconds) or self.boundary_buffer_seconds > 86400:
            raise ValueError("boundary buffer must be an integer between 0 and 86400")
        if type(self.snapshot_sha256) is not str or not re.fullmatch(
            r"[0-9a-f]{64}", self.snapshot_sha256
        ):
            raise ValueError("invalid patch snapshot SHA-256")
        if self.source_url != OFFICIAL_PATCH_URL:
            raise ValueError("patch evidence requires the official source URL")

    @classmethod
    def from_snapshot(
        cls,
        snapshot: bytes,
        *,
        patch: str,
        retrieved_at: str,
        boundary_buffer_seconds: int = 3600,
        source_url: str = OFFICIAL_PATCH_URL,
    ):
        """Validate a saved response; its exact bytes determine its identity."""
        if type(snapshot) is not bytes:
            raise ValueError("patch snapshot must be bytes")
        retrieved = _retrieved_timestamp(retrieved_at)
        try:
            document = json.loads(snapshot, object_pairs_hook=_unique_json_object)
        except (ValueError, UnicodeError) as error:
            raise ValueError("invalid patch snapshot JSON") from error
        rows = document.get("patches") if isinstance(document, dict) else None
        if not isinstance(rows, list) or not rows:
            raise ValueError("patch list must be nonempty")
        if any(
            not isinstance(row, dict)
            or not _patch_name(row.get("patch_number"))
            or not _integer(row.get("patch_timestamp"), minimum=1)
            or row["patch_timestamp"] > retrieved
            for row in rows
        ):
            raise ValueError("invalid release record or release after retrieval")
        names = {row["patch_number"] for row in rows}
        timestamps = {row["patch_timestamp"] for row in rows}
        if len(names) != len(rows) or len(timestamps) != len(rows):
            raise ValueError("ambiguous patch release records")
        if not _patch_name(patch) or patch not in names:
            raise ValueError("requested exact patch absent from snapshot")
        lower = next(row["patch_timestamp"] for row in rows if row["patch_number"] == patch)
        later = [timestamp for timestamp in timestamps if timestamp > lower]
        return cls(
            patch=patch,
            release_timestamp=lower,
            upper_exclusive=min(later) if later else retrieved,
            upper_kind="next_release" if later else "snapshot_retrieval",
            boundary_buffer_seconds=boundary_buffer_seconds,
            snapshot_sha256=hashlib.sha256(snapshot).hexdigest(),
            source_url=source_url,
            retrieved_at=retrieved_at,
        )

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        """Read stored identity, without claiming to verify unseen source bytes."""
        if not isinstance(value, dict) or set(value) != {field.name for field in fields(cls)}:
            raise ValueError("unexpected patch-window fields")
        return cls(**value)

    def discovery_bounds(self, now: int, min_age_hours=2, max_age_hours=96):
        """Age limits constrain start only; the patch interval also constrains end."""
        if (
            not _integer(now, minimum=1)
            or not _number(now)
            or now < _retrieved_timestamp(self.retrieved_at)
        ):
            raise ValueError("selection time must not precede snapshot retrieval")
        if not (
            _number(min_age_hours)
            and _number(max_age_hours)
            and 0 <= min_age_hours < max_age_hours
            and _number(max_age_hours * 3600)
        ):
            raise ValueError("age limits must be finite and ordered")
        end_upper = self.upper_exclusive - (
            self.boundary_buffer_seconds if self.upper_kind == "next_release" else 0
        )
        bounds = {
            "start_lower": max(
                self.release_timestamp + self.boundary_buffer_seconds,
                math.ceil(now - max_age_hours * 3600),
            ),
            "start_upper": min(end_upper, math.ceil(now - min_age_hours * 3600)),
            "end_upper": end_upper,
        }
        self._check_bounds(bounds)
        return bounds

    def _check_bounds(self, bounds):
        if not isinstance(bounds, dict) or set(bounds) != {
            "start_lower",
            "start_upper",
            "end_upper",
        }:
            raise ValueError("unexpected selection-bound fields")
        allowed_end = self.upper_exclusive - (
            self.boundary_buffer_seconds if self.upper_kind == "next_release" else 0
        )
        if not (
            all(_integer(value, minimum=1) for value in bounds.values())
            and self.release_timestamp + self.boundary_buffer_seconds
            <= bounds["start_lower"]
            < bounds["start_upper"]
            <= bounds["end_upper"]
            <= allowed_end
        ):
            raise ValueError("empty or widened selection window")

    def match_time_reasons(self, start, duration, bounds=None):
        if bounds is not None:
            self._check_bounds(bounds)
        if not _integer(start, minimum=1) or not _integer(duration):
            return ["unknown_time"]
        if start < self.release_timestamp or start >= self.upper_exclusive:
            return ["outside_interval"]
        end = start + duration
        if end >= self.upper_exclusive:
            return ["crosses_upper_boundary"]
        reasons = []
        if start < self.release_timestamp + self.boundary_buffer_seconds or (
            self.upper_kind == "next_release"
            and end >= self.upper_exclusive - self.boundary_buffer_seconds
        ):
            reasons.append("boundary_uncertain")
        if bounds is not None and not (
            bounds["start_lower"] <= start < bounds["start_upper"] and end < bounds["end_upper"]
        ):
            reasons.append("outside_selection_window")
        return reasons


def validate_match_metadata(
    meta: dict,
    discovery: dict,
    window: PatchWindow,
    *,
    expected_patch_code: int | None = None,
    bounds: dict | None = None,
    min_rank=70,
    min_duration=900,
):
    """Compare public records only; callers enforce URL, holdout and parser identity."""
    if not isinstance(window, PatchWindow):
        raise ValueError("a validated PatchWindow is required")
    if not _number(min_rank) or min_rank < 0 or not _integer(min_duration, minimum=1):
        raise ValueError("invalid rank/duration policy")
    if expected_patch_code is not None and not _integer(expected_patch_code, minimum=1):
        raise ValueError("expected patch code must be a positive integer or null")
    if not isinstance(meta, dict) or not isinstance(discovery, dict):
        return ["metadata_or_discovery_not_object"]
    reasons = []
    mid = discovery.get("match_id")
    if not _integer(mid, minimum=1) or not _integer(meta.get("match_id"), minimum=1):
        reasons.append("invalid_match_id")
    elif meta["match_id"] != mid:
        reasons.append("match_id_mismatch")
    players = meta.get("players")
    if (
        not isinstance(players, list)
        or len(players) != 10
        or not all(isinstance(player, dict) for player in players)
    ):
        reasons.append("players_incomplete")
    else:
        slots = [player.get("player_slot") for player in players]
        heroes = [player.get("hero_id") for player in players]
        if not all(type(slot) is int for slot in slots) or set(slots) != _PLAYER_SLOTS:
            reasons.append("player_slots_invalid")
        if not all(_integer(hero, minimum=1) for hero in heroes) or len(set(heroes)) != 10:
            reasons.append("heroes_incomplete")
    rank = discovery.get("avg_rank_tier")
    if not _number(rank) or rank < min_rank:
        reasons.append("discovery_rank_missing_or_below_threshold")
    meta_rank = meta.get("avg_rank_tier")
    if meta_rank is not None and (not _number(meta_rank) or meta_rank < min_rank):
        reasons.append("metadata_rank_below_threshold_or_invalid")
    if (
        type(meta.get("lobby_type")) is not int
        or type(meta.get("game_mode")) is not int
        or meta["lobby_type"] != 7
        or meta["game_mode"] != 22
    ):
        reasons.append("not_ranked_all_pick")
    patch_code = meta.get("patch")
    if not _integer(patch_code, minimum=1):
        reasons.append("metadata_patch_missing_or_invalid")
    elif expected_patch_code is not None and patch_code != expected_patch_code:
        reasons.append("metadata_patch_mismatch")
    start, duration = meta.get("start_time"), meta.get("duration")
    if not _integer(duration, minimum=min_duration):
        reasons.append("duration_missing_or_below_threshold")
    if any(
        type(meta.get(key)) is not int
        or type(discovery.get(key)) is not int
        or meta[key] != discovery[key]
        for key in ("start_time", "duration")
    ):
        reasons.append("discovery_metadata_time_mismatch")
    reasons.extend(window.match_time_reasons(start, duration, bounds))
    return reasons
