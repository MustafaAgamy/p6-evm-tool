// Update Analysis — the current schedule read against its baseline: the one inside the file, else
// the baseline attached for this update (here or on Earned Value; XER or XML — baseline.js).
//
// Six sections: (1) Time Status — verdict, six key numbers, donut + ruler, PV/EV/Variance
// (approved 2026-11-23); (2) Planned vs Actual by activity
// code — one chart per selected code; (3) Driving Path Analyzer — the governing milestone's
// driving path as work-front boxes (WBS rollup, or the activity itself when no cost); (4)
// Planned vs Actual by activity count (Completed / In Progress / Not Started), code-filtered;
// (5) Scope Weight; (6) Progress S-curve — Planned / Earned / Forecast, earlier updates on it.
// All numbers come from the server (metrics.compute), so they match the EVM tab.
import { state }      from './state.js';
import { showError }  from './render.js';
import { escapeHtml } from './format.js';
import { revealStage } from './featurereveal.js';
import { getSavedMode } from './appearance.js';
import { showReportPreview } from './preview.js';
import { UPDATE_NO_BASELINE_ADVICE } from './feature_needs.js';   // the same advice Help ▸ Feature guide gives
import { ATTACH_BASELINE_LABEL, attachBaselineFile, attachProblem, expectedBaselineAdvice } from './baseline.js';

let _shownReport = null;
// A new schedule was imported / opened: forget the files picked and the report shown for the last one.
if (typeof document !== 'undefined' && document.addEventListener) {
  document.addEventListener('controlyx:new-schedule', () => { _shownReport = null; _scopePicked = []; _pickedTypes = []; _countFilter = { type: '', value: '' }; });
}
let _summaryLevel = 0;
let _scopePicked = [];          // Section 5 — cost-loaded activity codes to weigh (multi-select)
let _pickedTypes = [];          // Section 2 — the activity-code dimensions to chart (one chart each)
let _countFilter = { type: '', value: '' };   // Section 4 — activity-code filter
let _uaTheme = getSavedMode();  // report-appearance mode for this panel's PDF preview

const C = { plan: 'var(--chart-3)', actual: 'var(--chart-1)', good: 'var(--success)', bad: 'var(--danger)', blue: 'var(--chart-1)' };
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
    .ua-pk { position: relative; display: inline-block; }
    .ua-pkbtn { border: 1px solid var(--accent); background: var(--bg); color: var(--accent); border-radius: 20px; padding: 6px 14px; font-weight: 700; cursor: pointer; font-size: 12.5px; }
    .ua-pkbtn b { color: var(--text); }
    .ua-pkpop { position: absolute; z-index: 30; top: 38px; left: 0; width: 540px; max-width: 86vw; max-height: 380px; overflow: auto; background: var(--card-bg, var(--bg)); border: 1px solid var(--border); border-radius: 10px; box-shadow: 0 8px 28px rgba(0,0,0,.18); padding: 10px; display: none; }
    .ua-pkpop.open { display: block; }
    .ua-pksearch { width: 100%; box-sizing: border-box; padding: 7px 9px; border: 1px solid var(--border); border-radius: 6px; margin-bottom: 8px; background: var(--bg); color: var(--text); }
    .ua-pkgrp { margin: 6px 0 10px; } .ua-pkgh { font-size: 11.5px; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; margin-bottom: 5px; }
    .ua-pkpop button { margin: 0 5px 6px 0; } .ua-pkpop button i { font-style: normal; opacity: .65; font-size: 11px; margin-left: 5px; }
    .ua-code-btn i { font-style: normal; opacity: .65; font-size: 11px; margin-left: 5px; }
    .ua-rename-wrap { display: inline-flex; align-items: center; gap: 6px; }
    .ua-title { font-weight: 800; font-size: 15px; padding: 3px 6px; border-radius: 5px; border-bottom: 2px dashed transparent; outline: none; }
    .ua-title:hover { border-bottom-color: var(--border); } .ua-title:focus { background: var(--bg); border-bottom-color: var(--accent); }
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
    .ua-btag { font-size: 9px; color: var(--warning); font-weight: 600; }
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
    .ua-cnt { width: 100%; border-collapse: collapse; font-size: 12.5px; margin-top: 6px; }
    .ua-cnt th { text-align: left; font-size: 11px; color: var(--muted); font-weight: 700; text-transform: uppercase; letter-spacing: .3px; padding: 6px 8px; border-bottom: 2px solid var(--border); }
    .ua-cnt td { padding: 7px 8px; border-bottom: 1px solid var(--border); vertical-align: middle; }
    .ua-cnt .ua-n { text-align: right; white-space: nowrap; }
    .ua-cnt tr.ua-tot td { font-weight: 800; border-top: 2px solid var(--border); }
    .ua-of { color: var(--muted); font-size: 11.5px; font-weight: 400; }
    .ua-gap { font-weight: 800; } .ua-good { color: var(--success, #15803d); }
    .ua-cbar { position: relative; height: 12px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; min-width: 140px; }
    .ua-cbar > i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 6px; }
    .ua-cbar > u { position: absolute; top: -3px; bottom: -3px; width: 3px; border-radius: 2px; background: var(--text); }
    .ua-cnwbs { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 6px 0 8px; }
    .ua-cnhow { font-size: 12px; color: var(--muted); margin-bottom: 4px; }
    .ua-strip { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin: 8px 0 10px; }
    .ua-k5 { background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 8px 11px; }
    .ua-k5 .t { font-size: 10.5px; color: var(--muted); text-transform: uppercase; font-weight: 700; } .ua-k5 .v { font-size: 18px; font-weight: 800; }
    .ua-rec2 { margin-top: 10px; padding: 10px 12px; border-radius: 9px; background: color-mix(in srgb, var(--warning) 14%, transparent); border-left: 4px solid var(--warning); font-size: 12.5px; }
    .ua-rec2 p { margin: 4px 0 0; }
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
    /* Section 1 summary band (approved 2026-11-23) */
    .ua-verdict { display: flex; gap: 14px; align-items: flex-start; border: 1px solid var(--border); border-left: 6px solid var(--danger); border-radius: 0 12px 12px 0; padding: 12px 16px; margin-bottom: 12px; background: var(--card-bg); }
    .ua-verdict.on_track { border-left-color: var(--success); } .ua-verdict.baseline { border-left-color: var(--accent); }
    .ua-pill { flex: none; background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); font-weight: 800; border-radius: 20px; padding: 3px 12px; font-size: 12px; margin-top: 2px; letter-spacing: .02em; }
    .ua-verdict.on_track .ua-pill { background: color-mix(in srgb, var(--success) 14%, transparent); color: var(--success); }
    .ua-verdict.baseline .ua-pill { background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--accent); }
    .ua-vh { font-size: 15.5px; font-weight: 700; color: var(--text); } .ua-vd { color: var(--muted); font-size: 13px; margin-top: 3px; }
    .ua-kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 12px; }
    .ua-kpi { border: 1px solid var(--border); border-top: 4px solid var(--muted); border-radius: 12px; padding: 10px 12px; background: var(--card-bg); }
    .ua-kpi.bad { border-top-color: var(--danger); } .ua-kpi.good { border-top-color: var(--success); }
    .ua-kpi .l { font-size: 10.5px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; font-weight: 700; }
    .ua-kpi .v { font-size: 21px; font-weight: 800; font-variant-numeric: tabular-nums; color: var(--text); margin-top: 2px; }
    .ua-kpi.bad .v { color: var(--danger); } .ua-kpi.good .v { color: var(--success); }
    .ua-kpi.date .v { font-size: 17px; padding-top: 4px; }
    .ua-kpi .s { font-size: 11.5px; color: var(--muted); }
    .ua-prog h4 { margin: 0 0 6px; font-size: 13px; color: var(--text); }
    .ua-progrow { display: flex; gap: 22px; align-items: center; }
    .ua-progrow .ua-rul { flex: 1; min-width: 240px; }
    .ua-donleg { font-size: 11px; color: var(--muted); text-align: center; margin-top: 2px; }
    .ua-ruler { position: relative; height: 30px; background: var(--bg); border: 1px solid var(--border); border-radius: 7px; margin: 46px 0 40px; }
    .ua-ruler .f { position: absolute; left: 0; top: 0; bottom: 0; background: var(--chart-1); border-radius: 7px 0 0 7px; }
    .ua-mk { position: absolute; top: -8px; bottom: -8px; width: 3px; border-radius: 2px; transform: translateX(-1px); }
    .ua-mk span { position: absolute; left: 50%; transform: translateX(-50%); white-space: nowrap; font-size: 11.5px; font-weight: 700; }
    .ua-mk.up span { top: -20px; } .ua-mk.up2 span { top: -36px; } .ua-mk.dn span { bottom: -21px; }
    .ua-gapnote { font-size: 12.5px; color: var(--text); margin-top: 4px; }
    @media (max-width: 1100px) { .ua-kpis { grid-template-columns: repeat(3, 1fr); } }
    /* Section 6 S-curve */
    .ua-earl { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; font-size: 12.5px; margin-bottom: 8px; color: var(--text); }
    .ua-chip { border: 1px solid var(--chart-1); color: var(--chart-1); border-radius: 16px; padding: 2px 4px 2px 10px; font-weight: 700; background: var(--card-bg); }
    .ua-chip button { border: 0; background: none; color: var(--muted); cursor: pointer; font-size: 13px; padding: 0 4px; }
    .ua-sc svg text { font-family: inherit; }
    .ua-sct td.dd { font-weight: 800; background: color-mix(in srgb, var(--accent) 8%, transparent); }
    .ua-sct summary, .ua-scnote summary { cursor: pointer; color: var(--accent); font-weight: 600; font-size: 12.5px; margin-top: 10px; }
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
  return _runAnalyze();
}

