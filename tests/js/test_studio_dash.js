/**
 * Unit tests for the pure helpers in ui/modules/studio_dash.js
 * Run: node tests/js/test_studio_dash.js
 */
import assert from 'node:assert/strict';
import { boardHtml, panelHtml, tileBodyHtml, kpiTileHtml, letterheadHtml,
         toneClass, sevClass } from '../../ui/modules/studio_dash.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

const META = { project_name: 'Grain Bulk Terminal', data_date: '2026-07-19 00:00:00', activity_count: 842 };
const countOf = (h, sub) => h.split(sub).length - 1;

console.log('\ntoneClass / sevClass mapping');
test('toneClass maps every tone', () => {
  assert.equal(toneClass('good'), 'pd-good');
  assert.equal(toneClass('warn'), 'pd-warn');
  assert.equal(toneClass('bad'), 'pd-bad');
  assert.equal(toneClass('accent'), 'pd-accent');
  assert.equal(toneClass('neutral'), 'pd-neutral');
  assert.equal(toneClass(undefined), 'pd-neutral');
});
test('sevClass maps every severity', () => {
  assert.equal(sevClass('high'), 'pd-bad');
  assert.equal(sevClass('medium'), 'pd-warn');
  assert.equal(sevClass('low'), 'pd-neutral');
  assert.equal(sevClass('info'), 'pd-accent');
  assert.equal(sevClass('what'), 'pd-neutral');
});

console.log('\nletterheadHtml');
test('shows the project name and the sliced data date', () => {
  const h = letterheadHtml(META);
  assert.ok(h.includes('pd-letterhead') && h.includes('Grain Bulk Terminal'));
  assert.ok(h.includes('Weekly Management Dashboard'));
  assert.ok(h.includes('Data date 2026-07-19') && !h.includes('00:00:00'));  // sliced to YYYY-MM-DD
  assert.ok(h.includes('842 activities'));
});
test('omits the optional bits when absent', () => {
  const h = letterheadHtml({ project_name: 'P' });
  assert.ok(h.includes('Weekly Management Dashboard') && !h.includes('Data date') && !h.includes('activities'));
});

console.log('\nboardHtml — kpis tile flattens to KPI tiles');
test('two kpi items → two .pd-kpi tiles with both values', () => {
  const tiles = [{ id: 't1', title: 'EVM', kind: 'kpis', shape: { w: 1, h: 0 },
    data: { items: [
      { label: 'SPI', value: '0.87', sub: '3 weeks declining', tone: 'bad' },
      { label: 'CPI', value: '1.02', sub: 'stable on cost', tone: 'good' },
    ] } }];
  const h = boardHtml(tiles, META);
  assert.equal(countOf(h, 'class="pd-kpi"'), 2);
  assert.ok(h.includes('0.87') && h.includes('1.02'));
  assert.ok(h.includes('pd-bad') && h.includes('pd-good'));
  assert.ok(h.includes('pd-kpirow') && !h.includes('pd-grid'));  // no non-kpi tiles → no grid
});

console.log('\nboardHtml — table tile');
test('renders .pd-tbl with a header and a toned cell', () => {
  const tiles = [{ id: 't', title: 'EVM table', kind: 'table', shape: { w: 2, h: 1 },
    data: { columns: ['Metric', 'Value'], aligns: ['l', 'r'],
      rows: [['SPI', ['0.87', 'bad']], ['CPI', '1.02']] } }];
  const h = boardHtml(tiles, META);
  assert.ok(h.includes('pd-tbl'));
  assert.ok(h.includes('<th') && h.includes('Metric') && h.includes('Value'));
  assert.ok(h.includes('SPI') && h.includes('0.87'));
  assert.ok(/<td class="pd-bad"[^>]*>0\.87<\/td>/.test(h));      // [text, tone] cell coloured
  assert.ok(h.includes('text-align:right'));                     // aligns respected
  assert.ok(h.includes('pd-panel span2'));                       // shape.w===2 → span2
});

console.log('\nboardHtml — bars tile (1 series)');
test('renders a .pd-bar with a .pd-fl width', () => {
  const tiles = [{ id: 't', title: 'Discipline gap', kind: 'bars', shape: { w: 1, h: 1 },
    data: { series: [{ label: 'Actual', tone: 'accent' }],
      rows: [{ label: 'Construction', values: [45], display: ['45%'] },
             { label: 'Engineering', values: [74], display: null }],
      note: 'weighted by cost' } }];
  const h = boardHtml(tiles, META);
  assert.ok(h.includes('pd-bar') && h.includes('pd-trk'));
  assert.ok(/pd-fl" style="width:45\.0%/.test(h));               // pct = value (no axis_max)
  assert.ok(h.includes('Construction') && h.includes('45%'));
  assert.ok(h.includes('weighted by cost'));                     // note
  assert.ok(!h.includes('pd-legend'));                           // single series → no legend
});
test('axis_max scales the width and 2 series draw a legend', () => {
  const h = tileBodyHtml('bars', { series: [{ label: 'Plan', tone: 'neutral' }, { label: 'Actual', tone: 'good' }],
    rows: [{ label: 'Civil', values: [30, 15] }], axis_max: 60 });
  assert.ok(/width:50\.0%/.test(h) && /width:25\.0%/.test(h));    // 30/60, 15/60
  assert.ok(h.includes('pd-legend') && h.includes('Plan') && h.includes('Actual'));
  assert.ok(h.includes('Civil · Plan'));                         // multi-series prefixes the series label
});

