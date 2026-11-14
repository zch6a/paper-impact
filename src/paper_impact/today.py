r"""paper-impact today: the newest arXiv papers in a category, the ones with signs that they will matter first.

    paper-impact today cs.CL                  the last 200 submissions to cs.CL
    paper-impact today cs.LG --days 7 --citations   a week's, with OpenAlex's early citation counts

Recommenders rank by closeness to your topics; this ranks by what the paper itself shows, each sign named:

- accepted: the arXiv comment says a venue took it ("Accepted at ICLR 2027", "To appear in TACL", "NeurIPS 2026
  camera-ready"); a workshop counts for less;
- code: a link to a repository or a model (GitHub, GitLab, Hugging Face, a project page) in the abstract or the
  comment, or "code is available";
- citations (with --citations): how many works already cite it, from OpenAlex (by the arXiv DOI; fresh papers have
  none yet, so it matters for --days 7 and more).

The papers come from arXiv's API (one request every three seconds); only the category and dates are sent. Nothing is
judged about the content: a paper with no signs is not a worse paper, it has not said anything yet.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from . import __version__
from .openalex import Client, OpenAlexError

ARXIV = "https://export.arxiv.org/api/query"
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
USER_AGENT = f"paper-impact/{__version__} (+https://github.com/zch6a/paper-impact)"
VENUES = (
    r"NeurIPS|NIPS|ICML|ICLR|CVPR|ICCV|ECCV|WACV|ACL|EMNLP|NAACL|EACL|COLING|COLM|TACL|TMLR|JMLR|AAAI|IJCAI|KDD|WWW|SIGIR|WSDM|"
    r"CIKM|ICRA|IROS|RSS|CoRL|MICCAI|AISTATS|UAI|COLT|ALT|ICASSP|Interspeech|INTERSPEECH|SIGGRAPH|TPAMI|IJCV|Nature|Science|"
    r"PNAS|MLSys|USENIX|OSDI|SOSP|NDSS|CCS|S&P|ICDE|VLDB|SIGMOD|ISMIR|LREC|CHI|UIST|CSCW|FAccT|AIES|ICSE|FSE|PLDI|POPL"
)
ACCEPTED = re.compile(
    rf"\b(?:accepted\s+(?:for\s+publication\s+)?(?:at|to|by|in|for)|to\s+appear\s+(?:at|in)|published\s+(?:at|in)|"
    rf"in\s+proceedings\s+of)\b(?P<where>[^.;\n]{{0,90}})"
    rf"|\b(?P<venue>{VENUES})\s*'?(?:\d{{2,4}}\s*)?(?:\(\s*(?:oral|spotlight|poster|main|findings)[^)]*\)|main\s+(?:track|conference)|"
    rf"camera[\s-]ready|oral\b|spotlight\b)",
    re.I,
)
KNOWN = re.compile(rf"\b({VENUES})\b", re.I)
CODE_URL = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.com|huggingface\.co|bitbucket\.org|codeberg\.org)/[\w.-]+/[\w.-]+"
    r"|https?://[\w-]+\.github\.io/?[\w./-]*",
    re.I,
)
WORKSHOP = re.compile(r"\bworkshop\b", re.I)
CODE = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.com|huggingface\.co|bitbucket\.org|codeberg\.org)/[\w.-]+(?:/[\w.-]+)?"
    r"|https?://[\w.-]+\.github\.io/?[\w./-]*"
    r"|\b(?:code|models?|data(?:set)?s?|implementation|weights)\s+(?:and\s+\w+\s+)?(?:is|are|will\s+be)\s+(?:publicly\s+|made\s+|freely\s+)?"
    r"(?:available|released|open-?sourced?)\b|\bproject\s+page\b",
    re.I,
)


@dataclass
class Paper:
    arxiv: str  # id with version
    title: str
    authors: list[str]
    published: str  # YYYY-MM-DD, first version
    comment: str = ""
    abstract: str = ""
    accepted: str = ""  # the venue named, if the comment says it was accepted
    workshop: bool = False
    code: str = ""  # the link (or phrase) found
    citations: int | None = None
    signs: list[str] = field(default_factory=list)
    score: float = 0.0

    @property
    def id(self) -> str:
        return re.sub(r"v\d+$", "", self.arxiv)


def signs(p: Paper) -> Paper:
    """The paper's signs and score: accepted 3 (a workshop 1), code 2, citations log2(1 + n).

    >>> p = signs(Paper("2601.00001v1", "T", [], "2026-01-01", comment="Accepted at ICLR 2026. Code: https://github.com/a/b"))
    >>> p.accepted, p.code, p.signs, p.score
    ('ICLR', 'https://github.com/a/b', ['accepted: ICLR', 'code'], 5.0)
    >>> signs(Paper("x", "T", [], "", comment="10 pages, under review at ICML")).signs
    []
    >>> [signs(Paper("x", "T", [], "", comment=c)).accepted for c in ["WSDM camera ready", "Accepted to IEEE TASLP 2026", "NeurIPS 2026 (Spotlight)"]]
    ['WSDM', 'IEEE TASLP 2026', 'NeurIPS']
    """
    text = f"{p.comment}\n{p.abstract}"
    m = ACCEPTED.search(p.comment)
    if m and not re.search(r"under\s+review|submitted\s+to", p.comment[max(0, m.start() - 30) : m.end()], re.I):
        where = m.group("where") or ""
        known = KNOWN.search(where)
        if m.group("venue"):
            p.accepted = m.group("venue")
        elif known:
            p.accepted = known.group(1)
        else:  # a venue not in the list: its first words, as written
            words = re.sub(r"^\s*(?:the|a)\s+", "", where.strip(" :,-"), flags=re.I)
            p.accepted = " ".join(words.split()[:6]) or "yes"
        p.workshop = bool(WORKSHOP.search(p.comment[max(0, m.start() - 40) : m.end() + 60]))
    c = CODE.search(text)
    if c:
        link = CODE_URL.search(text)  # the link itself when there is one, rather than "code is available"
        p.code = (link.group(0) if link else c.group(0)).rstrip(".,)")
    p.signs = []
    p.score = 0.0
    if p.accepted:
        p.signs.append(f"accepted: {p.accepted}" + (" (workshop)" if p.workshop else ""))
        p.score += 1.0 if p.workshop else 3.0
    if p.code:
        p.signs.append("code")
        p.score += 2.0
    if p.citations:
        p.signs.append(f"{p.citations} citation{'s' if p.citations > 1 else ''}")
        p.score += math.log2(1 + p.citations)
    return p


def parse(xml: bytes) -> list[Paper]:
    root = ET.fromstring(xml)
    out = []
    for e in root.findall("a:entry", ATOM):

        def text(tag: str, entry: ET.Element = e) -> str:
            el = entry.find(tag, ATOM)
            return re.sub(r"\s+", " ", el.text or "").strip() if el is not None else ""

        m = re.search(r"arxiv\.org/abs/(\S+)$", text("a:id"))
        if not m:
            continue
        authors = [re.sub(r"\s+", " ", (a.findtext("a:name", "", ATOM) or "")).strip() for a in e.findall("a:author", ATOM)]
        out.append(Paper(m.group(1), text("a:title"), authors, text("a:published")[:10], text("arxiv:comment"), text("a:summary")))
    return out


Getter = Callable[[str], bytes]


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - arXiv's API
        return r.read(20_000_000)


def fetch(category: str, days: int, limit: int, get: Getter = _get, sleep: Callable[[float], None] = time.sleep,
          today: dt.date | None = None) -> list[Paper]:  # fmt: skip
    """The category's submissions of the last `days` days (newest first), at most `limit`, 100 to a request."""
    since = (today or dt.date.today()) - dt.timedelta(days=days)
    out: list[Paper] = []
    start = 0
    while start < limit:
        query = urllib.parse.urlencode({"search_query": f"cat:{category}", "sortBy": "submittedDate", "sortOrder": "descending",
                                        "start": str(start), "max_results": str(min(100, limit - start))})  # fmt: skip
        if start:
            sleep(3.0)  # arXiv asks for one request every three seconds
        page = parse(get(f"{ARXIV}?{query}"))
        if not page:
            break
        out += [p for p in page if p.published >= since.isoformat()]
        if page[-1].published < since.isoformat():
            break
        start += len(page)
    return out


