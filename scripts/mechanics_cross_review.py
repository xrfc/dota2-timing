"""Build/check the complete Claude handoff, or compare returned judgments with Codex."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from dota_items.data.mechanics import load_enums, load_vocabulary
from dota_items.data.mechanics_cross_review import (
    compare_reviews,
    json_lines,
    make_cases,
    template_rows,
)
from dota_items.data.mechanics_facts import (
    ENUMS,
    HEROES,
    INPUTS,
    ITEM_TEXT,
    digest,
    load_facts,
)
from dota_items.data.source_io import parse_source_json, read_source_bytes

ROOT = Path(__file__).resolve().parents[1]
BASE = "knowledge/mechanics/extractions/v1/"
REVIEWS = "knowledge/mechanics/reviews/"
V2 = "knowledge/mechanics/vocabulary-v2.json"
RESOLUTION = REVIEWS + "batch-001-resolution.json"
INPUT_FILES = tuple(
    dict.fromkeys(
        (
            *INPUTS,
            V2,
            BASE + "facts-v1.json",
            BASE + "review.csv",
            BASE + "coverage.json",
            RESOLUTION,
            REVIEWS + "batch-001.json",
            REVIEWS + "batch-001-feedback-001.json",
            REVIEWS + "batch-001-feedback-002.json",
            REVIEWS + "targeting-examples-v2.json",
        )
    )
)
IMPLEMENTATION = (
    "src/dota_items/data/mechanics_cross_review.py",
    "scripts/mechanics_cross_review.py",
)
VERSION = "mechanics-cross-review-packet/1"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return parse_source_json(read_source_bytes(path))


def read_lines(path):
    text = read_source_bytes(path).decode("utf-8")
    return [parse_source_json(line.encode()) for line in text.splitlines() if line.strip()]


def new_directory(output):
    output.mkdir(parents=True, exist_ok=False)


def write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def subject_contexts(facts_doc, sources):
    from dota_items.data.mechanics_facts import pointer

    for subject in facts_doc["subjects"]:
        if subject["subject_type"] == "hero_ability":
            data = {"file": HEROES, "path": subject["pointer"]}
            context = pointer(sources[HEROES], subject["pointer"])
        else:
            data = {"file": ITEM_TEXT, "path": "/" + subject["subject"]}
            context = sources[ITEM_TEXT].get(subject["subject"])
        yield {**subject, "context_pointer": data, "context": context}


def condition_text(condition):
    result = [condition["context"]]
    if condition["requires_scepter"]:
        result.append("需要A杖")
    if condition["requires_shard"]:
        result.append("需要魔晶")
    if condition.get("item_ability_type"):
        result.append("装备模式=" + condition["item_ability_type"])
    return "；".join(result)


def build(output, repo=ROOT):
    output = Path(output)
    if output.exists():
        raise ValueError("Output exists; choose a new packet directory")
    raw = {name: read_source_bytes(repo / name) for name in INPUT_FILES}
    sources = {
        name: parse_source_json(value)
        if name.endswith(".json")
        else {"text": value.decode("utf-8")}
        for name, value in raw.items()
    }
    facts = sources[BASE + "facts-v1.json"]
    load_facts(facts, sources)
    vocab = load_vocabulary(sources[V2], load_enums(sources[ENUMS], sources[HEROES]["heroes"]))
    queue = list(csv.DictReader(io.StringIO(raw[BASE + "review.csv"].decode("utf-8"))))
    cases, fields = make_cases(facts, queue, vocab)
    resolution = sources[RESOLUTION]
    manifest = {
        "schema": VERSION,
        "patch_verified": False,
        "input_sha256": {name: sha(value) for name, value in raw.items()},
        "implementation_sha256": {
            name: sha(read_source_bytes(repo / name)) for name in IMPLEMENTATION
        },
        "vocabulary": V2,
    }
    manifest["packet_id"] = digest(manifest)
    summary = {
        "groups": len(cases),
        "pending_evidence_rows": sum(len(c["evidence"]) for c in cases),
        "field_observations": len(fields),
        "total_evidence_rows": len(facts["facts"]),
        "subjects": len(facts["subjects"]),
        "mechanisms": len(vocab),
        "codex_semantically_reviewed": len(resolution["reviews"]),
        "codex_not_yet_reviewed": len(cases) - len(resolution["reviews"]),
        "claude_reviewed": 0,
        "prior_user_audit_rows": 8,
    }
    new_directory(output)
    (output / "cases.jsonl").write_text(json_lines(cases), encoding="utf-8")
    names = {s["subject"]: s for s in facts["subjects"]}
    fields = [
        {
            **f,
            "hero_zh": names[f["subject"]].get("hero_name_zh", ""),
            "name_zh": names[f["subject"]]["name_zh"],
        }
        for f in fields
    ]
    (output / "field-observations.jsonl").write_text(json_lines(fields), encoding="utf-8")
    (output / "subjects.jsonl").write_text(
        json_lines(subject_contexts(facts, sources)), encoding="utf-8"
    )
    (output / "claude-template.jsonl").write_text(
        json_lines(template_rows(cases, manifest["packet_id"])), encoding="utf-8"
    )
    write_json(output / "codex-prior.json", resolution)
    write_json(
        output / "known-user-feedback.json",
        {
            "feedback": [sources[REVIEWS + f"batch-001-feedback-{n:03}.json"] for n in (1, 2)],
            "targeting_examples": sources[REVIEWS + "targeting-examples-v2.json"],
        },
    )
    write_json(output / "coverage.json", sources[BASE + "coverage.json"])
    write_json(output / "vocabulary.json", sources[V2])
    write_json(output / "summary.json", summary)
    # Searchable, short CSV index; full context lives in JSONL, not a truncated quote.
    with (output / "index.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            [
                "queue_index",
                "review_id",
                "hero_zh",
                "name_zh",
                "mechanism_zh",
                "conditions",
                "codex_status",
            ]
        )
        reviewed = {r["review_id"] for r in resolution["reviews"]}
        for case in cases:
            writer.writerow(
                [
                    case["queue_index"],
                    case["review_id"],
                    case["hero_zh"],
                    case["name_zh"],
                    case["mechanism_zh"],
                    condition_text(case["condition"]),
                    "reviewed" if case["review_id"] in reviewed else "not_reviewed",
                ]
            )
    directory = output / "mechanisms"
    directory.mkdir()
    links = []
    for mid, term in vocab.items():
        matching = [c for c in cases if c["mechanism"] == mid]
        links.append(f"| [{term['zh']}](mechanisms/{mid}.md) | {len(matching)} |")
        lines = [
            f"# {term['zh']}：完整候选清单",
            "",
            term["definition"],
            "",
            "以下是证据候选，不含预填的Claude结论。完整上下文见 subjects.jsonl。",
            "",
        ]
        for case in matching:
            name = "·".join(filter(None, [case["hero_zh"], case["name_zh"]]))
            lines += [
                f"## {case['queue_index']}. {name}",
                "",
                f"ID：`{case['review_id']}`",
                "",
                "条件：" + condition_text(case["condition"]),
                "",
            ]
            for fact in case["evidence"]:
                lines += [
                    f"- `{fact['fact_id']}`；{fact['publisher']}；`{fact['evidence_kind']}`",
                    f"- 来源：`{fact['pointer']['file']}#{fact['pointer']['path']}`",
                    "",
                    "~~~~text",
                    fact["quote"],
                    "~~~~",
                    "",
                ]
        (directory / (mid + ".md")).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "README.md").write_text(
        "# Claude复核包\n\n"
        + f"包ID：`{manifest['packet_id']}`\n\n"
        + "交接：[Claude](../../../../docs/handoff/mk-claude-cross-review.md)。\n\n"
        + f"共{len(cases)}组候选、{len(fields)}条字段观测；Codex人工复核24组，其余未审。\n\n"
        + "先读 vocabulary.json、cases.jsonl 和 subjects.jsonl。"
        + "独立填写 claude-template.jsonl 的副本，"
        + "再参考 codex-prior.json 与 known-user-feedback.json 对照。双方相同标签仍需检查条件。\n\n"
        + "index.csv 可按英雄、技能或机制检索。coverage.json保留未命中/无说明清单，"
        + "field-observations.jsonl完整列出结构化字段观测，不把未命中当作无机制。\n\n"
        + "| 机制 | 候选组数 |\n|---|---|\n"
        + "\n".join(links)
        + "\n",
        encoding="utf-8",
    )
    manifest["output_sha256"] = {
        p.relative_to(output).as_posix(): sha(read_source_bytes(p))
        for p in sorted(output.rglob("*"))
        if p.is_file()
    }
    write_json(output / "manifest.json", manifest)
    return summary


def verify(packet, repo=ROOT):
    packet = Path(packet).resolve()
    manifest = read_json(packet / "manifest.json")
    if manifest.get("schema") != VERSION:
        raise ValueError("Unsupported packet schema")
    seed = {k: v for k, v in manifest.items() if k not in ("packet_id", "output_sha256")}
    if digest(seed) != manifest["packet_id"]:
        raise ValueError("Packet identity mismatch")
    if set(manifest["input_sha256"]) != set(INPUT_FILES):
        raise ValueError("Unexpected packet inputs")
    for name, expected in manifest["input_sha256"].items():
        if sha(read_source_bytes(repo / name)) != expected:
            raise ValueError(f"Source snapshot changed: {name}")
    for name, expected in manifest["output_sha256"].items():
        path = (packet / name).resolve()
        if not path.is_relative_to(packet) or Path(name).is_absolute():
            raise ValueError("Unsafe packet path")
        if sha(read_source_bytes(path)) != expected:
            raise ValueError(f"Packet file changed: {name}")
    return manifest


def compare(packet, returned, output, require_complete=False):
    manifest = verify(packet)
    cases = read_lines(Path(packet) / "cases.jsonl")
    prior = read_json(Path(packet) / "codex-prior.json")["reviews"]
    report = compare_reviews(
        cases,
        prior,
        read_lines(Path(returned)),
        manifest["packet_id"],
        require_complete=require_complete,
    )
    new_directory(Path(output))
    write_json(Path(output) / "comparison.json", report)
    counts = report["counts"]
    lines = [
        "# 双AI复核对照",
        "",
        f"Claude已判定 {report['claude_reviewed']}/{report['total_groups']} 组。",
        "",
        "同标签不等于条件一致；未有Codex结论的条目必须回到Codex复核。",
        "",
        "| 状态 | 数量 |",
        "|---|---|",
    ]
    lines += [f"| {key} | {value} |" for key, value in sorted(counts.items())]
    lines += [
        "",
        f"与既有用户二元结论冲突：{report['user_label_conflicts']}。",
        "",
        "完整逐条解释、待审ID、分歧与用户冲突见 comparison.json；不自动修改事实包。",
    ]
    (Path(output) / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {k: v for k, v in report.items() if k != "comparisons"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("build")
    export.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("--packet", type=Path, required=True)
    diff = commands.add_parser("compare")
    diff.add_argument("--packet", type=Path, required=True)
    diff.add_argument("--review", type=Path, required=True)
    diff.add_argument("--output", type=Path, required=True)
    diff.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    if args.command == "build":
        result = build(args.output)
    elif args.command == "verify":
        result = {"packet_id": verify(args.packet)["packet_id"], "verified": True}
    else:
        result = compare(args.packet, args.review, args.output, args.require_complete)
    print(json.dumps(result, ensure_ascii=False))
