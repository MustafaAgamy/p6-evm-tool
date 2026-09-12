/**
 * Unit tests for the pure helpers in ui/modules/audit.js
 * Run: node tests/js/test_audit.js
 */
import assert from 'node:assert/strict';
import { filterFindings, severityClass, scoreColor, gaugeDashoffset, uniqueValues, areaOf, shortWbs, gradeClass,
         oosPillClass, oosCritLabel, barPct, tabScore, statusColor, statusDot, verdictClass,
         oosLagLabel, oosRelLabel, oosDefaultOp, oosOpSummary, oosHasFix, oosBulkOutcome,
         dngDefaultOp, dngHasFix, dngResolvedActs, dngMergeOps, dngCompletionMilestone,
         lagQuickPickValues, normalizeColumnFilter, matchesColumnFilter, filterLagFindings, sortLagFindings,
         LAG_FILTER_COLUMNS }
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

// ── OOS Resolve & Correct helpers ─────────────────────────────────────────
test('lag label zero → empty',   () => assert.equal(oosLagLabel(0), ''));
test('lag label positive',       () => assert.equal(oosLagLabel(3), '(+3d)'));
test('lag label negative',       () => assert.equal(oosLagLabel(-2), '(−2d)'));
test('rel label no lag',         () => assert.equal(oosRelLabel('FS', 0), 'FS'));
test('rel label with lag',       () => assert.equal(oosRelLabel('SS', 3), 'SS(+3d)'));
test('rel label empty rel',      () => assert.equal(oosRelLabel('', 0), ''));
test('default op maps fields', () => {
  const f = { finding_id: 'abc', pred_id: 'P1', activity_id: 'S1',
    resolution: { action: 'change', new_type: 'SS', new_lag_days: 3, new_pred_id: 'P1' } };
  const op = oosDefaultOp(f);
  assert.equal(op.finding_id, 'abc');
  assert.equal(op.pred_id, 'P1');
  assert.equal(op.succ_id, 'S1');
  assert.equal(op.action, 'change');
  assert.equal(op.new_type, 'SS');
  assert.equal(op.new_lag_days, 3);
});
test('op summary change', () => assert.equal(
  oosOpSummary({ action: 'change', pred_id: 'P1', succ_id: 'S1', new_type: 'SS', new_lag_days: 3 }),
  'Changed P1 → S1 to SS(+3d)'));
test('op summary remove', () => assert.equal(
  oosOpSummary({ action: 'remove', pred_id: 'P1', succ_id: 'S1' }),
  'Removed link P1 → S1'));

console.log('\nApply all — which findings have a recommended fix (oosHasFix)');
test('change on pred is a fix',   () => assert.equal(oosHasFix({ resolution: { action: 'change' } }), true));
test('remove on pred is a fix',   () => assert.equal(oosHasFix({ resolution: { action: 'remove' } }), true));
test('replace on pred is a fix',  () => assert.equal(oosHasFix({ resolution: { action: 'replace' } }), true));
test('manual review is NOT a fix',() => assert.equal(oosHasFix({ resolution: { action: 'manual', applicable: false } }), false));
test('data error is NOT a fix',   () => assert.equal(oosHasFix({ resolution: { action: 'data' } }), false));
test('no resolution is NOT a fix',() => assert.equal(oosHasFix({}), false));
test('pred_resolution overrides resolution', () => assert.equal(
  oosHasFix({ resolution: { action: 'manual' }, pred_resolution: { action: 'change' } }), true));
test('succ tie fix counts when pred needs review', () => assert.equal(
  oosHasFix({ resolution: { action: 'manual' }, succ_id: 'S1', succ_resolution: { action: 'change' } }), true));
test('succ fix ignored without succ_id', () => assert.equal(
  oosHasFix({ resolution: { action: 'manual' }, succ_resolution: { action: 'change' } }), false));

