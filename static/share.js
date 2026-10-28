// "Grafiki do udostępnienia" (templates/_cards.html, share_dialog): a window where the
// reader picks what to share — a voting day's summary, a club's or an MP's term or
// latest sitting — or puts two MPs or two clubs side by side. The day and club images
// come ready with the site (sejmomat/card.py); an MP's and the comparisons are drawn
// here, in the browser (static/card.js), from the site's own API (api/v1/). Nothing is
// sent anywhere: the image is shown, then handed over as a download or to the
// system's share sheet.
(() => {
  const dialog = document.getElementById("grafiki");
  const opener = document.querySelector("[data-share-open]");
  if (!dialog || !opener || !dialog.showModal) return;
  const L = JSON.parse(dialog.dataset.labels);
  const CLUBS = JSON.parse(dialog.dataset.clubs);
  const ROOT = dialog.dataset.root, SITE = dialog.dataset.siteRoot;
  const kinds = dialog.querySelector(".share-kinds"), fields = dialog.querySelector(".share-fields");
  const status = dialog.querySelector(".share-status");
  const img = Object.assign(document.createElement("img"), { alt: "", hidden: true });
  dialog.querySelector(".share-preview").append(img);
  const download = dialog.querySelector(".share-download"), native = dialog.querySelector(".share-native");

  const el = (tag, props = {}, ...children) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children.flat().filter((c) => c !== null && c !== undefined && c !== false));
    return node;
  };
  const json = {};
  const get = (url) => (json[url] ??= fetch(url).then((r) => {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).catch((e) => {
    delete json[url];
    throw e;
  }));
  const short = (id) => (!id || id === "niez." ? L.independent : CLUBS.find((c) => c.id === id)?.short || id);
  const slug = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  // ---- what is on show: a ready image (its address) or a drawn one (a blob)
  let blobUrl = null, blob = null, turn = 0;
  const clear = (text = "") => {
    if (blobUrl) URL.revokeObjectURL(blobUrl);
    blobUrl = blob = null;
    img.hidden = true;
    img.removeAttribute("src");
    download.hidden = native.hidden = true;
    status.textContent = text;
    status.hidden = !text;
  };
  const showReady = (src, file) => {
    clear();
    img.src = src;
    img.hidden = false;
    download.href = src;
    download.download = `${file}.png`;
    download.hidden = false;
    native.hidden = !navigator.canShare;
    blob = null;
  };
  // a drawing: only the latest asked for is shown, if the reader changed their mind meanwhile
  const showDrawn = async (make, file) => {
    const mine = ++turn;
    clear(L.loading);
    try {
      await document.fonts?.ready;
      const canvas = await make();
      const b = await window.SejmomatCards.toBlob(canvas);
      canvas.width = canvas.height = 0;
      if (mine !== turn) return;
      clear();
      blob = b;
      blobUrl = URL.createObjectURL(b);
      img.src = blobUrl;
      img.hidden = false;
      download.href = blobUrl;
      download.download = `${file}.png`;
      download.hidden = false;
      native.hidden = !navigator.canShare?.({ files: [new File([b], `${file}.png`, { type: "image/png" })] });
    } catch {
      if (mine === turn) clear(L.failed);
    }
  };
  native.addEventListener("click", async () => {
    try {
      const b = blob || await (await fetch(img.src)).blob();
      await navigator.share({ files: [new File([b], download.download, { type: "image/png" })] });
    } catch {
      // the reader closed the share sheet, or it is not there: the download stays
    }
  });

  // ---- the fields of each kind
  const field = (label, control) => el("label", { className: "share-field" }, el("span", { textContent: label }), control);
  const select = (options, value) => {
    const s = el("select", {}, options.map(([v, text]) => el("option", { value: v, textContent: text })));
    if (value !== undefined) s.value = value;
    return s;
  };
  const variant = (value = "kadencja") => field(L.variant, select([["kadencja", L.term], ["posiedzenie", L.sitting]], value));

  // MPs: a field with the names to pick from (the browser's own list as one types)
  let mpList = null;
  const mpsReady = () => get(dialog.dataset.mps).then((rows) => {
    if (!mpList) {
      const active = rows.filter((m) => m.active).sort((a, b) => a.name.localeCompare(b.name, "pl"));
      mpList = el("datalist", { id: "grafiki-mps" }, active.map((m) => el("option", { value: m.name })));
      dialog.append(mpList);
    }
    return rows;
  });
  const mpField = (label) => {
    const input = el("input", { type: "text", autocomplete: "off", placeholder: L.typeName });
    input.setAttribute("list", "grafiki-mps");
    return [field(label, input), input];
  };
  const findMp = (rows, name) => rows.find((m) => m.active && m.name === name.trim()) || rows.find((m) => m.name === name.trim());

  const KINDS = {
    day: async () => {
      const days = await get(dialog.dataset.days);
      const pick = select(days.filter((d) => d.image).map((d) => [d.day, d.day.split("-").reverse().join(".")]));
      const go = () => {
        const d = days.find((x) => x.day === pick.value);
        if (d) showReady(`${SITE}${d.image}`, `sejmomat-${d.day}`);
      };
      pick.addEventListener("change", go);
      fields.replaceChildren(field(L.pickDay, pick));
      go();
    },
    club: async () => {
      const list = CLUBS.filter((c) => c.cards.length);
      const pick = select(list.map((c) => [c.id, c.current ? c.short : `${c.short} (${L.former})`]));
      const which = variant();
      const go = () => {
        const c = list.find((x) => x.id === pick.value);
        const card = c && (c.cards.find(([, path]) => path.endsWith(`-${which.querySelector("select").value}.png`)) || c.cards[0]);
        if (card) showReady(`${SITE}${card[1]}`, `sejmomat-${slug(c.short)}-${card[1].split("-").pop().replace(".png", "")}`);
      };
      pick.addEventListener("change", go);
      which.addEventListener("change", go);
      fields.replaceChildren(field(L.pickClub, pick), which);
      go();
    },
    mp: async () => {
      const rows = await mpsReady();
      const [f, input] = mpField(L.pickMp);
      const which = variant();
      const go = async () => {
        if (!input.value.trim()) return clear();
        const m = findMp(rows, input.value);
        if (!m) return clear(L.noMp);
        const kind = which.querySelector("select").value === "posiedzenie" ? "sitting" : "term";
        showDrawn(async () => {
          // the MP page carries the card's data (templates/_cards.html, mp)
          const page = await (await fetch(`${ROOT}posel/${m.id}.html`)).text();
          const data = JSON.parse(new DOMParser().parseFromString(page, "text/html").getElementById("mp-card").textContent);
          if (kind === "sitting" && !data.sitting) throw new Error("no sitting");
          return window.SejmomatCards.mp(data, kind);
        }, `sejmomat-${slug(m.name)}-${kind === "sitting" ? "posiedzenie" : "kadencja"}`);
      };
      input.addEventListener("change", go);
      which.addEventListener("change", go);
      fields.replaceChildren(f, which);
      clear();
      input.focus();
    },
    mps: async () => {
      const rows = await mpsReady();
      const [fa, a] = mpField(L.first), [fb, b] = mpField(L.second);
      const side = (m) => ({ ...m, sub: short(m.club), photo: dialog.dataset.photo.replace("{id}", m.id) });
      const go = () => {
        const ma = a.value.trim() && findMp(rows, a.value), mb = b.value.trim() && findMp(rows, b.value);
        if ((a.value.trim() && !ma) || (b.value.trim() && !mb)) return clear(L.noMp);
        if (!ma || !mb) return clear(L.pickBoth);
        if (ma.id === mb.id) return clear(L.same);
        showDrawn(() => window.SejmomatCards.compareMps(side(ma), side(mb), dialog.dataset.logo),
          `sejmomat-${slug(ma.name)}-vs-${slug(mb.name)}`);
      };
      a.addEventListener("change", go);
      b.addEventListener("change", go);
      fields.replaceChildren(fa, fb);
      clear(L.pickBoth);
      a.focus();
    },
    clubs: async () => {
      const [rows, clubs] = await Promise.all([get(dialog.dataset.mps), get(dialog.dataset.clubsApi)]);
      // clubs sitting now, each once (the TD names of 2023 are former clubs)
      const now = CLUBS.filter((c) => c.current && clubs.some((x) => x.id === c.id && x.exists));
      const pa = select(now.map((c) => [c.id, c.short]), now[0]?.id), pb = select(now.map((c) => [c.id, c.short]), now[1]?.id);
      const figures = (id) => {
        const c = clubs.find((x) => x.id === id);
        const members = rows.filter((m) => m.active && m.club === id);
        const avg = (k) => (members.length ? members.reduce((t, m) => t + (m[k] || 0), 0) / members.length : 0);
        return { name: short(id), sub: "", members: members.length, cohesion: c.cohesion, effectiveness: c.effectiveness,
          turnout: avg("turnout"), speeches: avg("speeches"), questions: avg("questions") };
      };
      const go = () => {
        if (pa.value === pb.value) return clear(L.sameClub);
        const shared = clubs.find((x) => x.id === pa.value)?.agreement?.find((x) => x.club === pb.value);
        showDrawn(() => window.SejmomatCards.compareClubs(figures(pa.value), figures(pb.value),
          shared ? { rate: shared.rate, votes: shared.sharedVotes } : null, dialog.dataset.logo),
        `sejmomat-${slug(short(pa.value))}-vs-${slug(short(pb.value))}`);
      };
      pa.addEventListener("change", go);
      pb.addEventListener("change", go);
      fields.replaceChildren(field(L.first, pa), field(L.second, pb));
      go();
    },
  };

  // ---- the kinds as a row of choices
  const order = ["day", "club", "mp", "mps", "clubs"];
  let current = null;
  const choose = async (kind) => {
    if (kind === current) return;
    current = kind;
    turn++;
    kinds.querySelectorAll("button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.kind === kind)));
    fields.replaceChildren();
    clear(L.loading);
    try {
      await KINDS[kind]();
    } catch {
      if (current === kind) clear(L.failed);
    }
  };
  kinds.append(...order.map((k) => {
    const b = el("button", { type: "button", className: "share-kind", textContent: L[k] });
    b.dataset.kind = k;
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", "false");
    b.addEventListener("click", () => choose(k));
    return b;
  }));
  // arrows move between the kinds, as in any group of radio buttons
  kinds.addEventListener("keydown", (e) => {
    const i = order.indexOf(current), step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (!step) return;
    e.preventDefault();
    const k = order[(i + step + order.length) % order.length];
    choose(k);
    kinds.querySelector(`[data-kind="${k}"]`).focus();
  });

  opener.addEventListener("click", () => {
    dialog.showModal();
    if (!current) choose("day");
  });
  // a click on the backdrop closes it, as Escape does
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) dialog.close();
  });
})();
