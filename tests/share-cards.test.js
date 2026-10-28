const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('comparison waits for bundled fonts, preserves names and figures, exports PNG', async () => {
  const drawn = [], pending = [];
  const context = new Proxy({
    measureText: (s) => ({ width: String(s).length * 20 }),
    fillText: (s) => drawn.push(String(s)),
  }, { get: (target, key) => key in target ? target[key] : () => {} });
  const document = {
    fonts: { load: (font) => new Promise(resolve => pending.push({ font, resolve })) },
    createElement: () => ({ getContext: () => context, toBlob: (done, type) => done({ type }) }),
  };
  const window = {};
  vm.runInNewContext(fs.readFileSync('static/card.js', 'utf8'), { window, document, Intl, Date });
  const a = { name: 'Klub pierwszy', sub: 'Koalicja', members: 99, cohesion: .99, effectiveness: .5, turnout: .9, speeches: 12, questions: 15 };
  const b = { ...a, name: 'Klub drugi', members: 20 };
  const rendering = window.SejmomatCards.compareClubs(a, b, null, null);
  assert.equal(drawn.length, 0);
  assert.equal(pending.length, 3);
  assert.ok(pending.some(p => p.font.includes('Source Serif 4')));
  pending.forEach(p => p.resolve([]));
  const canvas = await rendering;
  assert.equal(canvas.width, 1200);
  assert.ok(canvas.height >= 675 && canvas.height < 3000);
  for (const value of ['Klub pierwszy', 'Klub drugi', '99', '20', '99,0%']) assert.ok(drawn.includes(value), value);
  assert.equal((await window.SejmomatCards.toBlob(canvas)).type, 'image/png');
});
