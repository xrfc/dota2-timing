# 机制知识框架（U26；U27扩为完整版，里程碑MK）

三层结构，每层只依赖下层；设计与状态见[知识框架说明](../../docs/knowledge-framework.md)。

| 层 | 文件 | 状态 |
|---|---|---|
| 1 事实层：官方原始枚举的含义 | `enums-v1.json` | 助手草稿，待用户确认（`confirmed`字段，MK-T2） |
| 1 事实层：机制词表 | `vocabulary-v1.json` | 助手草稿（42项），定义待用户拍板（MK-T1） |
| 1 事实层：官方说明事实 | 待建（MK-T3） | — |
| 2 机制规则层：机制交互与装备↔机制克制 | 待建（MK-T4） | — |
| 3 推导层：英雄/装备机制档案、克制图、hero-traits v2 | 待建（MK-T5） | — |

- 读取一律用`dota_items.data.mechanics.load_enums(doc, registry_heroes)`与`load_vocabulary(doc, enums)`：每个例子技能必须存在且取值一致；登记表中出现的取值必须全部有解释，补丁更新出现新取值时直接报错。
- 修改须记决策并升版本（v2…），旧版本不覆盖。
