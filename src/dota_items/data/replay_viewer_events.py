"""Frozen retrospective jump evidence. Never read or disclose it in team views."""

import hashlib
from collections import defaultdict
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash


class EventEvidence:
    def __init__(self, roots, repository):
        self.repository = Path(repository)
        self.sources = {}
        self.cache = {}
        for root in roots:
            root = Path(root)
            summary_bytes = read_source_bytes(root / "summary.json")
            summary = parse_source_json(summary_bytes)
            for match in summary["matches"]:
                mid = match["match_id"]
                if mid in self.sources:
                    raise ValueError("Duplicate event evidence match")
                self.sources[mid] = (root, summary, hashlib.sha256(summary_bytes).hexdigest())

    def load(self, mid, aligned_manifest):
        if mid not in self.sources:
            return None
        if mid in self.cache:
            return self.cache[mid]
        root, summary, summary_hash = self.sources[mid]
        content = read_source_bytes(root / f"{mid}.json", max_bytes=128 * 1024**2)
        if hashlib.sha256(content).hexdigest() != summary["outputs"][f"{mid}.json"]:
            raise ValueError("Event evidence hash mismatch")
        document = parse_source_json(content)
        if document["match_id"] != mid or document["schema_version"] != "replay-jump-events/1":
            raise ValueError("Event identity/schema mismatch")
        # Bind the event evidence to the very same raw bytes as the displayed timeline.
        raw = {
            h for p, h in aligned_manifest["inputs_and_code"].items() if Path(p).name == "raw.json"
        }
        inputs = summary["inputs"]
        audit_name = document["semantic_audit"]
        if audit_name not in inputs:
            raise ValueError("Unbound semantic audit")
        audit_path = self.repository / audit_name
        if file_hash(audit_path) != inputs[audit_name]:
            raise ValueError("Semantic audit hash mismatch")
        audit = parse_source_json(read_source_bytes(audit_path, max_bytes=128 * 1024**2))
        raw_hash = audit["provenance"]["consumed_files"]["raw.json"]
        if audit["match_id"] != mid or raw != {raw_hash}:
            raise ValueError("Event/timeline source mismatch")
        raw_path = Path(audit["provenance"]["preparation"]) / "raw.json"
        if inputs.get(str(raw_path)) != raw_hash:
            raise ValueError("Raw evidence not bound")
        if file_hash(self.repository / raw_path) != raw_hash:
            raise ValueError("Raw evidence changed")
        grouped = defaultdict(list)
        for jump in document["jumps"]:
            start, end = jump["previous"]["source_tick"], jump["current"]["source_tick"]
            if type(start) is not int or type(end) is not int or start > end:
                raise ValueError("Invalid jump interval")
            events = []
            for event in jump["events"]:
                # Never display future context, even in this retrospective panel.
                if event["tick"] > end or event["scope"] == "future_context":
                    continue
                events.append(
                    {
                        k: event.get(k)
                        for k in (
                            "tick",
                            "game_time_s",
                            "log_type",
                            "inflictor_name",
                            "roles",
                            "source_ref",
                            "scope",
                            "core_candidate",
                            "boundary_candidate",
                            "preceding_candidate",
                            "teleport_modifier_end",
                        )
                    }
                )
            grouped[(jump["player_slot"], end)].append(
                {
                    "previous_tick": start,
                    "current_tick": end,
                    "distance": jump["distance_native_units"],
                    "category": jump["category"],
                    "jump_ref": jump["jump_ref"],
                    "events": events,
                    "causal_verified": False,
                }
            )
        result = {
            "groups": grouped,
            "count": len(document["jumps"]),
            "event_types": document["event_types"],
            "summary_sha256": summary_hash,
        }
        self.cache[mid] = result
        return result

    def attach(self, frame, aligned_manifest):
        # Early return before looking up sources or loading anything: team boundary.
        if frame["view"] != "omniscient":
            return frame
        evidence = self.load(frame["match_id"], aligned_manifest)
        frame["event_evidence_status"] = "available" if evidence else "not_audited"
        for player in frame["players"]:
            player["jump_evidence"] = (
                evidence["groups"].get((player["player_slot"], frame["tick"]), [])
                if evidence
                else []
            )
        return frame
