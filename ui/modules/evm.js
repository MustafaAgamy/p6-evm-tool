import { state } from './state.js';
import { escapeHtml, fmtDate } from './format.js';

// ── pure helpers (unit-tested in tests/js/test_evm.js) ────────────────────
export function egp(n) {
  if (n == null) return '—';
  const a = Math.abs(n);
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  return Math.round(n).toLocaleString();
}
export function asPct(x) { return x == null ? '—' : `${Math.round(x * 100)}%`; }
export function spiStatus(spi) {
  if (spi == null) return { label: 'n/a', cls: 'color-neutral' };
  if (spi >= 1.0) return { label: 'Ahead / On Schedule', cls: 'color-green' };
  if (spi >= 0.95) return { label: 'Slightly Behind', cls: 'color-amber' };
  return { label: 'Behind Schedule', cls: 'color-red' };
}
// Show a gap as "Ahead X" when Earned > Planned (negative gap) instead of a confusing minus.
export function gapText(v, fmt = (x) => x) {
  if (v == null) return '—';
  return v < 0 ? `Ahead ${fmt(-v)}` : fmt(v);
}
export function overallProgress(categories, weights) {
  let sumW = 0, pw = 0, wa = 0;
  for (const [name, c] of Object.entries(categories || {})) {
    const w = (weights && weights[name] != null) ? weights[name] : (c.weight || 0);
    sumW += w;
    pw += w * (c.planned_pct || 0);
    wa += w * (c.actual_pct || 0);
  }
  return { planned: sumW ? pw / sumW : 0, actual: sumW ? wa / sumW : 0 };
}

// Overall project Planned % / Actual % — the *unnormalised* weighted sum, matching
// the Overall row of the Category Weights table exactly (Σ weight×%). Used by the
// top slicer so its numbers equal what the category table shows.
export function projectProgress(categories, weights) {
  let planned = 0, actual = 0;
  for (const [name, c] of Object.entries(categories || {})) {
    const w = (weights && weights[name] != null) ? weights[name] : (c.weight || 0);
    planned += w * (c.planned_pct || 0);
    actual += w * (c.actual_pct || 0);
  }
  return { planned, actual };
}

// ── module state ──────────────────────────────────────────────────────────
let _weights = {};       // {category: weight fraction}
let _actualCost = null;  // user override (EGP) or null → use P6
let _gap = null;
let _slice = 'Overall';  // current slicer selection (Overall or a category name)
let _e1Extras = null;    // {overall, category_actuals, gaps} from an E1 Log upload

function _wkey() { return `p6evm_w_${(state.currentResult || {}).project_name || 'x'}`; }
function _ackey() { return `p6evm_ac_${(state.currentResult || {}).project_name || 'x'}`; }

function _loadInputs(result) {
  const cats = result.categories || {};
  _weights = {};
  for (const [n, c] of Object.entries(cats)) _weights[n] = c.weight || 0;
  try {
    const w = JSON.parse(localStorage.getItem(_wkey()) || 'null');
    if (w) Object.assign(_weights, w);
    const ac = localStorage.getItem(_ackey());
    _actualCost = ac != null && ac !== '' ? Number(ac) : null;
  } catch { /* ignore */ }
}
function _saveInputs() {
  try {
    localStorage.setItem(_wkey(), JSON.stringify(_weights));
    if (_actualCost == null) localStorage.removeItem(_ackey());
    else localStorage.setItem(_ackey(), String(_actualCost));
  } catch { /* ignore */ }
}

function _effectiveAC(result) {
  if (_actualCost != null) return _actualCost;
  return result.ac;   // P6 value (editable when it equals EV)
}

