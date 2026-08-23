// Consultant Review — Baseline vs Current Update.
// The update is the currently-open schedule; the user picks a baseline to compare
// against. Renders the driving logic/lag change table, the duration table, the
// change summary and milestone finishes. (Before/after impact, the three-way
// S-curve and the corrected but-for XML arrive in the next slice.)

import { state }             from './state.js';
import { showError, clearError } from './render.js';
import { escapeHtml }        from './format.js';
import { getSavedMode, buildAppearancePicker, backdropColor } from './appearance.js';

// The report-appearance mode chosen in this panel's PDF preview modal — remembered
// across sessions via appearance.js, shared with every other report preview flow.
let _cmpTheme = getSavedMode();

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

// Dashboard reconciliation: the "changed activities" total splits into the driving-logic
// subset and the duration-only remainder, which sum back to the total exactly. Pure and
// unit-tested so the dashboard tile and the table heading can never drift apart.
export function changedBreakdown(dash) {
  const d = dash || {};
  return {
    total: d.changed_activities ?? 0,
    logic: d.logic_changed ?? 0,
    duration: d.duration_only ?? 0,
  };
}

// ── Executive-dashboard charts — pure data helpers (unit-tested) ────────────

// Ranked bars for "how the logic was changed": the logic-group change-summary items,
// biggest first, each with a width % relative to the largest. Duration items dropped.
export function changeTypeBars(items) {
  const logic = (items || []).filter(it => it && it.group === 'logic' && (it.count || 0) > 0);
  logic.sort((a, b) => (b.count || 0) - (a.count || 0));
  const max = logic.length ? (logic[0].count || 1) : 1;
  return logic.map(it => ({
    label: it.label || it.kind || '',
    count: it.count || 0,
    pct: Math.round((it.count || 0) / max * 100),
  }));
}

// Finish-slip headline: signed days → magnitude + direction word. Positive = later.
export function slipInfo(days) {
  if (days == null) return { value: null, word: 'no finish date', dir: 'none' };
  if (days > 0) return { value: days, word: days === 1 ? 'day later' : 'days later', dir: 'late' };
  if (days < 0) return { value: -days, word: days === -1 ? 'day earlier' : 'days earlier', dir: 'early' };
  return { value: 0, word: 'on the baseline finish', dir: 'ontime' };
}

// Two-segment donut fractions (logic vs duration-only), guarding a zero total.
export function donutSegments(logic, duration) {
  const l = Math.max(0, logic || 0), d = Math.max(0, duration || 0), t = l + d;
  return t ? { logicFrac: l / t, durationFrac: d / t } : { logicFrac: 0, durationFrac: 0 };
}

// ── Chart rendering (DOM) ───────────────────────────────────────────────────

const _DONUT_C = 326.726;   // circumference of the r=52 donut ring

function _chartBars(report) {
  const bars = changeTypeBars((report.change_summary || {}).items);
  if (!bars.length) return '<p class="cmp-empty">No driving-logic or lag changes to chart.</p>';
  return `<div class="cmp-bars">${bars.map(b => `
    <div class="cmp-bar-row">
      <div class="cmp-bar-label" title="${escapeHtml(b.label)}">${escapeHtml(b.label)}</div>
      <div class="cmp-bar-track"><div class="cmp-bar-fill" style="width:${b.pct}%"></div></div>
      <div class="cmp-bar-val">${escapeHtml(String(b.count))}</div>
    </div>`).join('')}</div>`;
}

// But-for summary from the instant no-F9 estimate: how many of the reported delay's working
// days the flagged edits manufactured (reported − but-for). Pure, unit-tested.
export function butForSummary(dash) {
  const d = dash || {};
  const rep = d.delay_working_days, bf = d.butfor_delay_working_days, mfd = d.manufactured_working_days;
  if (bf == null || mfd == null) return null;
  let verdict;
  if (mfd > 0) verdict = `${mfd} of the ${rep} working days were manufactured — reverting the flagged changes pulls the finish in to ${d.butfor_finish || '—'}.`;
  else if (mfd === 0) verdict = `Reverting the flagged changes doesn't move the finish — the ${rep}-working-day delay is genuine, not manufactured.`;
  else verdict = 'Reverting the flagged changes does not reduce the delay.';
  return { reported: rep, butfor: bf, manufactured: mfd, verdict };
}

