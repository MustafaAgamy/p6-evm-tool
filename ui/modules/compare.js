// Consultant Review — Baseline vs Current Update.
// The update is the currently-open schedule; the user picks a baseline to compare
// against. Renders the driving logic/lag change table, the duration table, the
// change summary and milestone finishes. (Before/after impact, the three-way
// S-curve and the corrected but-for XML arrive in the next slice.)

import { state }             from './state.js';
import { showError, clearError } from './render.js';
import { escapeHtml }        from './format.js';
import { showReportPreview } from './preview.js';

// ── Pure helpers (unit-tested in tests/js/test_compare.js) ────────────────

// A relationship label: 'FS' when lag is 0, else 'FS+10' / 'SS-2' (working days, rounded).
export function fmtLag(type, lagDays) {
  const n = Math.round(lagDays || 0);
  if (!n) return type || 'FS';
  return `${type || 'FS'}${n > 0 ? '+' : ''}${n}`;
}

// Highlight class for a driving-link cell by its diff status.
export function statusClass(status) {
  return { added: 'cmp-add', removed: 'cmp-rem', changed: 'cmp-chg' }[status] || '';
}

// Change-summary pills from [{kind,label,count}].
export function summaryPills(items) {
  if (!items || !items.length) {
    return '<span class="mut">No logic, lag or duration changes vs the baseline.</span>';
  }
  return items.map(it =>
    `<span class="cmp-pill"><b>${it.count}</b> ${escapeHtml(it.label)}</span>`).join('');
}

// Signed working-day delta, e.g. '+3 d' / '−2 d' / '0 d'.
export function signedDays(n) {
  const v = Math.round((n || 0) * 10) / 10;
  if (v > 0) return `+${v} d`;
  if (v < 0) return `−${Math.abs(v)} d`;
  return '0 d';
}

// Suggested filename for the corrected but-for XML, from the update's file name.
export function suggestedCorrectedName(updateName) {
  const base = (updateName || 'update').replace(/\.[^.]+$/, '');
  return `${base}_but-for.xml`;
}

// ── Rendering ─────────────────────────────────────────────────────────────

function cellStack(list, key) {
  if (!list || !list.length) return '<span class="mut">—</span>';
  return list.map(l => {
    const val = key === 'rel' ? fmtLag(l.type, l.lag_days)
              : key === 'id' ? l.code : (l.name || '');
    const cls = statusClass(l.status);
    const inner = cls ? `<span class="cmp-pill ${cls}">${escapeHtml(String(val))}</span>`
                      : escapeHtml(String(val));
    const mark = (l.driving && key === 'id') ? '<span class="cmp-drv-dot" title="Driving link">▶</span>' : '';
    return `<div class="cmp-dl${l.driving ? ' cmp-driving' : ''}">${mark}${inner}</div>`;
  }).join('');
}

function _kpi(label, val) {
  return `<div class="kpi"><div class="k">${escapeHtml(label)}</div>` +
         `<div class="v">${escapeHtml(String(val))}</div></div>`;
}

function _durStatus(status) {
  const map = {
    extended: ['cmp-st-ext', 'Duration extended'],
    not_burning: ['cmp-st-burn', 'Not burning down'],
  };
  const [cls, label] = map[status] || ['cmp-st-ok', 'On track'];
  return `<span class="cmp-stbadge ${cls}">${label}</span>`;
}