// ── main render ─────────────────────────────────────────────────────────
export function renderEvm(result) {
  if (!result) return;
  _loadInputs(result);
  _gap = result.gap || null;
  const body = document.getElementById('evm-body');
  if (!body) return;
  _slice = 'Overall';
  _e1Extras = result.e1_extras || null;
  _applyE1ToCategories(result);
  body.innerHTML = `
    <div class="evm-sec">Project Progress — Planned vs Actual
      <span class="evm-hdr-right" id="evm-slicer-chips"></span></div>
    <div id="evm-slicer"></div>
    <div class="evm-sec">Executive Dashboard
      <button class="btn-mini" id="evm-edit-inputs">✎ Project Setup</button></div>
    <div id="evm-dash"></div>
    <div class="evm-sec">Planned Value vs Earned Value</div>
    <div id="evm-bar"></div>
    <div class="evm-sec">Category Weights &amp; Overall Progress</div>
    <div id="evm-cats"></div>
    <div class="evm-sec">Engineering Progress
      <span class="evm-hdr-right"><span id="evm-eng-src"></span>
        <button class="btn-mini primary" id="evm-upload-e1">⬆ Upload Log(s)</button></span></div>
    <div id="evm-eng"></div>
    <div class="evm-sec">PV vs EV Gap Analysis
      <span class="evm-hdr-right">Group by <select class="evm-sel" id="evm-gap-dim"></select></span></div>
    <div id="evm-gap"></div>`;

  renderSlicer(result);
  renderDashboard(result);
  renderBar(result);
  renderCats(result);
  renderEngineering(result);
  renderGapDimOptions(result);
  renderGap();

  document.getElementById('evm-edit-inputs').addEventListener('click', () => openInputsEditor(result));
  document.getElementById('evm-upload-e1').addEventListener('click', () => uploadE1(result));
  document.getElementById('evm-gap-dim').addEventListener('change', (e) => changeGapDim(result, e.target.value));
}

function tile(label, value, note, cls, accent) {
  const a = accent ? ` style="border-left:3px solid var(--${accent})"` : '';
  const n = note ? `<div class="kpi-note">${escapeHtml(note)}</div>` : '';
  return `<div class="kpi-tile"${a}><div class="kpi-label">${escapeHtml(label)}</div>
    <div class="kpi-value ${cls || 'color-neutral'}">${escapeHtml(value)}</div>${n}</div>`;
}

function renderSlicer(result) {
  const cats = result.categories || {};
  const chips = ['Overall', ...Object.keys(cats)];
  if (!chips.includes(_slice)) _slice = 'Overall';
  const chipBox = document.getElementById('evm-slicer-chips');
  if (chipBox) {
    chipBox.innerHTML = chips.map(n =>
      `<button class="evm-chip${n === _slice ? ' on' : ''}" data-slice="${escapeHtml(n)}">${escapeHtml(n)}</button>`).join('');
    chipBox.querySelectorAll('.evm-chip').forEach(b =>
      b.addEventListener('click', () => { _slice = b.dataset.slice; renderSlicer(result); }));
  }

  let planned, actual, subP, subA, scope, scale;
  if (_slice === 'Overall' || !cats[_slice]) {
    const t = projectProgress(cats, _weights);          // matches Category Weights Overall row
    planned = t.planned; actual = t.actual;
    subP = 'Overall Planned Weight %'; subA = 'Overall Weighted Actual %'; scope = 'Overall project';
    scale = Math.max(planned, actual, 0.0001);
  } else {
    const c = cats[_slice];
    planned = c.planned_pct || 0; actual = c.actual_pct || 0;
    subP = `${_slice} Planned %`; subA = `${_slice} Actual %`; scope = _slice;
    scale = 1;
  }
  const v = actual - planned, behind = v < 0;
  const vTxt = `${behind ? '−' : '+'}${(Math.abs(v) * 100).toFixed(2)}%`;
  const pct = x => `${(x * 100).toFixed(2)}%`;
  const box = document.getElementById('evm-slicer');
  if (!box) return;
  box.innerHTML = `
    <div class="evm-slice-scope">Showing: <b>${escapeHtml(scope)}</b></div>
    <div class="evm-slice-ro">
      <div class="evm-ro plan"><div class="k">Planned %</div><div class="v">${pct(planned)}</div><div class="n">${escapeHtml(subP)}</div></div>
      <div class="evm-ro act"><div class="k">Actual %</div><div class="v">${pct(actual)}</div><div class="n">${escapeHtml(subA)}</div></div>
      <div class="evm-ro var"><div class="k">Variance</div><div class="v ${behind ? 'behind' : 'ahead'}">${vTxt}</div><div class="n">${behind ? 'behind plan' : 'ahead of plan'}</div></div>
    </div>
    <div class="evm-slice-bars">
      <div class="evm-dbar"><span class="dl">Planned</span><span class="dtrack"><span class="dfill s" style="width:${(planned / scale * 100).toFixed(1)}%"></span></span><span class="dv">${pct(planned)}</span></div>
      <div class="evm-dbar"><span class="dl">Actual</span><span class="dtrack"><span class="dfill a" style="width:${(actual / scale * 100).toFixed(1)}%"></span></span><span class="dv">${pct(actual)}</span></div>
    </div>`;
}

