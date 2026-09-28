/** Unit tests for the pure helpers in ui/modules/elog.js — run: node tests/js/test_elog.js */
import assert from 'node:assert/strict';
import {
  sureLevel, setColumnField, setCodeVerdict, firstCheckColumn, codeGroups, previewTotals, readableLayouts, otherSheetNotes,
  openElogConfirm,
} from '../../ui/modules/elog.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

function layout() {
  return {
    fields: [{ key: 'submittal_type', label: 'Submittal type' }, { key: 'trade', label: 'Discipline (trade)' },
      { key: 'ignore', label: 'Ignore' }],
    sheets: [
      { sheet: 'Summary', include: false, kind: 'summary', columns: [] },
      { sheet: 'Civil', include: true, kind: 'register', columns: [
        { index: 4, letter: 'E', header: 'Type', field: 'ignore', confidence: 0.65, level: 'medium' },
        { index: 6, letter: 'G', header: 'Type', field: 'submittal_type', confidence: 0.75, level: 'high' },
        { index: 7, letter: 'H', header: '', field: 'ignore', confidence: 0.35, level: 'check' },
        { index: 10, letter: 'K', header: 'TYPE', field: 'trade', confidence: 0.7, level: 'medium' },
      ] },
    ],
    codes: [{ value: 'B', count: 4, verdict: 'approved' }, { value: 'C', count: 3, verdict: 'not_approved' },
      { value: 'W', count: 1, verdict: 'under_review' }, { value: 'A', count: 0, verdict: 'approved' },
      { value: 'Done', count: 5, verdict: 'ignore' }],
    code_map: { B: 'approved', C: 'not_approved', W: 'under_review', A: 'approved', Done: 'ignore' },
  };
}

console.log('\nsureLevel');
test('0.75 and up is High', () => assert.equal(sureLevel(0.75), 'high'));
test('0.5 to 0.75 is Medium', () => assert.equal(sureLevel(0.6), 'medium'));
test('below 0.5 is Check', () => assert.equal(sureLevel(0.35), 'check'));
test('missing confidence is Check', () => assert.equal(sureLevel(undefined), 'check'));

console.log('\nsetColumnField');
test('one column per meaning — the other Type is freed', () => {
  const l = setColumnField(layout(), 'Civil', 4, 'submittal_type');
  const cols = l.sheets[1].columns;
  assert.equal(cols[0].field, 'submittal_type');
  assert.equal(cols[0].level, 'high');
  assert.equal(cols[1].field, 'ignore');
  assert.match(cols[1].reason, /column E for Submittal type/);
  assert.equal(cols[3].field, 'trade');                   // untouched
});
test('Ignore never frees other columns', () => {
  const l = setColumnField(layout(), 'Civil', 6, 'ignore');
  assert.equal(l.sheets[1].columns[3].field, 'trade');
  assert.equal(l.sheets[1].columns[1].field, 'ignore');
});
test('unknown sheet / column leaves the layout as it was', () => {
  const before = JSON.stringify(layout());
  assert.equal(JSON.stringify(setColumnField(layout(), 'Nope', 4, 'trade')), before);
  assert.equal(JSON.stringify(setColumnField(layout(), 'Civil', 99, 'trade')), before);
});

console.log('\nsetCodeVerdict');
test('a code can be re-mapped (Done → Approved)', () => {
  const l = setCodeVerdict(layout(), 'Done', 'approved');
  assert.equal(l.code_map.Done, 'approved');
  assert.equal(l.codes.find((c) => c.value === 'Done').verdict, 'approved');
});
test('an unknown verdict is refused', () => {
  const l = setCodeVerdict(layout(), 'B', 'maybe');
  assert.equal(l.code_map.B, 'approved');
});

console.log('\nfirstCheckColumn');
test('the first Check column of a counted sheet', () =>
  assert.deepEqual(firstCheckColumn(layout()), { sheet: 'Civil', index: 7 }));
test('then the first Medium one', () => {
  const l = layout();
  l.sheets[1].columns[2].level = 'high';
  assert.deepEqual(firstCheckColumn(l), { sheet: 'Civil', index: 4 });
});
test('columns the planner already set are skipped', () => {
  const l = setColumnField(layout(), 'Civil', 7, 'ignore');
  assert.deepEqual(firstCheckColumn(l), { sheet: 'Civil', index: 4 });
});
test('no counted sheet → null', () => {
  const l = layout();
  l.sheets[1].include = false;
  assert.equal(firstCheckColumn(l), null);
});

