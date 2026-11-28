"""Bounded HTTP stages reject partial identities and keep failed attempts inspectable."""

import hashlib
import json

import httpx
import pytest

from dota_items.sources import replay_collection_io as io
from dota_items.sources.opendota_budget import BudgetPaused, RequestBudget

URL = "https://replay112.valve.net/570/match.dem.bz2"
MIB = 1024**2


class Stream(httpx.SyncByteStream):
    def __init__(self, iterator):
        self.iterator = iterator

    def __iter__(self):
        return iter(self.iterator())


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)


@pytest.mark.parametrize(
    "url",
    [
        URL,
        "http://replay112.valve.net:80/570/match",
        "https://replay.example.steamcontent.com:443/match",
        "https://replay.dota2.com.cn/match",
        "https://replay.valveusercontent.com/match",
    ],
)
def test_only_public_replay_subdomains_are_allowed(url):
    assert io.replay_url_allowed(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://valve.net/match",
        "https://evilvalve.net/match",
        "https://replay.valve.net.evil.invalid/match",
        "https://user:secret@replay112.valve.net/match",
        "https://replay112.valve.net:8000/match",
        "https://replay112.valve.net:99999/match",
        "file:///tmp/match.dem",
        "ftp://replay112.valve.net/match",
        "http://127.0.0.1/match",
        "//replay112.valve.net/match",
        None,
    ],
)
def test_url_tricks_and_credentials_are_rejected(url):
    assert not io.replay_url_allowed(url)


def test_discovery_filters_the_end_before_spending_metadata_requests():
    query = io.discovery_sql(
        {"start_lower": 10000, "start_upper": 20000, "end_upper": 21000},
        9_100_000_001,
        heroes=(1, 5),
        limit=8,
    )
    assert "start_time>=10000" in query
    assert "start_time<20000" in query
    assert "start_time+duration<21000" in query
    assert "match_id<9100000001" in query
    assert "lobby_type=7 AND game_mode=22" in query
    assert "(1=ANY(radiant_team) OR 1=ANY(dire_team) OR 5=ANY(radiant_team)" in query
    assert query.endswith("ORDER BY match_id DESC LIMIT 8")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cursor": "1; DROP TABLE public_matches"},
        {"cursor": True},
        {"heroes": ["1) OR TRUE --"]},
        {"heroes": [True]},
        {"min_rank": "70 OR TRUE"},
        {"limit": 101},
        {"limit": 0},
        {"min_duration": -1},
    ],
)
def test_sql_interpolation_has_no_unvalidated_string_path(kwargs):
    arguments = {"cursor": 9_100_000_001, **kwargs}
    with pytest.raises(ValueError):
        io.discovery_sql(
            {"start_lower": 10000, "start_upper": 20000, "end_upper": 21000}, **arguments
        )


def test_budget_hooks_cover_failures_and_do_not_follow_redirects(tmp_path, monkeypatch):
    requests = []

    def response(request):
        requests.append(str(request.url))
        return httpx.Response(429, headers={"Retry-After": "60"}, content=b"busy")

    original = httpx.Client
    options_seen = []

    def isolated_client(**options):
        options_seen.append(options)
        return original(transport=httpx.MockTransport(response), **options)

    monkeypatch.setattr(io.httpx, "Client", isolated_client)
    monkeypatch.setenv("HTTP_PROXY", "http://invalid.invalid:1")
    budget = RequestBudget(tmp_path / "budget.json", clock=lambda: 100000, sleep=lambda _: None)
    api, public = io.clients(budget)
    try:
        with pytest.raises(BudgetPaused):
            api.get(io.API + "/matches/9100000001")
        assert len(requests) == 1
        saved = json.loads(budget.path.read_text())
        assert len(saved["requests"]) == 1
        assert saved["blocked_until"] == 186400
        with pytest.raises(BudgetPaused):
            api.get(io.API + "/matches/9100000002")
        assert len(requests) == 1
        # Valve reads neither spend OpenDota quota nor inherit its cooldown hook.
        assert public.get(URL).status_code == 429
        assert len(json.loads(budget.path.read_text())["requests"]) == 1
        assert all(option["trust_env"] is False for option in options_seen)
        assert all(option["follow_redirects"] is False for option in options_seen)
    finally:
        api.close()
        public.close()


