# 树身份与临时视野来源：长度写入补证（2026-11-28）

按[本轮授权](decisions/2026-11-27-viewer-wire.md)，复用已有八场精确7.42/build6993工程录像。上一轮的86个栖树局部关联仍成立；本轮补齐临时viewer的协议逻辑长度和有效标志消费，并为完整树身份建立严格入口。**完整树映射、游戏意义上的有效视距、技能来源归因和完整FOW仍未认证。** 正式知识保持7.41f，行动复盘及训练门禁不变。

## 已完成与未完成

| 项目 | 当前证据 | 边界 |
|---|---|---|
| 容器长度 | 八场594次长度写入，在固定Gem把长度写入FieldState前截取 | 是解码后的协议值，不声称直接保存了每个字段的原始bit流 |
| 当前协议成员 | 270234次字段写入、80个容器实体身份；按长度、valid、队伍与实体进入/离开状态重放 | slot会复用，不是80个技能来源；有效标志也不证明视距或具体法术 |
| 有效标志变化 | 51799次true→false、51581次false→true | 是槽位标志变化，不是等量技能施放或独立来源生命周期 |
| 独立核验 | 109448个包/实体状态，2677603次成员出现；原探针19529快照的2844048字段值一致 | 统计分母为重复观测，不是独立游戏样本 |
| 完整树身份入口 | 解析完成标记、精确补丁/声明build、原生ID双向实体检查及XYZ一一对应校验 | 本地2394棵树尚无原生ID表；86局部关联不能推广其余2308棵 |
| 维护耦合 | 解析环境准备提到共享data接口，B线experiments负责运行和发布，CLI只收参数 | 旧CLI仍保留供冻结产物复现；没有批量搬迁或忽略旧哈希 |

八场实际长度最大值为27–63；没有观察到缩短正例。因此缩短/清空/再扩展由合成回归验证，不冒充实战证据。仅依据逻辑长度还不够，范围内的槽也可能`m_bValid=false`或字段未完整观察。对这种槽保留原值和未知，不把容量、残存字段或缺失值变成有效视野。

## 代码接口与迁移

- `data.map_capture_environment.prepare_capture_environment(spec_path, pins, match_allowed=...)`：准备固定来源、解析器与依赖；调用方必须注入比赛用途检查。与旧`capture_map_runtime.prepare()`的准备结果和输入清单做等价回归。
- `sources.viewer_wire_capture`：只接录像和明确match/build；临时包裹固定解析器的`read_fields`和`FieldState._set_compact`，采集长度及成员写入；无论成功或异常都恢复hook，不修改解析器源码和解码结果。记录完成包、tick、最终暂停感知时钟，以及仅team/version变化的事件。
- `data.viewer_wire_io`：旧锚点登记、真实身份与留出检查先于正文；严格核对新生产者闭包和迁移声明、依赖、大小与摘要。旧回执不能冒充新捕获。
- `data.viewer_membership`：纯重放，容器长度与存储容量分离。长度缩短移除越界成员，再扩展不复活已删槽的旧字段；包内写入完成后才产生快照。无序、缺写入、无创建基线、缺失时钟和未解释的容器中间层写入拒绝消费。
- `experiments.awareness.viewer_capture`：私有解析器副本、捕获、前后来源复验和原子发布。`capture_viewer_wire.py`仅为CLI；不再动态导入另一个CLI。
- `data.tree_identity`：纯解析/对账，不根据数组排序、邻近坐标或缺省值补原生ID。

迁移登记`pinned-capture-preparation/1`位于`data/viewer_wire_io.py`，只接受旧`capture_map_runtime.py`摘要`b5b16f78d4c4330e9909c98a7ab5bc31e1fb2fde4cdb3ffc3a27e1fde032504b`。模式为**new-capture-only**：原生产者不改，新捕获固定新接口摘要，旧产物不重贴标签。这不是允许任意旧哈希过关的通用迁移。

## 运行与存储

