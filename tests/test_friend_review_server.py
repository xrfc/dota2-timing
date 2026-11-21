"""Exercise the friend review service through a local HTTP client and temporary reports."""

import http.client
import importlib.util
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode

import pytest


@pytest.fixture
def service(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/friend_review_server.py"
    spec = importlib.util.spec_from_file_location("friend_review_server", script)
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


def login(port, code):
    origin = f"http://127.0.0.1:{port}"
    status, headers, _ = request(
        port,
        "/login",
        method="POST",
        body=urlencode({"code": code}),
        headers={"Origin": origin, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 303
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    status, _, body = request(port, "/reviews", headers={"Cookie": cookie})
    assert status == 200
    return cookie, json.loads(body)["reviewer"]


def test_only_authenticated_report_assets_are_readable(service):
    module, root, db = service
    (root / "action-comparison-lane-001/private.txt").write_text("outside public asset set")
    code = module.issue(db)
    with listening(service) as port:
        for path in ("/lane/", "/jungle/cases.json", "/reviews"):
            assert request(port, path)[0] == 401
        assert request(port, "/")[1]["Referrer-Policy"] == "same-origin"
        cookie, _ = login(port, code)
        headers = {"Cookie": cookie}
        assert request(port, "/lane/", headers=headers)[2] == b"review-lane"
        assert request(port, "/wave/cases.json", headers=headers)[0] == 200
        for path in ("/lane/private.txt", "/lane/actions/", "/reviews.sqlite3"):
            status, _, body = request(port, path, headers=headers)
            assert status in (403, 404) and b"outside public asset set" not in body


def test_reviews_require_same_origin_and_remain_private_after_restart(service):
    module, _, db = service
    first_code = module.issue(db)
    second_code = module.issue(db)
    payload = dict(case_id="lane-sample", choice="farm", first="farm", previewed=False, note="再看")
    with listening(service) as port:
        origin = f"http://127.0.0.1:{port}"
        cookie, reviewer = login(port, first_code)
        other_cookie, other = login(port, second_code)
        assert reviewer != other
        headers = {
            "Content-Type": "application/json",
            "Cookie": cookie,
            "Origin": origin,
            "X-Review-Reviewer": reviewer,
        }

        def submit(fields, request_headers):
            return request(
                port, "/reviews", method="POST", body=json.dumps(fields), headers=request_headers
            )[0]

        assert submit(payload, {k: v for k, v in headers.items() if k != "Cookie"}) == 401
        assert submit(payload, {k: v for k, v in headers.items() if k != "Origin"}) == 403
        assert submit(payload, headers | {"Origin": "http://another.invalid"}) == 403
        assert submit(payload, headers | {"X-Review-Reviewer": other}) == 409
        assert submit(payload, headers) == 200
        assert (
            json.loads(request(port, "/reviews", headers={"Cookie": other_cookie})[2])["reviews"]
            == []
        )
    with listening(service) as port:
        status, _, body = request(port, "/reviews", headers={"Cookie": cookie})
        assert status == 200
        result = json.loads(body)
        assert result["reviewer"] == reviewer
        assert len(result["reviews"]) == 1
        assert {k: result["reviews"][0][k] for k in payload} == payload


def test_unchanged_and_revised_evidence_have_distinct_opinions(service):
    module, root, db = service
    code = module.issue(db)
    doc = root / "action-comparison-lane-001" / "cases.json"
    payload = {"case_id": "lane-sample", "choice": "farm", "first": "farm", "note": ""}
    original = json.loads(doc.read_text())
    sha = module.case_sha256(original["cases"][0])

    def post(port, cookie, reviewer, body):
        headers = {
            "Origin": f"http://127.0.0.1:{port}",
            "Cookie": cookie,
            "Content-Type": "application/json",
            "X-Review-Reviewer": reviewer,
            "X-Review-Version": "1",
        }
        return request(port, "/reviews", method="POST", body=json.dumps(body), headers=headers)

    with listening(service) as port:
        cookie, reviewer = login(port, code)
        auth = {"Cookie": cookie, "X-Review-Version": "1"}
        packet = json.loads(request(port, "/lane/cases.json", headers=auth)[2])
        assert packet["case_versions"]["lane-sample"] == sha
        assert post(port, cookie, reviewer, payload)[0] == 409
        assert post(port, cookie, reviewer, {**payload, "case_sha256": sha})[0] == 200
        original["cases"][0]["mana"] = 45
        doc.write_text(json.dumps(original))
        assert json.loads(request(port, "/lane/cases.json", headers=auth)[2]) == packet

    with listening(service) as port:
        data = json.loads(request(port, "/reviews", headers=auth)[2])
        assert data["reviews"] == [] and data["previously_seen"] == ["lane-sample"]
        assert post(port, cookie, reviewer, {**payload, "case_sha256": sha})[0] == 409
        updated = module.case_sha256(original["cases"][0])
        status, _, response = post(port, cookie, reviewer, {**payload, "case_sha256": updated})
        assert status == 200 and json.loads(response)["previewed"] is True
        result = json.loads(request(port, "/reviews", headers=auth)[2])
        assert len(result["reviews"]) == 1 and result["reviews"][0]["case_sha256"] == updated
        rows = module.read_reviews(db)
        assert {r["case_sha256"]: r["previewed"] for r in rows} == {sha: 0, updated: 1}


def test_legacy_database_and_old_clients_remain_unbound(service):
    module, _, db = service
    code = module.issue(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE review_versions")
        reviewer = conn.execute("SELECT reviewer FROM invites").fetchone()[0]
        conn.execute(
            "INSERT INTO reviews VALUES (?,?,?,?,?,?)",
            (reviewer, "lane-sample", "farm", "farm", 0, "old"),
        )
    assert module.read_reviews(db)[0]["case_sha256"] is None
    with listening(service) as port:
        cookie, _ = login(port, code)
        old = json.loads(request(port, "/reviews", headers={"Cookie": cookie})[2])
        assert old["reviews"][0]["first"] == "farm"
        current = json.loads(
            request(port, "/reviews", headers={"Cookie": cookie, "X-Review-Version": "1"})[2]
        )
        assert current["reviews"] == [] and current["previously_seen"] == ["lane-sample"]


def test_partial_portal_pins_only_whitelisted_cases_and_current_ui(service):
    module, root, db = service
    code = module.issue(db)
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
        cookie, _ = login(port, code)
        auth = {"Cookie": cookie}

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
