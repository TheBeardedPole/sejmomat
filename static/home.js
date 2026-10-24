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

const INTERESTS_KEY = "sejmomat-interests";
const REMIND_DAYS = 30;

// ---- time: the API's times are Warsaw time without a zone ("2026-11-05T10:00:00")
const warsawNow = (now = new Date()) => new Intl.DateTimeFormat("sv-SE", {
  timeZone: "Europe/Warsaw", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
}).format(now).replace(" ", "T");

// "5 listopada, 10:00" from a Warsaw time, without the browser's own zone getting in the way
const formatWhen = (iso, lang = "pl", withYear = false) => {
  const [d, t] = iso.split("T");
  const [y, m, day] = d.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, day, 12));
  const opts = { timeZone: "UTC", day: "numeric", month: "long", ...(withYear ? { year: "numeric" } : {}) };
  const text = new Intl.DateTimeFormat(lang === "en" ? "en-GB" : "pl-PL", opts).format(date);
  return t ? `${text}, ${t.slice(0, 5)}` : text;
};

const daysBetween = (a, b) => Math.round((Date.parse(`${b}T12:00:00Z`) - Date.parse(`${a}T12:00:00Z`)) / 86400000);

// ---- broadcasts
const PLENARY = "posiedzenie";

// Of the API's broadcasts: those whose scheduled time has come and not passed
// (candidates for live; plenary first), and the next one to start (with the
// next plenary sitting too, when the next broadcast is something else).
const pickBroadcasts = (videos, now) => {
  const today = now.slice(0, 10);
  const byStart = [...videos].filter((v) => v.startDateTime).sort((a, b) => a.startDateTime.localeCompare(b.startDateTime));
  const current = byStart
    .filter((v) => v.startDateTime <= now && v.startDateTime.slice(0, 10) === today && (!v.endDateTime || now < v.endDateTime))
    .sort((a, b) => (b.type === PLENARY) - (a.type === PLENARY));
  const ahead = byStart.filter((v) => v.startDateTime > now);
  const next = ahead[0] || null;
  const nextPlenary = next && next.type !== PLENARY ? ahead.find((v) => v.type === PLENARY) || null : null;
  return { current, next, nextPlenary };
};

// Is there video in a stream? Its playlist names the variants; a variant's
// playlist lists segments (#EXTINF) once there is something to play.
const hasSegments = (text) => /#EXTINF/.test(text || "");
const firstVariant = (text) => (text || "").split("\n").map((l) => l.trim()).find((l) => l && !l.startsWith("#")) || null;

const streamIsOn = async (url, fetchFn = fetch, timeoutMs = 8000) => {
  const get = async (u) => {
    const ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer = ctrl && setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const r = await fetchFn(u, { cache: "no-store", signal: ctrl?.signal });
      if (!r.ok) return null;
      return { text: await r.text(), url: r.url || u };
    } finally {
      if (timer) clearTimeout(timer);
    }
  };
  try {
    const master = await get(url);
    if (!master) return false;
    if (hasSegments(master.text)) return true;
    const variant = firstVariant(master.text);
    if (!variant) return false;
    const media = await get(new URL(variant, master.url).href);
    return !!media && hasSegments(media.text);
  } catch {
    return false;
  }
};

// What the box says: "live" (confirmed), "scheduled" (its time has come but no
// video yet, or it cannot be checked from here), "next", "none" or "error".
const broadcastState = (picked, liveIndex) => {
  if (!picked) return { state: "error" };
  const { current, next, nextPlenary } = picked;
  if (liveIndex !== -1 && current[liveIndex]) {
    return { state: "live", video: current[liveIndex], others: current.filter((_, i) => i !== liveIndex) };
  }
  if (current.length) return { state: "scheduled", video: current[0], next, nextPlenary };
  if (next) return { state: "next", video: next, nextPlenary };
  return { state: "none" };
};

