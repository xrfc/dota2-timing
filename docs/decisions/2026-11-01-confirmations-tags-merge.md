# U30 可驱散性表确认；闪避与致盲分开；补打版本标签；合并PR #9

- 决定（用户2026-11-01“可驱散性表确认，闪避和致盲分开，打标签后可以整理合并了”）：
  1. `knowledge/mechanics/enums-v1.json`中`dispellable`四个取值全部标为已确认（0不产生可驱散效果、1仅强驱散、2弱驱散可驱散、3不可驱散）。其余字段（`immunity`、`target_team`、`damage`、`type`）仍待确认。
  2. 词表中闪避（`evasion`，自身躲避攻击，金箍棒类可穿透）与致盲（`blind`，使敌方攻击落空，靠驱散或离开范围）分开，关闭该待答问题。
  3. 补打版本标签：`v0.3.0`→331c6d0（2026-10-04，pyproject升到0.3.0）、`v0.4.0`→63d395a（2026-10-05，升到0.4.0），与v0.1.0/v0.2.0同为附注标签。
  4. 整理后合并PR #9（claude-temp→main）。
- 追加（2026-11-01）：用户确认其余四张枚举表（`immunity`、`target_team`、`damage`、`type`）——“剩下四张枚举表也确认”。`enums-v1.json`全部取值`confirmed=true`，MK-T2完成。标签推送等用户回到电脑前再做（“推送标签可以等我回去”）。
- 执行情况：标签已在云端本地创建，但**推送标签被会话的git通道拒绝**（重试4次均为`remote end hung up`，代理无失败记录；同一通道推送分支正常），远端暂无v0.3.0/v0.4.0。需用户在本地执行：
  ```bash
  git fetch origin
  git tag -a v0.3.0 331c6d0 -m "v0.3.0: version bumped in pyproject on 2026-10-04 (tagged retroactively 2026-11-01, U30)"
  git tag -a v0.4.0 63d395a -m "v0.4.0: version bumped in pyproject on 2026-10-05 (tagged retroactively 2026-11-01, U30)"
  git push origin v0.3.0 v0.4.0
  ```
- 来源：2026-11-01用户消息“可驱散性表确认，闪避和致盲分开，打标签后可以整理合并了”。
