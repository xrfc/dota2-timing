# 三场突跳与技能、物品、复活事件核对（2026-10-23）

接续[直接实体取证](replay-identity-2026-10-22.md)及[语义审计](replay-semantics-2026-10-22.md)。本轮按用户指令核对既有1,170次突跳，仅消费原三场冻结日志；无下载、扩量、重解析、训练、标签/划分修改或客户端操作。

## 结论

**全部1,170次突跳已有逐条事件关联记录；这不等于全部原因已确认。**

|证据分组（互斥，按表中优先级）|9056009571|9056009136|9056009130|合计|
|---|---:|---:|---:|---:|
|区间内恢复存活|93|83|62|238|
|非存活端点、无恢复转换|0|1|0|1|
|区间内有位移候选使用/传送效果结束|368|356|138|862|
|相关事件恰在前采样同tick|29|25|7|61|
|仅前邻窗口有位移候选使用|6|0|0|6|
|未命中上述使用/传送清单|0|0|2|2|
|合计|496|465|209|1,170|

最后2次进一步逐条查看，均有受害者身上的`modifier_pudge_meat_hook`添加和移除记录，详见下文；不为得到“零未解释”而改写成确定肉钩标签。死亡实体的1次移动仍无机制解释。其他各组也只代表不同强度的关联，不是因果置信度分数。

## 方法、口径及时间边界

- 保持原阈值≥1,200原生单位及原1,170条清单，保留原始坐标、tick、slot、来源引用；不删异常、不补坐标、不把距离除以时间直接作正常速度。
- 严格核心区间为`(previous_tick, current_tick]`。另保留两侧60 tick上下文；传送卷轴、Tinker传送、双生门使用额外向前取300 tick。无暂停时约2秒和10秒；它们是助手选择的探索性审计窗口，不是机制最大时长或用户研究决定。
- 前采样同tick事件单独分组，因为坐标采样与战斗事件在同tick内先后顺序未认证。61次不能简单说“发生在位移前”或“漏了一秒”。future_context只作离线事后检查，不可作为预测时特征。
- 通过玩家ID→英雄名连接；英雄名仅移除下划线作兼容别名，拒绝别名碰撞。攻击方/目标方须明确`is_hero=True`且`is_illusion=False`。缺失标志不当False，幻象事件不借给主英雄。日志没有用于这种连接的实体index/serial，仍有同解析器名字连接限制。
- 位移技能/物品为显式探索清单，完整清单固化在结果configuration，**不是同build技能机制百科，也不是穷尽分类器**。Glimpse/Roshan投掷取目标角色；Blink等自身位移取施法者；其他候选保留角色以供复核。
- `modifier_teleporting`和`modifier_twin_gate_warp_channel`移除只说明效果结束，可能成功、取消或中断；不认证落点或引导成功。300 tick内多次使用全部保留，不擅自挑一条配对。
- 全部附近ABILITY、ITEM、MODIFIER_ADD/REMOVE、DEATH、BUYBACK关联事件保留原字段及`combat_log[index]`。不只输出命中清单的事件。原日志中的UNKNOWN事件仍在冻结raw中，本轮不解码；缺少已命名事件不等于游戏中没有事件。
- 31次突跳有多个核心候选事件（2、27、2，按9130、9136、9571顺序），没有强选唯一原因。核心候选事件跨突跳复用为0；近邻上下文允许复用，不能把上下文链接数当独立事件数。

### 探索过程与版本

初版v1得到848条核心关联、83条未命中。检查未命中案例后，v2补充双生门效果结束、Roshan投掷候选，分开前采样同tick与前邻上下文，并收紧Glimpse/自身Blink角色。**这是看过试点数据后的探索性规则完善，不是预注册或独立验证。** 两版目录均保留，v2为当前交付，v1不再作为最终计数。

## 对应到了哪些技能、物品

v2核心候选事件引用计数（不是互斥突跳数，可与复活组重叠）：

|事件|引用数|解释边界|
|---|---:|---|
|普通跳刀使用 `item_blink`|304|证明记录到使用；不证明全部位移仅由跳刀造成|
|痛苦女王Blink|207|同上；不是距离/落点机制验证|
|传送效果结束 `modifier_teleporting`|341|未认证成功/取消，也未唯一绑定起始施法|
|双生门引导效果结束|16|保留引导与结束记录；不强称成功|
|幻影刺客Phantom Strike|11|保留施法者/目标角色|
|Tinker Warp Grenade|5|探索性位移候选，补丁机制未独立认证|
|Overwhelming Blink|5|装备使用记录，非购买或持有推断|
|剑圣Omni Slash|3|过程可能跨多个tick，非普通步行|
|复仇之魂Nether Swap / Magnus Skewer|各2|多角色和效果链需继续核验|
|Earthshaker Enchant Totem / Force Staff / Roshan投掷|各1|不能仅凭技能名称判断具体升级、受影响对象和完整轨迹|

购买记录、物品栏持有、最终装备均未用作“已经施放”的替代证据。

## 复活核对：246次恢复状态，不是238次突跳

检查全量246次`1/2→0`状态转换，而不只看达到位移阈值的238次；这避免漏掉原地重生。

