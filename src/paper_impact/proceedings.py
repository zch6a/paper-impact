"""Paper lists from the venues' own proceedings pages: what a venue published is what its proceedings list, and the
page is the source of that count. Parsed with the standard library's HTML parser; titles only, with the link to each
paper's page (no abstracts, no PDFs).

- ``neurips``: papers.nips.cc's page for a year: ``<a title="paper title" href=...>Title</a>`` in the paper list.
- ``pmlr``: a Proceedings of Machine Learning Research volume (ICML and others): ``<div class="paper"><p class="title">``
  with the abstract page as the first link of ``<p class="links">``.
- ``cvf``: the Computer Vision Foundation's open access page of a conference (CVPR, ICCV, WACV), all days:
  ``<dt class="ptitle"><a href=...>Title</a></dt>``.
- ``virtual``: a conference's virtual site, its papers page (ICLR since 2021): the plain list of links to each paper's
  page, ``<a href="/virtual/2024/poster/18969">Title</a>`` (posters and orals).
- ``acl``: an ACL Anthology volume page: each paper is ``<strong><a class="align-middle" href=...>Title</a></strong>``;
  the volume's own entry (its front matter, ``….0/``) is not a paper.
"""

from __future__ import annotations

import re
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
        self._count: list[str] | None = None
        self.declared: int | None = None  # the page's own "679 papers"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "a" and a.get("title") == "paper title" and a.get("href"):
            self._href, self._text = a["href"], []
        elif tag == "span" and "paper-count" in (a.get("class") or "").split():
            self._count = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)
        if self._count is not None:
            self._count.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self._count is not None:
            digits = "".join(c for c in "".join(self._count) if c.isdigit())
            self.declared = int(digits) if digits else None
            self._count = None
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


class _Linked(_Parser):
    """A paper is the text of a link inside an element that marks it (``dt.ptitle``, ``strong``)."""

    def __init__(self, base: str, holder: str, holder_class: str, link_class: str, skip: str) -> None:
        super().__init__(base)
        self._holder, self._holder_class, self._link_class, self._skip = holder, holder_class, link_class, skip
        self._inside = False
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == self._holder and (not self._holder_class or self._holder_class in (a.get("class") or "").split()):
            self._inside = True
        elif tag == "a" and self._inside and a.get("href") and (not self._link_class or self._link_class in (a.get("class") or "").split()):
            self._href, self._text = a["href"], []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def skipped(self, href: str) -> bool:
        return bool(self._skip) and href.rstrip("/").endswith(self._skip)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            title = " ".join("".join(self._text).split())
            if title and not self.skipped(self._href):
                self.out.append(Listed(title, urllib.parse.urljoin(self.base, self._href)))
            self._href = None
        elif tag == self._holder:
            self._inside = False


class _Cvf(_Linked):
    def __init__(self, base: str) -> None:
        super().__init__(base, "dt", "ptitle", "", "")


class _Acl(_Linked):
    def __init__(self, base: str) -> None:
        super().__init__(base, "strong", "", "align-middle", ".0")

    def skipped(self, href: str) -> bool:
        # the volume's own entry: 2020.acl-main.0, and in the old identifiers P17-1000
        return href.rstrip("/").endswith(".0") or re.search(r"/[A-Z]\d{2}-\d000$", href.rstrip("/")) is not None


class _Virtual(_Parser):
    """Links to /virtual/<year>/poster/<n> or /oral/<n>: each a paper."""

    def __init__(self, base: str) -> None:
        super().__init__(base)
        self._href: str | None = None
        self._text: list[str] = []
        self._kinds: dict[str, set[str]] = {}  # title -> the kinds of page (poster, oral) it was listed under

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href") or ""
        if tag == "a" and re.fullmatch(r"/virtual/\d{4}/(?:poster|oral)/\d+/?", href.strip()):
            self._href, self._text = href.strip(), []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            title = " ".join("".join(self._text).split())
            # an oral is listed under its oral and its poster page: one paper (the first link kept); two posters (or two
            # orals) of one title are two papers
            kind = "oral" if "/oral/" in self._href else "poster"
            kinds = self._kinds.setdefault(title.casefold(), set())
            if title and (not kinds or kind in kinds):
                self.out.append(Listed(title, urllib.parse.urljoin(self.base, self._href)))
            kinds.add(kind)
            self._href = None


PARSERS: dict[str, type[_Parser]] = {"neurips": _Neurips, "pmlr": _Pmlr, "cvf": _Cvf, "acl": _Acl, "virtual": _Virtual}


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
    declared = getattr(parser, "declared", None)
    if declared is not None and declared != len(parser.out):
        raise ValueError(f"{base} says it lists {declared} papers, but {len(parser.out)} were read: has the page changed?")
    seen: set[str] = set()
    out = []
    for item in parser.out:
        url = item.url if urllib.parse.urlparse(item.url).scheme in ("http", "https") else ""  # no javascript: links
        key = url or item.title
        if key not in seen:  # the same paper listed twice; two papers may share a title, not a link
            seen.add(key)
            out.append(Listed(item.title, url))
    return out
