"""Rebuild a closed 7.42 candidate from registered engineering evidence."""

import argparse
import hashlib
import json
import tempfile
from html import escape
from pathlib import Path

from dota_items.data.atomic_directory import publish_directory
from dota_items.data.mechanics_evidence_admission import build_evidence_admission
from dota_items.data.mechanics_evidence_projection import project_evidence_assets
from dota_items.data.mechanics_evidence_source import MechanicsEvidenceSource
from dota_items.data.patch_asset_evidence import EvidencePins
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]
PRODUCER_FILES = (
    "scripts/build_mechanics_evidence_assets.py",
    "src/dota_items/__init__.py",
    "src/dota_items/contracts/__init__.py",
    "src/dota_items/data/__init__.py",
    "src/dota_items/data/atomic_directory.py",
    "src/dota_items/data/map_replay_source.py",
    "src/dota_items/data/mechanics_engineering_evidence.py",
    "src/dota_items/data/mechanics_evidence_admission.py",
    "src/dota_items/data/mechanics_evidence_projection.py",
    "src/dota_items/data/mechanics_evidence_source.py",
    "src/dota_items/data/patch_asset_evidence.py",
    "src/dota_items/data/source_io.py",
    "src/dota_items/storage.py",
)


def render_report(admission, summary):
    rows = []
    for fact in admission["rows"]:
        evidence = fact.get("engineering_admission")
        if evidence is None:
            continue
        cells = [
            fact["review_id"],
            evidence["operation"],
            "候选可用" if fact["candidate_usable"] else "证据不足",
            json.dumps(evidence["conditions"], ensure_ascii=False),
            ", ".join(evidence["unproven_capabilities"]),
        ]
        rows.append("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in cells) + "</tr>")
    return f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>7.42机制证据准入核验</title>
<style>body{{font:16px/1.6 system-ui;max-width:1300px;margin:30px auto;padding:0 16px}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:8px}}
td{{overflow-wrap:anywhere}}pre{{white-space:pre-wrap}}.notice{{background:#fff1cc;padding:12px}}</style>
<h1>7.42机制证据准入核验</h1>
<p class="notice">工程候选：没有新增用户裁定，未开放正式复盘或训练。</p>
<p>只消费登记来源的14条补证；能选择敌方单位不自动证明格挡或反弹交互。
受影响的旧克制关系和特性仍等待完整条件求值，未知保持未知。</p>
<p><a href="receipt.json">来源回执</a> · <a href="mechanics-admission.json">新准入</a> ·
<a href="mechanics-capabilities.json">带条件的能力集合</a> ·
<a href="mechanics-counter_graph.json">保守重投影的克制候选</a></p>
<table><thead><tr><th>事实ID</th><th>更新类型</th><th>状态</th><th>条件</th><th>尚未证明</th>
</tr></thead><tbody>{"".join(rows)}</tbody></table>
<p>感染的吸血和治疗标签归入同一回血效果；这不是实际触发次数或效果量统计。
正式知识入口仍为7.41f。</p>
<h2>派生核对</h2><pre>{escape(json.dumps(summary, ensure_ascii=False, indent=2))}</pre>
</html>"""


def run(spec_path, output, *, repository_root=ROOT):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists")
    initial = EvidencePins()
    spec_ref = initial.track(Path(spec_path).absolute())
    spec = initial.read(spec_ref)
    if (
        set(spec) != {"schema", "exact_patch", "baseline_receipt", "engineering_evidence"}
        or spec["schema"] != "mechanics-evidence-assets-spec/1"
        or spec["exact_patch"] != "7.42"
    ):
        raise ValueError("Explicit registered exact-patch specification required")
    source = MechanicsEvidenceSource(
        spec["baseline_receipt"], spec["engineering_evidence"], repository_root=repository_root
    )
    source.pins.add(spec_ref)
    for filename in PRODUCER_FILES:
        source.pins.track(repository_root / filename)
    admission = build_evidence_admission(
        source.baseline,
        source.engineering,
        source.documents,
        exact_patch="7.42",
        source_refs=source.refs,
    )
    admission_bytes = (
        json.dumps(admission, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode()
    source_refs = {
        "baseline_receipt": spec["baseline_receipt"],
        "engineering_evidence": spec["engineering_evidence"],
        "admission": {
            "path": str(output / "mechanics-admission.json"),
            "sha256": hashlib.sha256(admission_bytes).hexdigest(),
        },
        **{f"baseline_{key}": ref for key, ref in source.asset_refs.items()},
    }
    projected = project_evidence_assets(
        source.baseline,
        admission,
        source.assets,
        exact_patch="7.42",
        source_refs=source_refs,
        engineering_evidence=source.engineering,
        documents=source.documents,
    )
    summary = projected.pop("summary")
    payloads = {"mechanics-admission.json": admission, "projection-summary.json": summary}
    payloads.update({f"mechanics-{key}.json": doc for key, doc in projected.items()})
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mechanics-evidence-", dir=output.parent) as temp:
        staging = Path(temp) / "result"
        staging.mkdir()
        for filename, document in payloads.items():
            (staging / filename).write_text(
                json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            )
        if file_hash(staging / "mechanics-admission.json") != source_refs["admission"]["sha256"]:
            raise ValueError("New admission output differs from derived dependency reference")
        (staging / "report.html").write_text(render_report(admission, summary))
        source.verify()
        receipt = {
            "schema": "mechanics-evidence-assets-receipt/1",
            "exact_patch": "7.42",
            "spec": spec_ref,
            "used_files": source.pins.inventory,
            "output_sha256": {p.name: file_hash(p) for p in sorted(staging.iterdir())},
            "formal_use_allowed": False,
            "training_allowed": False,
            "action_review_allowed": False,
        }
        (staging / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        publish_directory(staging, output)
    return {"admission": admission["summary"], "projection": summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.spec, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
