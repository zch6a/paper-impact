"""From a venue list to data: each venue-year's papers from its proceedings page, matched to OpenAlex, written as open
JSON (an index, and one file per venue-year) for the site and for anyone to use. A rebuild reuses the matches already
in the data: only new venue-years (or papers) are searched, and matched works' numbers are refreshed by ID."""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .match import RULE, close_match, match, normalize
from .model import Paper, VenueYear
from .openalex import BudgetExhausted, Client, KeyRejected, OpenAlexError
from .proceedings import PARSERS, parse

SLUG = re.compile(r"[^a-z0-9]+")


@dataclass
class Venue:
    name: str  # short: NeurIPS
    full: str = ""
    kind: str = ""  # the proceedings parser: neurips, pmlr
    pages: dict[int, str] = field(default_factory=dict)  # year -> its proceedings page
    expect: dict[int, list[str]] = field(default_factory=dict)  # year -> text the page must contain (a wrong volume fails)
    lists: dict[int, list[str]] = field(default_factory=dict)  # year -> the pages that list the papers, when not the page itself

    @property
    def slug(self) -> str:
        return SLUG.sub("-", self.name.lower()).strip("-")


def read_venues(path: Path) -> list[Venue]:
    """The venue list: JSON, ``{"venues": [{"name", "full", "proceedings": {"kind": "pmlr", "pages": {"2017": url or
    {"url": url, "expect": ["International Conference on Machine Learning", "2017"]}}}}]}``: a page may name the text
    it must contain, so that a wrong volume number fails instead of bringing in another conference."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise ValueError(f"{path.as_posix()}: not a readable venue list ({e})") from e
    venues = []
    for i, v in enumerate((data.get("venues") if isinstance(data, dict) else None) or []):
        if not isinstance(v, dict) or not isinstance(v.get("name"), str) or not v["name"].strip():
            raise ValueError(f"{path.as_posix()}: venue {i + 1} has no name")
        raw = v.get("proceedings")
        proc: dict[str, Any] = raw if isinstance(raw, dict) else {}
        if proc.get("kind") not in PARSERS:
            raise ValueError(f"{path.as_posix()}: {v['name']}: proceedings kind must be one of {', '.join(PARSERS)}")
        pages, expect, lists = {}, {}, {}
        if not isinstance(proc.get("pages") or {}, dict):
            raise ValueError(f"{path.as_posix()}: {v['name']}: pages is an object of years and links")
        for year, entry in (proc.get("pages") or {}).items():
            url = entry.get("url") if isinstance(entry, dict) else entry
            wanted = entry.get("expect", []) if isinstance(entry, dict) else []
            more = entry.get("lists", []) if isinstance(entry, dict) else []
            if not isinstance(more, list) or not all(isinstance(x, str) and x.startswith("https://") for x in more):
                raise ValueError(f"{path.as_posix()}: {v['name']} {year}: lists is a list of https links (pages that list the papers)")
            if not str(year).isdigit() or not isinstance(url, str) or not url.startswith("https://"):
                raise ValueError(f"{path.as_posix()}: {v['name']} {year}: a proceedings page is a year and an https link")
            if not isinstance(wanted, list) or not all(isinstance(x, str) and x for x in wanted):
                raise ValueError(f"{path.as_posix()}: {v['name']} {year}: expect is a list of texts")
            pages[int(year)], expect[int(year)] = url, wanted
            if more:
                lists[int(year)] = more
        if not pages:
            raise ValueError(f"{path.as_posix()}: {v['name']}: no proceedings pages")
        venues.append(Venue(v["name"].strip(), str(v.get("full") or ""), proc["kind"], pages, expect, lists))
    if not venues:
        raise ValueError(f"{path.as_posix()}: no venues")
    if len({v.slug for v in venues}) != len(venues):
        raise ValueError(f"{path.as_posix()}: two venues with the same name")
    return venues


RETRY_DAYS = 30  # a paper searched for in vain is searched again after this many days, not every build
EXACT_MISSED = "exact:"  # tried = "exact:2026-11-13": its exact search missed; its looser try is still to come


def read_previous(out: Path, venue: Venue, year: int) -> tuple[str, list[Paper], int]:
    """The proceedings page, papers and matching rule of an earlier build of this venue-year (empty when there is none)."""
    path = out / "data" / venue.slug / f"{year}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", [], RULE
    if not isinstance(data, dict) or not isinstance(data.get("papers") or [], list):
        return "", [], RULE  # not this tool's data: built afresh
    papers = []
    for p in data.get("papers") or []:
        if isinstance(p, dict) and isinstance(p.get("title"), str) and p["title"]:
            try:
                papers.append(Paper.from_data({"year": year, **p}))
            except TypeError:
                continue  # one damaged entry is searched again, the others are kept
    rule = data.get("rule")
    return str(data.get("source") or ""), papers, rule if isinstance(rule, int) and not isinstance(rule, bool) else 0


def _due(tried: str, today: dt.date) -> bool:
    if tried.startswith(EXACT_MISSED):
        return False  # waiting for its looser try, not for another exact search
    try:
        return (today - dt.date.fromisoformat(tried)).days >= RETRY_DAYS
    except ValueError:
        return True


def build_venue_year(
    venue: Venue, year: int, client: Client, as_of_year: int, previous: list[Paper], today: dt.date | None = None, rule: int = RULE
) -> VenueYear:
    """A venue-year: its proceedings page read; papers matched before refreshed by ID (one whose ID OpenAlex no longer
    returns is searched again, and so is an exact match made under an older matching `rule`); the others searched,
    except those searched in vain less than RETRY_DAYS ago; papers that share a title within the venue-year left
    unmatched (one record cannot be told apart for two papers)."""
    today = today or dt.date.today()
    url = venue.pages[year]
    papers, seen = [], set()
    for listing in venue.lists.get(year) or [url]:  # a conference may list its papers over several pages (one a day)
        page = client.page(listing)
        missing = [x for x in venue.expect.get(year, []) if x not in page]
        if missing:
            raise ValueError(f"{listing} does not mention {', '.join(repr(x) for x in missing)}: is it {venue.name} {year}'s proceedings?")
        for item in parse(venue.kind, page, listing):
            if (item.url or item.title) not in seen:
                seen.add(item.url or item.title)
                papers.append(Paper(item.title, year, item.url))
    if not papers:
        raise ValueError(f"{url} lists no papers: has the page changed?")
    norm = {id(p): normalize(p.title) for p in papers}
    counts = Counter(norm.values())
    previous_norm = [(normalize(q.title), q) for q in previous]
    previous_counts = Counter(n for n, _ in previous_norm)
    by_url = {q.url: (n, q) for n, q in previous_norm if q.url}
    by_title = {n: q for n, q in previous_norm if previous_counts[n] == 1}

    def earlier(p: Paper) -> Paper | None:
        """The same paper in the earlier build: by its link (if its title is still the same), else by its title."""
        if p.url in by_url:
            n, q = by_url[p.url]
            return q if n == norm[id(p)] else None  # the title changed on the page: a paper to look up afresh
        return by_title.get(norm[id(p)])

    before = {id(p): earlier(p) for p in papers}

    known = {id(p): q for p in papers if (q := before[id(p)]) is not None and q.id and counts[norm[id(p)]] == 1}
    try:
        fresh = {w.get("id"): w for w in client.by_ids([q.id for q in known.values()])} if known else {}
        refreshed = True
    except BudgetExhausted:
        fresh, refreshed = {}, False  # the budget is spent: the numbers of the last build stand
    if refreshed:
        known = {k: q for k, q in known.items() if q.id in fresh}  # an ID OpenAlex no longer returns: search the title again

    def wanted(p: Paper) -> bool:
        q = before[id(p)]
        return id(p) not in known and counts[norm[id(p)]] == 1 and bool(norm[id(p)]) and (q is None or not q.tried or _due(q.tried, today))

    # the exact search has changed since these were matched: searched again (a batch of 20 costs one search), the old
    # match kept until a new one replaces it, so a spent budget loses nothing
    redo = {k for k, q in known.items() if rule < RULE and q.how in ("exact", "")}
    to_search = [p.title for p in papers if wanted(p) or id(p) in redo]
    found = match(to_search, year, client.search, close=False) if to_search and not client.exhausted else {}
    out = []
    for p in papers:
        n, q = norm[id(p)], before[id(p)]
        if id(p) in redo and n in found and found[n].work is not None:
            out.append(p.with_work(found[n].work, as_of_year, found[n].also, found[n].how))  # type: ignore[arg-type]
        elif id(p) in known and q is not None:
            out.append(
                p.with_work(fresh[q.id], as_of_year, q.also, q.how)
                if q.id in fresh
                else Paper.from_data({**asdict(q), "title": p.title, "url": p.url})
            )
        elif n in found and found[n].work is not None and wanted(p):
            out.append(p.with_work(found[n].work, as_of_year, found[n].also, found[n].how))  # type: ignore[arg-type]
        elif n in found and wanted(p):
            out.append(Paper(p.title, year, p.url, tried=EXACT_MISSED + today.isoformat()))  # the exact search missed today
        else:  # a title shared in this venue-year carries no mark: it is never searched
            keep = q is not None and not q.id and counts[n] == 1
            out.append(Paper(p.title, year, p.url, tried=q.tried if keep and q is not None else ""))
    done = all(norm[k] in found for k in redo)  # every old match answered under the new rule (else the next build goes on)
    return VenueYear(venue.name, year, url, out, RULE if done else rule)


class Stopped(KeyRejected):
    """OpenAlex refused the key midway: the run stops, with what it built (the venue-years not reached carried over), to
    be written before exiting so that the budget spent is not lost."""

    def __init__(self, cause: KeyRejected, built: list[VenueYear], failures: list[Failure]) -> None:
        super().__init__(str(cause))
        self.built, self.failures = built, failures


@dataclass
class Failure:
    venue: str
    year: int
    reason: str


def build(venues: list[Venue], years: range, client: Client, as_of_year: int, out: Path) -> tuple[list[VenueYear], list[Failure]]:
    """Every venue-year of the list: those in `years` built (a failing one, a changed page say, keeps its previous data
    and is reported); the others carried over from the previous data unchanged. A rejected key stops the run: Stopped
    carries what was built, the rest carried over."""
    built: list[VenueYear] = []
    failures: list[Failure] = []
    rejected: KeyRejected | None = None
    for v in venues:
        for y in sorted(v.pages):
            source, previous, rule = read_previous(out, v, y)
            if y not in years or rejected is not None:
                if previous:
                    built.append(VenueYear(v.name, y, source or v.pages[y], previous, rule))
                continue
            try:
                built.append(build_venue_year(v, y, client, as_of_year, previous, rule=rule))
            except KeyRejected as e:
                rejected = e
                if previous:
                    built.append(VenueYear(v.name, y, source or v.pages[y], previous, rule))
            except (OpenAlexError, ValueError) as e:
                failures.append(Failure(v.name, y, str(e)))
                if previous:
                    built.append(VenueYear(v.name, y, source or v.pages[y], previous, rule))
    if rejected is not None:
        raise Stopped(rejected, built, failures)
    if not client.exhausted:
        try:
            _close_pass([vy for vy in built if vy.year in years], client, as_of_year)
        except KeyRejected as e:
            raise Stopped(e, built, failures) from e
    return built, failures


def _close_pass(venue_years: list[VenueYear], client: Client, as_of_year: int, today: dt.date | None = None) -> None:
    """The looser try for every paper whose exact search missed, with the budget the exact searches left, the longest
    waiting first (across venue-years, so the later ones are not starved): a paper still unmatched after it is marked
    as tried today (and searched again only after RETRY_DAYS); one the budget did not reach keeps waiting. A title
    shared within its venue-year is not tried."""
    today = today or dt.date.today()
    waiting: list[tuple[str, VenueYear, int]] = []  # (since when, venue-year, index): the oldest first, so none starves
    for vy in venue_years:
        counts = Counter(normalize(p.title) for p in vy.papers)
        for i, p in enumerate(vy.papers):
            if not p.id and p.tried.startswith(EXACT_MISSED) and counts[normalize(p.title)] == 1:
                waiting.append((p.tried, vy, i))
    waiting.sort(key=lambda t: t[0])
    held = {id(vy): {p.id for p in vy.papers if p.id} for vy in venue_years}
    for _, vy, i in waiting:
        if client.exhausted:
            return
        p = vy.papers[i]
        found = close_match([p.title], vy.year, client.search)
        m = found.get(normalize(p.title))
        if m is None:
            continue  # the budget ran out: it keeps waiting
        work_id = str((m.work or {}).get("id") or "")
        if m.work is not None and work_id not in held[id(vy)]:  # a record another paper of the venue-year holds is not this one
            vy.papers[i] = p.with_work(m.work, as_of_year, m.also, m.how)
            held[id(vy)].add(work_id)
        else:
            vy.papers[i] = Paper(p.title, p.year, p.url, tried=today.isoformat())


def write_data(out: Path, venues: list[Venue], venue_years: list[VenueYear], generated: str) -> list[Path]:
    """``data/index.json`` (venues; venue-years with the proceedings page, papers listed and matched) and
    ``data/<venue>/<year>.json`` (the papers). Metadata and links only."""
    data = out / "data"
    written = []
    slugs = {v.name: v.slug for v in venues}
    index: dict[str, Any] = {
        "tool": "paper-impact",
        "tool_version": __version__,
        "generated": generated,
        "source": "papers: each venue's proceedings; numbers: OpenAlex (https://openalex.org), CC0",
        "venues": [{"name": v.name, "full": v.full, "slug": v.slug} for v in venues],
        "venue_years": [],
    }
    for vy in venue_years:
        path = data / slugs[vy.venue] / f"{vy.year}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {"venue": vy.venue, "year": vy.year, "source": vy.source, "rule": vy.rule, "papers": [asdict(p) for p in vy.papers]}
        path.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        written.append(path)
        index["venue_years"].append({"venue": vy.venue, "year": vy.year, "file": path.relative_to(out).as_posix(), "source": vy.source,
                                     "listed": len(vy.papers), "matched": vy.matched, "coverage": vy.coverage})  # fmt: skip
    for stale in sorted(data.glob("*/*.json")):  # a venue-year no longer in the list is not published
        if stale not in written:
            stale.unlink()
    for folder in sorted(data.glob("*")):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    (data / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    written.append(data / "index.json")
    return written
