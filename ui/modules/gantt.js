// Project ▸ Critical Activities (Gantt). Renders a time-scaled bar chart from the slim activity list
// stored with the snapshot (result.activities — present after an import AND after re-opening
// from Recent Projects). Bars use the CURRENT schedule dates (actual where the work has
// started / finished, remaining early dates otherwise — P6's Start / Finish columns) with %
// complete, critical highlighting, month gridlines and a data-date line, grouped by top-level
// WBS. schedulePrint() hands the same rows to File ▸ Print / PDF / Word / HTML.
import { escapeHtml, dateText, monthScaleHtml } from './format.js';
import { reportNameField, onReportName } from './reportname.js';

const DAY = 86400000;
const ROW_H = 38, GRP_H = 26;   // = .g-row / .g-grp heights in style.css (border-box)
const GANTT_BLOCK = 60;         // rows per lazily laid-out block
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const toMs = (s) => new Date(s).getTime();
const attr = (v) => escapeHtml(String(v == null ? '' : v)).replace(/"/g, '&quot;');
// '09 Feb 2026' — the same text the Excel export writes (fixed month names, not the browser's 'Sept')
export function gDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
  return m ? dateText(iso) : '—';
}
const gShort = (iso) => { const t = gDate(iso); return t === '—' ? t : `${t.slice(0, 7)}${t.slice(9)}`; };   // 09 Feb 26
// an ACTUAL date carries an 'A' beside it, as P6 prints it (19-Jun.26 A)
const dA = (iso, actual) => (gShort(iso) + (actual && gShort(iso) !== '—' ? ' A' : ''));
const stCls = (st) => (st === 'Completed' ? 'done' : st === 'In Progress' ? 'prog' : '');
const stTag = (st) => (st ? `<em class="g-st ${stCls(st)}">${escapeHtml(st)}</em>` : '');
// the critical activities in numbers: how many, their share of the schedule, and their Actual %
// (budget-weighted over the top WBS of the critical-only summary)
export function criticalFigures(result, acts, all) {
  const roots = (result.wbs_critical || []).filter((n) => n.depth === 0);
  const bac = roots.reduce((m, n) => m + (n.bac || 0), 0);
  return {
    n: acts.length, all: all.length,
    share: all.length ? (100 * acts.length) / all.length : null,
    planned: bac > 0 ? (100 * roots.reduce((m, n) => m + (n.pv || 0), 0)) / bac : null,
    actual: bac > 0 ? (100 * roots.reduce((m, n) => m + (n.ev || 0), 0)) / bac : null,
    prog: acts.filter((a) => a.status === 'In Progress').length,
    notStarted: acts.filter((a) => a.status === 'Not Started').length,
  };
}
const f1 = (v) => (v == null ? '—' : `${v.toFixed(1)}%`);
const tfText = (a) => (a.tf == null ? '—' : `${a.tf} d`);

// Groups = the true top-level WBS (keyed by its id, so two WBS with the same name never merge),
// ordered by earliest start; activities inside a group ordered by start. The Excel export
// (p6_evm/schedule_excel.py) uses the same rule.
export function ganttGroups(acts) {
  const groups = new Map();
  for (const a of acts || []) {
    const key = a.wbs_top_id || a.wbs_top || 'Ungrouped';
    const sMs = toMs(a.start);
    let g = groups.get(key);
    if (!g) { g = { key, name: a.wbs_top || 'Ungrouped', first: sMs, rows: [] }; groups.set(key, g); }
    g.rows.push({ a, sMs, fMs: toMs(a.finish) });
    if (sMs < g.first) g.first = sMs;
  }
  const out = [...groups.values()].sort((x, y) => x.first - y.first);
  for (const g of out) g.rows.sort((x, y) => x.sMs - y.sMs);
  return out;
}

export function ganttCounts(acts) {
  let crit = 0, ms = 0, done = 0, prog = 0;
  for (const a of acts || []) {
    if (a.critical) crit++;
    if (a.milestone) ms++;
    if (a.status === 'Completed') done++; else if (a.status === 'In Progress') prog++;
  }
  return { total: (acts || []).length, crit, ms, done, prog, notStarted: (acts || []).length - done - prog };
}

