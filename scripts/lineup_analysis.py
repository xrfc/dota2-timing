"""Local form-based prototype using frozen models; no network data, fit or test scores."""

# ruff: noqa: E501 -- HTML/CSS literals kept together for readability.

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dota_items.contracts.tasks import WHOLE_LOG_TASK_ID, task_contract
from dota_items.modeling.artifacts import load_model
from dota_items.modeling.lineup_analysis import analyze
from dota_items.storage import digest, file_hash

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "reports/whole-log-regularization-2026-10-22/logistic_c0_1.model.json"
BASELINE = ROOT / "reports/whole-log-fixed-baseline-2026-10-21/frequency.model.json"
SNAPSHOT = ROOT / "reports/cohort-whole-log-11-2026-10-21/snapshot.json"
HASHES = {
    MODEL: "46262e167a7cd02c68c5edc11708203b9030acb112f162f5d8d61fbc7f0ea5c1",
    BASELINE: "8fce24ca21ab4a6b20c1ca0f0d118bebe188856c5e7dfa49d515ddf0448799ca",
}
DEFAULT = dict(target_hero_id=8, ally_hero_ids=[8, 1, 2, 3, 4], enemy_hero_ids=[10, 11, 12, 13, 14])


def load_inputs():
    for path, expected in HASHES.items():
        if file_hash(path) != expected:
            raise ValueError("Frozen model bytes changed")
    contract = task_contract(WHOLE_LOG_TASK_ID)
    model = load_model(MODEL, expected_task_contract=contract)
    baseline = load_model(BASELINE, expected_task_contract=contract)
    snapshot = json.loads(SNAPSHOT.read_text())
    if digest(snapshot) != model["provenance"]["source_sha256"]:
        raise ValueError("Training snapshot does not match model provenance")
    if snapshot["preprocessing"] != model["preprocessing"]:
        raise ValueError("Snapshot encoding mismatch")
    if snapshot["task"]["contract"] != contract:
        raise ValueError("Snapshot task mismatch")
    names = {}
    for path in (ROOT / "knowledge/hero-capabilities/heroes").glob("*.json"):
        hero = json.loads(path.read_text())
        names[hero["hero_id"]] = hero["name_zh"]
    samples = [r for r in snapshot["samples"] if r["split"] == "train"]
    if len(samples) != 1592:
        raise ValueError("Unexpected training membership")
    return model, baseline, samples, names


def esc(value):
    return html.escape(str(value), quote=True)