// ---- interests
const readInterests = (storage) => {
  try {
    const s = JSON.parse(storage.getItem(INTERESTS_KEY) || "null");
    return s && typeof s === "object" ? s : null;
  } catch {
    return null;
  }
};
const writeInterests = (storage, value) => {
  try {
    storage.setItem(INTERESTS_KEY, JSON.stringify(value));
  } catch {
    // storage unavailable: the choice lasts for this page only
  }
  return value;
};
// saving (or confirming) starts a new 30-day period; skipping keeps nothing but the skip
const saveInterests = (ids, today) => ({ ids: [...new Set(ids)], saved: today, asked: today });
const confirmInterests = (state, today) => ({ ...state, asked: today });
const skipInterests = (today) => ({ ids: [], skipped: today });
const reminderDue = (state, today) =>
  !!(state && state.ids?.length && state.asked && daysBetween(state.asked, today) >= REMIND_DAYS);

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
// over a step on the way), then the newer. This is an order for reading, not
// a judgement of what matters most.
const weight = (e) => (e.k === "vote" || IMPORTANT_STAGES.has(e.s) ? 3 : e.k === "agenda" ? 2 : 1);
const highlights = (events, today, n = 5) => {
  const scored = events.map((e) => ({ e, score: weight(e) * 10 - Math.max(0, daysBetween(e.d, today)) / 3 }))
    .sort((a, b) => b.score - a.score || b.e.d.localeCompare(a.e.d));
  const seen = new Set();
  const out = [];
  for (const { e } of scored) {
    if (seen.has(e.root)) continue;
    seen.add(e.root);
    out.push(e);
    if (out.length === n) break;
  }
  return out;
};

// ---- MPs: their scores in the chosen topics added up, reasons merged
const suggestMps = (data, ids, n = 6) => {
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
  return [...total.values()].sort((a, b) => b.score - a.score || a.id - b.id).slice(0, n);
};

if (typeof module !== "undefined") {
  module.exports = {
    warsawNow, formatWhen, daysBetween, pickBroadcasts, hasSegments, firstVariant, streamIsOn, broadcastState,
    readInterests, writeInterests, saveInterests, confirmInterests, skipInterests, reminderDue,
    eventsFor, highlights, suggestMps, INTERESTS_KEY, REMIND_DAYS,
  };
}