console.log('\ntileBodyHtml — segbar');
test('stacked segments sized by share, with a legend', () => {
  const h = tileBodyHtml('segbar', { segments: [
    { label: 'Done', value: 30, tone: 'good' }, { label: 'Open', value: 10, tone: 'warn' }],
    note: 'by count' });
  assert.ok(h.includes('pd-seg') && h.includes('pd-seg-part'));
  assert.ok(/width:75\.0%/.test(h) && /width:25\.0%/.test(h));    // 30/40, 10/40
  assert.ok(h.includes('Done 30') && h.includes('Open 10') && h.includes('by count'));
});

console.log('\nboardHtml — findings tile');
test('a high finding → a pd-dot pd-bad; detail shown', () => {
  const tiles = [{ id: 't', title: 'Attention', kind: 'findings', shape: { w: 1, h: 1 },
    data: { items: [{ severity: 'high', title: '14 activities on negative float', detail: 'Schedule Audit · Float' }],
      empty: 'Nothing flagged.' } }];
  const h = boardHtml(tiles, META);
  assert.ok(h.includes('pd-finds'));
  assert.ok(/<span class="pd-dot pd-bad">/.test(h));
  assert.ok(h.includes('14 activities on negative float') && h.includes('Schedule Audit · Float'));
});
test('empty findings list → the empty message', () => {
  const h = tileBodyHtml('findings', { items: [], empty: 'Nothing flagged.' });
  assert.ok(h.includes('pd-na') && h.includes('Nothing flagged.'));
});

console.log('\ntileBodyHtml — keyvals / text / note');
test('keyvals → a .pd-stats grid', () => {
  const h = tileBodyHtml('keyvals', { pairs: [['PV', 'EGP 12M'], ['EV', 'EGP 9M']] });
  assert.ok(h.includes('pd-stats') && h.includes('pd-stat-l') && h.includes('PV') && h.includes('EGP 9M'));
});
test('text → paragraphs in a .pd-usertext wrapper', () => {
  const h = tileBodyHtml('text', { paragraphs: ['First line.', 'Second line.'] });
  assert.ok(h.includes('pd-usertext') && h.includes('<p>First line.</p>') && h.includes('<p>Second line.</p>'));
});
test('note → a .pd-note callout, info tone maps to accent', () => {
  const h = tileBodyHtml('note', { message: 'Verdict is opt-in.', tone: 'info' });
  assert.ok(/class="pd-note pd-accent"/.test(h) && h.includes('Verdict is opt-in.'));
});

console.log('\nboardHtml — group tile renders every nested block');
test('a keyvals + findings group shows both blocks', () => {
  const tiles = [{ id: 'g', title: 'Summary', kind: 'group', shape: { w: 2, h: 1 },
    data: { blocks: [
      { kind: 'keyvals', data: { pairs: [['Delay', '+34 d']] } },
      { kind: 'findings', data: { items: [{ severity: 'medium', title: '23 out-of-sequence' }] } },
    ] } }];
  const h = boardHtml(tiles, META);
  assert.ok(h.includes('pd-stats') && h.includes('+34 d'));                 // block 1
  assert.ok(h.includes('pd-finds') && h.includes('23 out-of-sequence'));    // block 2
  assert.ok(/pd-dot pd-warn/.test(h));                                      // medium severity in the nested finding
});

console.log('\nboardHtml — no_data + empty board');
test('no_data tile → No data available', () => {
  assert.ok(tileBodyHtml('no_data', {}).includes('No data available.'));
  assert.ok(tileBodyHtml('totally_unknown', {}).includes('No data available.'));
});
test('empty tiles → the friendly empty-state message', () => {
  const h = boardHtml([], META);
  assert.ok(h.includes('pd-empty-state'));
  assert.ok(h.includes('Pick results in the builder, then switch to Dashboard to see them here.'));
});
test('the board is always wrapped in the view-mode shell', () => {
  const h = boardHtml([{ id: 'k', title: 'x', kind: 'kpis', shape: { w: 1, h: 0 }, data: { items: [{ label: 'A', value: '1' }] } }], META);
  assert.ok(h.includes('studio-dash-wrap') && h.includes('pd-toolbar') && h.includes('View mode') && h.includes('pd-sheet'));
});

console.log('\npanelHtml / kpiTileHtml — structure');
test('panelHtml wraps the body in a titled panel', () => {
  const h = panelHtml({ title: 'CPLI health', kind: 'note', shape: { w: 1, h: 1 }, data: { message: 'below 1.0', tone: 'warn' } });
  assert.ok(h.includes('pd-panel') && h.includes('pd-p-head') && h.includes('CPLI health') && h.includes('pd-p-body'));
  assert.ok(!h.includes('span2'));
});
test('kpiTileHtml builds a head/body KPI tile', () => {
  const h = kpiTileHtml({ label: 'Delay', value: '+34 d', sub: 'vs baseline', tone: 'bad' });
  assert.ok(h.includes('pd-kpi') && h.includes('pd-k-head') && h.includes('Delay'));
  assert.ok(h.includes('pd-kv pd-bad') && h.includes('+34 d') && h.includes('vs baseline'));
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
