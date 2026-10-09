// Project ▸ Overview and Project ▸ WBS views.
// Both render from the parsed result already held in state — no re-parse, no new
// API. Overview is a project-level "at a glance"; WBS is a summary of the WBS
// hierarchy on a calendar — the user picks a main branch (e.g. Engineering /
// Construction) and every WBS beneath it is shown, expanded to the level that
// holds activities, with weighted planned/actual % and a start→finish bar.
import { fmtEGP, fmtDate, dateText, monthScaleHtml } from './format.js';
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

// ── Execution dashboard: progress BY COUNT of the activities (E1-log style) ──────────────────────
// One table per WBS area, one row per stage, a Total row at the end of each. Actual follows the
// E1 rule (an activity counts once it has STARTED); "Planned till cut-off date" = the activities whose
// baseline finish is on/before the cut-off date. Submittals, Approvals and the other activities
// (PO, delivery ...) are counted in their own columns.
const upct = (v) => (v == null ? '—' : `${v.toFixed(1)}%`);
function uChip(behind) { return behind > 0 ? `<span class="uc-chip ${behind <= 5 ? 'y' : 'r'}">${behind} behind</span>` : '<span class="uc-chip g">On plan</span>'; }
function uGroups(t) {
  const tot = t.total || {};
  return [
    ...(tot.st ? [{ key: 's', label: 'Submittals', n: 'st', due: 'sdue', start: 'sd' }] : []),
    ...(tot.at ? [{ key: 'a', label: 'Approvals', n: 'at', due: 'adue', start: 'ad' }] : []),
    ...(tot.ot ? [{ key: 'o', label: 'Other activities', n: 'ot', due: 'odue', start: 'os' }] : []),
  ];
}
function uRow(r, total, groups) {
  const w = (v) => Math.max(0, Math.min(100, v || 0)).toFixed(1);
  const g = groups.map((x) => `<td class="uc-n">${r[x.n] || '—'}</td><td class="uc-n">${r[x.n] ? r[x.due] : '—'}</td><td class="uc-n">${r[x.n] ? r[x.start] : '—'}</td>`).join('');
  return `<tr class="${total ? 'uc-total' : ''}"><td>${escapeHtml(r.label)}</td>${g}`
    + `<td data-export="bar"><div class="uc-pair"><i class="p" style="width:${w(r.planned_pct)}%"></i><i class="a" style="width:${w(r.actual_pct)}%"></i></div></td>`
    + `<td class="uc-n">${upct(r.planned_pct)}</td><td class="uc-n"><b>${upct(r.actual_pct)}</b></td><td class="uc-c">${uChip(r.behind)}</td></tr>`;
}
function uTable(t, cut) {
  const groups = uGroups(t);
  const h1 = groups.map((x) => `<th colspan="3" class="uc-gh">${x.label}</th>`).join('');
  const ct = cut ? ` (${escapeHtml(cut)})` : '';
  const h2 = groups.map(() => `<th class="uc-n">Total</th><th class="uc-n">Planned till cut-off date${ct}</th><th class="uc-n">Actual till cut-off date${ct}</th>`).join('');
  return `<div class="uc-block" data-part="exec.${escapeAttr(t.title)}" data-part-label="${escapeAttr(t.title)}"><h4>${escapeHtml(t.title)} <span class="uc-tag">count of activities</span></h4>
      <table class="uc-table"><thead><tr><th rowspan="2">${t.first}</th>${h1}<th rowspan="2">Planned vs Actual</th><th rowspan="2" class="uc-n">Planned %${cut ? ' till ' + escapeHtml(cut) : ''}</th><th rowspan="2" class="uc-n">Actual %${cut ? ' till ' + escapeHtml(cut) : ''}</th><th rowspan="2" class="uc-c">Status</th></tr><tr>${h2}</tr></thead>
      <tbody>${t.rows.map((r) => uRow(r, false, groups)).join('')}${uRow(t.total, true, groups)}</tbody></table></div>`;
}
// The Execution dashboard of ONE main WBS (shown above that WBS's table): its headline, the rule, then
// one table per area with a Total row. '' when the WBS has no such activities.
function _countDashboardBody(u, cutoffText, branch) {
  const tabsOf = ((u && u.tables) || []).filter((t) => !branch || (t.branches || []).includes(branch));
  if (!tabsOf.length) return '';
  const sum = tabsOf.reduce((m, t) => { for (const k of ['n', 'started', 'done', 'prog', 'ns', 'due', 'due_prog', 'due_ns']) m[k] += t.total[k] || 0; return m; },
    { n: 0, started: 0, done: 0, prog: 0, ns: 0, due: 0, due_prog: 0, due_ns: 0 });
  const ap = sum.n ? (100 * sum.started) / sum.n : null, pp = sum.n ? (100 * sum.due) / sum.n : null, behind = Math.max(0, sum.due - sum.started);
  const head = `<div class="uc-tiles">
      <div><span>Activities</span><b>${sum.n}</b><em>${branch ? escapeHtml(branch) : 'all branches'} · milestones excluded</em></div>
      <div><span>Actual till cut-off date${cutoffText ? ' ' + escapeHtml(cutoffText) : ''}</span><b>${upct(ap)}</b><em>${sum.started} activities till the cut-off date (${sum.done} completed, ${sum.prog} in progress) · ${sum.ns} not started</em></div>
      <div><span>Planned till cut-off date${cutoffText ? ' ' + escapeHtml(cutoffText) : ''}</span><b>${upct(pp)}</b><em>${sum.due} planned · ${sum.due_prog} should be in progress · ${sum.due_ns} not yet due</em></div>
      <div><span>Behind plan</span><b class="${behind > 0 ? 'bad' : ''}">${behind}</b><em>planned till the cut-off date but not started (${sum.due} − ${sum.started})</em></div></div>`;
  const ex = ((u.summary || {}).excluded_wbs) || [];
  const rule = `<p class="ov-note uc-rule">Counted <b>by number of activities</b>, as in the E1 log: <b>Planned till cut-off date</b> = the activities whose baseline finish is on or before the cut-off date, counted for Submittals, Approvals and the other activities each; <b>Actual till cut-off date</b> = the number of activities <b>till the cut-off date</b> that are in progress or completed. Milestone activities are excluded${ex.length ? `, and the WBS made of milestones (${ex.map(escapeHtml).join(', ')}) are left out completely` : ''}.</p>`;
  const legend = '<div class="uc-legend"><span><i class="p"></i>Planned % till the cut-off date</span><span><i class="a"></i>Actual % till the cut-off date</span></div>';
  const cut = cutoffText ? escapeHtml(cutoffText) : 'the cut-off date';
  const badge = `<div class="uc-badge"><span class="uc-seal">#</span><div><b>COUNT-BASED PROGRESS</b><em>every activity counts as one — no cost weighting</em></div></div>`;
  const howto = `<div class="uc-howto"><b>How to read this progress</b>
      <ul><li><span class="uc-k p"></span><b>Planned % till ${cut}</b> = number of activities whose baseline finish is on or before ${cut} ÷ total number of activities</li>
      <li><span class="uc-k a"></span><b>Actual % till ${cut}</b> = number of activities till ${cut} (in progress or completed) ÷ total number of activities</li>
      <li><span class="uc-k t"></span><b>Submittals · Approvals · Other activities</b> are counted apart; the Total row adds up each column</li></ul></div>`;
  return { badge, body: `${howto}${head}${rule}${legend}${tabsOf.map((t) => uTable(t, cutoffText)).join('')}` };
}
export function executionDashboard(u, cutoffText, branch) {
  const r = _countDashboardBody(u, cutoffText, branch);
  if (!r) return '';
  return `<div class="uc-panel"><div class="uc-titlerow"><div><h3>Execution dashboard</h3><p class="uc-sub">${escapeHtml(branch || 'Project')} Progress Planned VS Actual</p></div>${r.badge}</div>${r.body}</div>`;
}

