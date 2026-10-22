"""Pure comparison supports and package boundaries, without production data."""

import subprocess
import sys

import pytest

from dota_items.contracts.tasks import WHOLE_LOG_ITEMS
from dota_items.modeling.whole_log_comparison import compare, evaluate


def test_unknown_unscored_and_single_class_support():
    rows = [
        {
            "labels": dict.fromkeys(WHOLE_LOG_ITEMS, label),
            "label_mask": dict.fromkeys(WHOLE_LOG_ITEMS, mask),
            "probabilities": dict.fromkeys(WHOLE_LOG_ITEMS, probability),
        }
        for label, mask, probability in [(1, True, 0.5), (0, True, None), (None, False, None)]
    ]
    result = evaluate(rows)
    for item in WHOLE_LOG_ITEMS:
        score = result["per_item"][item]
        assert score["brier"] == 0.25
        assert score["unknown"] == 1
        assert score["known"] == 2
        assert score["unscored_known"] == 1
        assert score["roc_auc"] is None
    assert result["macro"]["brier"]["included_items"] == list(WHOLE_LOG_ITEMS)
    assert result["macro"]["roc_auc"] == {"value": None, "included_items": []}


def test_comparison_rejects_missing_candidates():
    with pytest.raises(ValueError, match="Four fixed candidates"):
        compare({}, {}, candidates={"logistic_c0_1": 0.1, "logistic_c0_01": 0.01}, rules={})


def test_pure_comparison_does_not_import_orchestration_or_training():
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from dota_items.modeling import whole_log_comparison
for prefix in ('dota_items.experiments', 'dota_items.data', 'dota_items.modeling.training'):
    assert not any(n == prefix or n.startswith(prefix + '.') for n in sys.modules), prefix
""",
        ],
        check=True,
    )
