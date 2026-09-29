/** Unit tests for pure helpers in ui/modules/evm.js — run: node tests/js/test_evm.js */
import assert from 'node:assert/strict';
import { egp, egpExact, asPct, spiStatus, overallProgress, projectProgress, sourceType, sourceName, baselineBannerState } from '../../ui/modules/evm.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

console.log('\negp / asPct');
test('egp millions', () => assert.equal(egp(412.6e6), '412.60M'));
test('egp millions 2dp matches P6', () => assert.equal(egp(80.15e6), '80.15M'));
test('egpExact full number for KPI tiles', () => assert.equal(egpExact(243805396.8), '243,805,397'));
test('egpExact null', () => assert.equal(egpExact(null), '—'));
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

console.log('\nsourceType / sourceName (active-file label — XML vs XER)');
test('xml path → XML', () => assert.equal(sourceType('C:\\Users\\x\\Alstom-UP-006-12-Oct.25.xml'), 'XML'));
test('xer path → XER', () => assert.equal(sourceType('C:\\Users\\x\\Alstom-UP-006-12-Oct.25.xer'), 'XER'));
test('forward-slash path', () => assert.equal(sourceType('/home/x/schedule.XER'), 'XER'));
test('no extension → dash', () => assert.equal(sourceType('C:\\folder\\noext'), '—'));
test('empty → dash', () => assert.equal(sourceType(''), '—'));
test('name from win path', () => assert.equal(sourceName('C:\\a\\b\\Alstom.xml'), 'Alstom.xml'));
test('name from posix path', () => assert.equal(sourceName('/a/b/Update.xer'), 'Update.xer'));

console.log('\nbaselineBannerState (attach-baseline prompt)');
test('XER without baseline → amber attach', () => {
  const s = baselineBannerState({ isXer: true, attachedName: null });
  assert.equal(s.cls, 'warn');
  assert.deepEqual(s.actions, ['attach']);
});
test('attached → green with matched count', () => {
  const s = baselineBannerState({ isXer: true, attachedName: 'BL.xer', matched: 1236, total: 1240 });
  assert.equal(s.cls, 'ok');
  assert.ok(s.title.includes('1236/1240 matched'));
  assert.deepEqual(s.actions, ['replace', 'remove']);
});
test('attached without count → green, no count text', () => {
  const s = baselineBannerState({ isXer: true, attachedName: 'BL.xer' });
  assert.equal(s.cls, 'ok');
  assert.ok(!s.title.includes('matched'));
});
test('XML (embedded baseline) → no banner', () => {
  assert.equal(baselineBannerState({ isXer: false, attachedName: null }), null);
});
test('attached but 0 matched → amber mismatch warning, not green', () => {
  const s = baselineBannerState({ isXer: true, attachedName: 'WRONG.xer', matched: 0, total: 1240 });
  assert.equal(s.cls, 'warn');
  assert.ok(s.title.toLowerCase().includes('no activities matched'));
  assert.deepEqual(s.actions, ['replace', 'remove']);
});

console.log('\nattached baseline survives a re-render (Ctrl+R / Analysis ▸ Run again)');
{
  const fs = await import('node:fs');
  const src = fs.readFileSync(new URL('../../ui/modules/evm.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
  const fn = src.slice(src.indexOf('async function attachBaseline'), src.indexOf('async function removeBaseline'));
  test('attachBaseline records the baseline ON THE RESULT (renderEvm restores from result.baseline_*)', () => {
    for (const k of ['baseline_name', 'baseline_path', 'baseline_matched', 'baseline_total']) {
      assert.match(fn, new RegExp(`result\\.${k}\\s*=`), `attachBaseline does not set result.${k}`);
    }
    assert.ok(fn.indexOf('result.baseline_name') < fn.indexOf('_mergeEvmNumbers(result, data)'),
      'set result.baseline_* before re-rendering');
  });
  test('renderEvm restores state.baseline* from result.baseline_* (the re-render path)', () => {
    assert.match(src, /if \(result\.baseline_name\) \{[^}]*state\.baselinePath = result\.baseline_path;/);
  });
}

console.log('\nProject Setup (weights + Actual Cost) is saved with the project, not the browser');
{
  const { resolveEvmSetup } = await import('../../ui/modules/evm.js');
  const cats2 = { Construction: { weight: 0.7 }, Engineering: { weight: 0.3 } };
  test('nothing saved → the schedule weights, Actual Cost from P6', () => {
    assert.deepEqual(resolveEvmSetup(cats2, null, null),
      { weights: { Construction: 0.7, Engineering: 0.3 }, actualCost: null, fromLegacy: false });
  });
  test('the project\'s saved setup wins over the schedule weights', () => {
    const r = resolveEvmSetup(cats2, { weights: { Construction: 0.5, Engineering: 0.5 }, actual_cost: 1200 }, null);
    assert.deepEqual(r, { weights: { Construction: 0.5, Engineering: 0.5 }, actualCost: 1200, fromLegacy: false });
  });
  test('saved setup wins over an old browser copy (which is ignored)', () => {
    const r = resolveEvmSetup(cats2, { weights: { Construction: 0.4 }, actual_cost: null },
      { weights: { Construction: 0.9 }, actualCost: 5 });
    assert.equal(r.weights.Construction, 0.4);
    assert.equal(r.actualCost, null);
    assert.equal(r.fromLegacy, false);
  });
  test('an old browser copy is used once and flagged to be moved into the project', () => {
    const r = resolveEvmSetup(cats2, null, { weights: { Engineering: 0.1 }, actualCost: 77 });
    assert.deepEqual(r, { weights: { Construction: 0.7, Engineering: 0.1 }, actualCost: 77, fromLegacy: true });
  });
  test('only finite numbers are taken (a corrupt value never reaches the math)', () => {
    const r = resolveEvmSetup(cats2, { weights: { Construction: 'x', Engineering: NaN }, actual_cost: Infinity }, null);
    assert.deepEqual(r.weights, { Construction: 0.7, Engineering: 0.3 });
    assert.equal(r.actualCost, null);
  });
  const src = (await import('node:fs')).readFileSync(new URL('../../ui/modules/evm.js', import.meta.url), 'utf8');
  test('the editor saves through /api/project/evm-setup and never writes browser storage', () => {
    assert.match(src, /api\/project\/evm-setup/);
    assert.doesNotMatch(src, /localStorage\.setItem\(/);
  });
  test('a failed save is shown in the dialog (no alert — a no-op in WebView2)', () => {
    const at = src.indexOf('function openInputsEditor');
    const ed = src.slice(at, at + 4000);
    assert.match(ed, /Not saved — \$\{res\.error\}/);
    assert.doesNotMatch(ed, /\balert\(/);
  });
}

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
