// The Sejm's live stream of a plenary sitting, on the home page and the
// upcoming sitting page (templates/_cards.html, live_box). Only on the
// sitting's days does the browser ask the Sejm's API for today's streams
// (videos/today); while a sitting is live the stream plays, muted (HLS,
// played with hls.js, starting at the lowest quality and never above what the
// player's size needs). Nothing to add by
// hand: the API lists each day's plenary stream ("posiedzenie") with its
// scheduled times.
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
      const hls = new window.Hls({ liveSyncDurationCount: 3, startLevel: 0, capLevelToPlayerSize: true });
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

  const show = async (v, now) => {
    const time = (iso) => iso.slice(11, 16);
    const live = v.startDateTime <= now && (!v.endDateTime || now < v.endDateTime);
    box.replaceChildren(
      el("h2", {}, live ? el("span", { className: "live-dot", ariaHidden: "true" }) : null,
        live ? L.live : `${L.today} ${time(v.startDateTime)}`),
      el("p", { className: "muted" }, `${v.title}${v.room ? ` · ${v.room}` : ""}`),
    );
    box.hidden = false;
    if (live && v.videoLink) {
      const video = await player(v.videoLink);
      box.append(video);
      video.play?.().catch(() => {});
    }
    if (v.playerLink) {
      box.append(el("p", { className: "live-links" },
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
