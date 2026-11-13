"""paper-impact: which papers at AI venues mattered, as open JSON and a static site. The papers are what each venue's
proceedings list; their citations and field-normalized impact are OpenAlex's.

paper-impact build venues.json -o site/ --years 2015-2025     read the proceedings, match the papers, write the site

Matching titles is an OpenAlex search ($0.001 each; about one per 20 papers). Without OPENALEX_API_KEY the budget is
$0.10 a day shared by everyone on your IP address; a free key gives $1. A rebuild only searches papers it has not
matched before, and refreshes the others by ID.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from . import __version__
from .build import build, read_venues, write_data
from .openalex import Client, OpenAlexError
from .site import write_site


def _years(text: str) -> range:
    """2015-2025 or 2020.

    >>> _years("2015-2017"), _years("2020")
    (range(2015, 2018), range(2020, 2021))
    """
    first, _, last = text.partition("-")
    if not first.isdigit() or (last and not last.isdigit()):
        raise argparse.ArgumentTypeError(f"years are 2015-2025 or 2020, not {text!r}")
    a, b = int(first), int(last or first)
    if not 1900 <= a <= b <= 2100:
        raise argparse.ArgumentTypeError(f"years run forward between 1900 and 2100, not {text!r}")
    return range(a, b + 1)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="paper-impact", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="exit status: 0 done, 2 an error")  # fmt: skip
    ap.add_argument("--version", action="version", version=f"paper-impact {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="read the proceedings, match the papers in OpenAlex, write the data and the site")
    b.add_argument("venues", type=Path, help="the venue list (JSON)")
    b.add_argument("-o", "--out", type=Path, default=Path("site"), help="the site's folder (default site/); its data is reused")
    b.add_argument("--years", type=_years, default=_years(f"2012-{dt.date.today().year}"), help="e.g. 2015-2025 (default 2012 to this year)")
    args = ap.parse_args(argv)
    try:
        client = Client()
        venues = read_venues(args.venues)
        today = dt.date.today()
        venue_years = build(venues, args.years, client, today.year, args.out)
        write_data(args.out, venues, venue_years, today.isoformat())
        write_site(args.out)
        listed = sum(len(vy.papers) for vy in venue_years)
        matched = sum(vy.matched for vy in venue_years)
        print(f"paper-impact: {len(venue_years)} venue-years, {listed} papers, {matched} matched in OpenAlex "
              f"({100 * matched / listed if listed else 0:.0f}%), {client.calls} requests -> {args.out.as_posix()}/")  # fmt: skip
        if client.exhausted:
            print("paper-impact: OpenAlex's daily budget ran out: the papers not matched yet are listed without numbers, and the next "
                  "build (reusing this one's data) carries on; a free OPENALEX_API_KEY makes the budget ten times larger")  # fmt: skip
    except (OpenAlexError, OSError, ValueError) as e:
        print(f"paper-impact: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
