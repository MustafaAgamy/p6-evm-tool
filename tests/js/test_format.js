/**
 * Unit tests for ui/modules/format.js
 * Run: node tests/js/test_format.js
 */
import assert from 'node:assert/strict';
import { fmtEGP, fmtDate, kpiColor } from '../../ui/modules/format.js';

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (err) {
    console.error(`  ✗ ${name}`);
    console.error(`    ${err.message}`);
    failed++;
  }
}

// ── fmtEGP ────────────────────────────────────────────────────────────────
console.log('\nfmtEGP');

test('null returns em-dash',      () => assert.equal(fmtEGP(null), '—'));
test('undefined returns em-dash', () => assert.equal(fmtEGP(undefined), '—'));
test('zero',                      () => assert.equal(fmtEGP(0), 'EGP 0'));
test('small number has EGP prefix', () => assert.match(fmtEGP(1500), /^EGP /));
test('small number no M/B suffix',  () => assert.doesNotMatch(fmtEGP(999999), /[MB]$/));
test('millions → M suffix',       () => assert.match(fmtEGP(2_500_000), /EGP 2\.5M/));
test('millions one decimal place',() => assert.match(fmtEGP(1_100_000), /EGP 1\.1M/));
test('billions → B suffix',       () => assert.match(fmtEGP(3_200_000_000), /EGP 3\.20B/));
test('billions two decimal places',() => assert.match(fmtEGP(1_000_000_000), /EGP 1\.00B/));
test('negative millions',         () => assert.match(fmtEGP(-1_500_000), /EGP -1\.5M/));
test('negative billions',         () => assert.match(fmtEGP(-2_000_000_000), /EGP -2\.00B/));
test('just at billion threshold', () => assert.match(fmtEGP(1_000_000_000), /B$/));
test('just below billion → M',    () => assert.match(fmtEGP(999_999_999), /M$/));
test('just at million threshold', () => assert.match(fmtEGP(1_000_000), /M$/));
test('just below million → no suffix', () => assert.doesNotMatch(fmtEGP(999_999), /[MB]$/));

// ── fmtDate ───────────────────────────────────────────────────────────────
console.log('\nfmtDate');

test('null returns em-dash',         () => assert.equal(fmtDate(null), '—'));
test('undefined returns em-dash',    () => assert.equal(fmtDate(undefined), '—'));
test('empty string returns em-dash', () => assert.equal(fmtDate(''), '—'));
test('valid ISO contains year 2024', () => assert.match(fmtDate('2024-07-01'), /2024/));
test('valid ISO contains Jul',       () => assert.match(fmtDate('2024-07-01'), /Jul/));
test('valid ISO is not em-dash',     () => assert.notEqual(fmtDate('2024-07-01'), '—'));
test('invalid string returned as-is',() => assert.equal(fmtDate('not-a-date'), 'not-a-date'));
test('random text returned as-is',   () => assert.equal(fmtDate('hello'), 'hello'));

// ── kpiColor ──────────────────────────────────────────────────────────────
console.log('\nkpiColor');

test('null → color-neutral',             () => assert.equal(kpiColor(null, 'delay'), 'color-neutral'));
test('undefined → color-neutral',        () => assert.equal(kpiColor(undefined, 'index'), 'color-neutral'));
test('delay positive → color-red',       () => assert.equal(kpiColor(5, 'delay'), 'color-red'));
test('delay 1 → color-red',             () => assert.equal(kpiColor(1, 'delay'), 'color-red'));
test('delay zero → color-green',         () => assert.equal(kpiColor(0, 'delay'), 'color-green'));
test('delay negative → color-green',     () => assert.equal(kpiColor(-3, 'delay'), 'color-green'));
test('index < 0.85 → color-red',         () => assert.equal(kpiColor(0.8, 'index'), 'color-red'));
test('index 0.0 → color-red',           () => assert.equal(kpiColor(0.0, 'index'), 'color-red'));
test('index exactly 0.85 → color-amber',() => assert.equal(kpiColor(0.85, 'index'), 'color-amber'));
test('index 0.9 → color-amber',          () => assert.equal(kpiColor(0.9, 'index'), 'color-amber'));
test('index 0.99 → color-amber',         () => assert.equal(kpiColor(0.99, 'index'), 'color-amber'));
test('index exactly 1.0 → color-green', () => assert.equal(kpiColor(1.0, 'index'), 'color-green'));
test('index 1.1 → color-green',          () => assert.equal(kpiColor(1.1, 'index'), 'color-green'));
test('index 1.5 → color-green',          () => assert.equal(kpiColor(1.5, 'index'), 'color-green'));
test('unknown type → color-neutral',     () => assert.equal(kpiColor(5, 'unknown'), 'color-neutral'));

// ── Summary ────────────────────────────────────────────────────────────────
console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
