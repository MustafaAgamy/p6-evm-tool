/**
 * Unit tests for ui/prefs_bridge.js — screen preferences (Appearance, Report Contents picks,
 * remembered table columns / E1 layouts ...) survive an app restart (owner comment 31 b).
 * The app window's browser storage is wiped at every launch (private WebView2 + a new
 * random port), so the bridge loads the app's saved copy (window.__UI_PREFS__) into the
 * page's storage before any module reads it, and mirrors every later change to
 * POST /api/ui-prefs (batched, retried with backoff, never losing a newer change).
 * The bridge is a classic ES5 script (server.py inlines it into index.html), so it is
 * evaluated here in a vm sandbox with a fake Storage and fake timers.
 * Run: node tests/js/test_prefs_bridge.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'ui', 'prefs_bridge.js'), 'utf8');

let passed = 0;
let failed = 0;
async function test(name, fn) {
  try { await fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}`); console.error(`    ${err.stack || err.message}`); failed++; }
}

function loadBridge() {
  const sandbox = { module: { exports: {} } };
  vm.runInNewContext(SRC, sandbox, { filename: 'prefs_bridge.js' });
  return sandbox.module.exports;
}
const B = loadBridge();

// A fresh Storage "class" per test so patching its prototype never leaks between tests.
function makeWin({ stored = {}, saved, quotaAt = Infinity, storageThrows = false } = {}) {
  function Storage() { this._d = {}; }
  Storage.prototype.getItem = function (k) { return Object.prototype.hasOwnProperty.call(this._d, k) ? this._d[k] : null; };
  Storage.prototype.setItem = function (k, v) {
    if (Object.keys(this._d).length >= quotaAt && !(k in this._d)) { throw new Error('QuotaExceededError'); }
    this._d[String(k)] = String(v);
  };
  Storage.prototype.removeItem = function (k) { delete this._d[k]; };
  Storage.prototype.clear = function () { this._d = {}; };
  Storage.prototype.key = function (i) { return Object.keys(this._d)[i] ?? null; };
  Object.defineProperty(Storage.prototype, 'length', { get() { return Object.keys(this._d).length; } });
  const ls = new Storage();
  Object.assign(ls._d, stored);
  const ss = new Storage();
  const listeners = {};
  const win = {
    Storage, sessionStorage: ss, __UI_PREFS__: saved,
    addEventListener(t, f) { (listeners[t] = listeners[t] || []).push(f); },
    fire(t) { (listeners[t] || []).forEach(f => f()); },
  };
  Object.defineProperty(win, 'localStorage', {
    get() { if (storageThrows) throw new Error('SecurityError'); return ls; },
  });
  return { win, ls, ss };
}

function makeIO(answers = []) {
  const timers = [];
  const posts = [];
  return {
    timers, posts,
    setTimeout(f, ms) { timers.push({ f, ms }); return timers.length; },
    post(body, keepalive) {
      posts.push({ body: JSON.parse(JSON.stringify(body)), keepalive });
      const a = answers.length ? answers.shift() : { ok: true };
      return a instanceof Error ? Promise.reject(a) : Promise.resolve(a);
    },
    async tick() {                       // run the due timers, then let promises settle
      const due = timers.splice(0);
      due.forEach(t => t.f());
      for (let i = 0; i < 5; i++) await Promise.resolve();
      return due.map(t => t.ms);
    },
  };
}

function install(winOpts, answers) {
  const w = makeWin(winOpts);
  const io = makeIO(answers);
  const b = B.create(w.win, { setTimeout: io.setTimeout, post: io.post }).install();
  return { ...w, io, b };
}

// ── 1. the saved copy reaches the page before any module reads it ─────────
await test('saved preferences are loaded into the page storage (the saved copy wins)', async () => {
  const { ls, io } = install({
    stored: { p6_report_appearance: 'light' },
    saved: { p6_report_appearance: 'midnight', p6evm_w_cols: '["a","b"]' },
  });
  assert.equal(ls.getItem('p6_report_appearance'), 'midnight');
  assert.equal(ls.getItem('p6evm_w_cols'), '["a","b"]');
  await io.tick();
  assert.equal(io.posts.length, 0, 'loading the saved copy must not be sent back');
});

await test('non-string saved values are ignored (never written as "[object Object]")', async () => {
  const { ls } = install({ saved: { a: 'x', b: 5, c: { d: 1 } } });
  assert.equal(ls.getItem('a'), 'x');
  assert.equal(ls.getItem('b'), null);
  assert.equal(ls.getItem('c'), null);
});

await test('keys only this page holds are sent to the app once', async () => {
  const { io } = install({ stored: { only_here: '1', both: 'x' }, saved: { both: 'x' } });
  assert.deepEqual(await io.tick(), [B.DEBOUNCE_MS]);
  assert.equal(io.posts.length, 1);
  assert.deepEqual(io.posts[0].body, { set: { only_here: '1' }, remove: [] });
  await io.tick();
  assert.equal(io.posts.length, 1);
});

// ── 2. every later change is mirrored, batched ─────────────────────────────
await test('setItem / removeItem after install are batched into one POST', async () => {
  const { ls, io } = install({ saved: { old: 'x' } });
  ls.setItem('p6_report_appearance', 'sepia');
  ls.setItem('p6_report_appearance', 'blueprint');   // the newest value wins
  ls.setItem('n', 3);                                   // stored as a string, like a browser
  ls.removeItem('old');
  assert.equal(io.timers.length, 1, 'one debounce timer, not one per change');
  await io.tick();
  assert.equal(io.posts.length, 1);
  assert.deepEqual(io.posts[0].body, { set: { p6_report_appearance: 'blueprint', n: '3' }, remove: ['old'] });
});

await test('a set after a remove (and vice versa) keeps only the newest intent', async () => {
  const { ls, io } = install({ saved: { k: 'a', j: 'b' } });
  ls.removeItem('k'); ls.setItem('k', 'c');
  ls.setItem('j', 'd'); ls.removeItem('j');
  await io.tick();
  assert.deepEqual(io.posts[0].body, { set: { k: 'c' }, remove: ['j'] });
});

await test('[startup:F3] the Narrative project setup (bn_setup_*, logos + layout drawing) is never mirrored', async () => {
  const big = 'data:image/png;base64,' + 'A'.repeat(700 * 1024);   // over ui_prefs' 512 KB cap
  const { ls, io } = install({ stored: { bn_setup_7: '{"owner":"x"}', keep: 'y' }, saved: {} });
  ls.setItem('bn_setup_12', JSON.stringify({ owner: 'Roots', owner_logo: big }));
  ls.setItem('p6evm_wbs_cols', '["code","name"]');
  ls.removeItem('bn_setup_7');
  await io.tick();
  assert.equal(io.posts.length, 1);
  assert.deepEqual(io.posts[0].body, { set: { keep: 'y', p6evm_wbs_cols: '["code","name"]' }, remove: [] });
  ls.clear();
  await io.tick();
  assert.deepEqual(io.posts[1].body.remove.sort(), ['keep', 'p6evm_wbs_cols']);
  assert.ok(B.SKIP.test('bn_setup_default') && !B.SKIP.test('p6_report_appearance'));
});

await test('clear() removes every key the page held', async () => {
  const { ls, io } = install({ saved: { a: '1', b: '2' } });
  ls.clear();
  await io.tick();
  assert.deepEqual(io.posts[0].body.set, {});
  assert.deepEqual(io.posts[0].body.remove.sort(), ['a', 'b']);
});

await test('sessionStorage changes are not mirrored (only the page\'s localStorage)', async () => {
  const { ss, io } = install({});
  ss.setItem('tmp', '1');
  assert.equal(ss.getItem('tmp'), '1');
  await io.tick();
  assert.equal(io.posts.length, 0);
});

// ── 3. a busy / offline local service never loses a change ─────────────────
await test('a failed save is retried with backoff and a newer change is not overwritten', async () => {
  const { ls, io, b } = install({}, [new Error('offline'), { ok: false }, { ok: true }]);
  ls.setItem('mode', 'dark');
  await io.tick();                                // POST #1 rejects -> requeued
  assert.equal(io.posts.length, 1);
  ls.setItem('mode', 'midnight');                 // newer change while waiting
  assert.deepEqual(io.timers.map(t => t.ms), [B.RETRY_MS[0]]);
  await io.tick();                                // POST #2 -> ok:false -> requeued
  assert.deepEqual(io.posts[1].body.set, { mode: 'midnight' }, 'the newer value is sent, not the old one');
  assert.deepEqual(io.timers.map(t => t.ms), [B.RETRY_MS[1]], 'second retry waits longer');
  await io.tick();                                // POST #3 ok
  assert.deepEqual(io.posts[2].body.set, { mode: 'midnight' });
  assert.equal(b.failures, 2);
  assert.deepEqual(JSON.parse(JSON.stringify(b.pending())), { set: {}, remove: [] });
});

await test('pending changes are flushed (keepalive) when the page closes', async () => {
  const { ls, io, win } = install({});
  ls.setItem('x', '1');
  win.fire('pagehide');
  await Promise.resolve();
  assert.equal(io.posts.length, 1);
  assert.equal(io.posts[0].keepalive, true);
  assert.deepEqual(io.posts[0].body.set, { x: '1' });
});

// ── 4. never breaks the page ───────────────────────────────────────────────
await test('blocked storage: install does nothing and does not throw', async () => {
  const w = makeWin({ storageThrows: true, saved: { a: '1' } });
  const io = makeIO();
  const b = B.create(w.win, { setTimeout: io.setTimeout, post: io.post }).install();
  assert.equal(b.installed, false);
  await io.tick();
  assert.equal(io.posts.length, 0);
});

await test('a quota error still reaches the module and nothing is recorded', async () => {
  const { ls, io } = install({ saved: { a: '1' }, quotaAt: 1 });
  assert.throws(() => ls.setItem('big', 'x'), /Quota/);
  await io.tick();
  assert.equal(io.posts.length, 0);
});

await test('install() is idempotent on a window (one bridge, prototype patched once)', async () => {
  const w = makeWin({ saved: {} });
  const b1 = B.install(w.win);
  const setAfterFirst = w.win.Storage.prototype.setItem;
  const b2 = B.install(w.win);
  assert.equal(b1, b2);
  assert.equal(w.win.Storage.prototype.setItem, setAfterFirst);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
