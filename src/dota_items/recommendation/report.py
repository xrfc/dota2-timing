"""Render existing recommendation values; no ranking or factual inference here."""

from html import escape

from dota_items.recommendation.engine import Analysis
from dota_items.recommendation.knowledge import Bundle


def render_text(analysis: Analysis, bundle: Bundle) -> str:
    result = analysis.recommendation
    request = result.request
    heroes = {h.hero_id: h.name for h in bundle.knowledge.heroes}
    items = {i.item_key: i.name for i in bundle.knowledge.items}
    facts = {f.fact_id: f for f in bundle.knowledge.facts}
    sources = {s.source_id: s for s in bundle.knowledge.sources}
    statuses = {"supported": "首批规则摘录覆盖齐全", "partial": "部分覆盖", "unsupported": "不支持"}
    lines = [
        f"7.41f 阵容装备建议 · {heroes[request.target_hero_id]} · {request.role}号位",
        "实验规则版：条件候选，不是固定出装表或购买顺序。",
        f"状态：{statuses[result.status]}",
        "天辉：" + "、".join(heroes[h] for h in request.radiant),
        "夜魇：" + "、".join(heroes[h] for h in request.dire),
        "",
        "适用范围与局限",
        *(f"- {limit}" for limit in result.limitations),
    ]
    if result.empty_reason:
        lines.extend(["", "没有输出候选：" + result.empty_reason])
    lines.extend(["", "阵容需求与风险（队友能力不代表实际承担）"])
    for need in analysis.needs:
        lines.extend([f"- {need.title} [{need.rule_id}]", "  事实：" + ", ".join(need.fact_ids)])
        lines.extend("  条件：" + condition for condition in need.conditions)
    categories = {"core": "常规核心方向", "situational": "本局针对方向", "alternative": "条件备选"}
    for stage, name in (("early", "早期"), ("mid", "中期"), ("late", "后期")):
        rows = [c for c in result.candidates if c.stage == stage]
        if not rows:
            continue
        lines.extend(["", name + "候选（同阶段按规则分排序，分数不是概率）"])
        for candidate in rows:
            score = sum(c.value for c in candidate.score_components)
            lines.extend(
                [
                    f"- {items[candidate.item_key]} / {categories[candidate.category]}"
                    f" / 规则分 {score:g}",
                    "  理由：" + candidate.reason,
                    *("  条件：" + text for text in candidate.conditions),
                    *("  代价：" + text for text in candidate.tradeoffs),
                    "  依据：" + ", ".join(candidate.fact_ids),
                    "  规则：" + ", ".join(candidate.rule_ids),
                    *(
                        f"  分数组成：{c.name} = {c.value:g}；{c.reason}"
                        for c in candidate.score_components
                    ),
                ]
            )
    lines.extend(["", "未入选与暂缓项"])
    lines.extend(f"- {items[row.item_key]}：{row.reason}" for row in analysis.exclusions)
    lines.extend(["", "逐英雄覆盖（仅首批规则摘录）"])
    labels = {"verified": "摘录已核对", "unknown": "未知", "conflict": "冲突"}
    lines.extend(
        f"- {heroes[row.hero_id]}：{labels[row.status]}；{row.notes}" for row in result.coverage
    )
    lines.extend(["", "事实引用（文字核对，不是实战效果认证）"])
    for evidence in result.evidence:
        fact = facts[evidence.fact_id]
        source = sources[fact.source_id]
        lines.extend(
            [
                f"- {fact.fact_id}：{fact.summary}",
                f"  原文：{fact.quote}",
                f"  来源：{source.url}",
                f"  快照：{evidence.source_ref}",
                f"  SHA-256：{source.sha256}",
            ]
        )
    lines.extend(
        [
            "",
            "复现身份",
            f"输入：{result.input_fingerprint}",
            f"知识：{result.knowledge_version} / {result.knowledge_sha256}",
            f"规则：{result.rules_version} / {result.rules_sha256}",
            f"引擎：{result.engine_version}",
        ]
    )
    return "\n".join(lines) + "\n"


