# 控制分类重读（U88）

控制分类改了，定义变了，所以重读全部对象。范围是缠绕、捆缚、束缚、嘲讽、恐惧、蛊惑和候选词条“创造地形”。

- Codex：`gpt-6.1-sol`，`reasoning effort: high`，临时账号（38批日志都记录`account=temp`），约71万tokens，934个对象全覆盖。盲审：输入不含现有记录。批次复用`../full-audit-001/batches/`。
- 结果在`results/`：缠绕20、捆缚8、束缚7、嘲讽10、恐惧8、蛊惑5、创造地形10（其中不确定3条）。

`make_rulings.py`把U85–U89写成`../recheck-rulings-001.jsonl`。

局限：只读文字，未运行游戏。取舍由Claude看过结果后提出，不是盲审；写入内容按U88、U89。
