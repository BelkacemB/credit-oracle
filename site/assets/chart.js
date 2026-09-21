// Minimal SVG charts: a time-series line, a step/tenor chart, sparklines.
// Written against the CSS tokens in style.css; no library.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  };
  const fmtPct = (p, d = 1) => (p * 100).toFixed(d) + "%";
  const fmtDate = (d) => new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "2-digit" });

  function niceTicks(min, max, n = 4) {
    const span = max - min || 1;
    const raw = span / n;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
    const out = [];
    for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }

  // Re-render registry so charts re-fit on resize instead of scaling their type.
  const renders = new Map();
  let rt = null;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => renders.forEach(fn => fn()), 120); });
  const register = (container, fn) => { renders.set(container, fn); };

  function frame(container, { w, h = 260, ml = 52, mr = 16, mt = 14, mb = 28 } = {}) {
    container.classList.add("chart");
    container.innerHTML = "";
    w = w || Math.max(280, Math.round(container.clientWidth || 720));
    if (w < 480) { h = Math.round(h * 0.85); ml = 44; }
    const svg = el("svg", { viewBox: `0 0 ${w} ${h}`, role: "img" }, container);
    const tip = document.createElement("div");
    tip.className = "tip";
    container.appendChild(tip);
    return { svg, tip, w, h, ml, mr, mt, mb, pw: w - ml - mr, ph: h - mt - mb };
  }

  function yAxis(f, y, ticks, fmt) {
    const g = el("g", { class: "grid" }, f.svg);
    const a = el("g", { class: "axis" }, f.svg);
    for (const t of ticks) {
      el("line", { x1: f.ml, x2: f.ml + f.pw, y1: y(t), y2: y(t) }, g);
      const tx = el("text", { x: f.ml - 6, y: y(t) + 4, "text-anchor": "end" }, a);
      tx.textContent = fmt(t);
    }
  }

  // ---- time-series line ---------------------------------------------------
  // series: [[isoDate, p], ...]  single series -> no legend (title names it)
  window.lineChart = function (container, series, opts = {}) {
    if (!series || series.length < 2) { container.innerHTML = '<p class="muted small">No price history yet.</p>'; return; }
    register(container, () => window.lineChart(container, series, opts));
    const f = frame(container, opts);
    const xs = series.map(d => new Date(d[0]).getTime());
    const ys = series.map(d => d[1]);
    const x0 = opts.x0 != null ? new Date(opts.x0).getTime() : Math.min(...xs), x1 = opts.x1 != null ? new Date(opts.x1).getTime() : Math.max(...xs);
    let ymin = 0, ymax = Math.max(0.1, Math.min(1, Math.max(...ys) * 1.15));
    if (opts.full) { ymin = 0; ymax = 1; }
    if (opts.price) { const lo = Math.min(...ys), hi = Math.max(...ys), pad = Math.max(0.5, (hi - lo) * 0.12); ymin = lo - pad; ymax = hi + pad; }
    const fmtV = opts.price ? (v => v.toFixed(opts.dp ?? 1)) : fmtPct;
    const x = v => f.ml + (v - x0) / (x1 - x0 || 1) * f.pw;
    const y = v => f.mt + f.ph - (v - ymin) / (ymax - ymin) * f.ph;
    yAxis(f, y, niceTicks(ymin, ymax, 4), opts.price ? (v => v.toFixed(0)) : (v => Math.round(v * 100) + "%"));
    // x ticks: ~5 evenly spaced dates
    const ax = el("g", { class: "axis" }, f.svg);
    el("line", { x1: f.ml, x2: f.ml + f.pw, y1: y(ymin), y2: y(ymin) }, ax);
    for (let i = 0; i <= 4; i++) {
      const t = x0 + (x1 - x0) * i / 4;
      const tx = el("text", { x: x(t), y: f.h - 8, "text-anchor": i === 0 ? "start" : i === 4 ? "end" : "middle" }, ax);
      tx.textContent = fmtDate(t);
    }
    const path = series.map((d, i) => (i ? "L" : "M") + x(xs[i]).toFixed(1) + " " + y(ys[i]).toFixed(1)).join(" ");
    if (!opts.price) el("path", { class: "area", d: path + ` L${x(xs[xs.length - 1]).toFixed(1)} ${y(ymin)} L${x(xs[0]).toFixed(1)} ${y(ymin)} Z` }, f.svg);
    el("path", { class: "line", d: path, style: opts.color ? `stroke:var(${opts.color})` : "" }, f.svg);
    // end label
    const last = series[series.length - 1];
    const dot = el("circle", { class: "dot", r: 4, cx: x(xs[xs.length - 1]), cy: y(last[1]), style: opts.color ? `fill:var(${opts.color})` : "" }, f.svg);
    const lbl = el("text", { class: "lbl", x: x(xs[xs.length - 1]) - 8, y: y(last[1]) - 10, "text-anchor": "end" }, f.svg);
    lbl.textContent = fmtV(last[1]);
    // hover
    const cross = el("line", { class: "crosshair", y1: f.mt, y2: f.mt + f.ph, x1: -10, x2: -10 }, f.svg);
    const hdot = el("circle", { class: "dot", r: 4, cx: -10, cy: -10, visibility: "hidden" }, f.svg);
    f.svg.addEventListener("mousemove", ev => {
      const r = f.svg.getBoundingClientRect();
      const px = (ev.clientX - r.left) / r.width * f.w;
      const t = x0 + (px - f.ml) / f.pw * (x1 - x0);
      let i = 0; while (i < xs.length - 1 && xs[i + 1] <= t) i++;
      if (i < xs.length - 1 && Math.abs(xs[i + 1] - t) < Math.abs(xs[i] - t)) i++;
      cross.setAttribute("x1", x(xs[i])); cross.setAttribute("x2", x(xs[i]));
      hdot.setAttribute("cx", x(xs[i])); hdot.setAttribute("cy", y(ys[i])); hdot.setAttribute("visibility", "visible");
      f.tip.style.display = "block";
      f.tip.innerHTML = `${fmtDate(xs[i])}<br><b>${fmtV(ys[i])}</b>`;
      const left = (x(xs[i]) / f.w) * r.width;
      f.tip.style.left = Math.min(left + 12, r.width - f.tip.offsetWidth - 4) + "px";
      f.tip.style.top = (y(ys[i]) / f.h) * r.height - 40 + "px";
    });
    f.svg.addEventListener("mouseleave", () => { f.tip.style.display = "none"; cross.setAttribute("x1", -10); cross.setAttribute("x2", -10); hdot.setAttribute("visibility", "hidden"); });
  };

  // ---- tenor chart (CDF or hazard vs years) ---------------------------------
  // curves: [{name, color:'--s1', tenor:[...], values:[...], step:bool, raw:[{tenor,value,hollow,label}]}]
  window.tenorChart = function (container, curves, opts = {}) {
    register(container, () => window.tenorChart(container, curves, opts));
    const f = frame(container, Object.assign({ h: 240 }, opts));
    const allT = curves.flatMap(c => c.tenor), allV = curves.flatMap(c => c.values).concat(curves.flatMap(c => (c.raw || []).map(r => r.value)));
    const x1 = Math.max(0.5, ...allT);
    const ymax = opts.ymax != null ? opts.ymax : Math.max(0.05, Math.max(...allV) * 1.15);
    const x = v => f.ml + v / x1 * f.pw;
    const y = v => f.mt + f.ph - v / ymax * f.ph;
    yAxis(f, y, niceTicks(0, ymax, 4), opts.fmt || (v => Math.round(v * 100) + "%"));
    const ax = el("g", { class: "axis" }, f.svg);
    el("line", { x1: f.ml, x2: f.ml + f.pw, y1: y(0), y2: y(0) }, ax);
    for (const t of niceTicks(0, x1, 5)) {
      const tx = el("text", { x: x(t), y: f.h - 8, "text-anchor": "middle" }, ax);
      tx.textContent = t + "y";
    }
    const hits = [];
    curves.forEach((c, ci) => {
      const col = `var(${c.color || "--s" + ((ci % 8) + 1)})`;
      let d = "";
      if (c.step) {
        // piecewise-constant on (t_{i-1}, t_i]
        let prev = 0;
        c.tenor.forEach((t, i) => { d += `${i ? "L" : "M"}${x(prev).toFixed(1)} ${y(c.values[i]).toFixed(1)} L${x(t).toFixed(1)} ${y(c.values[i]).toFixed(1)} `; prev = t; });
      } else {
        d = "M" + x(0) + " " + y(0) + " " + c.tenor.map((t, i) => `L${x(t).toFixed(1)} ${y(c.values[i]).toFixed(1)}`).join(" ");
      }
      el("path", { class: "line", d, style: `stroke:${col}` }, f.svg);
      (c.raw || []).forEach(r => {
        const dot = el("circle", { class: "dot raw" + (r.hollow ? " hollow" : ""), r: 4, cx: x(r.tenor), cy: y(r.value) }, f.svg);
        hits.push({ cx: x(r.tenor), cy: y(r.value), html: `${r.label}<br><b>${fmtPct(r.value)}</b> raw${r.hollow ? " · grade C" : ""}` });
      });
      c.tenor.forEach((t, i) => {
        hits.push({ cx: x(t), cy: y(c.values[i]), html: `${c.name}<br>${t.toFixed(2)}y → <b>${(opts.fmt || fmtPct)(c.values[i])}</b>` });
      });
      if (curves.length > 1 && curves.length <= 4) {
        // direct label sits above the last segment, inside the plot
        const lt = el("text", { class: "lbl", x: x(c.tenor[c.tenor.length - 1]), y: y(c.values[c.values.length - 1]) - 6, "text-anchor": "end" }, f.svg);
        lt.textContent = c.name;
      }
    });
    const hdot = el("circle", { class: "dot", r: 5, cx: -10, cy: -10, visibility: "hidden", style: "fill:none;stroke:var(--ink)" }, f.svg);
    f.svg.addEventListener("mousemove", ev => {
      const r = f.svg.getBoundingClientRect();
      const px = (ev.clientX - r.left) / r.width * f.w, py = (ev.clientY - r.top) / r.height * f.h;
      let best = null, bd = 1e9;
      for (const h of hits) { const d = (h.cx - px) ** 2 + (h.cy - py) ** 2; if (d < bd) { bd = d; best = h; } }
      if (!best || bd > 30 * 30) { f.tip.style.display = "none"; hdot.setAttribute("visibility", "hidden"); return; }
      hdot.setAttribute("cx", best.cx); hdot.setAttribute("cy", best.cy); hdot.setAttribute("visibility", "visible");
      f.tip.style.display = "block"; f.tip.innerHTML = best.html;
      f.tip.style.left = Math.min(best.cx / f.w * r.width + 12, r.width - f.tip.offsetWidth - 4) + "px";
      f.tip.style.top = best.cy / f.h * r.height - 44 + "px";
    });
    f.svg.addEventListener("mouseleave", () => { f.tip.style.display = "none"; hdot.setAttribute("visibility", "hidden"); });
  };

  window.sparkline = function (series, w = 84, h = 24) {
    if (!series || series.length < 2) return "";
    const ys = series.map(d => d[1]);
    const mn = Math.min(...ys), mx = Math.max(...ys);
    const pts = ys.map((v, i) => `${(i / (ys.length - 1) * (w - 2) + 1).toFixed(1)},${(h - 2 - (mx > mn ? (v - mn) / (mx - mn) : 0.5) * (h - 4)).toFixed(1)}`);
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path d="M${pts.join(" L")}"/></svg>`;
  };
})();

// ---- scatter (weekly Δcrowd vs Δbond) --------------------------------------
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}, parent) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (parent) parent.appendChild(e); return e; };
  window.scatterChart = function (container, pairs, opts = {}) {
    container.classList.add("chart"); container.innerHTML = "";
    const w = Math.max(280, Math.round(container.clientWidth || 480)), h = opts.h || 260, ml = 48, mr = 14, mt = 14, mb = 30;
    const pw = w - ml - mr, ph = h - mt - mb;
    const svg = el("svg", { viewBox: `0 0 ${w} ${h}`, role: "img" }, container);
    const tip = document.createElement("div"); tip.className = "tip"; container.appendChild(tip);
    const xs = pairs.map(p => p[0]), ys = pairs.map(p => p[1]);
    const xm = Math.max(1, ...xs.map(Math.abs)), ym = Math.max(0.5, ...ys.map(Math.abs));
    const x = v => ml + (v + xm) / (2 * xm) * pw, y = v => mt + ph - (v + ym) / (2 * ym) * ph;
    const g = el("g", { class: "grid" }, svg), ax = el("g", { class: "axis" }, svg);
    el("line", { x1: ml, x2: ml + pw, y1: y(0), y2: y(0), class: "axis" }, g);
    el("line", { y1: mt, y2: mt + ph, x1: x(0), x2: x(0) }, g);
    for (const v of [-xm, xm]) { const t = el("text", { x: x(v), y: h - 8, "text-anchor": v < 0 ? "start" : "end" }, ax); t.textContent = (v > 0 ? "+" : "") + v.toFixed(0) + " pts"; }
    for (const v of [-ym, ym]) { const t = el("text", { x: ml - 6, y: y(v) + 4, "text-anchor": "end" }, ax); t.textContent = (v > 0 ? "+" : "") + v.toFixed(1); }
    if (opts.beta != null) {
      el("line", { class: "line", x1: x(-xm), y1: y(-xm * opts.beta), x2: x(xm), y2: y(xm * opts.beta), style: "stroke:var(--s1);stroke-dasharray:4 3;stroke-width:1.5" }, svg);
    }
    const hits = [];
    pairs.forEach(p => { el("circle", { class: "dot", r: 4, cx: x(p[0]), cy: y(p[1]), style: "fill:var(--s1);fill-opacity:.75" }, svg); hits.push({ cx: x(p[0]), cy: y(p[1]), html: `Δcrowd <b>${p[0] > 0 ? "+" : ""}${p[0].toFixed(1)} pts</b><br>Δbond <b>${p[1] > 0 ? "+" : ""}${p[1].toFixed(2)} pts</b>` }); });
    const xl = el("text", { class: "lbl", x: ml + pw, y: mt + ph - 6, "text-anchor": "end" }, svg); xl.textContent = "Δ crowd probability, " + (opts.step || 7) + "d";
    const yl = el("text", { class: "lbl", x: ml + 6, y: mt + 12 }, svg); yl.textContent = "Δ bond price";
    svg.addEventListener("mousemove", ev => {
      const r = svg.getBoundingClientRect(); const px = (ev.clientX - r.left) / r.width * w, py = (ev.clientY - r.top) / r.height * h;
      let best = null, bd = 1e9; for (const hh of hits) { const d = (hh.cx - px) ** 2 + (hh.cy - py) ** 2; if (d < bd) { bd = d; best = hh; } }
      if (!best || bd > 400) { tip.style.display = "none"; return; }
      tip.style.display = "block"; tip.innerHTML = best.html; tip.style.left = Math.min(best.cx / w * r.width + 12, r.width - tip.offsetWidth - 4) + "px"; tip.style.top = best.cy / h * r.height - 44 + "px";
    });
    svg.addEventListener("mouseleave", () => { tip.style.display = "none"; });
  };
})();

// ---- heatmap (time × tenor, sequential single hue) -------------------------
(function () {
  const RAMP_L = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"];
  const isDark = () => document.documentElement.dataset.theme === "dark" || (document.documentElement.dataset.theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  window.heatmap = function (container, rows, tenors, opts = {}) {
    container.innerHTML = "";
    const vals = rows.flatMap(r => r.avg_hazard).filter(v => v != null);
    if (!vals.length) { container.innerHTML = '<p class="muted small">No history yet.</p>'; return; }
    const vmax = Math.max(...vals), vmin = Math.min(...vals);
    const ramp = isDark() ? RAMP_L.slice().reverse() : RAMP_L;   // dark: light = high, so "near zero" recedes to the dark surface
    const color = v => ramp[Math.min(ramp.length - 1, Math.floor((v - vmin) / (vmax - vmin || 1) * (ramp.length - 1)))];
    let html = `<div class="hm"><div class="hm-head"><span class="hm-date"></span>${tenors.map(t => `<span>${t}y</span>`).join("")}</div>`;
    const step = Math.max(1, Math.ceil(rows.length / 40));
    rows.forEach((r, i) => {
      html += `<div class="hm-row"><span class="hm-date">${i % step === 0 || i === rows.length - 1 ? r.asof.slice(5) : ""}</span>${r.avg_hazard.map((v, j) => v == null ? `<span class="hm-cell empty"></span>` : `<span class="hm-cell" style="background:${color(v)}" title="${r.asof} · ${tenors[j]}y · ${(v * 100).toFixed(0)}%/yr"></span>`).join("")}</div>`;
    });
    html += `</div><div class="legend"><span>avg. hazard to tenor, %/yr</span><span class="hm-scale">${ramp.map(c => `<i style="background:${c}"></i>`).join("")}</span><span>${(vmin * 100).toFixed(0)}% → ${(vmax * 100).toFixed(0)}%</span></div>`;
    container.innerHTML = html;
  };
})();
