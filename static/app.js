// Click a <th data-sort> to sort its table; numeric cells use data-v. The
// header's text goes into a button so the keyboard can sort too, and
// aria-sort tells screen readers which column the rows follow.
document.querySelectorAll("th[data-sort]").forEach((th) => {
  const btn = Object.assign(document.createElement("button"), { type: "button", className: "sort-btn" });
  btn.append(...th.childNodes);
  th.append(btn);
  btn.addEventListener("click", () => {
    const table = th.closest("table");
    const idx = [...th.parentNode.children].indexOf(th);
    const body = table.tBodies[0];
    const asc = th.dataset.dir !== "asc";
    th.dataset.dir = asc ? "asc" : "desc";
    for (const other of th.parentNode.querySelectorAll("th[aria-sort]")) other.removeAttribute("aria-sort");
    th.setAttribute("aria-sort", asc ? "ascending" : "descending");
    const key = (tr) => {
      const td = tr.children[idx];
      const v = td.dataset.v ?? td.textContent.trim();
      return th.dataset.sort === "num" ? parseFloat(v) || 0 : v.toLowerCase();
    };
    const rows = [...body.rows].sort((a, b) => {
      const x = key(a), y = key(b);
      return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1);
    });
    rows.forEach((r) => body.appendChild(r));
  });
});

// Club rows on a voting page expand to the named votes of that club. The
// ballots live in one JSON file per sitting (shared by both languages) and
// are loaded on first use; the whole row is clickable.
const clubsTable = document.querySelector(".clubs-table");
if (clubsTable) {
  const { ballots, mps, vote, root } = clubsTable.dataset;
  const labels = JSON.parse(clubsTable.dataset.labels);
  let data = null;
  const json = (url) => fetch(url).then((r) => {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  });
  // a failed load is forgotten, so the next try fetches again
  const load = () =>
    data ??= Promise.all([json(ballots), json(mps)]).catch((e) => { data = null; throw e; });

  const el = (tag, props = {}, children = []) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children);
    return node;
  };

  const fill = async (tr, cell) => {
    const [byVote, names] = await load();
    const groups = byVote[vote]?.[tr.dataset.club] ?? {};
    const rebels = new Set(tr.dataset.rebels.split(",").filter(Boolean).map(Number));
    for (const code of ["Y", "N", "A", "X"]) {
      const ids = groups[code];
      if (!ids?.length) continue;
      const items = ids.map((id) => el("li", rebels.has(id) ? { className: "rebel", title: labels.rebel } : {}, [
        el("a", { href: `${root}posel/${id}.html`, textContent: names[id] ?? `#${id}` }),
      ]));
      cell.append(el("div", {}, [
        el("p", { className: `v-${code}` }, [el("strong", { textContent: labels[code] }), ` (${ids.length})`]),
        el("ul", {}, items),
      ]));
    }
  };

  // Fill a club's names once; while loading the cell holds a note, so a
  // quick close and reopen does not start a second fill. On failure the note
  // says so and offers another try.
  const show = (tr, cell) => {
    cell.replaceChildren(el("p", { className: "muted", textContent: T.loading }));
    fill(tr, cell).then(() => cell.firstChild.remove(), () => {
      const retry = el("button", { type: "button", className: "link-btn", textContent: T.retry });
      retry.addEventListener("click", () => show(tr, cell));
      cell.replaceChildren(el("p", { className: "muted", role: "alert" }, [`${T.namesFailed} `, retry]));
    });
  };

  clubsTable.querySelectorAll(".club-row").forEach((tr) => {
    const btn = tr.querySelector(".club-toggle");
    const row = document.getElementById(btn.getAttribute("aria-controls"));
    const cell = row.querySelector(".name-cols");
    tr.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      const open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(open));
      row.hidden = !open;
      if (open && !cell.childElementCount) show(tr, cell);
    });
  });
}

