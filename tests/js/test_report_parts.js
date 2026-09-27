/**
 * Unit tests for ui/modules/report_parts.js — the two-level Report Contents picker (pure).
 * Run: node tests/js/test_report_parts.js
 */
import assert from 'node:assert/strict';
import {
  scanElements, scanReport, buildTree, restoreState, sectionCheck, partChecked, toggleSection,
  togglePart, selectAll, clearAll, moveSection, serverKeys, countTicked, pruneHtml, textOf, NO_DATA_HTML,
} from '../../ui/modules/report_parts.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}\n    ${err.message}`); failed++; }
}

// A report shaped like the real renderers (EVM / Calendar): head, sections, parts, footer.
const REPORT = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>EVM</title>
<style>.x{color:red} /* <div data-sec="fake"> */</style></head><body>
<div class="head"><div class="title">EVM Results</div></div>
<div data-sec="progress"><h2 class="sec">Project Progress</h2>
  <div data-part="progress.kpis" data-part-label="Planned / Actual tiles"><div class="kpi"><div class="k">Planned %</div><div class="v">36.8%</div></div></div>
  <div data-part="progress.chart" data-part-label="Planned vs Actual bars" data-export="image"><div class="bar-row">Planned</div><br><img src="data:image/png;base64,AA"></div>
</div>
<div data-sec="category"><h2 class="sec">Category Weights &amp; Progress</h2>
  <div data-part="category.table"><table><caption>Weights table</caption><tr><td>Construction</td><td>95%</td></tr></table></div>
  <div data-part="category.empty" data-part-label="Nothing here"></div>
