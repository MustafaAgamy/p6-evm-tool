// Update Analysis — a single-file read of the current schedule against its own baseline.
//
// Four sections: (1) Time Status donut + PV/EV/Variance; (2) Planned vs Actual by activity
// code — one chart per selected code; (3) Driving Path Analyzer — the governing milestone's
// driving path as work-front boxes (WBS rollup, or the activity itself when no cost); (4)
// Planned vs Actual by activity count (Completed / In Progress / Not Started), code-filtered.
// All numbers come from the server (metrics.compute), so they match the EVM tab.
import { state }      from './state.js';
import { showError }  from './render.js';
import { escapeHtml } from './format.js';

let _shownReport = null;
let _summaryLevel = 0;
let _scopePicked = [];          // Section 5 — cost-loaded activity codes to weigh (multi-select)
let _pickedTypes = [];          // Section 2 — the activity-code dimensions to chart (one chart each)
let _countFilter = { type: '', value: '' };   // Section 4 — activity-code filter

const C = { plan: '#e0912f', actual: '#2a78d6', good: '#16a34a', bad: '#dc2626', blue: '#2a78d6' };
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function _fileName() {
  const p = state.currentXmlPath || state.currentCachedPath || '';
  return p.split(/[\\/]/).pop() || 'current schedule';
}

function _fdate(iso) {
  if (!iso) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso));
  if (!m) return String(iso);
  return `${m[3]}-${MON[parseInt(m[2], 10) - 1]}.${m[1]}`;
}
function _num(n) { return (typeof n === 'number') ? n.toLocaleString('en-US', { maximumFractionDigits: 0 }) : '—'; }
function _pct(v) { return (typeof v === 'number') ? `${Math.round(v)}%` : '—'; }
const _pct2 = v => (typeof v === 'number') ? v.toFixed(2) + '%' : '—';
function _sv(v) { return v == null ? '—' : (v > 0 ? `+${v}` : `${v}`); }

