// AI Copilot — the tool's central assistant.
//  • Assistant (V2, default): offline expert engine — reads every module's result for the
//    open project and answers Planning/Management questions in plain language, plus a
//    one-click Manager Report. No cloud, no cost.
//  • Delay analysis (what-if): the Time Impact Analysis workspace (Slice A) — build the
//    impacted P6 file, F9, read the exact impact. The day-count is P6's (Decision 003).

import { state }                 from './state.js';
import { showError, clearError } from './render.js';
import { escapeHtml }            from './format.js';
import { resolveActivity }       from './copilot_helpers.js';
import { showReportPreview }     from './preview.js';

const MGMT_Q = [
  { id: 'why_delayed', text: 'Why is the project delayed?' },
  { id: 'which_wbs',   text: 'Which part is causing it?' },
  { id: 'risks',       text: 'Biggest risks right now' },
  { id: 'health',      text: 'Overall project health' },
  { id: 'eot_likely',  text: 'Is a time extension likely?' },
  { id: 'actions',     text: 'Top actions this week' },
];

// What-if scenarios (Slice 2). Each builds a modified P6 file; the exact impact comes from F9.
const SCENARIOS = [
  { kind: 'delay',   name: 'Delay an activity',           activity: true,  daysLabel: 'Delay by (working days)' },
  { kind: 'shorten', name: 'Shorten / crash an activity', activity: true,  daysLabel: 'Shorten by (working days)' },
  { kind: 'six_day', name: 'Work 6 days a week',          activity: false },
];

function _cp() {
  if (!state.copilot) state.copilot = { subview: 'assistant', mode: 'management', answer: null,
    activeQ: null, scenarioKind: 'delay', activityId: '', activityName: '', activityInput: '',
    delayDays: '', estimate: null, plannerOpen: false, scenario: null, impact: null, activities: null };
  return state.copilot;
}

