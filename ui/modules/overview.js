// Project ▸ Overview and Project ▸ WBS views.
// Both render from the parsed result already held in state — no re-parse, no new
// API. Overview is a project-level "at a glance"; WBS is a summary of the WBS
// hierarchy on a calendar — the user picks a main branch (e.g. Engineering /
// Construction) and every WBS beneath it is shown, expanded to the level that
// holds activities, with weighted planned/actual % and a start→finish bar.
import { fmtEGP, fmtDate, dateText } from './format.js';
import { state } from './state.js';
import { baselineApprox, baselineApproxLine } from './baseline.js';

// printable sections for the global File ▸ Print flow
let _ovPrint = null, _wbsPrint = null;
export function overviewPrint() { return _ovPrint; }
export function wbsPrint() { return _wbsPrint; }

const pct = (v) => (v == null ? '—' : `${(v * 100).toFixed(2)}%`);
const bar = (planned, actual) => {
  const p = Math.max(0, Math.min(100, (planned || 0) * 100));
  const a = Math.max(0, Math.min(100, (actual || 0) * 100));
  return `<div class="ovb"><div class="ovb-plan" style="width:${p.toFixed(1)}%"></div>
    <div class="ovb-act" style="width:${a.toFixed(1)}%"></div></div>`;
};

const OV_GROUP_KEY = 'p6evm_ov_group';
let ovGroupKey = null;             // the picked "Progress by" grouping (WBS or an activity code)
export function overviewGroupKey() { return ovGroupKey; }
const OV_HIDE0_KEY = 'p6evm_ov_hide0';
let ovHideZero = null;             // hide the values whose Planned % and Actual % are both 0
export function overviewHideZero() { return !!ovHideZero; }
const isZero = (v) => !(Math.abs(v || 0) >= 0.00005);          // shows as 0.00 %
// One histogram pair: a Planned column and an Actual column side by side, value on top.
const histGroup = (name, n, planned, actual, extra, ax) => {
  const h = (v) => Math.max(0, Math.min(100, (v || 0) * 100));
  return `<div class="ovh-g" title="${escapeAttr(name)} — planned ${pct(planned)} · actual ${pct(actual)}">
      <div class="ovh-bars">
        <div class="ovh-col p"><em>${pct(planned)}</em><i style="height:${h(planned).toFixed(1)}%"></i></div>
        <div class="ovh-col a"><em>${pct(actual)}</em><i style="height:${h(actual).toFixed(1)}%"></i></div>
      </div>
      <div class="ovh-lbl">${escapeHtml(name)}<span>${n} activities${extra || ''}</span></div>
    </div>`;
};

