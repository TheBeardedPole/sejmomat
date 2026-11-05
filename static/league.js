// Sejmowa liga (templates/league.html, liga.html): the page of the fantasy game. The game
// data comes with the site (api/v1/fantasy/game.json, points/<kolejka>.json, made by
// sejmomat/fantasy.py); accounts, squads and the leaderboard from the server
// (server/fantasy.php, /srv/fantasy.php). Rules are checked here for the reader's
// convenience and again on the server, which has the last word.
(() => {
  const root = document.getElementById("liga");
  if (!root) return;
  const L = JSON.parse(root.dataset.labels);
  const API = root.dataset.api;
  const PHOTO = root.dataset.photo;
  const SITE = root.dataset.siteRoot;

  const el = (tag, props = {}, ...children) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
    return node;
  };
  const fmt = (tenths) => (tenths / 10).toFixed(1).replace(".", L.decimal);
  const mln = (tenths) => `${fmt(tenths)} ${L.mln}`;
  const api = async (action, body) => {
    const r = await fetch(`${API}?a=${action}`, body === undefined ? { credentials: "same-origin" } : {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const json = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(json.error || L.failed);
    return json;
  };

  let game = null;     // game.json
  let me = null;       // ?a=me
  let draft = null;    // the squad being edited: {slots: [{mp, pos}], captain}
  let flash = "";      // a word after saving, shown once the squad is drawn again
  const POS = () => game.positions;
  const price = (mp, pos) => Math.round((game.prices[mp]?.[pos] ?? NaN) * 10);
  const formOf = (mp, pos) => game.form?.[mp]?.[pos];
  const nameOf = (mp) => game.mps[mp]?.[0] || `#${mp}`;
  const clubOf = (mp) => game.mps[mp]?.[1] || "niez.";
  const clubName = (c) => (c === "niez." ? L.independent : (L.clubs[c] || c));

  // the squad's slots in a fixed order: each position's places, as many as the rules ask
  const layout = () => POS().flatMap((p, i) => Array.from({ length: game.squad[p] }, () => i));

  // money left if the draft were saved: places kept keep their selling price, the rest cost today's price
  const bankAfter = () => {
    const saved = me?.squad;
    let bank = saved ? saved.bank : Math.round(game.budget * 10);
    const keep = new Map((saved?.slots || []).map((s, i) => [`${s.mp}:${s.pos}`, saved.sell[i]]));
    for (const s of draft.slots) {
      if (!s) continue;
      const key = `${s.mp}:${s.pos}`;
      if (keep.has(key)) keep.delete(key);
      else bank -= price(s.mp, s.pos);
    }
    for (const v of keep.values()) bank += v;
    return bank;
  };
  // places changed since the squad at the last lock (as the server counts them)
  const transfersInDraft = () => {
    if (me.transfers.first) return 0;
    const base = new Set(me.transfers.base);
    return draft.slots.filter((s) => s && !base.has(`${s.mp}:${s.pos}`)).length;
  };
  const clubCount = () => {
    const n = {};
    for (const s of draft.slots) if (s) n[clubOf(s.mp)] = (n[clubOf(s.mp)] || 0) + 1;
    return n;
  };

  // ---- the parts of the page
  const status = el("section", { className: "liga-status" });
  const main = el("div", { className: "liga-main" });
  const board = el("section", { className: "liga-board", ariaLabelledby: "liga-board-h" });
  root.replaceChildren(status, main, board);

  const showStatus = () => {
    const k = game.kolejka;
    const live = game.live;
    const parts = [];
    if (live) {
      parts.push(el("p", { className: "liga-state live" }, el("span", { className: "live-dot", ariaHidden: "true" }),
        L.live.replace("{n}", live.number || "")));
      parts.push(el("p", { className: "muted small", textContent: L.liveNote }));
    } else if (k) {
      const lock = new Date(k.lock);
      const left = lock - Date.now();
      const days = Math.floor(left / 86400000), hours = Math.floor((left % 86400000) / 3600000);
      parts.push(el("p", { className: "liga-state" }, el("strong", { textContent: k.number ? L.kolejkaN.replace("{n}", k.number) : L.kolejkaNext }),
        ` · ${L.dates}: ${k.dates.map((d) => d.slice(8, 10) + "." + d.slice(5, 7)).join(", ")}`));
      parts.push(el("p", { className: "liga-lock" }, L.locks, " ",
        el("time", { dateTime: k.lock, textContent: L.lockAt.replace("{d}", new Date(lock - 60000).toLocaleDateString(L.locale, { day: "numeric", month: "long" })) }),
        left > 0 ? ` (${L.inTime.replace("{d}", days).replace("{h}", hours)})` : ""));
    } else {
      parts.push(el("p", { className: "liga-state", textContent: L.off }));
    }
    status.replaceChildren(...parts);
  };

  const loginBox = () => {
    if (!me.game.configured) return el("div", { className: "card liga-login" }, el("p", { textContent: L.notReady }));
    return el("div", { className: "card liga-login" },
      el("h2", { textContent: L.joinTitle }),
      el("p", { textContent: L.joinText }),
      el("p", {}, el("a", { className: "btn liga-google", href: `${API}?a=login` }, googleIcon(), L.login)),
      el("p", { className: "muted small", textContent: L.loginPrivacy }));
  };
  const googleIcon = () => {
    const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("aria-hidden", "true");
    s.innerHTML = '<path fill="#fff" d="M21.6 12.2c0-.7-.1-1.4-.2-2H12v3.8h5.4a4.6 4.6 0 0 1-2 3v2.5h3.2c1.9-1.7 3-4.3 3-7.3z"/><path fill="#fff" opacity=".85" d="M12 22c2.7 0 5-.9 6.6-2.4l-3.2-2.5c-.9.6-2 1-3.4 1-2.6 0-4.8-1.8-5.6-4.1H3.1v2.6A10 10 0 0 0 12 22z"/><path fill="#fff" opacity=".7" d="M6.4 14a6 6 0 0 1 0-3.9V7.5H3.1a10 10 0 0 0 0 9z"/><path fill="#fff" opacity=".55" d="M12 6c1.5 0 2.8.5 3.8 1.5l2.9-2.9A10 10 0 0 0 3.1 7.5L6.4 10C7.2 7.7 9.4 6 12 6z"/>';
    return s;
  };

  const nickBox = () => {
    const input = el("input", { id: "liga-nick", type: "text", maxLength: 20, autocomplete: "nickname", required: true });
    const msg = el("p", { className: "liga-msg", role: "alert" });
    const form = el("form", { className: "card liga-nick" }, el("h2", { textContent: L.nickTitle }),
      el("p", { textContent: L.nickText }), el("label", { htmlFor: "liga-nick", textContent: L.nick }), input,
      el("p", {}, el("button", { type: "submit", className: "btn", textContent: L.nickSave })), msg);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("nick", { nick: input.value });
        await refresh();
      } catch (err) {
        msg.textContent = err.message;
      }
    });
    return form;
  };

  // ---- the squad
  const slotCard = (i, posIndex, open) => {
    const s = draft.slots[i];
    const pos = POS()[posIndex];
    if (!s) {
      const add = el("button", { type: "button", className: "liga-slot empty", disabled: !open },
        el("span", { className: "liga-pos", textContent: L.posNames[pos] }), el("span", { className: "liga-add", textContent: `+ ${L.pick}` }));
      add.addEventListener("click", () => picker(i, posIndex));
      return add;
    }
    const captain = draft.captain === i;
    const photo = el("img", { className: "liga-photo", src: PHOTO.replace("{id}", s.mp), alt: "", loading: "lazy", width: 40, height: 50 });
    photo.addEventListener("error", () => photo.remove(), { once: true });
    const cap = el("button", { type: "button", className: `liga-cap${captain ? " on" : ""}`, textContent: "C", disabled: !open,
      title: captain ? L.isCaptain : L.makeCaptain, ariaLabel: captain ? L.isCaptain : L.makeCaptain });
    cap.setAttribute("aria-pressed", String(captain));
    cap.addEventListener("click", () => { draft.captain = i; drawSquad(); });
    const change = el("button", { type: "button", className: "lnk", textContent: L.change, disabled: !open });
    change.addEventListener("click", () => picker(i, posIndex));
    const f = formOf(s.mp, posIndex);
    return el("div", { className: `liga-slot${captain ? " captain" : ""}` },
      el("span", { className: "liga-pos", textContent: L.posNames[pos] }),
      el("div", { className: "liga-who" }, photo, el("div", {},
        el("a", { href: `${SITE}posel/${s.mp}.html`, textContent: nameOf(s.mp) }),
        el("span", { className: "muted small", textContent: `${clubName(clubOf(s.mp))} · ${mln(price(s.mp, posIndex))}${f !== undefined ? ` · ${L.form} ${String(f).replace(".", L.decimal)}` : ""}` }))),
      el("div", { className: "liga-slot-acts" }, cap, change));
  };

  // ---- the squad in the plenary hall, as a football game shows a team on the pitch: the
  // Mówcy at the rostrum, Lojaliści and Klikacze in the middle benches, Buntownicy on the
  // back benches, Zwycięzca and Opozycjonista at the two ends of the back row. Seats are by
  // position, never by club. [radius (0 rostrum, 1 back row), angle (180 left, 0 right)]
  const SEATS = { "Mówca": [[0.28, 135], [0.28, 45]], "Lojalista": [[0.62, 150], [0.62, 115]], "Klikacz": [[0.62, 65], [0.62, 30]],
    "Buntownik": [[1, 122], [1, 58]], "Zwycięzca": [[1, 166]], "Opozycjonista": [[1, 14]] };
  const CX = 50, CY = 92, RX = 44, RY = 80;   // % of the hall's width and height
  const VIEW_KEY = "sejmomat-liga-view";
  let view = (() => {
    try { return localStorage.getItem(VIEW_KEY) || (matchMedia("(max-width: 700px)").matches ? "list" : "hall"); } catch { return "hall"; }
  })();
  const surname = (name) => name.split(" ").slice(-1)[0];
  // a seat of the hall: the squad being made (src = draft), or another's played squad, read only,
  // its MPs' points (pts) in place of their price
  const seat = (i, posIndex, open, src = draft, pts = null) => {
    const s = src.slots[i];
    const pos = POS()[posIndex];
    const captain = s && src.captain === i;
    const node = el("div", { className: `liga-seat${s ? "" : " empty"}${captain ? " captain" : ""}` });
    const label = el("span", { className: "liga-seat-pos", textContent: L.posNames[pos] });
    if (!s) {
      const add = el("button", { type: "button", className: "liga-seat-main", disabled: !open, title: `${L.pick}: ${L.posNames[pos]}` },
        el("span", { className: "liga-seat-plus", ariaHidden: "true", textContent: "+" }), label);
      add.addEventListener("click", () => picker(i, posIndex));
      node.append(add);
      return node;
    }
    const photo = el("img", { className: "liga-seat-photo", src: PHOTO.replace("{id}", s.mp), alt: "", loading: "lazy", width: 44, height: 44 });
    photo.addEventListener("error", () => photo.replaceWith(el("span", { className: "liga-seat-photo none", ariaHidden: "true" })), { once: true });
    if (pts) {   // read only: name, club, the points they made (doubled for the captain)
      node.append(el("div", { className: "liga-seat-main", title: `${nameOf(s.mp)} · ${clubName(clubOf(s.mp))}` },
        photo, el("strong", { textContent: surname(nameOf(s.mp)) }),
        el("span", { className: "liga-seat-meta", textContent: clubName(clubOf(s.mp)) }),
        el("span", { className: "liga-seat-pts", textContent: `${pts[i]} ${L.pts}` }), label));
      if (captain) node.append(el("span", { className: "liga-seat-cap on", textContent: "C", title: L.isCaptain, ariaLabel: L.isCaptain }));
      return node;
    }
    const main = el("button", { type: "button", className: "liga-seat-main", disabled: !open, title: `${nameOf(s.mp)} · ${clubName(clubOf(s.mp))} · ${L.change}` },
      photo, el("strong", { textContent: surname(nameOf(s.mp)) }),
      el("span", { className: "liga-seat-meta", textContent: `${clubName(clubOf(s.mp))} · ${fmt(price(s.mp, posIndex))}` }), label);
    main.addEventListener("click", () => picker(i, posIndex));
    const cap = el("button", { type: "button", className: `liga-seat-cap${captain ? " on" : ""}`, textContent: "C", disabled: !open,
      title: captain ? L.isCaptain : L.makeCaptain, ariaLabel: `${captain ? L.isCaptain : L.makeCaptain}: ${nameOf(s.mp)}` });
    cap.setAttribute("aria-pressed", String(captain));
    cap.addEventListener("click", () => { draft.captain = i; drawSquad(); });
    node.append(main, cap);
    return node;
  };
  const hall = (open, src = draft, pts = null) => {
    const lay = src === draft ? layout() : src.slots.map((x) => x.pos);
    const used = {};
    const seats = lay.map((pi, i) => {
      const pos = POS()[pi];
      const k = used[pos] = (used[pos] ?? -1) + 1;
      const [r, a] = (SEATS[pos] || [])[k] || [0.92, 90];
      const node = seat(i, pi, open, src, pts);
      node.style.left = `${CX + Math.cos((a * Math.PI) / 180) * r * RX}%`;
      node.style.top = `${CY - Math.sin((a * Math.PI) / 180) * r * RY}%`;
      return node;
    });
    // the benches: rows of seats around the rostrum, drawn once (no data in them)
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 160 90");
    svg.setAttribute("aria-hidden", "true");
    svg.classList.add("liga-benches");
    let marks = "";
    for (const r of [0.2, 0.32, 0.44, 0.56, 0.68, 0.8, 0.92, 1.04, 1.14]) {
      const n = Math.round(14 + r * 46);
      for (let j = 0; j <= n; j++) {
        const a = Math.PI * (0.02 + 0.96 * (j / n));
        const x = 80 + Math.cos(a) * r * 70.4, y = 82.8 - Math.sin(a) * r * 72;
        marks += `<rect x="${(x - 0.9).toFixed(2)}" y="${(y - 0.7).toFixed(2)}" width="1.8" height="1.4" rx="0.4"/>`;
      }
    }
    svg.innerHTML = `<g class="seat-dots">${marks}</g><rect class="rostrum" x="72" y="82" width="16" height="6" rx="1.2"/>`;
    return el("div", { className: "liga-hall-wrap" }, el("div", { className: "liga-hall", role: "group", ariaLabel: L.hall },
      svg, el("span", { className: "liga-rostrum-label", textContent: L.rostrum }), seats));
  };

  const squadBox = el("section", { className: "liga-squad", ariaLabelledby: "liga-squad-h" });
  const drawSquad = () => {
    const open = !!me.game.open;
    const lay = layout();
    const groups = view === "hall" ? [hall(open)] : POS().map((pos, pi) => el("div", { className: "liga-group" },
      el("h3", {}, L.posNames[pos], el("span", { className: "muted small", textContent: ` · ${L.posRules[pos]}` })),
      el("div", { className: "liga-slots" }, lay.map((p, i) => (p === pi ? slotCard(i, pi, open) : null)))));
    const switcher = el("div", { className: "liga-view", role: "group", ariaLabel: L.viewLabel }, [["hall", L.viewHall], ["list", L.viewList]].map(([v, t]) => {
      const b = el("button", { type: "button", className: "liga-view-btn", textContent: t });
      b.setAttribute("aria-pressed", String(view === v));
      b.addEventListener("click", () => {
        view = v;
        try { localStorage.setItem(VIEW_KEY, v); } catch { /* the choice lasts for this page */ }
        drawSquad();
      });
      return b;
    }));
    const bank = bankAfter();
    const full = draft.slots.every(Boolean);
    const made = transfersInDraft();
    const free = me.transfers.first ? Infinity : me.transfers.free;
    const hit = Math.max(0, made - free) * game.transfers.hit;
    const clubs = clubCount();
    const over = Object.entries(clubs).filter(([c, n]) => c !== "niez." && n > game.clubCap).map(([c]) => clubName(c));
    const changed = JSON.stringify(draft) !== JSON.stringify(saved());
    const save = el("button", { type: "button", className: "btn", textContent: L.save,
      disabled: !open || !full || bank < 0 || over.length > 0 || draft.captain === null || !changed });
    const msg = el("p", { className: "liga-msg", role: "status", textContent: flash });
    flash = "";
    save.addEventListener("click", async () => {
      save.disabled = true;
      try {
        await api("squad", { slots: draft.slots.map((s) => ({ mp: s.mp, pos: POS()[s.pos] })), captain: draft.captain });
        flash = L.saved;
        await refresh();
      } catch (err) {
        msg.textContent = err.message;
        save.disabled = false;
      }
    });
    const reset = el("button", { type: "button", className: "lnk", textContent: L.undo, hidden: !changed });
    reset.addEventListener("click", () => { draft = saved(); drawSquad(); });
    const facts = el("div", { className: "liga-facts" },
      el("p", {}, el("span", { className: "muted", textContent: `${L.bank}: ` }), el("strong", { className: bank < 0 ? "v-N" : "", textContent: mln(bank) })),
      el("p", {}, el("span", { className: "muted", textContent: `${L.transfers}: ` }),
        el("strong", { textContent: me.transfers.first ? L.firstFree : L.transfersMade.replace("{m}", made).replace("{f}", free) }),
        hit ? el("span", { className: "v-N", textContent: ` (−${hit} ${L.pts})` }) : null),
      over.length ? el("p", { className: "v-N", textContent: L.clubOver.replace("{n}", game.clubCap).replace("{c}", over.join(", ")) }) : null,
      draft.captain === null && full ? el("p", { className: "muted", textContent: L.pickCaptain }) : null);
    squadBox.replaceChildren(
      el("div", { className: "liga-squad-head" }, el("h2", { id: "liga-squad-h", textContent: L.squad }),
        open ? null : el("span", { className: "badge neutral", textContent: L.closed }), switcher),
      facts, ...groups,
      el("div", { className: "liga-save" }, save, reset, msg));
  };
  const saved = () => {
    const lay = layout();
    const slots = Array(lay.length).fill(null);
    let captain = null;
    if (me.squad) {
      // the saved squad into the fixed layout: each position's places in turn
      const used = new Set();
      me.squad.slots.forEach((s, si) => {
        const i = lay.findIndex((p, k) => p === s.pos && !used.has(k));
        if (i >= 0) {
          used.add(i);
          slots[i] = { mp: s.mp, pos: s.pos };
          if (si === me.squad.captain) captain = i;
        }
      });
    }
    return { slots, captain };
  };

  // the list of MPs for a place: search, sorting, and why one cannot be picked
  const dlg = el("dialog", { className: "liga-picker" });
  document.body.append(dlg);
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  const picker = (slot, posIndex) => {
    const pos = POS()[posIndex];
    const q = el("input", { type: "search", placeholder: L.search, ariaLabel: L.search, id: "liga-q" });
    const sort = el("select", { ariaLabel: L.sortBy, id: "liga-sort" },
      [["form", L.byForm], ["afford", L.byAfford], ["price", L.byPriceDown], ["cheap", L.byPriceUp], ["name", L.byName]].map(([v, t]) => el("option", { value: v, textContent: t })));
    const list = el("ul", { className: "liga-list" });
    const inSquad = new Set(draft.slots.filter((s, i) => s && i !== slot).map((s) => s.mp));
    const current = draft.slots[slot];
    const draw = () => {
      const words = q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
      const clubs = clubCount();
      if (current) clubs[clubOf(current.mp)]--;
      const bank = bankAfter() + (current ? (sellOrPrice(current)) : 0);
      let rows = Object.keys(game.prices).map(Number).filter((mp) => !inSquad.has(mp))
        .filter((mp) => words.every((w) => `${nameOf(mp)} ${clubName(clubOf(mp))}`.toLowerCase().includes(w)));
      // why an MP cannot be picked now: the club already has its places, or the budget is short
      const whyNot = (mp) => {
        const club = clubOf(mp);
        return club !== "niez." && (clubs[club] || 0) >= game.clubCap ? L.clubFull : price(mp, posIndex) > bank ? L.tooDear : "";
      };
      const byForm = (a, b) => (formOf(b, posIndex) ?? -99) - (formOf(a, posIndex) ?? -99);
      const by = { form: byForm,
        // "stać mnie": the ones that can be picked now first, best form first, then the rest
        afford: (a, b) => (whyNot(a) ? 1 : 0) - (whyNot(b) ? 1 : 0) || byForm(a, b),
        price: (a, b) => price(b, posIndex) - price(a, posIndex), cheap: (a, b) => price(a, posIndex) - price(b, posIndex),
        name: (a, b) => nameOf(a).localeCompare(nameOf(b), "pl") }[sort.value];
      rows = rows.sort(by).slice(0, 120);
      list.replaceChildren(...rows.map((mp) => {
        const cost = price(mp, posIndex);
        const club = clubOf(mp);
        const why = whyNot(mp);
        const f = formOf(mp, posIndex);
        const b = el("button", { type: "button", className: "liga-row", disabled: !!why },
          el("span", { className: "liga-row-name" }, el("strong", { textContent: nameOf(mp) }), el("span", { className: "muted small", textContent: clubName(club) })),
          el("span", { className: "num small", textContent: f !== undefined ? String(f).replace(".", L.decimal) : "–" }),
          el("span", { className: "num", textContent: mln(cost) }),
          why ? el("span", { className: "liga-why small", textContent: why }) : null);
        b.addEventListener("click", () => {
          draft.slots[slot] = { mp, pos: posIndex };
          if (draft.captain === null && draft.slots.every(Boolean)) draft.captain = 0;
          dlg.close();
          drawSquad();
        });
        return el("li", {}, b);
      }));
    };
    q.addEventListener("input", draw);
    sort.addEventListener("change", draw);
    const close = el("button", { type: "button", className: "icon-btn", ariaLabel: L.close, title: L.close, textContent: "×" });
    close.addEventListener("click", () => dlg.close());
    const remove = current ? el("button", { type: "button", className: "lnk", textContent: L.remove }) : null;
    remove?.addEventListener("click", () => {
      draft.slots[slot] = null;
      if (draft.captain === slot) draft.captain = null;
      dlg.close();
      drawSquad();
    });
    dlg.replaceChildren(
      el("div", { className: "liga-picker-head" }, el("h2", { textContent: `${L.posNames[pos]}: ${L.pickTitle}` }), close),
      el("p", { className: "muted small", textContent: L.posRules[pos] }),
      el("div", { className: "liga-picker-tools" }, q, sort, remove),
      el("div", { className: "liga-list-head small muted" }, el("span", { textContent: L.mp }), el("span", { textContent: L.form }), el("span", { textContent: L.price })),
      list);
    draw();
    dlg.showModal();
    q.focus();
  };
  const sellOrPrice = (s) => {
    const i = me.squad?.slots.findIndex((x) => x.mp === s.mp && x.pos === s.pos) ?? -1;
    return i >= 0 ? me.squad.sell[i] : price(s.mp, s.pos);
  };

  // ---- past kolejki
  // the kolejki played, each with every MP's points: the player's own, or another's from the ranking
  const historyBox = (history = me.history, heading = L.history, open = false) => {
    const ks = Object.entries(history || {}).sort((a, b) => b[0].localeCompare(a[0]));
    if (!ks.length) return null;
    return el("section", { className: "liga-history" }, heading ? el("h2", { textContent: heading }) : null,
      ks.map(([kid, h], i) => el("details", { className: "card liga-k", open: open && i === 0 },
        el("summary", {}, el("strong", { textContent: h.number ? L.kolejkaN.replace("{n}", h.number) : kid }),
          el("span", { className: "liga-k-pts", textContent: `${h.total} ${L.pts}` }),
          h.final ? null : el("span", { className: "badge neutral", textContent: L.notFinal }),
          h.hit ? el("span", { className: "muted small", textContent: ` (${L.hit.replace("{n}", h.hit)})` }) : null),
        el("table", { className: "liga-k-table" }, el("tbody", {}, h.rows.map((r) => el("tr", {},
          el("td", { className: "liga-k-pos", textContent: L.posNames[POS()[r.pos]] }),
          el("td", { className: "liga-k-who" }, el("a", { href: `${SITE}posel/${r.mp}.html`, textContent: nameOf(r.mp) }),
            r.captain ? el("span", { className: "liga-k-cap", title: L.isCaptain, ariaLabel: L.isCaptain, textContent: "C" }) : null),
          el("td", { className: "liga-k-facts muted small", textContent: describe(r.facts) }),
          el("td", { className: "num liga-k-num", textContent: r.points }))))))));
  };
  const describe = (f) => Object.entries(f || {}).filter(([k]) => L.factNames[k]).map(([k, v]) => `${L.factNames[k]}: ${v}`).join(" · ");

  // ---- another player's squads (only the kolejki already locked), from the ranking
  const playerDlg = el("dialog", { className: "liga-picker liga-player" });
  document.body.append(playerDlg);
  playerDlg.addEventListener("click", (e) => { if (e.target === playerDlg) playerDlg.close(); });
  const playerButton = (r) => {
    const b = el("button", { type: "button", className: "lnk liga-who-btn", textContent: r.nick, title: L.seeSquads });
    b.addEventListener("click", async () => {
      const close = el("button", { type: "button", className: "icon-btn", ariaLabel: L.close, title: L.close, textContent: "×" });
      close.addEventListener("click", () => playerDlg.close());
      const head = el("div", { className: "liga-picker-head" }, el("h2", { textContent: r.nick }), close);
      playerDlg.replaceChildren(head, el("p", { className: "muted", textContent: L.loading }));
      playerDlg.showModal();
      try {
        const p = await api(`player&id=${encodeURIComponent(r.id)}`);
        // their latest kolejka in the hall, with each MP's points; every kolejka below, MP by MP
        const latest = Object.entries(p.history || {}).sort((a, b) => b[0].localeCompare(a[0]))[0];
        const h = latest && latest[1];
        const view = h ? [el("p", { className: "liga-player-k" }, el("strong", { textContent: h.number ? L.kolejkaN.replace("{n}", h.number) : latest[0] }),
                                ` · ${h.total} ${L.pts}`),
                          hall(false, { slots: h.rows.map((r) => ({ mp: r.mp, pos: r.pos })), captain: h.rows.findIndex((r) => r.captain) },
                               h.rows.map((r) => r.points))] : [];
        playerDlg.replaceChildren(head,
          el("p", {}, L.playerLine.replace("{r}", p.rank).replace("{t}", p.total)), ...view,
          historyBox(p.history, null, false) || el("p", { className: "muted", textContent: L.noKolejki }));
      } catch {
        playerDlg.replaceChildren(head, el("p", { className: "muted", textContent: L.failed }));
      }
    });
    return b;
  };

  // ---- the leaderboard
  const drawBoard = async () => {
    board.replaceChildren(el("h2", { id: "liga-board-h", textContent: L.board }), el("p", { className: "muted", textContent: L.loading }));
    try {
      const b = await api("board");
      if (!b.rows.length) {
        board.replaceChildren(board.firstChild, el("p", { className: "muted", textContent: L.boardEmpty }));
        return;
      }
      // a visitor has no rank of their own: nothing in its place (null would print as text)
      board.replaceChildren(...[board.firstChild,
        b.me ? el("p", {}, L.yourRank.replace("{r}", b.me.rank).replace("{n}", b.players).replace("{t}", b.me.total)) : null,
        el("div", { className: "table-scroll" }, el("table", { className: "liga-table" },
          el("thead", {}, el("tr", {}, el("th", { className: "num", textContent: "#" }), el("th", { textContent: L.player }),
            el("th", { className: "num", textContent: L.lastK }), el("th", { className: "num", textContent: L.total }))),
          el("tbody", {}, b.rows.map((r) => el("tr", { className: r.me ? "me" : "" },
            el("td", { className: "num", textContent: r.rank }),
            el("td", {}, r.id ? playerButton(r) : r.nick),
            el("td", { className: "num", textContent: r.last ?? "–" }), el("td", { className: "num", textContent: r.total }))))))].filter(Boolean));
    } catch {
      board.replaceChildren(board.firstChild, el("p", { className: "muted", textContent: L.failed }));
    }
  };

  // ---- account: the address for the newsletter and the reminder, sign-out, deletion
  const accountBox = () => {
    const e = me.email || {};
    const email = el("input", { type: "email", id: "liga-email", value: e.address || "", autocomplete: "email", placeholder: L.emailPh });
    const news = el("input", { type: "checkbox", id: "liga-news", checked: !!e.newsletter });
    const rem = el("input", { type: "checkbox", id: "liga-rem", checked: e.address ? !!e.reminders : true });
    const msg = el("p", { className: "liga-msg", role: "status",
      textContent: e.address ? (e.confirmed ? L.emailOk : L.emailPending) : "" });
    const save = el("button", { type: "button", className: "btn2", textContent: L.emailSave });
    save.addEventListener("click", async () => {
      try {
        const r = await api("email", { email: email.value, newsletter: news.checked, reminders: rem.checked });
        msg.textContent = r.email === null ? L.emailRemoved : r.confirmed ? L.emailOk : L.emailSent;
      } catch (err) {
        msg.textContent = err.message;
      }
    });
    const logout = el("button", { type: "button", className: "lnk", textContent: L.logout });
    logout.addEventListener("click", async () => { await api("logout", {}).catch(() => {}); refresh(); });
    const del = el("button", { type: "button", className: "lnk v-N", textContent: L.deleteAccount });
    const sure = el("div", { className: "liga-sure", hidden: true }, el("p", { textContent: L.deleteSure }));
    const yes = el("button", { type: "button", className: "btn2 v-N", textContent: L.deleteYes });
    const no = el("button", { type: "button", className: "lnk", textContent: L.cancel });
    sure.append(el("p", {}, yes, " ", no));
    del.addEventListener("click", () => { sure.hidden = false; });
    no.addEventListener("click", () => { sure.hidden = true; });
    yes.addEventListener("click", async () => { await api("delete", {}).catch(() => {}); refresh(); });
    return el("section", { className: "card liga-account" }, el("h2", { textContent: L.account }),
      el("p", { className: "muted small", textContent: L.emailText }),
      el("div", { className: "liga-email" }, el("label", { htmlFor: "liga-email", textContent: L.email }), email),
      el("p", { className: "liga-checks" }, el("label", {}, rem, ` ${L.reminders}`), el("label", {}, news, ` ${L.newsletter}`)),
      el("p", {}, save), msg,
      el("p", { className: "liga-account-foot" }, el("span", { className: "muted small", textContent: `${L.signedAs} ${me.user.nick}` }), logout, del), sure);
  };

  const refresh = async () => {
    me = await api("me");
    showStatus();
    if (!me.user) {
      main.replaceChildren(loginBox());
    } else if (!me.user.nick) {
      main.replaceChildren(nickBox());
    } else {
      draft = saved();
      drawSquad();
      main.replaceChildren(el("p", { className: "liga-total" }, `${L.yourTotal}: `, el("strong", { textContent: `${me.user.total} ${L.pts}` })),
        ...[squadBox, historyBox(), accountBox()].filter(Boolean));   // no past kolejki: no history (null would print as text)
    }
    drawBoard();
  };

  // what the address says after a round trip (sign-in, the confirmation link)
  const q = new URLSearchParams(location.search);
  const note = { "login=failed": L.loginFailed, "email=ok": L.emailOk, "email=failed": L.linkFailed, "email=removed": L.emailRemoved };
  const said = Object.entries(note).find(([k]) => { const [a, b] = k.split("="); return q.get(a) === b; });
  if (said) {
    root.before(el("p", { className: "card liga-note", role: "status", textContent: said[1] }));
    history.replaceState(null, "", location.pathname);
  }

  fetch(root.dataset.game).then((r) => r.json()).then((g) => {
    game = g;
    return refresh();
  }).catch(() => {
    root.replaceChildren(el("p", { className: "muted", textContent: L.failed }));
  });
})();
