// Consultant Review — Baseline vs Current Update.
// The update is the currently-open schedule; the user picks a baseline to compare
// against. Renders the driving logic/lag change table, the duration table, the
// change summary and milestone finishes. (Before/after impact, the three-way
// S-curve and the corrected but-for XML arrive in the next slice.)

import { state }             from './state.js';
import { showError, clearError } from './render.js';
import { escapeHtml }        from './format.js';

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

// ── Rendering ─────────────────────────────────────────────────────────────

function cellStack(list, key) {
  if (!list || !list.length) return '<span class="mut">—</span>';
  return list.map(l => {
    const val = key === 'rel' ? fmtLag(l.type, l.lag_days)
              : key === 'id' ? l.code : (l.name || '');
    const cls = statusClass(l.status);
    const inner = cls ? `<span class="cmp-pill ${cls}">${escapeHtml(String(val))}</span>`
                      : escapeHtml(String(val));
    return `<div class="cmp-dl">${inner}</div>`;
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
    <div class="cmp-foot">Driving links are derived from the schedule's remaining early dates and lags (P6 exports no driving flag). Where an activity has more than one driving predecessor or successor, every driving link is listed. Red = changed vs baseline · green = added · struck = removed.</div>`;
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
    <td>${_durStatus(r.status)}</td></tr>`).join('');
  return `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-table">
    <thead><tr><th>Activity ID</th><th>Activity name</th><th class="num">Baseline orig.</th><th class="num">Update orig.</th><th class="num">Remaining</th><th class="num">Rem − baseline</th><th>Status</th></tr></thead>
    <tbody>${body}</tbody></table></div>`;
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

export function renderCompareReport(report) {
  const body = document.getElementById('compare-body');
  if (!body) return;
  const dash = report.dashboard || {};
  const logic = report.logic || { rows: [], summary: {} };
  const durs = report.durations || { rows: [] };
  const cs = report.change_summary || { items: [] };
  const mismatch = (report.matched_activities === 0)
    ? `<div class="cmp-warn">No activities matched by ID between the two files — is this the right baseline for this update? Nothing changed can be detected until they line up.</div>`
    : '';
  body.innerHTML = `
    ${_fileBar(report)}
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
    <div class="mod-sec">Milestones — baseline vs update finish</div>
    ${_milestoneTable(report.milestones || [])}
    <div class="cmp-note">Next slice: the delay before/after the changes, the three-way S-curve, and the corrected "but-for" XML you F9 in P6. Nothing is written to your schedule.</div>`;
  const chg = document.getElementById('cmp-change-baseline');
  if (chg) chg.addEventListener('click', chooseBaselineAndCompare);
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
    state.compareBaselineName = path.split(/[\\/]/).pop();
    renderCompareReport(data.report);
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
    renderComparePanel();
  }
}