function span(acts, dataDate) {
  let min = Infinity, max = -Infinity;
  for (const a of acts) { const s = toMs(a.start), f = toMs(a.finish); if (s < min) min = s; if (f > max) max = f; }
  const dd = dataDate ? toMs(dataDate) : null;
  const ddOk = dd != null && !Number.isNaN(dd);
  if (ddOk) { min = Math.min(min, dd); max = Math.max(max, dd); }
  // the scale opens on the 1st of its first month, so that month is whole and always labelled
  if (Number.isFinite(min)) { const m0 = new Date(min); m0.setDate(1); m0.setHours(0, 0, 0, 0); min = m0.getTime(); }
  // ... and closes on the last day of its last month, so the name of that month fits too
  if (Number.isFinite(max)) { const m1 = new Date(max); m1.setMonth(m1.getMonth() + 1, 1); m1.setHours(0, 0, 0, 0); max = m1.getTime() - 1; }
  return { min, max, dd: ddOk ? dd : null };
}

const tip = (a) => `${a.id} — ${a.name}\nStart ${gDate(a.start)} → Finish ${gDate(a.finish)}`
  + `\n${a.status || ''}${a.status ? ' · ' : ''}Actual ${a.pct}% complete · Total float ${tfText(a)}${a.critical ? ' · Critical' : ''}`
  + (a.wbs ? `\nWBS: ${a.wbs}` : '');

let _print = null;
export function schedulePrint() { return _print; }

// The CRITICAL activities per major WBS of P6 (Phase I Construction Works, Phase I Key Dates ...):
// the planner picks one major WBS, or all of them. Remembered between sessions.
let ganttMain = null, ganttMainFor = null;
export function ganttScope(result) {
  const all = (result && result.activities) || [];
  // the WBS tree of ALL activities (so a WBS without a critical activity still maps to its major WBS)
  const tree = (result && ((result.wbs_summary || []).length ? result.wbs_summary : result.wbs_critical)) || [];
  const byId = new Map(tree.map((n) => [n.id, n]));
  const rootOf = (id) => { let n = byId.get(id), g = 0; while (n && n.parent && byId.has(n.parent) && g++ < 60) n = byId.get(n.parent); return n ? n.id : null; };
  // the results cover the WHOLE project until a major WBS is picked; a newly opened project starts on 'All'
  if (ganttMain == null || ganttMainFor !== result) { ganttMain = ''; ganttCodeVal = ''; ganttMainFor = result; }
  const counts = new Map();
  for (const a of all) if (a.critical) { const r = rootOf(a.wbs_id); if (r) counts.set(r, (counts.get(r) || 0) + 1); }
  const roots = tree.filter((n) => counts.has(n.id)).map((n) => ({ id: n.id, name: n.name, n: counts.get(n.id) }));
  const main = roots.some((r) => r.id === ganttMain) ? ganttMain : '';
  return { all, roots, main, rootOf, scope: main ? all.filter((a) => rootOf(a.wbs_id) === main) : all };
}

// The pick-a-code column: the planner chooses one P6 activity code and the column shows each
// critical activity's value of it. Remembered between sessions.
const CODE_KEY = 'p6evm_gantt_code';
let ganttCode = null, ganttCodeVal = '';                 // the picked activity code, and the value of it to show ('' = every value)
export function ganttCodeColumn() { return ganttCode || ''; }
// {code, value} when the planner narrowed the Gantt to one value of an activity code (Silos Area Name = Silo 3)
export function ganttCodeFilter(result) {
  const gs = ganttScope(result);
  const types = new Set(gs.all.filter((a) => a.critical).flatMap((a) => Object.keys(a.codes || {})));
  return ganttCode && ganttCodeVal && types.has(ganttCode) ? { code: ganttCode, value: ganttCodeVal } : null;
}
// Delay = the update's Total Float with P6's own sign: −72 d is 72 days late, a positive figure is spare float
const delayText = (a) => (a.delay == null ? '—' : `${a.delay} d`);
const delayCls = (a) => (a.delay == null || a.delay === 0 ? '' : (a.delay < 0 ? ' late' : ' early'));

