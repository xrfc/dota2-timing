"""Read-only Markdown presentation of an existing sensitivity result; never fit models."""

import math


def validate_report(result):
    """Reject malformed display evidence without fitting or repairing the selection."""
    try:
        if result["training_executed"] is not True:
            raise ValueError("Expected executed comparison")
        if not isinstance(result["items"], dict) or not isinstance(
            result["excluded_train_single_class_items"], list
        ):
            raise ValueError("Invalid item collections")
        for item, group in result["items"].items():
            trials = group["trials"]
            selected = group["selected_index"]
            if type(selected) is not int or not 0 <= selected < len(trials):
                raise ValueError(f"{item}: invalid selected_index")
            if sum(t["name"] == "frequency" for t in trials) != 1:
                raise ValueError(f"{item}: expected exactly one frequency baseline")
            support = None
            for trial in trials:
                m = trial["metrics"]["validation"]
                n, positive = m["observed"], m["positive"]
                if (
                    type(n) is not int
                    or type(positive) is not int
                    or not 0 <= positive <= n
                    or n == 0
                ):
                    raise ValueError(f"{item}: invalid validation support")
                if support is not None and support != (n, positive):
                    raise ValueError(f"{item}: inconsistent validation support")
                support = (n, positive)
                for key in ("brier", "mean_prediction", "positive_rate", "average_precision"):
                    value = m[key]
                    if key == "average_precision" and value is None:
                        continue
                    if (
                        type(value) not in (int, float)
                        or not math.isfinite(value)
                        or not 0 <= value <= 1
                    ):
                        raise ValueError(f"{item}: invalid {key}")
                bias = m["mean_prediction_minus_observed"]
                if type(bias) not in (int, float) or not math.isfinite(bias):
                    raise ValueError(f"{item}: invalid probability bias")
                if not math.isclose(m["positive_rate"], positive / n, abs_tol=1e-12):
                    raise ValueError(f"{item}: inconsistent positive rate")
                if not math.isclose(bias, m["mean_prediction"] - positive / n, abs_tol=1e-12):
                    raise ValueError(f"{item}: inconsistent probability bias")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Malformed sensitivity report fields") from exc


def render_report(result, *, source_sha256):
    if not isinstance(result, dict):
        raise ValueError("Expected sensitivity result object")
    if result.get("schema_version") != "purchase-log-sensitivity/1":
        raise ValueError("Unsupported sensitivity schema")
    if result.get("test_evaluated") is not False:
        raise ValueError("Expected train/validation-only evidence")
    validate_report(result)

    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    lines = [
        "# 截距与正则化对照报告",
        "",
        f"输入结果 SHA-256：`{source_sha256}`",
        "",
        "本报告只展示已有结果，不训练、不重新选模、不读取比赛缓存或测试集。",
        "输入可能来自合成测试；本报告本身不证明已运行真实实验。",
        "",
        "## 指标怎么读",
        "",
        "- Brier越低越好：平均(probability - label)²，衡量概率预测误差。",
        "- ΔBrier = 本候选验证Brier − 频率基线验证Brier；负数表示本次验证集更好。",
        "- 平均偏差 = 平均预测 − 观测比例；负数表示总体低估，以百分点展示。",
        "- AP越高通常越好，衡量排序；不能与Brier互相替代。",
        "- C越小正则化越强；截距是共享偏置，不等于实际平均预测概率。",
        "",
    ]
    for item, group in result["items"].items():
        trials = group["trials"]
        frequency = next(t for t in trials if t["name"] == "frequency")
        baseline = frequency["metrics"]["validation"]["brier"]
        lines += [
            f"## {cell(item)}",
            "",
            "星号表示输入结果选中的候选；选择依据为验证Brier，完全并列沿用原候选顺序。",
            "",
            "| 候选 | C | 验证样本/正例 | 验证Brier | ΔBrier | 验证AP | "
            "平均预测 | 观测比例 | 平均偏差（百分点） |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for index, trial in enumerate(trials):
            m = trial["metrics"]["validation"]
            ap = "不可计算" if m["average_precision"] is None else f"{m['average_precision']:.4f}"
            name = cell(trial["name"]) + (" *" if index == group["selected_index"] else "")
            c = "—" if trial["C"] is None else str(trial["C"])
            lines.append(
                f"| {name} | {c} | {m['observed']}/{m['positive']} | {m['brier']:.4f} "
                f"| {m['brier'] - baseline:+.4f} | {ap} | {m['mean_prediction']:.2%} "
                f"| {m['positive_rate']:.2%} | {100 * m['mean_prediction_minus_observed']:+.2f} |"
            )
        lines.append("")
    excluded = ", ".join(cell(i) for i in result["excluded_train_single_class_items"]) or "无"
    lines += [
        "## 边界与未训练目标",
        "",
        f"训练集不具备两个类别而跳过：{excluded}。",
        "",
        "- 验证集同时用于选择和诊断，不是独立泛化证据；不据此声称显著提升。",
        "- liblinear与lbfgs同时改变截距惩罚和优化算法，不是单因素因果消融。",
        "- 目标是购买日志观测，不是最优出装；未对新增数据或测试集作评估。",
        "",
    ]
    return "\n".join(lines)
