// Sejmomat's own live coverage on YouTube (youtube.com/@Sejmomat): when it is on, it
// takes the place of the Sejm's stream (static/live.js, static/home.js,
// static/schedule.js). Whether it is on comes from our server (server/youtube-live.php,
// checked at most once a minute), never from the reader's browser asking YouTube.
//
// The player is YouTube's (youtube-nocookie.com), and loading it sends the reader's
// address to Google; so it starts by itself (muted) only for a reader who accepted
// optional cookies and services ("Zgadzam się", static/app.js), and otherwise waits for
// a click on Play.

window.SejmomatYT = (() => {
  let asked = null;   // one request per page view, shared by the scripts that ask

  // static/app.js knows the consent and its version; without it, no consent
  const consented = () => window.sejmomatConsented?.() === true;

  // {live: true, id, title} or null (not live, or the server could not tell)
  const check = (url, fresh = false) => {
    if (!url) return Promise.resolve(null);
    if (fresh || !asked) {
      asked = fetch(url, { cache: fresh ? "no-store" : "default" })
        .then((r) => (r.ok ? r.json() : null))
        // a video's id (YouTube's own page said so), or the channel's (the stream server said so)
        .then((a) => (a?.live && (/^[A-Za-z0-9_-]{11}$/.test(a.id || "") || /^UC[A-Za-z0-9_-]{22}$/.test(a.channel || "")) ? a : null))
        .catch(() => null);
    }
    return asked;
  };

  const lang = document.documentElement.lang === "en" ? "en" : "pl";
  const T = lang === "en"
    ? { title: "Sejmomat live", play: "Play the broadcast", note: "The YouTube player loads only when you press Play.", open: "On YouTube" }
    : { title: "Sejmomat na żywo", play: "Odtwórz transmisję", note: "Odtwarzacz YouTube wczytamy dopiero po kliknięciu.", open: "Na YouTube" };

  // the video, or whatever the channel has live now
  const embedPath = (info) => (info.id ? info.id : `live_stream?channel=${info.channel}`);
  const iframe = (info, muted) => Object.assign(document.createElement("iframe"), {
    className: "yt-frame", title: T.title, allowFullscreen: true, loading: "eager",
    src: `https://www.youtube-nocookie.com/embed/${embedPath(info)}${info.id ? "?" : "&"}autoplay=1&mute=${muted ? 1 : 0}&playsinline=1&rel=0`,
    allow: "autoplay; encrypted-media; picture-in-picture; fullscreen",
  });

  // the player for a live stream: at once (muted) with consent, else a box with Play
  const player = (info, { auto = true } = {}) => {
    const box = document.createElement("div");
    box.className = "yt-box";
    if (auto && consented()) {
      box.append(iframe(info, true));
      return box;
    }
    const play = Object.assign(document.createElement("button"), { type: "button", className: "yt-play" });
    play.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>';
    play.append(Object.assign(document.createElement("span"), { textContent: T.play }));
    const face = document.createElement("div");
    face.className = "yt-face";
    face.append(Object.assign(document.createElement("p"), { className: "yt-face-title", textContent: info.title || T.title }),
      play, Object.assign(document.createElement("p"), { className: "yt-face-note", textContent: T.note }));
    play.addEventListener("click", () => box.replaceChildren(iframe(info, false)));
    box.append(face);
    return box;
  };

  const watchUrl = (info) => (info.id ? `https://www.youtube.com/watch?v=${info.id}` : `https://www.youtube.com/channel/${info.channel}/live`);
  // what tells one stream from another: the video, or the channel's live slot
  const key = (info) => (info ? info.id || info.channel : null);
  return { check, player, watchUrl, consented, key, T };
})();
