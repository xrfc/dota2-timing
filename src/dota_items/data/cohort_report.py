"""Render existing cohort evidence only; never replay sources or grant admission."""

import hashlib
import json
import math
import os
import tempfile
from collections import Counter
from pathlib import Path

from dota_items.data.source_io import read_source_bytes


def _require(condition):
    if not condition:
        raise ValueError("Invalid cohort audit structure, counts or boundary declarations")


def _count(value):
    _require(type(value) is int and value >= 0)
    return value


def _object(value):
    _require(type(value) is dict)
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _finite(value):
    if isinstance(value, dict):
        for child in value.values():
            _finite(child)
    elif isinstance(value, list):
        for child in value:
            _finite(child)
    elif isinstance(value, float):
        _require(math.isfinite(value))


def _text(value):
    _require(type(value) is str and bool(value.strip()))
    return value


def _counts(value):
    for key, count in _object(value).items():
        _text(key)
        _count(count)
    return value


def _validate(audit):
    _object(audit)
    _finite(audit)
    _require(audit["schema_version"] == "purchase-cohort-audit/1")
    for key in ("training_allowed", "new_split_assigned", "old_split_changed"):
        _require(audit[key] is False)
    if "producer_migration" in audit:
        _require(audit["producer_migration"] == "public-reader/1")
    collections = _object(audit["collections"])
    for name in ("old", "new"):
        c = _object(collections[name])
        for key in ("attempted", "retained", "excluded", "excluded_cache_present"):
            _count(c[key])
        _require(c["attempted"] == c["retained"] + c["excluded"])
        _require(c["excluded_cache_present"] <= c["excluded"])
        reasons = _counts(c["reason_counts"])
        rows = c["exclusions"]
        _require(type(rows) is list and len(rows) == c["excluded"])
        observed, ids, cached = Counter(), set(), 0
        for row in rows:
            _object(row)
            mid = _count(row["requested_match_id"])
            _require(mid > 0 and mid not in ids)
            ids.add(mid)
            _require(type(row["cache_present"]) is bool)
            cached += row["cache_present"]
            _require(
                row["evidence_level"]
                == ("historical_receipt_only" if name == "old" else "offline_replayed")
            )
            _require(type(row["reasons"]) is list and bool(row["reasons"]))
            for reason in row["reasons"]:
                _text(reason)
            _require(len(set(row["reasons"])) == len(row["reasons"]))
            observed.update(row["reasons"])
        _require(dict(observed) == reasons and cached == c["excluded_cache_present"])
    distributions = _object(audit["distributions"])
    for name in ("old_retained", "new_retained", "new_inspectable"):
        d = _object(distributions[name])
        n = _count(d["matches"])
        for key in ("log_status", "role_hints", "patch_time"):
            _require(sum(_counts(d[key]).values()) == n)
        for key in (
            "empty_logs",
            "event_at_or_after_1800",
            "matches_with_exact_duplicate_rows",
            "matches_with_simultaneous_distinct_items",
            "matches_with_recipe_rows",
        ):
            _require(_count(d[key]) <= n)
        for key in (
            "start_time_unix",
            "duration_seconds",
            "discovery_average_rank_hint",
            "discovery_rank_record_count",
        ):
            stats = _object(d[key])
            observed = _count(stats["observed"])
            _require(observed + _count(stats["missing"]) == n)
            values = [stats[k] for k in ("min", "median", "max")]
            if observed:
                _require(all(type(v) in (int, float) for v in values))
                _require(values[0] <= values[1] <= values[2])
            else:
                _require(values == [None, None, None])
        support = _object(d["log_observation_support"])
        _require(bool(support))
        for item, s in support.items():
            _text(item)
            _object(s)
            p, neg, unknown = (_count(s[k]) for k in ("positive", "negative", "unknown"))
            _require(p + neg + unknown == n)
            rate = s["positive_rate"]
            if p + neg:
                _require(type(rate) in (int, float) and rate == p / (p + neg))
            else:
                _require(rate is None)
    old, new = collections["old"]["retained"], collections["new"]["retained"]
    inspectable = distributions["new_inspectable"]["matches"]
    _require(distributions["old_retained"]["matches"] == old)
    _require(distributions["new_retained"]["matches"] == new)
    _require(new <= inspectable <= new + collections["new"]["excluded_cache_present"])
    items = set(distributions["old_retained"]["log_observation_support"])
    _require(all(set(d["log_observation_support"]) == items for d in distributions.values()))
    for name, new_count in (
        ("retained_only", new),
        ("including_new_excluded_inspectable", inspectable),
    ):
        g = _object(audit["graphs"][name])
        _require(g["not_a_model_split"] is True)
        _require(
            g["bucket_meaning"]
            == {"train": "old cohort", "validation": "new cohort", "test": "empty"}
        )
        _require(type(g["identity_coverage_complete"]) is bool)
        identity = _counts(g["identity_summary"])
        _require(identity["matches"] == old + new_count)
        defects = sum(
            identity[k]
            for k in ("duplicate_known_slots", "invalid_player_slots", "unknown_player_slots")
        )
        _require(g["identity_coverage_complete"] == (defects == 0))
        _require(_count(g["direct_shared_known_players"]) <= identity["known_distinct_players"])
        groups = g["groups"]
        _require(type(groups) is list)
        seen, old_total, new_total = set(), 0, 0
        sizes, bridges, mixed, bridging_new, disconnected = [], 0, 0, 0, 0
        for row in groups:
            _object(row)
            size, oc, nc = (_count(row[k]) for k in ("size", "old_count", "new_count"))
            _require(size > 0 and size == oc + nc)
            ids = row["match_ids"]
            _require(type(ids) is list and len(ids) == size)
            for mid in ids:
                _require(_count(mid) > 0 and mid not in seen)
                seen.add(mid)
            splits = row["old_splits"]
            _require(
                type(splits) is list and all(s in ("train", "validation", "test") for s in splits)
            )
            _require(len(splits) == len(set(splits)) and bool(splits) == bool(oc))
            _require(len(splits) <= _count(row["old_group_count"]) <= oc)
            _require(row["bridges_old_splits"] is (len(splits) > 1))
            sizes.append(size)
            old_total += oc
            new_total += nc
            bridges += len(splits) > 1
            mixed += bool(oc and nc)
            bridging_new += nc if len(splits) > 1 else 0
            disconnected += nc if not oc else 0
        _require((old_total, new_total) == (old, new_count))
        expected = {
            "group_count": len(groups),
            "largest_group": max(sizes, default=0),
            "bridging_group_count": bridges,
            "mixed_old_new_groups": mixed,
            "new_in_bridging_groups": bridging_new,
            "new_without_observed_old_connection": disconnected,
        }
        for key, count in expected.items():
            _require(_count(g[key]) == count)
    _require(type(audit["limitations"]) is list and bool(audit["limitations"]))
    for line in audit["limitations"]:
        _text(line)
    evidence = _object(audit["evidence_sha256"])
    _require(bool(evidence))
    for digest in evidence.values():
        _require(
            type(digest) is str
            and len(digest) == 64
            and all(c in "0123456789abcdef" for c in digest)
        )


