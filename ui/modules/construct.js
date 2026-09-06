// Constructability Review — rule-based, offline, powered by the local Knowledge
// Base (Decision 009). No AI, no key, no cost. Runs when the tab is opened.
// Reuses the approved review-report layout (.ai-* styles) and the shared helpers.

import { state }                                    from './state.js';
import { showError, clearError }                    from './render.js';
import { escapeHtml }                               from './format.js';
import { showReportContentsPreview }                from './preview.js';
import { showDatabase }                             from './database.js';

function _typeSelect(report) {
  const cur = report.detected ? report.detected.type : '';
  const opts = (report.available_types || []).map(t =>
    `<option value="${escapeHtml(t.type)}" ${t.type === cur ? 'selected' : ''}>${escapeHtml(t.category)} › ${escapeHtml(t.type)}</option>`).join('');
  return `<select id="ct-type" class="ct-select"><option value="">— auto-detect —</option>${opts}</select>`;
}

// Type dropdown with a caller-chosen id, pre-selected to the detected type (used
// by the "Add to Database" EPS picker so the user confirms/changes the filing).
function _typeSelectFor(report, id) {
  const cur = state.constructForcedType || (report.detected ? report.detected.type : '');
  const opts = (report.available_types || []).map(t =>
    `<option value="${escapeHtml(t.type)}" ${t.type === cur ? 'selected' : ''}>${escapeHtml(t.category)} › ${escapeHtml(t.type)}</option>`).join('');
  return `<select id="${id}" class="ct-select">${opts}</select>`;
}

// ── report + prompt rendering ──────────────────────────────────────────────

// ── Evidence-graded output (R1–R7) rendered ON SCREEN — same data as the PDF ──
const _SEV_DISP = { strong: 'Strong', moderate: 'Moderate', weak: 'Low', insufficient: 'Low' };
const _SEV_HEX = { strong: '#dc2626', moderate: '#d97706', weak: '#64748b', insufficient: '#94a3b8' };
const _BAND_HEX2 = { green: '#16a34a', amber: '#d97706', orange: '#ea580c', red: '#dc2626' };

function _sevChip(s) {
  const h = _SEV_HEX[s] || '#64748b';
  return `<span class="v2chip" style="background:${h}1a;color:${h};border-color:${h}55">${_SEV_DISP[s] || s}</span>`;
}

function _v2RiskSummary(report) {
  const a = report.archetype || {}, s = report.v2_score, fs = report.v2_findings || [];
  if (!s && !a.archetype) return '';
  const conf = (a.confidence || 'low'), cap = conf.charAt(0).toUpperCase() + conf.slice(1);
  const hb = _BAND_HEX2[s ? s.band : ''] || '#64748b';
  const bys = (s && s.by_strength) || {}, low = (bys.weak || 0) + (bys.insufficient || 0);
  const sp = []; if (bys.strong) sp.push(`${bys.strong} Strong`); if (bys.moderate) sp.push(`${bys.moderate} Moderate`); if (low) sp.push(`${low} Low`);
  const calc = s ? `<details class="v2calc"><summary>How is this score calculated?</summary>
    <div class="v2calcb">Independent of project size — it uses finding-severity <b>density</b>, not a flat subtraction.<br>
    Severity points per <b>finding</b> (never per activity): Strong 10 · Moderate 5 · Low 2.<br>
    Weighted density = (Σ points ÷ total activities) × 100 · Risk Score = 100 − density (clamped 0–100).<br>
    This project: ${s.total_severity_points} point(s) ÷ ${s.total_activities} activities × 100 = ${s.weighted_finding_density} → <b>${s.overall}</b>/100.</div></details>` : '';
  return `<div class="v2sec">
    <div class="v2h">Project Risk Summary</div>
    <div class="v2prs">
      <div class="v2row"><span class="v2k">Project Type</span><b>${escapeHtml(a.archetype_name || a.archetype || '—')}</b>
        <span class="v2k">Confidence</span>${_confChip(conf, cap)}</div>
      <div class="v2legend"><span class="v2lt">Confidence</span> <b>High</b> strong &amp; consistent evidence · <b>Medium</b> some ambiguity remains · <b>Low</b> limited / conflicting</div>
      <div class="v2hero"><span class="v2num" style="color:${hb}">${s ? s.overall : '—'}</span><span class="v2den">/ 100</span>
        <span class="v2band" style="color:${hb}">${s ? escapeHtml(s.band_label) : ''}</span><span class="v2lbl">Constructability Risk Score</span></div>
      <div class="v2legend"><span class="v2lt">Score</span> 80–100 Low Risk · 60–79 Moderate · 40–59 Significant · 0–39 High</div>
      ${calc}
      <div class="v2row"><span class="v2k">Total findings</span><b>${fs.length}</b>
        <span class="v2k">Severity</span><span>${sp.join(' · ') || 'none'}</span></div>
      ${_v2Coverage(report.v2_coverage, fs.length)}
    </div></div>`;
}

