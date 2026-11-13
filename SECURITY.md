# Security

## What it does

- **Talks to two kinds of hosts, over HTTPS only**: the proceedings pages that `venues.json` lists (a link that is
  not `https://` is refused when the list is read), and OpenAlex (`api.openalex.org`). The User-Agent names the tool,
  not the user.
- **The API key**, if any, comes from `OPENALEX_API_KEY` and goes in the `Authorization` header of requests to
  OpenAlex only: never to a proceedings site, never in a URL, the data files, the page or a log line.
- **Stores metadata and links only**: titles, links to each paper's own page, OpenAlex IDs and numbers. No PDF,
  abstract or full text is fetched or kept.
- **The page is inert to the data**: every title and venue is set as text (`textContent`), never as markup, and a
  link is made only when it is `http(s)`; it loads nothing from other sites.
- **The daily workflow** builds in a job with read-only permissions (the optional key is its only secret); the job
  that publishes to GitHub Pages runs no project code, only the official deploy action. Every action is pinned to a
  commit.

## What it does not protect against

- **Wrong data at the source**: a proceedings page that lists a paper wrongly, or OpenAlex counting a paper's
  citations under another record. The page links every number to the OpenAlex record it came from, and says how each
  title was matched.

## Reporting a vulnerability

Please open a private security advisory on GitHub (Security → Report a vulnerability) rather than a public issue.
