"""The notebook binds local feedback to the exact clip in the viewer's report."""

import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts import b5_trial_notebook as notebook


def reports():
    clips = [
        {"hero": "甲", "domain": "兵线", "time": "16:07", "rows": ["录像实况"]},
        {"hero": "乙</ScRiPt>", "domain": "兵线", "time": "16:07", "action": "观察到的动作"},
    ]
    return {
        "matches": [
            {"id": "200", "report_sha256": "a" * 64, "clips": clips},
            {"id": "300", "report_sha256": "b" * 64, "clips": []},
        ]
    }


def test_catalog_preserves_source_order_and_viewer_clip_index():
    matches = notebook.build_catalog(reports(), 8123)["matches"]
    first, empty = matches
    assert first["id"] == "200" and first["report_sha256"] == "a" * 64
    assert empty == {"id": "300", "report_sha256": "b" * 64, "clips": []}
    assert [c["hero"] for c in first["clips"]] == ["甲", "乙</ScRiPt>"]
    for index, clip in enumerate(first["clips"]):
        assert set(clip) == {"hero", "domain", "time", "seconds", "url"}
        assert clip["time"] == "16:07" and clip["seconds"] == 967
        link = urlsplit(clip["url"])
        assert (link.scheme, link.netloc, link.path) == ("http", "127.0.0.1:8123", "/")
        assert parse_qs(link.fragment) == {
            "match": ["200"],
            "i": [str(index)],
            "t": ["967"],
            "scene": ["兵线"],
        }


def test_cli_uses_local_api_and_publishes_a_new_complete_page(tmp_path, monkeypatch, capsys):
    template = tmp_path / "template.html"
    start, end = '<script type="application/json">', "</script>"
    template.write_text(start + notebook.PLACEHOLDER + end, encoding="utf-8")
    monkeypatch.setattr(notebook, "TEMPLATE", template)
    output = tmp_path / "subdir" / "trial.html"
    args = ["--port", "8123", "--output", str(output)]
    with patch.object(notebook.http.client, "HTTPConnection") as connect:
        response = connect.return_value.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps(reports()).encode("utf-8")
        notebook.main(args)
        connect.assert_called_once_with("127.0.0.1", 8123, timeout=10)
        connect.return_value.request.assert_called_once_with("GET", "/api/reports")
        assert capsys.readouterr().out.strip() == output.as_uri()
        page = output.read_text(encoding="utf-8")
        assert page.lower().count("</script>") == 1
        assert json.loads(page.removeprefix(start).removesuffix(end)) == notebook.build_catalog(
            reports(), 8123
        )
        output.write_text("已保留的内容", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            notebook.main(args)
        assert exc.value.code == 1
        assert output.read_text(encoding="utf-8") == "已保留的内容"
        assert list(output.parent.iterdir()) == [output]


def test_redirect_is_rejected_without_contacting_another_url():
    with patch.object(notebook.http.client, "HTTPConnection") as connect:
        response = connect.return_value.getresponse.return_value
        response.status = 302
        with pytest.raises(ValueError, match="HTTP 302"):
            notebook.read_reports(8796)
        assert connect.call_count == 1
        response.read.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [("id", "non-numeric"), ("report_sha256", ""), ("clips", None)],
)
def test_invalid_report_identity_is_rejected(field, value):
    raw = reports()
    raw["matches"][0][field] = value
    with pytest.raises(ValueError, match="工作台"):
        notebook.build_catalog(raw, 8796)


def test_rejects_duplicate_identity_and_invalid_game_time():
    raw = reports()
    raw["matches"][1]["id"] = raw["matches"][0]["id"]
    with pytest.raises(ValueError):
        notebook.build_catalog(raw, 8796)
    raw = reports()
    clips = raw["matches"][0]["clips"]
    clips.append(clips[0])
    with pytest.raises(ValueError, match="重复片段"):
        notebook.build_catalog(raw, 8796)
    clips[0]["time"] = "16:67"
    with pytest.raises(ValueError, match="游戏时刻"):
        notebook.build_catalog(raw, 8796)
