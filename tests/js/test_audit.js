/**
 * Unit tests for the pure helpers in ui/modules/audit.js
 * Run: node tests/js/test_audit.js
 */
import assert from 'node:assert/strict';
import { filterFindings, severityClass, scoreColor, gaugeDashoffset, uniqueValues, areaOf, shortWbs, gradeClass,
         oosPillClass, oosCritLabel, barPct, tabScore, statusColor, statusDot, verdictClass }
  from '../../ui/modules/audit.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

const F = [
  { severity: 'Critical', check_id: 'LOGIC-003', check_name: 'Circular Logic', wbs_path: 'T > Sub',  activity_id: 'A1', activity_name: 'Loop' },
  { severity: 'High',     check_id: 'LOGIC-001', check_name: 'Open Ends',      wbs_path: 'T > Roof', activity_id: 'A2', activity_name: 'Steel' },
  { severity: 'Medium',   check_id: 'FLOAT-001', check_name: 'Float Analysis', wbs_path: 'T > MEP',  activity_id: 'A3', activity_name: 'Ducts' },
];

console.log('\nfilterFindings');
test('no filters returns all',    () => assert.equal(filterFindings(F, {}).length, 3));
test('severity filter',           () => assert.equal(filterFindings(F, { severity: 'High' }).length, 1));
test('check filter',              () => assert.equal(filterFindings(F, { check: 'Open Ends' })[0].activity_id, 'A2'));
test('wbs contains',              () => assert.equal(filterFindings(F, { wbs: 'MEP' }).length, 1));
test('query matches id',          () => assert.equal(filterFindings(F, { query: 'a1' }).length, 1));
test('query matches name ci',     () => assert.equal(filterFindings(F, { query: 'steel' })[0].activity_id, 'A2'));
test('combined filters AND',      () => assert.equal(filterFindings(F, { severity: 'High', query: 'zzz' }).length, 0));

console.log('\narea filter (clickable score cards)');
test('areaOf float',   () => assert.equal(areaOf({ check_id: 'FLOAT-001' }), 'Float Analysis'));
test('areaOf logic',   () => assert.equal(areaOf({ check_id: 'LOGIC-002' }), 'Schedule Logic'));
test('areaOf unknown', () => assert.equal(areaOf({ check_id: 'XYZ' }), ''));
test('area = Float Analysis keeps only float', () => {
  const r = filterFindings(F, { area: 'Float Analysis' });
  assert.equal(r.length, 1);
  assert.equal(r[0].activity_id, 'A3');
});
test('area = Schedule Logic keeps the 2 logic findings', () =>
  assert.equal(filterFindings(F, { area: 'Schedule Logic' }).length, 2));

console.log('\nseverityClass / scoreColor / gauge / uniqueValues');
test('sev crit',        () => assert.equal(severityClass('Critical'), 't-crit'));
test('sev unknown → low', () => assert.equal(severityClass('???'), 't-low'));
test('score green',     () => assert.equal(scoreColor(90), 'color-green'));
test('score amber',     () => assert.equal(scoreColor(70), 'color-amber'));
test('score red',       () => assert.equal(scoreColor(40), 'color-red'));
test('gauge full at 0',  () => assert.equal(gaugeDashoffset(0, 100), 100));
test('gauge empty at 100', () => assert.equal(gaugeDashoffset(100, 100), 0));

console.log('\nFloat Health gauge (barPct + colour boundaries)');
test('barPct caps at 100',    () => assert.equal(barPct(21.6, 20), 100));
test('barPct proportional',   () => assert.equal(barPct(1.2, 5), 24));
test('barPct zero',           () => assert.equal(barPct(0, 10), 0));
test('barPct guards max=0',   () => assert.equal(barPct(5, 0), 100));
test('fh colour 85 → green',  () => assert.equal(scoreColor(85), 'color-green'));
test('fh colour 60 → amber',  () => assert.equal(scoreColor(60), 'color-amber'));
test('fh colour 59 → red',    () => assert.equal(scoreColor(59), 'color-red'));
test('unique checks sorted', () => assert.deepEqual(uniqueValues(F, 'check_name'),
     ['Circular Logic', 'Float Analysis', 'Open Ends']));

console.log('\nshortWbs / gradeClass (V2)');
test('shortWbs keeps last 3',   () => assert.equal(shortWbs('A > B > C > D > E'), 'C > D > E'));
test('shortWbs short path',     () => assert.equal(shortWbs('Only > Two'), 'Only > Two'));
test('shortWbs empty',          () => assert.equal(shortWbs(''), ''));
test('gradeClass excellent',    () => assert.equal(gradeClass('Excellent'), 'g-exc'));
test('gradeClass critical',     () => assert.equal(gradeClass('Critical'), 'g-crit'));
test('gradeClass needs',        () => assert.equal(gradeClass('Needs Attention'), 'g-need'));

console.log('\nOut of Sequence review-log cells');
test('pill change',        () => assert.equal(oosPillClass('change'), 'change'));
test('pill remove',        () => assert.equal(oosPillClass('remove'), 'remove'));
test('pill same → same',   () => assert.equal(oosPillClass('same'), 'same'));
test('pill na → na',       () => assert.equal(oosPillClass('na'), 'na'));
test('pill unknown → change', () => assert.equal(oosPillClass('???'), 'change'));
test('crit label',         () => assert.equal(oosCritLabel('Critical'), 'Critical'));
test('near label',         () => assert.equal(oosCritLabel('Near-Critical'), 'Near-Critical'));
test('normal label dash',  () => assert.equal(oosCritLabel(''), '—'));

console.log('\nSchedule Health Review — rail + roll-up helpers (Slice 3)');
test('tabScore shows score',        () => assert.equal(tabScore({ score: 84.6 }), 84.6));
test('tabScore null → dash',        () => assert.equal(tabScore({ score: null }), '—'));
test('tabScore undefined → dash',   () => assert.equal(tabScore({}), '—'));
test('statusColor pass → success',  () => assert.equal(statusColor('Pass'), 'var(--success)'));
test('statusColor review → warning', () => assert.equal(statusColor('Review'), 'var(--warning)'));
test('statusColor critical → danger', () => assert.equal(statusColor('Critical'), 'var(--danger)'));
test('statusColor other → muted',   () => assert.equal(statusColor('Not computed'), 'var(--muted)'));
test('statusDot pass → d-g',        () => assert.equal(statusDot('Pass'), 'd-g'));
test('statusDot review → d-a',      () => assert.equal(statusDot('Review'), 'd-a'));
test('statusDot critical → d-c',    () => assert.equal(statusDot('Critical'), 'd-c'));
test('statusDot other → d-n',       () => assert.equal(statusDot('Not computed'), 'd-n'));
test('verdictClass ready → good',   () => assert.equal(verdictClass('Ready to submit'), 'v-good'));
test('verdictClass conditional → warn', () => assert.equal(verdictClass('Conditional pass'), 'v-warn'));
test('verdictClass not-ready → bad', () => assert.equal(verdictClass('Not ready to submit'), 'v-bad'));
test('verdictClass blocked → bad',  () => assert.equal(verdictClass('Blocked'), 'v-bad'));

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
