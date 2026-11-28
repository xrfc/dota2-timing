"""Fixed-source engineering proofs, independent of fact admission and user rulings.

Callers read and pin all source bytes. This pure builder checks explicit current
text and fields; it does not mutate the frozen candidate or approve semantics.
"""

import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import PurePosixPath

POLICY = "mechanics-engineering-evidence/7.42-v1"
HERO_IDS = (10, 33, 44, 45, 54, 56, 69, 82, 85, 87)
SOURCE_PATHS = {
    **{
        f"hero_{hero}_{language}": (
            f"knowledge/hero-capabilities/snapshots/2026-11-19/sources/hero-{hero}-{language}.json"
        )
        for hero in HERO_IDS
        for language in ("english", "schinese")
    },
    "items": "knowledge/items/sources/itemdata-english-2026-11-19/items.json",
    "vocabulary": "knowledge/mechanics/vocabulary-v15.json",
    "claim_key": "knowledge/mechanics/reviews/blind-742-001/claim-key.json",
    "blind_answers": "knowledge/mechanics/reviews/blind-742-001/answers.json",
    "recheck": "knowledge/mechanics/reviews/recheck-742-001/claude-review.json",
}
TARGETS = (
    (
        "ebbbbe178b11c4ce1cbd",
        56,
        "clinkz_death_pact",
        "target enemy creep",
        "敌方非英雄单位",
        "enemy_creep",
    ),
    (
        "0e234c07bae2d264c62c",
        69,
        "doom_bringer_devour",
        "enemy or neutral creep",
        "敌军或中立生物",
        "enemy_or_neutral_creep",
    ),
    (
        "8804d4b34b90572aa12b",
        54,
        "life_stealer_infest",
        "enemy creep or a neutral creep",
        "敌方非英雄单位或中立生物",
        "enemy_creep_base_enemy_hero_requires_scepter",
    ),
    (
        "0dba6399710fa947dc5d",
        10,
        "morphling_replicate",
        "targeted enemy",
        "敌方目标",
        "enemy_target",
    ),
    (
        "c4c9a19f3fd010964b01",
        44,
        "phantom_assassin_phantom_strike",
        "unit, friendly or enemy",
        "敌我皆可",
        "friendly_or_enemy_unit",
    ),
    (
        "9651e7885caaf7fd1553",
        45,
        "pugna_decrepify",
        "afflicted enemies",
        "受作用的敌军",
        "friendly_or_enemy_unit",
    ),
    (
        "d5e57f0f93f66dedf40f",
        85,
        "undying_soul_rip",
        "heal an ally, or damage an enemy",
        "队友或伤害敌人",
        "friendly_or_enemy_unit",
    ),
)


