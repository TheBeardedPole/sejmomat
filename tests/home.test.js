// Rules of the home page (static/home.js): broadcasts, interests, events, MPs.
// Run: node --test tests/
const test = require("node:test");
const assert = require("node:assert/strict");
const H = require("../static/home.js");

const v = (type, start, end = null, extra = {}) => ({ type, title: `${type} ${start}`, startDateTime: start, endDateTime: end, ...extra });

test("a broadcast whose time has come is only a candidate; plenary first", () => {
  const now = "2026-11-05T11:00:00";
  const p = H.pickBroadcasts([
    v("komisja", "2026-11-05T10:00:00", "2026-11-05T12:00:00"),
    v("posiedzenie", "2026-11-05T10:00:00"),
    v("komisja", "2026-11-05T08:00:00", "2026-11-05T09:00:00"),   // over
    v("komisja", "2026-11-04T10:00:00"),                           // yesterday, no end: not current
    v("posiedzenie", "2026-11-06T10:00:00"),
  ], now);
  assert.deepEqual(p.current.map((x) => x.type), ["posiedzenie", "komisja"]);
  assert.equal(p.next.startDateTime, "2026-11-06T10:00:00");
  assert.equal(p.nextPlenary, null);
});

test("the next broadcast, and the next plenary sitting when the next is something else", () => {
  const p = H.pickBroadcasts([v("inne", "2026-11-03T12:00:00"), v("posiedzenie", "2026-11-05T10:00:00")], "2026-11-01T09:00:00");
  assert.equal(p.next.type, "inne");
  assert.equal(p.nextPlenary.startDateTime, "2026-11-05T10:00:00");
});

test("live only when the stream is confirmed; a schedule alone is 'scheduled'", () => {
  const picked = H.pickBroadcasts([v("posiedzenie", "2026-11-05T10:00:00")], "2026-11-05T10:05:00");
  assert.equal(H.broadcastState(picked, -1).state, "scheduled");
  const live = H.broadcastState(picked, 0);
  assert.equal(live.state, "live");
  assert.deepEqual(live.others, []);
});

test("no broadcast ahead is 'none'; no data is 'error', not 'none'", () => {
  assert.equal(H.broadcastState(H.pickBroadcasts([], "2026-11-05T10:00:00"), -1).state, "none");
  assert.equal(H.broadcastState(null, -1).state, "error");
});

test("a stream is on only when its playlist lists segments", async () => {
  const master = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nlow/chunks.m3u8\n";
  const serve = (pages) => async (url) => {
    const body = pages[url];
    return body === undefined ? { ok: false } : { ok: true, url, text: async () => body };
  };
  const planned = serve({ "https://x/p.m3u8": master, "https://x/low/chunks.m3u8": "#EXTM3U\n#EXT-X-TARGETDURATION:0\n" });
  const on = serve({ "https://x/p.m3u8": master, "https://x/low/chunks.m3u8": "#EXTM3U\n#EXTINF:6.0,\nseg1.ts\n" });
  assert.equal(await H.streamIsOn("https://x/p.m3u8", planned), false);
  assert.equal(await H.streamIsOn("https://x/p.m3u8", on), true);
  assert.equal(await H.streamIsOn("https://x/missing.m3u8", on), false);
  const failing = async () => { throw new TypeError("blocked"); };
  assert.equal(await H.streamIsOn("https://x/p.m3u8", failing), false);
});

test("dates in Warsaw time, whatever the browser's zone", () => {
  assert.equal(H.formatWhen("2026-11-05T10:00:00", "pl"), "5 listopada, 10:00");
  assert.equal(H.formatWhen("2026-11-05T10:00:00", "en"), "5 November, 10:00");
  assert.equal(H.formatWhen("2026-11-05", "pl", true), "5 listopada 2026");
  // 23:30 UTC on 31 March is already 1 April in Warsaw (summer time)
  assert.equal(H.warsawNow(new Date("2026-03-31T23:30:00Z")).slice(0, 16), "2026-04-01T01:30");
});

