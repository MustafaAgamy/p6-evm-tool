// Update Analysis — a single-file read of the current schedule against its own baseline.
//
// Three sections, exactly as sketched: (1) Time Status donut — time elapsed vs earned;
// (2) Planned vs Actual by activity code — bars, one or more codes stacked; (3) Critical
// Path Analyzer — the governing completion milestone's driving path as WBS work-front
// boxes. All numbers come from the server (metrics.compute), so they match the EVM tab.
import { state }      from './state.js';
import { showError }  from './render.js';
import { escapeHtml } from './format.js';

let _shownReport = null;     // the report currently on screen (exports read this)
let _summaryLevel = 0;       // critical-path roll-up level: 0 work front · 1 area · 2 phase
let _pickedTypes = [];       // activity-code dimensions chosen for Section 2 (1 = direct, >1 = combined)

const C = { plan: '#cbd5e1', actual: '#2a78d6', good: '#16a34a', warn: '#d97706', bad: '#dc2626',
            blue: '#2a78d6', track: 'var(--border)' };

function _fileName() {
  const p = state.currentXmlPath || state.currentCachedPath || '';
  return p.split(/[\\/]/).pop() || 'current schedule';
}

// Prefer a meaningful default breakdown (discipline / trade / type of work / phase) over
// the alphabetically-first activity code, which is often an obscure internal dimension.
function _defaultCodeType(types) {
  if (!types.length) return null;
  const tiers = [/disciplin/i, /type of work/i, /type of civil/i, /\btrade\b/i, /main wbs/i, /\bphase\b/i];
  for (const re of tiers) {
    const m = types.find(t => re.test(t));
    if (m) return m;
  }
  return types[0];
}

function _injectStyle() {
  if (document.getElementById('ua-style')) return;
  const s = document.createElement('style');
  s.id = 'ua-style';
  s.textContent = `
    .ua-sec { margin: 22px 0 8px; font-size: 15px; font-weight: 600; color: var(--text); }
    .ua-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px; padding: 18px; }
    .ua-reco { background: var(--card-bg); border: 1px solid var(--border); border-left: 4px solid var(--accent); border-radius: 0 10px 10px 0; padding: 12px 15px; line-height: 1.6; color: var(--text); }
    .ua-ts { display: flex; gap: 26px; align-items: center; flex-wrap: wrap; }
    .ua-ts-sentence { font-size: 17px; line-height: 1.5; color: var(--text); }
    .ua-chip { display: inline-block; border-radius: 20px; padding: 5px 13px; font-size: 13px; margin: 10px 8px 0 0; }
    .ua-chip.bad { background: rgba(220,38,38,.12); color: var(--danger); }
    .ua-chip.good { background: rgba(22,163,74,.12); color: var(--success); }
    .ua-leg { margin-top: 12px; font-size: 12px; color: var(--muted); }
    .ua-leg span { display: block; margin: 3px 0; }
    .ua-leg i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: middle; margin-right: 7px; }
    .ua-note { color: var(--muted); font-style: italic; }
    .ua-slicer { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
    .ua-code-btn { border: 1px solid var(--border); background: var(--bg); color: var(--text); border-radius: 20px; padding: 5px 13px; font-size: 12.5px; cursor: pointer; }
    .ua-code-btn.on { background: var(--accent); color: #fff; border-color: var(--accent); }
    .ua-bc-row { margin-bottom: 15px; }
    .ua-bc-name { font-size: 13px; color: var(--text); margin-bottom: 4px; font-weight: 600; }
    .ua-bc-track { height: 12px; background: var(--bg); border: 1px solid var(--border); border-radius: 3px; overflow: hidden; margin-bottom: 4px; }
    .ua-bc-fill { height: 100%; }
    .ua-bc-num { font-size: 12px; color: var(--muted); }
    .ua-cp-head { background: rgba(42,120,214,.08); border: 1px solid var(--border); border-radius: 10px; padding: 12px 15px; font-size: 14px; line-height: 1.5; color: var(--text); margin-bottom: 14px; }
    .ua-chain { display: flex; align-items: stretch; flex-wrap: wrap; gap: 3px; }
    .ua-box { flex: none; max-width: 190px; display: flex; flex-direction: column; justify-content: center; border-radius: 9px; padding: 9px 12px; font-size: 12.5px; font-weight: 600; }
    .ua-box small { display: block; font-weight: 500; font-size: 10.5px; opacity: .92; margin-top: 2px; }
    .ua-box.shared { background: #bcd6f5; color: #1e3a8a; }
    .ua-box.newly { background: #f4a3a3; color: #7f1d1d; }
    .ua-box.done { background: #cbeacd; color: #166534; }
    .ua-arw { display: flex; align-items: center; color: var(--muted); font-weight: 800; font-size: 16px; padding: 0 2px; }
    .ua-mslabel { font-size: 11px; text-transform: uppercase; letter-spacing: .4px; color: var(--muted); margin: 4px 0 8px; font-weight: 700; }
    .ua-empty { color: var(--muted); padding: 40px; text-align: center; }
  `;
  document.head.appendChild(s);
}

