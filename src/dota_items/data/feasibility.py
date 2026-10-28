"""Read-only purchase-label feasibility diagnostics, never training admission."""

import hashlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from dota_items.data.contracts import SLOTS, PreparationConfig, StrictContract
from dota_items.data.patch_time import classify_patch_time
from dota_items.data.semantic_review import review_semantics
from dota_items.data.source_io import (
    MAX_BYTES as MAX_BYTES,
)
from dota_items.data.source_io import (
    AuditInputError as AuditInputError,
)
from dota_items.data.source_io import (
    parse_source_json,
    read_source_bytes,
)
from dota_items.normalize import normalize_match
from dota_items.storage import digest, file_hash

AUDITOR_VERSION = "purchase-feasibility/3"
MAX_EVENTS = 200_000


class AuditConfig(StrictContract):
    schema_version: Literal["purchase-feasibility-config/1"] = "purchase-feasibility-config/1"
    hero_id: int = Field(default=8, gt=0)
    requested_patch: Literal["7.41f"] = "7.41f"
    requested_role: Literal[1] = 1
    window_start: int = Field(default=0, ge=0)
    window_end: int = Field(default=1800, gt=0, le=86400)
    candidate_items: Annotated[list[str], Field(min_length=1)] = Field(
        default_factory=lambda: ["bfury", "maelstrom", "manta", "black_king_bar", "skadi"]
    )

    @model_validator(mode="after")
    def check_window_and_items(self):
        if self.window_start >= self.window_end:
            raise ValueError("window_start must precede window_end")
        PreparationConfig(candidate_items=self.candidate_items)
        return self


def _positive_int(value):
    return type(value) is int and value > 0


def _read_bytes(path: Path):
    """Compatibility wrapper; new consumers use source_io directly."""
    return read_source_bytes(path, max_bytes=MAX_BYTES)


def _parse(contents):
    """Compatibility wrapper with unchanged parsing behavior."""
    return parse_source_json(contents)


