# 自动采集demo（U128、U129）

`scripts/collect_demos.py`可以自己启动、自己跑，不需要和助手对话。它会一场一场地：找对局 → 向OpenDota要比赛信息 → 从Valve下载demo → 本地解析 → 压缩保存，直到达到目标场数。

## 启动

在项目目录（`/home/node/.openclaw/workspace/work/dota2-timing`）运行，后台跑、关掉终端也不停：

```bash
nohup env -u http_proxy -u https_proxy PYTHONPATH=src .venv/bin/python scripts/collect_demos.py run --root data/demos-2026-11 > data/demos-2026-11.out 2>&1 &
```

需要本机代理`127.0.0.1:7890`开着（OpenDota和Valve都走它；不走代理加`--route direct`）。

## 看进度

```bash
PYTHONPATH=src .venv/bin/python scripts/collect_demos.py report --root data/demos-2026-11
```

会显示：已解析场数、跳过和失败的原因、demo和解析结果占了多少GB、平均解析时间、出现过的英雄数和最少的15个英雄。详细记录在`data/demos-2026-11/log.txt`。

## 停止和续跑

- 停止：`pkill -f "collect_demos.py run"`（或关机）。
- 续跑：再运行同一条启动命令。已经处理过的比赛有回执（`receipts/`），不会重复；下载了一半的会重新下载，解析了一半的会重新解析。
- 同一个目录同时只能有一个采集程序；和项目里其他OpenDota采集脚本也不能同时跑（共用额度）。

## 它自己会停的情况

| 情况 | 行为 |
|---|---|
| 达到目标（默认1500场解析成功） | 停止 |
| 磁盘剩余不到30GB | 停止 |
| 连续3次下载或网络错误 | 停止，看`log.txt`后续跑 |
| OpenDota当天额度用完（自己限1,900次/天，遇到429停24小时） | 等到额度恢复后自动继续 |
| 暂时没有新对局 | 等30分钟再找 |

## 采什么、存什么

- 对局：当前补丁（启动时从Valve官方补丁列表读）、天梯全英雄选择、对局平均超凡及以上、15分钟以上、2小时到4天前的比赛（太新回放还没生成，太旧会过期）。不按英雄、不按位置筛选（U110、U116）。
- 每场保留：OpenDota比赛信息`meta/<id>.json`；原始demo`demos/<id>.dem.bz2`（约40–50MB，U112）；全部解析通道压缩后`parsed/<id>.normalized.json.gz`（含逐秒位置、视野、血蓝装备快照、经济、购买、战斗日志、眼位，U129）；回执`receipts/<id>.json`。
- 解析器每场会产生约0.8GB的中间文件（同一份数据的多份未压缩JSON），压缩副本读回校验一致后，删掉这一场的中间文件；想保留就加`--keep-workspace`（磁盘会很快不够）。
- 1500场预计（按试采实测：demo 41–52MB、压缩解析结果约6.5MB、每场94–127秒）：demo约70GB＋解析结果约10GB；全部约50小时；OpenDota请求约1,600次（发现对局＋每场1次）。机器内存只有5GB，所以一次只解析一场。
- 技能冷却解析器目前没有导出（试采确认），路线B需要时再补提取；demo保留着，可以重新解析。

## 冷门英雄补采

先看`report`里最少的英雄，再按英雄补（只找有该英雄的对局）：

```bash
nohup env -u http_proxy -u https_proxy PYTHONPATH=src .venv/bin/python scripts/collect_demos.py run --root data/demos-2026-11 --target 1700 --hero 91 --hero 103 > data/demos-2026-11.topup.out 2>&1 &
```

补采的对局含指定英雄，会让这些英雄的样本变多；统计时记得这些局不是无差别抽样（回执和`runs.jsonl`都记了当时的英雄筛选）。

## 不会做的事

不用付费密钥，不请求OpenDota解析，不训练模型，不上传任何东西；demo和解析结果都在被忽略的`data/`里，不进仓库（用户规定demo和对局解析文件不推送）。
