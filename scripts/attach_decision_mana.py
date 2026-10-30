"""Bind redecoded decision-tick mana to a NEW review package; base package stays untouched."""

import argparse
import json
from pathlib import Path

from dota_items.data.decision_mana import attach_current_mana
from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = (
    "scripts/attach_decision_mana.py",
    "src/dota_items/data/decision_mana.py",
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


def _protected_base(base):
    verified = read(base / "verification.json")
    protected = {**verified["source_files"]}
    protected[str(base / "verification.json")] = file_hash(base / "verification.json")
    for name, expected in verified["outputs"].items():
        if Path(name).name != name:
            raise ValueError("Invalid base output")
        protected[str(base / name)] = expected
    return verified, protected


def _protected_repair(repair, match_ids):
    acceptance = read(repair / "acceptance.json")
    if acceptance["training_performed"] is not False:
        raise ValueError("Unexpected repair acceptance")
    protected = {str(repair / "acceptance.json"): file_hash(repair / "acceptance.json")}
    protected |= {str(repair / n): h for n, h in acceptance["outputs"].items()}
    for match_id in match_ids:
        folder = repair / str(match_id)
        complete = read(folder / "complete.json")
        if complete["match_id"] != match_id or complete["training_allowed"] is not False:
            raise ValueError("Unexpected repair completion")
        protected[str(folder / "complete.json")] = file_hash(folder / "complete.json")
        protected |= {str(folder / n): h for n, h in complete["outputs"].items()}
    return protected


def _drifted(protected):
    return any(file_hash(Path(p)) != h for p, h in protected.items())


def attach(output, base, repair, repo=ROOT):
    output, base, repair = (_relative(repo, p) for p in (output, base, repair))
    if output.exists():
        raise ValueError("Output exists")
    _, protected = _protected_base(base)
    package = read(base / "cases.json")
    live_cards = [
        c for c in package["cards"] if (c.get("enhancement") or {}).get("live_state_card")
    ]
    if not live_cards:
        raise ValueError("No state cards to update")
    protected |= _protected_repair(repair, [c["case"]["match_id"] for c in live_cards])
    if _drifted(protected):
        raise ValueError("Frozen source drift")
    attached = []
    for card in live_cards:
        case, x = card["case"], card["enhancement"]
        folder = repair / str(case["match_id"])
        if x["live_state_card"]["tick"] != case["tick"]:
            raise ValueError("State card is not at the decision tick")
        resource = read(folder / "current-resource.json")
        if resource["match_id"] != case["match_id"]:
            raise ValueError("Resource match mismatch")
        x["live_state_card"] = attach_current_mana(
            x["live_state_card"],
            resource,
            read(folder / "capture.json"),
            read(folder / "comparison.json"),
            str((folder / "current-resource.json").relative_to(repo)),
        )
        attached.append({"case_id": case["id"], "match_id": case["match_id"], "tick": case["tick"]})
    package["resource_revision"] = {
        "schema": "decision-review-mana-revision/1",
        "base_package": str(base.relative_to(repo)),
        "repair": str(repair.relative_to(repo)),
        "attached": attached,
        "independent_gameplay_units_certified": False,
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
            "schema": "decision-review-mana-package/1",
            "source_files": protected,
            "outputs": {p.name: file_hash(p) for p in output.glob("*.json")},
            "implementation": {name: file_hash(repo / name) for name in IMPLEMENTATION},
            "original_decision_input_unchanged": True,
            "independent_gameplay_units_certified": False,
            "training_allowed": False,
        },
    )
    return {"cases": len(package["cards"]), "attached": len(attached), "output": str(output)}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", required=True)
    cli.add_argument("--base", required=True)
    cli.add_argument("--repair", required=True)
    args = cli.parse_args()
    print(json.dumps(attach(args.output, args.base, args.repair), ensure_ascii=False))
