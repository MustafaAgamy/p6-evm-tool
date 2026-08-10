// AI Copilot — delay-analysis & claims engine (Slice A: Time Impact Analysis).
// The planner picks a method + a delayed activity + a delay length; the tool builds the
// impacted P6 programme (base update + a named delay fragnet driving that activity), the
// planner presses F9 in P6 and re-exports, and the tool reads the EXACT impact back.
// The day-count is P6's — never computed here, never the AI's (Decision 003).

import { state }                 from './state.js';
import { showError, clearError } from './render.js';
import { escapeHtml }            from './format.js';

// Method knowledge (mirrors p6_claims/methods.py). TIA is executable now; the rest are
// shown as "known" — the copilot can explain them, execution lands in later slices.
const METHODS = [
  { key: 'tia',     name: 'Time impact analysis',         mip: 'AACE MIP 3.7', executable: true,
    needs: 'the update as it stood at the time of the event' },
  { key: 'iap',     name: 'Impacted as-planned',          mip: 'AACE MIP 3.6', executable: false,
    needs: 'the baseline only' },
  { key: 'windows', name: 'Windows analysis',             mip: 'AACE MIP 3.3', executable: false,
    needs: 'a series of updates across the period' },
  { key: 'but_for', name: 'Collapsed as-built (but-for)', mip: 'AACE MIP 3.8', executable: false,
    needs: 'already available as the Consultant Review' },
];

function _cp() {
  if (!state.copilot) state.copilot = { method: 'tia', activityId: '', activityName: '',
    delayDays: '', label: '', scenario: null, impact: null, activities: null };
  return state.copilot;
}

