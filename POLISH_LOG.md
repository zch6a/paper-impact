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

### 2026-11-13 — the proceedings, the matcher, the reuse; a first real measurement

- `proceedings.py`: NeurIPS's year pages and PMLR volumes, with the standard library's HTML parser; titles and each
  paper's page, nothing else. On the real pages: NeurIPS 2017 679 papers, ICML 2017 (PMLR 70) 434, the counts the
  pages print. Tests use synthetic pages of the same shape.
- `match.py`: titles normalized (compatibility-folded, case-folded, punctuation as spaces, apostrophes joined),
  searched about 20 to a search as exact phrases with punctuation stripped from the query (a comma or a `|` would cut
  OpenAlex's filter), within a year of the venue's; an exact normalized title only; the most cited record, the others
  kept as `also`; a batch cut at its page has its unmatched titles searched alone.
- The venue list now names each venue's proceedings pages (their list is the official one, and the page its source);
  the source-based fetch is gone. A paper OpenAlex does not have stays listed, without numbers. The key goes to
  OpenAlex only, never to the proceedings sites.
- A rebuild reads the data already written: papers matched before are refreshed by ID (100 to a call) and only the
  rest are searched.
- **Measured on ICML 2017** (keyless): 434 papers, 417 matched (96%) in 23 requests; the most cited are the expected
  ones (MAML 9,057, Wasserstein GAN 6,442, neural message passing 5,745). Curly apostrophes split words
  ("Priv’IT", "Nesterov’s"); joined now. The rebuild took 7 requests and matched 418. Of the 16 left, "Deep IV: A
  Flexible Approach for Counterfactual Prediction" is not in OpenAlex as that phrase at all (searched alone, no year:
  0 results).

The fetched pages and the trial site were in a temporary folder, deleted after.

Tests: 14 (synthetic pages, a fake OpenAlex). ruff, mypy clean.

Next: a looser second try for titles that miss (the title's words without the phrase, scored by overlap), the site's
handling of unmatched papers, a first venue list (NeurIPS and ICML since 2012, their pages), README, CI, the deploy
workflow.

### 2026-11-13 — a looser second try; the first venue list, every page checked

- **The looser try**: a title the exact search misses is searched once more by its words (no phrase), and a record is
  taken only when 85% of the words agree (a trailing plural "s" set aside), the length is within 15% and the year
  within one; the paper is marked `how: "close"`, an exact one `"exact"`, an unmatched one nothing.
- **Page checks**: a venue's page may name the text it must contain (the venue and the year); a page that does not
  is refused with the reason, so a wrong PMLR volume number cannot bring in another conference. A NeurIPS page that
  states its own count ("679 papers") must agree with what was read.
- **`venues.json`**: NeurIPS 2012–2024 (papers.nips.cc) and ICML 2013–2025 (PMLR volumes 28 … 267; ICML 2012 is not in
  PMLR). Every page fetched once, a second apart (no OpenAlex calls): all mention their venue and year; 34,673 papers
  in all, NeurIPS growing from 370 (2012) to 4,493 (2024), ICML from 283 (2013) to 3,330 (2025).
- **NeurIPS 2025** listed 64 papers: its page, under the heading "Creative AI", says "64 papers": only that track is
  up so far. Left out of the list until the main track is posted (listing it as "NeurIPS 2025" would mislead).

Tests: 18. ruff, mypy clean.

Next: README (English, Chinese), the site's look on the ICML 2017 build, CI, the scheduled build-and-deploy workflow
(the build job read-only; the Pages deploy runs no project code), the public repository; then a first full build.

### 2026-11-13 — the site with real data; README, CI, the monthly build

- **ICML 2017 built and looked at** (served locally, read in the browser pane): no console errors; the note links
  the proceedings and gives 434 listed, 418 found (96%); the expected papers on top. 39 requests: the looser tries
  for the 16 misses accepted none here.
- **Found**: 283 of the 418 found papers have no FWCI or percentile: OpenAlex computes them for some records only
  (MAML's matched record is its arXiv preprint, which has neither). Sorting by percentile would silently rank a
  minority, so the note now says how many have them ("135 of the 418 found") and that the rest come last.
- **README** (English, Chinese): what it is for, ICML 2017's real numbers, the site, building it, matching and cost,
  the monthly build, what each number is, the limits (OpenAlex's coverage, normalized numbers for a minority, venues
  appear once their proceedings are up).
- **CI** (three systems × Python 3.10/3.13), the release workflow, and **site.yml**: monthly and by hand; the build job
  runs the tool with a read-only token, restores and saves its data in the Actions cache (so only new papers are
  searched), and uploads the site; the deploy job only publishes it to Pages. Actions pinned to commits (cache
  v6.1.0, upload-pages-artifact v5.0.0, deploy-pages v5.0.1). An `OPENALEX_API_KEY` secret is optional.

The trial site was in a temporary folder, deleted after.

Tests: 18. ruff, mypy clean.

Next: the public repository and CI; Pages turned on (a repository setting), then the first full build: without a key
the shared $0.10 a day covers about 2,000 papers a day, so a key from the user would make it days instead of weeks.

### 2026-11-13 — a build that outlasts the day's budget

- A keyless build runs out of OpenAlex's shared daily budget long before 35,000 papers. It used to fail. Now a 429 with
  a long wait (or one that does not lift) marks the budget spent: the matches made so far are kept, papers matched in an
  earlier build keep their last numbers, the rest are listed without numbers, and the data is written as usual; the
  next build, reusing it, carries on. The command line says so. A test runs spent, then funded, then spent again.

Tests: 19.

### 2026-11-13 — public, and the first build

- Checked first: commits by zch6a with the noreply address only, no attribution, no personal paths or names.
- https://github.com/zch6a/paper-impact (public, main), description and topics; CI green (three systems × 3.10/3.13).
- GitHub Pages turned on for the repository (published by the workflow), and the site workflow run by hand: build
  and deploy succeeded. All 26 venue-years read (34,609 papers, as the pages list them); OpenAlex's shared budget on
  the runner's address ran out after 127 requests, with 649 papers matched (NeurIPS 2012 329 of 370, 2013 320 of 360,
  the rest waiting). The budget handling did what it is for: the site went up with what there was.
- Live at https://zch6a.github.io/paper-impact/ (page and data checked).
- At that pace a monthly build would take years to fill, so the build is now **daily**: each run carries on from the
  cached data, about 2,000 papers a run without a key, two or three weeks to fill; a run with nothing new only
  refreshes by ID. With an `OPENALEX_API_KEY` secret (the user's to add) it would take days. READMEs say so.

Next: the five polishing rounds while the data fills (an independent review; the site on real data at phone width;
more venues whose proceedings pages are reachable: ICLR, ACL, CVPR).
