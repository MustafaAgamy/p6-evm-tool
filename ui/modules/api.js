import { state }                                                  from './state.js';
import { setLoading, showError, clearError, renderResults, renderHistory } from './render.js';
import { evmInputs }                                             from './evm.js';

async function apiFetch(path, options) {
  const resp = await fetch(`http://localhost:${state.serverPort}/${path}`, options);
  if (!resp.ok) throw new Error(`Server error ${resp.status}`);
  return resp.json();
}

// showSpinner: show the browse-card spinner (true for Browse/drag-drop, false for history opens)
export async function importFile(filePath, { showSpinner = true } = {}) {
  clearError();
  if (showSpinner) setLoading(true);
  try {
    const data = await apiFetch('api/parse', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ path: filePath, overrides_path: null }),
    });
    if (!data.ok) { showError(data.error || 'Parse failed.'); return; }
    state.currentResult      = data.result;
    state.currentXmlPath     = filePath;
    state.currentCachedPath  = data.cached_path || null;
    state.currentSnapshotId  = data.snapshot_id || null;
    renderResults(data.result, filePath, { previousImport: data.previous_import || null });
    await loadHistory();
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (showSpinner) setLoading(false);
  }
}

export async function loadHistory() {
  try {
    const history = await apiFetch('api/history');
    renderHistory(history);
  } catch {
    // Non-fatal — table stays as-is
  }
}

class ButtonState {
  constructor(el, idleText) { this.el = el; this.idleText = idleText; }
  loading(text)               { this.el.disabled = true;  this.el.textContent = text; }
  reset()                     { this.el.disabled = false; this.el.textContent = this.idleText; }
  success(text, delay = 2500) { this.el.textContent = text; setTimeout(() => this.reset(), delay); }
}

export async function loadProject(projectId, filePath, cachedPath) {
  clearError();
  try {
    const data = await apiFetch('api/project/load', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ project_id: projectId }),
    });
    if (!data.ok) { showError(data.error || 'Load failed.'); return; }
    state.currentResult      = data.result;
    state.currentXmlPath     = filePath   || data.original_path || '';
    state.currentCachedPath  = cachedPath || data.cached_path   || null;
    state.currentSnapshotId  = data.snapshot_id || null;
    renderResults(data.result, state.currentXmlPath || cachedPath || '');
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  }
}

export async function deleteProject(projectId) {
  return apiFetch('api/project/delete', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ project_id: projectId }),
  });
}

function moduleMeta() {
  const r = state.currentResult || {};
  const file = (state.currentXmlPath || '').split(/[\\/]/).pop();
  return {
    project_name: r.project_name || 'Schedule',
    data_date:    r.data_date || '',
    source_file:  file,
    report_date:  new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }),
  };
}

export async function exportExcel() {
  if (!state.currentSnapshotId || !state.currentModule) { showError('Open a schedule and pick a module first.'); return; }
  const btn = new ButtonState(document.getElementById('excel-btn'), 'Export Module to Excel');
  btn.loading('Exporting…');
  try {
    const outputPath = await window.pywebview.api.choose_save_path(`${state.currentModule}_findings.xlsx`, 'xlsx');
    if (!outputPath) { btn.reset(); return; }
    const data = await apiFetch('api/export/excel', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ snapshot_id: state.currentSnapshotId, module: state.currentModule, output_path: outputPath }),
    });
    if (!data.ok) { showError(`Excel export failed: ${data.error}`); btn.reset(); }
    else          { btn.success('✓ Excel Saved'); }
  } catch {
    showError('Excel export failed. Check the output path and try again.');
    btn.reset();
  }
}

export async function generateModulePdf() {
  if (!state.currentSnapshotId || !state.currentModule) { showError('Open a schedule and pick a module first.'); return; }
  const btn = new ButtonState(document.getElementById('pdf-btn-audit'), 'Generate Module PDF');
  btn.loading('Generating…');
  try {
    const outputPath = await window.pywebview.api.choose_save_path(`${state.currentModule}_report.pdf`, 'pdf');
    if (!outputPath) { btn.reset(); return; }
    const data = await apiFetch('api/report/module', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ snapshot_id: state.currentSnapshotId, module: state.currentModule,
                                output_path: outputPath, meta: moduleMeta() }),
    });
    if (!data.ok) { showError(`PDF generation failed: ${data.error}`); btn.reset(); }
    else          { btn.success('✓ PDF Saved'); }
  } catch {
    showError('PDF generation failed. Check the output path and try again.');
    btn.reset();
  }
}

export async function generatePdf() {
  if (!state.currentXmlPath && !state.currentCachedPath) return;
  const btn = new ButtonState(document.getElementById('pdf-btn'), 'Generate EVM PDF');
  btn.loading('Generating…');
  try {
    const outputPath = await window.pywebview.api.choose_save_path('EVM_report.pdf');
    if (!outputPath) { btn.reset(); return; }

    const r = state.currentResult || {};
    const inputs = evmInputs();
    // Engineering for the PDF: E1 rows if uploaded, else the P6 rows as-is — the
    // report renders the four P6 columns (Planned/Actual SUB, Planned/Actual APP) itself.
    let engineering = null;
    if (r.engineering_e1 && r.engineering_e1.length) {
      engineering = { mode: 'E1', rows: r.engineering_e1 };
    } else if (r.engineering_p6 && r.engineering_p6.length) {
      engineering = { mode: 'P6', rows: r.engineering_p6 };
    }
    const meta = {
      project_name: r.project_name || 'Schedule', data_date: (r.data_date || '').slice(0, 10),
      report_date: new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }),
      source_file: (state.currentXmlPath || '').split(/[\\/]/).pop(),
      baseline_finish: r.baseline_finish, expected_finish: r.expected_finish,
    };
    const data = await apiFetch('api/report/evm', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        xml_path: state.currentXmlPath, cached_path: state.currentCachedPath, output_path: outputPath,
        baseline_path: state.baselinePath || null,
        meta, weights: inputs.weights, actual_cost: inputs.actualCost,
        dimension: inputs.gap && inputs.gap.dimension, engineering,
      }),
    });
    if (!data.ok) { showError(`PDF generation failed: ${data.error}`); btn.reset(); }
    else          { btn.success('✓ EVM PDF Saved'); }
  } catch {
    showError('PDF generation failed. Check the output path and try again.');
    btn.reset();
  }
}