def test_complete_download_has_content_digest_and_no_partial_file(tmp_path):
    payload = b"\x28\xb5\x2f\xfd" + bytes(range(256)) * 8
    target = tmp_path / "new" / "match.dem.bz2"
    with client_for(
        lambda _: httpx.Response(200, headers={"ETag": '"one"'}, content=payload)
    ) as client:
        result = io.download(client, URL, target, max_bytes=len(payload))
    assert target.read_bytes() == payload
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["size_bytes"] == len(payload)
    assert result["etag"] == '"one"'
    assert not target.with_name(target.name + ".partial").exists()


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_download_budget_rejects_before_network(tmp_path, limit):
    calls = []
    with client_for(lambda request: calls.append(request)) as client:
        with pytest.raises(ValueError):
            io.download(client, URL, tmp_path / "match.dem", max_bytes=limit)
    assert not calls


@pytest.mark.parametrize("existing", ["complete", "partial"])
def test_existing_attempts_are_never_overwritten_or_redownloaded(tmp_path, existing):
    target = tmp_path / "match.dem"
    preserved = target if existing == "complete" else target.with_name(target.name + ".partial")
    preserved.write_bytes(b"original evidence")
    calls = []
    with client_for(lambda request: calls.append(request)) as client:
        with pytest.raises(FileExistsError):
            io.download(client, URL, target, max_bytes=1024)
    assert not calls
    assert preserved.read_bytes() == b"original evidence"


def test_oversize_download_retains_only_bounded_partial(tmp_path):
    target = tmp_path / "match.dem"

    def pieces():
        yield b"a" * MIB
        yield b"overflow"

    with client_for(lambda _: httpx.Response(200, stream=Stream(pieces))) as client:
        with pytest.raises(ValueError, match="byte budget"):
            io.download(client, URL, target, max_bytes=MIB)
    assert not target.exists()
    assert target.with_name(target.name + ".partial").read_bytes() == b"a" * MIB


def test_network_interruption_preserves_evidence_without_publishing_success(tmp_path):
    target = tmp_path / "match.dem"

    def pieces():
        yield b"a" * MIB
        raise httpx.ReadError("injected connection interruption")

    with client_for(lambda _: httpx.Response(200, stream=Stream(pieces))) as client:
        with pytest.raises(httpx.ReadError):
            io.download(client, URL, target, max_bytes=2 * MIB)
    assert not target.exists()
    assert target.with_name(target.name + ".partial").stat().st_size == MIB