function _butForNote(report) {
  const s = butForSummary(report.dashboard);
  if (!s) return '';
  const cls = s.manufactured > 0 ? 'cmp-mfd-hot' : 'cmp-mfd-ok';
  return `<div class="cmp-butfor ${cls}">
      <b>But-for delay: ${escapeHtml(String(s.butfor))} wd</b> &nbsp;·&nbsp; <b>${escapeHtml(String(s.manufactured))} manufactured</b>
      <div class="mut">${escapeHtml(s.verdict)} <b>Instant estimate</b> — the tool schedules it, no F9; F9 the corrected file below to lock P6's exact date.</div>
    </div>`;
}

function _chartSlip(report) {
  // The honest delay = finish-date variance vs baseline in WORKING days (no F9 needed).
  const s = slipInfo((report.dashboard || {}).delay_working_days);
  const cls = { late: 'cmp-slip-late', early: 'cmp-slip-early', ontime: 'cmp-slip-flat', none: 'cmp-slip-flat' }[s.dir];
  const num = s.value == null ? '—' : `${s.dir === 'late' ? '+' : s.dir === 'early' ? '−' : ''}${s.value}`;
  const cap = { late: 'working days behind<br>the baseline finish',
                early: 'working days ahead of<br>the baseline finish',
                ontime: 'on the baseline finish', none: 'no finish date' }[s.dir];
  const dd = report.data_date || '—', bf = report.baseline_finish || '—', uf = report.update_finish || '—';
  const slipLine = (s.dir === 'late' || s.dir === 'early')
    ? `<line x1="150" y1="30" x2="268" y2="30" stroke="${s.dir === 'late' ? 'var(--danger)' : 'var(--success)'}" stroke-width="6" stroke-linecap="round"/>`
    : '';
  return `
    <div class="cmp-slip-head"><span class="cmp-slip-num ${cls}">${escapeHtml(num)}</span>
      <span class="cmp-slip-cap">${cap}</span></div>
    <svg viewBox="0 0 300 64" width="100%" role="img" aria-label="Delay: baseline finish versus update finish, ${escapeHtml(s.word)}">
      <line x1="14" y1="30" x2="286" y2="30" stroke="var(--border)" stroke-width="2" stroke-linecap="round"/>
      ${slipLine}
      <circle cx="36" cy="30" r="4.5" fill="var(--muted)"/>
      <text x="36" y="48" text-anchor="middle" style="font-size:8.5px;fill:var(--muted)">Data date</text>
      <text x="36" y="59" text-anchor="middle" style="font-size:8.5px;font-weight:700;fill:var(--text)">${escapeHtml(dd)}</text>
      <circle cx="150" cy="30" r="5.5" fill="var(--card-bg)" stroke="var(--accent)" stroke-width="3"/>
      <text x="150" y="15" text-anchor="middle" style="font-size:8.5px;fill:var(--muted)">Baseline</text>
      <text x="150" y="48" text-anchor="middle" style="font-size:8.5px;font-weight:700;fill:var(--text)">${escapeHtml(bf)}</text>
      <circle cx="268" cy="30" r="5.5" fill="var(--danger)"/>
      <text x="268" y="15" text-anchor="middle" style="font-size:8.5px;font-weight:700;fill:var(--danger)">Update</text>
      <text x="268" y="48" text-anchor="middle" style="font-size:8.5px;font-weight:700;fill:var(--text)">${escapeHtml(uf)}</text>
    </svg>`;
}