def page(lineup, result, names, *, interactive=True, error=None):
    def hero(h):
        return names.get(h, f"未知英雄 #{h}")

    def feature(column):
        side, rest = column.split("_", 1)
        title = "友方" if side == "ally" else "敌方"
        return title + ("未知英雄计数" if rest == "unknown_count" else hero(int(rest[5:])))

    out = [
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>主宰 · 阵容出装分析</title><style>",
        "body{font:16px system-ui;background:#101821;color:#e6edf4;margin:auto;max-width:1100px;padding:28px}",
        "h1{margin-bottom:8px}p{line-height:1.7}.muted{color:#adc0ce}section,details{background:#1a2733;padding:18px;margin:14px 0;border-radius:12px}",
        "select,button{padding:10px;margin:5px;background:#263a49;color:white;border:1px solid #587589;border-radius:6px}",
        "table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #334655}",
        "meter{width:100px}a{color:#86d7e8}.error{color:#ffb0a8}summary{cursor:pointer}small{color:#adc0ce}",
        "</style><h1>主宰 · 阵容出装分析</h1>",
        '<p class="muted">从真实对局学习购买倾向 · 7.41f历史模型 · 赛前研究原型</p>',
        "<p>这里预测的是装备在整局源日志中出现的概率，不是最优出装、胜率或购买顺序。模型尚未完成独立新数据验证。</p>",
    ]
    if interactive:
        out.append('<form action="/" method="get"><section><h2>选择开局阵容</h2>')
        for side, label in [("ally", "友方（包含主宰）"), ("enemy", "敌方")]:
            out.append(f"<p>{label}</p>")
            for i, selected in enumerate(lineup[f"{side}_hero_ids"]):
                out.append(f'<select aria-label="{label}第{i + 1}位" name="{side}{i}">')
                for h in sorted(set(names) | {selected}):
                    flag = " selected" if h == selected else ""
                    out.append(f'<option value="{h}"{flag}>{esc(hero(h))} #{h}</option>')
                out.append("</select>")
        out.append(
            '<p><button type="submit">分析这套阵容</button> 修改一位英雄后重新分析，可比较概率变化。</p></section></form>'
        )
    else:
        for side, label in [("ally", "友方"), ("enemy", "敌方")]:
            out.append(
                f"<p>{label}：{esc('、'.join(hero(h) for h in lineup[side + '_hero_ids']))}</p>"
            )
    if error:
        out.append(
            f'<p class="error">输入无法分析：{esc(error)}。请确保10位英雄不重复，友方包含主宰。</p>'
        )
    if result:
        if any(result["unknown_counts"].values()):
            out.append(
                '<p class="error">含训练词表外英雄：模型只保留未知计数，不理解该英雄身份；以下结果仅供观察。</p>'
            )
        out.append(
            "<section><h2>模型购买倾向</h2><p>按概率排序，不是出装顺序。差值单位为百分点；基线是不看阵容的训练购买比例。</p><table><tr><th>装备</th><th>模型概率</th><th>频率基线</th><th>差值</th></tr>"
        )
        for r in result["items"]:
            out.append(
                f'<tr><td>{esc(r["name"])}</td><td>{r["probability"]:.1%} <meter min="0" max="1" value="{r["probability"]}"></meter></td><td>{r["baseline"]:.1%}</td><td>{r["delta_pp"]:+.2f}</td></tr>'
            )
        out.append(
            "</table></section><h2>模型为什么给出这个数？</h2><p>下面是可精确复算的线性分数贡献（log-odds），不是概率百分点，也不是英雄克制的因果证明。贡献之和解释模型自身，不等于相对频率基线差值的分解。</p>"
        )
        for r in result["items"]:
            out.append(
                f"<details><summary>{esc(r['name'])} · 查看阵容贡献</summary><p>训练正例 {r['support']['positive']}/{r['support']['observed']}；截距 {r['intercept']:+.4f}；总分 {r['logit']:+.4f}</p><table><tr><th>输入因素</th><th>分数贡献</th></tr>"
            )
            for t in r["contributions"]:
                out.append(
                    f"<tr><td>{esc(feature(t['feature']))}</td><td>{t['contribution']:+.4f}</td></tr>"
                )
            out.append(
                "</table><small>概率 = sigmoid(截距 + 全部贡献)。独立逐装备模型不保证组合合理，不输出六神装排序。</small></details>"
            )
        out.append(
            "<section><h2>训练集中的相近阵容</h2><p>只按同侧英雄重合数选前3场，排除固定主宰后满分9；并列按比赛ID。不是同局势、最佳出装或独立评估证据。</p>"
        )
        for c in result["cases"]:
            out.append(f"<details><summary>比赛 {c['match_id']} · 重合 {c['overlap']}/9</summary>")
            for side, label in [("ally", "友方"), ("enemy", "敌方")]:
                out.append(
                    f"<p>{label}：{esc('、'.join(hero(h) for h in c['features'][side + '_hero_ids']))}</p>"
                )
            out.append(
                f"<p>日志记录的目标装备：{esc('、'.join(c['observed_items']) or '无')}</p><p>未知标签：{esc('、'.join(c['unknown_items']) or '无')}</p><small>训练案例；未列出的装备不代表真实未买。源SHA-256：{esc(c['source_sha256'])}</small></details>"
            )
        out.append(
            "</section><section><h2>这离出装建议还差什么？</h2><p>当前没有验证购买顺序、装备组合、对线位置、命石、局中经济或推荐收益。不会用“模型概率高”直接断言“这局应该买”。英雄机制解释尚未接入经版本核验的证据，本页不自动生成克制理由。</p><p>试用时重点检查：换敌方英雄后哪些装备变化？解释是否与概率一致？相近案例是否其实很不相近？这些问题用来指导下一轮特征研究，而不是再盲目调C。</p></section>"
        )
    out.append(
        "<footer>冻结C=0.1与frequency · 无重训 · 不读取前瞻评估集 · 无账号信息展示</footer></html>"
    )
    return "".join(out)


def make_handler(inputs):
    model, baseline, samples, names = inputs

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if urlparse(self.path).path != "/":
                self.send_error(404)
                return
            lineup = DEFAULT
            try:
                query = parse_qs(urlparse(self.path).query, strict_parsing=True)
                if query:
                    expected = {f"{s}{i}" for s in ("ally", "enemy") for i in range(5)}
                    if set(query) != expected or any(len(v) != 1 for v in query.values()):
                        raise ValueError("需要完整且唯一的10个英雄选择")
                    lineup = dict(
                        target_hero_id=8,
                        ally_hero_ids=[int(query[f"ally{i}"][0]) for i in range(5)],
                        enemy_hero_ids=[int(query[f"enemy{i}"][0]) for i in range(5)],
                    )
                result = analyze(lineup, model, baseline, samples)
                body, status = page(lineup, result, names), 200
            except ValueError as exc:
                body, status = page(lineup, None, names, error=str(exc)), 400
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--lineup", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    inputs = load_inputs()
    if args.serve:
        if args.lineup or args.output:
            parser.error("--serve cannot be combined with export options")
        print(f"Open http://127.0.0.1:{args.port} ; Ctrl+C to stop", flush=True)
        with HTTPServer(("127.0.0.1", args.port), make_handler(inputs)) as server:
            server.serve_forever()
    else:
        if not args.output:
            parser.error("--output required for export")
        lineup = json.loads(args.lineup.read_text()) if args.lineup else DEFAULT
        result = analyze(lineup, *inputs[:3])
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        (args.output / "index.html").write_text(page(lineup, result, inputs[3], interactive=False))
        print(args.output / "index.html")


if __name__ == "__main__":
    main()
