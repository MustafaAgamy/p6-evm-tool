/**
 * Unit tests for the pure helpers in ui/modules/audit.js
 * Run: node tests/js/test_audit.js
 */
import assert from 'node:assert/strict';
import { filterFindings, severityClass, scoreColor, gaugeDashoffset, uniqueValues }
  from '../../ui/modules/audit.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

const F = [
  { severity: 'Critical', check_name: 'Circular Logic', wbs_path: 'T > Sub',  activity_id: 'A1', activity_name: 'Loop' },
  { severity: 'High',     check_name: 'Open Ends',      wbs_path: 'T > Roof', activity_id: 'A2', activity_name: 'Steel' },
  { severity: 'Medium',   check_name: 'Float Analysis', wbs_path: 'T > MEP',  activity_id: 'A3', activity_name: 'Ducts' },
];

console.log('\nfilterFindings');
test('no filters returns all',    () => assert.equal(filterFindings(F, {}).length, 3));
test('severity filter',           () => assert.equal(filterFindings(F, { severity: 'High' }).length, 1));
test('check filter',              () => assert.equal(filterFindings(F, { check: 'Open Ends' })[0].activity_id, 'A2'));
test('wbs contains',              () => assert.equal(filterFindings(F, { wbs: 'MEP' }).length, 1));
test('query matches id',          () => assert.equal(filterFindings(F, { query: 'a1' }).length, 1));
test('query matches name ci',     () => assert.equal(filterFindings(F, { query: 'steel' })[0].activity_id, 'A2'));
test('combined filters AND',      () => assert.equal(filterFindings(F, { severity: 'High', query: 'zzz' }).length, 0));

console.log('\nseverityClass / scoreColor / gauge / uniqueValues');
test('sev crit',        () => assert.equal(severityClass('Critical'), 't-crit'));
test('sev unknown → low', () => assert.equal(severityClass('???'), 't-low'));
test('score green',     () => assert.equal(scoreColor(90), 'color-green'));
test('score amber',     () => assert.equal(scoreColor(70), 'color-amber'));
test('score red',       () => assert.equal(scoreColor(40), 'color-red'));
test('gauge full at 0',  () => assert.equal(gaugeDashoffset(0, 100), 100));
test('gauge empty at 100', () => assert.equal(gaugeDashoffset(100, 100), 0));
test('unique checks sorted', () => assert.deepEqual(uniqueValues(F, 'check_name'),
     ['Circular Logic', 'Float Analysis', 'Open Ends']));

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
