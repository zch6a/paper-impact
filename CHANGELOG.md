# Changelog

## 0.2.0 — 2026-11-14

- **`paper-impact today CATEGORY`**: the newest arXiv submissions to a category, ranked by the signs each paper shows
  about itself: accepted at a venue (from the arXiv comment, any venue; a workshop counts for less), code released (a
  repository, model or project-page link, or "code is available"), and with `--citations` OpenAlex's citation count by
  the arXiv DOI. `--days`, `--limit`, `--top`, `--format text|markdown|json`. arXiv is asked once per 100 papers,
  three seconds apart. Checked by hand on cs.CL and cs.CV: every sign shown was genuine.
- A CITATION.cff.

## 0.1.1 — 2026-11-14

- The agent skill's frontmatter is valid YAML again: its description held a `: `, which YAML reads as a new key, so
  the whole frontmatter failed to parse and the skill loaded without its description (`claude plugin validate`
  reported it). The values are quoted now.

## 0.1.0 — 2026-11-13

First release.

- `paper-impact build venues.json -o site`: reads each venue's proceedings pages (NeurIPS, PMLR, CVF, ACL Anthology,
  ICLR's conference site), matches every title to OpenAlex, and writes open JSON (one file per venue and year) and a
  static site.
- Per paper: citations, citations in the last two complete years, field-weighted citation impact, percentile, top 1% / 10%,
  and how the title was matched (exact; on a record OpenAlex dates later; or nearly), with the OpenAlex record
  linked.
- Per venue and year: papers listed, papers matched, coverage.
- Each build carries on from the last: matched papers are refreshed by ID; unmatched ones are searched again after
  30 days; a build stopped by the day's budget keeps what it found.
- `venues.json`: NeurIPS 2012–2024, ICML 2013–2025, ICLR 2021–2025, CVPR 2013–2025, ACL 2013–2025 (69,889 papers).
- A daily GitHub workflow rebuilds the site at https://zch6a.github.io/paper-impact/.
