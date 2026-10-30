"""Join fixed live probes to existing reviewed cases, preserving original decision inputs."""

import argparse
import json
import re
from pathlib import Path

from dota_items.data.decision_state import state_card
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
    base = repo / "reports/decision-enhanced-2026-10-27-v3"
    probes = repo / "reports/decision-live-probe-2026-10-27-v2"
    plan_path = probes / "plan.json"
    plan = read(plan_path)
    protected = {str(plan_path): file_hash(plan_path)}
    for path, expected in plan["sources"].items():
        if file_hash(Path(path)) != expected:
            raise ValueError("Probe source drift")
        protected[path] = expected
    base_verified = read(base / "verification.json")
    for name, expected in base_verified["outputs"].items():
        if Path(name).name != name or file_hash(base / name) != expected:
            raise ValueError("Enhanced package hash mismatch")
        protected[str(base / name)] = expected
    package = read(base / "cases.json")
    for card in package["cards"]:
        decision = card["evidence"]["decision_input"]
        mid = decision["match_id"]
        folder = probes / str(mid)
        complete = read(folder / "complete.json")
        probe_path = folder / "capture.json"
        if (
            complete["plan_sha256"] != file_hash(plan_path)
            or complete["capture_sha256"] != file_hash(probe_path)
            or complete["match_id"] != mid
        ):
            raise ValueError("Incomplete/mismatched live probe")
        protected[str(probe_path)] = complete["capture_sha256"]
        protected[str(folder / "complete.json")] = file_hash(folder / "complete.json")
        path = Path(card["evidence"]["provenance"]["raw"])
        if not path.is_absolute():
            path = repo / path
        expected = card["evidence"]["provenance"]["raw_sha256"]
        if file_hash(path) != expected:
            raise ValueError("Old raw hash mismatch")
        protected[str(path)] = expected
        raw = read(path, True)
        refs = card["evidence"]["state_refs"]
        if len(refs) != 1 or not re.fullmatch(r"coach_state_snapshots\[\d+\]", refs[0]):
            raise ValueError("Ambiguous old state reference")
        index = int(refs[0].split("[")[1][:-1])
        live = state_card(read(probe_path), decision, raw["coach_state_snapshots"][index])
        card["enhancement"]["live_state_card"] = live
        card["case"]["status"] = "真实局部状态取证已接入；条件性方案，非模型结论"
    package["review_stage"] = "反馈后状态卡：旧输入不改，新增来源状态另列"
    if any(file_hash(Path(p)) != h for p, h in protected.items()):
        raise ValueError("Input drift")
    output.mkdir(parents=True)
    write(output / "cases.json", package)
    for card in package["cards"]:
        name = card["case"]["id"] + "-after.json"
        with (output / name).open("xb") as stream:
            stream.write(read_source_bytes(base / name))
    write(
        output / "verification.json",
        {
            "schema": "decision-state-package/1",
            "cases": len(package["cards"]),
            "training_allowed": False,
            "original_decision_input_unchanged": True,
            "source_files": protected,
            "outputs": {p.name: file_hash(p) for p in output.glob("*.json")},
            "implementation": {
                str(p.relative_to(repo)): file_hash(p)
                for p in [
                    repo / "scripts/build_decision_state_cards.py",
                    repo / "src/dota_items/data/decision_state.py",
                    repo / "scripts/decision_review.py",
                    repo / "scripts/decision_review_assets/app.js",
                    repo / "scripts/decision_review_assets/index.html",
                ]
            },
        },
    )
    print(
        json.dumps(
            {
                "cases": len(package["cards"]),
                "protected_files": len(protected),
                "output": str(output),
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
