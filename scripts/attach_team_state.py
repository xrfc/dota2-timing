"""Bind all-hero decision-tick state to a NEW review package; base package stays untouched."""

import argparse
import json
from pathlib import Path

from dota_items.data.decision_team_state import team_state
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = (
    "scripts/attach_team_state.py",
    "src/dota_items/data/decision_team_state.py",
    "src/dota_items/data/decision_state.py",
    "scripts/decision_review.py",
    "scripts/decision_review_assets/app.js",
    "scripts/decision_review_assets/index.html",
    "scripts/decision_review_assets/style.css",
)


def read(path):
    return parse_source_json(read_source_bytes(path, max_bytes=64 * 1024**2))


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _relative(repo, value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Invalid package path")
    return repo / path


def _drifted(protected):
    return any(file_hash(Path(p)) != h for p, h in protected.items())


def attach(output, base, probe, repo=ROOT):
    output, base, probe = (_relative(repo, p) for p in (output, base, probe))
    if output.exists():
        raise ValueError("Output exists")
    verified = read(base / "verification.json")
    protected = {**verified["source_files"]}
    protected[str(base / "verification.json")] = file_hash(base / "verification.json")
    for name, expected in verified["outputs"].items():
        if Path(name).name != name:
            raise ValueError("Invalid base output")
        protected[str(base / name)] = expected
    package = read(base / "cases.json")
    cards = [c for c in package["cards"] if (c.get("enhancement") or {}).get("comparison_card")]
    if not cards:
        raise ValueError("No comparison cards to update")
    for card in cards:
        folder = probe / str(card["case"]["match_id"])
        complete = read(folder / "complete.json")
        if complete["match_id"] != card["case"]["match_id"] or complete["training_allowed"]:
            raise ValueError("Unexpected probe completion")
        protected[str(folder / "complete.json")] = file_hash(folder / "complete.json")
        protected |= {str(folder / n): h for n, h in complete["outputs"].items()}
    if _drifted(protected):
        raise ValueError("Frozen source drift")
    attached = []
    for card in cards:
        case, x = card["case"], card["enhancement"]
        decision = card["evidence"]["decision_input"]
        if decision["tick"] != case["tick"] or x["comparison_card"]["tick"] != case["tick"]:
            raise ValueError("Comparison card is not at the decision tick")
        state = team_state(
            read(probe / str(case["match_id"]) / "capture.json"),
            decision,
            x["comparison_card"]["team_state"],
        )
        target = [c for c in state["cards"] if c["player_slot"] == case["slot"]]
        live = x.get("live_state_card")
        if live and (
            len(target) != 1
            or (target[0]["mana"]["current"], target[0]["mana"]["max"])
            != (live["mana"]["current"], live["mana"]["max"])
        ):
            raise ValueError("Team probe disagrees with repaired target mana")
        state["source_ref"] = str(
            (probe / str(case["match_id"]) / "capture.json").relative_to(repo)
        )
        x["team_live_state"] = state
        attached.append(
            {"case_id": case["id"], "match_id": case["match_id"], "heroes": len(state["cards"])}
        )
    package["team_state_revision"] = {
        "schema": "decision-review-team-state-revision/1",
        "base_package": str(base.relative_to(repo)),
        "probe": str(probe.relative_to(repo)),
        "attached": attached,
        "user_decision": "2026-10-30 option A: allies full, visible enemies mana only",
        "training_allowed": False,
    }
    output.mkdir(parents=True)
    write(output / "cases.json", package)
    copied = {p.name for p in base.glob("*.json")} - {"cases.json", "verification.json"}
    for name in sorted(copied):
        with (output / name).open("xb") as stream:
            stream.write(read_source_bytes(base / name))
    if _drifted(protected):
        raise ValueError("Source drift during attach")
    write(
        output / "verification.json",
        {
            "schema": "decision-review-team-state-package/1",
            "source_files": protected,
            "outputs": {p.name: file_hash(p) for p in output.glob("*.json")},
            "implementation": {name: file_hash(repo / name) for name in IMPLEMENTATION},
            "original_decision_input_unchanged": True,
            "independent_gameplay_units_certified": False,
            "training_allowed": False,
        },
    )
    return {"cases": len(package["cards"]), "attached": attached, "output": str(output)}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", required=True)
    cli.add_argument("--base", required=True)
    cli.add_argument("--probe", required=True)
    args = cli.parse_args()
    print(json.dumps(attach(args.output, args.base, args.probe), ensure_ascii=False))
