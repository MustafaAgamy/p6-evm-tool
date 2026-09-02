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

let _cssCache = null;
async function appCss() {
  if (_cssCache != null) return _cssCache;
  try { _cssCache = await fetch(`http://localhost:${state.serverPort}/ui/style.css`).then((r) => r.text()); }
  catch { _cssCache = ''; }
  return _cssCache;
}

const PRINT_CSS = `
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
`;

function composeDoc(css, title, subtitle, sections, selectedKeys) {
  const picked = sections.filter((s) => selectedKeys.includes(s.key) && s.html);
  const body = picked.map((s) =>
    `<section class="pr-sec"><h2 class="pr-h">${s.label}</h2>${s.html}</section>`).join('');
  const brand = (typeof window !== 'undefined' && window.__APP_TITLE__) || 'Controlyx';
  return `<!doctype html><html class="light"><head><meta charset="utf-8">
    <style>${css}\n${PRINT_CSS}</style></head>
    <body><div class="pr-doc">
      <div class="pr-head"><div class="pr-brand">${brand}</div><h1>${title || 'Report'}</h1>${subtitle ? `<div class="pr-sub">${subtitle}</div>` : ''}</div>
      ${body || '<p class="pr-sub">No sections selected.</p>'}
    </div></body></html>`;
}

// sections: [{ key, label, html }] — html is the section's rendered content (may be '')
export async function printView({ module, title, subtitle, sections }) {
  const usable = (sections || []).filter(Boolean);
  if (!usable.length) return false;
  const css = await appCss();
  const keys = usable.map((s) => s.key);
  const storageKey = `p6_report_sections_${module}`;
  let selected = keys;
  try { const s = JSON.parse(localStorage.getItem(storageKey) || 'null'); if (Array.isArray(s)) selected = s.filter((k) => keys.includes(k)); } catch { /* default all */ }
  if (!selected.length) selected = keys;

  const secMeta = usable.map((s) => ({ key: s.key, label: s.label, empty: !s.html }));
  const doc = (sel) => composeDoc(css, title, subtitle, usable, sel);

  showReportPreview({
    title: title || 'Report',
    subtitle,
    html: doc(selected),
    sections: secMeta,
    selected,
    storageKey,
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
