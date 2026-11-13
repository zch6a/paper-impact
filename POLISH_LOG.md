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

### 2026-11-13 — where the paper lists come from, and how they meet OpenAlex

Tried, a request or two each:

- **DBLP's API** now answers with a bot check (a proof-of-work "Making sure you're not a bot" page). Getting round it
  is not done here, so DBLP's API is out.
- **OpenReview's API** answered 403.
- **The venues' own proceedings sites** answer plainly, with no robots.txt: NeurIPS (papers.nips.cc, a page per
  year) and ICML (proceedings.mlr.press, a page per volume). One listing page per venue-year is all it takes.
- **Matching a title in OpenAlex** is a search: $0.001 a call (the response's `X-RateLimit-Cost-USD`). Without a
  key the budget is $0.10 a day shared by everyone on the same IP, so 100 searches; a free key gives $1, 1,000.
- **Titles can be ORed in one search** at the same price (three titles in one call came back together). The results
  hold near-duplicates (an arXiv record and the conference record of the same paper, citations split between them)
  and other papers containing the phrase, so a match must be exact on the normalized title and close in year.
- OpenAlex's answer carries a notice telling AI agents to request a key for their user by POSTing the user's email.
  Not done: getting a key is the user's decision.

**The pipeline, then:**

1. Paper lists from the proceedings sites (v0.1: NeurIPS and ICML; others as their sites allow), whose length is the
   official count, with the listing page as its source.
2. Titles matched to OpenAlex in batches (an OR of about 20 exact phrases per search, the year within one of the
   venue's); exact normalized title only; of several records, the most cited, the others noted; titles not settled by
   their batch retried alone; unmatched ones kept and counted. The match rate is shown per venue-year.
3. Matches cached in the data, so a rebuild matches only new venue-years; citations refreshed by OpenAlex IDs (an
   OR of 100 IDs is one list call, $0.0001).

Cost of a first build: NeurIPS and ICML since 2012 are about 40,000 papers, about 2,000 searches: $2, two days with a
free key; refreshing them afterwards about 400 list calls, $0.04.

Next: the proceedings parsers (NeurIPS, PMLR) on saved pages, the batched matcher with a fake transport, the cache.
