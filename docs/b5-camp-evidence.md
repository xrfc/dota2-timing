# B5：营地事前可见证据

2026-11-26，接续已完成的[分类实收提取与对账 PR #47](https://github.com/xrfc/dota2-timing/pull/47)。[用户要求及边界](decisions/2026-11-26-camp-evidence.md)。本主题补充决策时可见的单位事实；目前处于实现与核验阶段，尚未完成真实全量提取。

## 固定范围

继续使用原 1,341 场开发集中的 1,169 场 7.41f、15,005 个兵线机会。动作仍为收线 6,235、朝野区移动 1,176、未知 7,594；原 t..t+6 标签不变，不按后续死亡或收益剔除机会。原 337 场已正式评分，不能作为新的独立验收；此批不读取它们。

输入是 `reports/b5-farm-income-20261125/plan.json`，SHA256 `8ad71d1e60b251360b9e96a4afc0c4a599443ddaa1c88abdb012b060cba7f3ad`；按 match/hero/t/fold/action 投影的人口摘要为 `4909b7905e5d5568831f96ca5cff385302fd28cd9a9228fde2c31c9746a80d42`。它是前一主题保存的不可变输入，本实现不导入尚未合并的金币脚本或模块。

## 来源与公开证据的边界

| 层 | 职责 | 不能据此声称 |
|---|---|---|
| `sources.gem_camp_evidence` | 在请求秒首个 tick-start、实体更新前冻结 active 中立类单位及双方可见性，保存原始审计证据 | 全知来源中的隐藏单位是玩家已知信息 |
| `data.camp_evidence` | 根据 PlayerResource 确认的观察阵营，白名单投影明确 visible 的单位事实 | 可见单位为零就代表空营，active 就代表存活 |
| `scripts/collect_b5_camp_evidence.py` | 固定计划、来源指纹、逐场原子发布、严格恢复与覆盖报告 | 已具备路线可达、完整营地存量或清营耗时标签 |

采样固定请求秒的首个回调，重复 tick 或同秒后续回调不能覆盖。首回调没有观察者身份就保留缺失，不能等后续身份出现再补回当前帧。完整解析后核对时间基准、比赛身份和来源版本，拒绝时钟漂移。

具体 NPC 名来自 `m_iUnitNameStringTableIndex` 对应的 **UnitNames**。EntityNames 可能只给通用 `npc_dota_creep_neutral`，两种名字分别保存，不能混查同一个索引。观察英雄归属来自 PlayerResource 的选定英雄 handle（index/serial）、阵营和槽位，不能依赖可能被重建的控制器缓存。

实际视野读取 `CDOTADataRadiant/Dire.m_bNPCVisibleState`，每个 word 对应 64 个实体 index；缺 word 是 unknown，不是 hidden，更不是空营。旧包末视野事件可能包含当前 tick 后续更新，因此不能直接拼接到更新前状态。`m_nFoWTeam` 不能替代实际可见位图。

首版范围是 active `CDOTA_BaseNPC_Creep_Neutral` 类，保留血量、最大血量、生命状态、位置、阵营和 index/serial；缺字段为 null 并注明原因。真实普通野怪和巨魔骷髅均可属于该类，被玩家控制也不据此删除。陈的其他单位类不在本版覆盖内。owner handle、控制掩码、出生/生成器等信息即使可从全知来源读出，也不能自动升级为当时已知事实。

公开层只包含己方明确可见的单位，不暴露隐藏/unknown 单位的数量、属性、位置或原始控制字段，也不附加未来死亡与动作标签。`stock_complete=false`、`empty_confirmed=null`、`camp_id=null` 保留限制；不按最近静态营地强行认定归属。审计原文和校验收据独立保存，不能直接作为模型输入。

## 自校验与后续出口

来源专项 48 项通过。首场固定开发录像 9080976703 的冻结源码小跑已完成：15 个机会均 observed，10 帧有可见单位，89 次可见单位观察，公开允许字段无缺失，耗时 34.7 秒。证据在 `reports/b5-camp-evidence-20261126/probe-frozen-first/`，199 个源码文件冻结在 `probe-producer-1/`。此前未冻结的小跑被前后源码漂移检查拒绝，未作为验收或复制进正式批次；原日志保留。

这是来源字段和时钟的小跑，不代表全集，也不是独立模型验收。另行真实重放及批处理验证仍在进行。

专项要覆盖首回调后状态变化、重复 tick、缺观察者、可见位图 64 位边界、UnitNames、实体 index 重用、隐藏属性及未来数据非干扰、严格恢复和来源漂移。真实验证先用固定开发计划的小批机会，再扩至全集；既有控制单位案例用于检查解析语义，不构成新的训练样本选择。

最终验收串行运行 `scripts/check.py --scope all`，比较包含未跟踪源码的前后文件指纹。完整提取完成后还需核对固定人口、每帧投影、字段覆盖与缺失原因；不能把“脚本成功退出”当成游戏语义全部核实。路线可通行、营地完整存量和清营能力仍各自待证，训练另按研究契约执行。

## API、批处理与恢复

`capture_camp_evidence(raw_demo_path, cases)` 接受解压 `.dem` 和 `(hero, t)` 对，返回 `gem-camp-evidence/1`；`project_camp_evidence(captured)` 返回 `camp-evidence/1`。后者为纯投影，不加载 Gem。来源延迟加载指定 compat-v1，验证 manifest 和全部 190 个 Python 文件；缺包、源码增删或哈希不符均拒绝。

CLI 的 `--compat` 指向 **gem 包目录**，不是父目录。`--limit 4` 只处理固定计划的前四场，已完成场也计入四场并重新校验；不会截短计划。去掉 limit 即继续全集。`--match` 可重复指定，仅允许固定计划内比赛作回归。最多四个工作进程，复用现有虚拟环境。

```bash
PYTHONPATH=src .venv/bin/python scripts/collect_b5_camp_evidence.py run \
  --plan reports/b5-farm-income-20261125/plan.json \
  --data data/demos-2026-11 \
  --compat data/replay-pilot-2026-10-22/compat-v1/gem \
  --out reports/b5-camp-evidence-20261126/batch-v1 --workers 4 --limit 4

PYTHONPATH=src .venv/bin/python scripts/collect_b5_camp_evidence.py report \
  --plan reports/b5-farm-income-20261125/plan.json \
  --data data/demos-2026-11 \
  --out reports/b5-camp-evidence-20261126/batch-v1
```

长任务从明确冻结的生产者目录运行，并把该目录的 `src` 放在 PYTHONPATH 中；CLI 验证实际导入位置属于生产者。当前工作区变更后不能冒用旧目录续跑；须回到完全相同的冻结实现，或为新实现另建批次，不忽略哈希失配。

每场原子发布 `matches/<match>/{raw.json,evidence.json,receipt.json}`。raw 是 `b5-camp-raw/1` 的全知审计包装；evidence 是白名单公开证据；receipt 绑定固定机会、录像/元数据/原收据、生产者、compat 及两个载荷的摘要。根 manifest 绑定整个批次，单目录写锁防止并发写；未发布的暂存目录不计完成。恢复时重读来源，校验载荷并重新投影比较，不能只检查文件存在或 checksum。

`report` 固定开始时已发布的名单，后来发布的比赛留给下一份报告。完整与待补按原计划计算，字段覆盖仅统计己方可见单位，不报告隐藏单位数量。`complete=true` 只说明固定人口已有结果，须结合缺失状态和独立审计理解；未取得证据的帧照样保留，不自动补零。
