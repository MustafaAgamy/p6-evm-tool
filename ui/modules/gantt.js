// Project ▸ Schedule (Gantt). Renders a time-scaled bar chart from the slim activity list
// stored with the snapshot (result.activities — present after an import AND after re-opening
// from Recent Projects). Bars use the CURRENT schedule dates (actual where the work has
// started / finished, remaining early dates otherwise — P6's Start / Finish columns) with %
// complete, critical highlighting, month gridlines and a data-date line, grouped by top-level
// WBS. schedulePrint() hands the same rows to File ▸ Print / PDF / Word / HTML.
import { escapeHtml, dateText } from './format.js';

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
  return { min, max, dd: ddOk ? dd : null };
}

const tip = (a) => `${a.id} — ${a.name}\nStart ${gDate(a.start)} → Finish ${gDate(a.finish)}`
  + `\n${a.status || ''}${a.status ? ' · ' : ''}Actual ${a.pct}% complete · Total float ${tfText(a)}${a.critical ? ' · Critical' : ''}`
  + (a.wbs ? `\nWBS: ${a.wbs}` : '');

let _print = null;
export function schedulePrint() { return _print; }

// The pick-a-code column: the planner chooses one P6 activity code and the column shows each
// critical activity's value of it. Remembered between sessions.
const CODE_KEY = 'p6evm_gantt_code';
let ganttCode = null;
export function ganttCodeColumn() { return ganttCode || ''; }
// Delay = the update's Total Float with P6's own sign: −72 d is 72 days late, a positive figure is spare float
const delayText = (a) => (a.delay == null ? '—' : `${a.delay} d`);
const delayCls = (a) => (a.delay == null || a.delay === 0 ? '' : (a.delay < 0 ? ' late' : ' early'));

