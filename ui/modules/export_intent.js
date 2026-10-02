// File ▸ Export to Word / Export to HTML (Ctrl+Shift+W / Ctrl+Shift+H) — where the command goes.
//
// A feature saves Word / HTML from the export bar of its report preview (showReportPreview,
// preview.js) once it has ADOPTED the one-document recipe (docs/report-picker-adoption.md,
// exports: ['pdf','docx','html','xlsx']). So the menu command opens the SAME preview that
// File ▸ Print opens (runReport('pdf')) and leaves a short-lived "pending export" note; the
// preview takes the note when it opens and presses its own ⬇ Word / ⬇ HTML button — or, when
// that feature has not opted in yet, says so inside the preview (never a dialog: WebView2
// alert/confirm are no-ops). Baseline Narrative and Reporting Studio keep their own richer
// Word (REPORT_BTN[view].docx in app.js) and are clicked directly.
// Pure (no DOM) — tests/js/test_export_intent.js.

export const DOC_KINDS = { docx: 'Word', html: 'HTML' };
// What a preview may be asked to press once it opens: Word / HTML (Ctrl+Shift+W / H) and Excel —
// File ▸ Export to Excel (Ctrl+E) on a view whose Excel lives in its preview bar (comment 43).
export const PENDING_KINDS = { ...DOC_KINDS, xlsx: 'Excel' };

// Long enough for a slow report render; short enough that a preview the user opens by hand
// later never saves a file they did not ask for.
export const PENDING_TTL_MS = 60000;

// The friendly "not yet" line. hasPdf / hasExcel: what the view CAN save instead.
export function noDocExportMessage(kind, what, { hasPdf = true, hasExcel = false, inPreview = false } = {}) {
  const label = PENDING_KINDS[kind] || String(kind || '').toUpperCase();
  const alt = [];
  if (hasPdf) alt.push(inPreview ? '⬇ PDF in this preview' : 'File ▸ Print / Export to PDF');
  if (hasExcel) alt.push('File ▸ Export to Excel');
  return `${what || 'This view'} has no ${label} export yet` + (alt.length ? ` — use ${alt.join(' or ')}.` : '.');
}

// Decide what runReport('docx'|'html') does for the open view.
//   map        — REPORT_BTN[view] ({pdf, xls, docx?, html?}) or undefined
//   printView  — the view prints through PRINT_VIEW (printView → showReportPreview)
//   standalone — a library view that needs no imported schedule
//   hasResult  — a schedule is imported
//   ownPreview — the view's PDF button opens the module's OWN preview overlay (Critical Path,
//                Update vs Update, Update Analysis), which never reads a pending note — so say
//                "not yet" now instead of leaving a note another report would pick up and save
// → {action:'click', id}           the view's own Word / HTML button (Narrative, Reporting Studio)
//   {action:'preview', kind, hasExcel} open the preview (same path as PDF) with a pending export
//   {action:'error', msg}           a friendly in-page message
export function docExportRoute({ kind, map, printView = false, standalone = false, hasResult = false,
                                ownPreview = false, what = 'This view' }) {
  if (!DOC_KINDS[kind]) return { action: 'none' };
  if (!standalone && !hasResult) return { action: 'error', msg: 'Import a P6 schedule and open a module first.' };
  const hasExcel = !!(map && map.xls);
  if (map && map[kind]) return { action: 'click', id: map[kind] };
  const hasPdf = !!((map && map.pdf) || printView);
  if (hasPdf && !ownPreview) return { action: 'preview', kind, hasExcel };
  return { action: 'error', msg: noDocExportMessage(kind, what, { hasPdf, hasExcel }) };
}

let _pending = null;

export function requestDocExport(kind, { what = '', hasExcel = false } = {}, now = Date.now()) {
  _pending = PENDING_KINDS[kind] ? { kind, what, hasExcel, until: now + PENDING_TTL_MS } : null;
  return _pending;
}

// Take (and clear) the pending export — null when there is none or it has expired.
export function takeDocExport(now = Date.now()) {
  const p = _pending;
  _pending = null;
  return p && now <= p.until ? p : null;
}

export function clearDocExport() { _pending = null; }

// What an opening preview does with a pending export.
//   offered — the export kinds its bar offers (e.g. ['pdf'] or ['pdf','docx','html','xlsx'])
// → null (nothing pending) | {click: kind} | {message}
export function pendingExportPlan(pending, offered, featureName = '') {
  if (!pending || !PENDING_KINDS[pending.kind]) return null;
  const kinds = Array.isArray(offered) ? offered : [];
  if (kinds.includes(pending.kind)) return { click: pending.kind };
  return {
    message: noDocExportMessage(pending.kind, pending.what || featureName, {
      hasPdf: kinds.includes('pdf'), hasExcel: kinds.includes('xlsx') || !!pending.hasExcel, inPreview: true,
    }),
  };
}
