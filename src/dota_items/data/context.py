"""Data cleaning and evidence verification for versioned replay contexts."""

from ..contracts.replay_context import CHANNELS as CHANNELS
from ..contracts.replay_context import COMBAT_TYPES as COMBAT_TYPES
from ..contracts.replay_context import CONTEXT_SCHEMA as CONTEXT_SCHEMA
from ..contracts.replay_context import VISIBILITY as VISIBILITY
from ..contracts.replay_context import VISIBILITY_CHANNELS as VISIBILITY_CHANNELS
from ..contracts.replay_context import check_channel as check_channel
from ..contracts.replay_context import check_payload as check_payload
from ..contracts.replay_context import context_header as context_header
from ..contracts.replay_context import export_context as export_context


def clean_context(match, config, issue):
    context = match.get("context")
    if context is None:
        return {}
    context_header(context)
    stats = {}
    for channel, rows in context["channels"].items():
        try:
            check_channel(channel, rows, match["duration"], config.max_rows_per_channel)
        except ValueError as error:
            # Losing a visibility transition makes later state unsafe. Disable the
            # whole channel, retain the input evidence, and never claim completeness.
            issue(f"context.channels.{channel}", str(error))
            context["channels"][channel] = None
        retained = context["channels"][channel]
        stats[channel] = {"available": retained is not None, "rows": len(retained or [])}
    return stats


def validate_context(match, evidence, external, resolve_ref):
    context = match.get("context")
    if context is None:
        return
    context_header(context)
    clock = None
    if external and any(context["channels"].values()):
        import gem

        clock = gem.from_dict({"game_clock": evidence.get("game_clock")}).game_clock
    for channel, rows in context["channels"].items():
        check_channel(channel, rows, match["duration"])
        for row in rows or []:
            if external:
                source = resolve_ref(evidence, row["source_ref"])
                if source != row["payload"]:
                    raise ValueError("Context evidence payload mismatch")
                if clock is None or clock.game_seconds_at(row["source_tick"]) != row["time"]:
                    raise ValueError("Context evidence time mismatch")
