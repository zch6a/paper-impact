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

### 2026-11-13 — polishing round 1

**The live site at phone width** (375 px, in the browser pane): the page scrolled sideways (494 px): the venue picker,
with its full name, and the table. Pickers now fit the screen, titles wrap anywhere, cells are tighter, the year
column is hidden on phones (the column sorted by stays); the note starts with a capital letter.

**Independent review** (12 findings, all fixed, tests in `tests/test_review_round1.py`):

1. **The daily build would stall**: papers OpenAlex does not have were searched again every run (about one search
   each), and NeurIPS 2012–2013's 81 misses alone would take most of the keyless budget, so later venue-years would
   never be reached. A miss now records the date (`tried`) and is searched again only after 30 days.
2. A `close` match became `exact` on the next build (the refresh dropped `how`): kept.
3. A work OpenAlex merged or dropped kept its old numbers for ever, never searched again: an ID that no longer comes
   back is searched again.
4. One failing venue-year (a changed page, five network errors) threw away the whole run and the day's budget: it now
   keeps its previous data and is reported, the rest are built and written. A key OpenAlex refuses (401/403) stops
   the run: going on would only fail.
5. Two papers with the same title: the parser dropped the second (it deduplicated by title), and both would have got
   the same record. Now deduplicated by link; papers sharing a normalized title in a venue-year are listed and left
   unmatched. Earlier papers are found again by their link, not their title.
6. Generic titles ("Introduction": 43 exact namesakes on one page) took the most cited stranger: a title of one or two
   words with more than three exact namesakes is left unmatched.
7. The page could show an earlier choice (a slower render finishing last), and a failed load stayed failed until a
   reload: each render has a ticket, a failed load is forgotten and reported; typing in the search box waits 150 ms.
8. A `javascript:` link from a proceedings page would reach `href`: the parser keeps only http(s) links, and the page
   links only http(s) addresses.
9. The year menu offered years a venue does not have (an empty table): it follows the venue.
10. Data of venue-years no longer in the list stayed published: removed; venue-years outside `--years` are carried
    over unchanged instead of dropped.
11. One unknown field in the earlier data discarded all of it (and every match): unknown fields are ignored.
12. Matching: accents and underscores are folded ("Rényi" = "Renyi", `$\ell_1$` = "ell 1"); the looser try also
    needs the words in order ("deep sets" is not "sets deep").

From its "plausible" list: the README says GitHub pauses scheduled workflows after 60 days without activity, and what
the looser tries cost.

Tests: 30 (were 19). ruff, mypy clean.

Next: round 2.

### 2026-11-13 — polishing round 2: two more venues, two passes, the real pace

Round 1's CI was green; its page went live with the next site run (26 venue-years, 903 papers matched, 134 requests).

- **The real pace.** The second run matched only 254 more papers. The README promised about 2,000 a run: wrong. A
  keyless run gets the runner's shared $0.10 (others on that address spend it too), and every miss spent a whole
  search on its looser try. So matching is now **two passes**: exact titles, batched, for every venue-year first;
  then the looser tries, one search each, with whatever budget is left. A paper whose exact search missed is marked
  (`tried: "exact:<date>"`) and goes straight to its looser try next time instead of back into the batches; after
  the looser try it waits 30 days. The README states the measured pace: months without a key, weeks at most with one.
