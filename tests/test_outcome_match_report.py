import hashlib
import json

import pytest

from scripts.outcome_match_report import DOMAINS, match_cases, render


def row(t):
    actual = {"hits": 2, "gold": -30, "xp": None, "death": 0, "dead_seconds": 0}
    return {
        "t": t,
        "match": 9081112126,
        "hero": "npc_dota_hero_drow_ranger",
        "fold": 0,
        "action": "farm",
        "observed": actual,
        "stratum": 1,
        "overlap_reason": None,
        "values": {"farm": {**actual, "death": 0.25}, "retreat": actual},
    }


def test_report_shows_observation_and_only_balanced_estimates():
    r = row(65)
    for after, reason in ((0.25, None), (0.251, None), (None, "sparse_training_arm")):
        text = render(r["match"], [("wave", {**r, "overlap_reason": reason}, after)], {})
        assert "1:05" in text and "录像实况 | 2 | -30 | 缺测 | 否" in text
        assert ("25.0%" in text) == (after == 0.25)
        assert ("后撤估计" in text) == (after == 0.25)


def test_new_report_accounts_for_rejected_and_unbalanced_candidates():
    case = {**row(60), "label_exclusions": {"xp": "unverified_level_transition"}}
    hero = case["hero"]
    other = "npc_dota_hero_axe"
    empty = dict(opportunities=0, eligible=0, supported=0, balanced=0, excluded=[])
    excluded = dict(
        t=100,
        hero=other,
        action="unknown",
        unknown_action=True,
        early_death=True,
        incomplete_window=True,
    )
    stats = {
        "wave": {**empty, "opportunities": 1, "eligible": 1, "supported": 1},
        "jungle": {**empty, "opportunities": 1, "excluded": [excluded]},
        "support": empty,
    }
    result = render(
        case["match"],
        [("wave", case, 0.2504)],
        {hero: "卓尔游侠", other: "斧王"},
        {"observed_heroes": [hero, other], "by_domain": stats},
    )
    assert "一号位：卓尔游侠、斧王" in result
    assert "| 兵线 | 1 | 1 | 1 | 0 |" in result
    assert "| 1:40 | 斧王 | 打野 | 未知 |" in result
    assert "前六秒无法按冻结规则识别动作、前六秒死亡、录像未覆盖完整的二十秒窗口" in result
    assert "距最近受击队友大于 400 且不超过 6000" in result
    assert "未触发还是所需记录缺失" in result
    assert "训练比赛有平均段位门槛" in result and "探索性复盘" in result
    assert "双动作比较证据不足" in result and "后撤估计" not in result
    assert "0.2504 超过 0.25" in result
    assert "同等级经验变化缺测。无法确认两个端点处于同一等级" in result


def test_one_arm_can_lack_experience_estimate_with_observed_experience():
    case = row(60)
    case["observed"]["xp"] = 12
    case["values"]["retreat"] = {**case["observed"], "xp": None}
    case["values"]["farm"]["xp"] = 15
    result = render(case["match"], [("wave", case, 0.25)], {})
    assert "| 录像实况 | 2 | -30 | 12 |" in result
    assert "| 继续收线估计 | 2.00 | -30.00 | 15.00 |" in result
    assert "| 后撤估计 | 2.00 | -30.00 | 缺估 |" in result
    assert "有标签的训练片段数、比赛数或加权有效样本量未达门槛" in result


def test_support_arrival_missingness_matches_the_frozen_label(monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from outcome_domains import arrived

    # A missing life state alone never makes the frozen label unknown.
    assert arrived({67: (0, 0)}, {67: (2, 2)}, 60, [67], {}) == 1
    assert arrived({}, {}, 60, [67], {67: {"life_state": 1}}) == 0
    assert arrived({67: (0, 0)}, {}, 60, [67], {}) is None


def test_no_identified_carry_or_candidates_is_reportable():
    empty = dict(opportunities=0, eligible=0, supported=0, balanced=0, excluded=[])
    result = render(
        123,
        [],
        {},
        {"observed_heroes": [], "by_domain": dict.fromkeys(DOMAINS, empty)},
    )
    assert "一号位：未能识别" in result
    assert "位置识别证据不足" in result
    assert result.count("未识别出一号位，无法为此场景取样") == len(DOMAINS)
    assert "未触发还是所需记录缺失" not in result


def test_report_filters_and_hash_checks_even_unselected_records(tmp_path):
    evidence = {}
    for domain in DOMAINS:
        folder = tmp_path / domain
        folder.mkdir()
        records = [row(900), {**row(850), "match": 1}, row(800)] if domain == "wave" else []
        payload = "".join(json.dumps(r) + "\n" for r in records).encode()
        path = folder / "predictions.jsonl"
        path.write_bytes(payload)
        evidence[domain] = {
            "predictions_sha256": hashlib.sha256(payload).hexdigest(),
            "training_strata_by_fold": {"0": {"1": {"balance": {"after": 0.25}}}},
        }
    assert [r["t"] for _, r, _ in match_cases(9081112126, tmp_path, evidence)] == [800, 900]
    with pytest.raises(ValueError, match="无该场"):
        match_cases(9081112027, tmp_path, evidence)
    path.write_text(json.dumps({**row(85), "match": 1}))
    with pytest.raises(ValueError, match="指纹"):
        match_cases(9081112126, tmp_path, evidence)


def test_reserved_match_rejected_before_file_access(tmp_path):
    from dota_items.data.awareness_split import is_holdout

    with pytest.raises(ValueError, match="留出集"):
        match_cases(next(n for n in range(100) if is_holdout(n)), tmp_path, {})


def test_existing_inputs_match_exact_demo_and_embedded_id(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from scripts.outcome_match_report import from_demo

    demo = tmp_path / "local.dem"
    demo.write_bytes(b"sample replay")
    cache = tmp_path / "inputs"
    cache.mkdir()
    manifest = cache / "replay-provenance.json"
    header = dict(match_id=123, end_time=456, player_count=10, game_mode=22, build_num=None)
    cached = dict(
        header,
        source_sha256=hashlib.sha256(demo.read_bytes()).hexdigest(),
        compat_manifest_sha256="frozen",
    )
    manifest.write_text(json.dumps(cached))
    monkeypatch.setitem(
        sys.modules,
        "new_replay_inputs",
        SimpleNamespace(
            prepare=None, active_compat=lambda: "frozen", replay_header=lambda _: header
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "new_replay_outcomes",
        SimpleNamespace(infer=lambda root, mid, map_dir: ([], {"match": mid})),
    )
    assert from_demo(demo, cache, None, tmp_path) == (123, [], {"match": 123})
    with pytest.raises(ValueError, match="比赛编号"):
        from_demo(demo, cache, 124, tmp_path)
    for key, value in header.items():
        manifest.write_text(json.dumps({**cached, key: (value or 0) + 1}))
        with pytest.raises(ValueError, match="原始录像"):
            from_demo(demo, cache, None, tmp_path)
    manifest.write_text(json.dumps({**cached, "compat_manifest_sha256": "old"}))
    with pytest.raises(ValueError, match="解析器"):
        from_demo(demo, cache, None, tmp_path)
    manifest.write_text(json.dumps(cached))
    demo.write_bytes(b"other")
    with pytest.raises(ValueError, match="其他录像"):
        from_demo(demo, cache, None, tmp_path)
