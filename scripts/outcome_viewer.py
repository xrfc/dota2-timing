"""Serve verified B5 match reports as a read-only, local timeline."""

import argparse
import hashlib
import json
import re
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).with_name("outcome_viewer_assets")
MAP_IMAGE = ROOT / "data/map-reference-2026-10-26-v1/gem/assets/maps/Game_map_7.41.jpg"
DOMAINS = ("兵线", "打野", "支援")
COUNT_KEYS = ("opportunities", "eligible", "supported", "balanced")
TIME = r"[0-9]+:[0-5][0-9]"
CLIP_HEADING = re.compile(rf"({TIME})\s+(.+?) · (兵线|打野|支援)")
PORTRAITS = ("phantom_assassin", "sven", "windrunner", "life_stealer")


def read_table(lines, first, headers):
    """Read the specific pipe tables emitted by outcome_match_report."""

    def cells(line):
        if not line.startswith("|") or not line.endswith("|"):
            raise ValueError("复盘表格格式不完整")
        return [cell.strip() for cell in line[1:-1].split("|")]

    if first + 1 >= len(lines) or cells(lines[first]) != headers:
        raise ValueError("复盘表头与当前报告格式不符")
    separator = cells(lines[first + 1])
    if len(separator) != len(headers) or not all(re.fullmatch(r":?-{3,}:?", s) for s in separator):
        raise ValueError("复盘表格列数与表头不符")
    end = first + 2
    rows = []
    while end < len(lines) and lines[end].startswith("|"):
        row = cells(lines[end])
        if len(row) != len(headers) or not all(row):
            raise ValueError("复盘表格存在缺列或空单元格")
        rows.append(row)
        end += 1
    return rows, end


def parse_overview(lines):
    counts, excluded, notes = [], [], []
    heroes = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("| 场景 |"):
            rows, i = read_table(
                lines, i, ["场景", "候选机会", "可复盘", "有双动作支持", "可比较两种动作"]
            )
            for domain, *values in rows:
                numbers = [int(value) for value in values]
                if numbers != sorted(numbers, reverse=True) or min(numbers) < 0:
                    raise ValueError("候选及可评段数存在矛盾")
                counts.append({"domain": domain, **dict(zip(COUNT_KEYS, numbers, strict=True))})
            continue
        if line.startswith("| 时间 |"):
            rows, i = read_table(lines, i, ["时间", "一号位", "场景", "动作", "排除原因"])
            keys = ("time", "hero", "domain", "action", "reason")
            excluded.extend(dict(zip(keys, row, strict=True)) for row in rows)
            continue
        if line.startswith("录像识别的一号位："):
            value = line.removeprefix("录像识别的一号位：").removesuffix("。")
            heroes = [] if value == "未能识别" else value.split("、")
        elif line.startswith("|"):
            raise ValueError("报告含未知统计表")
        elif line and line != "### 未进入复盘的候选":
            notes.append(line)
        i += 1
    if heroes is None or [row["domain"] for row in counts] != list(DOMAINS):
        raise ValueError("报告缺少完整的一号位或三类取样统计")
    return dict(heroes=heroes, counts=counts, excluded=excluded, notes=notes)


def parse_clip(section):
    heading, _, body = section.partition("\n")
    identity = CLIP_HEADING.fullmatch(heading)
    if not identity:
        raise ValueError(f"无法识别片段标题 {heading}")
    time, hero, domain = identity.groups()
    lines = body.splitlines()
    actions = [line for line in lines if line.startswith("观察到的动作：")]
    tables = [i for i, line in enumerate(lines) if line.startswith("| 来源 |")]
    if len(actions) != 1 or len(tables) != 1:
        raise ValueError(f"{time} 的动作或结果表不完整")
    first = tables[0]
    metrics = [
        {"兵线": "线上补刀", "打野": "野怪补刀", "支援": "线上与野怪补刀"}[domain],
        "现金净变化（金）",
        "同等级经验变化",
        "死亡",
        "死亡占用（秒）",
    ]
    if domain == "支援":
        metrics.append("队友受击时到场")
    rows, end = read_table(lines, first, ["来源", *metrics])
    if len(rows) not in (1, 3) or rows[0][0] != "录像实况":
        raise ValueError(f"{time} 的实况或双动作估计行不完整")
    labels = [row[0] for row in rows[1:]]
    if len(set(labels)) != len(labels) or not all(label.endswith("估计") for label in labels):
        raise ValueError(f"{time} 的估计行标签无效")
    notes = [line for line in lines[:first] + lines[end:] if line and line != actions[0]]
    return dict(
        time=time,
        hero=hero,
        domain=domain,
        action=actions[0].removeprefix("观察到的动作：").removesuffix("。"),
        metrics=metrics,
        rows=[dict(label=label, values=values) for label, *values in rows],
        notes=notes,
    )