def test_wall_budget_expiry_during_stream_preserves_partial(tmp_path, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(io.time, "monotonic", lambda: clock[0])
    target = tmp_path / "match.dem"

    def pieces():
        yield b"a" * MIB
        clock[0] = 12.0
        yield b"b"

    with client_for(lambda _: httpx.Response(200, stream=Stream(pieces))) as client:
        with pytest.raises(TimeoutError):
            io.download(client, URL, target, max_bytes=2 * MIB, deadline=11)
    assert not target.exists()
    assert target.with_name(target.name + ".partial").stat().st_size == MIB


def test_expired_wall_budget_sends_no_request(tmp_path, monkeypatch):
    monkeypatch.setattr(io.time, "monotonic", lambda: 11)
    calls = []
    with client_for(lambda request: calls.append(request)) as client:
        with pytest.raises(TimeoutError):
            io.download(client, URL, tmp_path / "match.dem", max_bytes=10, deadline=10)
    assert not calls


@pytest.mark.parametrize(
    "status,headers,payload",
    [
        (206, {"Content-Range": "bytes 0-3/16"}, b"part"),
        (200, {"Content-Range": "bytes 0-3/16"}, b"part"),
        (200, {"Content-Length": "99"}, b"short"),
        (200, {"Content-Length": "2"}, b"longer"),
        (200, {}, b""),
    ],
)
def test_partial_or_length_inconsistent_response_is_not_a_complete_demo(
    tmp_path, status, headers, payload
):
    target = tmp_path / "match.dem"
    with client_for(lambda _: httpx.Response(status, headers=headers, content=payload)) as client:
        with pytest.raises((ValueError, httpx.HTTPStatusError)):
            io.download(client, URL, target, max_bytes=1024)
    assert not target.exists()


def test_redirect_is_not_followed_to_an_unapproved_host(tmp_path):
    calls = []

    def response(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://unapproved.invalid/match"})

    target = tmp_path / "match.dem"
    with client_for(response) as client:
        with pytest.raises(httpx.HTTPStatusError):
            io.download(client, URL, target, max_bytes=1024)
    assert calls == [URL]
    assert not target.exists()


def test_download_disables_redirects_even_if_the_injected_client_follows_them(tmp_path):
    calls = []

    def response(request):
        calls.append(str(request.url))
        if request.url.host == "replay112.valve.net":
            return httpx.Response(302, headers={"Location": "https://unapproved.invalid/match"})
        return httpx.Response(200, content=b"unapproved body")

    with httpx.Client(transport=httpx.MockTransport(response), follow_redirects=True) as client:
        with pytest.raises(httpx.HTTPStatusError):
            io.download(client, URL, tmp_path / "match.dem", max_bytes=1024)
    assert calls == [URL]
    assert not (tmp_path / "match.dem").exists()


@pytest.mark.parametrize(
    "headers", [{"Content-Length": "-1"}, {"Content-Length": "999"}, {"Content-Encoding": "br"}]
)
def test_transport_encoding_and_invalid_or_oversize_length_are_not_silently_reinterpreted(
    tmp_path, headers
):
    calls = []

    def response(request):
        calls.append(request.headers["Accept-Encoding"])
        return httpx.Response(200, headers=headers, stream=Stream(lambda: iter([b"body"])))

    with client_for(response) as client:
        with pytest.raises(ValueError):
            io.download(client, URL, tmp_path / "match.dem", max_bytes=100)
    assert calls == ["identity"]
    assert not (tmp_path / "match.dem").exists()


def test_atomic_publication_cannot_clobber_a_racing_writer(tmp_path, monkeypatch):
    target = tmp_path / "match.dem"
    original_link = io.os.link

    def race(source, destination):
        target.write_bytes(b"other writer's evidence")
        return original_link(source, destination)

    monkeypatch.setattr(io.os, "link", race)
    with client_for(lambda _: httpx.Response(200, content=b"this attempt")) as client:
        with pytest.raises(FileExistsError):
            io.download(client, URL, target, max_bytes=1024)
    assert target.read_bytes() == b"other writer's evidence"
    assert target.with_name(target.name + ".partial").read_bytes() == b"this attempt"


def test_json_source_bounds_and_explorer_error_are_enforced():
    payload = b'{"rows":[{"match_id":9100000001}]}'
    with client_for(lambda _: httpx.Response(200, content=payload)) as client:
        raw, rows = io.explorer(client, "SELECT match_id FROM public_matches LIMIT 1")
        assert raw == payload and rows == [{"match_id": 9100000001}]
        with pytest.raises(ValueError, match="byte budget"):
            io.get_json(client, io.API + "/explorer", max_bytes=5)
    with client_for(lambda _: httpx.Response(200, json={"err": "timeout", "rows": []})) as client:
        with pytest.raises(ValueError, match="discovery response"):
            io.explorer(client, "SELECT 1")
