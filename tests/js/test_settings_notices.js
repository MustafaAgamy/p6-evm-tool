/**
 * Settings screens keep what the planner entered and say plainly when something was not kept
 * (owner comment 31 b):
 *   * AI Chat: an AI brain choice that could not be saved (it would revert on restart) is said
 *     beside the choices — brainChoiceProblem.
 *   * Schedule Health: "Edit contract milestones" pre-fills the saved milestones — from the
 *     saved list, or rebuilt from the evaluations of an older result — msGateRows.
 * Run: node tests/js/test_settings_notices.js
 */
import assert from 'node:assert/strict';
import { brainChoiceProblem } from '../../ui/modules/chat.js';
import { msGateRows } from '../../ui/modules/audit.js';

let passed = 0;
let failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}`); console.error(err); failed++; }
}

test('brain choice saved → no notice', () => {
  assert.equal(brainChoiceProblem({ ok: true, settings: { model_key: 'fast', saved: true } }), '');
  assert.equal(brainChoiceProblem({ ok: true, settings: { model_key: 'fast' } }), '', 'older answer without "saved"');
});

test('brain choice not written → says it will revert on restart', () => {
  const m = brainChoiceProblem({ ok: true, settings: { saved: false, error: 'Your AI brain choice could not be saved on this PC.' } });
  assert.match(m, /could not be saved/);
  assert.match(m, /previous choice when the app restarts/);
});

test('brain choice: app did not answer / refused → not saved, retry', () => {
  assert.match(brainChoiceProblem(null), /not saved.*again/);
  assert.match(brainChoiceProblem({ ok: false, error: 'disk full' }), /not saved — disk full/);
});

test('milestone gate: pre-fills from the saved list', () => {
  const mc = { contract_milestones: [{ name: 'Handover', date: '2027-09-30' }, { name: 'MC', date: '2027-06-30' }] };
  assert.deepEqual(msGateRows(mc), mc.contract_milestones);
});

test('milestone gate: older result without the list → rebuilt from the evaluations (ISO dates)', () => {
  const mc = { milestones: [
    { contract_name: 'Handover', contract_date: '30-Sep-2027' },
    { contract_name: 'Early works', contract_date: '9-Feb-2027' },
    { contract_name: 'No date', contract_date: null },
    { contract_date: '1-Jan-2027' },                              // no name → not a row
  ] };
  assert.deepEqual(msGateRows(mc), [
    { name: 'Handover', date: '2027-09-30' },
    { name: 'Early works', date: '2027-02-09' },
    { name: 'No date', date: '' },
  ]);
});

test('milestone gate: nothing entered yet → no rows (the gate adds one blank row)', () => {
  assert.deepEqual(msGateRows({}), []);
  assert.deepEqual(msGateRows(null), []);
  assert.deepEqual(msGateRows({ contract_milestones: [], milestones: [] }), []);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
