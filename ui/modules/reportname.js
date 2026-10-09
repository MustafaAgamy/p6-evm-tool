// The report name the planner types. It is shown IN PLACE OF the P6 project name (often an
// export name such as "Update Till 09 Aug.2026- Weekly Report") on screen and in every PDF /
// Word / Excel, is saved with the project in the app database (POST /api/report-name) and is
// carried to the project's next update. Emptied, the name in the P6 file is back. The P6 file
// itself is never changed.
import { state } from './state.js';

const attr = (s) => String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

let rerender = null;
// The view on screen registers how to redraw itself, so its report parts carry a new name at once.
export function onReportName(fn) { rerender = fn; }

export function reportNameField() {
  const r = state.currentResult || {};
  const p6 = r.p6_project_name !== undefined ? r.p6_project_name : r.project_name;
  return `<label class="rn-field" title="Shown instead of the P6 project name on screen and in the PDF, Word and Excel reports. Leave it empty to use the name in the P6 file.">
      <span>Report name</span>
      <input class="rn-input" type="text" maxlength="120" spellcheck="false" placeholder="${attr(p6 || 'Name shown on the report')}" value="${attr(r.report_name || '')}">
      <em class="rn-hint">press Enter to apply</em></label>`;
}

async function save(input) {
  const r = state.currentResult;
  if (!r) return;
  const name = input.value.replace(/\s+/g, ' ').trim();
  input.value = name;
  if (name === (r.report_name || '')) return;
  if (r.p6_project_name === undefined) r.p6_project_name = r.project_name || '';
  r.report_name = name;
  r.project_name = name || r.p6_project_name;
  try {
    if (state.currentSnapshotId) {
      await fetch(`http://localhost:${window.__SERVER_PORT__}/api/report-name`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ snapshot_id: state.currentSnapshotId, name }),
      });
    }
  } catch { /* the name still applies to this session's reports */ }
  if (rerender) { try { rerender(); } catch { /* the name shows on the next open of the view */ } }
}

document.addEventListener('change', (e) => {
  if (e.target && e.target.classList && e.target.classList.contains('rn-input')) save(e.target);
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && e.target && e.target.classList && e.target.classList.contains('rn-input')) e.target.blur();
});
