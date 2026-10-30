"""Build two post-feedback action-comparison packets from immutable local evidence."""

import argparse
import json
from pathlib import Path

from dota_items.data.decision_comparison import comparison_card
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]


def read(path, large=False):
    return parse_source_json(read_source_bytes(path, max_bytes=(512 if large else 64) * 1024**2))


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def build(output, repo=ROOT):
    if output.exists():
        raise ValueError("Output exists")
    base = repo / "reports/decision-state-cards-2026-10-27-v1"
    audit = repo / "reports/decision-mana-audit-2026-10-27-v1"
    verified = read(base / "verification.json")
    protected = {str(base / "verification.json"): file_hash(base / "verification.json")}
    protected.update(verified["source_files"])
    audit_plan = read(audit / "plan.json")
    protected.update(audit_plan["sources"])
    for name in ("plan.json", "audit.json"):
        protected[str(audit / name)] = file_hash(audit / name)
    for name, expected in verified["outputs"].items():
        if Path(name).name != name:
            raise ValueError("Invalid base output path")
        protected[str(base / name)] = expected
    if any(file_hash(Path(p)) != h for p, h in protected.items()):
        raise ValueError("Frozen input/source drift")
    package = read(base / "cases.json")
    audits = read(audit / "audit.json")
    if not audits["sources_unchanged"]:
        raise ValueError("Incomplete mana audit")
    for card in package["cards"]:
        decision = card["evidence"]["decision_input"]
        raw_path = Path(card["evidence"]["provenance"]["raw"])
        if not raw_path.is_absolute():
            raw_path = repo / raw_path
        expected = card["evidence"]["provenance"]["raw_sha256"]
        if file_hash(raw_path) != expected:
            raise ValueError("Raw mismatch")
        protected[str(raw_path)] = expected
        comparison = comparison_card(
            read(raw_path, True), decision, card["enhancement"]["live_state_card"]
        )
        entries = [r for r in audits["cases"] if r["match_id"] == decision["match_id"]]
        if len(entries) != 1:
            raise ValueError("Missing/ambiguous mana audit")
        comparison["mana_decoder_audit"] = entries[0]
        comparison["annotation"]["case_id"] = card["case"]["id"]
        card["enhancement"]["comparison_card"] = comparison
        card["case"]["status"] = "支援/刷钱条件对照；关键缺口未齐，不强制给动作标签"
    package["review_stage"] = "post_feedback_not_blind_not_training_label"
    output.mkdir(parents=True)
    write(output / "cases.json", package)
    write(
        output / "annotation-draft.json",
        {"cases": [c["enhancement"]["comparison_card"]["annotation"] for c in package["cards"]]},
    )
    for card in package["cards"]:
        name = card["case"]["id"] + "-after.json"
        with (output / name).open("xb") as stream:
            stream.write(read_source_bytes(base / name))
    if any(file_hash(Path(p)) != h for p, h in protected.items()):
        raise ValueError("Input drift")
    implementation = [
        "scripts/build_decision_comparisons.py",
        "src/dota_items/data/decision_comparison.py",
        "src/dota_items/data/decision_evidence.py",
        "scripts/audit_decision_mana.py",
        "scripts/decision_review.py",
        "scripts/decision_review_assets/app.js",
        "scripts/decision_review_assets/index.html",
        "scripts/decision_review_assets/style.css",
    ]
    write(
        output / "verification.json",
        {
            "schema": "decision-comparison-package/1",
            "cases": len(package["cards"]),
            "original_decision_input_unchanged": True,
            "training_allowed": False,
            "source_files": protected,
            "implementation": {name: file_hash(repo / name) for name in implementation},
            "outputs": {p.name: file_hash(p) for p in output.glob("*.json")},
        },
    )
    print(json.dumps({"output": str(output), "cases": len(package["cards"])}))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, required=True)
    build(cli.parse_args().output)
