// "Nagranie" on a sitting's agenda (templates/sitting.html): the debate on an
// item, cut from the Sejm's stream of that day (from the first speech on the
// item to the last), played under the item with hls.js, loaded on the first
// click (an iPhone plays HLS itself); and each speech in an item's list of
// speakers (▶ by the name). One video at a time.
(() => {
  const script = document.currentScript;
  let current = null;
  const loadHls = () => window.Hls ? Promise.resolve() : new Promise((resolve, reject) => {
    const s = Object.assign(document.createElement("script"), { src: script.dataset.hls, onload: resolve, onerror: reject });
    document.head.append(s);
  });

  // a speech in an item's list of speakers: "video,start,stop" (seconds), the
  // videos listed on the list's <details>
  const speechClip = (button) => {
    const [i, start, stop] = button.dataset.c.split(",").map(Number);
    const bases = JSON.parse(button.closest("details[data-bases]").dataset.bases);
    return `${bases[i]}?start=${start * 1000}&stop=${stop * 1000}`;
  };

  document.addEventListener("click", async (e) => {
    const button = e.target.closest("button[data-clip], button[data-c]");
    if (!button) return;
    current?.remove();   // the hls.js instance goes with its video
    document.querySelector(".sp-playing")?.classList.remove("sp-playing");
    const video = Object.assign(document.createElement("video"), { controls: true, playsInline: true, className: "clip-video" });
    const failed = () => video.replaceWith(Object.assign(document.createElement("p"), { className: "muted", textContent: script.dataset.failed }));
    let clip;
    if (button.dataset.c) {
      // a speech: above the list of speakers, which stays as it is, its row marked
      clip = speechClip(button);
      button.closest("details").querySelector("summary").after(video);
      button.closest("li").classList.add("sp-playing");
    } else {
      // the whole debate: under the item's line of links
      clip = button.dataset.clip;
      button.closest("p").after(video);
    }
    current = video;
    // hls.js wherever it can run; the browser's own HLS where it cannot (iPhone)
    if (!window.MediaSource && video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = clip;
    } else {
      try {
        await loadHls();
      } catch {
        failed();
        return;
      }
      const hls = new window.Hls();
      hls.on(window.Hls.Events.ERROR, (_, d) => d.fatal && failed());
      hls.loadSource(clip);
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
