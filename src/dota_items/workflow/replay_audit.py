"""Export provenance-bound offline trajectories and visibility from prepared replays."""

import json
from collections import Counter

from dota_items.storage import file_hash, read_json
from dota_items.workflow.workspace import Workspace


def audit(workspace, expected_id, metadata, output):
    preparations = sorted((workspace / "prepared").glob("*/manifest.json"))
    if len(preparations) != 1:
        raise ValueError("Expected exactly one preparation")
    manifest, folder = Workspace(workspace).preparation(preparations[0].parent.name)
    match = read_json(folder / "cleaned.json")
    if match["match_id"] != expected_id or metadata["match_id"] != expected_id:
        raise ValueError("Match identity mismatch")
    expected = {p["player_slot"]: p["hero_id"] for p in metadata["players"]}
    actual = {p["player_slot"]: p["hero_id"] for p in match["players"]}
    if len(match["players"]) != 10 or len(actual) != 10 or actual != expected:
        raise ValueError("Ten-player hero identity mismatch")
    output.mkdir(parents=True, exist_ok=False)
    raw_hash = file_hash(folder / "raw.json")
    coverage = []
    with (output / "trajectories.jsonl").open("x") as stream:
        for player in match["players"]:
            rows = player["position_log"]
            times = [r["time"] for r in rows]
            if times != sorted(times) or not rows:
                raise ValueError("Empty or unsorted trajectory")
            gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
            coverage.append(
                dict(
                    player_slot=player["player_slot"],
                    hero_id=player["hero_id"],
                    rows=len(rows),
                    first_time=times[0],
                    last_time=times[-1],
                    max_gap_seconds=max(gaps, default=None),
                    zero_time_gaps=sum(g == 0 for g in gaps),
                )
            )
            for row in rows:
                stream.write(
                    json.dumps(
                        dict(
                            match_id=expected_id,
                            player_slot=player["player_slot"],
                            hero_id=player["hero_id"],
                            raw_sha256=raw_hash,
                            **row,
                        )
                    )
                    + "\n"
                )
    channels = match["context"]["channels"]
    visibility = channels.get("hero_visibility_events")
    if visibility is None or not visibility:
        raise ValueError("Hero visibility evidence unavailable")
    with (output / "visibility.jsonl").open("x") as stream:
        for row in visibility:
            stream.write(json.dumps(dict(match_id=expected_id, raw_sha256=raw_hash, **row)) + "\n")
    summary = dict(
        match_id=expected_id,
        preparation_id=manifest["preparation_id"],
        preparation_path=str(folder),
        manifest_sha256=file_hash(folder / "manifest.json"),
        raw_sha256=raw_hash,
        duration=match["duration"],
        players=coverage,
        channel_rows={k: None if v is None else len(v) for k, v in channels.items()},
        visibility_states={
            team: dict(Counter(r["payload"].get(team + "_state", "unknown") for r in visibility))
            for team in ("radiant", "dire")
        },
        observer_sha256=file_hash(folder / "observer.jsonl"),
        quality=read_json(folder / "quality.json"),
        exports={p.name: file_hash(p) for p in output.glob("*.jsonl")},
        training_admission=False,
        semantic_review_required=True,
    )
    (output / "audit.json").write_text(json.dumps(summary, indent=2))
    return summary
