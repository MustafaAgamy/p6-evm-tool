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

const CP_SECTIONS = [
  ['verdict', 'Verdict banner'],
  ['dashboard', 'Execution dashboard'],
  ['driving_path', 'Driving path — schedule by schedule'],
  ['census', 'Critical & near-critical census'],
  ['milestones', 'Every milestone · finish comparison'],
  ['float_migration', 'Float migration'],
  ['recommendation', 'Effect & recommendation'],
];

function _renderReport(report) {
  document.getElementById('cpa-report').innerHTML = `
    <div class="cpa-exports">
      <button class="btn-secondary" id="cpa-export-pdf">Export PDF</button>
      <button class="btn-secondary" id="cpa-export-xlsx">Export Excel</button>
    </div>
    ${_conclusionBanner(report)}

    <div class="cpa-sech">Execution dashboard</div>
    <div class="cpa-card">${_dashboardHtml(report)}</div>

    <div class="cpa-sech">Driving path — schedule by schedule</div>
    <div class="cpa-card">${_lanesHtml(report)}</div>

    <div class="cpa-sech">Critical &amp; near-critical census</div>
    <div class="cpa-card">${_censusHtml(report)}</div>

    <div class="cpa-sech">Every milestone · finish comparison &amp; path health</div>
    <div class="cpa-card">${_milestonesHtml(report)}</div>

    <div class="cpa-sech">Float migration</div>
    <div class="cpa-card">${_migrationHtml(report)}</div>

    <div class="cpa-sech">Effect on completion &amp; recommendation</div>
    <div class="cpa-card">${_recoHtml(report)}</div>`;
  _wireLaneControls(report);
  document.getElementById('cpa-export-pdf').addEventListener('click', _openPreview);
  document.getElementById('cpa-export-xlsx').addEventListener('click', _exportExcel);
}

// ── Export: PDF preview (Report Contents picker) + Excel ─────────────────────

async function _openPreview() {
  if (!_shownReport) return;
  let html = '';
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/critpath/report`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report: _shownReport, preview: true }),
    });
    const data = await resp.json();
    if (!data.ok) { showError(data.error || 'Could not build the preview.'); return; }
    html = data.html;
  } catch { showError('Could not reach the local server for the preview.'); return; }

  const ex = document.getElementById('cpa-preview-overlay'); if (ex) ex.remove();
  const ov = document.createElement('div');
  ov.id = 'cpa-preview-overlay';
  ov.className = 'per-preview-overlay';
  const picks = CP_SECTIONS.map(([k, l]) =>
    `<label class="per-pick"><input type="checkbox" class="cpa-sec-cb" value="${k}" checked> ${escapeHtml(l)}</label>`).join('');
  ov.innerHTML = `<div class="per-preview-box">
      <div class="per-preview-bar"><span class="per-preview-title">Report preview — choose what to include, then print or save</span>
        <span class="per-preview-actions">
          <button class="btn-secondary" id="cpa-preview-close">Close</button>
          <button class="btn-secondary" id="cpa-preview-print">🖨 Print…</button>
          <button class="btn-primary" id="cpa-preview-save">Save as PDF</button></span></div>
      <div class="per-preview-body">
        <div class="per-preview-pick"><div class="per-pick-h">Include sections</div>${picks}
          <div class="per-pick-controls"><button class="btn-mini" id="cpa-pick-all">All</button><button class="btn-mini" id="cpa-pick-none">None</button></div>
        </div>
        <iframe class="per-preview-frame" id="cpa-preview-frame" title="Report preview"></iframe>
      </div>
    </div>`;
  document.body.appendChild(ov);
  const frame = document.getElementById('cpa-preview-frame');
  const close = () => ov.remove();
  ov.addEventListener('click', e => { if (e.target === ov) close(); });
  document.getElementById('cpa-preview-close').addEventListener('click', close);

  const cbs = () => Array.from(ov.querySelectorAll('.cpa-sec-cb'));
  const selected = () => cbs().filter(c => c.checked).map(c => c.value);
  const applyToFrame = () => {
    const doc = frame.contentDocument;
    if (!doc) return;
    const on = new Set(selected());
    doc.querySelectorAll('[data-sec]').forEach(el => { el.style.display = on.has(el.getAttribute('data-sec')) ? '' : 'none'; });
  };
  frame.onload = applyToFrame;
  frame.srcdoc = html;
  cbs().forEach(c => c.addEventListener('change', applyToFrame));
  document.getElementById('cpa-pick-all').addEventListener('click', () => { cbs().forEach(c => { c.checked = true; }); applyToFrame(); });
  document.getElementById('cpa-pick-none').addEventListener('click', () => { cbs().forEach(c => { c.checked = false; }); applyToFrame(); });
  document.getElementById('cpa-preview-print').addEventListener('click', () => {
    applyToFrame();
    try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch { showError('Could not open the print dialog.'); }
  });
  document.getElementById('cpa-preview-save').addEventListener('click', async () => {
    const outputPath = await window.pywebview.api.choose_save_path('critical_path_analyzer.pdf', 'pdf');
    if (!outputPath) return;
    const btn = document.getElementById('cpa-preview-save');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/critpath/report`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report: _shownReport, output_path: outputPath, sections: selected() }),
      });
      const data = await resp.json();
      if (!data.ok) showError(`PDF export failed: ${data.error || 'unknown error'}`);
      else close();
    } catch { showError('Could not reach the local server to export the PDF.'); }
    finally { if (btn) { btn.disabled = false; btn.textContent = 'Save as PDF'; } }
  });
}