// Amendment lists (adopted-amendments page, per-proposer pages): filter rows
// by proposer, outcome, committee recommendation and free text.
const amendTable = document.querySelector("#adopted-table, #amend-table");
if (amendTable) {
  const by = (id) => document.getElementById(id);
  const proposer = by("proposer-filter"), status = by("status-filter");
  const against = by("against-filter"), text = by("text-filter"), count = by("filter-count");
  const rows = [...amendTable.rows];
  const fold = (s) => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ł/g, "l");
  const apply = () => {
    const who = proposer?.value, outcome = status?.value, q = text ? fold(text.value.trim()) : "";
    let shown = 0;
    for (const tr of rows) {
      tr._text ??= q ? fold(tr.textContent) : undefined;
      const hide =
        (who && !(tr.dataset.proposer || "").split("|").includes(who)) ||
        (outcome && tr.dataset.outcome !== outcome) ||
        (against?.checked && tr.dataset.against !== "1") ||
        (q && !tr._text.includes(q));
      tr.hidden = Boolean(hide);
      if (!hide) shown++;
    }
    if (count) count.textContent = `${shown} / ${rows.length}`;
  };
  for (const el of [proposer, status, against]) el?.addEventListener("change", apply);
  text?.addEventListener("input", apply);
  apply();
}

// MP list: search by name, constituency or club, and filters. The choice is
// kept in the address (?q=…&klub=…), so a filtered list can be linked to.
const mpTable = document.getElementById("mp-table");
if (mpTable) {
  const form = document.getElementById("mp-filters");
  const fields = [...form.querySelectorAll("[name]")];
  const count = document.getElementById("mp-count");
  const rows = [...mpTable.tBodies[0].rows];
  const fold = (s) => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ł/g, "l");
  for (const tr of rows) tr._text = fold(tr.dataset.text);
  const value = (name) => {
    const el = form.querySelector(`[name="${name}"]`);
    return el.type === "checkbox" ? (el.checked ? el.value : "") : el.value.trim();
  };
  const apply = () => {
    const q = fold(value("q")), club = value("klub"), district = value("okreg"), active = value("mandat"), moved = value("zmiany");
    let shown = 0;
    for (const tr of rows) {
      const d = tr.dataset;
      const hide = (q && !q.split(/\s+/).every((w) => tr._text.includes(w))) || (club && d.club !== club) ||
        (district && d.district !== district) || (active && d.active !== active) || (moved && d.switch !== "1");
      tr.hidden = Boolean(hide);
      if (!hide) shown++;
    }
    count.textContent = `${shown} / ${rows.length}`;
    const params = new URLSearchParams();
    for (const el of fields) if (value(el.name)) params.set(el.name, value(el.name));
    history.replaceState(null, "", `${location.pathname}${params.size ? `?${params}` : ""}${location.hash}`);
  };
  const params = new URLSearchParams(location.search);
  for (const el of fields) {
    const v = params.get(el.name);
    if (v !== null) {
      if (el.type === "checkbox") el.checked = v === el.value;
      else if (el.tagName !== "SELECT" || [...el.options].some((o) => o.value === v)) el.value = v;
    }
    el.addEventListener(el.type === "search" ? "input" : "change", apply);
  }
  apply();
}

// A search box over a list of items (committee meetings): <input data-filter=".item">
// hides the items in its section whose data-text does not have every word typed.
// Items added later (a list loaded on request) are picked up at the next search.
for (const input of document.querySelectorAll("input[data-filter]")) {
  const scope = input.closest("section") || document;
  const count = scope.querySelector("[data-filter-count]");
  const fold = (s) => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ł/g, "l");
  input.addEventListener("input", () => {
    const items = [...scope.querySelectorAll(input.dataset.filter)];
    for (const el of items) el._text ??= fold(el.dataset.text || el.textContent);
    const words = fold(input.value.trim()).split(/\s+/).filter(Boolean);
    let shown = 0;
    for (const el of items) {
      el.hidden = !words.every((w) => el._text.includes(w));
      if (!el.hidden) shown++;
    }
    if (count) count.textContent = words.length ? `${shown} / ${items.length}` : "";
  });
}