if (typeof document !== "undefined") (() => {
  const el = (tag, props = {}, ...children) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children.flat().filter((c) => c !== null && c !== undefined && c !== false));
    return node;
  };
  const LANG = document.documentElement.lang === "en" ? "en" : "pl";
  const link = (href, text, external = false) => el("a", {
    href, textContent: text, ...(external ? { target: "_blank", rel: "noopener" } : {}),
  });

  // ---- the broadcast box
  const box = document.getElementById("transmisja");
  if (box) {
    const L = JSON.parse(box.dataset.labels);
    const plenaryDates = (box.dataset.sittingDates || "").split(",").filter(Boolean);
    let checking = false;
    const render = (s) => {
      const parts = [];
      const v = s.video;
      const when = (x) => formatWhen(x.startDateTime, LANG);
      const official = v?.playerLink || box.dataset.itv;
      if (s.state === "live") {
        box.classList.add("is-live");
        parts.push(el("p", { className: "broadcast-head" }, el("span", { className: "live-dot", ariaHidden: "true" }),
          el("strong", { textContent: L.live })));
        parts.push(el("p", { className: "broadcast-title", lang: "pl", textContent: v.title }));
        const actions = el("p", { className: "broadcast-actions" }, link(official, `${L.watch} ↗`, true));
        if (s.others.length) {
          actions.append(" · ", link(box.dataset.itv, `${L.others} (${s.others.length}) ↗`, true));
        }
        parts.push(actions);
      } else {
        box.classList.remove("is-live");
        if (s.state === "scheduled") {
          parts.push(el("p", { className: "broadcast-head" }, el("strong", { textContent: L.scheduled })));
          parts.push(el("p", { className: "broadcast-title" }, el("span", { lang: "pl", textContent: v.title }),
            el("span", { className: "muted", textContent: ` · ${L.from} ${when(v).split(", ").pop()}` })));
          parts.push(el("p", { className: "muted broadcast-note", textContent: L.unconfirmed }));
          parts.push(el("p", { className: "broadcast-actions" }, link(official, `${L.check} ↗`, true)));
        } else if (s.state === "next") {
          parts.push(el("p", { className: "broadcast-head" }, el("strong", { textContent: L.next })));
          parts.push(el("p", { className: "broadcast-title" }, el("strong", { textContent: when(v) }), " · ",
            el("span", { lang: "pl", textContent: v.title })));
          // a plenary sitting we have the agenda of: our page; otherwise the Sejm's
          const ours = v.type === PLENARY && plenaryDates.includes(v.startDateTime.slice(0, 10));
          parts.push(el("p", { className: "broadcast-actions" },
            ours ? link(box.dataset.upcoming, `${L.details} →`) : link(official, `${L.details} ↗`, true)));
        } else {
          parts.push(el("p", { className: "broadcast-head" }, el("strong", { textContent: L.title })));
          parts.push(el("p", { className: "muted", textContent: s.state === "error" ? L.error : L.none }));
          parts.push(el("p", { className: "broadcast-actions" }, link(box.dataset.itv, `${L.check} ↗`, true)));
        }
        const np = s.nextPlenary;
        if (np) {
          parts.push(el("p", { className: "muted broadcast-note" }, `${L.nextPlenary}: `,
            el("strong", { textContent: when(np) })));
        }
      }
      box.replaceChildren(...parts);
    };

    const check = async () => {
      if (checking) return;
      checking = true;
      try {
        const now = warsawNow();
        const till = new Date(Date.parse(`${now.slice(0, 10)}T12:00:00Z`) + 60 * 86400000).toISOString().slice(0, 10);
        let picked = null;
        try {
          const r = await fetch(`${box.dataset.api}?since=${now.slice(0, 10)}&till=${till}&limit=500`);
          if (r.ok) picked = pickBroadcasts(await r.json(), now);
        } catch {
          picked = null;
        }
        let liveIndex = -1;
        if (picked) {
          for (const [i, v] of picked.current.entries()) {
            if (v.videoLink && await streamIsOn(v.videoLink)) {
              liveIndex = i;
              break;
            }
          }
        }
        render(broadcastState(picked, liveIndex));
      } finally {
        checking = false;
      }
    };
    check();
    // a broadcast that starts or ends while the page is open
    setInterval(() => document.visibilityState === "visible" && check(), 2 * 60 * 1000);
  }

  // ---- interests
  const home = document.getElementById("dla-ciebie");
  const mpBox = document.getElementById("poslowie-dla-ciebie");
  if (!home) return;
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

  const heading = (id, text, ...rest) => el("div", { className: "home-head" }, el("h2", { id, textContent: text }), ...rest);
  const editButton = () => {
    const b = el("button", { type: "button", className: "link-btn", textContent: L.edit });
    b.addEventListener("click", () => showForm(state?.ids || []));
    return b;
  };

  // the survey: first visit, "Zmień", or "Tak, chcę je zmienić"
  const showForm = (selected, focus = true) => {
    const form = el("form", { className: "card interests-form" });
    const legendId = "interests-legend";
    const fs = el("fieldset", {},
      el("legend", { id: legendId }, el("strong", { className: "interests-title", textContent: L.askTitle })),
      el("p", { className: "muted", textContent: L.askText }),
      el("div", { className: "interest-chips" }, names.map((i) => el("label", { className: "interest-chip" },
        el("input", { type: "checkbox", name: "interest", value: i.id, checked: selected.includes(i.id) }),
        el("span", { textContent: i[LANG] })))));
    const msg = el("p", { className: "form-msg", role: "status" });
    const save = el("button", { type: "submit", className: "btn-primary", textContent: L.save });
    const skip = el("button", { type: "button", className: "link-btn", textContent: state?.ids?.length ? L.cancel : L.skip });
    form.append(fs, msg, el("p", { className: "interests-actions" }, save, skip),
      el("p", { className: "muted small", textContent: L.privacy }));
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const ids = [...form.querySelectorAll("input[name=interest]:checked")].map((x) => x.value);
      if (!ids.length) {
        msg.textContent = L.pickOne;
        return;
      }
      state = writeInterests(localStorage, saveInterests(ids, today));
      show();
    });
    skip.addEventListener("click", () => {
      if (!state?.ids?.length) state = writeInterests(localStorage, skipInterests(today));
      show();
    });
    home.replaceChildren(form);
    home.hidden = false;
    if (focus) form.querySelector("input")?.focus();
  };

  const reminder = () => {
    const yes = el("button", { type: "button", className: "btn-primary", textContent: L.remindYes });
    const no = el("button", { type: "button", className: "btn-secondary", textContent: L.remindNo });
    const card = el("aside", { className: "reminder", ariaLabel: L.remindTitle },
      el("p", {}, el("strong", { textContent: L.remindTitle }), " ",
        el("span", { textContent: `${L.remindLast}: ${listOf(state.ids)}.` })),
      el("p", { className: "interests-actions" }, yes, no));
    yes.addEventListener("click", () => showForm(state.ids));
    no.addEventListener("click", () => {
      state = writeInterests(localStorage, confirmInterests(state, today));
      card.remove();
    });
    return card;
  };

  // one event: title, date, kind, status, topics, why it is here, link
  const eventItem = (e, compact = false) => {
    const why = Object.entries(e.mine).map(([id, reasons]) => {
      const how = reasons.map(([k, v]) => (k === "tag" ? v : `${L.committee} ${data.committees[v] || v}`));
      return `${nameOf(id)} (${how.join(", ")})`;
    });
    const status = LANG === "en" ? e.se : e.s;
    const statusEl = status ? el("span", { className: `badge ${e.o === "adopted" ? "adopted" : e.o === "rejected" ? "rejected" : "neutral"}`, textContent: status }) : null;
    const tags = [...new Set(Object.values(e.mine).flat().filter(([k]) => k === "tag").map(([, v]) => v))];
    return el("li", { className: "event" },
      el("p", { className: "event-meta" },
        el("span", { className: "event-kind", textContent: L.kinds[e.k] }), " · ",
        el("time", { dateTime: e.d, textContent: formatWhen(e.d, LANG, true) }),
        statusEl ? [" ", statusEl] : null),
      el("p", { className: "event-title", lang: "pl" }, e.url ? link(href(e.url), e.t, /^https?:/.test(e.url)) : e.t),
      !compact && tags.length ? el("p", { className: "tags" }, tags.map((t) => el("span", { className: "tag", lang: "pl", textContent: t }))) : null,
      el("p", { className: "event-why muted", textContent: `${L.because}: ${why.join("; ")}` }));
  };

  const personal = async () => {
    const parts = [];
    if (reminderDue(state, today)) parts.push(reminder());
    const top = el("section", { className: "home-section" },
      heading("wazne-dla-ciebie", L.forYou, editButton()),
      el("p", { className: "muted", textContent: `${L.forYouText} ${L.following}: ${listOf(state.ids)}.` }));
    const feed = el("section", { className: "home-section" },
      heading("twoje-tematy", L.feedTitle));
    top.setAttribute("aria-labelledby", "wazne-dla-ciebie");
    feed.setAttribute("aria-labelledby", "twoje-tematy");
    parts.push(top, feed);
    home.replaceChildren(...parts);
    home.hidden = false;
    try {
      await load();
    } catch {
      const retry = el("button", { type: "button", className: "link-btn", textContent: L.retry });
      retry.addEventListener("click", personal);
      top.append(el("p", { className: "muted", role: "alert" }, `${L.failed} `, retry));
      feed.remove();
      return;
    }
    const mine = eventsFor(data.events, state.ids);
    if (!mine.length) {
      top.append(el("p", { textContent: L.empty }),
        el("p", {}, editButton(), " · ", link("#w-sejmie", `${L.general} ↓`)));
      feed.remove();
    } else {
      top.append(el("ul", { className: "events" }, highlights(mine, today).map((e) => eventItem(e))));
      const list = el("ul", { className: "events compact" });
      const step = 10;
      let shown = 0;
      const more = el("button", { type: "button", className: "link-btn", textContent: L.more });
      const page = () => {
        list.append(...mine.slice(shown, shown + step).map((e) => eventItem(e, true)));
        shown += step;
        if (shown >= mine.length) more.remove();
      };
      more.addEventListener("click", page);
      feed.append(el("p", { className: "muted", textContent: L.feedText.replace("{n}", data.days) }), list, more);
      page();
    }
    mps();
  };

  const mps = () => {
    if (!mpBox || !data) return;
    const rows = suggestMps(data, state.ids);
    const body = [heading("poslowie-tematy", L.mpsTitle), el("p", { className: "muted", textContent: L.mpsText })];
    if (!rows.length) {
      body.push(el("p", { textContent: L.mpsNone }));
    } else {
      body.push(el("ul", { className: "mp-cards" }, rows.map((r) => {
        const m = data.mps[r.id] || { name: `#${r.id}`, club: "" };
        const order = { committee: 0, bills: 1, questions: 2 };
        const why = [...r.why].sort((a, b) => order[a.k] - order[b.k]);
        const reasons = why.slice(0, 4).map((w) => {
          if (w.k === "committee") {
            const role = w.fn || L.member;
            return el("li", {}, `${role[0].toUpperCase()}${role.slice(1)} — `,
              link(`${ROOT}komisja/${w.code}.html`, data.committees[w.code] || w.code));
          }
          if (w.k === "questions") {
            return el("li", {}, link(`${ROOT}posel/${r.id}.html#interpelacje`,
              L.questions.replace("{n}", w.n).replace("{recent}", w.recent)), ` (${w.to.join(", ")})`);
          }
          return el("li", {}, `${L.bills.replace("{n}", w.n).replace("{topic}", nameOf(w.topic))}: `,
            link(`${ROOT}ustawa/${w.root}.html`, data.bills[w.root] || w.root));
        });
        return el("li", { className: "card mp-card" },
          el("p", { className: "mp-name" }, link(`${ROOT}posel/${r.id}.html`, m.name), el("span", { className: "muted", textContent: ` · ${m.club}` })),
          el("p", { className: "muted small", textContent: `${L.topics}: ${listOf(r.topics)}` }),
          el("p", { className: "small", textContent: L.whyMp }),
          el("ul", { className: "mp-why" }, reasons,
            why.length > 4 ? el("li", { className: "muted", textContent: L.moreReasons.replace("{n}", why.length - 4) }) : null),
          el("p", {}, link(`${ROOT}posel/${r.id}.html`, `${L.profile} →`)));
      })));
    }
    mpBox.replaceChildren(...body);
    mpBox.hidden = false;
  };

  const invite = () => {
    // skipped: a short line instead of the survey; the general news is below as always
    const b = el("button", { type: "button", className: "link-btn", textContent: L.pick });
    b.addEventListener("click", () => showForm([]));
    home.replaceChildren(el("p", { className: "card interests-invite" }, `${L.inviteText} `, b));
    home.hidden = false;
    if (mpBox) {
      const b2 = el("button", { type: "button", className: "link-btn", textContent: L.pick });
      b2.addEventListener("click", () => { showForm([]); home.scrollIntoView({ block: "start" }); });
      mpBox.replaceChildren(heading("poslowie-tematy", L.mpsTitle), el("p", { className: "muted" }, `${L.mpsStart} `, b2));
      mpBox.hidden = false;
    }
  };

  function show() {
    if (state?.ids?.length) personal();
    else if (state?.skipped) invite();
    else {
      showForm([], false);
      if (mpBox) mpBox.hidden = true;
    }
  }
  show();
})();
