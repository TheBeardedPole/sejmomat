// The MP tier list (tierlista.html): the reader's own categories, MPs dragged (or tapped) into them,
// filters on the pool, kept in this browser (localStorage "sejmomat-tierlista"), shared as a link
// (#t=<base64url JSON>, nothing sent to the server) or drawn as a PNG in the style of the site's
// images (static/card.js). Data: dane/tierlista.json from the build (sitting MPs: id, name, surname,
// club, district, voivodeship, birth date, terms served since 1997).
(() => {
  const root = document.getElementById("tierlist");
  if (!root) return;
  const L = JSON.parse(root.dataset.labels);
  const $ = (sel, el = root) => el.querySelector(sel);
  const h = (tag, props = {}, children = []) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...[].concat(children).filter((c) => c !== null && c !== undefined && c !== false));
    return node;
  };
  const fmt = (s, vars) => Object.entries(vars).reduce((t, [k, v]) => t.replace(`{${k}}`, v), s);
  const fold = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");
  const KEY = "sejmomat-tierlista";
  const DEFAULT_TIERS = [["S", "#ff7f7f"], ["A", "#ffbf7f"], ["B", "#ffdf7f"], ["C", "#ffff7f"], ["D", "#bfff7f"], ["F", "#7fbfff"]];
  const NEW_COLOURS = ["#7fffff", "#bf7fff", "#ff7fbf", "#d4d4d4", "#9fdf9f"];
  let uid = 0;
  const tier = (label, colour, ids = []) => ({ id: `t${++uid}`, label, colour, ids });
  // the image's look: the site's current theme until the reader picks one
  const siteTheme = () => document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const blank = () => ({ title: L.title, sign: "", theme: null, tiers: DEFAULT_TIERS.map(([l, c]) => tier(l, c)), filters: { clubs: [], voivs: [], districts: [], ages: [], terms: [], q: "" } });

  // dark or white text on a category's colour, whichever reads better
  const onColour = (hex) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.25 ? "#1d1d1f" : "#ffffff";
  };
  let data, byId, state, selected = null, fromLink = false;
  const photo = (id) => `https://api.sejm.gov.pl/sejm/term${data.term}/MP/${id}/photo-mini`;
  const clubName = (c) => (data.clubs.find((x) => x[0] === c) || [c, c])[1];
  const clubVar = (c) => `var(--c-${{ "Polska2050-TD": "Polska2050", "niez.": "other" }[c] || c}, var(--c-other))`;
  const today = new Date();
  const age = (b) => {
    if (!b) return null;
    const [y, m, d] = b.split("-").map(Number);
    return today.getFullYear() - y - ((today.getMonth() + 1 < m || (today.getMonth() + 1 === m && today.getDate() < d)) ? 1 : 0);
  };
  const TERMS_CAP = 7;   // "7 and more" in one chip

  // ---- saving, sharing ----
  const save = () => {
    if (fromLink) return;   // a list opened from a link is not saved over the reader's own until they change it
    try {
      localStorage.setItem(KEY, JSON.stringify({ title: state.title, sign: state.sign, theme: state.theme, tiers: state.tiers.map((t) => [t.label, t.colour, t.ids]), filters: state.filters }));
    } catch { /* storage unavailable: the list lasts for this visit */ }
  };
  const edited = () => { fromLink = false; save(); };
  const restore = (raw, filters) => {
    const known = (ids) => (ids || []).filter((id, k, a) => byId.has(id) && a.indexOf(id) === k);
    const tiers = (raw.tiers || []).filter((t) => Array.isArray(t)).map(([l, c, ids]) => tier(String(l || "").slice(0, 24), /^#[0-9a-f]{6}$/i.test(c) ? c : "#d4d4d4", known(ids)));
    const s = blank();
    if (tiers.length) s.tiers = tiers;
    if (typeof raw.title === "string") s.title = raw.title.slice(0, 60);
    if (typeof raw.sign === "string") s.sign = raw.sign.slice(0, 40);
    if (raw.theme === "light" || raw.theme === "dark") s.theme = raw.theme;
    if (filters && raw.filters) s.filters = { ...s.filters, ...raw.filters };
    return s;
  };
  const b64 = {
    enc: (obj) => btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(obj)))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""),
    dec: (s) => JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0)))),
  };
  const shareUrl = () => `${location.origin}${location.pathname}#t=${b64.enc({ title: state.title, sign: state.sign || undefined, theme: state.theme || undefined, tiers: state.tiers.map((t) => [t.label, t.colour, t.ids]) })}`;
  const status = (text) => { $(".tl-status").textContent = text || ""; };

  // ---- filters ----
  const placed = () => new Set(state.tiers.flatMap((t) => t.ids));
  const matches = (m) => {
    const f = state.filters;
    if (f.clubs.length && !f.clubs.includes(m.c)) return false;
    if (f.voivs.length && !f.voivs.includes(m.w)) return false;
    if (f.districts.length && !f.districts.includes(m.d)) return false;
    if (f.terms.length && !f.terms.includes(Math.min(m.t, TERMS_CAP))) return false;
    if (f.ages.length) {
      const a = age(m.b);
      if (a === null || !f.ages.some(([lo, hi]) => (lo === null || lo === "" || a >= +lo) && (hi === null || hi === "" || a <= +hi))) return false;
    }
    if (f.q && !fold(m.n).includes(fold(f.q))) return false;
    return true;
  };
  const chip = (label, on, onchange, colour, count) => {
    const box = h("input", { type: "checkbox", checked: on, onchange: (e) => onchange(e.target.checked) });
    return h("label", { className: `tl-chip${on ? " on" : ""}` }, [box,
      colour ? h("span", { className: "tl-dot", style: `background:${colour}` }) : null,
      h("span", { textContent: label }), count !== undefined ? h("span", { className: "muted", textContent: ` ${count}` }) : null]);
  };
  const toggle = (list, value, on) => { const i = list.indexOf(value); if (on && i < 0) list.push(value); if (!on && i >= 0) list.splice(i, 1); };
  const group = (title, body, hint) => h("fieldset", { className: "tl-group" }, [h("legend", { textContent: title }), hint ? h("p", { className: "muted tl-hint", textContent: hint }) : null, body]);

  const drawFilters = () => {
    const f = state.filters, all = data.mps;
    const count = (pred) => all.filter(pred).length;
    const refresh = () => { edited(); drawFilters(); drawPool(); };
    const clubs = h("div", { className: "tl-chips" }, data.clubs.map(([c, name]) =>
      chip(name, f.clubs.includes(c), (on) => { toggle(f.clubs, c, on); refresh(); }, clubVar(c), count((m) => m.c === c))));
    const voivList = [...new Set(all.map((m) => m.w))].filter(Boolean).sort((a, b) => a.localeCompare(b, "pl"));
    const voivs = h("div", { className: "tl-chips" }, voivList.map((w) =>
      chip(w, f.voivs.includes(w), (on) => {
        toggle(f.voivs, w, on);
        // districts outside the chosen voivodeships no longer apply
        if (f.voivs.length) f.districts = f.districts.filter((d) => all.some((m) => m.d === d && f.voivs.includes(m.w)));
        refresh();
      }, null, count((m) => m.w === w))));
    const dists = [...new Map(all.filter((m) => m.d && (!f.voivs.length || f.voivs.includes(m.w))).map((m) => [m.d, m.dn])).entries()].sort((a, b) => a[0] - b[0]);
    const districts = h("div", { className: "tl-chips tl-chips-scroll" }, dists.map(([d, dn]) =>
      chip(`${d} ${dn}`, f.districts.includes(d), (on) => { toggle(f.districts, d, on); refresh(); }, null, count((m) => m.d === d))));
    const num = (value, label, set) => h("label", { className: "tl-age-field" }, [h("span", { textContent: label }),
      h("input", { type: "number", min: 18, max: 110, inputMode: "numeric", value: value ?? "", onchange: (e) => { set(e.target.value === "" ? null : +e.target.value); edited(); drawPool(); } })]);
    const ages = h("div", {}, [
      ...f.ages.map((br, k) => h("div", { className: "tl-age" }, [
        num(br[0], L.ageFrom, (v) => { br[0] = v; }), num(br[1], L.ageTo, (v) => { br[1] = v; }), h("span", { className: "muted", textContent: L.years }),
        h("button", { type: "button", className: "tl-x", textContent: "×", title: L.removeAge, ariaLabel: L.removeAge, onclick: () => { f.ages.splice(k, 1); refresh(); } })])),
      h("button", { type: "button", className: "btn2 tl-small", textContent: `+ ${L.addAge}`, onclick: () => { f.ages.push([null, null]); refresh(); } }),
    ]);
    const maxT = Math.min(TERMS_CAP, Math.max(...all.map((m) => m.t)));
    const terms = h("div", { className: "tl-chips" }, Array.from({ length: maxT }, (_, k) => k + 1).map((n) =>
      chip(n === 1 ? `1 (${L.termsFirst})` : n === TERMS_CAP ? fmt(L.termsMore, { n }) : String(n), f.terms.includes(n),
        (on) => { toggle(f.terms, n, on); refresh(); }, null, count((m) => Math.min(m.t, TERMS_CAP) === n))));
    const active = ["clubs", "voivs", "districts", "ages", "terms"].filter((k) => f[k].length).length;
    $(".tl-filter-count").textContent = active ? `(${active})` : "";
    $(".tl-filter-body").replaceChildren(
      group(L.club, clubs), group(L.voiv, voivs), group(L.district, districts, f.voivs.length ? L.districtHint : null),
      group(L.age, ages), group(L.terms, terms),
      active ? h("p", {}, [h("button", { type: "button", className: "btn2 tl-small", textContent: L.clearFilters,
        onclick: () => { Object.assign(f, { clubs: [], voivs: [], districts: [], ages: [], terms: [] }); refresh(); } })]) : null);
  };

  // ---- board and pool ----
  const tile = (m) => {
    const t = h("button", { type: "button", className: `tl-mp${selected === m.i ? " sel" : ""}`, title: `${m.n} (${clubName(m.c)})` }, [
      // with CORS, so the PNG can draw the photo already on screen instead of fetching it again
      h("img", { crossOrigin: "anonymous", src: photo(m.i), alt: "", loading: "lazy", width: 56, height: 64, onerror: (e) => { e.target.replaceWith(h("span", { className: "tl-noimg", textContent: m.n.split(" ").map((w) => w[0]).join("").slice(0, 2) })); } }),
      h("span", { className: "tl-name", textContent: m.s }),
      // placed MPs: a corner × sends them back to the pool (a span, as a button cannot hold a button)
      h("span", { className: "tl-out", textContent: "×", title: L.out, ariaHidden: "true" }),
    ]);
    t.dataset.id = m.i;
    t.style.setProperty("--club", clubVar(m.c));
    t.setAttribute("aria-pressed", String(selected === m.i));
    return t;
  };
  const drawBoard = () => {
    $(".tl-board").replaceChildren(...state.tiers.map((t, k) => {
      const zone = h("div", { className: "tl-zone", tabIndex: 0 }, t.ids.map((id) => tile(byId.get(id))));
      zone.dataset.tier = t.id;
      zone.setAttribute("aria-label", fmt(L.moveTo, { tier: t.label || "…" }));
      const label = h("input", { type: "text", className: "tl-label", value: t.label, maxLength: 24, ariaLabel: L.rename,
        oninput: (e) => { t.label = e.target.value; zone.setAttribute("aria-label", fmt(L.moveTo, { tier: t.label || "…" })); edited(); } });
      const colour = h("input", { type: "color", className: "tl-colour", value: t.colour, title: L.colour, ariaLabel: L.colour,
        oninput: (e) => { t.colour = e.target.value; row.style.setProperty("--tier", t.colour); label.style.color = onColour(t.colour); edited(); } });
      const ctl = (text, title, fn, disabled) => h("button", { type: "button", className: "tl-ctl", textContent: text, title, ariaLabel: title, disabled, onclick: fn });
      const move = (dir) => { const [x] = state.tiers.splice(k, 1); state.tiers.splice(k + dir, 0, x); edited(); drawBoard(); };
      const row = h("div", { className: "tl-row" }, [
        h("div", { className: "tl-head" }, [label, colour]),
        zone,
        h("div", { className: "tl-ctls" }, [ctl("↑", L.up, () => move(-1), k === 0), ctl("↓", L.down, () => move(1), k === state.tiers.length - 1),
          Object.assign(ctl("×", L.remove, () => { state.tiers.splice(k, 1); edited(); drawBoard(); drawPool(); }, state.tiers.length === 1), { className: "tl-ctl tl-del" })]),
      ]);
      row.style.setProperty("--tier", t.colour);
      label.style.color = onColour(t.colour);
      return row;
    }));
  };
  const drawPool = () => {
    const on = placed();
    const fits = data.mps.filter(matches);
    const free = fits.filter((m) => !on.has(m.i));
    $(".tl-count").textContent = `${fmt(L.shown, { n: free.length, m: data.mps.length })} · ${on.size} ${L.placed}`;
    const pool = $(".tl-pool");
    pool.replaceChildren(...(free.length ? free.map(tile) : [h("p", { className: "muted tl-empty", textContent: fits.length ? L.allPlaced : L.empty })]));
  };
  const drawAll = () => {
    $(".tl-title").value = state.title; $(".tl-sign").value = state.sign || "";
    const th = state.theme || siteTheme();
    root.querySelectorAll('input[name="tl-theme"]').forEach((r) => { r.checked = r.value === th; }); drawBoard(); drawFilters(); drawPool(); };

  // ---- moving MPs ----
  const moveTo = (id, target, before = null) => {
    for (const t of state.tiers) { const i = t.ids.indexOf(id); if (i >= 0) t.ids.splice(i, 1); }
    if (target !== "pool") {
      const t = state.tiers.find((x) => x.id === target);
      if (!t) return;
      const at = before === null ? -1 : t.ids.indexOf(before);
      if (at >= 0) t.ids.splice(at, 0, id); else t.ids.push(id);
    }
    selected = null;
    status("");
    edited();
    drawBoard();
    drawPool();
  };
  const select = (id) => {
    selected = selected === id ? null : id;
    root.classList.toggle("tl-picking", selected !== null);
    root.querySelectorAll(".tl-mp").forEach((el) => { const on = +el.dataset.id === selected; el.classList.toggle("sel", on); el.setAttribute("aria-pressed", String(on)); });
    status(selected !== null ? fmt(L.selected, { name: byId.get(selected).n }) : "");
  };
  // a tap on an MP selects them; a tap on a category (or the pool) with an MP selected moves them there
  let suppressClick = false;
  root.addEventListener("click", (e) => {
    if (suppressClick) { suppressClick = false; return; }
    const out = e.target.closest(".tl-out");
    if (out) { moveTo(+out.closest(".tl-mp").dataset.id, "pool"); root.classList.remove("tl-picking"); return; }
    const mp = e.target.closest(".tl-mp");
    const zone = e.target.closest(".tl-zone, .tl-pool");
    if (mp && !(selected !== null && selected !== +mp.dataset.id && zone)) { select(+mp.dataset.id); return; }
    if (selected !== null && zone) {
      const before = mp && zone.classList.contains("tl-zone") ? +mp.dataset.id : null;
      moveTo(selected, zone.dataset.tier, before);
      root.classList.remove("tl-picking");
    }
  });
  // keys on the whole page: a button picked with the mouse may not keep focus (Safari, Firefox on macOS)
  document.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches(".tl-zone") && selected !== null) {
      e.preventDefault();
      moveTo(selected, e.target.dataset.tier);
      root.classList.remove("tl-picking");
    }
    if (e.key === "Escape" && selected !== null) { select(selected); root.classList.remove("tl-picking"); }
    // Delete or Backspace on a placed MP (picked, or with focus) sends them back to the pool
    if ((e.key === "Delete" || e.key === "Backspace") && !e.target.matches("input, textarea")) {
      const id = selected ?? (e.target.matches(".tl-zone .tl-mp") ? +e.target.dataset.id : null);
      if (id !== null && placed().has(id)) { e.preventDefault(); moveTo(id, "pool"); root.classList.remove("tl-picking"); }
    }
  });

  // Dragging: the mouse at once, a finger after holding still for a moment (so the page still scrolls).
  let drag = null;
  const zoneAt = (x, y) => document.elementFromPoint(x, y)?.closest(".tl-zone, .tl-pool");
  const beforeAt = (zone, x, y) => {
    if (!zone || !zone.classList.contains("tl-zone")) return null;
    for (const el of zone.querySelectorAll(".tl-mp")) {
      if (+el.dataset.id === drag.id) continue;
      const r = el.getBoundingClientRect();
      if (y < r.bottom && (y < r.top || x < r.left + r.width / 2)) return +el.dataset.id;
    }
    return null;
  };
  const dragStart = (el, x, y) => {
    const r = el.getBoundingClientRect();
    const ghost = el.cloneNode(true);
    ghost.classList.add("tl-ghost");
    ghost.querySelector(".tl-out")?.remove();
    Object.assign(ghost.style, { width: `${r.width}px`, height: `${r.height}px` });
    root.append(ghost);   // inside the list, for its club colours
    drag = { id: +el.dataset.id, el, ghost, dx: x - r.left, dy: y - r.top, zone: null };
    el.classList.add("tl-dragging");
    root.classList.add("tl-picking");
    dragMove(x, y);
  };
  const dragMove = (x, y) => {
    if (!drag) return;
    drag.ghost.style.transform = `translate(${x - drag.dx}px, ${y - drag.dy}px)`;
    const zone = zoneAt(x, y);
    if (zone !== drag.zone) { drag.zone?.classList.remove("tl-over"); zone?.classList.add("tl-over"); drag.zone = zone; }
    // near an edge the pool panel (when over it) or else the page scrolls along
    const panel = $(".tl-pool-wrap"), pr = panel.getBoundingClientRect();
    const overPanel = x >= pr.left && x <= pr.right && y >= pr.top && y <= pr.bottom && panel.scrollHeight > panel.clientHeight;
    if (overPanel && y < pr.top + 50) panel.scrollTop -= 12;
    else if (overPanel && y > pr.bottom - 50) panel.scrollTop += 12;
    else if (y < 60) scrollBy(0, -14); else if (y > innerHeight - 60) scrollBy(0, 14);
  };
  const dragEnd = (x, y) => {
    if (!drag) return;
    const zone = zoneAt(x, y);
    const d = drag;
    d.ghost.remove();
    d.el.classList.remove("tl-dragging");
    d.zone?.classList.remove("tl-over");
    root.classList.remove("tl-picking");
    if (zone) moveTo(d.id, zone.dataset.tier, beforeAt(zone, x, y));
    drag = null;
    suppressClick = true;
    setTimeout(() => { suppressClick = false; }, 50);
  };
  root.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "touch" || e.button !== 0) return;
    const el = e.target.closest(".tl-mp");
    if (!el || e.target.closest(".tl-out")) return;
    const sx = e.clientX, sy = e.clientY;
    const move = (ev) => {
      if (!drag && Math.hypot(ev.clientX - sx, ev.clientY - sy) > 6) dragStart(el, ev.clientX, ev.clientY);
      dragMove(ev.clientX, ev.clientY);
    };
    const up = (ev) => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); dragEnd(ev.clientX, ev.clientY); };
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
    e.preventDefault();   // no text selection or native image drag
  });
  root.addEventListener("touchstart", (e) => {
    const el = e.target.closest(".tl-mp");
    if (!el || e.touches.length > 1 || e.target.closest(".tl-out")) return;
    const t0 = e.touches[0], sx = t0.clientX, sy = t0.clientY;
    let last = t0;
    const hold = setTimeout(() => { navigator.vibrate?.(15); dragStart(el, last.clientX, last.clientY); }, 280);
    const move = (ev) => {
      last = ev.touches[0];
      if (!drag) { if (Math.hypot(last.clientX - sx, last.clientY - sy) > 8) cancel(); return; }
      ev.preventDefault();   // dragging, not scrolling
      dragMove(last.clientX, last.clientY);
    };
    const end = () => { cancel(); dragEnd(last.clientX, last.clientY); };
    const cancel = () => { clearTimeout(hold); removeEventListener("touchmove", move); removeEventListener("touchend", end); removeEventListener("touchcancel", end); };
    addEventListener("touchmove", move, { passive: false });
    addEventListener("touchend", end);
    addEventListener("touchcancel", end);
  }, { passive: true });
  root.addEventListener("contextmenu", (e) => { if (e.target.closest(".tl-mp")) e.preventDefault(); });   // long press on a phone

  // ---- the image ----
  // the image's two looks: the site's light and dark themes (static/style.css), club colours as in .sala/.tl
  const PALETTES = {
    light: { bg: "#fbfaf8", surface: "#ffffff", line: "#e4e2dd", text: "#1d1d1f", muted: "#6b6b70", foot: "#1d5fc4", footMuted: "#d3e2f8",
      clubs: { KO: "#eb6834", PiS: "#2a78d6", RozwojPlus: "#1baf7a", Polska2050: "#eda100", "PSL-TD": "#008300", Lewica: "#c2185b", Konfederacja: "#4a3aa7",
        Centrum: "#9e7bd8", Razem: "#b03a8a", Demokracja: "#4f8fb0", Republikanie: "#1f4fa0", Konfederacja_KP: "#7f6fd1", Kukiz15: "#6e6e6e", other: "#a3a3a3" } },
    dark: { bg: "#141416", surface: "#1c1c1f", line: "#2e2e33", text: "#ececee", muted: "#9a9aa2", foot: "#1d5fc4", footMuted: "#d3e2f8",
      clubs: { KO: "#f07a45", PiS: "#4a90e8", RozwojPlus: "#22c08a", Polska2050: "#f2b01c", "PSL-TD": "#2aa52a", Lewica: "#e0457f", Konfederacja: "#8f84ee",
        Centrum: "#b39af0", Razem: "#d063aa", Demokracja: "#79acc4", Republikanie: "#5a86d8", Konfederacja_KP: "#a99cf0", Kukiz15: "#9a9a9a", other: "#7d7d7d" } },
  };
  const W = 1200, PAD = 48, FOOT = 132, LABEL_W = 150, TILE_W = 88, TILE_H = 118, GAPX = 8;
  const FAMILY = '"Noto Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  const font = (weight, size) => `${weight === "bold" ? 700 : 400} ${size}px ${FAMILY}`;
  const loadImg = (src, cors) => new Promise((resolve) => {
    const img = new Image();
    if (cors) img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    setTimeout(() => resolve(null), 20000);   // the pool's own photos may be ahead in the queue
    img.src = src;
  });
  // a placed MP's photo: the one on screen when it has loaded, else fetched
  const photoFor = (id) => {
    const shown = root.querySelector(`.tl-zone .tl-mp[data-id="${id}"] img`);
    return shown && shown.complete && shown.naturalWidth ? Promise.resolve(shown) : loadImg(photo(id), true);
  };
  const fitText = (d, text, max) => {
    if (d.measureText(text).width <= max) return text;
    while (text.length > 1 && d.measureText(text + "…").width > max) text = text.slice(0, -1);
    return text + "…";
  };
  const wrapLines = (d, text, max, lines) => {
    const out = [];
    let line = "";
    for (const word of text.split(/\s+/).filter(Boolean)) {
      if (line && d.measureText(`${line} ${word}`).width > max) { out.push(line); line = word; } else line = line ? `${line} ${word}` : word;
    }
    if (line) out.push(line);
    return out.slice(0, lines).map((l, k, a) => (k === a.length - 1 && out.length > lines ? fitText(d, l + "…", max) : fitText(d, l, max)));
  };
  const drawPng = async () => {
    status(L.drawing);
    const perRow = Math.floor((W - 2 * PAD - LABEL_W - 12 + GAPX) / (TILE_W + GAPX));
    const rows = state.tiers.map((t) => Math.max(1, Math.ceil(t.ids.length / perRow)));
    const ids = state.tiers.flatMap((t) => t.ids);
    const [photos, logo] = await Promise.all([
      Promise.all(ids.map(photoFor)).then((list) => new Map(ids.map((id, k) => [id, list[k]]))),
      loadImg(`${root.dataset.root}${document.documentElement.lang === "en" ? "../" : ""}static/logo-white.png`, false),
    ]);
    const P = PALETTES[state.theme || siteTheme()] || PALETTES.light;
    const sign = (state.sign || "").trim();
    const top = sign ? 186 : 150, rowGap = 8;
    const bodyH = rows.reduce((s, n) => s + n * TILE_H + (n - 1) * 6 + 16 + rowGap, 0);
    const H = top + bodyH + 40 + FOOT;
    const c = Object.assign(document.createElement("canvas"), { width: W, height: H });
    const d = c.getContext("2d");
    d.fillStyle = P.bg; d.fillRect(0, 0, W, H);
    d.textBaseline = "alphabetic";
    d.fillStyle = P.muted; d.font = font("bold", 22);
    d.fillText(document.documentElement.lang === "en" ? "SEJM TIER LIST · SEJMOMAT" : "TIER LISTA POSŁÓW · SEJMOMAT", PAD, 62);
    d.fillStyle = P.text; d.font = font("bold", 50);
    d.fillText(fitText(d, state.title || L.title, W - 2 * PAD), PAD, 120);
    if (sign) { d.fillStyle = P.muted; d.font = font("regular", 28); d.fillText(fitText(d, fmt(L.signBy, { name: sign }), W - 2 * PAD), PAD, 162); }
    let y = top;
    state.tiers.forEach((t, k) => {
      const hgt = rows[k] * TILE_H + (rows[k] - 1) * 6 + 16;
      d.fillStyle = P.surface; d.strokeStyle = P.line; d.lineWidth = 2;
      d.beginPath(); d.roundRect(PAD, y, W - 2 * PAD, hgt, 14); d.fill(); d.stroke();
      d.fillStyle = t.colour;
      d.beginPath(); d.roundRect(PAD, y, LABEL_W, hgt, [14, 0, 0, 14]); d.fill();
      d.fillStyle = onColour(t.colour);
      const big = t.label.length <= 3;
      d.font = font("bold", big ? 46 : 24);
      const lines = wrapLines(d, t.label, LABEL_W - 20, big ? 1 : 4);
      const lh = big ? 50 : 30;
      lines.forEach((line, i) => {
        d.textAlign = "center";
        d.fillText(line, PAD + LABEL_W / 2, y + hgt / 2 + (i - (lines.length - 1) / 2) * lh + (big ? 16 : 9));
      });
      d.textAlign = "left";
      t.ids.forEach((id, i) => {
        const m = byId.get(id), x = PAD + LABEL_W + 12 + (i % perRow) * (TILE_W + GAPX), ty = y + 8 + Math.floor(i / perRow) * (TILE_H + 6);
        const img = photos.get(id), ph = 92;
        d.save();
        d.beginPath(); d.roundRect(x, ty, TILE_W, ph, 8); d.clip();
        if (img) {
          const s = Math.max(TILE_W / img.width, ph / img.height);
          d.drawImage(img, x + (TILE_W - img.width * s) / 2, ty, img.width * s, img.height * s);
        } else { d.fillStyle = P.line; d.fillRect(x, ty, TILE_W, ph); }
        d.restore();
        d.fillStyle = P.clubs[{ "Polska2050-TD": "Polska2050", "niez.": "other" }[m.c] || m.c] || P.clubs.other;
        d.fillRect(x, ty + ph - 5, TILE_W, 5);
        d.fillStyle = P.text; d.font = font("regular", 15);
        d.textAlign = "center";
        d.fillText(fitText(d, m.s, TILE_W), x + TILE_W / 2, ty + ph + 19);
        d.textAlign = "left";
      });
      y += hgt + rowGap;
    });
    // the footer band, as on the site's other images
    d.fillStyle = P.foot; d.fillRect(0, H - FOOT, W, FOOT);
    const mid = H - FOOT / 2 + 16;
    d.fillStyle = "#ffffff"; d.font = font("regular", 36);
    const lead = `${L.more} `;
    d.fillText(lead, PAD, mid);
    const lw0 = d.measureText(lead).width;
    d.font = font("bold", 50); d.fillText("sejmomat.pl", PAD + lw0, mid);
    d.textAlign = "right"; d.fillStyle = P.footMuted; d.font = font("regular", 22);
    if (logo) {
      const lh = 40, lw = Math.round(logo.width * lh / logo.height);
      d.drawImage(logo, W - PAD - lw, H - FOOT + 30, lw, lh);
      d.fillText(L.data, W - PAD, H - 30);
    } else d.fillText(L.data, W - PAD, mid);
    d.textAlign = "left";
    c.toBlob((blob) => {
      if (!blob) { status(L.error); return; }
      const a = h("a", { href: URL.createObjectURL(blob), download: "tier-lista-poslow.png" });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      status("");
      window.smTrack?.("tierlist_export", { placed: ids.length, tiers: state.tiers.length, theme: state.theme || siteTheme() });
    }, "image/png");
  };

  // ---- the bar ----
  $(".tl-title").addEventListener("input", (e) => { state.title = e.target.value; edited(); });
  $(".tl-title").setAttribute("aria-label", L.titleLabel);
  $(".tl-sign").addEventListener("input", (e) => { state.sign = e.target.value; edited(); });
  $(".tl-sign").setAttribute("aria-label", L.sign);
  root.querySelectorAll('input[name="tl-theme"]').forEach((r) => r.addEventListener("change", () => { state.theme = r.value; edited(); }));
  $(".tl-add").addEventListener("click", () => {
    state.tiers.push(tier(L.newTier, NEW_COLOURS[state.tiers.length % NEW_COLOURS.length]));
    edited(); drawBoard();
    root.querySelector(".tl-row:last-child .tl-label")?.select();
  });
  $(".tl-reset").addEventListener("click", () => {
    if (!confirm(L.resetConfirm)) return;
    const filters = state.filters;
    state = blank(); state.filters = filters; selected = null;
    edited(); drawAll();
  });
  $(".tl-png").addEventListener("click", () => drawPng().catch(() => status(L.error)));
  $(".tl-share").addEventListener("click", async () => {
    const url = shareUrl();
    try { await navigator.clipboard.writeText(url); status(L.copied); } catch { history.replaceState(null, "", url); status(L.copyFail); }
    window.smTrack?.("tierlist_share", { placed: placed().size });
  });
  const toggleBtn = $(".tl-filter-toggle");
  toggleBtn.addEventListener("click", () => {
    const open = toggleBtn.getAttribute("aria-expanded") !== "true";
    toggleBtn.setAttribute("aria-expanded", String(open));
    $(".tl-filters").hidden = !open;
  });
  let searchTimer = null;
  $(".tl-search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.filters.q = e.target.value.trim(); drawPool(); }, 150);
  });

  // ---- start ----
  fetch(root.dataset.src).then((r) => r.json()).then((d) => {
    data = d;
    byId = new Map(data.mps.map((m) => [m.i, m]));
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(KEY) || "null"); } catch { /* no storage */ }
    state = saved ? restore({ ...saved, tiers: saved.tiers }, true) : blank();
    state.filters.q = "";
    if (location.hash.startsWith("#t=")) {
      try {
        const shared = restore(b64.dec(location.hash.slice(3)), false);
        state = { ...shared, filters: state.filters };
        fromLink = true;
        status(L.loaded);
      } catch { /* a broken link: the reader's own list */ }
      history.replaceState(null, "", location.pathname + location.search);
    }
    drawAll();
  }).catch(() => status(L.error));
})();