export function renderSchedule(result) {
  const el = document.getElementById('schedule-body');
  _print = null;
  if (!el) return;
  // Owner comment 65: the chart shows the CRITICAL activities only (P6's own Critical flag),
  // and only those of the CONSTRUCTION works (the WBS branches that hold cost-loaded work).
  const all = (result && result.activities) || [];
  const acts = all.filter((a) => a.critical && a.construction !== false);
  if (all.length && !acts.length) {
    el.innerHTML = `
      <div class="ov-head"><div class="ov-title"><h2>Schedule Gantt (Critical activities)</h2>
        <div class="ov-chips"><span class="ov-chip"><b>0</b> critical of <b>${all.length}</b> activities</span></div></div></div>
      <p class="ov-note">No construction activity of this schedule is critical at the data date, so there is nothing to draw.</p>`;
    return;
  }
  if (!acts.length) {
    el.innerHTML = `
      <div class="ov-head"><div class="ov-title"><h2>Schedule (Gantt)</h2></div></div>
      <p class="ov-note">No activity timeline is available.${result && result.activity_count
        ? ' The schedule file of this project is no longer on this computer, so its Gantt cannot be rebuilt — import the schedule again to show it.'
        : ''}</p>
      <div class="action-buttons"><button class="btn-secondary" id="sched-excel-btn">Export to Excel</button></div>`;
    return;
  }

  const { min, max, dd } = span(acts, result.data_date);
  const totalDays = Math.max(1, Math.round((max - min) / DAY));
  const trackW = Math.max(720, Math.min(Math.round(totalDays * 4), 4400));
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
      if (xOf(nx.getTime()) < 46) continue;
    }
    const lbl = `${MON[t.getMonth()]} ${String(t.getFullYear()).slice(2)}`;
    ticks += `<div class="g-tick" style="left:${x.toFixed(1)}px"><span>${lbl}</span></div>`;
    if (raw >= 0) grid += `<div class="g-grid-line" style="left:calc(var(--g-lblw) + ${x.toFixed(1)}px)"></div>`;
  }
  const ddx = dd != null ? xOf(dd) : null;

  const groups = ganttGroups(acts);
  const counts = ganttCounts(acts);

  // activity codes assigned to the shown activities → the choices of the code column
  const codeTypes = [...new Set(acts.flatMap((a) => Object.keys(a.codes || {})))].sort((x, y) => x.localeCompare(y));
  if (ganttCode == null) { try { ganttCode = localStorage.getItem(CODE_KEY) || ''; } catch { ganttCode = ''; } }
  const code = codeTypes.includes(ganttCode) ? ganttCode : '';
  const codeOf = (a) => (code ? ((a.codes || {})[code] || '—') : '');
  // column widths follow the longest text they hold, so no Activity ID / name / code is cut
  // (a longer name wraps onto a second line)
  const longest = (f) => acts.reduce((m, a) => Math.max(m, String(f(a) || '').length), 0);
  const idW = Math.min(230, Math.max(110, Math.round(longest((a) => a.id) * 7.4 + 14)));
  const nameW = Math.min(360, Math.max(190, Math.round(longest((a) => a.name) * 6.3 / 1.9 + 16)));
  const codeW = code ? Math.min(200, Math.max(110, Math.round(Math.max(longest(codeOf), code.length) * 6.4 + 14))) : 0;
  const lblCols = `${idW}px ${code ? codeW + 'px ' : ''}${nameW}px 82px 82px 60px`;
  const lblW = idW + codeW + nameW + 82 + 82 + 60 + (code ? 5 : 4) * 8 + 22;

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
  const byWbs = new Map();
  for (const a of acts) { if (!byWbs.has(a.wbs_id)) byWbs.set(a.wbs_id, []); byWbs.get(a.wbs_id).push(a); }
  const nodeById = new Map(tree.map((n) => [n.id, n]));
  const keep = new Set();                              // WBS that hold a shown activity, with their ancestors
  for (const id of byWbs.keys()) { let n = nodeById.get(id); while (n && !keep.has(n.id)) { keep.add(n.id); n = nodeById.get(n.parent); } }
  const banded = tree.length > 0 && acts.every((a) => a.wbs_id && nodeById.has(a.wbs_id));
  const bands = banded ? tree.filter((n) => keep.has(n.id)) : [];
  const baseDepth = bands.reduce((m, n) => Math.min(m, n.depth), Infinity);
  const rowSets = banded
    ? bands.map((n) => ({ band: n, rows: (byWbs.get(n.id) || []).map((a) => ({ a, sMs: toMs(a.start), fMs: toMs(a.finish) })).sort((x, y) => x.sMs - y.sMs) }))
    : groups.map((g) => ({ group: g, rows: g.rows }));
  const bandCols = `minmax(0,1fr) 82px 82px 60px`;
  for (const set of rowSets) {
    if (set.band) {
      const n = set.band, d = n.depth - baseDepth;
      const bs = toMs(n.start), bf = toMs(n.finish);
      const dl = { delay: n.delay };
      const bbar = (!Number.isNaN(bs) && !Number.isNaN(bf)) ? `<div class="g-band-bar" style="left:${xOf(bs).toFixed(1)}px;width:${Math.max(3, xOf(bf) - xOf(bs)).toFixed(1)}px"></div>` : '';
      push(`<div class="g-grp g-band"><div class="g-lbl g-grp-lbl" style="--g-bandcols:${bandCols}" title="${attr(n.name)} — ${n.count} critical activities · Total Float ${n.total_float == null ? '—' : n.total_float + ' d'}">`
        + `<span style="padding-left:${d * 14}px">${escapeHtml(n.name)} <em>${n.count}</em></span><i>${gShort(n.start)}</i><i>${gShort(n.finish)}</i><i class="g-delay${delayCls(dl)}">${delayText(dl)}</i></div>`
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
        + `<div class="g-nm"><span>${escapeHtml(a.name)}</span></div>`
        + `<i>${gShort(a.start)}</i><i>${gShort(a.finish)}</i><i class="g-delay${delayCls(a)}">${delayText(a)}</i></div>`;
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

  const note = 'Only the critical activities of the construction works are shown — the activities P6 flags as Critical (work not finished) in the WBS that holds the cost-loaded work. Bars run from each activity’s Expected Start to its Expected Finish, as P6 shows them: actual dates where the work has started, the remaining early dates for the rest. Delay is the Total Float on this update, with the same sign as in P6: −72 d means 72 days late (it is not a comparison with the baseline). Each WBS band shows P6’s summary of its critical activities: earliest Expected Start, latest Expected Finish, the band’s own Total Float as Delay, and the number of critical activities. The red bar is the remaining work and its dark-red part is the Actual % complete (the figure beside the bar); the black bar on a WBS line is that WBS’s span; diamonds are milestones; the vertical line is the data date. Grouped by WBS in P6’s own order.';

  const codePick = codeTypes.length
    ? `<label class="g-codepick">Activity code column <select id="g-code">
        <option value="">— none —</option>${codeTypes.map((c) => `<option value="${attr(c)}"${c === code ? ' selected' : ''}>${escapeHtml(c)}</option>`).join('')}</select></label>`
    : '';

  el.innerHTML = `
    <div class="ov-head"><div class="ov-title"><h2>Schedule Gantt (Critical activities)</h2>
      <div class="ov-chips">
        <span class="ov-chip"><b>${counts.crit}</b> critical construction activities of <b>${all.length}</b> activities</span>
        <span class="ov-chip"><b>${counts.ms}</b> critical milestones</span>
        <span class="ov-chip">data date <b>${gDate(result.data_date)}</b></span>
        <span class="ov-chip"><i class="g-key crit"></i>critical &nbsp;<i class="g-key ms"></i>milestone</span>
        ${codePick}
      </div></div></div>
    <div class="g-wrap" style="--g-lblw:${lblW}px;--g-cols:${lblCols}"><div class="g-inner g-lazy" style="--trackw:${trackW}px">
      <div class="g-scale"><div class="g-lbl g-scale-lbl"><span>Activity ID</span>${code ? `<span>${escapeHtml(code)}</span>` : ''}<span>Activity name</span><i>Expected Start</i><i>Expected Finish</i><i>Delay</i></div>
        <div class="g-track g-scale-track">${ticks}${ddx != null ? `<div class="g-dd" style="left:${ddx.toFixed(1)}px"><span>data date</span></div>` : ''}</div></div>
      <div class="g-grids">${grid}${ddx != null ? `<div class="g-dd-line" style="left:calc(var(--g-lblw) + ${ddx.toFixed(1)}px)"></div>` : ''}</div>
      <div class="g-rows">${rows}</div>
    </div></div>
    <p class="ov-note">${note}</p>
    <div class="action-buttons">
      <button class="btn-secondary" id="sched-print-btn">Print / PDF / Word</button>
      <button class="btn-secondary" id="sched-excel-btn">Export to Excel</button>
    </div>`;

  _print = printSections(result, acts, groups, counts, { min, max, dd }, note, code, banded ? rowSets : null, baseDepth);

  const sel = document.getElementById('g-code');
  if (sel) sel.addEventListener('change', () => {
    ganttCode = sel.value;
    try { localStorage.setItem(CODE_KEY, ganttCode); } catch { /* non-fatal */ }
    renderSchedule(result);
  });
}

// ── File ▸ Print / PDF / Word / HTML — the same rows as the screen, laid out for a page ──
// One 'Summary' section and one 'Gantt chart' section whose parts are the WBS groups (each a
// table: ID, name, Start, Finish, %, float and the bar on a page-wide time scale), so the
// Report Contents picker can tick whole groups in or out.
function printSections(result, acts, groups, counts, sp, note, code, bandSets, baseDepth) {
  const total = Math.max(1, sp.max - sp.min);
  const pos = (ms) => Math.max(0, Math.min(100, ((ms - sp.min) / total) * 100));
  // month / quarter / year marks for the page-wide scale
  let scale = '';
  const months = Math.max(1, Math.round(total / DAY / 30.4));
  const step = [1, 2, 3, 6, 12, 24, 60].find((n) => months / n <= 4) || 120;      // at most ~4 labels: the column is narrow
  const t = new Date(sp.min); t.setDate(1); t.setHours(0, 0, 0, 0);
  t.setMonth(Math.ceil(t.getMonth() / step) * step);
  for (; t.getTime() <= sp.max; t.setMonth(t.getMonth() + step)) {
    if (t.getTime() < sp.min) continue;
    const p = pos(t.getTime());
    if (p > 82) continue;
    scale += `<span style="left:${p.toFixed(2)}%">${MON[t.getMonth()]} ${String(t.getFullYear()).slice(2)}</span>`;
  }
  const ddLine = sp.dd != null ? `<u style="left:${pos(sp.dd).toFixed(2)}%"></u>` : '';
  // every column has its own width, so adding / removing the code column never squeezes a name
  const cg = `<colgroup><col style="width:${code ? 12 : 13}%">${code ? '<col style="width:11%">' : ''}<col style="width:${code ? 21 : 25}%"><col style="width:7.5%"><col style="width:7.5%"><col style="width:5.5%"><col style="width:5.5%"><col></colgroup>`;
  const head = `${cg}<thead><tr><th>Activity ID</th>${code ? `<th>${escapeHtml(code)}</th>` : ''}<th>Activity name</th><th>Expected Start</th><th>Expected Finish</th><th class="gp-n">Delay</th><th class="gp-n">Actual %</th>`
    + `<th class="gp-tl" data-export="bar"><div class="gp-scale">${scale}</div></th></tr></thead>`;

  const rowHtml = ({ a, sMs, fMs }) => {
    const l = pos(sMs), w = Math.max(0.6, pos(fMs) - l);
    const bar = a.milestone
      ? `<b class="gp-ms${a.critical ? ' crit' : ''}" style="left:${l.toFixed(2)}%"></b>`
      : `<b class="gp-bar${a.critical ? ' crit' : ''}" style="left:${l.toFixed(2)}%;width:${Math.min(w, 100 - l).toFixed(2)}%"><s style="width:${Math.max(0, Math.min(100, a.pct))}%"></s></b>`;
    return `<tr${a.critical ? ' class="gp-crit"' : ''}><td class="gp-id">${escapeHtml(a.id)}${a.milestone ? ' ◆' : ''}</td>${code ? `<td>${escapeHtml((a.codes || {})[code] || '—')}</td>` : ''}<td>${escapeHtml(a.name)}</td>`
      + `<td class="gp-d">${gShort(a.start)}</td><td class="gp-d">${gShort(a.finish)}</td><td class="gp-n">${delayText(a)}</td><td class="gp-n">${a.pct}</td>`
      + `<td class="gp-tl" data-export="bar"><div class="gp-track">${ddLine}${bar}</div></td></tr>`;
  };

  // a WBS band line inside the table: P6's summary of the critical activities under that WBS
  const bandHtml = (n) => {
    const d = n.depth - baseDepth, bs = toMs(n.start), bf = toMs(n.finish);
    const l = pos(bs), w = Math.max(0.6, pos(bf) - l);
    const bar = (Number.isNaN(bs) || Number.isNaN(bf)) ? '' : `<b class="gp-band" style="left:${l.toFixed(2)}%;width:${Math.min(w, 100 - l).toFixed(2)}%"></b>`;
    return `<tr class="gp-bandrow"><td colspan="${code ? 3 : 2}" style="padding-left:${5 + d * 10}px">${escapeHtml(n.name)} <small>${n.count}</small></td>`
      + `<td class="gp-d">${gShort(n.start)}</td><td class="gp-d">${gShort(n.finish)}</td><td class="gp-n">${delayText({ delay: n.delay })}</td><td></td>`
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
      <h3 class="gp-h">${escapeHtml(bp.n.name)} <small>${bp.n.count} critical activit${bp.n.count === 1 ? 'y' : 'ies'}</small></h3>
      <table class="gp-table">${head}<tbody>${bp.html}</tbody></table></div>`).join('') : groups.map((g) => {
    const c = ganttCounts(g.rows.map((r) => r.a));
    return `<div data-part="gantt.${attr(g.key)}" data-part-label="${attr(g.name)}" class="gp-grp">
      <h3 class="gp-h">${escapeHtml(g.name)} <small>${c.total} activit${c.total === 1 ? 'y' : 'ies'} · ${c.crit} critical</small></h3>
      <table class="gp-table">${head}<tbody>${g.rows.map(rowHtml).join('')}</tbody></table></div>`;
  }).join('');

  const kv = (k, v) => `<tr><td>${k}</td><td><b>${v}</b></td></tr>`;
  const summary = `<div data-part="summary.counts" data-part-label="Schedule counts">
      <table class="gp-table gp-sum"><thead><tr><th>Item</th><th>Value</th></tr></thead><tbody>
      ${kv('Project', escapeHtml(result.project_name || 'Schedule'))}
      ${kv('Data date', gDate(result.data_date))}
      ${kv('Critical construction activities shown (as P6 flags them, not finished)', counts.crit)}
      ${kv('Activities in the schedule', result.activity_count ?? '—')}
      ${kv('In progress', counts.prog)}${kv('Not started', counts.notStarted)}
      ${kv('Critical milestones', counts.ms)}
      ${kv('WBS groups', groups.length)}
      ${kv('Earliest start', gDate(acts.reduce((m, a) => (a.start < m ? a.start : m), acts[0].start)))}
      ${kv('Latest finish', gDate(acts.reduce((m, a) => (a.finish > m ? a.finish : m), acts[0].finish)))}
      </tbody></table></div>
    <div data-part="summary.note" data-part-label="How to read the chart"><p class="ov-note">${note} A ◆ after the Activity ID marks a milestone; Delay is the total float as P6 shows it (negative = late).</p></div>`;

  return [
    { key: 'summary', label: 'Summary', html: summary },
    { key: 'gantt', label: 'Gantt chart by WBS', html: parts },
  ];
}