// ── Entry ────────────────────────────────────────────────────────────────────

export function renderUpdatePanel() {
  _injectStyle();
  const body = document.getElementById('update-body');
  if (!body) return;
  if (!state.currentXmlPath && !state.currentCachedPath) {
    body.innerHTML = `<div class="ua-empty">Import a schedule first, then open Update Analysis.</div>`;
    return;
  }
  body.innerHTML = `<div class="ua-empty">Reading this update against its baseline…</div>`;
  _runAnalyze();
}

async function _runAnalyze() {
  const body = document.getElementById('update-body');
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/update/analyze`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        xml_path: state.currentXmlPath || '', cached_path: state.currentCachedPath || '',
        summary_level: _summaryLevel,
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      if (data.code === 'no_baseline') {
        body.innerHTML = `<div class="ua-empty">
          <div style="font-size:15px;color:var(--text);margin-bottom:8px">This update has no baseline inside it.</div>
          <div>Attach a baseline on the EVM tab, then re-open Update Analysis — the planned side and the critical-path comparison both need it.</div></div>`;
        return;
      }
      body.innerHTML = `<div class="ua-empty">${escapeHtml(data.error || 'Could not analyze this update.')}</div>`;
      return;
    }
    _shownReport = data.report;
    if (!_pickedTypes.length) {
      _pickedTypes = [_defaultCodeType(data.report.code_types || [])].filter(Boolean);
    }
    _render(data.report);
  } catch {
    if (body) body.innerHTML = `<div class="ua-empty">Could not reach the local server. Try re-importing the schedule.</div>`;
  }
}

// ── Render ───────────────────────────────────────────────────────────────────

function _render(report) {
  const body = document.getElementById('update-body');
  body.innerHTML = `
    <div class="cmp-exports" style="margin-bottom:6px">
      <span class="cmp-file" style="margin-right:auto"><b>${escapeHtml(report.project_name || 'Project')}</b> · data date ${escapeHtml(report.data_date || '—')} · ${escapeHtml(_fileName())}</span>
      <button class="btn-secondary" id="ua-export-pdf">Export PDF</button>
      <button class="btn-secondary" id="ua-export-xlsx">Export Excel</button>
    </div>
    <div class="ua-reco">${escapeHtml(report.conclusion || '')}</div>

    <div class="ua-sec">1 · Time Status</div>
    <div class="ua-card">${_timeStatusHtml(report)}</div>

    <div class="ua-sec">2 · Planned vs Actual — by activity code</div>
    <div class="ua-card">${_byCodeControls(report)}<div id="ua-bc-bars">${_byCodeBars(_currentBuckets(report))}</div></div>

    <div class="ua-sec">3 · Critical Path Analyzer</div>
    <div class="ua-card">${_criticalHtml(report)}</div>`;

  document.getElementById('ua-export-pdf').addEventListener('click', _exportPdf);
  document.getElementById('ua-export-xlsx').addEventListener('click', _exportExcel);
  _wireByCode(report);
  _wireSummaryLevel();
}

function _donut(elapsed, planned, actual) {
  const arc = (r, pct) => {
    const c = 2 * Math.PI * r;
    const on = c * Math.max(0, Math.min(100, pct || 0)) / 100;
    return `${on.toFixed(1)} ${(c - on).toFixed(1)}`;
  };
  const lab = actual != null ? `${Math.round(actual)}%` : '—';
  const sub = planned != null ? `of ${Math.round(planned)}% planned` : '';
  return `<svg width="150" height="150" viewBox="0 0 150 150" aria-label="Time status">
    <circle cx="75" cy="75" r="58" fill="none" stroke="var(--border)" stroke-width="18"/>
    <circle cx="75" cy="75" r="58" fill="none" stroke="${C.blue}" stroke-width="18" stroke-dasharray="${arc(58, elapsed)}" transform="rotate(-90 75 75)"/>
    <circle cx="75" cy="75" r="40" fill="none" stroke="var(--border)" stroke-width="10"/>
    <circle cx="75" cy="75" r="40" fill="none" stroke="#a7e0bd" stroke-width="10" stroke-dasharray="${arc(40, planned)}" transform="rotate(-90 75 75)"/>
    <circle cx="75" cy="75" r="40" fill="none" stroke="${C.good}" stroke-width="10" stroke-dasharray="${arc(40, actual)}" transform="rotate(-90 75 75)"/>
    <text x="75" y="71" text-anchor="middle" font-size="16" font-weight="700" fill="var(--text)">${lab}</text>
    <text x="75" y="89" text-anchor="middle" font-size="10.5" fill="var(--muted)">${escapeHtml(sub)}</text>
  </svg>`;
}

function _pct(v) { return (typeof v === 'number') ? `${Math.round(v)}%` : '—'; }

function _timeStatusHtml(report) {
  const ts = report.time_status || {};
  const ep = ts.elapsed_pct, pp = ts.planned_pct, ap = ts.actual_pct;
  let elapsedTxt = ep != null ? `${Math.round(ep)}%` : '—';
  if (ts.exceeded_days) elapsedTxt = `100% — baseline exceeded by ${ts.exceeded_days} days`;
  const chips = [];
  if (ts.behind_clock != null) chips.push(`<span class="ua-chip ${ts.behind_clock > 0 ? 'bad' : 'good'}">${Math.abs(ts.behind_clock)} points ${ts.behind_clock > 0 ? 'behind' : 'ahead of'} the clock</span>`);
  if (ts.behind_plan != null) chips.push(`<span class="ua-chip ${ts.behind_plan > 0 ? 'bad' : 'good'}">${Math.abs(ts.behind_plan)} points ${ts.behind_plan > 0 ? 'behind' : 'ahead of'} plan</span>`);
  return `<div class="ua-ts">
    <div>${_donut(ep, pp, ap)}</div>
    <div style="flex:1;min-width:280px">
      <div class="ua-ts-sentence"><b>${escapeHtml(elapsedTxt)}</b> of the time has elapsed, and progress achieved is <b>${_pct(ap)}</b> against <b>${_pct(pp)}</b> planned.</div>
      <div>${chips.join('')}</div>
      <div class="ua-leg">
        <span><i style="background:${C.blue}"></i>Time elapsed ${ep != null ? _pct(ep) : '—'} — calendar days (working + non-working) to baseline finish</span>
        <span><i style="background:#a7e0bd"></i>Planned ${_pct(pp)} — PV ÷ budget</span>
        <span><i style="background:${C.good}"></i>Actual ${_pct(ap)} — earned value ÷ budget, cost-loaded activities</span>
      </div>
    </div></div>`;
}

// ── Section 2 · by code ──────────────────────────────────────────────────────

function _byCodeControls(report) {
  const types = report.code_types || [];
  if (!types.length) return '';
  const chips = types.map(t =>
    `<button class="ua-code-btn ${_pickedTypes.includes(t) ? 'on' : ''}" data-type="${escapeHtml(t)}">${escapeHtml(t)}</button>`).join('');
  return `<div class="ua-slicer"><span class="mut" style="color:var(--muted)">Activity code</span>${chips}
    <span style="margin-left:auto;color:var(--muted);font-size:12px">pick one, or stack more than one · worst gap first</span></div>`;
}

function _currentBuckets(report) {
  const by = report.by_code || {};
  if (_pickedTypes.length === 1) return by[_pickedTypes[0]] || [];
  return report._combined || [];   // filled in by _wireByCode when >1 picked
}

function _byCodeBars(rows) {
  if (!rows || !rows.length) return `<div class="ua-note">No activity codes to break progress down by. Pick a different dimension, or this schedule carries no activity codes.</div>`;
  const bars = rows.map(r => {
    const v = r.variance;
    const col = v <= -8 ? C.bad : (v < 0 ? C.warn : C.good);
    const sv = v > 0 ? `+${v}` : `${v}`;
    return `<div class="ua-bc-row">
      <div class="ua-bc-name">${escapeHtml(r.value)}</div>
      <div class="ua-bc-track"><div class="ua-bc-fill" style="width:${Math.max(0, Math.min(100, r.planned))}%;background:${C.plan}"></div></div>
      <div class="ua-bc-track"><div class="ua-bc-fill" style="width:${Math.max(0, Math.min(100, r.actual))}%;background:${col}"></div></div>
      <div class="ua-bc-num">planned ${Math.round(r.planned)}% · actual ${Math.round(r.actual)}% · <b style="color:${col}">${sv}</b></div>
    </div>`;
  }).join('');
  const leg = `<div class="ua-leg"><span><i style="background:${C.plan}"></i>Planned %&nbsp;&nbsp;&nbsp;<i style="background:${C.actual}"></i>Actual % (colour = size of gap)</span></div>`;
  return bars + leg;
}

function _wireByCode(report) {
  const box = document.getElementById('ua-bc-bars');
  document.querySelectorAll('.ua-code-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const t = btn.dataset.type;
      const i = _pickedTypes.indexOf(t);
      if (i >= 0) { if (_pickedTypes.length > 1) _pickedTypes.splice(i, 1); }  // keep at least one
      else _pickedTypes.push(t);
      document.querySelectorAll('.ua-code-btn').forEach(b =>
        b.classList.toggle('on', _pickedTypes.includes(b.dataset.type)));
      if (_pickedTypes.length <= 1) {
        report._combined = null;
        box.innerHTML = _byCodeBars(_currentBuckets(report));
      } else {
        box.innerHTML = `<div class="ua-note">Combining ${_pickedTypes.map(escapeHtml).join(' × ')}…</div>`;
        try {
          const resp = await fetch(`http://localhost:${state.serverPort}/api/update/bycode`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ xml_path: state.currentXmlPath || '', cached_path: state.currentCachedPath || '', types: _pickedTypes }),
          });
          const data = await resp.json();
          report._combined = data.ok ? data.rows : [];
          box.innerHTML = _byCodeBars(report._combined);
        } catch { box.innerHTML = `<div class="ua-note">Could not combine those codes.</div>`; }
      }
    });
  });
}

