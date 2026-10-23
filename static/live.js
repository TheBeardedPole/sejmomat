// The Sejm's live stream of a plenary sitting, on the home page and the
// upcoming sitting page (templates/_cards.html, live_box). Only on the
// sitting's days does the browser ask the Sejm's API for today's streams
// (videos/today); while a sitting is live the stream plays, muted (HLS,
// played with hls.js, starting at the lowest quality and never above what the
// player's size needs). Nothing to add by
// hand: the API lists each day's plenary stream ("posiedzenie") with its
// scheduled times. Next to the stream, the votes as they come in (below).
(() => {
  const box = document.querySelector(".live-box");
  if (!box) return;
  const L = JSON.parse(box.dataset.labels);
  // the API's times are Warsaw time without a zone; compare them as text
  const warsaw = () => new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Warsaw", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).format(new Date()).replace(" ", "T");
  if (!box.dataset.dates.split(",").includes(warsaw().slice(0, 10))) return;

  const el = (tag, props = {}, ...children) => {
    const e = Object.assign(document.createElement(tag), props);
    e.append(...children.filter(Boolean));
    return e;
  };
  let playing = false;
  const LAG = 100;
  let synced = null;   // {video, start (ms)}: the panel follows the video's clock

  // the player, playing muted from the start (browsers allow that without a click)
  const player = async (stream) => {
    playing = true;
    const video = el("video", { controls: true, playsInline: true, muted: true, autoplay: true, className: "live-video" });
    // hls.js wherever it can run (it starts at the live edge and keeps the quality down);
    // the browser's own HLS where it cannot (iPhone)
    if (!window.MediaSource && video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = stream;
      return video;
    }
    try {
      if (!window.Hls) {
        await new Promise((resolve, reject) => {
          document.head.append(el("script", { src: box.dataset.hls, onload: resolve, onerror: reject }));
        });
      }
      // LAG seconds behind live: the votes reach the API about a minute late, and
      // the panel shows each one when the video gets to it
      const hls = new window.Hls({ liveSyncDuration: LAG, liveMaxLatencyDuration: LAG + 90, startLevel: 0, capLevelToPlayerSize: true });
      synced = { video, start: Number(new URL(stream).searchParams.get("start")) || null };
      video.addEventListener("timeupdate", () => votes && renderVotes());
      hls.on(window.Hls.Events.ERROR, (_, d) => {
        if (d.fatal) video.replaceWith(el("p", { className: "muted", textContent: L.failed }));
      });
      hls.loadSource(stream);
      hls.attachMedia(video);
    } catch {
      return el("p", { className: "muted", textContent: L.failed });
    }
    return video;
  };

  // ---- the votes as they come in: the Sejm's API has each vote about a minute
  // after it is taken, its title naming the agenda item ("Pkt. 17 ..."). The
  // sitting's votes are read once, then only the next vote's number is asked
  // for (a short 404 until it exists).
  const agenda = JSON.parse(box.dataset.agenda || "{}");
  const ROOT = box.dataset.root || "";
  const PRINT = (n) => `https://www.sejm.gov.pl/Sejm${box.dataset.votes.match(/term(\d+)/)[1]}.nsf/druk.xsp?nr=${n}`;
  let votes = null;
  const panel = el("aside", { className: "live-votes", ariaLive: "polite" });
  const passed = (v) => v.majorityType === "SIMPLE_MAJORITY" ? v.yes > v.no : v.yes >= (v.majorityVotes || 0);
  const pointOf = (v) => (v.title || "").match(/^\s*Pkt\.?\s*(\d+)/)?.[1];
  const hhmm = (iso) => iso.slice(11, 16);
  // a vote's page here (glosowanie-na-zywo.html goes on to the regular page once the site has it)
  const votePage = (v) => `${ROOT}glosowanie-na-zywo.html?posiedzenie=${v.sitting}&nr=${v.votingNumber}`;
  const badge = (v) => el("span", { className: `badge ${passed(v) ? "adopted" : "rejected"}`, textContent: passed(v) ? L.passed : L.rejected });

  // a time from the API (Warsaw time, no zone) as a moment
  const warsawMs = (iso) => {
    const guess = Date.parse(`${iso}Z`);
    const there = Date.parse(`${new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw", year: "numeric", month: "2-digit",
      day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).format(new Date(guess)).replace(" ", "T")}Z`);
    return guess - (there - guess);
  };
  // the moment the video shows (the stream's start plus the position), or now without a video
  const clock = () => synced?.start && synced.video.readyState > 0 ? synced.start + synced.video.currentTime * 1000 : Date.now();
  // "wniosek mniejszości 5" and "poprawka 3" linked to their text, when the report has a page here
  const topicNode = (v, item) => {
    const t = v.topic || v.title || "";
    const minority = t.match(/wniosek mniejszości (?:nr )?(\d+)/i), amendment = t.match(/^poprawka (?:nr )?(\d+)/i);
    if (minority && item?.[3]) return el("a", { href: `${ROOT}druk/${item[3]}.html#wniosek-${minority[1]}`, textContent: t });
    if (amendment && item?.[4]) return el("a", { href: `${ROOT}druk/${item[4]}.html#poprawka-${amendment[1]}`, textContent: t });
    return t;
  };
  let shownCount = -1;

  const renderVotes = () => {
    const shown = votes.filter((v) => warsawMs(v.date) <= clock());
    if (shown.length === shownCount) return;   // called on every tick of the video
    shownCount = shown.length;
    // "as they happen" only while today's votes are coming in; otherwise the latest ones
    const today = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw" }).format(new Date());
    panel.replaceChildren(el("h3", {}, shown.at(-1)?.date.startsWith(today) ? L.votes : (L.latest || L.votes)));
    if (!shown.length) {
      panel.append(el("p", { className: "muted" }, L.none));
      return;
    }
    const v = shown.at(-1), n = pointOf(v), item = n && agenda[n];
    // the item from the agenda (with its links), else the vote's own title
    const title = item
      ? el("a", { href: `${ROOT}nadchodzace-posiedzenie.html#punkt-${n}`, textContent: `${L.item} ${n}. ${item[0]}` })
      : (v.title || "").replace(/^\s*Pkt\.?\s*\d+\.?\s*/, n ? `${L.item} ${n}. ` : "");
    const links = el("p", { className: "live-links" });
    if (item?.[1]) links.append(el("a", { href: `${ROOT}ustawa/${item[1]}.html`, textContent: `${L.bill} →` }), " ");
    if (item?.[2]?.length) {
      links.append(`${L.prints}: `);
      item[2].forEach((p, i) => links.append(i ? ", " : "", el("a", { href: PRINT(p), textContent: p })));
    }
    panel.append(el("div", { className: "live-now" },
      el("div", { className: "muted" }, el("a", { href: votePage(v), textContent: `${L.vote} ${v.votingNumber}` }), ` · ${hhmm(v.date)}`),
      el("div", { className: "item", lang: "pl" }, title),
      el("div", { className: "topic", lang: "pl" }, topicNode(v, item)),
      el("p", { className: "counts" }, badge(v), ` ${v.yes} ${L.yes} · ${v.no} ${L.no} · ${v.abstain} ${L.abstain}`),
      links.childNodes.length ? links : null));
    const earlier = shown.slice(-7, -1).reverse();
    if (earlier.length) {
      panel.append(el("h3", {}, L.earlier), el("ul", { className: "live-earlier" }, ...earlier.map((x) => el("li", { lang: "pl" },
        el("a", { href: votePage(x), textContent: `${L.no_ || "nr"} ${x.votingNumber}` }),
        ` · ${hhmm(x.date)} · ${pointOf(x) ? `${L.item} ${pointOf(x)} · ` : ""}`, topicNode(x, agenda[pointOf(x)]), " ", badge(x)))));
    }
    panel.append(el("p", { className: "live-note" }, synced ? L.synced : L.delay));
  };

  const nextVotes = async () => {
    // after one vote comes another, often within seconds: keep asking until a 404
    for (;;) {
      const r = await fetch(`${box.dataset.votes}/${(votes.at(-1)?.votingNumber || 0) + 1}`).catch(() => null);
      if (!r?.ok) return;
      votes.push(await r.json());
      shownCount = -1;
      renderVotes();
    }
  };
  const startVotes = async () => {
    if (votes) return;
    try {
      votes = (await (await fetch(box.dataset.votes)).json()).sort((a, b) => a.votingNumber - b.votingNumber);
    } catch {
      votes = [];
    }
    renderVotes();
    setInterval(nextVotes, 20 * 1000);
  };

  const show = async (v, now) => {
    const time = (iso) => iso.slice(11, 16);
    const live = v.startDateTime <= now && (!v.endDateTime || now < v.endDateTime);
    const main = el("div", { className: "live-main" });
    box.replaceChildren(
      el("h2", {}, live ? el("span", { className: "live-dot", ariaHidden: "true" }) : null,
        live ? L.live : `${L.today} ${time(v.startDateTime)}`),
      el("p", { className: "muted" }, `${v.title}${v.room ? ` · ${v.room}` : ""}`),
      el("div", { className: "live-grid with-votes" }, main, panel),
    );
    box.hidden = false;
    startVotes();
    if (live && v.videoLink) {
      const video = await player(v.videoLink);
      main.append(video);
      video.play?.().catch(() => {});
    }
    if (v.playerLink) {
      main.append(el("p", { className: "live-links" },
        el("a", { href: v.playerLink, target: "_blank", rel: "noopener", textContent: `${L.sejm} ↗` })));
    }
  };

  const check = async () => {
    if (playing) return;
    let videos;
    try {
      videos = await (await fetch(box.dataset.api)).json();
    } catch {
      return;   // no answer: leave the box hidden
    }
    const now = warsaw();
    const plenary = videos.filter((v) => v.type === "posiedzenie" && v.startDateTime?.slice(0, 10) === now.slice(0, 10))
      .sort((a, b) => a.startDateTime.localeCompare(b.startDateTime));
    // the one under way, else the next today; once the day's last has ended the box goes
    const v = plenary.find((x) => x.startDateTime <= now && (!x.endDateTime || now < x.endDateTime))
      || plenary.find((x) => x.startDateTime > now);
    if (v) show(v, now);
    else box.hidden = true;
  };
  check();
  // a stream that starts or ends while the page is open
  setInterval(check, 5 * 60 * 1000);
})();
