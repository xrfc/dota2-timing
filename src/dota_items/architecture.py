"""Machine-readable architecture map: two product tracks on one shared foundation.

Design and rationale: docs/architecture.md. This module is standard-library only and
is never imported by business code; tests/test_architecture.py enforces it.

Two independent axes classify every module and script:

* layer: the existing package (sources, data, contracts, handoff, modeling,
  experiments, workflow, recommendation) -- enforced by test_track_boundaries.
* track: which product line owns it -- shared foundation, track A (recommendation,
  machine learning on match-level data) or track B (awareness decisions on
  observer-perspective replay evidence).

Rules: shared code must not import either track; track A and track B must not import
each other. Cross-track reuse goes through shared modules. Files are classified in
place: frozen artifacts record source paths in their fingerprints, so physical moves
need a registered producer migration (docs/architecture.md section 5).
"""

SHARED = "shared"
RECOMMEND = "recommend"
AWARENESS = "awareness"

TRACKS = {
    SHARED: "共享底座：来源、存储、契约、录像解析、机制知识、通用评估与工作区",
    RECOMMEND: "路线A：阵容/出装/针对装/对线推荐（比赛级数据上的机器学习）",
    AWARENESS: "路线B：意识层面决策（防被抓、参团、集合抓人；当时可知的录像证据）",
}

STATUSES = {
    "active": "当前开发可扩展",
    "maintenance": "只为复现/校验冻结产物维护；不承载新功能，新需求另建新版本模块",
}

_S, _A, _B = SHARED, RECOMMEND, AWARENESS

