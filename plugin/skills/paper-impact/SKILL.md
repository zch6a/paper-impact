---
name: paper-impact
description: "Look up which papers at an AI venue mattered with paper-impact: citations, recent citations, field-weighted citation impact and percentile from OpenAlex for every paper NeurIPS, ICML, ICLR, CVPR and ACL published, by venue and year, with how many of the listed papers were matched. Use when the user asks for the most cited or most influential papers of a venue and year, how a paper did against its venue, or wants to build the same data for another venue list."
license: MIT
compatibility: "Reading needs only HTTPS to zch6a.github.io. Building needs Python 3.10+ and uv; it runs paper-impact with uvx from GitHub (git+https://github.com/zch6a/paper-impact) and reaches the proceedings sites and the OpenAlex API."
metadata:
  homepage: https://github.com/zch6a/paper-impact
---

# Paper impact by venue and year

The data is published daily as open JSON:

- `https://zch6a.github.io/paper-impact/data/index.json`: every venue-year with `listed`, `matched` and its `file`.
- `https://zch6a.github.io/paper-impact/<file>` (e.g. `data/neurips/2017.json`): that venue-year's papers (`title`,
  `url`, `id`, `cited_by_count`, `recent` = citations in the last two complete years, `fwci`, `percentile`, `top1`,
  `top10`, `how`).

Read the index first and give the venue-year's coverage (`matched` of `listed`) with any answer: an unmatched paper
has no numbers, so a "top 10" from a venue-year at low coverage is the top of what was matched, and you must say so.
`how` is `exact`, `later` (the same title on a record OpenAlex dates later, such as a reprint it merged) or `close`
(a nearly identical title): mention a `later` or `close` match when the paper matters to the answer; `id` is the
OpenAlex record, to cite for any number. Numbers are OpenAlex's as of the build date, not Google Scholar's.

To build it for another list (or offline copies):

```bash
uvx --from git+https://github.com/zch6a/paper-impact paper-impact build venues.json -o site --years 2017-2019
```

- `venues.json`: each venue's proceedings page per year (see the repository's for the format). Running it again on
  the same `-o` carries on from the data there.
- Without a key OpenAlex's free budget matches only a few hundred papers a day; a free `OPENALEX_API_KEY` raises it.
  Getting a key is the user's decision: never request one for them, and never put one in a file or a URL.
