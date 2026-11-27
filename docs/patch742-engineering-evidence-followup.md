# 7.42机制工程补证：条件、关联与字段例外

后续已由[独立新准入生产者](mechanics-evidence-admission.md)消费本页14条证据：8提升、1降级、3补关联、2继续阻断。下文保留原补证阶段事实和旧附件；旧admission字节不变，新候选未准入为96行，不再把“尚未接入”当成当前状态。

本轮复核[机制待决清单](patch742-open-decisions.md)E类工程证据，使用已固定的本地7.42官方快照。**没有修改旧事实、候选准入、用户决定或正式入口**；证据变充分与用户批准是两个状态。G/A/N中的机制分类裁定仍按原清单处理。

## 本轮结果

独立纯模块`data.mechanics_engineering_evidence`输出14条可追溯记录：1条谜团条件收窄提案、3条感染关联效果原文支持、7条单体指向的双语原文与行为字段支持；动能栅栏的触发范围以及两项持续施法的打断行为仍未证明。原103条未准入计数不因这份附件自动减少。

本轮实测输入26份：旧admission＋25份当前来源。每条记录保留原review_id、当前candidate状态、JSON指针和完整文件SHA；选中原文完整字符串及词表条目另做注册指纹检查，改写或给原文加否定前缀不能继续匹配旧证明。

## E1：谜团魔晶召唤

精确行：`audit:enigma_malefice:summons:shard`，旧admission `/rows/2952`；当前仍是`candidate_usable=false`、`condition_changed`。当前中英H33的`/result/data/heroes/0/abilities/0/shard_loc`均说明：**有魔晶，憎恶每次眩晕作用于敌方英雄目标时，在其旁边生成虚灵体，且这些虚灵体不会继续分裂**。旧复核`recheck /rows/521`也已要求收窄条件。

本模块产出明确机器条件：`requires_shard=true`、`target_scope=enemy_hero`、`trigger=each_malefice_stun`、`summon=Eidolon`、`can_multiply=false`。这是对现有accept的条件收窄提案，不是新增机制批准。旧行中文引文缺“敌方英雄”，不应继续无条件用于所有目标。最小后续变更是在新候选生产者中消费此条件证据，再重建派生；不能直接改被冻结事实或回填旧receipt。

## E3：关联能力已有候选，补齐来源链并保留触发边界

原清单写“需补关联能力证据”，但这四条已经存在于当前候选且为`two_ai_overlay/candidate_usable=true`；盲审`unclear`与后续补入说明的候选状态应同时保留。不能把“已有候选”说成“用户已批准”，也不能继续说这些行完全没有实现。

| claim／review_id | 固定来源链 | 本轮可证明 | 尚不推断 |
|---|---|---|---|
| c046／`7.42:life_stealer_infest:slow:shard` | H54 `abilities/4/shard_loc`→`abilities/1/desc_loc` | 感染魔晶爆炸向范围内敌人施加撕裂伤口；关联说明含减移速 | 实际施加等级及减速数值 |
| c047／`7.42:life_stealer_infest:lifesteal:shard` | 同上 | 对受影响敌人造成伤害的友军按伤害比例恢复生命 | 不拆成第二次治疗事件，不把所有伤害来源细节补齐 |
| c048／`7.42:life_stealer_infest:healing:shard` | 同上 | 同一回血效果的治疗表述；与吸血标签共享事件 | 不与感染基础自身回复混为同一来源 |
| c073／`7.42:disruptor_kinetic_fence:aoe_damage:shard` | H87 `abilities/3/desc_loc`→`abilities/4/desc_loc` | 触墙明确调用电磁排斥；常规电磁排斥说明存在范围伤害 | **触墙调用是否继承常规技能的范围中心、半径、受害者集合仍未知** |

上表英雄指针均以`/result/data/heroes/0/`开头，并同时核中英文。感染持续3秒另由H54 `/result/data/heroes/0/abilities/4/special_values/10/values_shard=[3]`固定；`dot_duration`按名字唯一定位，不能以数组下标碰巧一致代替身份检查。claim-key指针为`/45,/46,/47,/72`，盲审答案为`/54,/55,/56,/74`。

