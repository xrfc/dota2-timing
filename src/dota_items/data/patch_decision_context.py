"""Observer facts and static candidate geometry, without omniscient resource state."""

import copy
import math
import re
from pathlib import PurePosixPath


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


class DecisionContextIndex:
    """Only the observer view is queried; dynamic/cycle hindsight is not accepted."""

    def __init__(self, vision_index, camp_assets, *, exact_patch, map_source_ref):
        if (
            exact_patch != "7.42"
            or camp_assets.get("schema") != "patch-camp-assets/1"
            or camp_assets.get("exact_patch") != exact_patch
            or camp_assets.get("action_review_allowed") is not False
            or camp_assets.get("training_allowed") is not False
        ):
            raise ValueError("Exact candidate map evidence required")
        self.vision, self.exact_patch = vision_index, exact_patch
        if (
            not isinstance(map_source_ref, dict)
            or set(map_source_ref) != {"path", "sha256"}
            or not isinstance(map_source_ref.get("path"), str)
            or not PurePosixPath(map_source_ref["path"]).is_absolute()
            or not isinstance(map_source_ref.get("sha256"), str)
            or not re.fullmatch("[0-9a-f]{64}", map_source_ref["sha256"])
        ):
            raise ValueError("Explicit absolute map source reference required")
        self.map_source_ref = copy.deepcopy(map_source_ref)
        self.camps = []
        seen = set()
        for camp in camp_assets["camps"]:
            cid, box = camp["camp_id"], camp["rectangle"]
            if (
                not isinstance(cid, str)
                or not cid
                or cid in seen
                or set(box) != {"min_x", "max_x", "min_y", "max_y"}
                or not all(_finite(v) for v in box.values())
                or box["min_x"] >= box["max_x"]
                or box["min_y"] >= box["max_y"]
            ):
                raise ValueError("Invalid or duplicate static camp geometry")
            seen.add(cid)
            # Do not copy current-match type timelines, membership, counts or future evidence.
            self.camps.append({"camp_id": cid, "rectangle": dict(box)})
        if not self.camps:
            raise ValueError("Static camp geometry is empty")

    def at(self, *, game_time, replay_tick, observer_team, max_age_seconds):
        view = self.vision.at(
            game_time=game_time,
            replay_tick=replay_tick,
            observer_team=observer_team,
            max_age_seconds=max_age_seconds,
        )
        if (
            view.get("schema") != "patch-decision-view/1"
            or view.get("exact_patch") != self.exact_patch
            or view.get("training_allowed") is not False
            or view.get("action_review_allowed") is not False
        ):
            raise ValueError("Observer view version mismatch")
        known = copy.deepcopy(view["known_view"])
        visible = known["visible_entities"]
        camps = []
        for camp in self.camps:
            box = camp["rectangle"]
            occupants = []
            for entity in visible:
                point = entity.get("position")
                if (
                    entity["class_name"] == "CDOTA_BaseNPC_Creep_Neutral"
                    and point is not None
                    and box["min_x"] <= point["x"] <= box["max_x"]
                    and box["min_y"] <= point["y"] <= box["max_y"]
                ):
                    occupants.append(copy.deepcopy(entity))
            camps.append(
                {
                    "camp_id": camp["camp_id"],
                    "observed_neutral_entities_in_trigger": occupants,
                    "membership_inferred": False,
                    "current_stock": None,
                    "current_phase": None,
                    "blocked": None,
                    "control_team": None,
                    "strategic_region": None,
                    "reason": "visible_position_is_not_camp_membership_or_complete_stock",
                    "phase_reason": "current_patch_evolution_rule_not_admitted",
                }
            )
        objectives = {}
        for kind, npc in (("roshan", "npc_dota_roshan"), ("tormentor", "npc_dota_miniboss")):
            rows = [copy.deepcopy(e) for e in visible if e.get("npc_name") == npc]
            objectives[kind] = {
                "observed_live_entities": rows,
                "status": "observed_live_at_sample" if rows else "current_state_unknown",
                "respawn_deadline": None,
                "reason": "observable_death_and_complete_timer_rule_not_established",
            }
        known["camp_observations"], known["objectives"] = camps, objectives
        return {
            "schema": "patch-decision-context/1",
            "exact_patch": self.exact_patch,
            "known_view": known,
            "provenance": {
                **copy.deepcopy(view["provenance"]),
                "map_geometry": copy.deepcopy(self.map_source_ref),
            },
            "geometry_status": "candidate_static_trigger_not_approved_tactical_region",
            "training_allowed": False,
            "action_review_allowed": False,
            "limits": [
                *view["limits"],
                "An observed neutral inside a trigger need not belong to that camp.",
                "No visible unit does not establish an empty, blocked or unspawned camp.",
                "Omniscient type changes, objective cycles and future outcomes are not inputs.",
                "A source pointer identifies bytes; it does not confer gameplay approval.",
            ],
        }
