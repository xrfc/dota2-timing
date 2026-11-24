"""将本机 B5 玩家反馈逐条定位到生成该反馈的报告版本和标题行。"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_REPORT_ROOT = Path(__file__).resolve().parents[1] / "reports/b5-three-replay-20261123"
FIELDS = ("match", "report_sha256", "hero", "domain", "time", "seconds", "feedback")
DOMAINS = ("兵线", "打野", "支援")
TIME = r"[0-9]+:[0-5][0-9]"
HEADING = re.compile(rf"## ({TIME})\s+(.+?) · ({'|'.join(DOMAINS)})")


def game_seconds(time):
    minutes, seconds = time.split(":")
    return 60 * int(minutes) + int(seconds)


def checked_record(record):
    if not isinstance(record, dict) or not all(key in record for key in FIELDS):
        raise ValueError("记录格式错误或缺少必填字段")
    for key in ("match", "report_sha256", "hero", "domain", "time", "feedback"):
        if not isinstance(record[key], str) or not record[key].strip():
            raise ValueError(f"{key} 需要非空文本")
    if not re.fullmatch(r"[0-9]+", record["match"]):
        raise ValueError("match 需要数字比赛编号")
    if not re.fullmatch(r"[0-9a-f]{64}", record["report_sha256"]):
        raise ValueError("report_sha256 需要小写 SHA-256 指纹")
    if record["domain"] not in DOMAINS or not re.fullmatch(TIME, record["time"]):
        raise ValueError("场景或游戏时刻格式无效")
    seconds = record["seconds"]
    if type(seconds) is not int or seconds != game_seconds(record["time"]):
        raise ValueError("seconds 需要与游戏时刻相符的整数秒")
    return {key: record[key] for key in FIELDS}


def read_headings(path, match, expected_digest):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise ValueError("报告 SHA-256 指纹与导出版本不符")
    lines = raw.decode("utf-8").replace("\r\n", "\n").split("\n")
    if lines[0] != f"# 对局 {match} · 一号位行动复盘":
        raise ValueError("报告标题与比赛编号不符")
    headings = {}
    for line_number, line in enumerate(lines, start=1):
        heading = HEADING.fullmatch(line)
        if heading:
            time, hero, domain = heading.groups()
            key = (hero, domain, game_seconds(time))
            if key in headings:
                raise ValueError("报告中有重复的片段标题，无法唯一定位")
            headings[key] = (time, line_number)
    return headings


def verify_feedback(payload, report_root):
    if not isinstance(payload, dict) or payload.get("schema") != "b5-trial-feedback/1":
        raise ValueError("需要 b5-trial-feedback/1 格式的导出文件")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("records 需要是数组")
    reports = {}
    seen = set()
    verified = []
    for number, original in enumerate(records, start=1):
        try:
            record = checked_record(original)
            match = record["match"]
            digest = record["report_sha256"]
            relative = Path(match) / "match-report.md"
            if match not in reports:
                reports[match] = digest, read_headings(report_root / relative, match, digest)
            source_digest, headings = reports[match]
            if digest != source_digest:
                raise ValueError("同场报告 SHA-256 指纹不一致")
            clip = (record["hero"], record["domain"], record["seconds"])
            if (match, clip) in seen:
                raise ValueError("同一片段的反馈记录重复")
            if clip not in headings or headings[clip][0] != record["time"]:
                raise ValueError("报告中找不到完全匹配的片段标题")
            seen.add((match, clip))
            verified.append({**record, "report": relative.as_posix(), "line": headings[clip][1]})
        except (ValueError, OSError) as err:
            raise ValueError(f"第 {number} 条记录：{err}") from err
    return {"schema": "b5-verified-feedback/1", "records": verified}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feedback", type=Path, help="本机记录页导出的反馈 JSON")
    parser.add_argument(
        "--report-root", type=Path, default=DEFAULT_REPORT_ROOT, help="B5 报告根目录"
    )
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.feedback.read_text(encoding="utf-8"))
        verified = verify_feedback(payload, args.report_root)
        output = json.dumps(verified, ensure_ascii=False, indent=2) + "\n"
    except (ValueError, OSError) as err:
        parser.exit(1, f"核对失败：{err}\n")
    sys.stdout.buffer.write(output.encode("utf-8", errors="backslashreplace"))


if __name__ == "__main__":
    main()