动能栅栏的英文关联名与当前能力名一致；中文触墙说明称“电磁斥力”，当前能力显示名为“电磁排斥”，因此记录命名差异，以明确英文关系及稳定能力身份追溯。**关联能力有范围伤害，不足以自动证明每一种触发调用也采用同样范围**。该条输出`linked_damage_text_found_trigger_scope_unproven`，旧候选状态作为历史保存；正式AoE消费仍需调用行为补证。

## E2：7条单体指向可补文本证据，2条持续施法保留行为缺口

按词表v15/U51，能选择敌方单位即可构成单体指向；CUSTOM或0不能单独决定接受/拒绝。本轮同时要求注册的完整双语原文、`behavior & 8`以及两语言一致的既有例外目标字段。以下均为**证据支持，尚未改写准入结果**。

| review_id／能力 | 当前H／ability索引 | 原始target_team | 原文可确认的目标范围 |
|---|---:|---:|---|
| `ebbbbe178b11c4ce1cbd`／死亡契约 | H56／2 | 0 | 敌方非英雄单位，或友方骷髅弓手 |
| `0e234c07bae2d264c62c`／吞噬 | H69／0 | 4 | 敌军或中立生物 |
| `8804d4b34b90572aa12b`／感染 | H54／4 | 4 | 基础可选敌方非英雄单位；敌方英雄需A杖，不能把升级条件下放 |
| `0dba6399710fa947dc5d`／变形 | H10／4 | 4 | 明确针对敌方目标 |
| `c4c9a19f3fd010964b01`／幻影突袭 | H44／1 | 4 | 友方或敌方单位 |
| `9651e7885caaf7fd1553`／衰老 | H45／1 | 4 | 友军和敌军分别生效，配合UNIT_TARGET |
| `d5e57f0f93f66dedf40f`／噬魂 | H85／1 | 4 | 治疗友军或伤害敌人 |

每行检查`/result/data/heroes/0/abilities/{索引}/desc_loc`、`behavior`、`target_team`和`notes_loc`，索引仅便于人工定位；实际API要求能力名唯一匹配。**不据此推断林肯、莲花、减益免疫交互或所有子类单位都可被选中**。

- `7056861bb759c22212b6`／米波忽悠：H82 `abilities/1/desc_loc`中英均明确米波持续施法后传送，但当前`channel_times=[0]`，不能用此数组否定文字；仍缺中断施法的执行证据。
- `95b9db1c3a9654525662`／陨星锤：当前itemdata `/meteor_hammer/desc_loc`含CHANNELED，`behavior=176`、`channel_times=[2]`；这些支持存在引导，仍不单凭标志认证U51要求的“施法者自身引导、被打断即停止”。

两行输出`channel_text_found_interruption_unproven`。缺口是明确的行为核验，不应让用户重新批准机械字段。

## API与校验

```python
from dota_items.data.mechanics_engineering_evidence import (
    SOURCE_PATHS,
    build_mechanics_engineering_evidence,
)

# documents：调用方经公共source_io读取并固定字节的25份JSON。
# source_refs：同键path/SHA256，加admission来源；先核验完整字节摘要，发布前再复验。
report = build_mechanics_engineering_evidence(
    admission,
    documents,
    exact_patch="7.42",
    source_refs=source_refs,
)
```

模块只用标准库，不读文件、不联网、不依赖workflow或模型。调用方负责完整原始字节和manifest/receipt校验；纯函数对既有行身份、升级条件、claim映射、源路径版本、原文完整指纹及词表条目另行校验。补丁字母版本不继承。

24项专项覆盖：真实固定来源、条件收窄、关联去重、触发范围未知、原文加否定、缺关联文字、错claim/目标/版本、候选用途拒绝、原始指针回查与输入不变；Ruff通过。命令：`PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_mechanics_engineering_evidence.py`。最终全库检查由主线程串行执行。

本模块独立实测附件：[mechanics-engineering-evidence-v1.json](../reports/patch742-decision-20261127/mechanics-engineering-evidence-v1.json)，14条、149199字节、SHA256 `9eb998532d7861817e21462cac4b6abcd7de0ced649a14630d922b80bfb03a3d`。完整发布产物以主线程本轮receipt为准。

