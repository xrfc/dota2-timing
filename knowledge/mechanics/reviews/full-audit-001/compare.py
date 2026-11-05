"""Compare Claude's and Codex's independent readings with facts v10 (U81). Run from repo root."""

import collections
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
CONTEXT = {"base": "base", "item": "base", "scepter_upgrade": "scepter", "shard_upgrade": "shard"}


def norm_condition(value):
    return "base" if value == "item" else value


def fact_condition(condition):
    label = CONTEXT.get(condition.get("context"), "base")
    if label == "base" and condition.get("requires_scepter"):
        return "scepter"
    if label == "base" and condition.get("requires_shard"):
        return "shard"
    return label


def main():
    doc = json.loads((ROOT / "knowledge/mechanics/extractions/v10/facts-v10.json").read_text())
    objects = {o["subject"]: o for o in json.loads((OUT / "objects.json").read_text())}
    terms = {t["id"]: t["zh"] for t in json.loads((OUT / "vocabulary.json").read_text())}
    facts = collections.defaultdict(list)
    for row in doc["rows"]:
        facts[(row["subject"], row["mechanism"], fact_condition(row["condition"]))].append(row)
    claude = {}
    for line in (OUT / "claude/adds.tsv").read_text(encoding="utf-8").splitlines():
        subject, mechanism, condition, quote = line.split("\t")
        if mechanism not in terms or subject not in objects:
            raise ValueError(f"Bad Claude row: {line}")
        claude[(subject, mechanism, norm_condition(condition))] = quote
    codex = {}
    uncertain = {}
    seen = set()
    for path in sorted((OUT / "results").glob("batch-*.json")):
        for item in json.loads(path.read_text(encoding="utf-8"))["objects"]:
            seen.add(item["subject"])
            for found in item["mechanisms"]:
                if found["mechanism"] not in terms or item["subject"] not in objects:
                    continue
                key = (item["subject"], found["mechanism"], norm_condition(found["condition"]))
                (uncertain if found["uncertain"] else codex)[key] = found["quote"]
    missing = sorted(set(objects) - seen)
    buckets = collections.defaultdict(list)
    for key in sorted(set(claude) | set(codex) | set(uncertain)):
        rows = facts.get(key, [])
        decisions = {row["decision"] for row in rows}
        bases = {row["basis"].split(":")[0] for row in rows}
        in_claude, in_codex = key in claude, key in codex
        entry = {
            "subject": key[0],
            "name_zh": objects[key[0]]["name_zh"],
            "mechanism": key[1],
            "mechanism_zh": terms[key[1]],
            "condition": key[2],
            "claude_quote": claude.get(key),
            "codex_quote": codex.get(key) or uncertain.get(key),
            "codex_uncertain": key in uncertain and not in_codex,
            "existing_basis": sorted(bases),
        }
        if "accept" in decisions:
            buckets["already_accepted"].append(entry)
        elif bases & {"user", "user_spot_check", "field"}:
            buckets["blocked_by_user_or_field"].append(entry)
        elif rows:
            name = "both_vs_two_ai_reject" if in_claude and in_codex else "one_vs_two_ai_reject"
            buckets[name].append(entry)
        elif in_claude and in_codex:
            buckets["new_both"].append(entry)
        elif in_claude:
            buckets["new_claude_only"].append(entry)
        elif in_codex:
            buckets["new_codex_only"].append(entry)
        else:
            buckets["new_codex_uncertain"].append(entry)
    accepted = {key for key in facts if any(r["decision"] == "accept" for r in facts[key])}
    not_reconfirmed = [
        {"subject": key[0], "mechanism": key[1], "condition": key[2]}
        for key in sorted(accepted)
        if key[0] in objects
        and key[1] in terms
        and key not in codex
        and key not in uncertain
        and {r["basis"].split(":")[0] for r in facts[key]} == {"two_ai"}
    ]
    summary = {name: len(rows) for name, rows in sorted(buckets.items())}
    summary["objects_without_codex_result"] = len(missing)
    summary["two_ai_accept_not_found_by_codex"] = len(not_reconfirmed)
    (OUT / "comparison.json").write_text(
        json.dumps(
            {
                "summary": summary,
                "missing": missing,
                "buckets": buckets,
                "two_ai_accept_not_found_by_codex": not_reconfirmed,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
