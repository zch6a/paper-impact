"""Papers and venue-years as the site shows them: every number OpenAlex's own (citations, FWCI, the field-normalized
percentile), the "recent" count summed from its citations by year, and the coverage of a venue-year against the
official count of accepted papers, which comes with its source."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Paper:
    id: str  # https://openalex.org/W...
    title: str
    year: int
    cited_by_count: int
    fwci: float | None = None  # field-weighted citation impact: 1.0 is the world average for the field and year
    percentile: float | None = None  # OpenAlex's citation_normalized_percentile, 0 to 1
    top1: bool = False
    top10: bool = False
    recent: int = 0  # citations in the last two complete years, a speed
    doi: str = ""

    @classmethod
    def from_openalex(cls, w: dict[str, Any], as_of_year: int) -> Paper | None:
        """A paper from an OpenAlex work; None when it has no id, title or year.

        >>> p = Paper.from_openalex({"id": "https://openalex.org/W1", "title": "T", "publication_year": 2017, "cited_by_count": 9,
        ...     "fwci": 2.5, "citation_normalized_percentile": {"value": 0.97, "is_in_top_1_percent": False, "is_in_top_10_percent": True},
        ...     "counts_by_year": [{"year": 2026, "cited_by_count": 1}, {"year": 2025, "cited_by_count": 3},
        ...                        {"year": 2024, "cited_by_count": 4}]}, 2026)
        >>> p.percentile, p.top10, p.recent
        (0.97, True, 7)
        """
        title, year = w.get("title") or w.get("display_name"), w.get("publication_year")
        if not w.get("id") or not isinstance(title, str) or not title.strip() or not _whole(year):
            return None
        raw = w.get("citation_normalized_percentile")
        pct: dict[str, Any] = raw if isinstance(raw, dict) else {}
        recent = sum(
            _whole(c.get("cited_by_count")) or 0
            for c in w.get("counts_by_year") or []
            if isinstance(c, dict) and c.get("year") in (as_of_year - 1, as_of_year - 2)
        )
        return cls(
            id=str(w["id"]),
            title=" ".join(title.split()),
            year=int(year),  # type: ignore[arg-type]
            cited_by_count=_whole(w.get("cited_by_count")) or 0,
            fwci=_number(w.get("fwci")),
            percentile=_number(pct.get("value")),
            top1=pct.get("is_in_top_1_percent") is True,
            top10=pct.get("is_in_top_10_percent") is True,
            recent=recent,
            doi=str(w.get("doi") or ""),
        )


@dataclass
class VenueYear:
    venue: str  # the short name, e.g. NeurIPS
    year: int
    papers: list[Paper] = field(default_factory=list)
    openalex_count: int = 0  # how many works OpenAlex has under the venue's sources for the year
    official_count: int | None = None  # accepted papers, as the venue says
    official_source: str = ""  # where that count comes from
    complete: bool = False  # every work fetched (with a key), or only the most cited first page

    @property
    def coverage(self) -> float | None:
        """OpenAlex's count against the official one (can pass 1: OpenAlex may count workshop papers too)."""
        return None if not self.official_count else self.openalex_count / self.official_count


def _whole(v: object) -> int | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        return None
    return int(v)


def _number(v: object) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        return None
    return float(v)
