import { state }                                                  from './state.js';
import { setLoading, showError, clearError, renderResults, renderHistory } from './render.js';
import { evmInputs }                                             from './evm.js';
import { showReportPreview }                                     from './preview.js';
import { getSavedMode }                                          from './appearance.js';

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
    state.compareReport      = null;   // a new schedule invalidates any prior comparison
    state.compareBaselineName = null;
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
    state.compareReport      = null;   // a different project invalidates any prior comparison
    state.compareBaselineName = null;
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

export async function exportExcel(btnId = 'excel-btn') {
  if (!state.currentSnapshotId || !state.currentModule) { showError('Open a schedule and pick a module first.'); return; }
  const _el = document.getElementById(btnId);
  const btn = new ButtonState(_el, _el ? _el.textContent : 'Export to Excel');
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

// Re-render the preview HTML for a newly-picked appearance mode (used by the shared preview
// modal's Appearance picker). Returns the report HTML string for the given theme.
function _previewFetcher(route, reqBody) {
  return async (theme) => {
    const data = await apiFetch(route, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ ...reqBody, preview: true, theme }),
    });
    if (!data.ok || !data.html) throw new Error(data.error || 'no content');
    return data.html;
  };
}

export async function generateModulePdf(btnId = 'pdf-btn-audit') {
  if (!state.currentSnapshotId || !state.currentModule) { showError('Open a schedule and pick a module first.'); return; }
  const _el = document.getElementById(btnId);
  const btn = new ButtonState(_el, _el ? _el.textContent : 'Generate PDF');
  btn.loading('Preparing preview…');
  const module = state.currentModule;
  const reqBody = { snapshot_id: state.currentSnapshotId, module, meta: moduleMeta() };

  // Summary PDF: send the health the screen is CURRENTLY showing so the PDF matches
  // exactly (incl. a Milestone Check the user just entered), plus the completion float
  // (from the CPLI module) for the headline stat.
  if (module === '__summary__' && state.currentModules) {
    reqBody.health = state.currentModules.health || null;
    const ck = ((state.currentModules.modules || {}).cpli || {}).kpis || {};
    reqBody.completion_float = ck.project_total_float_days;
  }

  // Report-content selector — the sections this check exposes + the remembered choice.
  // Fully generic: ANY module that carries a presentation.sections list gets the picker,
  // so every current and future feature inherits it automatically.
  const mod = (state.currentModules && state.currentModules.modules && state.currentModules.modules[module]) || {};
  let sections;
  if (module === '__summary__') {
    // The Summary is the roll-up, not a module, so it carries no presentation —
    // give it its own component registry so it inherits the picker like every check.
    const sh = (state.currentModules && state.currentModules.health) || {};
    const noAreas = !(((sh.problem_areas || {}).areas) || []).length;
    const noFixes = !((sh.fix_first) || []).length;
    sections = [
      { key: 'overview',    label: 'Overall score & verdict',       empty: false },
      { key: 'checks',      label: 'Checks status (donut)',         empty: false },
      { key: 'headline',    label: 'Headline stats',                empty: false },
      { key: 'composition', label: 'Sub-feature scores × weights',  empty: false },
      { key: 'problems',    label: 'Where the problems are',        empty: noAreas },
      { key: 'fixes',       label: 'Fix these first',               empty: noFixes },
      { key: 'conclusion',  label: 'Conclusion',                    empty: false },
    ];
  } else {
    const useSelector = mod.presentation && Array.isArray(mod.presentation.sections);
    sections = useSelector ? mod.presentation.sections : null;
  }
  const storageKey = `p6_report_sections_${module}`;
  let selected = sections ? sections.filter(s => !s.empty).map(s => s.key) : null;
  if (sections) { try { const saved = JSON.parse(localStorage.getItem(storageKey) || 'null'); if (Array.isArray(saved)) selected = saved; } catch { /* default */ } }

  const mode = getSavedMode();                        // the saved appearance mode (one of the 6)
  const fetchPreview = async (keys, theme) => {
    const data = await apiFetch('api/report/module', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ ...reqBody, preview: true, sections: keys || undefined, theme: theme || mode }),
    });
    return (data.ok && data.html) ? data.html : null;
  };

  try {
    const html = await fetchPreview(selected, mode);
    btn.reset();
    if (!html) { showError('Preview failed — please retry.'); return; }
    showReportPreview({
      title: 'Report — Schedule Health Review', subtitle: mod.name || module, html,
      sections, selected, storageKey, initialMode: mode,
      onRerender:    (keys, theme) => fetchPreview(keys, theme),
      onThemeChange: (theme, keys) => fetchPreview(keys, theme),
      onSave: (m, keys) => _savePdf('api/report/module', { ...reqBody, theme: m, sections: keys }, `${module}_report.pdf`, 'pdf'),
    });
  } catch {
    showError('Preview failed. Check the schedule and try again.');
    btn.reset();
  }
}