function _chartDonut(report) {
  const b = changedBreakdown(report.dashboard);
  const seg = donutSegments(b.logic, b.duration);
  const gap = (seg.logicFrac > 0 && seg.durationFrac > 0) ? 2 : 0;
  const la = Math.max(0, seg.logicFrac * _DONUT_C - gap), da = Math.max(0, seg.durationFrac * _DONUT_C - gap);
  const pct = f => Math.round(f * 100);
  return `
    <div class="cmp-donut-wrap">
      <svg viewBox="0 0 130 130" width="108" height="108" role="img" aria-label="${escapeHtml(String(b.total))} changed: ${escapeHtml(String(b.logic))} logic or lag, ${escapeHtml(String(b.duration))} duration only">
        <circle cx="65" cy="65" r="52" fill="none" stroke="var(--border)" stroke-width="20"/>
        <circle cx="65" cy="65" r="52" fill="none" stroke="var(--accent)" stroke-width="20"
                stroke-dasharray="${la.toFixed(1)} ${(_DONUT_C - la).toFixed(1)}" transform="rotate(-90 65 65)"/>
        <circle cx="65" cy="65" r="52" fill="none" stroke="var(--chart-3)" stroke-width="20"
                stroke-dasharray="${da.toFixed(1)} ${(_DONUT_C - da).toFixed(1)}" stroke-dashoffset="${(-seg.logicFrac * _DONUT_C).toFixed(1)}" transform="rotate(-90 65 65)"/>
        <text x="65" y="61" text-anchor="middle" style="font-size:20px;font-weight:800;fill:var(--text)">${escapeHtml(String(b.total))}</text>
        <text x="65" y="78" text-anchor="middle" style="font-size:9px;fill:var(--muted)">changed</text>
      </svg>
      <div class="cmp-donut-legend">
        <div><i style="background:var(--accent)"></i><b>${escapeHtml(String(b.logic))}</b> logic / lag <span class="mut">(${pct(seg.logicFrac)}%)</span></div>
        <div><i style="background:var(--chart-3)"></i><b>${escapeHtml(String(b.duration))}</b> duration only <span class="mut">(${pct(seg.durationFrac)}%)</span></div>
      </div>
    </div>`;
}

function _chartsSection(report) {
  const total = changedBreakdown(report.dashboard).total;
  return `
    <div class="cmp-charts">
      <div class="cmp-chart">
        <div class="cmp-chart-t">How the logic was changed</div>
        <div class="cmp-chart-s">Every driving-logic / lag change, by type — the fingerprint of what changed.</div>
        ${_chartBars(report)}
      </div>
      <div class="cmp-chart">
        <div class="cmp-chart-t">Delay vs baseline</div>
        <div class="cmp-chart-s">Finish date vs baseline, in working days — the honest delay, straight away (no F9).</div>
        ${_chartSlip(report)}
        ${_butForNote(report)}
      </div>
      <div class="cmp-chart">
        <div class="cmp-chart-t">Changed activities</div>
        <div class="cmp-chart-s">The ${escapeHtml(String(total))} split by what changed.</div>
        ${_chartDonut(report)}
      </div>
    </div>`;
}

function _changedKpi(dash) {
  const b = changedBreakdown(dash);
  return `<div class="kpi cmp-kpi-changed"><div class="k">Changed activities</div>` +
         `<div class="v">${escapeHtml(String(b.total))}</div>` +
         `<div class="cmp-kpi-brk"><span><b>${escapeHtml(String(b.logic))}</b>logic / lag</span>` +
         `<span><b>${escapeHtml(String(b.duration))}</b>duration</span></div></div>`;
}