function _logicTable(rows) {
  if (!rows || !rows.length) {
    return '<p class="cmp-empty">No driving relationship or lag changes vs the baseline.</p>';
  }
  const body = rows.map(r => `
    <tr>
      <td class="mono">${escapeHtml(r.activity_id)}</td>
      <td>${escapeHtml(r.activity_name)}</td>
      <td><span class="cmp-tag">${escapeHtml(r.change_label)}</span></td>
      <td class="sepL">${cellStack(r.baseline_preds, 'id')}</td><td>${cellStack(r.baseline_preds, 'rel')}</td><td>${cellStack(r.baseline_preds, 'name')}</td>
      <td>${cellStack(r.baseline_succs, 'id')}</td><td>${cellStack(r.baseline_succs, 'rel')}</td><td>${cellStack(r.baseline_succs, 'name')}</td>
      <td class="sepU">${cellStack(r.update_preds, 'id')}</td><td>${cellStack(r.update_preds, 'rel')}</td><td>${cellStack(r.update_preds, 'name')}</td>
      <td>${cellStack(r.update_succs, 'id')}</td><td>${cellStack(r.update_succs, 'rel')}</td><td>${cellStack(r.update_succs, 'name')}</td>
    </tr>`).join('');
  return `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-log">
    <thead>
      <tr><th rowspan="2">Activity ID</th><th rowspan="2">Activity name</th><th rowspan="2">Change</th>
        <th colspan="6" class="cmp-gh-base">Baseline — driving links</th>
        <th colspan="6" class="cmp-gh-upd">Update — driving links</th></tr>
      <tr><th class="sepL">Pred. ID</th><th>Pred. rel</th><th>Pred. name</th><th>Succ. ID</th><th>Succ. rel</th><th>Succ. name</th>
        <th class="sepU">Pred. ID</th><th>Pred. rel</th><th>Pred. name</th><th>Succ. ID</th><th>Succ. rel</th><th>Succ. name</th></tr>
    </thead>
    <tbody>${body}</tbody></table></div>
    <div class="cmp-foot">Every predecessor and successor relationship is read straight from the files. <b>▶ bold</b> = the driving link (date-derived; may be absent on completed activities). Red = changed vs baseline · green = added · struck = removed.</div>`;
}

function _durationTable(rows) {
  if (!rows || !rows.length) {
    return '<p class="cmp-empty">No duration or remaining changes vs the baseline.</p>';
  }
  const body = rows.map(r => `<tr>
    <td class="mono">${escapeHtml(r.activity_id)}</td><td>${escapeHtml(r.activity_name)}</td>
    <td class="num mut">${r.baseline_orig_days} d</td>
    <td class="num">${r.status === 'extended' ? `<span class="cmp-pill cmp-chg">${r.update_orig_days} d</span>` : `${r.update_orig_days} d`}</td>
    <td class="num">${r.remaining_days} d</td>
    <td class="num ${r.over_baseline ? 'cmp-over' : ''}">${signedDays(r.remaining_minus_baseline_days)}</td>
    <td>${_durStatus(r.status)}</td>
    <td>${_durImpact(r.impact)}</td></tr>`).join('');
  return `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-table">
    <thead><tr><th>Activity ID</th><th>Activity name</th><th class="num">Baseline orig.</th><th class="num">Update orig.</th><th class="num">Remaining</th><th class="num">Rem − baseline</th><th>Status</th><th>Impact on finish</th></tr></thead>
    <tbody>${body}</tbody></table></div>`;
}

// Impact of a duration change on the project finish, from the activity's P6 float.
export function durImpactLabel(impact) {
  return { Direct: 'Direct', Potential: 'Potential', None: 'Float absorbs', Unknown: '—' }[impact] || '—';
}
function _durImpact(impact) {
  const cls = { Direct: 'cmp-imp-direct', Potential: 'cmp-imp-pot', None: 'cmp-imp-none' }[impact] || 'cmp-imp-none';
  return `<span class="cmp-imp ${cls}">${escapeHtml(durImpactLabel(impact))}</span>`;
}

function _milestoneTable(rows) {
  if (!rows || !rows.length) {
    return '<p class="cmp-empty">No milestones matched between the two schedules.</p>';
  }
  const body = rows.map(m => `<tr><td class="mono">${escapeHtml(m.activity_id)}</td><td>${escapeHtml(m.name)}</td>
    <td class="mut">${escapeHtml(m.baseline_finish || '—')}</td><td>${escapeHtml(m.update_finish || '—')}</td></tr>`).join('');
  return `<div class="tblwrap"><table class="audit-table cmp-table"><thead><tr>
    <th>Milestone ID</th><th>Name</th><th>Baseline finish</th><th>Update finish</th></tr></thead>
    <tbody>${body}</tbody></table></div>`;
}

function _fileBar(report) {
  return `<div class="cmp-files">
    <span class="cmp-file"><span class="k">Baseline</span> <b>${escapeHtml(report.baseline_file || state.compareBaselineName || '—')}</b></span>
    <span class="cmp-vs">vs</span>
    <span class="cmp-file"><span class="k">Current update</span> <b>${escapeHtml(report.update_file || '—')}</b></span>
    <button class="btn-mini" id="cmp-change-baseline">Change baseline</button>
  </div>`;
}