// Shared "Save as PDF" from a preview: pick a path, POST the same body with output_path.
// Returns true on success (preview closes), false if the user cancelled or it failed.
async function _savePdf(route, reqBody, defaultName, ext) {
  const outputPath = await window.pywebview.api.choose_save_path(defaultName, ext);
  if (!outputPath) return false;
  const data = await apiFetch(route, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ ...reqBody, output_path: outputPath }),
  });
  if (!data.ok) { showError(`PDF generation failed: ${data.error}`); return false; }
  return true;
}

function _evmReportBody() {
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
  return {
    xml_path: state.currentXmlPath, cached_path: state.currentCachedPath,
    baseline_path: state.baselinePath || null,
    meta, weights: inputs.weights, actual_cost: inputs.actualCost,
    dimension: inputs.gap && inputs.gap.dimension, engineering,
  };
}

export async function exportCalendarExcel() {
  if (!state.currentSnapshotId) { showError('Open a schedule first.'); return; }
  const btn = new ButtonState(document.getElementById('cal-excel-btn'), 'Export to Excel');
  btn.loading('Exporting…');
  try {
    const outputPath = await window.pywebview.api.choose_save_path('calendar_audit.xlsx', 'xlsx');
    if (!outputPath) { btn.reset(); return; }
    const data = await apiFetch('api/export/calendar_excel', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ snapshot_id: state.currentSnapshotId, output_path: outputPath }),
    });
    if (!data.ok) { showError(`Excel export failed: ${data.error}`); btn.reset(); }
    else          { btn.success('✓ Excel Saved'); }
  } catch {
    showError('Excel export failed. Check the output path and try again.');
    btn.reset();
  }
}

// ── Calendar Audit — weather / location / settings ────────────────────────
export async function geocodePlace(q) {
  try {
    return await apiFetch('api/geocode', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q }),
    });
  } catch { return { ok: false, error: 'offline' }; }
}

// Reverse-geocode a dropped/dragged pin → a friendly place name.
export async function reverseGeocode(lat, lon) {
  try {
    return await apiFetch('api/geocode', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lon }),
    });
  } catch { return { ok: false, error: 'offline' }; }
}

export async function computeWeather(lat, lon, placeName, thresholds) {
  return apiFetch('api/weather', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      snapshot_id: state.currentSnapshotId, xml_path: state.currentXmlPath,
      cached_path: state.currentCachedPath, lat, lon, place_name: placeName,
      thresholds: thresholds || null,
    }),
  });
}

export async function saveCalendarSettings(patch) {
  return apiFetch('api/calendar/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      snapshot_id: state.currentSnapshotId, xml_path: state.currentXmlPath,
      cached_path: state.currentCachedPath, ...patch,
    }),
  });
}

// Which Calendar Audit sections to print — from the section-picker checkboxes.
// Returns null (all sections) unless the user has unticked at least one.
function _calendarSections() {
  const cbs = [...document.querySelectorAll('.cal-sec-cb')];
  if (!cbs.length) return null;
  const on = cbs.filter(c => c.checked).map(c => c.value);
  return on.length === cbs.length ? null : on;
}

export async function generateCalendarPdf() {
  if (!state.currentSnapshotId) { showError('Open a schedule first.'); return; }
  const btn = new ButtonState(document.getElementById('cal-pdf-btn'), 'Generate Calendar Audit PDF');
  btn.loading('Preparing preview…');
  const reqBody = { snapshot_id: state.currentSnapshotId, meta: moduleMeta(), sections: _calendarSections() };
  const mode = getSavedMode();
  try {
    const data = await apiFetch('api/report/calendar', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ ...reqBody, preview: true, theme: mode }),
    });
    btn.reset();
    if (!data.ok || !data.html) { showError(`Preview failed: ${data.error || 'no content'}`); return; }
    showReportPreview({
      title: 'Calendar Audit preview', subtitle: reqBody.meta.source_file, html: data.html, initialMode: mode,
      onThemeChange: _previewFetcher('api/report/calendar', reqBody),
      onSave: (m) => _savePdf('api/report/calendar', { ...reqBody, theme: m }, 'Calendar_Audit.pdf', 'pdf'),
    });
  } catch {
    showError('Preview failed. Check the schedule and try again.');
    btn.reset();
  }
}

export async function generatePdf() {
  if (!state.currentXmlPath && !state.currentCachedPath) return;
  const btn = new ButtonState(document.getElementById('pdf-btn'), 'Generate EVM PDF');
  btn.loading('Preparing preview…');
  const reqBody = _evmReportBody();
  const mode = getSavedMode();
  try {
    // Preview first — render the report HTML and show it fitted before writing any PDF.
    const data = await apiFetch('api/report/evm', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ ...reqBody, preview: true, theme: mode }),
    });
    btn.reset();
    if (!data.ok || !data.html) { showError(`Preview failed: ${data.error || 'no content'}`); return; }
    showReportPreview({
      title: 'EVM report preview', subtitle: reqBody.meta.source_file, html: data.html, initialMode: mode,
      onThemeChange: _previewFetcher('api/report/evm', reqBody),
      onSave: (m) => _savePdf('api/report/evm', { ...reqBody, theme: m }, 'EVM_report.pdf', 'pdf'),
    });
  } catch {
    showError('Preview failed. Check the schedule and try again.');
    btn.reset();
  }
}
