// Click a <th data-sort> to sort its table; numeric cells use data-v.
document.querySelectorAll("th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => {
    const table = th.closest("table");
    const idx = [...th.parentNode.children].indexOf(th);
    const body = table.tBodies[0];
    const asc = th.dataset.dir !== "asc";
    th.dataset.dir = asc ? "asc" : "desc";
    const key = (tr) => {
      const td = tr.children[idx];
      const v = td.dataset.v ?? td.textContent.trim();
      return th.dataset.sort === "num" ? parseFloat(v) || 0 : v.toLowerCase();
    };
    const rows = [...body.rows].sort((a, b) => {
      const x = key(a), y = key(b);
      return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1);
    });
    rows.forEach((r) => body.appendChild(r));
  });
});

// Club rows on a voting page expand to the named votes of that club. The
// ballots live in one JSON file per sitting (shared by both languages) and
// are loaded on first use; the whole row is clickable.
const clubsTable = document.querySelector(".clubs-table");
if (clubsTable) {
  const { ballots, mps, vote, root } = clubsTable.dataset;
  const labels = JSON.parse(clubsTable.dataset.labels);
  let data = null;
  const load = () =>
    data ??= Promise.all([fetch(ballots).then((r) => r.json()), fetch(mps).then((r) => r.json())]);

  const el = (tag, props = {}, children = []) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children);
    return node;
  };

  const fill = async (tr, cell) => {
    const [byVote, names] = await load();
    const groups = byVote[vote]?.[tr.dataset.club] ?? {};
    const rebels = new Set(tr.dataset.rebels.split(",").filter(Boolean).map(Number));
    for (const code of ["Y", "N", "A", "X"]) {
      const ids = groups[code];
      if (!ids?.length) continue;
      const items = ids.map((id) => el("li", rebels.has(id) ? { className: "rebel", title: labels.rebel } : {}, [
        el("a", { href: `${root}posel/${id}.html`, textContent: names[id] ?? `#${id}` }),
      ]));
      cell.append(el("div", {}, [
        el("p", { className: `v-${code}` }, [el("strong", { textContent: labels[code] }), ` (${ids.length})`]),
        el("ul", {}, items),
      ]));
    }
  };

  clubsTable.querySelectorAll(".club-row").forEach((tr) => {
    const btn = tr.querySelector(".club-toggle");
    const row = document.getElementById(btn.getAttribute("aria-controls"));
    const cell = row.querySelector(".name-cols");
    tr.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      const open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(open));
      row.hidden = !open;
      if (open && !cell.childElementCount) fill(tr, cell);
    });
  });
}

// Adopted-amendments page: filter rows by proposer / against recommendation.
const proposerFilter = document.getElementById("proposer-filter");
const againstFilter = document.getElementById("against-filter");
if (proposerFilter) {
  const apply = () => {
    const who = proposerFilter.value;
    const against = againstFilter.checked;
    document.querySelectorAll("#adopted-table tr").forEach((tr) => {
      const clubs = (tr.dataset.proposer || "").split("|");
      tr.hidden = (who && !clubs.includes(who)) || (against && tr.dataset.against !== "1");
    });
  };
  proposerFilter.addEventListener("change", apply);
  againstFilter.addEventListener("change", apply);
}
