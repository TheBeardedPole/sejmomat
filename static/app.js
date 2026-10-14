// Click a <th data-sort> to sort its table; numeric cells use data-v.
document.querySelectorAll("th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => {
    const table = th.closest("table");
    const idx = [...th.parentNode.children].indexOf(th);
    const body = table.tBodies[0];
    const asc = th.dataset.dir !== "asc";
    th.dataset.dir = asc ? "asc" : "desc";
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
  const load = () =>
    data ??= Promise.all([fetch(ballots).then((r) => r.json()), fetch(mps).then((r) => r.json())]);

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

  clubsTable.querySelectorAll(".club-row").forEach((tr) => {
    const btn = tr.querySelector(".club-toggle");
    const row = document.getElementById(btn.getAttribute("aria-controls"));
    const cell = row.querySelector(".name-cols");
    tr.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      const open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(open));
      row.hidden = !open;
      if (open && !cell.childElementCount) fill(tr, cell);
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
const COFFEE_URL = "https://buycoffee.to/adamkoscielak";
// ROOT is the language root ("" or "en/" level); the games live at the site root.
const SITE_ROOT = LANG === "en" ? `${ROOT}../` : ROOT;
const T = {
  pl: {
    privacy: "Prywatność", consentSettings: "Ustawienia zgody", contents: "Spis treści", articles: "Artykuły",
    consentText: "Ta strona Cię nie śledzi. Za Twoją zgodą zapisze w przeglądarce licznik odwiedzonych podstron, " +
      "używany wyłącznie po to, by od czasu do czasu przypomnieć o możliwości wsparcia projektu.",
    essential: "Tylko niezbędne", agree: "Zgadzam się",
    support: "Wesprzyj", close: "Zamknij", useful: "Sejmomat się przydaje?",
    pitch: "Projekt jest darmowy, bez reklam i śledzenia. Jeśli chcesz, możesz postawić autorowi kawę.",
    buy: "Postaw kawę", later: "Nie teraz",
  },
  en: {
    privacy: "Privacy", consentSettings: "Consent settings", contents: "Contents", articles: "Articles",
    consentText: "This site does not track you. With your consent it will keep a page-view counter in your browser, " +
      "used only to occasionally mention that you can support the project.",
    essential: "Only essential", agree: "I agree",
    support: "Support", close: "Close", useful: "Finding Sejmomat useful?",
    pitch: "The project is free, with no ads or tracking. If you like, you can buy the author a coffee.",
    buy: "Buy a coffee", later: "Not now",
  },
}[LANG];
const h = (tag, props = {}, children = []) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
const privacyLink = () => h("a", { href: `${ROOT}prywatnosc.html`, textContent: T.privacy });

// Consent for optional browser storage. The choice itself is kept in
// localStorage (needed to remember the answer); nothing optional runs before
// "agree". To add analytics later: create its <script> inside an
// onConsent.push(() => { ... }) callback below, update the consent text and
// the privacy page, and bump CONSENT_VERSION so everyone is asked again.
const CONSENT_VERSION = 1;
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
const choose = (optional) => {
  try {
    localStorage.setItem(CONSENT_KEY, JSON.stringify({ v: CONSENT_VERSION, optional, at: Date.now() }));
    if (!optional) localStorage.removeItem(SUPPORT_KEY);
  } catch {
    // storage unavailable: the choice lasts for this page only
  }
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

// Support note: a corner card for really dedicated readers only, and only
// with consent (it counts page views in localStorage). It needs at least
// SUPPORT_MIN_VIEWS page views, waits before appearing, never blocks the
// page, and stays away for months once shown, closed or clicked.
const SUPPORT_MIN_VIEWS = 40;
const SUPPORT_DELAY_MS = 30000;
const DAY_MS = 86400000;
onConsent.push(() => {
  try {
    const state = JSON.parse(localStorage.getItem(SUPPORT_KEY) || "{}");
    const save = () => localStorage.setItem(SUPPORT_KEY, JSON.stringify(state));
    state.views = (state.views || 0) + 1;
    save();
    if (state.views < SUPPORT_MIN_VIEWS || state.until > Date.now()) return;
    const snooze = (days) => {
      state.until = Date.now() + days * DAY_MS;
      save();
    };
    const close = (days) => () => {
      note.hidden = true;
      snooze(days);
    };
    const note = h("aside", { className: "support-note", hidden: true }, [
      h("button", { type: "button", className: "support-close", textContent: "×", ariaLabel: T.close, onclick: close(180) }),
      h("p", {}, [h("strong", { textContent: `☕ ${T.useful}` })]),
      h("p", { textContent: T.pitch }),
      h("p", {}, [
        h("a", { className: "support-link", href: COFFEE_URL, target: "_blank", rel: "noopener", textContent: T.buy, onclick: close(365) }),
        h("button", { type: "button", className: "support-later", textContent: T.later, onclick: close(180) }),
      ]),
    ]);
    note.setAttribute("aria-label", T.support);
    document.body.append(note);
    setTimeout(() => {
      note.hidden = false;
      snooze(30); // ignored: not again for a month
    }, SUPPORT_DELAY_MS);
  } catch {
    // storage unavailable (private mode, blocked): never show the note
  }
});

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
document.querySelector("header.top nav")?.append(h("a", { href: `${SITE_ROOT}sejmdle/`, textContent: "Sejmdle" }));
const foot = document.querySelector("footer.foot");
if (foot) {
  const settings = h("a", { href: "#", textContent: T.consentSettings });
  settings.addEventListener("click", (e) => {
    e.preventDefault();
    consentBar.hidden = false;
  });
  foot.append(" · ", privacyLink(), " · ", settings);
}
const consent = readConsent();
if (consent) applyConsent(consent.optional);
else consentBar.hidden = false;

// Light/dark switch in the header. The choice is kept in localStorage (a
// setting the reader asked for, so no consent needed) and applied by the
// inline script in <head> before the page is drawn; with no choice made the
// page follows the system setting.
const THEME_KEY = "sejmomat-theme";
const systemDark = matchMedia("(prefers-color-scheme: dark)");
const isDark = () => (document.documentElement.dataset.theme || (systemDark.matches ? "dark" : "light")) === "dark";
document.querySelectorAll(".theme-switch").forEach((btn) => {
  const sync = () => btn.setAttribute("aria-pressed", String(isDark()));
  sync();
  systemDark.addEventListener("change", sync);
  btn.addEventListener("click", () => {
    const theme = isDark() ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    try {
      // picking what the system already shows means "follow the system"
      if (theme === (systemDark.matches ? "dark" : "light")) {
        delete document.documentElement.dataset.theme;
        localStorage.removeItem(THEME_KEY);
      } else {
        localStorage.setItem(THEME_KEY, theme);
      }
    } catch {
      // storage unavailable: the choice lasts for this page only
    }
    sync();
  });
});