- **CVPR** (CVF open access, 2013–2025) and **ACL** (Anthology, long papers 2013–2025; 2020's main volume): two
  parsers (`cvf`: `dt.ptitle > a`; `acl`: `strong > a.align-middle`, the volume's own entry skipped), tested on
  synthetic pages. Every page checked once (no OpenAlex calls): ACL from 175 (2013) to 1,602 (2025); CVPR from 471
  (2013) to 2,871 (2025).
- **CVPR 2018–2020 read 0 papers**: those years list their papers by day (`CVPR2019.py?day=2019-06-18` …) and the
  `?day=all` page is empty. A venue-year may now name several listing pages (`lists`), its `url` staying the page a
  reader is sent to; read that way: 979, 1,294, 1,466. And a venue-year whose pages list no papers is refused
  ("lists no papers") instead of published empty.
- In all, venues.json lists 60,234 papers: NeurIPS and ICML 34,609, CVPR 18,452, ACL 7,173.

Tests: 32 (were 30). ruff, mypy clean.

Next: round 3.

### 2026-11-13 — polishing round 3

- **ICLR** has no proceedings site beyond OpenReview (whose API answers 403), but its conference site's papers page
  (`iclr.cc/virtual/<year>/papers.html`) carries a plain list of links to each paper's page (inside `<noscript>`).
  A `virtual` parser reads it; ICLR 2021–2025: 860, 1,095, 1,584, 2,296, 3,827 (2021 and 2022 equal the accepted
  counts; 2024–2025 run a little above, as that page lists them).

**Second independent review** (5 confirmed, 2 plausible, all fixed; tests in `tests/test_review_round2.py`):

1. The looser pass matched short generic titles the exact pass had refused ("Introduction" → the most cited of five
   namesakes): the looser try is never made for titles of one or two words.
2. A title that became shared on a later day kept its "exact:" mark and the looser pass matched both papers to one
   record: a shared title carries no mark and the looser pass skips it.
3. ACL 2013–2019 counted each volume's front matter as a paper (old identifiers end in `000`, e.g. `P17-1000`): skipped
   now, seven entries fewer.
4. Reading back the earlier data was quadratic (4,500 papers: 160 s; about 15 minutes of CPU every daily build):
   linear now (5,000 papers in under a second in the test).
5. The workflow's comment still promised 2,000 papers a run: the measured pace.
6. (plausible) The looser pass walked the venues in order, so later ones could wait for ever: it now takes the longest
   waiting first, across venue-years.
7. (plausible) A title changed on the same link kept the old paper's record or mark: a changed title is looked up
   afresh.

Also: the README says ACL 2020 is its main volume (long and short papers). venues.json now lists 69,889 papers
(NeurIPS and ICML 34,609, ICLR 9,662, CVPR 18,452, ACL 7,166).

Tests: 39 (were 32). ruff, mypy clean.

Next: round 4.

### 2026-11-13 — polishing round 4

Checked: the live site (26 venue-years, 903 of 34,609 matched so far, the keyless budget); a fresh
`uvx --from git+https://github.com/zch6a/paper-impact` install (`--version`, `build --help`); no subprocess, eval,
pickle or innerHTML in the source; versions agree (0.1.0).

**AlexNet was matched to the wrong record.** Making the social card from the live site showed NeurIPS 2012 topped by
word2vec, with AlexNet nowhere near: it had been matched to a minor 2012 record with 830 citations, because OpenAlex
dates AlexNet's main record, 114,706 citations, 2017 (it merged the CACM reprint into it), outside the one-year
window. Any paper republished later (CACM research highlights, journal versions OpenAlex merged) was undercounted the
same way.

- The exact search now takes records of the same title dated later too, for titles of five words or more (shorter
  ones have namesakes in other years); the most cited record still wins, and one dated after the window is marked
  `later` ("later record" on the page). Measured on one real batch: 23 results instead of 18, the same cost.
- The search asks for the most cited first: a title's best records can no longer fall past a cut page (before, a
  title that found a lesser record on the page was never retried).
- Each venue-year's data records the matching rule it was made under (`rule`, now 2): exact matches made under an
  older rule are searched again (20 titles a search: the 903 matched so far cost about 45 searches); close matches
  and misses keep theirs.
- A title with an underscore (`Minimum $L_p$ Loss`) was searched as the words "l p", which OpenAlex's one token
  `l_p` never matches as a phrase: such titles had matched only under round 1's normalization, and re-matching would
  have lost them. The phrase searched is now cut before the first word with an underscore (when four words or more
  come before it); exactness is still checked on the whole title. Measured: 19 of the same 20 real titles match,
  AlexNet now with its main record, nothing else changed.
- The page now links each citation count to the OpenAlex record it came from and tags `later` and `close` matches
  (with a tooltip saying what they mean): SECURITY.md's claim that it does is now true.

Also: SECURITY.md (the hosts contacted, the key only to OpenAlex, the inert page, the workflow's split), CONTRIBUTING
(module map, adding a venue, the rules), CHANGELOG, the plugin Skill (reads the published JSON, checked against the
live files: `file` is relative to the site, not to `data/`), the social card and a screenshot of the site at the top
of the README (both from a local copy of the live data with AlexNet as the fixed matcher gives it, the real record);
pyproject's comment about "templates for the SVG" (copied from scholar-cards) corrected.

Tests: 48 (were 39). ruff, mypy clean.

Next: round 5 (a third independent review), then v0.1.0.

### 2026-11-13 — polishing round 5

The round-4 rebuild went live: AlexNet now shows its main record (114,706 citations, rule 2), the underscore title
kept its match, and the site has 57 venue-years (ICLR, CVPR, ACL now in), 1,647 of 69,889 papers matched.

**Third independent review** (5 confirmed, 2 plausible, all fixed; tests in `tests/test_review_round3.py`):

1. A rule upgrade on a spent budget wiped the old exact matches (and stamped the new rule anyway): the 903 live matches
   survived today only because the budget lasted. Old matches are now kept until a new search replaces them, and the
   new rule is stamped only when every one of them was searched again.
2. The looser try for a title of one or two words could never match, but its search was still paid for (every 30
   days): no search now.
3. A looser match could take a record another paper of the venue-year already held exactly (one record's citations
   shown twice, the coverage inflated): refused now.
4. The ICLR parser merged two different papers of one title (it removed repeats by title, meant for an oral listed
   under its oral and its poster page): only an oral-and-poster pair is one paper now.
5. Odd saved data or an odd venue list: one damaged paper entry threw away its whole venue-year (skipped alone now); a
   data file that is a JSON list, or `pages` given as a list, crashed with a traceback (read as no data / a clean
   error now).
6. (plausible) A key refused midway threw away the whole run's matches: the build now writes what it built (the
   venue-years not reached carried over) and exits 2; the workflow keeps that data in the cache; a refusal without a
   key no longer asks whether the key is right.
7. (plausible) A re-run of the site workflow saved its data under the first attempt's cache key (a collision, so the
   data was not kept): the key now includes the attempt.

