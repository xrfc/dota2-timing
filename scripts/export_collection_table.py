"""Export a point-in-time, read-only collection inventory for Excel (UTF-8 BOM)."""

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def read(path):
    return json.loads(path.read_text())


def main():
    output = Path("reports/collection-tables")
    output.mkdir(parents=True, exist_ok=True)
    summary = []
    for root in sorted(Path("data").glob("purchase-*")):
        discoveries = sorted(root.glob("batch-*/discovery.json"))
        if not discoveries:
            continue
        rows = []
        for discovery in discoveries:
            batch = discovery.parent
            report_path = batch / "preflight.json"
            report = read(report_path) if report_path.exists() else {}
            kept = {s["match_id"] for s in report.get("samples", [])}
            excluded = {
                s["requested_match_id"]: "; ".join(s["reasons"])
                for s in report.get("exclusions", [])
            }
            for item in read(discovery):
                mid = item["match_id"]
                raw = batch / "matches" / f"{mid}.json"
                failure = batch / f"failure-{mid}.json"
                if mid in kept:
                    state = "通过初筛"
                elif mid in excluded:
                    state = "初筛排除"
                elif failure.exists():
                    state = "请求失败"
                elif raw.exists():
                    state = "已下载待预检"
                else:
                    state = "待下载"
                rows.append(
                    {
                        "比赛ID": mid,
                        "开始时间_北京时间": datetime.fromtimestamp(
                            item["start_time"], ZoneInfo("Asia/Shanghai")
                        ).isoformat(),
                        "时长_分钟": round(item["duration"] / 60, 2),
                        "大厅类型编码_7为天梯": item.get("lobby_type"),
                        "游戏模式编码": item.get("game_mode"),
                        "平均段位编码_非MMR": item.get("avg_rank_tier"),
                        "可用段位记录人数": item.get("num_rank_tier"),
                        "状态": state,
                        "排除原因": excluded.get(mid, ""),
                        "批次": batch.name,
                        "原始文件存在": raw.exists(),
                        "原始JSON绝对路径": str(raw.resolve()) if raw.exists() else "",
                        "OpenDota链接": f"https://www.opendota.com/matches/{mid}",
                        "预检报告路径": str(report_path.resolve()) if report_path.exists() else "",
                    }
                )
        assert len({r["比赛ID"] for r in rows}) == len(rows), root
        path = output / f"{root.name}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        counts = dict(Counter(r["状态"] for r in rows))
        summary.append({"collection": root.name, "rows": len(rows), "counts": counts})
    metadata = {
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "note": "静态快照；运行期间跨文件非事务一致。通过初筛不等于训练准入。",
        "collections": summary,
    }
    (output / "summary.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
