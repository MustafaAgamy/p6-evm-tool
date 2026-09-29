/**
 * Unit tests for ui/modules/boot.js — the animated startup splash.
 *  * BLACK-9: its caption and bar follow the REAL start-up steps the startup guard records
 *    (ui/startup_guard.js): never a step shown as passed, or 'Ready', before it happened;
 *    the owner's 11-s presentation keeps its length; a failed start makes it step aside
 *    at once (the guard's Retry card), a start still running holds it on the real step.
 *  * VER-2: the product name comes from window.__APP_NAME__ / __APP_EDITION__ /
 *    __APP_TITLE__ (server.py injects them from utils.APP_*), never hardcoded — in the
 *    splash or in index.html.
 * Run: node tests/js/test_boot_splash.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..', '..');
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), 'utf8');

let passed = 0;
let failed = 0;
async function test(name, fn) {
  try { await fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}`); console.error(`    ${err.message}`); failed++; }
}

// ── a tiny fake DOM + clock, enough for playBoot ────────────────────────────
function fakeEl(tag) {
  const el = {
    tagName: String(tag).toUpperCase(), id: '', style: {}, attrs: {}, children: [], parentNode: null,
    innerHTML: '', textContent: '', _q: {},
    classList: { set: new Set(), add(c) { this.set.add(c); }, contains(c) { return this.set.has(c); } },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentNode = null; },
    querySelector(sel) { return this._q[sel] || (this._q[sel] = fakeEl('x')); },
  };
  return el;
}
function fakeWorld(guard, brand = { __APP_NAME__: 'Controlyx', __APP_EDITION__: '2026', __APP_TITLE__: 'Controlyx 2026' }) {
  const head = fakeEl('head');
  const body = fakeEl('body');
  const cover = fakeEl('div'); cover.id = 'brand-splash'; body.appendChild(cover);
  let frames = [];
  let timers = [];
  let clock = 0;
  const document = {
    head, body,
    createElement: fakeEl,
    createElementNS: (_ns, tag) => fakeEl(tag),
    getElementById: id => body.children.find(c => c.id === id) || null,
  };
  const window = {
    ...brand, __cxStartup: guard || undefined,
    matchMedia: () => ({ matches: false }),
  };
  globalThis.window = window;
  globalThis.document = document;
  globalThis.requestAnimationFrame = f => { frames.push(f); return frames.length; };
  globalThis.cancelAnimationFrame = () => { frames = []; };
  globalThis.setTimeout = (f, ms) => { timers.push({ at: clock + ms, f }); return timers.length; };
  const w = {
    window, document, body, cover,
    boot: () => body.children.find(c => c.id === 'boot') || null,
    // run animation frames until `ms` of presentation time has passed
    play(ms, step = 100) {
      const until = clock + ms;
      while (clock < until) {
        clock += step;
        const due = timers.filter(t => t.at <= clock); timers = timers.filter(t => t.at > clock);
        due.forEach(t => t.f());
        const fs_ = frames; frames = [];
        fs_.forEach(f => f(clock));
      }
    },
  };
  return w;
}
function fakeGuard(phase, steps) {
  const g = { phase, steps: { server: false, program: false, screen: false, history: false, ...steps }, ls: [] };
  g.onChange = fn => { g.ls.push(fn); return () => { g.ls = g.ls.filter(x => x !== fn); }; };
  g.set = (k, v) => { if (k === 'phase') g.phase = v; else g.steps[k] = v; g.ls.slice().forEach(f => f(k, g)); };
  return g;
}
const capt = w => w.boot().querySelector('.capt').textContent;
const pct = w => w.boot().querySelector('.pct').textContent;

const boot = await import(pathToFileURL(path.join(ROOT, 'ui', 'modules', 'boot.js')).href);
const { bootProgress, bootDecision, BOOT_STEPS, playBoot } = boot;
const ALL = { server: true, program: true, screen: true, history: true };

console.log('boot.js');

await test('the caption names only real steps (no scripted stages)', () => {
  assert.deepEqual(BOOT_STEPS.map(s => s[0]), ['server', 'program', 'screen', 'history']);
  const src = read('ui', 'modules', 'boot.js');
  for (const fake of ['Loading knowledge base', 'Preparing analysis engine', 'Loading calendars']) {
    assert.ok(!src.includes(fake), `no scripted "${fake}"`);
  }
});

await test('all steps done: the owner\'s 11-s presentation plays as before and ends on Ready', () => {
  assert.equal(bootProgress(0, ALL).pct, 0);
  assert.equal(bootProgress(0.03 + 0.86 / 2, ALL).pct, 50);
  const end = bootProgress(0.9, ALL);
  assert.equal(end.pct, 100);
  assert.equal(end.label, 'Ready');
  assert.equal(end.ready, true);
});

await test('the bar is held at the first step not done, and says that step', () => {
  const p = bootProgress(0.95, { server: true, program: true });
  assert.equal(p.pct, 50);
  assert.equal(p.label, 'Building the screen');
  assert.equal(p.held, true);
  assert.equal(p.ready, false);
  const none = bootProgress(0.95, {});
  assert.equal(none.pct, 0);
  assert.equal(none.label, 'Starting local server');
  const noHistory = bootProgress(1, { server: true, program: true, screen: true });
  assert.equal(noHistory.pct, 75);
  assert.equal(noHistory.label, 'Opening project history');
});

await test('never Ready — and never a later step — before it really happened', () => {
  const combos = [{}, { server: true }, { server: true, program: true },
                  { server: true, program: true, screen: true }, { program: true, screen: true, history: true }];
  for (const steps of combos) {
    for (let t = 0; t <= 1.2; t += 0.01) {
      const p = bootProgress(t, steps);
      assert.equal(p.ready, false);
      assert.notEqual(p.label, 'Ready');
      const idx = BOOT_STEPS.findIndex(s => s[1] === p.label);
      const firstNotDone = BOOT_STEPS.findIndex(s => !steps[s[0]]);
      assert.ok(idx <= firstNotDone, `t=${t.toFixed(2)} ${JSON.stringify(steps)} -> ${p.label}`);
    }
  }
});

await test('decision: failed/retrying -> abort; still loading -> wait; ready + all steps + played -> finish', () => {
  assert.equal(bootDecision(fakeGuard('failed'), false, false), 'abort');
  assert.equal(bootDecision(fakeGuard('retrying'), true, true), 'abort');
  assert.equal(bootDecision(fakeGuard('loading', { server: true, program: true }), true, true), 'wait');
  assert.equal(bootDecision(fakeGuard('slow', { server: true, program: true }), true, true), 'wait');
  assert.equal(bootDecision(fakeGuard('ready', ALL), false, false), 'wait', 'the presentation plays in full');
  assert.equal(bootDecision(fakeGuard('ready', ALL), true, false), 'finish');
  const slowHistory = fakeGuard('ready', { server: true, program: true, screen: true });
  assert.equal(bootDecision(slowHistory, true, false), 'wait');
  assert.equal(bootDecision(slowHistory, true, true), 'finish', 'history slower than the cap: Recent Projects says its own state');
  assert.equal(bootDecision(null, false, false), 'wait');
  assert.equal(bootDecision(null, true, false), 'finish');
});

await test('playBoot: name and edition come from the injected globals', () => {
  const w = fakeWorld(fakeGuard('ready', ALL), { __APP_NAME__: 'Brandly', __APP_EDITION__: '2031', __APP_TITLE__: 'Brandly 2031' });
  playBoot({});
  const html = w.boot().innerHTML;
  assert.match(html, /<div class="nm">Brandly<span class="yr">2031<\/span><\/div>/);
  assert.match(html, /<div class="ver">Brandly&nbsp;2031 · /);
  assert.ok(!/Controlyx|2026/.test(html), 'nothing hardcoded');
  assert.equal(w.cover.parentNode, null, 'the cover hands over to the splash');
});

await test('playBoot: html in the injected name is escaped', () => {
  const w = fakeWorld(fakeGuard('ready', ALL), { __APP_NAME__: '<b>x</b>', __APP_EDITION__: '', __APP_TITLE__: '' });
  playBoot({});
  assert.ok(!w.boot().innerHTML.includes('<b>x</b>'));
});

await test('playBoot: a normal start plays the full presentation, ends on Ready 100%, then lifts', () => {
  const g = fakeGuard('ready', ALL);
  const w = fakeWorld(g);
  let done = 0;
  playBoot({ onDone: () => done++ });
  w.play(5000);
  assert.ok(w.boot() && !w.boot().classList.contains('gone'), 'still playing at 5 s');
  assert.notEqual(capt(w), 'Ready');
  w.play(5000);                                    // t = 10 s > 0.9 × 11 s
  assert.equal(capt(w), 'Ready');
  assert.equal(pct(w), '100%');
  assert.ok(w.boot().classList.contains('gone'));
  assert.equal(done, 1);
});

await test('playBoot: a screen not built yet holds the splash on the real step, then lifts when ready', () => {
  const g = fakeGuard('loading', { server: true, program: true });
  const w = fakeWorld(g);
  let done = 0;
  playBoot({ onDone: () => done++ });
  w.play(14000);                                   // past the hard cap (DUR + 1.5 s)
  assert.ok(!w.boot().classList.contains('gone'), 'not lifted over an unbuilt screen');
  assert.equal(capt(w), 'Building the screen');
  assert.equal(pct(w), '50%');
  g.set('screen', true);
  g.set('phase', 'ready');
  assert.ok(w.boot().classList.contains('gone'), 'lifts as soon as the screen is built (past the cap)');
  assert.equal(done, 1);
});

await test('playBoot: project history still loading holds on it, then Ready when it answers', () => {
  const g = fakeGuard('ready', { server: true, program: true, screen: true });
  const w = fakeWorld(g);
  playBoot({});
  w.play(10500);
  assert.ok(!w.boot().classList.contains('gone'));
  assert.equal(capt(w), 'Opening project history');
  assert.equal(pct(w), '75%');
  g.set('history', true);
  w.play(100);
  assert.equal(capt(w), 'Ready');
  assert.ok(w.boot().classList.contains('gone'));
});

await test('playBoot: a failed start steps aside at once for the guard\'s Retry card', () => {
  const g = fakeGuard('loading', { server: true, program: true });
  const w = fakeWorld(g);
  let done = 0;
  playBoot({ onDone: () => done++ });
  w.play(2000);
  g.set('phase', 'retrying');
  assert.equal(w.boot(), null, 'removed, not finished into an empty shell');
  assert.equal(done, 0);
  const w2 = fakeWorld(fakeGuard('failed', {}));
  playBoot({});
  assert.equal(w2.boot(), null, 'already failed: never shown');
});

await test('playBoot without a guard is a plain timed presentation', () => {
  const w = fakeWorld(null);
  playBoot({});
  w.play(10000);
  assert.equal(capt(w), 'Ready');
  assert.ok(w.boot().classList.contains('gone'));
});

await test('VER-2: index.html and boot.js never hardcode the product name', () => {
  const html = read('ui', 'index.html');
  const src = read('ui', 'modules', 'boot.js');
  const code = src.replace(/\/\/.*$/gm, '');
  assert.ok(!/Controlyx/i.test(html), 'index.html: the server fills data-brand from utils.APP_*');
  assert.ok(!/Controlyx|\b2026\b/.test(code), 'boot.js reads window.__APP_*');
  for (const m of ['title', 'name']) assert.match(html, new RegExp(`data-brand="${m}"`));
  assert.match(html, /<title data-brand="title"><\/title>/);
  assert.match(html, /id="app-title" data-brand="title"/);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
