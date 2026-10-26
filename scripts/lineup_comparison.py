"""Paired local forms and pre-specified case report; no refit or held-out scoring."""
# ruff: noqa: E501 -- Local HTML presentation literals.

import argparse
import copy
import json
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from lineup_analysis import ROOT, esc, load_inputs

from dota_items.modeling.lineup_comparison import compare
from dota_items.storage import file_hash

CASES = ROOT / "examples/lineup-comparison-cases.json"


def feature_name(column, names):
    side, tail = column.split("_", 1)
    label = "友方" if side == "ally" else "敌方"
    return label + ("未知英雄计数" if tail == "unknown_count" else names.get(int(tail[5:]), tail))


def render(result, names):
    out = ["<p>按变化绝对值排序。概率是购买日志倾向，不是最优推荐；变化是B−A，单位为百分点。</p>"]
    if any(result[k]["unknown_counts"][s] for k in ("a", "b") for s in ("ally", "enemy")):
        out.append('<p class="warn">存在训练词表外英雄：模型只知道未知计数，不理解该英雄。</p>')
    changes = [
        "{}{}：{}".format(
            ("友方" if c["side"] == "ally" else "敌方"),
            ("移除" if c["direction"] == "removed" else "加入"),
            names.get(c["hero_id"], c["hero_id"]),
        )
        for c in result["changes"]
    ]
    out.append("<p>" + esc("；".join(changes) or "两套阵容英雄集合相同") + "</p>")
    out.append(
        f"<p>完整同侧阵容训练支持：A={result['exact_lineup_support']['a']}场，B={result['exact_lineup_support']['b']}场。零精确匹配不等于无法预测，但不能声称见过相同阵容。</p>"
    )
    out.append(
        "<table><tr><th>装备</th><th>A</th><th>B</th><th>B−A（百分点）</th><th>共同频率基线</th></tr>"
    )
    for r in result["items"]:
        out.append(
            f"<tr><td>{esc(r['name'])}</td><td>{r['a']:.1%}</td><td>{r['b']:.1%}</td><td>{r['delta_pp']:+.2f}</td><td>{r['baseline']:.1%}</td></tr>"
        )
    out.append(
        "</table><h3>解释与训练支持</h3><p>贡献变化为log-odds，不是概率百分点。边际支持只表示训练时见过该侧英雄，不是当前完整阵容的可靠性证明；不同英雄组可以重叠。</p>"
    )
    for r in result["items"]:
        out.append(
            f"<details><summary>{esc(r['name'])} · 分数差 {r['delta_logit']:+.4f}</summary><ul>"
        )
        for t in r["contribution_changes"]:
            out.append(
                f"<li>{esc(feature_name(t['feature'], names))}：{t['a']:+.4f} → {t['b']:+.4f}，差 {t['difference']:+.4f}</li>"
            )
        out.append(
            "</ul><table><tr><th>训练英雄组</th><th>比赛数</th><th>有效标签</th><th>记录该装备</th><th>未知</th></tr>"
        )
        for g in result["hero_support"]:
            s = g["items"][r["item"]]
            label = ("友方" if g["side"] == "ally" else "敌方") + str(
                names.get(g["hero_id"], g["hero_id"])
            )
            out.append(
                f"<tr><td>{esc(label)}</td><td>{g['matches']}</td><td>{s['observed']}</td><td>{s['positive']}</td><td>{s['unknown']}</td></tr>"
            )
        out.append("</table></details>")
    return "".join(out)


def document(body):
    return (
        """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>主宰 A/B 阵容实验室</title><style>body{font:16px system-ui;background:#101821;color:#e6edf4;max-width:1200px;margin:auto;padding:24px}p{line-height:1.7}section,details{background:#1a2733;padding:16px;margin:12px 0;border-radius:10px}select,button{padding:8px;margin:4px;background:#263a49;color:white;border:1px solid #587589}table{width:100%;border-collapse:collapse}th,td{padding:9px;text-align:left;border-bottom:1px solid #334655}summary{cursor:pointer}.warn{color:#ffcf85}.pair{display:flex;flex-wrap:wrap;gap:16px}.pair section{flex:1;min-width:300px}a{color:#86d7e8}</style><h1>主宰 A/B 阵容实验室</h1><p>冻结C=0.1 · 11装备源日志行为预测 · 不重训 · 不作为独立评估</p>"""
        + body
        + "</html>"
    )


def default_pair(plan):
    a = copy.deepcopy(plan["base"])
    b = copy.deepcopy(a)
    c = plan["cases"][0]
    b["enemy_hero_ids"] = [
        c["with_enemy"] if h == c["replace_enemy"] else h for h in b["enemy_hero_ids"]
    ]
    return a, b


def form_page(a, b, result, names, error=None):
    out = ['<form method="get" action="/"><div class="pair">']
    for tag, lineup in [("a", a), ("b", b)]:
        out.append(f"<section><h2>阵容{tag.upper()}</h2>")
        for side, label in [("ally", "友方"), ("enemy", "敌方")]:
            out.append(f"<p>{label}</p>")
            for i, chosen in enumerate(lineup[side + "_hero_ids"]):
                out.append(
                    f'<select aria-label="{tag.upper()}{label}{i + 1}" name="{tag}_{side}{i}">'
                )
                for hero in sorted(set(names) | {chosen}):
                    selected = " selected" if hero == chosen else ""
                    out.append(
                        f'<option value="{hero}"{selected}>{esc(names.get(hero, "未知英雄"))} #{hero}</option>'
                    )
                out.append("</select>")
        out.append("</section>")
    out.append(
        '</div><button type="submit">比较两套阵容</button></form><p>建议先只替换一名敌方英雄。位置顺序不代表分路；更换英雄同时改变多个属性，不是控制变量的真实对局实验。</p>'
    )
    if error:
        out.append(
            '<p class="warn">' + esc(error) + "；请检查每方五名英雄、全场不重复、友方包含主宰。</p>"
        )
    if result:
        out.append(render(result, names))
    return document("".join(out))