def validate_audit(audit):
    """Check report-relevant semantics, not raw-source authenticity or all source fields."""
    try:
        _validate(audit)
    except (KeyError, TypeError, IndexError, RecursionError) as exc:
        raise ValueError("Missing or malformed cohort audit fields") from exc


def _escape(value):
    # Encode all ASCII punctuation: no links, HTML, table separators or headings.
    return "".join(
        " "
        if c.isspace() or ord(c) < 32
        else f"&#{ord(c)};"
        if c.isascii() and not c.isalnum()
        else c
        for c in value
    )


def render_report(audit):
    """Pure Markdown rendering; only supplied aggregate counts are displayed."""
    validate_audit(audit)
    lines = [
        "# 队列审计质量报告",
        "",
        "仅转述已有审计 JSON；不重算审计、不读取原始缓存、不认证来源真实性。",
        "不是独立性认证、训练许可或模型效果评估；新增用途未授权。",
        "",
        "## 数据范围与排除证据",
        "",
    ]
    for name, label in (("old", "旧"), ("new", "新")):
        c = audit["collections"][name]
        lines.append(
            f"- {label}队列：尝试 {c['attempted']}；候选 {c['retained']}；"
            f"排除 {c['excluded']}；排除记录现存缓存 {c['excluded_cache_present']}。"
        )
        for reason, count in sorted(c["reason_counts"].items()):
            lines.append(f"  - {_escape(reason)}：{count}（分母：排除记录 {c['excluded']}）")
    lines += [
        "",
        "候选不等于新增研究准入。原因可重叠，不能求和当作排除比赛总数。",
        "旧排除为历史收据证据，不声称已独立重放缺失原始缓存；新排除保留离线审计证据层级。",
        "缺日志是未知，不是负标签；非法事件与审计失败不应被解释成实际未购买。",
        "",
        "## 日志观测分母",
        "",
    ]
    for name, label in (
        ("old_retained", "旧候选"),
        ("new_retained", "新候选"),
        ("new_inspectable", "新可检查缓存（含排除）"),
    ):
        d = audit["distributions"][name]
        lines.append(f"- {label}：{d['matches']} 场。")
        for status, count in sorted(d["log_status"].items()):
            lines.append(f"  - 日志 {_escape(status)}：{count}。")
    lines += [
        "日志 present 不保证完整、不覆盖冻结预检准入；缺字段不补零。",
        "",
        "## 玩家连通风险",
        "",
    ]
    for name, label in (
        ("retained_only", "旧候选 + 新候选"),
        ("including_new_excluded_inspectable", "旧候选 + 新可检查缓存（含排除）"),
    ):
        g = audit["graphs"][name]
        lines.append(
            f"- {label}：{g['identity_summary']['matches']} 场；"
            f"连通组 {g['group_count']}；最大组 {g['largest_group']} 场；"
            f"跨旧 split 组 {g['bridging_group_count']}；"
            f"这些组内新增 {g['new_in_bridging_groups']} 场。"
        )
        coverage = "完整（仅已知账号字段）" if g["identity_coverage_complete"] else "不完整"
        lines.append(
            f"  - 身份覆盖：{coverage}；新旧直接共有已知账号数 "
            f"{g['direct_shared_known_players']}；未观察到旧关联的新增 "
            f"{g['new_without_observed_old_connection']} 场（非独立测试集认证）。"
        )
    lines += [
        "",
        "组是已知账号路径连接的比赛集合；跨旧 split 表示组含多个旧划分的比赛，"
        "不等于原旧划分直接账号重叠。扩展图组数减少可能是合并更多，不是风险降低。",
        "train/validation/test 图桶仅指旧队列/新队列/空，不是给新增比赛分配 split。",
        "账号不等于现实人物；缺失账号会隐藏边。旧划分不变，也未分配新划分。",
        "",
        "## 待用户决定（未执行）",
        "",
        "1. 保持旧实验，新增仅审计（当前边界）。",
        "2. 若另行授权合并队列，先确定是否纳入排除缓存作为连通证据，再制定整组划分协议。",
        "3. 若需要独立评估，先冻结选择与时间规则；不得自动使用无观测旧关联的场次。",
        "",
        "## 原审计局限（转义文本，不是新增许可）",
        "",
    ]
    lines.extend(f"- {_escape(line)}" for line in audit["limitations"])
    return "\n".join(lines) + "\n"


def write_report(input_path: Path, output_path: Path):
    """Validate first; publish a complete file without overwriting even dangling links."""
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError("Report output already exists")
    contents = read_source_bytes(input_path)
    try:
        audit = json.loads(contents, object_pairs_hook=_pairs)
        report = render_report(audit)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("Invalid cohort audit JSON") from exc
    digest = hashlib.sha256(contents).hexdigest()
    report += f"\n输入 JSON SHA-256：{digest}\n"
    # Same-directory staging + exclusive hard link: failures never publish partial Markdown.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output_path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(report.encode("utf-8"))
        os.link(temporary, output_path)
    finally:
        if temporary is not None:
            temporary.unlink()
    return digest