采集spec为`viewer-wire-spec/1`，其余字段与上一轮登记锚点相同：`exact_patch`和`anchor.capture/receipt`（绝对路径与SHA256）。仅接受已登记八场来源，必须使用新进程、新输出目录：

```bash
PYTHONPATH=src .venv/bin/python scripts/capture_viewer_wire.py \
  --spec reports/patch742-viewer-wire-20261127/spec.json \
  --output reports/patch742-viewer-wire-20261127/capture-new

PYTHONPATH=src .venv/bin/python scripts/build_viewer_membership.py \
  --capture /absolute/capture.json --capture-sha256 <sha256> \
  --receipt /absolute/receipt.json --receipt-sha256 <sha256> \
  --output /absolute/new-membership-directory
```

八场最终捕获为`capture-<match_id>-r2/`、派生为`members-<match_id>-r2/`。捕获合计50884281字节；派生63023597字节。派生以不可变`member_states`表存槽位原值和资格，帧内`member_state_ids`按逻辑成员顺序引用；相同内容完全展开参照607632263字节，去重节省89.63%。参照是同信息编码计量，不是压缩包或另一个可直接消费格式。不要在下游持久化重复展开快照。

## 完整树ID的缺失来源与可执行准备

现有Workshop `mapdata.json`的2394棵树只含坐标与team，没有原生ID或实体编号。本地新增覆盖账本逐棵保留`native_tree_id=null`；86处另记局部栖树关联，完整原生映射状态为false。新增字符串表清单只是覆盖调查，没有把资源名称或数组序号解释成空间身份。

已准备[只读导出辅助脚本](../tools/workshop/export_tree_identity.lua)，在已有精确7.42的Workshop原地图、清树前手动运行；不启动客户端，不创建/摧毁/复活树。辅助脚本枚举`ent_dota_tree`，读取实体坐标和`GetTreeIdForEntityIndex`，再用`GetEntityIndexForTreeId`做反向检查，最后打印带BEGIN/END和总数的记录流。build是调用者依据控制台version输出填写的声明，不冒充脚本测得的版本。

在现有addon的VScript环境中加载该文件后，调用返回函数，例如`export_tree_identity("7.42", 6993)`；6993仅为例子，须填写实际client build并另存version输出。读取端`parse_tree_export(text, exact_patch="7.42", expected_build=实际build)`再交给`reconcile_tree_identity(map_trees, rows)`，要求所有树的XYZ精确覆盖且ID、实体、坐标均唯一。跨build仍需额外录像对账，字母补丁不继承；完整坐标覆盖也不证明观察者树位平面语义。

辅助脚本尚未在游戏内执行，本环境也没有Lua运行时；已测试Python解析与完整性门禁，不能把合成正例当实际原生导出。用户是否仍持有精确7.42 Tools环境已询问，在来源补齐之前保留完整映射缺口。API依据为[Valve原始更新说明](https://www.dota2.com/reborn/updates/?l=english)及[当前API声明](https://docs.moddota.com/lua_server/)；它们支持转换接口的用途，不证明当前本地地图ID的顺序。

## 自检与后续

首版复核发现只有team/version变化时可能不输出，已保留r1为中间记录，补回归后八场重跑r2。发布时复验全部来源和解析器副本，结果见[可分发验收摘要](acceptance/viewer-wire-20261127.json)；独立重放及旧字段对账见本地`reports/patch742-viewer-wire-20261127/independent-audit.json`。41项新增测试及旧探针/架构专项共165项通过；最终全库结果和文件指纹另存同目录`full-check.json`。

接下来优先接收/核验原生树ID表，并继续临时viewer格网单位、radius单位、type含义和具体来源归因；已有协议成员状态不重复列作尚未提取。当前29种候选type原值未解释，不能按经验编号配技能。有效英雄视距、完整FOW、昼夜HeroID_t显式解码迁移、动态阶段/目标计时和剩余机制条件继续按计划推进；不以新工程通过数代替训练和行动效果验收。
