# 装备登记表（U14）

- `item-registry.json`：每件装备的键名、**官方简体中文名**（Valve）、英文名、价格、配件、是否合成装（`completed`）、是否图纸/中立物品、来源。代码通过`dota_items.data.item_registry.load_registry`/`display_name`读取；名称找不到时显示英文或原始键名，**不得手写猜测译名**。
- `sources/`：2026-10-30 16:35 UTC下载的原始文件与`manifest.json`（URL、发布方、SHA-256）。Valve为名称权威；价格与配件来自OpenDota社区数据，非官方。
- 重建：`PYTHONPATH=src .venv/bin/python scripts/build_item_registry.py --overwrite`（先核对来源哈希）。更新补丁时需重新下载来源并获用户同意联网。
- “是否成品”判断（看局装统计用）：合成装，或不作为任何装备配件且价格≥1000的单买装（如闪烁匕首）；排除图纸、中立物品。
