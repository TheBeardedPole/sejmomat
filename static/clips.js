// "Nagranie" on a sitting's agenda (templates/sitting.html): the debate on an
// item, cut from the Sejm's stream of that day (from the first speech on the
// item to the last), played under the item with hls.js, loaded on the first
// click (an iPhone plays HLS itself). One video at a time.
(() => {
  const script = document.currentScript;
  let current = null;
  const loadHls = () => window.Hls ? Promise.resolve() : new Promise((resolve, reject) => {
    const s = Object.assign(document.createElement("script"), { src: script.dataset.hls, onload: resolve, onerror: reject });
    document.head.append(s);
  });

  document.addEventListener("click", async (e) => {
    const button = e.target.closest("button[data-clip]");
    if (!button) return;
    current?.remove();   // the hls.js instance goes with its video
    const video = Object.assign(document.createElement("video"), { controls: true, playsInline: true, className: "clip-video" });
    const failed = () => video.replaceWith(Object.assign(document.createElement("p"), { className: "muted", textContent: script.dataset.failed }));
    // under the item's line of links
    button.closest("p").after(video);
    current = video;
    // hls.js wherever it can run; the browser's own HLS where it cannot (iPhone)
    if (!window.MediaSource && video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = button.dataset.clip;
    } else {
      try {
        await loadHls();
      } catch {
        failed();
        return;
      }
      const hls = new window.Hls();
      hls.on(window.Hls.Events.ERROR, (_, d) => d.fatal && failed());
      hls.loadSource(button.dataset.clip);
      hls.attachMedia(video);
      new MutationObserver((_, obs) => {
        if (!video.isConnected) {
          hls.destroy();
          obs.disconnect();
        }
      }).observe(video.parentNode, { childList: true });
    }
    video.play().catch(() => {});
  });
})();