test("interests: save, skip, and the 30-day question", () => {
  const s = H.saveInterests(["zdrowie", "edukacja", "zdrowie"], "2026-10-01");
  assert.deepEqual(s, { ids: ["zdrowie", "edukacja"], saved: "2026-10-01", asked: "2026-10-01" });
  assert.equal(H.reminderDue(s, "2026-10-30"), false);
  assert.equal(H.reminderDue(s, "2026-10-31"), true);
  // "No": the same interests, asked again 30 days on
  const kept = H.confirmInterests(s, "2026-10-31");
  assert.deepEqual(kept.ids, s.ids);
  assert.equal(H.reminderDue(kept, "2026-11-29"), false);
  assert.equal(H.reminderDue(kept, "2026-11-30"), true);
  // no answer: nothing changes, so the question stays due
  assert.equal(H.reminderDue(s, "2026-12-15"), true);
  // skipped: never reminded
  assert.equal(H.reminderDue(H.skipInterests("2026-10-01"), "2027-01-01"), false);
});

test("interests survive a reload and a broken store", () => {
  const store = new Map();
  const storage = { getItem: (k) => store.get(k) ?? null, setItem: (k, val) => store.set(k, val) };
  H.writeInterests(storage, H.saveInterests(["rolnictwo"], "2026-10-01"));
  assert.deepEqual(H.readInterests(storage).ids, ["rolnictwo"]);
  store.set(H.INTERESTS_KEY, "{not json");
  assert.equal(H.readInterests(storage), null);
  const blocked = { getItem: () => { throw new Error("denied"); }, setItem: () => { throw new Error("denied"); } };
  assert.equal(H.readInterests(blocked), null);
  assert.deepEqual(H.writeInterests(blocked, { ids: ["x"] }), { ids: ["x"] });
});

const events = [
  { k: "stage", d: "2026-10-20", root: "1", s: "I czytanie w komisjach", m: { zdrowie: [["tag", "Szpitale"]] } },
  { k: "vote", d: "2026-10-10", root: "1", s: "Ustawa przyjęta", o: "adopted", m: { zdrowie: [["tag", "Szpitale"]] } },
  { k: "vote", d: "2026-10-22", root: "2", s: "Ustawa przyjęta", o: "adopted", m: { rolnictwo: [["committee", "RRW"]] } },
  { k: "agenda", d: "2026-11-05", root: "3", s: "", m: { zdrowie: [["committee", "ZDR"]], edukacja: [["tag", "Edukacja"]] } },
];

test("only events in the chosen topics, newest first, each with its reasons", () => {
  const mine = H.eventsFor(events, ["zdrowie"]);
  assert.deepEqual(mine.map((e) => e.root + e.k), ["3agenda", "1stage", "1vote"]);
  assert.deepEqual(Object.keys(mine[0].mine), ["zdrowie"]);   // the edukacja match is not shown as a reason
  assert.deepEqual(H.eventsFor(events, []), []);
});

test("highlights: one per bill, decisions before steps", () => {
  const top = H.highlights(H.eventsFor(events, ["zdrowie", "rolnictwo"]), "2026-10-24");
  assert.deepEqual(top.map((e) => `${e.root}:${e.k}`), ["2:vote", "1:vote", "3:agenda"]);
});

test("suggested MPs: scores added across topics, reasons kept once", () => {
  const data = { suggested: {
    zdrowie: [{ id: 7, score: 4, why: [{ k: "committee", code: "ZDR", fn: "" }] }, { id: 9, score: 3, why: [{ k: "questions", n: 3, recent: 3, to: ["minister zdrowia"] }] }],
    edukacja: [{ id: 9, score: 3, why: [{ k: "committee", code: "ENM", fn: "" }] }],
  } };
  const rows = H.suggestMps(data, ["zdrowie", "edukacja"]);
  assert.deepEqual(rows.map((r) => [r.id, r.score]), [[9, 6], [7, 4]]);
  assert.deepEqual(rows[0].topics, ["zdrowie", "edukacja"]);
  assert.equal(rows[0].why.length, 2);
  assert.deepEqual(H.suggestMps(data, ["rolnictwo"]), []);
});