function _defaultCodeType(types) {
  if (!types.length) return null;
  const tiers = [/disciplin/i, /type of work/i, /type of civil/i, /\btrade\b/i, /main wbs/i, /\bphase\b/i];
  for (const re of tiers) { const m = types.find(t => re.test(t)); if (m) return m; }
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
    .ua-note { color: var(--muted); font-style: italic; }
    .ua-mono { font-variant-numeric: tabular-nums; }
    .ua-bad { color: var(--danger); } .ua-good { color: var(--success); }
    /* Time status */
    .ua-ts { display: flex; gap: 24px; align-items: center; flex-wrap: wrap; }
    .ua-ts-sentence { font-size: 16px; line-height: 1.5; color: var(--text); }
    .ua-verd { margin-top: 12px; display: flex; flex-direction: column; gap: 7px; }
    .ua-vrow { display: flex; gap: 10px; font-size: 13px; color: var(--text); }
    .ua-vtag { flex: none; width: 118px; font-weight: 700; }
    .ua-cost { margin-top: 16px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .ua-costcard { border: 1px solid var(--border); border-radius: 10px; padding: 11px 14px; }
    .ua-cl { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .3px; }
    .ua-cv { font-size: 18px; font-weight: 700; margin-top: 3px; font-variant-numeric: tabular-nums; color: var(--text); }
    /* Slicer */
    .ua-slicer { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
    .ua-code-btn { border: 1px solid var(--border); background: var(--bg); color: var(--text); border-radius: 20px; padding: 5px 13px; font-size: 12.5px; cursor: pointer; }
    .ua-code-btn.on { background: var(--accent); color: #fff; border-color: var(--accent); }
    .ua-scope-btn { border: 1px solid var(--border); background: var(--bg); color: var(--text); border-radius: 20px; padding: 5px 13px; font-size: 12.5px; cursor: pointer; }
    .ua-scope-btn.on { background: var(--accent); color: #fff; border-color: var(--accent); }
    .ua-sel { padding: 5px 9px; border: 1px solid var(--border); border-radius: 8px; background: var(--card-bg); color: var(--text); }
    /* By code */
    .ua-chart2 { border: 1px solid var(--border); border-radius: 11px; padding: 14px 16px; margin-bottom: 14px; }
    .ua-chart2 h4 { margin: 0 0 12px; font-size: 13.5px; color: var(--accent); }
    .ua-bc-row { margin-bottom: 13px; }
    .ua-bc-name { font-size: 12.5px; font-weight: 600; margin-bottom: 4px; color: var(--text); }
    .ua-bc-track { height: 13px; background: var(--bg); border: 1px solid var(--border); border-radius: 3px; overflow: hidden; margin-bottom: 4px; }
    .ua-bc-fill { height: 100%; }
    .ua-bc-num { font-size: 12px; color: var(--muted); }
    .ua-leg { margin-top: 8px; font-size: 12px; color: var(--muted); }
    .ua-sw { display: inline-block; width: 13px; height: 13px; border-radius: 3px; vertical-align: -2px; margin: 0 6px 0 14px; }
    .ua-leg .ua-sw:first-child { margin-left: 0; }
    /* Driving path */
    .ua-dphead { background: rgba(42,120,214,.08); border: 1px solid var(--border); border-radius: 10px; padding: 12px 15px; font-size: 14px; line-height: 1.5; color: var(--text); margin-bottom: 14px; }
    .ua-chain { display: flex; align-items: stretch; flex-wrap: wrap; gap: 5px; }
    .ua-arw { display: flex; align-items: center; color: var(--muted); font-weight: 800; font-size: 17px; }
    .ua-msbox { flex: none; width: 200px; border: 2px solid var(--accent); border-radius: 12px; padding: 12px 13px; background: rgba(42,120,214,.08); }
    .ua-msbox.start { border-color: var(--success); background: rgba(22,163,74,.08); }
    .ua-msbox.start .ua-msflag, .ua-msbox.start .ua-mst { color: var(--success); }
    .ua-msflag { font-size: 10px; text-transform: uppercase; letter-spacing: .4px; color: var(--accent); opacity: .85; margin-bottom: 7px; }
    .ua-mst { font-size: 13px; font-weight: 800; color: var(--accent); line-height: 1.25; margin-bottom: 7px; }
    .ua-msr { display: flex; justify-content: space-between; font-size: 12px; margin: 3px 0; color: var(--text); }
    .ua-msr span { color: var(--muted); }
    .ua-box { flex: none; width: 196px; border: 1px solid var(--border); border-radius: 11px; padding: 10px 12px; background: var(--card-bg); }
    .ua-box.done { border-color: var(--success); }
    .ua-bt { font-size: 12.5px; font-weight: 700; line-height: 1.25; color: var(--text); }
    .ua-btag { font-size: 9px; color: #b45309; font-weight: 600; }
    .ua-bcrumb { font-size: 10px; color: var(--muted); margin: 3px 0 9px; }
    .ua-b4 { display: grid; grid-template-columns: 1fr 1fr; gap: 7px 9px; }
    .ua-k { font-size: 9.5px; color: var(--muted); text-transform: uppercase; letter-spacing: .3px; }
    .ua-v { font-size: 12.5px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--text); margin-top: 1px; }
    .ua-full { grid-column: 1 / -1; border-top: 1px dashed var(--border); padding-top: 5px; }
    /* Counts */
    .ua-cntt { font-size: 13px; margin-bottom: 12px; color: var(--text); }
    .ua-cnrow { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
    .ua-cnlbl { flex: none; width: 108px; font-size: 13px; font-weight: 600; color: var(--text); }
    .ua-cnbars { flex: 1; }
    .ua-cntrack { position: relative; height: 20px; background: var(--bg); border: 1px solid var(--border); border-radius: 4px; margin: 3px 0; overflow: hidden; }
    .ua-cntrack > i { display: block; height: 100%; }
    .ua-cntrack > span { position: absolute; left: 8px; top: 1px; font-size: 11.5px; font-weight: 700; color: var(--text); }
    .ua-empty { color: var(--muted); padding: 40px; text-align: center; }
    /* Scope */
    .ua-scope-h { font-size: 12.5px; color: var(--muted); margin-bottom: 12px; }
    .ua-wrow { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
    .ua-wname { flex: none; width: 220px; font-size: 12.5px; color: var(--text); }
    .ua-wtrack { flex: 1; height: 19px; background: var(--bg); border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
    .ua-wfill { height: 100%; background: rgba(42,120,214,.4); }
    .ua-wrow.top .ua-wfill { background: var(--accent); }
    .ua-wpct { flex: none; width: 52px; text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--text); }
    .ua-wcost { flex: none; width: 120px; text-align: right; font-variant-numeric: tabular-nums; color: var(--muted); font-size: 12px; }
    .ua-whead { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; font-size: 10px; text-transform: uppercase; letter-spacing: .3px; color: var(--muted); }
    .ua-wpa { flex: none; width: 150px; }
    .ua-wpa-t { height: 5px; background: var(--bg); border: 1px solid var(--border); border-radius: 3px; overflow: hidden; margin: 2px 0; }
    .ua-wpa-t > i { display: block; height: 100%; }
    .ua-wpanum { font-size: 10.5px; color: var(--muted); font-variant-numeric: tabular-nums; margin-top: 1px; }
    .ua-rec { margin-top: 16px; background: rgba(42,120,214,.08); border: 1px solid var(--border); border-radius: 11px; padding: 14px 16px; }
    .ua-rec h4 { margin: 0 0 8px; font-size: 11px; text-transform: uppercase; letter-spacing: .4px; color: var(--accent); }
    .ua-rec p { margin: 6px 0; font-size: 13.5px; color: var(--text); }
    .ua-rec .ua-star { color: var(--accent); font-weight: 800; margin-right: 6px; }
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
      body: JSON.stringify({ xml_path: state.currentXmlPath || '', cached_path: state.currentCachedPath || '', summary_level: _summaryLevel }),
    });
    const data = await resp.json();
    if (!data.ok) {
      if (data.code === 'no_baseline') {
        body.innerHTML = `<div class="ua-empty"><div style="font-size:15px;color:var(--text);margin-bottom:8px">This update has no baseline inside it.</div>
          <div>Attach a baseline on the EVM tab, then re-open Update Analysis.</div></div>`;
        return;
      }
      body.innerHTML = `<div class="ua-empty">${escapeHtml(data.error || 'Could not analyze this update.')}</div>`;
      return;
    }
    _shownReport = data.report;
    if (!_pickedTypes.length) _pickedTypes = [_defaultCodeType(data.report.code_types || [])].filter(Boolean);
    if (!_scopePicked.length) _scopePicked = [data.report.scope_default].filter(Boolean);
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
      <span class="cmp-file" style="margin-right:auto"><b>${escapeHtml(report.project_name || 'Project')}</b> · data date ${escapeHtml(_fdate(report.data_date))} · ${escapeHtml(_fileName())}</span>
      <button class="btn-secondary" id="ua-export-pdf">Export PDF</button>
      <button class="btn-secondary" id="ua-export-xlsx">Export Excel</button>
    </div>
    <div class="ua-reco">${escapeHtml(report.conclusion || '')}</div>

    <div class="ua-sec">1 · Time Status</div>
    <div class="ua-card">${_timeStatusHtml(report)}</div>

    <div class="ua-sec">2 · Planned vs Actual — by activity code</div>
    <div class="ua-card">${_byCodeControls(report)}<div id="ua-bc-charts">${_byCodeCharts(report)}</div></div>

    <div class="ua-sec">3 · Driving Path Analyzer</div>
    <div class="ua-card">${_drivingHtml(report)}</div>

    <div class="ua-sec">4 · Planned vs Actual — by activity count</div>
    <div class="ua-card">${_countControls(report)}<div id="ua-cn-body">${_countsHtml(report.counts)}</div></div>

    <div class="ua-sec">5 · Scope Weight &amp; Recommendation</div>
    <div class="ua-card">${_scopeControls(report)}<div id="ua-scope-body">${_scopeHtml(report)}</div></div>`;

  document.getElementById('ua-export-pdf').addEventListener('click', _exportPdf);
  document.getElementById('ua-export-xlsx').addEventListener('click', _exportExcel);
  _wireByCode(report);
  _wireSummaryLevel();
  _wireCounts(report);
  _wireScope(report);
}

// Section 5 — scope weight + recommendation (multi-select; one code renders instantly, several are combined server-side)
function _scopeControls(report) {
  const scope = report.scope || {};
  const types = Object.keys(scope);
  if (!types.length) return '';
  _scopePicked = _scopePicked.filter(t => scope[t]);
  if (!_scopePicked.length) _scopePicked = [scope[report.scope_default] ? report.scope_default : types[0]];
  const chips = types.map(t => `<button class="ua-scope-btn ${_scopePicked.includes(t) ? 'on' : ''}" data-scope="${escapeHtml(t)}">${escapeHtml(t)}</button>`).join('');
  return `<div class="ua-slicer"><span style="color:var(--muted)">Weight by</span>${chips}
    <span style="margin-left:auto;color:var(--muted);font-size:12px">pick one or more · recommendation updates with the codes</span></div>`;
}
function _scopeRender(s) {
  if (!s) return `<div class="ua-note">No cost-loaded activity codes to weigh.</div>`;
  const rows = s.rows || [];
  const mx = Math.max(...rows.map(r => r.weight_pct), 1) || 1;
  const head = `<div class="ua-whead">
    <span style="flex:none;width:220px">Scope</span>
    <span style="flex:1">Weight</span>
    <span style="flex:none;width:52px;text-align:right">%</span>
    <span style="flex:none;width:120px;text-align:right">Budget</span>
    <span style="flex:none;width:150px">Planned vs Actual</span></div>`;
  const bars = rows.slice(0, 12).map((r, i) => {
    const g = +((r.planned || 0) - (r.actual || 0)).toFixed(1);
    const behindHtml = g > 0 ? ` · <span class="ua-bad">−${g}</span>` : '';
    return `<div class="ua-wrow ${i === 0 ? 'top' : ''}">
    <div class="ua-wname">${escapeHtml(r.value)}</div>
    <div class="ua-wtrack"><div class="ua-wfill" style="width:${r.weight_pct / mx * 100}%"></div></div>
    <div class="ua-wpct">${r.weight_pct.toFixed(1)}%</div>
    <div class="ua-wcost">${_num(r.bac)}</div>
    <div class="ua-wpa">
      <div class="ua-wpa-t"><i style="width:${Math.max(0, Math.min(100, r.planned || 0))}%;background:${C.plan}"></i></div>
      <div class="ua-wpa-t"><i style="width:${Math.max(0, Math.min(100, r.actual || 0))}%;background:${C.actual}"></i></div>
      <div class="ua-wpanum">P ${(r.planned || 0).toFixed(1)}% · A ${(r.actual || 0).toFixed(1)}%${behindHtml}</div>
    </div></div>`;
  }).join('');
  const leg = `<div class="ua-leg"><span class="ua-sw" style="background:rgba(42,120,214,.4)"></span>Weight<span class="ua-sw" style="background:${C.plan}"></span>Planned<span class="ua-sw" style="background:${C.actual}"></span>Actual</div>`;
  const recs = (s.recommendation || []).map(t => `<p><span class="ua-star">★</span>${escapeHtml(t)}</p>`).join('');
  const rec = recs ? `<div class="ua-rec"><h4>◆ Recommendation — by weight</h4>${recs}</div>` : '';
  return `<div class="ua-scope-h">Weighting by <b>${escapeHtml(s.code_type || '')}</b> · share of the cost-loaded scope</div>${head}${bars}${leg}${rec}`;
}
function _scopeHtml(report) {
  const scope = report.scope || {};
  if (_scopePicked.length === 1) return _scopeRender(scope[_scopePicked[0]]);
  if (!_scopePicked.length) return `<div class="ua-note">No cost-loaded activity codes to weigh.</div>`;
  return `<div class="ua-note">Weighting…</div>`;
}
function _wireScope(report) {
  const box = document.getElementById('ua-scope-body');
  if (!box) return;
  const scope = report.scope || {};
  const paint = () => document.querySelectorAll('.ua-scope-btn[data-scope]').forEach(b => b.classList.toggle('on', _scopePicked.includes(b.dataset.scope)));
  const refresh = async () => {
    if (_scopePicked.length <= 1) { box.innerHTML = _scopeRender(scope[_scopePicked[0]]); return; }
    box.innerHTML = `<div class="ua-note">Weighting…</div>`;
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/update/scope`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ xml_path: state.currentXmlPath || '', cached_path: state.currentCachedPath || '', types: _scopePicked }),
      });
      const data = await resp.json();
      if (data.ok) box.innerHTML = _scopeRender(data.scope);
      else box.innerHTML = `<div class="ua-note">Could not combine those codes.</div>`;
    } catch { box.innerHTML = `<div class="ua-note">Could not reach the server.</div>`; }
  };
  document.querySelectorAll('.ua-scope-btn[data-scope]').forEach(btn => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.scope, i = _scopePicked.indexOf(t);
      if (i >= 0) { if (_scopePicked.length > 1) _scopePicked.splice(i, 1); } else _scopePicked.push(t);
      paint();
      refresh();
    });
  });
  if (_scopePicked.length > 1) refresh();
}

