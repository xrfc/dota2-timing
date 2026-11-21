"""Prepare an organizer's private handoff from existing lane, wave and jungle reports."""

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from threading import Thread

from audit_decision_reports import audit_reports
from check_support_travel import MATCHES
from friend_review_server import MODES, make_server, read_reviews
from friend_review_server import issue as issue_invite
from review_judgments import CHOICES, build_queue

ROOT = Path(__file__).resolve().parents[1]
STATES = {
    "data_required": "缺少可核验的报告",
    "repair_required": "有材料需要修复",
    "human_judgment": "等待人工判断",
    "complete": "本轮抽查与裁定已完成",
}


def manifest_stamps(folders):
    stamps = []
    for folder in folders:
        path = folder / "cases.json"
        try:
            with path.open("rb") as stream:
                stamps.append(hashlib.file_digest(stream, "sha256").hexdigest())
        except FileNotFoundError:
            stamps.append(None)
    return stamps


def prepare(folders, reviews=(), adjudications=None, limit=5):
    stamps = manifest_stamps(folders)
    audit = audit_reports(folders)
    ready_folders, eligible, repairs = {}, set(), []
    legacy = 0
    for report in audit["reports"]:
        folder, mode = report["folder"], report["mode"]
        if mode is not None:
            if mode in ready_folders:
                raise ValueError(f"同一模式只接受一份活动报告：{mode}")
            ready_folders[mode] = Path(folder)
        for issue in report["issues"]:
            repairs.append({"folder": folder, **issue})
        for row in report["cases"]:
            if row["status"] == "passed":
                eligible.add(row["case_id"])
                legacy += row["checks"].get("match_end") == "unverified_legacy"
            else:
                for issue in row["issues"]:
                    repairs.append({"folder": folder, "case_id": row["case_id"], **issue})
    judgments = build_queue(
        ready_folders.values(), reviews, limit, eligible_ids=eligible, adjudications=adjudications
    )
    if manifest_stamps(folders) != stamps:
        raise ValueError("核验期间报告已更换，请重新运行。")
    if repairs:
        missing_only = all(item["reason"] in {"missing_file", "no_cases"} for item in repairs)
        state = "data_required" if missing_only and not eligible else "repair_required"
    else:
        state = "human_judgment" if judgments["queue"] else "complete"
    return (
        {
            "schema": "decision-review-handoff/1",
            "state": state,
            "audit_counts": audit["counts"],
            "legacy_end_unverified": legacy,
            "material_issues": repairs,
            "judgments": judgments,
        },
        ready_folders,
        eligible,
        stamps,
    )


def read_ledger(path):
    if not path.exists():
        return None
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT case_id, evidence_sha256, decision FROM verdicts ORDER BY seq
        """)
        return {"schema": "review-adjudications/1", "decisions": [dict(row) for row in rows]}


def record(path, task, choice, rationale=""):
    if choice not in CHOICES[task["mode"]] or not task.get("evidence_sha256"):
        raise ValueError("该裁定不适用于此片段。")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    key = task["case_id"], task["evidence_sha256"]
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS verdicts (
            seq INTEGER PRIMARY KEY, case_id TEXT NOT NULL, evidence_sha256 TEXT NOT NULL,
            decision TEXT NOT NULL, rationale TEXT NOT NULL, UNIQUE(case_id,evidence_sha256))""")
        conn.execute(
            "INSERT OR IGNORE INTO verdicts VALUES(NULL,?,?,?,?)", (*key, choice, rationale)
        )
        previous = conn.execute(
            "SELECT decision, rationale FROM verdicts WHERE case_id=? AND evidence_sha256=?", key
        ).fetchone()
        if previous != (choice, rationale):
            raise ValueError("这份证据已有不同裁定，请检查原记录。")


def generate_missing(demo_root, folders, fetch_map=False):
    # Use the existing 7.41f generator and its original three non-holdout matches.
    if all(folder.exists() for folder in folders):
        return
    from build_map_knowledge import prepare_741_map
    from prepare_lane_inputs import prepare_inputs

    prepare_741_map(ROOT / "data/map-reference-2026-10-26-v1", fetch=fetch_map)
    prepare_inputs(demo_root, MATCHES)
    for mode, folder in zip(MODES, folders, strict=True):
        if folder.exists():
            continue
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/lane_decision_review.py"),
                "--mode",
                mode,
                "--root",
                str(demo_root.resolve()),
                "--matches",
                *map(str, MATCHES),
                "--out",
                str(folder.resolve()),
            ],
            check=True,
            stdout=sys.stderr,
        )


def show(result, portal):
    counts, queue = result["audit_counts"], result["judgments"]
    print(STATES[result["state"]])
    print(
        f"证据核验通过 {counts['passed']} 段，材料不全 {counts['incomplete']} 段，"
        f"存在矛盾 {counts['failed']} 段。"
    )
    summary = queue["counts"]
    print(
        f"已抽查 {summary['covered_groups']}/{summary['selected_groups']} 组，"
        f"暂不排序 {summary['unranked_cases']} 段，已裁定 {summary['adjudicated_cases']} 段。"
    )
    if summary["unversioned_reviews"] or summary["other_version_reviews"]:
        print(
            f"历史意见：无版本 {summary['unversioned_reviews']} 条，其他版本 "
            f"{summary['other_version_reviews']} 条。"
        )
    if result["legacy_end_unverified"]:
        print(f"其中 {result['legacy_end_unverified']} 段旧报告缺少可独立核对的终局边界。")
    for item in result["material_issues"]:
        print(
            f"材料：{item['folder']} {item.get('case_id') or ''} {item['field']} ({item['reason']})"
        )
    for n, task in enumerate(queue["queue"], 1):
        print(f"{n}. {task['prompt']} {portal.rstrip('/')}{task['url']}")
    if queue["deferred"]:
        print(f"本轮上限之外另有 {queue['deferred']} 项，处理当前队列后将继续显示。")