export function renderSchedule(result) {
  onReportName(() => renderSchedule(result));     // a new report name: the report parts are rebuilt with it
  const el = document.getElementById('schedule-body');
  _print = null;
  if (!el) return;
  // Owner comment 65: the chart shows the CRITICAL REMAINING activities - everything P6 flags
  // as Critical whose work is not finished (P6's own count); completed activities are hidden.
  const gs = ganttScope(result);
  const all = gs.scope;                                    // the activities of the chosen major WBS (or all)
  const acts0 = all.filter((a) => a.critical);
  if (all.length && !acts0.length) {
    el.innerHTML = `
      <div class="ov-head"><div class="ov-title"><h2>Critical Activities (Gantt)</h2>
        <div class="ov-chips"><span class="ov-chip"><b>0</b> critical of <b>${all.length}</b> activities</span></div></div></div>
      <p class="ov-note">No remaining activity of this schedule is critical at the data date, so there is nothing to draw (completed activities are hidden).</p>`;
    return;
  }
  if (!acts0.length) {
    el.innerHTML = `
      <div class="ov-head"><div class="ov-title"><h2>Critical Activities (Gantt)</h2></div></div>
      <p class="ov-note">No activity timeline is available.${result && result.activity_count
        ? ' The schedule file of this project is no longer on this computer, so its Gantt cannot be rebuilt — import the schedule again to show it.'
        : ''}</p>
      <div class="action-buttons"><button class="btn-secondary" id="sched-excel-btn">Export to Excel</button></div>`;
    return;
  }

  // activity codes assigned to the shown activities → the choices of the code column
  const codeTypes = [...new Set(acts0.flatMap((a) => Object.keys(a.codes || {})))].sort((x, y) => x.localeCompare(y));
  if (ganttCode == null) { try { ganttCode = localStorage.getItem(CODE_KEY) || ''; } catch { ganttCode = ''; } }
  const code = codeTypes.includes(ganttCode) ? ganttCode : '';
  // the values of the picked code among the critical activities (Silo 1, Silo 2, Silo 3 ...), with their counts
  const valCount = new Map();
  if (code) for (const a of acts0) { const v = (a.codes || {})[code]; if (v) valCount.set(v, (valCount.get(v) || 0) + 1); }
  const codeVals = [...valCount.keys()].sort((x, y) => x.localeCompare(y, undefined, { numeric: true }));
  if (!code || !valCount.has(ganttCodeVal)) ganttCodeVal = '';
  const acts = ganttCodeVal ? acts0.filter((a) => (a.codes || {})[code] === ganttCodeVal) : acts0;
  const codeOf = (a) => (code ? ((a.codes || {})[code] || '—') : '');
  // column widths follow the longest text they hold, so no Activity ID / name / code is cut
  // (a longer name wraps onto a second line)
  const longest = (f) => acts.reduce((m, a) => Math.max(m, String(f(a) || '').length), 0);
  const idW = Math.min(230, Math.max(110, Math.round(longest((a) => a.id) * 7.4 + 14)));
  const nameW = Math.min(360, Math.max(190, Math.round(longest((a) => a.name) * 6.3 / 1.9 + 16)));
  const codeW = code ? Math.min(200, Math.max(110, Math.round(Math.max(longest(codeOf), code.length) * 6.4 + 14))) : 0;
  const lblCols = `${idW}px ${code ? codeW + 'px ' : ''}${nameW}px 82px 82px 60px`;
  const lblW = idW + codeW + nameW + 82 + 82 + 60 + (code ? 5 : 4) * 8 + 22;

  const { min, max, dd } = span(acts, result.data_date);
  const totalDays = Math.max(1, Math.round((max - min) / DAY));
  // the time line takes the width of the screen, so EVERY month shows with no sideways scrolling
  const trackW = Math.max(420, (el.clientWidth || 1300) - lblW - 64);
  const ppd = trackW / totalDays;
  const xOf = (ms) => ((ms - min) / DAY) * ppd;

  // month ticks + full-height gridlines (the first, partial month is labelled too)
  let ticks = '', grid = '';
  const t = new Date(min); t.setDate(1); t.setHours(0, 0, 0, 0);
  for (; t.getTime() <= max; t.setMonth(t.getMonth() + 1)) {
    const raw = xOf(t.getTime());
    if (raw > trackW + 0.5) continue;
    const x = Math.max(0, raw);
    if (raw < 0) {                                         // a first month with only a few days left: its
      const nx = new Date(t); nx.setMonth(nx.getMonth() + 1);   // label would sit under the next month's
      if (xOf(nx.getTime()) < 18) continue;
    }
    // every month by name (Jan, Feb ...); alternate rows when they would touch; the year on its own row
    const lo = ppd * 30.4 < 34 && t.getMonth() % 2 === 1;
    ticks += `<div class="g-tick" style="left:${x.toFixed(1)}px"><span${lo ? ' class="lo"' : ''}>${MON[t.getMonth()]}</span></div>`;
    if (t.getMonth() === 0 || !ticks.includes('g-yr')) ticks += `<div class="g-yr" style="left:${(x + 3).toFixed(1)}px">${t.getFullYear()}</div>`;
    if (raw >= 0) grid += `<div class="g-grid-line" style="left:calc(var(--g-lblw) + ${x.toFixed(1)}px)"></div>`;
  }
  const ddx = dd != null ? xOf(dd) : null;

  const groups = ganttGroups(acts);
  const counts = ganttCounts(acts);

  // Rows are built in blocks of GANTT_BLOCK lines; each block carries its exact height, so
  // the browser lays out only the blocks on screen (content-visibility) — a 6,000-activity
  // schedule then opens without a long freeze of the Run bar (owner comment 36).
  const blocks = [];
  let blk = '', blkH = 0, blkN = 0;
  const push = (html, h) => {
    blk += html; blkH += h; blkN++;
    if (blkN >= GANTT_BLOCK) { blocks.push(`<div class="g-blk" style="contain-intrinsic-size:auto ${blkH}px">${blk}</div>`); blk = ''; blkH = 0; blkN = 0; }
  };
  // WBS bands the way P6 lays them out: every WBS level above the critical activities, in P6's
  // order, each band carrying P6's summary of ITS critical activities — Expected Start (earliest),
  // Expected Finish (latest), Delay (= its Total Float) and the Activity Count. Built from the
  // critical-only WBS summary the server stores; a result without it keeps the plain groups.
  const tree = (result.wbs_critical || []);
  const nodeById = new Map(tree.map((n) => [n.id, n]));
  const bandModel = (list) => {
    const byWbs = new Map();
    for (const a of list) { if (!byWbs.has(a.wbs_id)) byWbs.set(a.wbs_id, []); byWbs.get(a.wbs_id).push(a); }
    const keep = new Set();                              // WBS that hold a shown activity, with their ancestors
    for (const id of byWbs.keys()) { let n = nodeById.get(id); while (n && !keep.has(n.id)) { keep.add(n.id); n = nodeById.get(n.parent); } }
    const banded = tree.length > 0 && list.every((a) => a.wbs_id && nodeById.has(a.wbs_id));
    const bands = banded ? tree.filter((n) => keep.has(n.id)) : [];
    return {
      banded, baseDepth: bands.reduce((m, n) => Math.min(m, n.depth), Infinity),
      sets: banded ? bands.map((n) => ({ band: n, rows: (byWbs.get(n.id) || []).map((a) => ({ a, sMs: toMs(a.start), fMs: toMs(a.finish) })).sort((x, y) => x.sMs - y.sMs) })) : null,
    };
  };
  const bm = bandModel(acts);
  const banded = bm.banded, baseDepth = bm.baseDepth;
  const rowSets = banded ? bm.sets : groups.map((g) => ({ group: g, rows: g.rows }));
  const bandCols = `minmax(0,1fr) 82px 82px 60px`;
  for (const set of rowSets) {
    if (set.band) {
      const n = set.band, d = n.depth - baseDepth;
      const bs = toMs(n.start), bf = toMs(n.finish);
      const dl = { delay: n.delay };
      const bbar = (!Number.isNaN(bs) && !Number.isNaN(bf)) ? `<div class="g-band-bar" style="left:${xOf(bs).toFixed(1)}px;width:${Math.max(3, xOf(bf) - xOf(bs)).toFixed(1)}px"></div>` : '';
      push(`<div class="g-grp g-band"><div class="g-lbl g-grp-lbl" style="--g-bandcols:${bandCols}" title="${attr(n.name)} — ${n.count} critical activities · Total Float ${n.total_float == null ? '—' : n.total_float + ' d'}">`
        + `<span style="padding-left:${d * 14}px">${escapeHtml(n.name)}${stTag(n.status)}</span><i>${dA(n.start, n.start_actual)}</i><i>${dA(n.finish, n.finish_actual)}</i><i class="g-delay${delayCls(dl)}">${delayText(dl)}</i></div>`
        + `<div class="g-track">${bbar}</div></div>`, GRP_H);
    } else {
      const g = set.group;
      push(`<div class="g-grp"><div class="g-lbl g-grp-lbl" style="grid-template-columns:minmax(0,1fr) auto" title="${attr(g.name)}"><span>${escapeHtml(g.name)}</span><em>${g.rows.length}</em></div><div class="g-track"></div></div>`, GRP_H);
    }
    for (const { a, sMs, fMs } of set.rows) {
      const left = xOf(sMs);
      const w = Math.max(3, xOf(fMs) - left);
      const tt = attr(tip(a));
      const lbl = `<div class="g-lbl" title="${tt}"><b class="g-id">${escapeHtml(a.id)}</b>${code ? `<span class="g-code">${escapeHtml(codeOf(a))}</span>` : ''}`
        + `<div class="g-nm"><span>${escapeHtml(a.name)}${stTag(a.status)}</span></div>`
        + `<i>${dA(a.start, a.start_actual)}</i><i>${dA(a.finish, a.finish_actual)}</i><i class="g-delay${delayCls(a)}">${delayText(a)}</i></div>`;
      const bar = a.milestone
        ? `<div class="g-ms${a.critical ? ' crit' : ''}" style="left:${Math.max(0, left - 6).toFixed(1)}px" title="${tt}"></div>`
        : `<div class="g-bar${a.critical ? ' crit' : ''}" style="left:${left.toFixed(1)}px;width:${w.toFixed(1)}px" title="${tt}">
             <span class="g-fill" style="width:${Math.max(0, Math.min(100, a.pct))}%"></span></div>
           <span class="g-plabel" style="left:${(left + w + 6).toFixed(1)}px" title="Actual % complete">${a.pct}% actual</span>`;
      push(`<div class="g-row">${lbl}<div class="g-track">${bar}</div></div>`, ROW_H);
    }
  }
  if (blkN) blocks.push(`<div class="g-blk" style="contain-intrinsic-size:auto ${blkH}px">${blk}</div>`);
  const rows = blocks.join('');

  const note = 'This shows the CRITICAL REMAINING activities only — every activity P6 flags as Critical whose work is not finished; completed activities are hidden. Bars run from each activity’s Expected Start to its Expected Finish, as P6 shows them: actual dates where the work has started, the remaining early dates for the rest. Delay is the Total Float on this update, with the same sign as in P6: −72 d means 72 days late (it is not a comparison with the baseline). Each WBS band shows P6’s summary of its critical activities: earliest Expected Start, latest Expected Finish, the band’s own Total Float as Delay, and its status (Completed / In Progress / Not Started). The red bar is the remaining work and its dark-red part is the Actual % complete (the figure beside the bar); the black bar on a WBS line is that WBS’s span; diamonds are milestones; the dashed vertical line is the cut-off date (data date). Grouped by WBS in P6’s own order.';

  const valPick = code && codeVals.length
    ? `<label class="g-codepick">Show only <select id="g-codeval"><option value="">All ${escapeHtml(code)} (${acts0.length})</option>${codeVals.map((v) =>
        `<option value="${attr(v)}"${v === ganttCodeVal ? ' selected' : ''}>${escapeHtml(v)} (${valCount.get(v)})</option>`).join('')}</select></label>`
    : '';
  const codePick = codeTypes.length
    ? `<label class="g-codepick">Activity code column <select id="g-code">
        <option value="">— none —</option>${codeTypes.map((c) => `<option value="${attr(c)}"${c === code ? ' selected' : ''}>${escapeHtml(c)}</option>`).join('')}</select></label>`
    : '';

  const mainPick = gs.roots.length > 1
    ? `<div class="wbst-mainsel"><span>Critical activities of</span><div class="wbst-seg" id="g-mainseg">
        <button data-gm="" class="${gs.main === '' ? 'on' : ''}">All major WBS (${gs.all.filter((a) => a.critical).length})</button>${gs.roots.map((r) =>
          `<button data-gm="${attr(r.id)}" class="${r.id === gs.main ? 'on' : ''}">${escapeHtml(r.name)} (${r.n})</button>`).join('')}</div></div>`
    : '';

  el.innerHTML = `
    <div class="ov-head"><div class="ov-title"><h2>Critical Activities (Gantt)</h2>
      ${reportNameField()}
      <div class="ov-chips">
        <span class="ov-chip"><b>${counts.crit}</b> critical remaining activities of <b>${all.length}</b> · completed activities hidden</span>
        <span class="ov-chip"><b>A</b> beside a date = Actual date</span>
        <span class="ov-chip"><b>${counts.ms}</b> critical milestones</span>
        <span class="ov-chip">cut-off date <b>${gDate(result.data_date)}</b></span>
        <span class="ov-chip"><i class="g-key crit"></i>critical &nbsp;<i class="g-key ms"></i>milestone</span>
        ${codePick}${valPick}
      </div></div></div>
    <div class="g-banner"><b>CRITICAL REMAINING ACTIVITIES ONLY</b> — every activity P6 flags as Critical whose work is not finished; completed activities are hidden.</div>
    <p class="ov-note g-note">${note}</p>
    ${mainPick}
    <div class="g-wrap" style="--g-lblw:${lblW}px;--g-cols:${lblCols}"><div class="g-inner g-lazy" style="--trackw:${trackW}px">
      <div class="g-scale"><div class="g-lbl g-scale-lbl"><span>Activity ID</span>${code ? `<span>${escapeHtml(code)}</span>` : ''}<span>Activity name</span><i>Expected Start</i><i>Expected Finish</i><i>Delay</i></div>
        <div class="g-track g-scale-track">${ticks}${ddx != null ? `<div class="g-dd" style="left:${ddx.toFixed(1)}px"><span>Cut-off ${gShort(result.data_date)}</span></div>` : ''}</div></div>
      <div class="g-grids">${grid}${ddx != null ? `<div class="g-dd-line" style="left:calc(var(--g-lblw) + ${ddx.toFixed(1)}px)"></div>` : ''}</div>
      <div class="g-rows">${rows}</div>
    </div></div>
    <div class="action-buttons">
      <button class="btn-secondary" id="sched-print-btn">Print / PDF / Word</button>
      <button class="btn-secondary" id="sched-excel-btn">Export to Excel</button>
    </div>`;

  const allCrit = gs.all.filter((a) => a.critical && (!ganttCodeVal || (a.codes || {})[code] === ganttCodeVal));
  const printRoots = tree.length ? gs.roots.map((r) => {
    const list = allCrit.filter((a) => gs.rootOf(a.wbs_id) === r.id);
    return { id: r.id, name: r.name, n: list.length, model: bandModel(list) };
  }).filter((r) => r.model.banded) : [];
  const spAll = span(allCrit, result.data_date);
  _print = printSections(result, allCrit, ganttGroups(allCrit), ganttCounts(allCrit), spAll, note, code, null, 0, gs.all, { ...gs, main: '' }, printRoots);
  const valSel = document.getElementById('g-codeval');
  if (valSel) valSel.addEventListener('change', () => { ganttCodeVal = valSel.value; renderSchedule(result); });
  const segG = document.getElementById('g-mainseg');
  if (segG) segG.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-gm]');
    if (!b || b.dataset.gm === gs.main) return;
    ganttMain = b.dataset.gm;
    renderSchedule(result);
  });

  const sel = document.getElementById('g-code');
  if (sel) sel.addEventListener('change', () => {
    ganttCode = sel.value; ganttCodeVal = '';
    try { localStorage.setItem(CODE_KEY, ganttCode); } catch { /* non-fatal */ }
    renderSchedule(result);
  });
}

