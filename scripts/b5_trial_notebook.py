"""从本机 B5 工作台生成可填写玩家反馈的独立 HTML。"""

import argparse
import http.client
import json
import os
import re
import tempfile
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path(__file__).with_name("b5_trial_notebook_assets") / "notebook.html"
PLACEHOLDER = "__B5_CATALOG_JSON__"
DOMAINS = ("兵线", "打野", "支援")


def read_reports(port):
    with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=10)) as connection:
        connection.request("GET", "/api/reports")
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"本机工作台 /api/reports 返回 HTTP {response.status}")
        return json.loads(response.read())


def clip_entry(clip, match_id, index, port):
    if not isinstance(clip, dict):
        raise ValueError(f"比赛 {match_id} 第 {index + 1} 个片段格式无效")
    hero, domain, time = (clip.get(k) for k in ("hero", "domain", "time"))
    if (
        not isinstance(hero, str)
        or not hero.strip()
        or domain not in DOMAINS
        or not isinstance(time, str)
        or not re.fullmatch(r"[0-9]+:[0-5][0-9]", time)
    ):
        raise ValueError(f"比赛 {match_id} 第 {index + 1} 个片段的英雄、场景或游戏时刻无效")
    minutes, remainder = map(int, time.split(":"))
    seconds = minutes * 60 + remainder
    fragment = urlencode({"match": match_id, "t": seconds, "i": index, "scene": domain})
    return dict(
        hero=hero,
        domain=domain,
        time=time,
        seconds=seconds,
        url=f"http://127.0.0.1:{port}/#{fragment}",
    )


def build_catalog(reports, port):
    matches = reports.get("matches") if isinstance(reports, dict) else None
    if not isinstance(matches, list) or not matches:
        raise ValueError("工作台未提供比赛清单")
    catalog = []
    match_ids = set()
    for match in matches:
        if not isinstance(match, dict):
            raise ValueError("工作台比赛条目格式无效")
        match_id, digest, rows = (match.get(k) for k in ("id", "report_sha256", "clips"))
        if (
            not isinstance(match_id, str)
            or not re.fullmatch(r"[0-9]+", match_id)
            or match_id in match_ids
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not isinstance(rows, list)
        ):
            raise ValueError("比赛编号、报告指纹或片段清单无效，需使用含报告指纹的 B5 工作台")
        match_ids.add(match_id)
        clips = [clip_entry(clip, match_id, index, port) for index, clip in enumerate(rows)]
        if len({(c["hero"], c["domain"], c["seconds"]) for c in clips}) != len(clips):
            raise ValueError(f"比赛 {match_id} 含有重复片段")
        catalog.append(dict(id=match_id, report_sha256=digest, clips=clips))
    return {"matches": catalog}


def write_notebook(output, catalog):
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise ValueError("试用记录页模板缺少唯一的目录占位符")
    # The HTML parser sees the script's closing tag even in application/json text.
    inline_json = json.dumps(catalog, ensure_ascii=False).replace("<", r"\u003c")
    page = template.replace(PLACEHOLDER, inline_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publish only a complete page, without replacing an existing file on a retry.
    temporary = tempfile.NamedTemporaryFile(dir=output.parent, delete=False)
    staged = Path(temporary.name)
    try:
        with temporary:
            temporary.write(page.encode("utf-8"))
        os.link(staged, output)
    finally:
        staged.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8796, help="本机 B5 工作台端口（默认 8796）")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports/b5-trial-notebook/index.html",
        help="新 HTML 文件路径（保留已有文件）",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port 须在 1 至 65535 之间")
    try:
        catalog = build_catalog(read_reports(args.port), args.port)
        write_notebook(args.output, catalog)
    except FileExistsError:
        parser.exit(1, f"{args.output} 已存在，请用 --output 指定新路径。\n")
    except ConnectionRefusedError:
        parser.exit(1, f"无法连接本机 B5 工作台，请确认服务已启动并监听端口 {args.port}。\n")
    except (OSError, ValueError, http.client.HTTPException) as err:
        parser.exit(1, f"生成试用记录页失败：{err}\n")
    print(args.output.resolve().as_uri())


if __name__ == "__main__":
    main()
