# 游戏文件快照（U46）

来自第三方公开镜像SteamDatabase/GameTracking-Dota2固定提交的游戏文本文件，含技能定义和英文本地化。用于核对机制证据，不用于训练。快照不覆盖，新抓取放新日期目录；每个文件的来源和SHA-256见`manifest.json`。

镜像未声明许可证，文件内容属于游戏文件；用户已同意进远端（U53）。`2026-11-03-items`、`2026-11-03-neutral`是同一提交的`items.txt`、`neutral_items.txt`。首次使用见[破坏对照](../mechanics/reviews/break-check-001/README.md)。

## 2026-11-17：核对最新版本（用户授权“可以抓取”）

- 抓取镜像提交`ab523510b09908cedec32e7b0cce6333c27e5af2`（客户端版本6976，`VersionDate=Nov 16 2026`）的`npc_abilities.txt`、`items.txt`、技能和物品的英文本地化、`steam.inf`，放在`snapshots/2026-11-17/`。
- 与11-02快照（版本6969）逐字节比较：`npc_abilities.txt`、`items.txt`、技能英文本地化**完全相同**；英雄技能文件在两次提交之间也没有改动（镜像的提交对比只显示`items_english.txt`多了3行文字）。所以demo采集期间（11-08至11-15）的游戏数值就是11-02快照的数值，不需要重建知识库。
- 用途：路线B死亡风险模型第2版的“己方假眼覆盖”用了`item_ward_observer`的视野1600、持续360秒（`data.death_risk.OBSERVER_VISION`）。
- 另查了Valve官方GitHub（`ValveSoftware`）：和Dota 2有关的库只有问题追踪（玩法bug帖、Linux/Mac和Vulkan客户端问题），没有游戏数据文件。玩法bug帖是玩家写的、几乎没有官方标签，只在某条机制事实有疑问时按需搜索，不批量使用。
