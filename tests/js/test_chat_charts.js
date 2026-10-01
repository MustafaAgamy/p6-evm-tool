/**
 * AI Chat — charts inside the answers (owner comment 33) and the dashboard chart fixes.
 * ui/modules/chat.js: chartHtml / chartsHtml / answerV2Html / scurveTicks.
 * Run: node tests/js/test_chat_charts.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chartHtml, chartsHtml, answerV2Html, scurveTicks } from '../../ui/modules/chat.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'ui', 'modules', 'chat.js'), 'utf8');

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}
const count = (s, re) => (s.match(re) || []).length;
const widths = (h) => [...h.matchAll(/style="width:([\d.]+)%"/g)].map((m) => Number(m[1]));

const KPI = { type: 'kpi', title: 'Where the project stands', items: [
  { label: 'SPI', value: '0.66', tone: 'bad', hint: 'work done ÷ work planned' },
  { label: 'Finish', value: '60 days late', tone: 'weird', hint: '' }] };
const BARS = { type: 'bars', title: 'Progress by discipline', legend: 'solid = done · light = planned (%)', items: [
  { name: 'Construction Works', planned: 61, actual: 40 }, { name: 'Design <b>', planned: 140, actual: -5 }] };
const PAIRS = { type: 'pairs', title: 'Value of work', legend: ['planned by the data date', 'done'], unit: "the schedule's own cost unit", items: [
  { name: 'Civil Works', a: 560, b: 369.5, la: '560.3 million', lb: '369.5 million' }, { name: 'Mechanical', a: 2.3, b: 0.9, la: '2.3 million', lb: '908 thousand' }] };
const HBAR = { type: 'hbar', title: 'Client items still open — working days late', unit: 'working days late', note: 'Late at the data date.', items: [
  { name: 'Layout Approval (INP.EMP.1010)', value: 122, label: '122 days', tone: 'bad' }, { name: 'Road Level (INP.EMP.1030)', value: 61, label: '61 days', tone: 'warn' }] };

console.log('\nAI Chat — charts in the answers');
test('KPI tiles: the figure, its tone, its hint', () => {
  const h = chartHtml(KPI);
  assert.ok(h.includes('data-chart="kpi"') && h.includes('Where the project stands'));
  assert.equal(count(h, /class="pv2-ckpi /g), 2);
  assert.ok(h.includes('class="pv2-ckpi bad"') && h.includes('<div class="v">0.66</div>') && h.includes('work done ÷ work planned'));
  assert.ok(h.includes('class="pv2-ckpi info"'));                           // an unknown tone falls back, never raw
});
test('progress bars: done over planned, clamped to 0–100, names escaped', () => {
  const h = chartHtml(BARS);
  assert.deepEqual(widths(h), [61, 40, 100, 0]);
  assert.ok(h.includes('40% <small>of 61%</small>') && h.includes('solid = done · light = planned (%)'));
  assert.ok(h.includes('Design &lt;b&gt;') && !h.includes('Design <b>'));
});
test('planned-against-done bars share one scale, so packages compare', () => {
  const h = chartHtml(PAIRS);
  assert.deepEqual(widths(h), [100, 66, 0.4, 0.2]);                          // 560 = full width; 2.3 is a sliver
  assert.ok(h.includes('369.5 million <small>of 560.3 million</small>'));
  assert.ok(h.includes('upper bar = planned by the data date · lower bar = done') && h.includes("in the schedule's own cost unit"));
});
test('single-value bars: longest = the largest, each with its own label and tone', () => {
  const h = chartHtml(HBAR);
  assert.deepEqual(widths(h), [100, 50]);
  assert.ok(h.includes('class="hb bad"') && h.includes('class="hb warn"') && h.includes('>122 days<') && h.includes('Late at the data date.'));
  assert.ok(h.includes('title="Layout Approval (INP.EMP.1010)"'));           // the full name on hover when the row is cut
});
test('nothing to draw → nothing drawn (never an empty box)', () => {
  assert.equal(chartHtml(null), '');
  assert.equal(chartHtml({ type: 'hbar', title: 'x', items: [] }), '');
  assert.equal(chartHtml({ type: 'pie', title: 'x', items: [{ name: 'a', value: 1 }] }), '');
  assert.equal(chartsHtml([]), '');
  assert.equal(chartsHtml(null), '');
  assert.equal(count(chartsHtml([KPI, { type: 'hbar', items: [] }, HBAR]), /class="pv2-chart /g), 2);
});
test('in the answer the charts sit right under the short answer, before the full analysis', () => {
  const a = { id: 'q13', question: 'Claims', verdict: 'Yes.', sections: [{ label: 'S', paras: ['p'] }],
    brief: { problem: 'There is a case.', where: ['w'], why: [], do: ['d'] }, charts: [HBAR] };
  const h = answerV2Html(a, {});
  const iBrief = h.indexOf('class="pv2-brief"'), iChart = h.indexOf('class="pv2-charts"'), iMore = h.indexOf('<details class="pv2-more"');
  assert.ok(iBrief > 0 && iChart > iBrief && iMore > iChart, [iBrief, iChart, iMore].join());
  assert.ok(h.includes('class="pv2-chart pv2-rv"'));                         // revealed with the rest of the answer
  // an answer with no brief still shows them, under its verdict
  const { brief, ...old } = a;
  const o = answerV2Html(old, {});
  assert.ok(o.indexOf('pv2-verdict') < o.indexOf('pv2-charts') && o.indexOf('pv2-charts') < o.indexOf('pv2-sec'));
  assert.ok(!answerV2Html({ ...a, charts: [] }, {}).includes('pv2-charts'));
});
test('the charts use the app colour tokens only, so every appearance mode themes them', () => {
  const css = src.slice(src.indexOf('.pv2-charts{'), src.indexOf('.pv2-crow .v small{'));
  assert.ok(css.length > 500);
  assert.ok(!/#[0-9a-fA-F]{3,6}\b/.test(css), 'a fixed colour in the chart styles');
  for (const tok of ['var(--danger)', 'var(--warning)', 'var(--success)', 'var(--accent)', 'var(--border)', 'var(--card-bg)']) assert.ok(css.includes(tok), tok);
});

console.log('\nDashboard — S-curve month labels');
test('first, last and the data date are always labelled', () => {
  const t = scurveTicks(33, 21, 518);
  assert.ok(t.includes(0) && t.includes(32) && t.includes(21));
});
test('no two labels closer than the minimum — the data-date month no longer prints over its neighbour', () => {
  for (const [n, dd] of [[33, 21], [33, 20], [13, 8], [25, 23], [60, 1], [7, 3]]) {
    const t = scurveTicks(n, dd, 518);
    for (let i = 1; i < t.length; i++) {
      const gap = 518 * (t[i] - t[i - 1]) / (n - 1);
      assert.ok(gap >= 52, `n=${n} dd=${dd}: ${t.join()} gap ${gap}`);
    }
    assert.deepEqual(t, [...t].sort((a, b) => a - b));
  }
  assert.deepEqual(scurveTicks(1, 0, 518), [0]);
  assert.deepEqual(scurveTicks(0, -1, 518), []);
  assert.ok(scurveTicks(40, -1, 518).length >= 5);                           // still enough labels to read the axis
});
test('the end labels stay inside the frame; the time bar labels too', () => {
  assert.ok(src.includes("const anchor = i === 0 ? 'start' : (i === n - 1 ? 'end' : 'middle');"));
  assert.ok(src.includes('class="mk first"') && src.includes('class="mk last"'));
  assert.ok(src.includes('.pdash .tl .mk.last{transform:translateX(-100%);text-align:right}'));
  assert.ok(!src.includes("'<br>' + escapeHtml(ts.start)"));                // one line: it used to climb over the heading
});

console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