function _reconHtml(dash) {
  const b = changedBreakdown(dash);
  return `<b>${escapeHtml(String(b.total))}</b> activities changed vs baseline = ` +
         `<b>${escapeHtml(String(b.logic))}</b> with driving-logic / lag changes + ` +
         `<b>${escapeHtml(String(b.duration))}</b> with duration changes only.`;
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
  const body = rows.map((r, i) => `
    <tr>
      <td class="cmp-sn">${i + 1}</td>
      <td class="mono">${escapeHtml(r.activity_id)}</td>
      <td>${escapeHtml(r.activity_name)}</td>
      <td><span class="cmp-tag">${escapeHtml(r.change_label)}</span></td>
      <td class="sepL mono">${cellStack(r.baseline_preds, 'id')}</td><td class="cmp-rel">${cellStack(r.baseline_preds, 'rel')}</td><td class="cmp-nm">${cellStack(r.baseline_preds, 'name')}</td>
      <td class="mono">${cellStack(r.baseline_succs, 'id')}</td><td class="cmp-rel">${cellStack(r.baseline_succs, 'rel')}</td><td class="cmp-nm">${cellStack(r.baseline_succs, 'name')}</td>
      <td class="sepU mono">${cellStack(r.update_preds, 'id')}</td><td class="cmp-rel">${cellStack(r.update_preds, 'rel')}</td><td class="cmp-nm">${cellStack(r.update_preds, 'name')}</td>
      <td class="mono">${cellStack(r.update_succs, 'id')}</td><td class="cmp-rel">${cellStack(r.update_succs, 'rel')}</td><td class="cmp-nm">${cellStack(r.update_succs, 'name')}</td>
    </tr>`).join('');
  return `<div class="tblwrap cmp-logwrap"><table class="audit-table cmp-log">
    <colgroup>
      <col class="c-sn"><col class="c-aid"><col class="c-anm"><col class="c-chg">
      <col class="c-id"><col class="c-rel"><col class="c-nm">
      <col class="c-id"><col class="c-rel"><col class="c-nm">
      <col class="c-id"><col class="c-rel"><col class="c-nm">
      <col class="c-id"><col class="c-rel"><col class="c-nm">
    </colgroup>
    <thead>
      <tr><th rowspan="3">#</th><th rowspan="3">Activity ID</th><th rowspan="3">Activity name</th><th rowspan="3">Change</th>
        <th colspan="6" class="cmp-gh-base">Baseline — driving links</th>
        <th colspan="6" class="cmp-gh-upd">Update — driving links</th></tr>
      <tr><th colspan="3" class="sepL cmp-gh-base">Predecessor</th><th colspan="3" class="cmp-gh-base">Successor</th>
        <th colspan="3" class="sepU cmp-gh-upd">Predecessor</th><th colspan="3" class="cmp-gh-upd">Successor</th></tr>
      <tr><th class="sepL">Pred. ID</th><th>Rel</th><th>Pred. name</th><th>Succ. ID</th><th>Rel</th><th>Succ. name</th>
        <th class="sepU">Pred. ID</th><th>Rel</th><th>Pred. name</th><th>Succ. ID</th><th>Rel</th><th>Succ. name</th></tr>
    </thead>
    <tbody>${body}</tbody></table></div>
    <div class="cmp-foot">Every predecessor and successor relationship is read straight from the files. <b>▶ bold</b> = the driving link (date-derived; may be absent on completed activities). Red = changed vs baseline · green = added · struck = removed.</div>`;
}

function _durationTable(rows) {
  if (!rows || !rows.length) {
    return '<p class="cmp-empty">No duration or remaining changes vs the baseline.</p>';
  }
  const body = rows.map(r => {
    return `<tr>
    <td class="mono">${escapeHtml(r.activity_id)}</td><td>${escapeHtml(r.activity_name)}</td>
    <td class="num mut">${r.baseline_orig_days} d</td>
    <td class="num">${r.status === 'extended' ? `<span class="cmp-pill cmp-chg">${r.update_orig_days} d</span>` : `${r.update_orig_days} d`}</td>
    <td class="num">${r.remaining_days} d</td>
    <td class="num ${r.over_baseline ? 'cmp-over' : ''}">${signedDays(r.remaining_minus_baseline_days)}</td>
    <td>${_durStatus(r.status)}</td>
    <td>${_durImpact(r.impact)}</td></tr>`;
  }).join('');
  return `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-table">
    <thead><tr><th>Activity ID</th><th>Activity name</th><th class="num">Baseline orig.</th><th class="num">Update orig.</th><th class="num">Remaining</th><th class="num">Rem − baseline</th><th>Status</th><th>Impact on finish</th></tr></thead>
    <tbody>${body}</tbody></table></div>
    ${_durationLegend()}`;
}

