// Owner comment 1 — "Every feature split into sub-features, with a picker to print any sub-feature
// or any single part of it."  The UI side of the roll-out:
//   * ONE preview for every report: Update Analysis, Update vs Update and Critical Path left their
//     private overlays and open showReportPreview;
//   * a report's own options (code filter, path style, milestone choice) live in the preview's
//     `extras` slot and re-render the report through the same route;
//   * screen views printed with File > Print get their parts from the server's annotate route.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert';
import { fileURLToPath } from 'node:url';
import { scanReport, buildTree, restoreState, togglePart, pruneHtml } from '../../ui/modules/report_parts.js';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const preview = read('ui/modules/preview.js');
const printview = read('ui/modules/printview.js');

let passed = 0;
function test(name, fn) { fn(); passed += 1; console.log('  ok  ' + name); }

test('the shared preview offers an extras slot with a rerender() the feature can call', () => {
  assert.match(preview, /serverOrder, extras \}\) \{/);
  assert.match(preview, /<div class="rpv-extras" id="rpv-extras"><\/div>/);
  assert.match(preview, /extras\(extrasHost, \{ rerender \}\)/);
  const fn = preview.slice(preview.indexOf('const rerender = async () => {'));
  const body = fn.slice(0, fn.indexOf('\n  };'));
  assert.match(body, /await onRerender\(keys, mode\)/);          // same route, current ticks + appearance
  assert.match(body, /adopt\(newHtml, keys\)/);                    // new parts are learned, ticks kept
  assert.match(body, /showFinal\(\)/);
});

test('the three former private previews open the shared one', () => {
  for (const [file, key, route] of [['update.js', 'p6_report_sections_update', 'api/update/report'],
    ['period.js', 'p6_report_sections_period', 'api/period/report'],
    ['critpath.js', 'p6_report_sections_critpath', 'api/critpath/report']]) {
    const src = read('ui/modules/' + file);
    assert.match(src, /import \{ showReportPreview \} from '\.\/preview\.js';/, file);
    assert.ok(src.includes(`storageKey: '${key}'`), file + ' remembers its own ticks');
    assert.ok(src.includes(route), file);
    assert.ok(!/per-preview-overlay|cpa-preview-overlay/.test(src), file + ' still builds an overlay');
    assert.ok(!/output_path: outputPath, sections: selected\(\)/.test(src), file + ' still saves through its own route');
  }
});

test('their own report options moved into the extras slot', () => {
  const period = read('ui/modules/period.js');
  assert.match(period, /extras: \(host, \{ rerender \}\) => \{/);
  assert.match(period, /Filter by activity code/);
  assert.match(period, /Critical-path style/);
  assert.match(period, /code_filter: codeFilter/);                // the filter reaches the server render
  const cp = read('ui/modules/critpath.js');
  assert.match(cp, /Milestone paths to draw/);
  assert.match(cp, /milestone_ids: msIds/);
  assert.match(cp, /msIds = Array\.from\(host\.querySelectorAll\('\.cpa-ms-cb'\)\)\.filter\(c => c\.checked\)/);
});

test('screen views get their parts from the annotate route, and still print when it fails', () => {
  assert.match(printview, /api\/report\/annotate/);
  assert.match(printview, /html: await withParts\(doc\(selected\)\),/);
  assert.match(printview, /onRerender: \(sel\) => withParts\(doc\(sel\)\),/);
  const fn = printview.slice(printview.indexOf('async function withParts(html) {'));
  assert.match(fn.slice(0, fn.indexOf('\n}\n')), /catch \{ return html; \}/);
});

test('an automatically marked part is listed under its section and removed when unticked', () => {
  const html = '<html><body><div data-sec="findings"><h2>Findings</h2>'
    + '<table data-part="findings.a1" data-part-label="Table — Activity ID" data-auto-part="1"><tr><td>ROW-ONE</td></tr></table>'
    + '<div data-part="findings.a2" data-part-label="Lags by type" data-auto-part="1"><svg></svg>CHART-TWO</div>'
    + '</div></body></html>';
  const scan = scanReport(html);
  assert.deepEqual(scan.parts.map((p) => [p.id, p.label]), [['findings.a1', 'Table — Activity ID'], ['findings.a2', 'Lags by type']]);
  const tree = buildTree([{ key: 'findings', label: 'Detailed findings' }], scan);
  assert.equal(tree[0].parts.length, 2);
  let st = restoreState(null, tree, ['findings']);
  st = togglePart(st, tree, 'findings.a2');
  const out = pruneHtml(html, st, { knownSections: ['findings'] });
  assert.ok(out.includes('ROW-ONE') && !out.includes('CHART-TWO'));
  assert.ok(out.includes('<h2>Findings</h2>'));                    // the section and its title stay
});

console.log(`\n${passed} passed`);