Checked by hand that the refused-key test fails for the right reason (the first version passed through the looser
pass by accident: rewritten, and confirmed the stop comes from the venue-year itself).

Also: release.yml's comment promised `zch6a/paper-impact@v0` for workflows (this project has no action): it is for
`uvx --from git+...@v0`; the sdist checked (docs/ excluded); CHANGELOG dated.

Tests: 58 (were 48). ruff, mypy clean.

Next: release v0.1.0.

### 2026-11-14 — Chinese README: AI tone

1 place changed: a 「而不是」 correction (报错，而不是悄悄混进另一个会议) stated directly as 不会.
The checks follow the findings of lieflat-less-ai-tone (shiujan, CC BY-NC 4.0); its findings are applied, its text is not copied.
Left as is: the colon-led list of why citation counts scatter, the semicolon list of rebuild steps after a colon, venue enumerations, tables, and the tool links.

### 2026-11-14 — v0.1.1

Putting every tool's skill into one marketplace (research-kit) and running `claude plugin validate` on each
showed this one's SKILL.md frontmatter did not parse: a plain YAML value with `: ` inside ("…: text size…")
starts a new key, so Claude Code loaded the skill with no description, and an agent would never pick it. The
description and compatibility values are quoted (a JSON string is a YAML double-quoted scalar); validation passes.
Released as 0.1.1 so that `v0`, which the marketplace installs from, carries the fix.

### 2026-11-14 — a link to research-kit

Both READMEs now end (before the licence) with a short section pointing to research-kit, the toolkit's front door: all
thirteen tools in the order of the work, and one Claude Code plugin marketplace for their skills. Documentation only.

### 2026-11-14 — 0.2.0: paper-impact today

From research-kit's list: "rank the daily feed by signs that a paper will matter: accepted venue, released code,
early citations" (recommenders score closeness to your topics only).

`today.py`: arXiv's API by category and submission date, signs from the comment and abstract, OpenAlex citations by
the arXiv DOI (50 to a request), a stable ranking (score, then newest).

Checked by hand on real days (to 2026-11-14): cs.CL, 60 papers. Every sign shown was right (7 acceptances, 17 code);
4 acceptances were missed because the venue was not in the list or had no year ("Accepted to IEEE TASLP 2026",
"Published at the 19th ... INLG", "Accepted for publication in PMLR", "WSDM camera ready"). Now any acceptance phrase
counts, with the venue's words. cs.CV, 86 papers: 18 acceptances, all genuine (WACV, BMVC, ICME, ACM MM, CoRL,
workshops marked), 29 code signs, all genuine; one abstract's link was a placeholder ("github.com."), and the phrase
"code is available" was shown where a link followed it: the link is shown now. Bare "NeurIPS 2026" comments are left
out on purpose (a submission or an acceptance?). 3 tests with a made-up arXiv feed and OpenAlex.
