// The stats page (templates/stats.html): maps of MPs placed by how alike they
// vote (positions from sejmomat/stats.py, dane/statystyki.json), drawn on
// canvas in club colours; hover shows the MP, a click opens their page, a
// club in the legend is highlighted on every map. And the chart of margins.
(() => {
  const page = document.getElementById("stats");
  if (!page) return;
  const L = JSON.parse(page.dataset.labels);
  const ROOT = page.dataset.root;
  const css = getComputedStyle(page);
  // former and provisional ids share their club's colour
  const SAME = { "Polska2050-TD": "Polska2050", PSL: "PSL-TD", Nowa_Lewica: "Lewica" };
  const colour = (club) => css.getPropertyValue(`--c-${SAME[club] || club}`).trim() || css.getPropertyValue("--c-other").trim();
  const ink = () => getComputedStyle(document.body).color;
  const edgeRGB = css.getPropertyValue("--edge").trim();
  let focus = null;   // highlighted club
  const maps = [];

  const draw = (m) => {
    const { canvas, data, big } = m;
    const w = canvas.clientWidth, h = canvas.clientHeight, dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    // fit the map to the canvas, keeping its proportions
    const pad = big ? 24 : 8, xs = data.mps.map((p) => p[1]), ys = data.mps.map((p) => p[2]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const s = Math.min((w - 2 * pad) / ((x1 - x0) || 1), (h - 2 * pad) / ((y1 - y0) || 1));
    const ox = (w - (x1 - x0) * s) / 2 - x0 * s, oy = (h - (y1 - y0) * s) / 2 - y0 * s;
    m.pts = data.mps.map(([id, x, y, club, name]) => ({ id, club, name, px: ox + x * s, py: oy + y * s }));
    const lit = (p) => !focus || (SAME[p.club] || p.club) === focus;
    // links first, faint; links of the highlighted club a little stronger
    ctx.lineWidth = big ? 0.5 : 0.35;
    for (const [i, j] of data.edges) {
      const a = m.pts[i], b = m.pts[j];
      const on = focus && lit(a) && lit(b);
      ctx.strokeStyle = `rgba(${edgeRGB}, ${focus ? (on ? 0.35 : 0.03) : 0.12})`;
      ctx.beginPath();
      ctx.moveTo(a.px, a.py);
      ctx.lineTo(b.px, b.py);
      ctx.stroke();
    }
    const r = big ? 3.2 : 2.2;
    for (const p of [...m.pts].sort((a, b) => lit(a) - lit(b))) {
      ctx.globalAlpha = lit(p) ? 1 : 0.15;
      ctx.fillStyle = colour(p.club);
      ctx.beginPath();
      ctx.arc(p.px, p.py, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    // on the big map, each club's name at the middle of its MPs
    if (big) {
      const groups = new Map();
      for (const p of m.pts) {
        const key = SAME[p.club] || p.club;
        if (key === "niez.") continue;
        (groups.get(key) || groups.set(key, []).get(key)).push(p);
      }
      ctx.font = "600 13px Noto Sans, system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      for (const [club, ps] of groups) {
        if (ps.length < 3 || (focus && club !== focus)) continue;
        const x = ps.reduce((t, p) => t + p.px, 0) / ps.length, y = ps.reduce((t, p) => t + p.py, 0) / ps.length;
        ctx.lineWidth = 4;
        ctx.strokeStyle = getComputedStyle(document.body).backgroundColor;
        ctx.strokeText(club, x, y);
        ctx.fillStyle = ink();
        ctx.fillText(club, x, y);
      }
    }
  };

  // hover: the nearest MP within reach; click: their page
  const tip = Object.assign(document.createElement("div"), { className: "stats-tip", hidden: true });
  const near = (m, e) => {
    const box = m.canvas.getBoundingClientRect(), x = e.clientX - box.left, y = e.clientY - box.top;
    let best = null, dist = 12 * 12;
    for (const p of m.pts || []) {
      const d = (p.px - x) ** 2 + (p.py - y) ** 2;
      if (d < dist) [best, dist] = [p, d];
    }
    return best && { p: best, x, y };
  };
  const attach = (m) => {
    m.canvas.parentElement.style.position = "relative";
    m.canvas.addEventListener("pointermove", (e) => {
      const hit = near(m, e);
      if (!hit) { tip.hidden = true; m.canvas.style.cursor = ""; return; }
      m.canvas.parentElement.append(tip);
      tip.textContent = `${hit.p.name} · ${hit.p.club}`;
      tip.hidden = false;
      tip.style.left = `${Math.min(hit.x + 12, m.canvas.clientWidth - tip.offsetWidth)}px`;
      tip.style.top = `${hit.y + 12}px`;
      m.canvas.style.cursor = "pointer";
    });
    m.canvas.addEventListener("pointerleave", () => { tip.hidden = true; });
    m.canvas.addEventListener("click", (e) => {
      const hit = near(m, e);
      if (hit) location.href = `${ROOT}posel/${hit.p.id}.html`;
    });
  };

  const legend = (data) => {
    const box = document.getElementById("stats-legend");
    const count = new Map();
    for (const [, , , club] of data.mps) {
      const key = SAME[club] || club;
      count.set(key, (count.get(key) || 0) + 1);
    }
    const button = (key, label) => {
      const b = document.createElement("button");
      b.type = "button";
      b.setAttribute("aria-pressed", String(focus === key));
      if (key) b.append(Object.assign(document.createElement("i"), { style: `background:${colour(key)}` }));
      b.append(label);
      b.addEventListener("click", () => {
        focus = focus === key ? null : key;
        for (const x of box.children) x.setAttribute("aria-pressed", "false");
        if (focus) b.setAttribute("aria-pressed", "true");
        maps.forEach(draw);
      });
      return b;
    };
    box.replaceChildren(button(null, L.all), ...[...count].sort((a, b) => b[1] - a[1])
      .map(([club, n]) => button(club, `${club === "niez." ? L.other : club} ${n}`)));
  };

  // the margins: one bar per margin, the line at zero between passed and failed
  const histogram = () => {
    const box = document.getElementById("stats-hist");
    if (!box) return;
    // the close range one vote at a time; lopsided votes only counted, below the chart
    const all = JSON.parse(box.dataset.margins), lo = -40, hi = 40;
    const rows = all.filter(([m]) => m >= lo && m <= hi);
    const above = all.filter(([m]) => m > hi).reduce((t, [, n]) => t + n, 0), below = all.filter(([m]) => m < lo).reduce((t, [, n]) => t + n, 0);
    const W = 720, H = 200, padL = 34, padB = 22;
    const max = Math.max(...rows.map(([, n]) => n));
    const x = (m) => padL + (m - lo) / (hi - lo + 1) * (W - padL - 6), bw = (W - padL - 6) / (hi - lo + 1);
    const y = (n) => (H - padB) - n / max * (H - padB - 8);
    const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("role", "img");
    const add = (tag, attrs, text) => {
      const e = document.createElementNS(ns, tag);
      for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
      if (text !== undefined) e.textContent = text;
      svg.append(e);
      return e;
    };
    for (const t of [0, 0.5, 1].map((f) => Math.round(max * f))) {
      add("line", { x1: padL, x2: W - 6, y1: y(t), y2: y(t) });
      add("text", { x: padL - 4, y: y(t) + 4, "text-anchor": "end" }, t);
    }
    for (const [m, n] of rows) {
      const hit = add("rect", { class: "hit", x: x(m), y: 8, width: bw, height: H - padB - 8 });
      add("rect", { class: "hbar", x: x(m) + 0.5, y: y(n), width: Math.max(1, bw - 1), height: (H - padB) - y(n), rx: 1.5 });
      const label = `${L.margin} ${m > 0 ? "+" : ""}${m}: ${n} ${L.count}`;
      hit.append(Object.assign(document.createElementNS(ns, "title"), { textContent: label }));
    }
    add("line", { class: "zero", x1: x(0), x2: x(0), y1: 4, y2: H - padB });
    for (const t of [-40, -20, 0, 20, 40]) add("text", { x: x(t) + bw / 2, y: H - 6, "text-anchor": "middle" }, t > 0 ? `+${t}` : t);
    box.append(svg, Object.assign(document.createElement("p"), { className: "note",
      textContent: L.outside.replace("{a}", above).replace("{b}", below) }));
  };

  fetch(page.dataset.src).then((r) => r.json()).then((data) => {
    maps.push({ canvas: document.getElementById("stats-term"), data: data.term, big: true });
    for (const c of document.querySelectorAll("#stats-panels canvas")) maps.push({ canvas: c, data: data.panels[Number(c.dataset.panel)], big: false });
    legend(data.term);
    maps.forEach((m) => { draw(m); attach(m); });
    let t;
    window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(() => maps.forEach(draw), 150); });
    // redraw when the theme changes (colours come from CSS)
    new MutationObserver(() => maps.forEach(draw)).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  });
  histogram();
})();
