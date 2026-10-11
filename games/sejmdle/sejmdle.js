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

// Voivodeships: rough centre [latitude, longitude] and the ones they border.
const REGIONS = {
  "dolnośląskie": [51.0, 16.4, ["lubuskie", "wielkopolskie", "opolskie"]],
  "kujawsko-pomorskie": [53.1, 18.5, ["pomorskie", "warmińsko-mazurskie", "mazowieckie", "łódzkie", "wielkopolskie"]],
  "lubelskie": [51.2, 22.9, ["podlaskie", "mazowieckie", "świętokrzyskie", "podkarpackie"]],
  "lubuskie": [52.2, 15.3, ["zachodniopomorskie", "wielkopolskie", "dolnośląskie"]],
  "łódzkie": [51.6, 19.4, ["kujawsko-pomorskie", "mazowieckie", "świętokrzyskie", "śląskie", "opolskie", "wielkopolskie"]],
  "małopolskie": [49.9, 20.3, ["śląskie", "świętokrzyskie", "podkarpackie"]],
  "mazowieckie": [52.3, 21.1, ["warmińsko-mazurskie", "podlaskie", "lubelskie", "świętokrzyskie", "łódzkie", "kujawsko-pomorskie"]],
  "opolskie": [50.6, 17.9, ["dolnośląskie", "wielkopolskie", "łódzkie", "śląskie"]],
  "podkarpackie": [49.9, 22.2, ["małopolskie", "świętokrzyskie", "lubelskie"]],
  "podlaskie": [53.3, 22.9, ["warmińsko-mazurskie", "mazowieckie", "lubelskie"]],
  "pomorskie": [54.2, 18.0, ["zachodniopomorskie", "wielkopolskie", "kujawsko-pomorskie", "warmińsko-mazurskie"]],
  "śląskie": [50.3, 19.0, ["opolskie", "łódzkie", "świętokrzyskie", "małopolskie"]],
  "świętokrzyskie": [50.8, 20.8, ["łódzkie", "mazowieckie", "lubelskie", "podkarpackie", "małopolskie", "śląskie"]],
  "warmińsko-mazurskie": [53.9, 20.8, ["pomorskie", "kujawsko-pomorskie", "mazowieckie", "podlaskie"]],
  "wielkopolskie": [52.3, 17.2, ["zachodniopomorskie", "pomorskie", "kujawsko-pomorskie", "łódzkie", "opolskie", "dolnośląskie", "lubuskie"]],
  "zachodniopomorskie": [53.6, 15.5, ["pomorskie", "wielkopolskie", "lubuskie"]],
};
const COMPASS = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"]; // east, then anticlockwise

// How the target's voivodeship lies relative to the guessed one:
// {same, neighbour, arrow}; the arrow points from the guess towards the target.
const regionHint = (guessed, target) => {
  const g = REGIONS[guessed], t = REGIONS[target];
  if (guessed === target || !g || !t) return { same: guessed === target, neighbour: false, arrow: "" };
  // a degree of longitude is shorter than one of latitude at Poland's latitude
  const angle = Math.atan2(t[0] - g[0], (t[1] - g[1]) * Math.cos((52 * Math.PI) / 180));
  return { same: false, neighbour: g[2].includes(target), arrow: COMPASS[(Math.round(angle / (Math.PI / 4)) + 8) % 8] };
};

