"""Exercise the friend review service through a local HTTP client and temporary reports."""

import http.client
import importlib.util
import json
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
def listening(service):
    module, root, db = service
    server = module.make_server(root, db)
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
