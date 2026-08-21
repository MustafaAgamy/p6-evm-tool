// Critical Path Analyzer — compare the critical path across 2–3 schedules.
//
// The currently-open schedule is always the CURRENT update. The user picks the
// previous update and/or the baseline, per the chosen mode. Slice 1: mode picker,
// file slots, and the critical & near-critical census (count + % per schedule +
// variance). Later slices add the dashboard, driving-path lanes, tables and exports.
import { state }      from './state.js';
import { showError }  from './render.js';
import { escapeHtml } from './format.js';

const MODES = [
  ['two_updates',       'Two updates',          'Update A vs Update B — this period vs a prior one',  ['previous']],
  ['update_baseline',   'Update vs Baseline',   'Current forecast path vs the plan',                  ['baseline']],
  ['two_plus_baseline', 'Two updates + Baseline','Both updates and the baseline, side by side',       ['previous', 'baseline']],
];
const ROLE_LABEL = { current: 'Current update', previous: 'Previous update', baseline: 'Baseline' };

let _mode = 'update_baseline';
let _picked = { previous: null, baseline: null };   // chosen file paths
let _shownReport = null;
let _milestone = null;   // selected finish-milestone code (null = governing)
let _level = 0;          // driving-path rollup: 0 work front · 1 area · 2 phase

function _currName() {
  const p = state.currentXmlPath || state.currentCachedPath || '';
  return p.split(/[\\/]/).pop() || 'current schedule';
}

function _neededRoles() {
  return (MODES.find(m => m[0] === _mode) || MODES[1])[3];
}

// ── Entry ────────────────────────────────────────────────────────────────────

export function renderCritPathPanel() {
  _injectStyle();
  const body = document.getElementById('critpath-body');
  if (!body) return;
  if (!state.currentXmlPath && !state.currentCachedPath) {
    body.innerHTML = `<div class="cpa-empty">Import a schedule first, then open the Critical Path Analyzer.</div>`;
    return;
  }
  body.innerHTML = `
    <div class="mod-sec">Critical Path Analyzer</div>
    <div class="cpa-note">Compare the critical path across your schedules — how it rerouted, which activities are critical and near-critical, and what it does to completion. The open schedule is the <b>current update</b>; pick what to compare it against.</div>
    <div id="cpa-modes" class="cpa-modes"></div>
    <div id="cpa-inputs" class="cpa-inputs"></div>
    <div class="cpa-actions"><button class="btn-primary" id="cpa-run" disabled>Analyze critical path</button></div>
    <div id="cpa-report"></div>`;
  _renderModes();
  _renderInputs();
  document.getElementById('cpa-run').addEventListener('click', _run);
}

function _renderModes() {
  const box = document.getElementById('cpa-modes');
  box.innerHTML = MODES.map(([key, title, sub]) =>
    `<button class="cpa-mode${key === _mode ? ' on' : ''}" data-mode="${key}">
       <div class="cpa-mt">${escapeHtml(title)}</div><div class="cpa-md">${escapeHtml(sub)}</div>
     </button>`).join('');
  box.querySelectorAll('.cpa-mode').forEach(b =>
    b.addEventListener('click', () => { _mode = b.dataset.mode; _renderModes(); _renderInputs(); }));
}

function _renderInputs() {
  const box = document.getElementById('cpa-inputs');
  const slots = [`<div class="cpa-slot filled"><div class="cpa-slbl">${ROLE_LABEL.current}</div>
      <div class="cpa-sval"><b>${escapeHtml(_currName())}</b><span class="cpa-tag">open schedule</span></div></div>`];
  for (const role of _neededRoles()) {
    const name = _picked[role] ? _picked[role].split(/[\\/]/).pop() : null;
    slots.push(`<div class="cpa-slot${name ? ' filled' : ''}" data-role="${role}">
        <div class="cpa-slbl">${ROLE_LABEL[role]}</div>
        <div class="cpa-sval">${name ? `<b>${escapeHtml(name)}</b>` : '<span class="cpa-dim">No file chosen</span>'}
          <button class="btn-mini cpa-pick" data-role="${role}">${name ? 'Change…' : 'Choose file…'}</button></div>
      </div>`);
  }
  box.innerHTML = slots.join('');
  box.querySelectorAll('.cpa-pick').forEach(b =>
    b.addEventListener('click', () => _pick(b.dataset.role)));
  _syncRun();
}