# Full selected text fingerprints prevent a changed/negated statement retaining a proof.
TEXT_SHA256 = {
    (
        "enigma_malefice",
        "english",
        "shard_loc",
    ): "8c79ff5bbf61fea2b15d345b9de2e1418816ddc35b7400d8f067955275294fe3",
    (
        "enigma_malefice",
        "schinese",
        "shard_loc",
    ): "2d805f855aa0ece20052acb6500e527591fe37074c28ef49d57b0ebf39ed5d51",
    (
        "life_stealer_open_wounds",
        "english",
        "desc_loc",
    ): "d005ebf104836519eb8005da48089fbaf026d2b5bbe1478d436750a48cfab384",
    (
        "life_stealer_infest",
        "english",
        "desc_loc",
    ): "c1724992c8947c53e429a14c4607a72f6762da5ef82319b000fecf38b09c8e20",
    (
        "life_stealer_infest",
        "english",
        "shard_loc",
    ): "778c236456f8460750d3e8e9f050bd62f9fcacad4741c04eacb9c9780780e5ed",
    (
        "life_stealer_open_wounds",
        "schinese",
        "desc_loc",
    ): "1c61ceccf7bc8db8137df2fc86900f000ca670444649efe141f02889eb788f5d",
    (
        "life_stealer_infest",
        "schinese",
        "desc_loc",
    ): "88947a2730c27807fe7dddd99c8acd090da6da1d71a813e2b93d070ebaf4c989",
    (
        "life_stealer_infest",
        "schinese",
        "shard_loc",
    ): "5470dad823fb5719f2084733608996b250d1c59f4fd634c999542cecd4d6fb85",
    (
        "disruptor_kinetic_fence",
        "english",
        "desc_loc",
    ): "f621899e9a2d1bc324a326b835dffea8ef9e7ddc0f474bb5aace10d0ebdc8d5a",
    (
        "disruptor_electromagnetic_repulsion",
        "english",
        "desc_loc",
    ): "7e21a2571233beb8afa3eda5e42f50986f033ec2e8e7165a0cea714d268467a5",
    (
        "disruptor_kinetic_fence",
        "schinese",
        "desc_loc",
    ): "bb5994152882f9f388482464d9641e1ec15254bd3008fe3a684db0e671bd87af",
    (
        "disruptor_electromagnetic_repulsion",
        "schinese",
        "desc_loc",
    ): "f8fff2e2560f4d5c60f1a0f045acb28a485f93fdbe0518e61f566a3df58951a9",
    (
        "clinkz_death_pact",
        "english",
        "desc_loc",
    ): "d9e3bb3679bc5fdbc2923aa4fb06cdb959168ddc96fcb821d2dcdad1e3d7f14d",
    (
        "clinkz_death_pact",
        "schinese",
        "desc_loc",
    ): "4ec24cbe072bc4cb02c4e12d9f1a99ba0f04532936637f40a7746ad7014a4572",
    (
        "doom_bringer_devour",
        "english",
        "desc_loc",
    ): "4f89a3112513ab55df28af312db06b40896e396029981ff5c575cccbb8f9a91e",
    (
        "doom_bringer_devour",
        "schinese",
        "desc_loc",
    ): "2b8e53b09dfded4951c39cb1160d1e10e2cbca01daeff62d930f933d0c0c5fe8",
    (
        "morphling_replicate",
        "english",
        "desc_loc",
    ): "8aad2b08521a3b312a0a86eae21ab6336e572f7f1335ef709d71114f4585894e",
    (
        "morphling_replicate",
        "schinese",
        "desc_loc",
    ): "80afd384b7fd5d7fe1167be501ae77222efc41b49811aaac60a19128cb9b2e15",
    (
        "phantom_assassin_phantom_strike",
        "english",
        "desc_loc",
    ): "2e66e1538cb6fc8385482fc438df6e9e3b6d89622e90d52e4ab1936b668a27af",
    (
        "phantom_assassin_phantom_strike",
        "schinese",
        "desc_loc",
    ): "e56b21fcec03662d568b7f09f1e14312c5e1ce0f9089f368c372b70cc197183a",
    (
        "pugna_decrepify",
        "english",
        "desc_loc",
    ): "224d2cff2a9c9720f69b9753d6acd7b62993a96bbee58a226ccda35e3eb2cce6",
    (
        "pugna_decrepify",
        "schinese",
        "desc_loc",
    ): "d9c440ca5db0bd0eb889a53bd7ad22c6b15985f0a7818877dab673d77c91b1a5",
    (
        "undying_soul_rip",
        "english",
        "desc_loc",
    ): "8310dbe1a70d84c1fd5c6c9c7d59776a1e9951c455eb7db5a0a228a0ecd8e79e",
    (
        "undying_soul_rip",
        "schinese",
        "desc_loc",
    ): "a293a78893c50bc8523cec87b0f7cfec3f7fe398227a8a72e5528dbec62173cd",
    (
        "meepo_poof",
        "english",
        "desc_loc",
    ): "51a00fe085a9d25880abfaf493e9cc8ab44e96eae36ccf8f333df0d392d8069c",
    (
        "meepo_poof",
        "schinese",
        "desc_loc",
    ): "303f450576ef7773ff24e149cba08b6dc6e25c6bb44dbdebc5671c65d9dbe32f",
    (
        "item_meteor_hammer",
        "english",
        "desc_loc",
    ): "f776c89d3beaebc5d1045a5940c5ceba3b239a90631b129179225568a658d7a2",
}


