"""paper-impact today, with a made-up arXiv answer (no network)."""

from __future__ import annotations

import datetime as dt
import json

from paper_impact import today
from paper_impact.cli import main


def entry(aid: str, date: str, title: str, comment: str = "", summary: str = "We study things.") -> str:
    c = f"<arxiv:comment>{comment}</arxiv:comment>" if comment else ""
    return (f"<entry><id>http://arxiv.org/abs/{aid}v1</id><published>{date}T10:00:00Z</published><title>{title}</title>"
            f"<summary>{summary}</summary><author><name>Ada Lovelace</name></author>{c}</entry>")  # fmt: skip


FEED = ('<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">'
        + entry("2611.00003", "2026-11-13", "Plain")
        + entry("2611.00002", "2026-11-13", "Has Code", "12 pages. Code: https://github.com/ada/engine")
        + entry("2611.00001", "2026-11-12", "Accepted One", "Accepted at ICLR 2027 (Oral)")
        + entry("2611.00004", "2026-11-12", "Workshop", "Accepted at the Workshop on X, NeurIPS 2026")
        + entry("2611.00005", "2026-11-12", "Under Review", "Under review at ICML 2027")
        + entry("2611.00000", "2026-11-01", "Too Old", "Accepted at ACL 2026")
        + "</feed>")  # fmt: skip


def test_fetch_signs_and_rank():
    urls: list[str] = []

    def get(url: str) -> bytes:
        urls.append(url)
        return FEED.encode()

    papers = today.fetch("cs.CL", 2, 400, get=get, sleep=lambda s: None, today=dt.date(2026, 11, 14))
    assert "cat%3Acs.CL" in urls[0] and len(urls) == 1  # the page ended before the window: one request
    ranked = today.rank(papers)
    assert [p.title for p in ranked] == ["Accepted One", "Has Code", "Workshop", "Plain", "Under Review"]
    assert ranked[0].signs == ["accepted: ICLR"] and ranked[1].code == "https://github.com/ada/engine"
    assert ranked[2].signs == ["accepted: NeurIPS (workshop)"]
    out = today.text("cs.CL", ranked, 3)
    assert out.startswith("cs.CL: 5 papers, 3 with signs (accepted 2, code 1)") and "... and 2 more" in out


def test_citations_from_openalex():
    class Fake:
        def get(self, path, params):
            assert "10.48550/arxiv.2611.00001" in params["filter"]
            return {"results": [{"doi": "https://doi.org/10.48550/arxiv.2611.00001", "cited_by_count": 7}]}

    ps = [today.Paper("2611.00001v2", "A", [], "2026-11-01"), today.Paper("2611.00002v1", "B", [], "2026-11-01")]
    today.citations(ps, Fake())
    assert [p.citations for p in ps] == [7, None]
    assert today.rank(ps)[0].signs == ["7 citations"]


def test_cli(monkeypatch, capsys):
    monkeypatch.setattr(today, "_get", lambda url: FEED.encode())
    monkeypatch.setattr(today.time, "sleep", lambda s: None)
    monkeypatch.setattr(today, "fetch", lambda cat, days, limit: today.parse(FEED.encode()))
    assert main(["today", "cs.CL", "--format", "json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["category"] == "cs.CL" and doc["papers"][0]["accepted"] == "ICLR"
    assert main(["today", "cs.CL", "--format", "markdown", "--top", "2"]) == 0
    assert "| [Accepted One](https://arxiv.org/abs/2611.00001) | accepted: ICLR |" in capsys.readouterr().out
    assert main(["today", "not a category"]) == 2