async function _pick(role) {
  try {
    const path = await window.pywebview.api.choose_file();
    if (!path) return;
    _picked[role] = path;
    _renderInputs();
  } catch { showError('Could not open the file picker.'); }
}

function _syncRun() {
  const ready = _neededRoles().every(r => _picked[r]);
  const btn = document.getElementById('cpa-run');
  if (btn) btn.disabled = !ready;
}

async function _run(keepMilestone) {
  const rep = document.getElementById('cpa-report');
  rep.innerHTML = `<div class="cpa-note">Reading the schedules and comparing critical paths…</div>`;
  if (!keepMilestone) { _milestone = null; _level = 0; }
  const payload = { mode: _mode, current_path: state.currentXmlPath || '', cached_path: state.currentCachedPath || '',
                    milestone_code: _milestone, summary_level: _level };
  for (const role of _neededRoles()) payload[`${role}_path`] = _picked[role];
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/critpath/analyze`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!data.ok) { rep.innerHTML = `<div class="cpa-empty">${escapeHtml(data.error || 'Could not analyze.')}</div>`; return; }
    _shownReport = data.report;
    _renderReport(data.report);
  } catch { rep.innerHTML = `<div class="cpa-empty">Could not reach the local server. Try re-importing the schedule.</div>`; }
}

// ── Render report ────────────────────────────────────────────────────────────

function _renderReport(report) {
  document.getElementById('cpa-report').innerHTML = `
    <div class="cpa-sech">Critical &amp; near-critical census</div>
    <div class="cpa-card">${_censusHtml(report)}</div>

    <div class="cpa-sech">Driving path — schedule by schedule</div>
    <div class="cpa-card">${_lanesHtml(report)}</div>`;
  _wireLaneControls(report);
}

// ── Driving-path lanes (the §3 chart per schedule, new path highlighted) ─────

function _fdate(s) { return s || '—'; }
function _sv(v) { return v == null ? '—' : `${v > 0 ? '+' : ''}${v}`; }

function _milestoneSelect(report) {
  const list = report.milestones_list || [];
  if (!list.length) return '';
  const sel = report.selected_milestone;
  const opts = list.map(m => {
    const gov = m.is_governing ? ' (governing)' : '';
    const on = (sel == null && m.is_governing) || sel === m.id;
    return `<option value="${escapeHtml(m.id)}"${on ? ' selected' : ''}>◆ ${escapeHtml(m.name)}${gov}</option>`;
  }).join('');
  return `<span>Milestone</span><select id="cpa-ms" class="cpa-sel">${opts}</select>`;
}

function _lanesHtml(report) {
  const lanes = report.lanes || [];
  const slicer = `<div class="cpa-slicer">${_milestoneSelect(report)}
    <span style="margin-left:auto">Summarise at</span>
    <select id="cpa-level" class="cpa-sel">
      <option value="0"${_level === 0 ? ' selected' : ''}>Work front</option>
      <option value="1"${_level === 1 ? ' selected' : ''}>Area / zone</option>
      <option value="2"${_level === 2 ? ' selected' : ''}>Phase</option>
    </select></div>`;
  if (!lanes.some(l => (l.boxes || []).length)) {
    return slicer + `<div class="cpa-note">No governing completion milestone with a driving path was found in these schedules.</div>`;
  }
  const laneCls = { baseline: 'bl', previous: 'prev', current: 'curr' };
  const html = lanes.map(lane => {
    const ms = lane.milestone || {};
    const chain = [`<div class="cpa-msbox"><div class="cpa-msflag">◆ Milestone</div>
      <div class="cpa-mst">${escapeHtml(ms.name || '')}</div>
      <div class="cpa-msr"><span>${lane.role === 'baseline' ? 'BL Finish' : 'Exp Finish'}</span><b>${_fdate(lane.role === 'baseline' ? ms.baseline_finish : ms.expected_finish)}</b></div>
      <div class="cpa-msr"><span>Delay</span><b class="${(ms.slip_days || 0) > 0 ? 'cpa-bad' : ''}">${_sv(ms.slip_days)} d</b></div></div>`];
    (lane.boxes || []).forEach(b => {
      chain.push(`<div class="cpa-arw">▸</div>`);
      const st = b.state || 'stayed';
      const flag = st === 'new' ? `<div class="cpa-newflag">NEW ON PATH</div>`
                 : st === 'left' ? `<div class="cpa-dropflag">LEFT PATH</div>` : '';
      const last = st === 'left'
        ? `<div class="cpa-full"><div class="cpa-k">Float now</div><div class="cpa-v" style="color:var(--success)">${b.driver_tf == null ? '—' : _sv(b.driver_tf) + ' wd'}</div></div>`
        : `<div class="cpa-full"><div class="cpa-k">Slip</div><div class="cpa-v ${(b.slip_days || 0) > 0 ? 'cpa-bad' : ''}">${_sv(b.slip_days)} d</div></div>`;
      chain.push(`<div class="cpa-box cpa-${st}">${flag}
        <div class="cpa-bt">${escapeHtml(b.name || '')}</div>
        <div class="cpa-bcrumb">${escapeHtml(b.crumb || '')}</div>
        <div class="cpa-b4">
          <div><div class="cpa-k">Actual</div><div class="cpa-v">${Math.round(b.pct || 0)}%</div></div>
          <div><div class="cpa-k">Exp Finish</div><div class="cpa-v">${_fdate(b.exp_finish)}</div></div>
          ${last}
        </div></div>`);
    });
    return `<div class="cpa-lane">
      <div class="cpa-lanehdr"><span class="cpa-lanetag ${laneCls[lane.role]}">${escapeHtml(lane.label)}</span>
        <span class="cpa-lanesub">${escapeHtml(lane.sub || '')}</span></div>
      <div class="cpa-chain">${chain.join('')}</div></div>`;
  }).join('');
  const legend = `<div class="cpa-leg">
    <span class="cpa-sw" style="background:rgba(220,38,38,.12);border:2px solid var(--danger)"></span>New on critical path (the reroute)
    <span class="cpa-sw" style="background:rgba(148,163,184,.20);border:1px dashed var(--muted)"></span>Left the path (float recovered)
    <span class="cpa-sw" style="background:var(--card-bg);border:1px solid var(--border)"></span>Stayed on path
    <span class="cpa-sw" style="background:var(--card-bg);border:1px solid var(--success)"></span>Complete</div>`;
  return slicer + html + legend;
}

function _wireLaneControls(report) {
  const ms = document.getElementById('cpa-ms');
  if (ms) ms.addEventListener('change', () => { _milestone = ms.value; _run(true); });
  const lvl = document.getElementById('cpa-level');
  if (lvl) lvl.addEventListener('change', () => { _level = parseInt(lvl.value, 10) || 0; _run(true); });
}

function _fmtCpli(v) { return v == null ? 'n/a' : v.toFixed(2); }

// Difference chip a→b, coloured by whether a rise is bad for this measure.
function _dchip(a, b, unit, higherIsBad) {
  if (a == null || b == null) return '<span class="cpa-dim">—</span>';
  const d = Math.round((a - b) * 100) / 100;
  if (d === 0) return '<span class="cpa-chip flat">■ 0' + unit + '</span>';
  const bad = higherIsBad ? d > 0 : d < 0;
  const cls = bad ? 'up' : 'down';
  const arw = d > 0 ? '▲' : '▼';
  return `<span class="cpa-chip ${cls}">${arw} ${d > 0 ? '+' : ''}${d}${unit}</span>`;
}

function _censusHtml(report) {
  const c = report.census || {};
  const roles = report.roles || [];
  const has = r => roles.includes(r);
  const col = r => has(r) ? `<th class="num">${escapeHtml(ROLE_LABEL[r])}</th>` : '';
  const cur = c.current || {}, prev = c.previous || {}, bl = c.baseline || {};
  const cell = (r, get) => has(r) ? `<td class="num">${get(c[r] || {})}</td>` : '';
  const cnt = (n, p) => o => (o[n] == null ? '—' : `${o[n]} · <b>${o[p]}%</b>`);
  const wd = k => o => (o[k] == null ? '—' : `${o[k]} wd`);

  // [label, value-getter, current-key, higherIsBad, unit]
  const rows = [
    ['Critical activities <span class="cpa-dim">(TF ≤ 0)</span>', cnt('critical', 'critical_pct'), 'critical_pct', true, ' pts'],
    ['Near-critical <span class="cpa-dim">(0 &lt; TF &lt; 10 wd)</span>', cnt('near', 'near_pct'), 'near_pct', true, ' pts'],
    ['Critical path length <span class="cpa-dim">(remaining, wd)</span>', wd('path_length_wd'), 'path_length_wd', true, ' wd'],
    ['Total float · finish <span class="cpa-dim">(wd)</span>', wd('total_float_wd'), 'total_float_wd', false, ' wd'],
    ['CPLI · project finish', o => _fmtCpli(o.cpli), 'cpli', false, ''],
  ];

  const body = rows.map(([label, get, key, higherIsBad, unit]) => `<tr>
      <td>${label}</td>
      ${cell('baseline', get)}${cell('previous', get)}${cell('current', get)}
      ${has('previous') ? `<td class="num">${_dchip(cur[key], prev[key], unit, higherIsBad)}</td>` : ''}
      ${has('baseline') ? `<td class="num">${_dchip(cur[key], bl[key], unit, higherIsBad)}</td>` : ''}
    </tr>`).join('');

  return `<table class="cpa-table">
    <thead><tr><th>Measure</th>${col('baseline')}${col('previous')}${col('current')}
      ${has('previous') ? '<th class="num">Δ this period</th>' : ''}
      ${has('baseline') ? '<th class="num">Δ vs baseline</th>' : ''}</tr></thead>
    <tbody>${body}</tbody></table>
    <div class="cpa-leg">% = share of all counted activities. CPLI = (remaining path length + total float) ÷ remaining path length; below 0.95 = at risk. Baseline length is the full path (no progress yet).</div>`;
}

// ── Style ────────────────────────────────────────────────────────────────────

function _injectStyle() {
  if (document.getElementById('cpa-style')) return;
  const s = document.createElement('style');
  s.id = 'cpa-style';
  s.textContent = `
    .cpa-empty { color: var(--muted); padding: 40px; text-align: center; }
    .cpa-note { color: var(--muted); font-size: 13px; line-height: 1.5; margin: 6px 0 14px; }
    .cpa-modes { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
    .cpa-mode { flex: 1; min-width: 200px; text-align: left; background: var(--card-bg); border: 1.5px solid var(--border); border-radius: 10px; padding: 11px 13px; cursor: pointer; color: var(--text); }
    .cpa-mode.on { border-color: var(--accent); background: rgba(59,130,246,.07); }
    .cpa-mt { font-weight: 700; font-size: 13px; }
    .cpa-mode.on .cpa-mt { color: var(--accent); }
    .cpa-md { color: var(--muted); font-size: 11.5px; margin-top: 3px; }
    .cpa-inputs { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
    .cpa-slot { flex: 1; min-width: 220px; border: 1.5px dashed var(--border); border-radius: 10px; padding: 10px 12px; }
    .cpa-slot.filled { border-style: solid; }
    .cpa-slbl { font-size: 10.5px; text-transform: uppercase; letter-spacing: .4px; color: var(--muted); font-weight: 700; }
    .cpa-sval { display: flex; align-items: center; gap: 8px; margin-top: 5px; font-size: 13px; flex-wrap: wrap; }
    .cpa-tag { font-size: 10.5px; color: var(--accent); background: rgba(59,130,246,.1); border-radius: 5px; padding: 1px 7px; }
    .cpa-dim { color: var(--muted); }
    .cpa-actions { margin: 4px 0 16px; }
    .cpa-sech { font-size: 12px; text-transform: uppercase; letter-spacing: .5px; color: var(--accent); font-weight: 800; margin: 20px 2px 10px; }
    .cpa-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
    .cpa-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
    .cpa-table th, .cpa-table td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); }
    .cpa-table th { font-size: 11px; text-transform: uppercase; letter-spacing: .4px; color: var(--muted); font-weight: 700; }
    .cpa-table td.num, .cpa-table th.num { text-align: right; font-variant-numeric: tabular-nums; }
    .cpa-chip { display: inline-block; border-radius: 6px; padding: 2px 7px; font-size: 11.5px; font-weight: 700; }
    .cpa-chip.up { background: rgba(220,38,38,.12); color: var(--danger); }
    .cpa-chip.down { background: rgba(22,163,74,.12); color: var(--success); }
    .cpa-chip.flat { background: var(--border); color: var(--muted); }
    .cpa-leg { color: var(--muted); font-size: 11.5px; margin-top: 10px; line-height: 1.6; }
    .cpa-sw { display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: -2px; margin: 0 5px 0 14px; }
    .cpa-leg .cpa-sw:first-child { margin-left: 0; }
    /* slicer */
    .cpa-slicer { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; font-size: 12.5px; color: var(--muted); }
    .cpa-sel { padding: 5px 8px; border: 1px solid var(--border); border-radius: 7px; background: var(--card-bg); color: var(--text); font-size: 12.5px; }
    /* lanes */
    .cpa-lane { margin-bottom: 16px; }
    .cpa-lanehdr { display: flex; align-items: center; gap: 9px; margin-bottom: 7px; }
    .cpa-lanetag { font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .5px; padding: 3px 9px; border-radius: 6px; }
    .cpa-lanetag.bl { background: rgba(148,163,184,.20); color: var(--muted); }
    .cpa-lanetag.prev { background: rgba(217,119,6,.15); color: var(--warning); }
    .cpa-lanetag.curr { background: rgba(59,130,246,.15); color: var(--accent); }
    .cpa-lanesub { color: var(--muted); font-size: 11.5px; }
    .cpa-chain { display: flex; align-items: stretch; flex-wrap: wrap; gap: 5px; }
    .cpa-arw { display: flex; align-items: center; color: var(--muted); font-weight: 800; font-size: 17px; }
    .cpa-msbox { flex: none; width: 178px; border: 2px solid var(--accent); border-radius: 12px; padding: 11px 12px; background: rgba(59,130,246,.08); }
    .cpa-msflag { font-size: 10px; text-transform: uppercase; letter-spacing: .4px; color: var(--accent); opacity: .85; margin-bottom: 6px; }
    .cpa-mst { font-size: 12.5px; font-weight: 800; color: var(--accent); line-height: 1.2; margin-bottom: 6px; }
    .cpa-msr { display: flex; justify-content: space-between; font-size: 11.5px; margin: 2px 0; color: var(--text); }
    .cpa-msr span { color: var(--muted); }
    .cpa-box { flex: none; width: 176px; border: 1px solid var(--border); border-radius: 11px; padding: 9px 11px; background: var(--card-bg); position: relative; }
    .cpa-box.cpa-done { border-color: var(--success); }
    .cpa-box.cpa-new { border: 2px solid var(--danger); background: rgba(220,38,38,.07); box-shadow: 0 0 0 3px rgba(220,38,38,.10); }
    .cpa-box.cpa-left { border-style: dashed; opacity: .6; background: rgba(148,163,184,.10); }
    .cpa-newflag { position: absolute; top: -9px; left: 9px; background: var(--danger); color: #fff; font-size: 9px; font-weight: 800; letter-spacing: .4px; padding: 2px 7px; border-radius: 5px; }
    .cpa-dropflag { position: absolute; top: -9px; left: 9px; background: var(--muted); color: #fff; font-size: 9px; font-weight: 800; letter-spacing: .4px; padding: 2px 7px; border-radius: 5px; }
    .cpa-bt { font-size: 12px; font-weight: 700; line-height: 1.2; color: var(--text); }
    .cpa-bcrumb { font-size: 9.5px; color: var(--muted); margin: 3px 0 8px; }
    .cpa-b4 { display: grid; grid-template-columns: 1fr 1fr; gap: 5px 8px; }
    .cpa-k { font-size: 9px; color: var(--muted); text-transform: uppercase; letter-spacing: .3px; }
    .cpa-v { font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--text); margin-top: 1px; }
    .cpa-full { grid-column: 1 / -1; border-top: 1px dashed var(--border); padding-top: 4px; }
    .cpa-bad { color: var(--danger); }
  `;
  document.head.appendChild(s);
}
