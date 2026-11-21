"""Serve an invite-only replay review portal behind a same-origin HTTPS reverse proxy."""

import argparse
import hashlib
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

MODES = ("lane", "jungle", "wave")
WEEK = 7 * 86400
COOKIE = "friend_review"
BODY_LIMIT = 16 * 1024
LOGIN = """<!doctype html><html lang="zh-CN"><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>录像复盘</title><h1>录像复盘</h1><form method=post action="/login">
<label>邀请码 <input name=code type=password required maxlength=128></label>
<button>进入复盘</button></form></html>"""
HOME = """<!doctype html><html lang="zh-CN"><meta charset=utf-8><title>选择复盘</title>
<h1>选择复盘</h1><p><a href="/lane/">带线</a> · <a href="/jungle/">打野</a> ·
<a href="/wave/">补刀前的兵线取舍</a></p></html>"""


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def initialize(db):
    db.parent.mkdir(parents=True, exist_ok=True)
    os.close(os.open(db, os.O_CREAT | os.O_RDWR, 0o600))
    with closing(sqlite3.connect(db)) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS invites (
            digest TEXT PRIMARY KEY, reviewer TEXT UNIQUE NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
            digest TEXT PRIMARY KEY, reviewer TEXT NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS reviews (
            reviewer TEXT NOT NULL, case_id TEXT NOT NULL, choice TEXT, first TEXT,
            previewed INTEGER NOT NULL, note TEXT NOT NULL, PRIMARY KEY(reviewer,case_id));
        CREATE TABLE IF NOT EXISTS failures (at INTEGER NOT NULL);
        """)


def issue(db):
    initialize(db)
    code = secrets.token_urlsafe(24)
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(
            "INSERT INTO invites VALUES (?,?,?)",
            (digest(code), secrets.token_hex(12), int(time.time()) + WEEK),
        )
    return code


def catalogue(root):
    assets, cases = {}, {}
    for mode in MODES:
        folder = (root / f"action-comparison-{mode}-001").resolve()
        base = f"/{mode}/"
        files = ["index.html", "map.jpg", "app.js", "style.css", "cases.json"]
        for case in json.loads((folder / "cases.json").read_text(encoding="utf-8"))["cases"]:
            key = case["id"]
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", key) or key in cases:
                raise ValueError("invalid or duplicate case id")
            cases[key] = mode
            files += [f"actions/{key}.json", f"outcomes/{key}.json"]
        for name in files:
            path = folder / name
            if path.resolve().parent not in (folder, folder / "actions", folder / "outcomes"):
                raise ValueError("report asset outside expected directory")
            assets[base + name] = path
        assets[base] = assets[base + "index.html"]
    return assets, cases


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Do not log paths, headers or submitted invite codes.
        pass

    def respond(self, status, data=b"", kind="application/json", headers=()):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'; "
            "form-action 'self'; base-uri 'none'",
        )
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def json(self, payload):
        self.respond(200, json.dumps(payload, ensure_ascii=False).encode())

    def session(self, conn):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        if COOKIE not in cookies:
            return None
        row = conn.execute(
            "SELECT reviewer FROM sessions WHERE digest=? AND expires>?",
            (digest(cookies[COOKIE].value), int(time.time())),
        ).fetchone()
        return row[0] if row else None

    def do_GET(self):
        path = self.path.partition("?")[0]
        with closing(sqlite3.connect(self.server.db)) as conn:
            reviewer = self.session(conn)
            if path == "/":
                return self.respond(
                    200, (HOME if reviewer else LOGIN).encode(), "text/html; charset=utf-8"
                )
            if reviewer is None:
                return self.respond(401)
            if path == "/reviews":
                rows = conn.execute(
                    "SELECT case_id,choice,first,previewed,note FROM reviews "
                    "WHERE reviewer=? ORDER BY case_id",
                    (reviewer,),
                )
                return self.json(
                    {
                        "reviewer": reviewer,
                        "reviews": [
                            dict(case_id=k, choice=c, first=f, previewed=bool(p), note=n)
                            for k, c, f, p, n in rows
                        ],
                    }
                )
        asset = self.server.assets.get(path)
        if asset is None or not asset.is_file():
            return self.respond(404)
        self.respond(
            200,
            asset.read_bytes(),
            mimetypes.guess_type(asset.name)[0] or "application/octet-stream",
        )

    def do_POST(self):
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin", "")
        if origin not in ("https://" + host, "http://" + host) or not host:
            return self.respond(403)
        local = urlsplit(origin).hostname in ("localhost", "127.0.0.1", "::1")
        if not local and not origin.startswith("https://"):
            return self.respond(403)
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            return self.respond(400)
        if not 0 <= length <= BODY_LIMIT or self.headers.get("Transfer-Encoding"):
            return self.respond(413)
        body = self.rfile.read(length)
        with closing(sqlite3.connect(self.server.db)) as conn, conn:
            if self.path == "/login":
                if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                    return self.respond(415)
                return self.login(conn, body, origin.startswith("https://"))
            if self.path != "/reviews":
                return self.respond(404)
            reviewer = self.session(conn)
            if not reviewer:
                return self.respond(401)
            if self.headers.get("X-Review-Reviewer") != reviewer:
                return self.respond(409)
            if self.headers.get_content_type() != "application/json":
                return self.respond(415)
            try:
                record = json.loads(body)
            except (ValueError, UnicodeError, RecursionError):
                return self.respond(400)
            self.review(conn, reviewer, record)

    def login(self, conn, body, secure):
        try:
            code = parse_qs(body.decode(), max_num_fields=4).get("code", [""])[0]
        except ValueError:
            return self.respond(400)
        now = int(time.time())
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM failures WHERE at<=?", (now - 60,))
        if conn.execute("SELECT COUNT(*) FROM failures").fetchone()[0] >= 20:
            return self.respond(HTTPStatus.TOO_MANY_REQUESTS)
        row = conn.execute(
            "SELECT reviewer,expires FROM invites WHERE digest=? AND expires>?", (digest(code), now)
        ).fetchone()
        if not row:
            conn.execute("INSERT INTO failures VALUES (?)", (now,))
            return self.respond(403)
        token = secrets.token_urlsafe(32)
        conn.execute("DELETE FROM sessions WHERE expires<=?", (now,))
        conn.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(token), *row))
        conn.commit()
        flags = f"Path=/; HttpOnly; SameSite=Strict; Max-Age={row[1] - now}"
        if secure:
            flags += "; Secure"
        self.respond(303, headers=(("Location", "/"), ("Set-Cookie", f"{COOKIE}={token}; {flags}")))

    def review(self, conn, reviewer, row):
        if not isinstance(row, dict) or not isinstance(row.get("case_id"), str):
            return self.respond(400)
        key = row["case_id"]
        if key not in self.server.cases:
            return self.respond(400)
        options = ["farm", "unknown", None]
        options += ["rotate", "support"] if self.server.cases[key] == "jungle" else ["retreat"]
        choice, first = row.get("choice"), row.get("first")
        previewed, note = row.get("previewed", False), row.get("note", "")
        if (
            choice not in options
            or first not in options
            or not isinstance(previewed, bool)
            or not isinstance(note, str)
            or len(note) > 2500
            or (first is not None and not choice)
        ):
            return self.respond(400)
        try:
            note.encode("utf-8")
        except UnicodeError:
            return self.respond(400)
        conn.execute(
            """
        INSERT INTO reviews VALUES (?,?,?,?,?,?)
        ON CONFLICT(reviewer,case_id) DO UPDATE SET choice=excluded.choice,
        first=coalesce(reviews.first,excluded.first),
        previewed=CASE WHEN reviews.first IS NULL THEN max(reviews.previewed,excluded.previewed)
                       ELSE reviews.previewed END, note=excluded.note
        """,
            (reviewer, key, choice, first or choice, previewed, note),
        )
        conn.commit()
        self.json({"ok": True})


def make_server(root, db, port=0):
    initialize(db)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.assets, server.cases = catalogue(root)
    server.db = db
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--root", default=Path("reports"), type=Path)
    parser.add_argument("--port", default=8796, type=int)
    parser.add_argument("command", choices=("serve", "issue", "export"), default="serve", nargs="?")
    args = parser.parse_args()
    if args.command == "issue":
        print(issue(args.db))
    elif args.command == "export":
        with closing(sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM reviews ORDER BY reviewer,case_id")
            print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
    else:
        with make_server(args.root, args.db, args.port) as server:
            server.serve_forever()


if __name__ == "__main__":
    main()
