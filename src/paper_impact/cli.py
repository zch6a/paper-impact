"""paper-impact: which papers at AI venues mattered, from OpenAlex, as open JSON and a static site.

paper-impact build venues.json -o site/ --years 2015-2025     fetch, write site/data/*.json and site/index.html
paper-impact sources "Neural Information Processing Systems"   find a venue's OpenAlex source IDs for venues.json

Without OPENALEX_API_KEY each venue-year holds its 200 most cited papers (OpenAlex pages only with a free key);
with it, all of them.
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
                                 epilog="exit status: 0 done, 1 nothing found, 2 an error")  # fmt: skip
    ap.add_argument("--version", action="version", version=f"paper-impact {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="fetch the venue-years and write the data and the site")
    b.add_argument("venues", type=Path, help="the venue list (JSON)")
    b.add_argument("-o", "--out", type=Path, default=Path("site"), help="the site's folder (default site/)")
    b.add_argument("--years", type=_years, default=_years(f"2012-{dt.date.today().year - 1}"), help="e.g. 2015-2025 (default 2012 to last year)")
    b.add_argument("--top", type=int, help="the most cited N per venue-year (default: 200 without a key, all with one)")
    s = sub.add_parser("sources", help="find a venue's OpenAlex source IDs")
    s.add_argument("name")
    args = ap.parse_args(argv)
    try:
        client = Client()
        if args.command == "sources":
            found = client.sources(args.name)
            for src in found:
                short = str(src.get("id", "")).rsplit("/", 1)[-1]
                print(f"{short:12} {src.get('display_name', '')}  ·  {src.get('type', '')}  ·  {src.get('works_count', 0)} works")
            return 0 if found else 1
        if args.top is not None and not 1 <= args.top <= 200:
            ap.error("--top is from 1 to 200")
        top = args.top if args.top is not None else (None if client.key else 200)
        venues = read_venues(args.venues)
        today = dt.date.today()
        venue_years = build(venues, args.years, client, top, today.year)
        write_data(args.out, venues, venue_years, today.isoformat())
        write_site(args.out)
        partial = sum(not vy.complete for vy in venue_years)
        print(f"paper-impact: {len(venue_years)} venue-years, {sum(len(vy.papers) for vy in venue_years)} papers, {client.calls} requests -> "
              f"{args.out.as_posix()}/" + (f" ({partial} venue-years hold only their most cited papers)" if partial else ""))  # fmt: skip
    except (OpenAlexError, OSError, ValueError) as e:
        print(f"paper-impact: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