function _v2Coverage(cov, nFindings) {
  if (!cov) return '';
  const sys = (cov.systems || []).length;
  const line = `<div class="v2cov">Analysed <b>${cov.activities}</b> activities · <b>${cov.relationships}</b> `
    + `relationships · <b>${cov.classified}</b> classified into <b>${sys}</b> system(s) · all 7 constructability checks run</div>`;
  const clean = (nFindings === 0)
    ? `<div class="v2clean">✓ No sequencing risks found — the schedule is well-linked and correctly `
      + `sequenced for the systems present. A clean result here means the logic is sound, not that nothing was checked.</div>`
    : '';
  return line + clean;
}

function _confChip(conf, cap) {
  const h = { high: '#16a34a', medium: '#d97706', low: '#64748b' }[conf] || '#64748b';
  return `<span class="v2chip" style="background:${h}1a;color:${h};border-color:${h}55">${cap}</span>`;
}

function _v2Logic(primary) {
  if (!primary || !primary.id) return '—';
  const preds = primary.preds || [], succs = primary.succs || [];
  let c = '';
  if (preds.length) { const p = preds[0]; c += `<span class="v2mono">${escapeHtml(p.id)}</span> ${escapeHtml(p.name)} <span class="v2rt">${escapeHtml(p.type)}${p.lag ? ' ' + escapeHtml(p.lag) : ''}</span> → `; }
  c += `<b><span class="v2mono">${escapeHtml(primary.id)}</span> ${escapeHtml(primary.name)}</b>`;
  if (succs.length) { const s = succs[0]; c += ` <span class="v2rt">${escapeHtml(s.type)}${s.lag ? ' ' + escapeHtml(s.lag) : ''}</span> → <span class="v2mono">${escapeHtml(s.id)}</span> ${escapeHtml(s.name)}`; }
  return c;
}

function _relList(rels) {
  if (!rels || !rels.length) return '<span class="v2mut">— none —</span>';
  return rels.map(r => `<span class="v2mono">${escapeHtml(r.id)}</span> ${escapeHtml(r.name)} <span class="v2rt">${escapeHtml(r.type)}</span>${r.lag ? ' <b>' + escapeHtml(r.lag) + '</b>' : ''}`).join('<br>');
}

