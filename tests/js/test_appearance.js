/**
 * Unit tests for the pure helpers in ui/modules/appearance.js — the shared report
 * Appearance picker. DOM-dependent parts (buildAppearancePicker) aren't covered here;
 * these check the mode catalogue, the backdrop lookup, and the safe fallbacks.
 * Run: node tests/js/test_appearance.js
 */
import assert from 'node:assert/strict';
import { REPORT_MODES, DEFAULT_MODE, backdropColor, getSavedMode } from '../../ui/modules/appearance.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

const EXPECTED = ['light', 'dark', 'midnight', 'sepia', 'contrast', 'blueprint'];

test('six modes in the expected order — matches report_theme.MODES', () => {
  assert.deepEqual(REPORT_MODES.map(m => m.id), EXPECTED);
});

test('every mode carries a label, description and swatch colours', () => {
  for (const m of REPORT_MODES) {
    assert.ok(m.label && m.desc, `${m.id} missing label/desc`);
    for (const k of ['page', 'accent', 'tile']) {
      assert.match(m[k], /^#[0-9a-fA-F]{6}$/, `${m.id}.${k} not a hex`);
    }
  }
});

test('DEFAULT_MODE is light', () => {
  assert.equal(DEFAULT_MODE, 'light');
});

test('backdropColor returns the page colour for a mode', () => {
  assert.equal(backdropColor('dark'), '#131922');
  assert.equal(backdropColor('blueprint'), '#0f3560');
  assert.equal(backdropColor('light'), '#ffffff');
});

test('backdropColor falls back to the light page for an unknown mode', () => {
  assert.equal(backdropColor('nope'), '#ffffff');
  assert.equal(backdropColor(undefined), '#ffffff');
});

test('getSavedMode falls back to light when storage is unavailable (node)', () => {
  assert.equal(getSavedMode(), 'light');
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