async function _exportExcel() {
  if (!_shownReport) return;
  const outputPath = await window.pywebview.api.choose_save_path('critical_path_analyzer.xlsx', 'xlsx');
  if (!outputPath) return;
  const btn = document.getElementById('cpa-export-xlsx');
  if (btn) { btn.disabled = true; btn.textContent = 'Exporting…'; }
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/critpath/excel`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report: _shownReport, output_path: outputPath }),
    });
    const data = await resp.json();
    if (!data.ok) showError(`Excel export failed: ${data.error || 'unknown error'}`);
  } catch { showError('Could not reach the local server to export Excel.'); }
  finally { if (btn) { btn.disabled = false; btn.textContent = 'Export Excel'; } }
}

// ── Execution dashboard (charts + Critical Path Health) ──────────────────────

function _conclusionBanner(report) {
  const d = report.dashboard || {};
  const st = d.status || 'warn';
  return `<div class="cpa-verdict cpa-vd-${st}">
    <span class="cpa-vdtag">${escapeHtml(d.status_label || '')}</span>
    <span class="cpa-vdtext">${escapeHtml(report.conclusion || d.verdict || '')}</span></div>`;
}

function _kpiDelta(k) {
  if (k.delta == null || k.delta === 0) return k.delta === 0 ? '<span class="cpa-dim">no change</span>' : '';
  const bad = k.higher_is_bad ? k.delta > 0 : k.delta < 0;
  const arw = k.delta > 0 ? '▲' : '▼';
  return `<span class="cpa-kd ${bad ? 'bad' : 'good'}">${arw} ${k.delta > 0 ? '+' : ''}${k.delta}</span>`;
}

function _dashboardHtml(report) {
  const d = report.dashboard || {};
  const kpis = (d.kpis || []).map(k => `<div class="cpa-kpi">
      <div class="cpa-kk">${escapeHtml(k.label)}</div>
      <div class="cpa-kv">${k.value == null ? 'n/a' : (k.key === 'cpli' ? Number(k.value).toFixed(2) : k.value)}${k.key === 'length' ? ' <span class="cpa-ku">wd</span>' : ''}</div>
      <div class="cpa-kr">${_kpiDelta(k)}</div></div>`).join('');
  const factors = (d.factors || []).map(f => `<li>${escapeHtml(f)}</li>`).join('');
  return `<div class="cpa-dash">
      <div class="cpa-health cpa-hb-${d.status || 'warn'}">
        <div class="cpa-hgauge">${_gauge(d.cpli, d.status)}</div>
        <div class="cpa-hbody">
          <div class="cpa-htitle">Critical Path Health</div>
          <div class="cpa-hverdict">${escapeHtml(d.verdict || '')}</div>
          <ul class="cpa-hfactors">${factors}</ul>
        </div>
      </div>
      <div class="cpa-kpis">${kpis}</div>
    </div>
    <div class="cpa-charts">
      <div class="cpa-chart"><div class="cpa-cht">Critical &amp; near-critical by schedule</div>${_barsCritNear(d.charts)}</div>
      <div class="cpa-chart"><div class="cpa-cht">CPLI trend</div>${_lineCpli(d.charts)}</div>
      <div class="cpa-chart"><div class="cpa-cht">Milestone slip vs baseline (wd)</div>${_barsMsVar(d.charts)}</div>
    </div>`;
}

function _gauge(cpli, status) {
  const lo = 0.7, hi = 1.2, r = 58, cx = 75, cy = 72;
  const col = status === 'bad' ? 'var(--danger)' : status === 'warn' ? 'var(--warning)' : 'var(--success)';
  const frac = cpli == null ? 0 : Math.max(0, Math.min(1, (Math.max(lo, Math.min(hi, cpli)) - lo) / (hi - lo)));
  const ang = Math.PI * (1 - frac);
  const x = (cx + r * Math.cos(ang)).toFixed(1), y = (cy - r * Math.sin(ang)).toFixed(1);
  return `<svg width="150" height="84" viewBox="0 0 150 84" role="img" aria-label="CPLI gauge">
    <path d="M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}" fill="none" stroke="var(--border)" stroke-width="11" stroke-linecap="round"/>
    <path d="M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${x} ${y}" fill="none" stroke="${col}" stroke-width="11" stroke-linecap="round"/>
    <text x="${cx}" y="${cy - 8}" text-anchor="middle" font-size="23" font-weight="800" fill="var(--text)">${cpli == null ? 'n/a' : cpli.toFixed(2)}</text>
    <text x="${cx}" y="${cy + 7}" text-anchor="middle" font-size="9.5" fill="var(--muted)">CPLI</text>
  </svg>`;
}

function _chartColor(role) {
  return role === 'baseline' ? '#94a3b8' : role === 'previous' ? 'var(--warning)' : 'var(--accent)';
}

function _barsCritNear(charts) {
  const s = (charts || {}).crit_near || {};
  const roles = s.roles || [];
  if (!roles.length) return '<div class="cpa-nochart">—</div>';
  const vals = roles.flatMap((_, i) => [s.critical[i] || 0, s.near[i] || 0]);
  const max = Math.max(1, ...vals);
  const W = 230, H = 130, base = 104, top = 12, gw = W / roles.length, bw = 18;
  let out = `<svg width="100%" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">`;
  out += `<line x1="6" y1="${base}" x2="${W - 6}" y2="${base}" stroke="var(--border)"/>`;
  roles.forEach((role, i) => {
    const cx = i * gw + gw / 2;
    const hc = (base - top) * (s.critical[i] || 0) / max, hn = (base - top) * (s.near[i] || 0) / max;
    out += `<rect x="${cx - bw - 2}" y="${base - hc}" width="${bw}" height="${hc}" rx="2" fill="var(--danger)"/>`;
    out += `<rect x="${cx + 2}" y="${base - hn}" width="${bw}" height="${hn}" rx="2" fill="var(--warning)"/>`;
    out += `<text x="${cx}" y="${base + 13}" text-anchor="middle" font-size="9" fill="var(--muted)">${escapeHtml(ROLE_LABEL[role].split(' ')[0])}</text>`;
    out += `<text x="${cx - bw / 2 - 2}" y="${base - hc - 3}" text-anchor="middle" font-size="9" font-weight="700" fill="var(--danger)">${s.critical[i] || 0}</text>`;
    out += `<text x="${cx + bw / 2 + 2}" y="${base - hn - 3}" text-anchor="middle" font-size="9" font-weight="700" fill="var(--warning)">${s.near[i] || 0}</text>`;
  });
  out += `</svg><div class="cpa-clegend"><span class="cpa-dot" style="background:var(--danger)"></span>Critical <span class="cpa-dot" style="background:var(--warning)"></span>Near</div>`;
  return out;
}

