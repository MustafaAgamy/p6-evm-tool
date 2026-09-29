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
test('attached, every activity matched → green with matched count', () => {
  const s = baselineBannerState({ isXer: true, attachedName: 'BL.xer', matched: 1240, total: 1240 });
  assert.equal(s.cls, 'ok');
  assert.ok(s.title.includes('1240/1240 matched'));
  assert.deepEqual(s.actions, ['replace', 'remove']);
});
test('attached but part of the update is not in it → amber, says how many and which baseline P6 names (F4)', () => {
  const s = baselineBannerState({ isXer: true, attachedName: 'BL.xer', matched: 876, total: 1503,
    expectedName: 'GBT REV.03 - B1' });
  assert.equal(s.cls, 'warn');
  assert.ok(s.title.includes('876/1503 matched'));
  assert.match(s.msg, /627 of this update’s activities are not in that baseline/);
  assert.match(s.msg, /attach “GBT REV\.03 - B1”/);
  assert.deepEqual(s.actions, ['replace', 'remove']);
});
test('attached a different revision than the baseline P6 names → amber "P6 names X; you attached Y" (F4)', () => {
  const s = baselineBannerState({ isXer: false, fmt: 'XML', source: 'attached', attachedName: 'GBT_REV01.xer',
    matched: 1503, total: 1503, expectedName: 'Grain Bulk Terminal Detailed Schedule - Phase I REV.03 - B1',
    mismatch: true, attachedProject: 'Grain Bulk Terminal Phase I - Schedule Last REV' });
  assert.equal(s.cls, 'warn');
  assert.match(s.title, /not the baseline P6 names/);
  assert.match(s.msg, /P6 names “Grain Bulk Terminal Detailed Schedule - Phase I REV\.03 - B1” as this update’s baseline; you attached “Grain Bulk Terminal Phase I - Schedule Last REV”/);
  // no expected name known (an XML exported without its <BaselineProject>) → no mismatch claim
  assert.equal(baselineBannerState({ source: 'attached', fmt: 'XML', attachedName: 'B.xer', matched: 5, total: 5,
    mismatch: true }).cls, 'ok');
});
test('no baseline attached → the amber banner names the baseline P6 expects (F4)', () => {
  const s = baselineBannerState({ source: 'self', fmt: 'XER', attachedName: null,
    expectedName: 'SAINT GOBAIN, AS2 -  Civil Package 03 - Rev.01 Clean' });
  assert.match(s.msg, /P6 names “SAINT GOBAIN, AS2 -  Civil Package 03 - Rev\.01 Clean” as this update’s baseline — export that project \(XER or XML\) and attach it\./);
  assert.ok(!/P6 names/.test(baselineBannerState({ source: 'self', fmt: 'XER', attachedName: null }).msg));
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
// baseline_source (server: embedded | attached | self) drives it — XER and XML alike (R4)
test('XML exported WITHOUT its baseline (source self) → amber attach, says XML', () => {
  const s = baselineBannerState({ source: 'self', fmt: 'XML', attachedName: null });
  assert.equal(s.cls, 'warn');
  assert.deepEqual(s.actions, ['attach']);
  assert.match(s.msg, /XML was exported without its baseline project/);
  assert.match(s.msg, /XER or XML/);
});
test('XER update (source self) → amber attach, says the XER carries only a pointer to its baseline', () => {
  const s = baselineBannerState({ source: 'self', fmt: 'XER', attachedName: null });
  assert.deepEqual(s.actions, ['attach']);
  assert.match(s.msg, /XER update doesn’t include its baseline project/);
  assert.match(s.msg, /only a pointer/);
});
test('baseline embedded in the file → no banner, whatever the format', () => {
  assert.equal(baselineBannerState({ source: 'embedded', fmt: 'XML', attachedName: null }), null);
  assert.equal(baselineBannerState({ source: 'embedded', fmt: 'XER', attachedName: null }), null);
});
test('XML + attached baseline → green, same as XER + attached', () => {
  const s = baselineBannerState({ source: 'attached', fmt: 'XML', attachedName: 'BL.xer', matched: 12, total: 12 });
  assert.equal(s.cls, 'ok');
  assert.ok(s.title.includes('12/12 matched'));
});
test('no baseline assigned in P6 (baseline programme) → neutral info line, never the amber warning', () => {
  for (const fmt of ['XML', 'XER']) {
    const s = baselineBannerState({ source: 'self', fmt, attachedName: null, expected: false });
    assert.equal(s.cls, 'info');
    assert.match(s.title + ' ' + s.msg, /No baseline is assigned to this project in P6 — its own Planned dates are the baseline/);
    assert.ok(!/approximate|exported without/.test(s.msg));
  }
  // expected / unknown (older results) keep the amber "attach" warning
  assert.equal(baselineBannerState({ source: 'self', fmt: 'XML', attachedName: null, expected: true }).cls, 'warn');
  assert.equal(baselineBannerState({ source: 'self', fmt: 'XML', attachedName: null }).cls, 'warn');
});
test('a failed attach is said on EVERY banner — info (no baseline assigned in P6) and wrong-file too (alert() is a no-op in WebView2)', () => {
  const problem = 'No activities in “SG_bl_standalone.xml” match this update by Activity ID — it is probably another project’s baseline, so it was not attached.';
  const info = baselineBannerState({ source: 'self', fmt: 'XML', attachedName: null, problem, expected: false });
  assert.equal(info.cls, 'info');
  assert.ok((info.title + ' ' + info.msg).includes(problem), 'problem shown in the info banner');
  const none = baselineBannerState({ source: 'attached', fmt: 'XER', attachedName: 'WRONG.xer', matched: 0, total: 9, problem: 'Baseline not attached: disk error.' });
  assert.ok(none.msg.includes('Baseline not attached: disk error.'));
  const warn = baselineBannerState({ source: 'self', fmt: 'XER', attachedName: null, problem: 'Baseline not attached: x.' });
  assert.ok(warn.msg.includes('Baseline not attached: x.'));
  // and no stray text when nothing failed
  assert.ok(!/undefined|null/.test(baselineBannerState({ source: 'self', fmt: 'XML', attachedName: null, expected: false }).msg));
});
{
  const { baselineExpected } = await import('../../ui/modules/baseline.js');
  test('baselineExpected: only an explicit false means "none assigned in P6"', () => {
    assert.equal(baselineExpected({ baseline_expected: false }), false);
    assert.equal(baselineExpected({ baseline_expected: true }), true);
    assert.equal(baselineExpected({}), true);
    assert.equal(baselineExpected(null), true);
  });
}
test('an attached baseline that is no longer on disk is named in the banner', () => {
  const s = baselineBannerState({ source: 'self', fmt: 'XER', attachedName: null, missing: 'BL-Rev01.xer' });
  assert.match(s.msg, /BL-Rev01\.xer\) is no longer available/);
});
{
  const { baselineSource } = await import('../../ui/modules/baseline.js');
  test('baselineSource: server value wins; attached name = attached; old results fall back by extension', () => {
    assert.equal(baselineSource({ baseline_source: 'self' }, 'a.xml'), 'self');
    assert.equal(baselineSource({ baseline_source: 'embedded' }, 'a.xer'), 'embedded');
    assert.equal(baselineSource({ baseline_name: 'BL.xer' }, 'a.xml'), 'attached');
    assert.equal(baselineSource({}, 'C:/x/update.XER'), 'self');
    assert.equal(baselineSource({}, 'C:/x/update.xml'), 'embedded');
  });
}

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

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
