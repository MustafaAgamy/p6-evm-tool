/**
 * Unit tests for the pure helpers in ui/modules/aireview_helpers.js
 * Run: node tests/js/test_aireview.js
 */
import assert from 'node:assert/strict';
import { bandHex, kindClass, markerLeft, impactPill } from '../../ui/modules/aireview_helpers.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

test('bandHex maps each band to a colour, unknown → grey', () => {
  assert.equal(bandHex('green'), '#16a34a');
  assert.equal(bandHex('amber'), '#d97706');
  assert.equal(bandHex('orange'), '#ea580c');
  assert.equal(bandHex('red'), '#dc2626');
  assert.equal(bandHex('what'), '#94a3b8');
});

test('kindClass maps suggestion kinds', () => {
  assert.equal(kindClass('add'), 'ai-add');
  assert.equal(kindClass('remove'), 'ai-rem');
  assert.equal(kindClass('change'), 'ai-chg');
  assert.equal(kindClass('keep'), 'ai-keep');
  assert.equal(kindClass(undefined), '');
});

test('markerLeft clamps to 0–100', () => {
  assert.equal(markerLeft(74), 74);
  assert.equal(markerLeft(-5), 0);
  assert.equal(markerLeft(140), 100);
  assert.equal(markerLeft('x'), 0);
});

test('impactPill renders the right severity pill', () => {
  assert.ok(impactPill('Critical').includes('ai-crit'));
  assert.ok(impactPill('Near-critical').includes('ai-warn'));
  assert.ok(impactPill('Minor').includes('ai-minor'));
  assert.ok(impactPill('anything else').includes('ai-minor'));
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
