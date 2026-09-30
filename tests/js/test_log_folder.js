/**
 * [startup:F4] BLACK-8 — Help ▸ Contact & Support "Open log folder" (ui/modules/help.js).
 * The button opens the folder holding startup.log through the desktop app's bridge
 * (window.pywebview.api.open_log_folder); the log file's path is always said in words
 * (from GET /api/health) so it can be found even when the folder cannot be opened.
 * Failures are said beside the button — never alert/confirm (no-ops in WebView2).
 * Run: node tests/js/test_log_folder.js
 */
import assert from 'node:assert/strict';
import { wireLogFolder } from '../../ui/modules/help.js';

let passed = 0;
let failed = 0;
const queue = [];
function test(name, fn) { queue.push([name, fn]); }
async function runAll() {
  for (const [name, fn] of queue) {
    try { await fn(); console.log(`  ✓ ${name}`); passed++; }
    catch (err) { console.error(`  ✗ ${name}`); console.error(err); failed++; }
  }
}
const tick = () => new Promise(r => setTimeout(r, 0));
const settle = async () => { for (let i = 0; i < 8; i++) await tick(); };
const LOG = 'C:\\Users\\u\\AppData\\Roaming\\.controlyx\\logs\\startup.log';

function fakeRoot() {
  const handlers = {};
  const btn = { disabled: false, addEventListener: (ev, fn) => { handlers[ev] = fn; }, click: () => handlers.click && handlers.click() };
  const cls = new Set();
  const out = {
    textContent: '',
    classList: { toggle: (c, on) => (on ? cls.add(c) : cls.delete(c)), contains: c => cls.has(c) },
  };
  return { btn, out, querySelector: s => (s === '#hc-log-open' ? btn : s === '#hc-log-status' ? out : null) };
}
const health = (path) => () => Promise.resolve({ json: () => Promise.resolve({ ok: true, log_path: path }) });

test('shows where the log file is as soon as Help opens', async () => {
  globalThis.fetch = health(LOG);
  const r = fakeRoot();
  wireLogFolder(r, {});
  await settle();
  assert.equal(r.out.textContent, 'Log file: ' + LOG);
});

test('opens the folder through the app bridge', async () => {
  globalThis.fetch = health(LOG);
  const calls = [];
  const win = { pywebview: { api: { open_log_folder: () => { calls.push(1); return Promise.resolve({ ok: true, path: LOG }); } } } };
  const r = fakeRoot();
  wireLogFolder(r, win);
  await settle();
  r.btn.click();
  assert.equal(r.btn.disabled, true);
  assert.equal(r.out.textContent, 'Opening…');
  await settle();
  assert.equal(calls.length, 1);
  assert.equal(r.btn.disabled, false);
  assert.ok(r.out.textContent.startsWith('Opened.'), r.out.textContent);
  assert.ok(r.out.textContent.includes(LOG));
  assert.equal(r.out.classList.contains('err'), false);
});

test('folder could not be opened: says so and where the file is', async () => {
  globalThis.fetch = health(LOG);
  const win = { pywebview: { api: { open_log_folder: () => Promise.resolve({ ok: false, path: LOG }) } } };
  const r = fakeRoot();
  wireLogFolder(r, win);
  r.btn.click();
  await settle();
  assert.equal(r.out.textContent, 'Could not open the folder — the log file is here: ' + LOG);
  assert.equal(r.out.classList.contains('err'), true);
});

test('bridge call throws: path from /api/health, error shown, button usable again', async () => {
  globalThis.fetch = health(LOG);
  const win = { pywebview: { api: { open_log_folder: () => Promise.reject(new Error('bridge gone')) } } };
  const r = fakeRoot();
  wireLogFolder(r, win);
  r.btn.click();
  await settle();
  assert.equal(r.btn.disabled, false);
  assert.ok(r.out.textContent.includes(LOG) && r.out.classList.contains('err'));
});

test('no desktop bridge (plain browser): tells the path to open by hand', async () => {
  globalThis.fetch = health(LOG);
  const r = fakeRoot();
  wireLogFolder(r, {});
  r.btn.click();
  await settle();
  assert.equal(r.out.textContent, 'Open this folder in Explorer: ' + LOG);
  assert.equal(r.out.classList.contains('err'), false);
});

test('nothing answers: plain error, never a silent button', async () => {
  globalThis.fetch = () => Promise.reject(new Error('down'));
  const r = fakeRoot();
  wireLogFolder(r, {});
  r.btn.click();
  await settle();
  assert.equal(r.out.textContent, 'Could not open the folder (the app is not answering).');
  assert.equal(r.out.classList.contains('err'), true);
});

await runAll();
console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
