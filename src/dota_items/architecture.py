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
    "handoff": (_S, "active"),
    "handoff.bundle": (_S, "active"),
    # sources
    "sources": (_S, "active"),
    "sources.collection_history": (_S, "active"),
    "sources.gem_capture": (_S, "active"),
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
    "data.mechanics_rules_v11": (_S, "active"),
    "data.mechanics_facts_v19": (_S, "active"),
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
    "data.decision_context": (_B, "active"),
    "data.decision_evidence": (_B, "active"),
    "data.decision_mana": (_B, "active"),
    "data.decision_state": (_B, "active"),
    "data.decision_team_state": (_B, "active"),
    "data.replay_identity": (_B, "maintenance"),
    "data.replay_jump_events": (_B, "maintenance"),
    "data.replay_semantics": (_B, "active"),
    "data.replay_status": (_B, "active"),
    "data.replay_viewer": (_B, "active"),
    "data.replay_viewer_events": (_B, "active"),
    "data.tick_alignment": (_B, "active"),
    # modeling: shared learning infrastructure
    "modeling": (_S, "active"),
    "modeling._validation": (_S, "active"),
    "modeling.evaluation": (_S, "active"),
    # modeling: track A
    "modeling.artifacts": (_A, "active"),
    "modeling.batch": (_A, "active"),
    "modeling.estimators": (_A, "active"),
    "modeling.estimators.frequency": (_A, "active"),
    "modeling.estimators.logistic": (_A, "active"),
    "modeling.foundation": (_A, "maintenance"),
    "modeling.inference": (_A, "active"),
    "modeling.inspection": (_A, "active"),
    "modeling.item_timing": (_A, "active"),
    "modeling.lineup_analysis": (_A, "active"),
    "modeling.lineup_comparison": (_A, "active"),
    "modeling.provenance": (_A, "active"),
    "modeling.purchase_baseline": (_A, "maintenance"),
    "modeling.purchase_diagnostics": (_A, "maintenance"),
    "modeling.purchase_sensitivity": (_A, "maintenance"),
    "modeling.sensitivity_report": (_A, "maintenance"),
    "modeling.situational_items": (_A, "active"),
    "modeling.situational_reference": (_A, "active"),
    "modeling.specs": (_A, "active"),
    "modeling.synthetic_foundation": (_A, "maintenance"),
    "modeling.training": (_A, "active"),
    "modeling.whole_log_comparison": (_A, "maintenance"),
    "modeling.whole_log_diagnostics": (_A, "maintenance"),
    # experiments: track A historical whole-log experiment
    "experiments": (_S, "active"),
    "experiments.whole_log": (_A, "maintenance"),
    "experiments.whole_log.baseline": (_A, "maintenance"),
    "experiments.whole_log.diagnostics": (_A, "maintenance"),
    "experiments.whole_log.handoff": (_A, "maintenance"),
    "experiments.whole_log.inputs": (_A, "maintenance"),
    "experiments.whole_log.io": (_A, "maintenance"),
    "experiments.whole_log.regularization": (_A, "maintenance"),
    # recommendation: track A rule prototype (7.41f lineup rules)
    "recommendation": (_A, "maintenance"),
    "recommendation.cli": (_A, "maintenance"),
    "recommendation.contracts": (_A, "maintenance"),
    "recommendation.engine": (_A, "maintenance"),
    "recommendation.files": (_A, "maintenance"),
    "recommendation.knowledge": (_A, "maintenance"),
    "recommendation.report": (_A, "maintenance"),
    # workflow: coach workspace (prepare/observe/doctor), shared
    "workflow": (_S, "active"),
    "workflow.admission": (_S, "active"),
    "workflow.cli": (_S, "active"),
    "workflow.contracts": (_S, "active"),
    "workflow.datasets": (_S, "active"),
    "workflow.demo": (_S, "active"),
    "workflow.jobs": (_S, "active"),
    "workflow.processes": (_S, "active"),
    "workflow.replay_audit": (_S, "active"),
    "workflow.reviews": (_S, "active"),
    "workflow.templates": (_S, "active"),
    "workflow.validation": (_S, "active"),
    "workflow.workspace": (_S, "active"),
}