// The report/impact currently ON SCREEN. Exports read these, not state.compareReport,
// which a background re-import nulls while the panel still shows the old results.
let _shownReport = null;
let _shownImpact = null;

export function renderCompareReport(report) {
  const body = document.getElementById('compare-body');
  if (!body) return;
  _shownReport = report;
  _shownImpact = null;   // a freshly-rendered report has no before/after loaded yet
  const dash = report.dashboard || {};
  const logic = report.logic || { rows: [], summary: {} };
  const durs = report.durations || { rows: [] };
  const cs = report.change_summary || { items: [] };
  const mismatch = (report.matched_activities === 0)
    ? `<div class="cmp-warn">No activities matched by ID between the two files — is this the right baseline for this update? Nothing changed can be detected until they line up.</div>`
    : '';
  body.innerHTML = `
    ${_fileBar(report)}
    <div class="cmp-exports">
      <button class="btn-secondary" id="cmp-export-pdf">Export PDF</button>
      <button class="btn-secondary" id="cmp-export-xlsx">Export Excel</button>
    </div>
    ${mismatch}
    <div class="mod-sec">Executive dashboard</div>
    <div class="cmp-kpis">
      ${_kpi('Changed activities', dash.changed_activities ?? 0)}
      ${_kpi('Baseline finish', report.baseline_finish || '—')}
      ${_kpi('Update finish', report.update_finish || '—')}
      ${_kpi('Data date', report.data_date || '—')}
    </div>
    <div class="mod-sec">Driving logic &amp; lag changes vs baseline</div>
    <div class="cmp-chgsum">
      <div class="cmp-chgsum-t">Total changed activities: <b>${logic.summary.changed_activities ?? 0}</b></div>
      <div class="cmp-pills">${summaryPills(cs.items)}</div>
    </div>
    ${_logicTable(logic.rows)}
    <div class="mod-sec">Duration &amp; remaining changes vs baseline</div>
    ${_durationTable(durs.rows)}
    <div class="mod-sec">Corrected but-for XML</div>
    ${_correctedSection(report)}`;
  const chg = document.getElementById('cmp-change-baseline');
  if (chg) chg.addEventListener('click', chooseBaselineAndCompare);
  const epdf = document.getElementById('cmp-export-pdf');
  if (epdf) epdf.addEventListener('click', exportComparePdf);
  const exls = document.getElementById('cmp-export-xlsx');
  if (exls) exls.addEventListener('click', exportCompareExcel);
  _wireCorrected();
}

// ── Exports (PDF + Excel) ───────────────────────────────────────────────────

function _shownReportOrWarn() {
  const report = state.compareReport || _shownReport;
  if (!report) { showError('Run the comparison first (pick a baseline), then export.'); return null; }
  return report;
}

async function _withBtn(id, idle, fn) {
  const btn = document.getElementById(id);
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try { await fn(); }
  finally { if (btn) { btn.disabled = false; btn.textContent = idle; } }
}

export async function exportComparePdf() {
  const report = _shownReportOrWarn();
  if (!report) return;
  const impact = state.compareImpact || _shownImpact || null;
  const url = `http://localhost:${state.serverPort}/api/compare/report`;
  await _withBtn('cmp-export-pdf', 'Export PDF', async () => {
    try {
      // Preview first — render the report HTML and show it fitted before writing any PDF.
      const resp = await fetch(url, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report, impact, preview: true }),
      });
      const data = await resp.json();
      if (!data.ok || !data.html) { showError(`Preview failed: ${data.error || 'no content'}`); return; }
      showReportPreview({
        title: 'Consultant Review preview',
        subtitle: report.project_name || 'Baseline vs Current Update',
        html: data.html,
        onSave: async () => {
          const outputPath = await window.pywebview.api.choose_save_path('consultant_review.pdf', 'pdf');
          if (!outputPath) return false;
          const r = await fetch(url, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ report, impact, output_path: outputPath }),
          });
          const d = await r.json();
          if (!d.ok) { showError(`PDF generation failed: ${d.error || 'unknown error'}`); return false; }
          return true;
        },
      });
    } catch {
      showError('Could not reach the local server to preview the PDF.');
    }
  });
}

