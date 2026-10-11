// Sejmdle: three daily games built on the Sejmomat JSON API (api/v1/games.json).
// No build step, no dependencies. Game logic is in pure functions at the top
// (also exported for tests under Node); the DOM code is below.
"use strict";

// ----------------------------------------------------------------- logic

const fold = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l").trim();

// FNV-1a: small stable hash for picking the daily puzzle.
const hash = (str) => {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  // final mixing (murmur3): without it, neighbouring days favour the same items
  h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b);
  h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35);
  h ^= h >>> 16;
  return h >>> 0;
};

// "Sprawozdanie Komisji o rządowym projekcie ustawy o ..." -> "Rządowy projekt ..." is
// not worth guessing at; just drop the report prefix.
const shortTitle = (title) => {
  const t = title.replace(/^(Poprawione )?[Ss]prawozdanie Komisji o\s+/, "").replace(/^:\s*-?\s*/, "");
  return t.charAt(0).toUpperCase() + t.slice(1);
};

// Items ordered by hash(day, game, item key). Adding new items to the data
// later in the day rarely changes who comes first, unlike "index = seed % n".
const dailyOrder = (items, key, day, game) =>
  items.map((it) => [hash(`${day}|${game}|${key(it)}`), it]).sort((a, b) => a[0] - b[0]).map((p) => p[1]);

const warsawDay = (now = new Date()) =>
  new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw" }).format(now); // YYYY-MM-DD

const age = (birthDate, day) => {
  const [y, m, d] = birthDate.split("-").map(Number);
  const [ty, tm, td] = day.split("-").map(Number);
  return ty - y - (tm < m || (tm === m && td < d) ? 1 : 0);
};

// Compare a guessed MP with the target. Each cell: {text, color, arrow}.
// green = same, yellow = close, grey = different; arrows point towards the target.
const compareMps = (guess, target, axis, day) => {
  const num = (g, t, closeBy, fmt) => ({
    text: fmt(g),
    color: g === t ? "green" : Math.abs(g - t) <= closeBy(t) ? "yellow" : "grey",
    arrow: g === t ? "" : t > g ? "↑" : "↓",
  });
  const gi = axis.indexOf(guess.club), ti = axis.indexOf(target.club);
  return {
    club: {
      text: guess.club,
      color: guess.club === target.club ? "green" : "grey",
      // target sits further left (←) or right (→) on the axis; unknown if either is off it
      arrow: guess.club === target.club || gi < 0 || ti < 0 ? "" : ti < gi ? "←" : "→",
    },
    district: {
      text: `${guess.district} (${guess.voivodeship})`,
      color: guess.districtNum === target.districtNum ? "green"
        : guess.voivodeship === target.voivodeship ? "yellow" : "grey",
      arrow: "",
    },
    age: num(age(guess.birthDate, day), age(target.birthDate, day), () => 5, (v) => `${v} lat`),
    electionVotes: num(guess.electionVotes, target.electionVotes, (t) => t * 0.25, (v) => v.toLocaleString("pl-PL")),
    turnout: num(Math.round(guess.turnout * 1000) / 10, Math.round(target.turnout * 1000) / 10, () => 3,
      (v) => `${v.toLocaleString("pl-PL")}%`),
    education: { text: guess.education || "—", color: guess.education === target.education ? "green" : "grey", arrow: "" },
    // first letter of the surname: ↑ the target's comes later in the alphabet, ↓ earlier
    initial: (() => {
      const g = surnameInitial(guess.name), t = surnameInitial(target.name);
      const order = g.localeCompare(t, "pl");
      return { text: g, color: order === 0 ? "green" : "grey", arrow: order === 0 ? "" : order < 0 ? "↑" : "↓" };
    })(),
  };
};

// "Agnieszka Wojciechowska van Heukelom" -> "W": the surname is everything after the first name.
const surnameInitial = (name) => (name.trim().split(/\s+/)[1] || name).charAt(0).toUpperCase();

const voteOf = (final, mpId) =>
  ["yes", "no", "abstain", "absent"].find((k) => (final.votes[k] || []).includes(mpId)) || null;

