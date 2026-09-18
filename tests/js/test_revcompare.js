/**
 * Unit tests for the pure helpers in ui/modules/revcompare.js
 * Run: node tests/js/test_revcompare.js
 */
import assert from 'node:assert/strict';
import { bucketOf, num, deltaCell } from '../../ui/modules/revcompare.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

console.log('\nbucketOf');
test('added rolls up to scope',    () => assert.equal(bucketOf('added'), 'scope'));
test('removed rolls up to scope',  () => assert.equal(bucketOf('removed'), 'scope'));
test('idchange → identity',        () => assert.equal(bucketOf('idchange'), 'identity'));
test('moved_wbs → wbs',            () => assert.equal(bucketOf('moved_wbs'), 'wbs'));
test('logic stays logic',          () => assert.equal(bucketOf('logic'), 'logic'));

console.log('\nnum');
test('null → em dash',             () => assert.equal(num(null), '—'));
test('positive with sign',         () => assert.equal(num(5, true), '+5'));
test('positive without sign',      () => assert.equal(num(5), '5'));
test('negative keeps its sign',    () => assert.equal(num(-3, true), '-3'));
test('zero with sign flag',        () => assert.equal(num(0, true), '0'));

console.log('\ndeltaCell');
test('null → zero class, em dash', () => { const s = deltaCell(null); assert.ok(s.includes('zero') && s.includes('—')); });
test('positive → up class + sign', () => { const s = deltaCell(5); assert.ok(s.includes('rc-d up') && s.includes('+5')); });
test('negative → down class',      () => { const s = deltaCell(-2); assert.ok(s.includes('rc-d down') && s.includes('-2')); });
test('zero → zero class',          () => { const s = deltaCell(0); assert.ok(s.includes('zero')); });
test('string passes through',      () => { const s = deltaCell('CP +47 d'); assert.ok(s.includes('CP +47 d')); });

console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