|恢复关联|全部恢复转换|涉及本轮突跳|
|---|---:|---:|
|附近BUYBACK记录|9|8|
|此前死亡记录`will_reincarnate=True`|7|1|
|机制仍未细分|230|229|
|合计|246|238|

- BUYBACK的`value`为0–9玩家ID，按冻结Gem `results/assembly.py`的既有解释连接，并非用空英雄名或Dire slot 128–132连接。
- 先找该恢复之前最近一次采样的存活→死亡转换，再在其±60 tick范围找同英雄真实DEATH；不拿很早以前的任意死亡做佐证。买活窗口为恢复前后采样边界外扩60 tick，仍属于相邻证据。
- 本轮恢复记录的死亡候选及买活候选均未出现多条歧义，但不因此宣称独立真值。
- 7个重生标志关联中：9130场3次Skeleton King；9136场1次Phantom Assassin；9571场Juggernaut、Beastmaster、Luna各1次。**标志本身不区分Aegis、英雄技能及其他来源。** 已有Aegis pickup也不能单独证明最终消耗原因；本轮不把它们都命名为不朽盾复活。
- 原始战斗日志没有单独的RESPAWN类型；230次不能仅由“无买活/无重生标志”推断成普通计时复活。生命状态为主要恢复证据，独立机制确认仍不足。

## 重点案例与剩余缺口

以下`jumps[i]`均指对应比赛v2结果，其`jump_ref`同时指向上轮语义清单。

1. **肉钩效果（9130场）**：slot 1，1112→1113秒，1,214.94单位，`jumps[22]`。肉钩效果在tick 39246添加、39268移除，引用`combat_log[33374]`、`[33392]`；坐标tick为39246→39276。
2. **肉钩效果（9130场）**：slot 128，856→857秒，1,217.86单位，`jumps[125]`。肉钩效果tick 31566添加、31588移除，引用`combat_log[22695]`、`[22732]`；坐标tick为31566→31596。两例均是目标方效果证据，不是“旁边有人使用肉钩”猜测；仍未认证完整拉拽过程/落点。
3. **仅前邻候选（9571场）**：`jumps[315]`、`[334]`、`[459]`、`[485]`、`[487]`附近有Glimpse；后两类可能同时有Blink/Force Staff。`jumps[318]`在Roshan投掷后的下个采样区间仍有位移。保留延迟/连续运动可能，不将全部位移归给最近事件。对应原始引用在每条events中。
4. **死亡实体移动（9136场）**：slot 3，2469→2470秒，1,277.49单位，`jumps[102]`，tick 81354→81384，两端状态均2；原坐标引用`players[3].position_log[2558/2559]`。本轮角色限定窗口内没有相关事件。**仍未解释，不把它判为幻象、传送、复活或解析错误。**

下一步若继续核验，应针对同tick采样/战斗事件顺序、传送开始—中断/完成—落点链，以及死亡实体移动的底层实体属性变化取证；无需先扩量。不得仅扩大窗口直到每个案例都能找到一个技能。

## 代码、API、产物与复现

新增数据侧文件，不修改已有未提交文件、共享入口、共享接口、环境和Git索引：

- `src/dota_items/data/replay_jump_events.py`：纯函数`inspect_jumps(raw, audit, tolerance=60, channel_lookback=300)`；不修改输入，不调用训练。
- `scripts/audit_replay_jump_events.py`：只读冻结输入、核对哈希和比赛身份、拒绝覆盖输出。
- `tests/test_replay_jump_events.py`：17项专项用例。
- 本文为独立数据侧入口/API/命令/验收说明；未改需双方协调的共享文档索引。

当前产物：[v2目录](../data/replay-jump-events-2026-10-23-v2/)，三份逐条JSON及[summary.json](../data/replay-jump-events-2026-10-23-v2/summary.json)。summary绑定消费输入、实现及每场输出哈希。读取使用公共`data.source_io`，显式512MiB上限；semantic receipt→audit、audit→manifest、manifest/audit→raw核对，并在输出前复查输入和代码未漂移。该校验不是完整bundle验收，不重跑旧生产者。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/audit_replay_jump_events.py \
  --semantics data/replay-semantics-2026-10-22-v1 \
  --output data/replay-jump-events-new

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider \
  tests/test_replay_jump_events.py tests/test_replay_identity.py \
  tests/test_replay_semantics.py tests/test_replay_compat.py \
  tests/test_replay_ingestion.py tests/test_observer_context.py -q
```

实测**70项专项测试通过**（本轮17项），新增三个Python文件ruff检查/格式检查通过。覆盖前后边界、未来不算核心、幻象/缺失标志、重复事件及输入不可变、施法者与目标角色、买活ID、死亡实体、重生旧死亡拒绝、候选复用、传送结束不认证成功、错比赛、输入哈希错误、旧输出保护。开发首次lint有长行/导入问题，格式化后检查通过。

未组织双方暂停写入的最终全库验收，70项不代表全库通过。没有提交、推送、依赖安装、训练或改变数据用途。所有结果`training_admission=False`；同解析器跨通道证据仍不等于独立游戏语义认证。