// Section 1
function _donut(elapsed, planned, actual) {
  const arc = (r, pct) => { const c = 2 * Math.PI * r; const on = c * Math.max(0, Math.min(100, pct || 0)) / 100; return `${on.toFixed(1)} ${(c - on).toFixed(1)}`; };
  return `<svg width="140" height="140" viewBox="0 0 150 150">
    <circle cx="75" cy="75" r="58" fill="none" stroke="var(--border)" stroke-width="18"/>
    <circle cx="75" cy="75" r="58" fill="none" stroke="${C.blue}" stroke-width="18" stroke-dasharray="${arc(58, elapsed)}" transform="rotate(-90 75 75)"/>
    <circle cx="75" cy="75" r="40" fill="none" stroke="var(--border)" stroke-width="10"/>
    <circle cx="75" cy="75" r="40" fill="none" stroke="${C.good}" stroke-width="10" stroke-dasharray="${arc(40, actual)}" transform="rotate(-90 75 75)"/>
    <text x="75" y="70" text-anchor="middle" font-size="17" font-weight="700" fill="var(--text)">${_pct2(actual)}</text>
    <text x="75" y="88" text-anchor="middle" font-size="10" fill="var(--muted)">earned</text>
  </svg>`;
}

function _timeStatusHtml(report) {
  const ts = report.time_status || {};
  const ep = ts.elapsed_pct, pp = ts.planned_pct, ap = ts.actual_pct;
  let elapsed = ep != null ? `${ep.toFixed(1)}%` : '—';
  if (ts.exceeded_days) elapsed = `100% — baseline exceeded by ${ts.exceeded_days} days`;
  let verd = '';
  if (ts.behind_plan != null && pp != null && ap != null) {
    const v = ts.behind_plan, cls = v > 0 ? 'ua-bad' : 'ua-good';
    verd += `<div class="ua-vrow"><span class="ua-vtag ${cls}">Behind plan · ${Math.abs(v)}</span><span>You planned to have earned <b>${_pct2(pp)}</b> by the data date; you’ve earned <b>${_pct2(ap)}</b> — ${Math.abs(v)} points ${v > 0 ? 'short of' : 'ahead of'} the plan.</span></div>`;
  }
  if (ts.behind_clock != null && ep != null && ap != null) {
    const v = ts.behind_clock, cls = v > 0 ? 'ua-bad' : 'ua-good';
    verd += `<div class="ua-vrow"><span class="ua-vtag ${cls}">Behind clock · ${Math.abs(v)}</span><span><b>${ep.toFixed(1)}%</b> of the baseline calendar is used up, but only <b>${_pct2(ap)}</b> of the work is done — ${Math.abs(v)} points ${v > 0 ? 'less' : 'more'} work than time spent.</span></div>`;
  }
  const cv = ts.cost_variance;
  return `<div class="ua-ts"><div>${_donut(ep, pp, ap)}</div>
    <div style="flex:1;min-width:300px">
      <div class="ua-ts-sentence"><b>${escapeHtml(elapsed)}</b> of the baseline time has elapsed, but only <b>${_pct2(ap)}</b> of the work is earned (planned to be at <b>${_pct2(pp)}</b> by now).</div>
      <div class="ua-verd">${verd}</div>
    </div></div>
    <div class="ua-cost">
      <div class="ua-costcard"><div class="ua-cl">Planned Value (PV)</div><div class="ua-cv">${_num(ts.pv)}</div></div>
      <div class="ua-costcard"><div class="ua-cl">Earned Value (EV)</div><div class="ua-cv">${_num(ts.ev)}</div></div>
      <div class="ua-costcard"><div class="ua-cl">Variance = EV − PV</div><div class="ua-cv ${cv < 0 ? 'ua-bad' : ''}">${_num(cv)}</div></div>
    </div>`;
}