// ── Section 3 · critical path ────────────────────────────────────────────────

function _criticalHtml(report) {
  const cp = report.critical_path || {};
  const levelSel = `<div class="ua-slicer"><span style="color:var(--muted)">Summarise at</span>
    <select id="ua-cp-level" style="padding:5px 9px;border:1px solid var(--border);border-radius:8px;background:var(--card-bg);color:var(--text)">
      <option value="0"${_summaryLevel === 0 ? ' selected' : ''}>Work front</option>
      <option value="1"${_summaryLevel === 1 ? ' selected' : ''}>Area / zone</option>
      <option value="2"${_summaryLevel === 2 ? ' selected' : ''}>Phase</option>
    </select><span style="margin-left:auto;color:var(--muted);font-size:12px">construction / execution work only</span></div>`;
  if (!cp.charts || !cp.charts.length) {
    return levelSel + `<div class="ua-note">No governing completion milestone with a driving path was found in this update.</div>`;
  }
  const parts = [levelSel];
  if (cp.headline) parts.push(`<div class="ua-cp-head">${escapeHtml(cp.headline)}</div>`);
  cp.charts.forEach(chart => {
    const ms = chart.milestone || {};
    const slip = ms.slip_days != null ? (ms.slip_days > 0 ? `+${ms.slip_days}` : `${ms.slip_days}`) : '—';
    parts.push(`<div class="ua-mslabel">Driving path → ${escapeHtml(ms.name || '')} · baseline ${escapeHtml(ms.baseline_finish || '—')} → expected ${escapeHtml(ms.expected_finish || '—')} · slip ${slip} wd</div>`);
    const boxes = chart.boxes || [];
    const chain = [];
    boxes.forEach((b, i) => {
      const cls = b.complete ? 'done' : 'shared';
      const bslip = b.slip_days != null ? (b.slip_days > 0 ? ` · +${b.slip_days} wd` : '') : '';
      chain.push(`<div class="ua-box ${cls}" title="${escapeHtml(b.crumb || '')}">
        ${escapeHtml(b.name || '')}
        <small>${Math.round(b.pct || 0)}% · exp ${escapeHtml(b.exp_finish || '—')}${bslip}</small>
        ${b.crumb ? `<small>${escapeHtml(b.crumb)}</small>` : ''}
      </div>`);
      if (i < boxes.length - 1) chain.push(`<div class="ua-arw">▸</div>`);
    });
    parts.push(`<div class="ua-chain">${chain.join('')}</div>`);
  });
  parts.push(`<div class="ua-leg" style="margin-top:12px">
    <span><i style="background:#bcd6f5"></i>on the driving path&nbsp;&nbsp;&nbsp;<i style="background:#cbeacd"></i>complete</span></div>`);
  return parts.join('');
}

