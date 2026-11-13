"""Proceedings titles to OpenAlex works: searched in batches (several titles ORed in one search, which costs as much as
one), accepted only on an exact normalized title within a year of the venue's, or, for a title of LATER_WORDS words or
more, dated later (OpenAlex may date a paper's main record by a later reprint: AlexNet, NeurIPS 2012, is a 2017 record
with its citations); of several such records (a preprint and the published paper, citations split between them) the
most cited, the others kept as "also", and marked "later" when it is dated after the venue's year and the next. The
answer comes most cited first, so a title's best records are never past the page; titles a batch does not settle (its
answer was cut) are searched alone. A title still unmatched gets one looser try (its words, not the phrase, within a
year), accepted only when 85% of the words agree and the length is close, and marked "close"; after that it stays
unmatched and counted."""

from __future__ import annotations

import contextlib
import difflib
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .openalex import FIELDS, BudgetExhausted

WORD = re.compile(r"[\W_]+")
RULE = 2  # the matching rule's version: exact matches made under an older one are made again (2: later records, most cited first)
LATER_WORDS = 5  # a record dated later is taken for a title this long: shorter ones have namesakes in other years


def normalize(title: str) -> str:
    r"""A title as matching compares it: compatibility-folded, case-folded, punctuation and spacing as single spaces.

    >>> normalize("Attention Is  All You Need!"), normalize("ﬁne-tuning: “BERT”"), normalize("Nesterov’s Priv'IT")
    ('attention is all you need', 'fine tuning bert', 'nesterovs privit')
    >>> normalize("Rényi Divergence for $\\ell_1$")  # accents and underscores as OpenAlex may print them, or not
    'renyi divergence for ell 1'
    """
    return " ".join(WORD.sub(" ", _fold(title)).split())


def _fold(title: str) -> str:
    decomposed = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", title))
    folded = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    return re.sub("['’ʼ`´]", "", folded)  # an apostrophe joins: "Nesterov’s" is one word, as OpenAlex may print it with ' or none


def phrase(title: str) -> str:
    r"""The phrase searched for a title: its normalized words, cut before the first word with an underscore when four or
    more come before it. OpenAlex indexes ``$L_p$`` as one token, which the split words "l p" never match as a phrase
    (and it may print it ``Lp`` or ``ℓp``); exactness is checked on the whole title afterwards.

    >>> phrase("Optimal Tuning Curves for Arbitrary Stimuli: Minimum $L_p$ Loss"), phrase("On the $L_p$ Loss")
    ('optimal tuning curves for arbitrary stimuli minimum', 'on the l p loss')
    """
    words = re.sub(r"\W+", " ", _fold(title)).split()
    cut = next((i for i, w in enumerate(words) if "_" in w), len(words))
    return " ".join(words[:cut]) if cut >= 4 else normalize(title)


@dataclass
class Match:
    title: str
    work: dict[str, Any] | None = None  # the chosen OpenAlex work
    also: list[str] = field(default_factory=list)  # other OpenAlex records of the same title and year (IDs)
    how: str = ""  # exact, later (the exact title, dated later), close (the looser try), or "" when nothing matched


Searcher = Callable[[dict[str, str]], dict[str, Any]]  # params -> OpenAlex's answer


def _query(phrases_: list[str], year: int) -> dict[str, str]:
    # the phrases with punctuation removed: a comma or a | would cut the filter; exactness is checked here, not there
    phrases = "|".join(f'"{n}"' for n in phrases_)
    return {"filter": f"title.search:{phrases},publication_year:>{year - 2}", "per_page": "200", "sort": "cited_by_count:desc", "select": FIELDS}


def _pick(norm: str, works: Iterable[dict[str, Any]], year: int) -> Match:
    later = len(norm.split()) >= LATER_WORDS
    same = [w for w in works if normalize(str(w.get("title") or "")) == norm and isinstance(w.get("publication_year"), int)
            and (abs(w["publication_year"] - year) <= 1 or (later and w["publication_year"] > year))]  # fmt: skip
    if not same:
        return Match(norm)
    if len(same) > 3 and len(norm.split()) <= 2:
        return Match(norm)  # "Introduction", "Deep Learning": many works of that title; which one is this paper cannot be told
    same.sort(key=lambda w: (-(w.get("cited_by_count") or 0), abs(w["publication_year"] - year), str(w.get("id"))))
    how = "later" if same[0]["publication_year"] > year + 1 else "exact"
    return Match(norm, same[0], [str(w.get("id")) for w in same[1:]], how=how)


