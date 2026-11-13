"""From a venue list to data: each venue-year's papers from OpenAlex, its coverage against the official count, written
as open JSON (an index, and one file per venue-year) for the site and for anyone to use."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .model import Paper, VenueYear
from .openalex import Client

SLUG = re.compile(r"[^a-z0-9]+")


@dataclass
class Venue:
    name: str  # short: NeurIPS
    full: str = ""
    sources: list[str] = field(default_factory=list)  # OpenAlex source IDs (S...): a venue can have several
    official: dict[int, tuple[int, str]] = field(default_factory=dict)  # year -> (accepted papers, where that is said)

    @property
    def slug(self) -> str:
        return SLUG.sub("-", self.name.lower()).strip("-")


def read_venues(path: Path) -> list[Venue]:
    """The venue list: JSON, ``{"venues": [{"name", "full", "sources": [...], "official": {"2017": {"count", "source"}}}]}``.
    An official count must say where it comes from."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise ValueError(f"{path.as_posix()}: not a readable venue list ({e})") from e
    venues = []
    for i, v in enumerate((data.get("venues") if isinstance(data, dict) else None) or []):
        if not isinstance(v, dict) or not isinstance(v.get("name"), str) or not v["name"].strip():
            raise ValueError(f"{path.as_posix()}: venue {i + 1} has no name")
        sources = v.get("sources")
        if (
            not isinstance(sources, list)
            or not sources
            or not all(isinstance(s, str) and re.fullmatch(r"(?:https://openalex\.org/)?S\d+", s) for s in sources)
        ):
            raise ValueError(f"{path.as_posix()}: {v['name']}: sources must be OpenAlex source IDs (S…); find them with: paper-impact sources NAME")
        official = {}
        for year, o in (v.get("official") or {}).items():
            if not str(year).isdigit() or not isinstance(o, dict) or not isinstance(o.get("count"), int) or o["count"] <= 0:
                raise ValueError(f"{path.as_posix()}: {v['name']} {year}: an official count is a positive whole number")
            if not isinstance(o.get("source"), str) or not o["source"].startswith("https://"):
                raise ValueError(f"{path.as_posix()}: {v['name']} {year}: an official count needs its source (an https link)")
            official[int(year)] = (o["count"], o["source"])
        venues.append(Venue(v["name"].strip(), str(v.get("full") or ""), sources, official))
    if not venues:
        raise ValueError(f"{path.as_posix()}: no venues")
    if len({v.slug for v in venues}) != len(venues):
        raise ValueError(f"{path.as_posix()}: two venues with the same name")
    return venues


def build(venues: list[Venue], years: range, client: Client, top: int | None, as_of_year: int) -> list[VenueYear]:
    """Every venue-year: its papers (the `top` most cited, or all when `top` is None), OpenAlex's count, the official one."""
    out = []
    for venue in venues:
        for year in years:
            count, works = client.works(venue.sources, year, top)
            papers = [p for w in works if (p := Paper.from_openalex(w, as_of_year)) is not None]
            official = venue.official.get(year)
            out.append(VenueYear(venue.name, year, papers, count, official[0] if official else None, official[1] if official else "",
                                 complete=top is None or count <= len(papers)))  # fmt: skip
    return out


def write_data(out: Path, venues: list[Venue], venue_years: list[VenueYear], generated: str) -> list[Path]:
    """``data/index.json`` (venues, venue-years with counts and coverage, when and how it was made) and
    ``data/<venue>/<year>.json`` (the papers). Metadata and links only."""
    data = out / "data"
    written = []
    slugs = {v.name: v.slug for v in venues}
    index: dict[str, Any] = {
        "tool": "paper-impact",
        "tool_version": __version__,
        "generated": generated,
        "source": "OpenAlex (https://openalex.org), CC0",
        "venues": [{"name": v.name, "full": v.full, "slug": v.slug, "sources": v.sources} for v in venues],
        "venue_years": [],
    }
    for vy in venue_years:
        path = data / slugs[vy.venue] / f"{vy.year}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"venue": vy.venue, "year": vy.year, "papers": [asdict(p) for p in vy.papers]}, ensure_ascii=False,
                                   separators=(",", ":")) + "\n", encoding="utf-8")  # fmt: skip
        written.append(path)
        index["venue_years"].append({"venue": vy.venue, "year": vy.year, "file": path.relative_to(out).as_posix(), "papers": len(vy.papers),
                                     "openalex_count": vy.openalex_count, "official_count": vy.official_count,
                                     "official_source": vy.official_source, "coverage": vy.coverage, "complete": vy.complete})  # fmt: skip
    (data / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    written.append(data / "index.json")
    return written