// Plain-language key for the duration table's columns and the impact-on-finish values.
function _durationLegend() {
  return `<div class="cmp-legend">
    <div class="cmp-legend-l"><b>Columns —</b>
      <b>Baseline orig.</b> original duration in the baseline ·
      <b>Update orig.</b> original duration now ·
      <b>Remaining</b> duration still left at the data date ·
      <b>Rem − baseline</b> remaining minus the baseline original (positive = more work left than the baseline ever allowed).</div>
    <div class="cmp-legend-l"><b>Impact on finish —</b>
      <span class="cmp-imp cmp-imp-direct">Direct</span> on the critical path, pushes the finish ·
      <span class="cmp-imp cmp-imp-pot">Potential</span> near-critical (≤ 10 working-days float) ·
      <span class="cmp-imp cmp-imp-none">Float absorbs</span> enough float to swallow it ·
      <span class="cmp-imp">—</span> the P6 export carries no float value for this activity, so it can't be judged.</div>
  </div>`;
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
      <button class="btn-secondary" id="cmp-preview-pdf">Preview PDF</button>
      <button class="btn-secondary" id="cmp-export-pdf">Export PDF</button>
      <button class="btn-secondary" id="cmp-export-xlsx">Export Excel</button>
    </div>
    ${mismatch}
    <div class="mod-sec">Executive dashboard</div>
    <div class="cmp-kpis">
      ${_changedKpi(dash)}
      ${_kpi('Baseline finish', report.baseline_finish || '—')}
      ${_kpi('Update finish', report.update_finish || '—')}
      ${_kpi('Data date', report.data_date || '—')}
    </div>
    <div class="cmp-recon">${_reconHtml(dash)}</div>
    ${_chartsSection(report)}
    <div class="mod-sec">Driving logic &amp; lag changes vs baseline</div>
    <div class="cmp-chgsum">
      <div class="cmp-chgsum-t">Activities with driving-logic / lag changes: <b>${dash.logic_changed ?? logic.summary.changed_activities ?? 0}</b><span class="cmp-chgsum-sub"> — of the ${dash.changed_activities ?? 0} total changed (the other ${dash.duration_only ?? 0} changed in duration only)</span></div>
      <div class="cmp-pills">${summaryPills(cs.items)}</div>
    </div>
    ${_logicTable(logic.rows)}
    <div class="mod-sec">Duration &amp; remaining changes vs baseline</div>
    ${_durationTable(durs.rows)}
    <div class="mod-sec">Corrected but-for XML</div>
    ${_correctedSection(report)}`;
  const chg = document.getElementById('cmp-change-baseline');
  if (chg) chg.addEventListener('click', chooseBaselineAndCompare);
  const eprev = document.getElementById('cmp-preview-pdf');
  if (eprev) eprev.addEventListener('click', previewComparePdf);
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

// Print preview: render the exact PDF HTML (server preview=true) in a modal, so the report
// can be reviewed before saving — works both before and after the corrected file is loaded
// (the impact section shows once it is). A "Save as PDF" button exports from the preview.
export async function previewComparePdf() {
  const report = _shownReportOrWarn();
  if (!report) return;
  const impact = state.compareImpact || _shownImpact || null;
  const btn = document.getElementById('cmp-preview-pdf');
  if (btn) { btn.disabled = true; btn.textContent = 'Preparing…'; }
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/compare/report`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report, impact, preview: true, theme: _cmpTheme }),
    });
    const data = await resp.json();
    if (!data.ok) { showError(`Preview failed: ${data.error || 'unknown error'}`); return; }
    _showPreviewModal(data.html, report, impact);
  } catch {
    showError('Could not reach the local server to build the preview.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Preview PDF'; }
  }
}