function renderDashboard(result) {
  const spi = result.spi, st = spiStatus(spi);
  const ac = _effectiveAC(result);
  const cpi = (ac && result.ev != null) ? result.ev / ac : result.cpi;
  const acNote = _actualCost != null ? 'entered' : 'from P6';
  document.getElementById('evm-dash').innerHTML = `<div class="evm-tiles">
    ${tile('SPI · Schedule', asPct(spi), st.label, st.cls, st.cls === 'color-red' ? 'danger' : (st.cls === 'color-amber' ? 'warning' : 'success'))}
    ${tile('Planned Value', egp(result.pv), 'EGP')}
    ${tile('Earned Value', egp(result.ev), 'EGP')}
    ${tile('Actual Cost', egp(ac), acNote, _actualCost != null ? 'color-blue' : '')}
    ${tile('CPI · Cost', asPct(cpi), 'auto from Actual Cost')}
    ${tile('Baseline Finish', fmtDate(result.baseline_finish))}
    ${tile('Expected Finish', fmtDate(result.expected_finish))}
    ${tile('Delay', result.delay_days != null ? `${result.delay_days} days` : '—',
           '', result.delay_days > 0 ? 'color-red' : 'color-green')}
  </div>`;
}

function renderBar(result) {
  const pv = result.pv || 0, ev = result.ev || 0, mx = Math.max(pv, ev, 1);
  const row = (label, v, color) =>
    `<div class="evm-barrow"><div class="evm-barlabel">${label}</div>
      <div class="evm-bartrack"><div class="evm-barfill" style="width:${(100 * v / mx).toFixed(1)}%;background:${color}"></div></div>
      <div class="evm-barval">${egp(v)}</div></div>`;
  document.getElementById('evm-bar').innerHTML =
    row('Planned Value (PV)', pv, '#3b6fa8') + row('Earned Value (EV)', ev, '#8bb648');
}

function renderCats(result) {
  const cats = result.categories || {};
  let rows = '', totPW = 0, totWA = 0;
  for (const [name, c] of Object.entries(cats)) {
    const w = _weights[name] != null ? _weights[name] : (c.weight || 0);
    const pw = w * (c.planned_pct || 0) * 100, wa = w * (c.actual_pct || 0) * 100;
    totPW += pw; totWA += wa;
    rows += `<tr><td>${escapeHtml(name)}</td><td class="num">${(w * 100).toFixed(1)}%</td>
      <td class="num">${((c.planned_pct || 0) * 100).toFixed(1)}%</td>
      <td class="num">${((c.actual_pct || 0) * 100).toFixed(1)}%</td>
      <td class="num">${pw.toFixed(2)}%</td><td class="num">${wa.toFixed(2)}%</td></tr>`;
  }
  document.getElementById('evm-cats').innerHTML = `<div class="tblwrap"><table class="evm-table">
    <thead><tr><th>WBS Category</th><th class="num">Weight %</th><th class="num">Planned %</th>
    <th class="num">Actual %</th><th class="num">Planned Wt %</th><th class="num">Weighted Act %</th></tr></thead>
    <tbody>${rows}<tr class="evm-tot"><td>Overall</td><td class="num">—</td><td class="num">—</td>
    <td class="num">—</td><td class="num">${totPW.toFixed(2)}%</td><td class="num">${totWA.toFixed(2)}%</td></tr></tbody></table></div>`;
}

function _applyE1ToCategories(result) {
  // E1 Approved % drives the Design/Engineering categories' Actual % (Ibrahim's rule).
  if (!_e1Extras || !_e1Extras.category_actuals || !result.categories) return;
  for (const [name, actual] of Object.entries(_e1Extras.category_actuals)) {
    if (result.categories[name]) result.categories[name].actual_pct = actual;
  }
}

function renderEngineering(result) {
  const e1 = result.engineering_e1, p6 = result.engineering_p6 || [];
  const src = document.getElementById('evm-eng-src');
  const box = document.getElementById('evm-eng');
  if (e1 && e1.length) {
    src.innerHTML = '<span class="src-chip on">Source: E1 Log</span>';
    box.innerHTML = engTable(e1, true) + engGaps(_e1Extras && _e1Extras.gaps);
  } else if (p6.length) {
    src.innerHTML = '<span class="src-chip p6">Source: P6 (Mode B)</span>';
    box.innerHTML = engTable(p6, false);
  } else {
    src.innerHTML = '';
    box.innerHTML = '<p class="evm-empty">No engineering activities in P6. Upload the E1 Log to populate this section.</p>';
  }
}

