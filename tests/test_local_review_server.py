"""Exercise the friend review service through a local HTTP client and temporary reports."""

import http.client
import importlib.util
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest


@pytest.fixture
def service(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/local_review_server.py"
    spec = importlib.util.spec_from_file_location("local_review_server", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "reports"
    for mode in ("lane", "jungle", "wave"):
        directory = root / f"action-comparison-{mode}-001"
        directory.mkdir(parents=True)
        (directory / "index.html").write_text(f"review-{mode}", encoding="utf-8")
        (directory / "cases.json").write_text(
            json.dumps({"mode": mode, "cases": [{"id": f"{mode}-sample"}]}), encoding="utf-8"
        )
    db = tmp_path / "reviews.sqlite3"
    return module, root, db


@contextmanager
def listening(service, **options):
    module, root, db = service
    server = module.make_server(root, db, **options)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def request(port, path, *, method="GET", body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def test_only_local_report_assets_are_readable(service):
    with listening(service) as port:
        assert request(port, "/lane/")[2] == b"review-lane"
        assert request(port, "/reviews.sqlite3")[0] == 404
        assert request(port, "/login")[0] == 404
        for headers in ({"Host": "example.com"}, {"X-Forwarded-Host": "example.com"}):
            assert request(port, "/reviews", headers=headers)[0] == 403
        headers = {"Origin": "https://example.com"}
        assert request(port, "/reviews", method="POST", headers=headers)[0] == 403


def test_unchanged_and_revised_evidence_have_distinct_opinions(service):
    module, root, db = service
    module.initialize(db)
    doc = root / "action-comparison-lane-001" / "cases.json"
    payload = {"case_id": "lane-sample", "choice": "farm", "first": "farm", "note": ""}
    original = json.loads(doc.read_text())
    sha = module.case_sha256(original["cases"][0])

    def post(port, reviewer, body):
        headers = {
            "Origin": f"http://127.0.0.1:{port}",
            "Content-Type": "application/json",
            "X-Review-Reviewer": reviewer,
            "X-Review-Version": "1",
        }
        return request(port, "/reviews", method="POST", body=json.dumps(body), headers=headers)

    with listening(service) as port:
        reviewer = json.loads(request(port, "/reviews")[2])["reviewer"]
        auth = {"X-Review-Version": "1"}
        packet = json.loads(request(port, "/lane/cases.json", headers=auth)[2])
        assert packet["case_versions"]["lane-sample"] == sha
        assert post(port, reviewer, payload)[0] == 409
        assert post(port, reviewer, {**payload, "case_sha256": sha})[0] == 200
        original["cases"][0]["mana"] = 45
        doc.write_text(json.dumps(original))
        assert json.loads(request(port, "/lane/cases.json", headers=auth)[2]) == packet

    with listening(service) as port:
        data = json.loads(request(port, "/reviews", headers=auth)[2])
        assert data["reviews"] == [] and data["previously_seen"] == ["lane-sample"]
        assert post(port, reviewer, {**payload, "case_sha256": sha})[0] == 409
        updated = module.case_sha256(original["cases"][0])
        status, _, response = post(port, reviewer, {**payload, "case_sha256": updated})
        assert status == 200 and json.loads(response)["previewed"] is True
        result = json.loads(request(port, "/reviews", headers=auth)[2])
        assert len(result["reviews"]) == 1 and result["reviews"][0]["case_sha256"] == updated
        rows = module.read_reviews(db)
        assert {r["case_sha256"]: r["previewed"] for r in rows} == {sha: 0, updated: 1}


def test_legacy_database_and_old_clients_remain_unbound(service):
    module, _, db = service
    module.initialize(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE review_versions")
        reviewer = module.LOCAL_REVIEWER
        conn.execute(
            "INSERT INTO reviews VALUES (?,?,?,?,?,?)",
            (reviewer, "lane-sample", "farm", "farm", 0, "old"),
        )
    assert module.read_reviews(db)[0]["case_sha256"] is None
    with listening(service) as port:
        old = json.loads(request(port, "/reviews", headers={})[2])
        assert old["reviews"][0]["first"] == "farm"
        current = json.loads(request(port, "/reviews", headers={"X-Review-Version": "1"})[2])
        assert current["reviews"] == [] and current["previously_seen"] == ["lane-sample"]


def test_partial_portal_pins_only_whitelisted_cases_and_current_ui(service):
    module, root, db = service
    module.initialize(db)
    folder = root / "action-comparison-lane-001"
    doc = {"mode": "lane", "cases": [{"id": "keep"}, {"id": "omit"}, None]}
    (folder / "cases.json").write_text(json.dumps(doc))
    for relative in ["actions", "outcomes"]:
        (folder / relative).mkdir()
        for key in ["keep", "omit"]:
            (folder / relative / f"{key}.json").write_text(json.dumps({"key": key}))
    with listening(
        service, folders={"lane": folder}, current_ui=True, eligible_ids={"keep"}
    ) as port:
        auth = {}

        def get(url):
            return request(port, url, headers=auth)

        assert b"/jungle/" not in get("/")[2] and get("/jungle/")[0] == 404
        assert get("/lane/")[2] == (module.UI_DIR / "index.html").read_bytes()
        assert json.loads(get("/lane/cases.json")[2])["cases"] == [{"id": "keep"}]
        (folder / "actions/keep.json").write_text("{}")
        assert json.loads(get("/lane/actions/keep.json")[2]) == {"key": "keep"}
        assert get("/lane/actions/omit.json")[0] == get("/lane/outcomes/omit.json")[0] == 404
        assert (
            request(port, "/lane/actions/keep.json", headers={**auth, "X-Case-SHA256": "old"})[0]
            == 409
        )
