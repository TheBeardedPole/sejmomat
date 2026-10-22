// Two votes side by side (templates/compare.html), from the Sejm's API, so
// any vote can be compared, also one taken since the last rebuild. Each
// side's choice can be flipped: in a motion to reject a bill "for" is
// against the bill, so it lines up with "against" in the vote on the whole
// bill. Flipped by default for motions to reject (not those about a Senate
// resolution, where "for" keeps the act). The choice is kept in the address:
// ?a=67-48&b=67-50, and &fa=1 / &fb=0 for a flip set by hand.
(() => {
  const box = document.getElementById("compare");
  if (!box) return;
  const L = JSON.parse(box.dataset.labels);
  const API = box.dataset.api, ROOT = box.dataset.root;
  const result = document.getElementById("cmp-result");
  const el = (tag, props = {}, ...children) => {
    const e = Object.assign(document.createElement(tag), props);
    e.append(...children.filter((c) => c !== null && c !== undefined && c !== ""));
    return e;
  };
  const CODE = { YES: "Y", NO: "N", ABSTAIN: "A" };   // anything else: did not vote
  const FLIP = { Y: "N", N: "Y", A: "A", X: "X" };
  const passed = (v) => v.majorityType === "SIMPLE_MAJORITY" ? v.yes > v.no : v.yes >= (v.majorityVotes || 0);
  const agenda = (v) => (v.title || "").replace(/^\s*Pkt\.?\s*\d+\.?\s*/, "").trim();
  const isRejection = (v) => /odrzuc/i.test(v.topic || "") && !/senatu/i.test(`${v.topic} ${v.title}`);
  const isFinal = (v) => /całością/i.test(v.topic || "");
  const lists = new Map();   // sitting -> votes (no ballots)
  const full = new Map();    // "s-n" -> vote with ballots
  const get = async (url) => {
    const r = await fetch(url);
    if (!r.ok) throw new Error(r.status);
    return r.json();
  };
  const listOf = (s) => lists.get(s) || lists.set(s, get(`${API}/${s}`).then((vs) => vs.sort((a, b) => a.votingNumber - b.votingNumber))).get(s);
  const voteOf = (s, n) => full.get(`${s}-${n}`) || full.set(`${s}-${n}`, get(`${API}/${s}/${n}`)).get(`${s}-${n}`);

  const q = new URLSearchParams(location.search);
  const parse = (x) => (x || "").match(/^(\d+)-(\d+)$/)?.slice(1).map(Number);
  const sides = {};
  for (const fs of box.querySelectorAll("fieldset[data-side]")) {
    const side = fs.dataset.side;
    sides[side] = { fs, s: fs.querySelector(".cmp-s"), v: fs.querySelector(".cmp-v"), flip: fs.querySelector(".cmp-flip"),
                    meta: fs.querySelector(".meta"), pick: parse(q.get(side)), flipSet: q.has(`f${side}`) ? q.get(`f${side}`) === "1" : null };
  }

  const fillSelect = async (side, keep) => {
    const x = sides[side], s = Number(x.s.value);
    x.v.replaceChildren(el("option", { value: "", textContent: L.loading }));
    let votes;
    try {
      votes = await listOf(s);
    } catch {
      x.v.replaceChildren(el("option", { value: "", textContent: L.error }));
      return;
    }
    x.v.replaceChildren(el("option", { value: "", textContent: L.pick }), ...votes.map((v) => el("option", {
      value: v.votingNumber, textContent: `${v.votingNumber}. ${v.topic || ""} — ${agenda(v).slice(0, 90)}`,
    })));
    if (keep && votes.some((v) => v.votingNumber === keep)) x.v.value = keep;
  };

  // the other key vote on the same item: the whole bill for a motion to reject, and the other way round
  const suggest = async () => {
    const a = sides.a, b = sides.b;
    if (b.pick || !a.pick) return;
    const votes = await listOf(a.pick[0]).catch(() => []);
    const va = votes.find((v) => v.votingNumber === a.pick[1]);
    if (!va) return;
    const same = votes.filter((v) => v.votingNumber !== va.votingNumber && agenda(v) === agenda(va));
    const pick = (isRejection(va) ? same.find(isFinal) : same.find(isRejection)) || same.find(isFinal);
    if (pick) b.pick = [a.pick[0], pick.votingNumber];
  };

  const label = (code, flipped) => {
    if (code === "X") return L.X;
    const raw = L[code];
    if (code === "A") return raw;
    const meaning = (flipped ? FLIP[code] : code) === "Y" ? L.forBill : L.againstBill;
    return el("span", {}, raw, " ", el("span", { className: "raw" }, `(${meaning})`));
  };

  const compare = async () => {
    const a = sides.a, b = sides.b;
    const na = Number(a.v.value), nb = Number(b.v.value), sa = Number(a.s.value), sb = Number(b.s.value);
    const url = new URL(location.href);
    url.search = "";
    if (na) url.searchParams.set("a", `${sa}-${na}`);
    if (nb) url.searchParams.set("b", `${sb}-${nb}`);
    for (const side of ["a", "b"]) if (sides[side].flipSet !== null) url.searchParams.set(`f${side}`, sides[side].flip.checked ? "1" : "0");
    history.replaceState(null, "", url);
    if (!na || !nb) {
      result.replaceChildren();
      return;
    }
    result.replaceChildren(el("p", { className: "muted" }, L.loading));
    let va, vb;
    try {
      [va, vb] = await Promise.all([voteOf(sa, na), voteOf(sb, nb)]);
    } catch {
      result.replaceChildren(el("p", { className: "muted" }, L.error));
      return;
    }
    // a flip not set by hand follows the kind of vote
    for (const [x, v] of [[a, va], [b, vb]]) if (x.flipSet === null) x.flip.checked = isRejection(v);
    for (const [x, v, s, n] of [[a, va, sa, na], [b, vb, sb, nb]]) {
      x.meta.replaceChildren(el("span", { className: `badge ${passed(v) ? "adopted" : "rejected"}`, textContent: passed(v) ? L.passed : L.rejected }),
        ` ${v.yes} / ${v.no} / ${v.abstain} · ${v.date.slice(0, 10)} · `, el("a", { href: `${ROOT}glosowanie/${s}-${n}.html`, textContent: L.page }),
        el("br"), el("span", { lang: "pl" }, agenda(v)));
    }
    const fa = a.flip.checked, fb = b.flip.checked;
    const ballots = (v, flip) => new Map((v.votes || []).map((x) => {
      const raw = CODE[x.vote] || "X";
      return [x.MP, { raw, code: flip ? FLIP[raw] : raw, club: x.club, name: `${x.firstName} ${x.lastName}` }];
    }));
    const A = ballots(va, fa), B = ballots(vb, fb);
    const rows = [], clubs = new Map();
    for (const [mp, xb] of B) {
      const xa = A.get(mp);
      if (!xa) continue;
      const state = xa.code === "X" || xb.code === "X" ? "missing" : xa.code === xb.code ? "same" : "different";
      const c = clubs.get(xb.club) || { same: 0, different: 0, missing: 0 };
      c[state]++;
      clubs.set(xb.club, c);
      if (state === "different") rows.push({ mp, xa, xb });
    }
    const total = (k) => [...clubs.values()].reduce((t, c) => t + c[k], 0);
    const share = (c) => c.same + c.different ? `${((c.same / (c.same + c.different)) * 100).toFixed(1).replace(".", ",")}%` : "—";
    rows.sort((x, y) => x.xb.club.localeCompare(y.xb.club) || x.xb.name.split(" ").at(-1).localeCompare(y.xb.name.split(" ").at(-1)));
    result.replaceChildren(
      el("div", { className: "grid", style: "margin-top:16px" },
        el("div", { className: "card stat" }, el("b", { textContent: total("same") }), L.same),
        el("div", { className: "card stat" }, el("b", { className: "v-N", textContent: total("different") }), L.different),
        el("div", { className: "card stat" }, el("b", { className: "v-X", textContent: total("missing") }), L.missing)),
      el("p", { className: "note" }, L.note),
      el("h2", {}, L.clubs),
      el("div", { className: "table-scroll" }, el("table", { id: "cmp-clubs" },
        el("thead", {}, el("tr", {}, el("th", {}, L.club), el("th", {}, L.same), el("th", {}, L.different), el("th", {}, L.missing), el("th", {}, L.sameShare))),
        el("tbody", {}, ...[...clubs].sort((x, y) => (y[1].same + y[1].different + y[1].missing) - (x[1].same + x[1].different + x[1].missing))
          .map(([club, c]) => el("tr", {}, el("td", {}, club), el("td", { textContent: c.same }),
            el("td", { className: c.different ? "v-N" : "", textContent: c.different }), el("td", { className: "v-X", textContent: c.missing }),
            el("td", { textContent: share(c) })))))),
      el("h2", {}, `${L.mps} (${rows.length})`),
      rows.length
        ? el("div", { className: "table-scroll" }, el("table", { className: "cmp-diff" },
          el("thead", {}, el("tr", {}, el("th", {}, L.mp), el("th", {}, L.club), el("th", {}, `${L.a} (${na})`), el("th", {}, `${L.b} (${nb})`))),
          el("tbody", {}, ...rows.map(({ mp, xa, xb }) => el("tr", {},
            el("td", {}, el("a", { href: `${ROOT}posel/${mp}.html`, textContent: xb.name })),
            el("td", {}, xa.club === xb.club ? xb.club : `${xa.club} → ${xb.club}`),
            el("td", { className: `v-${xa.raw}` }, label(xa.raw, fa)),
            el("td", { className: `v-${xb.raw}` }, label(xb.raw, fb)))))))
        : el("p", { className: "muted" }, L.none),
    );
  };

  (async () => {
    await suggest();
    for (const side of ["a", "b"]) {
      const x = sides[side];
      x.s.value = x.pick?.[0] || sides.a.pick?.[0] || box.dataset.latest;
      await fillSelect(side, x.pick?.[1]);
      x.s.addEventListener("change", async () => { await fillSelect(side); compare(); });
      x.v.addEventListener("change", () => { x.flipSet = null; compare(); });
      x.flip.addEventListener("change", () => { x.flipSet = x.flip.checked; compare(); });
    }
    compare();
  })();
})();
