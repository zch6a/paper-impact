"""From a venue list to data: each venue-year's papers from its proceedings page, matched to OpenAlex, written as open
JSON (an index, and one file per venue-year) for the site and for anyone to use. A rebuild reuses the matches already
in the data: only new venue-years (or papers) are searched, and matched works' numbers are refreshed by ID."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .match import match, normalize
from .model import Paper, VenueYear
from .openalex import Client
from .proceedings import PARSERS, parse

SLUG = re.compile(r"[^a-z0-9]+")


@dataclass
class Venue:
    name: str  # short: NeurIPS
    full: str = ""
    kind: str = ""  # the proceedings parser: neurips, pmlr
    pages: dict[int, str] = field(default_factory=dict)  # year -> its proceedings page

    @property
    def slug(self) -> str:
        return SLUG.sub("-", self.name.lower()).strip("-")


def read_venues(path: Path) -> list[Venue]:
    """The venue list: JSON, ``{"venues": [{"name", "full", "proceedings": {"kind": "neurips", "pages": {"2017": url}}}]}``."""
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
        pages = {}
        for year, url in (proc.get("pages") or {}).items():
            if not str(year).isdigit() or not isinstance(url, str) or not url.startswith("https://"):
                raise ValueError(f"{path.as_posix()}: {v['name']} {year}: a proceedings page is a year and an https link")
            pages[int(year)] = url
        if not pages:
            raise ValueError(f"{path.as_posix()}: {v['name']}: no proceedings pages")
        venues.append(Venue(v["name"].strip(), str(v.get("full") or ""), proc["kind"], pages))
    if not venues:
        raise ValueError(f"{path.as_posix()}: no venues")
    if len({v.slug for v in venues}) != len(venues):
        raise ValueError(f"{path.as_posix()}: two venues with the same name")
    return venues


def read_previous(out: Path, venue: Venue, year: int) -> dict[str, Paper]:
    """The papers of an earlier build of this venue-year, by normalized title (empty when there is none)."""
    path = out / "data" / venue.slug / f"{year}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {normalize(p["title"]): Paper(**p) for p in data.get("papers") or []}
    except (OSError, ValueError, TypeError, KeyError):
        return {}


def build_venue_year(venue: Venue, year: int, client: Client, as_of_year: int, previous: dict[str, Paper]) -> VenueYear:
    url = venue.pages[year]
    listed = parse(venue.kind, client.page(url), url)
    papers = [Paper(item.title, year, item.url) for item in listed]
    known = {normalize(p.title): previous[normalize(p.title)] for p in papers if normalize(p.title) in previous and previous[normalize(p.title)].id}
    fresh = {w.get("id"): w for w in client.by_ids([p.id for p in known.values()])} if known else {}
    to_search = [p.title for p in papers if normalize(p.title) not in known]
    found = match(to_search, year, client.search) if to_search else {}
    out = []
    for p in papers:
        n = normalize(p.title)
        if n in known and known[n].id in fresh:
            out.append(p.with_work(fresh[known[n].id], as_of_year, known[n].also))
        elif n in found and found[n].work is not None:
            out.append(p.with_work(found[n].work, as_of_year, found[n].also))  # type: ignore[arg-type]
        else:
            out.append(p)
    return VenueYear(venue.name, year, url, out)


def build(venues: list[Venue], years: range, client: Client, as_of_year: int, out: Path) -> list[VenueYear]:
    """Every venue-year with a proceedings page in `years`."""
    return [build_venue_year(v, y, client, as_of_year, read_previous(out, v, y)) for v in venues for y in sorted(v.pages) if y in years]


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
        body = {"venue": vy.venue, "year": vy.year, "source": vy.source, "papers": [asdict(p) for p in vy.papers]}
        path.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        written.append(path)
        index["venue_years"].append({"venue": vy.venue, "year": vy.year, "file": path.relative_to(out).as_posix(), "source": vy.source,
                                     "listed": len(vy.papers), "matched": vy.matched, "coverage": vy.coverage})  # fmt: skip
    (data / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    written.append(data / "index.json")
    return written