export function renderOverview(result) {
  const el = document.getElementById('overview-body');
  _ovPrint = null;
  if (!el || !result) return;
  // Owner comment 93: every progress figure here comes from the COST-LOADED activities only
  // (budget-weighted, as P6 weights them) — activities with no cost (Engineering /
  // Procurement) take no part. A schedule with no cost at all keeps the duration-weighted
  // figures and says so.
  const cl = result.cost_loaded || null;
  const plannedPct = cl ? cl.planned_pct : result.overall_planned_pct;
  const actualPct = cl ? cl.actual_pct : result.overall_actual_pct;
  const pv = cl ? cl.pv : result.pv, ev = cl ? cl.ev : result.ev;
  const spiVal = cl ? cl.spi : result.spi;
  const spi = spiVal != null ? spiVal.toFixed(2) : '—';
  // Delay in working days from the finish-milestone float; when the schedule
  // carries no milestone float, fall back to forecast-finish minus baseline-finish.
  let delayDays = result.delay_days;
  if (delayDays == null && result.expected_finish && result.baseline_finish) {
    const d = Math.round((new Date(result.expected_finish) - new Date(result.baseline_finish)) / 86400000);
    if (!Number.isNaN(d)) delayDays = d;
  }
  const delay = delayDays != null ? `${delayDays} d` : '—';
  const delayCls = delayDays > 0 ? 'bad' : (delayDays < 0 ? 'good' : '');
  // No baseline in the file and none attached: the update's own Planned dates stand in, so every
  // baseline-derived value is marked '· approx' + one 'Baseline:' line (printed too — R2).
  const approx = baselineApprox(result, state.currentXmlPath);
  const ax = approx ? ' · approx' : '';
  const blLine = approx ? `<p class="ov-note" data-baseline-approx>${escapeHtml(baselineApproxLine(result, state.currentXmlPath))}</p>` : '';

  // Progress by WBS / by a P6 activity code (owner comment 94) — cost-loaded activities only
  const groups = (cl && Array.isArray(result.progress_groups)) ? result.progress_groups : [];
  if (ovGroupKey == null) { try { ovGroupKey = localStorage.getItem(OV_GROUP_KEY); } catch { /* default */ } }
  const group = groups.find((g) => g.key === ovGroupKey) || groups[0] || null;
  if (ovHideZero == null) { try { ovHideZero = localStorage.getItem(OV_HIDE0_KEY) === '1'; } catch { ovHideZero = false; } }
  const cats = Object.entries(result.categories || {});
  const allRows = group
    ? group.rows.map((r) => ({ name: r.name, n: r.activities, planned: r.planned_pct, actual: r.actual_pct, extra: '' }))
    : cats.map(([name, c]) => ({ name, n: c.activity_count, planned: c.planned_pct, actual: c.actual_pct, extra: c.overridden ? ' · manual override' : '' }));
  const zeroN = allRows.filter((r) => isZero(r.planned) && isZero(r.actual)).length;
  const shown = ovHideZero ? allRows.filter((r) => !(isZero(r.planned) && isZero(r.actual))) : allRows;
  const catRows = shown.map((r) => histGroup(r.name, r.n, r.planned, r.actual, r.extra, ax)).join('');
  const byLabel = group ? group.label : 'category';

  const basis = cl
    ? `Planned %, Actual %, Planned value, Earned value and SPI are taken from the <b>${cl.activities}</b> cost-loaded activities only (of ${cl.all_activities}), each weighted by its budget as P6 weights it. Activities with no cost — Engineering, Procurement — are not included. SPI = Actual % ÷ Planned %.`
    : 'This schedule carries no cost loading, so Planned % and Actual % are weighted by activity duration instead of budget.';
  const kpisHtml = `<div class="ov-kpis">
      <div class="ov-kpi"><div class="k">SPI · schedule${ax}</div><div class="v ${spiVal != null && spiVal < 1 ? 'bad' : ''}">${spi}</div></div>
      <div class="ov-kpi"><div class="k">Forecast finish</div><div class="v sm">${result.expected_finish ? fmtDate(result.expected_finish) : '—'}</div></div>
      <div class="ov-kpi"><div class="k">Delay${ax}</div><div class="v ${delayCls}">${delay}</div></div>
      <div class="ov-kpi"><div class="k">Baseline finish${ax}</div><div class="v sm">${result.baseline_finish ? fmtDate(result.baseline_finish) : '—'}</div></div>
      <div class="ov-kpi"><div class="k">Planned %${ax}</div><div class="v">${pct(plannedPct)}</div></div>
      <div class="ov-kpi"><div class="k">Actual %</div><div class="v">${pct(actualPct)}</div></div>
      <div class="ov-kpi"><div class="k">Planned value${ax}</div><div class="v sm">${fmtEGP(pv)}</div></div>
      <div class="ov-kpi"><div class="k">Earned value</div><div class="v sm">${fmtEGP(ev)}</div></div>
    </div><p class="ov-note ov-basis">${basis}</p>${blLine}`;
  const legend = `<div class="ovh-legend"><span><i class="p"></i>Planned %${ax}</span><span><i class="a"></i>Actual %</span>${ovHideZero && zeroN ? `<span class="ovh-hid">${zeroN} with Planned 0 % and Actual 0 % hidden</span>` : ''}</div>`;
  const catsHtml = catRows
    ? `${legend}<div class="ovh" data-export="image">${catRows}</div>`
    : `<p class="ov-empty">${allRows.length ? 'Every value has Planned 0 % and Actual 0 % — untick “Hide 0 %” to show them.' : 'No categories configured for this schedule.'}</p>`;

  _ovPrint = [
    { key: 'kpis', label: 'Key indicators', html: kpisHtml },
    { key: 'categories', label: `Progress by ${byLabel}`, html: catsHtml },
  ];

  const picker = groups.length > 1
    ? `<label class="ov-groupby">Show by <select id="ov-group">${groups.map((g) =>
        `<option value="${escapeAttr(g.key)}"${g === group ? ' selected' : ''}>${escapeHtml(g.key === 'wbs' ? 'WBS' : 'Activity code — ' + g.label)}</option>`).join('')}</select></label>`
    : '';

  el.innerHTML = `
    <div class="ov-head">
      <div class="ov-title">
        <h2>${result.project_name || 'Project overview'}</h2>
        <div class="ov-chips">
          <span class="ov-chip">data date <b>${fmtDate(result.data_date)}</b></span>
          <span class="ov-chip"><b>${result.activity_count ?? '—'}</b> activities</span>
          ${cl ? `<span class="ov-chip"><b>${cl.activities}</b> cost-loaded</span>` : ''}
          <span class="ov-chip"><b>${result.calendar_count ?? '—'}</b> calendars</span>
        </div>
      </div>
    </div>
    ${kpisHtml}
    <div class="ov-section-label">Progress by ${escapeHtml(byLabel)} ${picker}
      <label class="ov-groupby ov-hide0"><input type="checkbox" id="ov-hide0"${ovHideZero ? ' checked' : ''}> Hide Planned 0 % and Actual 0 %${zeroN ? ` (${zeroN})` : ''}</label></div>
    ${catsHtml}
    <p class="ov-note">${group ? 'Pick <b>WBS</b> or any P6 <b>activity code</b> in “Show by” to see a Planned % column beside an Actual % column for each value of that code — cost-loaded activities only, weighted by budget. Tick “Hide Planned 0 % and Actual 0 %” to drop the values with no progress planned or achieved yet.' : 'A project summary from the imported update.'} Open a module from the navigator to drill in.</p>`;

  const h0 = document.getElementById('ov-hide0');
  if (h0) h0.addEventListener('change', () => {
    ovHideZero = h0.checked;
    try { localStorage.setItem(OV_HIDE0_KEY, ovHideZero ? '1' : '0'); } catch { /* non-fatal */ }
    renderOverview(result);
  });
  const sel = document.getElementById('ov-group');
  if (sel) sel.addEventListener('change', () => {
    ovGroupKey = sel.value;
    try { localStorage.setItem(OV_GROUP_KEY, ovGroupKey); } catch { /* non-fatal */ }
    renderOverview(result);
  });
}

