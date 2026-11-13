"""OpenAlex, as far as the site needs it: a venue-year's works (the first page of the most cited without a key; every
page with one), and a search for a venue's source IDs. The key, from ``OPENALEX_API_KEY``, goes in a header, never a
URL; the User-Agent names the tool, not the user; waits and retries when told to."""

from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

from . import __version__

API = "https://api.openalex.org"
USER_AGENT = f"paper-impact/{__version__} (+https://github.com/zch6a/paper-impact)"
FIELDS = "id,title,publication_year,cited_by_count,fwci,citation_normalized_percentile,counts_by_year,doi"
Getter = Callable[[str, dict[str, str]], tuple[int, dict[str, str], bytes]]


class OpenAlexError(Exception):
    pass


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

    def get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = API + path + "?" + urllib.parse.urlencode(params)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        status = 0
        for attempt in range(5):
            if self.calls:
                self._sleep(self._pause)
            self.calls += 1
            status, response_headers, body = self._get(url, headers)
            if status in (0, 429) or status >= 500:
                wait = response_headers.get("retry-after", "")
                self._sleep(min(60.0, float(wait)) if wait.replace(".", "", 1).isdigit() else 2.0**attempt)
                continue
            if status == 401 and "cursor" in params:
                raise OpenAlexError("OpenAlex needs a (free) API key to page past the first page: set OPENALEX_API_KEY, or use --top")
            if status != 200:
                raise OpenAlexError(f"OpenAlex answered {status} for {url}: {body[:200].decode('utf-8', 'replace')}")
            try:
                data = json.loads(body)
            except ValueError as e:
                raise OpenAlexError(f"OpenAlex's answer for {url} is not JSON ({e})") from e
            if not isinstance(data, dict):
                raise OpenAlexError(f"OpenAlex's answer for {url} is not a list of results")
            return data
        what = "could not be reached" if status == 0 else f"kept answering {status}"
        raise OpenAlexError(f"OpenAlex {what} for {url}; try later, or set OPENALEX_API_KEY")

    def works(self, sources: list[str], year: int, top: int | None) -> tuple[int, Iterator[dict[str, Any]]]:
        """(OpenAlex's count of the venue-year's works, the works, most cited first): `top` of them from the first page,
        or every one (cursor paging, which needs a key) when `top` is None."""
        ids = "|".join(s.rstrip("/").rsplit("/", 1)[-1] for s in sources)
        params = {"filter": f"primary_location.source.id:{ids},publication_year:{year}", "sort": "cited_by_count:desc",
                  "per_page": str(min(200, top) if top else 200), "select": FIELDS}  # fmt: skip
        if top is None:
            params["cursor"] = "*"
        first = self.get("/works", params)
        count = int((first.get("meta") or {}).get("count") or 0)

        def pages() -> Iterator[dict[str, Any]]:
            data = first
            while True:
                yield from (w for w in data.get("results") or [] if isinstance(w, dict))
                cursor = (data.get("meta") or {}).get("next_cursor")
                if top is not None or not cursor or not data.get("results"):
                    return
                data = self.get("/works", {**params, "cursor": cursor})

        return count, pages()

    def sources(self, name: str) -> list[dict[str, Any]]:
        data = self.get("/sources", {"search": name, "per_page": "10", "select": "id,display_name,type,works_count,host_organization_name"})
        return [s for s in data.get("results") or [] if isinstance(s, dict)]