function _lineCpli(charts) {
  const s = (charts || {}).cpli_trend || {};
  const roles = s.roles || [], vals = s.values || [];
  if (!roles.length) return '<div class="cpa-nochart">—</div>';
  const lo = 0.7, hi = 1.15, W = 230, H = 130, base = 104, top = 14, l = 8, r = W - 8;
  const y = v => base - (base - top) * (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo);
  const x = i => roles.length === 1 ? (l + r) / 2 : l + (r - l) * i / (roles.length - 1);
  let out = `<svg width="100%" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">`;
  // 0.95 and 1.0 reference lines
  [[0.95, 'var(--danger)'], [1.0, 'var(--muted)']].forEach(([v, c]) => {
    out += `<line x1="${l}" y1="${y(v).toFixed(1)}" x2="${r}" y2="${y(v).toFixed(1)}" stroke="${c}" stroke-dasharray="3 3" opacity=".5"/>`;
    out += `<text x="${r}" y="${(y(v) - 2).toFixed(1)}" text-anchor="end" font-size="8" fill="${c}">${v.toFixed(2)}</text>`;
  });
  const pts = vals.map((v, i) => v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`).filter(Boolean);
  if (pts.length > 1) out += `<polyline points="${pts.join(' ')}" fill="none" stroke="var(--accent)" stroke-width="2"/>`;
  vals.forEach((v, i) => {
    if (v == null) return;
    out += `<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="4" fill="var(--accent)"/>`;
    out += `<text x="${x(i).toFixed(1)}" y="${(y(v) - 8).toFixed(1)}" text-anchor="middle" font-size="9" font-weight="700" fill="var(--text)">${v.toFixed(2)}</text>`;
    out += `<text x="${x(i).toFixed(1)}" y="${base + 13}" text-anchor="middle" font-size="9" fill="var(--muted)">${escapeHtml(ROLE_LABEL[roles[i]].split(' ')[0])}</text>`;
  });
  out += `</svg>`;
  return out;
}

function _barsMsVar(charts) {
  const items = (charts || {}).ms_variance || [];
  if (!items.length) return '<div class="cpa-nochart">No milestone variance to show</div>';
  const max = Math.max(1, ...items.map(i => Math.abs(i.var)));
  return `<div class="cpa-hbars">` + items.map(it => {
    const w = Math.round(Math.abs(it.var) / max * 100);
    const cls = it.var > 0 ? 'bad' : 'good';
    return `<div class="cpa-hbrow"><div class="cpa-hblbl" title="${escapeHtml(it.name)}">${escapeHtml(it.name)}</div>
      <div class="cpa-hbtrack"><i class="cpa-hbfill ${cls}" style="width:${w}%"></i></div>
      <div class="cpa-hbval ${cls}">${it.var > 0 ? '+' : ''}${it.var}</div></div>`;
  }).join('') + `</div>`;
}

// ── Effect + recommendation ──────────────────────────────────────────────────

function _recoHtml(report) {
  const rec = (report.recommendation || []).map(r => `<li>${escapeHtml(r)}</li>`).join('');
  return `<div class="cpa-effect">${escapeHtml(report.effect || '')}</div>
    <div class="cpa-recoh">Recommendation</div>
    <ol class="cpa-reco">${rec}</ol>`;
}

// ── Every-milestone table ────────────────────────────────────────────────────

function _mschip(v) {
  if (v == null) return '<span class="cpa-dim">—</span>';
  const cls = v > 0 ? 'slip' : v < 0 ? 'gain' : 'hold';
  return `<span class="cpa-mchip ${cls}">${v > 0 ? '+' : ''}${v} d</span>`;
}
function _cplichip(v) {
  if (v == null) return '<span class="cpa-dim">n/a</span>';
  const cls = v >= 1.0 ? 'cok' : v >= 0.95 ? 'cwarn' : 'cbad';
  return `<span class="cpa-mchip ${cls}">${v.toFixed(2)}</span>`;
}

function _milestonesHtml(report) {
  const rows = report.milestones || [];
  const roles = report.roles || [];
  if (!rows.length) return `<div class="cpa-note">No finish milestones found in these schedules.</div>`;
  const has = r => roles.includes(r);
  const col = (r, lbl) => has(r) ? `<th class="num">${lbl}</th>` : '';
  const body = rows.map(m => `<tr class="${m.is_governing ? 'cpa-gov' : ''}">
      <td>${m.is_governing ? '<span class="cpa-godot"></span>' : ''}${escapeHtml(m.name)}</td>
      ${has('baseline') ? `<td class="num">${_fdate((m.finishes || {}).baseline)}</td>` : ''}
      ${has('previous') ? `<td class="num">${_fdate((m.finishes || {}).previous)}</td>` : ''}
      ${has('current') ? `<td class="num">${_fdate((m.finishes || {}).current)}</td>` : ''}
      <td class="num">${_mschip(m.var_vs_baseline_d)}</td>
      ${has('previous') ? `<td class="num">${_mschip(m.var_this_period_d)}</td>` : ''}
      <td class="num">${_cplichip(m.cpli)}</td>
      <td class="num">${m.crit_fronts == null ? '—' : `${m.crit_fronts} / ${m.near_fronts}`}</td>
    </tr>`).join('');
  return `<table class="cpa-table">
    <thead><tr><th>Milestone</th>
      ${col('baseline', 'Baseline')}${col('previous', 'Previous')}${col('current', 'Current')}
      <th class="num">vs Baseline</th>${has('previous') ? '<th class="num">This period</th>' : ''}
      <th class="num">CPLI</th><th class="num">Crit / Near fronts</th></tr></thead>
    <tbody>${body}</tbody></table>
    <div class="cpa-leg"><span class="cpa-godot"></span> governing milestone · green ahead / red behind · CPLI &lt; 0.95 = the path can't absorb more delay · Crit/Near fronts = work fronts on that milestone's driving path.</div>`;
}

// ── Float migration ──────────────────────────────────────────────────────────

function _migrationHtml(report) {
  const m = report.float_migration;
  if (!m) return `<div class="cpa-note">Load a previous update or a baseline to see how float moved.</div>`;
  const c = m.counts || {};
  const base = report.float_migration_base === 'baseline' ? 'baseline' : 'last period';
  const bands = [
    ['Near → CRITICAL', c.near_to_crit, 'bad', 'worsened'],
    ['Safe → near', c.safe_to_near, 'warn', 'eroding'],
    ['Critical → recovered', c.crit_to_recovered, 'good', 'improved'],
    ['Held critical', c.held_crit, 'flat', 'unchanged'],
  ];
  const toward = (c.near_to_crit || 0) + (c.safe_to_near || 0);
  const cells = bands.map(([lbl, n, cls, tag]) => `<div class="cpa-band">
      <div class="cpa-bandl">${lbl}</div><div class="cpa-bandv ${cls}">${n || 0}</div>
      <div class="cpa-bandt ${cls}">${tag}</div></div>`).join('');
  return `<div class="cpa-bands">${cells}</div>
    <div class="cpa-leg">${toward} activities lost float toward the critical path vs ${base} — early warning of the coming slip. Matched by activity ID.</div>`;
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
    .cpa-exports { display: flex; gap: 8px; justify-content: flex-end; margin-bottom: 10px; }
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
    /* milestone table chips */
    .cpa-mchip { display: inline-block; border-radius: 6px; padding: 2px 8px; font-size: 11.5px; font-weight: 700; }
    .cpa-mchip.slip { background: rgba(220,38,38,.12); color: var(--danger); }
    .cpa-mchip.gain { background: rgba(22,163,74,.14); color: var(--success); }
    .cpa-mchip.hold { background: var(--border); color: var(--muted); }
    .cpa-mchip.cok { background: rgba(22,163,74,.14); color: var(--success); }
    .cpa-mchip.cwarn { background: rgba(217,119,6,.15); color: var(--warning); }
    .cpa-mchip.cbad { background: rgba(220,38,38,.12); color: var(--danger); }
    .cpa-gov td { font-weight: 800; }
    .cpa-godot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--accent); margin-right: 6px; vertical-align: middle; }
    /* float bands */
    .cpa-bands { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    .cpa-band { border: 1px solid var(--border); border-radius: 8px; padding: 10px; text-align: center; }
    .cpa-bandl { font-size: 11px; color: var(--muted); font-weight: 700; }
    .cpa-bandv { font-size: 20px; font-weight: 800; margin-top: 3px; }
    .cpa-bandt { font-size: 11px; font-weight: 700; margin-top: 3px; }
    .cpa-bandv.bad, .cpa-bandt.bad { color: var(--danger); }
    .cpa-bandv.warn, .cpa-bandt.warn { color: var(--warning); }
    .cpa-bandv.good, .cpa-bandt.good { color: var(--success); }
    .cpa-bandv.flat, .cpa-bandt.flat { color: var(--muted); }
    /* verdict banner */
    .cpa-verdict { display: flex; align-items: center; gap: 12px; border-radius: 10px; padding: 12px 16px; margin-bottom: 4px; border: 1px solid var(--border); }
    .cpa-verdict.cpa-vd-bad { background: rgba(220,38,38,.08); border-color: rgba(220,38,38,.35); }
    .cpa-verdict.cpa-vd-warn { background: rgba(217,119,6,.08); border-color: rgba(217,119,6,.35); }
    .cpa-verdict.cpa-vd-good { background: rgba(22,163,74,.08); border-color: rgba(22,163,74,.35); }
    .cpa-vdtag { flex: none; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .5px; padding: 3px 10px; border-radius: 6px; color: #fff; }
    .cpa-vd-bad .cpa-vdtag { background: var(--danger); }
    .cpa-vd-warn .cpa-vdtag { background: var(--warning); }
    .cpa-vd-good .cpa-vdtag { background: var(--success); }
    .cpa-vdtext { font-size: 13.5px; font-weight: 600; color: var(--text); }
    /* dashboard layout */
    .cpa-dash { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 14px; }
    .cpa-health { flex: 1; min-width: 300px; display: flex; gap: 14px; align-items: center; border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; }
    .cpa-health.cpa-hb-bad { border-left: 4px solid var(--danger); }
    .cpa-health.cpa-hb-warn { border-left: 4px solid var(--warning); }
    .cpa-health.cpa-hb-good { border-left: 4px solid var(--success); }
    .cpa-hgauge { flex: none; }
    .cpa-htitle { font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: .4px; color: var(--muted); }
    .cpa-hverdict { font-size: 13px; font-weight: 700; color: var(--text); margin: 4px 0 6px; line-height: 1.35; }
    .cpa-hfactors { margin: 0; padding-left: 16px; font-size: 11.5px; color: var(--muted); line-height: 1.5; }
    .cpa-kpis { flex: 1; min-width: 300px; display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .cpa-kpi { border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; }
    .cpa-kk { font-size: 10.5px; text-transform: uppercase; letter-spacing: .3px; color: var(--muted); font-weight: 700; }
    .cpa-kv { font-size: 22px; font-weight: 800; margin-top: 3px; color: var(--text); }
    .cpa-ku { font-size: 12px; font-weight: 600; color: var(--muted); }
    .cpa-kr { font-size: 12px; margin-top: 3px; }
    .cpa-kd { font-weight: 700; }
    .cpa-kd.bad { color: var(--danger); }
    .cpa-kd.good { color: var(--success); }
    /* charts */
    .cpa-charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }
    .cpa-chart { border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; }
    .cpa-cht { font-size: 11.5px; font-weight: 700; color: var(--text); margin-bottom: 8px; }
    .cpa-nochart { color: var(--muted); font-size: 12px; padding: 30px 0; text-align: center; }
    .cpa-clegend { font-size: 10.5px; color: var(--muted); margin-top: 4px; }
    .cpa-dot { display: inline-block; width: 9px; height: 9px; border-radius: 2px; vertical-align: 0; margin: 0 4px 0 8px; }
    .cpa-clegend .cpa-dot:first-child { margin-left: 0; }
    .cpa-hbars { display: flex; flex-direction: column; gap: 6px; }
    .cpa-hbrow { display: flex; align-items: center; gap: 8px; font-size: 11px; }
    .cpa-hblbl { flex: none; width: 78px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text); }
    .cpa-hbtrack { flex: 1; height: 12px; background: var(--bg); border-radius: 3px; overflow: hidden; }
    .cpa-hbfill { display: block; height: 100%; border-radius: 3px; }
    .cpa-hbfill.bad { background: var(--danger); }
    .cpa-hbfill.good { background: var(--success); }
    .cpa-hbval { flex: none; width: 34px; text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; }
    .cpa-hbval.bad { color: var(--danger); }
    .cpa-hbval.good { color: var(--success); }
    /* effect + recommendation */
    .cpa-effect { font-size: 13px; line-height: 1.6; color: var(--text); background: var(--bg); border-left: 3px solid var(--accent); border-radius: 0 8px 8px 0; padding: 11px 14px; }
    .cpa-recoh { font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: .4px; color: var(--accent); margin: 14px 0 6px; }
    .cpa-reco { margin: 0; padding-left: 20px; font-size: 12.7px; line-height: 1.7; color: var(--text); }
  `;
  document.head.appendChild(s);
}
