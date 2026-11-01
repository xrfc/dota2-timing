# 主宰阵容分析原型（2026-10-25）

用户要求回到可体验的出装分析功能，并明确授权按建议实现。这里执行已有冻结制品的手工阵容推理，不训练、不使用新前瞻数据，不变更已批准采集协议。

## 能做什么

- 选择双方各五名英雄，友方含主宰；输入检查拒绝重复、非法ID或缺少目标英雄。
- 显示11装备源日志出现概率、训练频率基线及百分点差值。按概率排序，不代表购买顺序或推荐排名。
- 展开每件装备，查看全量有效输入的log-odds贡献、截距、训练正例支持数。检查sigmoid(截距+贡献和)精确重建现有推理结果。
- 检索三个训练集历史案例，只用同侧英雄重合数排序，排除固定主宰后满分9，并列按ID。检索不看标签、胜负或预测结果；显示双方阵容、已记录装备、未知标签和源字节哈希。
- 训练词表外英雄明确降级为未知计数，不假装模型了解新英雄。英雄中文名只作展示，不消费知识库中尚未审核的机制解释。

## 产品与学习边界

这是**行为分析原型**，还不是完整建议系统。购买倾向不是最优决策，贡献是模型关联不是克制因果；不同模型的频率基线不能当逻辑回归截距。
第一版未接入补丁核验的机制解释、装备组合、购买顺序或收益判断，不输出“这局应该买”的断言。
默认阵容是已有手工演示输入，未认证为合理分路或真实比赛。案例来自训练集，不是泛化测试。默认输入最近三个案例仅重合3/9，不能据此称为高度相似局势。

建议试用练习：固定九个英雄，只换一个敌方英雄，查看概率与分数贡献；检查大幅变化是否具有足够样本支持，并记录模型不合理行为，再决定下一轮特征或目标研究。不按单个案例重新选择C。

## 启动与导出

在项目根目录使用现有环境，不安装依赖：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/lineup_analysis.py --serve --port 8765
```

浏览器打开 `http://127.0.0.1:8765`。只绑定服务所在机器的回环地址；若从另一台设备访问，需要现有端口转发，不能把手机/电脑的localhost当服务器。Ctrl+C结束。
页面是标准HTML表单，选择后提交到本地Python推理，无第三方页面资源和浏览器端重写模型算法。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/lineup_analysis.py \
  --lineup examples/model-foundation-lineup.json --output reports/my-lineup-analysis
```

导出目录必须不存在；包含JSON和可直接打开的静态HTML。静态报告只支持展开解释，不支持重新输入阵容；改阵容需使用本地服务或重新导出。

Windows PowerShell（仓库及本地模型/快照齐全时）：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\lineup_analysis.py --serve --port 8765
```

## 实现与证据

- `src/dota_items/modeling/lineup_analysis.py`：纯模型解释与训练案例检索，复用既有predict_lineup。
- `scripts/lineup_analysis.py`：冻结制品加载、原型HTML与本地HTTP表单、离线导出；不使用共享workflow或recommendation模块。
- `tests/test_lineup_analysis.py`：真实冻结输入只读验收，无fit；没有本地私有制品的环境明确skip，不能将skip报告为通过。
- 严格校验两个模型文件的已知字节哈希、模型内部校验和、任务契约、同源快照canonical digest和预处理一致性；案例只取1592条train成员。
- 原型输出：[静态分析](../reports/lineup-prototype-2026-10-25/index.html)、[结构化数据](../reports/lineup-prototype-2026-10-25/analysis.json)、[单英雄替换对照](../reports/lineup-prototype-2026-10-25/enemy-swap.json)。这些是手工阵容功能演示，不是新数据评价或新性能报告。

真实演示将敌方英雄10换成25，其余不变：跳刀概率48.98%→59.44%，冰眼27.28%→16.90%，A杖52.74%→60.97%；所有频率基线不变。这说明输入确实影响已训练模型，不证明变化合理或推荐正确。

验证命令：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider \
  tests/test_lineup_analysis.py tests/test_model_foundation.py \
  tests/test_model_foundation_validation.py tests/test_architecture.py -q
```

本轮只修改上述模型专属文件及本文件、模型进度文档；不改共享路线/配置、采集器、冻结协议或旧模型。未安装依赖、提交、推送或执行全库验收。

实测结果：上述专项**158项通过**，无跳过；Ruff及格式检查通过。真实模型导出、单英雄替换以及本地HTTP表单默认/合法/非法输入均完成验证。浏览器视觉布局未验证（当前环境未提供可用Playwright）；不声称已完成视觉验收。[验证收据](../reports/lineup-prototype-2026-10-25/verification.json)记录本轮源码和输出哈希。