const ALPHABET = "AĄBCĆDEĘFGHIJKLŁMNŃOÓPQRSŚTUVWXYZŹŻ";
const LETTER_CLOSE = 2;

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
      // yellow: the neighbouring club on the left-right axis
      color: guess.club === target.club ? "green" : gi >= 0 && ti >= 0 && Math.abs(gi - ti) === 1 ? "yellow" : "grey",
      // target sits further left (←) or right (→) on the axis; unknown if either is off it
      arrow: guess.club === target.club || gi < 0 || ti < 0 ? "" : ti < gi ? "←" : "→",
    },
    // green: same constituency; yellow: same or neighbouring voivodeship;
    // outside the target's voivodeship, a compass arrow points towards it
    district: (() => {
      const r = regionHint(guess.voivodeship, target.voivodeship);
      return {
        text: `${guess.district} (${guess.voivodeship})`,
        color: guess.districtNum === target.districtNum ? "green" : r.same || r.neighbour ? "yellow" : "grey",
        arrow: r.arrow,
      };
    })(),
    age: num(age(guess.birthDate, day), age(target.birthDate, day), () => 5, (v) => `${v} lat`),
    electionVotes: num(guess.electionVotes, target.electionVotes, (t) => t * 0.25, (v) => v.toLocaleString("pl-PL")),
    turnout: num(Math.round(guess.turnout * 1000) / 10, Math.round(target.turnout * 1000) / 10, () => 3,
      (v) => `${v.toLocaleString("pl-PL")}%`),
    education: { text: guess.education || "—", color: guess.education === target.education ? "green" : "grey", arrow: "" },
    // first letter of the surname, read like a dictionary: the target's letter
    // comes before the guessed one (←) or after it (→)
    initial: (() => {
      const g = surnameInitial(guess.name), t = surnameInitial(target.name);
      const order = g.localeCompare(t, "pl");
      const gap = Math.abs(ALPHABET.indexOf(g) - ALPHABET.indexOf(t));
      return {
        text: order === 0 ? g : order < 0 ? `po ${g} →` : `← przed ${g}`,
        // yellow: at most LETTER_CLOSE letters away in the Polish alphabet
        color: order === 0 ? "green" : ALPHABET.includes(g) && ALPHABET.includes(t) && gap <= LETTER_CLOSE ? "yellow" : "grey",
        arrow: "",
      };
    })(),
  };
};

// "Agnieszka Wojciechowska van Heukelom" -> "W": the surname is everything after the first name.
const surnameInitial = (name) => (name.trim().split(/\s+/)[1] || name).charAt(0).toUpperCase();

// "Kim jestem?": what a wrong guess has in common with the target.
// green = same club; yellow = same constituency, or same or neighbouring
// voivodeship; grey = neither. Outside the target's voivodeship the text
// ends with a compass arrow pointing towards it.
const guessFeedback = (guess, target) => {
  const r = regionHint(guess.voivodeship, target.voivodeship);
  const sameClub = guess.club === target.club;
  const region = guess.districtNum === target.districtNum ? `ten sam okręg: ${guess.district}`
    : r.same ? `to samo województwo: ${guess.voivodeship}`
    : r.neighbour ? `sąsiednie województwo, kierunek ${r.arrow}`
    : `inne województwo, kierunek ${r.arrow}`;
  const club = sameClub ? `Ten sam klub: ${guess.clubName || guess.club}` : "Inny klub";
  return {
    color: sameClub ? "green" : guess.districtNum === target.districtNum || r.same || r.neighbour ? "yellow" : "grey",
    text: `${club} · ${region}`,
  };
};

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
  module.exports = { fold, hash, dailyOrder, warsawDay, age, compareMps, guessFeedback, regionHint, REGIONS, voteOf, whoPuzzle, shortTitle, surnameInitial };
}

// ------------------------------------------------------------------- DOM