def parse_report(path):
    match_id = path.parent.name
    source = path.read_bytes()
    overview, *sections = source.decode("utf-8").replace("\r\n", "\n").split("\n## ")
    lines = overview.splitlines()
    if not lines or lines[0] != f"# 对局 {match_id} · 一号位行动复盘":
        raise ValueError("报告标题与比赛目录不一致")
    data = parse_overview(lines[1:])
    if not sections or not sections[-1].startswith("逐秒输入覆盖\n"):
        raise ValueError("报告缺少逐秒输入覆盖")
    coverage = [s.strip().removeprefix("- ") for s in sections.pop().splitlines()[1:] if s.strip()]
    clips = [parse_clip(section) for section in sections]
    all_rows = clips + data["excluded"]
    identities = {(r["time"], r["hero"], r["domain"]) for r in all_rows}
    if len(identities) != len(all_rows) or any(
        not re.fullmatch(TIME, t) or h not in data["heroes"] or d not in DOMAINS
        for t, h, d in identities
    ):
        raise ValueError("片段的英雄、场景或决策秒与报告不符")
    total = Counter(r["domain"] for r in all_rows)
    eligible = Counter(r["domain"] for r in clips)
    balanced = Counter(r["domain"] for r in clips if len(r["rows"]) == 3)
    for row in data["counts"]:
        d = row["domain"]
        if (row["opportunities"], row["eligible"], row["balanced"]) != (
            total[d],
            eligible[d],
            balanced[d],
        ):
            raise ValueError(f"{d} 的片段明细与汇总不符")
    return dict(
        id=match_id,
        report_sha256=hashlib.sha256(source).hexdigest(),
        **data,
        clips=clips,
        coverage=coverage,
    )


def load_reports(root):
    matches = []
    for path in sorted(root.glob("*/match-report.md")):
        if not re.fullmatch(r"[0-9]+", path.parent.name):
            continue
        try:
            matches.append(parse_report(path))
        except ValueError as err:
            raise ValueError(f"{path}: {err}") from err
    if not matches:
        raise ValueError(f"{root} 中没有找到按比赛编号存放的 match-report.md")
    return {"matches": matches}


def read_map(path, match):
    payload = path.read_bytes()
    bundle = json.loads(payload)
    if (
        not isinstance(bundle, dict)
        or bundle.get("schema") != "b5-perspective-map/1"
        or bundle.get("match") != match["id"]
        or bundle.get("report_sha256") != match["report_sha256"]
    ):
        raise ValueError("地图与当前报告不匹配")
    return payload


def handler_for(reports, hero_dir, report_root=None):
    body = json.dumps(reports, ensure_ascii=False).encode("utf-8")
    maps = (
        {
            f"/api/map/{m['id']}": (report_root / m["id"] / "perspective-map.json", m)
            for m in reports["matches"]
        }
        if report_root is not None
        else {}
    )
    files = {
        "/": (ASSETS / "index.html", "text/html; charset=utf-8"),
        "/index.html": (ASSETS / "index.html", "text/html; charset=utf-8"),
        "/style.css": (ASSETS / "style.css", "text/css; charset=utf-8"),
        "/app.js": (ASSETS / "app.js", "text/javascript; charset=utf-8"),
        "/perspective.js": (ASSETS / "perspective.js", "text/javascript; charset=utf-8"),
        "/map.jpg": (MAP_IMAGE, "image/jpeg"),
        **{f"/heroes/{slug}.png": (hero_dir / f"{slug}.png", "image/png") for slug in PORTRAITS},
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            port = self.server.server_port
            if self.headers.get("Host") not in (f"localhost:{port}", f"127.0.0.1:{port}"):
                self.send_error(403)
                return
            path = urlsplit(self.path).path
            if path == "/api/reports":
                data, mime = body, "application/json; charset=utf-8"
            elif path in maps:
                source, match = maps[path]
                try:
                    data, mime = read_map(source, match), "application/json; charset=utf-8"
                except FileNotFoundError:
                    self.send_error(404)
                    return
                except (ValueError, OSError):
                    self.send_error(409)
                    return
            elif path in files and files[path][0].is_file():
                source, mime = files[path]
                data = source.read_bytes()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header(
                "Cache-Control", "private, max-age=3600" if path == "/map.jpg" else "no-store"
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-root", type=Path, default=ROOT / "reports/b5-three-replay-20261123"
    )
    parser.add_argument("--hero-dir", type=Path, default=ROOT / "reports/outcome-viewer-heroes")
    parser.add_argument("--port", type=int, default=8796)
    args = parser.parse_args()
    try:
        reports = load_reports(args.report_root)
        with ThreadingHTTPServer(
            ("127.0.0.1", args.port), handler_for(reports, args.hero_dir, args.report_root)
        ) as server:
            print(f"B5 单场复盘 http://127.0.0.1:{server.server_port}/", flush=True)
            server.serve_forever()
    except (ValueError, OSError) as err:
        parser.exit(1, f"{err}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
