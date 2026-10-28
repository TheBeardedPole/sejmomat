// Broadcast availability and Warsaw-time presentation shared by both pages.
const SejmomatBroadcasts = (() => {
// ---- time: the API's times are Warsaw time without a zone ("2026-11-05T10:00:00")
const warsawNow = (now = new Date()) => new Intl.DateTimeFormat("sv-SE", {
  timeZone: "Europe/Warsaw", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
}).format(now).replace(" ", "T");

// "5 listopada, 10:00" from a Warsaw time, without the browser's own zone getting in the way
const formatWhen = (iso, lang = "pl", withYear = false) => {
  const [d, t] = iso.split("T");
  const [y, m, day] = d.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, day, 12));
  const opts = { timeZone: "UTC", day: "numeric", month: "long", ...(withYear ? { year: "numeric" } : {}) };
  const text = new Intl.DateTimeFormat(lang === "en" ? "en-GB" : "pl-PL", opts).format(date);
  return t ? `${text}, ${t.slice(0, 5)}` : text;
};


// "czwartek, 5 listopada 2026" / "Thursday 5 November 2026" for a day
const formatDay = (day, lang = "pl", weekday = true) => {
  const [y, m, d] = day.slice(0, 10).split("-").map(Number);
  return new Intl.DateTimeFormat(lang === "en" ? "en-GB" : "pl-PL", {
    timeZone: "UTC", day: "numeric", month: "long", year: "numeric", ...(weekday ? { weekday: "long" } : {}),
  }).format(new Date(Date.UTC(y, m - 1, d, 12)));
};

// "20–22 października 2026", as the build's date_range filter has it
const dateRange = (first, last, lang = "pl") => {
  const one = (x) => formatDay(x, lang, false);
  if (first.slice(0, 10) === last.slice(0, 10)) return one(first);
  if (first.slice(0, 7) !== last.slice(0, 7)) return `${one(first)} – ${one(last)}`;
  return `${Number(first.slice(8, 10))}–${one(last)}`;
};

// the Polish form for n: plural(n, ["temat", "tematy", "tematów"]); English passes [one, other, other]
const plural = (n, [one, few, many]) => {
  if (n === 1) return one;
  return n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? few : many;
};

// ---- broadcasts
const PLENARY = "posiedzenie";

// Of the API's broadcasts: those whose scheduled time has come and not passed
// (candidates for live; plenary first), and the next one to start (with the
// next plenary sitting too, when the next broadcast is something else).
const pickBroadcasts = (videos, now) => {
  const today = now.slice(0, 10);
  const byStart = [...videos].filter((v) => v.startDateTime).sort((a, b) => a.startDateTime.localeCompare(b.startDateTime));
  const current = byStart
    .filter((v) => v.startDateTime <= now && v.startDateTime.slice(0, 10) === today && (!v.endDateTime || now < v.endDateTime))
    .sort((a, b) => (b.type === PLENARY) - (a.type === PLENARY));
  const ahead = byStart.filter((v) => v.startDateTime > now);
  const next = ahead[0] || null;
  const nextPlenary = next && next.type !== PLENARY ? ahead.find((v) => v.type === PLENARY) || null : null;
  return { current, next, nextPlenary };
};

// Is there video in a stream? Its playlist names the variants; a variant's
// playlist lists segments (#EXTINF) once there is something to play.
const hasSegments = (text) => /#EXTINF/.test(text || "");
const firstVariant = (text) => (text || "").split("\n").map((l) => l.trim()).find((l) => l && !l.startsWith("#")) || null;

const streamIsOn = async (url, fetchFn = fetch, timeoutMs = 8000) => {
  const get = async (u) => {
    const ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer = ctrl && setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const r = await fetchFn(u, { cache: "no-store", signal: ctrl?.signal });
      if (!r.ok) return null;
      return { text: await r.text(), url: r.url || u };
    } finally {
      if (timer) clearTimeout(timer);
    }
  };
  try {
    const master = await get(url);
    if (!master) return false;
    if (hasSegments(master.text)) return true;
    const variant = firstVariant(master.text);
    if (!variant) return false;
    const media = await get(new URL(variant, master.url).href);
    return !!media && hasSegments(media.text);
  } catch {
    return false;
  }
};

// What the box says: "live" (confirmed), "scheduled" (its time has come but no
// video yet, or it cannot be checked from here), "next", "none" or "error".
const broadcastState = (picked, liveIndex) => {
  if (!picked) return { state: "error" };
  const { current, next, nextPlenary } = picked;
  if (liveIndex !== -1 && current[liveIndex]) {
    return { state: "live", video: current[liveIndex], others: current.filter((_, i) => i !== liveIndex) };
  }
  if (current.length) return { state: "scheduled", video: current[0], next, nextPlenary };
  if (next) return { state: "next", video: next, nextPlenary };
  return { state: "none" };
};


// One decision for both pages: a scheduled time alone never proves a live stream.
const load = async ({ api, yt, days = 60, now = warsawNow(), fetchFn = fetch,
  checkOurs = (url, fresh) => window.SejmomatYT?.check(url, fresh) }) => {
  const today = now.slice(0, 10);
  const till = new Date(Date.parse(`${today}T12:00:00Z`) + days * 86400000).toISOString().slice(0, 10);
  const own = yt ? Promise.resolve().then(() => checkOurs(yt, true)).catch(() => null) : Promise.resolve(null);
  let videos = null;
  try {
    const response = await fetchFn(`${api}?since=${today}&till=${till}&limit=500`, { cache: "no-store" });
    if (!response.ok) throw new Error(response.status);
    const data = await response.json();
    if (!Array.isArray(data)) throw new TypeError("Invalid broadcast list");
    videos = data.filter((v) => v && typeof v.startDateTime === "string" && v.startDateTime.slice(0, 10) >= today)
      .sort((a, b) => a.startDateTime.localeCompare(b.startDateTime) || (a.title || "").localeCompare(b.title || ""));
  } catch {
    // null means unavailable; an empty list is a successful response with no broadcasts
  }
  const picked = videos === null ? null : pickBroadcasts(videos, now);
  const current = picked?.current || [];
  const confirmed = await Promise.all(current.map((v) => v.videoLink ? streamIsOn(v.videoLink, fetchFn) : false));
  const liveIndex = confirmed.indexOf(true);
  let state = broadcastState(picked, liveIndex);
  if (liveIndex !== -1) state = { ...state, others: current.filter((v, i) => i !== liveIndex && confirmed[i]) };
  const ours = await own;
  if (ours) state = { state: "ours", yt: ours };
  return { videos, state, ours, live: new Set(current.filter((v, i) => confirmed[i]).map((v) => v.unid)), checkedAt: now };
};

  return { warsawNow, formatWhen, formatDay, dateRange, plural, PLENARY,
    pickBroadcasts, hasSegments, firstVariant, streamIsOn, broadcastState, load };
})();
if (typeof module !== "undefined" && module.exports) module.exports = SejmomatBroadcasts;
else window.SejmomatBroadcasts = SejmomatBroadcasts;
