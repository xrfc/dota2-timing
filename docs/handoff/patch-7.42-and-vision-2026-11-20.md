# 交接：7.42知识库更新与视野检验（2026-11-20，Claude→Codex）

2026-11-26 补充：本页为当日历史交接。用户现已授权少量 7.42 demo 工程试采；本地已有 Workshop 7.42 地图候选，但应用及几何/视野回归尚待验证。当前分层状态与本轮授权见[试采审查](../demo-742-pilot-2026-11-26.md)，下文的“暂缓”不覆盖本轮已授权的少量采集，也不代表地图已验收。

用户要求把下面两件事交给Codex继续开发。先读本页，再读[当前状态](../current-status.md)、[开发计划](../development-plan-2026-10-30.md)§0和§7、[7.42影响清单](../patch-7.42-impact.md)。

## 1. 分支（都只在本地，未推送，未开PR）

```
origin/main
  └─ claude/b0-review-2026-11-10   路线B的B0、死亡风险、地图知识、视野工具（7个提交，已推送到远端同名分支，未并入main）
       ├─ claude/patch-7.42-2026-11-19     7.42知识库更新（本页的主要内容）
       └─ claude/vision-sources-2026-11-20 视野模拟检验（崖边、树半径）
```

- 两条新分支都从`claude/b0-review-2026-11-10`开出，因为地图工具和7.42预案只在那条分支上；PR应在b0分支合并后再开，或先开到b0分支。按U135：推送功能分支、开PR不需要另问；**合并PR、推送main、删除分支要用户同意**。流程见[功能分支与PR](ai-temp-branch-contract.md)和`AGENTS.md`。
- 单worktree、共享index：切分支前先提交，不要同时让两个AI操作git。

## 2. 7.42知识库更新（`claude/patch-7.42-2026-11-19`）

**已完成**

- 7.42快照、官方补丁说明、差异、影响范围：`knowledge/mechanics/reviews/patch-update-2026-11-19/`。
- 共享构建器（U177）：`data.mechanics_facts_overlay`、`scripts/build_mechanics_facts_overlay.py`，能逐字节重建v26。v27起所有事实版本都用它，不再复制`mechanics_facts_vN.py`。
- 逐行复核（U179、U180）：Codex `gpt-6.2-astra`＋Claude，`reviews/recheck-742-001/`（逐行去向在`claude-review.json`的`lane`）；新技能抽取`reviews/new-abilities-742-001/`；双盲复核（U185）`reviews/blind-742-001/`。
- 用户已定：U177–U188，见[决策](../decisions/2026-11-19-patch-7.42.md)。重要的通用规则：
  - **证据优先级**（U182）：官方补丁说明＞游戏脚本＞数据接口的标记和数值＞数据接口的说明文字（接口里常留着没更新的A杖/魔晶说明）。
  - **命石一律不用**（U184）：数据接口里的`facets_loc`是废弃内容。
  - 授予来源（`ability_is_granted_by_scepter/shard`）要单独比对，差异脚本以前没比（米波·掘地就漏了）。

**还在等用户**（见[影响清单](../patch-7.42-impact.md)A8及§5下方）

- 用户进游戏核对：凯·天隼冲击能否越过地形；巨魔战将·战斗专注“攻击时无法被减速”算不算减速抗性（U183暂按删）。
- 米波两只分摊伤害算不算“护盾/减伤”、米波·投掷300视野记不记：已向用户解释，待回复。
- 影响清单A1（全局机制7条）、A2、A4、A6、A7的“按建议”尚未逐块确认；用户已对其中多处给了具体裁定（U181–U188），其余未回复的块不要当成已同意。

**下一步（用户确认后）**

1. 写`knowledge/mechanics/reviews/v27-inputs-001.json`（`mechanics-overlay-inputs/1`）：把`claude-review.json`里`lane=change_two_ai`的行和用户裁定逐条写成`decision_change`/`retire`/`add_row`/`note`；删除的技能（`packet-summary.json`的`removed`）写`retire`。需要“改条件”（米波·掘地魔晶→A杖）这一种操作，共享构建器还没有，要新增`condition_change`并补测试。
2. 规则或词表要改的（A1：R06、R09、R18、`damage_block`定义）先出规则v14、词表v16。
3. **字段重建**：英雄注册表`knowledge/hero-capabilities/hero-registry.json`是10-09数据，要用7.42快照重建（`knowledge/hero-capabilities/build_profiles.py`），再重建由字段读出的行和`field_observations`（驱散、伤害类型、免疫、魔耗、IsBreakable）。旧的生成逻辑在v1–v4的抽取模块里，入口参考`docs/mechanics-facts.md`。
4. 写构建spec（`mechanics-facts-build/1`，游戏脚本指向`knowledge/game-files/snapshots/2026-11-19*`），出事实v27，再出派生层v18（参考`scripts/build_mechanics_derived_v16.py`等），改`scripts/build_mechanics_current.py`切到7.42并先`verified=false`，跑`scripts/check_patch_knowledge.py check`逐条核对后再设`true`。
5. 地图：暂缓（U178）。用户可能用Workshop Tools自己导出7.42地图数据（`docs/map-workshop-export.md`）；拿到后和7.41数据做新旧对照。`knowledge/map/objectives-v1.json`里痛苦魔方和肉山复活两条不适用于7.42，影响清单A7建议出v2。

## 3. 视野检验（`claude/vision-sources-2026-11-20`）

- 崖边检验（U186）：`scripts/vision_cliff_check.py`，结论在`docs/map-knowledge-design.md`§10.5——崖边细化高度不值得做（最多约0.5个百分点）；被树挡掉的占漏判24%。
- 树按真实半径遮挡：`scripts/vision_tree_check.py`，结果`reports/vision-tree-check-2026-11-20/`（本地，未跟踪），结论写在视野分支的`docs/map-knowledge-design.md`§10.6。
- **被砍的树**：用户同意改解析器，但2026-11-20查过，已检查的一场7.41f录像里**没有直接的砍树记录**：战斗日志没有`TREE_CUT`（类型35）条目，没有树实体，字符串表里也没有树的状态。可能的间接来源是树倒下的特效（`UM_ParticleManager`）或音效（`GE_SosStartSoundEvent`），要先研究怎么从哈希找到树的特效名，再决定做不做。详见视野分支的§10.6。

## 4. 容易踩的坑

- **解析demo必须用兼容版解析库**：`PYTHONPATH=data/replay-pilot-2026-10-22/compat-v1:src`。直接用`.venv`里的原版`gem-dota 0.10.0`会在开局几千tick报`BufferReadError`，不是demo坏了（2026-11-20踩过）。
- 全量检查：`NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost .venv/bin/python scripts/check.py --scope all`；有代理时两个本地HTTP测试会失败（计划§8已登记）。只在检查通过后提交；新文档要登记到`docs/README.md`。
- 新脚本、新模块要在`src/dota_items/architecture.py`登记，并更新`docs/architecture.md`的统计表（`PYTHONPATH=src .venv/bin/python scripts/architecture_stats.py`）。
- Codex复核脚本用`~/.local/bin/codex-prefer`，模型`gpt-6.2-astra`，推理强度high（U180）；只读、空目录、不存会话。
- 账号ID只在未跟踪的`configs/user.local.json`。

2026-11-20 更新：候选 v27 的已完成项与剩余裁定见[执行顺序](../patch-7.42-plan.md)。旧差异计数由 revision-2 取代。
