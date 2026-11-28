"""Public-handoff integrity, full-population retention and atomic audit publication."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from dota_items.storage import digest, file_hash, write_json

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "b5_camp_conditions", ROOT / "scripts/audit_b5_camp_conditions.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def unit(index, **changes):
    value = dict(
        entity_index=index,
        entity_serial=2,
        unit_name="npc_dota_neutral_test",
        team=4,
        x=0.0,
        y=100.0,
        health=100,
        max_health=100,
        life_state=0,
        missing_reasons=[],
    )
    value.update(changes)
    value["missing_reasons"] = [f"missing_{key}" for key, field in value.items() if field is None]
    return value


@pytest.fixture
def handoff(tmp_path, monkeypatch):
    batch = tmp_path / "batch"
    plan_path, snapshot_path = tmp_path / "plan.json", tmp_path / "snapshot.json"
    mids = [
        mid for mid in range(9000000000, 9000000050) if not audit.awareness_split.is_holdout(mid)
    ][:2]
    matches, publics = [], {}
    for i, mid in enumerate(mids):
        fold = int.from_bytes(hashlib.sha256(f"lane-study-v1:{mid}".encode()).digest(), "big") % 5
        cases = [
            dict(
                match=mid,
                hero="npc_dota_hero_sven",
                t=100 + i * 10 + n,
                fold=fold,
                action="unknown" if n else "stay_lane" if i == 0 else "move_to_jungle",
            )
            for n in range(2)
        ]
        matches.append(
            dict(
                match=mid,
                duration=100 if i == 0 else 200,
                patch=60,
                demo_sha256="a" * 64,
                meta_sha256="b" * 64,
                receipt_sha256="c" * 64,
                cases=cases,
            )
        )
        frames = [
            dict(
                hero=case["hero"],
                t=case["t"],
                tick=3000 + case["t"],
                net_tick=4000 + case["t"],
                status="observed",
                observer=dict(team=2 if i == 0 else 3),
                units=[],
                stock_complete=False,
                empty_confirmed=None,
                camp_id=None,
            )
            for case in cases
        ]
        if i == 0:
            frames[0]["units"] = [
                unit(1),
                unit(2, health=0, life_state=2),
                unit(3, team=2, health=50),
                unit(4, team=3, health=75),
                unit(5, health=None),
            ]
            frames[1].update(status="missing_observer", observer=None)
        else:
            frames[1]["units"] = [unit(6, health=0), unit(7, team=None, health=5)]
        publics[mid] = dict(
            schema="camp-evidence/1",
            source_schema="gem-camp-evidence/1",
            match_id=mid,
            sampling="first_tick_start_before_entity_updates",
            frames=frames,
        )
    plan = dict(
        schema="b5-farm-plan/1", rows_sha256="d" * 64, routes_sha256="e" * 64, matches=matches
    )
    write_json(plan_path, plan)
    population = [case for match in matches for case in match["cases"]]
    monkeypatch.setattr(audit, "MATCHES", 2)
    monkeypatch.setattr(audit, "OPPORTUNITIES", 4)
    monkeypatch.setattr(audit, "ACTIONS", dict(stay_lane=1, move_to_jungle=1, unknown=2))
    monkeypatch.setattr(audit, "PLAN_SHA256", file_hash(plan_path))
    monkeypatch.setattr(audit, "POPULATION_SHA256", digest(population))
    manifest = dict(
        schema="b5-camp-run/1",
        plan_sha256=audit.PLAN_SHA256,
        population_sha256=audit.POPULATION_SHA256,
        compat_manifest_sha256=audit.COMPAT_SHA256,
        implementation_sha256={"frozen-public-producer.py": "f" * 64},
    )
    write_json(batch / "manifest.json", manifest)
    monkeypatch.setattr(audit, "MANIFEST_SHA256", file_hash(batch / "manifest.json"))
    files = {}
    for match in matches:
        mid = match["match"]
        directory = batch / "matches" / str(mid)
        write_json(directory / "evidence.json", publics[mid])
        receipt = dict(
            schema="b5-camp-record/1",
            match_id=mid,
            source=match,
            binding=manifest,
            raw_sha256="0" * 64,
            evidence_sha256=file_hash(directory / "evidence.json"),
        )
        receipt["payload_sha256"] = digest(receipt)
        write_json(directory / "receipt.json", receipt)
        # Poison files are deliberately present, but must never be opened.
        (directory / "raw.json").write_text("DO NOT READ OMNISCIENT MATERIAL")
        for name in ("receipt.json", "evidence.json"):
            files[f"matches/{mid}/{name}"] = file_hash(directory / name)
    snapshot = dict(
        schema="camp-quality-snapshot/1",
        plan_sha256=audit.PLAN_SHA256,
        manifest_sha256=audit.MANIFEST_SHA256,
        published_matches=mids,
        files_sha256=files,
    )
    write_json(snapshot_path, snapshot)
    monkeypatch.setattr(audit, "SNAPSHOT_SHA256", file_hash(snapshot_path))
    return dict(
        plan_path=plan_path, batch=batch, snapshot_path=snapshot_path, out=tmp_path / "audit"
    )


def first_bundle(handoff):
    return sorted((handoff["batch"] / "matches").iterdir())[0]


def resign_receipt(directory):
    value = json.loads((directory / "receipt.json").read_bytes())
    value["evidence_sha256"] = file_hash(directory / "evidence.json")
    value.pop("payload_sha256")
    value["payload_sha256"] = digest(value)
    write_json(directory / "receipt.json", value)


def reanchor_snapshot(handoff, monkeypatch):
    """Synthetic fixture-only anchor change to exercise checks beyond the trusted hash."""
    path = handoff["snapshot_path"]
    value = json.loads(path.read_bytes())
    value["files_sha256"] = {
        relative: file_hash(handoff["batch"] / relative) for relative in value["files_sha256"]
    }
    write_json(path, value)
    monkeypatch.setattr(audit, "SNAPSHOT_SHA256", file_hash(path))


def test_complete_public_audit_retains_unknown_and_null_facts(handoff, monkeypatch):
    read_paths = []
    original = audit.source_io.read_source_bytes

    def bounded_read(path, **kwargs):
        assert path.name != "raw.json" and "demos" not in path.parts
        read_paths.append(path)
        return original(path, **kwargs)

    monkeypatch.setattr(audit.source_io, "read_source_bytes", bounded_read)
    summary = audit.audit(**handoff)
    assert summary["complete_population"] and summary["opportunities"] == 4
    assert summary["action_population"] == dict(stay_lane=1, move_to_jungle=1, unknown=2)
    totals = summary["overall"]
    assert totals["facts_available_frames"] == 3 and totals["facts_unavailable_frames"] == 1
    assert totals["observed_zero_visible_frames"] == 1
    assert totals["fact_observation_sums"] == dict(
        visible_units=7,
        alive=4,
        not_alive=1,
        life_unknown=1,
        life_conflict=1,
        alive_neutral_team=1,
        alive_player_team=2,
        alive_other_or_unknown_team=1,
        alive_neutral_team_visible_health_sum=100,
    )
    assert totals["team_relation_observations"] == dict(
        neutral=4, own=1, opponent=1, other_or_unknown=1
    )
    assert all(status == {"unconfirmed": 4} for status in totals["condition_statuses"].values())
    assert all(
        reasons["observation_unavailable"] == 1
        for reasons in totals["condition_missing_evidence"].values()
    )
    rows = [json.loads(line) for line in (handoff["out"] / "frames.jsonl").read_text().splitlines()]
    assert len(rows) == 4 and rows[1]["audit_metadata"]["action"] == "unknown"
    assert rows[1]["frame"]["facts"] is None
    assert all("action" not in row["frame"] and "fold" not in row["frame"] for row in rows)
    assert all(
        row["frame"]["stock_complete"] is False and row["frame"]["empty_confirmed"] is None
        for row in rows
    )
    assert summary["planned_at_duration"] == 1 and summary["planned_after_duration"] == 1
    assert len(summary["duration_boundary_cases"]) == 2  # No end-of-match exclusion.
    for groups in summary["groups"].values():
        assert sum(group["statistics"]["frames"] for group in groups) == 4
    assert len(read_paths) == 7  # plan + manifest + snapshot + two public/receipt pairs
    provenance = json.loads((handoff["out"] / "provenance.json").read_bytes())
    assert provenance["inputs_sha256_before"] == provenance["inputs_sha256_after"]
    assert provenance["producer_sha256_before"] == provenance["producer_sha256_after"]
    assert len(provenance["producer_sha256_before"]) == 5


def test_fixed_defaults_match_accepted_handoff():
    assert (audit.MATCHES, audit.OPPORTUNITIES) == (1169, 15005)
    assert audit.ACTIONS == dict(stay_lane=6235, move_to_jungle=1176, unknown=7594)
    assert (
        audit.MANIFEST_SHA256 == "7e196e7f1c149d790ebd5132ba6f070f30d4dc2da492019383cf41f62f124318"
    )
    assert (
        audit.SNAPSHOT_SHA256 == "46caa3fff31a0cb0ba5dbcdab921c35a77c27432c024b4e48f2b02eaec391582"
    )


@pytest.mark.parametrize("target", ["plan_path", "snapshot_path", "manifest"])
def test_accepted_input_requires_exact_bytes_before_public_reads(handoff, target):
    path = handoff["batch"] / "manifest.json" if target == "manifest" else handoff[target]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="accepted input fingerprint"):
        audit.audit(**handoff)
    assert not handoff["out"].exists()


@pytest.mark.parametrize("mutation", ["change", "drop", "duplicate", "extra_public_field"])
def test_changed_public_and_resigned_receipt_still_fail_accepted_snapshot(handoff, mutation):
    directory = first_bundle(handoff)
    value = json.loads((directory / "evidence.json").read_bytes())
    if mutation == "change":
        value["frames"][0]["units"][0]["health"] += 1
    elif mutation == "drop":
        value["frames"].pop()  # The original unknown opportunity must remain.
    elif mutation == "duplicate":
        value["frames"].append(deepcopy(value["frames"][0]))
    else:
        value["frames"][0]["hidden_units"] = 55
    write_json(directory / "evidence.json", value)
    resign_receipt(directory)
    with pytest.raises(ValueError, match="accepted input fingerprint"):
        audit.audit(**handoff)
    assert not handoff["out"].exists()


@pytest.mark.parametrize("mutation", ["source_action", "producer", "match_id", "checksum"])
def test_receipt_is_independently_validated_after_anchor(handoff, monkeypatch, mutation):
    directory = first_bundle(handoff)
    path = directory / "receipt.json"
    value = json.loads(path.read_bytes())
    if mutation == "source_action":
        value["source"]["cases"][0]["action"] = "unknown"
    elif mutation == "producer":
        value["binding"]["implementation_sha256"] = {"changed.py": "0" * 64}
    elif mutation == "match_id":
        value["match_id"] = True
    else:
        value["payload_sha256"] = "0" * 64
    if mutation != "checksum":
        value.pop("payload_sha256")
        value["payload_sha256"] = digest(value)
    write_json(path, value)
    reanchor_snapshot(handoff, monkeypatch)
    with pytest.raises(ValueError, match="receipt"):
        audit.audit(**handoff)
    assert not handoff["out"].exists()


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "nonpublic"])
def test_frame_population_and_core_whitelist_are_checked(handoff, monkeypatch, mutation):
    directory = first_bundle(handoff)
    path = directory / "evidence.json"
    value = json.loads(path.read_bytes())
    if mutation == "drop":
        value["frames"].pop()
    elif mutation == "duplicate":
        value["frames"].append(deepcopy(value["frames"][0]))
    else:
        value["frames"][0]["units"][0]["owner"] = 123
    write_json(path, value)
    resign_receipt(directory)
    reanchor_snapshot(handoff, monkeypatch)
    with pytest.raises(ValueError):
        audit.audit(**handoff)


@pytest.mark.parametrize("extra", [True, False])
def test_incomplete_or_unknown_published_population_rejected(handoff, extra):
    if extra:
        (handoff["batch"] / "matches" / "123").mkdir()
    else:
        first_bundle(handoff).rename(handoff["batch"] / "removed-match")
    with pytest.raises(ValueError, match="incomplete or unplanned"):
        audit.audit(**handoff)
    assert not handoff["out"].exists()


def test_heldout_rejected_before_receipt_or_public_reads(handoff, monkeypatch):
    plan = json.loads(handoff["plan_path"].read_bytes())
    heldout = next(
        mid for mid in range(9000000000, 9000000050) if audit.awareness_split.is_holdout(mid)
    )
    plan["matches"][0]["match"] = heldout
    write_json(handoff["plan_path"], plan)
    monkeypatch.setattr(audit, "PLAN_SHA256", file_hash(handoff["plan_path"]))
    with pytest.raises(ValueError, match="heldout"):
        audit.audit(**handoff)
    assert not handoff["out"].exists()


@pytest.mark.parametrize("mutation", ["action", "fold", "duplicate"])
def test_original_plan_invariants_not_only_top_hash(handoff, monkeypatch, mutation):
    plan = json.loads(handoff["plan_path"].read_bytes())
    case = plan["matches"][0]["cases"][0]
    if mutation == "action":
        case["action"] = "unknown"
    elif mutation == "fold":
        case["fold"] = (case["fold"] + 1) % 5
    else:
        plan["matches"][0]["cases"].append(deepcopy(case))
    write_json(handoff["plan_path"], plan)
    monkeypatch.setattr(audit, "PLAN_SHA256", file_hash(handoff["plan_path"]))
    with pytest.raises(ValueError):
        audit.audit(**handoff)


def test_core_cannot_drop_or_change_frame_identity(handoff, monkeypatch):
    original = audit.camp_conditions.summarize_camp_evidence

    def drop(value):
        result = original(value)
        result["frames"].pop()
        return result

    monkeypatch.setattr(audit.camp_conditions, "summarize_camp_evidence", drop)
    with pytest.raises(ValueError, match="omitted or changed"):
        audit.audit(**handoff)
    assert not handoff["out"].exists()


@pytest.mark.parametrize(
    "target", ["public", "receipt", "plan", "snapshot", "manifest", "inventory"]
)
def test_input_drift_during_consumption_cannot_publish(handoff, monkeypatch, target):
    original = audit.camp_conditions.summarize_camp_evidence
    changed = False

    def mutate(value):
        nonlocal changed
        result = original(value)
        if not changed:
            changed = True
            paths = dict(
                public=first_bundle(handoff) / "evidence.json",
                receipt=first_bundle(handoff) / "receipt.json",
                plan=handoff["plan_path"],
                snapshot=handoff["snapshot_path"],
                manifest=handoff["batch"] / "manifest.json",
            )
            if target == "inventory":
                (handoff["batch"] / "matches" / "123").mkdir()
            else:
                path = paths[target]
                path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(audit.camp_conditions, "summarize_camp_evidence", mutate)
    with pytest.raises(ValueError, match="changed"):
        audit.audit(**handoff)
    assert not handoff["out"].exists()


def test_producer_drift_cannot_publish(handoff, monkeypatch):
    source = handoff["out"].parent / "producer.py"
    source.write_text("before")
    monkeypatch.setattr(audit, "producer_sources", lambda: {str(source): file_hash(source)})
    original = audit.camp_conditions.summarize_camp_evidence

    def mutate(value):
        result = original(value)
        source.write_text("after")
        return result

    monkeypatch.setattr(audit.camp_conditions, "summarize_camp_evidence", mutate)
    with pytest.raises(ValueError, match="producer changed"):
        audit.audit(**handoff)
    assert not handoff["out"].exists()


def test_imported_module_must_belong_to_executing_producer(handoff, monkeypatch):
    monkeypatch.setattr(audit.camp_conditions, "__file__", str(handoff["out"].parent / "other.py"))
    with pytest.raises(ValueError, match="outside this checkout"):
        audit.audit(**handoff)


def test_deterministic_three_outputs_and_no_overwrite(handoff):
    audit.audit(**handoff)
    first = {p.name: p.read_bytes() for p in handoff["out"].iterdir()}
    assert set(first) == {"frames.jsonl", "summary.json", "provenance.json"}
    second = dict(handoff, out=handoff["out"].with_name("repeat"))
    audit.audit(**second)
    assert first == {p.name: p.read_bytes() for p in second["out"].iterdir()}
    with pytest.raises(ValueError, match="existing condition audit"):
        audit.audit(**handoff)


@pytest.mark.parametrize("location", ["batch", "producer"])
def test_output_not_inside_input_or_producer(handoff, location):
    handoff["out"] = (
        handoff["batch"] / "output" if location == "batch" else ROOT / "src" / "unexpected-output"
    )
    with pytest.raises(ValueError, match="outside batch and producer"):
        audit.audit(**handoff)


def test_receipt_symlink_is_not_an_accepted_input(handoff):
    path = first_bundle(handoff) / "receipt.json"
    actual = handoff["out"].parent / "receipt-backup.json"
    path.rename(actual)
    path.symlink_to(actual)
    with pytest.raises(ValueError, match="symlink"):
        audit.audit(**handoff)


def test_resigning_public_receipt_and_snapshot_cannot_replace_accepted_anchor(handoff):
    directory = first_bundle(handoff)
    public_path = directory / "evidence.json"
    value = json.loads(public_path.read_bytes())
    value["frames"][0]["units"][0]["health"] += 1
    write_json(public_path, value)
    resign_receipt(directory)
    snapshot = json.loads(handoff["snapshot_path"].read_bytes())
    snapshot["files_sha256"] = {
        relative: file_hash(handoff["batch"] / relative) for relative in snapshot["files_sha256"]
    }
    write_json(handoff["snapshot_path"], snapshot)
    # The recorded external acceptance fingerprint stays fixed.
    with pytest.raises(ValueError, match="accepted input fingerprint"):
        audit.audit(**handoff)
    assert not handoff["out"].exists()


def test_later_match_cannot_hide_changes_to_an_earlier_read(handoff, monkeypatch):
    original = audit.camp_conditions.summarize_camp_evidence
    first_mid = int(first_bundle(handoff).name)

    def mutate(value):
        result = original(value)
        if value["match_id"] != first_mid:
            path = first_bundle(handoff) / "evidence.json"
            path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(audit.camp_conditions, "summarize_camp_evidence", mutate)
    with pytest.raises(ValueError, match="input or producer changed"):
        audit.audit(**handoff)
    assert not handoff["out"].exists()
