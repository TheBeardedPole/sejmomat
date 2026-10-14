// Votes by sitting on MP and club pages (templates/_breakdown.html). Each
// sitting is one row of figures; a click on it loads that sitting's votes
// from two files shared by both languages: what was voted on, the outcome
// and every club's line (dane/posiedzenia/N.json) and the ballots
// (dane/glosy/N.json). "#posiedzenie-N" in the address opens that sitting.
(() => {
  const table = document.querySelector(".by-sitting");
  if (!table) return;
  const { kind, id, votes, ballots, mps, root } = table.dataset;
  const L = JSON.parse(table.dataset.labels);
  // a club page lists its current members, to tag those who have left since
  const current = table.dataset.current !== undefined ? new Set(table.dataset.current.split(",").filter(Boolean).map(Number)) : null;
  const EN = document.documentElement.lang === "en";
  const CODES = ["Y", "N", "A", "X"];
  const NO_LINE = new Set(["niez.", "?"]); // MPs outside any club have no line to follow

  const el = (tag, props = {}, children = []) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children.filter((c) => c !== null && c !== undefined && c !== false));
    return node;
  };
  const json = (url) => fetch(url).then((r) => {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  });
  const loaded = new Map();
  let names = null;
  const load = (s) => {
    if (!loaded.has(s)) {
      loaded.set(s, Promise.all([json(votes.replace("{s}", s)), json(ballots.replace("{s}", s)),
        kind === "club" ? (names ??= json(mps)) : {}]));
    }
    return loaded.get(s);
  };

  // as club_slug() in sejmomat/build.py
  const clubPage = (club, s) => `${root}klub/${club.replace(/[^\p{L}\p{N}_-]/gu, "") || "klub"}.html#posiedzenie-${s}`;
  const mpPage = (mp, s) => `${root}posel/${mp}.html#posiedzenie-${s}`;
  const short = (text) => (text.length > 120 ? `${text.slice(0, 117)}…` : text);
  const voteCell = (s, v) => el("td", {}, [
    el("a", { href: `${root}glosowanie/${s}-${v.n}.html`, lang: "pl", textContent: v.t || v.a }),
    v.t && v.a ? el("div", { className: "snippet", lang: "pl", textContent: short(v.a) }) : null,
  ]);
  const outcomeCell = (v) => el("td", {}, [el("span", { className: `badge ${v.o}`, textContent: v.l[EN ? 1 : 0] })]);
  const lineNode = (club, line) => (line ? el("span", { className: `v-${line}`, textContent: L.line[line] })
    : el("span", { className: "muted", textContent: NO_LINE.has(club) ? "—" : L.split }));
  const th = (text, num) => el("th", { className: num ? "num" : "", textContent: text });
  const tableOf = (head, rows) => el("div", { className: "table-scroll" }, [el("table", {}, [
    el("thead", {}, [el("tr", {}, head)]), el("tbody", {}, rows)])]);
  const flag = (text) => el("span", { className: "badge warn", textContent: text });

  // An MP's sitting: every vote they could take part in, with their ballot
  // and their club's line; missed votes and votes against the line stand out
  // and can be shown alone.
  const mpVotes = (s, list, byVote) => {
    const mp = Number(id), rows = [];
    for (const v of list) {
      let club = null, code = null;
      for (const [c, groups] of Object.entries(byVote[v.n] || {})) {
        for (const k of CODES) if ((groups[k] || []).includes(mp)) [club, code] = [c, k];
      }
      if (!club) continue; // not an MP at the time of this vote
      const line = v.c[club];
      const rebel = Boolean(line) && code !== "X" && code !== line;
      rows.push(el("tr", { className: code === "X" ? "missed" : rebel ? "rebel" : "" }, [
        el("td", { className: "num", textContent: v.n }), voteCell(s, v), outcomeCell(v),
        el("td", { className: `v-${code}` }, [code === "X" ? flag(L.vote.X) : el("strong", { textContent: L.vote[code] })]),
        el("td", {}, [lineNode(club, line), " ",
          el("a", { className: "muted", href: clubPage(club, s), textContent: `(${club})` }), " ", rebel ? flag(L.rebel) : null]),
      ]));
    }
    if (!rows.length) return [el("p", { className: "muted", textContent: L.none })];
    const count = (cls) => rows.filter((tr) => tr.classList.contains(cls)).length;
    const buttons = [["", L.all, rows.length], ["missed", L.missed, count("missed")], ["rebel", L.rebel, count("rebel")]]
      .map(([cls, text, n]) => {
        const b = el("button", { type: "button", className: "chip", textContent: `${text} (${n})`, disabled: !n });
        b.setAttribute("aria-pressed", String(cls === ""));
        b.addEventListener("click", () => {
          for (const tr of rows) tr.hidden = Boolean(cls) && !tr.classList.contains(cls);
          for (const other of buttons) other.setAttribute("aria-pressed", String(other === b));
        });
        return b;
      });
    return [el("p", { className: "sitting-filter" }, buttons),
      tableOf([th(L.nr, true), th(L.voting), th(L.outcome), th(L.ballot), th(L.clubLine)], rows)];
  };

  // A club's sitting: first its MPs, those who missed most on top; then every
  // vote with the club's ballots, its line, and who broke it or did not vote.
  const clubVotes = (s, list, byVote, mpNames) => {
    const name = (mp) => mpNames[mp] ?? `#${mp}`;
    const people = (mps) => mps.flatMap((mp, i) => [i ? ", " : "", el("a", { href: mpPage(mp, s), textContent: name(mp) })]);
    const members = new Map(), rows = [];
    for (const v of list) {
      const groups = (byVote[v.n] || {})[id];
      if (!groups) continue; // the club did not exist, or had nobody in the chamber's records, at this vote
      const line = v.c[id], rebels = [];
      for (const code of CODES) {
        for (const mp of groups[code] || []) {
          const m = members.get(mp) || members.set(mp, { total: 0, missed: 0, rebel: 0 }).get(mp);
          m.total++;
          if (code === "X") m.missed++;
          else if (line && code !== line) { m.rebel++; rebels.push(mp); }
        }
      }
      const absent = groups.X || [];
      rows.push(el("tr", {}, [
        el("td", { className: "num", textContent: v.n }), voteCell(s, v), outcomeCell(v),
        ...CODES.slice(0, 3).map((k) => el("td", { className: `num v-${k}`, textContent: (groups[k] || []).length })),
        el("td", { className: "num v-X" }, [absent.length
          ? el("details", {}, [el("summary", { textContent: absent.length }), el("div", { className: "who" }, people(absent))])
          : "0"]),
        el("td", {}, [lineNode(id, line)]),
        el("td", { className: "who" }, people(rebels)),
      ]));
    }
    if (!rows.length) return [el("p", { className: "muted", textContent: L.none })];
    const memberRows = [...members].sort((a, b) => b[1].missed - a[1].missed || name(a[0]).localeCompare(name(b[0]), "pl"))
      // the row stands out when at least half of the sitting's votes were missed
      .map(([mp, m]) => el("tr", { className: m.missed * 2 >= m.total ? "missed" : "" }, [
        el("td", {}, [el("a", { href: mpPage(mp, s), textContent: name(mp) }), " ", m.missed === m.total ? flag(L.allMissed) : null,
          current && !current.has(mp) ? el("span", { className: "badge former", textContent: L.former }) : null]),
        el("td", { className: "num", textContent: m.total }),
        el("td", { className: "num" }, [m.missed ? el("strong", { className: "v-X", textContent: m.missed }) : "0"]),
        el("td", { className: "num", textContent: m.rebel }),
      ]));
    return [
      el("h3", { textContent: L.members }),
      tableOf([th(L.mp), th(L.votes, true), th(L.missed, true), th(L.rebel, true)], memberRows),
      el("h3", { textContent: L.votes }),
      tableOf([th(L.nr, true), th(L.voting), th(L.outcome), th(L.vote.Y, true), th(L.vote.N, true), th(L.short.A, true),
        th(L.short.X, true), th(L.clubLine), th(L.rebel)], rows),
    ];
  };

  // The row under a sitting's row that holds its votes, made on first use.
  const votesRow = (tr) => {
    const s = tr.dataset.s;
    let row = document.getElementById(`votes-${s}`);
    if (!row) {
      row = el("tr", { id: `votes-${s}`, className: "names-row", hidden: true }, [
        el("td", { colSpan: tr.children.length }, [el("div", { className: "sitting-votes" })])]);
      row.setAttribute("data-pagefind-ignore", "");
      tr.after(row);
      tr.querySelector(".club-toggle").setAttribute("aria-controls", row.id);
    }
    return row;
  };
  const toggle = async (tr, open) => {
    const button = tr.querySelector(".club-toggle");
    const row = votesRow(tr);
    const box = row.querySelector(".sitting-votes");
    button.setAttribute("aria-expanded", String(open));
    row.hidden = !open;
    if (!open || box.dataset.state) return;
    const s = tr.dataset.s;
    box.dataset.state = "loading";
    box.replaceChildren(el("p", { className: "muted", textContent: L.loading }));
    try {
      const [list, byVote, mpNames] = await load(s);
      box.replaceChildren(...(kind === "mp" ? mpVotes(s, list, byVote) : clubVotes(s, list, byVote, mpNames)));
      box.dataset.state = "done";
    } catch {
      loaded.delete(s); // the next click tries again
      delete box.dataset.state;
      box.replaceChildren(el("p", { className: "muted", textContent: L.failed }));
    }
  };
  for (const tr of table.querySelectorAll(".sitting-row")) {
    tr.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      toggle(tr, tr.querySelector(".club-toggle").getAttribute("aria-expanded") !== "true");
    });
  }
  const fromAddress = () => {
    const tr = /^#posiedzenie-\d+$/.test(location.hash) && document.getElementById(location.hash.slice(1));
    if (tr) toggle(tr, true);
  };
  window.addEventListener("hashchange", fromAddress);
  fromAddress();
})();
