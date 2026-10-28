"""Conservative persistent budget shared by discovery and detail HTTP requests."""

import time
from pathlib import Path

from dota_items.storage import json_bytes, read_json


class BudgetPaused(RuntimeError):
    """Stop the collector without marking a match as invalid."""


class RequestBudget:
    def __init__(self, path: Path, *, clock=time.time, sleep=time.sleep):
        self.path, self.clock, self.sleep = path, clock, sleep
        self.state = read_json(path) if path.exists() else {"requests": [], "blocked_until": 0}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_bytes(json_bytes(self.state))
        temp.replace(self.path)

    def before(self, request):
        if request.url.host != "api.opendota.com":
            return
        now = self.clock()
        if now < self.state.get("blocked_until", 0):
            raise BudgetPaused("OpenDota cooldown active; no HTTP request sent")
        recent = [t for t in self.state["requests"] if t > now - 86400]
        # Below both legacy 2,000/day and current source default 3,000/day.
        if len(recent) >= 1900:
            self.state.update(requests=recent, blocked_until=recent[0] + 86400)
            self.save()
            raise BudgetPaused("Local rolling 24-hour budget exhausted; no HTTP request sent")
        if recent:
            self.sleep(max(0, recent[-1] + 1.5 - now))
        recent.append(self.clock())  # Reserve before sending; failed requests count too.
        self.state["requests"] = recent
        self.save()

    def after(self, response):
        if response.request.url.host != "api.opendota.com":
            return
        headers = response.headers
        remaining = {}
        for name in ("day", "minute"):
            try:
                remaining[name] = int(headers[f"X-Rate-Limit-Remaining-{name}"])
            except (KeyError, ValueError):
                pass
        self.state["remaining"] = remaining
        self.state["last_status"] = response.status_code
        delay = 0
        if response.status_code == 429 or remaining.get("day", 100) <= 20:
            # Unknown reset timezone / shared IP: use conservative 24-hour cooldown.
            delay = 86400
            try:
                delay = max(delay, float(headers.get("Retry-After", "0")))
            except ValueError:
                from email.utils import parsedate_to_datetime

                try:
                    delay = max(
                        delay,
                        parsedate_to_datetime(headers["Retry-After"]).timestamp() - self.clock(),
                    )
                except (ValueError, TypeError, KeyError, OverflowError):
                    pass
        elif remaining.get("minute", 100) <= 5:
            delay = 65
        if delay:
            self.state["blocked_until"] = self.clock() + delay
        self.save()
        if response.status_code == 429:
            raise BudgetPaused("OpenDota returned 429; cooldown saved, automatic retries disabled")