def audit_file(path: Path, config: AuditConfig) -> dict:
    """Keep one result for every attempted input, including invalid/missing files."""
    row = {
        "input": str(path),
        "match_id": None,
        "status": "invalid",
        "training_allowed": False,
        "reasons": [],
    }
    try:
        contents = _read_bytes(path)
        row["sha256"] = hashlib.sha256(contents).hexdigest()
        raw = _parse(contents)
        row["content_sha256"] = digest(raw)
        if not isinstance(raw, dict) or not _positive_int(raw.get("match_id")):
            raise AuditInputError("match_id must be a positive integer")
        row["match_id"] = raw["match_id"]
        duration = raw.get("duration")
        if type(duration) is not int or not 0 <= duration <= 86400:
            raise AuditInputError("invalid duration")
        patch = raw.get("patch")
        if patch is not None and (type(patch) is not int or patch <= 0):
            raise AuditInputError("OpenDota patch must be a numeric ID or null")
        players = raw.get("players")
        if not isinstance(players, list) or len(players) != 10:
            raise AuditInputError("expected ten players")
        if any(
            not isinstance(p, dict)
            or type(p.get("player_slot")) is not int
            or p["player_slot"] not in SLOTS
            or not _positive_int(p.get("hero_id"))
            for p in players
        ):
            raise AuditInputError("invalid player identity")
        if {p["player_slot"] for p in players} != SLOTS:
            raise AuditInputError("duplicate or missing player slots")
        if len({p["hero_id"] for p in players}) != 10:
            raise AuditInputError("duplicate hero identities")
        row["lineup"] = [
            {"player_slot": p["player_slot"], "hero_id": p["hero_id"]}
            for p in sorted(players, key=lambda p: p["player_slot"])
        ]
        row["duration_seconds"] = duration
        row["patch_id_observed"] = patch
        row["synthetic_marker_present"] = "_fixture" in raw
        row["scope"] = {
            "patch": "unverified",
            "role": "unverified",
            "high_skill": "unverified",
            "note": "Numeric patch ID, lane_role and league/rank hints do not certify scope.",
        }
        receipt = path.with_suffix(".manifest.json")
        row["source_receipt"] = "absent"
        if receipt.exists():
            receipt_bytes = _read_bytes(receipt)
            manifest = _parse(receipt_bytes)
            if (
                not isinstance(manifest, dict)
                or manifest.get("sha256") != row["sha256"]
                or type(manifest.get("match_id")) is not int
                or manifest["match_id"] != raw["match_id"]
            ):
                raise AuditInputError("source receipt hash or identity mismatch")
            row["source_receipt"] = {
                "sha256": hashlib.sha256(receipt_bytes).hexdigest(),
                "source": manifest.get("source"),
                "fetched_at": manifest.get("fetched_at"),
            }
        target = next((p for p in players if p["hero_id"] == config.hero_id), None)
        if target is None:
            row.update(status="out_of_scope", reasons=["target_hero_absent"])
            return row
        log = target.get("purchase_log")
        if isinstance(log, list) and len(log) > MAX_EVENTS:
            raise AuditInputError("purchase log exceeds row limit")
        timeline = normalize_match(
            raw, target["player_slot"], source=str(path), fingerprint="sha256:" + row["sha256"]
        )
        events = timeline.events
        in_window = [e for e in events if config.window_start <= e.time_seconds < config.window_end]
        groups = defaultdict(set)
        for event in in_window:
            groups[event.time_seconds].add(event.item_key)
        counts = Counter(e.item_key for e in in_window)
        row.update(
            status="inspectable",
            target_slot=target["player_slot"],
            scope_hints={
                key: value if type(value) is int else None
                for key, value in {
                    "leagueid": raw.get("leagueid"),
                    "rank_tier": target.get("rank_tier"),
                    "lane_role": target.get("lane_role"),
                    "start_time": raw.get("start_time"),
                }.items()
            },
            purchase_log_status=timeline.purchase_log_status,
            raw_purchase_rows=len(log) if isinstance(log, list) else None,
            valid_purchase_rows=len(events),
            invalid_purchase_rows=sum(
                f.startswith("invalid_event:") for f in timeline.quality_flags
            ),
            purchase_time_range=[events[0].time_seconds, events[-1].time_seconds]
            if events
            else None,
            window_complete_in_duration=duration >= config.window_end,
            observed_keys_in_window=dict(sorted(counts.items())),
            recipe_rows_in_window=sum(n for key, n in counts.items() if key.startswith("recipe_")),
            noncandidate_rows_in_window=sum(
                n for key, n in counts.items() if key not in config.candidate_items
            ),
            simultaneous_distinct_item_times=sorted(
                t for t, keys in groups.items() if len(keys) > 1
            ),
            exact_duplicate_event_rows=len(events)
            - len({(e.time_seconds, e.item_key) for e in events}),
            final_inventory_fields_present=sum(f"item_{i}" in target for i in range(6)),
            additional_item_fields_present=[
                key
                for key in ("inventory_log", "item_usage", "items", "purchase_time")
                if key in target
            ],
            quality_flags=timeline.quality_flags,
            candidates=[
                {
                    "item_key": key,
                    "observation": "observed_purchase" if counts[key] else "unknown",
                    "event_refs": [e.source_event_ref for e in in_window if e.item_key == key],
                    "event_times": [e.time_seconds for e in in_window if e.item_key == key],
                    "completion_label_available": False,
                }
                for key in config.candidate_items
            ],
            reasons=[
                "patch_unverified",
                "role_unverified",
                "high_skill_unverified",
                "purchase_coverage_unverified",
                "completion_semantics_unverified",
            ],
        )
        if not row["window_complete_in_duration"]:
            row["reasons"].append("right_censored")
        if timeline.purchase_log_status != "present":
            row["reasons"].append("purchase_log_" + timeline.purchase_log_status)
        if row["invalid_purchase_rows"]:
            row["reasons"].append("invalid_purchase_events")
        if row["synthetic_marker_present"]:
            row["reasons"].append("synthetic_marker")
        row["semantic_review"] = review_semantics(raw, target, timeline, config.candidate_items)
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        # Raw payload and URL/query strings are deliberately not echoed.
        row.update(
            status="invalid",
            reasons=["invalid_or_unreadable_input"],
            error_type=type(error).__name__,
        )
        if isinstance(error, AuditInputError):
            row["diagnostic"] = str(error)
    return row


