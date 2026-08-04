/** Unit tests for pure helpers in ui/modules/evm.js — run: node tests/js/test_evm.js */
import assert from 'node:assert/strict';
import { egp, asPct, spiStatus, overallProgress, projectProgress } from '../../ui/modules/evm.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

console.log('\negp / asPct');
test('egp millions', () => assert.equal(egp(412.6e6), '412.6M'));
test('egp billions', () => assert.equal(egp(1.2e9), '1.20B'));
test('egp null', () => assert.equal(egp(null), '—'));
test('asPct 0.94 → 94%', () => assert.equal(asPct(0.94), '94%'));
test('asPct null', () => assert.equal(asPct(null), '—'));

console.log('\nspiStatus');
test('ahead', () => assert.equal(spiStatus(1.02).cls, 'color-green'));
test('slightly behind', () => assert.equal(spiStatus(0.97).cls, 'color-amber'));
test('behind', () => assert.equal(spiStatus(0.80).label, 'Behind Schedule'));

console.log('\noverallProgress (weights)');
const cats = {
  A: { weight: 0.5, planned_pct: 0.8, actual_pct: 0.6 },
  B: { weight: 0.5, planned_pct: 0.4, actual_pct: 0.2 },
};
test('default weights', () => {
  const o = overallProgress(cats, null);
  assert.equal(Math.round(o.planned * 100), 60);   // (0.8+0.4)/2
  assert.equal(Math.round(o.actual * 100), 40);
});
test('edited weights renormalize', () => {
  const o = overallProgress(cats, { A: 0.9, B: 0.1 });
  // planned = (0.9*0.8 + 0.1*0.4)/1.0 = 0.76
  assert.equal(Math.round(o.planned * 100), 76);
});

console.log('\nprojectProgress (slicer Overall — matches Category Weights totals)');
const pcats = {
  Construction: { weight: 0.95, planned_pct: 0.345, actual_pct: 0.324 },
  Design:       { weight: 0.015, planned_pct: 0.80, actual_pct: 0.72 },
};
test('unnormalised weighted sum (default weights)', () => {
  const o = projectProgress(pcats, null);
  // planned = .95*.345 + .015*.80 = 0.33975 ; actual = .95*.324 + .015*.72 = 0.3186
  assert.equal((o.planned * 100).toFixed(2), '33.98');
  assert.equal((o.actual * 100).toFixed(2), '31.86');
});
test('does NOT renormalise when weights sum < 1', () => {
  const o = projectProgress({ A: { weight: 0.5, planned_pct: 0.8, actual_pct: 0.6 } }, null);
  assert.equal((o.planned * 100).toFixed(1), '40.0');   // 0.5*0.8, not 0.8
  assert.equal((o.actual * 100).toFixed(1), '30.0');
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
