# U82 全量补漏用Codex高推理强度

- 用户决定（原话）：“可以用high”。
- 背景：用户问Codex用什么模型和强度。日志显示`gpt-6.1-sol`、`reasoning effort: none`；`~/.codex/config.toml`不存在，调用时也没传参数，所以是默认值，不是有意选择。
- 落地：停掉强度`none`的全量补漏，已完成的批次移到`knowledge/mechanics/reviews/full-audit-001/results-effort-none/`，只作对比；改用`-m gpt-6.1-sol -c model_reasoning_effort=high`从头重跑。
- 之后每轮Codex记录都要写明模型和强度。
- 第1–8轮目录没有留下模型和强度记录，无法确认；当时同样没指定，很可能也是默认值。是否复查，待这轮结果出来后再由用户决定。
- 来源：用户消息。