// `report`/`impact` are the exact payload the modal was opened with (captured by the caller,
// not re-read from state) — the appearance picker's re-fetch reuses them so the re-rendered
// preview matches the one first shown, even if a background re-import clears state.compare*.
function _showPreviewModal(html, report, impact) {
  const old = document.getElementById('cmp-preview-modal');
  if (old) old.remove();
  const modal = document.createElement('div');
  modal.id = 'cmp-preview-modal';
  modal.className = 'cmp-modal';
  modal.innerHTML = `
    <div class="cmp-modal-bar">
      <span class="cmp-modal-t">Print preview — Consultant Review</span>
      <div class="cmp-modal-actions">
        <button class="btn-primary" id="cmp-modal-save">Save as PDF</button>
        <button class="btn-mini" id="cmp-modal-close">Close</button>
      </div>
    </div>
    <iframe class="cmp-modal-frame" id="cmp-modal-frame" title="Consultant Review PDF preview"></iframe>`;
  document.body.appendChild(modal);
  const frame = document.getElementById('cmp-modal-frame');
  frame.srcdoc = html;
  frame.style.background = backdropColor(_cmpTheme);

  const actions = modal.querySelector('.cmp-modal-actions');
  const picker = buildAppearancePicker({
    current: _cmpTheme,
    compact: true,
    onChange: async (mode) => {
      _cmpTheme = mode;
      frame.style.background = backdropColor(_cmpTheme);
      try {
        const resp = await fetch(`http://localhost:${state.serverPort}/api/compare/report`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ report, impact, preview: true, theme: _cmpTheme }),
        });
        const data = await resp.json();
        if (data.ok) frame.srcdoc = data.html;
      } catch { /* keep showing the last-good preview */ }
    },
  });
  if (actions) actions.insertBefore(picker, actions.firstChild);

  document.getElementById('cmp-modal-close').addEventListener('click', () => modal.remove());
  document.getElementById('cmp-modal-save').addEventListener('click', () => { modal.remove(); exportComparePdf(); });
}

