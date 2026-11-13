"""Round 4: AlexNet (NeurIPS 2012) was matched to a minor 2012 duplicate with 830 citations, because OpenAlex dates its
main record, with 114,706 citations, 2017 (it merged the CACM reprint). Records dated later now count, marked "later";
data matched under the older rule is matched again."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from test_impact import FakeWeb, work

from paper_impact.build import Venue, build_venue_year, read_previous, write_data
from paper_impact.match import RULE, match, normalize
from paper_impact.model import Paper, VenueYear
from paper_impact.openalex import Client
from paper_impact.site import PAGE

ALEXNET = "ImageNet Classification with Deep Convolutional Neural Networks"
URL = "https://papers.nips.cc/paper_files/paper/2012"
PAGE_2012 = (
    f'<a title="paper title" href="/h/alexnet">{ALEXNET}</a><a title="paper title" href="/h/b">Practical Bayesian Optimization of Learning</a>'
)
VENUE = Venue("NeurIPS", "", "neurips", {2012: URL})


def answer(*works: dict[str, object]) -> dict[str, object]:
    return {"meta": {"count": len(works)}, "results": list(works)}


def test_a_main_record_dated_later_wins_and_says_so() -> None:
    found = match([ALEXNET], 2012, lambda p: answer(work(2, ALEXNET, 114706, 2017), work(1, ALEXNET, 830, 2012)))
    m = found[normalize(ALEXNET)]
    assert m.work["id"] == "https://openalex.org/W2" and m.how == "later" and m.also == ["https://openalex.org/W1"]  # type: ignore[index]


def test_an_in_window_record_that_is_more_cited_stays_exact() -> None:
    found = match([ALEXNET], 2012, lambda p: answer(work(1, ALEXNET, 9000, 2012), work(2, ALEXNET, 40, 2019)))
    assert found[normalize(ALEXNET)].how == "exact" and found[normalize(ALEXNET)].work["id"] == "https://openalex.org/W1"  # type: ignore[index]


def test_a_short_title_never_takes_a_later_namesake() -> None:
    calls: list[dict[str, str]] = []

    def search(p: dict[str, str]) -> dict[str, object]:
        calls.append(p)
        return answer(work(2, "Learning to Rank Fast", 5000, 2019))

    assert match(["Learning to Rank Fast"], 2012, search, close=False)["learning to rank fast"].work is None


def test_the_search_asks_for_the_most_cited_first_and_any_later_year() -> None:
    calls: list[dict[str, str]] = []
    match([ALEXNET], 2012, lambda p: (calls.append(p), answer())[1], close=False)
    assert calls[0]["sort"] == "cited_by_count:desc" and calls[0]["filter"].endswith(",publication_year:>2010")


def _client(web: FakeWeb) -> Client:
    return Client(key="", get=web, sleep=lambda _: None)


def test_exact_matches_under_an_older_rule_are_made_again_and_close_ones_kept() -> None:
    old_exact = Paper(ALEXNET, 2012, URL + "/h/alexnet").with_work(work(1, ALEXNET, 830, 2012), 2026, how="exact")
    old_close = Paper("Practical Bayesian Optimization of Learning", 2012, URL + "/h/b").with_work(work(5, "x", 77), 2026, how="close")
    web = FakeWeb({URL: PAGE_2012})
    vy = build_venue_year(VENUE, 2012, _client(web), 2026, [old_exact, old_close], today=dt.date(2026, 11, 14), rule=0)
    searched = [u for u, _ in web.calls if "title.search" in u]
    assert len(searched) == 1 and "imagenet" in searched[0] and "bayesian" not in searched[0]  # the close match kept, by ID
    assert vy.rule == RULE and vy.papers[1].id == "https://openalex.org/W5" and vy.papers[1].how == "close"
    # under the current rule nothing is searched again: both refreshed by ID
    web2 = FakeWeb({URL: PAGE_2012})
    build_venue_year(VENUE, 2012, _client(web2), 2026, [old_exact, old_close], today=dt.date(2026, 11, 14), rule=RULE)
    assert not [u for u, _ in web2.calls if "title.search" in u]


def test_the_rule_is_written_and_read_back(tmp_path: Path) -> None:
    write_data(tmp_path, [VENUE], [VenueYear("NeurIPS", 2012, URL, [Paper("T", 2012)], RULE)], "2026-11-14")
    assert read_previous(tmp_path, VENUE, 2012)[2] == RULE
    f = tmp_path / "data" / "neurips" / "2012.json"
    body = json.loads(f.read_text(encoding="utf-8"))
    del body["rule"]  # data from before rules were numbered
    f.write_text(json.dumps(body), encoding="utf-8")
    assert read_previous(tmp_path, VENUE, 2012)[2] == 0


def test_the_page_links_each_number_to_its_record_and_says_how_it_was_matched() -> None:
    assert "safe(p.id)" in PAGE and '"later record"' in PAGE and '"near title"' in PAGE and "title: HOW[p.how][1]" in PAGE


def test_a_title_with_an_underscore_is_searched_by_the_words_before_it() -> None:
    title = "Optimal Neural Tuning Curves for Arbitrary Stimulus Distributions: Discrimax, Infomax and Minimum $L_p$ Loss"
    calls: list[dict[str, str]] = []

    def search(p: dict[str, str]) -> dict[str, object]:
        calls.append(p)
        return answer(work(1, title, 19, 2012))

    assert match([title], 2012, search, close=False)[normalize(title)].work is not None  # matched on the whole title
    assert '"optimal neural tuning curves for arbitrary stimulus distributions discrimax infomax and minimum"' in calls[0]["filter"]