// Sections of MP and club pages as tabs (templates/_tabs.html): one shown
// at a time, picked by a click or by the address, which a click updates
// without jumping; arrow keys move between tabs.
const tabBar = document.querySelector(".tab-bar");
const tabPanels = document.querySelector(".tab-panels");
const tabs = tabBar ? [...tabBar.querySelectorAll("a")] : [];
const showTab = (id, focus = false) => {
  const tab = tabs.find((t) => t.getAttribute("aria-controls") === id);
  if (!tab) return;
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    document.getElementById(t.getAttribute("aria-controls"))?.classList.toggle("active", on);
  }
  // bring the tab into view in a bar that scrolls sideways, without moving the page
  if (tab.offsetLeft < tabBar.scrollLeft || tab.offsetLeft + tab.offsetWidth > tabBar.scrollLeft + tabBar.clientWidth) {
    tabBar.scrollLeft = tab.offsetLeft - 16;
  }
  if (focus) tab.focus();
};
if (tabBar && tabPanels && tabs.length) {
  tabBar.setAttribute("role", "tablist");
  for (const t of tabs) {
    t.setAttribute("role", "tab");
    const panel = document.getElementById(t.getAttribute("aria-controls"));
    panel?.setAttribute("role", "tabpanel");
    panel?.setAttribute("aria-labelledby", t.id);
    t.addEventListener("click", (e) => {
      e.preventDefault();
      showTab(t.getAttribute("aria-controls"));
      history.replaceState(null, "", t.getAttribute("href"));
    });
    t.addEventListener("keydown", (e) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      const next = tabs[(tabs.indexOf(t) + step + tabs.length) % tabs.length];
      showTab(next.getAttribute("aria-controls"), true);
      history.replaceState(null, "", next.getAttribute("href"));
    });
  }
  showTab(tabs[0].getAttribute("aria-controls"));
  tabPanels.classList.add("ready");
}

// Jumping to an anchor inside a collapsed <details> (the index of law
// changes on bill pages) or a tab that is not shown: open the sections
// around the target first. A tab's own address scrolls to the tab bar.
const revealTarget = () => {
  const target = location.hash.length > 1 && document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if (!target) return;
  const panel = target.closest(".tab-panels > .tab-panel");
  if (panel) showTab(panel.id);
  for (let d = target.closest("details"); d; d = d.parentElement?.closest("details")) d.open = true;
  (target === panel ? tabBar : target).scrollIntoView({ block: "start" });
};
window.addEventListener("hashchange", revealTarget);
revealTarget();