export async function exportComparePdf() {
  const report = _shownReportOrWarn();
  if (!report) return;
  const outputPath = await window.pywebview.api.choose_save_path('consultant_review.pdf', 'pdf');
  if (!outputPath) return;
  await _withBtn('cmp-export-pdf', 'Export PDF', async () => {
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/compare/report`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report, impact: state.compareImpact || _shownImpact || null, output_path: outputPath, theme: _cmpTheme }),
      });
      const data = await resp.json();
      if (!data.ok) showError(`PDF export failed: ${data.error || 'unknown error'}`);
    } catch {
      showError('Could not reach the local server to export the PDF.');
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
  const x0 = 50, x1 = 604, y0 = 250, y1 = 40, n = periods.length;   // taller plot, more headroom
  const xAt = i => x0 + (x1 - x0) * (i / (n - 1));
  const yAt = p => y0 - (y0 - y1) * (Math.max(0, Math.min(100, p || 0)) / 100);
  const poly = (arr, color, dash) => {
    if (!arr || !arr.length) return '';
    const pts = arr.map((p, i) => `${xAt(i).toFixed(1)},${yAt(p).toFixed(1)}`).join(' ');
    return `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2"${dash ? ` stroke-dasharray="${dash}"` : ''} stroke-linejoin="round"/>`;
  };
  // Y gridlines + labels at 0/25/50/75/100 (more readable spacing)
  let ygrid = '';
  for (const p of [0, 25, 50, 75, 100]) {
    const y = yAt(p);
    ygrid += `<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" stroke="var(--border)" stroke-width="${p === 0 ? 1 : 0.5}"${p === 0 ? '' : ' stroke-dasharray="2 4"'}/>`;
    ygrid += `<text x="${x0 - 7}" y="${(y + 3).toFixed(1)}" text-anchor="end" style="fill:var(--muted);font-size:9px">${p}%</text>`;
  }
  const step = Math.max(1, Math.round(n / 8));   // ~8 well-spaced date labels
  let xlabels = '';
  for (let i = 0; i < n; i += step) {
    xlabels += `<text x="${xAt(i).toFixed(1)}" y="${y0 + 17}" text-anchor="middle" style="fill:var(--muted);font-size:9px">${escapeHtml(periods[i])}</text>`;
  }
  // Finish markers — baseline & update finishes, staggered on two rows and edge-aware so the
  // labels never overlap even when the two finishes sit close together.
  const m = sc.markers || {};
  const bx = m.baseline_idx != null ? xAt(m.baseline_idx) : null;
  const ux = m.update_idx != null ? xAt(m.update_idx) : null;
  const anch = x => (x > x1 - 78 ? 'end' : (x < x0 + 78 ? 'start' : 'middle'));
  let marks = '';
  if (bx != null && ux != null && ux > bx) {
    marks += `<rect x="${bx.toFixed(1)}" y="${y1}" width="${(ux - bx).toFixed(1)}" height="${y0 - y1}" fill="rgba(226,75,74,.09)"/>`;
    marks += `<text x="${((bx + ux) / 2).toFixed(1)}" y="${(y1 + 13).toFixed(1)}" text-anchor="middle" style="fill:var(--danger);font-size:9px;font-weight:700">◄ slip ►</text>`;
  }
  if (bx != null) marks += `<line x1="${bx.toFixed(1)}" y1="${y1}" x2="${bx.toFixed(1)}" y2="${y0}" stroke="var(--muted)" stroke-width="1" stroke-dasharray="3 2"/>` +
    `<text x="${bx.toFixed(1)}" y="${(y1 - 16).toFixed(1)}" text-anchor="${anch(bx)}" style="fill:var(--muted);font-size:9px;font-weight:700">Baseline ${escapeHtml(m.baseline_label || '')}</text>`;
  if (ux != null) marks += `<line x1="${ux.toFixed(1)}" y1="${y1}" x2="${ux.toFixed(1)}" y2="${y0}" stroke="var(--danger)" stroke-width="1" stroke-dasharray="3 2"/>` +
    `<text x="${ux.toFixed(1)}" y="${(y1 - 5).toFixed(1)}" text-anchor="${anch(ux)}" style="fill:var(--danger);font-size:9px;font-weight:700">Update ${escapeHtml(m.update_label || '')}</text>`;
  return `<svg viewBox="0 0 620 278" width="100%" role="img" aria-label="S-curve: baseline plan vs update, with the finish of each marked and the slip between them shaded">
    ${ygrid}
    ${marks}
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="var(--border)" stroke-width="1"/>
    ${poly(sc.baseline, 'var(--muted)', '4 3')}
    ${poly(sc.after, 'var(--danger)')}
    ${poly(sc.before, 'var(--accent)')}
    ${xlabels}
  </svg>`;
}

function _scurveSection(sc) {
  if (!sc || !(sc.periods || []).length) return '';
  return `
    <div class="mod-sec">S-curve — baseline vs reported vs but-for</div>
    <div class="cmp-scurve-card">
      <div class="cmp-scurve-legend">
        <span><i style="background:var(--muted)"></i>Baseline plan</span>
        <span><i style="background:var(--danger)"></i>Reported (update)</span>
        <span><i style="background:var(--accent)"></i>But-for (corrected)</span>
      </div>
      ${_scurveSvg(sc)}
      <div class="cmp-scurve-note">Each curve reaches 100% at that schedule's finish — the dashed lines mark the <b>baseline finish</b> and the <b>update finish</b>, and the shaded band between them is the <b>slip</b>. The but-for curve shows where the finish would sit with the flagged changes reverted; the exact delay is in the numbers above.</div>
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
