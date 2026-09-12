/**
 * Unit tests for the pure helpers in ui/modules/studio_dash.js
 * Run: node tests/js/test_studio_dash.js
 */
import assert from 'node:assert/strict';
import { boardHtml, panelHtml, tileBodyHtml, kpiTileHtml, letterheadHtml,
         toneClass, sevClass, statusHeaderHtml, sparkHtml, ragLetter } from '../../ui/modules/studio_dash.js';

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
  assert.equal((h.match(/class="pd-kpi(?:"| )/g) || []).length, 2);   // tiles (may carry rail-*), not .pd-kpirow
  assert.ok(h.includes('0.87') && h.includes('1.02'));
  assert.ok(h.includes('pd-bad') && h.includes('pd-good'));
  assert.ok(h.includes('rail-bad') && h.includes('rag bad'));  // RAG rail + redundant letter
  assert.ok(h.includes('pd-kpirow') && !h.includes('pd-grid'));  // no non-kpi tiles → no grid
});

console.log('\nboardHtml — table tile → chart (charts-only dashboard)');
test('a table is charted as bars (NOT a <table>), one numeric column', () => {
  const tiles = [{ id: 't', title: 'EVM table', kind: 'table', shape: { w: 2, h: 1 },
    data: { columns: ['Metric', 'Value'], aligns: ['l', 'r'],
      rows: [['SPI', ['0.87', 'bad']], ['CPI', '1.02']] } }];
  const h = boardHtml(tiles, META);
  assert.ok(!h.includes('<table') && !h.includes('pd-tbl'));     // never a <table> on the dashboard
  assert.ok(h.includes('pd-bar') && h.includes('pd-fl') && h.includes('pd-trk'));
  assert.ok(/pd-fl" style="width:85\.3%/.test(h));               // 0.87 / max(1.02) → 85.3%
  assert.ok(/pd-fl" style="width:100\.0%/.test(h));              // 1.02 / 1.02 → 100%
  assert.ok(h.includes('SPI') && h.includes('CPI'));             // row labels (col 0)
  assert.ok(h.includes('0.87') && h.includes('1.02'));           // display values from cell[0]
  assert.ok(h.includes('pd-legend') && h.includes('Value'));     // legend names the numeric column
  assert.ok(h.includes('table → chart'));                        // subtle converted badge
  assert.ok(h.includes('pd-panel span2'));                       // shape.w===2 → span2 (panel unchanged)
});
test('a table with numeric percent columns → grouped bars, 0..100 scale + legend', () => {
  const h = tileBodyHtml('table', { columns: ['Category', 'Planned %', 'Actual %'],
    rows: [['Construction', '70.0%', '45.0%'], ['Engineering', '88.0%', '74.0%'],
           ['Procurement', '60.0%', '52.0%']] });
  assert.ok(!h.includes('<table'));                              // charted, not tabular
  assert.ok(h.includes('pd-bar') && h.includes('pd-fl'));
  assert.ok(/width:70\.0%/.test(h) && /width:45\.0%/.test(h));   // percent scale (axisMax 100)
  assert.ok(h.includes('Construction · Planned %'));             // multi-column → row · column label
  assert.ok(h.includes('var(--chart-1)') && h.includes('var(--chart-2)')); // colour by column order
  const leg = h.slice(h.indexOf('pd-legend'));
  assert.ok(leg.includes('Planned %') && leg.includes('Actual %'));         // legend names both columns
});
test('a table of only text columns (register) → graceful row-count note, no crash', () => {
  const h = tileBodyHtml('table', { columns: ['Activity', 'Status'],
    rows: [['Pour slab', 'Open'], ['Erect steel', 'Late'], ['Fit MEP', 'Open']] });
  assert.ok(!h.includes('<table') && !h.includes('pd-bar'));     // nothing numeric to chart
  assert.ok(h.includes('3 rows') && h.includes('see the Document'));
  assert.ok(h.includes('table → chart'));                        // still a tile with the badge
});
test('an ID/code register (A100, FS) is NOT charted as bars — falls back', () => {
  // Activity IDs / codes carry digits but are not quantities; they must not chart.
  const h = tileBodyHtml('table', { columns: ['Predecessor', 'Successor', 'Type'],
    rows: [['A100', 'A090', 'FS'], ['A200', 'A150', 'SS'], ['A300', 'A250', 'FS']] });
  assert.ok(!h.includes('pd-bar') && !h.includes('pd-fl'));       // no bars from IDs
  assert.ok(h.includes('3 rows') && h.includes('see the Document'));
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

console.log('\nboardHtml — findings tile → severity donut (charts-only dashboard)');
test('a findings list is charted as a severity donut with a total + legend', () => {
  const tiles = [{ id: 't', title: 'Attention', kind: 'findings', shape: { w: 1, h: 1 },
    data: { items: [
      { severity: 'high', title: '14 activities on negative float', detail: 'Schedule Audit · Float' },
      { severity: 'high', title: 'Missing predecessors', detail: 'Audit · Logic' },
      { severity: 'medium', title: '23 out-of-sequence', detail: 'OOS' },
      { severity: 'info', title: 'Data date is current', detail: 'EVM' }],
      empty: 'Nothing flagged.' } }];
  const h = boardHtml(tiles, META);
  assert.ok(!h.includes('pd-finds') && !h.includes('pd-dot'));   // not a text list any more
  assert.ok(h.includes('<svg') && h.includes('pd-donut') && h.includes('stroke-dasharray')); // ring segments
  assert.ok(h.includes('stroke="var(--danger)"') && h.includes('stroke="var(--warning)"'));  // severity colours
  assert.ok(h.includes('pd-legend'));
  assert.ok(h.includes('Critical 2') && h.includes('Review 1') && h.includes('Info 1'));      // counts by severity
  assert.ok(/>4<\/text>/.test(h));                               // total findings in the centre
  assert.ok(h.includes('list → chart'));                         // subtle converted badge
});
test('empty findings list → the empty message (no chart)', () => {
  const h = tileBodyHtml('findings', { items: [], empty: 'Nothing flagged.' });
  assert.ok(h.includes('pd-na') && h.includes('Nothing flagged.'));
  assert.ok(!h.includes('<svg'));
});
test('findings with an unknown severity falls into the Info bucket', () => {
  const h = tileBodyHtml('findings', { items: [{ severity: 'whatever', title: 'x' }] });
  assert.ok(h.includes('<svg') && h.includes('Info 1'));
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

console.log('\nboardHtml — group tile renders every nested block (each through the chart logic)');
test('a keyvals + findings group shows both blocks; the finding block is a donut', () => {
  const tiles = [{ id: 'g', title: 'Summary', kind: 'group', shape: { w: 2, h: 1 },
    data: { blocks: [
      { kind: 'keyvals', data: { pairs: [['Delay', '+34 d']] } },
      { kind: 'findings', data: { items: [{ severity: 'medium', title: '23 out-of-sequence' }] } },
    ] } }];
  const h = boardHtml(tiles, META);
  assert.ok(h.includes('pd-stats') && h.includes('+34 d'));                 // block 1 (keyvals, unchanged)
  assert.ok(h.includes('<svg') && h.includes('pd-donut'));                  // block 2 charted as a donut
  assert.ok(h.includes('Review 1'));                                        // medium severity counted
  assert.ok(!h.includes('pd-finds') && !h.includes('pd-dot'));              // no text-list markup
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

console.log('\nline / sparkline (trends)');
test('line tile → svg polyline + reference line + legend', () => {
  const h = tileBodyHtml('line', { series: [
    { label: 'SPI', tone: 'accent', points: [0.95, 0.92, 0.87] },
    { label: 'CPI', tone: 'good', points: [1.0, 1.01, 1.02] }],
    x: ['w1', 'w2', 'w3'], ref: { value: 1.0, label: '1.00 target' } });
  assert.ok(h.includes('<svg') && h.includes('<polyline'));
  assert.ok(h.includes('1.00 target') && h.includes('stroke-dasharray'));   // reference line
  assert.ok(h.includes('SPI') && h.includes('CPI'));                        // legend
});
test('line with <2 points → no data', () => {
  assert.ok(tileBodyHtml('line', { series: [{ label: 'x', points: [1] }] }).includes('pd-na'));
});
test('sparkHtml: ≥2 points → a polyline, <2 → empty', () => {
  assert.ok(sparkHtml([1, 2, 3]).includes('<polyline'));
  assert.equal(sparkHtml([1]), '');
  assert.equal(sparkHtml(null), '');
});
test('kpiTileHtml carries a delta + a sparkline when present', () => {
  const h = kpiTileHtml({ label: 'SPI', value: '0.87', tone: 'bad', delta: '-0.03', delta_tone: 'neutral', spark: [0.95, 0.9, 0.87] });
  assert.ok(h.includes('pd-trend') && h.includes('-0.03'));
  assert.ok(h.includes('class="spark"'));
  assert.ok(h.includes('rail-bad') && h.includes('>R<'));                   // rail + redundant letter
});

console.log('\nvariance bars (discipline gap)');
test('variance bars → actual fill + planned tick + shaded shortfall', () => {
  const h = tileBodyHtml('bars', { style: 'variance', series: [{ label: 'Actual', tone: 'accent' }],
    rows: [{ label: 'Construction', values: [45], display: ['45%'], target: 70, target_display: '70%', tone: 'bad' }] });
  assert.ok(h.includes('pd-fl') && h.includes('pd-tick') && h.includes('pd-fl-short'));
  assert.ok(h.includes('Construction') && h.includes('45%'));
});

console.log('\nstatus_header (executive)');
test('no verdict → honest chips-only header with a "Not run" chip', () => {
  const h = statusHeaderHtml({ domains: [
    { domain: 'EVM', tone: 'neutral', headline: 'SPI 0.87' },
    { domain: 'Schedule quality', tone: 'warn', headline: '72/100' },
    { domain: 'Buildability', tone: 'neutral', headline: 'Not run' }], verdict: null });
  assert.ok(h.includes('pd-exec') && h.includes('Status by area'));
  assert.ok(h.includes('Schedule quality') && h.includes('72/100'));
  assert.ok(h.includes('pd-chip warn') && h.includes('Not run'));
  assert.ok(!h.includes('pd-verdict-lab pd-'));   // no coloured single verdict when none is set
});
test('with a verdict → coloured verdict label + rail', () => {
  const h = statusHeaderHtml({ domains: [{ domain: 'EVM', tone: 'bad', headline: 'SPI 0.87' }],
    verdict: { label: 'At risk', tone: 'warn', note: 'schedule slipping' } });
  assert.ok(h.includes('At risk') && h.includes('rail-warn') && h.includes('schedule slipping'));
});
test('boardHtml renders a status_header band above the KPI row', () => {
  const h = boardHtml([
    { id: 'sh', title: 'Status', kind: 'status_header', shape: { w: 2, h: 0 }, data: { domains: [{ domain: 'EVM', tone: 'neutral', headline: 'SPI 0.87' }], verdict: null } },
    { id: 'k', title: 'x', kind: 'kpis', shape: { w: 1, h: 0 }, data: { items: [{ label: 'A', value: '1' }] } }], META);
  assert.ok(h.includes('pd-exec') && h.indexOf('pd-exec') < h.indexOf('pd-kpirow'));
});
test('ragLetter maps tones to R/A/G', () => {
  assert.equal(ragLetter('bad'), 'R'); assert.equal(ragLetter('warn'), 'A');
  assert.equal(ragLetter('good'), 'G'); assert.equal(ragLetter('neutral'), '');
});

// ── edit-mode layout (backward-compatible, pure) ────────────────────────────────
// a GRID panel whose title is distinct from its body text (so indexOf tests the head)
const GP = (id, title) => ({ id, title, kind: 'note', shape: { w: 1, h: 1 }, data: { message: 'msg-' + id } });

console.log('\nletterheadHtml — optional header (edit-mode data)');
test('a custom header shows the title, sized+bold classes and a logo img', () => {
  const h = letterheadHtml(META, { title: 'ACME Weekly', title_bold: true,
    logos_left: [{ src: 'data:image/png;base64,AAA', size: 'm' }] });
  assert.ok(h.includes('ACME Weekly'));
  assert.ok(h.includes('pd-h-title tsz-m pd-b'));                              // size + bold classes
  assert.ok(h.includes('pd-logos pd-logos-left') && h.includes('<img class="pd-logo sz-m"'));
  assert.ok(h.includes('data:image/png;base64,AAA'));
  assert.ok(!h.includes('LOGO'));                                             // custom → no placeholder slots
  assert.ok(!h.includes('contenteditable'));                                  // header without editing → plain
});
test('letterheadHtml(meta) with no header is unchanged (default)', () => {
  const h = letterheadHtml(META);
  assert.ok(h.includes('pd-letterhead') && h.includes('Grain Bulk Terminal'));
  assert.ok(h.includes('Weekly Management Dashboard') && h.includes('LOGO'));
  assert.ok(!h.includes('contenteditable') && !h.includes('pd-logos'));
});
test('an editing header is contenteditable and carries the inline controls', () => {
  const h = letterheadHtml(META, { title: 'X', subtitle: 'Y' }, true);
  assert.ok(h.includes('contenteditable="true"'));
  assert.ok(h.includes('pd-textsizes') && h.includes('pd-addlogo'));          // size/bold + add-logo controls
});

console.log('\nboardHtml — optional layout (order / sizes / titles / header)');
test('no layout → still today\'s view-mode output (guard)', () => {
  const tiles = [GP('a', 'PanelA'), GP('b', 'PanelB')];
  const h = boardHtml(tiles, META);
  assert.ok(h.includes('studio-dash-wrap') && h.includes('pd-toolbar') && h.includes('View mode') && h.includes('pd-sheet'));
  assert.ok(h.includes('pd-grid') && h.includes('PanelA') && h.includes('PanelB'));
  assert.ok(h.indexOf('PanelA') < h.indexOf('PanelB'));                       // natural order preserved
  assert.ok(!h.includes('contenteditable') && !h.includes('pd-grip'));        // view mode → no edit chrome
  assert.ok(h.includes('data-dash="pdf"') && h.includes('data-dash="edit"')); // toolbar has PDF + Edit
});
test('layout.order reorders the grid panels', () => {
  const tiles = [GP('a', 'PanelA'), GP('b', 'PanelB')];
  const h = boardHtml(tiles, META, { order: ['b', 'a'] });
  assert.ok(h.indexOf('PanelB') < h.indexOf('PanelA'));
});
test('layout.order: ids not listed keep their order and are appended', () => {
  const tiles = [GP('a', 'PanelA'), GP('b', 'PanelB'), GP('c', 'PanelC')];
  const h = boardHtml(tiles, META, { order: ['c'] });                         // only c pinned first
  assert.ok(h.indexOf('PanelC') < h.indexOf('PanelA'));
  assert.ok(h.indexOf('PanelA') < h.indexOf('PanelB'));                       // a, b keep relative order
});
test('layout.sizes applies span2 + a height class to that panel', () => {
  const tiles = [GP('a', 'PanelA')];
  assert.ok(/pd-panel span2 pd-tall/.test(boardHtml(tiles, META, { sizes: { a: { w: 2, h: 2 } } })));
  const compact = boardHtml(tiles, META, { sizes: { a: { w: 1, h: 0 } } });
  assert.ok(compact.includes('pd-compact') && !compact.includes('span2'));
});
test('layout.titles overrides a grid-panel title', () => {
  const h = boardHtml([GP('a', 'PanelA')], META, { titles: { a: 'Custom Title' } });
  assert.ok(h.includes('Custom Title') && !h.includes('PanelA'));
});
test('layout.header replaces the auto letterhead subtitle', () => {
  const h = boardHtml([GP('a', 'PanelA')], META, { header: { title: 'ACME Weekly', subtitle: 'wk 30' } });
  assert.ok(h.includes('ACME Weekly') && h.includes('wk 30'));
  assert.ok(!h.includes('Weekly Management Dashboard'));                      // custom header wins
});
test('layout never reorders/resizes kpis or status_header tiles', () => {
  const tiles = [
    { id: 'sh', title: 'Status', kind: 'status_header', shape: { w: 2, h: 0 },
      data: { domains: [{ domain: 'EVM', tone: 'neutral', headline: 'SPI 0.87' }], verdict: null } },
    { id: 'k', title: 'KPIs', kind: 'kpis', shape: { w: 1, h: 0 },
      data: { items: [{ label: 'SPI', value: '0.87', tone: 'bad' }] } },
    GP('a', 'PanelA'),
  ];
  // even asked to reorder/resize the kpis + status ids, they stay a band / in the KPI row
  const h = boardHtml(tiles, META, { order: ['k', 'sh', 'a'], sizes: { k: { w: 2, h: 2 }, sh: { w: 1, h: 2 } } });
  assert.ok(h.indexOf('pd-exec') < h.indexOf('pd-kpirow'));                   // status band above KPI row
  assert.ok(h.indexOf('pd-kpirow') < h.indexOf('pd-grid'));                   // KPI row above the grid
  assert.ok(!h.includes('span2') && !h.includes('pd-tall') && !h.includes('pd-compact')); // sizes ignored for them
});

console.log('\ncharts-only dashboard — bars / line still render unchanged');
test('bars still render as bars and line still renders as a polyline', () => {
  const bars = tileBodyHtml('bars', { series: [{ label: 'Actual', tone: 'accent' }],
    rows: [{ label: 'Construction', values: [45], display: ['45%'] }] });
  assert.ok(/pd-fl" style="width:45\.0%/.test(bars) && !bars.includes('table → chart'));
  const line = tileBodyHtml('line', { series: [{ label: 'SPI', tone: 'accent', points: [0.95, 0.9, 0.87] }] });
  assert.ok(line.includes('<polyline') && !line.includes('pd-donut'));
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
