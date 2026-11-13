"""The site: one self-contained page (no libraries, fonts or trackers fetched) that reads the JSON next to it. Pick a
venue and a year (or all years), sort by citations, field-normalized percentile, FWCI or recent citations, search
titles; each venue-year says how much of it OpenAlex covers against the official count, with that count's source.
Text from the data is set with textContent, never as HTML."""

from __future__ import annotations

from pathlib import Path

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>paper-impact</title>
<meta name="description" content="Which papers at AI venues mattered: citations and field-normalized impact from OpenAlex, by venue and year.">
<style>
:root{--bg:#ffffff;--fg:#1f2328;--muted:#57606a;--line:#d0d7de;--accent:#0969da;--chip:#f6f8fa}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--muted:#8b949e;--line:#30363d;--accent:#58a6ff;--chip:#161b22}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}h1{font-size:26px;margin:0 0 4px}h1 span{color:var(--accent)}
.lead{color:var(--muted);margin:0 0 18px}.controls{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 12px}
select,input{font:inherit;color:var(--fg);background:var(--chip);border:1px solid var(--line);border-radius:6px;padding:6px 10px}
input{flex:1;min-width:200px}.note{font-size:13px;color:var(--muted);margin:0 0 12px}.note a{color:var(--accent)}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top}
th:nth-child(2),td:nth-child(2){text-align:left}th{font-size:13px;color:var(--muted);font-weight:600}td a{color:var(--fg);text-decoration:none}td a:hover{color:var(--accent);text-decoration:underline}
.tag{display:inline-block;font-size:11px;padding:0 6px;border-radius:10px;border:1px solid var(--line);color:var(--muted);margin-left:6px}
footer{margin-top:28px;font-size:13px;color:var(--muted)}footer a{color:var(--accent)}
@media (max-width:640px){th:nth-child(5),td:nth-child(5),th:nth-child(6),td:nth-child(6){display:none}}
</style>
</head>
<body>
<main>
<h1>paper-<span>impact</span></h1>
<p class="lead">Which papers at AI venues mattered: citations and field-normalized impact from OpenAlex, by venue and year.</p>
<div class="controls">
  <select id="venue" aria-label="Venue"></select>
  <select id="year" aria-label="Year"></select>
  <select id="sort" aria-label="Sort by">
    <option value="cited_by_count">Most cited</option>
    <option value="percentile">Field-normalized percentile</option>
    <option value="fwci">FWCI</option>
    <option value="recent">Cited most in the last two years</option>
  </select>
  <input id="q" type="search" placeholder="Search titles" aria-label="Search titles">
</div>
<p class="note" id="note"></p>
<table>
  <thead><tr><th>#</th><th>Paper</th><th>Year</th><th>Citations</th><th title="Field-weighted citation impact: 1.0 is the world average for the field and year">FWCI</th><th title="OpenAlex's field-normalized citation percentile">Percentile</th><th title="Citations in the last two complete years">Recent</th></tr></thead>
  <tbody id="rows"></tbody>
</table>
<footer id="footer"></footer>
</main>
<script>
"use strict";
const $ = (id) => document.getElementById(id);
let index = null; const cache = new Map();
function el(tag, text, attrs) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v); return e; }
function num(v, digits) { return v === null || v === undefined ? "–" : digits ? v.toFixed(digits) : v.toLocaleString("en-US"); }
async function load(file) { if (!cache.has(file)) cache.set(file, fetch(file).then((r) => { if (!r.ok) throw new Error(file + ": " + r.status); return r.json(); })); return cache.get(file); }
function option(select, value, text) { select.append(el("option", text, { value: String(value) })); }
async function render() {
  const venue = $("venue").value, year = $("year").value, sort = $("sort").value, q = $("q").value.trim().toLowerCase();
  const vys = index.venue_years.filter((vy) => vy.venue === venue && (year === "all" || String(vy.year) === year));
  const files = await Promise.all(vys.map((vy) => load(vy.file)));
  let papers = files.flatMap((f) => f.papers);
  if (q) papers = papers.filter((p) => p.title.toLowerCase().includes(q));
  papers.sort((a, b) => (b[sort] ?? -1) - (a[sort] ?? -1) || b.cited_by_count - a.cited_by_count);
  const rows = $("rows"); rows.replaceChildren();
  papers.slice(0, 500).forEach((p, i) => {
    const tr = el("tr"); tr.append(el("td", String(i + 1)));
    const td = el("td"); td.append(el("a", p.title, { href: p.doi || p.id, rel: "noopener" }));
    if (p.top1) td.append(el("span", "top 1%", { class: "tag" })); else if (p.top10) td.append(el("span", "top 10%", { class: "tag" }));
    tr.append(td, el("td", String(p.year)), el("td", num(p.cited_by_count)), el("td", num(p.fwci, 1)), el("td", p.percentile === null ? "–" : (100 * p.percentile).toFixed(1)), el("td", num(p.recent)));
    rows.append(tr);
  });
  const note = $("note"); note.replaceChildren();
  const parts = [papers.length > 500 ? `the first 500 of ${papers.length.toLocaleString("en-US")} papers` : `${papers.length.toLocaleString("en-US")} papers`];
  if (vys.length === 1) {
    const vy = vys[0];
    parts.push(`OpenAlex lists ${vy.openalex_count.toLocaleString("en-US")} works for ${vy.venue} ${vy.year}`);
    if (!vy.complete) parts.push(`only the ${vy.papers} most cited are here (built without an OpenAlex key)`);
    note.append(el("span", parts.join("; ")));
    if (vy.official_count) { note.append(el("span", `; the venue accepted ${vy.official_count.toLocaleString("en-US")} (`)); note.append(el("a", "source", { href: vy.official_source, rel: "noopener" })); note.append(el("span", `): coverage ${(100 * vy.coverage).toFixed(0)}%.`)); }
    else note.append(el("span", "."));
  } else {
    const partial = vys.filter((vy) => !vy.complete).length;
    note.append(el("span", parts.join("; ") + (partial ? `; ${partial} of ${vys.length} years hold only their most cited papers.` : ".")));
  }
}
async function start() {
  try { index = await load("data/index.json"); } catch (e) { $("note").textContent = "The data could not be read: " + e.message; return; }
  for (const v of index.venues) option($("venue"), v.name, v.full ? `${v.name} — ${v.full}` : v.name);
  const years = [...new Set(index.venue_years.map((vy) => vy.year))].sort((a, b) => b - a);
  option($("year"), "all", "All years"); for (const y of years) option($("year"), y, String(y));
  $("footer").append(el("span", `Data: ${index.source}; built ${index.generated} by paper-impact ${index.tool_version}. `), el("a", "The data as JSON", { href: "data/index.json" }), el("span", " · "), el("a", "Source", { href: "https://github.com/zch6a/paper-impact" }));
  for (const id of ["venue", "year", "sort"]) $(id).addEventListener("change", render);
  $("q").addEventListener("input", render);
  render();
}
start();
</script>
</body>
</html>
"""


def write_site(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / "index.html"
    path.write_text(PAGE, encoding="utf-8")
    return path
