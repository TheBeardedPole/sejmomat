// Votes taken since the page was built, straight from the Sejm's API: the
// site is rebuilt only now and then, the API has each vote about a minute
// after it is taken. The element with data-live-votes (templates/_cards.html,
// new_votes; the sittings list) says which sitting and the last vote the page
// has; on the page:
//   .vote-list        the sitting's votes: new ones are added at the end as on
//                     the page (grouped by agenda item, under the last heading
//                     when it is the same item), each linked to its page here,
//                     drawn from the API until the next rebuild
//                     (glosowanie-na-zywo.html, static/livevote.js)
//   .new-votes        a note on them (and the list itself where the page has
//                     no .vote-list: the upcoming sitting page)
//   [data-live-count] the number of votes, [data-live-amend] of votes on
//                     amendments and motions (data-base: the page's own count)
//   [data-live-last]  the last voting day; [data-live-row] shown once there is a vote
// On the sitting's days the API is asked for the next vote every 30 seconds.
(() => {
  const src = document.querySelector("[data-live-votes]");
  if (!src) return;
  const D = src.dataset;
  const L = JSON.parse(D.labels || "{}");
  const box = document.querySelector(".new-votes");
  const list = document.querySelector(".vote-list") || box;
  const after = Number(D.after) || 0;
  const today = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw" }).format(new Date());
  const live = (D.dates || "").split(",").includes(today);
  const isAmendment = (v) => /poprawk|mniejszości/i.test(v.topic || "");
  const day = new Intl.DateTimeFormat(document.documentElement.lang === "en" ? "en-GB" : "pl", { day: "numeric", month: "long", year: "numeric" });
  const el = (tag, props = {}, ...children) => {
    const e = Object.assign(document.createElement(tag), props);
    e.append(...children.filter((c) => c !== null && c !== undefined && c !== ""));
    return e;
  };
  const passed = (v) => v.majorityType === "SIMPLE_MAJORITY" ? v.yes > v.no : v.yes >= (v.majorityVotes || 0);
  // a vote's agenda item as the page heads it (sejmomat/model.py, agenda_label)
  const agendaOf = (v) => (v.title || "").replace(/^\s*Pkt\.?\s*\d+\.?\s*/, "")
    .replace(/\s*\(\s*druk\w*\s+nr[^)]*\)/g, "").replace(/\s*-\s*trzecie czytanie\s*$/, "").trim();
  // the votes tab's count on a sitting page (templates/_tabs.html)
  const tab = document.querySelector('.tab-bar a[aria-controls="glosowania"] .tab-count');
  const tabBase = Number(tab?.textContent) || 0;
  let votes = [], shown = 0;

  // one vote as the page's own rows show it (templates/_macros.html, vote_row)
  const row = (v) => el("tr", { id: `glosowanie-${v.votingNumber}` },
    el("td", { className: "num", style: "width:3.5em" },
      el("a", { href: `${D.root}glosowanie-na-zywo.html?posiedzenie=${v.sitting}&nr=${v.votingNumber}`, textContent: v.votingNumber })),
    el("td", { lang: "pl" }, v.topic || ""),
    el("td", { style: "width:9em" }, el("span", { className: `badge ${passed(v) ? "adopted" : "rejected"}`, textContent: passed(v) ? L.passed : L.rejected })),
    el("td", { className: "num", style: "width:8em" }, el("span", { className: "counts" },
      el("span", { className: "y", textContent: v.yes }), " / ", el("span", { className: "n", textContent: v.no }),
      " / ", el("span", { className: "a", textContent: v.abstain }))));

  const render = () => {
    const fresh = votes.filter((v) => v.votingNumber > after);
    for (const e of document.querySelectorAll("[data-live-count]")) e.textContent = Number(e.dataset.base || 0) + fresh.length;
    for (const e of document.querySelectorAll("[data-live-amend]")) e.textContent = Number(e.dataset.base || 0) + fresh.filter(isAmendment).length;
    if (tab) tab.textContent = tabBase + fresh.length;
    if (!fresh.length) return;
    for (const e of document.querySelectorAll("[data-live-last]")) e.textContent = day.format(new Date(`${fresh.at(-1).date.slice(0, 10)}T12:00:00`));
    for (const e of document.querySelectorAll("[data-live-row]")) e.hidden = false;
    if (!list) return;
    if (box) {
      box.hidden = false;
      if (!box.querySelector(".new-votes-note")) {
        box.prepend(el("p", { className: "note new-votes-note" }, L.note));
        // where the votes go into the box itself (the upcoming sitting page), with a heading
        if (list === box) box.prepend(el("h2", {}, L.heading));
      }
    }
    // only the votes not yet on the page, under the last heading when it is the same agenda item
    for (const v of fresh.slice(shown)) {
      const sections = list.querySelectorAll(":scope > section.agenda");
      const last = sections[sections.length - 1];
      let tbody = last && last.querySelector("h2")?.textContent.trim() === agendaOf(v) ? last.querySelector("tbody") : null;
      if (!tbody) {
        tbody = el("tbody");
        list.append(el("section", { className: "agenda" }, el("h2", { className: "h3", lang: "pl" }, agendaOf(v) || L.procedural),
          el("div", { className: "table-scroll" }, el("table", {}, tbody))));
      }
      tbody.append(row(v));
    }
    shown = fresh.length;
  };

  const next = async () => {
    // votes often come seconds apart: ask until there is no next one
    for (;;) {
      const r = await fetch(`${D.liveVotes}/${(votes.at(-1)?.votingNumber || after) + 1}`).catch(() => null);
      if (!r?.ok) return;
      votes.push(await r.json());
      render();
    }
  };
  (async () => {
    try {
      votes = (await (await fetch(D.liveVotes)).json()).sort((a, b) => a.votingNumber - b.votingNumber);
    } catch {
      return;
    }
    render();
    if (live) setInterval(next, 30 * 1000);
  })();
})();
