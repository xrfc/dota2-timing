import pytest
from test_patch_review_producers import local_dependencies

from scripts.build_patch_decision_audit import PRODUCER_FILES, render_report, run


def test_execution_dependencies_are_all_bound_by_the_new_receipt():
    pinned = set(PRODUCER_FILES)
    for path in pinned:
        assert set(local_dependencies(path)) <= pinned, path


def test_existing_output_rejected_before_reading_any_source(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        run(tmp_path / "absent.json", output)
    assert list(output.iterdir()) == []


def test_local_report_escapes_source_strings_and_separates_hindsight():
    view = {
        "observer_team": 2,
        "requested_game_time": 1.25,
        "requested_replay_tick": 60,
        "friendly_heroes": [
            {
                "player_id": 0,
                "npc_name": '<script>alert("bad")</script>',
                "observed_state": {"health": 10, "life_state": 0},
                "position": None,
            }
        ],
        "camp_observations": [],
        "objectives": {"roshan": {"observed_live_entities": []}},
    }
    html = render_report(
        {"cases": [{"match_id": 123, "target_game_second": 1, "context": {"known_view": view}}]},
        {"matches": [{}], "summary": {}},
        {"summary": {"unresolved_active_units": 0}},
        {"summary": {"rows": 14}},
        [{"future": "</pre><script>bad</script>"}],
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "事后工程核对" in html and "完整坐标FOW没有被此报告认证" in html
    assert "当前状态未知" in html