async function _runAnalyze() {
  const body = document.getElementById('update-body');
  // The import already recorded whether this file carries its own baseline (the very test the
  // server makes, has_embedded_baseline). When it does not, answer at once — no whole-file
  // re-read under the Run bar just to say so. Unknown (older snapshot) → ask the server.
  if (state.currentResult && state.currentResult.has_embedded_baseline === false) {
    _showAnalysis(body, { ok: false, code: 'no_baseline' });
    return;
  }
  revealStage('Reading this update against its baseline');   // the open Run bar names the real step
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/update/analyze`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ xml_path: state.currentXmlPath || '', cached_path: state.currentCachedPath || '', summary_level: _summaryLevel, snapshot_id: state.currentSnapshotId || null }),
    });
    _showAnalysis(body, await resp.json());
  } catch {
    if (body) body.innerHTML = `<div class="ua-empty">Could not reach the local server. Try re-importing the schedule.</div>`;
  }
}

// Paints one /api/update/analyze answer (or the instant no-baseline answer above) into the body.
function _showAnalysis(body, data) {
  if (!data.ok) {
    if (data.code === 'no_baseline') {
      _noBaseline(body, data.baseline_missing, '', data.baseline_expected_name);
      return;
    }
    body.innerHTML = `<div class="ua-empty">${escapeHtml(data.error || 'Could not analyze this update.')}</div>`;
    return;
  }
  _shownReport = data.report;
  if (!_pickedTypes.length) _pickedTypes = [_defaultCodeType(data.report.code_types || [])].filter(Boolean);
  if (!_scopePicked.length) _scopePicked = [data.report.scope_default].filter(Boolean);
  _render(data.report);
}

// No baseline inside the file and none attached (an XER update, or an XML exported without its
// baseline project): say so plainly and let the planner attach it right here. The attachment is
// remembered for this update and used by every feature (Earned Value, reports, AI Chat…).
function _noBaseline(body, missing, problem, expectedName) {
  const lost = missing ? `<div style="margin-top:6px">The baseline attached earlier (${escapeHtml(missing)}) is no longer available — attach it again.</div>` : '';
  const prob = problem ? `<div class="ua-note" style="margin-top:10px;color:var(--danger)">${escapeHtml(problem)}</div>` : '';
  body.innerHTML = `<div class="ua-empty"><div style="font-size:15px;color:var(--text);margin-bottom:8px">This update carries no baseline and none is attached.</div>
    ${expectedName ? `<div style="margin-bottom:6px;color:var(--text)"><b>${escapeHtml(expectedBaselineAdvice(expectedName))}</b></div>` : ''}
    <div>${escapeHtml(UPDATE_NO_BASELINE_ADVICE)}</div>${lost}
    <div style="margin-top:12px"><button class="btn-primary" id="ua-attach-bl">${ATTACH_BASELINE_LABEL}</button></div>${prob}</div>`;
  document.getElementById('ua-attach-bl')?.addEventListener('click', async () => {
    const btn = document.getElementById('ua-attach-bl');
    if (btn) { btn.disabled = true; btn.textContent = 'Reading baseline…'; }
    const data = await attachBaselineFile();
    if (data.cancelled) { _noBaseline(body, missing, '', expectedName); return; }
    const p = attachProblem(data);
    if (p) { _noBaseline(body, missing, p, expectedName); return; }
    body.innerHTML = `<div class="ua-empty">Reading this update against its baseline…</div>`;
    _runAnalyze();                                 // the server now resolves the attached baseline
  });
}

// ── Render ───────────────────────────────────────────────────────────────────

function _render(report) {
  const body = document.getElementById('update-body');
  body.innerHTML = `
    <div class="cmp-exports" style="margin-bottom:6px">
      <span class="cmp-file" style="margin-right:auto"><b>${escapeHtml(report.project_name || 'Project')}</b> · data date ${escapeHtml(_fdate(report.data_date))} · ${escapeHtml(_fileName())}</span>
      <span class="ua-rename-wrap"><span id="ua-title" class="ua-title" contenteditable="true" spellcheck="false" title="Click to rename this report">${escapeHtml(report.title || 'Update Analysis')}</span>
        <button class="btn-secondary" id="ua-title-edit" title="Rename the report">✎ Rename</button>
        <button class="btn-secondary" id="ua-title-reset" title="Back to the default name">Reset</button></span>
      <button class="btn-secondary" id="ua-export-pdf">Export PDF</button>
      <button class="btn-secondary" id="ua-export-xlsx">Export Excel</button>
    </div>
    ${report.baseline_label ? `<div class="ua-note" id="ua-baseline" style="margin:0 0 6px">Baseline: ${escapeHtml(report.baseline_label)}</div>` : ''}
    <div class="ua-sec">1 · Time Status</div>
    <div class="ua-card">${_summaryHtml(report)}${_timeStatusHtml(report)}</div>

    <div class="ua-sec">2 · Planned vs Actual — by activity code</div>
    <div class="ua-card">${_byCodeControls(report)}<div id="ua-bc-charts">${_byCodeCharts(report)}</div></div>

    <div class="ua-sec">3 · Driving Path Analyzer</div>
    <div class="ua-card">${_drivingHtml(report)}</div>

    <div class="ua-sec">4 · Planned vs Actual — by activity count</div>
    <div class="ua-card">${_countControls(report)}<div id="ua-cn-body">${_countsHtml(report.counts)}</div></div>

    <div class="ua-sec">5 · Scope Weight &amp; Recommendation</div>
    <div class="ua-card">${_scopeControls(report)}<div id="ua-scope-body">${_scopeHtml(report)}</div></div>

    <div class="ua-sec">6 · Progress S-curve</div>
    <div class="ua-card" id="ua-sc-body">${_scurveHtml(report)}</div>`;

  _wireTitle(report);
  document.getElementById('ua-export-pdf').addEventListener('click', _exportPdf);
  document.getElementById('ua-export-xlsx').addEventListener('click', _exportExcel);
  _wireByCode(report);
  _wireSummaryLevel();
  _wireCounts(report);
  _wireScope(report);
  _wireScurve(report);
}

// The report name - editable on screen, carried into the PDF / Word / Excel (report.title).
function _wireTitle(report) {
  const t = document.getElementById('ua-title');
  if (!t) return;
  const save = () => {
    const v = (t.textContent || '').replace(/\s+/g, ' ').trim();
    report.title = v && v !== 'Update Analysis' ? v : '';
    if (_shownReport) _shownReport.title = report.title;
    t.textContent = v || 'Update Analysis';
  };
  t.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); t.blur(); } });
  t.addEventListener('blur', save);
  document.getElementById('ua-title-edit')?.addEventListener('click', () => {
    t.focus();
    const r = document.createRange(); r.selectNodeContents(t);
    const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  });
  document.getElementById('ua-title-reset')?.addEventListener('click', () => { t.textContent = 'Update Analysis'; save(); });
}

// One "Activity code" button: a click opens a panel listing every activity code (and its values
// where the section filters by value), with a search box (Ibrahim, 15-Oct). The chips inside keep
// each section's own data attributes, so each section's wiring is unchanged.
function _codePicker(id, label, inner) {
  return `<span class="ua-pk" id="${id}"><button class="ua-pkbtn" type="button">Activity code: <b class="ua-pkcur">${escapeHtml(label)}</b> ▾</button>
    <div class="ua-pkpop"><input class="ua-pksearch" placeholder="Search codes or values…">${inner}</div></span>`;
}
function _wirePicker(id) {
  const pk = document.getElementById(id);
  if (!pk) return;
  const pop = pk.querySelector('.ua-pkpop');
  pk.querySelector('.ua-pkbtn').addEventListener('click', e => {
    e.stopPropagation();
    document.querySelectorAll('.ua-pkpop.open').forEach(p => { if (p !== pop) p.classList.remove('open'); });
    pop.classList.toggle('open');
    if (pop.classList.contains('open')) pk.querySelector('.ua-pksearch').focus();
  });
  pop.addEventListener('click', e => e.stopPropagation());
  pk.querySelector('.ua-pksearch').addEventListener('input', e => {
    const q = e.target.value.toLowerCase();
    pop.querySelectorAll('button[data-q]').forEach(b => { b.style.display = !q || b.dataset.q.includes(q) ? '' : 'none'; });
    pop.querySelectorAll('.ua-pkgrp').forEach(g => {
      const any = [...g.querySelectorAll('button[data-q]')].some(b => b.style.display !== 'none');
      g.style.display = any ? '' : 'none';
    });
  });
}
function _pickerLabel(id, text) {
  const el = document.querySelector(`#${id} .ua-pkcur`);
  if (el) el.textContent = text;
}
if (typeof document !== 'undefined' && document.addEventListener) {
  document.addEventListener('click', () => document.querySelectorAll('.ua-pkpop.open').forEach(p => p.classList.remove('open')));
}

