# U25 AI临时分支：`<ai名>-temp`，经PR进main

- 背景：云端会话容器临时，未推送提交会丢失；用户规则是只在要求时推送`main`（U19、U24）。此前临时用一次性分支`claude/hero-traits-candidate-rules`防丢失，内容已全部并入main。
- 选项：①长期专用分支，随时推送，用户合并（助手推荐）；②每次临时起新分支；③直接推main。合并方式：A用户说“合并”由助手合并；B助手开PR、用户在网页合并（助手推荐，便于看改动、学习）。
- 决定：①＋B。分支名按用户建议采用`<ai名>-temp`（Claude为`claude-temp`），并写成契约，其他改动代码的AI也按此执行；删除旧临时分支`claude/hero-traits-candidate-rules`（删除前确认它已全部包含在main中）。
- 后果：契约见`docs/handoff/ai-temp-branch-contract.md`；AGENTS.md新增入口。temp分支可随时推送、开PR；合并PR、推送main、删除分支仍须用户同意。本地OpenClaw工作区仍只用main。
- 来源：2026-10-31用户消息“明白，那我们可以固化一个分支专门用于存放云端对话的修改？”；助手给出方案后，用户回复“可以，按这个写一份契约，告诉其他改动代码的ai也可以这样做，起名可以Claude-temp之类的？”。
