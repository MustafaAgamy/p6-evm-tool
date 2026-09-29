/**
 * Shared Run presentation — ui/modules/featurereveal.js (owner comment 36: "no gap after Run").
 *   • The bar follows REAL stages (analysing → calculating → results received → rendering → painted).
 *   • The label never reads 100% until the work settled AND a frame was painted since.
 *   • The reveal happens in the SAME frame the bar reaches 100% (no hold, no timer).
 *   • While a request is in flight the value stays below the wait cap, however long it takes.
 * Run: node tests/js/test_featurereveal.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRevealModel, installRequestTap, REVEAL_WATCHERS, REVEAL_TIMING } from '../../ui/modules/featurereveal.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..', '..');
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), 'utf8');

let passed = 0;
let failed = 0;
async function test(name, fn) {
  try { await fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}`); console.error(`    ${err.message}`); failed++; }
}

const FRAME = 16;
// Drive a model frame-by-frame. `events` = { atMs: fn(model, now) }. Returns the frame trace.
function drive(model, { events = {}, until = 5000, stopOnReveal = true, frameMs = FRAME } = {}) {
  const trace = [];
  const pending = Object.keys(events).map(Number).sort((a, b) => a - b);
  for (let now = 0; now <= until; now += frameMs) {
    while (pending.length && pending[0] <= now) { const at = pending.shift(); events[at](model, at); }
    const f = model.frame(now);
    trace.push({ now, ...f });
    if (f.reveal && stopOnReveal) break;
  }
  return trace;
}
const first = (trace, pred) => trace.find(pred);
const label100 = (f) => f.pct === 100;

console.log('\nStage model — invariants');
await test('instant work: 100% only on the reveal frame, after the settle + one painted frame', () => {
  const m = createRevealModel();
  const tr = drive(m, { events: { 20: (m, t) => m.workStarted(t), 25: (m, t) => m.settled(t) } });
  const rev = first(tr, f => f.reveal);
  assert.ok(rev, 'reveals');
  assert.equal(tr.filter(label100).length, 1, '100% is painted exactly once');
  assert.equal(first(tr, label100), rev, 'the first 100% frame IS the reveal frame');
  // an instant result still gets a short, smooth fill (brand), never a jump or a long hold
  assert.ok(rev.now >= REVEAL_TIMING.MIN_SHOW_MS - FRAME && rev.now <= REVEAL_TIMING.MIN_SHOW_MS + 3 * FRAME, `reveal at ${rev.now} ms`);
});

await test('never 100% before the work settles — even after 70 s of server compute', () => {
  const m = createRevealModel();
  const tr = drive(m, { events: { 20: (m, t) => { m.workStarted(t); m.requestSent(); } }, until: 70000, stopOnReveal: false });
  assert.ok(tr.every(f => !f.reveal && f.pct < 100), 'no 100%');
  const maxPct = Math.max(...tr.map(f => f.pct));
  assert.ok(maxPct < REVEAL_TIMING.WAIT_CAP, `max ${maxPct}% stays below the wait cap`);
  assert.ok(maxPct >= 85, `creeps on (reached ${maxPct}%) — never looks frozen at the start`);
  assert.equal(tr.at(-1).stage, 'computing');
  assert.match(tr.at(-1).label, /^Still calculating · 70 s$/);
});

await test('stages follow the real events: calculating → received → rendering → painted', () => {
  const m = createRevealModel();
  const tr = drive(m, { until: 20000, events: {
    16: (m, t) => { m.workStarted(t); m.requestSent(); },
    4000: (m) => m.requestDone(),
    4016: (m, t) => m.settled(t),
  } });
  const stages = [...new Set(tr.map(f => f.stage))];
  assert.deepEqual(stages, ['analysing', 'computing', 'received', 'rendering', 'painted']);
  const rendering = tr.filter(f => f.stage === 'rendering');
  assert.equal(rendering.length, 1, 'exactly one frame (the one that paints the results) between settle and painted');
  assert.ok(rendering[0].pct <= REVEAL_TIMING.RENDER_PCT && rendering[0].pct < 100);
  assert.equal(first(tr, f => f.stage === 'computing').label, 'Calculating');
  assert.equal(first(tr, f => f.stage === 'received').label, 'Results received');
  assert.equal(rendering[0].label, 'Rendering results');
});

await test('reveal follows the paint immediately (≤ FINAL_MS + 2 frames), not a timer', () => {
  const m = createRevealModel();
  const tr = drive(m, { until: 20000, events: {
    16: (m, t) => { m.workStarted(t); m.requestSent(); },
    6000: (m) => m.requestDone(),
    6010: (m, t) => m.settled(t),
  } });
  const painted = first(tr, f => f.stage === 'painted');
  const rev = first(tr, f => f.reveal);
  assert.ok(rev.now - painted.now <= REVEAL_TIMING.FINAL_MS + 2 * FRAME, `painted@${painted.now} reveal@${rev.now}`);
  assert.equal(first(tr, label100), rev);
});

await test('the displayed value never goes down (sequential requests, received → calculating again)', () => {
  const m = createRevealModel();
  const tr = drive(m, { until: 30000, events: {
    16: (m, t) => { m.workStarted(t); m.requestSent(); },
    3000: (m) => m.requestDone(),
    3200: (m) => m.requestSent(),
    9000: (m) => m.requestDone(),
    9100: (m, t) => m.settled(t),
  } });
  for (let i = 1; i < tr.length; i++) assert.ok(tr[i].display >= tr[i - 1].display, `frame ${i}: ${tr[i - 1].display} → ${tr[i].display}`);
  for (let i = 1; i < tr.length; i++) assert.ok(tr[i].pct >= tr[i - 1].pct);
  assert.ok(tr.at(-1).reveal);
});

await test('a long frame (throttled / blocked main thread) cannot push the bar to 100% early', () => {
  const m = createRevealModel();
  m.frame(0); m.workStarted(10); m.requestSent();
  const f = m.frame(45000);                          // one 45 s frame
  assert.ok(f.pct < 100 && !f.reveal);
  m.requestDone(); m.settled(45010);
  const g = m.frame(90000);                          // huge frame right after settle = the paint frame
  assert.equal(g.stage, 'rendering'); assert.ok(g.pct < 100 && !g.reveal);
  const h = m.frame(90016);
  assert.equal(h.stage, 'painted');
  // then the bar closes the last few % within FINAL_MS and reveals on the 100% frame
  let t = 90016, f2 = h;
  while (!f2.reveal && t < 90016 + REVEAL_TIMING.FINAL_MS + 2 * FRAME) { assert.ok(f2.pct < 100); t += FRAME; f2 = m.frame(t); }
  assert.ok(f2.reveal, `revealed by ${t - 90016} ms after the paint`); assert.equal(f2.pct, 100);
});

await test('synchronous work (no request): analysing → rendering → painted, no "calculating"', () => {
  const m = createRevealModel();
  const tr = drive(m, { events: { 16: (m, t) => m.workStarted(t), 1400: (m, t) => m.settled(t) } });
  assert.ok(!tr.some(f => f.stage === 'computing' || f.stage === 'received'));
  assert.ok(tr.at(-1).reveal);
  assert.ok(tr.at(-1).now - 1400 <= REVEAL_TIMING.FINAL_MS + 3 * FRAME);
});

await test('label is an integer below 100 until the reveal (never "100%" while width is 99.x)', () => {
  const m = createRevealModel();
  const tr = drive(m, { until: 20000, events: { 16: (m, t) => m.workStarted(t), 700: (m, t) => m.settled(t) } });
  tr.filter(f => !f.reveal).forEach(f => { assert.ok(Number.isInteger(f.pct) && f.pct <= 99); });
});

await test('reduced motion: jumps straight to each stage but still waits for the painted frame', () => {
  const m = createRevealModel({ reduce: true });
  m.frame(0); m.workStarted(5); m.requestSent();
  assert.ok(m.frame(16).pct < REVEAL_TIMING.WAIT_CAP);
  m.requestDone(); m.settled(20);
  const a = m.frame(32); assert.equal(a.stage, 'rendering'); assert.equal(a.pct, REVEAL_TIMING.RENDER_PCT); assert.ok(!a.reveal);
  const b = m.frame(48); assert.ok(b.reveal); assert.equal(b.pct, 100);
});

console.log('\nRequest tap (window.fetch)');
await test('counts /api/ requests only while a reveal listens; returns the ORIGINAL promise', async () => {
  let resolveReq;
  const orig = () => new Promise(r => { resolveReq = r; });
  const win = { fetch: orig };
  assert.equal(installRequestTap(win), true);
  assert.equal(installRequestTap(win), true, 'idempotent');
  const m = createRevealModel();
  m.frame(0); m.workStarted(1);
  // not listening yet → not counted
  const p0 = win.fetch('http://localhost:1/api/history'); resolveReq({ ok: true }); await p0;
  assert.equal(m.inflight, 0);
  REVEAL_WATCHERS.add(m);
  try {
    const p = win.fetch('http://localhost:1/api/compare', { method: 'POST' });
    assert.equal(typeof p.then, 'function');
    assert.equal(m.inflight, 1);
    assert.equal(m.frame(16).stage, 'computing');
    const resp = { ok: true, marker: 42 };
    resolveReq(resp);
    assert.equal(await p, resp, 'caller receives the untouched response');
    await Promise.resolve();
    assert.equal(m.inflight, 0);
    assert.equal(m.frame(32).stage, 'received');
    // static files are not requests to the server's compute
    const ps = win.fetch('http://localhost:1/ui/style.css'); resolveReq({}); await ps;
    assert.equal(m.inflight, 0);
    // a failed request still closes its stage (and the caller still sees the rejection)
    let rejectReq; win.fetch = win.fetch; // (same wrapper)
    const failing = { fetch: () => new Promise((_, j) => { rejectReq = j; }) };
    installRequestTap(failing);
    const pf = failing.fetch('http://localhost:1/api/x');
    assert.equal(m.inflight, 1);
    rejectReq(new Error('offline'));
    await assert.rejects(pf, /offline/);
    await Promise.resolve();
    assert.equal(m.inflight, 0);
  } finally { REVEAL_WATCHERS.delete(m); }
});

console.log('\nWiring — every Run goes through the shared, gated presentation');
const app = read('ui', 'app.js');
await test('the single-input Run gate uses revealAndRun (gated on the work), not an ungated timer reveal', () => {
  assert.match(app, /revealAndRun\(host, meta\.title, \(\) => runFeature\(view\)\)/);
  assert.doesNotMatch(app, /playFeatureReveal\(/);
});
await test('async single-input features RETURN their work promise from runFeature', () => {
  for (const [view, fn] of [['construct', 'renderConstructPanel'], ['narrative', 'renderNarrative'], ['update', 'renderUpdatePanel'], ['special', 'renderSpecialPanel']]) {
    assert.match(app, new RegExp(`case '${view}':\\s+return ${fn}\\(\\);`), view);
  }
  assert.match(read('ui', 'modules', 'construct.js'), /return fetchAndRender\(/);
  assert.match(read('ui', 'modules', 'update.js'), /return _runAnalyze\(\);/);
  assert.match(read('ui', 'modules', 'narrative.js'), /return startSetupChat\(\);/);
  assert.match(read('ui', 'modules', 'special.js'), /export async function renderSpecialPanel/);
});
await test('self-gating features call revealAndRun with a host inside their .view-panel (the overlay mounts on the panel)', () => {
  const html = read('ui', 'index.html');
  const cases = [['calendar.js', 'weather-body', 'weather-panel'], ['compare.js', 'compare-body', 'compare-panel'],
    ['period.js', 'period-body', 'period-panel'], ['revcompare.js', 'revcompare-body', 'revcompare-panel']];
  for (const [mod, body, panel] of cases) {
    assert.match(read('ui', 'modules', mod), /revealAndRun\(/, mod);
    assert.match(html, new RegExp(`<div class="view-panel[^"]*" id="${panel}">\\s*<div id="${body}">`), `${body} sits in .view-panel#${panel}`);
  }
  // Critical Path renders #cpa-report inside #critpath-body, which sits in .view-panel#critpath-panel
  assert.match(read('ui', 'modules', 'critpath.js'), /revealAndRun\(rep,/);
  assert.match(html, /<div class="view-panel[^"]*" id="critpath-panel">\s*<div id="critpath-body">/);
  const fr = read('ui', 'modules', 'featurereveal.js');
  assert.match(fr, /host\.closest\('\.view-panel'\)/);
  assert.doesNotMatch(fr, /DUR \+ \(gate \? 20000/, 'no fixed 20 s cap that lifts the overlay onto a placeholder');
  assert.doesNotMatch(fr, /setTimeout\(finish, 80\)/, 'no hold after 100%');
});
await test('second-step Runs (Schedule Health milestones, Narrative Generate) also go through the gated bar', () => {
  const audit = read('ui', 'modules', 'audit.js');
  assert.match(audit, /return revealAndRun\(document\.getElementById\('audit-body'\), 'Schedule Health'/);
  const nar = read('ui', 'modules', 'narrative.js');
  assert.match(nar, /return revealAndRun\(document\.getElementById\('narrative-body'\), 'Baseline Narrative'/);
  assert.match(nar, /return fetchAndRender\(\);/);
});
await test('every feature that waits on the server names its real stage on the bar (revealStage)', () => {
  for (const mod of ['calendar.js', 'compare.js', 'critpath.js', 'period.js', 'revcompare.js', 'special.js',
    'update.js', 'construct.js', 'audit.js', 'narrative.js']) {
    const src = read('ui', 'modules', mod);
    assert.match(src, /import \{[^}]*\brevealStage\b[^}]*\}\s+from '\.\/featurereveal\.js'/, mod);
    assert.match(src, /revealStage\('[^']+'\)/, mod);
  }
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
