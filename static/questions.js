// The rest of an MP's interpellations and written questions
// (templates/_questions.html): the page shows the latest ones, a click
// loads the whole list (dane/pytania/<id>.json) into the same table.
(() => {
  const button = document.querySelector(".questions-more");
  if (!button) return;
  const L = JSON.parse(button.dataset.labels);
  const day = new Intl.DateTimeFormat(L.lang === "en" ? "en-US" : "pl", { day: "numeric", month: "long", year: "numeric" });
  const el = (tag, props = {}, children = []) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children.filter((c) => c !== null && c !== undefined));
    return node;
  };
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const badge = (cls, text) => el("span", { className: `badge ${cls}`.trim(), textContent: text });
  // as status() in the template
  const status = (q) => q.a ? badge(q.l ? "warn" : "adopted", `${L.after} ${q.days} ${L.d}${q.l ? ` · ${L.late}` : ""}`)
    : q.o ? badge("rejected", L.overdue) : q.p ? badge("warn", L.prolonged) : badge("", L.waiting);
  const row = (q) => {
    const title = q.t.replace("Interpelacja w sprawie ", "W sprawie ").replace("Zapytanie w sprawie ", "W sprawie ");
    return el("tr", {}, [
      el("td", { style: "white-space:nowrap", textContent: q.d ? day.format(new Date(`${q.d}T12:00:00`)) : "" }),
      el("td", {}, [el("span", { className: "muted", textContent: `${L[q.k]} ${q.n}` }), el("br"),
        q.w ? el("a", { href: q.w, target: "_blank", rel: "noopener", lang: "pl", textContent: title }) : el("span", { lang: "pl", textContent: title })]),
      el("td", { lang: "pl", textContent: q.to.map(cap).join(", ") }),
      el("td", {}, [status(q)]),
    ]);
  };
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      const r = await fetch(button.dataset.src);
      if (!r.ok) throw new Error(r.status);
      const all = await r.json();
      const body = button.closest("section").querySelector("table.questions tbody");
      body.replaceChildren(...all.map(row));
      button.parentElement.remove();
      // the search box applies to the whole list now
      button.closest("section")?.querySelector("input[data-filter]")?.dispatchEvent(new Event("input"));
    } catch {
      button.disabled = false;
      button.replaceWith(el("span", { className: "muted", textContent: L.failed }));
    }
  });
})();
