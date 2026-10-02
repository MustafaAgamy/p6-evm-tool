/**
 * AI Chat ▸ Professional Dashboard ▸ Download PDF (owner comment 39) — ui/modules/chat.js.
 * The dashboard on screen is printed as ONE A4 landscape page, in the format the planner chose,
 * laid out as on screen. Also: amounts carry no invented currency symbol.
 * Run: node tests/js/test_chat_dashboard_pdf.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { dashPdfZoom, dashPdfName, dashXlsxName, dashPdfDoc, stripNarrowMedia, DASH_PDF_PAGE } from '../../ui/modules/chat.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'ui', 'modules', 'chat.js'), 'utf8');

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

console.log('\nAI Chat dashboard — Download PDF');
test('the page is A4 landscape and the dashboard is scaled to fit it, never enlarged', () => {
  assert.deepEqual(DASH_PDF_PAGE, { w: 1123, h: 794 });
  assert.equal(dashPdfZoom(800, 500), 1);                       // already fits → real size
  const z = dashPdfZoom(1341, 1077);                            // a wide desktop dashboard
  assert.ok(z < 1 && 1341 * z <= 1123 - 52 + 1 && 1077 * z <= 794 - 52 + 1, String(z));
  assert.equal(z, 0.689);                                       // height-bound: 742 / 1077
  assert.equal(dashPdfZoom(2000, 600), 0.536);                  // width-bound: 1071 / 2000
  assert.equal(dashPdfZoom(0, 0), 1);
  assert.equal(dashPdfZoom(9000, 9000), 0.4);                   // floor: still readable
});
test('the file is named after the project', () => {
  assert.equal(dashPdfName('Update Till 19 July.2026 - Weekly Report'), 'dashboard_Update_Till_19_July_2026_Weekly_Report.pdf');
  assert.equal(dashPdfName(''), 'dashboard_project.pdf');
  assert.equal(dashPdfName('مشروع'), 'dashboard_project.pdf');  // no usable letters → a safe name
  assert.ok(dashPdfName('x'.repeat(200)).length <= 'dashboard_.pdf'.length + 60);
});
test('narrow-screen rules never reach the paper (they stacked the cards and cut the page)', () => {
  const css = '.pdash .dgrid{display:grid}\n  @media (max-width:820px){ .pdash .dkpis{grid-template-columns:repeat(3,1fr)} .pdash .dgrid{grid-template-columns:1fr} }\n  @media (max-width:480px){ .pdash .drow{grid-template-columns:88px 1fr auto} }\n.pdash .keep{color:red}';
  const out = stripNarrowMedia(css);
  assert.ok(!out.includes('@media') && !out.includes('repeat(3,1fr)'));
  assert.ok(out.includes('.pdash .dgrid{display:grid}') && out.includes('.pdash .keep{color:red}'));
  assert.ok(/@media \(max-width:820px\)/.test(src), 'the screen keeps its narrow-window rule');
});
test('the print document: one sheet, on-screen layout, the chosen format, a report head', () => {
  const doc = dashPdfDoc({
    css: '.pdash{--ground:#0b1220}\n@media (max-width:820px){ .pdash .dgrid{grid-template-columns:1fr} }',
    dashHtml: '<div class="pdash" data-style="midnight"><div class="dprint-head"></div><div class="dhead">H</div></div>',
    w: 1341, h: 1077, zoom: 0.689, ground: '#0b1220', brand: 'Controlyx 2026', generated: '01 Oct 2026',
  });
  assert.ok(doc.startsWith('<!doctype html>') && doc.includes('<meta charset="utf-8">'));
  assert.ok(doc.includes('@page { size: A4 landscape; margin: 0; }'));
  assert.ok(doc.includes('data-style="midnight"'));                          // the format shown
  assert.ok(doc.includes('background: #0b1220 !important'));                 // the sheet takes its ground
  assert.ok(doc.includes('.dfit .pdash { width: 1341px; transform: scale(0.689)'));   // laid out as on screen
  assert.ok(doc.includes('.dfit { flex: none; width: 923px; height: 742px; overflow: hidden; }'));
  assert.ok(!doc.includes('max-width:820px'));
  assert.ok(doc.includes('Controlyx 2026 · Professional Dashboard') && doc.includes('Generated 01 Oct 2026'));
  assert.ok(doc.includes('print-color-adjust: exact'));
});
test('the button is on the dashboard, messages are in the page, controls stay off the paper', () => {
  assert.ok(src.includes('data-dpdf="1"') && src.includes('⬇ Download PDF'));
  assert.ok(src.includes("clone.querySelectorAll('[data-screen-only]').forEach((n) => n.remove())"));
  assert.ok(src.includes('<div class="dtools" data-screen-only="1">'));
  assert.ok(src.includes("postJSON('/api/report/html', { html, output_path: outputPath })"));
  assert.ok(src.includes("getPropertyValue('--ground')"));
  assert.ok(src.includes("'PDF saved — '") && src.includes('Saving a PDF is available in the desktop app.'));
  const fn = src.slice(src.indexOf('async function downloadDashboardPdf'), src.indexOf('function renderDashboard'));
  assert.ok(!/\balert\(|\bconfirm\(/.test(fn));                               // no-ops in the desktop window
});
test('amounts carry no invented currency symbol', () => {
  assert.ok(!src.includes('£'));
  assert.ok(src.includes("function money(v) { return Math.abs(Number(v) || 0).toFixed(1) + 'M'; }"));
});

test('Download Excel sits beside Download PDF and saves the figures shown (final sweep)', () => {
  assert.equal(dashXlsxName('Grain Bulk — Rev.01'), 'dashboard_Grain_Bulk_Rev_01.xlsx');
  assert.equal(dashXlsxName(''), 'dashboard_project.xlsx');
  assert.ok(src.includes('data-dxlsx="1"') && src.includes("'/api/chat/dashboard/excel'"));
  const tools = src.slice(src.indexOf('<div class="dtools" data-screen-only="1">'), src.indexOf('<div class="dpdf-note"'));
  assert.ok(tools.includes('data-dpdf') && tools.includes('data-dxlsx'), 'both buttons in the screen-only tools row');
});

console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