function _p6Table(p6) {
  if (!p6 || !p6.length) return '';
  const rows = p6.map(c => `<tr><td class="v2mono">${escapeHtml(c.id)}</td>
    <td>${escapeHtml(c.name)}<div class="v2mut">${escapeHtml(c.phase || '')}${c.system ? ' · ' + escapeHtml(c.system) : ''}</div></td>
    <td>${_relList(c.preds)}</td><td>${_relList(c.succs)}</td></tr>`).join('');
  return `<table class="v2p6"><thead><tr><th>Activity ID</th><th>Activity</th>
    <th>Current predecessor · type · lag</th><th>Current successor · type · lag</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function _v2Findings(report) {
  const fs = report.v2_findings || [];
  const head = `<div class="v2h">Constructability Findings</div>`;
  if (!fs.length) {
    return `<div class="v2sec">${head}<div class="v2empty">No constructability sequencing risks were detected against the current schedule logic.</div></div>`;
  }
  let rows = '';
  fs.forEach((f, i) => {
    const p6 = f.p6 || [], primary = p6[0] || {};
    const ids = p6.length ? p6.map(c => `<span class="v2mono">${escapeHtml(c.id)}</span>`).join('<br>') : '—';
    const names = p6.map(c => escapeHtml(c.name)).join('<br>');
    const rec = f.recommended_sequence || f.recommendation || '';
    const sup = f.support || {};
    const supln = sup.label ? `<div class="v2fw"><span class="v2fwl">Knowledge Support:</span> <span class="v2sup">${escapeHtml(sup.label)}</span></div>` : '';
    const fwe = `<div class="v2fw"><span class="v2fwl">Finding:</span> ${escapeHtml(f.title)}</div>
      <div class="v2fw"><span class="v2fwl">Why:</span> ${escapeHtml(f.reason)}</div>
      <div class="v2fw"><span class="v2fwl">Evidence:</span> ${escapeHtml(f.existing)}</div>${supln}`;
    const imp = (f.score_impact != null) ? `−${f.score_impact}` : '—';
    rows += `<tr class="v2frow">
      <td>${i + 1}</td><td>${ids}</td><td>${names}</td>
      <td class="v2logic">${_v2Logic(primary)}</td><td class="v2fwe">${fwe}</td>
      <td>${_sevChip(f.strength)}</td><td class="v2rec">${escapeHtml(rec)}</td><td class="v2mono v2imp">${imp}</td></tr>
      <tr class="v2detrow"><td></td><td colspan="7">
        <details class="v2det"><summary>P6 traceability &amp; current vs recommended</summary>
          <div class="v2cmp"><span class="v2ck">Current P6 Logic</span><span>${_v2Logic(primary)}</span></div>
          <div class="v2cmp"><span class="v2ck rec">Recommended Sequence</span><span><b>${escapeHtml(rec)}</b></span></div>
          ${_p6Table(p6)}</details></td></tr>`;
  });
  return `<div class="v2sec">${head}
    <table class="v2tbl"><thead><tr><th>#</th><th>Activity ID</th><th>Activity Name</th>
      <th>Current P6 Logic</th><th>Finding / Why / Evidence</th><th>Severity</th><th>Recommendation</th><th>Score Impact</th></tr></thead>
      <tbody>${rows}</tbody></table>
    <div class="v2legend"><span class="v2lt">Severity</span> ${_sevChip('strong')} significant execution / constructability risk ·
      ${_sevChip('moderate')} meaningful sequencing concern · ${_sevChip('weak')} minor or lower-impact concern</div>
    <div class="v2note">Every finding is raised solely from the current XER's own schedule logic; supporting knowledge is corroboration only. Open a row for the full P6 predecessors, successors, relationship types and lags.</div></div>`;
}

