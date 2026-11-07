# 补丁版本核对（MK-T6d，2026-11-06，U99、U113）

**结论：当前知识库（`current.json`）和当前游戏版本7.41f一致，没有发现过时的内容。** 只核对了官方文字和数据，没有在游戏里实测。

## 核对了什么

| 项目 | 做法 | 结果 |
|---|---|---|
| 当前补丁 | Valve官方补丁列表（`patchnoteslist-english.json`） | 最新仍是7.41f（2026-09-15），之后没有新补丁 |
| 游戏脚本 | 第三方镜像SteamDatabase/GameTracking-Dota2：固定版本`ee99709`（10-30）对比最新`b671cd0`（11-05），用已登录的`gh`只读比较 | 之间4个提交只改了版本号文件和下载清单，技能、英雄、物品脚本都没变（`mirror-check.json`）。7.41f之后英雄脚本只在10-14、10-15改过外观槽位，固定版本已包含 |
| 英雄和技能文字 | 重新抓Valve英雄数据（127个英雄，中英文），快照`knowledge/hero-capabilities/snapshots/2026-11-06/` | 与11-01完全相同（英文自10-09起未变）；事实里700个技能都在当前数据里 |
| 装备 | 抓Valve英文装备数据（147件，`knowledge/items/sources/itemdata-english-2026-11-06/`）；对照游戏文件和退出装备标记 | 142件有接受事实的装备都在游戏文件里，能买或已记来源 |
| 装备原文 | 装备事实的引用原文来自第三方dotaconstants，逐条检查在当前官方文本或属性里是否还有依据，属性数值是否一致 | 1处原文找不到、3件整体文字差异大；逐条看过都是误报（`review.json`）；数值全部一致 |

`report.json`是脚本输出的候选清单，`review.json`是逐条核对结论。

## 局限

- Valve数据接口没有版本号字段，版本对应靠“补丁列表最新是7.41f＋所有快照都在它之后＋游戏脚本未变”推断。
- 游戏文件来自第三方镜像，不是Valve直接发布。
- 只查“文字和数据是否还在”，不查机制判断本身对不对（那是抽查的事）。例如魔法芒果的“治疗”来自+0.4生命恢复属性，属性还在，所以版本一致；算不算治疗是定义问题。
- 中立物品和天赋不在知识库范围内，没有核对。
- 冻结的事实包（v1–v20）里的`patch_verified=false`不改；核对结果记在`current.json`的`patch`里。

## 回答之前的抽查疑问

U5抽查时用户在“殁境神蚀者·奥术天球／减伤”上标了“这个东西是在哪读出来的？？是7.41f吗”（`review_id` d3917c7271c8a9fb8413）。答：这条来自Valve接口里残留的旧A杖文字——接口的`ability_has_scepter`是false，文字却还在，所以不是7.41f的内容。MK-T3第3版证据已把这类过时升级文字整体去掉（`knowledge/mechanics/stale-upgrade-text-v1.json`），这一行在当前事实里已不存在，反馈保留在`unattached_feedback`。

## 复现

```bash
python scripts/refresh_hero_datafeed.py fetch --output <新目录>
PYTHONPATH=src python scripts/check_patch_knowledge.py fetch-items --output <新目录>
PYTHONPATH=src python scripts/check_patch_knowledge.py check --heroes <英雄快照>/sources --items <装备目录> --output <新路径>
```