// Section 2 — one chart per selected code
function _byCodeControls(report) {
  const types = report.code_types || [];
  if (!types.length) return '';
  const chips = types.map(t => `<button class="ua-code-btn ${_pickedTypes.includes(t) ? 'on' : ''}" data-type="${escapeHtml(t)}">${escapeHtml(t)}</button>`).join('');
  return `<div class="ua-slicer"><span style="color:var(--muted)">Activity code</span>${chips}
    <span style="margin-left:auto;color:var(--muted);font-size:12px">pick one or more — each gets its own chart</span></div>`;
}
function _oneChart(title, rows) {
  if (!rows || !rows.length) return `<div class="ua-chart2"><h4>${escapeHtml(title)}</h4><div class="ua-note">No values for this code.</div></div>`;
  const bars = rows.map(r => {
    const v = r.variance, col = v < 0 ? C.bad : C.good, sv = v > 0 ? `+${v}` : `${v}`;
    return `<div class="ua-bc-row"><div class="ua-bc-name">${escapeHtml(r.value)}</div>
      <div class="ua-bc-track"><div class="ua-bc-fill" style="width:${Math.max(0, Math.min(100, r.planned))}%;background:${C.plan}"></div></div>
      <div class="ua-bc-track"><div class="ua-bc-fill" style="width:${Math.max(0, Math.min(100, r.actual))}%;background:${C.actual}"></div></div>
      <div class="ua-bc-num">planned ${r.planned.toFixed(1)}% · actual ${r.actual.toFixed(1)}% · <b style="color:${col}">${sv}</b></div></div>`;
  }).join('');
  const leg = `<div class="ua-leg"><span class="ua-sw" style="background:${C.plan}"></span>Planned %<span class="ua-sw" style="background:${C.actual}"></span>Actual %</div>`;
  return `<div class="ua-chart2"><h4>${escapeHtml(title)}</h4>${bars}${leg}</div>`;
}
function _byCodeCharts(report) {
  const by = report.by_code || {};
  if (!_pickedTypes.length) return `<div class="ua-note">Pick an activity code above.</div>`;
  return _pickedTypes.map(t => _oneChart(t, by[t] || [])).join('');
}
function _wireByCode(report) {
  const box = document.getElementById('ua-bc-charts');
  document.querySelectorAll('.ua-code-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.type, i = _pickedTypes.indexOf(t);
      if (i >= 0) { if (_pickedTypes.length > 1) _pickedTypes.splice(i, 1); } else _pickedTypes.push(t);
      document.querySelectorAll('.ua-code-btn').forEach(b => b.classList.toggle('on', _pickedTypes.includes(b.dataset.type)));
      box.innerHTML = _byCodeCharts(report);
    });
  });
}