function renderReport(report) {
  const body = document.getElementById('construct-body');
  if (!body) return;
  if (!report.detected) { renderPick(report); return; }
  const draft = (report.detected.status === 'draft')
    ? '<span class="ct-draft" title="Starter knowledge — confirm before relying on it">draft KB</span>' : '';
  body.innerHTML = `
    <div class="ai-filebar">
      <div class="fb"><span class="k">Detected project sub-type</span>
        <span class="v ai-type">${escapeHtml(report.project_type)}</span> ${draft}</div>
      <div class="fb"><span class="k">Engine</span><span class="v">Rule + Knowledge Base · offline</span></div>
      ${report.knowledge_enhanced ? `<div class="fb"><span class="k">Knowledge</span>
        <span class="v ai-enh" title="Checking against the standard plus what the tool learned from schedules you added for this type">✦ Standard + your ${(report.learned && report.learned.imports) || 0} schedule(s)</span></div>` : ''}
      <div class="fb"><span class="k">Change sub-type</span>${_typeSelect(report)}</div>
    </div>
    <div class="ai-banner"><span class="spark">🧠</span>
      <span class="txt"><b>Findings from the local Knowledge Base + rule checks — offline, no AI, no cost.</b>
      Advisory: review before acting; it never changes your schedule. Kept separate from the exact rule-based audits.</span></div>

    <div class="xd-exportbar">
      <button class="btn-secondary" id="cx-adddb">➕ Add to Database</button>
      <button class="btn-secondary" id="cx-xls">📊 Export Excel</button>
      <button class="btn-primary" id="cx-pdf">📄 Print Preview</button>
    </div>
    <div class="cx-kb" id="cx-kb">
      <span class="cx-kb-info" id="cx-kb-info">Knowledge Base…</span>
      <button class="btn-secondary" id="cx-kb-manage">📚 Manage Knowledge Base</button>
      <span class="cx-kb-note">Supporting knowledge only · never changes a finding · add projects in the Knowledge Base</span>
    </div>
    <div class="cx-eps hidden" id="cx-eps-row">
      <label for="cx-eps-select">Add this schedule to the Database under (EPS):</label>
      ${_typeSelectFor(report, 'cx-eps-select')}
      <button class="btn-primary" id="cx-eps-save">Save to Database</button>
      <span id="cx-eps-note" class="cx-eps-note"></span>
    </div>

    ${_v2RiskSummary(report)}
    ${_v2Findings(report)}`;
    // The Constructability Review is ONE engine, ONE score — the two sections above.
    // The legacy KB-standard dashboard / illogical / missing / WBS / conclusion (a
    // second, contradictory score) is intentionally not shown (Ibrahim's V1 spec:
    // only two sections; no repeated/duplicate information).

  const sel = document.getElementById('ct-type');
  if (sel) sel.addEventListener('change', () => fetchAndRender(sel.value || null));
  const pdf = document.getElementById('cx-pdf');
  if (pdf) pdf.addEventListener('click', () => previewReport(pdf));
  const xls = document.getElementById('cx-xls');
  if (xls) xls.addEventListener('click', () => exportReport('excel', xls));
  const adb = document.getElementById('cx-adddb');
  if (adb) adb.addEventListener('click', () => {
    document.getElementById('cx-eps-row')?.classList.toggle('hidden');
  });
  const save = document.getElementById('cx-eps-save');
  if (save) save.addEventListener('click', () => {
    const s = document.getElementById('cx-eps-select');
    addToDatabase((s && s.value) || null, save);
  });
  const kbm = document.getElementById('cx-kb-manage');
  if (kbm) kbm.addEventListener('click', () => showDatabase());
  kbKnowledgeRefresh();
}

function _kbInfoText(d) {
  return `Planning Knowledge Engine: ${d.projects_learned} project(s) learned · `
    + `${d.pattern_count} generalized pattern(s)`
    + (d.raw_projects && d.raw_projects.length ? ` · ${d.raw_projects.length} raw XER(s) kept` : '');
}