def audit_paths(
    paths: list[Path],
    config: AuditConfig,
    *,
    failures: list[dict] | None = None,
    patch_window: dict | None = None,
    expected_ids: dict[Path, int] | None = None,
) -> dict:
    config = AuditConfig.model_validate(config)
    rows = [audit_file(path, config) for path in paths] + list(failures or [])
    for path, row in zip(paths, rows, strict=False):
        expected = (expected_ids or {}).get(path)
        if expected is not None:
            row["requested_match_id"] = expected
            if row["match_id"] != expected:
                row["status"] = "invalid"
                row["reasons"].append("requested_match_identity_mismatch")
        if patch_window is not None and row["status"] == "inspectable":
            check = classify_patch_time(
                row["scope_hints"]["start_time"], row["duration_seconds"], patch_window
            )
            row["patch_time_check"] = check
            if check != "time_consistent":
                row["reasons"].append("patch_time_" + check)
    grouped = defaultdict(list)
    for row in rows:
        if _positive_int(row.get("match_id")):
            grouped[row["match_id"]].append(row)
    for group in grouped.values():
        hashed = [r for r in group if "content_sha256" in r]
        if len({r["content_sha256"] for r in hashed}) > 1:
            # Block every version, not merely the later copy.
            for row in group:
                row["reasons"].append("same_match_conflicting_payloads")
                row["status"] = "conflict"
        elif len(hashed) > 1:
            valid = [r for r in hashed if r["status"] != "invalid"]
            for row in valid[1:]:
                row["reasons"].append("duplicate_match")
                row["status"] = "duplicate"
    usable = [r for r in rows if r["status"] == "inspectable"]
    return {
        "schema_version": "purchase-feasibility-report/1",
        "auditor_version": AUDITOR_VERSION,
        "implementation_sha256": {
            name: file_hash(Path(__file__).resolve().parents[1] / name)
            for name in (
                "data/feasibility.py",
                "data/source_io.py",
                "data/producer_migration.py",
                "data/feasibility_cli.py",
                "data/feasibility_sampling.py",
                "data/patch_time.py",
                "data/semantic_review.py",
                "data/contracts.py",
                "normalize.py",
                "domain.py",
                "storage.py",
            )
        },
        "config": config.model_dump(mode="json"),
        "patch_time_evidence": patch_window,
        "training_allowed": False,
        "limitations": [
            "Inspectable means structural diagnostics only, not verified 7.41f carry data.",
            "Window is exploratory [start,end); absence is unknown, never a negative label.",
            "Purchase records and final inventory do not prove completion or delivery.",
            "Candidate keys are an experiment allowlist, not a verified item catalog.",
        ],
        "summary": {
            "attempted_inputs": len(rows),
            "unique_match_ids": len(grouped),
            "status_counts": dict(sorted(Counter(r["status"] for r in rows).items())),
            "reason_counts": dict(sorted(Counter(x for r in rows for x in r["reasons"]).items())),
            "inspectable_unique_matches": len(usable),
            "purchase_log_present_matches": sum(
                r["purchase_log_status"] == "present" for r in usable
            ),
            "full_window_matches": sum(r["window_complete_in_duration"] for r in usable),
            "patch_time_counts": dict(
                sorted(Counter(r.get("patch_time_check", "not_checked") for r in usable).items())
            ),
            "candidate_observed_match_counts": {
                key: sum(r["observed_keys_in_window"].get(key, 0) > 0 for r in usable)
                for key in config.candidate_items
            },
            "training_admitted_matches": 0,
        },
        "results": rows,
    }