## 输入指纹

H文件根目录为`knowledge/hero-capabilities/snapshots/2026-11-19/sources/`，对应`hero-{H}-{language}.json`。以下均为原文件字节SHA256，实际附件每个证据点还记录完整绝对路径和JSON指针。

| H | English SHA256 | Schinese SHA256 |
|---|---|---|
| 10 | `203a628192c25b7e5e24faf6a2e379a0042e65ea4eb64399b3b95ecfd9b65ab1` | `d80b8cdb2041d94eeb4b7b16da4d671e4e94c0ca4d91c985013725ea20ca6ca0` |
| 33 | `0c6b1af5599a1cfe6cc2b74d01c2a191993ad8d63298247781ce82a4b0df1df2` | `9dc0280452789b8d5cf4f553aecccfcea085f5f59efbd434c7151526ea7fd898` |
| 44 | `37c4554b08b0bba7c78449db60d23022f3994cf82dcbfbaca34c7d65b9e66a39` | `c72a9326ea0ff96ce4712c9f8ef689ae8bfce4620c06e3a7021791805da03ed2` |
| 45 | `2313dd84e9bbb414935c4c19358bfb2fcb19e6e76c42cf9a288a8ba3e80fce71` | `4d314322a170019118c3120ac36c820c5ecc3dc2291b8bbe8718a514774e96ba` |
| 54 | `76a50b3c87f68c067c2a02c6b480c693219edd4ab9e858b43c9a854699b8b516` | `f50a778f925863b82846989d783ba7f5651993a58535ce0c408a0ebc49f5da08` |
| 56 | `ab87f5b918c9d1a47d785bf74bc08a76f2e6d0d175e2766fa8930109dddc171b` | `b4805334f7aa89147e49f0ddff1cd3f1a8095932a185a89d7b7de1dc64ca2322` |
| 69 | `93daed3eaf694647c76fac84ab48c725715c77074772d0cbf3b960f049b622ec` | `b617eedb6242f90b29d9e62bbd06ce21feb41597637dbe2ab0043aed189e3c4f` |
| 82 | `4e8d33650ee265798471dfecb1c9f67214d6ec506af830530a63690731722b30` | `24ee472618edf8d69a6e62df0be7b98f4420e466e68908a9fa8de15d1c75ef48` |
| 85 | `504e2f9194677af29023c412440f653e96cf015fe395f9e75c98488c734dabee` | `b968f7be499480772a9916c46311cf779d5a0569f60479de26909cf92a2c310a` |
| 87 | `acf66c484e2e753a9287c5866ec5f069f5307bcd1b1a83f5813c4dcfec93dbd4` | `0331d4794ec504bd8c2495d1eac7bb3da110484393894e1a3b4383c10a6f602f` |

| 其他来源路径 | SHA256 |
|---|---|
| `knowledge/items/sources/itemdata-english-2026-11-19/items.json` | `c90f4c4e5e2a215391f5e17477466cd2679ad56e468b270bb4af7e778ff54e28` |
| `knowledge/mechanics/vocabulary-v15.json` | `b34cf18a6daba556996a8056a6e2b9121fd5a9b1449c7c79159174c7ba399802` |
| `knowledge/mechanics/reviews/blind-742-001/claim-key.json` | `49e74cb3948c9a50352006e63c80188d21110784321a4c7a50b28ca5e9425bd0` |
| `knowledge/mechanics/reviews/blind-742-001/answers.json` | `2ddc83c3e470b21bde043d98ffdffb6de6709f392361e49424de32bf1493dc0c` |
| `knowledge/mechanics/reviews/recheck-742-001/claude-review.json` | `5a77fd5b590368bc422e8d149fbe6dc73d428d073022fb16acf3c841573b34b1` |
| `reports/patch742-consumers-20261127/assets-final/mechanics-admission.json` | `4684ebc8c93063727ba57e363e721ba3c4c0933a76c4e38594b9c9da77bd78c5` |
