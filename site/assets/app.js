// Shared helpers + page renderers. Data is static JSON written by pipeline/build.py.
const CAT = {
  special_situations: "Special Situations", distressed: "Distressed", macro: "Macro / Rates",
  merger_arb: "Merger Arb", beta: "Beta",
};
const KIND = { ladder: "ladder → hazard curve", survival: "survival ladder", single: "single market", menu: "outcome menu", basket: "single-name basket" };
const pct = (p, d = 1) => p == null ? "–" : (p * 100).toFixed(d) + "%";
const pts = (d, dp = 1) => d == null ? "–" : (d > 0 ? "+" : "") + (d * 100).toFixed(dp);
const usd = v => v == null ? "–" : "$" + Math.round(v).toLocaleString("en-US");
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtDate = d => new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

function deltaCell(d, z) {
  if (d == null) return '<span class="muted">–</span>';
  const arrow = d > 0.0005 ? "▲" : d < -0.0005 ? "▼" : "";
  const zf = z == null ? null : (Math.abs(z) < 0.05 ? 0 : z).toFixed(1);
  const zt = z != null && Math.abs(z) >= 2 ? `<div class="z hot">z ${zf}</div>` : z != null ? `<div class="z">z ${zf}</div>` : "";
  return `<span class="delta"><span class="arrow">${arrow}</span> ${pts(d)}</span>${zt}`;
}
const gradeCell = g => `<span class="grade ${g}" title="liquidity grade ${g}">${g}</span>`;
const dirCell = d => `<span class="dir ${d}">${d === "positive" ? "+" : d === "negative" ? "−" : "±"}</span>`;

async function getJSON(path) { const r = await fetch(path, { cache: "no-store" }); if (!r.ok) throw new Error(path + " " + r.status); return r.json(); }

async function setAsof() {
  try { const m = await getJSON("data/meta.json"); document.querySelectorAll(".asof").forEach(e => e.textContent = "data as of " + fmtDate(m.fetched_at) + " " + new Date(m.fetched_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) + " UTC"); } catch {}
}

// ---------------- board ----------------
async function renderBoard() {
  const board = await getJSON("data/board.json");
  let rows = board.rows;
  const state = { sort: "d7abs", dir: "desc", cat: "all", minGrade: "C" };
  const gradeRank = { A: 3, B: 2, C: 1 };
  const tbody = document.querySelector("#board tbody");
  const moversEl = document.querySelector("#movers");

  moversEl.innerHTML = board.movers.map(id => {
    const r = rows.find(x => x.row_id === id);
    return `<a class="mover" href="event.html?slug=${encodeURIComponent(r.slug)}"><div class="t">${esc(r.title)}${r.subtitle ? " · " + esc(r.subtitle) : ""}</div><div class="v">${pts(r.d7)} <small>pts / 7d · now ${pct(r.p)}</small></div></a>`;
  }).join("");

  function draw() {
    let v = rows.filter(r => (state.cat === "all" || r.category === state.cat) && gradeRank[r.grade] >= gradeRank[state.minGrade]);
    const key = {
      d7abs: r => Math.abs(r.d7 ?? 0), p: r => r.p ?? -1, d7: r => r.d7 ?? -9, d30: r => r.d30 ?? -9,
      title: r => r.title, grade: r => gradeRank[r.grade], category: r => r.category,
    }[state.sort];
    v.sort((a, b) => (key(a) > key(b) ? 1 : key(a) < key(b) ? -1 : 0) * (state.dir === "desc" ? -1 : 1));
    tbody.innerHTML = v.map(r => `
      <tr class="${r.headline ? "headline" : ""}">
        <td><div class="title"><a href="event.html?slug=${encodeURIComponent(r.slug)}">${esc(r.title)}</a></div>
            <div class="sub">${esc(r.subtitle)}${r.kind === "ladder" || r.kind === "survival" ? " · " + KIND[r.kind] : ""}</div></td>
        <td class="hide-sm"><span class="chip cat">${CAT[r.category] || r.category}</span></td>
        <td class="num"><span class="p ${r.grade === "C" ? "c" : ""}" title="${esc(r.p_note)}">${pct(r.p)}</span>${r.hazard_12m != null ? `<div class="z">λ ${(r.hazard_12m * 100).toFixed(0)}%/yr</div>` : ""}</td>
        <td class="num">${deltaCell(r.d7, r.z7)}</td>
        <td class="num hide-sm">${deltaCell(r.d30)}</td>
        <td class="hide-sm">${sparkline(r.spark.map(v => [0, v]))}</td>
        <td>${gradeCell(r.grade)}</td>
        <td class="hide-sm">${dirCell(r.direction)}</td>
        <td class="exp hide-sm">${r.exposures.map(esc).join(" · ")}</td>
      </tr>`).join("");
    document.querySelectorAll("#board th[data-sort]").forEach(th => {
      if (th.dataset.sort === state.sort) th.setAttribute("aria-sort", state.dir === "desc" ? "descending" : "ascending"); else th.removeAttribute("aria-sort");
    });
  }
  document.querySelectorAll("#board th[data-sort]").forEach(th => th.addEventListener("click", () => {
    if (state.sort === th.dataset.sort) state.dir = state.dir === "desc" ? "asc" : "desc"; else { state.sort = th.dataset.sort; state.dir = "desc"; }
    draw();
  }));
  document.querySelector("#f-cat").addEventListener("change", e => { state.cat = e.target.value; draw(); });
  document.querySelector("#f-grade").addEventListener("change", e => { state.minGrade = e.target.value; draw(); });
  draw();
}

