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
await test('Narrative "Edit setup" re-opens the interview at once from the choices already read for this file (no bare wait)', () => {
  const nar = read('ui', 'modules', 'narrative.js');
  assert.match(nar, /addEventListener\('click', \(\) => startSetupChat\(\{ reuse: true \}\)\)/);
  assert.match(nar, /_chatMetaFor === chatFileKey\(\)/, 'only the SAME file\'s choices are reused');
  assert.match(nar, /_chatMeta = \{\}; _chatMetaFor = null;/, 'a new Run always reads the file afresh');
  assert.match(nar, /return startSetupChat\(\);/, 'the Run itself still reads the file under the gated bar');
});
await test('every feature that waits on the server names its real stage on the bar (revealStage)', () => {
  for (const mod of ['calendar.js', 'compare.js', 'critpath.js', 'period.js', 'revcompare.js', 'special.js',
    'update.js', 'construct.js', 'audit.js', 'narrative.js']) {
    const src = read('ui', 'modules', mod);
    assert.match(src, /import \{[^}]*\brevealStage\b[^}]*\}\s+from '\.\/featurereveal\.js'/, mod);
    assert.match(src, /revealStage\('[^']+'\)/, mod);
  }
});

await test('Update Analysis: a file with no baseline inside it is answered at once from the import flag (RUNUX-05)', () => {
  const upd = read('ui', 'modules', 'update.js');
  const fn = upd.slice(upd.indexOf('async function _runAnalyze'), upd.indexOf('function _showAnalysis'));
  const flag = fn.indexOf('has_embedded_baseline === false'), fetchAt = fn.indexOf('fetch(');
  assert.ok(flag > 0 && fetchAt > flag, 'the import flag must be checked BEFORE the /api/update/analyze request');
  assert.match(fn.slice(flag, fetchAt), /_showAnalysis\(body, \{ ok: false, code: 'no_baseline' \}\);\s*return;/,
    'the instant answer goes through the same no_baseline branch the server answer uses');
  const srv = read('server.py');
  assert.match(srv, /safe_result\['has_embedded_baseline'\] = bool\(getattr\(data, 'baseline_by_id', None\)\)/);
  assert.match(srv, /'has_embedded_baseline': safe_result\.get\('has_embedded_baseline'\)/, 'kept for Recent Projects re-opens');
  assert.match(srv, /result\['has_embedded_baseline'\] = extras\.get\('has_embedded_baseline'\)/);
  // the analysis decides "no baseline" by the very same test the import flag records
  assert.match(read('p6_update', 'analysis.py'), /has_baseline = bool\(getattr\(data, 'baseline_by_id', None\)\)/);
});

// ── RUNUX-07/08/09: long server Runs name their REAL steps and move through their bands ──
await test('server steps move the bar through their bands; never past the wait cap while the request runs', () => {
  const m = createRevealModel();
  const T = REVEAL_TIMING;
  const tr = drive(m, {
    until: 70000, stopOnReveal: false, frameMs: 50,
    events: {
      0: (mm, t) => { mm.workStarted(t); mm.requestSent(); },
      200: (mm, t) => mm.setBand(0, 0.25, 5, t),         // Reading Rev.00 (est 5 s)
      8000: (mm, t) => mm.setBand(0.25, 0.8, 11, t),     // Reading Rev.01 (est 11 s)
      30000: (mm, t) => mm.setBand(0.8, 1, 4, t),        // Matching and comparing (est 4 s)
    },
  });
  const at = ms => tr.find(f => f.now >= ms);
  const band = x => 6 + (T.WAIT_CAP - 6) * x;
  assert.ok(at(7900).display <= band(0.25) + 1e-9, 'first step stays inside its share of the bar');
  assert.ok(at(7900).display > band(0.2), 'and has moved through most of it by its estimate');
  assert.ok(at(29900).display <= band(0.8) + 1e-9 && at(29900).display > band(0.7), 'second step fills its share');
  assert.ok(tr.every(f => f.pct < 100 && f.display < T.WAIT_CAP), 'never 100% (nor the cap) while the request runs');
  for (let i = 1; i < tr.length; i++) assert.ok(tr[i].display >= tr[i - 1].display, 'never goes down');
});

