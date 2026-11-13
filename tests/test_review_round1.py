"""Regression tests for what the round-1 review found."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from test_impact import NEURIPS, WORKS, FakeWeb, work

from paper_impact.build import Venue, build, build_venue_year, read_previous, write_data
from paper_impact.match import match, normalize
from paper_impact.model import Paper
from paper_impact.openalex import Client, KeyRejected
from paper_impact.proceedings import parse
from paper_impact.site import PAGE

URL = "https://papers.nips.cc/paper_files/paper/2017"
VENUE = Venue("NeurIPS", "", "neurips", {2017: URL})


def client(web: FakeWeb) -> Client:
    return Client(key="", get=web, sleep=lambda _: None)


def test_a_miss_waits_for_its_looser_try_then_for_weeks() -> None:
    from paper_impact.build import _close_pass

    web = FakeWeb({URL: NEURIPS})
    vy = build_venue_year(VENUE, 2017, client(web), 2026, [], today=dt.date(2026, 11, 1))
    assert vy.papers[2].id == "" and vy.papers[2].tried == "exact:2026-11-01"  # the exact pass missed it
    web2 = FakeWeb({URL: NEURIPS})
    again = build_venue_year(VENUE, 2017, client(web2), 2026, vy.papers, today=dt.date(2026, 11, 2))
    assert not any("title.search" in u for u, _ in web2.calls) and again.papers[2].tried == "exact:2026-11-01"  # not exact-searched again
    c = client(FakeWeb({}))
    _close_pass([again], c, 2026, today=dt.date(2026, 11, 2))
    assert again.papers[2].tried == "2026-11-02" and c.calls == 1  # its looser try, once
    web3 = FakeWeb({URL: NEURIPS})
    build_venue_year(VENUE, 2017, client(web3), 2026, again.papers, today=dt.date(2026, 11, 20))
    assert not any("title.search" in u for u, _ in web3.calls)  # weeks later: still waiting
    web4 = FakeWeb({URL: NEURIPS})
    later = build_venue_year(VENUE, 2017, client(web4), 2026, again.papers, today=dt.date(2026, 12, 5))
    assert any("lacks" in u for u, _ in web4.calls) and later.papers[2].tried == "exact:2026-12-05"  # a month on: once more


def test_a_close_match_stays_close_on_refresh() -> None:
    previous = [Paper("Sparse Attention for Long Documents", 2017, f"{URL}/../hash/a-Abstract.html").with_work(WORKS[0], 2026, [], "close")]
    previous[0].url = "https://papers.nips.cc/paper_files/paper/2017/hash/a-Abstract.html"
    vy = build_venue_year(VENUE, 2017, client(FakeWeb({URL: NEURIPS})), 2026, previous)
    assert vy.papers[0].how == "close" and vy.papers[0].cited_by_count == 500


def test_an_id_openalex_no_longer_returns_is_searched_again() -> None:
    gone = Paper("Sparse Attention for Long Documents", 2017, "https://papers.nips.cc/paper_files/paper/2017/hash/a-Abstract.html").with_work(
        work(99, "Sparse attention for long documents", 10), 2026
    )
    web = FakeWeb({URL: NEURIPS})
    vy = build_venue_year(VENUE, 2017, client(web), 2026, [gone])
    assert vy.papers[0].id == "https://openalex.org/W1" and vy.papers[0].cited_by_count == 500  # found again, not the stale W99


def test_a_failing_venue_year_keeps_its_previous_data_and_the_rest_build(tmp_path: Path) -> None:
    venues = [
        VENUE,
        Venue("ICML", "", "pmlr", {2017: "https://proceedings.mlr.press/v70/"}, {2017: ["International Conference on Machine Learning"]}),
    ]
    vys, failures = build(
        venues, range(2017, 2018), client(FakeWeb({URL: NEURIPS, "https://proceedings.mlr.press/v70/": "<p>changed</p>"})), 2026, tmp_path
    )
    assert [vy.venue for vy in vys] == ["NeurIPS"] and failures[0].venue == "ICML"
    write_data(tmp_path, venues, vys, "2026-11-13")
    assert (tmp_path / "data" / "neurips" / "2017.json").exists()


def test_a_rejected_key_stops_the_run(tmp_path: Path) -> None:
    class Refused(FakeWeb):
        def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
            if url.startswith("https://api.openalex.org"):
                return 401, {}, b'{"error": "invalid key"}'
            return super().__call__(url, headers)

    with pytest.raises(KeyRejected):
        build([VENUE], range(2017, 2018), Client(key="bad", get=Refused({URL: NEURIPS}), sleep=lambda _: None), 2026, tmp_path)


def test_papers_sharing_a_title_are_both_listed_and_neither_gets_a_record() -> None:
    page = NEURIPS.replace("Calibrated Uncertainty, Revisited", "Sparse attention for long documents")
    listed = parse("neurips", page, URL)
    assert len(listed) == 3  # two papers, one title: both kept (they have their own links)
    vy = build_venue_year(VENUE, 2017, client(FakeWeb({URL: page})), 2026, [])
    assert vy.papers[0].id == "" and vy.papers[1].id == ""


def test_generic_titles_with_many_namesakes_are_not_matched() -> None:
    answer = {"meta": {"count": 5}, "results": [work(i, "Introduction", 100 * i) for i in range(1, 6)]}
    assert match(["Introduction"], 2017, lambda p: answer, close=False)["introduction"].work is None
    assert (
        match(["Deep Sets"], 2017, lambda p: {"meta": {"count": 2}, "results": [work(1, "Deep Sets", 9), work(2, "Deep sets", 3)]})["deep sets"].work
        is not None
    )


def test_links_are_only_http_and_the_page_never_makes_a_javascript_link() -> None:
    page = '<a title="paper title" href="javascript:alert(1)">Evil</a>'
    assert parse("neurips", page, URL)[0].url == ""
    assert "function safe(url)" in PAGE and "/^https?:" in PAGE


def test_venue_years_no_longer_listed_are_removed_and_old_data_with_new_fields_still_reads(tmp_path: Path) -> None:
    (tmp_path / "data" / "old").mkdir(parents=True)
    (tmp_path / "data" / "old" / "2010.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data" / "neurips").mkdir()
    papers = [{"title": "T", "year": 2017, "id": "https://openalex.org/W1", "cited_by_count": 3, "a_later_field": 1}]
    (tmp_path / "data" / "neurips" / "2017.json").write_text(json.dumps({"source": URL, "papers": papers}), encoding="utf-8")
    source, previous, _ = read_previous(tmp_path, VENUE, 2017)
    assert source == URL and previous[0].cited_by_count == 3  # an unknown field does not throw everything away
    vys, _ = build([VENUE], range(2030, 2031), client(FakeWeb({})), 2026, tmp_path)  # outside --years: carried over
    write_data(tmp_path, [VENUE], vys, "2026-11-13")
    assert not (tmp_path / "data" / "old").exists() and (tmp_path / "data" / "neurips" / "2017.json").exists()


def test_accents_and_underscores_match() -> None:
    assert normalize("Rényi Differential Privacy") == normalize("Renyi differential privacy")
    assert normalize("$\\ell_1$ minimization") == normalize("ell 1 minimization")