def match(titles: list[str], year: int, search: Searcher, batch: int = 20, close: bool = True) -> dict[str, Match]:
    """Each title's match, by its normalized form. `search` runs one OpenAlex works search. When OpenAlex's budget runs
    out midway, the matches made so far are returned; the other titles are left out (unmatched, for the next run)."""
    out: dict[str, Match] = {}
    with contextlib.suppress(BudgetExhausted):
        _match(titles, year, search, batch, close, out)
    return out


def _match(titles: list[str], year: int, search: Searcher, batch: int, close: bool, out: dict[str, Match]) -> None:
    searched: dict[str, str] = {}  # normalized title -> the phrase searched
    for t in titles:
        if (n := normalize(t)) and n not in searched:
            searched[n] = phrase(t)
    norms = list(searched)
    retry: list[str] = []
    for i in range(0, len(norms), batch):
        group = norms[i : i + batch]
        answer = search(_query([searched[n] for n in group], year))
        results = [w for w in answer.get("results") or [] if isinstance(w, dict)]
        cut = int((answer.get("meta") or {}).get("count") or 0) > len(results)
        for n in group:
            m = _pick(n, results, year)
            if m.work is None and cut:
                retry.append(n)  # its record may be past the page
            else:
                out[n] = m
    for n in retry:
        answer = search(_query([searched[n]], year))
        out[n] = _pick(n, (w for w in answer.get("results") or [] if isinstance(w, dict)), year)
    if close:
        for n in [n for n, m in out.items() if m.work is None and not _short(n)]:
            answer = search({"filter": f"title.search:{n},publication_year:{year - 1}-{year + 1}", "per_page": "25", "select": FIELDS})
            out[n] = _close(n, [w for w in answer.get("results") or [] if isinstance(w, dict)], year)


def close_match(titles: list[str], year: int, search: Searcher) -> dict[str, Match]:
    """The looser try alone, one search a title (for titles whose exact search missed in an earlier pass). Titles left
    out of the answer were not tried (OpenAlex's budget ran out)."""
    out: dict[str, Match] = {}
    with contextlib.suppress(BudgetExhausted):
        for n in dict.fromkeys(normalize(t) for t in titles):
            if n and _short(n):
                out[n] = Match(n)  # never matched "nearly": no search spent on it
            elif n:
                answer = search({"filter": f"title.search:{n},publication_year:{year - 1}-{year + 1}", "per_page": "25", "select": FIELDS})
                out[n] = _close(n, [w for w in answer.get("results") or [] if isinstance(w, dict)], year)
    return out


def similar(a: str, b: str) -> float:
    """How alike two normalized titles are: the words they share over the words of either (Jaccard), 0 to 1, a trailing
    plural "s" set aside ("algorithm" and "algorithms" are one word).

    >>> similar("deep iv a flexible approach for counterfactual prediction", "deep iv a flexible approach to counterfactual prediction")
    0.778
    >>> similar("adaptive gradient algorithms", "adaptive gradient algorithm")
    1.0
    """
    x, y = {_stem(w) for w in a.split()}, {_stem(w) for w in b.split()}
    return round(len(x & y) / len(x | y), 3) if x | y else 0.0


def in_order(a: str, b: str) -> float:
    """How much of the word order two titles share (0 to 1): "deep sets" and "sets deep" share the words, not the title.

    >>> in_order("deep sets", "sets deep"), in_order("adaptive gradient algorithms", "adaptive gradient algorithm")
    (0.5, 1.0)
    """
    return round(difflib.SequenceMatcher(None, [_stem(w) for w in a.split()], [_stem(w) for w in b.split()]).ratio(), 3)


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _short(norm: str) -> bool:
    return len(norm.split()) <= 2


def _close(norm: str, works: list[dict[str, Any]], year: int) -> Match:
    if _short(norm):
        return Match(norm)  # a short title ("Introduction", "Deep Sets"): exact or nothing, never "nearly"
    return _closest(norm, works, year)


def _closest(norm: str, works: list[dict[str, Any]], year: int) -> Match:
    """The looser try's pick: a title sharing at least 85% of the words (a hyphen, a plural, a dropped article), of a
    length within 15%, in the year window; the most alike, then the most cited."""
    good = []
    for w in works:
        other = normalize(str(w.get("title") or ""))
        y = w.get("publication_year")
        if not other or not isinstance(y, int) or abs(y - year) > 1:
            continue
        if similar(norm, other) >= 0.85 and in_order(norm, other) >= 0.85 and abs(len(other) - len(norm)) <= 0.15 * len(norm):
            good.append((similar(norm, other), w.get("cited_by_count") or 0, w))
    if not good:
        return Match(norm)
    good.sort(key=lambda t: (-t[0], -t[1]))
    return Match(norm, good[0][2], [str(t[2].get("id")) for t in good[1:]], how="close")
