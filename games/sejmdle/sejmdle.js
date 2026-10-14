// Sejmdle: five daily games built on the Sejmomat JSON API (api/v1/games.json).
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

// "52 lata", "55 lat"
const years = (n) => `${n} ${n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14) ? "lata" : "lat"}`;

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
// The constituency cell has one more step, blue: the right voivodeship.
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
    // green: same constituency; blue: same voivodeship; yellow: a neighbouring
    // one; outside the target's voivodeship, a compass arrow points towards it
    district: (() => {
      const r = regionHint(guess.voivodeship, target.voivodeship);
      return {
        text: `${guess.district} (${guess.voivodeship})`,
        color: guess.districtNum === target.districtNum ? "green" : r.same ? "blue" : r.neighbour ? "yellow" : "grey",
        arrow: r.arrow,
      };
    })(),
    age: num(age(guess.birthDate, day), age(target.birthDate, day), () => 5, years),
    electionVotes: num(guess.electionVotes, target.electionVotes, (t) => t * 0.25, (v) => v.toLocaleString("pl-PL")),
    turnout: num(Math.round(guess.turnout * 1000) / 10, Math.round(target.turnout * 1000) / 10, () => 3,
      (v) => `${v.toLocaleString("pl-PL")}%`),
    education: { text: guess.education || "—", color: guess.education === target.education ? "green" : "grey", arrow: "" },
    // first letter of the surname, read like a dictionary: the target's letter
    // comes before the guessed one (←) or after it (→)
    initial: (() => {
      const g = surnameInitial(guess), t = surnameInitial(target);
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

// The surname as the Sejm gives it ("Wojciechowska van Heukelom"); without
// that field, the last word of the name (second names come before it).
const surnameOf = (mp) => mp.lastName || mp.name.trim().split(/\s+/).pop();
const surnameInitial = (mp) => surnameOf(mp).charAt(0).toUpperCase();
// "Lubnauer Katarzyna Anna": how names read in a list sorted by surname.
const surnameFirst = (mp) => {
  const last = surnameOf(mp);
  return mp.name.endsWith(last) ? `${last} ${mp.name.slice(0, -last.length).trim()}`.trim() : mp.name;
};

// "Kim jestem?": what a wrong guess has in common with the target.
// green = same club; blue = same voivodeship (or constituency); yellow = a
// neighbouring voivodeship; grey = neither. Outside the target's voivodeship
// the text ends with a compass arrow pointing towards it.
const guessFeedback = (guess, target) => {
  const r = regionHint(guess.voivodeship, target.voivodeship);
  const sameClub = guess.club === target.club;
  const region = guess.districtNum === target.districtNum ? `ten sam okręg: ${guess.district}`
    : r.same ? `to samo województwo: ${guess.voivodeship}`
    : r.neighbour ? `sąsiednie województwo, kierunek ${r.arrow}`
    : `inne województwo, kierunek ${r.arrow}`;
  const club = sameClub ? `Ten sam klub: ${guess.clubName || guess.club}` : "Inny klub";
  return {
    color: sameClub ? "green" : guess.districtNum === target.districtNum || r.same ? "blue" : r.neighbour ? "yellow" : "grey",
    text: `${club} · ${region}`,
  };
};

// The clue colours as squares, for the result a player shares.
const SQUARE = { green: "🟩", blue: "🟦", yellow: "🟨", grey: "⬜" };
// "Zgadnij posła": a row of squares per guess, a square per column (`keys`).
const guessSquares = (cmps, keys) => cmps.map((cmp) => keys.map((k) => SQUARE[cmp[k].color]).join("")).join("\n");
// "Kim jestem?": the steps in order (a wrong guess as the colour of its
// feedback, a skipped turn as a light bulb), then how it ended.
const whoSquares = (steps, won) =>
  steps.map((st) => (st === "hint" ? "💡" : SQUARE[st] || SQUARE.grey)).join("") + (won ? "✅" : "❌");

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

// ---- Prezydium and Siatka: slots to fill with MPs who fit their conditions

// Short names of clubs, for lists and conditions.
const CLUB_SHORT = { Polska2050: "Polska 2050", "PSL-TD": "PSL", RozwojPlus: "Rozwój Plus",
  Demokracja: "Demokracja Bezpośrednia (Kukiz)", Konfederacja_KP: "Konfederacja Korony Polskiej" };
const clubShort = (club) => CLUB_SHORT[club] || (club === "niez." ? "Niezrzeszeni" : club);
// Clubs of the governing coalition. Every other club or group is the
// opposition; MPs outside any club go with the side they vote with (below).
const COALITION = ["KO", "Lewica", "Polska2050", "Centrum", "PSL-TD"];
// Independents have no club line to follow, so they are counted with the
// side they vote with: in each contested final vote (data.finals) the
// coalition's choice is what most of its MPs voted; an independent who made
// the same choice in at least LEAN_SHARE of their ballots goes with the
// coalition, one who made it in at most 1 - LEAN_SHARE with the opposition,
// anyone in between (or with fewer than LEAN_MIN_VOTES ballots) with neither.
const LEAN_SHARE = 0.6;
const LEAN_MIN_VOTES = 20;
const independentLeans = (data) => {
  const club = new Map(data.mps.map((m) => [m.id, m.club]));
  const CHOICES = ["yes", "no", "abstain"];
  const tally = new Map(); // id -> [ballots as the coalition chose, ballots]
  for (const f of data.finals || []) {
    const count = Object.fromEntries(CHOICES.map((k) => [k, (f.votes[k] || []).filter((id) => COALITION.includes(club.get(id))).length]));
    const line = CHOICES.reduce((a, b) => (count[b] > count[a] ? b : a));
    if (!count[line]) continue;
    for (const k of CHOICES) {
      for (const id of f.votes[k] || []) {
        if (club.get(id) !== "niez.") continue;
        const t = tally.get(id) || tally.set(id, [0, 0]).get(id);
        t[1]++;
        if (k === line) t[0]++;
      }
    }
  }
  const out = new Map();
  for (const [id, [same, cast]] of tally) {
    if (cast < LEAN_MIN_VOTES) continue;
    if (same / cast >= LEAN_SHARE) out.set(id, "coalition");
    else if (same / cast <= 1 - LEAN_SHARE) out.set(id, "opposition");
  }
  return out;
};
// Voivodeships grouped into the official statistical macro-regions (NUTS 1),
// so that a condition is never about one small voivodeship.
const MACRO_REGIONS = [
  ["polnoc", "Polska północna", ["pomorskie", "kujawsko-pomorskie", "warmińsko-mazurskie"]],
  ["polnocny-zachod", "Polska północno-zachodnia", ["zachodniopomorskie", "lubuskie", "wielkopolskie"]],
  ["poludniowy-zachod", "Polska południowo-zachodnia", ["dolnośląskie", "opolskie"]],
  ["poludnie", "Polska południowa", ["śląskie", "małopolskie"]],
  ["centrum", "Polska centralna", ["łódzkie", "świętokrzyskie"]],
  ["wschod", "Polska wschodnia", ["lubelskie", "podkarpackie", "podlaskie"]],
  ["mazowsze", "Mazowsze", ["mazowieckie"]],
];
const CAT_MIN = 12;        // a condition needs at least this many MPs who meet it
const COMMITTEE_MIN = 35;  // committees smaller than this are not used as conditions
const committeeName = (entry) => entry.replace(/ \([^()]*\)$/, ""); // without "(przewodniczący)"

const firstName = (mp) => mp.name.trim().split(/\s+/)[0];
// Every condition an MP can meet: {id, kind, label, detail, test}. Conditions
// of one family are never combined with each other; a family is a kind,
// except that the coalition/opposition pair belongs with the clubs.
const family = (kind) => (kind === "block" ? "club" : kind);
const categories = (data) => {
  const out = [];
  const count = (items) => items.reduce((acc, k) => acc.set(k, (acc.get(k) || 0) + 1), new Map());
  const add = (kind, key, label, detail, test) => {
    if (data.mps.filter(test).length >= CAT_MIN) out.push({ id: `${kind}:${key}`, kind, label, detail, test });
  };
  const inClub = (m) => Boolean(m.club) && m.club !== "niez.";
  const leans = independentLeans(data);
  const side = (m) => (COALITION.includes(m.club) ? "coalition" : inClub(m) ? "opposition" : leans.get(m.id) || null);
  add("block", "koalicja", "Koalicja rządząca", `${COALITION.map(clubShort).join(", ")} i niezrzeszeni głosujący z koalicją`,
    (m) => side(m) === "coalition");
  add("block", "opozycja", "Opozycja", "pozostałe kluby i koła oraz niezrzeszeni głosujący z opozycją",
    (m) => side(m) === "opposition");
  for (const club of count(data.mps.filter(inClub).map((m) => m.club)).keys()) {
    add("club", club, `Klub: ${clubShort(club)}`, "", (m) => m.club === club);
  }
  for (const [key, label, voivodeships] of MACRO_REGIONS) {
    add("region", key, label, voivodeships.join(", "), (m) => voivodeships.includes(m.voivodeship));
  }
  const born = (m) => Number(m.birthDate.slice(0, 4));
  add("decade", "do-1959", "Urodzeni przed 1960", "", (m) => born(m) < 1960);
  for (const d of [60, 70, 80]) {
    add("decade", `19${d}`, `Urodzeni w latach ${d}.`, `19${d}–19${d + 9}`, (m) => born(m) >= 1900 + d && born(m) <= 1909 + d);
  }
  add("decade", "od-1990", "Urodzeni po 1989", "", (m) => born(m) >= 1990);
  for (const letter of count(data.mps.map(surnameInitial)).keys()) {
    add("initial", letter, `Nazwisko na ${letter}`, "", (m) => surnameInitial(m) === letter);
  }
  for (const name of count(data.mps.map(firstName)).keys()) {
    add("name", name, `Imię: ${name}`, "", (m) => firstName(m) === name);
  }
  add("votes", "30", "Ponad 30 tys. głosów", "w wyborach do Sejmu w 2023 r.", (m) => m.electionVotes > 30000);
  add("votes", "10", "Poniżej 10 tys. głosów", "w wyborach do Sejmu w 2023 r.", (m) => m.electionVotes < 10000);
  const seats = (m) => m.committees || [];
  add("committee", "prezydium", "Prezydium komisji", "przewodniczy komisji sejmowej albo jest zastępcą",
    (m) => seats(m).some((c) => /\([^()]*przewodnicz[^()]*\)$/.test(c)));
  for (const [name, size] of count(data.mps.flatMap((m) => seats(m).map(committeeName)))) {
    if (size < COMMITTEE_MIN || name.length > 36 || /^(Nadzwyczajna|Śledcza)/.test(name)) continue;
    add("committee", name, `Komisja ${name.replace(/^Do /, "do ")}`, "zasiada w tej komisji",
      (m) => seats(m).some((c) => committeeName(c) === name));
  }
  return out;
};
const fitting = (data, cats) => data.mps.filter((m) => cats.every((c) => c.test(m)));

// "Prezydium": seven seats, each with one or two conditions; the first seat
// (the Marshal's) always has two. Every seat has at least as many fitting MPs
// as there are seats, so all of them can be filled with different people.
const SEATS = 7;
const SEAT_KINDS = ["block", "club", "region", "region", "decade", "committee", "votes"]; // a seat's first condition
const SEAT_SECOND_KINDS = ["block", "club", "region", "decade", "initial", "name"];       // one per family at most
const seatsPuzzle = (data, seed, cats = categories(data)) => {
  const shuffled = (items, key, salt) => dailyOrder(items, key, `${seed}|${salt}`, "prezydium");
  const used = new Set(), seconds = new Set(), seats = [];
  const free = (kinds, salt) => shuffled(cats.filter((c) => kinds.includes(c.kind) && !used.has(c.id)), (c) => c.id, salt);
  shuffled(SEAT_KINDS.map((kind, i) => [kind, i]), (p) => String(p[1]), "kinds").forEach(([kind], i) => {
    const first = free([kind], `a${i}`)[0] || free(SEAT_KINDS, `a${i}`)[0];
    if (!first) return;
    used.add(first.id);
    const two = i === 0 || hash(`${seed}|prezydium|two|${i}`) % 2 === 0;
    const second = two && free(SEAT_SECOND_KINDS.filter((k) => family(k) !== family(first.kind) && !seconds.has(family(k))), `b${i}`)
      .find((c) => fitting(data, [first, c]).length >= SEATS);
    if (second) { used.add(second.id); seconds.add(family(second.kind)); }
    seats.push(second ? [first, second] : [first]);
  });
  return seats;
};

// "Siatka": three conditions down, three across; a field needs an MP who
// meets both. The three of one side are of one family and no MP meets two
// of them; with at least GRID_MIN fitting MPs in every field, the nine fields
// can then always be filled with nine different people.
const GRID_MIN = 3;
const GRID_SIDE_KINDS = ["club", "club", "region", "region", "decade"]; // the side of one family
const GRID_CROSS_KINDS = ["club", "region", "decade", "initial", "name", "votes", "committee"];
const gridPuzzle = (data, seed, cats = categories(data)) => {
  const shuffled = (items, key, salt) => dailyOrder(items, key, `${seed}|${salt}`, "siatka");
  for (let attempt = 0; attempt < 300; attempt++) {
    const kind = shuffled(GRID_SIDE_KINDS.map((k, i) => [k, i]), (p) => String(p[1]), `k${attempt}`)[0][0];
    const side = [];
    for (const c of shuffled(cats.filter((c) => family(c.kind) === kind), (c) => c.id, `s${attempt}`)) {
      if (side.length < 3 && side.every((o) => fitting(data, [o, c]).length === 0)) side.push(c);
    }
    if (side.length < 3) continue;
    // the other side: three conditions, each of another family
    const cross = [];
    for (const k of shuffled(GRID_CROSS_KINDS.filter((k) => k !== kind), (k) => k, `x${attempt}`)) {
      const c = cross.length < 3 && shuffled(cats.filter((c) => family(c.kind) === k), (c) => c.id, `c${attempt}`)
        .find((c) => side.every((o) => fitting(data, [o, c]).length >= GRID_MIN));
      if (c) cross.push(c);
    }
    if (cross.length < 3) continue;
    return hash(`${seed}|siatka|turn`) % 2 ? { rows: side, cols: cross } : { rows: cross, cols: side };
  }
  return null;
};

// How well known an MP is among those fitting the same slot, 1-99: the share
// of them who got fewer votes in the election (with the MP counted as half).
// There are no statistics of players' answers; the election result stands in
// for them.
const popularity = (mp, fits) => {
  const below = fits.filter((m) => m.electionVotes < mp.electionVotes).length;
  const level = fits.filter((m) => m.electionVotes === mp.electionVotes).length;
  return Math.min(99, Math.max(1, Math.round((100 * (below + level / 2)) / Math.max(1, fits.length))));
};
// The score is the sum of the picks' popularity; an empty slot (null) costs 100.
const slotScore = (points) => points.reduce((sum, p) => sum + (p === null ? 100 : p), 0);
const rarityTier = (p) => (p === null ? "none" : p <= 33 ? "green" : p <= 66 ? "yellow" : "orange");
const RARITY_SQUARE = { green: "🟩", yellow: "🟨", orange: "🟧", none: "⬜" };
// The slots as squares, `perRow` to a line.
const raritySquares = (points, perRow) => points.map((p, i) =>
  (i && i % perRow === 0 ? "\n" : "") + RARITY_SQUARE[rarityTier(p)]).join("");

if (typeof module !== "undefined") {
  module.exports = { categories, family, fitting, seatsPuzzle, gridPuzzle, popularity, slotScore, rarityTier, raritySquares, firstName,
    COALITION, independentLeans, LEAN_SHARE, MACRO_REGIONS, SEATS, GRID_MIN, fold, hash, dailyOrder, warsawDay, age, years, compareMps, guessFeedback, guessSquares, whoSquares, SQUARE, regionHint, REGIONS, surnameOf, surnameFirst, voteOf, whoPuzzle, shortTitle, surnameInitial };
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
  // The result to share: a line of words, rows of squares (no spoilers), and
  // the game's address, so sharing it brings people here; the #game part
  // opens the same game. Change SHARE_URL (and og:url in index.html) when the
  // games move to their own address.
  const SHARE_URL = "https://sejmomat.pl/sejmdle/";
  const copyText = async (text) => {
    try { await navigator.clipboard.writeText(text); return true; } catch { /* no clipboard here, or no permission */ }
    // the older way: select the text in an unseen box and ask the browser to copy it
    const box = h("textarea", { value: text, readOnly: true });
    box.style.cssText = "position:fixed;top:0;left:0;opacity:0";
    document.body.append(box);
    box.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { /* not allowed either */ }
    box.remove();
    return ok;
  };
  // The text is shown as it will be pasted, with: the system's share sheet
  // (phones, some desktop browsers), a copy button, and ready-made posts.
  const share = (game, lines) => {
    const text = [...lines, `Zagraj: ${SHARE_URL}#${game}`].join("\n");
    const status = h("p", { className: "muted share-status" });
    status.setAttribute("role", "status");
    const copy = async () => {
      status.textContent = (await copyText(text)) ? "Skopiowano — wklej, gdzie chcesz."
        : "Nie udało się skopiować. Zaznacz tekst powyżej i skopiuj ręcznie.";
    };
    const native = navigator.share && h("button", { type: "button", className: "btn primary", textContent: "Udostępnij",
      // closing the sheet without sharing is not an error; anything else falls back to copying
      onclick: () => navigator.share({ text }).catch((err) => { if (err.name !== "AbortError") copy(); }) });
    const post = (name, url) => h("a", { className: "btn", href: url + encodeURIComponent(text), target: "_blank",
      rel: "noopener", textContent: name, title: `Opublikuj wynik w serwisie ${name}` });
    return h("div", { className: "card share" }, [
      h("p", { className: "clue-label", textContent: "Podziel się wynikiem" }),
      h("pre", { className: "share-text", textContent: text }),
      h("div", { className: "share-actions" }, [native,
        h("button", { type: "button", className: native ? "btn" : "btn primary", textContent: "Skopiuj wynik", onclick: copy }),
        post("X", "https://x.com/intent/post?text="), post("Bluesky", "https://bsky.app/intent/compose?text=")]),
      status,
    ]);
  };
  const mpLink = (mp) => h("a", { href: `${SITE}posel/${mp.id}.html`, textContent: mp.name });
  const voteLink = (v, text) => h("a", { href: `${SITE}glosowanie/${v.s}-${v.n}.html`, textContent: text });
  const mpCard = (mp) => h("div", { className: "card reveal" }, [
    h("img", { className: "photo", src: PHOTO(mp.id), alt: mp.name, referrerPolicy: "no-referrer" }),
    h("div", {}, [
      h("p", {}, [h("strong", {}, [mpLink(mp)])]),
      h("p", { className: "muted", textContent: `${mp.clubName} · okręg ${mp.district} (${mp.voivodeship})` }),
    ]),
  ]);
  // Level for the two MP games. Hard: type the name. Easy: the same box plus
  // a grid of all MPs grouped by club (left to right), to pick from.
  let easy = store.get("sejmdle:easy") === "1";
  const levelNote = () => (easy ? " (poziom łatwy)" : "");
  const clubGroups = (data) => (data.groups ||= [...new Set([...data.clubAxis, ...data.mps.map((m) => m.club)])]
    .map((club) => ({
      club, name: CLUB_SHORT[club] || (club === "niez." ? "Niezrzeszeni" : club),
      mps: data.mps.filter((m) => m.club === club).sort((x, y) => surnameFirst(x).localeCompare(surnameFirst(y), "pl")),
    })).filter((g) => g.mps.length));
  // `used`: ids already guessed (greyed out in the grid); `rerender` redraws the game after a level change.
  const guessForm = (data, onGuess, rerender, used = [], label = "Zgaduję") => {
    const input = h("input", { type: "text", placeholder: easy ? "Wpisz nazwisko albo otwórz listę posłów…" : "Imię i nazwisko posła…", autocomplete: "off" });
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
    const setLevel = (value) => {
      easy = value;
      store.set("sejmdle:easy", value ? "1" : "0");
      rerender();
    };
    const seg = (text, on, value) => {
      const b = h("button", { type: "button", className: "seg", textContent: text, onclick: () => setLevel(value) });
      b.setAttribute("aria-pressed", String(on));
      return b;
    };
    const level = h("p", { className: "level" }, [
      h("span", { className: "muted", textContent: "Poziom:" }),
      h("span", { className: "segs" }, [seg("Trudny", !easy, false), seg("Łatwy — lista posłów", easy, true)]),
    ]);
    // Easy level: a button next to the box opens the list of MPs.
    const pick = easy && h("button", { type: "button", className: "btn", textContent: "☰ Lista posłów",
      onclick: () => showPicker(data, used, onGuess) });
    const form = h("div", { className: "guess" }, [input,
      h("button", { className: "btn primary", textContent: label, onclick: submit }), pick, msg]);
    return h("div", {}, [level, form]);
  };

  // The list of MPs as a popup: one column per club, left to right, scrolled
  // sideways; each column scrolls through its own names. Shortcuts at the top
  // jump to a club, the box filters by name, a click on a name is the guess.
  const JUMP_LABEL = { Polska2050: "PL2050", "PSL-TD": "PSL", RozwojPlus: "Rozwój+", Demokracja: "Kukiz", Konfederacja_KP: "KKP" };
  const pickDialog = h("dialog", { className: "picker" });
  const closePicker = () => (pickDialog.close ? pickDialog.close() : pickDialog.removeAttribute("open"));
  pickDialog.addEventListener("click", (e) => { if (e.target === pickDialog) closePicker(); });
  document.body.append(pickDialog);
  const showPicker = (data, used, onGuess) => {
    const names = [];
    const cols = clubGroups(data).map((g) => {
      const list = h("ul", {}, g.mps.map((m) => {
        const b = h("button", { type: "button", className: "name", textContent: surnameFirst(m),
          disabled: used.includes(m.id), onclick: () => { closePicker(); onGuess(m); } });
        const li = h("li", {}, [b]);
        names.push([fold(m.name), li]);
        return li;
      }));
      const count = h("span", { className: "muted", textContent: `(${g.mps.length})` });
      return { g, count, list, col: h("section", { className: "club-col" }, [h("h3", {}, [g.name, " ", count]), list]) };
    });
    const row = h("div", { className: "club-cols" }, cols.map((c) => c.col));
    const jump = h("p", { className: "club-jump" }, cols.map((c) => h("button", { type: "button", className: "chip",
      textContent: JUMP_LABEL[c.g.club] || c.g.club, title: c.g.name,
      onclick: () => c.col.scrollIntoView?.({ behavior: "smooth", block: "nearest", inline: "start" }) })));
    const filter = h("input", { type: "search", placeholder: "Szukaj po nazwisku…", autocomplete: "off" });
    filter.addEventListener("input", () => {
      const q = fold(filter.value);
      for (const [name, li] of names) li.hidden = Boolean(q) && !name.includes(q);
      // clubs with nobody left to show drop out of the row
      for (const c of cols) {
        const left = [...c.list.children].filter((li) => !li.hidden).length;
        c.col.hidden = left === 0;
        c.count.textContent = `(${q ? `${left} z ${c.g.mps.length}` : c.g.mps.length})`;
      }
    });
    pickDialog.replaceChildren(
      h("button", { type: "button", className: "help-close", textContent: "×", ariaLabel: "Zamknij", onclick: closePicker }),
      h("h2", { textContent: "Wybierz posła" }),
      h("p", { className: "muted picker-hint", textContent: "Kluby od lewej do prawej — przewijaj w bok. Kliknij nazwisko, żeby zgadnąć." }),
      filter, jump, row,
    );
    if (pickDialog.open) return;
    if (pickDialog.showModal) pickDialog.showModal(); else pickDialog.setAttribute("open", "");
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
      const cmps = guesses.map((g) => compareMps(g, target, data.clubAxis, DAY));
      const rows = guesses.map((g, i) => {
        const cmp = cmps[i];
        return h("tr", { className: g === guesses[guesses.length - 1] ? "latest" : "" }, [h("td", { className: "name", textContent: g.name }),
          ...COLS.map(([k]) => h("td", { className: cmp[k].color, textContent: `${cmp[k].text} ${cmp[k].arrow}`.trim() }))]);
      });
      draw(
        lead("Zgadnij posła dnia", "posel", [
          [`Wpisz imię i nazwisko dowolnego posła. Masz ${MAX_GUESSES} prób.`],
          ["Nie znasz posłów z nazwiska? Przełącz „Poziom” na łatwy: przycisk „Lista posłów” otworzy listę wszystkich posłów pogrupowanych klubami, z której wybierasz kliknięciem."],
          ["Po każdej próbie pola pokażą, jak blisko jesteś: ", tile("green", "zgadza się"), " ", tile("yellow", "blisko"), " ", tile("grey", "nie")],
          ["Strzałki prowadzą do celu: ← → klub bardziej na lewo lub prawo, ↑ ↓ liczba większa lub mniejsza."],
          ["Okręg ma o jeden kolor więcej: ", tile("green", "ten sam okręg"), " ", tile("blue", "to samo województwo"), " ",
            tile("yellow", "sąsiednie województwo"), " ", tile("grey", "dalej")],
          ["Przy okręgu strzałka działa jak kompas: pokazuje, w którą stronę na mapie leży szukane województwo (↑ północ, → wschód, ↘ południowy wschód…)."],
          ["Kluby od lewej do prawej: ", h("span", { className: "axis",
            textContent: data.clubAxis.map((c) => CLUB_SHORT[c] || c).join(" → ") })],
          ["Litera nazwiska działa jak słownik: „← przed K” znaczy, że szukane nazwisko zaczyna się wcześniej w alfabecie niż K, a „po K →”, że później."],
        ], `„Blisko” to: sąsiedni klub na tej liście, sąsiednie województwo, wiek ±5 lat, głosy w wyborach ±25%, frekwencja ±3 pkt proc., litera nazwiska najwyżej ${LETTER_CLOSE} litery dalej w alfabecie.`),
        marks(over ? "Próby:" : `Próba ${guesses.length + 1} z ${MAX_GUESSES}:`,
          Array.from({ length: MAX_GUESSES }, (_, k) => k >= guesses.length ? "todo" : (won && k === guesses.length - 1 ? "ok" : "used"))),
        guesses.length ? h("div", { className: "grid-scroll" }, [h("table", { className: "grid" }, [
          h("thead", {}, [h("tr", {}, [h("th", { textContent: "Poseł" }), ...COLS.map(([, t]) => h("th", { textContent: t }))])]),
          h("tbody", {}, rows),
        ])]) : null,
        !over && guessForm(data, (mp) => {
          if (!state.guesses.includes(mp.id)) { state.guesses.push(mp.id); save("posel", state); }
          render();
        }, render, state.guesses),
        over && h("p", { className: `result ${won ? "ok" : "bad"}`,
          textContent: won ? `Brawo! Trafione za ${guesses.length}. razem.` : "Tym razem się nie udało." }),
        over && mpCard(target),
        over && share("posel", [`Sejmdle ${label()} — Zgadnij posła${levelNote()}: ${won ? guesses.length : "X"}/${MAX_GUESSES}`,
          guessSquares(cmps, COLS.map(([k]) => k))]),
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
          share("przeszlo", [`Sejmdle ${label()} — Czy przeszło?: ${score}/${items.length}`,
            state.answers.map((a, k) => (a === items[k].adopted ? "🟩" : "🟥")).join("")]),
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
    // Region is left to the feedback on wrong guesses (with its compass
    // arrow), so the clues say something else: age, committees, club, photo.
    // The committee clue is skipped if the data file has no committee lists
    // at all (an older data file), rather than claiming the MP sits on none.
    const committees = mp.committees;
    const HINTS = [
      ["Wiek", () => years(age(mp.birthDate, DAY))],
      committees && ["Komisje sejmowe", () => (committees.length
        ? h("ul", { className: "committees" }, committees.map((c) => h("li", { textContent: c })))
        : "Nie zasiadam w żadnej komisji sejmowej.")],
      ["Klub", () => mp.clubName],
      ["Zdjęcie", () => h("img", { className: "photo", src: PHOTO(mp.id), alt: "Zdjęcie posła", referrerPolicy: "no-referrer" })],
    ].filter(keep);
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
            tile("green", "ten sam klub"), " ", tile("blue", "to samo województwo"), " ",
            tile("yellow", "sąsiednie województwo"), " ", tile("grey", "nic wspólnego")],
          ["Jeśli województwo się nie zgadza, strzałka-kompas pokaże, w którą stronę na mapie leży właściwe (↑ północ, → wschód)."],
          ["Każda zła odpowiedź i każde „Pomiń” odsłania kolejną podpowiedź: wiek, komisje sejmowe, klub, zdjęcie."],
          [`Zaczynasz z ${max} punktami, a każdy taki krok zabiera jeden.`],
          ["Nie znasz posłów z nazwiska? Przełącz „Poziom” na łatwy: przycisk „Lista posłów” otworzy listę wszystkich posłów pogrupowanych klubami, z której wybierasz kliknięciem."],
        ]),
        marks("Punkty:", Array.from({ length: max }, (_, k) => (!state.lost && k < points) ? (state.won ? "ok" : "used") : "todo")),
        ...timeline,
        !over && guessForm(data, (guess) => {
          if (guess.id === mp.id) { state.won = true; save("kim", state); render(); }
          else if (!state.steps.includes(guess.id)) step(guess.id);
        }, render, state.steps.filter((v) => v !== "hint")),
        !over && h("button", { className: "btn", onclick: () => step("hint"),
          textContent: state.steps.length < HINTS.length ? "Pomiń — pokaż kolejną podpowiedź" : "Poddaję się" }),
        over && h("div", { className: `card answer ${state.won ? "won" : "lost"}` }, [
          h("p", { className: "clue-label", textContent: state.won ? `Odpowiedź · ${points} pkt z ${max}` : "Odpowiedź · 0 pkt" }),
          mpCard(mp),
        ]),
        over && share("kim", [`Sejmdle ${label()} — Kim jestem?${levelNote()}: ${state.won ? points : 0}/${max} pkt`,
          whoSquares(state.steps.map((v) => {
            const guess = v === "hint" ? null : data.byId.get(v);
            return guess ? guessFeedback(guess, mp).color : "hint";
          }), state.won)]),
        nextButton("kim", over),
      );
    };
    render();
  };

  // ---- 4. Prezydium and 5. Siatka
  // One engine for both: slots, each with conditions and the MPs who fit
  // them. A click picks a slot, a guess fills it; a wrong guess costs one of
  // the allowed mistakes. The games differ in the puzzle and in `board`,
  // which lays the slots out (`slot(i, withConditions)` gives one slot).
  const playSlots = (data, { game, title, shareName, perRow, intro, slots, board }) => {
    const n = slots.length, maxMistakes = n;
    const saved = load(game);
    // picks: an MP's id per slot (null = empty); wrong: "slot:id" of each wrong guess
    const state = saved && Array.isArray(saved.picks) && saved.picks.length === n ? saved
      : { picks: Array(n).fill(null), wrong: [], done: false };
    const nextOpen = (from) => {
      for (let k = 1; k <= n; k++) if (state.picks[(from + k) % n] === null) return (from + k) % n;
      return -1;
    };
    let active = nextOpen(-1), flash = null;
    const render = (focus) => {
      const over = state.done;
      const picked = state.picks.map((id) => (id === null ? null : data.byId.get(id) || null));
      const points = picked.map((mp, i) => (mp ? popularity(mp, slots[i].fits) : null));
      const score = slotScore(points), filled = points.filter((p) => p !== null).length;
      const names = (s) => s.cats.map((c) => c.label).join(" + ");
      const votes = (mp) => mp.electionVotes.toLocaleString("pl-PL");
      const slot = (i, withConditions) => {
        const s = slots[i], mp = picked[i];
        const conditions = withConditions ? [s.title && h("span", { className: "slot-title", textContent: s.title }),
          ...s.cats.map((c) => h("span", { className: "slot-cond" }, [c.label, c.detail ? h("small", { textContent: c.detail }) : null]))] : [];
        if (mp) {
          return h("div", { className: "slot filled" }, [...conditions,
            h("img", { className: "thumb", src: PHOTO(mp.id), alt: "", referrerPolicy: "no-referrer" }),
            h("span", { className: "slot-name" }, [over ? mpLink(mp) : mp.name]),
            h("span", { className: `pts ${rarityTier(points[i])}`, textContent: points[i],
              title: `Punkty popularności: ${votes(mp)} głosów w wyborach` })]);
        }
        if (over) return h("div", { className: "slot missed" }, [...conditions, h("span", { className: "pts none", textContent: "100", title: "Puste miejsce" })]);
        const b = h("button", { type: "button", className: `slot open${i === active ? " active" : ""}`,
          onclick: () => { active = i; flash = null; render(true); } },
          [...conditions, withConditions ? null : h("span", { className: "slot-plus", textContent: "+" })]);
        b.setAttribute("aria-pressed", String(i === active));
        b.setAttribute("aria-label", names(s));
        return b;
      };
      const onGuess = (mp) => {
        if (active < 0) return;
        const s = slots[active];
        if (state.picks.includes(mp.id)) {
          flash = { ok: false, text: `${mp.name} ma już swoje miejsce. Każdy poseł może być użyty tylko raz.` };
        } else if (s.fits.includes(mp)) {
          state.picks[active] = mp.id;
          flash = { ok: true, text: `${mp.name} pasuje: ${popularity(mp, s.fits)} pkt popularności.` };
          active = nextOpen(active);
        } else {
          if (!state.wrong.includes(`${active}:${mp.id}`)) state.wrong.push(`${active}:${mp.id}`);
          const failed = s.cats.filter((c) => !c.test(mp)).map((c) => c.label);
          flash = { ok: false, text: `${mp.name} nie pasuje — ${failed.length > 1 ? "nie spełnia warunków" : "nie spełnia warunku"}: ${failed.join(", ")}.` };
        }
        if (!state.picks.includes(null) || state.wrong.length >= maxMistakes) state.done = true;
        save(game, state);
        render(true);
      };
      draw(
        lead(title, game, [
          ...intro,
          ["Kliknij miejsce, a potem wpisz posła. Każdy poseł może być użyty tylko raz."],
          ["Im mniej znany poseł, tym lepiej. Za każde miejsce dostajesz od 1 do 99 punktów popularności: ",
            tile("green", "mało znany"), " ", tile("yellow", "średnio"), " ", tile("orange", "bardzo znany"),
            ". Puste miejsce to 100 punktów. Liczy się jak najniższa suma."],
          ["Skąd punkty? Z głosów, które posłowie zdobyli w wyborach do Sejmu w 2023 r. — nie z odpowiedzi innych graczy. Porównujemy tylko posłów pasujących do danego miejsca: ten z najmniejszą liczbą głosów dostaje około 1 punktu, ten z największą około 99."],
          [`Możesz się pomylić ${maxMistakes} razy. Zła odpowiedź nie zajmuje miejsca, ale zabiera jedną pomyłkę.`],
          ["Regiony to grupy sąsiednich województw (makroregiony GUS), np. Polska północna to pomorskie, kujawsko-pomorskie i warmińsko-mazurskie. Skład regionu zobaczysz po kliknięciu miejsca."],
          [`Koalicja rządząca to kluby: ${COALITION.map(clubShort).join(", ")}. Opozycja to pozostałe kluby i koła. Posłowie niezrzeszeni liczą się do strony, z którą głosują: z koalicją, jeśli w spornych głosowaniach nad całymi ustawami co najmniej ${Math.round(LEAN_SHARE * 100)}% ich głosów było takich jak większości koalicji, z opozycją — jeśli najwyżej ${Math.round((1 - LEAN_SHARE) * 100)}%.`],
          ["Nie znasz posłów z nazwiska? Przełącz „Poziom” na łatwy: przycisk „Lista posłów” otworzy listę wszystkich posłów pogrupowanych klubami."],
        ], "Liczba głosów to tylko przybliżenie rozpoznawalności: zależy też od wielkości okręgu i miejsca na liście."),
        marks(over ? "Pomyłki:" : `Pomyłki (${state.wrong.length} z ${maxMistakes}):`,
          Array.from({ length: maxMistakes }, (_, k) => (k < state.wrong.length ? "bad" : "todo"))),
        h("p", { className: "score-line" }, [h("strong", { textContent: `Wynik: ${score} pkt` }),
          h("span", { className: "muted", textContent: ` · im mniej, tym lepiej · obsadzone ${filled} z ${n}` })]),
        h("p", { className: "muted points-source", textContent: "Punkty to popularność posła: im więcej głosów zdobył w wyborach 2023 r. na tle innych pasujących do miejsca, tym więcej punktów." }),
        board(slot),
        flash && h("p", { className: `result ${flash.ok ? "ok" : "bad"}`, textContent: flash.text }),
        !over && active >= 0 && h("p", { className: "picking" }, ["Szukasz posła, który pasuje do: ",
          ...slots[active].cats.flatMap((c, k) => [k ? " + " : "", h("strong", { textContent: c.label }), c.detail ? ` (${c.detail})` : ""])]),
        !over && guessForm(data, onGuess, () => render(), state.picks.filter((id) => id !== null), "Wstawiam"),
        !over && h("p", { className: "next" }, [h("button", { type: "button", className: "btn quiet", textContent: "Kończę — pokaż wynik",
          onclick: () => { state.done = true; flash = null; save(game, state); render(); } })]),
        over && h("p", { className: `result ${filled === n ? "ok" : "bad"}`,
          textContent: filled === n ? `Komplet! Wynik: ${score} pkt.` : `Koniec gry. Wynik: ${score} pkt, obsadzone ${filled} z ${n}.` }),
        over && share(game, [`Sejmdle ${label()} — ${shareName}${levelNote()}: ${score} pkt (im mniej, tym lepiej)`, raritySquares(points, perRow)]),
        // what the best answers were: the three least known MPs fitting each slot
        over && h("details", { className: "context" }, [
          h("summary", { textContent: "Najrzadsze możliwe odpowiedzi (z liczbą głosów w wyborach)" }),
          h("ul", { className: "answers" }, slots.map((s) => h("li", {}, [h("strong", { textContent: names(s) }),
            ` (pasujących posłów: ${s.fits.length}) — `,
            ...[...s.fits].sort((a, b) => a.electionVotes - b.electionVotes).slice(0, 3).flatMap((m, k) => [k ? ", " : "", mpLink(m), ` (${votes(m)})`])]))),
        ]),
        nextButton(game, over),
      );
      // after a click on a slot or a guess, typing can go on without another click
      if (focus && !over && !easy) main.querySelector(".guess input")?.focus({ preventScroll: true });
    };
    render();
  };
  const noPuzzle = () => draw(h("p", { textContent: "Nie udało się ułożyć zagadki z dzisiejszych danych. Spróbuj ponownie później." }));
  const allCategories = (data) => (data.cats ||= categories(data));

  const playPrezydium = (data) => {
    const seats = seatsPuzzle(data, seedFor("prezydium"), allCategories(data));
    if (seats.length < SEATS) { noPuzzle(); return; }
    playSlots(data, {
      game: "prezydium", title: "Prezydium dnia", shareName: "Prezydium", perRow: SEATS,
      intro: [[`Obsadź ${SEATS} miejsc w Prezydium Sejmu: marszałka i wicemarszałków. Na każde miejsce wskaż posła, który spełnia wszystkie podane przy nim warunki.`]],
      slots: seats.map((cats, i) => ({ title: i ? "Wicemarszałek" : "Marszałek", cats, fits: fitting(data, cats) })),
      board: (slot) => h("div", { className: "seats" }, seats.map((_, i) => slot(i, true))),
    });
  };

  const playSiatka = (data) => {
    const grid = gridPuzzle(data, seedFor("siatka"), allCategories(data));
    if (!grid) { noPuzzle(); return; }
    const { rows, cols } = grid;
    const head = (c, scope) => { const th = h("th", { textContent: c.label, title: c.detail }); th.setAttribute("scope", scope); return th; };
    playSlots(data, {
      game: "siatka", title: "Siatka dnia", shareName: "Siatka", perRow: cols.length,
      intro: [["Wypełnij 9 pól siatki. W każde pole wpisz posła, który pasuje jednocześnie do warunku ze swojego wiersza i ze swojej kolumny."]],
      slots: rows.flatMap((r) => cols.map((c) => ({ cats: [r, c], fits: fitting(data, [r, c]) }))),
      board: (slot) => h("table", { className: "siatka" }, [
        h("thead", {}, [h("tr", {}, [h("td"), ...cols.map((c) => head(c, "col"))])]),
        h("tbody", {}, rows.map((r, ri) => h("tr", {}, [head(r, "row"),
          ...cols.map((_, ci) => h("td", {}, [slot(ri * cols.length + ci, false)]))]))),
      ]),
    });
  };

  // ---- start
  const GAMES = { posel: playPosel, przeszlo: playPrzeszlo, kim: playKim, prezydium: playPrezydium, siatka: playSiatka };
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