# module (relative to dota_items, "" = package root) -> (track, status)
MODULES = {
    "": (_S, "active"),
    "architecture": (_S, "active"),
    "analysis": (_S, "maintenance"),
    "cli": (_S, "maintenance"),
    "domain": (_S, "active"),
    "normalize": (_S, "active"),
    "report": (_S, "maintenance"),
    "storage": (_S, "active"),
    # contracts / handoff: standard-library interfaces and read-only transport
    "contracts": (_S, "active"),
    "contracts.lineup": (_S, "active"),
    "contracts.numeric": (_S, "active"),
    "contracts.replay_context": (_S, "active"),
    "contracts.tasks": (_S, "active"),
    "contracts.death_risk": (_B, "active"),
    "handoff": (_S, "active"),
    "handoff.bundle": (_S, "active"),
    # sources
    "sources": (_S, "active"),
    "sources.collection_history": (_S, "active"),
    "sources.gem_capture": (_S, "active"),
    "sources.gem_camp_evidence": (_S, "active"),
    "sources.gem_capture_creeps": (_S, "active"),
    "sources.gem_capture_extras": (_S, "active"),
    "sources.gem_capture_v3": (_S, "active"),
    "sources.gem_farm_income": (_S, "active"),
    "sources.gem_observations": (_S, "active"),
    "sources.gem_replay": (_S, "active"),
    "sources.opendota": (_S, "active"),
    "sources.opendota_budget": (_S, "active"),
    "sources.decision_mana": (_B, "active"),
    "sources.decision_state_capture": (_B, "active"),
    "sources.replay_identity": (_B, "maintenance"),
    # data: shared foundation (reading, replay cleaning, knowledge)
    "data": (_S, "active"),
    "data.acceptance": (_S, "active"),
    "data.cleaning": (_S, "active"),
    "data.context": (_S, "active"),
    "data.contracts": (_S, "active"),
    "data.features": (_S, "maintenance"),
    "data.item_registry": (_S, "active"),
    "data.mechanics": (_S, "active"),
    "data.mechanics_cross_review": (_S, "active"),
    "data.mechanics_facts": (_S, "maintenance"),
    "data.mechanics_facts_v2": (_S, "maintenance"),
    "data.mechanics_facts_v3": (_S, "maintenance"),
    "data.mechanics_facts_v4": (_S, "maintenance"),
    "data.mechanics_facts_v5": (_S, "maintenance"),
    "data.mechanics_facts_v6": (_S, "maintenance"),
    "data.mechanics_facts_v7": (_S, "maintenance"),
    "data.mechanics_facts_v8": (_S, "maintenance"),
    "data.mechanics_facts_v9": (_S, "maintenance"),
    "data.mechanics_facts_v10": (_S, "maintenance"),
    "data.mechanics_facts_v11": (_S, "maintenance"),
    "data.mechanics_facts_v12": (_S, "maintenance"),
    "data.mechanics_facts_v13": (_S, "maintenance"),
    "data.mechanics_facts_v14": (_S, "maintenance"),
    "data.mechanics_facts_v15": (_S, "maintenance"),
    "data.mechanics_facts_v16": (_S, "maintenance"),
    "data.mechanics_facts_v17": (_S, "maintenance"),
    "data.mechanics_facts_v18": (_S, "active"),
    "data.mechanics_traits_v3": (_S, "active"),
    "data.mechanics_current": (_S, "active"),
    "data.map_api": (_S, "active"),
    "data.static_map_connectivity": (_S, "active"),
    "data.mechanics_api": (_S, "active"),
    "data.position_rule": (_S, "active"),
    "data.knowledge_superseded": (_S, "active"),
    "data.mechanics_rules_v11": (_S, "active"),
    "data.mechanics_facts_v19": (_S, "active"),
    "data.mechanics_profiles_v4": (_S, "active"),
    "data.mechanics_facts_v20": (_S, "active"),
    "data.mechanics_facts_v21": (_S, "active"),
    "data.mechanics_facts_v22": (_S, "active"),
    "data.mechanics_facts_v23": (_S, "active"),
    "data.mechanics_facts_v24": (_S, "active"),
    "data.mechanics_facts_v25": (_S, "active"),
    "data.mechanics_facts_v26": (_S, "active"),
    "data.mechanics_facts_overlay": (_S, "active"),
    "data.mechanics_profiles_v5": (_S, "active"),
    "data.mechanics_traits_v4": (_S, "active"),
    "data.mechanics_conditions": (_S, "active"),
    "data.mechanics_profiles_v3": (_S, "active"),
    "data.mechanics_feedback": (_S, "active"),
    "data.mechanics_profiles_v2": (_S, "active"),
    "data.mechanics_rules_v8": (_S, "active"),
    "data.mechanics_graph": (_S, "active"),
    "data.mechanics_graph_v2": (_S, "active"),
    "data.mechanics_interactions": (_S, "active"),
    "data.mechanics_profiles": (_S, "active"),
    "data.mechanics_rules": (_S, "maintenance"),
    "data.mechanics_rules_v2": (_S, "active"),
    "data.observer": (_S, "active"),
    "data.patch_time": (_S, "active"),
    "data.pipeline": (_S, "active"),
    "data.preprocessing": (_S, "maintenance"),
    "data.producer_migration": (_S, "active"),
    "data.semantic_review": (_S, "active"),
    "data.source_io": (_S, "active"),
    "data.smoke_breaks": (_S, "active"),
    "data.teleports": (_S, "active"),
    "data.unit_state": (_S, "active"),
    "data.vision_sim": (_S, "active"),
    "data.validation": (_S, "active"),
    # data: track A (match-level tables and purchase cohorts)
    "data.cohort_handoff": (_A, "maintenance"),
    "data.cohort_report": (_A, "maintenance"),
    "data.cohort_split_feasibility": (_A, "maintenance"),
    "data.feasibility": (_A, "maintenance"),
    "data.feasibility_cli": (_A, "maintenance"),
    "data.feasibility_sampling": (_A, "maintenance"),
    "data.hero_traits": (_A, "maintenance"),
    "data.lineup_preflight": (_A, "maintenance"),
    "data.match_snapshot": (_A, "active"),
    "data.match_table": (_A, "active"),
    "data.player_overlap": (_A, "maintenance"),
    "data.purchase_observation": (_A, "maintenance"),
    "data.purchase_snapshot": (_A, "maintenance"),
    "data.random_cohort_snapshot": (_A, "maintenance"),
    "data.task_snapshot": (_A, "maintenance"),
    "data.whole_log_snapshot": (_A, "maintenance"),
    # data: track B (observer-perspective replay evidence and decision points)
    "data.decision_comparison": (_B, "active"),
    "data.gank_events": (_B, "active"),
    "data.gank_depth": (_B, "active"),
    "data.death_tags": (_B, "active"),
    "data.death_risk": (_B, "active"),
    "data.gank_foresight": (_B, "active"),
    "data.catch_threat": (_B, "active"),
    "data.farm_value": (_B, "active"),
    "data.camp_conditions": (_B, "active"),
