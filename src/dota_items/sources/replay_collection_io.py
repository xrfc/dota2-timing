"""Bounded network reads for the explicit-version collector; no data/workflow imports."""

import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

REPLAY_HOSTS = ("valve.net", "dota2.com.cn", "steamcontent.com", "valveusercontent.com")
API = "https://api.opendota.com/api"


def replay_url_allowed(url):
    try:
        parts = urlsplit(url)
        return (
            parts.scheme in ("https", "http")
            and not parts.username
            and not parts.password
            and parts.port in (None, 80, 443)
            and any((parts.hostname or "").endswith("." + host) for host in REPLAY_HOSTS)
        )
    except (ValueError, TypeError):
        return False


def clients(budget, *, proxy=None):
    options = {"trust_env": False, "follow_redirects": False, "proxy": proxy, "timeout": 60}
    return (
        httpx.Client(
            **options, event_hooks={"request": [budget.before], "response": [budget.after]}
        ),
        httpx.Client(**options),
    )


def remaining(deadline):
    seconds = deadline - time.monotonic() if deadline is not None else 60
    if seconds <= 0:
        raise TimeoutError("Collection wall-clock budget exhausted")
    return min(seconds, 60)


def get_json(client, url, *, params=None, max_bytes=64 * 1024**2, deadline=None):
    chunks, total = [], 0
    with client.stream("GET", url, params=params, timeout=remaining(deadline)) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes(1024**2):
            remaining(deadline)
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("Source JSON exceeds byte budget")
            chunks.append(chunk)
    raw = b"".join(chunks)
    return raw, json.loads(raw)


def discovery_sql(bounds, cursor, *, min_duration=900, min_rank=70, heroes=(), limit=100):
    values = [cursor, min_duration, min_rank, limit, *bounds.values(), *heroes]
    if any(type(value) is not int or value < 0 for value in values) or not 1 <= limit <= 100:
        raise ValueError("Discovery parameters must be bounded positive integers")
    filters = [
        f"match_id>{max(0, cursor - 1_000_000)}",
        f"match_id<{cursor}",
        f"start_time>={bounds['start_lower']}",
        f"start_time<{bounds['start_upper']}",
        f"start_time+duration<{bounds['end_upper']}",
        f"duration>={min_duration}",
        "lobby_type=7",
        "game_mode=22",
        f"avg_rank_tier>={min_rank}",
    ]
    if heroes:
        filters.append(
            "("
            + " OR ".join(f"{hero}=ANY(radiant_team) OR {hero}=ANY(dire_team)" for hero in heroes)
            + ")"
        )
    return (
        "SELECT match_id,start_time,duration,avg_rank_tier FROM public_matches WHERE "
        + " AND ".join(filters)
        + f" ORDER BY match_id DESC LIMIT {limit}"
    )


def explorer(client, query, *, deadline=None):
    raw, payload = get_json(client, API + "/explorer", params={"sql": query}, deadline=deadline)
    if (
        not isinstance(payload, dict)
        or payload.get("err")
        or not isinstance(payload.get("rows"), list)
    ):
        raise ValueError("Invalid discovery response")
    return raw, payload["rows"]


def download(client, url, target: Path, *, max_bytes, deadline=None):
    """Publish only complete bounded downloads; retain incomplete attempts for diagnosis.

    No blind Range append: a retry uses a different attempt filename. Completed
    downloads are reused by the workflow only after digest verification.
    """
    if not replay_url_allowed(url):
        raise ValueError("Replay URL is not an approved public CDN address")
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("Download byte budget exhausted")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    if target.exists() or partial.exists():
        raise FileExistsError("Download attempt already exists")
    checksum, size = hashlib.sha256(), 0
    with client.stream(
        "GET",
        url,
        timeout=remaining(deadline),
        headers={"Accept-Encoding": "identity"},
        follow_redirects=False,
    ) as response:
        response.raise_for_status()
        if response.status_code != 200 or response.headers.get("content-range"):
            raise ValueError("A complete HTTP 200 replay response is required")
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise ValueError("Unexpected HTTP content encoding")
        length = response.headers.get("content-length")
        if length is not None and (not length.isdecimal() or int(length) > max_bytes):
            raise ValueError("Invalid or oversized replay Content-Length")
        with partial.open("xb") as stream:
            for chunk in response.iter_bytes(1024**2):
                remaining(deadline)
                if size + len(chunk) > max_bytes:
                    raise ValueError("Replay exceeds download byte budget")
                stream.write(chunk)
                checksum.update(chunk)
                size += len(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        if not size:
            raise ValueError("Replay download is empty")
        if length is not None and size != int(length):
            raise ValueError("Replay Content-Length mismatch")
        os.link(partial, target)
        partial.unlink()
        return {
            "path": str(target.resolve()),
            "sha256": checksum.hexdigest(),
            "size_bytes": size,
            "etag": response.headers.get("etag"),
        }
