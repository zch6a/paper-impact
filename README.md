<div align="center">

# paper-impact

**Which papers at AI venues mattered: every paper NeurIPS, ICML, CVPR and ACL published, with its citations and field-normalized
impact, by year.** The paper lists come from each venue's own proceedings; the numbers from
[OpenAlex](https://openalex.org) (open, CC0). Open JSON and a static site, rebuilt daily.

<a href="https://github.com/zch6a/paper-impact/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/zch6a/paper-impact/actions/workflows/ci.yml/badge.svg"></a>
<img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue">
<img alt="No dependencies" src="https://img.shields.io/badge/dependencies-none-2ea44f">
<a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-blue"></a>

**English** · [简体中文](README.zh-CN.md)

</div>

---

Citation counts of conference papers are scattered: a paper's preprint and its proceedings version are separate
records, venues are filed inconsistently (OpenAlex's own "International Conference on Learning Representations"
source holds 602 works), and raw counts favour older papers and bigger fields. paper-impact starts from what each
venue's proceedings list, finds each paper in OpenAlex, and shows OpenAlex's field-normalized numbers next to the raw
count, saying how much it found.

ICML 2017, as built (434 papers in the proceedings):

| | |
|---|---|
| found in OpenAlex | 418 (96%), in 39 requests (the page, 22 searches of exact titles, 16 looser tries for the misses) |
| most cited | Model-Agnostic Meta-Learning (9,057), Wasserstein GAN (6,442), Neural Message Passing for Quantum Chemistry (5,745) |
| with FWCI and percentile | 135 of the 418 (OpenAlex gives them for some records only, not for preprint records) |

## The site

Pick a venue and a year (or all years), sort by citations, field-normalized percentile, FWCI or citations in the last
two years, search titles. Each venue-year links its proceedings and says how many of its papers were found; papers
not found are listed without numbers. The data is public: `data/index.json` and one file per venue-year.

## Build it

```bash
uvx --from git+https://github.com/zch6a/paper-impact paper-impact build venues.json -o site/ --years 2015-2024
```

[venues.json](venues.json) lists NeurIPS 2012–2024, ICML 2013–2025 (PMLR), CVPR 2013–2025 (CVF open access) and ACL
2013–2025 (long papers; 2020's main volume) by their proceedings pages, 60,234 papers; each page names the
text it must contain (the venue, the year), so a wrong volume fails instead of bringing in another conference.

- **Matching**: titles are searched in OpenAlex about 20 to a search, accepted only on the exact title (normalized)
  within a year of the venue's; a miss gets one looser try (85% of the words, the length close), marked `close` in
  the data. Of a preprint and a proceedings record, the more cited one is shown, the other kept in `also` (not added:
  OpenAlex counts them apart).
- **Cost**: a search is $0.001 of OpenAlex's budget: a venue-year of 1,000 papers is about 50 searches, plus one looser
  try per miss ($0.05 to $0.15). A paper searched for in vain is searched again only after 30 days. Without
  `OPENALEX_API_KEY` the budget is $0.10 a day shared by everyone on your IP address; a free key gives $1. A rebuild
  reuses the data already in `site/`: only papers not yet found are searched, the others refreshed by ID (100 to a
  request, $0.0001); a paper whose OpenAlex ID no longer comes back is searched again. A venue-year whose page fails
  (it changed, the site is down) keeps its previous data and is reported; the others are built. Two papers with the
  same title in one venue-year are both listed, neither matched (one record cannot be told apart for two papers);
  so are very short titles with many namesakes ("Introduction").
- **The daily build** ([site.yml](.github/workflows/site.yml)): the build job runs with a read-only token and keeps
  its data in the Actions cache; the deploy job only publishes to Pages. Each run searches exact titles first, in
  batches, for every venue-year, and spends what budget is left on the looser tries. Without a key the budget is the
  runner's shared $0.10, and the first runs matched about 250 to 650 papers each, so the site fills over months; an
  `OPENALEX_API_KEY` secret (1,000 searches a day, about 20,000 titles) makes it weeks at most.

## What the numbers are

| | |
|---|---|
| Citations | OpenAlex's count for the matched record |
| FWCI | field-weighted citation impact: 1.0 is the world average for works of the same field, type and year |
| Percentile | OpenAlex's `citation_normalized_percentile`, with its top 1% / top 10% flags |
| Recent | citations in the last two complete years, from OpenAlex's counts by year |

## Limits

- Only what OpenAlex has: about 4% of ICML 2017's papers are not there under their title, and a paper whose citations
  are split across records shows one record's count.
- FWCI and the percentile exist for a minority of conference papers (often not for preprint records); sorting by
  them ranks those, the rest come last, and the page says how many.
- A venue appears once its proceedings are posted: NeurIPS 2025 is left out while only its Creative AI track is up.
- GitHub pauses scheduled workflows in a repository with no activity for 60 days; the daily build then waits for a
  commit or a run by hand (the cached data is kept for 7 days unused).

## Also in this toolkit

[paper-proof](https://github.com/zch6a/paper-proof) checks a paper's references and numbers;
[submit-check](https://github.com/zch6a/submit-check) checks it against a venue's rules;
[arxiv-diff](https://github.com/zch6a/arxiv-diff) shows what changed between versions;
[exp-tables](https://github.com/zch6a/exp-tables) turns results into tables with honest bold;
[scholar-cards](https://github.com/zch6a/scholar-cards) puts a researcher's numbers on their homepage.

## License

MIT for the code. The data is OpenAlex's (CC0) and the venues' proceedings listings (titles and links).
