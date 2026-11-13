"""The site: one self-contained page (no libraries, fonts or trackers fetched) that reads the JSON next to it. Pick a
venue and a year (or all years), sort by citations, field-normalized percentile, FWCI or recent citations, search
titles; each venue-year links its proceedings (the official list) and says how many of its papers OpenAlex has.
Text from the data is set with textContent, never as HTML."""

from __future__ import annotations

from pathlib import Path

PAGE = r"""<!doctype html>
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
select,input{font:inherit;color:var(--fg);background:var(--chip);border:1px solid var(--line);border-radius:6px;padding:6px 10px;max-width:100%}
input{flex:1;min-width:200px}.note{font-size:13px;color:var(--muted);margin:0 0 12px}.note a{color:var(--accent)}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top}
th:nth-child(2),td:nth-child(2){text-align:left}th{font-size:13px;color:var(--muted);font-weight:600}td a{color:var(--fg);text-decoration:none}td a:hover{color:var(--accent);text-decoration:underline}
.tag{display:inline-block;font-size:11px;padding:0 6px;border-radius:10px;border:1px solid var(--line);color:var(--muted);margin-left:6px}
footer{margin-top:28px;font-size:13px;color:var(--muted)}footer a{color:var(--accent)}
td:nth-child(2){overflow-wrap:anywhere}
@media (max-width:640px){th:nth-child(3),td:nth-child(3),th:nth-child(5),td:nth-child(5),th:nth-child(6),td:nth-child(6){display:none}
  table{font-size:14px}th,td{padding:6px 4px}select{flex:1 1 100%}
  table[data-sort="fwci"] th:nth-child(5),table[data-sort="fwci"] td:nth-child(5),table[data-sort="percentile"] th:nth-child(6),table[data-sort="percentile"] td:nth-child(6){display:table-cell}}
</style>
</head>
<body>
<main>
<h1>paper-<span>impact</span></h1>
<p class="lead">Which papers at AI venues mattered: every paper the proceedings list, with its citations and field-normalized impact from OpenAlex.</p>
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
let index = null; const cache = new Map(); let ticket = 0;
function el(tag, text, attrs) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v); return e; }
function num(v, digits) { return v === null || v === undefined ? "–" : digits ? v.toFixed(digits) : v.toLocaleString("en-US"); }
function safe(url) { return typeof url === "string" && /^https?:\/\//i.test(url) ? url : ""; }  // never a javascript: link
async function load(file) {
  if (!cache.has(file)) cache.set(file, fetch(file).then((r) => { if (!r.ok) throw new Error(file + ": " + r.status); return r.json(); }).catch((e) => { cache.delete(file); throw e; }));
  return cache.get(file);
}
function option(select, value, text) { select.append(el("option", text, { value: String(value) })); }
function years() {  // the years of the venue picked, keeping the year picked when it has one
  const venue = $("venue").value, keep = $("year").value, select = $("year");
  const ys = index.venue_years.filter((vy) => vy.venue === venue).map((vy) => vy.year).sort((a, b) => b - a);
  select.replaceChildren(); option(select, "all", "All years"); for (const y of ys) option(select, y, String(y));
  select.value = ys.map(String).includes(keep) ? keep : "all";
}
async function render() {
  const mine = ++ticket;  // a slower earlier render must not overwrite this one
  const venue = $("venue").value, year = $("year").value, sort = $("sort").value, q = $("q").value.trim().toLowerCase();
  const vys = index.venue_years.filter((vy) => vy.venue === venue && (year === "all" || String(vy.year) === year));
  let files;
  try { files = await Promise.all(vys.map((vy) => load(vy.file))); }
  catch (e) { if (mine === ticket) $("note").textContent = "The data could not be read: " + e.message + " (try again)"; return; }
  if (mine !== ticket) return;
  let papers = files.flatMap((f) => f.papers);
  if (q) papers = papers.filter((p) => p.title.toLowerCase().includes(q));
  papers.sort((a, b) => (b[sort] ?? -1) - (a[sort] ?? -1) || (b.cited_by_count ?? -1) - (a.cited_by_count ?? -1));
  document.querySelector("table").dataset.sort = sort;
  const rows = $("rows"); rows.replaceChildren();
  papers.slice(0, 500).forEach((p, i) => {
    const tr = el("tr"); tr.append(el("td", String(i + 1)));
    const td = el("td"), href = safe(p.url) || safe(p.doi) || safe(p.id);
    td.append(href ? el("a", p.title, { href, rel: "noopener" }) : el("span", p.title));
    if (p.top1) td.append(el("span", "top 1%", { class: "tag" })); else if (p.top10) td.append(el("span", "top 10%", { class: "tag" }));
    tr.append(td, el("td", String(p.year)), el("td", num(p.cited_by_count)), el("td", num(p.fwci, 1)), el("td", p.percentile === null || p.percentile === undefined ? "–" : (100 * p.percentile).toFixed(1)), el("td", num(p.recent)));
    rows.append(tr);
  });
  const note = $("note"); note.replaceChildren();
  if (!vys.length) { note.textContent = "No proceedings for this choice."; return; }
  const listed = vys.reduce((n, vy) => n + vy.listed, 0), matched = vys.reduce((n, vy) => n + vy.matched, 0);
  const shown = papers.length > 500 ? `The first 500 of ${papers.length.toLocaleString("en-US")} papers` : `${papers.length.toLocaleString("en-US")} papers`;
  const normalized = papers.filter((p) => p.percentile !== null && p.percentile !== undefined).length, found = papers.filter((p) => p.id).length;
  const scope = found ? `OpenAlex gives FWCI and the field-normalized percentile for ${normalized.toLocaleString("en-US")} of the ${found.toLocaleString("en-US")} found (not for preprint records, among others); sorting by them ranks those, the rest come last. ` : "";
  if (vys.length === 1) {
    const vy = vys[0], src = safe(vy.source);
    note.append(el("span", `${shown}. The `), src ? el("a", "proceedings", { href: src, rel: "noopener" }) : el("span", "proceedings"),
      el("span", ` of ${vy.venue} ${vy.year} list ${vy.listed.toLocaleString("en-US")}; ${vy.matched.toLocaleString("en-US")} (${(100 * (vy.coverage || 0)).toFixed(0)}%) were found in OpenAlex. Papers not found (yet) are listed without numbers. ` + scope));
  } else {
    note.append(el("span", `${shown}. The proceedings list ${listed.toLocaleString("en-US")}; ${matched.toLocaleString("en-US")} (${listed ? (100 * matched / listed).toFixed(0) : 0}%) were found in OpenAlex. ` + scope));
  }
}
async function start() {
  try { index = await load("data/index.json"); } catch (e) { $("note").textContent = "The data could not be read: " + e.message; return; }
  for (const v of index.venues) option($("venue"), v.name, v.full ? `${v.name} — ${v.full}` : v.name);
  years();
  $("footer").append(el("span", `Data: ${index.source}; built ${index.generated} by paper-impact ${index.tool_version}. `), el("a", "The data as JSON", { href: "data/index.json" }), el("span", " · "), el("a", "Source", { href: "https://github.com/zch6a/paper-impact" }));
  $("venue").addEventListener("change", () => { years(); render(); });
  for (const id of ["year", "sort"]) $(id).addEventListener("change", render);
  let typing; $("q").addEventListener("input", () => { clearTimeout(typing); typing = setTimeout(render, 150); });
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
