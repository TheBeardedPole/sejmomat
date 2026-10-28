// The home page's own parts (templates/index.html): the broadcast at the top,
// the reader's interests and what happened in them, and MPs whose work is on
// those topics. The rules are plain functions, exported for Node at the end
// (tests/home.test.js); the page code runs only in a browser.
//
// Broadcasts come from the Sejm's API (videos: every broadcast with its
// scheduled times and stream address). A schedule alone never makes a
// broadcast "live": it is live only when its stream has video in it (the
// stream's playlist lists segments; a planned one lists none). The video
// servers answer only Polish addresses, so elsewhere a broadcast stays
// "scheduled" rather than being called live.
//
// Interests stay in this browser (localStorage "sejmomat-interests"), as the
// theme does; nothing about them is sent anywhere. The data they are matched
// against is dane/zainteresowania.json (sejmomat/interests.py), loaded only
// when the reader has picked something.

const { warsawNow, formatWhen, formatDay, dateRange, plural, PLENARY,
  pickBroadcasts, hasSegments, firstVariant, streamIsOn, broadcastState, load: loadBroadcasts } =
  typeof module !== "undefined" && module.exports ? require("./broadcasts.js") : window.SejmomatBroadcasts;
const { INTERESTS_KEY, REMIND_DAYS, daysBetween, readInterests, writeInterests,
  saveInterests, confirmInterests, skipInterests, reminderDue } =
  typeof module !== "undefined" && module.exports ? require("./interests-state.js") : window.SejmomatInterests;

// ---- events in the reader's topics
const IMPORTANT_STAGES = new Set(["Uchwalono", "Odrzucono", "Prezydent podpisał ustawę", "Wniosek Prezydenta (weto)",
  "Prezydent skierował ustawę do Trybunału Konstytucyjnego", "nie uchwalona ponownie po wecie Prezydenta"]);

const matchesFor = (event, ids) => Object.fromEntries(Object.entries(event.m || {}).filter(([id]) => ids.includes(id)));

// Events in the chosen topics, newest first.
const eventsFor = (events, ids) => events
  .map((e) => ({ ...e, mine: matchesFor(e, ids) }))
  .filter((e) => Object.keys(e.mine).length)
  .sort((a, b) => b.d.localeCompare(a.d));

// A few to start with: one per bill, the weightier kinds first (a decision
// over a step on the way, a bill passed over a motion to reject it), then the
// newer, taken from the reader's topics in turn so that one busy topic does not
// fill them all. This is an order for reading, not a judgement of what matters most.
const weight = (e) => (e.k === "vote" ? (e.mo === "final" ? 3 : 2.5) : IMPORTANT_STAGES.has(e.s) ? 3 : e.k === "agenda" ? 2 : 1);
const highlights = (events, today, n = 4, ids = null) => {
  const scored = events.filter((e) => e.k !== "amend")
    .map((e) => ({ e, score: weight(e) * 10 - Math.max(0, daysBetween(e.d, today)) / 3 }))
    .sort((x, y) => y.score - x.score || y.e.d.localeCompare(x.e.d))
    .map(({ e }) => e);
  const topics = ids || [...new Set(scored.flatMap((e) => Object.keys(e.mine || e.m || {})))];
  const seen = new Set();
  const out = [];
  const take = (e) => {
    seen.add(e.root);
    out.push(e);
  };
  for (let round = 0; out.length < n && round < n; round++) {
    for (const id of topics) {
      const e = scored.find((x) => !seen.has(x.root) && id in (x.mine || x.m || {}));
      if (e) take(e);
      if (out.length === n) break;
    }
  }
  // topics with too little: the rest by score
  for (const e of scored) {
    if (out.length === n) break;
    if (!seen.has(e.root)) take(e);
  }
  return out;
};

// The feed in groups: one per sitting (an event on a sitting's day names it),
// and what happened between two sittings in a group of its own. Events come
// newest first; a group is a run of events with the same sitting.
const feedGroups = (events) => {
  const groups = [];
  for (const e of events) {
    const key = e.p ?? null;
    const last = groups[groups.length - 1];
    if (last && last.p === key) last.events.push(e);
    else groups.push({ p: key, events: [e] });
  }
  return groups;
};