async function kbKnowledgeRefresh() {
  const info = document.getElementById('cx-kb-info');
  if (!info) return;
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/kb/knowledge`);
    const d = await resp.json();
    if (d.ok) info.textContent = _kbInfoText(d);
  } catch { /* leave default text */ }
}

function previewReport(btn) {
  const rep = state.constructReport;
  if (!rep || !rep.detected) return;
  const slug = (rep.detected.type || 'constructability').replace(/[^\w]+/g, '_').replace(/^_+|_+$/g, '');
  // The Global Print-Preview framework drives the whole overlay: it loads the Report
  // Contents list, lets the user pick/reorder sections, live-previews the exact
  // document, and saves the PDF / prints the identical document (Preview == PDF == Print).
  showReportContentsPreview({
    feature: 'constructability',
    report: rep,
    title: 'Constructability Review — report',
    subtitle: rep.project_type || '',
    serverPort: state.serverPort,
    choosePath: () => window.pywebview.api.choose_save_path(`${slug}_constructability.pdf`, 'pdf'),
    onError: (msg) => showError(msg),
  });
}

async function addToDatabase(type, btn) {
  const rep = state.constructReport;
  const note = document.getElementById('cx-eps-note');
  if (!rep || (!state.currentXmlPath && !state.currentCachedPath)) return;
  if (!type) { if (note) { note.textContent = 'Pick a project type first.'; note.className = 'cx-eps-note warn'; } return; }
  const orig = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  if (note) { note.textContent = ''; note.className = 'cx-eps-note'; }
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/database/add`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        xml_path: state.currentXmlPath, cached_path: state.currentCachedPath, forced_type: type,
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      showError(data.error || 'Could not add to the Construction Database.');
      if (note) { note.textContent = data.error || 'Failed.'; note.className = 'cx-eps-note warn'; }
    } else {
      state.dbLibrary = null;   // force the Database + learned views to reload
      if (note) {
        note.textContent = `✓ Added to ${data.type} — ${data.activities} activities. It now also teaches the tool this project type.`;
        note.className = 'cx-eps-note ok';
      }
    }
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = orig; }
  }
}

async function exportReport(kind, btn) {
  const rep = state.constructReport;
  if (!rep || !rep.detected) return;
  const slug = (rep.detected.type || 'constructability').replace(/[^\w]+/g, '_').replace(/^_+|_+$/g, '');
  const ext = kind === 'pdf' ? 'pdf' : 'xlsx';
  let path = null;
  try { path = await window.pywebview.api.choose_save_path(`${slug}_constructability.${ext}`, ext); }
  catch { showError('Could not open the save dialog.'); return; }
  if (!path) return;
  const orig = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try {
    const url = kind === 'pdf' ? '/api/constructability/report' : '/api/constructability/excel';
    const resp = await fetch(`http://localhost:${state.serverPort}${url}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report: rep, output_path: path }),
    });
    const data = await resp.json();
    if (!data.ok) showError(data.error || 'Export failed.');
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = orig; }
  }
}

function renderPick(report) {
  const body = document.getElementById('construct-body');
  if (!body) return;
  body.innerHTML = `
    <div class="ai-prompt">
      <div class="ai-prompt-t">Pick the project type to review against</div>
      <div class="ai-prompt-d">${escapeHtml(report.conclusion || 'Choose the sub-type from the Knowledge Base.')}</div>
      <div class="ct-pickrow">${_typeSelect(report)}
        <button class="btn-primary" id="ct-go">Review</button></div>
    </div>`;
  const go = document.getElementById('ct-go');
  if (go) go.addEventListener('click', () => {
    const sel = document.getElementById('ct-type');
    fetchAndRender((sel && sel.value) || null);
  });
}

async function fetchAndRender(forcedType) {
  const body = document.getElementById('construct-body');
  if (!state.currentXmlPath && !state.currentCachedPath) {
    if (body) body.innerHTML = '<p class="ai-empty">Open a schedule first, then the Constructability Review runs automatically.</p>';
    return;
  }
  clearError();
  if (body) body.innerHTML = '<div class="cmp-loading">Reviewing against the Knowledge Base…</div>';
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/constructability`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        xml_path: state.currentXmlPath, cached_path: state.currentCachedPath,
        forced_type: forcedType || null,
      }),
    });
    const data = await resp.json();
    if (!data.ok) { showError(data.error || 'Constructability review failed.'); return; }
    state.constructReport = data.report;
    state.constructForcedType = forcedType || null;
    renderReport(data.report);
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  }
}

export function renderConstructPanel() {
  if (state.constructReport) { renderReport(state.constructReport); return; }
  fetchAndRender(state.constructForcedType || null);
}
