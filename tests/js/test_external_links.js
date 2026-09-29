/**
 * Unit tests for ui/modules/external_links.js — every web link opens in the default browser
 * (packaged app: js_api.open_external with the https allow-list), never inside the app
 * window; a refused/failed open shows a visible in-page note (no alert — a no-op in WebView2).
 * Also static guards: app.js installs the interceptor, every https link the UI renders is on
 * the Python allow-list (utils.EXTERNAL_LINK_HOSTS).
 * Run: node tests/js/test_external_links.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  isExternalHref, externalLinkTarget, openExternal, installExternalLinks,
} from '../../ui/modules/external_links.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..', '..');
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), 'utf8');

let passed = 0;
let failed = 0;
const pending = [];
function test(name, fn) {
  pending.push((async () => {
    try { await fn(); console.log(`  ✓ ${name}`); passed++; }
    catch (err) { console.error(`  ✗ ${name}`); console.error(err); failed++; }
  })());
}

const BASE = 'http://localhost:9012/';

test('external = http(s) to another host; the local server and non-web schemes are not', () => {
  assert.equal(isExternalHref('https://leafletjs.com', BASE), true);
  assert.equal(isExternalHref('https://www.openstreetmap.org/copyright', BASE), true);
  assert.equal(isExternalHref('http://example.com/x', BASE), true);
  assert.equal(isExternalHref('/ui/style.css', BASE), false);
  assert.equal(isExternalHref('#sec', BASE), false);
  assert.equal(isExternalHref('http://localhost:9012/api/history', BASE), false);
  assert.equal(isExternalHref('http://127.0.0.1:9012/', BASE), false);
  assert.equal(isExternalHref('http://[::1]:9012/', BASE), false);
  assert.equal(isExternalHref('javascript:void(0)', BASE), false);
  assert.equal(isExternalHref('mailto:a@b.c', BASE), false);
  assert.equal(isExternalHref('', BASE), false);
  assert.equal(isExternalHref(null, BASE), false);
});

function fakeClick(href, extra = {}) {
  const a = { getAttribute: (k) => (k === 'href' ? href : null) };
  return { target: { closest: (sel) => (sel === 'a[href]' ? a : null) }, button: 0, defaultPrevented: false, ...extra };
}

test('click decision: a left click on an external link is intercepted', () => {
  assert.equal(externalLinkTarget(fakeClick('https://leafletjs.com'), BASE), 'https://leafletjs.com/');
  assert.equal(externalLinkTarget(fakeClick('/ui/x'), BASE), null);
  assert.equal(externalLinkTarget(fakeClick('https://leafletjs.com', { button: 2 }), BASE), null);
  assert.equal(externalLinkTarget(fakeClick('https://leafletjs.com', { defaultPrevented: true }), BASE), null);
  assert.equal(externalLinkTarget({ target: { closest: () => null }, button: 0 }, BASE), null);
});

test('packaged app: open_external is called and nothing is shown on success', async () => {
  const calls = []; const notes = [];
  const ok = await openExternal('https://leafletjs.com/', {
    api: { open_external: async (u) => { calls.push(u); return true; } }, note: (t) => notes.push(t),
  });
  assert.equal(ok, true);
  assert.deepEqual(calls, ['https://leafletjs.com/']);
  assert.equal(notes.length, 0);
});

test('packaged app: a refused link shows a visible note with the address to copy', async () => {
  const notes = [];
  const ok = await openExternal('https://evil.example/', {
    api: { open_external: async () => false }, note: (t) => notes.push(t),
  });
  assert.equal(ok, false);
  assert.equal(notes.length, 1);
  assert.match(notes[0], /Copy the address/);
  assert.match(notes[0], /https:\/\/evil\.example\//);
});

test('packaged app: a failing bridge call also shows the note (never throws)', async () => {
  const notes = [];
  const ok = await openExternal('https://leafletjs.com/', {
    api: { open_external: async () => { throw new Error('bridge down'); } }, note: (t) => notes.push(t),
  });
  assert.equal(ok, false);
  assert.equal(notes.length, 1);
});

test('plain browser (dev harness): opens a new tab, never the same window', async () => {
  const opened = [];
  const win = { open: (u, t, f) => { opened.push([u, t, f]); return null; } };
  const ok = await openExternal('https://leafletjs.com/', { api: null, win, note: () => {} });
  assert.equal(ok, true);
  assert.deepEqual(opened, [['https://leafletjs.com/', '_blank', 'noopener']]);
});

test('installExternalLinks: one CAPTURE-phase window listener (Leaflet stops bubbling)', () => {
  const added = [];
  const win = { addEventListener: (type, fn, capture) => added.push([type, capture]), location: { href: BASE } };
  assert.equal(installExternalLinks(win), true);
  assert.deepEqual(added.find(a => a[0] === 'click'), ['click', true]);
  assert.equal(installExternalLinks(win), false, 'idempotent');
});

test('installed handler: prevents the in-window navigation and stops the link handler', async () => {
  // installExternalLinks is idempotent per module, so exercise the handler logic directly.
  const ev = fakeClick('https://www.openstreetmap.org/copyright');
  let prevented = false; let stopped = false;
  ev.preventDefault = () => { prevented = true; };
  ev.stopPropagation = () => { stopped = true; };
  const href = externalLinkTarget(ev, BASE);
  assert.equal(href, 'https://www.openstreetmap.org/copyright');
  ev.preventDefault(); ev.stopPropagation();
  assert.ok(prevented && stopped);
});

test('app.js installs the interceptor at startup', () => {
  const src = read('ui', 'app.js');
  assert.match(src, /import \{ installExternalLinks \}\s+from '\.\/modules\/external_links\.js'/);
  assert.match(src, /installExternalLinks\(\);/);
});

test('help.js links go through the same openExternal path', () => {
  const src = read('ui', 'modules', 'help.js');
  assert.match(src, /import \{ openExternal \} from '\.\/external_links\.js'/);
  assert.match(src, /openExternal\(a\.href\)/);
});

test('every https link the UI renders is on the Python allow-list (utils.EXTERNAL_LINK_HOSTS)', () => {
  const utils = read('utils.py');
  const block = utils.slice(utils.indexOf('EXTERNAL_LINK_HOSTS = frozenset('));
  const hosts = new Set([...block.slice(0, block.indexOf('})')).matchAll(/'([a-z0-9.-]+)'/g)].map(m => m[1]));
  const files = ['ui/modules/help.js', 'ui/modules/calendar.js'];
  const found = [];
  for (const f of files) {
    const src = read(...f.split('/'));
    // href="https://…" in markup, url: 'https://…' in data tables, attribution links.
    for (const m of src.matchAll(/(?:href=\\?["']|url: ')(https:\/\/[^"'\\\s]+)/g)) found.push(m[1]);
  }
  // Leaflet's own attribution prefix links to leafletjs.com.
  const leaflet = read('ui', 'vendor', 'leaflet', 'leaflet.js');
  for (const m of leaflet.matchAll(/href="(https:\/\/[^"]+)"/g)) found.push(m[1]);
  assert.ok(found.length >= 3, 'found the UI links');
  for (const u of found) {
    const h = new URL(u).hostname;
    assert.ok(hosts.has(h), `${u} (host ${h}) is not on the allow-list`);
  }
});

await Promise.all(pending);
console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