function _post(path, body) {
  return fetch(`http://localhost:${state.serverPort}/${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(r => r.json());
}

function _basePaths() { return { xml_path: state.currentXmlPath, cached_path: state.currentCachedPath }; }
function _mdBold(s) { return escapeHtml(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>'); }

function _fmtDate(s) {
  if (!s) return '—';
  const d = new Date(s);
  return isNaN(d.getTime()) ? String(s).slice(0, 10)
    : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

// ── panel shell (sub-nav → Assistant | Delay analysis) ──────────────────────
export async function renderCopilotPanel() {
  const body = document.getElementById('copilot-body');
  if (!body) return;
  if (!state.currentXmlPath && !state.currentCachedPath) {
    body.innerHTML = '<p class="ai-empty">Open a schedule first, then the AI Copilot can analyse it.</p>';
    return;
  }
  _renderShell();
}

function _renderShell() {
  const body = document.getElementById('copilot-body');
  if (!body) return;
  const cp = _cp();
  body.innerHTML = `
    <div class="cp-subnav">
      <button class="cp-sub ${cp.subview !== 'delay' ? 'on' : ''}" data-sub="assistant">Assistant</button>
      <button class="cp-sub ${cp.subview === 'delay' ? 'on' : ''}" data-sub="delay">What-if scenarios</button>
    </div>
    <div id="cp-view"></div>`;
  body.querySelectorAll('.cp-sub').forEach(b => b.addEventListener('click', () => { _cp().subview = b.dataset.sub; _renderShell(); }));
  if (cp.subview === 'delay') { _renderWorkspace(); if (!cp.activities) _loadActivities(); }
  else _renderAssistant();
}

// ── Assistant (V2 offline expert engine) ────────────────────────────────────
function _renderAssistant() {
  const view = document.getElementById('cp-view');
  if (!view) return;
  const cp = _cp();
  const r = state.currentResult || {};
  const mgmt = cp.mode !== 'planning';
  view.innerHTML = `
    <div class="ai-filebar">
      <div class="fb"><span class="k">Project</span><span class="v ai-type">${escapeHtml(r.project_name || '—')}</span></div>
      <div class="fb"><span class="k">Update</span><span class="v">${escapeHtml((r.data_date || '').slice(0, 10) || '—')}</span></div>
      <div class="fb"><span class="k">Mode</span><span class="cp-modes">
        <button class="cp-mode ${mgmt ? 'on' : ''}" data-mode="management">Management</button>
        <button class="cp-mode ${!mgmt ? 'on' : ''}" data-mode="planning">Planning</button></span></div>
    </div>
    <div class="ai-banner"><span class="spark">🤖</span><span class="txt"><b>AI Copilot — offline expert engine.</b>
      It reads every module's results for this project and answers in plain language, with the evidence. No internet, no cost. Advisory.</span></div>
    <div class="cp-reads"><span>Reading:</span> ${['EVM', 'Delay', 'Out of Sequence', 'Float'].map(m => `<span class="cp-modchip">${m}</span>`).join('')}<span class="cp-modchip" style="opacity:.55">Calendar · Constructability — next</span></div>

    <div class="cp-report-cta">
      <div><div class="h">📄 Manager Report</div><div class="d">A plain-English one-pager on this update — status, why, risks, what to do. Export to PDF.</div></div>
      <button class="btn-primary" id="cp-report-btn">Generate Manager Report</button>
    </div>

    ${mgmt ? `
      <div class="mod-sec">Ask about this project</div>
      <div class="cp-qs">${MGMT_Q.map(q => `<button class="cp-q ${cp.activeQ === q.id ? 'on' : ''}" data-q="${q.id}">${escapeHtml(q.text)}</button>`).join('')}</div>
      <div id="cp-answer">${cp.answer ? '' : '<p class="ai-empty">Pick a question — the Copilot answers from this project’s own numbers.</p>'}</div>`
    : `
      <div class="cp-plan-note"><b>Planning Engineer view</b> — the technical answers (critical path, logic, crashing, per-activity what-if)
        arrive in the next slice. <b>Management mode is live now</b> — switch back to try it, or use <b>What-if scenarios</b> above.</div>`}`;

  view.querySelectorAll('.cp-mode').forEach(b => b.addEventListener('click', () => { _cp().mode = b.dataset.mode; _renderAssistant(); }));
  const rb = document.getElementById('cp-report-btn'); if (rb) rb.addEventListener('click', _managerReport);
  view.querySelectorAll('.cp-q').forEach(b => b.addEventListener('click', () => _ask(b.dataset.q)));
  if (mgmt && cp.answer) _renderAnswer(cp.answer);
}

async function _ask(qid) {
  const cp = _cp();
  cp.activeQ = qid;
  document.querySelectorAll('.cp-q').forEach(b => b.classList.toggle('on', b.dataset.q === qid));
  const area = document.getElementById('cp-answer');
  if (area) area.innerHTML = '<div class="cmp-loading">Thinking…</div>';
  clearError();
  try {
    const data = await _post('api/copilot/ask', { snapshot_id: state.currentSnapshotId, question_id: qid, mode: cp.mode });
    if (!data.ok) { showError(data.error || 'Could not answer that.'); if (area) area.innerHTML = ''; return; }
    cp.answer = data.answer;
    _renderAnswer(data.answer);
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}

function _renderAnswer(a) {
  const area = document.getElementById('cp-answer');
  if (!area) return;
  const body = (a.body || []).map(p => `<p>${_mdBold(p)}</p>`).join('');
  const advice = (a.advice && a.advice.length)
    ? `<div class="cp-advice"><div class="cp-advice-h">💡 What to do</div><ul>${a.advice.map(x => `<li>${_mdBold(x)}</li>`).join('')}</ul></div>` : '';
  const ev = (a.evidence && a.evidence.length)
    ? `<div class="cp-ev"><span>Based on:</span> ${a.evidence.map(e => `<span class="cp-src">${escapeHtml(e.module)} · ${escapeHtml(e.value)}</span>`).join('')}</div>` : '';
  area.innerHTML = `<div class="cp-ans"><div class="cp-ans-h">${_mdBold(a.headline)}</div>${body}${advice}${ev}</div>`;
}

// Manager Report → preview the HTML, then save as PDF (reuses the shared report preview).
async function _managerReport() {
  clearError();
  const btn = document.getElementById('cp-report-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Preparing…'; }
  try {
    const data = await _post('api/copilot/report', { snapshot_id: state.currentSnapshotId, preview: true });
    if (!data.ok) { showError(data.error || 'Could not build the report.'); return; }
    showReportPreview({
      title: 'Manager Report', subtitle: (state.currentResult || {}).project_name || '',
      html: data.html, onSave: _saveReportPdf,
    });
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Generate Manager Report'; }
  }
}

async function _saveReportPdf() {
  const outputPath = await window.pywebview.api.choose_save_path('Manager_Report.pdf', 'pdf');
  if (!outputPath) return false;
  const data = await _post('api/copilot/report', { snapshot_id: state.currentSnapshotId, output_path: outputPath });
  if (!data.ok) { showError(`PDF generation failed: ${data.error}`); return false; }
  return true;
}

// ── What-if scenario engine (Slice 2) — delay / shorten / 6-day, impact via F9 ──
function _renderWorkspace() {
  const view = document.getElementById('cp-view');
  if (!view) return;
  const cp = _cp();
  const sc = SCENARIOS.find(s => s.kind === cp.scenarioKind) || SCENARIOS[0];
  const count = cp.activities ? cp.activities.filter(a => !a.is_milestone).length : 0;
  view.innerHTML = `
    <div class="ai-banner"><span class="spark">🤖</span>
      <span class="txt"><b>What-if — an instant estimate from this update's analysis. No Primavera needed.</b>
      It nets your change against each activity's spare time and the critical path, and gives advice.</span></div>

    <div class="mod-sec">1 · Choose a what-if</div>
    <div class="cp-methods">${SCENARIOS.map(s => `<button class="cp-m ${s.kind === cp.scenarioKind ? 'on' : ''}" data-kind="${s.kind}">${escapeHtml(s.name)}</button>`).join('')}</div>

    <div class="mod-sec">2 · The change</div>
    ${sc.activity ? `
    <div class="cp-form">
      <label class="cp-fld"><span>Activity — search by ID or name</span>
        <input id="cp-activity" class="cp-input" list="cp-activity-list" autocomplete="off"
               value="${escapeHtml(cp.activityInput || '')}"
               placeholder="${cp.activities ? `Type an Activity ID or name… (${count} activities)` : 'Loading activities…'}">
        <datalist id="cp-activity-list"></datalist>
        <span id="cp-activity-match" class="cp-match"></span></label>
      <label class="cp-fld cp-fld-sm"><span>${escapeHtml(sc.daysLabel)}</span>
        <input type="number" min="1" step="1" id="cp-delay" class="cp-input" value="${escapeHtml(String(cp.delayDays || ''))}" placeholder="e.g. 14"></label>
    </div>`
    : `<div class="cp-plan-note">Makes <b>Saturday a working day</b> across the schedule — no other input needed.</div>`}

    <div class="cp-step"><button class="btn-primary" id="cp-est">Estimate impact</button>
      <span class="cp-hint">Instant — worked out from this update, no Primavera steps.</span></div>
    <div id="cp-estimate">${cp.estimate ? _estimateHtml(cp.estimate) : ''}</div>

    <div class="cp-planner">
      <button class="cp-disclose" id="cp-planner-toggle">${cp.plannerOpen ? '▾' : '▸'} Planner: get the exact figure via Primavera (F9)</button>
      ${cp.plannerOpen ? `
      <div class="cp-planner-body">
        <div class="cp-hint" style="margin-bottom:8px">For a precise, claim-grade number: build the scenario file, open it in P6, press F9, re-export and load it back. (Planner tool — the estimate above needs none of this.)</div>
        <div class="cp-step"><button class="btn-secondary" id="cp-gen">Generate scenario file…</button></div>
        <div id="cp-scenario">${cp.scenario ? _scenarioHtml(cp.scenario) : ''}</div>
        <div class="cp-step"><button class="btn-secondary" id="cp-load" ${cp.scenario ? '' : 'disabled'}>Load rescheduled file (after F9)…</button></div>
        <div id="cp-impact">${cp.impact ? _impactHtml(cp.impact) : ''}</div>
      </div>` : ''}
    </div>`;

  view.querySelectorAll('.cp-m').forEach(b => b.addEventListener('click', () => {
    const c = _cp();
    c.scenarioKind = b.dataset.kind; c.estimate = null; c.scenario = null; c.impact = null;
    _renderWorkspace();
    if (!_cp().activities) _loadActivities(); else _fillActivityList();
  }));
  const est = document.getElementById('cp-est'); if (est) est.addEventListener('click', _estimateWhatif);
  const tog = document.getElementById('cp-planner-toggle'); if (tog) tog.addEventListener('click', () => { _cp().plannerOpen = !_cp().plannerOpen; _renderWorkspace(); });
  const gen = document.getElementById('cp-gen'); if (gen) gen.addEventListener('click', _generateScenario);
  const load = document.getElementById('cp-load'); if (load) load.addEventListener('click', _loadRescheduled);
  _fillActivityList();
  _bindInputs();
}

async function _estimateWhatif() {
  const cp = _cp();
  clearError();
  const sc = SCENARIOS.find(s => s.kind === cp.scenarioKind) || SCENARIOS[0];
  let activity_id = null, days = null;
  if (sc.activity) {
    if (!resolveActivity(cp.activities, cp.activityInput)) { showError('Type a valid Activity ID, or pick an activity from the list.'); return; }
    days = parseInt(cp.delayDays, 10);
    if (!days || days < 1) { showError('Enter a number of working days (at least 1).'); return; }
    activity_id = cp.activityId;
  }
  const btn = document.getElementById('cp-est');
  if (btn) { btn.disabled = true; btn.textContent = 'Estimating…'; }
  try {
    const data = await _post('api/copilot/whatif', { ..._basePaths(), kind: cp.scenarioKind, activity_id, days });
    if (!data.ok) { showError(data.error || 'Could not estimate the impact.'); return; }
    cp.estimate = data.result;
    _renderWorkspace();
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Estimate impact'; }
  }
}

function _estimateHtml(r) {
  const d = r.impact_days;
  const cls = d > 0 ? 'late' : (d < 0 ? 'early' : 'none');
  const sign = d > 0 ? '+' : '';
  const dir = d > 0 ? 'later' : (d < 0 ? 'earlier' : 'no change');
  return `<div class="cp-impact ${cls}">
    <div class="cp-impact-num">${sign}${escapeHtml(String(d))} <span>working days ${escapeHtml(dir)}</span></div>
    <div class="cp-est-head">${escapeHtml(r.headline)}</div>
    <div class="cp-est-basis">${escapeHtml(r.basis)}</div>
    <div class="cp-est-advice">💡 ${escapeHtml(r.advice)}</div>
    <div class="cp-impact-tag est">Estimate — from this update's analysis, not a Primavera recalculation.</div>
  </div>`;
}

function _bindInputs() {
  const del = document.getElementById('cp-delay');
  if (del) del.addEventListener('input', e => { _cp().delayDays = e.target.value; });
  const lab = document.getElementById('cp-label');
  if (lab) lab.addEventListener('input', e => { _cp().label = e.target.value; });
  const act = document.getElementById('cp-activity');
  if (act) act.addEventListener('input', () => { _cp().activityInput = act.value; _showActivityMatch(); });
}

async function _loadActivities() {
  try {
    const data = await _post('api/claims/activities', _basePaths());
    if (!data.ok) { showError(data.error || 'Could not read the schedule activities.'); return; }
    _cp().activities = data.activities || [];
    if (_cp().subview === 'delay') _renderWorkspace();
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}

function _fillActivityList() {
  const list = document.getElementById('cp-activity-list');
  const cp = _cp();
  if (!list || !cp.activities) return;
  list.innerHTML = cp.activities.filter(a => !a.is_milestone).map(a =>
    `<option value="${escapeHtml(a.id + ' — ' + a.name)}"></option>`).join('');
  _showActivityMatch();
}

function _showActivityMatch() {
  const cp = _cp();
  const el = document.getElementById('cp-activity-match');
  if (!el) return;
  const a = resolveActivity(cp.activities, cp.activityInput);
  cp.activityId = a ? a.id : '';
  cp.activityName = a ? a.name : '';
  if (a) {
    el.innerHTML = `<span class="cp-ok">✓ ${escapeHtml(a.id)} — ${escapeHtml(a.name)}${a.wbs_path ? ' <span class="cp-wbs">· ' + escapeHtml(a.wbs_path) + '</span>' : ''}</span>`;
  } else if ((cp.activityInput || '').trim()) {
    el.innerHTML = `<span class="cp-warn">No exact match yet — type a full Activity ID, or pick a name from the list.</span>`;
  } else { el.innerHTML = ''; }
}

async function _generateScenario() {
  const cp = _cp();
  clearError();
  const sc = SCENARIOS.find(s => s.kind === cp.scenarioKind) || SCENARIOS[0];
  let activity_id = null, days = null;
  if (sc.activity) {
    if (!resolveActivity(cp.activities, cp.activityInput)) { showError('Type a valid Activity ID, or pick an activity from the list.'); return; }
    days = parseInt(cp.delayDays, 10);
    if (!days || days < 1) { showError('Enter a number of working days (at least 1).'); return; }
    activity_id = cp.activityId;
  }
  const safe = (sc.activity ? (activity_id || 'activity') : 'six-day-week').replace(/[^A-Za-z0-9_-]+/g, '_');
  const outPath = await window.pywebview.api.choose_save_path(`${safe}_whatif.xml`, 'xml');
  if (!outPath) return;
  const btn = document.getElementById('cp-gen');
  if (btn) { btn.disabled = true; btn.textContent = 'Building…'; }
  try {
    const data = await _post('api/copilot/scenario', {
      ..._basePaths(), kind: cp.scenarioKind, activity_id, days, output_path: outPath });
    if (!data.ok) { showError(data.error || 'Could not build the scenario file.'); return; }
    cp.scenario = { ...data, days, kind: cp.scenarioKind, activity_name: cp.activityName || data.activity_name };
    cp.impact = null;
    _renderWorkspace();
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Generate scenario file…'; }
  }
}

function _scenarioHtml(s) {
  return `<div class="cp-note ok">
    <div class="cp-note-h">✓ Scenario saved</div>
    <div class="cp-note-b"><b>${escapeHtml(s.label || 'Scenario')}</b>${s.activity_name ? ' — ' + escapeHtml(s.activity_name) : ''}, saved to<br>
      <span class="mono">${escapeHtml(s.output_path)}</span></div>
    <ol class="cp-steps">
      <li>Open that file in Primavera P6.</li>
      <li>Press <b>F9</b> to reschedule.</li>
      <li>Re-export the XML and load it back below to read the exact impact.</li>
    </ol></div>`;
}

async function _loadRescheduled() {
  clearError();
  const path = await window.pywebview.api.choose_file();
  if (!path) return;
  const btn = document.getElementById('cp-load');
  if (btn) { btn.disabled = true; btn.textContent = 'Reading impact…'; }
  try {
    const data = await _post('api/claims/impact', { ..._basePaths(), rescheduled_path: path });
    if (!data.ok) { showError(data.error || 'Could not read the impact.'); return; }
    _cp().impact = data.impact;
    _renderWorkspace();
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Load rescheduled file (after F9)…'; }
  }
}

function _impactHtml(im) {
  const days = im.impact_days;
  const sign = days > 0 ? '+' : '';
  const cls = days > 0 ? 'late' : (days < 0 ? 'early' : 'none');
  const dir = days > 0 ? 'later' : (days < 0 ? 'earlier' : 'no change');
  return `<div class="cp-impact ${cls}">
    <div class="cp-impact-num">${sign}${escapeHtml(String(days))} <span>working days ${escapeHtml(dir)}</span></div>
    <div class="cp-impact-sub">Completion ${im.milestone_name ? '(' + escapeHtml(im.milestone_name) + ') ' : ''}moved
      ${_fmtDate(im.before_finish)} → ${_fmtDate(im.after_finish)}</div>
    <div class="cp-impact-tag">✓ from P6 · F9 — exact</div>
    <div class="cp-impact-claim">The exact schedule impact of this what-if — P6's own number, not an estimate.</div>
  </div>`;
}