// Section 3 — driving path
function _drivingHtml(report) {
  const cp = report.critical_path || {};
  const levelSel = `<div class="ua-slicer"><span style="color:var(--muted)">Summarise at</span>
    <select id="ua-cp-level" class="ua-sel">
      <option value="0"${_summaryLevel === 0 ? ' selected' : ''}>Work front</option>
      <option value="1"${_summaryLevel === 1 ? ' selected' : ''}>Area / zone</option>
      <option value="2"${_summaryLevel === 2 ? ' selected' : ''}>Phase</option>
    </select><span style="margin-left:auto;color:var(--muted);font-size:12px">construction / execution work only</span></div>`;
  if (!cp.charts || !cp.charts.length) return levelSel + `<div class="ua-note">No governing completion milestone with a driving path was found.</div>`;
  const parts = [levelSel];
  if (cp.headline) parts.push(`<div class="ua-dphead">${escapeHtml(cp.headline)}</div>`);
  cp.charts.forEach(chart => {
    const ms = chart.milestone || {};
    const sm = chart.start_milestone || null;
    const chain = [];
    if (sm && sm.name) {
      chain.push(`<div class="ua-msbox start"><div class="ua-msflag">▶ Start Milestone</div><div class="ua-mst">${escapeHtml(sm.name)}</div>
        <div class="ua-msr"><span>Date</span><b class="ua-mono">${escapeHtml(_fdate(sm.date))}</b></div></div>`);
      chain.push(`<div class="ua-arw">▸</div>`);
    }
    (chart.boxes || []).forEach(b => {
      const tag = b.source === 'activity' ? ` <span class="ua-btag">activity — no cost in WBS</span>` : '';
      chain.push(`<div class="ua-box ${b.complete ? 'done' : ''}">
        <div class="ua-bt">${escapeHtml(b.name || '')}${tag}</div>
        <div class="ua-bcrumb">${escapeHtml(b.crumb || '')}</div>
        <div class="ua-b4">
          <div><div class="ua-k">Planned</div><div class="ua-v">${(b.planned || 0).toFixed(1)}%</div></div>
          <div><div class="ua-k">Actual</div><div class="ua-v">${(b.pct || 0).toFixed(1)}%</div></div>
          <div><div class="ua-k">Baseline Finish</div><div class="ua-v ua-mono">${escapeHtml(_fdate(b.bl_finish))}</div></div>
          <div><div class="ua-k">Expected Finish</div><div class="ua-v ua-mono">${escapeHtml(_fdate(b.exp_finish))}</div></div>
          <div class="ua-full"><div class="ua-k">Delay</div><div class="ua-v ${(b.slip_days || 0) > 0 ? 'ua-bad' : ''}">${_sv(b.slip_days)} d</div></div>
        </div></div>`);
      chain.push(`<div class="ua-arw">▸</div>`);
    });
    chain.push(`<div class="ua-msbox"><div class="ua-msflag">◆ Completion Milestone</div><div class="ua-mst">${escapeHtml(ms.name || '')}</div>
      <div class="ua-msr"><span>Baseline Finish</span><b class="ua-mono">${escapeHtml(_fdate(ms.baseline_finish))}</b></div>
      <div class="ua-msr"><span>Expected Finish</span><b class="ua-mono">${escapeHtml(_fdate(ms.expected_finish))}</b></div>
      <div class="ua-msr"><span>Delay</span><b class="ua-bad">${_sv(ms.slip_days)} d</b></div></div>`);
    parts.push(`<div class="ua-chain">${chain.join('')}</div>`);
  });
  return parts.join('');
}
function _wireSummaryLevel() {
  const sel = document.getElementById('ua-cp-level');
  if (sel) sel.addEventListener('change', () => { _summaryLevel = parseInt(sel.value, 10) || 0; _runAnalyze(); });
}