// Section 5 — scope weight + recommendation (multi-select; one code renders instantly, several are combined server-side)
function _scopeControls(report) {
  const scope = report.scope || {};
  const types = Object.keys(scope);
  if (!types.length) return '';
  _scopePicked = _scopePicked.filter(t => scope[t]);
  if (!_scopePicked.length) _scopePicked = [scope[report.scope_default] ? report.scope_default : types[0]];
  const chips = types.map(t => `<button class="ua-scope-btn ${_scopePicked.includes(t) ? 'on' : ''}" data-scope="${escapeHtml(t)}" data-q="${escapeHtml(t.toLowerCase())}">${escapeHtml(t)}<i>${(scope[t].rows || []).length} values</i></button>`).join('');
  return `<div class="ua-slicer">${_codePicker('ua-pk-scope', _scopePicked.join(', '), `<div class="ua-pkgrp"><div class="ua-pkgh">Cost-loaded activity codes</div>${chips}</div>`)}
    <span style="margin-left:auto;color:var(--muted);font-size:12px">pick one or more · recommendation updates with the codes</span></div>`;
}
function _m(v) { v = +v || 0; return Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + ' M' : Math.round(v).toLocaleString(); }
function _scopeRender(s) {
  if (!s) return `<div class="ua-note">No cost-loaded activity codes to weigh.</div>`;
  const rows = s.rows || [];
  const pv = s.pv != null ? s.pv : rows.reduce((t, r) => t + (r.pv || 0), 0);
  const ev = s.ev != null ? s.ev : rows.reduce((t, r) => t + (r.ev || 0), 0);
  const d = ev - pv;
  const tile = (t, v) => `<div class="ua-k5"><div class="t">${t}</div><div class="v">${v}</div></div>`;
  const strip = `<div class="ua-strip">${tile('Cost', _m(s.total))}${tile('Planned Value', _m(pv))}${tile('Earned Value', _m(ev))}`
    + tile('EV − PV', `<span class="${d < 0 ? 'ua-bad' : 'ua-good'}">${d < 0 ? '−' : '+'}${_m(Math.abs(d))}</span>`)
    + tile('SPI', pv ? (ev / pv).toFixed(2) : '—') + `</div>`;
  const body = rows.map(r => {
    const dd = (r.ev || 0) - (r.pv || 0);
    const col = dd >= 0 ? C.actual : ((r.pv && dd / r.pv > -0.1) ? '#d68a1c' : '#c0392b');
    return `<tr><td><b>${escapeHtml(r.value)}</b></td><td class="ua-n">${_m(r.bac)}</td><td class="ua-n">${(r.weight_pct || 0).toFixed(1)}%</td>
      <td class="ua-n">${_m(r.pv)}</td><td class="ua-n">${_m(r.ev)}</td>
      <td class="ua-n ua-gap ${dd < 0 ? 'ua-bad' : 'ua-good'}">${dd < 0 ? '−' : '+'}${_m(Math.abs(dd))}</td>
      <td><div class="ua-cbar"><i style="width:${Math.max(0, Math.min(100, r.actual || 0))}%;background:${col}"></i><u style="left:calc(${Math.max(0, Math.min(100, r.planned || 0))}% - 1px)"></u></div>
        <div class="ua-of">${(r.actual || 0).toFixed(1)}% earned · ${(r.planned || 0).toFixed(1)}% planned</div></td></tr>`;
  }).join('');
  const recs = (s.recommendation || []).map(t => `<p>${escapeHtml(t)}</p>`).join('');
  return `<div class="ua-scope-h">Scope by <b>${escapeHtml(s.code_type || '')}</b> · cost-loaded construction scope</div>${strip}
    <table class="ua-cnt"><thead><tr><th>Scope</th><th class="ua-n">Cost</th><th class="ua-n">Weight</th><th class="ua-n">Planned Value</th>
      <th class="ua-n">Earned Value</th><th class="ua-n">EV − PV</th><th style="width:200px">Earned vs planned</th></tr></thead><tbody>${body}</tbody></table>
    <div class="ua-leg"><span class="ua-sw" style="background:${C.actual}"></span>earned % <span class="ua-sw" style="background:#1b2433;width:3px"></span>planned % · Planned Value = Cost × planned % · Earned Value = Cost × actual %</div>
    ${recs ? `<div class="ua-rec2"><b>Recommendation</b>${recs}</div>` : ''}`;
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
  _wirePicker('ua-pk-scope');
  const paint = () => {
    document.querySelectorAll('.ua-scope-btn[data-scope]').forEach(b => b.classList.toggle('on', _scopePicked.includes(b.dataset.scope)));
    _pickerLabel('ua-pk-scope', _scopePicked.join(', '));
  };
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

// Section 1 (approved 2026-11-23): verdict line, six key numbers, Progress at the data date
// (the donut + the ruler) — the text comes ready-made from the server (report.summary), so
// the screen, the PDF / Word and Excel say the same thing. PV / EV / Variance cards below.
function _summaryHtml(report) {
  const sm = report.summary || {};
  const ts = report.time_status || {};
  const kpi = k => `<div class="ua-kpi ${k.tone || ''}${k.key === 'finish' ? ' date' : ''}"><div class="l">${escapeHtml(k.label)}</div>
    <div class="v">${escapeHtml(k.value)}</div><div class="s">${escapeHtml(k.sub || '')}</div></div>`;
  return `<div class="ua-verdict ${escapeHtml(sm.status || '')}"><span class="ua-pill">${escapeHtml(sm.label || '')}</span>
      <div><div class="ua-vh">${escapeHtml(sm.headline || '')}</div><div class="ua-vd">${escapeHtml(sm.detail || '')}</div></div></div>
    <div class="ua-kpis">${(sm.kpis || []).map(kpi).join('')}</div>
    <div class="ua-prog"><h4>Progress at the data date</h4>${_progressHtml(ts)}</div>`;
}

function _progressHtml(ts) {
  const ep = ts.elapsed_pct, pp = ts.planned_pct, ap = ts.actual_pct;
  const clamp = v => Math.max(0, Math.min(100, +v || 0));
  const e = clamp(ap), t = clamp(ep), p = clamp(pp);
  const close = Math.abs(t - p) < 14;
  const tMk = ep != null ? `<div class="ua-mk up" style="left:${t}%;background:var(--muted)"><span style="color:var(--muted)">Time ${ep.toFixed(1)}%</span></div>` : '';
  const pMk = pp != null ? `<div class="ua-mk ${close && ep != null ? 'up2' : 'up'}" style="left:${p}%;background:${C.plan}"><span style="color:${C.plan}">Planned ${_pct2(pp)}</span></div>` : '';
  const gap = [];
  if (ts.behind_plan != null) gap.push(`Behind plan <b class="${ts.behind_plan > 0 ? 'ua-bad' : 'ua-good'}">${Math.abs(ts.behind_plan).toFixed(2)} points</b> (earned vs planned)`);
  if (ts.behind_clock != null) gap.push(`behind the clock <b class="${ts.behind_clock > 0 ? 'ua-bad' : 'ua-good'}">${Math.abs(ts.behind_clock).toFixed(2)} points</b> (earned vs time used)`);
  const cv = ts.cost_variance;
  const varTxt = typeof cv === 'number' ? ` Variance EV − PV <b class="${cv < 0 ? 'ua-bad' : 'ua-good'}">${cv < 0 ? '−' : '+'}${_m(Math.abs(cv))}</b>.` : '';
  return `<div class="ua-progrow"><div>${_donut(ep, pp, ap)}<div class="ua-donleg"><span style="color:${C.blue}">●</span> outer: time ${ep != null ? ep.toFixed(1) + '%' : '—'} · <span style="color:${C.good}">●</span> inner: earned</div></div>
      <div class="ua-rul"><div class="ua-ruler"><div class="f" style="width:${e}%"></div>
        <div class="ua-mk dn" style="left:${e}%;background:${C.actual}"><span style="color:${C.actual}">Earned ${_pct2(ap)}</span></div>${tMk}${pMk}</div></div></div>
    <div class="ua-gapnote">${gap.join(' · ')}${gap.length ? '.' : ''}${varTxt}</div>`;
}

function _timeStatusHtml(report) {
  const ts = report.time_status || {};
  const cv = ts.cost_variance;
  return `<div class="ua-cost">
      <div class="ua-costcard"><div class="ua-cl">Planned Value (PV)</div><div class="ua-cv">${_num(ts.pv)}</div></div>
      <div class="ua-costcard"><div class="ua-cl">Earned Value (EV)</div><div class="ua-cv">${_num(ts.ev)}</div></div>
      <div class="ua-costcard"><div class="ua-cl">Variance = EV − PV</div><div class="ua-cv ${cv < 0 ? 'ua-bad' : ''}">${_num(cv)}</div></div>
    </div>`;
}

// Section 6 — Progress S-curve (approved 2026-11-23). Planned = the Time Status rule at every
// month end; Earned = rebuilt from actual dates, or an earlier imported update of the same
// job at its own data date; Forecast = remaining work over P6's remaining dates.
function _scurveHtml(report) {
  const sc = report.scurve || {};
  const pts = sc.points || [];
  if (!pts.length) return `<div class="ua-note">${sc.error ? 'The S-curve could not be drawn for this file.' : 'Not enough dated activities to draw the S-curve.'}</div>`;
  const earlier = sc.earlier || [];
  const on = earlier.filter(e => e.on), off = earlier.filter(e => !e.on && e.earned != null);
  const chips = on.map(e => `<span class="ua-chip">● ${escapeHtml(_fdate(e.data_date))} · ${_pct2(e.earned)}${e.auto ? '' : ' (added)'}<button data-scpick="${e.snapshot_id}" data-scon="0" title="Take it off the curve">×</button></span>`).join('');
  const add = off.length ? `<select class="ua-sel" id="ua-sc-add"><option value="">+ Add an earlier imported update…</option>${off.map(e =>
      `<option value="${e.snapshot_id}">${escapeHtml(_fdate(e.data_date))} · ${escapeHtml(e.label || e.file || '')} · ${_pct2(e.earned)} earned</option>`).join('')}</select>` : '';
  const dd = pts.find(p => p.kind === 'data_date') || {};
  const lastRem = sc.last_remaining_finish;
  const ms = (((report.critical_path || {}).charts || [])[0] || {}).milestone || {};
  const rows = pts.map(p => {
    const g = p.earned != null && p.planned != null ? p.earned - p.planned : null;
    const src = p.earned_source === 'update' ? 'earlier update' : (p.earned_source || '');
    const k = p.kind === 'data_date' ? 'dd' : '';
    return `<tr><td class="${k}">${escapeHtml(_fdate(p.date))}${p.kind === 'data_date' ? ' · data date' : p.kind === 'update' ? ' · update' : ''}</td>
      <td class="ua-n ${k}">${p.planned != null ? _pct2(p.planned) : ''}</td><td class="ua-n ${k}">${p.earned != null ? _pct2(p.earned) : ''}</td>
      <td class="ua-n ${k}">${p.forecast != null ? _pct2(p.forecast) : ''}</td>
      <td class="ua-n ${k} ${g == null ? '' : g < 0 ? 'ua-bad' : 'ua-good'}">${g == null ? '' : (g > 0 ? '+' : '') + g.toFixed(2)}</td>
      <td class="${k}" style="color:var(--muted)">${escapeHtml(src)}</td></tr>`;
  }).join('');
  const basis = sc.basis === 'duration' ? 'its planned duration (this file carries no cost)' : 'its budget';
  const msNote = ms.expected_finish && lastRem && String(ms.expected_finish).slice(0, 10) !== lastRem
    ? ` (${escapeHtml(ms.name || 'the completion milestone')} is ${escapeHtml(_fdate(ms.expected_finish))})` : '';
  return `<div class="ua-earl"><b>Earlier updates on this curve:</b>${chips || '<span style="color:var(--muted)">none found with the same baseline</span>'}${add}</div>
    <div class="ua-sc">${_scurveSvg(pts, dd, ms)}</div>
    <div class="ua-leg"><span class="ua-sw" style="background:${C.plan}"></span>Planned (baseline)<span class="ua-sw" style="background:${C.actual}"></span>Earned, rebuilt from actual dates<span class="ua-sw" style="background:${C.actual};border-radius:50%"></span>Earned, from an earlier update<span class="ua-sw" style="background:none;border-top:2px dashed ${C.bad};height:0;width:16px"></span>Forecast (P6 remaining dates)</div>
    <div class="ua-note" style="font-style:normal;margin-top:8px"><b>How each line is drawn.</b> <b>Planned</b> = the same Planned % rule as Time Status (each activity's baseline dates, in its own calendar's working time, weighted by ${basis}), at every month end; on the data date it is exactly ${_pct2(dd.planned)}.
      <b>Earned</b> = each activity's % complete spread over its actual start → actual finish (or the data date); where an earlier update of this job was imported, its own Earned % stands at its data date; on the data date it is exactly ${_pct2(dd.earned)}.
      <b>Forecast</b> = each activity's remaining work spread over its remaining start → finish in this P6 file${lastRem ? `; it reaches 100% on ${escapeHtml(_fdate(lastRem))}` : ''}${msNote}.</div>
    <details class="ua-sct" open><summary>Monthly values</summary>
      <table class="ua-cnt"><thead><tr><th>Date</th><th class="ua-n">Planned %</th><th class="ua-n">Earned %</th><th class="ua-n">Forecast %</th><th class="ua-n">Gap (earned − planned)</th><th>Earned from</th></tr></thead><tbody>${rows}</tbody></table></details>`;
}

function _scurveSvg(pts, dd, ms) {
  const W = 1060, H = 360, L = 48, R = 150, T = 22, B = 44;
  const t = s => Date.parse(String(s).slice(0, 10));
  const tms = pts.map(p => t(p.date));
  const ext = [ms.baseline_finish, ms.expected_finish].filter(Boolean).map(t);
  const tA = Math.min(...tms) - 15 * 864e5, tB = Math.max(...tms, ...ext) + 5 * 864e5;
  const X = v => L + (v - tA) / (tB - tA) * (W - L - R), Y = v => T + (100 - v) * (H - T - B) / 100;
  let s = '';
  for (let v = 0; v <= 100; v += 25) s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--border)"/><text x="${L - 8}" y="${Y(v) + 4}" font-size="11" text-anchor="end" fill="var(--muted)">${v}%</text>`;
  const months = pts.filter(p => p.kind === 'month'), every = Math.max(1, Math.ceil(months.length / 12));
  months.forEach((p, i) => { if (i % every === 0) s += `<text x="${X(t(p.date)).toFixed(1)}" y="${H - 16}" font-size="11" text-anchor="middle" fill="var(--muted)">${escapeHtml(_fdate(p.date).slice(3))}</text>`; });
  const line = key => pts.filter(p => p[key] != null).map((p, i) => `${i ? 'L' : 'M'}${X(t(p.date)).toFixed(1)},${Y(p[key]).toFixed(1)}`).join(' ');
  s += `<path d="${line('planned')}" fill="none" stroke="${C.plan}" stroke-width="3"/>`;
  s += `<path d="${line('forecast')}" fill="none" stroke="${C.bad}" stroke-width="2.5" stroke-dasharray="7 5"/>`;
  s += `<path d="${line('earned')}" fill="none" stroke="${C.actual}" stroke-width="3.5"/>`;
  pts.filter(p => p.earned != null && p.kind === 'month').forEach(p => { s += `<circle cx="${X(t(p.date)).toFixed(1)}" cy="${Y(p.earned).toFixed(1)}" r="3" fill="var(--card-bg)" stroke="${C.actual}" stroke-width="1.5"/>`; });
  pts.filter(p => p.kind === 'update').forEach(p => { s += `<circle cx="${X(t(p.date)).toFixed(1)}" cy="${Y(p.earned).toFixed(1)}" r="5.5" fill="${C.actual}"><title>Earlier update ${escapeHtml(_fdate(p.date))}: ${_pct2(p.earned)} earned</title></circle>`; });
  if (dd.date) {
    const xd = X(t(dd.date));
    s += `<line x1="${xd}" x2="${xd}" y1="${T}" y2="${H - B}" stroke="var(--accent)" stroke-dasharray="4 4"/><text x="${xd + 6}" y="${T + 10}" font-size="11.5" fill="var(--accent)" font-weight="700">data date ${escapeHtml(_fdate(dd.date))}</text>`;
    if (dd.planned != null) s += `<circle cx="${xd}" cy="${Y(dd.planned)}" r="5.5" fill="${C.plan}"/><text x="${xd - 9}" y="${Y(dd.planned) - 8}" font-size="12" text-anchor="end" font-weight="700" fill="${C.plan}">Planned ${_pct2(dd.planned)}</text>`;
    s += `<circle cx="${xd}" cy="${Y(dd.earned)}" r="5.5" fill="${C.actual}"/><text x="${xd + 9}" y="${Y(dd.earned) + 18}" font-size="12" font-weight="700" fill="${C.actual}">Earned ${_pct2(dd.earned)}</text>`;
  }
  if (ms.baseline_finish) { const xb = X(t(ms.baseline_finish)); s += `<line x1="${xb}" x2="${xb}" y1="${Y(100)}" y2="${H - B}" stroke="var(--muted)" stroke-dasharray="3 4"/><text x="${xb - 4}" y="${Y(100) - 6}" font-size="11" text-anchor="end" fill="var(--muted)">baseline finish ${escapeHtml(_fdate(ms.baseline_finish))}</text>`; }
  if (ms.expected_finish) {
    const xe = X(t(ms.expected_finish)), sl = ms.slip_days;
    s += `<line x1="${xe}" x2="${xe}" y1="${Y(100)}" y2="${H - B}" stroke="${C.bad}" stroke-dasharray="3 4"/><text font-size="11" fill="${C.bad}" font-weight="700"><tspan x="${xe + 5}" y="${Y(45)}">expected finish</tspan><tspan x="${xe + 5}" dy="14">${escapeHtml(_fdate(ms.expected_finish))}</tspan>${sl != null ? `<tspan x="${xe + 5}" dy="14">(${sl > 0 ? '+' : ''}${sl} d)</tspan>` : ''}</text>`;
  }
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Progress S-curve">${s}</svg>`;
}

