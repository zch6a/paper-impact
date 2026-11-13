"""Paper lists from the venues' own proceedings pages: what a venue published is what its proceedings list, and the
page is the source of that count. Parsed with the standard library's HTML parser; titles only, with the link to each
paper's page (no abstracts, no PDFs).

- ``neurips``: papers.nips.cc's page for a year: ``<a title="paper title" href=...>Title</a>`` in the paper list.
- ``pmlr``: a Proceedings of Machine Learning Research volume (ICML and others): ``<div class="paper"><p class="title">``
  with the abstract page as the first link of ``<p class="links">``.
"""

from __future__ import annotations

import html
import urllib.parse
from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True)
class Listed:
    title: str
    url: str  # the paper's page in the proceedings


class _Parser(HTMLParser):
    def __init__(self, base: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base = base
        self.out: list[Listed] = []


class _Neurips(_Parser):
    def __init__(self, base: str) -> None:
        super().__init__(base)
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "a" and a.get("title") == "paper title" and a.get("href"):
            self._href, self._text = a["href"], []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            title = " ".join("".join(self._text).split())
            if title:
                self.out.append(Listed(title, urllib.parse.urljoin(self.base, self._href)))
            self._href = None


class _Pmlr(_Parser):
    def __init__(self, base: str) -> None:
        super().__init__(base)
        self._in_paper = self._in_title = self._in_links = False
        self._title: list[str] = []
        self._url = ""
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if tag == "div" and "paper" in classes:
            self._in_paper, self._title, self._url, self._depth = True, [], "", 0
        elif self._in_paper:
            if tag == "div":
                self._depth += 1
            elif tag == "p" and "title" in classes:
                self._in_title = True
            elif tag == "p" and "links" in classes:
                self._in_links = True
            elif tag == "a" and self._in_links and not self._url:
                self._url = urllib.parse.urljoin(self.base, dict(attrs).get("href") or "")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._in_paper:
            return
        if tag == "p":
            self._in_title = self._in_links = False
        elif tag == "div":
            if self._depth:
                self._depth -= 1
                return
            title = " ".join("".join(self._title).split())
            if title:
                self.out.append(Listed(title, self._url))
            self._in_paper = False


PARSERS: dict[str, type[_Parser]] = {"neurips": _Neurips, "pmlr": _Pmlr}


def parse(kind: str, page: str, base: str) -> list[Listed]:
    """The papers a proceedings page lists, in its order, each once.

    >>> parse("neurips", '<ul class="paper-list"><li><a title="paper title" href="/p/1-Abstract.html">A  Study &amp; More</a></li></ul>',
    ...       "https://papers.nips.cc/paper_files/paper/2017")
    [Listed(title='A Study & More', url='https://papers.nips.cc/p/1-Abstract.html')]
    """
    if kind not in PARSERS:
        raise ValueError(f"no parser for {kind!r}; the parsers are {', '.join(PARSERS)}")
    parser = PARSERS[kind](base)
    parser.feed(page)
    parser.close()
    seen: set[str] = set()
    out = []
    for item in parser.out:
        key = html.unescape(item.title).casefold()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