// A main WBS with at least 95% of its activities cost loaded (Construction) is NOT measured by count:
// its Execution dashboard gives the Planned % / Actual % of its cost-loaded activities (budget weighted).
const COST_SHARE = 0.95;
function costNode(result, id) { return (result.wbs_summary || []).find((n) => n.id === id) || null; }
export function costShare(result, id) {
  const n = costNode(result, id);
  const all = n ? (n.count || n.activities || 0) : 0;
  return all ? (n.cost_loaded || 0) / all : 0;
}
function _costDashboardBody(result, id, name, cutoffText) {
  const n = costNode(result, id);
  if (!n) return null;
  const all = n.count || n.activities || 0, cl = n.cost_loaded || 0;
  const cut = cutoffText ? escapeHtml(cutoffText) : 'the cut-off date';
  const pl = n.planned, ac = n.actual, gap = pl != null && ac != null ? Math.max(0, pl - ac) : null;
  const sub = (result.wbs_summary || []);
  const i0 = sub.findIndex((x) => x.id === id);
  const kids = [];
  if (i0 >= 0) for (let j = i0 + 1; j < sub.length && sub[j].depth > sub[i0].depth; j++) if (sub[j].depth === sub[i0].depth + 1) kids.push(sub[j]);
  const w = (v) => Math.max(0, Math.min(100, v || 0)).toFixed(1);
  const rows = kids.map((k) => `<tr><td>${escapeHtml(k.name)}</td><td class="uc-n">${k.count || k.activities || 0}</td><td class="uc-n">${k.cost_loaded || 0}</td>`
    + `<td data-export="bar"><div class="uc-pair"><i class="p" style="width:${w(k.planned)}%"></i><i class="a" style="width:${w(k.actual)}%"></i></div></td>`
    + `<td class="uc-n">${k.cost_loaded ? pctVal(k.planned) : '—'}</td><td class="uc-n"><b>${k.cost_loaded ? pctVal(k.actual) : '—'}</b></td>`
    + `<td class="uc-c">${(() => { if (!k.cost_loaded || k.planned == null || k.actual == null) return '—'; const g = Math.max(0, k.planned - k.actual); return g > 0 ? `<span class="uc-chip ${g <= 5 ? 'y' : 'r'}">${g.toFixed(1)}% behind</span>` : '<span class="uc-chip g">On plan</span>'; })()}</td></tr>`).join('');
  const table = rows ? `<div class="uc-block" data-part="exec.cost.${escapeAttr(id)}" data-part-label="${escapeAttr(name)} — by WBS"><h4>${escapeHtml(name)} — by WBS <span class="uc-tag">cost-loaded activities</span></h4>
      <table class="uc-table"><thead><tr><th>WBS</th><th class="uc-n">Activities</th><th class="uc-n">Cost loaded</th><th>Planned vs Actual</th><th class="uc-n">Planned % till ${cut}</th><th class="uc-n">Actual % till ${cut}</th><th class="uc-c">Status</th></tr></thead><tbody>${rows}</tbody></table></div>` : '';
  const badge = '<div class="uc-badge cl"><span class="uc-seal">$</span><div><b>COST-LOADED PROGRESS</b><em>weighted by the budget of each activity (P6 cost)</em></div></div>';
  const howto = `<div class="uc-howto"><b>How to read this progress</b><ul>
      <li><span class="uc-k p"></span><b>Planned % till ${cut}</b> = Planned value ÷ budget of the cost-loaded activities</li>
      <li><span class="uc-k a"></span><b>Actual % till ${cut}</b> = Earned value ÷ budget of the cost-loaded activities</li>
      <li><span class="uc-k t"></span>${cl} of the ${all} activities of this WBS (${(100 * cl / all).toFixed(1)}%) are cost loaded, so it is measured by cost, not by the number of activities</li></ul></div>`;
  const tiles = `<div class="uc-tiles">
      <div><span>Cost-loaded activities</span><b>${cl}</b><em>of ${all} activities · ${(100 * cl / all).toFixed(1)}%</em></div>
      <div><span>Planned % till ${cut}</span><b>${pctVal(pl)}</b><em>Planned value ${fmtEGP(n.pv)}</em></div>
      <div><span>Actual % till ${cut}</span><b>${pctVal(ac)}</b><em>Earned value ${fmtEGP(n.ev)}</em></div>
      <div><span>Behind plan</span><b class="${gap > 0 ? 'bad' : ''}">${gap == null ? '—' : gap.toFixed(1) + '%'}</b><em>Planned % − Actual %</em></div></div>`;
  const legend = '<div class="uc-legend"><span><i class="p"></i>Planned % till the cut-off date</span><span><i class="a"></i>Actual % till the cut-off date</span></div>';
  return { badge, body: `${howto}${tiles}${legend}${table}` };
}
function costDashboard(result, id, name, cutoffText) {
  const r = _costDashboardBody(result, id, name, cutoffText);
  if (!r) return '';
  return `<div class="uc-panel"><div class="uc-titlerow"><div><h3>Execution dashboard</h3><p class="uc-sub">${escapeHtml(name)} Progress Planned VS Actual</p></div>${r.badge}</div>${r.body}</div>`;
}
// the Execution dashboard of one main WBS: by COST when it is (almost) all cost loaded, else by COUNT
// Milestone-only WBS: Gantt chart showing Planned ◇ vs Actual/Expected ◆ per milestone.
// Each row: Activity ID | Name | Variance | Status chip | Timeline (both markers on one track).
// Planned % = 100 when the baseline finish is on/before the data date, 0 otherwise (P6 logic).
function milestoneGantt(result, branchId, branchName, cutoffText) {
  const MO = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const fmtD = (d) => `${String(d.getDate()).padStart(2, '0')}-${MO[d.getMonth()]}`;
  const toMs = (s) => { if (!s) return NaN; const d = new Date(s.length <= 10 ? s + 'T00:00:00' : s); return d.getTime(); };
  const dd = result.data_date ? new Date(result.data_date) : null;
  const acts = (result.activities || []).filter((a) => a.milestone && (a.wbs_top_id === branchId || a.wbs_top === branchName));
  if (!acts.length) return '';
  const cut = cutoffText ? escapeHtml(cutoffText) : 'the cut-off date';
  const done = acts.filter((a) => a.finish_actual).length;
  const due  = acts.filter((a) => dd && a.planned_finish && new Date(a.planned_finish) <= dd).length;
  const behind = Math.max(0, due - done);

  // time scale: span all baseline + expected dates + data date, padded 15 days each side
  const allT = acts.flatMap((a) => [toMs(a.planned_finish), toMs(a.finish)]).filter((t) => !Number.isNaN(t));
  if (dd) allT.push(dd.getTime());
  if (!allT.length) return '';
  const minT = Math.min(...allT) - 15 * 86400000;
  const maxT = Math.max(...allT) + 15 * 86400000;
  const span = maxT - minT;
  const pctPos = (t) => (((t - minT) / span) * 100).toFixed(3) + '%';

  // month scale header
  const cur = new Date(minT); cur.setDate(1); cur.setHours(0, 0, 0, 0);
  let scaleHtml = '';
  while (cur.getTime() <= maxT) {
    const x = pctPos(cur.getTime());
    scaleHtml += `<div class="mg-month" style="left:${x}">${MO[cur.getMonth()]}</div>`;
    if (cur.getMonth() === 0) scaleHtml += `<div class="mg-yr" style="left:${x}">${cur.getFullYear()}</div>`;
    cur.setMonth(cur.getMonth() + 1);
  }

  // gridlines (reused per row)
  const gc = new Date(minT); gc.setDate(1); gc.setHours(0, 0, 0, 0);
  let gridsHtml = '';
  while (gc.getTime() <= maxT) {
    gridsHtml += `<div class="mg-gl${gc.getMonth() === 0 ? ' yr' : ''}" style="left:${pctPos(gc.getTime())}"></div>`;
    gc.setMonth(gc.getMonth() + 1);
  }
  const ddX = dd ? pctPos(dd.getTime()) : null;

  // rows
  const rows = acts.map((a) => {
    const blT = toMs(a.planned_finish), exT = toMs(a.finish);
    const hasBl = !Number.isNaN(blT), hasEx = !Number.isNaN(exT);
    const blX = hasBl ? pctPos(blT) : null;
    const exX = hasEx ? pctPos(exT) : null;
    const diffD = (hasBl && hasEx) ? Math.round((exT - blT) / 86400000) : null;
    const slipped = diffD != null && diffD > 1;
    const early   = diffD != null && diffD < -1;
    const same    = diffD != null && Math.abs(diffD) <= 1;
    const isDone  = !!a.finish_actual;
    const ddPlanned = dd && hasBl && blT <= dd.getTime();

    // variance text + class
    const varTxt = diffD == null ? '—' : same ? 'On time' : slipped ? `+${diffD}d` : `${diffD}d`;
    const varCls = same ? 'mg-same' : slipped ? 'mg-slip' : 'mg-early';

    // status chip
    const chip = isDone
      ? '<span class="uc-chip g">✓ Completed</span>'
      : ddPlanned ? '<span class="uc-chip r">Not Completed</span>'
      : '<span class="uc-chip y">Not Yet Due</span>';

    // connector between bl and ex
    let connHtml = '';
    if (hasBl && hasEx && !same) {
      const lft = Math.min(parseFloat(blX), parseFloat(exX));
      const w   = Math.abs(parseFloat(exX) - parseFloat(blX)).toFixed(3) + '%';
      const midX = ((parseFloat(blX) + parseFloat(exX)) / 2).toFixed(3) + '%';
      const cls = slipped ? 'slip' : 'early';
      connHtml = `<div class="mg-conn ${cls}" style="left:${lft.toFixed(3)}%;width:${w}"></div>
        <div class="mg-varlbl ${cls}" style="left:${midX}">${escapeHtml(varTxt)}</div>`;
      if (slipped) connHtml += `<div class="mg-arrow" style="left:${exX}"></div>`;
    }

    // markers
    const blMark  = blX ? `<div class="mg-dm bl"  style="left:${blX}" title="Baseline: ${a.planned_finish}"></div><div class="mg-lbl bl" style="left:${blX}">${fmtD(new Date(blT))}</div>` : '';
    const exClass = isDone ? 'done' : slipped ? 'slip' : early ? 'early' : 'same';
    const exMark  = exX ? `<div class="mg-dm ex ${exClass}" style="left:${exX}" title="${isDone ? 'Actual' : 'Expected'}: ${a.finish}"></div><div class="mg-lbl ex ${exClass}" style="left:${exX}">${fmtD(new Date(exT))}${isDone ? ' A' : ''}</div>` : '';

    return `<div class="mg-row">
      <div class="mg-cell mg-id">${escapeHtml(a.id || '')}</div>
      <div class="mg-cell mg-name">${escapeHtml(a.name || '')}</div>
      <div class="mg-cell mg-var ${varCls}">${escapeHtml(varTxt)}</div>
      <div class="mg-cell mg-chip">${chip}</div>
      <div class="mg-cell mg-tl">
        <div class="mg-track">${gridsHtml}${ddX ? `<div class="mg-dd" style="left:${ddX}"></div>` : ''}${connHtml}${blMark}${exMark}</div>
      </div>
    </div>`;
  }).join('');

  const tiles = `<div class="uc-tiles">
    <div><span>Milestones</span><b>${acts.length}</b><em>${escapeHtml(branchName)}</em></div>
    <div><span>Completed</span><b>${done}</b><em>${acts.length ? ((100 * done / acts.length).toFixed(1) + '%') : '—'} of milestones</em></div>
    <div><span>Planned till ${cut}</span><b>${due}</b><em>should be done by cut-off date</em></div>
    <div><span>Behind plan</span><b class="${behind > 0 ? 'bad' : ''}">${behind}</b><em>planned but not completed</em></div>
  </div>`;

  const legend = `<div class="mg-legend">
    <span><span class="mg-ld-dm bl"></span> Planned (baseline) date</span>
    <span><span class="mg-ld-dm done"></span> Actual date (completed)</span>
    <span><span class="mg-ld-dm ex slip"></span> Expected date (not complete)</span>
    <span><span class="mg-ld-line slip"></span> Slipped</span>
    <span><span class="mg-ld-line early"></span> Early / On time</span>
    ${ddX ? `<span><span class="mg-ld-dd"></span> Cut-off date${cutoffText ? ' ' + escapeHtml(cutoffText) : ''}</span>` : ''}
  </div>`;

  const ganttBody = `<div class="mg-wrap">
    <div class="mg-gantt">
      <div class="mg-head">
        <div class="mg-hcell mg-id">Act. ID</div>
        <div class="mg-hcell mg-name">Milestone</div>
        <div class="mg-hcell mg-var">Variance</div>
        <div class="mg-hcell mg-chip">Status</div>
        <div class="mg-hcell mg-tl"><div class="mg-scale">${scaleHtml}</div></div>
      </div>
      ${rows}
    </div>
  </div>
  ${legend}
  <p class="ov-note">◇ Planned = baseline finish date. ◆ Expected/Actual = current finish in P6. Variance = days slipped (+) or early (−). <b>A</b> beside a date = Actual date. Planned % = 100 when baseline finish ≤ cut-off date.</p>`;

  return { tiles, ganttBody, behind };
}