// ── File ▸ Print / PDF / Word / HTML — the same rows as the screen, laid out for a page ──
// One 'Summary' section and one 'Gantt chart' section whose parts are the WBS groups (each a
// table: ID, name, Start, Finish, %, float and the bar on a page-wide time scale), so the
// Report Contents picker can tick whole groups in or out.
function printSections(result, acts, groups, counts, sp, note, code, bandSets, baseDepth, scope, gs, printRoots) {
  const total = Math.max(1, sp.max - sp.min);
  const pos = (ms) => Math.max(0, Math.min(100, ((ms - sp.min) / total) * 100));
  // month / quarter / year marks for the page-wide scale
  let scale = '';
  scale = monthScaleHtml(sp.min, sp.max, pos);       // EVERY month, written out (Jan, Feb, ...)
  const ddLine = sp.dd != null ? `<u style="left:${pos(sp.dd).toFixed(2)}%"></u>` : '';
  // every column has its own width, so adding / removing the code column never squeezes a name
  const cg = `<colgroup><col style="width:${code ? 12 : 13}%">${code ? '<col style="width:11%">' : ''}<col style="width:${code ? 21 : 25}%"><col style="width:7.5%"><col style="width:7.5%"><col style="width:5.5%"><col style="width:5.5%"><col></colgroup>`;
  const head = `${cg}<thead><tr><th>Activity ID</th>${code ? `<th>${escapeHtml(code)}</th>` : ''}<th>Activity name</th><th>Expected Start</th><th>Expected Finish</th><th class="gp-n">Delay</th><th class="gp-n">Actual %</th>`
    + `<th class="gp-tl" data-export="bar"><div class="gp-scale gp-scale-m">${scale}</div></th></tr></thead>`;

  const rowHtml = ({ a, sMs, fMs }) => {
    const l = pos(sMs), w = Math.max(0.6, pos(fMs) - l);
    const bar = a.milestone
      ? `<b class="gp-ms${a.critical ? ' crit' : ''}" style="left:${l.toFixed(2)}%"></b>`
      : `<b class="gp-bar${a.critical ? ' crit' : ''}" style="left:${l.toFixed(2)}%;width:${Math.min(w, 100 - l).toFixed(2)}%"><s style="width:${Math.max(0, Math.min(100, a.pct))}%"></s></b>`;
    return `<tr${a.critical ? ' class="gp-crit"' : ''}><td class="gp-id">${escapeHtml(a.id)}${a.milestone ? ' ◆' : ''}</td>${code ? `<td>${escapeHtml((a.codes || {})[code] || '—')}</td>` : ''}<td>${escapeHtml(a.name)} <small class="gp-st ${stCls(a.status)}">${escapeHtml(a.status || '')}</small></td>`
      + `<td class="gp-d">${dA(a.start, a.start_actual)}</td><td class="gp-d">${dA(a.finish, a.finish_actual)}</td><td class="gp-n">${delayText(a)}</td><td class="gp-n">${a.pct}</td>`
      + `<td class="gp-tl" data-export="bar"><div class="gp-track">${ddLine}${bar}</div></td></tr>`;
  };

  // a WBS band line inside the table: P6's summary of the critical activities under that WBS
  const bandHtml = (n, base = baseDepth) => {
    const d = n.depth - base, bs = toMs(n.start), bf = toMs(n.finish);
    const l = pos(bs), w = Math.max(0.6, pos(bf) - l);
    const bar = (Number.isNaN(bs) || Number.isNaN(bf)) ? '' : `<b class="gp-band" style="left:${l.toFixed(2)}%;width:${Math.min(w, 100 - l).toFixed(2)}%"></b>`;
    return `<tr class="gp-bandrow"><td colspan="${code ? 3 : 2}" style="padding-left:${5 + d * 10}px">${escapeHtml(n.name)} <small class="gp-st ${stCls(n.status)}">${escapeHtml(n.status || '')}</small></td>`
      + `<td class="gp-d">${dA(n.start, n.start_actual)}</td><td class="gp-d">${dA(n.finish, n.finish_actual)}</td><td class="gp-n">${delayText({ delay: n.delay })}</td><td></td>`
      + `<td class="gp-tl" data-export="bar"><div class="gp-track">${ddLine}${bar}</div></td></tr>`;
  };
  // banded (P6 layout): one part per top band, its sub-bands and activities in P6's order
  const bandParts = [];
  if (bandSets) {
    let cur = null;
    for (const set of bandSets) {
      if (set.band.depth === baseDepth || !cur) { cur = { n: set.band, html: '' }; bandParts.push(cur); }
      cur.html += bandHtml(set.band) + set.rows.map(rowHtml).join('');
    }
  }
  const parts = bandSets ? bandParts.map((bp) => `<div data-part="gantt.${attr(bp.n.id)}" data-part-label="${attr(bp.n.name)}" class="gp-grp">
      <h3 class="gp-h">${escapeHtml(bp.n.name)} <small class="gp-st ${stCls(bp.n.status)}">${escapeHtml(bp.n.status || '')}</small></h3>
      <table class="gp-table">${head}<tbody>${bp.html}</tbody></table></div>`).join('') : groups.map((g) => {
    const c = ganttCounts(g.rows.map((r) => r.a));
    return `<div data-part="gantt.${attr(g.key)}" data-part-label="${attr(g.name)}" class="gp-grp">
      <h3 class="gp-h">${escapeHtml(g.name)} <small>${c.total} activit${c.total === 1 ? 'y' : 'ies'} · ${c.crit} critical</small></h3>
      <table class="gp-table">${head}<tbody>${g.rows.map(rowHtml).join('')}</tbody></table></div>`;
  }).join('');

  const kv = (k, v) => `<tr><td>${k}</td><td><b>${v}</b></td></tr>`;
  const whole = scope || result.activities || [];
  const wc = (st) => whole.filter((a) => a.status === st).length;
  const cf = criticalFigures(result, acts, whole);
  const summary = `<div data-part="summary.counts" data-part-label="Schedule counts">
      <table class="gp-table gp-sum"><thead><tr><th>Item</th><th>Value</th></tr></thead><tbody>
      ${kv('Project', escapeHtml(result.project_name || 'Schedule'))}
      ${ganttCodeVal ? kv('Shown only', `${escapeHtml(code)} = ${escapeHtml(ganttCodeVal)}`) : ''}
      ${kv('Cut-off date (data date)', gDate(result.data_date))}
      ${kv(gs && gs.main ? 'Activities in this WBS' : 'Activities in the schedule', whole.length || (result.activity_count ?? '—'))}
      ${kv(gs && gs.main ? 'Completed (this WBS)' : 'Completed (whole schedule)', wc('Completed'))}
      ${kv(gs && gs.main ? 'In progress (this WBS)' : 'In progress (whole schedule)', wc('In Progress'))}
      ${kv(gs && gs.main ? 'Not started (this WBS)' : 'Not started (whole schedule)', wc('Not Started'))}
      ${kv('Critical activities shown (as P6 flags them) — remaining only, completed activities are hidden', cf.n)}
      ${kv('Critical activities in progress / not started', `${cf.prog} / ${cf.notStarted}`)}
      ${kv('Current % of the critical activities', `${f1(cf.share)} (${cf.n} of ${cf.all} activities)`)}
      ${kv('A beside a date', 'Actual date (the work has started / finished on that date)')}
      ${kv('Critical milestones', counts.ms)}
      </tbody></table></div>
    <div data-part="summary.note" data-part-label="How to read the chart"><p class="ov-note">${note} A ◆ after the Activity ID marks a milestone; <b>A</b> beside a date = <b>Actual</b> date (a date without A is an expected date); Delay is the total float as P6 shows it (negative = late). The dashed line is the cut-off date ${gDate(result.data_date)}.</p></div>`;

  // one section per MAJOR WBS (Phase I Construction Works, Phase I Key Dates ...): the Report Contents
  // picker lists each of them, so any can be ticked in or out
  if (printRoots && printRoots.length) {
    return [
      { key: 'summary', label: 'Summary', html: summary },
      ...printRoots.map((r) => ({
        key: `gantt.${r.id}`, label: `${r.name} (${r.n} critical)`,
        html: `<div data-part="gantt.${attr(r.id)}" data-part-label="${attr(r.name)}" class="gp-grp"><p class="gp-banner"><b>Critical remaining activities only</b> — completed activities are hidden.</p><h3 class="gp-h">${escapeHtml(r.name)} <small>${r.n} critical remaining activities</small></h3>`
          + `<table class="gp-table">${head}<tbody>${r.model.sets.map((set) => bandHtml(set.band, r.model.baseDepth) + set.rows.map(rowHtml).join('')).join('')}</tbody></table></div>`,
      })),
    ];
  }
  return [
    { key: 'summary', label: 'Summary', html: summary },
    { key: 'gantt', label: 'Gantt chart by WBS', html: parts },
  ];
}