function _wireSummaryLevel() {
  const sel = document.getElementById('ua-cp-level');
  if (!sel) return;
  sel.addEventListener('change', () => {
    _summaryLevel = parseInt(sel.value, 10) || 0;
    _runAnalyze();   // server re-rolls the boxes at the chosen level
  });
}

// ── Exports ──────────────────────────────────────────────────────────────────

const UA_SECTIONS = [
  ['conclusion', 'Executive read'], ['time', 'Time Status'],
  ['bycode', 'Planned vs Actual by code'], ['critical', 'Critical Path Analyzer'],
];

async function _exportPdf() {
  if (!_shownReport) { showError('Analyze the update first, then export.'); return; }
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/update/report`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report: _shownReport, preview: true, code_filter: _pdfCodeFilter() }),
    });
    const data = await resp.json();
    if (!data.ok) { showError(`Preview failed: ${data.error || 'unknown error'}`); return; }
    _showPdfPreview(data.html);
  } catch { showError('Could not reach the local server for the preview.'); }
}

function _pdfCodeFilter() {
  // Carry the on-screen code selection into the PDF so preview == PDF.
  if (_pickedTypes.length === 1) return { type: _pickedTypes[0] };
  if (_pickedTypes.length > 1 && _shownReport._combined) {
    return { types: _pickedTypes, rows: _shownReport._combined, label: _pickedTypes.join(' · ') };
  }
  return null;
}

function _showPdfPreview(reportHtml) {
  const existing = document.getElementById('per-preview-overlay');
  if (existing) existing.remove();
  const ov = document.createElement('div');
  ov.id = 'per-preview-overlay';
  ov.className = 'per-preview-overlay';
  const picks = UA_SECTIONS.map(([k, l]) =>
    `<label class="per-pick"><input type="checkbox" class="ua-sec-cb" value="${k}" checked> ${escapeHtml(l)}</label>`).join('');
  ov.innerHTML = `<div class="per-preview-box">
      <div class="per-preview-bar"><span class="per-preview-title">Report preview — choose what to include, then print or save</span>
        <span class="per-preview-actions">
          <button class="btn-secondary" id="ua-preview-close">Close</button>
          <button class="btn-secondary" id="ua-preview-print">🖨 Print…</button>
          <button class="btn-primary" id="ua-preview-save">Save as PDF</button></span></div>
      <div class="per-preview-body">
        <div class="per-preview-pick"><div class="per-pick-h">Include sections</div>${picks}
          <div class="per-pick-controls"><button class="btn-mini" id="ua-pick-all">All</button><button class="btn-mini" id="ua-pick-none">None</button></div></div>
        <iframe class="per-preview-frame" id="ua-preview-frame" title="Report preview"></iframe>
      </div>
    </div>`;
  document.body.appendChild(ov);
  const frame = document.getElementById('ua-preview-frame');
  const close = () => ov.remove();
  ov.addEventListener('click', e => { if (e.target === ov) close(); });
  document.getElementById('ua-preview-close').addEventListener('click', close);

  const cbs = () => Array.from(ov.querySelectorAll('.ua-sec-cb'));
  const selected = () => cbs().filter(c => c.checked).map(c => c.value);
  const applyToFrame = () => {
    const doc = frame.contentDocument;
    if (!doc) return;
    const on = new Set(selected());
    doc.querySelectorAll('[data-sec]').forEach(el => { el.style.display = on.has(el.getAttribute('data-sec')) ? '' : 'none'; });
  };
  frame.onload = applyToFrame;
  frame.srcdoc = reportHtml;
  cbs().forEach(c => c.addEventListener('change', applyToFrame));
  document.getElementById('ua-pick-all').addEventListener('click', () => { cbs().forEach(c => { c.checked = true; }); applyToFrame(); });
  document.getElementById('ua-pick-none').addEventListener('click', () => { cbs().forEach(c => { c.checked = false; }); applyToFrame(); });

  document.getElementById('ua-preview-print').addEventListener('click', () => {
    applyToFrame();
    try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch { showError('Could not open the print dialog.'); }
  });
  document.getElementById('ua-preview-save').addEventListener('click', async () => {
    const outputPath = await window.pywebview.api.choose_save_path('update_analysis.pdf', 'pdf');
    if (!outputPath) return;
    const btn = document.getElementById('ua-preview-save');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/update/report`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report: _shownReport, output_path: outputPath, sections: selected(), code_filter: _pdfCodeFilter() }),
      });
      const data = await resp.json();
      if (!data.ok) showError(`PDF export failed: ${data.error || 'unknown error'}`);
      else close();
    } catch { showError('Could not reach the local server to export the PDF.'); }
    finally { if (btn) { btn.disabled = false; btn.textContent = 'Save as PDF'; } }
  });
}

async function _exportExcel() {
  if (!_shownReport) { showError('Analyze the update first, then export.'); return; }
  const outputPath = await window.pywebview.api.choose_save_path('update_analysis.xlsx', 'xlsx');
  if (!outputPath) return;
  const btn = document.getElementById('ua-export-xlsx');
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/update/excel`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report: _shownReport, output_path: outputPath }),
    });
    const data = await resp.json();
    if (!data.ok) showError(`Excel export failed: ${data.error || 'unknown error'}`);
  } catch { showError('Could not reach the local server to export to Excel.'); }
  finally { if (btn) { btn.disabled = false; btn.textContent = 'Export Excel'; } }
}