function executionPanel(result, m, cutoffText) {
  const isCost = costShare(result, m.id) >= COST_SHARE;
  const main = isCost
    ? _costDashboardBody(result, m.id, m.name, cutoffText)
    : _countDashboardBody(result.uncosted, cutoffText, m.name);
  const ms = milestoneGantt(result, m.id, m.name, cutoffText);
  if (!main && !ms) return '';
  const badge = main ? main.badge : '';
  const title = isCost ? 'Execution Dashboard' : 'Execution Dashboard';
  const msSection = ms
    ? `<div class="mg-section-divider">Milestone Progress</div>${ms.tiles}${ms.ganttBody}`
    : '';
  return `<div class="uc-panel"><div class="uc-titlerow"><div><h3>${title}</h3><p class="uc-sub">${escapeHtml(m.name)} — Progress Planned VS Actual</p></div>${badge}</div>${main ? main.body : ''}${msSection}</div>`;
}

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
      <div class="ov-kpi"><div class="k">Forecast finish</div><div class="v sm">${result.expected_finish ? fmtDate(result.expected_finish) : '—'}</div></div>
      <div class="ov-kpi"><div class="k">Baseline finish${ax}</div><div class="v sm">${result.baseline_finish ? fmtDate(result.baseline_finish) : '—'}</div></div>
      <div class="ov-kpi"><div class="k">SPI · schedule${ax}</div><div class="v ${spiVal != null && spiVal < 1 ? 'bad' : ''}">${spi}</div></div>
      <div class="ov-kpi"><div class="k">Delay${ax}</div><div class="v ${delayCls}">${delay}</div></div>
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
  { key: 'planned',         label: 'Planned %',       w: 84, kind: 'pct'  },
  { key: 'actual',          label: 'Actual %',        w: 84, kind: 'pct'  },
  { key: 'delay',           label: 'Delay',           w: 74, kind: 'delay'},
];
export function wbsCriticalMode() { return false; }
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

