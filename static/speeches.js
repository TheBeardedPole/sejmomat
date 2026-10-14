// Speeches in the chamber (templates/_speeches.html), on an MP's page
// (kind "mp") or a bill's (kind "bill"). The list loads when the visitor
// asks for it, arrives at #wystapienia or clicks a word in the cloud: a
// search box, shortcuts, and per speech a preview, the full text, the vote
// that settled the bill at that sitting, the official transcript and the
// video cut to that speech.
//
// An MP's list (dane/wystapienia/<id>.json) comes without the full texts,
// which for a busy MP run to megabytes (<id>.tekst.json): they load only for
// a full text or a search inside the texts. A bill's debate
// (dane/debaty/<print>.json) is small enough to come with its texts.
// The video streams from the Sejm's own server; browsers without built-in
// HLS get hls.js, loaded only on the first play.
(() => {
  const box = document.querySelector(".speeches");
  if (!box) return;
  const L = JSON.parse(box.dataset.labels);
  const { kind = "mp", src, texts: textsUrl, hls: hlsUrl, root, transcript } = box.dataset;
  const EN = document.documentElement.lang === "en";
  const PAGE = 20;
  const PREVIEW = 300;
  const el = (tag, props = {}, children = []) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children.filter((c) => c !== null && c !== undefined && c !== false));
    return node;
  };
  const fold = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");
  const dateText = (iso) => new Intl.DateTimeFormat(EN ? "en-GB" : "pl-PL", { day: "numeric", month: "long", year: "numeric" })
    .format(new Date(`${iso}T12:00:00`));
  const duration = (s) => (s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`);
  // as club_slug() in sejmomat/build.py
  const NO_CLUB = new Set(["niez.", "?"]);
  const clubPage = (club) => `${root}klub/${club.replace(/[^\p{L}\p{N}_-]/gu, "") || "klub"}.html#wystapienia`;

  // full texts: a separate file for an MP, in the list itself for a bill
  let textsReady = null;
  const loadTexts = () => textsReady ??= fetch(textsUrl).then((r) => {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).catch((e) => { textsReady = null; throw e; });

  let hlsReady = null;
  const loadHls = () => hlsReady ??= new Promise((resolve, reject) => {
    document.head.append(el("script", { src: hlsUrl, onload: () => resolve(window.Hls), onerror: reject }));
  });
  const play = async (holder, url) => {
    const video = el("video", { controls: true, playsInline: true, preload: "auto", className: "speech-video" });
    holder.replaceChildren(video);
    try {
      if (video.canPlayType("application/vnd.apple.mpegurl")) video.src = url;
      else {
        const Hls = await loadHls();
        if (!Hls.isSupported()) throw new Error("no HLS");
        const player = new Hls();
        player.loadSource(url);
        player.attachMedia(video);
      }
      await video.play().catch(() => {}); // a browser may want a second click to start with sound
    } catch {
      holder.replaceChildren(el("p", { className: "muted", textContent: L.videoFailed }));
    }
  };

  const voteLink = (v) => el("a", { className: "speech-vote", href: `${root}glosowanie/${v.s}-${v.n}.html` }, [
    `${L.vote}: `, el("span", { className: `badge ${v.o}`, textContent: v.l[EN ? 1 : 0] }), ` ${v.yes}:${v.no}`]);

  const item = (s) => {
    const body = el("div", { className: "speech-text", lang: "pl" }, [el("p", { textContent: s.preview })]);
    const media = el("div");
    const actions = el("p", { className: "speech-actions" }, [
      s.long && el("button", { type: "button", textContent: L.full, onclick: async (e) => {
        const button = e.target;
        button.disabled = true;
        try {
          const all = await loadTexts();
          body.replaceChildren(...all[s.key].split("\n").map((p) => el("p", { textContent: p })));
          button.remove();
        } catch {
          button.disabled = false;
          body.append(el("p", { className: "muted", textContent: L.failed }));
        }
      } }),
      s.clip && el("button", { type: "button", textContent: `▶ ${L.video}`, onclick: () => play(media, s.clip) }),
      s.day && el("a", { href: transcript.replace("{s}", s.sitting).replace("{d}", s.day).replace("{n}", s.num),
        target: "_blank", rel: "noopener", textContent: L.transcript }),
      kind === "mp" && s.bill && el("a", { href: `${root}ustawa/${s.bill}.html#wystapienia`, textContent: L.debate }),
      s.vote && voteLink(s.vote),
    ]);
    const meta = [
      s.function && s.function !== "Poseł" ? el("span", { className: "badge", lang: "pl", textContent: s.function }) : null,
      s.unspoken ? el("span", { className: "badge warn", textContent: L.unspoken })
        : s.seconds !== null ? el("span", { className: "muted", textContent: ` · ${duration(s.seconds)}` }) : null,
    ];
    if (kind === "bill") {
      const who = s.mp ? el("a", { href: `${root}posel/${s.mp}.html#wystapienia`, textContent: s.name }) : el("span", { textContent: s.name });
      return el("article", { className: "speech" }, [
        el("p", { className: "speech-head" }, [el("strong", {}, [who]),
          // independents have no club page
          s.club ? [" ", NO_CLUB.has(s.club) ? el("span", { className: "muted", textContent: `(${s.club})` })
            : el("a", { className: "muted", href: clubPage(s.club), textContent: `(${s.club})` })] : null,
          ...meta].flat()),
        el("p", { className: "speech-stage", lang: "pl" }, [`${dateText(s.date)} · ${s.topic}`]),
        body, actions, media,
      ]);
    }
    const topic = s.bill ? el("a", { href: `${root}ustawa/${s.bill}.html`, lang: "pl", textContent: s.topic })
      : el("span", { lang: "pl", textContent: s.topic });
    if (s.agenda.length > 1) topic.title = s.agenda.join("\n");
    return el("article", { className: "speech" }, [
      el("p", { className: "speech-head" }, [el("span", { className: "muted", textContent: dateText(s.date) }), " · ", topic, ...meta]),
      body, actions, media,
    ]);
  };

  let ui = null; // the search box and its filter, once the list is shown
  const show = async () => {
    box.replaceChildren(el("p", { className: "muted", textContent: L.loading }));
    let list;
    try {
      list = await fetch(src).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
    } catch {
      box.replaceChildren(el("p", { className: "muted", textContent: L.failed }),
        el("button", { type: "button", textContent: L.retry, onclick: show }));
      return;
    }
    if (kind === "bill") { // the texts came along: make the previews here
      const all = {};
      list.forEach((s) => {
        s.key = `${s.date}#${s.num}`;
        all[s.key] = s.text;
        const cut = s.text.length <= PREVIEW ? s.text : `${s.text.slice(0, PREVIEW).replace(/\s+\S*$/, "")}…`;
        s.preview = cut.split("\n")[0];
        s.long = s.preview !== s.text;
      });
      textsReady = Promise.resolve(all);
      list.fullText = true;
    }
    const keyOf = (s, text) => fold(`${s.name || ""} ${s.club || ""} ${s.topic} ${s.agenda.join(" ")} ${text}`);
    list.forEach((s) => { s._k = keyOf(s, s.text || s.preview); });
    const search = el("input", { type: "search", placeholder: L.search, className: "speech-search" });
    const count = el("p", { className: "muted" });
    const items = el("div");
    const more = el("button", { type: "button", className: "speech-more", textContent: L.more });
    let found = list, shown = 0;
    const render = (reset) => {
      if (reset) { items.replaceChildren(); shown = 0; }
      items.append(...found.slice(shown, shown + PAGE).map(item));
      shown = Math.min(found.length, shown + PAGE);
      count.textContent = L.count.replace("{n}", found.length).replace("{all}", list.length);
      more.hidden = shown >= found.length;
    };
    // An MP's search covers topics and previews at once; the full texts are
    // fetched on the first search and joined in when they arrive.
    // `forms`: a word from the cloud, searched for in all its forms
    let forms = null;
    const filter = () => {
      const q = fold(search.value.trim());
      const any = forms ? forms.map(fold) : [q];
      found = q ? list.filter((s) => any.some((f) => s._k.includes(f))) : list;
      render(true);
      if (q.length >= 3 && !list.fullText) {
        count.textContent += ` · ${L.searchingTexts}`;
        loadTexts().then((all) => {
          if (list.fullText) return;
          list.fullText = true;
          list.forEach((s) => { s._k = keyOf(s, all[s.key] || s.preview); });
          filter();
        }).catch(() => {});
      }
    };
    search.addEventListener("input", () => { forms = null; filter(); });
    more.addEventListener("click", () => render(false));
    // the most frequent topics (a bill's: its stages), as shortcuts to search for
    const topics = [...list.reduce((m, s) => m.set(s.topic, (m.get(s.topic) || 0) + 1), new Map())]
      .filter(([t]) => t !== "—").sort((a, b) => b[1] - a[1]).slice(0, 8);
    const chips = topics.length > 1 && el("p", { className: "speech-topics" }, topics.map(([t, n]) => el("button", {
      type: "button", className: "chip", lang: "pl", title: t,
      textContent: `${t.length > 60 ? `${t.slice(0, 57)}…` : t} (${n})`,
      onclick: () => { search.value = t; forms = null; filter(); },
    })));
    box.replaceChildren(...[search, chips, count, items, more].filter(Boolean));
    render(true);
    ui = { search, filter, setForms: (f) => { forms = f; } };
  };

  box.querySelector(".speech-open")?.addEventListener("click", show);
  if (location.hash === "#wystapienia") show();
  // a word in the cloud searches the speeches for it, in all its forms
  document.addEventListener("click", async (e) => {
    const word = e.target.closest(".cloud [data-q]");
    if (!word) return;
    if (!ui) await show();
    if (!ui) return;
    ui.search.value = word.textContent;
    ui.setForms(word.dataset.q.split("|"));
    ui.filter();
    ui.search.scrollIntoView({ behavior: "smooth", block: "start" });
  });
})();