function _wireScurve(report) {
  const box = document.getElementById('ua-sc-body');
  if (!box) return;
  const pick = async (id, on) => {
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/update/scurve_earlier`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ snapshot_id: state.currentSnapshotId || null, scurve: report.scurve, pick: id, on }),
      });
      const data = await resp.json();
      if (!data.ok) { showError(`Could not change the S-curve: ${data.error || 'unknown error'}`); return; }
      report.scurve = data.scurve; if (_shownReport) _shownReport.scurve = data.scurve;
      box.innerHTML = _scurveHtml(report);
      _wireScurve(report);
    } catch { showError('Could not reach the local server to change the S-curve.'); }
  };
  box.querySelectorAll('[data-scpick]').forEach(b => b.addEventListener('click', () => pick(+b.dataset.scpick, b.dataset.scon === '1')));
  box.querySelector('#ua-sc-add')?.addEventListener('change', e => { if (e.target.value) pick(+e.target.value, true); });
}

// Section 2 — one chart per selected code
function _byCodeControls(report) {
  const types = report.code_types || [];
  if (!types.length) return '';
  const by = report.by_code || {};
  const chips = types.map(t => `<button class="ua-code-btn ${_pickedTypes.includes(t) ? 'on' : ''}" data-type="${escapeHtml(t)}" data-q="${escapeHtml(t.toLowerCase())}">${escapeHtml(t)}<i>${(by[t] || []).length} values</i></button>`).join('');
  return `<div class="ua-slicer">${_codePicker('ua-pk-bycode', _pickedTypes.join(', ') || 'pick a code', `<div class="ua-pkgrp"><div class="ua-pkgh">Activity codes</div>${chips}</div>`)}
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
  _wirePicker('ua-pk-bycode');
  document.querySelectorAll('.ua-code-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.type, i = _pickedTypes.indexOf(t);
      if (i >= 0) { if (_pickedTypes.length > 1) _pickedTypes.splice(i, 1); } else _pickedTypes.push(t);
      document.querySelectorAll('.ua-code-btn').forEach(b => b.classList.toggle('on', _pickedTypes.includes(b.dataset.type)));
      _pickerLabel('ua-pk-bycode', _pickedTypes.join(', '));
      box.innerHTML = _byCodeCharts(report);
    });
  });
}

