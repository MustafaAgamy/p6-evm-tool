/**
 * Unit tests for the pure helpers in ui/modules/calendar.js
 * Run: node tests/js/test_calendar.js
 */
import assert from 'node:assert/strict';
import { fmtCalDate, statusClass, monthGridCells, conflictSeverityClass,
         SITE_TYPES, SITE_TYPE_ORDER, matchSiteType, buildSiteCriteria, histBarGeom,
         hist3Geom }
  from '../../ui/modules/calendar.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

console.log('\nfmtCalDate');
test('formats an ISO date',        () => assert.equal(fmtCalDate('2025-01-05'), '05 Jan 2025'));
test('null -> dash',               () => assert.equal(fmtCalDate(null), '—'));
test('garbage -> dash',            () => assert.equal(fmtCalDate('not-a-date'), '—'));

console.log('\nstatusClass');
test('work',      () => assert.equal(statusClass('work'), 'cs-work'));
test('shutdown',  () => assert.equal(statusClass('shutdown'), 'cs-shutdown'));
test('unknown -> work', () => assert.equal(statusClass('???'), 'cs-work'));

console.log('\nmonthGridCells');
test('pads leading blanks by weekday', () => {
  const m = { first_weekday: 2, days: [{ d: 1, status: 'work' }, { d: 2, status: 'weekend' }] };
  const cells = monthGridCells(m);
  assert.equal(cells.length, 4);            // 2 blanks + 2 days
  assert.equal(cells[0].blank, true);
  assert.equal(cells[1].blank, true);
  assert.equal(cells[2].d, 1);
  assert.equal(cells[2].status, 'work');
});
test('no pad when weekday 0', () => {
  const cells = monthGridCells({ first_weekday: 0, days: [{ d: 1, status: 'work' }] });
  assert.equal(cells.length, 1);
  assert.equal(cells[0].d, 1);
});
test('empty days -> only blanks', () => {
  const cells = monthGridCells({ first_weekday: 3, days: [] });
  assert.equal(cells.length, 3);
  assert.ok(cells.every(c => c.blank));
});

console.log('\nconflictSeverityClass');
test('High',  () => assert.equal(conflictSeverityClass('High'), 'cf-high'));
test('Low default', () => assert.equal(conflictSeverityClass('???'), 'cf-low'));

console.log('\nSITE_TYPES (must mirror weather.py)');
test('desert equals the app default limits', () =>
  assert.deepEqual(SITE_TYPES.desert.thresholds, { rain_mm: 5, temp_max_c: 42, wind_kmh: null, dust: true }));
test('marine turns wind on at 35, heat 40', () => {
  assert.equal(SITE_TYPES.marine.thresholds.wind_kmh, 35);
  assert.equal(SITE_TYPES.marine.thresholds.temp_max_c, 40);
});
test('order lists the four presets', () =>
  assert.deepEqual(SITE_TYPE_ORDER, ['marine', 'desert', 'coastal', 'building']));

console.log('\nmatchSiteType');
test('desert preset limits → desert', () =>
  assert.equal(matchSiteType({ rain_mm: 5, temp_max_c: 42, wind_kmh: null, dust: true }), 'desert'));
test('marine preset limits → marine', () =>
  assert.equal(matchSiteType({ ...SITE_TYPES.marine.thresholds }), 'marine'));
test('edited limits → null (Custom)', () =>
  assert.equal(matchSiteType({ rain_mm: 3, temp_max_c: 38, wind_kmh: 30, dust: true }), null));

console.log('\nbuildSiteCriteria');
test('wind first, marine framing, on-state', () => {
  const rows = buildSiteCriteria('marine', SITE_TYPES.marine.thresholds);
  assert.deepEqual(rows.map(r => r.key), ['wind', 'heat', 'rain', 'dust']);
  assert.equal(rows[0].on, true);
  assert.match(rows[0].value, /35/);
  assert.match(rows[0].explain.toLowerCase(), /marine|crane/);
});
test('wind off shown as off / not counted', () => {
  const wind = buildSiteCriteria('desert', SITE_TYPES.desert.thresholds)[0];
  assert.equal(wind.on, false);
  assert.equal(wind.value, 'off');
});

console.log('\nhistBarGeom (Calendar Timeline histogram — Feature 1 §2)');
test('tallest month scales to ~100px; column split into working + non-working', () => {
  const g = histBarGeom([
    { label: 'Jan', working_days: 20, nonworking_days: 11 },   // 31 total → tallest
    { label: 'Feb', working_days: 18, nonworking_days: 10 },   // 28 total → shorter
  ]);
  assert.equal(g.length, 2);
  assert.equal(g[0].totPx, 100);                    // the tallest month fills the axis
  assert.equal(g[0].wd, 20);                        // the number above the bar = net working days
  assert.equal(g[0].nwPx + g[0].wPx, g[0].totPx);   // the two segments fill the column exactly
  assert.ok(g[1].totPx < g[0].totPx);               // a shorter month is a shorter bar
});
test('empty months → no bars', () => assert.deepEqual(histBarGeom([]), []));
test('a zero-day month → flat bar, no NaN', () => {
  const g = histBarGeom([{ label: 'X', working_days: 0, nonworking_days: 0 }])[0];
  assert.equal(g.totPx, 0); assert.equal(g.nwPx, 0); assert.equal(g.wPx, 0);
});

console.log('\nhist3Geom (Feature 2 — Bad Weather 3-colour histogram)');
test('tallest month (net+bad+nonworking) fills ~H; segments scale to it', () => {
  const g = hist3Geom([
    { label: 'Jan 26', net: 20, bad: 3, nonworking: 8 },   // 31 total → tallest
    { label: 'Feb 26', net: 18, bad: 1, nonworking: 8 },   // 27 total → shorter
  ], 100);
  assert.equal(g.length, 2);
  const tall = g[0].netPx + g[0].badPx + g[0].nwPx;
  const short = g[1].netPx + g[1].badPx + g[1].nwPx;
  assert.ok(Math.abs(tall - 100) <= 2, `tallest stack ~fills the axis (got ${tall})`);  // ±rounding
  assert.equal(g[0].net, 20);                               // net working days carried through (label above bar)
  assert.ok(short < tall);                                  // a shorter month is a shorter stack
});
test('empty histogram → no bars', () => assert.deepEqual(hist3Geom([]), []));
test('missing fields default to 0 (no NaN)', () => {
  const g = hist3Geom([{ label: 'X' }])[0];
  assert.equal(g.net, 0); assert.equal(g.bad, 0); assert.equal(g.nonworking, 0);
  assert.equal(g.netPx, 0); assert.equal(g.badPx, 0); assert.equal(g.nwPx, 0);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