// ---------------------------------------------------------------------------
// Site-wide extras: footer links, consent bar, support pill and support note.
// They are added here rather than in the page template on purpose: the site
// is ~18,000 static HTML files, and anything in the shared template forces
// every one of them to be re-uploaded. Changing this file uploads one file.
const LANG = document.documentElement.lang === "en" ? "en" : "pl";
const ROOT = (document.querySelector(".brand")?.getAttribute("href") || "index.html").replace(/index\.html$/, "");
const COFFEE_URL = "https://buycoffee.to/sejmomat?tab=subs";
// ROOT is the language root ("" or "en/" level); the games live at the site root.
const SITE_ROOT = LANG === "en" ? `${ROOT}../` : ROOT;
const T = {
  pl: {
    privacy: "Prywatność", consentSettings: "Ustawienia zgody", stats: "Statystyki", contents: "Spis treści", articles: "Artykuły",
    consentText: "Ta strona Cię nie śledzi. Za Twoją zgodą zapisze w przeglądarce, ile czasu dziś tu spędzasz, " +
      "wyłącznie po to, by najwyżej raz dziennie przypomnieć o możliwości wsparcia projektu, i sama włączy odtwarzacz " +
      "YouTube, gdy nadajemy na żywo (Google otrzymuje wtedy Twój adres IP).",
    consentTextGa: "Za Twoją zgodą strona użyje Google Analytics, by liczyć odwiedziny (pliki cookie Google), i zapisze w przeglądarce " +
      "czas spędzony dziś na stronie, używany do przypominania o możliwości wsparcia projektu, oraz sama włączy odtwarzacz YouTube, " +
      "gdy nadajemy na żywo. Bez zgody nic z tego się nie dzieje.",
    pitchGa: "Projekt jest darmowy i bez reklam. Jeśli chcesz, możesz postawić autorowi kawę.",
    essential: "Tylko niezbędne", agree: "Zgadzam się",
    support: "Wesprzyj", close: "Zamknij", useful: "Sejmomat się przydaje?",
    pitch: "Projekt jest darmowy, bez reklam i śledzenia. Jeśli chcesz, możesz postawić autorowi kawę.",
    buy: "Postaw kawę", later: "Nie teraz",
    fundTitle: "Wesprzyj Sejmomat",
    fundText: "Sejmomat jest i będzie darmowy, ale żeby się rozwijać potrzebuje funduszy.",
    fundNow: "Teraz: {x} zł miesięcznie", fundMonthly: "zł miesięcznie", fundGo: "Wesprzyj na buycoffee.to", fundLater: "Może później",
    fundTiers: [[150, "pełne samodzielne finansowanie serwisu"], [200, "lepszy serwer: wyższa jakość transmisji"],
      [550, "fact-checking na żywo i nakładki z posiedzeń komisji"]],
    skip: "Przejdź do treści", loading: "Wczytywanie…", namesFailed: "Nie udało się wczytać listy posłów.", retry: "Spróbuj ponownie",
  },
  en: {
    privacy: "Privacy", consentSettings: "Consent settings", stats: "Statistics", contents: "Contents", articles: "Articles",
    consentText: "This site does not track you. With your consent it will keep in your browser how long you spend here each day, " +
      "used only to mention at most once a day that you can support the project, and start the YouTube player by itself when we are " +
      "live (Google then receives your IP address).",
    consentTextGa: "With your consent the site will use Google Analytics to count visits (Google cookies), and keep in your browser " +
      "the time spent on the site today, used to mention that you can support the project, and start the YouTube player by itself when we " +
      "are live. Without consent none of this happens.",
    pitchGa: "The project is free, with no ads. If you like, you can buy the author a coffee.",
    essential: "Only essential", agree: "I agree",
    support: "Support", close: "Close", useful: "Finding Sejmomat useful?",
    pitch: "The project is free, with no ads or tracking. If you like, you can buy the author a coffee.",
    buy: "Buy a coffee", later: "Not now",
    fundTitle: "Support Sejmomat",
    fundText: "Sejmomat is and will stay free, but to grow it needs funding.",
    fundNow: "Now: {x} zł a month", fundMonthly: "zł a month", fundGo: "Support on buycoffee.to", fundLater: "Maybe later",
    fundTiers: [[150, "the site funds itself in full"], [200, "a better server: higher-quality streaming"],
      [550, "live fact-checking and committee overlays"]],
    skip: "Skip to content", loading: "Loading…", namesFailed: "Could not load the list of MPs.", retry: "Try again",
  },
}[LANG];
const h = (tag, props = {}, children = []) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
// "Skip to content", the first stop for the keyboard; shown only when focused.
const mainEl = document.querySelector("main");
if (mainEl) {
  mainEl.id ||= "tresc";
  mainEl.tabIndex = -1;
  document.body.prepend(h("a", { className: "skip-link", href: `#${mainEl.id}`, textContent: T.skip }));
}
const privacyLink = () => h("a", { href: `${ROOT}prywatnosc.html`, textContent: T.privacy });