// Delay = the WBS's Total Float on the update with P6's own sign (−72 d = 72 days late), worked out by
// the server from the WBS's latest Late Finish against its latest Early Finish on the project's
// default calendar. A result stored before that figure existed falls back to calendar days.
function wbsDelay(n) {
  if ('delay' in n) return n.delay;
  const ef = toMs(n.finish), bf = toMs(n.baseline_finish);
  if (Number.isNaN(ef) || Number.isNaN(bf)) return null;
  return -Math.round((ef - bf) / DAY);
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

// A WBS whose activities carry no cost has no Planned % / Actual %: its cells say how many
// activities it holds and how many are completed / in progress / not started - by actual status
// (Actual) and by the baseline dates at the cut-off date (Planned).
function ncText(n, kind) {
  const total = n.nc_total || 0;
  if (!total) return '—';
  const parts = [['done', 'completed'], ['prog', 'in progress'], ['ns', 'not started']]
    .filter(([k]) => n[`nc_${kind}_${k}`]).map(([k, l]) => `${n[`nc_${kind}_${k}`]} ${l}`);
  return `${total} activities: ${parts.join(', ')}`;
}
const ncActual = (n) => `<b>Actual</b> ${ncText(n, 'a')}`;
const ncPlanned = (n) => `<b>Planned</b> ${ncText(n, 'p')}`;

function wbsCellVal(col, n) {
  // a WBS with no cost: the COUNT-BASED Planned % / Actual % of its activities (see the Execution dashboard)
  // a WBS whose expected finish is an actual date (all work done) shows 100% actual
  if (col.kind === 'pct') {
    if (col.key === 'actual' && n.finish_actual) return '100.0%';
    return pctVal(wbsHasPct(n) ? n[col.key] : (col.key === 'planned' ? n.planned_count_pct : n.actual_count_pct));
  }
  if (col.kind === 'date') {
    const ms = toMs(n[col.key]);
    if (Number.isNaN(ms)) return '—';
    // an ACTUAL date carries an 'A' beside it, as P6 prints it
    return fmtShort(ms) + ((col.key === 'start' && n.start_actual) || (col.key === 'finish' && n.finish_actual) ? ' A' : '');
  }
  if (col.kind === 'money') return money(n[col.key]);
  if (col.kind === 'int')   return n[col.key] == null ? '—' : String(n[col.key]);
  if (col.kind === 'days')  return n[col.key] == null ? '—' : `${n[col.key]} d`;
  const d = wbsDelay(n);                                // delay
  return d == null ? '—' : `${d} d`;
}

// ── The WBS report: EVERY main WBS is a section of the Report Contents picker, each with its own
// parts (its Execution dashboard, its WBS table) so any WBS can be ticked in or out ───────────────
function sliceBranch(nodes, id) {
  const i = nodes.findIndex((n) => n.id === id);
  if (i < 0) return nodes;
  const bd = nodes[i].depth, out = [nodes[i]];
  for (let j = i + 1; j < nodes.length && nodes[j].depth > bd; j++) out.push(nodes[j]);
  return out;
}
function buildWbsPrint(result, nodes, mains, ctx) {
  const { approx, blLine, dd, critical, ucCut } = ctx;
  const list = mains.length ? mains : (nodes[0] ? [{ id: nodes[0].id, name: nodes[0].name }] : []);
  const sections = [], ovRows = [];
  for (const m of list) {
    const subset = sliceBranch(nodes, m.id);
    if (!subset.length) continue;
    const baseDepth = subset[0].depth, branch = subset[0];
    const branchPct = subset.some(wbsHasPct);
    const cols = wbsShownCols();
    let min = Infinity, max = -Infinity;
    for (const n of subset) for (const v of [n.start, n.finish, n.baseline_start, n.baseline_finish]) {
      const t = toMs(v);
      if (!Number.isNaN(t)) { min = Math.min(min, t); max = Math.max(max, t); }
    }
    if (!Number.isNaN(dd)) { min = Math.min(min, dd); max = Math.max(max, dd); }
    const dated = Number.isFinite(min) && Number.isFinite(max) && max > min;
    const pPos = (ms) => Math.max(0, Math.min(100, ((ms - min) / (max - min)) * 100));
    const pScale = dated ? monthScaleHtml(min, max, pPos) : '';          // EVERY month, written out (Jan, Feb, ...)
    const pDd = (dated && !Number.isNaN(dd)) ? `<u style="left:${pPos(dd).toFixed(2)}%"></u>` : '';
    const headCells = cols.map((c) => `<th class="${c.kind === 'date' ? 'wp-date' : 'wp-num'}">${wbsColLabel(c, approx)}</th>`).join('')
      + (dated ? `<th class="gp-tl wp-bar" data-export="bar"><div class="gp-scale gp-scale-m">${pScale}</div></th>` : '');
    const bodyRows = subset.map((n) => {
      const rd = n.depth - baseDepth;
      const cells = cols.map((c) => `<td class="${c.kind === 'date' ? 'wp-date' : 'wp-num'}">${wbsCellVal(c, n)}</td>`).join('');
      const s0 = toMs(n.start), f0 = toMs(n.finish);
      let pbar = '';
      if (dated && !Number.isNaN(s0) && !Number.isNaN(f0)) {
        const l = pPos(s0), w = Math.max(0.6, pPos(f0) - l);
        const hp = wbsHasPct(n);
        const ac = hp && n.actual != null ? Math.max(0, Math.min(100, n.actual)) : null;
        const pl = hp && n.planned != null ? Math.max(0, Math.min(100, n.planned)) : null;
        const beh = ac != null && pl != null && pl > ac ? `<i style="left:${ac}%;width:${(pl - ac).toFixed(1)}%"></i>` : '';
        pbar = `<b class="gp-bar" style="left:${l.toFixed(2)}%;width:${Math.min(w, 100 - l).toFixed(2)}%">${ac != null ? `<s style="width:${ac}%"></s>` : ''}${beh}${pl != null ? `<em style="left:${pl}%"></em>` : ''}</b>`;
      }
      const barCell = dated ? `<td class="gp-tl wp-bar" data-export="bar"><div class="gp-track">${pDd}${pbar}</div></td>` : '';
      return `<tr class="${n.leaf ? 'leaf' : 'sum'}"><td style="padding-left:${8 + rd * 12}px">${escapeHtml(n.name)}</td>${cells}${barCell}</tr>`;
    }).join('');
    const legend = `<div class="wbs-legend" data-export="skip"><span><i class="dur"></i>duration → finish</span>${branchPct ? '<span><i class="act"></i>actual %</span><span><i class="beh"></i>behind plan</span><span><i class="tgt"></i>plan target</span>' : ''}<span><i class="cut"></i>cut-off date${!Number.isNaN(dd) ? ' ' + fmtShort(dd) : ''}</span><span><b>A</b> beside a date = Actual date</span></div>`;
    const dash = executionPanel(result, m, ucCut);
    const table = `<table class="wbs-print wbs-print-bars"><thead><tr><th>WBS</th>${headCells}</tr></thead><tbody>${bodyRows}</tbody></table>${legend}`;
    sections.push({
      key: `wbs.${m.id}`, label: `${m.name}${critical ? ' (critical activities)' : ''}`,
      html: (dash ? `<div data-part="wbs.${escapeAttr(m.id)}.dash" data-part-label="Execution dashboard — ${escapeAttr(m.name)}">${dash}</div>` : '')
        + `<div data-part="wbs.${escapeAttr(m.id)}.table" data-part-label="WBS table — ${escapeAttr(m.name)}">${table}</div>`,
    });
    const byCost = wbsHasPct(branch);
    ovRows.push(`<tr><td>${escapeHtml(m.name)}</td><td class="wp-num">${branch.count ?? branch.activities ?? '—'}</td>`
      + `<td class="wp-num">${pctVal(byCost ? branch.planned : branch.planned_count_pct)}</td><td class="wp-num">${pctVal(byCost ? branch.actual : branch.actual_count_pct)}</td>`
      + `<td>${byCost ? 'by cost' : 'by count of activities'}</td></tr>`);
  }
  const overview = `<table class="wbs-print"><thead><tr><th>Main WBS</th><th class="wp-num">Activities</th><th class="wp-num">Planned %${ucCut ? ' till ' + escapeHtml(ucCut) : ''}${approx ? ' · approx' : ''}</th><th class="wp-num">Actual %${ucCut ? ' till ' + escapeHtml(ucCut) : ''}</th><th>Basis</th></tr></thead><tbody>${ovRows.join('')}</tbody></table>`
    + `<p class="ov-note">Cut-off date (data date): <b>${!Number.isNaN(dd) ? fmtShort(dd) : '—'}</b>. <b>A</b> beside a date = <b>Actual</b> date. Planned % / Actual % of a WBS with no cost are counted by number of activities (see its Execution dashboard).${approx ? ` Baseline: ${escapeHtml(blLine.replace(/^Baseline: /, ''))}` : ''}</p>`;
  return [{ key: 'overview', label: `WBS overview${critical ? ' — critical activities' : ''}`, html: overview }, ...sections];
}

export function renderWbs(result) {
  const el = document.getElementById('wbs-body');
  _wbsPrint = null;
  if (!el || !result) return;
  // 'All activities' or 'Critical activities' — the second summarises each WBS over its critical
  // activities only, exactly what P6 shows in its WBS bands with the Critical filter on.
  if (wbsMode == null) { try { wbsMode = localStorage.getItem(WBS_MODE_KEY) || 'all'; } catch { wbsMode = 'all'; } }
  const critNodes = result.wbs_critical || [];
  const critical = false;                                  // the WBS screen shows every activity; the critical ones have their own Gantt
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
  const cols = wbsShownCols();
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
  const step = 1;                                              // EVERY month is on the scale
  let ticks = '', grid = '', k = 0;
  const t = new Date(min); t.setDate(1); t.setHours(0, 0, 0, 0);
  for (; t.getTime() <= max; t.setMonth(t.getMonth() + 1), k++) {
    const x = xOf(t.getTime());
    if (x < -0.05 || x > 100.05) continue;
    const mn = t.toLocaleDateString('en-GB', { month: 'short' });                   // Jan, Feb, ... never a single letter
    const lbl = k % step === 0 ? `<span${monthPx < 30 && k % 2 ? ' class="lo"' : ''}>${mn}</span>` : '';
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
        if (d != null && d < 0) cls += ' wc-bad';          // negative float = late
        else if (d != null && d > 0) cls += ' wc-good';
      }
      if (c.key === 'actual') inner = `<b>${inner}</b>`;
      return `<div class="${cls}" style="width:${c.w}px">${inner}</div>`;
    }).join('');
    return `<div class="wbst-row ${leaf ? 'leaf' : 'sum'} d${rd}">
      <div class="wc-wbs"><div class="wbst-nm" style="padding-left:${rd * 16}px">${marker}<span class="nm" title="${escapeAttr(n.name)}">${escapeHtml(n.name)}</span></div></div>
      ${dataCells}
      <div class="wc-tl">${bar}</div>
    </div>`;
  }).join('');

  // printable WBS: EVERY main WBS is a section of the Report Contents picker (see buildWbsPrint)
  const approx = baselineApprox(result, state.currentXmlPath);
  const blLine = approx ? baselineApproxLine(result, state.currentXmlPath) : '';
  const ucCut = !Number.isNaN(dd) ? fmtShort(dd) : '';
  const execHtml = executionPanel(result, { id: branch.id, name: branch.name }, ucCut);       // the dashboard of the WBS shown
  _wbsPrint = buildWbsPrint(result, nodes, mains, { approx, blLine, dd, critical, ucCut });

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
        ${!Number.isNaN(dd) ? `<span class="ov-chip">cut-off date <b>${fmtShort(dd)}</b></span>` : ''}
        ${wbsHasPct(branch) ? `<span class="ov-chip">overall <b>${pctVal(branch.planned)}</b> planned${approx ? ' (approx)' : ''} · <b>${pctVal(branch.actual)}</b> actual</span>` : `<span class="ov-chip">overall <b>${pctVal(branch.planned_count_pct)}</b> planned · <b>${pctVal(branch.actual_count_pct)}</b> actual (by count of activities)</span>`}
      </div></div></div>${approx ? `<p class="ov-note" data-baseline-approx>${escapeHtml(blLine)}</p>` : ''}
    ${seg ? `<div class="wbst-mainsel"><span>Main WBS</span>${seg}</div>` : ''}
    ${execHtml ? `<div class="uc-section-name">Execution Dashboard</div>${execHtml}` : ''}
    <div class="wbst-toolbar">
      <div class="wbst-legend">
        <span><i class="wbst-lg dur"></i>duration → finish</span>
        ${branchPct ? `<span><i class="wbst-lg act"></i>actual %</span>
        <span><i class="wbst-lg beh"></i>behind plan</span>
        <span><i class="wbst-lg tgt"></i>plan target</span>` : ''}
        <span><i class="wbst-lg cut"></i>cut-off date</span>
        <span><b>A</b> beside a date = Actual date</span>
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
    <p class="ov-note">Pick the <b>main WBS</b> — every branch beneath it is shown, expanded to the level that holds activities (●). Each bar is the full rolled-up <b>duration</b>: its right edge lands on the <b>Expected Finish</b>. The deep fill is actual % complete, the amber segment is the gap still behind plan, and the tick marks the plan target. <b>Delay</b> is the WBS’s <b>Total Float on this update</b> with the same sign as in P6 — −72 d means 72 days late, a positive figure is spare float; it is not a comparison with the baseline. The dashed line is the <b>cut-off date</b> (data date). WBS are listed in the same order as in P6. Use <b>▦ Columns</b> to choose which columns appear. <b>Planned %</b> and <b>Actual %</b> are shown only for a WBS that holds cost-loaded activities, weighted by their budget; a WBS whose activities carry no cost in P6 shows a count instead — its activities and how many are completed / in progress / not started, by actual status and by the baseline dates at the cut-off date. <b>A</b> beside a date = <b>Actual</b> date.</p>`;

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