VOCABULARY_ROW_SHA256 = {
    "summons": "4210530accb4e1147eb29efab88934faf0338d069296d948a9c2ebf03babc011",
    "slow": "61eaadc320f81b017e617f1b02efd7bbdbed33466c5dccd34ad039d9be007581",
    "healing": "35841757f4c14190073453fa24a7f15f03cdcd2487a90d3a0449fddcedd9c8b7",
    "lifesteal": "ed359a4ebe69a92d77657d9b7d2b3dc4cae1dc5b43f9e3b8a893c23f73819df4",
    "aoe_damage": "3addd444f5336d43ce245eebf4ad4d7ad10caf9610e3d4c688f68a547ef29948",
    "unit_target_spell": "d370026af21e17b024ace0015858b8aaf6e6829d11b18a8c893e1bbb8546c486",
    "channeled": "5e0ad70a491f3202b800c95cc2ed9058e8e32a28176dcf4b12b77429e2fb4adc",
}


def _unique(rows, key, value):
    if not isinstance(rows, list):
        raise ValueError("Evidence rows must be a list")
    found = [
        (i, row) for i, row in enumerate(rows) if isinstance(row, dict) and row.get(key) == value
    ]
    if len(found) != 1:
        raise ValueError(f"Expected one {key}={value}")
    return found[0]


def _number(value):
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        return int(value)
    return None