await test('stage polls (/api/run/stage) are not counted as work by the request tap', async () => {
  const target = { fetch: () => Promise.resolve({ ok: true }) };
  installRequestTap(target);
  const m = createRevealModel();
  REVEAL_WATCHERS.add(m);
  try {
    await target.fetch('http://localhost:1/api/run/stage?id=x');
    assert.equal(m.inflight, 0);
    const p = target.fetch('http://localhost:1/api/revcompare');
    assert.equal(m.inflight, 1);
    await p; await Promise.resolve();
    assert.equal(m.inflight, 0);
  } finally { REVEAL_WATCHERS.delete(m); }
});

await test('followRunStages polls with its id, shows the step + its band, and stops when told', async () => {
  const { followRunStages } = await import('../../ui/modules/featurereveal.js');
  const urls = [];
  let answer = { ok: true, stage: { label: 'Reading Rev.01 — b.xml', from: 0.25, to: 0.8, est_s: 11, step: 2, steps: 3 } };
  const realFetch = globalThis.fetch;
  globalThis.fetch = (u) => { urls.push(String(u)); return Promise.resolve({ json: () => Promise.resolve(answer) }); };
  const m = createRevealModel();
  REVEAL_WATCHERS.add(m);
  try {
    const st = followRunStages(4321, { every: 20 });
    assert.match(st.id, /^run-/);
    await new Promise(r => setTimeout(r, 120));
    assert.ok(urls.length >= 1 && urls.every(u => u === `http://localhost:4321/api/run/stage?id=${st.id}`));
    m.workStarted(0); m.requestSent();
    const f = m.frame(1000);
    assert.equal(f.label, 'Reading Rev.01 — b.xml');
    st.stop();
    const n = urls.length;
    answer = { ok: true, stage: { label: 'late', from: 0.8, to: 1, est_s: 1, step: 3, steps: 3 } };
    await new Promise(r => setTimeout(r, 100));
    assert.ok(urls.length <= n + 1, 'no more polling after stop()');
    assert.equal(m.frame(1100).label, 'Reading Rev.01 — b.xml', 'a poll answered after stop() is ignored');
  } finally { REVEAL_WATCHERS.delete(m); globalThis.fetch = realFetch; }
});

await test('Baseline Revision, Critical Path and Consultant Review send a run_id and follow the server steps', () => {
  for (const [mod, api] of [['revcompare.js', '/api/revcompare'], ['critpath.js', '/api/critpath/analyze'], ['compare.js', '/api/compare']]) {
    const src = read('ui', 'modules', mod);
    assert.match(src, /import \{[^}]*\bfollowRunStages\b[^}]*\}\s+from '\.\/featurereveal\.js'/, mod);
    const at = src.indexOf(api + '`');
    const win = src.slice(src.lastIndexOf('followRunStages(state.serverPort)', at), at + 700);
    assert.ok(win.startsWith('followRunStages(state.serverPort)'), mod + ': poller started before the request');
    assert.match(win, /run_id/, mod + ': run_id sent with the request');
    assert.match(win, /\}\)\.finally\(stages\.stop\);/, mod + ': polling stops the moment the answer arrives');
  }
  const srv = read('server.py');
  assert.match(srv, /elif self\.path\.startswith\('\/api\/run\/stage'\):/);
  for (const lbl of ["f'Reading Rev.00 — ", "f'Reading Rev.01 — ", "'Matching activities and comparing the revisions'",
    "'Tracing the driving path to every finish milestone'", "f'Reading the baseline — ", "'Comparing logic, durations and milestones'"]) {
    assert.ok(srv.includes(lbl), 'server step: ' + lbl);
  }
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