</div>
<!-- <div data-sec="commented"> -->
<div data-sec="gap"><h2>PV vs EV Gap</h2><div data-part="gap.table" data-part-label="Gap table"><p>gap rows</p></div></div>
<div class="foot">footer</div>
</body></html>`;

const SECTIONS = [
  { key: 'progress', label: 'Project progress' },
  { key: 'category', label: 'Category weights' },
  { key: 'dashboard', label: 'Executive dashboard', empty: true },
];

console.log('\nscan');
test('scanElements finds sections and parts with exact ranges (ignores comments / style text)', () => {
  const recs = scanElements(REPORT);
  const secs = recs.filter(r => r.attrs['data-sec'] != null).map(r => r.attrs['data-sec']);
  assert.deepEqual(secs, ['progress', 'category', 'gap']);
  const r = recs.find(x => x.attrs['data-part'] === 'category.table');
  assert.ok(REPORT.slice(r.start, r.end).startsWith('<div data-part="category.table">'));
  assert.ok(REPORT.slice(r.start, r.end).endsWith('</table></div>'));
});
test('scanReport labels: data-part-label, else first heading/caption; flags empty parts', () => {
  const { sections, parts } = scanReport(REPORT);
  assert.deepEqual(sections.map(s => s.key), ['progress', 'category', 'gap']);
  assert.equal(sections[1].label, 'Category Weights & Progress');
  const byId = Object.fromEntries(parts.map(p => [p.id, p]));
  assert.equal(byId['progress.kpis'].label, 'Planned / Actual tiles');
  assert.equal(byId['category.table'].label, 'Weights table');
  assert.equal(byId['category.table'].sec, 'category');
  assert.equal(byId['category.empty'].empty, true);
  assert.equal(byId['progress.chart'].empty, false);       // an image counts as content
});
test('textOf strips tags and decodes entities', () => {
  assert.equal(textOf('<b>A &amp; B</b>&nbsp;<i>c</i>'), 'A & B c');
});

console.log('\ntree');
const scan = scanReport(REPORT);
const tree = buildTree(SECTIONS, scan);
test('buildTree keeps caller order, appends sections found only in the HTML', () => {
  assert.deepEqual(tree.map(s => s.key), ['progress', 'category', 'dashboard', 'gap']);
  assert.deepEqual(tree[0].parts.map(p => p.id), ['progress.kpis', 'progress.chart']);
  assert.equal(tree[2].empty, true);
  assert.equal(tree[3].label, 'PV vs EV Gap');
});
test('buildTree keeps parts of a section that is not in the current render (prev tree)', () => {
  const partial = scanReport('<div data-sec="progress"><div data-part="progress.kpis">x</div></div>');
  const t2 = buildTree(SECTIONS, partial, tree);
  assert.deepEqual(t2.find(s => s.key === 'category').parts.map(p => p.id), ['category.table', 'category.empty']);
  assert.ok(t2.some(s => s.key === 'gap'));
});

console.log('\nstate');
test('restoreState: default = every non-empty section ticked, all parts on, natural order', () => {
  const st = restoreState(null, tree);
  assert.deepEqual(st.sections, ['progress', 'category', 'gap']);
  assert.deepEqual(st.offParts, []);
  assert.deepEqual(st.order, ['progress', 'category', 'dashboard', 'gap']);
});
test('restoreState: legacy saved array of section keys still works', () => {
  const st = restoreState(['category'], tree);
  assert.deepEqual(st.sections, ['category']);
});
test('restoreState: v2 remembers sections + parts + order; drops unknown keys, appends new sections', () => {
  const st = restoreState({ v: 2, order: ['gap', 'zzz', 'progress'], sections: ['gap', 'progress', 'dashboard'], offParts: ['progress.chart', 'zzz.x'] }, tree);
  assert.deepEqual(st.order, ['gap', 'progress', 'category', 'dashboard']);
  assert.deepEqual(st.sections, ['gap', 'progress']);        // empty 'dashboard' never ticked
  assert.deepEqual(st.offParts, ['progress.chart']);
});
test('tri-state section checkbox', () => {
  let st = restoreState(null, tree);
  assert.equal(sectionCheck(st, tree, 'progress'), 'all');
  st = togglePart(st, tree, 'progress.chart', false);
  assert.equal(sectionCheck(st, tree, 'progress'), 'some');
  assert.equal(partChecked(st, tree, 'progress.chart'), false);
  assert.equal(partChecked(st, tree, 'progress.kpis'), true);
  st = togglePart(st, tree, 'progress.kpis', false);         // last part off → section off
  assert.equal(sectionCheck(st, tree, 'progress'), 'none');
  assert.ok(!st.sections.includes('progress'));
});
test('ticking one part of an unticked section brings only that part in', () => {
  let st = toggleSection(restoreState(null, tree), tree, 'progress', false);
  st = togglePart(st, tree, 'progress.chart', true);
  assert.ok(st.sections.includes('progress'));
  assert.equal(partChecked(st, tree, 'progress.chart'), true);
  assert.equal(partChecked(st, tree, 'progress.kpis'), false);
});
test('section toggle ticks all its parts again; empty sections cannot be ticked', () => {
  let st = togglePart(restoreState(null, tree), tree, 'progress.chart', false);
  st = toggleSection(st, tree, 'progress', true);
  assert.equal(sectionCheck(st, tree, 'progress'), 'all');
  assert.deepEqual(toggleSection(st, tree, 'dashboard', true), st);
});
test('select all / clear all / count', () => {
  let st = clearAll(restoreState(null, tree));
  assert.deepEqual(serverKeys(st), []);
  assert.equal(countTicked(st, tree), 0);
  st = selectAll(st, tree);
  assert.deepEqual(serverKeys(st), ['progress', 'category', 'gap']);
  assert.equal(countTicked(st, tree), 5);
});
test('moveSection reorders (drag down and drag up) and serverKeys follows the order', () => {
  let st = restoreState(null, tree);
  st = moveSection(st, 'progress', 'gap');                  // drag down onto the last
  assert.deepEqual(st.order, ['category', 'dashboard', 'gap', 'progress']);
  st = moveSection(st, 'gap', 'category');                  // drag up onto the first
  assert.deepEqual(st.order, ['gap', 'category', 'dashboard', 'progress']);
  assert.deepEqual(serverKeys(st), ['gap', 'category', 'progress']);
});

console.log('\nprune');
test('an unticked part is ABSENT from the final HTML (not hidden)', () => {
  const st = togglePart(restoreState(null, tree), tree, 'progress.chart', false);
  const out = pruneHtml(REPORT, st);
  assert.ok(!out.includes('data-part="progress.chart"'));
  assert.ok(!out.includes('bar-row'));
  assert.ok(out.includes('data-part="progress.kpis"'));
  assert.ok(out.includes('<div class="foot">footer</div>'));
  assert.ok(!/display\s*:\s*none/.test(out));
});
test('an unticked section is removed with its heading', () => {
  const st = toggleSection(restoreState(null, tree), tree, 'category', false);
  const out = pruneHtml(REPORT, st);
  assert.ok(!out.includes('Category Weights'));
  assert.ok(!out.includes('Construction'));
  assert.ok(out.includes('PV vs EV Gap'));
});
test('a ticked part with no content shows "No data available"', () => {
  const out = pruneHtml(REPORT, restoreState(null, tree));
  assert.ok(out.includes(`<div data-part="category.empty" data-part-label="Nothing here">${NO_DATA_HTML}</div>`));
});
test('data-empty="1" keeps the part heading and adds "No data available"', () => {
  const html = '<div data-sec="a"><div data-part="a.t" data-empty="1"><h3>Title</h3></div></div>';
  const t = buildTree([{ key: 'a', label: 'A' }], scanReport(html));
  const out = pruneHtml(html, restoreState(null, t));
  assert.ok(out.includes('<h3>Title</h3>' + NO_DATA_HTML));
});
test('sections are reordered in the final HTML; content between them stays put', () => {
  let st = moveSection(restoreState(null, tree), 'gap', 'progress');
  const out = pruneHtml(REPORT, st);
  const g = out.indexOf('data-sec="gap"'), p = out.indexOf('data-sec="progress"'), c = out.indexOf('data-sec="category"');
  assert.ok(g < p && p < c, `${g} ${p} ${c}`);
  assert.ok(out.indexOf('class="head"') < g);
  assert.ok(out.indexOf('<!-- <div data-sec="commented"> -->') > 0);
  assert.ok(out.lastIndexOf('class="foot"') > c);
});
test('an HTML without picker hooks passes through unchanged', () => {
  const html = '<html><body><h1>x</h1><table><tr><td>1</td></tr></table></body></html>';
  assert.equal(pruneHtml(html, restoreState(null, buildTree([], scanReport(html)))), html);
});
test('void / self-closing tags and unclosed <p> do not break the ranges', () => {
  const html = '<div data-sec="s"><p>one<p>two<br/><img src="x"><svg><rect/></svg><div data-part="s.p">keep</div></div><div data-sec="t"><div data-part="t.q">q</div></div>';
  const t = buildTree([{ key: 's' }, { key: 't' }], scanReport(html));
  const out = pruneHtml(html, togglePart(restoreState(null, t), t, 't.q', false));
  assert.ok(out.includes('keep'));
  assert.ok(!out.includes('data-sec="t"'));                // its only part went → section went
});
test('a section the picker does not manage is left alone', () => {
  const html = '<div data-sec="x">X</div><div data-sec="a"><div data-part="a.1">1</div></div>';
  const t = buildTree([{ key: 'a', label: 'A' }], { sections: [], parts: scanReport(html).parts });
  const out = pruneHtml(html, toggleSection(restoreState(null, t), t, 'a', false), { knownSections: ['a'] });
  assert.ok(out.includes('<div data-sec="x">X</div>'));
  assert.ok(!out.includes('data-sec="a"'));
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
