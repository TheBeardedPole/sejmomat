// A vote taken since the last rebuild (templates/live_vote.html), drawn from
// the Sejm's API in the layout of a regular voting page: the result, how each
// club voted (expanding to names), the club line and who broke it. The line
// is worked out as on the site (sejmomat/analysis.py): the most common choice
// among a club's members who voted, if more than half of them and at least
// three voted; independents have none. Once the site is rebuilt, the regular
// page exists and is linked.
(() => {
  const box = document.getElementById("live-vote");
  if (!box) return;
  const L = JSON.parse(box.dataset.labels), M = JSON.parse(box.dataset.majorities), slugs = JSON.parse(box.dataset.clubs);
  const ROOT = box.dataset.root;
  const q = new URLSearchParams(location.search);
  const sitting = Number(q.get("posiedzenie")), number = Number(q.get("nr"));
  const el = (tag, props = {}, ...children) => {
    const e = Object.assign(document.createElement(tag), props);
    e.append(...children.filter((c) => c !== null && c !== undefined && c !== ""));
    return e;
  };
  const CODE = { YES: "Y", NO: "N", ABSTAIN: "A" };   // anything else: did not vote
  const MIN_CLUB_VOTERS = 3, NO_CLUB = new Set(["niez.", "?"]);
  const passed = (v) => v.majorityType === "SIMPLE_MAJORITY" ? v.yes > v.no : v.yes >= (v.majorityVotes || 0);
  const date = (iso) => new Intl.DateTimeFormat(document.documentElement.lang === "en" ? "en-GB" : "pl",
    { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
  const fail = () => box.replaceChildren(el("p", { className: "muted" }, L.missing));

  const render = (v) => {
    // ballots by club, and each club's line
    const clubs = new Map();
    for (const b of v.votes || []) {
      const c = clubs.get(b.club) || { Y: [], N: [], A: [], X: [] };
      c[CODE[b.vote] || "X"].push(b);
      clubs.set(b.club, c);
    }
    const rows = [...clubs].map(([club, c]) => {
      const cast = c.Y.length + c.N.length + c.A.length;
      const top = ["Y", "N", "A"].sort((a, b) => c[b].length - c[a].length)[0];
      const line = !NO_CLUB.has(club) && cast >= MIN_CLUB_VOTERS && c[top].length * 2 > cast ? top : null;
      const rebels = line ? ["Y", "N", "A"].filter((k) => k !== line).flatMap((k) => c[k].map((b) => [b, k])) : [];
      return { club, c, total: cast + c.X.length, cast, line, share: line ? c[line].length / cast : 0, rebels };
    }).sort((a, b) => b.total - a.total);
    const name = (b) => `${b.firstName} ${b.lastName}`;
    const mpLink = (b) => el("a", { href: `${ROOT}posel/${b.MP}.html`, textContent: name(b) });
    const clubLink = (club) => slugs[club] ? el("a", { href: `${ROOT}klub/${slugs[club]}.html`, textContent: club }) : club;
    const title = (v.title || "").replace(/^\s*Pkt\.?\s*\d+\.?\s*/, "");
    document.title = `${(v.topic || title).replace(/^./, (x) => x.toUpperCase())} · Sejmomat`;

    const table = el("table", { className: "clubs-table" },
      el("thead", {}, el("tr", {}, el("th", {}, L.club), el("th", { className: "num" }, L.yes), el("th", { className: "num" }, L.no),
        el("th", { className: "num" }, L.abstainShort), el("th", { className: "num" }, L.absentShort), el("th", {}, L.line), el("th"))));
    const tbody = el("tbody");
    rows.forEach((r, i) => {
      const names = el("tr", { className: "names-row", hidden: true, id: `names-${i}` }, el("td", { colSpan: 7 },
        el("div", { className: "muted" }, clubLink(r.club)),
        el("div", { className: "name-cols" }, ...["Y", "N", "A", "X"].filter((k) => r.c[k].length).map((k) => el("div", {},
          el("p", { className: `v-${k}` }, el("strong", { textContent: L[k] }), ` (${r.c[k].length})`),
          el("ul", {}, ...r.c[k].map((b) => el("li", r.line && k !== "X" && k !== r.line ? { className: "rebel" } : {}, mpLink(b)))))))));
      const toggle = el("button", { type: "button", className: "club-toggle", textContent: r.club, ariaExpanded: "false" });
      toggle.setAttribute("aria-controls", names.id);
      const bar = el("div", { className: "bar" }, ...["Y", "N", "A", "X"].map((k) =>
        el("span", { className: k, style: `width:${r.total ? r.c[k].length / r.total * 100 : 0}%` })));
      const row = el("tr", { className: "club-row" }, el("td", {}, toggle),
        ...["Y", "N", "A", "X"].map((k) => el("td", { className: `num v-${k}`, textContent: r.c[k].length })),
        el("td", {}, r.line ? el("span", {}, L[`line${r.line}`], " ", el("span", { className: "muted" }, `(${(r.share * 100).toFixed(1).replace(".", ",")}%)`))
          : el("span", { className: "muted" }, NO_CLUB.has(r.club) ? "—" : L.split)),
        el("td", {}, bar));
      row.addEventListener("click", (e) => {
        if (e.target.closest("a")) return;
        const open = toggle.getAttribute("aria-expanded") !== "true";
        toggle.setAttribute("aria-expanded", String(open));
        names.hidden = !open;
      });
      tbody.append(row, names);
    });
    table.append(tbody);

    const rebels = rows.flatMap((r) => r.rebels.map(([b, k]) => ({ b, k, club: r.club, line: r.line })))
      .sort((a, b) => a.club.localeCompare(b.club) || a.b.lastName.localeCompare(b.b.lastName));
    box.replaceChildren(
      el("div", { className: "crumbs" }, el("a", { href: `${ROOT}posiedzenie/${sitting}.html`, textContent: `${sitting}. ${L.sitting}` }),
        ` · ${L.vote} ${v.votingNumber} · ${date(v.date)}`),
      el("h1", { lang: "pl" }, (v.topic || title).replace(/^./, (x) => x.toUpperCase())),
      el("p", { className: "muted", lang: "pl" }, title),
      el("p", { className: "note" }, L.note),
      el("p", { className: "compare-link" }, (() => {
        const a = el("a", { className: "btn2", href: `${ROOT}porownaj-glosowania.html?a=${sitting}-${number}` });
        a.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 8h14l-4-4"/><path d="M20 16H6l4 4"/></svg>';   // fixed markup: the icon
        a.append(L.compare);
        return a;
      })()),
      el("div", { className: "card" },
        el("p", {}, el("span", { className: `badge ${passed(v) ? "adopted" : "rejected"}`, textContent: passed(v) ? L.passed : L.rejected })),
        el("div", { className: "grid" },
          el("div", { className: "stat" }, el("b", { className: "v-Y", textContent: v.yes }), L.yes),
          el("div", { className: "stat" }, el("b", { className: "v-N", textContent: v.no }), L.no),
          el("div", { className: "stat" }, el("b", { className: "v-A", textContent: v.abstain }), L.abstain),
          el("div", { className: "stat" }, el("b", { className: "v-X", textContent: v.notParticipating }), L.absent)),
        el("p", { className: "note" }, `${L.majority}: ${M[v.majorityType] || v.majorityType}`,
          v.majorityType !== "SIMPLE_MAJORITY" ? ` (${v.majorityVotes} ${L.votesWord})` : "", ".")),
      el("h2", {}, L.clubs),
      el("p", { className: "muted" }, L.click),
      el("div", { className: "table-scroll" }, table),
      el("h2", {}, `${L.rebels} (${rebels.length})`),
      rebels.length
        ? el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, L.mp), el("th", {}, L.club), el("th", {}, L.ballot), el("th", {}, L.clubLine))),
          el("tbody", {}, ...rebels.map((x) => el("tr", {}, el("td", {}, mpLink(x.b)), el("td", {}, x.club),
            el("td", { className: `v-${x.k}`, textContent: L[x.k] }), el("td", { className: `v-${x.line}`, textContent: L[`line${x.line}`] })))))
        : el("p", { className: "muted" }, L.noRebels),
    );
  };

  (async () => {
    if (!sitting || !number) return fail();
    // the regular page, once the site has it
    const regular = `${ROOT}glosowanie/${sitting}-${number}.html`;
    if ((await fetch(regular, { method: "HEAD" }).catch(() => null))?.ok) {
      location.replace(regular);
      return;
    }
    const r = await fetch(`${box.dataset.api}/${sitting}/${number}`).catch(() => null);
    if (!r?.ok) return fail();
    render(await r.json());
  })();
})();
