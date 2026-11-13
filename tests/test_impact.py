"""The parsers, the matcher, the client, the build with reuse, the data and the site, on synthetic pages and a fake
OpenAlex (no test reaches the network)."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from paper_impact.build import Venue, build, read_venues, write_data
from paper_impact.cli import main
from paper_impact.match import match, normalize
from paper_impact.model import Paper
from paper_impact.openalex import Client, OpenAlexError
from paper_impact.proceedings import parse
from paper_impact.site import write_site

NEURIPS = """<html><body><ul class="paper-list">
<li><div class="paper-content"><a title="paper title" href="/paper_files/paper/2017/hash/a-Abstract.html">Sparse Attention for  Long Documents</a>
<span class="paper-authors">A. Author</span></div></li>
<li><div class="paper-content"><a title="paper title" href="/paper_files/paper/2017/hash/b-Abstract.html">Calibrated Uncertainty, Revisited</a>
</div></li>
<li><div class="paper-content"><a title="paper title" href="/paper_files/paper/2017/hash/c-Abstract.html">A Paper OpenAlex Lacks</a></div></li>
</ul><a href="/other">not a paper</a></body></html>"""
PMLR = """<div class="paper"><p class="title">Robust Tabular Learning</p><p class="details"><span class="authors">B. Author</span></p>
<p class="links">[<a href="https://proceedings.mlr.press/v70/b17a.html">abs</a>][<a href="x.pdf">Download PDF</a>]</p></div>
<div class="paper"><p class="title">Seeds &amp; Variance</p><p class="links">[<a href="https://proceedings.mlr.press/v70/c17a.html">abs</a>]</p></div>"""


def work(i: int, title: str, cites: int, year: int = 2017) -> dict[str, object]:
    return {"id": f"https://openalex.org/W{i}", "title": title, "publication_year": year, "cited_by_count": cites, "fwci": cites / 10,
            "citation_normalized_percentile": {"value": 0.5 + cites / 2000, "is_in_top_1_percent": cites > 400, "is_in_top_10_percent": cites > 100},
            "counts_by_year": [{"year": 2025, "cited_by_count": cites // 10}, {"year": 2024, "cited_by_count": cites // 20}], "doi": ""}  # fmt: skip


WORKS = [work(1, "Sparse attention for long documents", 500), work(2, "Sparse Attention for Long Documents", 40, 2016),
         work(3, "Calibrated uncertainty: revisited", 120), work(4, "Sparse attention for long documents in vision", 900),
         work(5, "Robust Tabular Learning", 77)]  # fmt: skip


class FakeWeb:
    """OpenAlex (title searches, works by ID) and the proceedings sites, answering from WORKS and the pages above."""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        self.calls.append((url, headers))
        if url in self.pages:
            return 200, {}, self.pages[url].encode()
        q = parse_qs(urlparse(url).query)
        f = q.get("filter", [""])[0]
        if f.startswith("openalex:"):
            ids = {f"https://openalex.org/{i}" for i in f[len("openalex:") :].split("|")}
            results = [w for w in WORKS if w["id"] in ids]
        else:
            phrases = [p.strip('"') for p in f.split(",publication_year:")[0][len("title.search:") :].split("|")]
            results = [w for w in WORKS if any(p in normalize(str(w["title"])) for p in phrases)]
        return 200, {}, json.dumps({"meta": {"count": len(results)}, "results": results}).encode()


def test_the_parsers() -> None:
    n = parse("neurips", NEURIPS, "https://papers.nips.cc/paper_files/paper/2017")
    assert [x.title for x in n] == ["Sparse Attention for Long Documents", "Calibrated Uncertainty, Revisited", "A Paper OpenAlex Lacks"]
    assert n[0].url == "https://papers.nips.cc/paper_files/paper/2017/hash/a-Abstract.html"
    p = parse("pmlr", PMLR, "https://proceedings.mlr.press/v70/")
    assert [(x.title, x.url) for x in p] == [("Robust Tabular Learning", "https://proceedings.mlr.press/v70/b17a.html"),
                                             ("Seeds & Variance", "https://proceedings.mlr.press/v70/c17a.html")]  # fmt: skip
    with pytest.raises(ValueError, match="no parser"):
        parse("dblp", "", "")


def test_a_neurips_page_that_disagrees_with_its_own_count_is_refused() -> None:
    page = NEURIPS.replace('<ul class="paper-list">', '<span class="paper-count">5 papers</span><ul class="paper-list">')
    with pytest.raises(ValueError, match="says it lists 5 papers, but 3 were read"):
        parse("neurips", page, "https://papers.nips.cc/paper_files/paper/2017")
    assert len(parse("neurips", page.replace("5 papers", "3 papers"), "https://papers.nips.cc/paper_files/paper/2017")) == 3


def test_a_page_that_does_not_mention_its_venue_and_year_is_refused(tmp_path: Path) -> None:
    venues = [Venue("ICML", "", "pmlr", {2017: "https://proceedings.mlr.press/v70/"}, {2017: ["International Conference on Machine Learning"]})]
    web = FakeWeb({"https://proceedings.mlr.press/v70/": PMLR})
    vys, failures = build(venues, range(2017, 2018), Client(key="", get=web, sleep=lambda _: None), 2026, tmp_path)
    assert vys == [] and len(failures) == 1 and "does not mention 'International Conference on Machine Learning'" in failures[0].reason


def test_the_matcher_is_exact_and_takes_the_most_cited_record() -> None:
    web = FakeWeb({})
    c = Client(key="", get=web, sleep=lambda _: None)
    found = match(["Sparse Attention for Long Documents", "Calibrated Uncertainty, Revisited", "A Paper OpenAlex Lacks"], 2017, c.search)
    s = found[normalize("Sparse Attention for Long Documents")]
    assert s.work["id"] == "https://openalex.org/W1" and s.also == ["https://openalex.org/W2"]  # type: ignore[index]  # not W4: a longer title
    assert found[normalize("Calibrated Uncertainty, Revisited")].work["id"] == "https://openalex.org/W3"  # type: ignore[index]
    assert found[normalize("A Paper OpenAlex Lacks")].work is None
    assert len(web.calls) == 2 and "%22" not in web.calls[1][0]  # one search for the batch, one looser try (no phrase) for the miss


def test_a_cut_batch_retries_its_unmatched_titles_alone() -> None:
    answers = [{"meta": {"count": 500}, "results": [work(1, "Alpha", 3)]}, {"meta": {"count": 1}, "results": [work(2, "Beta", 4)]}]
    calls: list[dict[str, str]] = []

    def search(params: dict[str, str]) -> dict[str, object]:
        calls.append(params)
        return answers.pop(0)

    found = match(["Alpha", "Beta"], 2017, search)
    assert found["alpha"].work["id"] == "https://openalex.org/W1" and found["beta"].work["id"] == "https://openalex.org/W2"  # type: ignore[index]
    assert '"beta"' in calls[1]["filter"] and '"alpha"' not in calls[1]["filter"]


def test_the_looser_try_accepts_nearly_the_same_words_and_says_so() -> None:
    answers = [
        {"meta": {"count": 0}, "results": []},  # the exact phrase: nothing
        {
            "meta": {"count": 2},
            "results": [
                work(7, "Stochastic Modified Equations and Adaptive Stochastic Gradient Algorithm", 50),  # plural lost
                work(8, "Stochastic Equations for Adaptive Learning", 900),
            ],
        },  # fmt: skip
        {"meta": {"count": 0}, "results": []},
        {"meta": {"count": 1}, "results": [work(9, "Deep IV for Counterfactual Prediction", 300)]},  # too different
    ]
    found = match(["Stochastic Modified Equations and Adaptive Stochastic Gradient Algorithms"], 2017, lambda p: answers.pop(0))
    m = found[normalize("Stochastic Modified Equations and Adaptive Stochastic Gradient Algorithms")]
    assert m.how == "close" and m.work["id"] == "https://openalex.org/W7"  # type: ignore[index]
    assert (
        match(["Deep IV: A Flexible Approach for Counterfactual Prediction"], 2017, lambda p: answers.pop(0))[
            normalize("Deep IV: A Flexible Approach for Counterfactual Prediction")
        ].work
        is None
    )


def test_punctuation_never_reaches_the_filter() -> None:
    calls: list[dict[str, str]] = []
    match(['Seeds, "Variance" | Tables'], 2017, lambda p: calls.append(p) or {"meta": {"count": 0}, "results": []})  # type: ignore[func-returns-value]
    assert calls[0]["filter"] == 'title.search:"seeds variance tables",publication_year:2016-2018'


def test_venues(tmp_path: Path) -> None:
    good = {"venues": [{"name": "NeurIPS", "proceedings": {"kind": "neurips", "pages": {"2017": "https://papers.nips.cc/paper_files/paper/2017"}}}]}
    (tmp_path / "v.json").write_text(json.dumps(good), encoding="utf-8")
    assert read_venues(tmp_path / "v.json")[0].pages == {2017: "https://papers.nips.cc/paper_files/paper/2017"}
    for bad, message in (({"venues": []}, "no venues"), ({"venues": [{"name": "X", "proceedings": {"kind": "dblp"}}]}, "kind must be"),
                         ({"venues": [{"name": "X", "proceedings": {"kind": "pmlr", "pages": {"2017": "http://x"}}}]}, "https link"),
                         ({"venues": [{"name": "X", "proceedings": {"kind": "pmlr", "pages": {}}}]}, "no proceedings pages")):  # fmt: skip
        (tmp_path / "v.json").write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            read_venues(tmp_path / "v.json")


def test_build_writes_the_data_and_a_rebuild_reuses_the_matches(tmp_path: Path) -> None:
    pages = {"https://papers.nips.cc/paper_files/paper/2017": NEURIPS, "https://proceedings.mlr.press/v70/": PMLR}
    venues = [Venue("NeurIPS", "Neural Information Processing Systems", "neurips", {2017: "https://papers.nips.cc/paper_files/paper/2017"}),
              Venue("ICML", "", "pmlr", {2017: "https://proceedings.mlr.press/v70/", 2030: "https://proceedings.mlr.press/v999/"})]  # fmt: skip
    web = FakeWeb(pages)
    c = Client(key="k", get=web, sleep=lambda _: None)
    vys, _ = build(venues, range(2017, 2018), c, 2026, tmp_path)
    assert [(vy.venue, len(vy.papers), vy.matched) for vy in vys] == [("NeurIPS", 3, 2), ("ICML", 2, 1)]
    assert vys[0].papers[0].cited_by_count == 500 and vys[0].papers[0].recent == 75 and vys[0].papers[2].id == ""
    assert all("Authorization" not in h for u, h in web.calls if not u.startswith("https://api.openalex.org"))  # the key stays with OpenAlex
    write_data(tmp_path, venues, vys, "2026-11-13")
    index = json.loads((tmp_path / "data" / "index.json").read_text(encoding="utf-8"))
    assert index["venue_years"][0] == {"venue": "NeurIPS", "year": 2017, "file": "data/neurips/2017.json",
                                       "source": "https://papers.nips.cc/paper_files/paper/2017", "listed": 3, "matched": 2,
                                       "coverage": 2 / 3}  # fmt: skip
    web2 = FakeWeb(pages)
    vys2, _ = build(venues, range(2017, 2018), Client(key="", get=web2, sleep=lambda _: None), 2026, tmp_path)
    searches = [u for u, _ in web2.calls if "title.search" in u]
    assert [vy.matched for vy in vys2] == [2, 1] and searches == []  # the misses were searched today: not again for weeks
    assert vys2[0].papers[2].tried == vys[0].papers[2].tried != ""


def test_a_paper_without_a_work_has_no_numbers() -> None:
    p = Paper("T", 2017, "https://x")
    assert p.cited_by_count is None and p.recent is None and p.id == ""


def test_proceedings_pages_must_be_https() -> None:
    with pytest.raises(OpenAlexError, match="https only"):
        Client(key="", get=FakeWeb({}), sleep=lambda _: None).page("http://papers.nips.cc/")


def test_the_site_reads_the_data_and_sets_text_safely(tmp_path: Path) -> None:
    page = write_site(tmp_path).read_text(encoding="utf-8")
    assert 'load("data/index.json")' in page and "innerHTML" not in page and "textContent" in page
    assert "<script src" not in page and "@import" not in page and "http://" not in page


def test_the_cli_builds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import paper_impact.cli as cli

    (tmp_path / "v.json").write_text(json.dumps({"venues": [{"name": "ICML", "proceedings": {"kind": "pmlr", "pages": {"2017": "https://proceedings.mlr.press/v70/"}}}]}),
                                     encoding="utf-8")  # fmt: skip
    monkeypatch.setattr(cli, "Client", lambda: Client(key="", get=FakeWeb({"https://proceedings.mlr.press/v70/": PMLR}), sleep=lambda _: None))
    assert main(["build", str(tmp_path / "v.json"), "-o", str(tmp_path / "site"), "--years", "2017"]) == 0
    assert (tmp_path / "site" / "index.html").exists() and (tmp_path / "site" / "data" / "icml" / "2017.json").exists()
    assert "1 venue-years, 2 papers, 1 matched in OpenAlex (50%)" in capsys.readouterr().out
    assert main(["build", str(tmp_path / "missing.json")]) == 2


def test_an_exhausted_budget_keeps_what_was_found_and_the_next_build_carries_on(tmp_path: Path) -> None:
    pages = {"https://papers.nips.cc/paper_files/paper/2017": NEURIPS}
    venues = [Venue("NeurIPS", "", "neurips", {2017: "https://papers.nips.cc/paper_files/paper/2017"})]

    class Spent(FakeWeb):
        def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
            if url.startswith("https://api.openalex.org"):
                self.calls.append((url, headers))
                return 429, {"retry-after": "40000"}, b"{}"
            return super().__call__(url, headers)

    c = Client(key="", get=Spent(pages), sleep=lambda _: None)
    vys, _ = build(venues, range(2017, 2018), c, 2026, tmp_path)
    assert c.exhausted and [len(vy.papers) for vy in vys] == [3] and vys[0].matched == 0  # listed, not matched
    write_data(tmp_path, venues, vys, "2026-11-13")
    vys, _ = build(venues, range(2017, 2018), Client(key="", get=FakeWeb(pages), sleep=lambda _: None), 2026, tmp_path)
    assert vys[0].matched == 2  # the next day: matched
    write_data(tmp_path, venues, vys, "2026-11-14")
    c = Client(key="", get=Spent(pages), sleep=lambda _: None)
    vys, _ = build(venues, range(2017, 2018), c, 2026, tmp_path)
    assert vys[0].matched == 2 and vys[0].papers[0].cited_by_count == 500  # spent again: the last numbers stand


CVF = """<dl><dt class="ptitle"><br><a href="/content/CVPR2023/html/A_Paper_CVPR_2023_paper.html">A Vision Paper</a></dt><dd>authors</dd>
<dt class="ptitle"><br><a href="/content/CVPR2023/html/B_CVPR_2023_paper.html">Another One: With <i>Style</i></a></dt></dl><a href="/x">menu</a>"""
ACL = """<p><strong><a class=align-middle href=/2023.acl-long.0/>Proceedings of the 61st Annual Meeting</a></strong></p>
<p><strong><a class=align-middle href=/2023.acl-long.1/>One Cannot Stand for Everyone! <span class=acl-fixed-case>L</span>everaging Data</a></strong>
<br><a href=/people/x/>An Author</a></p>
<p><strong><a class=align-middle href=/2023.acl-long.2/>Second Paper</a></strong></p>"""


def test_the_cvf_and_acl_parsers() -> None:
    cvf = parse("cvf", CVF, "https://openaccess.thecvf.com/CVPR2023?day=all")
    assert [(p.title, p.url) for p in cvf] == [("A Vision Paper", "https://openaccess.thecvf.com/content/CVPR2023/html/A_Paper_CVPR_2023_paper.html"),
                                               ("Another One: With Style",
                                                "https://openaccess.thecvf.com/content/CVPR2023/html/B_CVPR_2023_paper.html")]  # fmt: skip
    acl = parse("acl", ACL, "https://aclanthology.org/volumes/2023.acl-long/")
    assert [(p.title, p.url) for p in acl] == [("One Cannot Stand for Everyone! Leveraging Data", "https://aclanthology.org/2023.acl-long.1/"),
                                               ("Second Paper", "https://aclanthology.org/2023.acl-long.2/")]  # fmt: skip


def test_a_venue_year_listed_over_several_pages_and_an_empty_one(tmp_path: Path) -> None:
    day1 = CVF
    day2 = CVF.replace("A Vision Paper", "A Third Paper").replace("A_Paper", "C_Paper").replace("B_CVPR", "B_CVPR")  # one new, one repeated
    venue = Venue("CVPR", "", "cvf", {2019: "https://openaccess.thecvf.com/CVPR2019"}, {2019: ["CVPR2019"]},
                  {2019: ["https://openaccess.thecvf.com/CVPR2019.py?day=1", "https://openaccess.thecvf.com/CVPR2019.py?day=2"]})  # fmt: skip
    pages = {"https://openaccess.thecvf.com/CVPR2019.py?day=1": day1.replace("CVPR2023", "CVPR2019"),
             "https://openaccess.thecvf.com/CVPR2019.py?day=2": day2.replace("CVPR2023", "CVPR2019")}  # fmt: skip
    vys, failures = build([venue], range(2019, 2020), Client(key="", get=FakeWeb(pages), sleep=lambda _: None), 2026, tmp_path)
    assert not failures and [p.title for p in vys[0].papers] == ["A Vision Paper", "Another One: With Style", "A Third Paper"]
    assert vys[0].source == "https://openaccess.thecvf.com/CVPR2019"
    empty = {
        "https://openaccess.thecvf.com/CVPR2019.py?day=1": "<p>CVPR2019</p>",
        "https://openaccess.thecvf.com/CVPR2019.py?day=2": "<p>CVPR2019</p>",
    }
    vys, failures = build([venue], range(2019, 2020), Client(key="", get=FakeWeb(empty), sleep=lambda _: None), 2026, tmp_path / "x")
    assert vys == [] and "lists no papers" in failures[0].reason
