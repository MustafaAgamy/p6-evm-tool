/**
 * [accept:c25:r1] Help ▸ What's New (ui/modules/help.js whatsNewHtml).
 * The owner's comment 25: Help showed version 2.2.0 while the release was 2.8.0. About
 * and the footer were fixed, but What's New still carried a hand-typed "Since v2.2.0"
 * badge. The screen is now built from the newest CHANGELOG release (utils.release_notes(),
 * injected as window.__APP_RELEASE_NOTES__) and the one app version — never a literal.
 * Run: node tests/js/test_whats_new.js
 */
import assert from 'node:assert/strict';
import { whatsNewHtml } from '../../ui/modules/help.js';

let passed = 0;
let failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}`); console.error(err); failed++; }
}

const NOTES = {
  version: '2.8.0',
  date: '2026-09-26',
  items: [
    { kind: 'Added', title: 'Offline AI Chat: 15 complete answers, read straight from your P6 file',
      points: ['15 questions instead of 182', 'Nothing is lost'], more: 3 },
    { kind: 'Changed', title: 'Offline AI Chat', points: ["Manager's briefing"], more: 0 },
    { kind: 'Fixed', title: 'Fixes', points: ['AI Chat answers no longer show "None"'], more: 1 },
  ],
  upcoming: [
    { kind: 'Added', title: 'Shortcuts, Help and contacts', points: ['31 keyboard shortcuts'], more: 0 },
  ],
};
const versions = html => [...html.matchAll(/\bv?(\d+\.\d+\.\d+)\b/g)].map(m => m[1]);

test("heading and lead name the app's own version and release date", () => {
  const html = whatsNewHtml(NOTES, '2.8.0', 'Controlyx 2026');
  assert.match(html, /<h2>What's new in v2\.8\.0<\/h2>/);
  assert.match(html, /The headline changes in Controlyx 2026 v2\.8\.0, released 26 Sep 2026\./);
});

test('no other version than the app version appears anywhere (c25)', () => {
  const html = whatsNewHtml(NOTES, '2.8.0', 'Controlyx 2026');
  assert.deepEqual([...new Set(versions(html))], ['2.8.0']);
  assert.ok(!html.includes('hc-ver-pill'), 'no hand-typed version badge');
  assert.ok(!html.includes('2.2.0'));
});

test('every release item is listed with its kind badge, points and "more" count', () => {
  const html = whatsNewHtml(NOTES, '2.8.0', 'Controlyx 2026');
  assert.match(html, /Offline AI Chat: 15 complete answers, read straight from your P6 file <span class="hc-wn-kind">New<\/span>/);
  assert.match(html, /Offline AI Chat <span class="hc-wn-kind">Improved<\/span>/);
  assert.match(html, /Fixes <span class="hc-wn-kind">Fixed<\/span>/);
  assert.match(html, /<li>15 questions instead of 182<\/li><li>Nothing is lost<\/li><li class="more">…and 3 more changes<\/li>/);
  assert.match(html, /<li class="more">…and 1 more change<\/li>/);
  assert.match(html, /<li>AI Chat answers no longer show &quot;None&quot;<\/li>/, 'changelog text is escaped');
});

test('changes already in this build are listed under "Also in this build"', () => {
  const html = whatsNewHtml(NOTES, '2.8.0', 'Controlyx 2026');
  assert.match(html, /<h3 class="hc-wn-sub">Also in this build<\/h3>/);
  assert.ok(html.indexOf('Also in this build') > html.indexOf('Offline AI Chat'), 'release first');
  assert.match(html, /Shortcuts, Help and contacts/);
  const none = whatsNewHtml({ ...NOTES, upcoming: [] }, '2.8.0', 'Controlyx 2026');
  assert.ok(!none.includes('Also in this build'), 'section absent when the build has nothing extra');
});

test('no version known: no version text at all, never an invented one', () => {
  const html = whatsNewHtml({ version: '', date: '', items: [], upcoming: [] }, '', 'Controlyx 2026');
  assert.deepEqual(versions(html), []);
  assert.match(html, /<h2>Recent highlights<\/h2>/);
  assert.match(html, /The release notes are not included in this copy of Controlyx 2026\./);
});

test('missing or malformed notes never throw', () => {
  for (const bad of [null, undefined, 'x', 42, { items: 'x' }, { items: [null, 7, {}] }]) {
    const html = whatsNewHtml(bad, '2.8.0', 'Controlyx 2026');
    assert.match(html, /data-sec="whats-new"/);
  }
});

test('changelog text cannot inject markup', () => {
  const html = whatsNewHtml({ version: '2.8.0', items: [
    { kind: 'Added', title: '<img src=x onerror=alert(1)>', points: ['<b>x</b>'], more: 0 }] },
  '2.8.0', 'Controlyx 2026');
  assert.ok(!html.includes('<img'));
  assert.ok(!html.includes('<b>x</b>'));
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
