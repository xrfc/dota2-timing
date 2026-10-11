# 7.41f 阵容推荐契约（M01 首个切片）

更新：2026-10-11。实现位于 `src/dota_items/recommendation/contracts.py`，复用已有
Pydantic 2，不新增依赖，不导入回放、数据准备或训练模块。本模块只定义和验证协议，
**不生成装备建议，也不证明来源已被人工核验**。

## 范围和输入

首个产品验收英雄为主宰（hero ID 8）；通用契约接受目录中的其他英雄，
不代表推荐器已经支持它们。位置必须由调用者明确提供，不从英雄或数组顺序推测。
2026-10-11用户已确认首版仅支持一号位主宰，保留全英雄/全位置扩展能力。
首批装备与应用入口已落地，见[本地推荐说明](lineup-recommendation.md)。

```python
import json
from pathlib import Path

from dota_items.recommendation.contracts import validate_lineup

catalog = json.loads(Path("knowledge/hero-capabilities/sources/opendota-heroes.json").read_text())
request = validate_lineup(
    {
        "patch": "7.41f",
        "radiant": [8, 1, 2, 3, 4],
        "dire": [5, 6, 7, 9, 10],
        "target_team": "radiant",
        "target_hero_id": 8,
        "role": 1,
    },
    known_hero_ids={row["id"] for row in catalog.values()},
)
print(request.model_dump_json())
print(request.fingerprint())
```

上例仅演示有效输入，不表示阵容质量或出装结论。从仓库根目录执行。

| 字段 | 约束 |
|---|---|
| `schema_version` | `coach-lineup-request/1`，可省略使用此默认值 |
| `patch` | 必须显式为 `7.41f`，不接受 `latest` |
| `radiant` / `dire` | 每方恰好 5 个正整数 ID，双方合计不得重复 |
| `target_team` / `target_hero_id` | 阵营为 `radiant` 或 `dire`；目标必须属于该阵营 |
| `role` | 必填整数 1–5，仅代表目标位置 |

拒绝字符串数字、布尔 ID/位置和未知字段，包括命石、库存等本轮未建模输入。
队内英雄按 ID 排序后保存为不可变元组；数组位置不表示分路。
`fingerprint()` 对规范化输入的稳定 JSON 求 SHA-256；队内换序不改变指纹，
更改目标、位置或阵营会改变指纹。JSON Schema 可由 `model_json_schema()` 获取。

`LineupRequest.model_validate()` 仅做结构校验。应用入口应使用 `validate_lineup()`，
并显式传入非空英雄目录；它不读取文件或联网。目录成员身份不等于7.41f机制覆盖。

## 错误与未知必须分开

| 情况 | 表现 |
|---|---|
| 格式、人数、重复、目标归属、版本或位置错误 | Pydantic `ValidationError`；不伪装成空推荐 |
| 已满足结构但 ID 不在目录 | `UnknownHeroError`，`code="unknown_hero"`，`hero_ids` 为排序后的未知 ID |
| 目录为空或含非正整数 | `ValueError`，属于调用边界配置错误 |
| 英雄身份已知，但机制无证据或冲突 | 输出覆盖为 `unknown` / `conflict`，不删除该英雄 |

## 推荐结果信封

`Recommendation` 的版本为 `coach-lineup-recommendation/1`，必须绑定完整请求及其
`input_fingerprint`，并提供知识/规则版本与各自 SHA-256、引擎版本和非空局限说明。
知识/规则哈希的格式被校验，但文件内容与哈希的一致性须由未来调用层核验。

- `coverage`：十位英雄各一条，不可重复、缺失或混入阵容外英雄。
  `verified` 必须引用事实，`unknown` / `conflict` 不得携带已验证事实列表。
- `evidence`：事实 ID 唯一，含来源引用、来源 SHA-256、`source_patch="7.41f"`、
  `review_status="verified"` 和可选英雄 ID。覆盖引用必须解析到同一英雄的事实。
  `hero_id=None` 可表达装备或通用事实；本层不核验来源文件是否存在或审核是否真实。
- `candidates`：装备 key 全局唯一；含 `core` / `situational` / `alternative` 分类、
  `early` / `mid` / `late` 阶段、理由、可选条件、非空代价、规则 ID 和事实 ID。
  事实引用必须解析到证据；规则 ID 的存在性留给未来规则包校验。
- `score_components`：可选的具名分数组成，名称唯一、值有限；允许负分，
  不代表概率、胜率或已校准的推荐质量。
- `empty_reason`：无候选时必填，有候选时必须为空。

| `status` | 结构语义 |
|---|---|
| `supported` | 十位英雄覆盖均为 `verified`；仍可因无合适装备而返回有理由的空候选 |
| `partial` | 1–9 位英雄覆盖为 `verified`，其余未知或冲突 |
| `unsupported` | 不允许候选；即使英雄证据齐全，也可因目标位置等超出引擎范围而拒绝 |

任何非空候选都要求目标英雄覆盖为 `verified`。覆盖和引用验证只保证声明自洽；
不能把测试中的 `verified` 声明当作真实机制审查结果。

## 当前边界与兼容性

- 首批规则知识已作为独立版本包接入；装备是否存在、是否属于范围、配方与例外未在此契约层判断。
  小件可作为后续目标，树枝、卷轴和消耗品不作为产品目标，但本层不硬编码未核验目录。
- 没有经济、库存、时间或队友位置输入，不能声称“现在立即购买”、最优顺序或精确购买时机。
- 已有独立推荐用例、CLI 与报告，入口调用目录验证、英雄/位置配置与来源字节/引用核验。
  来源版本关联与人工实战验证的边界见[使用说明](lineup-recommendation.md)。
- 新契约与旧回放/训练 Schema 隔离；包版本保持 0.4.0，不改变真实训练准入状态。
- 模型不可变，嵌套实例在验证边界重新校验。调用者不得用 `model_construct()` 或
  未经再次验证的 `model_copy(update=...)` 绕过协议约束。

验证入口：`.venv/bin/python -m pytest tests/test_recommendation_contracts.py -q`。
测试中的装备、事实、哈希及审核声明均为合成夹具，不是出装建议或7.41f知识证据。
M01原契约切片在 `112056a` 时为部分完成；本轮范围确认、候选清单和应用入口接入后，
首版范围内M01完成。知识深度与推荐质量验收仍独立保留，不因契约验收而关闭。