// ── Project ▸ WBS summary timeline ──────────────────────────────────────
const DAY = 86400000;
const WBS_WBS_W = 260;             // the WBS tree column (always shown)
// Optional data columns the user can show/hide (WBS tree + timeline are always on).
const WBS_COLS = [
  { key: 'baseline_start',  label: 'Baseline Start',  w: 96, kind: 'date' },
  { key: 'baseline_finish', label: 'Baseline Finish', w: 96, kind: 'date' },
  { key: 'start',           label: 'Expected Start',  w: 96, kind: 'date' },
  { key: 'finish',          label: 'Expected Finish', w: 96, kind: 'date' },
  { key: 'planned',         label: 'Planned %',       w: 64, kind: 'pct'  },
  { key: 'actual',          label: 'Actual %',        w: 64, kind: 'pct'  },
  { key: 'delay',           label: 'Delay',           w: 74, kind: 'delay'},
];
const WBS_MODE_KEY = 'p6evm_wbs_mode';
let wbsMode = null;               // 'all' | 'critical' — which activities the WBS summarises
const money = (v) => (typeof v === 'number' ? v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—');
const WBS_COLS_KEY = 'p6evm_wbs_cols';
let wbsMainId = null;              // remembers the picked main branch across re-renders
let wbsCols = null;               // Set of shown column keys (localStorage-backed)
let wbsColMenuOpen = false;       // Columns dropdown open state (kept across re-renders)

const toMs = (s) => { if (!s) return NaN; const d = new Date(s.length <= 10 ? s + 'T00:00:00' : s); const t = d.getTime(); return Number.isNaN(t) ? NaN : t; };
const fmtShort = (ms) => dateText(new Date(ms));           // 03-Dec.2026 (comment 46)
const pctVal = (v) => (v == null ? '—' : `${v.toFixed(1)}%`);   // backend already gives 0–100

function wbsShownCols() {
  if (!wbsCols) {
    let shown = WBS_COLS.map((c) => c.key);           // default: all shown
    try { const s = JSON.parse(localStorage.getItem(WBS_COLS_KEY) || 'null'); if (Array.isArray(s)) shown = s; } catch { /* default */ }
    wbsCols = new Set(shown);
  }
  return WBS_COLS.filter((c) => wbsCols.has(c.key));
}

// Delay = the WBS's Total Float on the update read as days late, −(total float), worked out by
// the server from the WBS's latest Late Finish against its latest Early Finish on the project's
// default calendar. A result stored before that figure existed falls back to calendar days.
function wbsDelay(n) {
  if ('delay' in n) return n.delay;
  const ef = toMs(n.finish), bf = toMs(n.baseline_finish);
  if (Number.isNaN(ef) || Number.isNaN(bf)) return null;
  return Math.round((ef - bf) / DAY);
}

// Columns measured against the baseline — marked '· approx' when the update's own Planned dates
// stand in for it (no baseline in the file, none attached).
const WBS_BL_COLS = new Set(['baseline_start', 'baseline_finish', 'planned', 'delay']);
function wbsColLabel(col, approx) {
  return approx && WBS_BL_COLS.has(col.key) ? `${col.label} · approx` : col.label;
}

// Owner comment 63: a WBS with no cost-loaded activity has no Planned % / Actual % in P6, so
// none is shown for it. (A schedule with no cost at all keeps its duration-weighted figures.)
let wbsAnyCost = false;
const wbsHasPct = (n) => !wbsAnyCost || (n.cost_loaded || 0) > 0;

function wbsCellVal(col, n) {
  if (col.kind === 'pct')  return wbsHasPct(n) ? pctVal(n[col.key]) : 'no cost';
  if (col.kind === 'date') { const ms = toMs(n[col.key]); return Number.isNaN(ms) ? '—' : fmtShort(ms); }
  if (col.kind === 'money') return money(n[col.key]);
  if (col.kind === 'int')   return n[col.key] == null ? '—' : String(n[col.key]);
  if (col.kind === 'days')  return n[col.key] == null ? '—' : `${n[col.key]} d`;
  const d = wbsDelay(n);                                // delay
  return d == null ? '—' : `${d > 0 ? '+' : ''}${d} d`;
}

export function renderWbs(result) {
  const el = document.getElementById('wbs-body');
  _wbsPrint = null;
  if (!el || !result) return;
  // 'All activities' or 'Critical activities' — the second summarises each WBS over its critical
  // activities only, exactly what P6 shows in its WBS bands with the Critical filter on.
  if (wbsMode == null) { try { wbsMode = localStorage.getItem(WBS_MODE_KEY) || 'all'; } catch { wbsMode = 'all'; } }
  const critNodes = result.wbs_critical || [];
  const critical = wbsMode === 'critical' && critNodes.length > 0;
  const nodes = critical ? critNodes : (result.wbs_summary || []);
  const nodeIds = new Set(nodes.map((n) => n.id));
  const mains = (result.wbs_main || []).filter((m) => nodeIds.has(m.id));

  if (!nodes.length) {
    el.innerHTML = `
      <div class="ov-head"><div class="ov-title"><h2>WBS — summary</h2></div></div>
      <p class="ov-note">No WBS breakdown is available.${result.activity_count
        ? ' Re-import this schedule to build the WBS summary — a re-opened project loads rolled-up metrics from the database rather than the WBS tree.'
        : ''}</p>`;
    return;
  }

  wbsAnyCost = nodes.some((n) => (n.cost_loaded || 0) > 0);

  // pick the main branch (default to the first; keep the user's choice if still valid)
  const mainIds = mains.map((m) => m.id);
  if (!wbsMainId || !mainIds.includes(wbsMainId)) wbsMainId = mainIds.length ? mainIds[0] : null;

  // slice the pre-order tree to the chosen branch + its descendants, depth rebased
  let subset = nodes;
  const startIdx = nodes.findIndex((n) => n.id === wbsMainId);
  if (startIdx >= 0) {
    const bd = nodes[startIdx].depth;
    subset = [nodes[startIdx]];
    for (let i = startIdx + 1; i < nodes.length && nodes[i].depth > bd; i++) subset.push(nodes[i]);
  }
  const baseDepth = subset.length ? subset[0].depth : 0;
  const branch = subset[0] || {};
  // a branch with no cost-loaded WBS at all (e.g. Engineering) loses the two % columns
  const branchPct = subset.some(wbsHasPct);
  const cols = wbsShownCols().filter((c) => branchPct || c.kind !== 'pct');
  // The WBS column is as wide as its longest name at its level needs (indent included), so no
  // level is cut short; a name longer than the room left wraps onto a second line instead.
  const colsW = cols.reduce((s, c) => s + c.w, 0);
  const need = subset.reduce((m, n) => Math.max(m, (n.depth - baseDepth) * 16 + String(n.name || '').length * 7.4 + 52), WBS_WBS_W);
  const room = Math.max(WBS_WBS_W, (el.clientWidth || 1180) - colsW - 320);
  const wbsW = Math.round(Math.min(need, room, 620));
  const leftW = wbsW + colsW;

  // time scale over the branch's dated nodes — baseline and expected both, so
  // the track spans the wider of the two (+ data date)
  let min = Infinity, max = -Infinity;
  for (const n of subset) {
    for (const v of [n.start, n.finish, n.baseline_start, n.baseline_finish]) {
      const t = toMs(v);
      if (!Number.isNaN(t)) { min = Math.min(min, t); max = Math.max(max, t); }
    }
  }
  const dd = toMs(result.data_date);
  if (!Number.isNaN(dd)) { min = Math.min(min, dd); max = Math.max(max, dd); }
  const dated = Number.isFinite(min) && Number.isFinite(max) && max > min;
  if (!dated) { min = Date.now(); max = min + DAY; }

  const totalDays = Math.max(1, Math.round((max - min) / DAY));
  // Owner comment 64: the timeline always fits the width of the screen (positions are a
  // share of the track), so the whole WBS shows with no sideways scroll.
  const trackW = Math.max(160, (el.clientWidth || 1180) - leftW - 4);
  const ppd = trackW / totalDays;
  const xOf = (ms) => ((ms - min) / (max - min)) * 100;

  // month ticks / gridlines / year markers
  const monthPx = ppd * 30.4;
  const step = monthPx >= 60 ? 1 : Math.ceil(60 / monthPx);
  let ticks = '', grid = '', k = 0;
  const t = new Date(min); t.setDate(1); t.setHours(0, 0, 0, 0);
  for (; t.getTime() <= max; t.setMonth(t.getMonth() + 1), k++) {
    const x = xOf(t.getTime());
    if (x < -0.05 || x > 100.05) continue;
    const lbl = k % step === 0 ? `<span>${t.toLocaleDateString('en-GB', { month: 'short' })}</span>` : '';
    ticks += `<div class="wbst-tk" style="left:${x.toFixed(2)}%">${lbl}</div>`;
    grid  += `<div class="wbst-gl" style="left:${x.toFixed(2)}%"></div>`;
    if (t.getMonth() === 0) ticks += `<div class="wbst-yr" style="left:calc(${x.toFixed(2)}% + 3px)">${t.getFullYear()}</div>`;
  }
  const ddx = !Number.isNaN(dd) ? xOf(dd) : null;

  const rows = subset.map((n) => {
    const rd = n.depth - baseDepth;
    const leaf = n.leaf;
    const marker = leaf ? '<span class="wbst-dot"></span>' : '<span class="wbst-mk">▾</span>';
    const sMs = toMs(n.start), fMs = toMs(n.finish);
    const hasBar = dated && !Number.isNaN(sMs) && !Number.isNaN(fMs);
    let bar = '';
    if (hasBar) {
      const left = xOf(sMs), w = Math.max(0.6, xOf(fMs) - left);
      const hp = wbsHasPct(n);
      const ac = (!hp || n.actual == null) ? null : Math.max(0, Math.min(100, n.actual));
      const pl = (!hp || n.planned == null) ? null : Math.max(0, Math.min(100, n.planned));
      const behind = ac != null && pl != null && pl > ac
        ? `<div class="wbst-behind" style="left:${ac}%;width:${(pl - ac).toFixed(1)}%"></div>` : '';
      const tick = pl != null ? `<div class="wbst-tick" style="left:${pl}%"></div>` : '';
      bar = `<div class="wbst-bar${leaf ? '' : ' sum'}" style="left:${left.toFixed(2)}%;width:${Math.min(w, 100 - left).toFixed(2)}%">
          ${ac != null ? `<div class="wbst-act" style="width:${ac}%"></div>` : ''}${behind}${tick}
          <div class="wbst-cap"></div></div>`;
    }
    const dataCells = cols.map((c) => {
      let cls = 'wc-cell ' + (c.kind === 'date' ? 'wc-date' : 'wc-num');
      let inner = wbsCellVal(c, n);
      if (c.kind === 'delay') {
        const d = wbsDelay(n);
        if (d != null && d > 0) cls += ' wc-bad';
        else if (d != null && d < 0) cls += ' wc-good';
      }
      if (c.kind === 'pct' && !wbsHasPct(n)) cls += ' wc-nocost';
      else if (c.key === 'actual') inner = `<b>${inner}</b>`;
      return `<div class="${cls}" style="width:${c.w}px">${inner}</div>`;
    }).join('');
    return `<div class="wbst-row ${leaf ? 'leaf' : 'sum'} d${rd}">
      <div class="wc-wbs"><div class="wbst-nm" style="padding-left:${rd * 16}px">${marker}<span class="nm" title="${escapeAttr(n.name)}">${escapeHtml(n.name)}</span></div></div>
      ${dataCells}
      <div class="wc-tl">${bar}</div>
    </div>`;
  }).join('');

  // printable WBS: a clean static table of the visible columns (no scrolling timeline)
  const approx = baselineApprox(result, state.currentXmlPath);
  const blLine = approx ? baselineApproxLine(result, state.currentXmlPath) : '';
  const headCells = cols.map((c) => `<th class="${c.kind === 'date' ? 'wp-date' : 'wp-num'}">${wbsColLabel(c, approx)}</th>`).join('');
  const bodyRows = subset.map((n) => {
    const rd = n.depth - baseDepth;
    const cells = cols.map((c) => `<td class="${c.kind === 'date' ? 'wp-date' : 'wp-num'}">${wbsCellVal(c, n)}</td>`).join('');
    return `<tr class="${n.leaf ? 'leaf' : 'sum'}"><td style="padding-left:${rd * 14}px">${escapeHtml(n.name)}</td>${cells}</tr>`;
  }).join('');
  // Printable WBS report split into individually-selectable sections for the
  // Report Contents picker (File ▸ Print): a headline Overview + the detailed table.
  // (Both plain wbs-print tables, so they inherit the existing report styling.)
  const _wbsLeaves = subset.filter((n) => n.leaf).length;
  const _wbsOverview = `<table class="wbs-print"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>
      <tr><td>Main WBS branch</td><td>${escapeHtml(branch.name || 'all')}</td></tr>
      <tr><td>Activities</td><td>${branch.activities ?? '—'}</td></tr>
      <tr><td>WBS nodes shown</td><td>${subset.length} (${_wbsLeaves} at activity level)</td></tr>
      <tr><td>Date span</td><td>${dated ? `${fmtShort(min)} → ${fmtShort(max)}` : '—'}</td></tr>
      <tr><td>Data date</td><td>${!Number.isNaN(dd) ? fmtShort(dd) : '—'}</td></tr>
${wbsHasPct(branch) ? `
      <tr><td>Overall planned${approx ? ' · approx' : ''}</td><td>${pctVal(branch.planned)}</td></tr>
      <tr><td>Overall actual</td><td>${pctVal(branch.actual)}</td></tr>` : ''}${approx ? `
      <tr><td>Baseline</td><td>${escapeHtml(blLine.replace(/^Baseline: /, ''))}</td></tr>` : ''}
    </tbody></table>`;
  _wbsPrint = [
    { key: 'overview', label: `WBS overview — ${branch.name || 'all'}${critical ? ' (critical activities)' : ''}`, html: _wbsOverview },
    { key: 'table',    label: 'WBS summary table',
      html: `<table class="wbs-print"><thead><tr><th>WBS</th>${headCells}</tr></thead><tbody>${bodyRows}</tbody></table>` },
  ];

  const modeSeg = critNodes.length
    ? `<div class="wbst-seg wbst-mode" id="wbst-mode"><button data-mode="all" class="${critical ? '' : 'on'}">All activities</button><button data-mode="critical" class="${critical ? 'on' : ''}">Critical activities</button></div>`
    : '';
  const seg = mains.length > 1
    ? `<div class="wbst-seg" id="wbst-seg">${mains.map((m) =>
        `<button data-mw="${escapeAttr(m.id)}" class="${m.id === wbsMainId ? 'on' : ''}">${escapeHtml(m.name)}</button>`).join('')}</div>`
    : '';

  // column chooser — the WBS tree + timeline are always on; every other column is optional
  const chooser = `<div class="wbst-colpick">
      <button type="button" class="wbst-colbtn" id="wbst-colbtn" aria-expanded="${wbsColMenuOpen ? 'true' : 'false'}">▦ Columns</button>
      <div class="wbst-colmenu${wbsColMenuOpen ? '' : ' hidden'}" id="wbst-colmenu">
        <div class="wbst-colmenu-t">Columns to show</div>
        ${WBS_COLS.map((c) =>
          `<label><input type="checkbox" data-col="${c.key}" ${wbsCols.has(c.key) ? 'checked' : ''}> ${c.label}</label>`).join('')}
      </div></div>`;

  el.innerHTML = `
    <div class="ov-head"><div class="ov-title"><h2>WBS — summary${critical ? ' (Critical activities)' : ''}</h2>
      <div class="ov-chips">
        <span class="ov-chip"><b>${branch.activities ?? '—'}</b> activities</span>
        ${dated ? `<span class="ov-chip">${fmtShort(min)} → ${fmtShort(max)}</span>` : ''}
        ${wbsHasPct(branch) ? `<span class="ov-chip">overall <b>${pctVal(branch.planned)}</b> planned${approx ? ' (approx)' : ''} · <b>${pctVal(branch.actual)}</b> actual</span>` : '<span class="ov-chip">not cost-loaded — no Planned % / Actual %</span>'}
      </div></div></div>${approx ? `<p class="ov-note" data-baseline-approx>${escapeHtml(blLine)}</p>` : ''}
    ${modeSeg}${critical ? '<p class="ov-note wbst-modenote">Each WBS is summarised over its <b>critical activities only</b> (flagged Critical in P6, not finished) — the same figures P6 shows in its WBS bands with the Critical filter on: Start, Finish, BL dates, Schedule % (Planned %), Performance % (Actual %) and Total Float (shown as Delay).</p>' : ''}
    <div class="wbst-toolbar">${seg}
      <div class="wbst-legend">
        <span><i class="wbst-lg dur"></i>duration → finish</span>
        <span><i class="wbst-lg act"></i>actual %</span>
        <span><i class="wbst-lg beh"></i>behind plan</span>
        <span><i class="wbst-lg tgt"></i>plan target</span>
        <span><i class="wbst-lg cut"></i>cut-off date</span>
      </div>${chooser}</div>
    <div class="wbst-wrap"><div class="wbst-inner wbst-fit" style="--wbsw:${wbsW}px;min-width:${leftW + 160}px">
      <div class="wbst-scale">
        <div class="wc-wbs wbst-h">WBS</div>
        ${cols.map((c) => `<div class="wc-cell wbst-h ${c.kind === 'date' ? 'wc-date' : 'wc-num'}" style="width:${c.w}px">${wbsColLabel(c, approx)}</div>`).join('')}
        <div class="wc-tl wbst-scale-track">${ticks}${ddx != null ? `<div class="wbst-ddl${ddx > 78 ? ' r' : ''}" style="left:${ddx.toFixed(2)}%"><span>Cut-off date ${fmtShort(dd)}</span></div>` : ''}</div>
      </div>
      <div class="wbst-grids" style="left:${leftW}px">${grid}${ddx != null ? `<div class="wbst-dd" style="left:${ddx.toFixed(2)}%"></div>` : ''}</div>
      <div class="wbst-rows">${rows}</div>
    </div></div>
    <p class="ov-note">Pick the <b>main WBS</b> — every branch beneath it is shown, expanded to the level that holds activities (●). Each bar is the full rolled-up <b>duration</b>: its right edge lands on the <b>Expected Finish</b>. The deep fill is actual % complete, the amber segment is the gap still behind plan, and the tick marks the plan target. <b>Delay</b> is the WBS’s <b>Total Float on this update</b> read as days late — a float of −60 d is a delay of 60 d (+ late / − ahead); it is not a comparison with the baseline. The dashed line is the <b>cut-off date</b> (data date). WBS are listed in the same order as in P6. Use <b>▦ Columns</b> to choose which columns appear. <b>Planned %</b> and <b>Actual %</b> are shown only for a WBS that holds cost-loaded activities, weighted by their budget; a WBS whose activities carry no cost in P6 shows <b>no cost</b> instead.</p>`;

  const modeEl = document.getElementById('wbst-mode');
  if (modeEl) modeEl.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-mode]');
    if (!b || b.dataset.mode === (critical ? 'critical' : 'all')) return;
    wbsMode = b.dataset.mode;
    try { localStorage.setItem(WBS_MODE_KEY, wbsMode); } catch { /* non-fatal */ }
    renderWbs(result);
  });
  const segEl = document.getElementById('wbst-seg');
  if (segEl) segEl.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-mw]');
    if (!b || b.dataset.mw === wbsMainId) return;
    wbsMainId = b.dataset.mw;
    renderWbs(result);
  });

  // column chooser — toggle the menu; toggling a checkbox shows/hides that column.
  // closeMenu re-queries the DOM so a stale listener left over from a re-render
  // still acts on the live menu (idempotent).
  const colBtn = document.getElementById('wbst-colbtn');
  const colMenu = document.getElementById('wbst-colmenu');
  if (colBtn && colMenu) {
    const closeMenu = () => {
      wbsColMenuOpen = false;
      const m = document.getElementById('wbst-colmenu');
      const b = document.getElementById('wbst-colbtn');
      if (m) m.classList.add('hidden');
      if (b) b.setAttribute('aria-expanded', 'false');
    };
    colBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (colMenu.classList.contains('hidden')) {
        colMenu.classList.remove('hidden');
        wbsColMenuOpen = true;
        colBtn.setAttribute('aria-expanded', 'true');
        document.addEventListener('click', closeMenu, { once: true });   // outside click closes it
      } else {
        closeMenu();
      }
    });
    colMenu.addEventListener('click', (e) => e.stopPropagation());        // keep clicks inside from closing
    colMenu.addEventListener('change', (e) => {
      const cb = e.target.closest('input[data-col]');
      if (!cb) return;
      if (cb.checked) wbsCols.add(cb.dataset.col); else wbsCols.delete(cb.dataset.col);
      try { localStorage.setItem(WBS_COLS_KEY, JSON.stringify([...wbsCols])); } catch { /* non-fatal */ }
      wbsColMenuOpen = true;                 // keep the menu open while the user toggles columns
      renderWbs(result);
    });
    // re-render happened with the menu open → re-arm the outside-click close
    if (wbsColMenuOpen) document.addEventListener('click', closeMenu, { once: true });
  }
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }
