/**
 * Online services show a clear in-page message when offline — never a silent grey map, a
 * forever-disabled button, or an invented zero estimate.
 *   * AI brain setup: polling stops (buttons come back) once the download ends WITHOUT
 *     success (offline / cut short / no engine) — brainSetupSettled.
 *   * Bad Weather: a failed Calculate renders a visible notice card and keeps the last
 *     estimate; the map shows an offline note when its tiles cannot load; the place search
 *     shows the server's plain message.
 * Run: node tests/js/test_online_notices.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { brainSetupSettled } from '../../ui/modules/chat.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..', '..');
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), 'utf8').split('\r\n').join('\n');

let passed = 0;
let failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}`); console.error(err); failed++; }
}

test('brain setup: still downloading → keep polling', () => {
  assert.equal(brainSetupSettled({ downloading: true, progress: 12 }), false);
  assert.equal(brainSetupSettled({ downloading: false }), false, 'not started yet');
  assert.equal(brainSetupSettled(null), false);
});

test('brain setup: ready, failed or no engine → stop polling, give the buttons back', () => {
  assert.equal(brainSetupSettled({ ready: true }), true);
  assert.equal(brainSetupSettled({ downloading: false, error: 'No internet connection — …' }), true);
  assert.equal(brainSetupSettled({ downloading: false, engine: false }), true);
});

const chat = read('ui', 'modules', 'chat.js');
test('brain setup: the error is written into the page (not only the pill)', () => {
  assert.match(chat, /else if \(BRAIN\.error\) note\.textContent = '⚠ ' \+ BRAIN\.error/);
  assert.match(chat, /if \(brainSetupSettled\(BRAIN\)\) stop\(\);/);
  assert.match(chat, /if \(d && d\.ok === false\)/, 'an immediate refusal is shown, not polled');
});

const cal = read('ui', 'modules', 'calendar.js');
test('weather: a failed Calculate shows a notice card and keeps the last estimate', () => {
  assert.match(cal, /_wxNotice = \{ text: resp\.error/);
  assert.match(cal, /No new weather estimate\./);
  assert.match(cal, /The estimate below is the last one calculated\./);
  // the failure branch must not overwrite _weather
  const branch = cal.slice(cal.indexOf('} else {\n        // No estimate'), cal.indexOf('} catch {\n      _wxNotice'));
  assert.ok(branch.length > 0, 'found the failure branch');
  assert.doesNotMatch(branch, /_weather = /);
});

test('weather: data gaps are shown on screen (banner + source rows)', () => {
  assert.match(cal, /Calculated with a data gap:/);
  assert.match(cal, /row\('Data gap', escapeHtml\(g\)\)/);
  assert.match(read('p6_calendar', 'report.py'), /ref_pairs\.append\(\('Data gap'/);
});

test('map: offline tiles → a visible note; OSM attribution is a real link', () => {
  assert.match(cal, /tiles\.on\('tileerror'/);
  assert.match(cal, /The map pictures need an internet connection/);
  assert.match(cal, /href="https:\/\/www\.openstreetmap\.org\/copyright"/);
});

test('place search: the server message is shown (offline ≠ "no match")', () => {
  assert.match(cal, /if \(!resp\.ok\) \{/);
  assert.match(cal, /No places match/);
  assert.doesNotMatch(cal, /No matches \(offline\?\)/);
});

test('CSS: the notices are themed (tokens, no fixed colours)', () => {
  const css = read('ui', 'style.css');
  for (const cls of ['.cal-map-offline', '.cal-loc-err', '.cal-wx-notice']) {
    const i = css.indexOf(cls + ' {');
    assert.ok(i >= 0, cls);
    assert.match(css.slice(i, css.indexOf('}', i)), /var\(--warning-bg\)/);
  }
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