function _post(path, body) {
  return fetch(`http://localhost:${state.serverPort}/${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(r => r.json());
}

function _basePaths() {
  return { xml_path: state.currentXmlPath, cached_path: state.currentCachedPath };
}

function _fmtDate(s) {
  if (!s) return '—';
  const d = new Date(s);
  return isNaN(d.getTime()) ? String(s).slice(0, 10)
    : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

// ── panel entry ─────────────────────────────────────────────────────────────
export async function renderCopilotPanel() {
  const body = document.getElementById('copilot-body');
  if (!body) return;
  if (!state.currentXmlPath && !state.currentCachedPath) {
    body.innerHTML = '<p class="ai-empty">Open a schedule first, then the AI Copilot can analyse its delays.</p>';
    return;
  }
  _renderWorkspace();
  const cp = _cp();
  if (!cp.activities) await _loadActivities();
}

function _methodChips() {
  const cur = _cp().method || 'tia';
  return METHODS.map(m => {
    const on = m.key === cur;
    const cls = `cp-m${on ? ' on' : ''}${m.executable ? '' : ' soon'}`;
    const tag = m.executable ? '' : ' <span class="cp-soon">known</span>';
    return `<button class="${cls}" data-method="${m.key}" ${m.executable ? '' : 'disabled'}
      title="${escapeHtml(m.name)} — needs ${escapeHtml(m.needs)}">${escapeHtml(m.name)}${tag}</button>`;
  }).join('');
}

function _renderWorkspace() {
  const body = document.getElementById('copilot-body');
  if (!body) return;
  const cp = _cp();
  const m = METHODS.find(x => x.key === cp.method) || METHODS[0];
  body.innerHTML = `
    <div class="ai-filebar">
      <div class="fb"><span class="k">Method</span><span class="v ai-type">${escapeHtml(m.name)}</span></div>
      <div class="fb"><span class="k">Standard</span><span class="v">${escapeHtml(m.mip)}</span></div>
      <div class="fb"><span class="k">Source</span><span class="v">${escapeHtml(m.needs)}</span></div>
    </div>
    <div class="ai-banner"><span class="spark">🤖</span>
      <span class="txt"><b>AI Copilot — delay analysis. Advisory opinion, not legal advice.</b>
      The method knowledge is the copilot's; the day-count is P6's own (from F9), never invented.
      Nothing in your schedule is changed.</span></div>

    <div class="mod-sec">Delay-analysis method</div>
    <div class="cp-methods">${_methodChips()}</div>
    <div class="cp-methodnote">${escapeHtml(m.name)} — ${escapeHtml(methodDescription(m.key))}</div>

    <div class="mod-sec">1 · The delay</div>
    <div class="cp-form">
      <label class="cp-fld"><span>Delayed activity</span>
        <select id="cp-activity" class="ct-select">
          <option value="">${cp.activities ? '— pick an activity —' : 'Loading activities…'}</option>
        </select></label>
      <label class="cp-fld cp-fld-sm"><span>Delay (working days)</span>
        <input type="number" min="1" step="1" id="cp-delay" class="cp-input" value="${escapeHtml(String(cp.delayDays || ''))}" placeholder="e.g. 14"></label>
      <label class="cp-fld"><span>Delay event (optional)</span>
        <input type="text" id="cp-label" class="cp-input" value="${escapeHtml(cp.label || '')}" placeholder="e.g. Late site access"></label>
    </div>

    <div class="mod-sec">2 · Build the impacted programme &amp; F9 in P6</div>
    <div class="cp-step">
      <button class="btn-primary" id="cp-gen">Generate impacted P6 file…</button>
      <span class="cp-hint">Adds a named delay activity that drives the chosen activity, for you to open in P6.</span>
    </div>
    <div id="cp-scenario">${cp.scenario ? _scenarioHtml(cp.scenario) : ''}</div>

    <div class="mod-sec">3 · Read the exact impact</div>
    <div class="cp-step">
      <button class="btn-secondary" id="cp-load" ${cp.scenario ? '' : 'disabled'}>Load rescheduled file (after F9)…</button>
      <span class="cp-hint">P6 gives the number — the movement of your completion milestone.</span>
    </div>
    <div id="cp-impact">${cp.impact ? _impactHtml(cp.impact, m) : ''}</div>`;

  // wire
  body.querySelectorAll('.cp-m').forEach(b => b.addEventListener('click', () => {
    if (b.disabled) return;
    _cp().method = b.dataset.method; _renderWorkspace();
    if (!_cp().activities) _loadActivities(); else _fillActivitySelect();
  }));
  const gen = document.getElementById('cp-gen');
  if (gen) gen.addEventListener('click', _generateScenario);
  const load = document.getElementById('cp-load');
  if (load) load.addEventListener('click', _loadRescheduled);
  _fillActivitySelect();
  _bindInputs();
}

function methodDescription(key) {
  return {
    tia: 'inserts the delay into the programme as it stood at the time of the event, then reschedules — the SCL-preferred prospective method for an extension of time.',
    iap: 'inserts the delay into the baseline programme and reschedules to model the push.',
    windows: 'splits the period into windows and measures the delay that accrued in each.',
    but_for: 'removes the delaying events from the as-built to show what would have happened but for them.',
  }[key] || '';
}

function _bindInputs() {
  const del = document.getElementById('cp-delay');
  if (del) del.addEventListener('input', e => { _cp().delayDays = e.target.value; });
  const lab = document.getElementById('cp-label');
  if (lab) lab.addEventListener('input', e => { _cp().label = e.target.value; });
  const act = document.getElementById('cp-activity');
  if (act) act.addEventListener('change', e => {
    _cp().activityId = e.target.value;
    const opt = e.target.selectedOptions[0];
    _cp().activityName = opt ? opt.dataset.name || '' : '';
  });
}

async function _loadActivities() {
  try {
    const data = await _post('api/claims/activities', _basePaths());
    if (!data.ok) { showError(data.error || 'Could not read the schedule activities.'); return; }
    _cp().activities = data.activities || [];
    _fillActivitySelect();
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}

function _fillActivitySelect() {
  const sel = document.getElementById('cp-activity');
  const cp = _cp();
  if (!sel || !cp.activities) return;
  const opts = cp.activities.filter(a => !a.is_milestone).map(a =>
    `<option value="${escapeHtml(a.id)}" data-name="${escapeHtml(a.name)}" ${a.id === cp.activityId ? 'selected' : ''}>${escapeHtml(a.id)} — ${escapeHtml(a.name)}</option>`).join('');
  sel.innerHTML = `<option value="">— pick an activity —</option>${opts}`;
}

// ── step 2: build the impacted XML ──────────────────────────────────────────
async function _generateScenario() {
  const cp = _cp();
  clearError();
  if (!cp.activityId) { showError('Pick the delayed activity first.'); return; }
  const days = parseInt(cp.delayDays, 10);
  if (!days || days < 1) { showError('Enter a delay of at least one working day.'); return; }
  const safe = (cp.activityId || 'activity').replace(/[^A-Za-z0-9_-]+/g, '_');
  const outPath = await window.pywebview.api.choose_save_path(`${safe}_TIA-impacted.xml`, 'xml');
  if (!outPath) return;
  const btn = document.getElementById('cp-gen');
  if (btn) { btn.disabled = true; btn.textContent = 'Building…'; }
  try {
    const data = await _post('api/claims/scenario', {
      ..._basePaths(), activity_id: cp.activityId, delay_days: days,
      label: cp.label || null, output_path: outPath,
    });
    if (!data.ok) { showError(data.error || 'Could not build the impacted file.'); return; }
    cp.scenario = { ...data, days, activity_name: cp.activityName || data.activity_name };
    cp.impact = null;
    _renderWorkspace();
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Generate impacted P6 file…'; }
  }
}

function _scenarioHtml(s) {
  return `<div class="cp-note ok">
    <div class="cp-note-h">✓ Impacted programme saved</div>
    <div class="cp-note-b">Added the delay activity <b>${escapeHtml(s.delay_name || s.delay_id)}</b>
      (${escapeHtml(String(s.days))} wd) driving <b>${escapeHtml(s.activity_name || '')}</b>, saved to<br>
      <span class="mono">${escapeHtml(s.output_path)}</span></div>
    <ol class="cp-steps">
      <li>Open that file in Primavera P6.</li>
      <li>Press <b>F9</b> to reschedule.</li>
      <li>Read the delay straight from P6, or re-export the XML and load it back below for the full before/after.</li>
    </ol></div>`;
}

// ── step 3: read the exact impact ───────────────────────────────────────────
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

function _impactHtml(im, m) {
  const days = im.impact_days;
  const sign = days > 0 ? '+' : '';
  const cls = days > 0 ? 'late' : (days < 0 ? 'early' : 'none');
  return `<div class="cp-impact ${cls}">
    <div class="cp-impact-num">${sign}${escapeHtml(String(days))} <span>working days</span></div>
    <div class="cp-impact-sub">Completion ${im.milestone_name ? '(' + escapeHtml(im.milestone_name) + ') ' : ''}moved
      ${_fmtDate(im.before_finish)} → ${_fmtDate(im.after_finish)}</div>
    <div class="cp-impact-tag">✓ from P6 · F9 — exact</div>
    <div class="cp-impact-method">${escapeHtml(m.name)}: ${escapeHtml(methodDescription(m.key))}</div>
    <div class="cp-impact-claim">→ This is the <b>Effect</b> and <b>Method of proof</b> for an Extension of Time claim.
      Claim drafting (Cause · Entitlement · Substantiation) lands in the next slice.</div>
  </div>`;
}
