/**
 * [startup:F3] BLACK-6 — Help ▸ Contact & Support "Safe graphics" switch (ui/modules/help.js).
 * The switch reads/saves GET/POST /api/graphics-mode; the status line says plainly what is
 * saved, since when, why it was switched on automatically and whether it applies now or
 * from the next launch. A failed save is said beside the switch and the tick goes back
 * (never alert/confirm — they are no-ops in the app's WebView2).
 * Run: node tests/js/test_safe_graphics.js
 */
import assert from 'node:assert/strict';
import { graphicsStatusText, wireGraphicsSwitch } from '../../ui/modules/help.js';

let passed = 0;
let failed = 0;
const queue = [];                 // run ONE at a time: the tests share globalThis.fetch
function test(name, fn) { queue.push([name, fn]); }
async function runAll() {
  for (const [name, fn] of queue) {
    try { await fn(); console.log(`  ✓ ${name}`); passed++; }
    catch (err) { console.error(`  ✗ ${name}`); console.error(err); failed++; }
  }
}
const tick = () => new Promise(r => setTimeout(r, 0));
const settle = async () => { for (let i = 0; i < 6; i++) await tick(); };

function fakeRoot() {
  const handlers = {};
  const box = {
    checked: false, disabled: true,
    addEventListener: (ev, fn) => { handlers[ev] = fn; },
    fire: ev => handlers[ev] && handlers[ev](),
  };
  const cls = new Set();
  const out = {
    textContent: '',
    classList: { toggle: (c, on) => (on ? cls.add(c) : cls.delete(c)), remove: c => cls.delete(c),
                 contains: c => cls.has(c) },
  };
  return { box, out, querySelector: sel => (sel === '#hc-gfx-toggle' ? box : sel === '#hc-gfx-status' ? out : null) };
}
const reply = (body, status = 200) => Promise.resolve({ status, json: () => Promise.resolve(body) });
const OFF = { ok: true, saved: false, reason: null, since: null, this_launch: 'normal', forced: null };
const ON = { ok: true, saved: true, reason: 'turned on in Help', since: '2026-09-30T10:00:00', this_launch: 'normal', forced: null };

console.log('\nstatus text');
test('off, this window normal', () => {
  assert.equal(graphicsStatusText(OFF), 'Off (normal graphics).');
});
test('switched on in Help: applies from the next launch', () => {
  assert.equal(graphicsStatusText(ON), 'On since 2026-09-30. Takes effect the next time you open the app.');
});
test('switched on automatically after a black start: says why; relaunched window uses it now', () => {
  const t = graphicsStatusText({ ...ON, reason: 'WebView2 never showed the page', this_launch: 'safe' });
  assert.ok(t.includes('turned on automatically (WebView2 never showed the page)'), t);
  assert.ok(t.endsWith('This window is using it now.'), t);
});
test('switched off while this window runs in safe graphics: next launch', () => {
  assert.ok(graphicsStatusText({ ...OFF, this_launch: 'safe' }).endsWith('Takes effect the next time you open the app.'));
});
test('a user environment override is named', () => {
  assert.ok(graphicsStatusText({ ...OFF, forced: '1' }).includes('CONTROLYX_SAFE_GRAPHICS'));
});
test('no answer / error answer -> plain message, never blank', () => {
  assert.equal(graphicsStatusText(null), 'Could not read the graphics setting.');
  assert.equal(graphicsStatusText({ ok: false, error: 'X' }), 'X');
});

console.log('\nswitch wiring');
test('reads the saved choice, then saves a change and shows the new status', async () => {
  const calls = [];
  globalThis.fetch = (url, opts) => {
    calls.push([url, opts && opts.method, opts && opts.body]);
    return reply(opts && opts.method === 'POST' ? ON : OFF);
  };
  const r = fakeRoot();
  wireGraphicsSwitch(r);
  await settle();
  assert.equal(r.box.checked, false);
  assert.equal(r.box.disabled, false);
  assert.equal(r.out.textContent, 'Off (normal graphics).');
  r.box.checked = true;
  r.box.fire('change');
  assert.equal(r.out.textContent, 'Saving…');
  assert.equal(r.box.disabled, true);                     // no double submit
  await settle();
  assert.deepEqual(calls.map(c => c[0]), ['/api/graphics-mode', '/api/graphics-mode']);
  assert.equal(calls[1][1], 'POST');
  assert.deepEqual(JSON.parse(calls[1][2]), { safe: true });
  assert.equal(r.box.checked, true);
  assert.ok(r.out.textContent.startsWith('On since 2026-09-30'));
  assert.equal(r.out.classList.contains('err'), false);
});
test('a refused save puts the tick back and says why beside the switch', async () => {
  let n = 0;
  globalThis.fetch = () => (n++ === 0 ? reply(OFF)
    : reply({ ...OFF, ok: false, error: 'The graphics setting could not be saved (the app data folder is not writable).' }, 500));
  const r = fakeRoot();
  wireGraphicsSwitch(r);
  await settle();
  r.box.checked = true;
  r.box.fire('change');
  await settle();
  assert.equal(r.box.checked, false);
  assert.equal(r.box.disabled, false);
  assert.ok(r.out.textContent.startsWith('Not saved — The graphics setting could not be saved'), r.out.textContent);
  assert.equal(r.out.classList.contains('err'), true);
});
test('the app not answering: switch stays disabled with a plain message; a failed save reverts', async () => {
  globalThis.fetch = () => Promise.reject(new Error('down'));
  const r = fakeRoot();
  wireGraphicsSwitch(r);
  await settle();
  assert.equal(r.box.disabled, true);
  assert.ok(r.out.textContent.includes('not answering'));
  assert.equal(r.out.classList.contains('err'), true);
  r.box.disabled = false;
  r.box.checked = true;
  r.box.fire('change');
  await settle();
  assert.equal(r.box.checked, false);
  assert.equal(r.out.textContent, 'Not saved — the app is not answering. Try again.');
});

await runAll();
console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
