/**
 * Baseline Narrative on screen — the report's stylesheet must style the REPORT only.
 * The server renders one HTML for the screen and the PDF / HTML exports; its page-level
 * rules (`body`, `p`, `table`, `*`) are right for a standalone page, but mounted inside the
 * app they restyled every feature (Times New Roman text, grey page, dark text colour in the
 * dark modes, a jump of the menu bar) from the moment the report was generated.
 * scopeReportCss() confines those rules to the report container on screen; :where() keeps
 * their specificity exactly as written, so the report itself renders the same.
 * Run: node tests/js/test_narrative_screen_css.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { scopeReportCss } from '../../ui/modules/narrative.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..', '..');
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), 'utf8');

let passed = 0;
let failed = 0;
async function test(name, fn) {
  try { await fn(); passed++; console.log('  ✓ ' + name); }
  catch (e) { failed++; console.log('  ✗ ' + name + '\n    ' + (e && e.message)); }
}

// The report's real stylesheet, straight from the renderer (p6_narrative/html.py _CSS).
const CSS = (read('p6_narrative', 'html.py').match(/\n_CSS = """([\s\S]*?)"""/) || [])[1];
const HTML = '<style>' + CSS + '</style><div class="page"><p>x</p></div>';

// Top-level rule selectors (and those inside @media blocks), in order.
function selectors(css) {
  const out = [];
  css.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[{}])\s*([^{}@]+?)\s*\{/g, (m, b, sel) => { out.push(sel.trim()); return m; });
  return out;
}
const PAGE_LEVEL = new Set(['body', 'html', 'p', 'table', '*', 'h1', 'h2', 'h3', 'td', 'th', 'div', 'span', 'img']);

console.log('Narrative screen CSS');
await test('the renderer stylesheet was found (guards the regex above)', () => {
  assert.ok(CSS && CSS.length > 1000);
  assert.match(CSS, /\nbody \{[^}]*font-family/);
});
await test('no page-level rule of the report reaches the rest of the app once mounted', () => {
  const out = scopeReportCss(HTML);
  const css = out.match(/<style>([\s\S]*?)<\/style>/)[1];
  const leaking = selectors(css).flatMap(s => s.split(',').map(x => x.trim())).filter(x => PAGE_LEVEL.has(x));
  assert.deepEqual(leaking, []);
});
await test('the report keeps every rule, in order; only page-level selectors are confined to the report', () => {
  const before = selectors(CSS), after = selectors(scopeReportCss(HTML).match(/<style>([\s\S]*?)<\/style>/)[1]);
  assert.equal(after.length, before.length);
  before.forEach((s, i) => {
    if (s === 'body') assert.equal(after[i], ':where(#narrative-doc)');
    else if (PAGE_LEVEL.has(s)) assert.equal(after[i], ':where(#narrative-doc) ' + s);
    else assert.equal(after[i], s, 'class-scoped rule unchanged: ' + s);
  });
  // Nothing else changes — declarations, whitespace, markup (same font, colours, paper desk):
  // undoing the scope gives back the renderer's HTML byte for byte.
  const undone = scopeReportCss(HTML).replace(/:where\(#narrative-doc\)(?=\s*\{)/g, 'body').split(':where(#narrative-doc) ').join('');
  assert.equal(undone, HTML);
});
await test('the markup after the stylesheet is untouched; html without a stylesheet passes through', () => {
  assert.ok(scopeReportCss(HTML).endsWith('<div class="page"><p>x</p></div>'));
  assert.equal(scopeReportCss('<div>p { }</div>'), '<div>p { }</div>');
  assert.equal(scopeReportCss(''), '');
});
await test('the on-screen mount uses the scoped stylesheet (exports still send the document model)', () => {
  const nar = read('ui', 'modules', 'narrative.js');
  assert.match(nar, /host\.innerHTML = editStyles\(\) \+ scopeReportCss\(html\);/);
  assert.match(nar, /JSON\.stringify\(\{ doc: exportDoc\(\)/);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
