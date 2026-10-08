/**
 * Schedule (Gantt) opens fast on big schedules (owner comment 36 — no freeze on Run):
 * rows are emitted in blocks of GANTT_BLOCK lines, each block carrying its EXACT height
 * (so the scroll height, gridlines and data-date line are unchanged while off-screen
 * blocks are laid out lazily), and the WBS / start ordering is the same as before.
 * Run: node tests/js/test_gantt_blocks.js
 */
import assert from 'node:assert/strict';

const el = { innerHTML: '' };
globalThis.document = { getElementById: (id) => (id === 'schedule-body' ? el : null) };
const { renderSchedule } = await import('../../ui/modules/gantt.js');

let passed = 0, failed = 0;
async function test(name, fn) {
  try { await fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}`); console.error(`    ${err.message}`); failed++; }
}

const day = (n) => new Date(Date.UTC(2026, 0, 1 + n)).toISOString().slice(0, 10);
function acts() {
  const out = [];
  // group B starts earlier than group A → B must come first; rows inside sorted by start
  for (let i = 0; i < 100; i++) out.push({ id: `A${i}`, name: `a${i}`, wbs_top: 'A', start: day(10 + (99 - i)), finish: day(20 + (99 - i)), pct: 0, critical: true, milestone: false });
  for (let i = 0; i < 30; i++) out.push({ id: `B${i}`, name: `b${i}`, wbs_top: 'B', start: day(1 + i), finish: day(5 + i), pct: 50, critical: true, milestone: i === 7 });
  // not critical: the Gantt leaves these out (owner comment 65)
  for (let i = 0; i < 12; i++) out.push({ id: `N${i}`, name: `n${i}`, wbs_top: 'N', start: day(i), finish: day(3 + i), pct: 0, critical: false, milestone: false });
  return out;
}

console.log('Gantt — lazily laid-out row blocks');
await test('blocks carry their exact height; every row and group is present once', () => {
  renderSchedule({ activities: acts(), data_date: day(15), activity_count: 142 });
  const h = el.innerHTML;
  const blocks = [...h.matchAll(/<div class="g-blk" style="contain-intrinsic-size:auto (\d+)px">/g)].map(m => +m[1]);
  const rows = (h.match(/class="g-row"/g) || []).length, grps = (h.match(/class="g-grp"/g) || []).length;
  assert.equal(rows, 130);
  assert.equal(grps, 2);
  assert.equal(blocks.length, Math.ceil(132 / 60));
  assert.equal(blocks.reduce((a, b) => a + b, 0), rows * 38 + grps * 26, 'sum of block heights = laid-out height');
  assert.match(h, /class="g-inner g-lazy"/);
  assert.match(h, /<span>Activity ID<\/span><span>Activity name<\/span><i>Expected Start<\/i><i>Expected Finish<\/i><i>Delay<\/i>/, 'Activity ID has its own column');
  assert.doesNotMatch(h, /<b class="g-id">N\d+<\/b>/, 'non-critical activities are not drawn');
  assert.match(h, /<b>130<\/b> critical construction activities of <b>142<\/b> activities/);
});
await test('groups ordered by earliest start, rows by start (same order as before)', () => {
  const h = el.innerHTML;
  const ids = [...h.matchAll(/<b class="g-id">([AB]\d+)<\/b>/g)].map(m => m[1]);
  assert.equal(ids[0], 'B0');
  assert.equal(ids[29], 'B29');
  assert.equal(ids[30], 'A99');           // A99 has the earliest start in group A
  assert.equal(ids[129], 'A0');
});
await test('an empty schedule still shows the note (no blocks)', () => {
  renderSchedule({ activities: [], activity_count: 0 });
  assert.doesNotMatch(el.innerHTML, /g-blk/);
  assert.match(el.innerHTML, /No activity timeline is available/);
});

await test('a schedule with nothing critical says so', () => {
  renderSchedule({ activities: acts().map((a) => ({ ...a, critical: false })), activity_count: 142 });
  assert.doesNotMatch(el.innerHTML, /g-blk/);
  assert.match(el.innerHTML, /No construction activity of this schedule is critical/);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
