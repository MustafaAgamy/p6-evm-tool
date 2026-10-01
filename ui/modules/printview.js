// Shared "print this view" helper — the one path every screen view uses to satisfy
// the rule: any feature prints from the menu bar (File ▸ Print / Export to PDF) with
// the Printing Selection picker to choose which parts of the report to include.
//
// A view hands printView() its printable sections [{key, label, html}]. This composes
// a self-contained document (the app stylesheet inlined + light theme, only the ticked
// sections) and drives the shared showReportPreview — so Preview == PDF == Print, the
// PDF is saved through /api/report/html, and the section picker comes for free.
import { showReportPreview } from './preview.js';
import { state } from './state.js';

const _attr = (v) => String(v).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');

// The ONE shared page-composition layer (report_theme.pagination_css + its print-time
// composer), served by /api/report/pagination — headings kept with their content, charts /
// KPI rows moved whole, tables with a repeated header and no 1-2 stranded rows.
let _pgCache = null;
async function paginationHead() {
  if (_pgCache != null) return _pgCache;
  try {
    const d = await fetch(`http://localhost:${state.serverPort}/api/report/pagination`).then((r) => r.json());
    _pgCache = (d && d.ok) ? `<style id="rpt-pagination">${d.css || ''}</style><script id="rpt-pagination-js">${d.script || ''}</script>` : '';
  } catch { _pgCache = ''; }
  return _pgCache;
}

let _cssCache = null;
async function appCss() {
  if (_cssCache != null) return _cssCache;
  try { _cssCache = await fetch(`http://localhost:${state.serverPort}/ui/style.css`).then((r) => r.text()); }
  catch { _cssCache = ''; }
  return _cssCache;
}

const PRINT_CSS = `
  /* The inlined app stylesheet pins the app window (html, body { height:100%; overflow:hidden }):
     in THIS document that cut every report off after its first page. A report flows. */
  html, body { height:auto !important; overflow:visible !important; }
  html.light, body { background:#fff; margin:0; }
  .pr-doc { max-width: 900px; margin: 0 auto; padding: 26px 32px 40px;
    font: 14px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color:#1e293b; }
  .pr-head { border-bottom: 2px solid #1e293b; padding-bottom: 12px; margin-bottom: 20px; }
  .pr-brand { font-size: 11px; text-transform: uppercase; letter-spacing: .12em; color:#64748b; font-weight: 700; }
  .pr-head h1 { margin: 4px 0 2px; font-size: 22px; color:#0f172a; }
  .pr-sub { font-size: 12.5px; color:#64748b; }
  .pr-sec { margin: 0 0 22px; break-inside: avoid; }
  .pr-sec > .pr-h { font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color:#334155;
    font-weight: 800; margin: 0 0 10px; padding-bottom: 5px; border-bottom: 1px solid #e2e8f0; }
  /* neutralise interactive-only chrome that might ride along in a section */
  .wbst-colpick, #wbst-colbtn, .cp-ai, #aireview-body, .wbst-toolbar .wbst-seg { display: none !important; }
  .ov-note, .dash-trend-sub, .cp-sub { color:#64748b; }
  @page { margin: 14mm; }
  /* The inlined app stylesheet carries a print safety net (body > *:not(.rpv-overlay) →
     display:none) meant for the app window; in THIS document it hid the whole report, so
     every printView PDF / Print came out blank. The report body must always print. */
  @media print { body > .pr-doc { display: block !important; padding-bottom: 0; } }
  /* no trailing space after the last block: it could spill onto an empty last page */
  @media print { .pr-sec:last-child, .pr-sec:last-child > :last-child { margin-bottom: 0; } }
`;

// Sections come out in the SELECTED order (selectedKeys), each wrapped in [data-sec] so the
// shared picker prunes + reorders them on the client — the order the owner drags is the
// order of the Preview, PDF and Print (F2).
export function composeDoc(css, title, subtitle, sections, selectedKeys, extraHead = '') {
  const byKey = new Map(sections.map((s) => [s.key, s]));
  const picked = (selectedKeys || []).map((k) => byKey.get(k)).filter((s) => s && s.html);
  const body = picked.map((s) =>
    `<section class="pr-sec rpt-measure" data-sec="${_attr(s.key)}"><h2 class="pr-h">${s.label}</h2>${s.html}</section>`).join('');
  const brand = (typeof window !== 'undefined' && window.__APP_TITLE__) || 'Controlyx';
  return `<!doctype html><html class="light"><head><meta charset="utf-8">
    <style>${css}\n${PRINT_CSS}</style>${extraHead || ''}</head>
    <body><div class="pr-doc">
      <div class="pr-head"><div class="pr-brand">${brand}</div><h1>${title || 'Report'}</h1>${subtitle ? `<div class="pr-sub">${subtitle}</div>` : ''}</div>
      ${body || '<p class="pr-sub">No sections selected.</p>'}
    </div></body></html>`;
}

// sections: [{ key, label, html }] — html is the section's rendered content (may be '')
// exports / exportName / meta: an ADOPTED view (its sections carry data-part wrappers and mark
// screen-only cells data-export="skip") may offer Word / HTML beside PDF — default PDF only.
export async function printView({ module, title, subtitle, sections, exports, exportName, meta }) {
  const usable = (sections || []).filter(Boolean);
  if (!usable.length) return false;
  const css = await appCss();
  const pgHead = await paginationHead();
  const keys = usable.map((s) => s.key);
  const storageKey = `p6_report_sections_${module}`;
  let selected = keys;
  try { const s = JSON.parse(localStorage.getItem(storageKey) || 'null'); if (Array.isArray(s)) selected = s.filter((k) => keys.includes(k)); } catch { /* default all */ }
  if (!selected.length) selected = keys;

  const secMeta = usable.map((s) => ({ key: s.key, label: s.label, empty: !s.html }));
  const doc = (sel) => composeDoc(css, title, subtitle, usable, sel, pgHead);

  showReportPreview({
    title: title || 'Report',
    subtitle,
    html: doc(selected),
    sections: secMeta,
    selected,
    storageKey,
    ...(exports ? { exports, feature: title, exportName: exportName || `${module}_report`, meta: meta || {} } : {}),
    onRerender: (sel) => doc(sel),
    onSave: async (mode, sel) => {
      const outputPath = await window.pywebview.api.choose_save_path(`${module}_report.pdf`, 'pdf');
      if (!outputPath) return false;
      try {
        const data = await fetch(`http://localhost:${state.serverPort}/api/report/html`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ html: doc(sel), output_path: outputPath }),
        }).then((r) => r.json());
        return data.ok !== false;
      } catch { return false; }
    },
  });
  return true;
}
