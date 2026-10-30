"""Apply explicit post-feedback text/questions to a new package, never old inputs."""

import argparse
import json
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return parse_source_json(read_source_bytes(path, max_bytes=64 * 1024**2))


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def revise(output, revision, repo=ROOT):
    if output.exists():
        raise ValueError("Output exists")
    spec = read(revision)
    if spec["schema"] != "decision-review-revision/1" or spec["training_allowed"] is not False:
        raise ValueError("Unsupported review revision")
    relative = Path(spec["base_package"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Invalid base path")
    base = repo / relative
    verified = read(base / "verification.json")
    protected = {**verified["source_files"], str(revision): file_hash(revision)}
    protected[str(base / "verification.json")] = file_hash(base / "verification.json")
    for name, expected in verified["outputs"].items():
        if Path(name).name != name:
            raise ValueError("Invalid base output")
        protected[str(base / name)] = expected
    if file_hash(base / "cases.json") != spec["base_cases_sha256"] or any(
        file_hash(Path(p)) != h for p, h in protected.items()
    ):
        raise ValueError("Frozen source drift")
    package = read(base / "cases.json")
    cards = {c["case"]["id"]: c for c in package["cards"]}
    updates = spec["case_updates"]
    if len({u["case_id"] for u in updates}) != len(updates):
        raise ValueError("Duplicate case update")
    feedback = []
    for update in updates:
        card = cards[update["case_id"]]
        if set(update.get("case_fields", {})) - {
            "attention",
            "action",
            "reason",
            "stop_condition",
            "counterevidence",
        }:
            raise ValueError("Only advice text may change")
        d = card["evidence"]["decision_input"]
        claim = update.get("last_seen_claim")
        if claim:
            players = [p for p in d["positions"] if p["hero_id"] == claim["hero_id"]]
            if len(players) != 1 or players[0]["visibility"] != "hidden":
                raise ValueError("Missing hidden hero claim")
            last = players[0]["last_seen"]
            if not last or any(last[k] != claim[k] for k in claim if k != "hero_id"):
                raise ValueError("Last-seen claim mismatch")
            if d["time"] - last["time"] != claim["age_game_seconds"]:
                raise ValueError("Last-seen age mismatch")
        questions = update["questions"]
        if (
            len(questions) != 4
            or {q["axis"] for q in questions} != {"attention", "action", "stop", "missing"}
            or any(not isinstance(q["prompt"], str) or not q["prompt"].strip() for q in questions)
        ):
            raise ValueError("Four concrete review axes required")
        card["case"].update(update.get("case_fields", {}))
        card["case"]["review_questions"] = questions
        if claim:
            entry = {
                "case_id": update["case_id"],
                "user_feedback_verbatim": spec["user_feedback_verbatim"],
                "verified_last_seen": claim,
                "user_game_interpretation": update["interpretation"],
                "actual_route_or_current_location_verified": False,
                "training_label": None,
                "training_allowed": False,
            }
            card["enhancement"]["review_update"] = entry
            feedback.append(entry)
    package["review_stage"] = "post_feedback_not_blind_not_training_label"
    output.mkdir(parents=True)
    write(output / "cases.json", package)
    write(output / "user-followup.json", {"source": spec["source"], "feedback": feedback})
    for card in package["cards"]:
        name = card["case"]["id"] + "-after.json"
        with (output / name).open("xb") as stream:
            stream.write(read_source_bytes(base / name))
    with (output / "annotation-draft.json").open("xb") as stream:
        stream.write(read_source_bytes(base / "annotation-draft.json"))
    if any(file_hash(Path(p)) != h for p, h in protected.items()):
        raise ValueError("Source drift during revision")
    write(
        output / "verification.json",
        {
            "schema": "decision-review-revision-package/1",
            "source_files": protected,
            "outputs": {p.name: file_hash(p) for p in output.glob("*.json")},
            "implementation": {
                name: file_hash(repo / name)
                for name in (
                    "scripts/revise_decision_review.py",
                    "scripts/decision_review.py",
                    "scripts/decision_review_assets/app.js",
                    "scripts/decision_review_assets/index.html",
                    "scripts/decision_review_assets/style.css",
                )
            },
            "original_decision_input_unchanged": True,
            "training_allowed": False,
        },
    )
    return {"cases": len(cards), "output": str(output)}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--revision", type=Path, required=True)
    args = cli.parse_args()
    print(json.dumps(revise(args.output, args.revision)))
