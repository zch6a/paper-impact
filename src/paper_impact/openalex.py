"""OpenAlex, as far as the site needs it: title searches (to match proceedings titles), works by ID (to refresh their
numbers), and the proceedings pages themselves. The key, from ``OPENALEX_API_KEY``, goes in a header to OpenAlex only,
never in a URL; the User-Agent names the tool, not the user; waits and retries when told to."""

from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from . import __version__

API = "https://api.openalex.org"
USER_AGENT = f"paper-impact/{__version__} (+https://github.com/zch6a/paper-impact)"
FIELDS = "id,title,publication_year,cited_by_count,fwci,citation_normalized_percentile,counts_by_year,doi"
Getter = Callable[[str, dict[str, str]], tuple[int, dict[str, str], bytes]]


class OpenAlexError(Exception):
    pass


class BudgetExhausted(OpenAlexError):
    """OpenAlex's daily budget is spent (a 429 with a long wait, or one that does not lift): stop asking until tomorrow."""


def _urlopen(url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
    """GET: (status, lower-case headers, body); a network failure is status 0, retried like a 5xx."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:  # noqa: S310 - the API's URL
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read() or b""
    except (OSError, http.client.HTTPException) as e:
        return 0, {}, str(e).encode()


class Client:
    def __init__(self, key: str | None = None, get: Getter | None = None, sleep: Callable[[float], None] = time.sleep, pause: float = 0.12) -> None:
        self.key = key if key is not None else os.environ.get("OPENALEX_API_KEY", "")
        self._get = get or _urlopen
        self._sleep = sleep
        self._pause = pause  # between requests: under 10 a second, OpenAlex's keyless limit
        self.calls = 0
        self.exhausted = False  # the daily budget ran out during this run

    def get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = API + path + "?" + urllib.parse.urlencode(params)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        status = 0
        if self.exhausted:
            raise BudgetExhausted("OpenAlex's daily budget is spent")
        for attempt in range(5):
            if self.calls:
                self._sleep(self._pause)
            self.calls += 1
            status, response_headers, body = self._get(url, headers)
            if status in (0, 429) or status >= 500:
                wait = response_headers.get("retry-after", "")
                seconds = float(wait) if wait.replace(".", "", 1).isdigit() else 2.0**attempt
                if status == 429 and seconds > 60:  # told to come back in hours: the day's budget is gone
                    self.exhausted = True
                    raise BudgetExhausted(f"OpenAlex's daily budget is spent (come back in {seconds / 3600:.1f} hours)")
                self._sleep(min(60.0, seconds))
                continue
            if status != 200:
                raise OpenAlexError(f"OpenAlex answered {status} for {url}: {body[:200].decode('utf-8', 'replace')}")
            try:
                data = json.loads(body)
            except ValueError as e:
                raise OpenAlexError(f"OpenAlex's answer for {url} is not JSON ({e})") from e
            if not isinstance(data, dict):
                raise OpenAlexError(f"OpenAlex's answer for {url} is not a list of results")
            return data
        if status == 429:
            self.exhausted = True
            raise BudgetExhausted("OpenAlex kept answering 429: the daily budget is spent")
        what = "could not be reached" if status == 0 else f"kept answering {status}"
        raise OpenAlexError(f"OpenAlex {what} for {url}; try later, or set OPENALEX_API_KEY")

    def search(self, params: dict[str, str]) -> dict[str, Any]:
        """One works search (a title match)."""
        return self.get("/works", params)

    def by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        """Works by OpenAlex ID, 100 to a list call (refreshing the numbers of works matched before)."""
        out: list[dict[str, Any]] = []
        shorts = [i.rstrip("/").rsplit("/", 1)[-1] for i in ids]
        for k in range(0, len(shorts), 100):
            group = shorts[k : k + 100]
            data = self.get("/works", {"filter": "openalex:" + "|".join(group), "per_page": "100", "select": FIELDS})
            out += [w for w in data.get("results") or [] if isinstance(w, dict)]
        return out

    def page(self, url: str) -> str:
        """A proceedings page (another site: no key is sent there)."""
        if not url.startswith("https://"):
            raise OpenAlexError(f"{url}: proceedings pages are fetched over https only")
        for attempt in range(4):
            if self.calls:
                self._sleep(1.0)  # a person's pace on someone else's site
            self.calls += 1
            status, _, body = self._get(url, {"User-Agent": USER_AGENT, "Accept": "text/html"})
            if status == 200:
                return body.decode("utf-8", "replace")
            if status in (0, 429) or status >= 500:
                self._sleep(2.0**attempt)
                continue
            raise OpenAlexError(f"{url} answered {status}")
        raise OpenAlexError(f"{url} could not be read; try later")