console.log('\ncodeGroups');
test('codes grouped by meaning, most used first', () => {
  const g = codeGroups(layout().codes);
  assert.deepEqual(g.approved.map((c) => c.value), ['B', 'A']);
  assert.deepEqual(g.not_approved.map((c) => c.value), ['C']);
  assert.deepEqual(g.under_review.map((c) => c.value), ['W']);
  assert.deepEqual(g.ignore.map((c) => c.value), ['Done']);
});

console.log('\npreviewTotals');
test('totals follow the owner\'s % rules', () => {
  const t = previewTotals([
    { trade: 'Civil', req: 6, submitted_rows: 6, approved_rows: 3, not_approved_rows: 1, under_review_rows: 2 },
    { trade: 'Steel', req: 2, submitted_rows: 1, approved_rows: 1, not_approved_rows: 0, under_review_rows: 0 },
  ]);
  assert.equal(t.req, 8);
  assert.equal(t.approved_pct, 50);                    // 4 / 8
  assert.equal(t.submitted_pct, 75);                   // (7 − 1) / 8
});
test('empty preview → zeros, no division by zero', () => assert.equal(previewTotals([]).approved_pct, 0));

console.log('\nreadableLayouts');
test('files that failed to open are left out', () => {
  const ok = { path: 'C:/a.xlsx', sheets: [{ sheet: 'Civil' }] };
  const out = readableLayouts([ok, { path: 'C:/b.xls', error: 'old xls' }, { path: 'C:/c.xlsx', sheets: [] }]);
  assert.deepEqual(Object.keys(out), ['C:/a.xlsx']);
});

test('otherSheetNotes: other counted sheets\' notes carry their sheet name; auto-off registers listed', () => {
  const lay = { sheets: [
    { sheet: 'O&M LOG', include: true, kind: 'register', warnings: ['open-tab note'] },
    { sheet: 'Civil', include: true, kind: 'register', warnings: ['2 row(s) have no drawing number'] },
    { sheet: 'SPARE PARTS LOG', include: false, kind: 'register', auto_off: 'untracked', warnings: [] },
    { sheet: 'Summary', include: false, kind: 'summary', warnings: ['ignored'] },
  ] };
  const out = otherSheetNotes(lay, 'O&M LOG');
  assert.deepEqual(out.notes, ['Civil: 2 row(s) have no drawing number']);
  assert.deepEqual(out.switchedOff, ['SPARE PARTS LOG']);
  assert.deepEqual(otherSheetNotes(null, 'x'), { notes: [], switchedOff: [] });
});

// ── ELOG-8: a preview still running when Confirm/Cancel is clicked must not bring the panel back ──
function fakeHost() {
  const stubs = {};
  const stub = () => ({ handlers: {}, dataset: {}, classList: { add() {} }, disabled: false,
    addEventListener(t, fn) { this.handlers[t] = fn; }, focus() {}, scrollIntoView() {} });
  return {
    html: '', renders: 0, stubs,
    set innerHTML(v) { this.html = v; if (v.includes('id="elog-panel"')) this.renders++; else for (const k in stubs) delete stubs[k]; },
    get innerHTML() { return this.html; },
    querySelector(sel) {
      if (!this.html.includes('id="elog-panel"')) return null;
      return (stubs[sel] = stubs[sel] || stub());
    },
    querySelectorAll() { return []; },
    contains() { return false; },
  };
}
async function lateAfterClose(button) {
  globalThis.document = { activeElement: null };
  let release;
  globalThis.fetch = () => new Promise((res) => { release = () => res({ json: async () => ({ ok: true, layout: { ...layout(), path: 'x.xlsx' } }) }); });
  const host = fakeHost();
  const close = async () => { host.innerHTML = '<div id="e1-results">counted</div>'; };
  const panel = openElogConfirm(host, [{ ...layout(), path: 'x.xlsx' }], { port: 1, onConfirm: close, onCancel: close });
  const pending = panel.refresh();                         // preview request in flight
  await host.stubs[button].handlers.click();               // Confirm/Cancel closes the panel
  release(); await pending;                                // …then the old preview answers
  return host;
}
for (const button of ['#elog-confirm', '#elog-cancel']) {
  try {
    const host = await lateAfterClose(button);
    assert.equal(host.innerHTML, '<div id="e1-results">counted</div>');
    assert.equal(host.renders, 1);
    console.log(`  ✓ a late preview after ${button} does not redraw the closed panel`); passed++;
  } catch (e) { console.error(`  ✗ a late preview after ${button} does not redraw the closed panel\n    ${e.message}`); failed++; }
}

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