// Consent for optional browser storage and, when the site has a Google
// Analytics id (<meta name="sejmomat-ga">, set by the build from the
// GA_MEASUREMENT_ID variable), for analytics. The choice itself is kept in
// localStorage (needed to remember the answer); nothing optional runs before
// "agree". With analytics the text and the privacy page say so, and the
// consent version is new, so everyone is asked again.
const GA_ID = document.querySelector('meta[name="sejmomat-ga"]')?.content || "";
// 3 and 4 (were 1 and 2): consent also starts Sejmomat's YouTube player (static/yt.js), so it is asked again
const CONSENT_VERSION = GA_ID ? 4 : 3;
if (GA_ID) Object.assign(T, { consentText: T.consentTextGa, pitch: T.pitchGa });
const CONSENT_KEY = "sejmomat-consent";
const SUPPORT_KEY = "sejmomat-support";
const readConsent = () => {
  try {
    const c = JSON.parse(localStorage.getItem(CONSENT_KEY) || "null");
    return c && c.v === CONSENT_VERSION ? c : null;
  } catch {
    return null;
  }
};
const onConsent = [];
let consentApplied = false;
const applyConsent = (granted) => {
  if (!granted || consentApplied) return;
  consentApplied = true;
  onConsent.forEach((fn) => fn());
};
// Google Analytics' cookies (_ga, _ga_<id>), removed when consent is withdrawn;
// they are set for the site's domain, with or without "www."
const dropAnalyticsCookies = () => {
  const host = location.hostname.replace(/^www\./, "");
  for (const name of document.cookie.split(";").map((c) => c.split("=")[0].trim()).filter((n) => /^_ga(_|$)/.test(n))) {
    for (const domain of ["", `; domain=${host}`, `; domain=.${host}`]) {
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/${domain}`;
    }
  }
};
const choose = (optional) => {
  try {
    localStorage.setItem(CONSENT_KEY, JSON.stringify({ v: CONSENT_VERSION, optional, at: Date.now() }));
    if (!optional) localStorage.removeItem(SUPPORT_KEY);
  } catch {
    // storage unavailable: the choice lasts for this page only
  }
  if (!optional) dropAnalyticsCookies();
  consentBar.hidden = true;
  applyConsent(optional);
};
// Class names are deliberately neutral: cookie-notice filter lists hide
// elements by class (EasyList Cookie has a generic rule for ".consent-bar"),
// which made this bar vanish a moment after it appeared.
const consentBar = h("div", { className: "sm-choice", hidden: true }, [
  h("p", {}, [T.consentText + " ", privacyLink()]),
  h("p", { className: "sm-choice-actions" }, [
    h("button", { type: "button", textContent: T.essential, onclick: () => choose(false) }),
    h("button", { type: "button", textContent: T.agree, onclick: () => choose(true) }),
  ]),
]);
consentBar.setAttribute("role", "region");
consentBar.setAttribute("aria-label", T.consentSettings);

// Google Analytics, only with consent and only when the site has an id.
if (GA_ID) {
  onConsent.push(() => {
    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag() { window.dataLayer.push(arguments); };
    window.gtag("js", new Date());
    window.gtag("config", GA_ID);
    document.head.append(h("script", { async: true, src: `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(GA_ID)}` }));
  });
}

// Support window: once a day for readers who spend a while on the site. With consent the time
// is added up across pages in localStorage (the counter the consent text names), and the window
// comes once a day after SUPPORT_AFTER_S seconds on the site that day; without consent nothing is
// stored, and it comes after that long on one page, once a page view. It shows the monthly
// support so far against what each tier makes possible (static/wsparcie.json, edited by hand).
const SUPPORT_AFTER_S = 180;
const today = () => new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Warsaw" });
let supportShown = false;
const showSupport = async () => {
  if (supportShown || document.querySelector("dialog[open]")) return false;
  supportShown = true;
  let fund = { monthly: 0 };
  try {
    fund = await (await fetch(`${SITE_ROOT}static/wsparcie.json`, { cache: "no-cache" })).json();
  } catch {
    // no figure: the tiers alone
  }
  const now = Math.max(0, Number(fund.monthly) || 0);
  const top = T.fundTiers[T.fundTiers.length - 1][0];
  const pct = (x) => `${Math.min(100, (x / top) * 100).toFixed(2)}%`;
  const fill = h("span", { className: "fund-fill" });
  fill.style.width = pct(now);
  const marks = T.fundTiers.map(([amount, what]) => {
    const m = h("li", { className: `fund-tier${now >= amount ? " done" : ""}` }, [
      h("strong", { textContent: `${amount} zł` }), h("span", { textContent: what })]);
    return m;
  });
  const ticks = T.fundTiers.map(([amount]) => {
    const t = h("span", { className: `fund-tick${now >= amount ? " done" : ""}` });
    t.style.left = pct(amount);
    return t;
  });
  const dlg = h("dialog", { className: "fund-dialog" }, [
    h("button", { type: "button", className: "support-close", textContent: "×", ariaLabel: T.close, onclick: () => dlg.close() }),
    h("h2", { textContent: T.fundTitle }),
    h("p", { className: "fund-lead", textContent: T.fundText }),
    h("div", { className: "fund-meter", role: "meter" }, [h("span", { className: "fund-track" }, [fill, ...ticks])]),
    h("p", { className: "fund-now", textContent: T.fundNow.replace("{x}", now) }),
    h("ol", { className: "fund-tiers" }, marks),
    h("p", { className: "fund-actions" }, [
      h("a", { className: "btn fund-go", href: COFFEE_URL, target: "_blank", rel: "noopener", textContent: T.fundGo, onclick: () => dlg.close() }),
      h("button", { type: "button", className: "lnk", textContent: T.fundLater, onclick: () => dlg.close() }),
    ]),
  ]);
  const meter = dlg.querySelector(".fund-meter");
  meter.setAttribute("aria-valuemin", "0");
  meter.setAttribute("aria-valuemax", String(top));
  meter.setAttribute("aria-valuenow", String(now));
  meter.setAttribute("aria-label", T.fundNow.replace("{x}", now));
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener("close", () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
  return true;
};
// time on the page while it is in view, a tick every 5 seconds
const watchTime = (onTick) => {
  let last = Date.now();
  setInterval(() => {
    const t = Date.now();
    if (document.visibilityState === "visible") onTick((t - last) / 1000);
    last = t;
  }, 5000);
};
onConsent.push(() => {
  try {
    const read = () => JSON.parse(localStorage.getItem(SUPPORT_KEY) || "{}");
    watchTime(async (dt) => {
      const state = read();
      if (state.day !== today()) Object.assign(state, { day: today(), seconds: 0, shown: false });
      state.seconds = (state.seconds || 0) + dt;
      if (!state.shown && state.seconds >= SUPPORT_AFTER_S && await showSupport()) state.shown = true;
      localStorage.setItem(SUPPORT_KEY, JSON.stringify(state));
    });
  } catch {
    // storage unavailable: as without consent
  }
});
// #wesprzyj in the address opens it at once (a link to it, or a look at it)
if (location.hash === "#wesprzyj") showSupport();
// without consent: this page's own time only, nothing kept
setTimeout(() => {
  if (readConsent()?.optional === true) return;
  let seconds = 0;
  watchTime((dt) => {
    seconds += dt;
    if (seconds >= SUPPORT_AFTER_S && !supportShown && readConsent()?.optional !== true) showSupport();
  });
}, 0);

// Always-visible support pill (no storage involved), footer links, consent bar.
document.body.append(
  h("a", { className: "support-pill", href: COFFEE_URL, target: "_blank", rel: "noopener", textContent: `☕ ${T.support}` }),
  consentBar,
);
// Side navigation for legal documents (print and bill pages): sections,
// amended acts, amendment numbers and the articles of the full text. A fixed
// column on wide screens, a button that opens the same panel otherwise.
(() => {
  const content = document.querySelector("main");
  if (!content || !content.querySelector(".print-text, main > details.law, .amendment[id]")) return;
  const list = h("div", { className: "side-toc-list" });
  const link = (target, text, cls = "") => h("a", { href: `#${target.id}`, textContent: text, className: cls });
  const chips = (items) => h("p", { className: "side-toc-chips" }, items);
  let n = 0;
  for (const h2 of content.querySelectorAll("h2")) {
    h2.id ||= `sekcja-${++n}`;
    list.append(link(h2, h2.textContent.trim(), "side-toc-h"));
    // what follows this heading, up to the next one
    const acts = [], amendments = [];
    for (let el = h2.nextElementSibling; el && el.tagName !== "H2"; el = el.nextElementSibling) {
      if (el.matches("details.law[id]")) acts.push(el);
      if (el.matches(".amendment[id]")) amendments.push(el);
      if (el.matches(".print-text")) {
        // The document's own articles only. A bill quotes articles of the
        // acts it changes („Art. 11a. …”), and those would otherwise be listed
        // between the bill's Art. 1 and Art. 2: skip everything inside quotes.
        const own = [], sequential = [];
        let depth = 0, next = 1;
        for (const p of el.children) {
          const t = p.textContent;
          const m = /^Art\.\s*(\d+[a-z]*)\./.exec(t);
          if (m && depth <= 0) own.push([m[1], p]);
          if (m && m[1] === String(next)) { sequential.push([m[1], p]); next++; }
          for (const ch of t) depth += ch === "„" ? 1 : ch === "”" ? -1 : 0;
          if (depth < 0) depth = 0;
        }
        // an unclosed quote would hide the rest: then trust plain 1, 2, 3 … order
        const seen = new Set(), arts = [];
        for (const [label, p] of (own.length >= sequential.length ? own : sequential)) {
          if (seen.has(label)) continue;
          seen.add(label);
          p.id = `art-${label}`;
          arts.push(link(p, label));
        }
        if (arts.length > 1) list.append(h("p", { className: "side-toc-sub", textContent: T.articles }), chips(arts));
      }
    }
    for (const act of acts) {
      list.append(link(act, act.querySelector("summary strong")?.textContent.trim() || act.id, "side-toc-sub"));
      // the articles changed in this act, as listed by the index above the changes
      const arts = [...content.querySelectorAll(`.law-index a.chip[href^="#${act.id}-"]`)]
        .map((a) => h("a", { href: a.getAttribute("href"), textContent: a.textContent.replace(/^art\.\s*/, "") }));
      if (arts.length) list.append(chips(arts));
    }
    if (amendments.length > 1) list.append(chips(amendments.map((a) => link(a, a.id.replace(/^\D+/, "")))));
  }
  if (list.querySelectorAll("a").length < 6) return;
  const toc = h("nav", { className: "side-toc" }, [h("strong", { textContent: T.contents }), list]);
  toc.setAttribute("aria-label", T.contents);
  const toggle = h("button", { type: "button", className: "side-toc-toggle", textContent: `☰ ${T.contents}` });
  toggle.addEventListener("click", () => toc.classList.toggle("open"));
  list.addEventListener("click", (e) => { if (e.target.closest("a")) toc.classList.remove("open"); });
  document.body.append(toggle, toc);
})();

