"""MK-T5 v10: the illusion rows skipped in round 4 reach facts and rule 20."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge/mechanics/extractions/v10"
sys.path.insert(0, str(ROOT / "scripts"))

import build_mechanics_facts_v10 as builder  # noqa: E402

ADDED = {
    "naga_siren_mirror_image",
    "manta",
    "terrorblade_reflection",
    "ringmaster_funhouse_mirror",
    "spectre_haunt",
    "spectre_shadow_step",
    "dark_seer_normal_punch",
}


def test_package_matches_manifest_and_replays(tmp_path):
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    for name, expected in manifest["output_sha256"].items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
    fresh, _ = builder.run(tmp_path / "v10")
    stored = json.loads((PACKAGE / "facts-v10.json").read_text(encoding="utf-8"))
    assert json.dumps(fresh, sort_keys=True) == json.dumps(stored, sort_keys=True)


def test_illusions_added_and_reach_rule_twenty():
    doc = json.loads((PACKAGE / "facts-v10.json").read_text(encoding="utf-8"))
    rows = {
        r["subject"]: r
        for r in doc["rows"]
        if r["mechanism"] == "illusions" and r["origin"] == "t5_correction"
    }
    assert set(rows) == ADDED
    assert all(row["basis"] == "user:U80" for row in rows.values())
    assert rows["manta"]["item_status"] == "purchasable"
    assert rows["manta"]["subject_zh"] == "幻影斧"
    evaluation = json.loads((PACKAGE / "rules-evaluation.json").read_text(encoding="utf-8"))
    rule = next(item for item in evaluation["rules"] if item["id"] == "R20")
    assert ADDED - {"terrorblade_reflection"} <= set(rule["targets"])
    assert "terrorblade_reflection" not in rule["targets"]
