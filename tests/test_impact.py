"""The model, the client (a fake transport: no test reaches the network), the build, the data and the site."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from paper_impact.build import Venue, build, read_venues, write_data
from paper_impact.cli import main
from paper_impact.model import Paper
from paper_impact.openalex import Client, OpenAlexError
from paper_impact.site import write_site


def work(i: int, cites: int, year: int = 2017) -> dict[str, object]:
    return {"id": f"https://openalex.org/W{i}", "title": f"Paper  {i}\n", "publication_year": year, "cited_by_count": cites, "fwci": cites / 10,
            "citation_normalized_percentile": {"value": 0.5 + cites / 1000, "is_in_top_1_percent": cites > 400, "is_in_top_10_percent": cites > 100},
            "counts_by_year": [{"year": 2025, "cited_by_count": cites // 10}, {"year": 2024, "cited_by_count": cites // 20}], "doi": ""}  # fmt: skip


class FakeAPI:
    def __init__(self, pages: list[tuple[int, dict[str, object]]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        self.calls.append((url, headers))
        status, body = self.pages.pop(0)
        return status, {}, json.dumps(body).encode()


def client(pages: list[tuple[int, dict[str, object]]], key: str = "") -> tuple[Client, FakeAPI]:
    api = FakeAPI(pages)
    return Client(key=key, get=api, sleep=lambda _: None), api


def test_a_paper_from_openalex_and_bad_records() -> None:
    p = Paper.from_openalex(work(1, 500), 2026)
    assert p is not None and p.title == "Paper 1" and p.fwci == 50 and p.top1 and p.recent == 75
    assert Paper.from_openalex({"id": "W", "title": "", "publication_year": 2017}, 2026) is None
    assert Paper.from_openalex({"id": "W", "title": "T"}, 2026) is None
    odd = Paper.from_openalex({"id": "W", "title": "T", "publication_year": 2017, "cited_by_count": -3, "fwci": float("nan"),
                               "citation_normalized_percentile": "x", "counts_by_year": "y"}, 2026)  # fmt: skip
    assert odd is not None and odd.cited_by_count == 0 and odd.fwci is None and odd.percentile is None and odd.recent == 0


def test_without_a_key_the_first_page_with_a_key_every_page() -> None:
    c, api = client([(200, {"meta": {"count": 3}, "results": [work(1, 50), work(2, 40)]})])
    count, works = c.works(["S1", "https://openalex.org/S2"], 2017, top=2)
    assert count == 3 and [w["id"] for w in works] == ["https://openalex.org/W1", "https://openalex.org/W2"]
    url, headers = api.calls[0]
    assert "source.id%3AS1%7CS2" in url and "per_page=2" in url and "cursor" not in url and "Authorization" not in headers
    c, api = client([(200, {"meta": {"count": 3, "next_cursor": "abc"}, "results": [work(1, 50), work(2, 40)]}),
                     (200, {"meta": {"count": 3, "next_cursor": "def"}, "results": [work(3, 30)]}),
                     (200, {"meta": {"count": 3, "next_cursor": None}, "results": []})], key="k")  # fmt: skip
    count, works = c.works(["S1"], 2017, top=None)
    assert len(list(works)) == 3 and "cursor=abc" in api.calls[1][0] and api.calls[0][1]["Authorization"] == "Bearer k"
    assert all("k" not in url.split("?")[1].split("&")[-1] for url, _ in api.calls)  # the key never in a URL


def test_paging_without_a_key_says_what_to_do() -> None:
    c, _ = client([(401, {"error": "API key required"})])
    with pytest.raises(OpenAlexError, match="free\\) API key"):
        c.works(["S1"], 2017, top=None)


def test_venues_must_name_sources_and_official_counts_their_source(tmp_path: Path) -> None:
    good = {"venues": [{"name": "NeurIPS", "sources": ["S1"], "official": {"2017": {"count": 679, "source": "https://example.org/n17"}}}]}
    (tmp_path / "v.json").write_text(json.dumps(good), encoding="utf-8")
    assert read_venues(tmp_path / "v.json")[0].official == {2017: (679, "https://example.org/n17")}
    for bad, message in (
        ({"venues": []}, "no venues"),
        ({"venues": [{"name": "X", "sources": ["neurips"]}]}, "OpenAlex source IDs"),
        ({"venues": [{"name": "X", "sources": ["S1"], "official": {"2017": {"count": 5}}}]}, "needs its source"),
        ({"venues": [{"name": "A b", "sources": ["S1"]}, {"name": "a-B", "sources": ["S2"]}]}, "same name"),
    ):
        (tmp_path / "v.json").write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            read_venues(tmp_path / "v.json")


def test_build_coverage_and_the_data(tmp_path: Path) -> None:
    venues = [Venue("NeurIPS", "Neural Information Processing Systems", ["S1"], {2017: (4, "https://example.org/n17")})]
    c, _ = client([(200, {"meta": {"count": 3}, "results": [work(1, 500), work(2, 40)]}), (200, {"meta": {"count": 0}, "results": []})])
    vys = build(venues, range(2017, 2019), c, top=2, as_of_year=2026)
    assert [(vy.year, len(vy.papers), vy.openalex_count, vy.complete) for vy in vys] == [(2017, 2, 3, False), (2018, 0, 0, True)]
    assert vys[0].coverage == 0.75 and vys[1].coverage is None
    write_data(tmp_path, venues, vys, "2026-11-13")
    index = json.loads((tmp_path / "data" / "index.json").read_text(encoding="utf-8"))
    assert index["venue_years"][0] == {"venue": "NeurIPS", "year": 2017, "file": "data/neurips/2017.json", "papers": 2, "openalex_count": 3,
                                       "official_count": 4, "official_source": "https://example.org/n17", "coverage": 0.75,
                                       "complete": False}  # fmt: skip
    papers = json.loads((tmp_path / "data" / "neurips" / "2017.json").read_text(encoding="utf-8"))["papers"]
    assert papers[0]["title"] == "Paper 1" and papers[0]["top1"] is True


def test_the_site_reads_the_data_and_sets_text_safely(tmp_path: Path) -> None:
    page = write_site(tmp_path).read_text(encoding="utf-8")
    assert 'load("data/index.json")' in page and "innerHTML" not in page and "textContent" in page
    assert "<script src" not in page and "@import" not in page and "http://" not in page  # nothing fetched from elsewhere


def test_the_cli_builds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import paper_impact.cli as cli

    (tmp_path / "v.json").write_text(json.dumps({"venues": [{"name": "ICLR", "sources": ["S9"]}]}), encoding="utf-8")
    c, _ = client([(200, {"meta": {"count": 1}, "results": [work(1, 9, 2020)]})])
    monkeypatch.setattr(cli, "Client", lambda: c)
    assert main(["build", str(tmp_path / "v.json"), "-o", str(tmp_path / "site"), "--years", "2020"]) == 0
    assert (tmp_path / "site" / "index.html").exists() and (tmp_path / "site" / "data" / "iclr" / "2020.json").exists()
    assert "1 venue-years, 1 papers, 1 requests" in capsys.readouterr().out
    assert main(["build", str(tmp_path / "missing.json")]) == 2
    with pytest.raises(SystemExit):
        main(["build", str(tmp_path / "v.json"), "--years", "2025-2020"])