// ---- MPs: their scores in the chosen topics added up, reasons merged; then the
// best of each club (independents together), so the suggestions are not one side's
const suggestMps = (data, ids, n = Infinity) => {
  const total = new Map();
  for (const id of ids) {
    for (const row of data.suggested?.[id] || []) {
      const t = total.get(row.id) || { id: row.id, score: 0, topics: [], why: [] };
      t.score += row.score;
      t.topics.push(id);
      for (const w of row.why) {
        const key = w.k === "committee" ? `c:${w.code}` : w.k === "questions" ? `q:${w.to.join("|")}` : `b:${w.root}:${id}`;
        if (!t.why.some((x) => x.key === key)) t.why.push({ ...w, key, topic: id });
      }
      total.set(row.id, t);
    }
  }
  const clubs = new Set();
  return [...total.values()].sort((a, b) => b.score - a.score || a.id - b.id)
    .filter((r) => {
      const club = data.mps?.[r.id] ? data.mps[r.id].club || "niez." : `#${r.id}`;
      if (clubs.has(club)) return false;
      clubs.add(club);
      return true;
    })
    .slice(0, n);
};

// The same, every club's best few (up to `k`), for a pick that changes on each visit:
// {club: [rows best first]}, clubs in no particular order.
const mpPools = (data, ids, k = 3) => {
  const total = new Map();
  for (const id of ids) {
    for (const row of data.suggested?.[id] || []) {
      const t = total.get(row.id) || { id: row.id, score: 0, topics: [], why: [] };
      t.score += row.score;
      t.topics.push(id);
      for (const w of row.why) {
        const key = w.k === "committee" ? `c:${w.code}` : w.k === "questions" ? `q:${w.to.join("|")}` : `b:${w.root}:${id}`;
        if (!t.why.some((x) => x.key === key)) t.why.push({ ...w, key, topic: id });
      }
      total.set(row.id, t);
    }
  }
  const pools = {};
  for (const r of [...total.values()].sort((a, b) => b.score - a.score || a.id - b.id)) {
    const club = data.mps?.[r.id] ? data.mps[r.id].club || "niez." : `#${r.id}`;
    (pools[club] ||= []);
    if (pools[club].length < k) pools[club].push(r);
  }
  return pools;
};
// One MP from each club's pool, at random, and the clubs in a random order (no side
// first): a different set on every visit. rand: () => [0, 1), Math.random by default.
const shuffle = (list, rand = Math.random) => {
  const out = [...list];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
};
const rotate = (pools, rand = Math.random) =>
  shuffle(Object.values(pools).filter((p) => p.length).map((p) => p[Math.floor(rand() * p.length)]), rand);

if (typeof module !== "undefined") {
  module.exports = {
    warsawNow, formatWhen, formatDay, dateRange, plural, daysBetween, pickBroadcasts, hasSegments, firstVariant, streamIsOn, broadcastState,
    readInterests, writeInterests, saveInterests, confirmInterests, skipInterests, reminderDue,
    eventsFor, highlights, feedGroups, suggestMps, mpPools, rotate, shuffle, INTERESTS_KEY, REMIND_DAYS,
  };
}