def render_html(analysis: Analysis, bundle: Bundle) -> str:
    # Escape all source/knowledge text. No scripts or external resources.
    result = analysis.recommendation
    names = {h.hero_id: h.name for h in bundle.knowledge.heroes}
    items = {i.item_key: i.name for i in bundle.knowledge.items}
    target = names[result.request.target_hero_id]
    categories = {"core": "核心方向", "situational": "本局针对", "alternative": "条件备选"}
    sections = [
        f"<h1>{escape(target)} · {result.request.role}号位</h1>",
        "<p>7.41f 阵容装备建议 · 实验规则版</p>",
        '<p class="notice">这是带条件的候选清单，不是固定出装或购买顺序。'
        "规则分不是胜率；未输入当前经济、库存或技能状态。</p>",
    ]
    for label, team in (("天辉", result.request.radiant), ("夜魇", result.request.dire)):
        sections.append(f"<p><b>{label}</b>：{escape('、'.join(names[h] for h in team))}</p>")
    missing = [names[row.hero_id] for row in result.coverage if row.status != "verified"]
    if missing:
        sections.append(
            '<p class="notice">知识缺失或冲突：'
            + escape("、".join(missing))
            + "。以下仅为部分分析，不能据此忽略这些英雄的威胁。</p>"
        )
    if result.empty_reason:
        sections.append('<p class="notice">' + escape(result.empty_reason) + "</p>")
    sections.append("<h2>阵容需求与风险</h2><ul>")
    sections.extend("<li>" + escape(need.title) + "</li>" for need in analysis.needs)
    sections.append("</ul>")
    for stage, name in (("early", "早期"), ("mid", "中期"), ("late", "后期")):
        rows = [c for c in result.candidates if c.stage == stage]
        if not rows:
            continue
        sections.append(f'<h2>{name}候选</h2><div class="grid">')
        for row in rows:
            sections.append(
                "<article><h3>"
                + escape(items[row.item_key])
                + '</h3><p class="tag">'
                + categories[row.category]
                + "</p><p>"
                + escape(row.reason)
                + "</p>"
            )
            sections.append("<b>适用条件</b><ul>")
            sections.extend("<li>" + escape(c) + "</li>" for c in row.conditions)
            sections.append("</ul><b>代价与局限</b><ul>")
            sections.extend("<li>" + escape(c) + "</li>" for c in row.tradeoffs)
            sections.append("</ul></article>")
        sections.append("</div>")
    sections.append("<h2>未入选与暂缓项</h2><ul>")
    sections.extend(
        "<li><b>" + escape(items[row.item_key]) + "</b>：" + escape(row.reason) + "</li>"
        for row in analysis.exclusions
    )
    sections.append("</ul><h2>覆盖边界</h2><ul>")
    sections.extend("<li>" + escape(c) + "</li>" for c in result.limitations)
    sections.append(
        "</ul><details><summary>完整事实引用、分数组成与复现身份</summary><pre>"
        + escape(render_text(analysis, bundle))
        + "</pre></details>"
    )
    body = "".join(sections)
    return (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>7.41f 阵容装备建议 · 实验规则版</title>"
        "<style>body{margin:0;background:#101820;color:#e6edf3;font:16px/1.7 system-ui}"
        "main{max-width:1100px;margin:auto;padding:24px}h1,h2,h3{line-height:1.3}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));"
        "gap:16px}article{background:#182632;padding:20px;border-radius:12px}"
        ".notice{border-left:4px solid #e4b363;padding:12px;background:#252d32}"
        ".tag{color:#83d6b5}li{margin-bottom:6px}ul{padding-left:24px}"
        "details{margin-top:24px}summary{cursor:pointer;color:#83d6b5}"
        "pre{font:14px/1.6 monospace;white-space:pre-wrap;overflow-wrap:anywhere}</style>"
        f"<main>{body}</main></html>\n"
    )