class _Proofs:
    def __init__(self, admission, documents, refs):
        self.admission, self.documents, self.refs = admission, documents, refs

    def point(self, source, pointer, value):
        return {
            "source": source,
            "source_ref": copy.deepcopy(self.refs[source]),
            "pointer": pointer,
            "value": copy.deepcopy(value),
        }

    def ability(self, hero, subject, language):
        key = f"hero_{hero}_{language}"
        document = self.documents[key]
        heroes = document["result"]["data"]["heroes"]
        hi, owner = _unique(heroes, "id", hero)
        ai, ability = _unique(owner["abilities"], "name", subject)
        return key, f"/result/data/heroes/{hi}/abilities/{ai}", ability

    def fields(self, hero, subject, names):
        points, values = [], {}
        for language in ("english", "schinese"):
            source, pointer, ability = self.ability(hero, subject, language)
            values[language] = ability
            for name in names:
                if name not in ability:
                    raise ValueError(f"Missing source field: {subject}/{name}")
                points.append(self.point(source, pointer + "/" + name, ability[name]))
        return points, values

    def row(self, review_id, subject, mechanism, context):
        index, fact = _unique(self.admission["rows"], "review_id", review_id)
        if (
            fact.get("subject") != subject
            or fact.get("mechanism") != mechanism
            or fact.get("decision") != "accept"
            or not isinstance(fact.get("condition"), dict)
            or fact["condition"].get("context") != context
            or type(fact.get("candidate_usable")) is not bool
            or type(fact.get("user_approved_for_patch")) is not bool
            or (context == "shard_upgrade" and fact["condition"].get("requires_shard") is not True)
        ):
            raise ValueError("Fact identity, scope or candidate state changed")
        return {
            "review_id": review_id,
            "subject": subject,
            "mechanism": mechanism,
            "current_candidate_state": {
                key: copy.deepcopy(fact[key])
                for key in (
                    "condition",
                    "candidate_usable",
                    "user_approved_for_patch",
                    "patch_evidence_status",
                )
            },
            "admission_ref": self.point("admission", f"/rows/{index}", {"review_id": review_id}),
            "candidate_mutated": False,
            "user_ruling_added": False,
        }

    def definition(self, mechanism):
        index, definition = _unique(self.documents["vocabulary"]["mechanisms"], "id", mechanism)
        digest = hashlib.sha256(
            json.dumps(
                definition, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        if digest != VOCABULARY_ROW_SHA256.get(mechanism):
            raise ValueError("Registered vocabulary definition or decision notes changed")
        return self.point("vocabulary", f"/mechanisms/{index}", definition)

    def claim(self, claim_id, subject, mechanism):
        ci, claim = _unique(self.documents["claim_key"], "claim_id", claim_id)
        ai, answer = _unique(self.documents["blind_answers"], "claim_id", claim_id)
        if (claim.get("subject"), claim.get("mechanism"), claim.get("condition")) != (
            subject,
            mechanism,
            "shard_upgrade",
        ):
            raise ValueError("Claim identity or scope changed")
        return [
            self.point("claim_key", f"/{ci}", claim),
            self.point("blind_answers", f"/{ai}", answer),
        ]


def _has(abilities, english, chinese, field="desc_loc"):
    return all(
        isinstance(abilities[language].get(field), str)
        and token in abilities[language][field]
        and hashlib.sha256(abilities[language][field].encode()).hexdigest()
        == TEXT_SHA256.get((abilities[language].get("name"), language, field))
        for language, token in (("english", english), ("schinese", chinese))
    )


def _enigma(proofs):
    rid, subject = "audit:enigma_malefice:summons:shard", "enigma_malefice"
    row = proofs.row(rid, subject, "summons", "shard_upgrade")
    evidence, abilities = proofs.fields(33, subject, ("name", "shard_loc", "ability_has_shard"))
    index, review = _unique(proofs.documents["recheck"]["rows"], "review_id", rid)
    evidence.append(proofs.point("recheck", f"/rows/{index}", review))
    checks = {
        "enemy_hero_only": _has(
            abilities, "next to enemy Hero targets", "敌方英雄目标身旁", "shard_loc"
        ),
        "each_stun": _has(abilities, "every instance of Malefice stun", "每次", "shard_loc"),
        "summoned_eidolon": _has(abilities, "creates an Eidolon", "产生一个虚灵体", "shard_loc"),
        "does_not_multiply": _has(
            abilities,
            "These Eidolons will not multiply further",
            "这些虚灵体不会再次分裂",
            "shard_loc",
        ),
        "shard_source": all(a.get("ability_has_shard") is True for a in abilities.values()),
        "existing_review_requests_narrowing": review.get("codex") == "condition_changed"
        and review.get("lane") == "keep_two_ai",
    }
    return {
        **row,
        "group": "E1",
        "definition": proofs.definition("summons"),
        "proof_status": "condition_narrowing_proposed"
        if all(checks.values())
        else "source_requirement_unproven",
        "checks": checks,
        "proposed_conditions": {
            "requires_shard": True,
            "target_scope": "enemy_hero",
            "trigger": "each_malefice_stun",
            "summon": "Eidolon",
            "can_multiply": False,
        }
        if all(checks.values())
        else None,
        "evidence": evidence,
        "unknown": ["No actual game execution or formal patch admission was performed."],
    }


def _linked_infest(proofs, mechanism, claim_id):
    subject = "life_stealer_infest"
    row = proofs.row(f"7.42:{subject}:{mechanism}:shard", subject, mechanism, "shard_upgrade")
    evidence, trigger = proofs.fields(54, subject, ("name", "shard_loc"))
    linked_evidence, linked = proofs.fields(
        54, "life_stealer_open_wounds", ("name", "name_loc", "desc_loc", "notes_loc")
    )
    evidence += linked_evidence + proofs.claim(claim_id, subject, mechanism)
    duration_fields = []
    for language, ability in trigger.items():
        index, value = _unique(ability["special_values"], "name", "dot_duration")
        source, pointer, _ = proofs.ability(54, subject, language)
        duration_fields.append(value.get("values_shard"))
        evidence.append(
            proofs.point(
                source, pointer + f"/special_values/{index}/values_shard", value.get("values_shard")
            )
        )
    checks = {
        "explicit_link": _has(
            trigger, "Open Wounds to enemies in the damage radius", "撕裂伤口效果", "shard_loc"
        ),
        "linked_current_name": linked["english"].get("name_loc") == "Open Wounds"
        and linked["schinese"].get("name_loc") == "撕裂伤口",
        "three_second_shard_duration": duration_fields == [[3], [3]],
        "linked_effect": _has(linked, "slowing the victim's movement speed", "减缓受害者的移动速度")
        if mechanism == "slow"
        else _has(
            linked,
            "all allies to regain health for a percentage of the damage they deal",
            "并使所有友军",
        ),
    }
    return {
        **row,
        "claim_id": claim_id,
        "group": "E3",
        "proof_status": "linked_effect_text_supported"
        if all(checks.values())
        else "source_requirement_unproven",
        "checks": checks,
        "evidence": evidence,
        "definition": proofs.definition(mechanism),
        "verified_link": {
            "trigger": "infest_explosion",
            "requires_shard": True,
            "target_scope": "enemies_in_explosion_damage_radius",
            "effect_subject": "life_stealer_open_wounds",
            "duration_seconds": 3,
            "healing_beneficiary": "allies_dealing_damage_to_affected_enemy",
            "healing_and_lifesteal_same_event": True,
        }
        if all(checks.values())
        else None,
        "unknown": [
            "Applied level, strength and damage-source details are not proved by this link.",
            "Existing two_ai_overlay stays unchanged; no new approval or duplicate healing event.",
        ],
    }


def _linked_fence(proofs):
    subject, mechanism = "disruptor_kinetic_fence", "aoe_damage"
    row = proofs.row(f"7.42:{subject}:{mechanism}:shard", subject, mechanism, "shard_upgrade")
    evidence, trigger = proofs.fields(
        87, subject, ("name", "desc_loc", "ability_is_granted_by_shard", "special_values")
    )
    linked_evidence, linked = proofs.fields(
        87, "disruptor_electromagnetic_repulsion", ("name", "name_loc", "desc_loc")
    )
    evidence += linked_evidence + proofs.claim("c073", subject, mechanism)
    checks = {
        "explicit_link": _has(
            trigger,
            "Enemies touching the wall are struck by Electromagnetic Repulsion",
            "触碰墙壁的敌人会被电磁斥力打击",
        ),
        "linked_name": linked["english"].get("name_loc") == "Electromagnetic Repulsion"
        and linked["schinese"].get("name_loc") == "电磁排斥",
        "linked_base_effect_has_damage": _has(
            linked, "all nearby enemies within take damage", "附近所有敌人都会受到"
        ),
        "shard_granted": all(
            a.get("ability_is_granted_by_shard") is True for a in trigger.values()
        ),
    }
    return {
        **row,
        "claim_id": "c073",
        "group": "E3",
        "proof_status": "linked_damage_text_found_trigger_scope_unproven"
        if all(checks.values())
        else "source_requirement_unproven",
        "checks": checks,
        "evidence": evidence,
        "definition": proofs.definition(mechanism),
        "triggered_area_scope_verified": False,
        "chinese_trigger_name_matches_display_name": False,
        "unknown": [
            "Wall-touch does not prove inheritance of the ordinary area, centre or victim set.",
            "Keep candidate history; verify triggered damage scope before formal AoE use.",
            "Chinese wall text names 电磁斥力; the linked current display name is 电磁排斥.",
        ],
    }


def _target(proofs, spec):
    rid, hero, subject, english, chinese, scope = spec
    row = proofs.row(rid, subject, "unit_target_spell", "base")
    evidence, abilities = proofs.fields(
        hero, subject, ("name", "desc_loc", "notes_loc", "behavior", "target_team")
    )
    numbers = [_number(a.get("behavior")) for a in abilities.values()]
    checks = {
        "unit_target_behavior": all(value is not None and value & 8 for value in numbers),
        "bilingual_enemy_target_text": _has(abilities, english, chinese),
        "registered_exception_target_team": all(
            type(a.get("target_team")) is int
            and a["target_team"] == (0 if subject == "clinkz_death_pact" else 4)
            for a in abilities.values()
        ),
    }
    if subject == "life_stealer_infest":
        checks["base_excludes_enemy_heroes"] = _has(
            abilities, "Does not work on enemy heroes", "无法对敌方英雄生效"
        )
    return {
        **row,
        "group": "E2",
        "proof_status": "enemy_target_text_supported"
        if all(checks.values())
        else "source_requirement_unproven",
        "checks": {key: bool(value) for key, value in checks.items()},
        "evidence": evidence,
        "definition": proofs.definition("unit_target_spell"),
        "target_scope": scope if all(checks.values()) else None,
        "spell_block_or_reflect_inferred": False,
        "unknown": [
            "No spell-block/reflect, immunity or every-unit targetability is inferred.",
            "CUSTOM/zero alone cannot settle enemy targeting; current text adds evidence.",
        ],
    }


def _channels(proofs):
    evidence, abilities = proofs.fields(
        82, "meepo_poof", ("name", "desc_loc", "behavior", "channel_times", "special_values")
    )
    meepo = proofs.row("7056861bb759c22212b6", "meepo_poof", "channeled", "base")
    item = proofs.documents["items"].get("meteor_hammer")
    if not isinstance(item, dict) or item.get("name") != "item_meteor_hammer":
        raise ValueError("Current Meteor Hammer identity missing")
    meteor = proofs.row("95b9db1c3a9654525662", "meteor_hammer", "channeled", "item")
    item_evidence = [
        proofs.point("items", f"/meteor_hammer/{name}", item.get(name))
        for name in ("name", "desc_loc", "behavior", "channel_times")
    ]
    for row, points, text in (
        (meepo, evidence, _has(abilities, "after channeling for", "持续施法")),
        (
            meteor,
            item_evidence,
            isinstance(item.get("desc_loc"), str)
            and "CHANNELED - After a %max_duration%s channel" in item["desc_loc"]
            and hashlib.sha256(item["desc_loc"].encode()).hexdigest()
            == TEXT_SHA256[("item_meteor_hammer", "english", "desc_loc")],
        ),
    ):
        row.update(
            group="E2",
            proof_status="channel_text_found_interruption_unproven"
            if text
            else "source_requirement_unproven",
            checks={"explicit_channel_text": text, "interruption_behavior_verified": False},
            evidence=points,
            definition=proofs.definition("channeled"),
            unknown=[
                "The definition requires the caster's channel and stopping when interrupted.",
                "Text and channel fields are recorded; interrupted-cast samples are absent.",
            ],
        )
    return [meepo, meteor]


def build_mechanics_engineering_evidence(admission, documents, *, exact_patch, source_refs):
    """Return auditable proposals; neither fact admission nor gameplay validation changes."""
    if (
        exact_patch != "7.42"
        or not isinstance(admission, dict)
        or admission.get("schema") != "mechanics-action-admission/1"
        or admission.get("policy") != "mechanics-action-assets/7.42-v1"
        or admission.get("status") != "candidate"
        or admission.get("patch") != exact_patch
        or admission.get("formal_use_allowed") is not False
        or admission.get("training_allowed") is not False
        or not isinstance(admission.get("rows"), list)
        or not isinstance(documents, dict)
        or set(documents) != set(SOURCE_PATHS)
        or not isinstance(source_refs, dict)
        or set(source_refs) != set(SOURCE_PATHS) | {"admission"}
    ):
        raise ValueError("Exact current candidate and complete pinned documents required")
    for key, ref in source_refs.items():
        if (
            not isinstance(ref, dict)
            or set(ref) != {"path", "sha256"}
            or not isinstance(ref.get("path"), str)
            or not PurePosixPath(ref["path"]).is_absolute()
            or not isinstance(ref.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", ref["sha256"])
        ):
            raise ValueError("Explicit absolute source reference and SHA256 required")
        if key in SOURCE_PATHS and not ref["path"].endswith("/" + SOURCE_PATHS[key]):
            raise ValueError("Unregistered source location or snapshot version")
    proofs = _Proofs(admission, documents, source_refs)
    rows = [_enigma(proofs)]
    rows.extend(
        _linked_infest(proofs, mechanism, claim)
        for mechanism, claim in (("slow", "c046"), ("lifesteal", "c047"), ("healing", "c048"))
    )
    rows.append(_linked_fence(proofs))
    rows.extend(_target(proofs, spec) for spec in TARGETS)
    rows.extend(_channels(proofs))
    return {
        "schema": "mechanics-engineering-evidence/1",
        "policy": POLICY,
        "patch": exact_patch,
        "source_refs": copy.deepcopy(source_refs),
        "rows": rows,
        "summary": {
            "rows": len(rows),
            "proof_statuses": dict(Counter(row["proof_status"] for row in rows)),
            "candidate_rows_changed": 0,
            "user_rulings_added": 0,
        },
        "formal_use_allowed": False,
        "action_review_allowed": False,
        "training_allowed": False,
        "limits": [
            "Only registered current statements are checked; names/flags alone prove no claim.",
            "Proposals do not mutate admission, add user rulings or certify game execution.",
            "Linked text and triggered targets/radius/strength need separate proofs.",
        ],
    }