console.log('\nApply all — honest outcome counts (oosBulkOutcome)');
test('all applied cleared', () => {
  const o = oosBulkOutcome(['a', 'b', 'c'], []);            // none still open
  assert.equal(o.applied, 3); assert.equal(o.resolved, 3); assert.equal(o.notCleared, 0);
});
test('some applied did not clear', () => {
  const o = oosBulkOutcome(['a', 'b', 'c'], [{ finding_id: 'b' }]);   // b still out of sequence
  assert.equal(o.applied, 3); assert.equal(o.resolved, 2); assert.equal(o.notCleared, 1);
});
test('none cleared', () => {
  const o = oosBulkOutcome(['a', 'b'], [{ finding_id: 'a' }, { finding_id: 'b' }]);
  assert.equal(o.resolved, 0); assert.equal(o.notCleared, 2);
});
test('ignores untouched findings still open', () => {
  const o = oosBulkOutcome(['a'], [{ finding_id: 'z' }]);   // z was not applied by this bulk run
  assert.equal(o.applied, 1); assert.equal(o.resolved, 1); assert.equal(o.notCleared, 0);
});
test('empty touched is zero', () => {
  const o = oosBulkOutcome([], [{ finding_id: 'x' }]);
  assert.equal(o.applied, 0); assert.equal(o.resolved, 0); assert.equal(o.notCleared, 0);
});

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

console.log('\nLag Report — Excel-style column filters');
const LAG_VALUES = [10, -5, 20, 1, -20, 3];
test('quickpick all returns everything',   () => assert.deepEqual(lagQuickPickValues(LAG_VALUES, 'all'), LAG_VALUES));
test('quickpick ge2 by magnitude',         () => assert.deepEqual(lagQuickPickValues(LAG_VALUES, 'ge2'), [10, -5, 20, -20, 3]));
test('quickpick ge5 by magnitude',         () => assert.deepEqual(lagQuickPickValues(LAG_VALUES, 'ge5'), [10, -5, 20, -20]));
test('quickpick long is value > 14, not a lead', () => assert.deepEqual(lagQuickPickValues(LAG_VALUES, 'long'), [20]));
test('quickpick leads is value < 0',       () => assert.deepEqual(lagQuickPickValues(LAG_VALUES, 'leads'), [-5, -20]));
test('quickpick custom threshold by magnitude', () => assert.deepEqual(lagQuickPickValues(LAG_VALUES, 'custom', 8), [10, 20, -20]));
test('quickpick custom NaN falls back to all',  () => assert.deepEqual(lagQuickPickValues(LAG_VALUES, 'custom', 'nope'), LAG_VALUES));
test('quickpick unknown pick falls back to all', () => assert.deepEqual(lagQuickPickValues(LAG_VALUES, 'bogus'), LAG_VALUES));

test('normalize: all selected -> null (no filter)', () => assert.equal(normalizeColumnFilter(['a', 'b'], ['a', 'b']), null));
test('normalize: subset selected -> Set',  () => assert.deepEqual([...normalizeColumnFilter(['a'], ['a', 'b'])], ['a']));
test('normalize: null selection -> null',  () => assert.equal(normalizeColumnFilter(null, ['a', 'b']), null));
test('normalize: empty selection -> empty Set (matches nothing)', () => assert.equal(normalizeColumnFilter([], ['a', 'b']).size, 0));

test('matchesColumnFilter: no filter always matches', () => assert.equal(matchesColumnFilter('x', null), true));
test('matchesColumnFilter: value in set',  () => assert.equal(matchesColumnFilter('x', new Set(['x', 'y'])), true));
test('matchesColumnFilter: value not in set', () => assert.equal(matchesColumnFilter('z', new Set(['x', 'y'])), false));

test('LAG_FILTER_COLUMNS covers the 5 filterable columns', () =>
  assert.deepEqual(LAG_FILTER_COLUMNS.map(c => c.key),
    ['activity_id', 'activity_name', 'lag_days', 'pred_rel_type', 'pred_name']));

