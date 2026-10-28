# 2026-10-13 可行性与语义来源

- `patch-list.json` / `receipt.json`：官方发布时间快照、来源/时间/哈希，用于时间一致性推断，不认证客户端版本。
- `expansion-plan.json`：原发现列表第4–13条固定ID与配置；原发现JSON在忽略的data目录，异机复现需提供原件。
- `semantic-sources.json` / `opendota-*.ts.txt`：上游mutable master文本快照，不是部署版本证明。
- `OPENDOTA-LICENSE.txt`：OpenDota来源代码的MIT许可，保留原版权。

实测与边界：[数据审计](../../../docs/data-feasibility.md)、[语义核验](../../../docs/data-semantics.md)。
原玩家JSON/账号不进入本目录；脱敏记录见[验收目录](../../../docs/acceptance/)。