export async function exportCompareExcel() {
  const report = _shownReportOrWarn();
  if (!report) return;
  const outputPath = await window.pywebview.api.choose_save_path('consultant_review.xlsx', 'xlsx');
  if (!outputPath) return;
  await _withBtn('cmp-export-xlsx', 'Export Excel', async () => {
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/compare/excel`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report, output_path: outputPath }),
      });
      const data = await resp.json();
      if (!data.ok) showError(`Excel export failed: ${data.error || 'unknown error'}`);
    } catch {
      showError('Could not reach the local server to export the Excel.');
    }
  });
}

// ── Corrected but-for XML ───────────────────────────────────────────────────

function _revertList(ops) {
  if (!ops || !ops.length) {
    return '<p class="cmp-empty">No revertable changes — nothing to correct.</p>';
  }
  const items = ops.map(op => `
    <label class="cmp-rev-item">
      <input type="checkbox" class="cmp-rev-cb" value="${escapeHtml(op.id)}" checked>
      <span class="cmp-rev-txt"><b>${escapeHtml(op.label)}</b>
        <span class="cmp-rev-detail">${escapeHtml(op.detail || '')}</span></span>
    </label>`).join('');
  return `
    <div class="cmp-rev-controls">
      <button class="btn-mini" id="cmp-rev-all">Select all</button>
      <button class="btn-mini" id="cmp-rev-none">Select none</button>
    </div>
    <div class="cmp-rev-list">${items}</div>
    <div class="cmp-rev-actions">
      <button class="btn-primary" id="cmp-gen-xml">Generate corrected XML</button>
      <span class="cmp-rev-hint mut">Open it in P6 → F9 → read the right delay. It's a but-for analysis file, not your official schedule.</span>
    </div>
    <div class="cmp-rev-result" id="cmp-rev-result"></div>`;
}

function _correctedSection(report) {
  const updIsXml = /\.xml$/i.test(state.currentXmlPath || '');
  if (!updIsXml) {
    return `<div class="cmp-warn">To produce the corrected file, re-export the current update from P6 as an <b>XML</b> file and open it — the "but-for" file is written as P6 XML.</div>`;
  }
  return `
    <div class="cmp-note">Tick the manipulations to strip. The tool reverts only those relationships, lags and durations to baseline and leaves your actuals untouched — then you F9 in P6 to read the genuine delay.</div>
    ${_revertList(report.revert_ops)}
    <div class="cmp-reschedule">
      <div class="cmp-reschedule-t">Reschedule it in P6, then load it back</div>
      <div class="cmp-reschedule-d">Open the corrected file in P6 and press <b>F9</b> — P6 recalculates the dates from the reverted baseline logic (the file keeps the update's old dates until it does). Then <b>re-export it as XML and load it below</b> — that's what brings the rescheduled delay into the report; the delay before/after, the S-curve and the PDF all need it. (You can also read the delay straight off P6 after F9 for a quick look — but only the loaded file puts it into the report.)</div>
      <div class="cmp-manual">✎ Or apply it by hand in P6: using the <b>Driving logic &amp; lag changes</b> table above, set each flagged relationship's <b>type and lag</b> (and the durations) back to the baseline value shown, then F9 — that gives the same corrected delay directly, without importing the file.</div>
      <button class="btn-mini" id="cmp-load-resched">Load rescheduled corrected file</button>
    </div>
    <div id="cmp-impact"></div>`;
}

function _wireCorrected() {
  const gen = document.getElementById('cmp-gen-xml');
  if (gen) gen.addEventListener('click', generateCorrectedXml);
  const setAll = v => document.querySelectorAll('.cmp-rev-cb').forEach(cb => { cb.checked = v; });
  const all = document.getElementById('cmp-rev-all');
  const none = document.getElementById('cmp-rev-none');
  if (all) all.addEventListener('click', () => setAll(true));
  if (none) none.addEventListener('click', () => setAll(false));
  const resched = document.getElementById('cmp-load-resched');
  if (resched) resched.addEventListener('click', loadRescheduledAndCompare);
}

// ── Before/after impact (from the rescheduled corrected file) ───────────────

function _impactTile(label, val, hot) {
  const s = (val == null) ? '—' : `${val} d`;
  return `<div class="kpi"><div class="k">${escapeHtml(label)}</div>` +
         `<div class="v${hot ? ' cmp-hot' : ''}">${escapeHtml(s)}</div></div>`;
}

// Inline SVG of the three cumulative-% curves (baseline / before / after).
function _scurveSvg(sc) {
  const periods = sc.periods || [];
  if (periods.length < 2) return '<p class="cmp-empty">Not enough dated activities to draw the S-curve.</p>';
  const x0 = 45, x1 = 600, y0 = 180, y1 = 20, n = periods.length;
  const xAt = i => x0 + (x1 - x0) * (i / (n - 1));
  const yAt = p => y0 - (y0 - y1) * (Math.max(0, Math.min(100, p || 0)) / 100);
  const poly = (arr, color, dash) => {
    if (!arr || !arr.length) return '';
    const pts = arr.map((p, i) => `${xAt(i).toFixed(1)},${yAt(p).toFixed(1)}`).join(' ');
    return `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2"${dash ? ` stroke-dasharray="${dash}"` : ''} stroke-linejoin="round"/>`;
  };
  const step = Math.max(1, Math.round(n / 6));
  let xlabels = '';
  for (let i = 0; i < n; i += step) {
    xlabels += `<text x="${xAt(i).toFixed(1)}" y="198" text-anchor="middle" style="fill:var(--muted);font-size:10px">${escapeHtml(periods[i])}</text>`;
  }
  return `<svg viewBox="0 0 620 214" width="100%" role="img" aria-label="S-curve comparing baseline, before-changes and after-changes cumulative progress over time">
    <line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y0}" stroke="var(--border)" stroke-width="1"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="var(--border)" stroke-width="1"/>
    <text x="${x0 - 6}" y="${y1 + 4}" text-anchor="end" style="fill:var(--muted);font-size:10px">100%</text>
    <text x="${x0 - 6}" y="${(y0 + y1) / 2 + 4}" text-anchor="end" style="fill:var(--muted);font-size:10px">50%</text>
    <text x="${x0 - 6}" y="${y0 + 4}" text-anchor="end" style="fill:var(--muted);font-size:10px">0%</text>
    ${poly(sc.baseline, '#888781', '4 3')}
    ${poly(sc.after, '#e24b4a')}
    ${poly(sc.before, '#2a78d6')}
    ${xlabels}
  </svg>`;
}

function _scurveSection(sc) {
  if (!sc || !(sc.periods || []).length) return '';
  return `
    <div class="mod-sec">S-curve — baseline vs reported vs but-for</div>
    <div class="cmp-scurve-card">
      <div class="cmp-scurve-legend">
        <span><i style="background:#888781"></i>Baseline plan</span>
        <span><i style="background:#e24b4a"></i>Reported (update)</span>
        <span><i style="background:#2a78d6"></i>But-for (corrected)</span>
      </div>
      ${_scurveSvg(sc)}
      <div class="cmp-scurve-note">Planned progress profile from each schedule's activity dates &amp; durations — the gap between reported and but-for is the manufactured slip. The exact delay is in the numbers above.</div>
    </div>`;
}

export function renderImpact(impact) {
  const el = document.getElementById('cmp-impact');
  if (!el) return;
  _shownImpact = impact;   // carried into the PDF export even if state is invalidated
  const f = impact.forecast || {};
  const mfd = impact.manufactured_days;
  const warn = impact.warning ? `<div class="cmp-warn">${escapeHtml(impact.warning)}</div>` : '';
  el.innerHTML = `
    ${warn}
    <div class="mod-sec">Impact — reported vs but-for delay</div>
    <div class="cmp-kpis">
      ${_impactTile('Reported delay (as submitted)', impact.delay_after)}
      ${_impactTile('But-for delay (baseline logic)', impact.delay_before)}
      ${_impactTile('Manufactured', mfd, mfd != null && mfd > 0)}
    </div>
    <div class="cmp-forecast">Overall completion — baseline <b>${escapeHtml(f.baseline || '—')}</b> · reported (update) <b>${escapeHtml(f.after || '—')}</b> · but-for (corrected) <b>${escapeHtml(f.before || '—')}</b></div>
    ${_scurveSection(impact.scurve)}
    <div class="mod-sec">Consultant recommendation</div>
    <div class="cmp-reco">${escapeHtml(impact.recommendation || '')}</div>`;
}

export async function loadRescheduledAndCompare() {
  const path = await window.pywebview.api.choose_file();
  if (!path) return;
  const el = document.getElementById('cmp-impact');
  if (el) el.innerHTML = '<div class="cmp-loading">Computing the reported vs but-for delay…</div>';
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/compare/before-after`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        baseline_path: state.compareBaselinePath,
        update_path: state.currentXmlPath,
        cached_path: state.currentCachedPath,
        corrected_path: path,
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      if (el) el.innerHTML = `<div class="cmp-warn">${escapeHtml(data.error || 'Could not compute the before/after impact.')}</div>`;
      return;
    }
    state.compareImpact = data.impact;   // carried into the PDF export
    renderImpact(data.impact);
  } catch {
    if (el) el.innerHTML = '<div class="cmp-warn">Could not reach the local server. Try restarting the app.</div>';
  }
}

export async function generateCorrectedXml() {
  const ids = Array.from(document.querySelectorAll('.cmp-rev-cb:checked')).map(cb => cb.value);
  const resultEl = document.getElementById('cmp-rev-result');
  if (!ids.length) {
    if (resultEl) resultEl.innerHTML = '<span class="cmp-over">Tick at least one change to revert.</span>';
    return;
  }
  const updName = (state.currentXmlPath || '').split(/[\\/]/).pop() || 'update.xml';
  const outputPath = await window.pywebview.api.choose_save_path(suggestedCorrectedName(updName), 'xml');
  if (!outputPath) return;
  if (resultEl) resultEl.innerHTML = '<span class="mut">Writing corrected XML…</span>';
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/compare/corrected-xml`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        baseline_path: state.compareBaselinePath,
        update_path: state.currentXmlPath,
        cached_path: state.currentCachedPath,
        selected_ids: ids,
        output_path: outputPath,
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      if (resultEl) resultEl.innerHTML = `<span class="cmp-over">${escapeHtml(data.error || 'Could not write the corrected XML.')}</span>`;
      return;
    }
    const n = data.applied || 0;
    if (resultEl) resultEl.innerHTML = `<span class="cmp-ok">Corrected XML saved — ${n} change${n === 1 ? '' : 's'} reverted to baseline: <b>${escapeHtml(outputPath)}</b>.<br>Open it in P6, press <b>F9</b>, and read the right delay.</span>`;
  } catch {
    if (resultEl) resultEl.innerHTML = '<span class="cmp-over">Could not reach the local server. Try restarting the app.</span>';
  }
}