def run(args):
    folders = args.review_dir or [args.root / f"action-comparison-{mode}-001" for mode in MODES]
    if args.serve and (args.reviews or args.json):
        raise ValueError("--serve 使用实时数据库和交互终端。")
    if args.fetch_741_map and not args.demo_root:
        raise ValueError("--fetch-741-map 配合 --demo-root 生成 7.41f 报告。")
    if args.demo_root:
        if args.review_dir:
            raise ValueError("--demo-root 生成标准目录，不能同时指定 --review-dir。")
        generate_missing(args.demo_root, folders, args.fetch_741_map)
    private = args.root / "friend-review-private"
    db = args.db or private / "reviews.sqlite3"
    ledger = args.ledger or private / "adjudications.sqlite3"
    if args.db and not db.is_file() and not args.serve:
        raise ValueError(f"指定的评审数据库不存在：{db}")

    def refresh():
        if args.reviews:
            rows = json.loads(args.reviews.read_text(encoding="utf-8"))
        else:
            rows = read_reviews(db) if db.exists() else []
        return prepare(folders, rows, read_ledger(ledger), args.limit)

    result, available, eligible, stamps = refresh()
    if not args.serve or not eligible:
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            show(result, args.portal_url)
        return int(bool(result["material_issues"]))
    if not result["judgments"]["queue"]:
        show(result, args.portal_url)
        return int(bool(result["material_issues"]))
    if not sys.stdin.isatty():
        raise ValueError("--serve 需要可交互终端；批处理请使用 --json。")
    with make_server(
        args.root, db, args.port, folders=available, current_ui=True, eligible_ids=eligible
    ) as server:
        if manifest_stamps(folders) != stamps:
            raise ValueError("门户启动期间报告已更换，请重新运行。")
        origin = f"http://127.0.0.1:{server.server_port}"
        print(f"登录评审：{origin}/")
        with closing(sqlite3.connect(db)) as conn:
            has_invite = conn.execute("SELECT 1 FROM invites LIMIT 1").fetchone()
        if not has_invite:
            print(f"首次登录邀请码：{issue_invite(db)}")
        else:
            print("请使用已有邀请码；每个评审人使用自己的邀请码。")
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            while True:
                show(result, origin)
                tasks = result["judgments"]["queue"]
                if not tasks:
                    break
                answer = input(
                    "门户提交后按回车刷新；输入编号裁定，i 签发另一位评审人的邀请码，q 退出："
                ).strip()
                if answer.lower() == "q":
                    break
                if answer.lower() == "i":
                    print(f"新评审人的邀请码：{issue_invite(db)}")
                elif answer.isdecimal() and 1 <= int(answer) <= len(tasks):
                    task = tasks[int(answer) - 1]
                    if task.get("evidence_sha256"):
                        labels = {
                            "farm": "继续发育",
                            "rotate": "换区",
                            "support": "支援",
                            "retreat": "后撤",
                            "unknown": "证据不足",
                        }
                        choices = [key for key in labels if key in CHOICES[task["mode"]]]
                        menu = "，".join(f"{i} {labels[key]}" for i, key in enumerate(choices, 1))
                        response = input(
                            f"{task['case_id']} 最终判断（{menu}；可在选项后附理由）："
                        ).strip()
                        choice, _, rationale = response.partition(" ")
                        if choice.isdecimal() and 1 <= int(choice) <= len(choices):
                            choice = choices[int(choice) - 1]
                        if choice in choices:
                            record(ledger, task, choice, rationale.strip())
                        else:
                            print("未保存裁定。")
                    else:
                        print("请在门户提交个人独立判断。")
                latest, _, eligible_now, latest_stamps = refresh()
                if latest_stamps != stamps or eligible_now != eligible:
                    raise ValueError("活动报告或可用片段发生变化，请重启本地门户。")
                result = latest
        finally:
            server.shutdown()
    return int(bool(result["material_issues"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("reports"))
    parser.add_argument("--review-dir", nargs="+", type=Path)
    parser.add_argument(
        "--demo-root", type=Path, help="generate missing 7.41f reports from local inputs"
    )
    parser.add_argument(
        "--fetch-741-map", action="store_true", help="fetch missing pinned map files for generation"
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--db", type=Path)
    source.add_argument("--reviews", type=Path, help="existing private reviewer export")
    parser.add_argument("--ledger", type=Path, help="organizer's private adjudication database")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--portal-url", default="http://127.0.0.1:8798", help="link origin for an existing portal"
    )
    parser.add_argument(
        "--serve", action="store_true", help="open an interactive local organizer session"
    )
    parser.add_argument(
        "--port", type=int, default=8798, help="local session port, 0 selects an available port"
    )
    args = parser.parse_args()
    try:
        return run(args)
    except (ValueError, OSError, sqlite3.Error, subprocess.CalledProcessError) as error:
        parser.exit(2, f"{error}\n")
    except (EOFError, KeyboardInterrupt):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