// Section 4 — counts
function _countControls(report) {
  const types = report.code_types || [];
  const opts = ['<option value="">— all construction activities —</option>'].concat(types.map(t => `<option${_countFilter.type === t ? ' selected' : ''}>${escapeHtml(t)}</option>`)).join('');
  return `<div class="ua-slicer"><span style="color:var(--muted)">Filter by activity code</span>
    <select id="ua-cn-type" class="ua-sel">${opts}</select>
    <select id="ua-cn-val" class="ua-sel" ${_countFilter.type ? '' : 'disabled'}></select>
    <span style="margin-left:auto;color:var(--muted);font-size:12px">construction / execution activities only</span></div>`;
}
function _countsHtml(c) {
  if (!c || !c.total) return `<div class="ua-note">No construction/execution activities to count.</div>`;
  const mx = Math.max(c.total, 1);
  const row = (lbl, pn, an) => `<div class="ua-cnrow"><div class="ua-cnlbl">${lbl}</div><div class="ua-cnbars">
    <div class="ua-cntrack"><i style="width:${pn / mx * 100}%;background:${C.plan};opacity:.85"></i><span>Planned ${pn}</span></div>
    <div class="ua-cntrack"><i style="width:${an / mx * 100}%;background:${C.actual};opacity:.85"></i><span>Actual ${an}</span></div></div></div>`;
  const total = `<div class="ua-cntt">Activities: <b>${c.total}</b> (baseline dates on <b>${c.planned_total}</b>)</div>`;
  const leg = `<div class="ua-leg"><span class="ua-sw" style="background:${C.plan}"></span>Planned (count)<span class="ua-sw" style="background:${C.actual}"></span>Actual (count)</div>`;
  return total +
    row('Completed', c.planned_completed, c.actual_completed) +
    row('In Progress', c.planned_in_progress, c.actual_in_progress) +
    row('Not Started', c.planned_not_started, c.actual_not_started) + leg;
}
function _wireCounts(report) {
  const typeSel = document.getElementById('ua-cn-type');
  const valSel = document.getElementById('ua-cn-val');
  const box = document.getElementById('ua-cn-body');
  if (!typeSel) return;
  const fillVals = () => {
    const t = typeSel.value;
    if (!t) { valSel.innerHTML = ''; valSel.disabled = true; return; }
    const vals = (report.by_code[t] || []).map(r => r.value);
    valSel.disabled = !vals.length;
    valSel.innerHTML = vals.map(v => `<option${_countFilter.value === v ? ' selected' : ''}>${escapeHtml(v)}</option>`).join('');
  };
  const refresh = async () => {
    const cf = typeSel.value && valSel.value ? { type: typeSel.value, value: valSel.value } : null;
    _countFilter = cf || { type: typeSel.value, value: '' };
    box.innerHTML = `<div class="ua-note">Counting…</div>`;
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/update/counts`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ xml_path: state.currentXmlPath || '', cached_path: state.currentCachedPath || '', code_filter: cf }),
      });
      const data = await resp.json();
      if (data.ok) { report.counts = data.counts; if (_shownReport) _shownReport.counts = data.counts; box.innerHTML = _countsHtml(data.counts); }
      else box.innerHTML = `<div class="ua-note">Could not apply that filter.</div>`;
    } catch { box.innerHTML = `<div class="ua-note">Could not reach the server.</div>`; }
  };
  fillVals();
  typeSel.addEventListener('change', () => { fillVals(); if (!typeSel.value) refresh(); });
  valSel.addEventListener('change', refresh);
}

// ── Exports ──────────────────────────────────────────────────────────────────

const UA_SECTIONS = [
  ['conclusion', 'Executive read'], ['time', 'Time Status'], ['bycode', 'Planned vs Actual by code'],
  ['driving', 'Driving Path Analyzer'], ['counts', 'Planned vs Actual by count'], ['scope', 'Scope Weight & Recommendation'],
];

function _codeFilter() { return _pickedTypes.length ? { types: _pickedTypes.slice() } : null; }

async function _exportPdf() {
  if (!_shownReport) { showError('Analyze the update first, then export.'); return; }
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/update/report`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report: _shownReport, preview: true, code_filter: _codeFilter(), scope_code: _scopePicked[0] || '' }),
    });
    const data = await resp.json();
    if (!data.ok) { showError(`Preview failed: ${data.error || 'unknown error'}`); return; }
    _showPdfPreview(data.html);
  } catch { showError('Could not reach the local server for the preview.'); }
}