if (typeof document !== "undefined") (() => {
  const meta = (name, fallback) => document.querySelector(`meta[name="${name}"]`)?.content || fallback;
  const API = meta("sejmomat-api", "../api/v1/");
  const SITE = meta("sejmomat-site", "../");
  const PHOTO = (id) => `https://api.sejm.gov.pl/sejm/term10/MP/${id}/photo`;
  const DAY = warsawDay();
  // Daily puzzles are picked from the date plus this round number: raise
  // ROUND to deal everyone a fresh set.
  const ROUND = "3";
  // Endless mode (a testing aid): each game deals a new puzzle on demand,
  // counted per game in this browser. Set ENDLESS_AVAILABLE to false to
  // remove the switch and leave only the daily puzzles.
  const ENDLESS_AVAILABLE = true;
  const store = {
    get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* play without saving */ } },
    del: (k) => { try { localStorage.removeItem(k); } catch { /* nothing to remove */ } },
  };
  let endless = ENDLESS_AVAILABLE && store.get("sejmdle:endless") !== "0"; // on by default while testing
  const roundNo = (game) => Number(store.get(`sejmdle:n:${game}`)) || 1;
  const seedFor = (game) => (endless ? `bez-konca#${roundNo(game)}` : `${DAY}#${ROUND}`);
  const label = () => (endless ? "tryb bez końca" : DAY);
  let openGame = () => {};
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
  // "Jak grać?": the rules in a popup. A round "?" next to the game's title
  // opens it, and it opens by itself on a player's first visit to each game.
  const helpDialog = h("dialog", { className: "help" });
  helpDialog.addEventListener("click", (e) => { if (e.target === helpDialog) closeHelp(); }); // click on the backdrop
  document.body.append(helpDialog);
  const closeHelp = () => (helpDialog.close ? helpDialog.close() : helpDialog.removeAttribute("open"));
  const showHelp = (title, items, note) => {
    helpDialog.replaceChildren(...[
      h("button", { type: "button", className: "help-close", textContent: "×", ariaLabel: "Zamknij", onclick: closeHelp }),
      h("h2", { textContent: `Jak grać: ${title}` }),
      h("ol", {}, items.map((it) => h("li", {}, it))),
      note ? h("p", { className: "muted", textContent: note }) : null,
      h("p", { className: "help-ok" }, [h("button", { type: "button", className: "btn primary", textContent: "Gram!", onclick: closeHelp })]),
    ].filter(keep));
    if (helpDialog.open) return;
    if (helpDialog.showModal) helpDialog.showModal(); else helpDialog.setAttribute("open", "");
  };
  // The game's title line with its "?" button.
  const lead = (title, game, items, note) => {
    const open = () => showHelp(title, items, note);
    if (!store.get(`sejmdle:help:${game}`)) {
      store.set(`sejmdle:help:${game}`, "1");
      open();
    }
    return h("p", { className: "lead" }, [title, " ",
      h("button", { type: "button", className: "help-btn", textContent: "?", title: "Jak grać?", ariaLabel: "Jak grać?", onclick: open })]);
  };
  // A row of markers: tries used, answers so far, points left.
  const marks = (label, states) => h("p", { className: "marks" }, [
    h("span", { className: "muted", textContent: label }),
    ...states.map((st) => h("span", { className: `mark ${st}` })),
  ]);
  const tile = (cls, text) => h("span", { className: `pill ${cls}`, textContent: text });
  // Short names for the left-to-right list of clubs in the instructions.
  const CLUB_SHORT = { Polska2050: "Polska 2050", "PSL-TD": "PSL", RozwojPlus: "Rozwój Plus",
    Demokracja: "Demokracja Bezpośrednia (Kukiz)", Konfederacja_KP: "Konfederacja Korony Polskiej" };
  // Progress is kept per game and day, in this browser only.
  const load = (game) => {
    try { return JSON.parse(store.get(`sejmdle:${game}:${seedFor(game)}`) || "null"); } catch { return null; }
  };
  const save = (game, state) => store.set(`sejmdle:${game}:${seedFor(game)}`, JSON.stringify(state));
  // Endless mode: drop the finished (or skipped) puzzle and deal the next one.
  const nextPuzzle = (game) => {
    store.del(`sejmdle:${game}:${seedFor(game)}`);
    store.set(`sejmdle:n:${game}`, String(roundNo(game) + 1));
    openGame(game);
  };
  const nextButton = (game, over) => endless && h("p", { className: "next" }, [h("button", {
    className: over ? "btn primary" : "btn quiet", onclick: () => nextPuzzle(game),
    textContent: over ? "Następna zagadka →" : "Pomiń tę zagadkę",
  })]);
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
    const target = dailyOrder(data.mps, (m) => m.id, seedFor("posel"), "posel")[0];
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
        lead("Zgadnij posła dnia", "posel", [
          [`Wpisz imię i nazwisko dowolnego posła. Masz ${MAX_GUESSES} prób.`],
          ["Po każdej próbie pola pokażą, jak blisko jesteś: ", tile("green", "zgadza się"), " ", tile("yellow", "blisko"), " ", tile("grey", "nie")],
          ["Strzałki prowadzą do celu: ← → klub bardziej na lewo lub prawo, ↑ ↓ liczba większa lub mniejsza."],
          ["Przy okręgu strzałka działa jak kompas: pokazuje, w którą stronę na mapie leży szukane województwo (↑ północ, → wschód, ↘ południowy wschód…)."],
          ["Kluby od lewej do prawej: ", h("span", { className: "axis",
            textContent: data.clubAxis.map((c) => CLUB_SHORT[c] || c).join(" → ") })],
          ["Litera nazwiska działa jak słownik: „← przed K” znaczy, że szukane nazwisko zaczyna się wcześniej w alfabecie niż K, a „po K →”, że później."],
        ], `„Blisko” to: sąsiedni klub na tej liście, to samo lub sąsiednie województwo, wiek ±5 lat, głosy w wyborach ±25%, frekwencja ±3 pkt proc., litera nazwiska najwyżej ${LETTER_CLOSE} litery dalej w alfabecie.`),
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
        over && share(`Sejmdle ${label()} — Zgadnij posła: ${won ? guesses.length : "X"}/${MAX_GUESSES}`),
        nextButton("posel", over),
      );
    };
    render();
  };

  // ---- 2. Czy przeszło?
  const playPrzeszlo = (data) => {
    // Mostly amendments that come with a "what it changes" comparison (3 of 5).
    const ordered = dailyOrder(data.amendments, (a) => `${a.s}-${a.n}`, seedFor("przeszlo"), "przeszlo");
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
        lead("Czy ta poprawka przeszła?", "przeszlo", [
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
          share(`Sejmdle ${label()} — Czy przeszło?: ${score}/${items.length} ` +
            state.answers.map((a, k) => (a === items[k].adopted ? "🟩" : "🟥")).join("")),
        ]),
        nextButton("przeszlo", i >= items.length),
        ...done.reverse(),
      );
    };
    const answer = (value) => { state.answers.push(value); save("przeszlo", state); render(); };
    render();
  };

  // ---- 3. Kim jestem?
  // A timeline: the votes, then for every step (a wrong guess or a skipped
  // turn) what that guess had in common with the target and the next clue.
  const playKim = (data) => {
    const { mp, votes } = whoPuzzle(data, seedFor("kim"));
    const HINTS = [
      ["Województwo", () => mp.voivodeship],
      ["Okręg", () => mp.district],
      ["Klub", () => mp.clubName],
      ["Zdjęcie", () => h("img", { className: "photo", src: PHOTO(mp.id), alt: "Zdjęcie posła", referrerPolicy: "no-referrer" })],
    ];
    const max = HINTS.length + 1;
    const saved = load("kim");
    // steps: "hint" for a skipped turn, or the id of a wrongly guessed MP
    const state = saved && Array.isArray(saved.steps) ? saved : { steps: [], won: false, lost: false };
    const clue = (n, label, body, cls = "") => h("div", { className: `card clue ${cls}` }, [
      h("p", { className: "clue-label", textContent: `Podpowiedź ${n}${label ? ` · ${label}` : ""}` }), body]);
    const render = () => {
      const over = state.won || state.lost;
      const points = max - state.steps.length;
      const step = (value) => {
        // every step costs a point; with no clues left, the game is lost
        if (state.steps.length >= HINTS.length) state.lost = true;
        state.steps.push(value);
        save("kim", state); render();
      };
      const timeline = [clue(1, "Tak głosowałem(-am) nad całością ustaw",
        h("ul", { className: "votes" }, votes.map(({ final, vote }) => h("li", {}, [
          h("span", { className: `v-${vote}`, textContent: VOTE_PL[vote] }), " — ",
          over ? voteLink(final, shortTitle(final.title)) : shortTitle(final.title),
          h("span", { className: "muted", textContent: ` (${final.date})` }),
        ]))))];
      state.steps.forEach((value, k) => {
        const guess = value === "hint" ? null : data.byId.get(value);
        if (guess) {
          const fb = guessFeedback(guess, mp);
          timeline.push(h("div", { className: `card guessed ${fb.color}` }, [
            h("p", { className: "guessed-name", textContent: guess.name }),
            h("p", { className: "guessed-fb" }, [h("span", { className: `dot ${fb.color}` }), fb.text]),
          ]));
        }
        if (k < HINTS.length) timeline.push(clue(k + 2, HINTS[k][0], h("div", { className: "clue-value" }, [HINTS[k][1]()])));
      });
      draw(
        lead("Kim jestem?", "kim", [
          ["Na start widzisz, jak tajemniczy poseł głosował nad całością pięciu ustaw."],
          ["Zgadnij, kto to. Po złej odpowiedzi zobaczysz, czy trafiłeś(-aś) klub lub region: ",
            tile("green", "ten sam klub"), " ", tile("yellow", "to samo lub sąsiednie województwo"), " ", tile("grey", "nic wspólnego")],
          ["Jeśli województwo się nie zgadza, strzałka-kompas pokaże, w którą stronę na mapie leży właściwe (↑ północ, → wschód)."],
          ["Każda zła odpowiedź i każde „Pomiń” odsłania kolejną podpowiedź: województwo, okręg, klub, zdjęcie."],
          [`Zaczynasz z ${max} punktami, a każdy taki krok zabiera jeden.`],
        ]),
        marks("Punkty:", Array.from({ length: max }, (_, k) => (!state.lost && k < points) ? (state.won ? "ok" : "used") : "todo")),
        ...timeline,
        !over && guessForm(data, (guess) => {
          if (guess.id === mp.id) { state.won = true; save("kim", state); render(); }
          else if (!state.steps.includes(guess.id)) step(guess.id);
        }),
        !over && h("button", { className: "btn", onclick: () => step("hint"),
          textContent: state.steps.length < HINTS.length ? "Pomiń — pokaż kolejną podpowiedź" : "Poddaję się" }),
        over && h("div", { className: `card answer ${state.won ? "won" : "lost"}` }, [
          h("p", { className: "clue-label", textContent: state.won ? `Odpowiedź · ${points} pkt z ${max}` : "Odpowiedź · 0 pkt" }),
          mpCard(mp),
        ]),
        over && share(`Sejmdle ${label()} — Kim jestem?: ${state.won ? points : 0}/${max} pkt`),
        nextButton("kim", over),
      );
    };
    render();
  };

  // ---- start
  const GAMES = { posel: playPosel, przeszlo: playPrzeszlo, kim: playKim };
  const today = document.getElementById("today"), mode = document.getElementById("mode");
  let current = "posel";
  const showMode = () => {
    today.textContent = endless ? `${DAY} · tryb bez końca (testowy)` : DAY;
    mode.hidden = !ENDLESS_AVAILABLE;
    mode.textContent = endless ? "∞ Bez końca: włączony" : "∞ Bez końca: wyłączony";
    mode.setAttribute("aria-pressed", String(endless));
    mode.title = endless ? "Przełącz na zagadki dnia" : "Włącz tryb bez końca: nowe zagadki na żądanie";
  };
  mode.addEventListener("click", () => {
    endless = !endless;
    store.set("sejmdle:endless", endless ? "1" : "0");
    showMode();
    openGame(current);
  });
  showMode();
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
      current = game;
      tabs.forEach((t) => t.setAttribute("aria-selected", String(t.dataset.game === game)));
      GAMES[game](data);
      history.replaceState(null, "", `#${game}`);
    };
    openGame = open;
    tabs.forEach((t) => t.addEventListener("click", () => open(t.dataset.game)));
    open(GAMES[location.hash.slice(1)] ? location.hash.slice(1) : "posel");
  }).catch(() => {
    main.replaceChildren(h("p", { textContent: "Nie udało się wczytać danych. Spróbuj ponownie później." }));
  });
})();
