// An MP's work in the reader's topics, at the top of the MP's page, when it is opened
// from the home page's suggested MPs (posel/N.html?tematy=zdrowie,edukacja; static/home.js):
// their roles in the topics' committees, interpellations to the ministers concerned and
// bills in the topics, from dane/zainteresowania.json (sejmomat/interests.py). Each topic
// is a box to switch off; with none left, or without ?tematy, the panel stays hidden.
(() => {
  const box = document.getElementById("w-twoich-tematach");
  const wanted = new URLSearchParams(location.search).get("tematy");
  if (!box || !wanted) return;
  const L = JSON.parse(box.dataset.labels);
  const ROOT = box.dataset.root;
  const MP = Number(box.dataset.mp);
  const LANG = document.documentElement.lang === "en" ? "en" : "pl";
  const el = (tag, props = {}, ...children) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children.flat().filter((c) => c !== null && c !== undefined && c !== false));
    return node;
  };
  const link = (href, text) => el("a", { href, textContent: text });
  const cap = (s) => s && `${s[0].toUpperCase()}${s.slice(1)}`;

  fetch(box.dataset.src).then((r) => {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then((data) => {
    const nameOf = (id) => (data.interests.find((i) => i.id === id) || {})[LANG] || id;
    // the topics asked for in which this MP has something to show
    const topics = wanted.split(",").filter((id) => (data.suggested[id] || []).some((row) => row.id === MP));
    const on = new Set(topics);
    const list = el("ul", { className: "mp-why" });
    const empty = el("p", { className: "muted", textContent: L.none });
    const render = () => {
      // one line per committee, per group of addressees and per topic's bills, as on the home page
      const seen = new Set(), items = [];
      for (const id of topics.filter((t) => on.has(t))) {
        const row = data.suggested[id].find((x) => x.id === MP);
        for (const w of row.why) {
          const key = w.k === "committee" ? `c:${w.code}` : w.k === "questions" ? `q:${w.to.join("|")}` : `b:${w.root}:${id}`;
          if (seen.has(key)) continue;
          seen.add(key);
          if (w.k === "committee") {
            items.push([0, el("li", {}, `${cap(w.fn || L.member)} · `, link(`${ROOT}komisja/${w.code}.html`, data.committees[w.code] || w.code))]);
          } else if (w.k === "questions") {
            items.push([2, el("li", {}, link("#interpelacje", L.questions.replace("{n}", w.n).replace("{recent}", w.recent)), ` (${w.to.join(", ")})`)]);
          } else {
            items.push([1, el("li", {}, `${L.bills.replace("{n}", w.n).replace("{topic}", nameOf(id))} · `,
              link(`${ROOT}ustawa/${w.root}.html`, data.bills[w.root] || w.root))]);
          }
        }
      }
      list.replaceChildren(...items.sort((a, b) => a[0] - b[0]).map(([, li]) => li));
      empty.hidden = items.length > 0;
      list.hidden = !items.length;
    };
    const chips = topics.map((id) => {
      const b = el("button", { type: "button", className: "toggle-chip", textContent: nameOf(id) });
      b.setAttribute("aria-pressed", "true");
      b.addEventListener("click", () => {
        if (on.has(id)) on.delete(id);
        else on.add(id);
        b.setAttribute("aria-pressed", String(on.has(id)));
        render();
      });
      return b;
    });
    const close = el("button", { type: "button", className: "icon-btn topic-close", title: L.close, ariaLabel: L.close });
    close.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';
    close.addEventListener("click", () => {
      box.hidden = true;
      history.replaceState(null, "", location.pathname);
    });
    box.replaceChildren(
      el("div", { className: "topic-panel-head" }, el("h2", { id: "w-twoich-tematach-h", textContent: L.title }), close),
      el("p", { className: "muted", textContent: topics.length ? L.text : L.none }),
      topics.length ? el("div", { className: "interest-chips" }, chips) : null,
      topics.length ? list : null, topics.length ? empty : null);
    render();
    box.hidden = false;
    if (location.hash === "#w-twoich-tematach") box.scrollIntoView({ block: "start" });
  }).catch(() => {
    box.replaceChildren(el("p", { className: "muted", textContent: L.failed }));
    box.hidden = false;
  });
})();
