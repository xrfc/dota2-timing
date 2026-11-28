"""Render all three local route reviews as a portable Chinese HTML report."""

import argparse
import json
import re
from html import escape
from pathlib import Path
from string import Template
from tempfile import NamedTemporaryFile

from review_b5_farm_routes import JUNGLE, LANE, REPORT_HASHES, UNKNOWN


def gold(window, key):
    if window is None:
        return "窗口不完整"
    return " / ".join(
        "缺测" if window[k][key] is None else str(window[k][key]) for k in ("creep", "neutral")
    )


def route_table(report):
    rows = []
    for row in report["rows"]:
        t = row["t"]
        clock = f"{t // 60:02d}:{t % 60:02d}"
        primary, short = (row["windows"][n] for n in ("30", "20"))
        rows.append(
            f'<tr id="r-{report["match"]}-{t}"><th>{clock} {escape(row["name"])}</th>'
            f"<td>{escape(row['previous'])}</td><td>{escape(row['action'])}"
            f"<small>{escape(row['reason'])}</small></td><td><b>{gold(primary, 'counter')}</b></td>"
            f"<td>{gold(short, 'counter')}</td><td>{gold(primary, 'difference')}<small>"
            f"20 秒　{gold(short, 'difference')}</small></td></tr>"
        )
    return (
        f'<h2>比赛 {report["match"]} <small>{len(rows)} 段</small></h2><div class="scroll"><table>'
        "<thead><tr><th>决策时刻</th><th>旧动作</th><th>走位判定</th>"
        "<th>30 秒实收</th><th>20 秒实收</th><th>30 秒对账差额</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def render(reports):
    ids = [r["match"] for r in reports]
    if sorted(ids) != sorted(REPORT_HASHES) or any(
        r["schema"] != "b5-wave-route/1" or r["report_sha256"] != REPORT_HASHES[r["match"]]
        for r in reports
    ):
        raise ValueError("expected the three registered route reviews")
    rows = [row for r in reports for row in r["rows"]]
    summary = []
    for action in (LANE, JUNGLE, UNKNOWN):
        group = [row for row in rows if row["action"] == action]
        means = []
        for n in ("30", "20"):
            windows = [row["windows"][n] for row in group]
            sums = [
                w["creep"]["counter"] + w["neutral"]["counter"]
                for w in windows
                if w and all(w[k]["counter"] is not None for k in ("creep", "neutral"))
            ]
            means.append(
                f"{sum(sums) / len(sums):.1f} 金（{len(sums)} 段）" if sums else "无完整样本"
            )
        summary.append(
            f"<tr><th>{action}</th><td>{len(group)}</td><td>{means[0]}</td><td>{means[1]}</td></tr>"
        )
    template = Path(__file__).parent / "templates/b5_farm_routes.html"
    tables = "".join(route_table(r) for r in sorted(reports, key=lambda r: r["match"]))
    return Template(template.read_text()).substitute(
        count=len(rows), summary="".join(summary), tables=tables
    )


def install_workbench(path, page):
    """Add the report to the matching local B5 viewer, keeping its installed clip evidence."""
    html = path.read_text()
    evidence = re.search(
        r'<script type="application/json" id="installed-evidence">(.*?)</script>', html, re.S
    )
    if (
        not evidence
        or {m["id"]: m["report_sha256"] for m in json.loads(evidence[1])} != REPORT_HASHES
    ):
        raise ValueError("workbench report fingerprints differ")
    start = "<!-- b5-wave-route start -->"
    end = "<!-- b5-wave-route end -->"
    panel = (
        f'{start}<section id="farm-routes" class="panel" aria-label="收线还是转野">'
        '<iframe sandbox title="三场兵线决策与实收金币复盘" '
        'style="width:100%;height:78vh;border:0" '
        f'srcdoc="{escape(page, quote=True)}"></iframe></section>{end}'
    )
    if html.count(start) == html.count(end) == 1:
        html = re.sub(
            re.escape(start) + ".*?" + re.escape(end), lambda _: panel, html, count=1, flags=re.S
        )
    elif (
        start not in html
        and end not in html
        and html.count("</main>") == 1
        and html.count('<div class="workbench"') == 1
    ):
        html = html.replace(
            '<div class="workbench"',
            '<p><a href="#farm-routes">查看三场兵线决策与实收金币</a></p><div class="workbench"',
        )
        html = html.replace("</main>", panel + "</main>")
    else:
        raise ValueError("unexpected workbench HTML")
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as out:
        out.write(html)
    Path(out.name).replace(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reviews", type=Path, nargs=3)
    parser.add_argument("--install-workbench", type=Path)
    args = parser.parse_args()
    page = render([json.loads(path.read_bytes()) for path in args.reviews])
    if args.install_workbench:
        install_workbench(args.install_workbench, page)
    print(page)