function engTable(rows, isE1) {
  const head = isE1
    ? ['Trade', 'Type', 'Req', 'Planned', 'Submitted', 'Approved', 'Not Appr', 'Sub %', 'Appr %']
    : ['Trade', 'Type', 'Req', 'Pl. Sub', 'Act. Sub', 'Pl. Appr', 'Act. Appr', 'Sub %', 'Appr %'];
  let body = rows.map(r => isE1
    ? `<tr><td>${escapeHtml(r.trade)}</td><td>${escapeHtml(r.submittal_type)}</td>
       <td class="num">${r.req}</td><td class="num">${r.planned}</td><td class="num">${r.submitted_rows}</td>
       <td class="num">${r.approved_rows}</td><td class="num">${r.not_approved_rows}</td>
       <td class="num">${r.submitted_pct}%</td><td class="num">${r.approved_pct}%</td></tr>`
    : `<tr><td>${escapeHtml(r.trade)}</td><td>${escapeHtml(r.submittal_type)}</td>
       <td class="num">${r.req}</td><td class="num">${r.planned_sub}</td><td class="num">${r.actual_sub}</td>
       <td class="num">${r.planned_appr}</td><td class="num">${r.actual_appr}</td>
       <td class="num">${r.actual_sub_pct}%</td><td class="num">${r.actual_appr_pct}%</td></tr>`).join('');
  if (isE1 && _e1Extras && _e1Extras.overall) {
    const o = _e1Extras.overall;
    const ovRow = (label, x, cls) => x ? `<tr class="${cls}"><td>${label}</td><td></td>
       <td class="num">${x.req}</td><td class="num">${x.planned}</td><td class="num">${x.submitted_rows}</td>
       <td class="num">${x.approved_rows}</td><td class="num">${x.not_approved_rows}</td>
       <td class="num">${x.submitted_pct}%</td><td class="num">${x.approved_pct}%</td></tr>` : '';
    body += ovRow('Overall — Design Drawings', o.design, 'evm-ov-d')
          + ovRow('Overall — Engineering (Shop)', o.engineering, 'evm-ov-e');
  }
  // Trade + Type are text (left-aligned); the rest are numeric (right-aligned) to match the data cells
  const thead = head.map((h, i) => `<th${i < 2 ? '' : ' class="num"'}>${h}</th>`).join('');
  return `<div class="tblwrap" style="overflow-x:auto"><table class="evm-table" style="min-width:640px">
    <thead><tr>${thead}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function engGaps(gaps) {
  if (!gaps) return '';
  const one = (title, groups) => (!groups || !groups.length) ? '' : `
    <div class="evm-sec" style="margin-top:16px">${title}</div>
    <div class="tblwrap" style="overflow-x:auto"><table class="evm-table" style="min-width:520px">
      <thead><tr><th>Trade</th><th class="num">Planned</th><th class="num">Approved</th>
        <th class="num">Gap</th><th class="num">% of Gap</th></tr></thead>
      <tbody>${groups.map(g => `<tr><td>${escapeHtml(g.trade)}</td>
        <td class="num">${g.planned}</td><td class="num">${g.approved}</td>
        <td class="num">${gapText(g.gap)}</td><td class="num">${Math.round(Math.abs(g.pct_of_gap))}%</td></tr>`).join('')}</tbody>
    </table></div>`;
  return one('Engineering Gap — Design Drawings (Planned vs Approved)', gaps.design)
       + one('Engineering Gap — Shop Drawings (Planned vs Approved)', gaps.engineering);
}

function renderGapDimOptions(result) {
  const dims = result.activity_code_types || [];
  const cur = (_gap && _gap.dimension) || (dims[0] || '');
  document.getElementById('evm-gap-dim').innerHTML =
    dims.map(d => `<option value="${escapeHtml(d)}"${d === cur ? ' selected' : ''}>${escapeHtml(d)}</option>`).join('');
}

function renderGap() {
  const box = document.getElementById('evm-gap');
  if (!_gap || !_gap.groups || !_gap.groups.length) {
    box.innerHTML = '<p class="evm-empty">No PV–EV gap on this update (Earned Value ≈ Planned Value), or activities are uncoded for this dimension.</p>';
    return;
  }
  const mx = Math.max(..._gap.groups.map(g => Math.abs(g.gap)), 1);
  const bars = _gap.groups.slice(0, 12).map(g =>
    `<div class="evm-barrow"><div class="evm-barlabel">${escapeHtml(g.code)}</div>
      <div class="evm-bartrack"><div class="evm-barfill" style="width:${(100 * Math.abs(g.gap) / mx).toFixed(1)}%;background:${g.gap < 0 ? '#5aa86f' : '#c0764a'}"></div></div>
      <div class="evm-barval">${gapText(g.gap, egp)} · ${Math.round(Math.abs(g.pct_of_gap))}%</div></div>`).join('');
  box.innerHTML = `<p class="evm-note">Total gap (PV − EV) = ${gapText(_gap.total_gap, egp)} EGP</p>${bars}`;
}

// ── interactions ──────────────────────────────────────────────────────────
function openInputsEditor(result) {
  const cats = Object.keys(result.categories || {});
  const wRows = cats.map(n =>
    `<label class="edit-row"><span>${escapeHtml(n)}</span>
      <input class="edit-w" data-cat="${escapeHtml(n)}" value="${((_weights[n] || 0) * 100).toFixed(2)}"> %</label>`).join('');
  const acVal = _actualCost != null ? _actualCost : (result.ac || 0);
  const html = `<div class="modal-back" id="evm-modal">
    <div class="modal">
      <div class="modal-title">Project Setup — weights &amp; Actual Cost</div>
      <div class="modal-body">
        <div class="edit-grp">Category Weights (%) <span style="font-weight:400;color:var(--muted);text-transform:none;letter-spacing:0">· auto-detected from the schedule</span></div>${wRows}
        <div class="edit-grp">Actual Cost (EGP)</div>
        <label class="edit-row"><span>Actual Cost</span><input class="edit-ac" id="evm-ac-input" value="${acVal}"></label>
        <div class="edit-hint">Categories are detected automatically (Construction / Engineering / Design / Procurement); every weight is editable, including Construction. Engineering drawings: Design types drive Design, everything else (Shop + other) drives Engineering. CPI recomputes from Actual Cost. Saved per project.</div>
      </div>
      <div class="modal-foot">
        <button class="btn-secondary" id="evm-modal-cancel">Cancel</button>
        <button class="btn-primary" id="evm-modal-apply">Apply</button>
      </div>
    </div></div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  const close = () => document.getElementById('evm-modal').remove();
  document.getElementById('evm-modal-cancel').addEventListener('click', close);
  document.getElementById('evm-modal-apply').addEventListener('click', () => {
    document.querySelectorAll('.edit-w').forEach(inp => {
      const v = parseFloat(inp.value);
      if (!isNaN(v)) _weights[inp.dataset.cat] = v / 100;
    });
    const acv = parseFloat(document.getElementById('evm-ac-input').value);
    _actualCost = isNaN(acv) ? null : acv;
    _saveInputs();
    close();
    renderSlicer(result);
    renderDashboard(result);
    renderCats(result);
  });
}