function _showPdfPreview(reportHtml) {
  const ex = document.getElementById('per-preview-overlay'); if (ex) ex.remove();
  const ov = document.createElement('div');
  ov.id = 'per-preview-overlay'; ov.className = 'per-preview-overlay';
  const picks = UA_SECTIONS.map(([k, l]) => `<label class="per-pick"><input type="checkbox" class="ua-sec-cb" value="${k}" checked> ${escapeHtml(l)}</label>`).join('');
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
      </div></div>`;
  document.body.appendChild(ov);
  const frame = document.getElementById('ua-preview-frame');
  const close = () => ov.remove();
  ov.addEventListener('click', e => { if (e.target === ov) close(); });
  document.getElementById('ua-preview-close').addEventListener('click', close);
  const cbs = () => Array.from(ov.querySelectorAll('.ua-sec-cb'));
  const selected = () => cbs().filter(c => c.checked).map(c => c.value);
  const apply = () => { const doc = frame.contentDocument; if (!doc) return; const on = new Set(selected()); doc.querySelectorAll('[data-sec]').forEach(el => { el.style.display = on.has(el.getAttribute('data-sec')) ? '' : 'none'; }); };
  frame.onload = apply; frame.srcdoc = reportHtml;
  cbs().forEach(c => c.addEventListener('change', apply));
  document.getElementById('ua-pick-all').addEventListener('click', () => { cbs().forEach(c => { c.checked = true; }); apply(); });
  document.getElementById('ua-pick-none').addEventListener('click', () => { cbs().forEach(c => { c.checked = false; }); apply(); });
  document.getElementById('ua-preview-print').addEventListener('click', () => { apply(); try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch { showError('Could not open the print dialog.'); } });
  document.getElementById('ua-preview-save').addEventListener('click', async () => {
    const outputPath = await window.pywebview.api.choose_save_path('update_analysis.pdf', 'pdf');
    if (!outputPath) return;
    const btn = document.getElementById('ua-preview-save'); if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/update/report`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report: _shownReport, output_path: outputPath, sections: selected(), code_filter: _codeFilter(), scope_code: _scopePicked[0] || '' }),
      });
      const data = await resp.json();
      if (!data.ok) showError(`PDF export failed: ${data.error || 'unknown error'}`); else close();
    } catch { showError('Could not reach the local server to export the PDF.'); }
    finally { if (btn) { btn.disabled = false; btn.textContent = 'Save as PDF'; } }
  });
}

async function _exportExcel() {
  if (!_shownReport) { showError('Analyze the update first, then export.'); return; }
  const outputPath = await window.pywebview.api.choose_save_path('update_analysis.xlsx', 'xlsx');
  if (!outputPath) return;
  const btn = document.getElementById('ua-export-xlsx'); if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
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
