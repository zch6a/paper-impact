"""Regression tests for what the round-5 review (the third) found."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from test_impact import NEURIPS, FakeWeb, work

from paper_impact import cli
from paper_impact.build import Stopped, Venue, VenueYear, _close_pass, build, build_venue_year, read_previous, read_venues, write_data
from paper_impact.match import RULE, close_match, match
from paper_impact.model import Paper
from paper_impact.openalex import Client, KeyRejected
from paper_impact.proceedings import parse

URL = "https://papers.nips.cc/paper_files/paper/2017"
VENUE = Venue("NeurIPS", "", "neurips", {2017: URL})
SPARSE = "Sparse Attention for Long Documents"


def spent(web: FakeWeb) -> Client:
    """A client whose budget runs out at the first OpenAlex request (the proceedings page still answers)."""

    def get(url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        return web(url, headers) if url in web.pages else (429, {"retry-after": "40000"}, b"{}")

    return Client(key="", get=get, sleep=lambda _: None)


def test_a_rule_upgrade_on_a_spent_budget_keeps_the_old_matches() -> None:
    old = Paper(SPARSE, 2017, URL + "/hash/a-Abstract.html").with_work(work(1, SPARSE, 500), 2026, how="exact")
    vy = build_venue_year(VENUE, 2017, spent(FakeWeb({URL: NEURIPS})), 2026, [old], today=dt.date(2026, 11, 14), rule=1)
    assert vy.papers[0].id == "https://openalex.org/W1" and vy.papers[0].cited_by_count == 500
    assert vy.rule == 1  # not every old match was searched again: the next build goes on


def test_a_rule_upgrade_that_finishes_stamps_the_new_rule() -> None:
    old = Paper(SPARSE, 2017, URL + "/hash/a-Abstract.html").with_work(work(2, SPARSE, 40, 2016), 2026, how="exact")
    vy = build_venue_year(VENUE, 2017, Client(key="", get=FakeWeb({URL: NEURIPS}), sleep=lambda _: None), 2026, [old], rule=1)
    assert vy.rule == RULE and vy.papers[0].id == "https://openalex.org/W1"  # the better record, found again


def test_the_looser_try_spends_no_search_on_a_short_title() -> None:
    calls: list[dict[str, str]] = []

    def search(p: dict[str, str]) -> dict[str, object]:
        calls.append(p)
        return {"meta": {"count": 0}, "results": []}

    assert close_match(["Deep Sets"], 2017, search)["deep sets"].work is None and calls == []
    match(["Deep Sets"], 2017, search)
    assert len(calls) == 1  # the exact search only


def test_the_looser_pass_never_takes_a_record_another_paper_holds() -> None:
    held = Paper("Sparse Attention for Long Documents", 2017, "a").with_work(work(1, "Sparse attention for long documents", 500), 2026)
    waiting = Paper("Sparse Attention for the Long Documents", 2017, "b", tried="exact:2026-11-01")
    vy = VenueYear("NeurIPS", 2017, URL, [held, waiting])
    answer = json.dumps({"meta": {"count": 1}, "results": [work(1, "Sparse attention for long documents", 500)]}).encode()
    _close_pass([vy], Client(key="", get=lambda u, h: (200, {}, answer), sleep=lambda _: None), 2026, today=dt.date(2026, 11, 14))
    assert vy.papers[1].id == "" and vy.papers[1].tried == "2026-11-14" and vy.matched == 1


def test_iclr_keeps_two_papers_of_one_title_and_one_oral_listed_twice() -> None:
    page = """<a href="/virtual/2024/poster/1">Graph Neural Networks</a><a href="/virtual/2024/poster/2">Graph Neural Networks</a>
<a href="/virtual/2024/oral/3">An Oral</a><a href="/virtual/2024/poster/4">An Oral</a>"""
    got = [(x.title, x.url.rsplit("/", 2)[-2:]) for x in parse("virtual", page, "https://iclr.cc/virtual/2024/papers.html")]
    assert got == [("Graph Neural Networks", ["poster", "1"]), ("Graph Neural Networks", ["poster", "2"]), ("An Oral", ["oral", "3"])]


def test_odd_saved_data_loses_only_what_is_odd(tmp_path: Path) -> None:
    f = tmp_path / "data" / "neurips" / "2017.json"
    f.parent.mkdir(parents=True)
    f.write_text(
        json.dumps({"source": URL, "rule": RULE, "papers": [{"title": "Kept", "id": "W9"}, {"title": "Odd", "year": "x", "also": 5}]}), "utf-8"
    )
    _, papers, _ = read_previous(tmp_path, VENUE, 2017)
    assert [p.title for p in papers][:1] == ["Kept"] and papers[0].year == 2017
    f.write_text("[1, 2]", encoding="utf-8")
    assert read_previous(tmp_path, VENUE, 2017)[1] == []


def test_a_venue_list_with_pages_as_a_list_is_refused_cleanly(tmp_path: Path) -> None:
    (tmp_path / "v.json").write_text(json.dumps({"venues": [{"name": "X", "proceedings": {"kind": "pmlr", "pages": ["https://x"]}}]}), "utf-8")
    with pytest.raises(ValueError, match="pages is an object"):
        read_venues(tmp_path / "v.json")


def test_a_refused_key_midway_keeps_what_was_built_and_carries_over_the_rest(tmp_path: Path) -> None:
    other = "https://papers.nips.cc/paper_files/paper/2018"
    venue = Venue("NeurIPS", "", "neurips", {2017: URL, 2018: other})
    write_data(tmp_path, [venue], [VenueYear("NeurIPS", 2018, other, [Paper("Earlier Paper Kept Here", 2018, "u", id="W7")], RULE)], "2026-11-13")
    web = FakeWeb({URL: NEURIPS, other: NEURIPS})

    def get(url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        if url != other and any(u == other for u, _ in web.calls):  # the key is revoked once 2018 is under way
            return 403, {}, b"forbidden"
        return web(url, headers)

    with pytest.raises(Stopped) as stop:
        build([venue], range(2017, 2019), Client(key="k", get=get, sleep=lambda _: None), 2026, tmp_path)
    assert isinstance(stop.value, KeyRejected)
    by_year = {vy.year: vy for vy in stop.value.built}
    assert by_year[2017].matched == 2 and by_year[2018].papers[0].title == "Earlier Paper Kept Here"


def test_the_cli_writes_the_data_before_reporting_a_refused_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    built = [VenueYear("NeurIPS", 2017, URL, [Paper("T", 2017)], RULE)]

    def stop(*a: object, **k: object) -> None:
        raise Stopped(KeyRejected("refused"), built, [])

    monkeypatch.setattr(cli, "build", stop)
    (tmp_path / "v.json").write_text(
        json.dumps({"venues": [{"name": "NeurIPS", "proceedings": {"kind": "neurips", "pages": {"2017": URL}}}]}), "utf-8"
    )
    assert cli.main(["build", str(tmp_path / "v.json"), "-o", str(tmp_path / "site")]) == 2
    assert (tmp_path / "site" / "data" / "neurips" / "2017.json").exists()


def test_a_keyless_refusal_does_not_blame_the_key() -> None:
    with pytest.raises(KeyRejected, match="refused requests from this address"):
        Client(key="", get=lambda u, h: (403, {}, b"no"), sleep=lambda _: None).search({})
