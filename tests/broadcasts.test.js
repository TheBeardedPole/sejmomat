const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const B = require('../static/broadcasts.js');

const now = '2026-11-05T10:30:00';
const video = (unid, type = 'posiedzenie', startDateTime = '2026-11-05T10:00:00') => ({
  unid, type, startDateTime, endDateTime: '2026-11-05T12:00:00', title: unid, videoLink: `https://video/${unid}`,
});
const serve = (videos, on = []) => async (url) => url.startsWith('https://list?')
  ? { ok: true, json: async () => videos }
  : { ok: true, url, text: async () => on.includes(url.split('/').at(-1)) ? '#EXTM3U\n#EXTINF:6,\nx.ts' : '#EXTM3U' };

test('availability combines schedule and actual segments; only confirmed alternatives are live', async () => {
  const result = await B.load({ api: 'https://list', now,
    fetchFn: serve([video('planned'), video('committee', 'komisja'), video('plenary')], ['committee', 'plenary']) });
  assert.equal(result.state.state, 'live');
  assert.equal(result.state.video.unid, 'plenary');
  assert.deepEqual(result.state.others.map(v => v.unid), ['committee']);
  assert.deepEqual([...result.live].sort(), ['committee', 'plenary']);
});

test('empty, planned, future, unavailable and malformed listings stay distinct', async () => {
  for (const [videos, state] of [[[], 'none'], [[video('planned')], 'scheduled'],
    [[video('future', 'posiedzenie', '2026-11-06T10:00:00')], 'next'], [{ invalid: true }, 'error']]) {
    const result = await B.load({ api: 'https://list', now, fetchFn: serve(videos) });
    assert.equal(result.state.state, state);
    assert.equal(result.videos === null, state === 'error');
  }
  const result = await B.load({ api: 'https://list', now, fetchFn: async () => { throw Error('offline'); } });
  assert.equal(result.state.state, 'error');
});

test('owned coverage wins even if listing fails; owned-status failures do not hide confirmed streams', async () => {
  const ours = { live: true, id: '12345678901', title: 'Ours' };
  const result = await B.load({ api: 'https://list', yt: '/own', now,
    fetchFn: async () => { throw Error('offline'); }, checkOurs: async () => ours });
  assert.equal(result.state.state, 'ours');
  assert.equal(result.state.yt, ours);
  const official = await B.load({ api: 'https://list', yt: '/own', now,
    fetchFn: serve([video('plenary')], ['plenary']), checkOurs: async () => { throw Error('offline'); } });
  assert.equal(official.state.state, 'live');
});

test('stream probes follow relative master links after redirects and tolerate denied streams', async () => {
  const result = await B.load({ api: 'https://list', now, fetchFn: async url => {
    if (url.startsWith('https://list?')) return { ok: true, json: async () => [video('p')] };
    if (url === 'https://video/p') return { ok: true, url: 'https://edge/path/master.m3u8', text: async () => '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nlow/playlist.m3u8' };
    assert.equal(url, 'https://edge/path/low/playlist.m3u8');
    return { ok: true, text: async () => '#EXTM3U\n#EXTINF:6,\nx.ts' };
  } });
  assert.equal(result.state.state, 'live');
  const denied = await B.load({ api: 'https://list', now, fetchFn: async url => url.startsWith('https://list?')
    ? { ok: true, json: async () => [video('p')] } : { ok: false } });
  assert.equal(denied.state.state, 'scheduled');
});

// Exercise actual page wiring with a minimal DOM, not a second implementation of the rules.
class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.dataset = {}; this.textContent = ''; this.className = ''; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(name, value) { this[name] = value; }
  addEventListener() {}
  closest() { return this; }
  get classList() { return { add() {}, remove() {}, toggle() {} }; }
}
const textOf = node => typeof node === 'string' ? node : `${node.textContent || ''} ${node.children.map(textOf).join(' ')}`;

async function page(script) {
  const root = new Element();
  root.dataset = { api: 'https://list', schedule: 'transmisje.html', committees: '[]', prints: '[]', interests: '{}',
    labels: JSON.stringify({ live: 'LIVE', liveBadge: 'LIVE', watch: 'Watch', newTab: 'New tab', now: 'Now',
      types: { posiedzenie: 'Sitting' }, filters: { all: 'All', plenary: 'Plenary', committees: 'Committees', other: 'Other' },
      count1: '1 stream', src: 'Checked {when}' }) };
  const broadcasts = { ...B, warsawNow: () => now,
    load: options => B.load({ ...options, now, fetchFn: serve([video('plenary')], ['plenary']) }) };
  const context = vm.createContext({ window: { SejmomatBroadcasts: broadcasts },
    document: { documentElement: { lang: 'en' }, getElementById: id => id === (script === 'home' ? 'transmisja' : 'harmonogram') ? root : null,
      createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag) },
    localStorage: { getItem: () => null }, location: { hash: '' }, setInterval() {}, console,
  });
  vm.runInContext(fs.readFileSync(require.resolve('../static/interests-state.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(require.resolve(`../static/${script}.js`), 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.match(textOf(root), /plenary/);
  assert.match(textOf(root), /LIVE/);
}

test('home and schedule both render shared availability; schedule runs without home.js globals', async () => {
  await page('home');
  await page('schedule');
});

test('every template loading home or schedule declares shared scripts first', () => {
  for (const file of ['index.html', 'events.html', 'mps_for_you.html', 'schedule.html']) {
    const source = fs.readFileSync(`templates/${file}`, 'utf8');
    const target = source.indexOf(file === 'schedule.html' ? 'static/schedule.js?v=' : 'static/home.js?v=');
    for (const shared of ['static/broadcasts.js?v=', 'static/interests-state.js?v=']) {
      assert.ok(source.indexOf(shared) >= 0 && source.indexOf(shared) < target, `${file}: ${shared}`);
    }
    if (file === 'schedule.html') assert.ok(!source.includes('static/home.js?v='));
  }
});
