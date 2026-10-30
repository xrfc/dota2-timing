# 蓝量解码修复与机器学习特征准备（2026-10-28）

本阶段落实用户“自己开发自己检测、按照目标实现”的要求：先修复已确认的数据质量缺陷，为后续机器学习提供可追溯输入；不是继续靠人工规则替代学习模型。学习配套见[数据质量与X/y练习](data-quality-ml-lab-2026-10-28.md)。

## 当前设置与边界

- 复用原两场录像：9056008987，主宰player_id=4、决策tick=41048；9056008877，player_id=0、tick=38522。两例均为18:00，不能当未见测试。
- 保持原目标、标签、划分、装备候选与训练数据不变；不运行真实训练，不新增比赛/网络采集，不改共享依赖，不提交推送。
- 新模块与脚本为数据侧专属；旧解析器、安装环境、raw、计划、状态卡和当前8769页面均不覆盖。全局导航/共享接口未修改，不假定其他开发者已停写。
- 固定诊断窗口为决策前1800原生tick至后30tick，每30tick取样，共62条/场。该窗口是本轮实现选择，用于观察资源变化，不是新的研究范围或标签协议；本批对应约一分钟历史和一秒后续，不能推广为通用tick换算。
- 后一条仅验证；`current-resource.json`只含决策当时资源，不含未来变化量、全文件哈希或回放结束信息。

## 修复方式与API

旧Gem在缓存ServerInfo时没有先更新`game_build`，导致schema按0选择了早期蓝量范围8192；实际版本6965的原生范围是65536。

`sources.decision_mana.build_first_parser(base)`返回隔离子类：

1. 按冻结Gem相同的`/dota_v(数字)/`约定读取ServerInfo，先设置版本，再由原逻辑缓存/处理消息。
2. 构建schema前要求已存在唯一的有效ServerInfo、版本为6965、且尚未初始化实体管理器。
3. 将真实版本传入原schema解析逻辑，因此解码器从原位流按正确范围重新生成读数。
4. 未知/歧义/其他版本、schema先于ServerInfo、重复schema均拒绝。不声称支持旧版本或任意顺序的录像。

不会修改任何Gem全局函数、site-packages或compat-v1文件。新生产者身份为`decision-build-first/1`，是旧冻结解析器加新适配模块的组合，不冒充旧生产者精确重现。

`data.decision_mana.compare_captures(old,new)`：

- 比较比赛、build、解压demo哈希、决策tick；旧三条必须是前一秒/当前/后一秒。
- 旧三条的完整实际观测在移除蓝量与schema元数据后必须相等，包括英雄/物品/技能身份、CD、槽位、血量及游戏时间。
- 蓝量必须为有限非负值，元数据必须分别匹配旧8192、新65536的20bit、无特殊flag编码。
- 新窗口必须排序、无重复、目标实体index/serial不变，资源值合理、时钟不倒退。
- 对已核验的这类量化器检查新旧8倍关系，**这是重解析结果的诊断，不是生成新值的方法**。不能据此批量乘8修正任意字段。
- schema的`parent_name`等元数据会随正确版本的初始化变化，不将全部schema字节宣称为不变；比较对象是实际观测值，完整元数据仍在两份capture保留。

`current_resource(comparison)`只投影唯一的当前行；即使诊断包包含未来行，未来变化也不进入当前资源对象。该投影不是正式模型特征构建器。

## 冻结与命令

本轮产物：`reports/decision-mana-repair-2026-10-28-v1/`。`plan.json`绑定旧计划、采集收据、录像、旧capture与完成收据、完整compat源码清单及新实现指纹。执行时重新构造完整固定计划并比较，不能通过删除来源条目绕过校验。

```bash
# 新目录；已有计划不覆盖
PYTHONPATH=src .venv/bin/python scripts/repair_decision_mana.py \
  --freeze-plan reports/decision-mana-repair-new/plan.json

# 每场独立进程，串行即可；不改旧缓存
PYTHONPATH=src .venv/bin/python scripts/repair_decision_mana.py \
  --plan reports/decision-mana-repair-new/plan.json --match 9056008987 \
  --output reports/decision-mana-repair-new/9056008987
PYTHONPATH=src .venv/bin/python scripts/repair_decision_mana.py \
  --plan reports/decision-mana-repair-new/plan.json --match 9056008877 \
  --output reports/decision-mana-repair-new/9056008877

# 合成专项，不读取真实录像
PYTHONPATH=src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_decision_mana.py
```

Windows PowerShell先`$env:PYTHONPATH="src"`，解释器用`.\.venv\Scripts\python.exe`；多行命令可合并成一行。复用原环境，不需要安装新依赖。

每场目录包含`started.json`、`capture.json`、`comparison.json`、`current-resource.json`、`complete.json`；失败尝试保留但没有成功收据。只有完整解析、匹配身份/指定采样、全部比较和前后来源哈希核验通过，才发布`complete.json`。输出目录存在则拒绝。

## 当前证据能说明什么

- 可以确认：版本初始化顺序修复、原位流按正确范围重新解码；三条旧采样的非蓝量实际观测兼容；原文件未替换。
- 不能确认：独立客户端蓝量真值、每次技能实际消耗、具体回蓝来源、完整可施放条件。两个解析结果仍共享来源；合理数值及增长趋势不是独立认证。
- `independent_gameplay_units_certified=false`、`can_cast=null`、`training_allowed=false`保留。零CD不代表能放技能，蓝量正确也不能代替控制/目标/施法距离/TP落点条件。
- 当前8769仍展示旧案例包的“未认证”状态，本轮不热替换页面或更改旧manifest。后续采用新值需显式绑定新产物和来源，不能忽略旧指纹失配。

## 检查与下一步

本轮新增专项覆盖真实Gem protobuf/schema/位流解码、初始化顺序、未知/旧/歧义版本拒绝、重复/缺失/乱序样本、身份和CD/装备漂移、非法蓝量、覆盖拒绝，以及未来扰动不改变当前投影的正反控制。

专项、数据scope与真实两场结果分别记录在本轮报告目录的验收收据；数据scope不是已协调的全仓最终验收，也不是游戏质量认证。最终全量验收按[并行协议](handoff/parallel-development.md)串行执行并核对源码指纹；2026-10-28用户已取消其他开发者停写确认门禁。

下一项语义核验应固定过去窗口中的资源事件与更密集采样，以技能耗蓝/回蓝的独立通道核对，而不是扩大采集或先训练复杂模型。任务、范围、标签和划分冻结之前，新决策模型保持未训练。