async function uploadE1(result) {
  try {
    const paths = await window.pywebview.api.choose_excel();
    if (!paths || !paths.length) return;
    const src = document.getElementById('evm-eng-src');
    src.innerHTML = `<span class="src-chip p6">Reading ${paths.length} log${paths.length > 1 ? 's' : ''}…</span>`;
    const resp = await fetch(`http://localhost:${state.serverPort}/api/e1/upload`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot_id: state.currentSnapshotId, paths,
                             category_names: Object.keys(result.categories || {}) }),
    });
    const data = await resp.json();
    if (data.ok) {
      result.engineering_e1 = data.engineering_e1;
      result.e1_extras = data.e1_extras || null;
      _e1Extras = result.e1_extras;
      _applyE1ToCategories(result);   // Design/Engineering category Actual % ← E1 Approved %
      renderEngineering(result);
      renderCats(result);             // category table reflects E1
      renderSlicer(result);           // top slicer + overall reflect E1
      renderDashboard(result);
    } else {
      src.innerHTML = `<span class="src-chip p6">E1 read failed</span>`;
      alert('E1 Log read failed: ' + (data.error || 'unknown'));
      renderEngineering(result);
    }
  } catch {
    renderEngineering(result);
  }
}

async function changeGapDim(result, dim) {
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/gap`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ xml_path: state.currentXmlPath, cached_path: state.currentCachedPath, dimension: dim }),
    });
    const data = await resp.json();
    if (data.ok) { _gap = data.gap; renderGap(); }
  } catch { /* ignore */ }
}

export function evmInputs() { return { weights: _weights, actualCost: _actualCost, gap: _gap }; }
