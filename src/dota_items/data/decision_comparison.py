"""Observer-bounded support/farm review packet, not labels or a numerical policy."""

from copy import deepcopy

from .decision_evidence import build_evidence


def comparison_card(raw, decision, live):
    """Exact-tick health for visible heroes; friendly inventory only, no hidden truth.

    Current enemy inventory is deliberately withheld: being position-visible does
    not prove an inspect action or establish an inventory observation contract.
    """
    tick, view = decision["tick"], decision["observer_team"]
    if raw["match_id"] != decision["match_id"] or view not in {"radiant", "dire"}:
        raise ValueError("Comparison identity/view mismatch")
    if live["tick"] != tick:
        raise ValueError("Live state cutoff mismatch")
    slots = [p["player_slot"] for p in decision["positions"]]
    if len(set(slots)) != len(slots):
        raise ValueError("Duplicate player in decision")
    allies = set(range(5)) if view == "radiant" else set(range(128, 133))
    frame = {
        "match_id": decision["match_id"],
        "view": view,
        "tick": tick,
        "time": decision["time"],
        "players": decision["positions"],
    }
    rows = []
    for position in decision["positions"]:
        if position["visibility"] != "visible" and (
            position["current_position"] is not None or position["life_state"] is not None
        ):
            raise ValueError("Hidden state in observer frame")
        last = position.get("last_seen")
        if last and (last["source_tick"] > tick or last["time"] > decision["time"]):
            raise ValueError("Future last-seen")
        slot = position["player_slot"]
        if slot not in {*range(5), *range(128, 133)}:
            raise ValueError("Invalid player slot")
        friendly = slot in allies
        if position["relation"] != ("ally" if friendly else "enemy"):
            raise ValueError("Relation mismatch")
        row = {
            "player_slot": slot,
            "hero_id": position["hero_id"],
            "relation": position["relation"],
            "visibility": position["visibility"],
            "position_status": position["position_status"],
            "current_position": deepcopy(position["current_position"]),
            "last_seen": deepcopy(position["last_seen"]),
            "health": None,
            "level": None,
            "inventory": None,
            "ability_levels": None,
            "ability_cooldowns": None,
            "mana": None,
            "state_status": "withheld_not_currently_visible",
            "inventory_status": "unverified" if friendly else "no_enemy_inspection_evidence",
            "source_ref": None,
        }
        if position["visibility"] == "visible":
            pid = slot if slot < 5 else slot - 123
            players = [p for p in raw["players"] if p["player_id"] == pid]
            states = [
                (i, s)
                for i, s in enumerate(raw.get("coach_state_snapshots", []))
                if s["player_id"] == pid and s["tick"] == tick
            ]
            events = [
                e
                for e in raw.get("hero_visibility_events", [])
                if e["player_id"] == pid and e["tick"] <= tick
            ]
            latest = max((e["tick"] for e in events), default=-1)
            identities = {
                (e["entity_index"], e["entity_serial"], e.get(view + "_state"))
                for e in events
                if e["tick"] == latest
            }
            row["state_status"] = "missing_ambiguous_or_identity_unverified"
            if len(players) == len(states) == 1:
                index, state = states[0]
                identity = (state.get("entity_index"), state.get("entity_serial"), "visible")
                if (
                    players[0]["hero_id"] == row["hero_id"]
                    and players[0]["team"] == (2 if slot < 5 else 3)
                    and None not in identity
                    and identities == {identity}
                    and state.get("life_state") == position["life_state"]
                ):
                    row.update(
                        state_status="same_tick_visible_identity_matched_source",
                        health={"current": state.get("hp"), "max": state.get("max_hp")},
                        source_ref=f"coach_state_snapshots[{index}]",
                    )
                    if friendly:
                        evidence = build_evidence(frame, raw, slot)
                        row.update(
                            level=state.get("level"),
                            inventory=evidence["decision_input"]["inventory"],
                            inventory_status=evidence["decision_input"]["inventory"]["status"],
                            ability_levels=deepcopy(state.get("ability_levels")),
                        )
        rows.append(row)
    tp = live.get("tp")
    wait = None
    if tp and tp["cooldown_status"] in {"zero_observed", "countdown_consistent"}:
        wait = tp["cooldown_source_value"]
    omni = next((a for a in live["abilities"] if a["name"] == "juggernaut_omni_slash"), None)
    constraints = []
    if omni and omni["cooldown_status"] == "countdown_consistent":
        constraints.append(
            f"无敌斩源倒计时约{omni['cooldown_source_value']:.2f}秒；依赖立即无敌斩的收割条件未成立。"
        )
    if wait is not None and wait > 0:
        constraints.append(f"TP源倒计时约{wait:.2f}秒，不能按立刻开始传送估计到场。")
    return {
        "schema": "decision-comparison/1",
        "tick": tick,
        "team_state": rows,
        "fight_location": {
            "visible_positions": [
                {"player_slot": r["player_slot"], "position": deepcopy(r["current_position"])}
                for r in rows
                if r["visibility"] == "visible" and r["current_position"] is not None
            ],
            "fight_membership": None,
            "warning": "当前位置和过去交战日志不证明当前团战范围、人数优势或持续时间。",
        },
        "arrival": {
            "tp_cooldown_wait_source_seconds": wait,
            "can_start_tp": None,
            "legal_destinations": None,
            "channel_seconds": None,
            "post_tp_walk_seconds": None,
            "arrival_interval_seconds": None,
            "formula": "冷却等待 + 开始施法前等待 + TP通道 + 落地赶路（均需有效证据）",
            "warning": "冷却等待不是总到场时间；未验证落点、通道与路径，不能给出到场区间。",
        },
        "verified_constraints": constraints,
        "alternatives": [
            {
                "action": "join",
                "name": "支援／参团",
                "requirements": (
                    "合法安全落点、到场仍有有效战斗、关键技能与蓝量满足、贡献值得承担风险。"
                ),
                "potential_benefit": "收割、救援、保塔或争夺目标；收益不限于人头。",
                "opportunity_cost": "错过兵线/野区、传送资源和后续位置；当前存量及金额未知。",
                "stop": "到场窗口关闭、落点受威胁或关键技能无法完成预定贡献时重新比较。",
                "expected_gain": None,
            },
            {
                "action": "farm",
                "name": "继续刷钱",
                "requirements": "当时确有可安全取得的兵线或野区，且放弃支援的团队代价可接受。",
                "potential_benefit": "获取资源、推进装备成型；近期刷野日志不等于当前营地尚有资源。",
                "opportunity_cost": "放弃潜在击杀、救援或目标保护；不按后续战果倒推。",
                "stop": "敌方消失、视野退路或局部威胁变化时，转入换区/避险比较。",
                "expected_gain": None,
            },
            {
                "action": "reposition",
                "name": "换区／避险",
                "requirements": (
                    "本地资源不安全或撤退路径比原地停留可靠；失踪信息需结合眼位与开雾可能。"
                ),
                "potential_benefit": "降低暴露并保留后续发育/支援选择。",
                "opportunity_cost": "损失移动时间与原区域资源；不能把任何敌人靠近都判成必须撤退。",
                "stop": "安全区或情报条件变化后重新比较，而不是无条件长期逃跑。",
                "expected_gain": None,
            },
        ],
        "annotation": {
            "schema": "decision-annotation-draft/1",
            "case_id": None,
            "review_stage": "post_feedback_not_blind_not_training_label",
            "allowed_draft_values": [
                "acceptable",
                "conditional",
                "not_recommended",
                "insufficient_evidence",
            ],
            "actions": [
                {
                    "action": a,
                    "judgment": None,
                    "reason": None,
                    "conditions": [],
                    "evidence_refs": [],
                }
                for a in ("join", "farm", "reposition")
            ],
            "facts_that_could_change_judgment": [],
            "outcome_revealed": None,
            "protocol_approved": False,
            "training_allowed": False,
        },
        "training_allowed": False,
        "review_readiness": "conditional_discussion_only_not_complete_action_label",
        "blocking_unknowns": [
            "蓝量解码范围异常及控制/禁用等完整施放限制",
            "敌方装备检查证据与双方关键技能CD覆盖",
            "合法TP落点、通道和可走路径、有效战斗窗口",
            "当前可安全取得的资源存量与行动收益口径",
        ],
    }
