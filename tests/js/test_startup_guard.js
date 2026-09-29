/**
 * Unit tests for ui/startup_guard.js — the watchdog that keeps the window from ever
 * sitting on a silent black screen (startup audit BLACK-1): a program file that fails to
 * load, an error before the shell is built, or a stalled start reloads with backoff, then
 * shows a visible Retry card; ready() lifts it and completes the app's handshake.
 * The guard is a classic ES5 script (server.py inlines it into index.html), so it is
 * evaluated here in a vm sandbox with a tiny fake DOM and fake timers.
 * Run: node tests/js/test_startup_guard.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..', '..');
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), 'utf8');
const SRC = read('ui', 'startup_guard.js');

let passed = 0;
let failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}`); console.error(`    ${err.message}`); failed++; }
}

function loadGuard() {
  const sandbox = { module: { exports: {} } };
  vm.runInNewContext(SRC, sandbox, { filename: 'startup_guard.js' });
  return sandbox.module.exports;
}
const G = loadGuard();

// ── fakes ──────────────────────────────────────────────────────────────────
function fakeEl(tag) {
  const el = {
    tagName: tag.toUpperCase(), id: '', style: {}, attrs: {}, children: [], parentNode: null,
    _html: '', onclick: null,
    setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentNode = null; },
    getElementsByTagName(t) { return t === 'button' ? [this._button || (this._button = fakeEl('button'))] : []; },
  };
  Object.defineProperty(el, 'innerHTML', {
    get() { return this._html; },
    set(v) { this._html = v; this._button = null; },
  });
  return el;
}

function fakeWorld({ attempt = null, links = [], readyState = 'complete' } = {}) {
  const body = fakeEl('body');
  const listeners = {};
  const docListeners = {};
  const store = attempt == null ? {} : { cx_boot_attempt: String(attempt) };
  let clock = 0;
  let timers = [];
  const posts = [];
  const gets = [];
  let reloads = 0;
  const all = () => {
    const out = [];
    const walk = n => { out.push(n); n.children.forEach(walk); };
    walk(body);
    return out;
  };
  const doc = {
    body, documentElement: body, readyState,
    createElement: fakeEl,
    getElementById(id) {
      if (id === 'cx-startup-retry') {
        const ov = all().find(n => n.id === 'cx-startup');
        if (!ov || !ov.innerHTML.includes('id="cx-startup-retry"')) return null;
        return ov._retry || (ov._retry = fakeEl('button'));
      }
      return all().find(n => n.id === id) || null;
    },
    querySelectorAll() { return links; },
    addEventListener(t, f) { (docListeners[t] = docListeners[t] || []).push(f); },
  };
  const win = {
    document: doc, __APP_NAME__: 'Controlyx',
    addEventListener(t, f) { (listeners[t] = listeners[t] || []).push(f); },
  };
  const opts = {
    now: () => clock,
    setTimeout: (f, ms) => { const id = timers.length + 1; timers.push({ id, at: clock + ms, f }); return id; },
    clearTimeout: id => { timers = timers.filter(t => t.id !== id); },
    reload: () => { reloads++; },
    post: p => posts.push(p),
    getJson: (url, cb) => gets.push({ url, cb }),
    storage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
  };
  return {
    win, doc, opts, store, posts, gets,
    get reloads() { return reloads; },
    overlay: () => doc.getElementById('cx-startup'),
    fire(type, ev) { (listeners[type] || []).forEach(f => f(ev)); },
    domReady() { (docListeners.DOMContentLoaded || []).forEach(f => f()); },
    advance(ms) {
      const until = clock + ms;
      for (;;) {
        const due = timers.filter(t => t.at <= until).sort((a, b) => a.at - b.at)[0];
        if (!due) break;
        timers = timers.filter(t => t !== due);
        clock = due.at;
        due.f();
      }
      clock = until;
    },
  };
}
const start = w => G.create(w.win, w.opts).start();
const scriptErr = src => ({ target: { tagName: 'SCRIPT', src } });

console.log('startup_guard.js');

test('a program file that fails to load reloads automatically after a short backoff', () => {
  const w = fakeWorld();
  const g = start(w);
  w.fire('error', scriptErr('http://localhost:5/ui/modules/tooltip.js'));
  assert.equal(g.phase, 'retrying');
  assert.equal(w.store.cx_boot_attempt, '1');
  assert.match(w.overlay().innerHTML, /trying again automatically \(attempt 1 of 3\)/);
  w.advance(G.BACKOFF_MS[0] - 1);
  assert.equal(w.reloads, 0);
  w.advance(1);
  assert.equal(w.reloads, 1);
  assert.deepEqual(w.posts.map(p => p.kind), ['load-failed', 'retry']);
  assert.match(w.posts[0].detail, /tooltip\.js/);
});

test('backoff grows with each automatic attempt (count survives the reload)', () => {
  G.BACKOFF_MS.forEach((ms, i) => {
    const w = fakeWorld({ attempt: i });
    start(w).fail('load-failed', 'x');
    w.advance(ms - 1);
    assert.equal(w.reloads, 0, `attempt ${i}: too early`);
    w.advance(1);
    assert.equal(w.reloads, 1, `attempt ${i}: reload at ${ms} ms`);
    assert.equal(w.store.cx_boot_attempt, String(i + 1));
  });
});

test('after the automatic attempts a visible card offers Retry (never a black screen)', () => {
  const w = fakeWorld({ attempt: G.BACKOFF_MS.length });
  const g = start(w);
  w.fire('error', scriptErr('http://localhost:5/ui/modules/format.js'));
  assert.equal(g.phase, 'failed');
  const html = w.overlay().innerHTML;
  assert.match(html, /Controlyx couldn.t finish starting/);
  assert.match(html, /Your projects and data are safe/);
  assert.match(html, /format\.js/);
  assert.match(html, /id="cx-startup-retry"/);
  w.advance(60000);
  assert.equal(w.reloads, 0, 'no endless reload loop');
  w.doc.getElementById('cx-startup-retry').onclick();       // Retry
  assert.equal(w.reloads, 1);
  assert.equal(w.store.cx_boot_attempt, '0');
});

test('ready() lifts the guard, resets the counter, completes the handshake, checks health', () => {
  const w = fakeWorld({ attempt: 2 });
  const g = start(w);
  g.booted();
  g.ready();
  assert.equal(g.phase, 'ready');
  assert.equal(w.store.cx_boot_attempt, '0');
  assert.equal(w.overlay(), null);
  const r = w.posts.find(p => p.kind === 'ready');
  assert.ok(r, 'ready posted to /api/client-log');
  assert.match(r.detail, /after 2 automatic reload/);
  assert.equal(w.gets[0].url, '/api/health');
  w.advance(G.STALL_MS * 2);
  assert.equal(w.reloads, 0, 'timers cleared');
  assert.equal(w.overlay(), null);
});

test('errors after ready are ignored (the app handles its own errors from then on)', () => {
  const w = fakeWorld();
  const g = start(w);
  g.ready();
  w.fire('error', scriptErr('http://localhost:5/ui/vendor/leaflet/leaflet.js'));
  w.fire('error', { message: 'boom', filename: 'x.js', lineno: 3 });
  assert.equal(g.phase, 'ready');
  assert.equal(w.reloads, 0);
});

test('an exception before the shell is built fails fast with its message', () => {
  const w = fakeWorld({ attempt: 3 });
  const g = start(w);
  g.booted();
  w.fire('error', { message: 'TypeError: x is undefined', filename: 'http://l/ui/app.js', lineno: 120 });
  assert.equal(g.phase, 'failed');
  assert.match(w.overlay().innerHTML, /x is undefined \(http:\/\/l\/ui\/app\.js:120\)/);
});

test('a broken image is not fatal', () => {
  const w = fakeWorld();
  const g = start(w);
  w.fire('error', { target: { tagName: 'IMG', src: 'x.png' } });
  assert.equal(g.phase, 'loading');
});

test('a slow start says "Still starting" instead of a blank cover, then recovers', () => {
  const w = fakeWorld();
  const g = start(w);
  w.advance(G.SLOW_MS);
  assert.equal(g.phase, 'slow');
  assert.match(w.overlay().innerHTML, /Still starting/);
  assert.match(w.overlay().innerHTML, /Reload now/);
  g.ready();
  assert.equal(w.overlay(), null);
  assert.equal(g.phase, 'ready');
});

test('a stalled start is treated as a failure and retried', () => {
  const w = fakeWorld();
  const g = start(w);
  w.advance(G.STALL_MS);
  assert.equal(g.phase, 'retrying');
  assert.ok(w.posts.some(p => p.kind === 'timeout' && /did not finish loading/.test(p.detail)));
  w.advance(G.BACKOFF_MS[0]);
  assert.equal(w.reloads, 1);
});

test('a stylesheet that failed to load is caught at DOMContentLoaded', () => {
  const link = { getAttribute: () => '/ui/style.css', sheet: null };
  const w = fakeWorld({ links: [link], readyState: 'loading' });
  const g = start(w);
  assert.equal(g.phase, 'loading');
  w.domReady();
  assert.equal(g.phase, 'retrying');
  const ok = fakeWorld({ links: [{ getAttribute: () => '/ui/style.css', sheet: {} }], readyState: 'loading' });
  const g2 = start(ok);
  ok.domReady();
  assert.equal(g2.phase, 'loading');
});

test('health notice: a recovered database is explained, a healthy one says nothing', () => {
  const w = fakeWorld();
  const g = start(w);
  assert.equal(g.notice({ db: { status: 'ok' } }), null);
  assert.equal(g.notice(null), null);
  const el = g.notice({ db: { status: 'recovered', backup: 'controlyx.db.corrupt-bak-20260929-101500' } });
  assert.ok(el && el.id === 'cx-db-notice');
  assert.match(el.innerHTML, /corrupt-bak-20260929-101500/);
  assert.match(el.innerHTML, /re-import your schedules/);
  el.getElementsByTagName('button')[0].onclick();
  assert.equal(w.doc.getElementById('cx-db-notice'), null, 'dismissible');
  const el2 = g.notice({ db: { status: 'degraded', detail: 'database is locked' } });
  assert.match(el2.innerHTML, /database is locked/);
});

test('html in failure details is escaped', () => {
  const w = fakeWorld({ attempt: 3 });
  start(w).fail('error', '<img src=x onerror=alert(1)>');
  assert.ok(!w.overlay().innerHTML.includes('<img'));
});

test('install() registers once on window.__cxStartup', () => {
  const w = fakeWorld();
  w.win.setTimeout = w.opts.setTimeout;
  w.win.clearTimeout = w.opts.clearTimeout;
  const a = G.install(w.win);
  assert.equal(w.win.__cxStartup, a);
  assert.equal(G.install(w.win), a);
});

// ── real start-up steps (BLACK-9: the splash shows these, never a scripted stage) ──
const healthGets = w => w.gets.filter(x => x.url === '/api/health');

test('steps: health answered -> server; booted -> program; ready -> screen; app.js -> history', () => {
  const w = fakeWorld();
  const g = start(w);
  const seen = [];
  g.onChange(what => seen.push(what));
  assert.deepEqual([...G.STEPS], ['server', 'program', 'screen', 'history']);
  assert.equal(g.current(), 'server');
  assert.equal(healthGets(w).length, 1, 'the readiness handshake is probed at once');
  healthGets(w)[0].cb({ ok: true, db: { status: 'ok' } });
  assert.equal(g.steps.server, true);
  assert.deepEqual(g.health.db, { status: 'ok' });
  assert.equal(g.current(), 'program');
  g.booted();
  assert.equal(g.current(), 'screen');
  g.ready();
  assert.equal(g.current(), 'history');
  assert.equal(g.step('history'), true);
  assert.equal(g.step('history'), false, 'a step happens once');
  assert.equal(g.step('bogus'), false);
  assert.equal(g.current(), '');
  assert.deepEqual(seen, ['server', 'program', 'screen', 'phase', 'history']);
});

test('steps: a module graph that loaded proves the server answers, even before /api/health', () => {
  const w = fakeWorld();
  const g = start(w);
  g.booted();
  assert.equal(g.steps.server, true);
  assert.equal(g.steps.program, true);
});

test('health: an error is re-probed with backoff; a later answer completes the step', () => {
  const w = fakeWorld();
  const calls = [];
  w.opts.getJson = (url, cb, onErr) => calls.push({ url, cb, onErr });
  const g = G.create(w.win, w.opts).start();
  calls[0].onErr('HTTP 500');
  assert.equal(calls.length, 1);
  w.advance(G.HEALTH_RETRY_MS[0]);
  assert.equal(calls.length, 2, 're-probed after the first backoff');
  calls[1].cb({ ok: true });
  assert.equal(g.steps.server, true);
  assert.equal(g.phase, 'loading');
});

test('health: a server that refuses every probe before the program loads fails the start (Retry path)', () => {
  const w = fakeWorld();
  const calls = [];
  w.opts.getJson = (url, cb, onErr) => calls.push({ url, cb, onErr });
  const g = G.create(w.win, w.opts).start();
  for (let i = 0; i <= G.HEALTH_RETRY_MS.length; i++) {
    calls[i].onErr('Failed to fetch');
    if (i < G.HEALTH_RETRY_MS.length) w.advance(G.HEALTH_RETRY_MS[i]);
  }
  assert.equal(calls.length, G.HEALTH_RETRY_MS.length + 1);
  assert.equal(g.phase, 'retrying');
  assert.ok(w.posts.some(p => p.kind === 'health' && /did not answer/.test(p.message)));
  assert.ok(w.posts.some(p => p.kind === 'health' && /GET \/api\/health: Failed to fetch/.test(p.detail)));
});

test('health: probes failing after the program loaded are not fatal (the server clearly answers)', () => {
  const w = fakeWorld();
  const calls = [];
  w.opts.getJson = (url, cb, onErr) => calls.push({ url, cb, onErr });
  const g = G.create(w.win, w.opts).start();
  g.booted();
  calls[0].onErr('HTTP 500');
  w.advance(10000);
  assert.equal(calls.filter(c => c.url === '/api/health').length, 1, 'no re-probe once the step is done');
  assert.equal(g.phase, 'loading');
  g.ready();
  assert.equal(g.phase, 'ready');
});

test('phase changes are told to listeners (the splash steps aside on retry/failure)', () => {
  const w = fakeWorld({ attempt: 3 });
  const g = start(w);
  const seen = [];
  g.onChange((what, guard) => seen.push(what + ':' + guard.phase));
  g.fail('load-failed', 'x.js');
  assert.deepEqual(seen, ['phase:failed']);
  const w2 = fakeWorld();
  const g2 = start(w2);
  const seen2 = [];
  const off = g2.onChange((what, guard) => seen2.push(what + ':' + guard.phase));
  w2.advance(G.SLOW_MS);
  assert.deepEqual(seen2, ['phase:slow']);
  off();
  g2.ready();
  assert.deepEqual(seen2, ['phase:slow'], 'unsubscribed');
});

test('a listener that throws never breaks the guard', () => {
  const w = fakeWorld();
  const g = start(w);
  g.onChange(() => { throw new Error('boom'); });
  g.booted();
  g.ready();
  assert.equal(g.phase, 'ready');
});

test('the cover says the real current step (server, then program files)', () => {
  const w = fakeWorld();
  const cover = fakeEl('span');
  cover.id = 'cx-cover-stage';
  w.doc.body.appendChild(cover);
  const g = start(w);
  assert.equal(cover.textContent, 'Starting local server…');
  healthGets(w)[0].cb({ ok: true });
  assert.equal(cover.textContent, 'Loading program files…');
  void g;
});

// ── wiring ────────────────────────────────────────────────────────────────
test('guard source is safe to inline and never uses alert/confirm/prompt (WebView2 no-ops)', () => {
  assert.ok(!SRC.includes('<!--'), 'no HTML comment opener inside an inline script');
  assert.ok(!/<\/?script/i.test(SRC), 'no script tags inside an inline script');
  assert.ok(!/\b(alert|confirm|prompt)\s*\(/.test(SRC.replace(/\/\*[\s\S]*?\*\//g, '')));
  assert.ok(!/=>|\blet\b|\bconst\b|`/.test(SRC.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')),
    'ES5 only: it must run even where the modules fail');
});

test('index.html carries the guard marker before the stylesheet and a visible Starting cover', () => {
  const html = read('ui', 'index.html');
  const mark = html.indexOf('<!--cx:startup-guard-->');
  assert.ok(mark > 0 && mark < html.indexOf('/ui/style.css'), 'marker before the stylesheet');
  assert.match(html, /<div id="brand-splash"><div class="cxb-note">[\s\S]*Starting/);
  assert.match(html, /<span id="cx-cover-stage">Starting local server…<\/span>/,
    'the cover names the real first step, which the guard updates');
});

test('app.js marks the history step when the first Recent Projects call settles', () => {
  const js = read('ui', 'app.js');
  assert.match(js, /loadHistory\(\)\.finally\(\(\) => \{ if \(window\.__cxStartup\) window\.__cxStartup\.step\('history'\); \}\);/);
});

test('app.js reports booted() at module start and ready() at the end of startup', () => {
  const js = read('ui', 'app.js');
  const booted = js.indexOf('__cxStartup.booted()');
  const dcl = js.indexOf("document.addEventListener('DOMContentLoaded'");
  assert.ok(booted > 0 && booted < dcl, 'booted() before the DOMContentLoaded handler');
  const ready = js.lastIndexOf('__cxStartup.ready()');
  assert.ok(ready > dcl, 'ready() inside the handler');
  assert.equal(js.slice(ready).replace(/\s+/g, ''), '__cxStartup.ready();});',
    'ready() is the last statement of the startup handler');
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
