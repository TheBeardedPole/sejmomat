// Google Analytics with events: which features are used and where readers get stuck.
//
// Loaded only after consent: by static/app.js on the site's pages (it adds this script once the
// visitor clicks "Zgadzam się"), and by Sejmdle's pages, which have no consent bar of their own and
// so read the choice made on the site (the consent record keeps the GA id for them). Every event is
// checked against the consent again, so withdrawing it stops them at once.
//
// What is sent (GA4 event names; parameters to register as custom dimensions/metrics are in
// CLAUDE.md, "Analytics"). No free text a reader typed is sent, apart from search words, cut short
// and dropped when they look like an email address or a long number.
//   page type      content_group on every event (mp, club, vote, sejmdle, home, ...)
//   ui_click       buttons, tabs, fold-outs ("Jak liczymy?"), menus, selects: ui_label, ui_kind,
//                  ui_region, ui_action (open/close for fold-outs)
//   ui_change      selects, checkboxes, radios: ui_label, ui_value (an option's text)
//   share          share, copy and download buttons (site cards, Sejmdle results)
//   search         the search page: search_term, results_count; search_result_click with its position
//   content_copy   text copied from a page (readers wanting the data elsewhere)
//   scroll_depth   25/50/75/100 % of a long page
//   page_not_found the 404 page, with the address and where the reader came from
//   game_start, game_complete, game_left_unfinished   Sejmdle (from sejmdle.js through smTrack)
// Pain points:
//   js_error       uncaught errors and rejections from the site's own scripts
//   request_failed / request_slow   fetch() answers that fail or take over 5 s (Sejm API, data files)
//   resource_error images that do not load (MP photos)
//   rage_click     3+ clicks on one spot within a second
//   dead_click     a click on something that looks clickable (pictures, tiles, table cells) after
//                  which nothing on the page changes
//   page_perf      load time, LCP, CLS and the slowest interaction, once per page view
//
// Debugging: add ?sm_debug=1 to an address (kept for the tab) to log events to the console and see
// them in GA's DebugView.
(() => {
  if (window.smTrack) return;
  const stored = (() => {
    try { return JSON.parse(localStorage.getItem("sejmomat-consent") || "null") || {}; } catch { return {}; }
  })();
  const GA_ID = document.querySelector('meta[name="sejmomat-ga"]')?.content || stored.ga || "";
  if (!/^G-[A-Z0-9]{4,20}$/.test(GA_ID)) return;
  const consented = () => (window.sejmomatConsented ? window.sejmomatConsented() : stored.optional === true);
  if (!consented()) return;

  let debug = false;
  try {
    if (/[?&]sm_debug=1/.test(location.search)) sessionStorage.setItem("sm-debug", "1");
    debug = sessionStorage.getItem("sm-debug") === "1";
  } catch { /* no storage: no debugging */ }

  // Page type from the address: the first folder, or the page's name ("en/" skipped).
  const parts = location.pathname.replace(/^\/+/, "").replace(/^en\//, "").split("/");
  const FOLDERS = { posel: "mp", klub: "club", glosowanie: "vote", posiedzenie: "sitting", ustawa: "bill", druk: "print",
    poprawki: "amendment", komisja: "committee", temat: "topic", weto: "veto", ai: "ai_summaries", sejmdle: "sejmdle" };
  const GAME = document.querySelector('meta[name="sejmdle-game"]')?.content || "";
  const page = parts.length > 1 ? (FOLDERS[parts[0]] || parts[0]) : (parts[0].replace(/\.html$/, "") || "index");
  const PAGE_TYPE = document.querySelector(".not-found") ? "404"
    : page === "sejmdle" ? (GAME ? `sejmdle_${GAME}` : "sejmdle") : page === "index" ? "home" : page;

  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function gtag() { window.dataLayer.push(arguments); };
  window.gtag("js", new Date());
  // only to improve the site (privacy page): no Google Signals, nothing for ads
  window.gtag("set", { allow_google_signals: false, allow_ad_personalization_signals: false });
  window.gtag("config", GA_ID, { content_group: PAGE_TYPE, ...(debug ? { debug_mode: true } : {}) });
  const tag = document.createElement("script");
  tag.async = true;
  tag.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(GA_ID)}`;
  document.head.append(tag);

  // Per page view, each event name is capped so a loop or a broken page cannot flood the property.
  const sent = {};
  const CAP = { ui_click: 60, js_error: 5, request_failed: 5, request_slow: 3, resource_error: 5, rage_click: 3, dead_click: 5 };
  const track = (name, params = {}) => {
    if (!consented()) { window[`ga-disable-${GA_ID}`] = true; return; }
    sent[name] = (sent[name] || 0) + 1;
    if (sent[name] > (CAP[name] || 20)) return;
    if (debug) console.log("[sejmomat analytics]", name, JSON.stringify(params));
    window.gtag("event", name, params);
  };
  window.smTrack = track;

  // A short, groupable name for an element: its label, numbers replaced by "#", at most 60 characters.
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim().replace(/\d+/g, "#").slice(0, 60);
  const labelOf = (el) => {
    const count = el.querySelector?.(".tab-count");
    const text = count ? [...el.childNodes].filter((n) => n !== count).map((n) => n.textContent).join("") : el.textContent;
    const name = el.getAttribute("aria-label") || el.getAttribute("title") || (text.trim().length <= 80 ? text : "") || el.getAttribute("name") || el.id;
    // a large block (the page, a table) has no short label: its tag and first class
    return clean(name || `${el.tagName.toLowerCase()}${typeof el.className === "string" && el.className ? "." + el.className.split(" ")[0] : ""}`);
  };
  const regionOf = (el) => {
    if (!el || el === document.documentElement || el === document.body) return "page";
    if (el.closest("header, .site-header")) return "header";
    if (el.closest("footer")) return "footer";
    if (el.closest(".sm-choice, .sm-support, dialog")) return "popup";
    const box = el.closest(".tab-panel, section[id], [id]:not(button):not(a):not(input):not(select)");
    if (box && box.id) return clean(box.id);
    const cls = el.closest("[class]")?.className;
    return typeof cls === "string" ? clean(cls.split(" ")[0]) : "";
  };
  const kindOf = (el) => (el.closest(".tab-bar") ? "tab" : el.getAttribute("role") || el.tagName.toLowerCase());

  // Clicks: interactive elements, rage clicks and dead clicks.
  const INTERACTIVE = "button, summary, a[href], [role=button], [role=tab], select, label, input[type=checkbox], input[type=radio]";
  const SHARE = /udost[eę]pnij|kopiuj|pobierz|^(share|copy|download)\b/i;
  const LOOKS_CLICKABLE = "img, svg, canvas, th, td, .pill, .card, .tile, .stat, .mark, .seat, figure, h2, h3";
  let lastClick = { x: 0, y: 0, t: 0, n: 0 };
  document.addEventListener("click", (e) => {
    const now = e.timeStamp;
    const near = Math.abs(e.clientX - lastClick.x) < 30 && Math.abs(e.clientY - lastClick.y) < 30;
    lastClick = near && now - lastClick.t < 1000 ? { ...lastClick, t: now, n: lastClick.n + 1 } : { x: e.clientX, y: e.clientY, t: now, n: 1 };
    if (lastClick.n === 3) track("rage_click", { ui_label: labelOf(e.target), ui_region: regionOf(e.target) });

    const el = e.target.closest?.(INTERACTIVE);
    if (!el) {
      const look = e.target.closest?.(LOOKS_CLICKABLE);
      if (look && getComputedStyle(look).cursor !== "pointer") watchDeadClick(look);
      return;
    }
    if (el.matches("label") && el.control) return;   // its input reports the change
    if (el.matches("select, input")) return;          // reported on change
    const label = labelOf(el);
    // sharing: share, copy and download buttons and links, and the links in Sejmdle's result box
    if (el.matches("button, a[href], [role=button]") && (SHARE.test(label) || (GAME && el.closest(".share")))) {
      track("share", { method: label, content_type: GAME ? "sejmdle" : PAGE_TYPE, item_id: GAME || regionOf(el) });
      return;
    }
    if (el.matches("a[href]")) {
      if (PAGE_TYPE === "szukaj" && el.closest(".pagefind-ui__result")) {
        const results = [...document.querySelectorAll(".pagefind-ui__result")];
        track("search_result_click", { search_term: lastTerm, position: results.indexOf(el.closest(".pagefind-ui__result")) + 1 });
        return;
      }
      // Plain links between pages show up as page views; these say where a click came from.
      const href = el.getAttribute("href");
      if (!(href.startsWith("#") || PAGE_TYPE === "home" || el.closest("header, footer, nav, .tab-bar, .site-header"))) return;
    }
    const params = { ui_label: label, ui_kind: kindOf(el), ui_region: regionOf(el) };
    if (el.matches("summary")) params.ui_action = el.parentElement?.open ? "close" : "open";
    track("ui_click", params);
  }, true);

  // A dead click: nothing in the page changes within a second of it.
  let deadWatch = null;
  const watchDeadClick = (el) => {
    if (deadWatch) return;
    const before = location.href;
    let changed = false;
    // the header's script rewrites its menus' state on every click on the page, mostly to the same
    // values: neither counts as the page answering the click
    const obs = new MutationObserver((list) => {
      if (list.some((m) => !m.target.closest?.("header, .site-header")
        && !(m.type === "attributes" && m.oldValue === m.target.getAttribute(m.attributeName)))) changed = true;
    });
    obs.observe(document.body, { subtree: true, childList: true, attributes: true, attributeOldValue: true, characterData: true });
    deadWatch = setTimeout(() => {
      obs.disconnect();
      deadWatch = null;
      if (!changed && location.href === before) track("dead_click", { ui_label: labelOf(el), ui_kind: el.tagName.toLowerCase(), ui_region: regionOf(el) });
    }, 1000);
  };

  document.addEventListener("change", (e) => {
    const el = e.target;
    if (!el.matches?.("select, input[type=checkbox], input[type=radio]")) return;
    const label = clean(el.getAttribute("aria-label") || el.labels?.[0]?.textContent || el.name || el.id);
    const value = el.matches("select") ? clean(el.selectedOptions[0]?.textContent) : el.checked ? "on" : "off";
    track("ui_change", { ui_label: label, ui_value: value, ui_region: regionOf(el) });
  }, true);

  document.addEventListener("copy", () => {
    const n = String(getSelection() || "").length;
    if (n) track("content_copy", { ui_region: regionOf(getSelection().anchorNode?.parentElement || document.body), length: n < 50 ? "short" : n < 500 ? "medium" : "long" });
  });

  // Scroll depth on pages at least one and a half screens long.
  const marks = [25, 50, 75, 100];
  addEventListener("scroll", () => {
    const doc = document.documentElement;
    if (doc.scrollHeight < innerHeight * 1.5) return;
    const pct = (scrollY / (doc.scrollHeight - innerHeight)) * 100;   // of the distance there is to scroll
    while (marks.length && pct >= marks[0] - 1) track("scroll_depth", { percent: marks.shift() });
  }, { passive: true });

  // Search (szukaj.html, Pagefind's UI searches as one types): the words and the number of
  // results, once the reader has stopped typing for two seconds.
  let lastTerm = "";
  const safeTerm = (s) => {
    const t = s.trim().toLowerCase().slice(0, 60);
    return /@|\d{6,}/.test(t) ? "[usunięte]" : t;
  };
  const box = document.getElementById("search");
  if (box && PAGE_TYPE === "szukaj") {
    let timer = null, reported = "";
    new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const input = box.querySelector("input");
        const term = safeTerm(input?.value || "");
        if (!term || term === reported) return;
        reported = lastTerm = term;
        const msg = box.querySelector(".pagefind-ui__message")?.textContent || "";
        const n = box.querySelectorAll(".pagefind-ui__result").length ? parseInt(msg.replace(/\s/g, "").match(/\d+/)?.[0] || "0", 10) : 0;
        track("search", { search_term: term, results_count: n });
        if (!n) track("search_no_results", { search_term: term });
      }, 2000);
    }).observe(box, { subtree: true, childList: true, characterData: true });
  }

  if (PAGE_TYPE === "404") {
    let from = "";
    try { from = document.referrer ? new URL(document.referrer).host + new URL(document.referrer).pathname : ""; } catch { /* no referrer */ }
    track("page_not_found", { missing_path: location.pathname.slice(0, 100), from });
  }

  // Errors from the site's own scripts (extensions and other sites' scripts are left out),
  // and pictures that fail to load.
  const ours = (file) => !file || file.startsWith(location.origin);
  addEventListener("error", (e) => {
    const t = e.target;
    if (t && t !== window && t.tagName === "IMG") {
      try { track("resource_error", { request_host: new URL(t.currentSrc || t.src).host, page_type: PAGE_TYPE }); } catch { /* no address */ }
      return;
    }
    // no file: an opaque "Script error." from another origin, which says nothing
    if (!(e instanceof ErrorEvent) || !e.filename || !ours(e.filename)) return;
    track("js_error", { error_message: String(e.message).slice(0, 100), error_source: `${(e.filename || "").split("/").pop().split("?")[0]}:${e.lineno}` });
  }, true);
  addEventListener("unhandledrejection", (e) => {
    const r = e.reason;
    if (r?.name === "AbortError") return;
    const stack = String(r?.stack || "");
    if (stack && !stack.includes(location.origin)) return;
    track("js_error", { error_message: String(r?.message || r).slice(0, 100), error_source: "promise" });
  });

  // Requests: failures and slow answers. The path is grouped (numbers as "#").
  const fetch0 = window.fetch;
  if (fetch0) {
    window.fetch = function (input, init) {
      const started = performance.now();
      let url;
      try { url = new URL(typeof input === "string" ? input : input.url, location.href); } catch { return fetch0.apply(this, arguments); }
      const where = { request_host: url.host, request_path: url.pathname.replace(/\d+/g, "#").slice(0, 80) };
      return fetch0.apply(this, arguments).then((res) => {
        const ms = Math.round(performance.now() - started);
        if (!res.ok) track("request_failed", { ...where, status_code: res.status });
        else if (ms > 5000) track("request_slow", { ...where, duration_ms: ms });
        return res;
      }, (err) => {
        if (err?.name !== "AbortError" && !init?.signal?.aborted) track("request_failed", { ...where, status_code: 0 });
        throw err;
      });
    };
  }

  // Page speed, sent once when the page is hidden: load time, Largest Contentful Paint, layout
  // shift (summed; Google's tool uses session windows, close enough here) and the slowest
  // interaction (an approximation of INP).
  const perf = { lcp: 0, cls: 0, inp: 0 };
  const observe = (type, fn, opts = {}) => {
    try { new PerformanceObserver((list) => list.getEntries().forEach(fn)).observe({ type, buffered: true, ...opts }); } catch { /* not supported */ }
  };
  observe("largest-contentful-paint", (en) => { perf.lcp = Math.round(en.startTime); });
  observe("layout-shift", (en) => { if (!en.hadRecentInput) perf.cls += en.value; });
  observe("event", (en) => { if (en.interactionId) perf.inp = Math.max(perf.inp, Math.round(en.duration)); }, { durationThreshold: 40 });
  let perfSent = false;
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "hidden" || perfSent) return;
    perfSent = true;
    const nav = performance.getEntriesByType("navigation")[0];
    const rate = (v, good, poor) => (v <= good ? 0 : v <= poor ? 1 : 2);
    const worst = Math.max(rate(perf.lcp, 2500, 4000), rate(perf.cls, 0.1, 0.25), rate(perf.inp, 200, 500));
    track("page_perf", {
      lcp_ms: perf.lcp, cls_x1000: Math.round(perf.cls * 1000), inp_ms: perf.inp,
      ttfb_ms: nav ? Math.round(nav.responseStart) : 0, load_ms: nav && nav.loadEventEnd ? Math.round(nav.loadEventEnd) : 0,
      perf_rating: ["good", "needs_improvement", "poor"][worst],
    });
  });
})();
