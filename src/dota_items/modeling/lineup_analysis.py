"""Read-only lineup explanation and training-case retrieval, never recommendations."""

import math

from dota_items.contracts.lineup import encode_lineup
from dota_items.contracts.tasks import WHOLE_LOG_TASK_ID, task_contract

from .inference import predict_lineup

ITEM_NAMES = dict(
    zip(
        [
            "bfury",
            "maelstrom",
            "mjollnir",
            "manta",
            "sange_and_yasha",
            "butterfly",
            "blink",
            "ultimate_scepter",
            "monkey_king_bar",
            "diffusal_blade",
            "skadi",
        ],
        [
            "狂战斧",
            "小电锤",
            "大电锤",
            "分身斧",
            "散夜对剑",
            "蝴蝶",
            "跳刀",
            "阿哈利姆神杖",
            "金箍棒",
            "散失之刃",
            "斯嘉蒂之眼",
        ],
        strict=True,
    )
)


def analyze(lineup, model, baseline, samples, *, limit=3):
    contract = task_contract(WHOLE_LOG_TASK_ID)
    predicted = predict_lineup(model, lineup, expected_task_contract=contract)
    reference = predict_lineup(baseline, lineup, expected_task_contract=contract)
    if (
        model["family"] != "logistic"
        or baseline["family"] != "frequency"
        or model["preprocessing"] != baseline["preprocessing"]
        or model["provenance"]["source_sha256"] != baseline["provenance"]["source_sha256"]
    ):
        raise ValueError("Model/baseline pairing mismatch")
    x = encode_lineup(lineup, model["preprocessing"]["vocabulary"])
    items = []
    for m in model["models"]:
        key = m["item"]
        if m["status"] != "trained":
            raise ValueError("Prototype requires trained targets")
        terms = [
            dict(feature=column, value=value, contribution=value * coef)
            for column, value, coef in zip(
                model["preprocessing"]["columns"], x, m["coefficients"], strict=True
            )
            if value
        ]
        z = m["intercept"] + math.fsum(t["contribution"] for t in terms)
        p = predicted["probabilities"][key]
        reconstructed = math.exp(-max(0, -z)) / (1 + math.exp(-abs(z)))
        if not math.isclose(p, reconstructed, abs_tol=1e-12):
            raise ValueError("Explanation does not reconstruct prediction")
        items.append(
            dict(
                item=key,
                name=ITEM_NAMES[key],
                probability=p,
                baseline=reference["probabilities"][key],
                delta_pp=100 * (p - reference["probabilities"][key]),
                intercept=m["intercept"],
                logit=z,
                support=m["support"],
                contributions=sorted(terms, key=lambda t: -abs(t["contribution"])),
            )
        )
    # Similarity uses hero sets only, never labels, outcome, or predicted score.
    candidates = []
    for row in samples:
        if row["split"] != "train":
            continue
        features = row["features"]
        common = sum(
            len((set(lineup[side]) & set(features[side])) - {8})
            for side in ("ally_hero_ids", "enemy_hero_ids")
        )
        candidates.append((common, row["match_id"], row))
    cases = []
    for common, mid, row in sorted(candidates, key=lambda t: (-t[0], t[1]))[:limit]:
        cases.append(
            dict(
                match_id=mid,
                overlap=common,
                max_overlap=9,
                features=row["features"],
                source_sha256=row["source_sha256"],
                observed_items=[
                    ITEM_NAMES[k]
                    for k, y, mask in zip(ITEM_NAMES, row["labels"], row["label_mask"], strict=True)
                    if mask and y == 1
                ],
                unknown_items=[
                    ITEM_NAMES[k]
                    for k, mask in zip(ITEM_NAMES, row["label_mask"], strict=True)
                    if not mask
                ],
                split="train",
            )
        )
    return dict(
        lineup=lineup,
        items=sorted(items, key=lambda r: -r["probability"]),
        unknown_counts=predicted["unknown_counts"],
        cases=cases,
        meaning="整份源购买日志出现概率；不是最优出装、胜率或购买顺序",
        recommendation_validated=False,
    )
