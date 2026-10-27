// The broadcast schedule (templates/schedule.html, transmisje.html): every
// broadcast the Sejm's API lists from today on — sittings, committees and
// subcommittees, parliamentary groups, conferences — by day, with the room,
// the agenda and links to our committee and print pages. Read in the browser,
// as the schedule changes every day and the site is not rebuilt every day.
// "Na żywo" only when the stream has video in it (streamIsOn, static/home.js,
// which this page loads first for its shared rules: dates, the stream check).

(() => {
  const box = document.getElementById("harmonogram");
  if (!box) return;
  const L = JSON.parse(box.dataset.labels);
  const ROOT = box.dataset.root || "";
  const LANG = document.documentElement.lang === "en" ? "en" : "pl";
  const committees = new Set(JSON.parse(box.dataset.committees || "[]"));
  const prints = JSON.parse(box.dataset.prints || "[]");   // [[first, last], ...]
  const sittingDays = (box.dataset.upcoming || "").split(",").filter(Boolean);
  const byInterest = JSON.parse(box.dataset.interests || "{}");
  const FILTER_KEY = "sejmomat-schedule-filter";

  // the player, here on the page (the Sejm's own cannot be framed): hls.js, loaded when first
  // needed, starting at the lowest quality and never above the player's size; Safari plays
  // HLS itself. One at a time; it stays through the page's refreshes.
  let playing = null;   // {unid, wrap, hls, video}
  const loadHls = () => (window.Hls ? Promise.resolve() : new Promise((resolve, reject) =>
    document.head.append(Object.assign(document.createElement("script"), { src: box.dataset.hls, onload: resolve, onerror: reject }))));
  const stop = () => {
    if (!playing) return;
    playing.hls?.destroy();
    playing.video.pause();
    playing.wrap.remove();
    playing = null;
  };
  const play = async (v) => {
    const video = Object.assign(document.createElement("video"), { controls: true, playsInline: true, autoplay: true, className: "sched-video" });
    const wrap = Object.assign(document.createElement("div"), { className: "sched-player-box" });
    wrap.append(video);
    const failed = () => {
      const p = Object.assign(document.createElement("p"), { className: "muted small", textContent: `${L.playFailed} ` });
      if (v.playerLink) p.append(external(v.playerLink, L.player));
      wrap.replaceChildren(p);
    };
    let hls = null;
    try {
      if (!window.MediaSource && video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = v.videoLink;
      } else {
        await loadHls();
        if (!window.Hls?.isSupported()) throw new Error("hls");
        hls = new window.Hls({ startLevel: 0, capLevelToPlayerSize: true });
        hls.on(window.Hls.Events.ERROR, (_, d) => d.fatal && failed());
        hls.loadSource(v.videoLink);
        hls.attachMedia(video);
      }
      video.play?.().catch(() => {});
    } catch {
      failed();
    }
    return { unid: v.unid, wrap, hls, video };
  };

  const el = (tag, props = {}, ...children) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
    return node;
  };
  const external = (href, text, cls = "") => el("a", { href, target: "_blank", rel: "noopener", className: cls,
    ariaLabel: `${text} (${L.newTab})` }, `${text} ↗`);
  const hasPrint = (n) => prints.some(([a, b]) => a <= n && n <= b);
  const codesOf = (v) => (v.committee || "").split(/,\s*/).filter(Boolean);
  const group = (v) => (v.type === "posiedzenie" ? "plenary" : v.type === "komisja" || v.type === "podkomisja" ? "committees" : "other");

  // the reader's topics (home page), as committees
  const mineCommittees = (() => {
    const state = typeof readInterests === "function" ? readInterests(localStorage) : null;
    const ids = state?.ids || [];
    return new Set(ids.flatMap((id) => byInterest[id] || []));
  })();
  const filters = ["all", "plenary", "committees", "other", ...(mineCommittees.size ? ["mine"] : [])];
  let filter = "all";
  try {
    const saved = localStorage.getItem(FILTER_KEY);
    if (filters.includes(saved)) filter = saved;
  } catch {
    // no storage: the default
  }
  const shows = (v) => filter === "all" || (filter === "mine" ? codesOf(v).some((c) => mineCommittees.has(c)) : group(v) === filter);

  // text with "druk nr 3233" (or "druki nr 12 i 13") linked to our print pages
  const withPrints = (text) => {
    const out = [];
    let at = 0;
    for (const m of text.matchAll(/(druk\w*\s+nr\s+)(\d+(?:(?:\s*,\s*|\s+i\s+)\d+)*)/gi)) {
      out.push(text.slice(at, m.index), m[1]);
      let last = 0;
      for (const n of m[2].matchAll(/\d+/g)) {
        out.push(m[2].slice(last, n.index));
        out.push(hasPrint(+n[0]) ? el("a", { href: `${ROOT}druk/${n[0]}.html`, textContent: n[0] }) : n[0]);
        last = n.index + n[0].length;
      }
      out.push(m[2].slice(last));
      at = m.index + m[0].length;
    }
    out.push(text.slice(at));
    return out.filter((x) => x !== "");
  };
  const lines = (text) => (text || "").split(/<br\s*\/?>|\r?\n/i).map((x) => x.replace(/<[^>]*>/g, "").trim()).filter(Boolean);

  // a title line: "Komisja Infrastruktury (INF)" links to our committee page
  const titleLine = (line, v) => {
    const m = line.match(/^(.*?)\s*\(([A-Z]{2,4})\)\s*$/);
    if (m && committees.has(m[2])) return el("a", { href: `${ROOT}komisja/${m[2]}.html`, textContent: line.trim() });
    if (v.type === "posiedzenie" && sittingDays.includes(v.startDateTime.slice(0, 10))) {
      return el("a", { href: `${ROOT}nadchodzace-posiedzenie.html`, textContent: line.trim() });
    }
    return line.trim();
  };

  const hhmm = (iso) => iso.slice(11, 16);
  const span = (v) => {
    if (!v.endDateTime) return hhmm(v.startDateTime);
    // a sitting into the night ends "00:30" (the next morning, as the Sejm's own schedule has it); a date only past that
    const days = daysBetween(v.startDateTime.slice(0, 10), v.endDateTime.slice(0, 10));
    return `${hhmm(v.startDateTime)}–${days <= 1 ? hhmm(v.endDateTime) : formatWhen(v.endDateTime, LANG)}`;
  };

  const row = (v, now, live) => {
    const on = v.startDateTime <= now && (!v.endDateTime || now < v.endDateTime);
    const over = v.endDateTime && v.endDateTime <= now;
    const isLive = live.has(v.unid);
    const head = el("p", { className: "sched-head" },
      isLive ? el("span", { className: "live-badge" }, el("span", { className: "live-dot", ariaHidden: "true" }), L.live) : null,
      el("span", { className: `badge sched-type t-${group(v)}`, textContent: L.types[v.type] || v.type }),
      on && !isLive ? el("span", { className: "muted small", textContent: L.scheduledNow }) : null);
    const title = el("h3", { className: "sched-title", lang: "pl" },
      lines(v.title).map((l, i) => [i ? el("br") : null, titleLine(l, v)]));
    const desc = lines(v.description);
    const about = desc.length
      ? desc.length > 2
        ? el("details", { className: "sched-agenda" }, el("summary", { lang: "pl" }, withPrints(desc[0])),
          el("ul", { lang: "pl" }, desc.slice(1).map((d) => el("li", {}, withPrints(d)))))
        : el("p", { className: "sched-desc", lang: "pl" }, desc.map((d, i) => [i ? el("br") : null, withPrints(d)]))
      : null;
    const room = v.room ? el("p", { className: "sched-room muted small", lang: "pl", textContent: `${L.room}: ${v.room}` }) : null;
    const player = v.playerLink || null;
    const mine = playing?.unid === v.unid;
    // live or recorded: played here; still to come: the Sejm's player, which waits for it
    let here = null;
    if (v.videoLink && (isLive || over)) {
      here = el("button", { type: "button", className: isLive ? "btn" : "btn2",
        textContent: mine ? L.closePlayer : isLive ? L.watchHere : L.playRecording });
      here.setAttribute("aria-expanded", String(mine));
      here.addEventListener("click", async () => {
        const again = playing?.unid === v.unid;
        stop();
        if (!again) playing = await play(v);
        render();
        box.querySelector(`[data-unid="${v.unid}"] .sched-act button`)?.focus();
      });
    }
    const act = [here, player ? external(player, L.player, "sched-player small") : null];
    const li = el("li", { className: `sched-row${isLive ? " is-live" : ""}${over ? " is-over" : ""}${mine ? " is-playing" : ""}` },
      el("p", { className: "sched-time" }, el("time", { dateTime: v.startDateTime, textContent: span(v) })),
      el("div", { className: "sched-main" }, head, title, about, room),
      el("div", { className: "sched-act" }, act));
    li.dataset.unid = v.unid;
    if (mine) li.append(playing.wrap);
    return li;
  };

  let data = null;
  let ours = null;      // Sejmomat live on YouTube (static/yt.js): {id, title, box}
  let live = new Set();
  let checkedAt = null;

  const render = () => {
    const now = warsawNow();
    const today = now.slice(0, 10);
    const tomorrow = new Date(Date.parse(`${today}T12:00:00Z`) + 86400000).toISOString().slice(0, 10);
    const parts = [];
    // filters: one kind at a time
    const bar = el("div", { className: "sched-filters", role: "group", ariaLabel: L.filterLegend },
      filters.map((f) => {
        const b = el("button", { type: "button", className: "toggle-chip", textContent: L.filters[f] });
        b.setAttribute("aria-pressed", String(f === filter));
        b.addEventListener("click", () => {
          filter = f;
          try {
            localStorage.setItem(FILTER_KEY, f);
          } catch {
            // not remembered
          }
          render();
          box.querySelector(`.sched-filters button[aria-pressed="true"]`)?.focus();
        });
        return b;
      }));
    parts.push(bar);
    const shown = data.filter(shows);
    // on now first, then the days ahead (today's finished ones stay, greyed, with their recording)
    const current = shown.filter((v) => v.startDateTime <= now && (!v.endDateTime || now < v.endDateTime) && v.startDateTime.slice(0, 10) === today);
    // Sejmomat's own coverage, first and with its player open, whatever the filter
    const oursRow = ours ? el("li", { className: "sched-row is-live is-playing sched-ours" },
      el("p", { className: "sched-time", textContent: L.now }),
      el("div", { className: "sched-main" },
        el("p", { className: "sched-head" },
          el("span", { className: "live-badge" }, el("span", { className: "live-dot", ariaHidden: "true" }), L.live),
          el("span", { className: "badge sched-type t-plenary", textContent: L.oursType })),
        el("h3", { className: "sched-title", lang: "pl", textContent: ours.title || L.ours }),
        el("p", { className: "sched-desc muted", textContent: L.oursSub })),
      el("div", { className: "sched-act" }, external(window.SejmomatYT.watchUrl(ours), "YouTube", "sched-player small")),
      ours.box) : null;
    if (current.length || oursRow) {
      parts.push(el("section", { className: "sched-day sched-now" }, el("h2", { textContent: L.now }),
        el("ul", { className: "sched-list" }, oursRow, current.sort((a, b) => live.has(b.unid) - live.has(a.unid)).map((v) => row(v, now, live)))));
    }
    const days = new Map();
    for (const v of shown) {
      if (current.includes(v)) continue;
      const d = v.startDateTime.slice(0, 10);
      if (!days.has(d)) days.set(d, []);
      days.get(d).push(v);
    }
    if (!shown.length) {
      parts.push(el("p", { className: "placeholder-text muted", textContent: data.length ? L.noneFiltered : L.none }));
    }
    for (const [d, vs] of days) {
      const rel = d === today ? L.today : d === tomorrow ? L.tomorrow : null;
      const n = vs.length;
      const count = n === 1 ? L.count1 : plural(n, ["", L.countFew, L.countMany]).replace("{n}", n);
      parts.push(el("section", { className: "sched-day" },
        el("h2", {}, rel ? el("span", { className: "sched-rel", textContent: `${rel} · ` }) : null, formatDay(d, LANG),
          el("span", { className: "muted sched-count", textContent: ` · ${count}` })),
        el("ul", { className: "sched-list" }, vs.map((v) => row(v, now, live)))));
    }
    parts.push(el("p", { className: "muted small sched-src", textContent: L.src.replace("{when}", formatWhen(checkedAt, LANG)) }));
    box.replaceChildren(...parts);
  };

  const fail = () => {
    const retry = el("button", { type: "button", className: "btn2", textContent: L.retry });
    retry.addEventListener("click", load);
    box.replaceChildren(el("div", { className: "card callout-warn", role: "alert" }, el("p", { textContent: L.error }), retry));
  };

  async function load() {
    const now = warsawNow();
    const today = now.slice(0, 10);
    const till = new Date(Date.parse(`${today}T12:00:00Z`) + Number(box.dataset.days || 21) * 86400000).toISOString().slice(0, 10);
    try {
      const r = await fetch(`${box.dataset.api}?since=${today}&till=${till}&limit=500`, { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      data = (await r.json()).filter((v) => v.startDateTime && v.startDateTime.slice(0, 10) >= today)
        .sort((a, b) => a.startDateTime.localeCompare(b.startDateTime) || a.title.localeCompare(b.title));
    } catch {
      if (!data) fail();
      return;
    }
    checkedAt = now;
    const yt = await window.SejmomatYT?.check(box.dataset.yt, true);
    if (yt?.id !== ours?.id) {
      ours = yt ? { ...yt, box: window.SejmomatYT.player(yt) } : null;
      ours?.box.classList.add("sched-player-box");
    }
    render();
    // what should be on air: is it? (video in its stream)
    const due = data.filter((v) => v.videoLink && v.startDateTime <= now && (!v.endDateTime || now < v.endDateTime));
    const on = await Promise.all(due.map((v) => streamIsOn(v.videoLink)));
    live = new Set(due.filter((_, i) => on[i]).map((v) => v.unid));
    if (live.size) render();
  }
  load();
  setInterval(() => document.visibilityState === "visible" && load(), 2 * 60 * 1000);
})();
