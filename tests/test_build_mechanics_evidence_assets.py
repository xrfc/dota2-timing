import pytest
from test_patch_review_producers import local_dependencies

from scripts.build_mechanics_evidence_assets import PRODUCER_FILES, render_report, run


def test_all_executed_local_modules_are_in_the_new_producer_closure():
    pinned = set(PRODUCER_FILES)
    for filename in pinned:
        assert set(local_dependencies(filename)) <= pinned, filename


def test_existing_output_is_rejected_before_inputs_are_opened(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        run(tmp_path / "absent", output)
    assert not list(output.iterdir())


def test_report_escapes_conditions_and_labels_evidence_limits():
    html = render_report(
        {
            "rows": [
                {
                    "review_id": "<script>bad</script>",
                    "candidate_usable": True,
                    "engineering_admission": {
                        "operation": "promote",
                        "conditions": {"target": "</td><script>bad</script>"},
                        "unproven_capabilities": ["spell_reflect_interaction"],
                    },
                }
            ]
        },
        {},
    )
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "不自动证明格挡或反弹" in html
    assert "没有新增用户裁定" in html
