"""Papers and venue-years as the site shows them. A paper is what the venue's proceedings list (its title and page);
when it is matched to an OpenAlex work, OpenAlex's own numbers (citations, FWCI, the field-normalized percentile) and a
"recent" count summed from its citations by year. A venue-year is its proceedings page (the official list, and so the
official count) and how many of its papers were matched."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Paper:
    title: str  # as the proceedings print it
    year: int  # the venue's year
    url: str = ""  # the paper's page in the proceedings
    id: str = ""  # the OpenAlex work (https://openalex.org/W...); "" when unmatched
    cited_by_count: int | None = None
    fwci: float | None = None  # field-weighted citation impact: 1.0 is the world average for the field and year
    percentile: float | None = None  # OpenAlex's citation_normalized_percentile, 0 to 1
    top1: bool = False
    top10: bool = False
    recent: int | None = None  # citations in the last two complete years, a speed
    doi: str = ""
    also: list[str] = field(default_factory=list)  # other OpenAlex records of the same paper (a preprint), not added in
    how: str = ""  # how it was matched: exact, later (the exact title, a record dated later), close (nearly the same words), or ""
    tried: str = ""  # when unmatched: the date it was last searched for in vain (searched again only weeks later)

    def with_work(self, w: dict[str, Any], as_of_year: int, also: list[str] | None = None, how: str | None = None) -> Paper:
        """The paper with an OpenAlex work's numbers.

        >>> p = Paper("T", 2017).with_work({"id": "https://openalex.org/W1", "cited_by_count": 9, "fwci": 2.5,
        ...     "citation_normalized_percentile": {"value": 0.97, "is_in_top_1_percent": False, "is_in_top_10_percent": True},
        ...     "counts_by_year": [{"year": 2026, "cited_by_count": 1}, {"year": 2025, "cited_by_count": 3},
        ...                        {"year": 2024, "cited_by_count": 4}]}, 2026)
        >>> p.id, p.percentile, p.top10, p.recent
        ('https://openalex.org/W1', 0.97, True, 7)
        """
        raw = w.get("citation_normalized_percentile")
        pct: dict[str, Any] = raw if isinstance(raw, dict) else {}
        counts = w.get("counts_by_year") if isinstance(w.get("counts_by_year"), list) else []
        recent = sum(
            _whole(c.get("cited_by_count")) or 0 for c in counts or [] if isinstance(c, dict) and c.get("year") in (as_of_year - 1, as_of_year - 2)
        )
        return Paper(
            title=self.title,
            year=self.year,
            url=self.url,
            id=str(w.get("id") or ""),
            cited_by_count=_whole(w.get("cited_by_count")) or 0,
            fwci=_number(w.get("fwci")),
            percentile=_number(pct.get("value")),
            top1=pct.get("is_in_top_1_percent") is True,
            top10=pct.get("is_in_top_10_percent") is True,
            recent=recent,
            doi=str(w.get("doi") or ""),
            also=list(also if also is not None else self.also),
            how=how if how is not None else (self.how or "exact"),
        )

    @classmethod
    def from_data(cls, d: dict[str, Any]) -> Paper:
        """A paper from the data written before (fields a later version added or dropped are ignored)."""
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class VenueYear:
    venue: str  # the short name, e.g. NeurIPS
    year: int
    source: str  # the proceedings page: the official list
    papers: list[Paper] = field(default_factory=list)
    rule: int = 0  # the matching rule its matches were made under (match.RULE); 0 for data written before rules were numbered

    @property
    def matched(self) -> int:
        return sum(1 for p in self.papers if p.id)

    @property
    def coverage(self) -> float | None:
        """The share of the proceedings' papers matched in OpenAlex."""
        return self.matched / len(self.papers) if self.papers else None


def _whole(v: object) -> int | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        return None
    return int(v)


def _number(v: object) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        return None
    return float(v)