if (typeof document !== "undefined") (() => {
  const el = (tag, props = {}, ...children) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
    return node;
  };
  const LANG = document.documentElement.lang === "en" ? "en" : "pl";
  const link = (href, text, external = false, props = {}) => el("a", {
    href, textContent: text, ...(external ? { target: "_blank", rel: "noopener" } : {}), ...props,
  });
  // icons drawn from fixed markup (no data in them)
  const svg = (paths, size = 16, width = 2) => {
    const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("width", size);
    s.setAttribute("height", size);
    s.setAttribute("fill", "none");
    s.setAttribute("stroke", "currentColor");
    s.setAttribute("stroke-width", width);
    s.setAttribute("stroke-linecap", "round");
    s.setAttribute("stroke-linejoin", "round");
    s.setAttribute("aria-hidden", "true");
    s.setAttribute("class", "ico");
    s.innerHTML = paths;
    return s;
  };
  const ICON = {
    tv: '<rect x="2" y="7" width="20" height="13" rx="2"/><path d="M17 2l-5 5-5-5"/>',
    warn: '<path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
    check: '<path d="M20 6L9 17l-5-5"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/>',
    close: '<path d="M18 6L6 18M6 6l12 12"/>',
    left: '<path d="M15 18l-6-6 6-6"/>',
    right: '<path d="M9 18l6-6-6-6"/>',
    edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    committee: '<path d="M3 21h18"/><path d="M5 21V10M19 21V10M9 21V10M15 21V10"/><path d="M2 10 12 3l10 7z"/>',
    question: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    bill: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/>',
  };

  // ---- was / now / next: the broadcast in the middle column
  const box = document.getElementById("transmisja");
  if (box) {
    const L = JSON.parse(box.dataset.labels);
    const wg = box.closest(".wg");
    const plenaryDates = (box.dataset.sittingDates || "").split(",").filter(Boolean);
    const sitting = box.dataset.sitting;
    const nextDay = box.dataset.nextDay;
    const nextNumber = box.dataset.nextNumber;
    const sittingN = (n) => (LANG === "en" ? `Sitting ${n}` : `${n}. posiedzenie`);
    const newTab = (text) => ({ ariaLabel: `${text} (${L.newTab})` });
    const kicker = (icon, text) => el("p", { className: "wg-kicker" }, svg(icon), el("span", { className: "k", textContent: text }));
    const hour = (iso) => iso.slice(11, 16);
    let checking = false;

    // the player below opens only when asked for (static/live.js, data-on-request): this
    // button asks, and the link then scrolls to it
    const watchHere = () => {
      const a = link("#na-zywo", L.watch, false, { className: "btn" });
      a.addEventListener("click", () => document.dispatchEvent(new CustomEvent("sejmomat:watch")));
      return a;
    };
    const render = (s, checkedAt) => {
      const v = s.video;
      const official = v?.playerLink || box.dataset.itv;
      const parts = [];
      box.className = `wg-now broadcast ${s.state === "error" ? "error" : s.state === "none" && !nextDay ? "none" : ""}`.trim();
      wg?.classList.toggle("live", s.state === "live" || s.state === "ours");
      if (s.state === "ours") {
        // Sejmomat's own coverage on YouTube (static/yt.js): played in the live box when the page has one
        box.classList.add("live");
        parts.push(el("p", { className: "wg-kicker wg-livehead" },
          el("span", { className: "live-badge" }, el("span", { className: "live-dot", ariaHidden: "true" }), L.liveBadge),
          el("span", { className: "k", textContent: L.ours })));
        parts.push(el("p", { className: "wg-title", lang: "pl", textContent: s.yt.title || L.ours }));
        parts.push(el("p", { className: "wg-sub", textContent: L.oursSub }));
        const here = document.getElementById("na-zywo");
        parts.push(el("div", { className: "wg-actions" }, here
          ? watchHere()
          : link(`${box.dataset.schedule}#teraz`, L.watch, false, { className: "btn" })));
        box.replaceChildren(...parts);
        return;
      }
      if (s.state === "live") {
        box.classList.add("live");
        parts.push(el("p", { className: "wg-kicker wg-livehead" },
          el("span", { className: "live-badge" }, el("span", { className: "live-dot", ariaHidden: "true" }), L.liveBadge),
          el("span", { className: "k", textContent: L.live })));
        parts.push(el("p", { className: "wg-title", lang: "pl", textContent: v.title }));
        const today = warsawNow().slice(0, 10);
        const day = plenaryDates.indexOf(today);
        if (v.type === PLENARY && sitting && day !== -1) {
          parts.push(el("p", { className: "wg-sub" }, `${sittingN(sitting)} · ${L.day.replace("{n}", day + 1)} · `,
            link(box.dataset.upcoming, L.agenda)));
        }
        // our own player, when the page has it (static/live.js), else the Sejm's
        const ours = v.type === PLENARY && document.getElementById("na-zywo");
        const actions = el("div", { className: "wg-actions" }, ours
          ? watchHere()
          : link(`${box.dataset.schedule}#teraz`, L.watch, false, { className: "btn" }));
        if (s.others.length) {
          const n = s.others.length;
          const label = n === 1 ? L.othersOne : plural(n, ["", L.others, L.othersMany]).replace("{n}", n);
          actions.append(el("details", { className: "wg-others" }, el("summary", { textContent: label }),
            el("ul", {}, s.others.map((o) => el("li", {}, el("span", { className: "live-dot", ariaHidden: "true" }),
              el("a", { href: `${box.dataset.schedule}#teraz`, lang: "pl", textContent: o.title }))))));
        }
        parts.push(actions);
      } else {
        if (s.state === "error") {
          parts.push(kicker(ICON.warn, L.kicker));
          parts.push(el("p", { className: "wg-title plain", role: "status", textContent: L.error }));
          parts.push(el("p", { className: "wg-sub", textContent: L.errorNote }));
          const retry = el("button", { type: "button", className: "btn2", textContent: L.retry });
          retry.addEventListener("click", check);
          parts.push(el("div", { className: "wg-actions" }, retry,
            el("a", { className: "btn2", href: box.dataset.itv, target: "_blank", rel: "noopener", ...newTab("sejm.gov.pl") }, "sejm.gov.pl ↗")));
        } else if (s.state === "scheduled") {
          parts.push(kicker(ICON.tv, L.kicker));
          parts.push(el("p", { className: "wg-title", textContent: L.scheduled }));
          parts.push(el("p", { className: "wg-sub" }, el("span", { lang: "pl", textContent: v.title }),
            ` · ${L.from} ${hour(v.startDateTime)}. ${L.unconfirmed}`));
          parts.push(el("div", { className: "wg-actions" }, link(box.dataset.schedule, `${L.schedule} →`, false, { className: "btn2" })));
        } else if (s.state === "next" || nextDay) {
          parts.push(kicker(ICON.tv, L.kicker));
          parts.push(el("p", { className: "wg-title", textContent: L.noneNow }));
          if (s.state === "next") {
            parts.push(el("p", { className: "wg-sub" }, `${L.nextIs}: ${formatDay(v.startDateTime, LANG)}, ${L.at} ${hour(v.startDateTime)}: `,
              el("span", { lang: "pl", textContent: v.title }), "."));
            const np = s.nextPlenary;
            if (np) {
              parts.push(el("p", { className: "wg-sub" }, `${L.nextPlenary}: ${formatDay(np.startDateTime, LANG)}, ${L.at} ${hour(np.startDateTime)}.`));
            } else if (v.type !== PLENARY && nextDay) {
              parts.push(el("p", { className: "wg-sub", textContent: `${L.nextPlenary}: ${formatDay(nextDay, LANG)}.` }));
            }
          } else {
            // known only from the calendar of sittings, which gives no hour
            const name = nextNumber ? (LANG === "en" ? `Sejm sitting ${nextNumber}` : `${nextNumber}. posiedzenie Sejmu`) : L.sittingPlain;
            parts.push(el("p", { className: "wg-sub", textContent: `${L.nextIs}: ${formatDay(nextDay, LANG)}: ${name}. ${L.hourLater}` }));
          }
          parts.push(el("div", { className: "wg-actions" }, link(box.dataset.schedule, `${L.schedule} →`, false, { className: "btn2" })));
        } else {
          parts.push(kicker(ICON.tv, L.kicker));
          parts.push(el("p", { className: "wg-title plain", textContent: L.none }));
          parts.push(el("div", { className: "wg-actions" }, link(box.dataset.schedule, `${L.schedule} →`, false, { className: "btn2" })));
        }
      }
      box.replaceChildren(...parts);
    };

    async function check() {
      if (checking) return;
      checking = true;
      try {
        const result = await loadBroadcasts({ api: box.dataset.api, yt: box.dataset.yt });
        render(result.state, result.checkedAt);
      } finally {
        checking = false;
      }
    }
    check();
    // a broadcast that starts or ends while the page is open
    setInterval(() => document.visibilityState === "visible" && check(), 2 * 60 * 1000);
  }

  // ---- interests
  const home = document.getElementById("dla-ciebie");
  if (!home) return;
  // "home": what matters to the reader and MPs to know (the home page); "feed": every
  // event in their topics (wydarzenia.html); "mps": every suggested MP (poslowie-dla-ciebie.html)
  const PAGE = home.dataset.page || "home";
  const L = JSON.parse(home.dataset.labels);
  const ROOT = home.dataset.root || "";
  const today = warsawNow().slice(0, 10);
  let state = readInterests(localStorage);
  let data = null;      // the parsed file, once loaded
  let loading = null;   // the request under way; forgotten if it fails, so a retry asks again
  const load = () => loading ??= fetch(home.dataset.src).then((r) => {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then((json) => (data = json)).catch((e) => { loading = null; throw e; });
  const names = JSON.parse(home.dataset.interests);   // [{id, pl, en}], in the page so the form needs no request
  const nameOf = (id) => (names.find((i) => i.id === id) || {})[LANG] || id;
  const href = (url) => (/^https?:/.test(url) ? url : `${ROOT}${url}`);
  const listOf = (ids) => ids.map(nameOf).join(", ");
  const sittingN = (n) => (LANG === "en" ? `Sitting ${n}` : `${n}. posiedzenie`);
  const votesN = (n) => plural(n, [L.votesOne, L.votesFew, L.votesMany]).replace("{n}", n);
  const topicTags = (ids, inherited = false) => el("span", { className: "tags" }, ids.map((id) => el("span", {
    className: `tag ${inherited ? "inh" : "on"}`, textContent: nameOf(id), ...(inherited ? { title: L.inherited } : {}),
  })));
  const section = (id, title, ...body) => {
    const s = el("section", { className: "home-section" }, el("h2", { id, textContent: title }), ...body);
    s.setAttribute("aria-labelledby", id);
    return s;
  };
  const focusSoon = (node) => {
    if (!node) return;
    if (!node.hasAttribute("tabindex") && !/^(A|BUTTON|INPUT)$/.test(node.tagName)) node.tabIndex = -1;
    node.focus({ preventScroll: false });
  };

  // a box in place of a section the reader has not filled yet, leading to the survey
  const placeholder = (id, title, text) => {
    const a = el("a", { className: "btn2", href: "#ankieta", textContent: `${L.pick} ↑` });
    a.addEventListener("click", (e) => {
      e.preventDefault();
      if (!document.getElementById("ankieta")) showForm([]);
      const form = document.getElementById("ankieta");
      form.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
      focusSoon(form.querySelector(".toggle-chip"));
    });
    return section(id, title, el("div", { className: "placeholder" }, el("p", { textContent: text }), a));
  };
  const placeholders = () => (PAGE === "feed"
    ? [placeholder("twoje-tematy", L.feedTitle, L.feedEmpty)]
    : PAGE === "mps" ? [] : [placeholder("poslowie-tematy", L.mpsTitle, L.mpsStart)]);

  // the survey: first visit, "Zmień tematy", or "Tak, chcę je zmienić"
  function showForm(selected, focus = true) {
    const picked = new Set(selected);
    const editing = !!state?.ids?.length;
    const count = el("span", { className: "interests-count", ariaLive: "polite" });
    const save = el("button", { type: "button", className: "btn", textContent: L.save });
    const update = () => {
      const n = picked.size;
      save.disabled = n === 0;
      count.textContent = n === 0 ? L.count0 : n === 1 ? L.count1 : plural(n, ["", L.countFew, L.countMany]).replace("{n}", n);
    };
    const chips = names.map((i) => {
      const b = el("button", { type: "button", className: "toggle-chip" }, el("span", { textContent: i[LANG] }));
      b.setAttribute("aria-pressed", String(picked.has(i.id)));
      b.addEventListener("click", () => {
        if (picked.has(i.id)) picked.delete(i.id);
        else picked.add(i.id);
        b.setAttribute("aria-pressed", String(picked.has(i.id)));
        update();
      });
      return b;
    });
    const skip = el("button", { type: "button", className: "lnk", textContent: editing ? L.cancel : L.skip });
    const form = el("section", { className: "card interests-form", id: "ankieta" },
      el("h2", { id: "ankieta-h", textContent: L.askTitle }),
      el("p", { textContent: L.askText }),
      el("fieldset", {}, el("legend", { textContent: L.askHint }), el("div", { className: "interest-chips" }, chips)),
      el("p", { className: "interests-actions" }, save, skip, count),
      el("p", { className: "muted small", textContent: L.privacy }));
    form.setAttribute("aria-labelledby", "ankieta-h");
    save.addEventListener("click", () => {
      if (!picked.size) return;
      // in the order of the list, not of the clicks
      state = writeInterests(localStorage, saveInterests(names.map((i) => i.id).filter((id) => picked.has(id)), today));
      show({ saved: true });
    });
    skip.addEventListener("click", () => {
      if (!editing) state = writeInterests(localStorage, skipInterests(today));
      show({ focus: true });
    });
    update();
    home.replaceChildren(form, ...(editing ? [] : placeholders()));
    home.hidden = false;
    if (focus) focusSoon(chips[0]);
  }

  const reminder = () => {
    const yes = el("button", { type: "button", className: "btn", textContent: L.remindYes });
    const no = el("button", { type: "button", className: "btn2", textContent: L.remindNo });
    const close = el("button", { type: "button", className: "reminder-close", ariaLabel: L.close }, svg(ICON.close, 18));
    const card = el("aside", { className: "reminder" }, close,
      el("h2", { id: "przypomnienie-h", textContent: L.remindTitle }),
      el("p", { textContent: `${L.remindLast}: ${listOf(state.ids)}.` }),
      el("p", { className: "interests-actions" }, yes, no));
    card.setAttribute("aria-labelledby", "przypomnienie-h");
    yes.addEventListener("click", () => showForm(state.ids));
    no.addEventListener("click", () => {
      state = writeInterests(localStorage, confirmInterests(state, today));
      card.remove();
    });
    // closed without an answer: asked again on the next visit
    close.addEventListener("click", () => card.remove());
    return card;
  };

  const editButton = (cls = "lnk") => {
    const b = el("button", { type: "button", className: cls, textContent: L.edit });
    b.addEventListener("click", () => showForm(state?.ids || []));
    return b;
  };
  // the same, as a pencil beside the topics followed
  const editIcon = () => {
    const b = el("button", { type: "button", className: "icon-btn", title: L.edit, ariaLabel: L.edit }, svg(ICON.edit, 16));
    b.addEventListener("click", () => showForm(state?.ids || []));
    return b;
  };

  const statusOf = (e) => (LANG === "en" ? e.se : e.s);
  const badgeOf = (e, text = statusOf(e)) => (text
    ? el("span", { className: `badge ${e.o === "adopted" ? "adopted" : e.o === "rejected" ? "rejected" : "neutral"}`, textContent: text })
    : null);
  const countsOf = (e) => {
    const [y, n, a] = e.c;
    const c = el("span", { className: "counts" }, el("span", { className: "y", textContent: y }), " / ",
      el("span", { className: "n", textContent: n }), " / ", el("span", { className: "a", textContent: a }));
    c.setAttribute("aria-label", `${y} ${L.yes}, ${n} ${L.no}, ${a} ${L.abstain}`);
    return c;
  };
  const whenOf = (e) => [e.p ? sittingN(e.p) : null, formatWhen(e.d, LANG, true)].filter(Boolean).join(" · ");
  const titleLink = (e) => {
    const url = e.k === "vote" && e.bill ? `ustawa/${e.root}.html` : e.url;
    return url ? link(href(url), e.t, /^https?:/.test(url)) : e.t;
  };

  // "Ważne dla Ciebie": a card per bill
  const card = (e) => {
    // a wide, low tile: what happened on the left; the result, its numbers and the link on the right
    const ids = Object.keys(e.mine);
    const kind = e.k === "vote" ? L.motions[e.mo] || L.kinds.vote : L.kinds[e.k];
    const main = el("div", { className: "vcard-main" }, el("span", { className: "k", textContent: kind }),
      el("h3", { lang: "pl" }, titleLink(e)),
      el("div", { className: "vcard-meta" }, topicTags(ids), el("span", { textContent: whenOf(e) })));
    const side = el("div", { className: "vcard-side" }, e.k === "agenda" && e.p ? badgeOf(e, sittingN(e.p)) : badgeOf(e));
    if (e.k === "vote") {
      const total = e.c.reduce((x, y) => x + y, 0) || 1;
      const bar = el("div", { className: "bar", ariaHidden: "true" }, ["Y", "N", "A"].map((c, i) => {
        const sp = el("span", { className: c });
        sp.style.width = `${(e.c[i] / total) * 100}%`;
        return sp;
      }));
      side.append(el("div", { className: "vcard-bar" }, bar, countsOf(e)));
      const [n, k] = e.a || [0, 0];
      if (n) side.append(el("p", { className: "vcard-sum", textContent: L.amendBefore.replace("{n}", votesN(n)).replace("{k}", k) }));
      side.append(link(href(e.url), `${L.voteDetails} →`));
    } else if (e.k === "agenda") {
      side.append(link(href(e.url), `${L.agendaDetails} →`));
    } else if (e.k === "stage" && e.bill) {
      side.append(link(href(`ustawa/${e.root}.html`), `${L.billDetails} →`));
    }
    return el("li", { className: "card vcard" }, main, side);
  };

  // the latest events: a table per sitting (a list on phones, by the stylesheet)
  const row = (e) => {
    const ids = Object.keys(e.mine);
    let ev, res = null;
    if (e.k === "vote") {
      ev = e.mo === "final" ? `${L.voteNo.replace("{n}", e.n)} · ${L.whole}` : `${L.voteNo.replace("{n}", e.n)} · ${L.motions[e.mo] || ""}`;
      res = [badgeOf(e), el("br"), countsOf(e)];
    } else if (e.k === "amend") {
      ev = L.kinds.amend;
      res = link(href(e.url), `${votesN(e.a[0])} →`);
    } else if (e.k === "stage") {
      ev = `${L.kinds.stage} · ${formatWhen(e.d, LANG)}`;
      res = badgeOf(e);
    } else {
      ev = `${e.n ? L.agendaItem.replace("{n}", e.n) : L.kinds.agenda} · ${formatWhen(e.d, LANG)}`;
    }
    const title = e.k === "amend" ? link(href(e.url), `${L.amendTitle}: ${e.t}`) : e.url ? link(href(e.url), e.t, /^https?:/.test(e.url)) : e.t;
    return el("tr", { className: "frow" },
      el("td", { className: "ev", textContent: ev }),
      el("td", { className: "what", lang: "pl" }, title),
      el("td", {}, topicTags(ids, e.k === "amend")),
      el("td", { className: "res" }, res));
  };
  const caption = (g) => {
    if (g.p) {
      const days = data.sittings?.[g.p];
      const up = g.p === data.upcoming ? ` (${L.sittingUpcoming})` : "";
      return `${sittingN(g.p)}${up}${days ? ` · ${dateRange(days[0], days[1], LANG)}` : ""}`;
    }
    const ds = g.events.map((e) => e.d).sort();
    return `${L.between} · ${dateRange(ds[0], ds[ds.length - 1], LANG)}`;
  };
  const feedTable = (g) => el("div", { className: "card feed-card feed-group" }, el("table", { className: "feed" },
    el("caption", { textContent: caption(g) }),
    el("thead", {}, el("tr", {}, L.cols.map((c, i) => {
      const th = el("th", { scope: "col", textContent: c });
      if (i === 3) th.style.textAlign = "right";
      return th;
    }))),
    el("tbody", {}, g.events.map(row))));

  const personal = async ({ saved = false, focus = false } = {}) => {
    const parts = [];
    if (reminderDue(state, today)) parts.push(reminder());
    let note;
    if (saved) {
      note = el("div", { className: "card interests-note", role: "status" },
        el("span", { className: "ok-icon" }, svg(ICON.check, 18, 2.5)),
        el("div", {}, el("p", {}, el("strong", { textContent: L.savedTitle })),
          el("p", { className: "muted", textContent: `${L.following}: ${listOf(state.ids)}` })),
        editButton("btn2"));
    } else {
      note = el("div", { className: "following" }, el("span", { textContent: `${L.following}:` }),
        topicTags(state.ids), editIcon());
    }
    parts.push(note);
    const lead = el("div", { className: "home-lead" }, el("h2", { id: "wazne-dla-ciebie", textContent: L.forYou }),
      el("p", { textContent: L.forYouText }));
    const top = el("section", {}, lead);
    top.setAttribute("aria-labelledby", "wazne-dla-ciebie");
    parts.push(top);
    home.replaceChildren(...parts);
    home.hidden = false;
    if (saved || focus) focusSoon(note);
    try {
      await load();
    } catch {
      const retry = el("button", { type: "button", className: "lnk", textContent: L.retry });
      retry.addEventListener("click", () => personal());
      top.append(el("p", { className: "muted", role: "alert" }, `${L.failed} `, retry));
      return;
    }
    const mine = eventsFor(data.events, state.ids);
    if (PAGE === "mps") {
      top.remove();
      home.append(...mpsAll());
      return;
    }
    if (PAGE === "feed") {
      top.remove();
      if (!mine.length) {
        home.append(el("p", { textContent: L.empty }), el("p", {}, editButton()));
        return;
      }
      const groups = el("div");
      const more = el("button", { type: "button", className: "lnk feed-more", textContent: L.more });
      const step = 15;
      let shown = 0;
      const page = () => {
        shown += step;
        groups.replaceChildren(...feedGroups(mine.slice(0, shown)).map(feedTable));
        if (shown >= mine.length) more.remove();
      };
      more.addEventListener("click", page);
      home.append(el("p", { className: "muted", textContent: L.feedText.replace("{n}", data.days) }), groups, more);
      page();
      return;
    }
    if (!mine.length) {
      top.append(el("p", { textContent: L.empty }),
        el("p", {}, editButton(), " · ", link(`${ROOT}ostatnie-posiedzenie.html`, `${L.general} →`)));
    } else {
      top.append(el("ul", { className: "vcards" }, highlights(mine, today, 4, state.ids).map(card)),
        el("p", { className: "vcards-all" }, link(`${ROOT}wydarzenia.html`,
          `${L.feedAll.replace("{n}", data.days)} (${mine.length}) →`, false, { className: "btn2" })));
    }
    home.append(mps());
  };

  // ---- suggested MPs: a card each, all the same size: who, the topics, up to three lines
  // on their work (the weightiest of each kind), and a link to their page on these topics
  const roleRank = (fn) => (/^przewodnicz/.test(fn) ? 0 : /przewodnicz/.test(fn) ? 1 : 2);
  const mpCard = (r) => {
    const m = data.mps[r.id] || { name: `#${r.id}`, club: "" };
    const lines = [];
    const comms = r.why.filter((w) => w.k === "committee").sort((x, y) => roleRank(x.fn || "") - roleRank(y.fn || ""));
    // [icon, the line, its full text on hover]
    if (comms.length) {
      const c = comms[0], name = data.committees[c.code] || c.code;
      const more = comms.length > 1 ? ` +${comms.length - 1}` : "";
      lines.push([ICON.committee, `${name}${more}`, `${c.fn ? `${c.fn[0].toUpperCase()}${c.fn.slice(1)} · ` : ""}${name}${more}`]);
    }
    const qs = r.why.filter((w) => w.k === "questions").sort((x, y) => y.n - x.n);
    if (qs.length) {
      const line = plural(qs[0].n, L.questionsShort).replace("{n}", qs[0].n);
      lines.push([ICON.question, line, `${line} (${qs[0].to.join(", ")})`]);
    }
    const bills = r.why.filter((w) => w.k === "bills").sort((x, y) => y.n - x.n);
    if (bills.length) {
      const line = `${plural(bills[0].n, L.billsShort).replace("{n}", bills[0].n)} · ${nameOf(bills[0].topic)}`;
      lines.push([ICON.bill, line, line]);
    }
    const where = [m.club && m.club !== "niez." ? m.clubName || m.club : L.independent, m.districtNum && `${L.district} ${m.districtNum}`].filter(Boolean).join(" · ");
    const photo = el("img", { className: "mp-thumb", src: home.dataset.photo.replace("{id}", r.id), alt: "", loading: "lazy",
      width: 56, height: 70, decoding: "async" });
    photo.addEventListener("error", () => photo.remove(), { once: true });
    const page = `${ROOT}posel/${r.id}.html?tematy=${state.ids.filter((id) => r.topics.includes(id)).join(",")}#w-twoich-tematach`;
    return el("li", { className: "card mp-card" },
      el("div", { className: "mp-card-head" }, photo, el("div", {},
        el("h3", {}, link(`${ROOT}posel/${r.id}.html`, m.name)),
        el("p", { className: "muted small", textContent: where }))),
      topicTags(r.topics),
      el("ul", { className: "mp-facts" }, lines.map(([icon, text, full]) =>
        el("li", { title: full }, svg(icon, 15), el("span", { textContent: text })))),
      link(page, `${L.profile} →`, false, { className: "mp-more" }));
  };

  // the home page: one MP from each club (a different one on each visit, clubs in a new
  // order), three at a time in a row that scrolls, and a link to all of them
  const mps = () => {
    const picked = rotate(mpPools(data, state.ids));
    const body = [el("p", { className: "muted", textContent: L.mpsText })];
    if (!picked.length) {
      body.push(el("p", { textContent: L.mpsNone }));
      return section("poslowie-tematy", L.mpsTitle, body);
    }
    const track = el("ul", { className: "mp-cards mp-track", tabIndex: 0 }, picked.map(mpCard));
    track.setAttribute("aria-label", L.mpsTitle);
    const prev = el("button", { type: "button", className: "icon-btn mp-nav", ariaLabel: L.prev, title: L.prev }, svg(ICON.left, 18));
    const next = el("button", { type: "button", className: "icon-btn mp-nav", ariaLabel: L.next, title: L.next }, svg(ICON.right, 18));
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const step = (dir) => track.scrollBy({ left: dir * track.clientWidth, behavior: reduced ? "auto" : "smooth" });
    prev.addEventListener("click", () => step(-1));
    next.addEventListener("click", () => step(1));
    const ends = () => {
      prev.disabled = track.scrollLeft <= 2;
      next.disabled = track.scrollLeft + track.clientWidth >= track.scrollWidth - 2;
    };
    track.addEventListener("scroll", ends, { passive: true });
    new ResizeObserver(ends).observe(track);
    body.push(el("div", { className: "mp-carousel" }, track),
      el("div", { className: "mp-carousel-foot" }, el("span", { className: "mp-navs" }, prev, next),
        link(`${ROOT}poslowie-dla-ciebie.html`, `${L.allMps} (${Object.values(mpPools(data, state.ids)).flat().length}) →`, false, { className: "btn2" })));
    requestAnimationFrame(ends);
    return section("poslowie-tematy", L.mpsTitle, body);
  };

  // poslowie-dla-ciebie.html: every club's best three in the reader's topics, three to a row,
  // the clubs and each club's three in a new order on every visit
  const mpsAll = () => {
    const pools = mpPools(data, state.ids);
    const rows = shuffle(Object.values(pools)).flatMap((p) => shuffle(p));
    if (!rows.length) return [el("p", { textContent: L.mpsNone })];
    return [el("p", { className: "muted", textContent: L.mpsAllText }), el("ul", { className: "mp-cards mp-grid" }, rows.map(mpCard))];
  };

  const skipped = (focus) => {
    const b = el("button", { type: "button", className: "btn2", textContent: L.pick });
    b.addEventListener("click", () => showForm([]));
    const note = el("div", { className: "card interests-note skipped" }, el("p", { textContent: L.skippedText }), b);
    home.replaceChildren(note, ...placeholders());
    home.hidden = false;
    if (focus) focusSoon(note);
  };

  function show({ saved = false, focus = false } = {}) {
    if (state?.ids?.length) personal({ saved, focus });
    else if (state?.skipped) skipped(focus);
    else showForm([], false);
  }
  show();
})();