// Link to the games (kept out of the page template for the same reason).

// "Show all" under a list cut short (the home page's bills): without scripts the whole list shows.
document.querySelectorAll("[data-show-all]").forEach((btn) => {
  const list = document.getElementById(btn.dataset.showAll);
  if (!list) return;
  btn.hidden = false;
  btn.addEventListener("click", () => {
    list.classList.add("show-all");
    btn.closest("p")?.remove();
    list.querySelector("tr.extra a")?.focus();
  });
});

const foot = document.querySelector("footer.foot");
if (foot) {
  const settings = h("a", { href: "#", textContent: T.consentSettings });
  settings.addEventListener("click", (e) => {
    e.preventDefault();
    consentBar.hidden = false;
  });
  foot.append(" · ", h("a", { href: `${ROOT}statystyki.html`, textContent: T.stats }), " · ", privacyLink(), " · ", settings);
}
const consent = readConsent();
// for static/yt.js: the reader's current consent (of this version) to the optional services
window.sejmomatConsented = () => readConsent()?.optional === true;
if (consent) applyConsent(consent.optional);
else consentBar.hidden = false;

// Folded explanations ("Jak liczymy?", templates/_macros.html how) print opened.
window.addEventListener("beforeprint", () => {
  document.querySelectorAll("details.how:not([open])").forEach((d) => {
    d.open = true;
    d.dataset.printOpened = "1";
  });
});
window.addEventListener("afterprint", () => {
  document.querySelectorAll("details.how[data-print-opened]").forEach((d) => {
    d.open = false;
    delete d.dataset.printOpened;
  });
});