// "Who am I": the MP of the day and a few contested final votes they took part in.
const whoPuzzle = (data, day, count = 5) => {
  const mp = dailyOrder(data.mps, (m) => m.id, day, "kim")[0];
  const votes = [];
  for (const f of dailyOrder(data.finals, (f) => `${f.s}-${f.n}`, day, "kim-votes")) {
    const v = voteOf(f, mp.id);
    if (v && v !== "absent") votes.push({ final: f, vote: v });
    if (votes.length === count) break;
  }
  return { mp, votes };
};

if (typeof module !== "undefined") {
  module.exports = { fold, hash, dailyOrder, warsawDay, age, compareMps, voteOf, whoPuzzle, shortTitle, surnameInitial };
}

// ------------------------------------------------------------------- DOM

if (typeof document !== "undefined") (() => {
  const meta = (name, fallback) => document.querySelector(`meta[name="${name}"]`)?.content || fallback;
  const API = meta("sejmomat-api", "../api/v1/");
  const SITE = meta("sejmomat-site", "../");
  const PHOTO = (id) => `https://api.sejm.gov.pl/sejm/term10/MP/${id}/photo`;
  const DAY = warsawDay();
  // Puzzles are picked from the date plus this round number: raise ROUND to
  // deal everyone a fresh set. "?los=anything" in the address deals a private
  // extra set for testing, with its own saved progress.
  const ROUND = "3";
  const TEST = new URLSearchParams(location.search).get("los");
  const SEED = `${DAY}#${TEST ? `test-${TEST}` : ROUND}`;
  const MAX_GUESSES = 8, AMENDMENTS = 5;
  const VOTE_PL = { yes: "za", no: "przeciw", abstain: "wstrzymał(a) się", absent: "nie głosował(a)" };
  const main = document.getElementById("game");

  // Conditional pieces of a screen are written as `cond && node` or
  // `cond ? node : null`; the empty values must be dropped before they reach
  // the DOM, which would otherwise print them as the text "null" / "false".
  const keep = (c) => c !== null && c !== undefined && c !== false;
  const h = (tag, props = {}, children = []) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...[].concat(children).filter(keep));
    return node;
  };
  const draw = (...nodes) => main.replaceChildren(...nodes.filter(keep));
  // "Jak grać?": short rules, open until the player has made a first move.
  const howTo = (started, items, note) => h("details", { className: "howto", open: !started }, [
    h("summary", { textContent: "Jak grać?" }),
    h("ol", {}, items.map((it) => h("li", {}, it))),
    note ? h("p", { className: "muted", textContent: note }) : null,
  ]);
  // A row of markers: tries used, answers so far, points left.
  const marks = (label, states) => h("p", { className: "marks" }, [
    h("span", { className: "muted", textContent: label }),
    ...states.map((st) => h("span", { className: `mark ${st}` })),
  ]);
  const tile = (cls, text) => h("span", { className: `pill ${cls}`, textContent: text });
  // Progress is kept per game and day, in this browser only.
  const load = (game) => {
    try { return JSON.parse(localStorage.getItem(`sejmdle:${game}:${SEED}`) || "null"); } catch { return null; }
  };
  const save = (game, state) => {
    try { localStorage.setItem(`sejmdle:${game}:${SEED}`, JSON.stringify(state)); } catch { /* play without saving */ }
  };
  const share = (text) => h("button", {
    className: "btn", textContent: "Skopiuj wynik",
    onclick: (e) => navigator.clipboard?.writeText(text).then(() => { e.target.textContent = "Skopiowano"; }),
  });
  const mpLink = (mp) => h("a", { href: `${SITE}posel/${mp.id}.html`, textContent: mp.name });
  const voteLink = (v, text) => h("a", { href: `${SITE}glosowanie/${v.s}-${v.n}.html`, textContent: text });
  const mpCard = (mp) => h("div", { className: "card reveal" }, [
    h("img", { className: "photo", src: PHOTO(mp.id), alt: mp.name, referrerPolicy: "no-referrer" }),
    h("div", {}, [
      h("p", {}, [h("strong", {}, [mpLink(mp)])]),
      h("p", { className: "muted", textContent: `${mp.clubName} · okręg ${mp.district} (${mp.voivodeship})` }),
    ]),
  ]);
  const guessForm = (data, onGuess, label = "Zgaduję") => {
    const input = h("input", { type: "text", placeholder: "Imię i nazwisko posła…", autocomplete: "off" });
    input.setAttribute("list", "mp-names");
    const msg = h("span", { className: "muted" });
    const submit = () => {
      const mp = data.byName.get(fold(input.value));
      if (!mp) { msg.textContent = "Wybierz posła z listy."; return; }
      msg.textContent = "";
      input.value = "";
      onGuess(mp);
    };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
    return h("div", { className: "guess" }, [input, h("button", { className: "btn primary", textContent: label, onclick: submit }), msg]);
  };

  // ---- 1. Zgadnij posła
  const COLS = [["club", "Klub"], ["district", "Okręg (woj.)"], ["age", "Wiek"],
    ["electionVotes", "Głosy w wyborach"], ["turnout", "Frekwencja"], ["education", "Wykształcenie"],
    ["initial", "Nazwisko na literę"]];
  const playPosel = (data) => {
    const target = dailyOrder(data.mps, (m) => m.id, SEED, "posel")[0];
    const state = load("posel") || { guesses: [] };
    const render = () => {
      const guesses = state.guesses.map((id) => data.byId.get(id)).filter(Boolean);
      const won = guesses.some((g) => g.id === target.id);
      const over = won || guesses.length >= MAX_GUESSES;
      const rows = guesses.map((g) => {
        const cmp = compareMps(g, target, data.clubAxis, DAY);
        return h("tr", { className: g === guesses[guesses.length - 1] ? "latest" : "" }, [h("td", { className: "name", textContent: g.name }),
          ...COLS.map(([k]) => h("td", { className: cmp[k].color, textContent: `${cmp[k].text} ${cmp[k].arrow}`.trim() }))]);
      });
      draw(
        h("p", { className: "lead", textContent: "Zgadnij posła dnia." }),
        howTo(guesses.length > 0, [
          [`Wpisz imię i nazwisko dowolnego posła. Masz ${MAX_GUESSES} prób.`],
          ["Po każdej próbie pola pokażą, jak blisko jesteś: ", tile("green", "zgadza się"), " ", tile("yellow", "blisko"), " ", tile("grey", "nie")],
          ["Strzałki prowadzą do celu: ← → klub bardziej na lewo lub prawo, ↑ ↓ liczba większa lub mniejsza, a przy literze nazwiska dalej lub bliżej w alfabecie."],
        ], "„Blisko” to: to samo województwo, wiek ±5 lat, głosy w wyborach ±25%, frekwencja ±3 pkt proc."),
        marks(over ? "Próby:" : `Próba ${guesses.length + 1} z ${MAX_GUESSES}:`,
          Array.from({ length: MAX_GUESSES }, (_, k) => k >= guesses.length ? "todo" : (won && k === guesses.length - 1 ? "ok" : "used"))),
        !over && guessForm(data, (mp) => {
          if (!state.guesses.includes(mp.id)) { state.guesses.push(mp.id); save("posel", state); }
          render();
        }),
        guesses.length ? h("div", { className: "grid-scroll" }, [h("table", { className: "grid" }, [
          h("thead", {}, [h("tr", {}, [h("th", { textContent: "Poseł" }), ...COLS.map(([, t]) => h("th", { textContent: t }))])]),
          h("tbody", {}, rows),
        ])]) : null,
        over && h("p", { className: `result ${won ? "ok" : "bad"}`,
          textContent: won ? `Brawo! Trafione za ${guesses.length}. razem.` : "Tym razem się nie udało." }),
        over && mpCard(target),
        over && share(`Sejmdle ${DAY} — Zgadnij posła: ${won ? guesses.length : "X"}/${MAX_GUESSES}`),
      );
    };
    render();
  };

  // ---- 2. Czy przeszło?
  const playPrzeszlo = (data) => {
    // Mostly amendments that come with a "what it changes" comparison (3 of 5).
    const ordered = dailyOrder(data.amendments, (a) => `${a.s}-${a.n}`, SEED, "przeszlo");
    const withContext = ordered.filter((a) => a.context).slice(0, 3);
    const picked = new Set([...withContext, ...ordered.filter((a) => !a.context).slice(0, AMENDMENTS - withContext.length)]);
    const items = ordered.filter((a) => picked.has(a));
    const state = load("przeszlo") || { answers: [] };
    const KIND = { amendment: "Poprawka", minority: "Wniosek mniejszości", senate: "Poprawka Senatu" };
    // What the amendment changes in the bill: removed / added text among its
    // neighbours. The markup comes ready-made (and escaped) from the API.
    const context = (a) => {
      if (!a.context) return null;
      const rows = h("div", { className: "rows", lang: "pl" });
      rows.innerHTML = a.context.html;
      return h("details", { className: "context", open: true }, [
        h("summary", { textContent: `Co zmienia w projekcie (${a.context.where})` }), rows]);
    };
    const render = () => {
      const i = state.answers.length;
      const score = state.answers.filter((a, k) => a === items[k].adopted).length;
      const done = state.answers.map((ans, k) => {
        const a = items[k], ok = ans === a.adopted;
        return h("div", { className: "card" }, [
          h("p", { className: `result ${ok ? "ok" : "bad"}`,
            textContent: `${ok ? "Dobrze" : "Źle"} — ${a.adopted ? "przeszła" : "nie przeszła"} (${a.yes} za, ${a.no} przeciw)` }),
          h("p", { className: "muted" }, [`${KIND[a.kind] || "Poprawka"} · zgłaszający: ${a.proposer}` +
            (a.recommendation ? ` · komisja chciała: ${a.recommendation}` : "") + " · ", voteLink(a, shortTitle(a.bill).slice(0, 120))]),
          h("div", { className: "amend", lang: "pl", textContent: a.text }),
        ]);
      });
      draw(
        h("p", { className: "lead", textContent: "Czy ta poprawka przeszła?" }),
        howTo(i > 0, [
          [`Dostajesz ${items.length} poprawek, jedną po drugiej.`],
          ["Widzisz treść poprawki i to, co zmienia w projekcie, ale nie widzisz, kto ją zgłosił."],
          ["Wybierz „Przeszła” albo „Nie przeszła”. Po odpowiedzi zobaczysz wynik głosowania i zgłaszającego."],
        ], "Przy poprawkach Senatu „przeszła” znaczy, że Sejm jej nie odrzucił."),
        marks("Odpowiedzi:", items.map((a, k) => k >= i ? "todo" : (state.answers[k] === a.adopted ? "ok" : "bad"))),
        i < items.length ? h("div", { className: "card" }, [
          h("h2", { textContent: `Poprawka ${i + 1} z ${items.length}` }),
          h("p", { className: "muted", textContent: `${KIND[items[i].kind] || "Poprawka"} do projektu: ${shortTitle(items[i].bill)} (${items[i].date.slice(0, 4)})` }),
          h("div", { className: "amend", lang: "pl", textContent: items[i].text }),
          context(items[i]),
          h("div", { className: "guess choice" }, [
            h("button", { className: "btn yes", textContent: "Przeszła", onclick: () => answer(true) }),
            h("button", { className: "btn no", textContent: "Nie przeszła", onclick: () => answer(false) }),
          ]),
        ]) : h("div", {}, [
          h("p", { className: `result ${score * 2 >= items.length ? "ok" : "bad"}`, textContent: `Wynik: ${score} / ${items.length}` }),
          share(`Sejmdle ${DAY} — Czy przeszło?: ${score}/${items.length} ` +
            state.answers.map((a, k) => (a === items[k].adopted ? "🟩" : "🟥")).join("")),
        ]),
        ...done.reverse(),
      );
    };
    const answer = (value) => { state.answers.push(value); save("przeszlo", state); render(); };
    render();
  };

  // ---- 3. Kim jestem?
  const playKim = (data) => {
    const { mp, votes } = whoPuzzle(data, SEED);
    const HINTS = [
      ["Województwo", () => mp.voivodeship],
      ["Okręg", () => mp.district],
      ["Klub", () => mp.clubName],
      ["Zdjęcie", () => h("img", { className: "photo", src: PHOTO(mp.id), alt: "Zdjęcie posła", referrerPolicy: "no-referrer" })],
    ];
    const state = load("kim") || { hints: 0, wrong: [], won: false, lost: false };
    const render = () => {
      const over = state.won || state.lost;
      const points = HINTS.length + 1 - state.hints;
      const nextHint = () => {
        if (state.hints < HINTS.length) state.hints++; else state.lost = true;
        save("kim", state); render();
      };
      const max = HINTS.length + 1;
      draw(
        h("p", { className: "lead", textContent: "Kim jestem?" }),
        howTo(state.hints > 0 || state.wrong.length > 0 || over, [
          ["Na start widzisz, jak tajemniczy poseł głosował nad całością pięciu ustaw."],
          ["Zgadnij, kto to, albo odsłoń wskazówkę. Kolejno: województwo, okręg, klub, zdjęcie."],
          [`Zaczynasz z ${max} punktami. Każda wskazówka i każda zła odpowiedź zabiera jeden.`],
        ]),
        marks("Punkty:", Array.from({ length: max }, (_, k) => (!state.lost && k < points) ? (state.won ? "ok" : "used") : "todo")),
        h("div", { className: "card" }, [
          h("h2", { textContent: "Tak głosowałem(-am) nad całością ustaw" }),
          h("ul", { className: "votes" }, votes.map(({ final, vote }) => h("li", {}, [
            h("span", { className: `v-${vote}`, textContent: VOTE_PL[vote] }), " — ",
            over ? voteLink(final, shortTitle(final.title)) : shortTitle(final.title), h("span", { className: "muted", textContent: ` (${final.date})` }),
          ]))),
        ]),
        ...HINTS.slice(0, state.hints).map(([label, value]) =>
          h("div", { className: "card" }, [h("strong", { textContent: `${label}: ` }), value()])),
        state.wrong.length ? h("p", { className: "muted",
          textContent: `To nie: ${state.wrong.map((id) => data.byId.get(id)?.name).filter(Boolean).join(", ")}` }) : null,
        !over && guessForm(data, (guess) => {
          if (guess.id === mp.id) state.won = true;
          else { state.wrong.push(guess.id); if (state.hints < HINTS.length) state.hints++; else state.lost = true; }
          save("kim", state); render();
        }),
        !over && h("button", { className: "btn", onclick: nextHint,
          textContent: state.hints < HINTS.length ? "Pokaż kolejną wskazówkę" : "Poddaję się" }),
        over && h("p", { className: `result ${state.won ? "ok" : "bad"}`,
          textContent: state.won ? `Tak! ${points} pkt z ${HINTS.length + 1}.` : "Nie tym razem — 0 pkt." }),
        over && mpCard(mp),
        over && share(`Sejmdle ${DAY} — Kim jestem?: ${state.won ? points : 0}/${HINTS.length + 1} pkt`),
      );
    };
    render();
  };

  // ---- start
  const GAMES = { posel: playPosel, przeszlo: playPrzeszlo, kim: playKim };
  document.getElementById("today").textContent = TEST ? `${DAY} · tryb testowy` : DAY;
  document.getElementById("reroll").href = `?los=${Math.random().toString(36).slice(2, 8)}${location.hash}`;
  document.getElementById("site-link").href = SITE;
  fetch(`${API}games.json`).then((r) => {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then((data) => {
    data.byId = new Map(data.mps.map((m) => [m.id, m]));
    data.byName = new Map(data.mps.map((m) => [fold(m.name), m]));
    document.getElementById("mp-names").append(
      ...[...data.mps].sort((a, b) => a.name.localeCompare(b.name, "pl")).map((m) => h("option", { value: m.name })));
    const tabs = [...document.querySelectorAll(".tabs button")];
    const open = (game) => {
      tabs.forEach((t) => t.setAttribute("aria-selected", String(t.dataset.game === game)));
      GAMES[game](data);
      history.replaceState(null, "", `#${game}`);
    };
    tabs.forEach((t) => t.addEventListener("click", () => open(t.dataset.game)));
    open(GAMES[location.hash.slice(1)] ? location.hash.slice(1) : "posel");
  }).catch(() => {
    main.replaceChildren(h("p", { textContent: "Nie udało się wczytać danych. Spróbuj ponownie później." }));
  });
})();