def citations(papers: list[Paper], client: Client) -> None:
    """OpenAlex's citation counts, by the arXiv DOI (10.48550/arXiv.ID), 50 to a request."""
    for k in range(0, len(papers), 50):
        group = papers[k : k + 50]
        dois = "|".join(f"https://doi.org/10.48550/arxiv.{p.id}" for p in group)
        try:
            data = client.get("/works", {"filter": f"doi:{dois}", "per_page": "50", "select": "doi,cited_by_count"})
        except OpenAlexError:
            return
        by = {str(w.get("doi", "")).lower().rsplit("arxiv.", 1)[-1]: int(w.get("cited_by_count") or 0) for w in data.get("results") or []}
        for p in group:
            if p.id.lower() in by:
                p.citations = by[p.id.lower()]


def rank(papers: list[Paper]) -> list[Paper]:
    newest = sorted((signs(p) for p in papers), key=lambda p: p.published, reverse=True)
    return sorted(newest, key=lambda p: -p.score)  # stable: newest first among equal scores


def text(category: str, papers: list[Paper], top: int) -> str:
    with_signs = [p for p in papers if p.signs]
    out = [f"{category}: {len(papers)} papers, {len(with_signs)} with signs "
           f"(accepted {sum(bool(p.accepted) for p in papers)}, code {sum(bool(p.code) for p in papers)})", ""]  # fmt: skip
    for p in papers[:top]:
        authors = ", ".join(p.authors[:3]) + (" et al." if len(p.authors) > 3 else "")
        out.append(f"{p.published}  {p.id:12} {p.title[:110]}")
        out.append(f"            {authors}" + (f"  ·  {'; '.join(p.signs)}" if p.signs else ""))
        if p.code and p.code.startswith("http"):
            out.append(f"            {p.code}")
    rest = len(papers) - top
    if rest > 0:
        out += ["", f"... and {rest} more (--top N to see more)"]
    return "\n".join(out) + "\n"


def markdown(category: str, papers: list[Paper], top: int) -> str:
    out = [f"### {category}: {len(papers)} new papers, the ones with signs first", "", "| Paper | Signs | Date |", "|---|---|---|"]
    for p in papers[:top]:
        title = p.title.replace("|", "\\|")[:110]
        out.append(f"| [{title}](https://arxiv.org/abs/{p.id}) | {'; '.join(p.signs) or '—'} | {p.published} |")
    return "\n".join(out) + "\n"


def to_json(category: str, papers: list[Paper]) -> str:
    return json.dumps({"tool": "paper-impact today", "version": __version__, "category": category,
                       "papers": [asdict(p) for p in papers]}, indent=2, ensure_ascii=False) + "\n"  # fmt: skip
