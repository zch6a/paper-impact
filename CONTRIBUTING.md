# Contributing

```bash
uv sync
uv run pytest -q          # tests never touch the network: they hand the client a fake web
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

## Where things are

| Module | What it does |
| --- | --- |
| `model.py` | `Paper` (a listed paper and its numbers) and `VenueYear` (one venue's list for one year, with coverage) |
| `openalex.py` | the HTTP client: retries, waits when told, stops cleanly when the day's budget is spent; `page()` fetches a proceedings page without the key |
| `proceedings.py` | one parser per kind of proceedings site (`neurips`, `pmlr`, `cvf`, `acl`, `virtual`): titles and links |
| `match.py` | title matching: the exact pass (batched searches, same year, exact normalized title) and the looser try |
| `build.py` | `venues.json`, one venue-year at a time, carrying on from the previous build's data; writes the JSON files |
| `site.py` | the static page (one file, its own script; reads the JSON) |
| `cli.py` | `paper-impact build` |

## Adding a venue or a year

Add it to `venues.json`. A year is a link to its proceedings page, or `{"url": ..., "expect": ..., "lists": [...]}`
when the page must be checked for a phrase (a wrong year's page answers with 200 too) or the list is split over
several pages. If the site is a kind no parser reads, add a parser to `proceedings.py` with a small fixture in the
tests, and check a real page by hand: how many papers it gives, against the venue's own accepted count.

## Rules the project keeps

- Public pages and APIs only, at their pace; nothing behind a bot check.
- Metadata and links only: no PDFs, abstracts or full text in the repository or the data.
- Tests use made-up data and never the network.