// Section 3 — driving path
function _drivingHtml(report) {
  const cp = report.critical_path || {};
  // Work fronts only - the WBS each activity sits in (15-Oct: no other summary level)
  const levelSel = `<div class="ua-slicer"><span style="color:var(--muted)">Work fronts on the driving path, in order — the WBS each activity sits in</span>
    <span style="margin-left:auto;color:var(--muted);font-size:12px">construction / execution work only</span></div>`;
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
  const by = report.by_code || {};
  const on = (t, v) => _countFilter.type === t && _countFilter.value === v;
  const groups = types.map(t => {
    const vals = (by[t] || []).map(r => `<button class="ua-scope-btn ${on(t, r.value) ? 'on' : ''}" data-cnt="${escapeHtml(t)}" data-cnv="${escapeHtml(r.value)}" data-q="${escapeHtml((t + ' ' + r.value).toLowerCase())}">${escapeHtml(r.value)}${r.activity_count != null ? `<i>${Number(r.activity_count).toLocaleString()}</i>` : ''}</button>`).join('');
    return vals ? `<div class="ua-pkgrp"><div class="ua-pkgh">${escapeHtml(t)}</div>${vals}</div>` : '';
  }).join('');
  const all = `<button class="ua-scope-btn ${_countFilter.value ? '' : 'on'}" data-cnt="" data-cnv="" data-q="all activities">All activities</button>`;
  const cur = _countFilter.value ? `${_countFilter.type}: ${_countFilter.value}` : 'All activities';
  return `<div class="ua-slicer">${_codePicker('ua-pk-cn', cur, all + groups)}
    <span style="margin-left:auto;color:var(--muted);font-size:12px">every activity of each WBS, as P6 lists them</span></div>`;
}
// Section 4 - Planned vs Actual by COUNT of activities, per WBS (15-Oct redesign). Actual = P6's
// Activity Status; Planned = baseline dates at the data date. The planner can show only the WBS
// picked; the report and the workbook print the same rows (report.counts.wbs_shown).
let _cnWbs = null;          // null = every WBS, else a Set of the WBS names shown
function _cnRow(name, n, p, a, cls) {
  const pp = n ? 100 * p[0] / n : 0, ap = n ? 100 * a[0] / n : 0, g = ap - pp;
  const col = g >= -0.05 ? C.actual : (g > -10 ? '#d68a1c' : '#c0392b');
  const cell = i => `<td class="ua-n"><b>${a[i].toLocaleString()}</b> <span class="ua-of">/ ${p[i].toLocaleString()}</span></td>`;
  return `<tr class="${cls || ''}"><td>${escapeHtml(name)}</td><td class="ua-n">${n.toLocaleString()}</td>${cell(0)}${cell(1)}${cell(2)}
    <td><div class="ua-cbar"><i style="width:${ap}%;background:${col}"></i><u style="left:calc(${pp}% - 1px)"></u></div>
      <div class="ua-of">${ap.toFixed(1)}% actual · ${pp.toFixed(1)}% planned</div></td>
    <td class="ua-n ua-gap ${g < -0.05 ? 'ua-bad' : (g > 0.05 ? 'ua-good' : '')}">${g > 0 ? '+' : ''}${g.toFixed(1)}</td></tr>`;
}
function _countsHtml(c) {
  const rows = (c && c.by_wbs) || [];
  if (!c || !c.total || !rows.length) return `<div class="ua-note">No activities to count.</div>`;
  const shown = rows.filter(r => !_cnWbs || _cnWbs.has(r.wbs));
  c.wbs_shown = _cnWbs ? shown.map(r => r.wbs) : null;          // the exports print the same rows
  const chips = `<div class="ua-cnwbs"><span style="color:var(--muted)">Show WBS</span>
    <button class="ua-scope-btn ${_cnWbs ? '' : 'on'}" data-cnwbs="__all__">All</button>`
    + rows.map(r => `<button class="ua-scope-btn ${_cnWbs && _cnWbs.has(r.wbs) ? 'on' : ''}" data-cnwbs="${escapeHtml(r.wbs)}">${escapeHtml(r.wbs)}</button>`).join('')
    + `</div>`;
  const sum = list => list.reduce((t, r) => [t[0] + r.activities, t[1].map((x, i) => x + r.planned[i]), t[2].map((x, i) => x + r.actual[i])], [0, [0, 0, 0], [0, 0, 0]]);
  const body = shown.map(r => _cnRow(r.wbs, r.activities, r.planned, r.actual)).join('');
  const st = sum(shown), all = sum(rows);
  // one activity-code value picked: no total rows (Ibrahim, 15-Oct)
  const totals = (c.code_filter || _countFilter.value) ? '' :
    (_cnWbs ? _cnRow(`Shown WBS (${shown.length} of ${rows.length})`, st[0], st[1], st[2], 'ua-tot') : '')
    + _cnRow('Whole schedule', all[0], all[1], all[2], 'ua-tot');
  const nb = c.no_baseline ? ` · ${c.no_baseline.toLocaleString()} activit${c.no_baseline === 1 ? 'y has' : 'ies have'} no baseline dates (counted as planned Not Started)` : '';
  return chips + `<div class="ua-cnhow">Actual = P6 Activity Status (Completed / In Progress / Not Started) · Planned = baseline dates at the data date${nb}</div>
    <table class="ua-cnt"><thead><tr><th>WBS</th><th class="ua-n">Activities</th><th class="ua-n">Completed<br><span class="ua-of">actual / planned</span></th>
      <th class="ua-n">In Progress<br><span class="ua-of">actual / planned</span></th><th class="ua-n">Not Started<br><span class="ua-of">actual / planned</span></th>
      <th style="width:210px">% complete by count</th><th class="ua-n">Gap</th></tr></thead><tbody>${body}${totals}</tbody></table>
    <div class="ua-leg"><span class="ua-sw" style="background:${C.actual}"></span>actual % complete <span class="ua-sw" style="background:#1b2433;width:3px"></span>planned % complete · gap = actual − planned (points)</div>`;
}
function _wireCnWbs(report) {
  const box = document.getElementById('ua-cn-body');
  if (!box) return;
  box.querySelectorAll('[data-cnwbs]').forEach(b => b.addEventListener('click', () => {
    const w = b.dataset.cnwbs;
    if (w === '__all__') _cnWbs = null;
    else {
      const next = new Set(_cnWbs || []);
      next.has(w) ? next.delete(w) : next.add(w);
      _cnWbs = next.size ? next : null;
    }
    box.innerHTML = _countsHtml(report.counts);
    _wireCnWbs(report);
  }));
}
function _wireCounts(report) {
  const box = document.getElementById('ua-cn-body');
  if (!box) return;
  _wirePicker('ua-pk-cn');
  const refresh = async () => {
    const cf = _countFilter.type && _countFilter.value ? { type: _countFilter.type, value: _countFilter.value } : null;
    box.innerHTML = `<div class="ua-note">Counting…</div>`;
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/update/counts`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ xml_path: state.currentXmlPath || '', cached_path: state.currentCachedPath || '', code_filter: cf }),
      });
      const data = await resp.json();
      if (data.ok) {
        data.counts.code_filter = cf;                 // the exports drop the total rows too
        report.counts = data.counts; if (_shownReport) _shownReport.counts = data.counts;
        box.innerHTML = _countsHtml(data.counts); _wireCnWbs(report);
      } else box.innerHTML = `<div class="ua-note">Could not apply that filter.</div>`;
    } catch { box.innerHTML = `<div class="ua-note">Could not reach the server.</div>`; }
  };
  document.querySelectorAll('#ua-pk-cn [data-cnt]').forEach(btn => btn.addEventListener('click', () => {
    _countFilter = { type: btn.dataset.cnt, value: btn.dataset.cnv };
    document.querySelectorAll('#ua-pk-cn [data-cnt]').forEach(b => b.classList.toggle('on', b === btn));
    _pickerLabel('ua-pk-cn', _countFilter.value ? `${_countFilter.type}: ${_countFilter.value}` : 'All activities');
    document.querySelector('#ua-pk-cn .ua-pkpop')?.classList.remove('open');
    refresh();
  }));
  _wireCnWbs(report);
}

// ── Exports ──────────────────────────────────────────────────────────────────

const UA_SECTIONS = [
  ['time', 'Time Status'], ['bycode', 'Planned vs Actual by code'],
  ['driving', 'Driving Path Analyzer'], ['counts', 'Planned vs Actual by count'], ['scope', 'Scope Weight & Recommendation'],
  ['scurve', 'Progress S-curve'],
];

function _codeFilter() { return _pickedTypes.length ? { types: _pickedTypes.slice() } : null; }

// Export PDF opens the ONE shared preview (preview.js): tick whole sections or single tables /
// charts inside them, reorder, then Print or Save (owner comment 1). The report is rendered
// with the activity codes and the scope-weight code picked on screen.
async function _exportPdf() {
  if (!_shownReport) { showError('Analyze the update first, then export.'); return; }
  _uaTheme = getSavedMode();
  const fetchPreview = async (keys, theme) => {
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/update/report`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report: _shownReport, preview: true, code_filter: _codeFilter(), scope_code: _scopePicked[0] || '', theme: theme || _uaTheme }),
      });
      const data = await resp.json();
      if (!data.ok) { showError(`Preview failed: ${data.error || 'unknown error'}`); return null; }
      return data.html || null;
    } catch { showError('Could not reach the local server for the preview.'); return null; }
  };
  const html = await fetchPreview(null, _uaTheme);
  if (!html) return;
  const sections = UA_SECTIONS.map(([key, label]) => ({ key, label }));
  showReportPreview({
    title: 'Update Analysis preview', subtitle: _shownReport.file || _shownReport.project_name || '', html,
    sections, selected: sections.map(x => x.key), storageKey: 'p6_report_sections_update', initialMode: _uaTheme,
    feature: 'Update Analysis', exportName: 'update_analysis',
    exports: ['pdf', 'docx', 'html', 'xlsx'], onExcel: () => _exportExcel(),
    meta: { project: _shownReport.project_name || '', data_date: _shownReport.data_date ? String(_shownReport.data_date).slice(0, 10) : '' },
    onRerender:    (keys, theme) => fetchPreview(keys, theme),
    onThemeChange: (theme, keys) => { _uaTheme = theme; return fetchPreview(keys, theme); },
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
