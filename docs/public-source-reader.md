# 公共来源读取接口与生产者迁移（2026-10-17）

2026-10-20：来源读取与历史迁移规则保持不变。新增 /2 快照生产者独立于历史
生产者，仅显式启用；见[任务契约与命令](task-contracts.md)。下文既有 /1 包和
历史重建说明不代表 /2 已获训练准入。

本页是09:04用户授权的收尾：提取公共读取能力，保持数据语义，更新公共交接接口。
它替代模块化维护指南中“冻结私有读取暂不迁移”的决定。代码可以演进，旧证据不可覆盖。

## 读取API

~~~python
from pathlib import Path
from dota_items.data.source_io import read_source_bytes, parse_source_json, AuditInputError

contents = read_source_bytes(Path("local-match.json"))
value = parse_source_json(contents)
~~~

- read_source_bytes只读本地文件，默认64 MiB上限，最多读取上限+1字节，不依赖stat结果。
- 超限抛AuditInputError（ValueError子类）；缺文件和权限错误按文件系统异常原样传播。
- 新接口支持非负整数max_bytes，拒绝bool、负数和非整数；超限诊断文字保留历史64 MiB描述，
  自定义上限调用者应记录其参数，不从诊断文字反推出实际阈值。
- parse_source_json沿用标准库解码及原parse_constant规则；不做schema检查、清洗或来源认证。
- NaN/Infinity/-Infinity常量拒绝；重复键仍最后一个值生效，1e999仍可产生inf。
  后两者是明确保留的历史来源解析行为，不是新的安全承诺；严格收紧应另做行为迁移。
- 字节BOM/编码行为和标量/列表结果沿用标准库。来源JSON读取器不能替代严格模型/交接解码器。
- feasibility._read_bytes/_parse保留兼容包装；AuditInputError和MAX_BYTES旧导入仍有效。
  feasibility_sampling、player_overlap已直接使用公共接口，架构测试禁止新增私有读取依赖。

## 生产者证据与显式兼容重建

默认verify_snapshot、verify_preflight继续严格比较重建结果，旧实现指纹变化必须报错。
可显式传allow_producer_migration=True，CLI对应--allow-producer-migration。
当前仅登记public-reader/1迁移：五个既有文件的准确旧SHA-256，新增source_io和producer_migration模块。
比较器验证旧哈希属于登记值、新哈希属于当前文件；只允许指定位置的实现清单变化。
数据、配置、标签、mask、特征、split、数组顺序或JSON类型有任何差异都拒绝。
不是递归删除所有哈希、忽略来源变化或自动接受任意历史版本；也不是训练授权或真实性证明。

verify_snapshot在兼容模式验证后返回原快照，避免把新实现元数据冒充旧产物；
build_snapshot可在显式模式重建供比较，但不覆盖原快照。
verify_preflight的兼容验证返回compatible_replay及变化清单，不宣称旧生产者逐字节重现。
新报告审计清单加入两个新模块的指纹。旧快照内13项历史清单不改写；新重建清单为15项。

## 当前交接

新公共交接入口：reports/public-reader-2026-10-17/handoff/。
固定五载荷与purchase-data-handoff/1不变，模型快照格式仍为purchase-log-modeling-snapshot/1。
新包继续复制旧952场快照和来源摘要原字节，不生成新增1,038场训练快照。
manifest及cohort-audit同时声明producer_migration=public-reader/1；消费者拒绝不一致或未知声明。
仅verify_bundle检查字节/schema，不代表执行了来源重建或确认研究许可。
模型侧无需改输入字段，继续按快照词表、列序、mask和既有划分读取。

在仓库根目录使用现有环境，输出路径必须不存在：
~~~bash
PYTHONPATH=src .venv/bin/python scripts/prepare_purchase_snapshot.py \
  --summary reports/purchase-952-summary-2026-10-14.json \
  --verify reports/purchase-log-snapshot-952-2026-10-14.json \
  --allow-producer-migration

PYTHONPATH=src .venv/bin/python scripts/audit_purchase_cohorts.py \
  --old-root data/purchase-1000-2026-10-14 \
  --new-root data/purchase-additional-1000-2026-10-15 \
  --summary reports/purchase-952-summary-2026-10-14.json \
  --snapshot reports/purchase-log-snapshot-952-2026-10-14.json \
  --output reports/REPLACE-WITH-UNIQUE-audit.json --allow-producer-migration

PYTHONPATH=src .venv/bin/python scripts/package_purchase_handoff.py \
  --summary reports/purchase-952-summary-2026-10-14.json \
  --snapshot reports/purchase-log-snapshot-952-2026-10-14.json \
  --audit reports/REPLACE-WITH-UNIQUE-audit.json \
  --interface docs/handoff/purchase-data-interface.md \
  --output reports/REPLACE-WITH-UNIQUE-handoff --allow-producer-migration
~~~

先验证审计非实现字段与既有版本一致，再打包；本轮比较收据位于audit-comparison.json。
新审计同时绑定当前迁移相关源码；以后源码再次变化必须重建，不得绕过证据哈希。

## 本地证据与恢复

reports/public-reader-2026-10-17/内source-before.tar.gz保存本轮前820项仓库文件，
source-before.json记录SHA-256，protected-before.json绑定7,684项既存data/reports文件。
snapshot-migration.json记录7项实现指纹变化、旧快照/摘要身份及新的完整实现清单；
audit-comparison.json记录统计完全一致及实现证据变化。旧原始缓存、快照和包全部保留。
精确复现旧生产者需在独立暂存环境恢复归档及原路径映射，不能解压覆盖当前目录。
本轮不会真实训练、选模、改变标签/划分、安装依赖、提交或推送。
验收结果见[验证交付](validation-and-delivery.md)。