export function renderComparePanel() {
  const body = document.getElementById('compare-body');
  if (!body) return;
  if (state.compareReport) { renderCompareReport(state.compareReport); return; }
  const updName = (state.currentXmlPath || '').split(/[\\/]/).pop() || '—';
  body.innerHTML = `
    <div class="cmp-prompt">
      <div class="cmp-prompt-t">Compare against the approved baseline</div>
      <div class="cmp-prompt-d">Current update: <b>${escapeHtml(updName)}</b>. Choose the baseline programme (XER or XML) to compare it against — the tool shows what changed and, next, the corrected file that gives the right delay.</div>
      <button class="btn-primary" id="cmp-choose-baseline">Choose baseline file</button>
    </div>`;
  const btn = document.getElementById('cmp-choose-baseline');
  if (btn) btn.addEventListener('click', chooseBaselineAndCompare);
}

export async function chooseBaselineAndCompare() {
  if (!state.currentXmlPath && !state.currentCachedPath) {
    showError('Open a schedule first, then compare it against a baseline.');
    return;
  }
  const path = await window.pywebview.api.choose_file();
  if (!path) return;
  clearError();
  const body = document.getElementById('compare-body');
  if (body) body.innerHTML = '<div class="cmp-loading">Comparing against the baseline…</div>';
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/compare`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        baseline_path: path,
        update_path: state.currentXmlPath,
        cached_path: state.currentCachedPath,
      }),
    });
    const data = await resp.json();
    if (!data.ok) { showError(data.error || 'Comparison failed.'); renderComparePanel(); return; }
    state.compareReport = data.report;
    state.compareImpact = null;          // a fresh comparison clears any prior before/after
    state.compareBaselineName = path.split(/[\\/]/).pop();
    state.compareBaselinePath = path;   // full path — the corrected-XML writer needs it
    renderCompareReport(data.report);
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
    renderComparePanel();
  }
}
