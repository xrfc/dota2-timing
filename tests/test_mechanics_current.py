import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from dota_items.data.mechanics_current import load_current, read_current

ROOT = Path(__file__).resolve().parents[1]
MECH = ROOT / "knowledge/mechanics"


def _latest(pattern, directory):
    numbers = [int(m.group(1)) for p in directory.iterdir() if (m := re.fullmatch(pattern, p.name))]
    return max(numbers)


def test_current_json_is_up_to_date_and_valid():
    subprocess.run(
        [sys.executable, "scripts/build_mechanics_current.py", "--check"], cwd=ROOT, check=True
    )
    doc = load_current(ROOT)
    assert doc["patch"]["verified"] is True
    assert (ROOT / doc["patch"]["evidence"]).is_file()
    assert read_current("rules", ROOT)["version"]


def test_current_points_to_the_newest_versions():
    entries = load_current(ROOT)["entries"]
    vocab = _latest(r"vocabulary-v(\d+)\.json", MECH)
    rules = _latest(r"rules-v(\d+)\.json", MECH)
    facts = _latest(r"v(\d+)", MECH / "extractions")
    derived = _latest(r"derived-v(\d+)", MECH / "profiles")
    assert entries["vocabulary"]["path"].endswith(f"vocabulary-v{vocab}.json")
    assert entries["rules"]["path"].endswith(f"rules-v{rules}.json")
    assert entries["facts"]["path"].endswith(f"v{facts}/facts-v{facts}.json")
    assert f"derived-v{derived}/" in entries["counter_graph"]["path"]


def test_facts_manifest_reads_the_current_vocabulary_and_rules():
    entries = load_current(ROOT)["entries"]
    receipt = json.loads((ROOT / entries["facts"]["manifest"]).read_text())
    for name in ("vocabulary", "rules"):
        assert receipt["input_sha256"][entries[name]["path"]] == entries[name]["sha256"]


def _copy(tmp_path):
    entries = json.loads((MECH / "current.json").read_text())["entries"]
    for entry in entries.values():
        for key in ("path", "manifest"):
            if key in entry:
                target = tmp_path / entry[key]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / entry[key], target)
    (tmp_path / "knowledge/mechanics/current.json").write_text((MECH / "current.json").read_text())
    return entries


def test_edited_or_missing_files_raise(tmp_path):
    entries = _copy(tmp_path)
    load_current(tmp_path)
    (tmp_path / entries["rules"]["path"]).write_text("{}")
    with pytest.raises(ValueError, match="rules: .* hash differs"):
        load_current(tmp_path)
    (tmp_path / entries["rules"]["path"]).unlink()
    with pytest.raises(ValueError, match="does not exist"):
        load_current(tmp_path)


def test_output_must_match_its_build_manifest(tmp_path):
    entries = _copy(tmp_path)
    manifest = tmp_path / entries["facts"]["manifest"]
    receipt = json.loads(manifest.read_text())
    receipt["output_sha256"]["facts-v25.json"] = "0" * 64
    manifest.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="build manifest"):
        load_current(tmp_path)
    with pytest.raises(KeyError):
        read_current("nope", ROOT)
