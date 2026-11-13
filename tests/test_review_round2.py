"""Regression tests for what the round-2 review (the second) found."""

from __future__ import annotations

import datetime as dt
import time

from test_impact import NEURIPS, FakeWeb, work

from paper_impact.build import Venue, VenueYear, _close_pass, build_venue_year
from paper_impact.match import close_match
from paper_impact.model import Paper
from paper_impact.openalex import Client
from paper_impact.proceedings import parse

URL = "https://papers.nips.cc/paper_files/paper/2017"
VENUE = Venue("NeurIPS", "", "neurips", {2017: URL})


def test_the_looser_try_never_matches_a_short_title() -> None:
    answer = {"meta": {"count": 5}, "results": [work(i, "Introduction", 100 * i) for i in range(1, 6)]}
    assert close_match(["Introduction"], 2017, lambda p: answer)["introduction"].work is None


def test_a_title_that_becomes_shared_is_not_matched_by_the_looser_pass() -> None:
    page1 = '<a title="paper title" href="/h/a">Learning to Learn Quickly Everywhere</a>'
    page2 = page1 + '<a title="paper title" href="/h/b">Learning to Learn Quickly Everywhere</a>'
    venue = Venue("NeurIPS", "", "neurips", {2017: URL})
    answers = {"https://papers.nips.cc/paper_files/paper/2017": page1}
    first = build_venue_year(venue, 2017, Client(key="", get=FakeWeb(answers), sleep=lambda _: None), 2026, [], today=dt.date(2026, 11, 1))
    assert first.papers[0].tried.startswith("exact:")
    answers2 = {"https://papers.nips.cc/paper_files/paper/2017": page2}
    second = build_venue_year(
        venue, 2017, Client(key="", get=FakeWeb(answers2), sleep=lambda _: None), 2026, first.papers, today=dt.date(2026, 11, 2)
    )
    assert [p.tried for p in second.papers] == ["", ""]  # shared now: no mark carried over
    calls: list[str] = []
    client = Client(key="", get=lambda u, h: (calls.append(u), (200, {}, b'{"meta":{"count":0},"results":[]}'))[1], sleep=lambda _: None)
    _close_pass([second], client, 2026)
    assert calls == [] and not any(p.id for p in second.papers)


def test_acl_front_matter_of_old_volumes_is_not_a_paper() -> None:
    page = """<strong><a class=align-middle href=/P17-1000/>Proceedings of the 55th Annual Meeting (Volume 1: Long Papers)</a></strong>
<strong><a class=align-middle href=/P17-1001/>Adversarial Multi-task Learning for Text Classification</a></strong>"""
    assert [p.title for p in parse("acl", page, "https://aclanthology.org/volumes/P17-1/")] == [
        "Adversarial Multi-task Learning for Text Classification"
    ]


def test_reading_back_thousands_of_papers_is_fast() -> None:
    previous = [Paper(f"A Paper About Topic Number {i}", 2017, f"https://x/{i}", tried="2026-11-01") for i in range(5000)]
    page = "".join(f'<a title="paper title" href="/{i}">A Paper About Topic Number {i}</a>' for i in range(5000))
    web = FakeWeb({URL: page})
    start = time.perf_counter()
    build_venue_year(VENUE, 2017, Client(key="", get=web, sleep=lambda _: None), 2026, previous, today=dt.date(2026, 11, 2))
    assert time.perf_counter() - start < 5  # was quadratic: minutes


def test_a_changed_title_on_the_same_link_is_looked_up_afresh() -> None:
    old = Paper("Alpha Paper Old Title Here", 2017, "https://papers.nips.cc/paper_files/paper/2017/hash/a-Abstract.html").with_work(
        work(1, "x", 9), 2026
    )
    vy = build_venue_year(VENUE, 2017, Client(key="", get=FakeWeb({URL: NEURIPS}), sleep=lambda _: None), 2026, [old])
    assert vy.papers[0].title == "Sparse Attention for Long Documents" and vy.papers[0].cited_by_count == 500  # its own record, not the old one


def test_the_looser_pass_takes_the_longest_waiting_first() -> None:
    a = VenueYear("A", 2017, "u", [Paper("A Paper Waiting Since November", 2017, "a", tried="exact:2026-11-10")])
    b = VenueYear("B", 2017, "u", [Paper("A Paper Waiting Since October", 2017, "b", tried="exact:2026-10-01")])
    order: list[str] = []

    def get(url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        order.append(url)
        return (200, {}, b'{"meta":{"count":0},"results":[]}') if len(order) == 1 else (429, {"retry-after": "40000"}, b"{}")

    _close_pass([a, b], Client(key="", get=get, sleep=lambda _: None), 2026, today=dt.date(2026, 11, 12))
    assert "october" in order[0] and b.papers[0].tried == "2026-11-12" and a.papers[0].tried == "exact:2026-11-10"