# scripts/<name>.py -> track (scripts are entry points; layer rules do not apply)
SCRIPTS = {
    # shared: environment, checks, collection plumbing, replay ingestion, knowledge
    "bootstrap": _S,
    "check": _S,
    "accept_replays": _S,
    "audit_saved_replays": _S,
    "build_replay_compat": _S,
    "verify_context_replays": _S,
    "recover_large_replay_cleaning": _S,
    "collect_purchase_guarded": _S,
    "run_purchase_additional": _S,
    "export_collection_table": _S,
    "build_item_registry": _S,
    "refresh_hero_datafeed": _S,
    "build_mechanics_facts": _S,
    "build_mechanics_facts_v2": _S,
    "build_mechanics_facts_v3": _S,
    "build_mechanics_facts_v4": _S,
    "build_mechanics_facts_v5": _S,
    "build_mechanics_facts_v6": _S,
    "build_mechanics_facts_v7": _S,
    "build_mechanics_facts_v8": _S,
    "build_mechanics_facts_v9": _S,
    "build_mechanics_facts_v10": _S,
    "build_mechanics_facts_v11": _S,
    "build_mechanics_facts_v12": _S,
    "build_mechanics_facts_v13": _S,
    "build_mechanics_facts_v14": _S,
    "build_mechanics_facts_v15": _S,
    "build_mechanics_facts_v16": _S,
    "build_mechanics_facts_v17": _S,
    "build_mechanics_facts_v18": _S,
    "build_mechanics_derived": _S,
    "build_mechanics_derived_v2": _S,
    "build_mechanics_derived_v3": _S,
    "build_mechanics_derived_v4": _S,
    "build_mechanics_derived_v5": _S,
    "build_mechanics_derived_v6": _S,
    "build_mechanics_derived_v7": _S,
    "build_mechanics_derived_v8": _S,
    "check_mechanics_recall": _S,
    "build_mechanics_facts_v19": _S,
    "build_mechanics_derived_v9": _S,
    "collect_build_survey": _S,
    "build_mechanics_current": _S,
    "build_mechanics_profiles": _S,
    "build_stale_upgrade_text": _S,
    "fetch_game_files_snapshot": _S,
    "check_break_against_game_files": _S,
    "audit_mechanics_against_game_files": _S,
    "build_retired_items": _S,
    "mechanics_cross_review": _S,
    # track A
    "analyze_cohort_splits": _A,
    "audit_evaluation_feasibility": _A,
    "audit_purchase_cohorts": _A,
    "audit_purchase_observations": _A,
    "build_match_table": _A,
    "build_situational_reference": _A,
    "coach_app": _A,
    "collect_evaluation_cohort": _A,
    "collect_purchase_additional": _A,
    "collect_purchase_candidates": _A,
    "collect_purchase_latest": _A,
    "collect_purchase_until_daily": _A,
    "compare_purchase_sensitivity": _A,
    "diagnose_purchase_baseline": _A,
    "diagnose_whole_log_experiment": _A,
    "hero_trait_crosscheck": _A,
    "lineup_analysis": _A,
    "lineup_comparison": _A,
    "model_foundation": _A,
    "package_purchase_handoff": _A,
    "prepare_purchase_preview": _A,
    "prepare_purchase_snapshot": _A,
    "prepare_random_cohort": _A,
    "prepare_whole_log_cohort": _A,
    "probe_evaluation_sources": _A,
    "render_purchase_sensitivity": _A,
    "report_purchase_cohorts": _A,
    "report_whole_log_regularization": _A,
    "run_whole_log_experiment": _A,
    "run_whole_log_regularization": _A,
    "summarize_purchase_collection": _A,
    "train_item_timing": _A,
    "train_purchase_baseline": _A,
    "train_situational_items": _A,
    "verify_whole_log_handoff": _A,
    "whole_log_experiment": _A,
    "whole_log_regularization": _A,
    # track B
    "align_replay_ticks": _B,
    "attach_decision_mana": _B,
    "attach_team_state": _B,
    "audit_decision_mana": _B,
    "audit_replay_identity": _B,
    "audit_replay_jump_events": _B,
    "audit_replay_map_landmarks": _B,
    "audit_replay_semantics": _B,
    "audit_replay_tracks": _B,
    "build_decision_comparisons": _B,
    "build_decision_state_cards": _B,
    "collect_replay_expansion": _B,
    "decision_review": _B,
    "enhance_decision_cases": _B,
    "export_raw_replay_channels": _B,
    "probe_decision_state": _B,
    "probe_team_state": _B,
    "render_replay_semantics": _B,
    "repair_decision_mana": _B,
    "replay_viewer": _B,
    "report_replay_identity": _B,
    "revise_decision_review": _B,
    "run_replay_pilot": _B,
}

# importer track -> tracks it must not import
FORBIDDEN_TRACK_IMPORTS = {
    SHARED: (RECOMMEND, AWARENESS),
    RECOMMEND: (AWARENESS,),
    AWARENESS: (RECOMMEND,),
}


def track_of(module):
    """Track of a dotted module name inside dota_items (most specific entry wins)."""
    name = module.removeprefix("dota_items").removeprefix(".")
    while name:
        if name in MODULES:
            return MODULES[name][0]
        name = name.rpartition(".")[0]
    if module == "dota_items":
        return MODULES[""][0]
    raise KeyError(module)  # unclassified modules never fall back to the package root


def modules_in(track):
    return sorted(name for name, (owner, _) in MODULES.items() if owner == track)