const LAG_F = [
  { activity_id: 'A1', activity_name: 'Excavate',      pred_name: 'Site Clear',    rel_type: 'FS', lag_days: 10,  rel_key: 'k1' },
  { activity_id: 'A2', activity_name: 'Backfill',       pred_name: 'Excavate',      rel_type: 'FS', lag_days: -5,  rel_key: 'k2' },
  { activity_id: 'A3', activity_name: 'Formwork',       pred_name: 'Backfill',      rel_type: 'SS', lag_days: 20,  rel_key: 'k3' },
  { activity_id: 'A4', activity_name: 'Pour Concrete',  pred_name: 'Formwork',      rel_type: 'FF', lag_days: 1,   rel_key: 'k4' },
  { activity_id: 'A5', activity_name: 'Cure',           pred_name: 'Pour Concrete', rel_type: 'SF', lag_days: -20, rel_key: 'k5' },
];
test('filterLagFindings: no filters returns all',   () => assert.equal(filterLagFindings(LAG_F, {}).length, 5));
test('filterLagFindings: distinct-value column filter (lag_days)', () => {
  const r = filterLagFindings(LAG_F, { cols: { lag_days: new Set([20]) } });
  assert.equal(r.length, 1); assert.equal(r[0].activity_id, 'A3');
});
test('filterLagFindings: rel_type column filter (not the "FS+21" label)', () =>
  assert.equal(filterLagFindings(LAG_F, { cols: { pred_rel_type: new Set(['FS']) } }).length, 2));
test('filterLagFindings: global search matches activity name AND pred name', () =>
  assert.equal(filterLagFindings(LAG_F, { query: 'excavate' }).length, 2));
test('filterLagFindings: column filter AND search combine', () => {
  const r = filterLagFindings(LAG_F, { cols: { pred_rel_type: new Set(['FS']) }, query: 'backfill' });
  assert.equal(r.length, 1); assert.equal(r[0].activity_id, 'A2');
});
test('filterLagFindings: unchecking everything shows nothing', () =>
  assert.equal(filterLagFindings(LAG_F, { cols: { lag_days: new Set() } }).length, 0));

test('sortLagFindings: numeric asc on lag_days (not lexicographic)', () =>
  assert.deepEqual(sortLagFindings(LAG_F, 'lag_days', 'asc').map(f => f.activity_id),
    ['A5', 'A2', 'A4', 'A1', 'A3']));
test('sortLagFindings: numeric desc on lag_days', () =>
  assert.deepEqual(sortLagFindings(LAG_F, 'lag_days', 'desc').map(f => f.activity_id),
    ['A3', 'A1', 'A4', 'A2', 'A5']));
test('sortLagFindings: text column sorts alphabetically', () =>
  assert.deepEqual(sortLagFindings(LAG_F, 'activity_name', 'asc').map(f => f.activity_id),
    ['A2', 'A5', 'A1', 'A3', 'A4']));
test('sortLagFindings: unknown column returns input unchanged', () =>
  assert.deepEqual(sortLagFindings(LAG_F, 'nope', 'asc'), LAG_F));

console.log('\nDangling — Resolve & Correct helpers');
// start side: wrong-type predecessor (FF) → change P→A to the recommended type.
const DF_START = {
  finding_id: 'd1', activity_id: 'A200', start_dangling: true, finish_dangling: false,
  start_fix: { kind: 'change', target_id: 'A100', current_type: 'FF', current_lag_days: 2,
               recommended_type: 'FS', alt_type: 'SS', candidates: [{ id: 'A100', type: 'FF', lag_days: 2 }] },
};
// finish side: wrong-type successor (SS) → change A→S to the recommended type.
const DF_FINISH = {
  finding_id: 'd2', activity_id: 'B', start_dangling: false, finish_dangling: true,
  finish_fix: { kind: 'change', target_id: 'C', current_type: 'SS', current_lag_days: 0,
                recommended_type: 'FS', alt_type: 'FF', candidates: [{ id: 'C', type: 'SS', lag_days: 0 }] },
};
// no predecessor → review; nothing to apply.
const DF_REVIEW = { finding_id: 'd3', activity_id: 'X', start_dangling: true, finish_dangling: false,
  start_fix: { kind: 'review' } };

