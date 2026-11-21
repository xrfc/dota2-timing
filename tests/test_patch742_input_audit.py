import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from dota_items.data.awareness_split import is_holdout

REPO = Path(__file__).resolve().parents[1]
MID = 9099328699


def save_gzip(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")


def inputs(root, *, state=(0, 1, 2, 3), extras=(0, 1, 2, 3)):
    (root / "meta").mkdir()
    (root / "meta" / f"{MID}.json").write_text(json.dumps({"patch": 61, "match_id": MID}))
    save_gzip(
        root / "parsed" / f"{MID}.normalized.json.gz",
        [
            {
                "schema_version": "gem-adapter/3.1",
                "match_id": MID,
                "duration": 2,
                "context": {
                    "schema_version": "coach-context/1",
                    "channels": {"combat_log": [], "hero_visibility_events": [], "wards": []},
                },
            }
        ],
    )
    save_gzip(
        root / "state-v3" / f"{MID}.jsonl.gz",
        [
            {"schema": "gem-state-capture/3", "match_id": MID, "seconds": len(state)},
            *({"t": t, "heroes": [], "world": {"lane_fronts": {}}} for t in state),
        ],
    )
    save_gzip(
        root / "extras-v1" / f"{MID}.jsonl.gz",
        [
            {"schema": "gem-extras-capture/1", "match_id": MID, "seconds": len(extras)},
            *({"t": t, "creeps": [], "watchers": []} for t in extras),
        ],
    )


def run(root, mid=MID):
    return subprocess.run(
        [
            sys.executable,
            "scripts/audit_patch742_inputs.py",
            "--root",
            str(root),
            "--match",
            str(mid),
        ],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO / "src")},
        capture_output=True,
        text=True,
    )


def test_complete_inputs_report_end_of_match_and_keep_empty_observations(tmp_path):
    inputs(tmp_path, state=(-1, 0, 1, 2, 3))
    result = run(tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["complete_input_coverage"]
    assert report["shared_in_game_seconds"] == 3
    assert report["state_v3"]["pregame_seconds"] == report["state_v3"]["postgame_seconds"] == 1
    assert report["extras_v1"]["in_game_fields"]["creeps_recorded"] == 3
    assert report["extras_v1"]["in_game_fields"]["creeps_nonempty"] == 0


def test_internal_gap_is_incomplete_even_with_later_postgame_rows(tmp_path):
    inputs(tmp_path, extras=(0, 2, 3))
    result = run(tmp_path)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["extras_v1"]["missing_in_game_seconds"] == 1
    assert report["shared_in_game_seconds"] == 2
    assert report["state_only_in_game_seconds"] == 1


@pytest.mark.parametrize(
    "change", ["wrong_patch", "wrong_identity", "duplicate", "missing_header_rows"]
)
def test_incompatible_inputs_are_rejected(tmp_path, change):
    inputs(tmp_path)
    if change == "wrong_patch":
        (tmp_path / "meta" / f"{MID}.json").write_text(json.dumps({"patch": 60, "match_id": MID}))
    else:
        header = {"schema": "gem-extras-capture/1", "match_id": MID, "seconds": 2}
        seconds = [0, 1]
        if change == "wrong_identity":
            header["match_id"] = MID + 1
        if change == "duplicate":
            seconds = [0, 0]
        if change == "missing_header_rows":
            seconds = [0]
        save_gzip(
            tmp_path / "extras-v1" / f"{MID}.jsonl.gz", [header, *({"t": t} for t in seconds)]
        )
    result = run(tmp_path)
    assert result.returncode == 2 and not result.stdout


def test_holdout_is_checked_before_files_are_read(tmp_path):
    result = run(tmp_path, next(i for i in range(1, 100) if is_holdout(i)))
    assert result.returncode == 2 and "non-holdout" in result.stderr
