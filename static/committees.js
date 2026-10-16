// Committee meeting recordings (templates/_committees.html): a click on
// "Nagranie" plays the meeting in the page, from the Sejm's own streaming
// server, the stream cut to the meeting. As the speeches (static/speeches.js):
// browsers without built-in HLS get hls.js, loaded only on the first play.
(() => {
  const script = document.currentScript;
  const hlsUrl = script.dataset.hls, failed = script.dataset.failed;
  let hlsReady = null;
  const loadHls = () => hlsReady ??= new Promise((resolve, reject) => {
    document.head.append(Object.assign(document.createElement("script"), { src: hlsUrl, onload: () => resolve(window.Hls), onerror: reject }));
  });
  document.addEventListener("click", async (e) => {
    const button = e.target.closest("button[data-stream]");
    if (!button) return;
    const holder = button.closest(".meeting").querySelector(".meeting-video");
    const video = Object.assign(document.createElement("video"), { controls: true, playsInline: true, preload: "auto" });
    holder.replaceChildren(video);
    holder.hidden = false;
    try {
      if (video.canPlayType("application/vnd.apple.mpegurl")) video.src = button.dataset.stream;
      else {
        const Hls = await loadHls();
        if (!Hls.isSupported()) throw new Error("no HLS");
        const player = new Hls();
        player.loadSource(button.dataset.stream);
        player.attachMedia(video);
      }
      await video.play().catch(() => {}); // a browser may want a second click to start with sound
    } catch {
      holder.replaceChildren(Object.assign(document.createElement("p"), { className: "muted", textContent: failed }));
    }
  });
})();
