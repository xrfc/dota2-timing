# 复核后事实 v26（U126）

- **哈斯卡·牺牲**：“减益免疫”改为排除（原文是“减速效果无视减益免疫”，不是哈斯卡自己减益免疫）；“无视减益免疫”一行依据改为`user:U126`。清单`reviews/v26-inputs-001.json`。
- **术语改名**：“穿透减益免疫”改叫官方字段名“无视减益免疫”。词表v15、枚举v2、规则v13的文字和档案页面标签都改了，AI写的说明文字也一并改；机制编号`pierces_debuff_immunity`和规则含义不变；引用的官方原文不改，旧版本文件和历史决策不改。

接受2598→2597，排除697→698。

```bash
PYTHONPATH=src .venv/bin/python scripts/build_mechanics_facts_v26.py --output <新目录>
```