def handler(inputs, plan):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if urlparse(self.path).path != "/":
                self.send_error(404)
                return
            a, b = default_pair(plan)
            try:
                query = parse_qs(urlparse(self.path).query, strict_parsing=True)
                if query:
                    expected = {
                        f"{tag}_{side}{i}"
                        for tag in ("a", "b")
                        for side in ("ally", "enemy")
                        for i in range(5)
                    }
                    if set(query) != expected or any(len(v) != 1 for v in query.values()):
                        raise ValueError("必须提供20个唯一英雄选择字段")
                    pairs = []
                    for tag in ("a", "b"):
                        pairs.append(
                            dict(
                                target_hero_id=8,
                                ally_hero_ids=[int(query[f"{tag}_ally{i}"][0]) for i in range(5)],
                                enemy_hero_ids=[int(query[f"{tag}_enemy{i}"][0]) for i in range(5)],
                            )
                        )
                    a, b = pairs
                result = compare(a, b, *inputs[:3])
                text, status = form_page(a, b, result, inputs[3]), 200
            except ValueError as exc:
                text, status = form_page(a, b, None, inputs[3], str(exc)), 400
            body = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def run_cases(output, inputs):
    # Require the exact pre-prediction plan, never silently replace it after scoring.
    frozen = output / "cases-before-prediction.json"
    if not frozen.is_file() or file_hash(frozen) != file_hash(CASES):
        raise ValueError("Pre-prediction case plan missing or changed")
    if (output / "results.json").exists() or (output / "started.json").exists():
        raise ValueError("Case output already used; never overwrite")
    started = dict(plan_sha256=file_hash(frozen), started_at=datetime.now(UTC).isoformat())
    with (output / "started.json").open("x") as f:
        json.dump(started, f)
    plan = json.loads(frozen.read_text())
    results = []
    body = [
        "<p>六组预先记录的探索性案例；假设未经用户或补丁机制核验，不作正确率打分。页面包含全部11装备结果，未按成绩挑选案例。</p>",
        f'<p class="warn">{esc(plan["known_task_gap"])}</p>',
    ]
    for case in plan["cases"]:
        a = copy.deepcopy(plan["base"])
        b = copy.deepcopy(a)
        b["enemy_hero_ids"] = [
            case["with_enemy"] if h == case["replace_enemy"] else h for h in b["enemy_hero_ids"]
        ]
        result = compare(a, b, *inputs[:3])
        results.append(dict(case=case, result=result))
        body.append(
            f"<section><h2>{esc(case['question'])}</h2><p>预先假设：{esc(case['expectation'])}</p>"
        )
        for label, lineup in [("A", a), ("B", b)]:
            for side, side_label in [("ally", "友方"), ("enemy", "敌方")]:
                body.append(
                    f"<p>{label}{side_label}：{esc('、'.join(inputs[3].get(h, str(h)) for h in lineup[side + '_hero_ids']))}</p>"
                )
        body.append(render(result, inputs[3]) + "</section>")
    permutation = copy.deepcopy(plan["base"])
    permutation["ally_hero_ids"].reverse()
    perm = compare(plan["base"], permutation, *inputs[:3])
    assert all(abs(r["delta_pp"]) < 1e-12 for r in perm["items"])
    unknown = copy.deepcopy(plan["base"])
    unknown["enemy_hero_ids"][0] = 999999
    unknown_result = compare(plan["base"], unknown, *inputs[:3])
    assert unknown_result["b"]["unknown_counts"]["enemy"] == 1
    payload = dict(
        plan_sha256=started["plan_sha256"],
        cases=results,
        mechanical_checks=dict(permutation_invariant=True, unknown_flagged=True),
        human_judgment="pending",
        training_executed=False,
    )
    (output / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    (output / "index.html").write_text(document("".join(body)))
    if file_hash(frozen) != started["plan_sha256"] or file_hash(CASES) != started["plan_sha256"]:
        raise ValueError("Plan drift during comparison")
    payload_hashes = {p.name: file_hash(p) for p in sorted(output.iterdir()) if p.is_file()}
    with (output / "complete.json").open("x") as f:
        json.dump(
            dict(
                sha256=payload_hashes,
                implementation_sha256={
                    str(p.relative_to(ROOT)): file_hash(p)
                    for p in [
                        Path(__file__).resolve(),
                        ROOT / "scripts/lineup_analysis.py",
                        ROOT / "src/dota_items/modeling/lineup_analysis.py",
                        ROOT / "src/dota_items/modeling/lineup_comparison.py",
                    ]
                },
                independent_evaluation=False,
            ),
            f,
            indent=2,
        )
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    inputs = load_inputs()
    if args.serve:
        if args.output:
            parser.error("Use serve or export, not both")
        plan = json.loads(CASES.read_text())
        print(f"Open http://127.0.0.1:{args.port}", flush=True)
        with HTTPServer(("127.0.0.1", args.port), handler(inputs, plan)) as server:
            server.serve_forever()
    elif args.output:
        run_cases(args.output, inputs)
        print(args.output / "index.html")
    else:
        parser.error("--serve or --output required")


if __name__ == "__main__":
    main()
