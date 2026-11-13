# Polish log

### 2026-11-13 — research

- **Others.** No open site shows which papers at AI venues mattered, by venue and year; there are studies (a 2025
  arXiv paper models citation percentiles of 17,942 NeurIPS/ICML/ICLR papers) and raw accepted-paper lists.
- **OpenAlex** gives each work its own normalized impact: `fwci`, `citation_normalized_percentile` (with top 1% / 10%
  flags) and citations by year, so the site need not normalize anything itself, and every number traces to a record.
- **Cost.** A list query costs $0.10 per 1,000 calls, a lookup by ID or DOI nothing; a free key gives $1 a day.
- **Paging needs a key** (tried: page 2 by cursor answers 401 "API key required for cursor paging"); the first page
  of up to 200 is open.
- **Coverage** must be shown: under one NeurIPS source OpenAlex lists 196 works for 2017.

### 2026-11-13 — the skeleton, and a finding that changes the plan

- `model.py` (a paper with OpenAlex's numbers and a recent-citations count; a venue-year with OpenAlex's count, the
  official count and its source, coverage), `openalex.py` (a venue-year's works: the first page of the most cited
  without a key, every page with one; a 401 on paging says to set a key; the key in a header; retries), `build.py`
  (a venue list in JSON, whose official counts must cite an https source; the build; `data/index.json` and one file
  per venue-year), `site.py` (one self-contained page: venue, year, sort, search; coverage with the official count's
  source; text set with textContent), `cli.py` (`build`, `sources`).
- **The finding**: looking up the real venues, OpenAlex's sources for ML conferences hold a small part of them:
  "International Conference on Learning Representations" has 602 works in all, "International Conference on Machine
  Learning" 2,040 (both conferences have published tens of thousands). Most ML papers sit under arXiv, not their
  venue. So "a venue's works by source" cannot be the main path: the paper list has to come from where the venues
  publish it (DBLP, OpenReview, the proceedings sites) and be matched to OpenAlex works.

Tests: 9 (a fake transport). ruff, mypy clean.

Next: work out the paper lists (DBLP's proceedings records for NeurIPS, ICML, ICLR and others: complete, free, with
links and often DOIs; OpenReview for the recent ones) and the cheapest exact match to OpenAlex (by DOI, free; by
arXiv DOI; by title, which is a search and costs more), with the match rate measured and shown.