test('dngDefaultOp start: relationship is predecessor→activity', () => {
  const op = dngDefaultOp(DF_START, 'start');
  assert.equal(op.pred_id, 'A100'); assert.equal(op.succ_id, 'A200');
  assert.equal(op.action, 'change'); assert.equal(op.new_type, 'FS'); assert.equal(op.new_lag_days, 2);
  assert.equal(op.activity_id, 'A200');
});
test('dngDefaultOp finish: relationship is activity→successor', () => {
  const op = dngDefaultOp(DF_FINISH, 'finish');
  assert.equal(op.pred_id, 'B'); assert.equal(op.succ_id, 'C'); assert.equal(op.new_type, 'FS');
});
test('dngDefaultOp review side → null (no op)', () => assert.equal(dngDefaultOp(DF_REVIEW, 'start'), null));
test('dngDefaultOp side that is not dangling → null', () => assert.equal(dngDefaultOp(DF_START, 'finish'), null));

test('dngHasFix true when a change fix exists',  () => assert.equal(dngHasFix(DF_START), true));
test('dngHasFix true for finish change',         () => assert.equal(dngHasFix(DF_FINISH), true));
test('dngHasFix false when only review',         () => assert.equal(dngHasFix(DF_REVIEW), false));
test('dngHasFix false when no fixes at all',     () => assert.equal(dngHasFix({ activity_id: 'Z' }), false));

test('dngResolvedActs = activities gone after re-validation', () => {
  const all = [{ activity_id: 'A' }, { activity_id: 'B' }, { activity_id: 'C' }];
  const fresh = [{ activity_id: 'B' }];                 // A and C cleared
  assert.deepEqual(dngResolvedActs(all, fresh), ['A', 'C']);
});
test('dngResolvedActs: partially-fixed activity (still dangling) is NOT resolved', () => {
  const all = [{ activity_id: 'B' }];
  const fresh = [{ activity_id: 'B' }];                 // B still dangling on another side
  assert.deepEqual(dngResolvedActs(all, fresh), []);
});

console.log('\nDangling — merge applied ops by side (never lose a prior fix)');
const START_OP = { side: 'start', new_type: 'FS' };
const FINISH_OP = { side: 'finish', new_type: 'FS' };
test('merge: a new finish op preserves an earlier start op (the bug fix)', () => {
  // Apply-all on a partly-fixed activity: fresh finding exposes only finish → must keep prior start.
  const merged = dngMergeOps([START_OP], [FINISH_OP], ['finish']);
  assert.equal(merged.length, 2);
  assert.deepEqual(merged.map(o => o.side).sort(), ['finish', 'start']);
});
test('merge: same-side new op overwrites the prior one', () => {
  const merged = dngMergeOps([{ side: 'start', new_type: 'FS' }], [{ side: 'start', new_type: 'SS' }], ['start']);
  assert.equal(merged.length, 1); assert.equal(merged[0].new_type, 'SS');
});
test('merge: an exposed side set to review (no new op) drops its prior op', () => {
  const merged = dngMergeOps([FINISH_OP], [], ['finish']);   // planner chose "leave for review"
  assert.deepEqual(merged, []);
});
test('merge: a side NOT exposed by the current finding keeps its prior op', () => {
  const merged = dngMergeOps([START_OP], [], []);            // start already fixed, not re-exposed
  assert.deepEqual(merged, [START_OP]);
});

console.log('\nDangling — contract completion milestone picker');
test('completion = the matched milestone with the LATEST contract date', () => {
  const ms = [
    { contract_name: 'Commencement', matched_activity_id: 'NTP', contract_date: '5-Jan-2026' },
    { contract_name: 'Practical Completion', matched_activity_id: 'PC', contract_date: '20-Dec-2027' },
    { contract_name: 'Sectional', matched_activity_id: 'SEC', contract_date: '1-Jun-2027' },
  ];
  assert.deepEqual(dngCompletionMilestone(ms), { activity_id: 'PC', contract_date: '20-Dec-2027' });
});
test('completion ignores unmatched milestones', () => {
  const ms = [
    { contract_name: 'X', matched_activity_id: null, contract_date: '20-Dec-2099' },  // unmatched → skip
    { contract_name: 'Completion', matched_activity_id: 'PC', contract_date: '20-Dec-2027' },
  ];
  assert.equal(dngCompletionMilestone(ms).activity_id, 'PC');
});
test('completion null when none entered/matched', () => {
  assert.equal(dngCompletionMilestone([]), null);
  assert.equal(dngCompletionMilestone([{ contract_name: 'X', matched_activity_id: null, contract_date: '1-Jan-2026' }]), null);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