// ---------------- event ----------------
async function renderEvent() {
  const slug = new URLSearchParams(location.search).get("slug");
  const root = document.querySelector("#event");
  if (!slug) { root.innerHTML = "<p>No event given.</p>"; return; }
  let ev;
  try { ev = await getJSON(`data/events/${encodeURIComponent(slug)}.json`); } catch { root.innerHTML = "<p>Unknown event.</p>"; return; }
  document.title = ev.title + " — Credit Oracle";
  const live = ev.markets.filter(m => !m.closed);
  const isLadder = ev.kind === "ladder" || ev.kind === "survival";
  const focus = ev.kind === "menu" ? (live.find(m => m.label === ev.focus) || live[0]) : live[0];
  const H = ev.hazard;

  let html = `
    <p class="small"><a href="index.html">← Catalyst Board</a></p>
    <h1>${esc(ev.title)}</h1>
    <p class="lede"><span class="chip cat">${CAT[ev.category] || ev.category}</span> &nbsp;${KIND[ev.kind]} &nbsp;·&nbsp; credit direction if YES: ${dirCell(ev.direction)}
      &nbsp;·&nbsp; <a href="${esc(ev.polymarket_url)}" rel="noopener">Polymarket ↗</a></p>`;

  // headline stats
  const stats = [];
  if (isLadder && H && H.rungs.length) {
    const p12 = interp(H, 1.0);
    stats.push(["P(within 12m)", p12 == null ? "beyond ladder" : pct(p12), "interpolated on fitted CDF"]);
    stats.push(["Implied hazard, 12m avg", p12 == null ? "–" : (-Math.log(1 - p12) * 100).toFixed(0) + "<small>%/yr</small>", "−ln(1−P)/1y"]);
    stats.push(["E[time to event | occurs]", H.expected_time_years == null ? "–" : H.expected_time_years.toFixed(2) + "<small> y</small>", "conditional on last rung"]);
    stats.push(["P(by last rung)", pct(H.p_last), H.rungs[H.rungs.length - 1].t]);
  } else if (focus) {
    stats.push([ev.kind === "menu" ? `P(${esc(focus.label)})` : "P(YES)", pct(focus.p), "mid of best bid/ask"]);
    stats.push(["Δ 7d", pts(focus.d7) + "<small> pts</small>", focus.z7 != null ? "z " + focus.z7.toFixed(1) + " vs trailing 90d" : ""]);
    stats.push(["Δ 30d", pts(focus.d30) + "<small> pts</small>", ""]);
    stats.push(["Liquidity", usd(focus.liquidity), `grade ${focus.grade}${focus.grade_reasons.length ? " · " + esc(focus.grade_reasons.join("; ")) : ""}`]);
  }
  html += `<div class="stats">${stats.map(([k, v, n]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div><div class="small muted">${n}</div></div>`).join("")}</div>`;

  if (isLadder && H && H.rungs.length) {
    html += `<div class="grid2">
      <div class="card"><h3 style="margin-top:0">Crowd-implied CDF — P(${ev.kind === "survival" ? "ends" : "event"} by t)</h3><div id="cdf"></div>
        <div class="legend"><span><span class="sw" style="background:var(--s1)"></span>isotonic fit</span><span><span class="sw" style="background:var(--muted);height:8px;width:8px;border-radius:50%"></span>raw rung (hollow = grade C)</span></div>
        ${H.violations ? `<p class="notice">${H.violations} rung(s) moved by the monotone fit — thin rungs priced below an earlier date. Raw dots shown so you can judge.</p>` : `<p class="notice">Raw rungs already monotone; fit is identity.</p>`}</div>
      <div class="card"><h3 style="margin-top:0">Implied hazard rate, piecewise-constant</h3><div id="haz"></div>
        <p class="small muted">λᵢ = −ln(Sᵢ/Sᵢ₋₁)/Δtᵢ with S = 1 − P̂. Read it like a CDS-implied hazard curve: the crowd's instantaneous event intensity for each tenor bucket.</p></div>
    </div>`;
    if (H.notes.length) html += `<p class="small muted">${H.notes.map(esc).join(" · ")}</p>`;
  }

  // probability history of the focus / headline rung
  const histM = isLadder && H && H.rungs.length ? (live.find(m => m.id === H.benchmark_market_id) || live[0]) : focus;
  if (histM && histM.history.length > 1) {
    html += `<h2>Price history — ${esc(histM.label || histM.question)}${isLadder ? " (benchmark rung)" : ""}</h2><div class="card"><div id="hist"></div></div>`;
  }

  // ladder / menu / basket table
  html += `<h2>Markets in this event</h2><div class="card" style="overflow-x:auto"><table class="plain"><thead><tr><th>Market</th><th class="num">P</th><th class="num">bid / ask</th><th class="num">Δ7d</th><th class="num">Δ30d</th><th class="num">Liquidity</th><th class="num">Volume</th><th>Grade</th></tr></thead><tbody>`;
  for (const m of ev.markets) {
    const p = ev.kind === "survival" && m.p != null ? m.p : m.p;
    html += `<tr class="${m.closed ? "muted" : ""}"><td>${esc(m.label || m.question)}${m.closed ? ' <span class="chip">resolved</span>' : ""}</td><td class="num"><b>${pct(p)}</b></td><td class="num small">${m.bid == null ? "–" : pct(m.bid, 0) + " / " + pct(m.ask, 0)}</td><td class="num">${pts(m.d7)}</td><td class="num">${pts(m.d30)}</td><td class="num">${usd(m.liquidity)}</td><td class="num">${usd(m.volume)}</td><td>${gradeCell(m.grade)}</td></tr>`;
  }
  html += `</tbody></table></div>`;

  // exposures + scenarios
  const exps = ev.kind === "basket" ? ev.names : ev.exposures_full;
  html += `<div class="grid2" style="margin-top:16px">
    <div class="card"><h3 style="margin-top:0">Exposed instruments</h3>${exps.map(e => `
      <div class="exposure"><div class="issuer">${esc(e.issuer)} <span class="chip">${esc(e.confidence)} confidence</span></div>
        <div class="instr">${(e.instruments || []).map(i => `${i.isin ? `<code>${esc(i.isin)}</code> ` : ""}${esc(i.type)} — ${esc(i.note)}${i.verify ? ' <span class="muted">(ISIN to verify)</span>' : ""}`).join("<br>")}</div>
        <div class="chan">${esc(e.channel)}</div></div>`).join("")}</div>
    <div class="card"><h3 style="margin-top:0">Scenarios</h3><div class="scen">
      ${["best", "base", "worst"].map(k => `<div class="k">${k}</div><div>${esc(ev.scenarios[k] || "")}</div>`).join("")}</div>
      ${ev.resolution ? `<details class="res" style="margin-top:14px"><summary class="small">Polymarket resolution rules</summary><p>${esc(ev.resolution)}</p></details>` : ""}</div>
  </div>`;
  root.innerHTML = html;

  if (isLadder && H && H.rungs.length) {
    const raw = H.rungs.map((r, i) => ({ tenor: H.tenor_years[i], value: r.p_raw, hollow: r.grade === "C", label: r.label }));
    tenorChart(document.querySelector("#cdf"), [{ name: "fit", color: "--s1", tenor: H.tenor_years, values: H.p_fit, raw }], { ymax: 1 });
    tenorChart(document.querySelector("#haz"), [{ name: "hazard", color: "--s1", tenor: H.tenor_years, values: H.hazard, step: true }], { fmt: v => Math.round(v * 100) + "%/yr" });
  }
  if (histM && histM.history.length > 1) lineChart(document.querySelector("#hist"), histM.history);
}

function interp(H, t) {
  const xs = H.tenor_years, ys = H.p_fit;
  if (!xs.length || t > xs[xs.length - 1]) return null;
  let px = 0, py = 0;
  for (let i = 0; i < xs.length; i++) { if (t <= xs[i]) return xs[i] > px ? py + (ys[i] - py) * (t - px) / (xs[i] - px) : ys[i]; px = xs[i]; py = ys[i]; }
  return ys[ys.length - 1];
}

// ---------------- hazard overlay ----------------
async function renderHazard() {
  const data = await getJSON("data/hazard.json");
  const root = document.querySelector("#hazard");
  if (!data.curves.length) { root.innerHTML = "<p>No ladder markets in the current mapping.</p>"; return; }
  const curves = data.curves.slice(0, 4); // categorical cap: ≤4 direct-labelled series
  root.innerHTML = `
    <div class="card"><h3 style="margin-top:0">Crowd-implied hazard curves, all ladders</h3><div id="ov"></div>
      <div class="legend">${curves.map((c, i) => `<span><span class="sw" style="background:var(--s${i + 1})"></span>${esc(c.title)}${c.kind === "survival" ? " (hazard of ending)" : ""}</span>`).join("")}</div></div>
    <h2>Per-ladder detail</h2>
    <div class="card" style="overflow-x:auto"><table class="plain"><thead><tr><th>Ladder</th><th class="num">rungs</th><th class="num">P(12m)</th><th class="num">λ 12m</th><th class="num">E[T | occurs]</th><th class="num">P(last rung)</th><th class="num">moved by fit</th></tr></thead><tbody>
      ${data.curves.map(c => { const p12 = interp(c, 1); return `<tr><td><a href="event.html?slug=${encodeURIComponent(c.slug)}">${esc(c.title)}</a></td><td class="num">${c.rungs.length}</td><td class="num">${p12 == null ? "–" : pct(p12)}</td><td class="num">${p12 == null ? "–" : (-Math.log(1 - p12) * 100).toFixed(0) + "%/yr"}</td><td class="num">${c.expected_time_years == null ? "–" : c.expected_time_years.toFixed(2) + " y"}</td><td class="num">${pct(c.p_last)}</td><td class="num">${c.violations}</td></tr>`; }).join("")}
    </tbody></table></div>`;
  tenorChart(document.querySelector("#ov"), curves.map((c, i) => ({ name: c.title, color: `--s${i + 1}`, tenor: c.tenor_years, values: c.hazard, step: true })), { fmt: v => Math.round(v * 100) + "%/yr", h: 300 });
}

setAsof();
