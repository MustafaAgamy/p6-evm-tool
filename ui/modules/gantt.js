// Project ▸ Schedule (Gantt). Renders a time-scaled bar chart from the slim activity list
// stored with the snapshot (result.activities — present after an import AND after re-opening
// from Recent Projects). Bars use the CURRENT schedule dates (actual where the work has
// started / finished, remaining early dates otherwise — P6's Start / Finish columns) with %
// complete, critical highlighting, month gridlines and a data-date line, grouped by top-level
// WBS. schedulePrint() hands the same rows to File ▸ Print / PDF / Word / HTML.
import { escapeHtml, dateText } from './format.js';

const DAY = 86400000;
const ROW_H = 30, GRP_H = 26;   // = .g-row / .g-grp heights in style.css (border-box)
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
  + `\n${a.status || ''}${a.status ? ' · ' : ''}${a.pct}% complete · Total float ${tfText(a)}${a.critical ? ' · Critical' : ''}`
  + (a.wbs ? `\nWBS: ${a.wbs}` : '');

let _print = null;
export function schedulePrint() { return _print; }

export function renderSchedule(result) {
  const el = document.getElementById('schedule-body');
  _print = null;
  if (!el) return;
  const acts = (result && result.activities) || [];
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

  // Rows are built in blocks of GANTT_BLOCK lines; each block carries its exact height, so
  // the browser lays out only the blocks on screen (content-visibility) — a 6,000-activity
  // schedule then opens without a long freeze of the Run bar (owner comment 36).
  const blocks = [];
  let blk = '', blkH = 0, blkN = 0;
  const push = (html, h) => {
    blk += html; blkH += h; blkN++;
    if (blkN >= GANTT_BLOCK) { blocks.push(`<div class="g-blk" style="contain-intrinsic-size:auto ${blkH}px">${blk}</div>`); blk = ''; blkH = 0; blkN = 0; }
  };
  for (const g of groups) {
    push(`<div class="g-grp"><div class="g-lbl g-grp-lbl" title="${attr(g.name)}"><span>${escapeHtml(g.name)}</span><em>${g.rows.length}</em></div><div class="g-track"></div></div>`, GRP_H);
    for (const { a, sMs, fMs } of g.rows) {
      const left = xOf(sMs);
      const w = Math.max(3, xOf(fMs) - left);
      const tt = attr(tip(a));
      const lbl = `<div class="g-lbl" title="${tt}"><div class="g-nm"><b>${escapeHtml(a.id)}</b><span>${escapeHtml(a.name)}</span></div>`
        + `<i>${gShort(a.start)}</i><i>${gShort(a.finish)}</i></div>`;
      const bar = a.milestone
        ? `<div class="g-ms${a.critical ? ' crit' : ''}" style="left:${Math.max(0, left - 6).toFixed(1)}px" title="${tt}"></div>`
        : `<div class="g-bar${a.critical ? ' crit' : ''}" style="left:${left.toFixed(1)}px;width:${w.toFixed(1)}px" title="${tt}">
             <span class="g-fill" style="width:${Math.max(0, Math.min(100, a.pct))}%"></span></div>
           <span class="g-plabel" style="left:${(left + w + 6).toFixed(1)}px">${a.pct}%</span>`;
      push(`<div class="g-row">${lbl}<div class="g-track">${bar}</div></div>`, ROW_H);
    }
  }
  if (blkN) blocks.push(`<div class="g-blk" style="contain-intrinsic-size:auto ${blkH}px">${blk}</div>`);
  const rows = blocks.join('');

  const note = 'Bars run from each activity’s current Start to its current Finish, as P6 shows them: actual dates where the work has started or finished, the remaining early dates for the rest. The darker fill is % complete. Red = critical (total float of zero or less, work not finished); diamonds are milestones; the vertical line is the data date. Grouped by top-level WBS, earliest first.';

  el.innerHTML = `
    <div class="ov-head"><div class="ov-title"><h2>Schedule (Gantt)</h2>
      <div class="ov-chips">
        <span class="ov-chip"><b>${counts.total}</b> activities</span>
        <span class="ov-chip"><b>${counts.crit}</b> critical</span>
        <span class="ov-chip"><b>${counts.ms}</b> milestones</span>
        <span class="ov-chip">data date <b>${gDate(result.data_date)}</b></span>
        <span class="ov-chip"><i class="g-key"></i>not critical &nbsp;<i class="g-key crit"></i>critical &nbsp;<i class="g-key ms"></i>milestone</span>
      </div></div></div>
    <div class="g-wrap"><div class="g-inner g-lazy" style="--trackw:${trackW}px">
      <div class="g-scale"><div class="g-lbl g-scale-lbl"><span>Activity</span><i>Start</i><i>Finish</i></div>
        <div class="g-track g-scale-track">${ticks}${ddx != null ? `<div class="g-dd" style="left:${ddx.toFixed(1)}px"><span>data date</span></div>` : ''}</div></div>
      <div class="g-grids">${grid}${ddx != null ? `<div class="g-dd-line" style="left:calc(var(--g-lblw) + ${ddx.toFixed(1)}px)"></div>` : ''}</div>
      <div class="g-rows">${rows}</div>
    </div></div>
    <p class="ov-note">${note}</p>
    <div class="action-buttons">
      <button class="btn-secondary" id="sched-print-btn">Print / PDF / Word</button>
      <button class="btn-secondary" id="sched-excel-btn">Export to Excel</button>
    </div>`;

  _print = printSections(result, acts, groups, counts, { min, max, dd }, note);
}

// ── File ▸ Print / PDF / Word / HTML — the same rows as the screen, laid out for a page ──
// One 'Summary' section and one 'Gantt chart' section whose parts are the WBS groups (each a
// table: ID, name, Start, Finish, %, float and the bar on a page-wide time scale), so the
// Report Contents picker can tick whole groups in or out.
function printSections(result, acts, groups, counts, sp, note) {
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
  const head = `<thead><tr><th>Activity ID</th><th>Activity name</th><th>Start</th><th>Finish</th><th class="gp-n">%</th><th class="gp-n">Float</th>`
    + `<th class="gp-tl" data-export="bar"><div class="gp-scale">${scale}</div></th></tr></thead>`;

  const rowHtml = ({ a, sMs, fMs }) => {
    const l = pos(sMs), w = Math.max(0.6, pos(fMs) - l);
    const bar = a.milestone
      ? `<b class="gp-ms${a.critical ? ' crit' : ''}" style="left:${l.toFixed(2)}%"></b>`
      : `<b class="gp-bar${a.critical ? ' crit' : ''}" style="left:${l.toFixed(2)}%;width:${Math.min(w, 100 - l).toFixed(2)}%"><s style="width:${Math.max(0, Math.min(100, a.pct))}%"></s></b>`;
    return `<tr${a.critical ? ' class="gp-crit"' : ''}><td class="gp-id">${escapeHtml(a.id)}${a.milestone ? ' ◆' : ''}</td><td>${escapeHtml(a.name)}</td>`
      + `<td class="gp-d">${gShort(a.start)}</td><td class="gp-d">${gShort(a.finish)}</td><td class="gp-n">${a.pct}</td>`
      + `<td class="gp-n">${a.tf == null ? '—' : a.tf}</td><td class="gp-tl" data-export="bar"><div class="gp-track">${ddLine}${bar}</div></td></tr>`;
  };

  const parts = groups.map((g) => {
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
      ${kv('Activities shown', counts.total)}
      ${kv('Completed', counts.done)}${kv('In progress', counts.prog)}${kv('Not started', counts.notStarted)}
      ${kv('Critical (total float of zero or less, not finished)', counts.crit)}
      ${kv('Milestones', counts.ms)}
      ${kv('WBS groups', groups.length)}
      ${kv('Earliest start', gDate(acts.reduce((m, a) => (a.start < m ? a.start : m), acts[0].start)))}
      ${kv('Latest finish', gDate(acts.reduce((m, a) => (a.finish > m ? a.finish : m), acts[0].finish)))}
      </tbody></table></div>
    <div data-part="summary.note" data-part-label="How to read the chart"><p class="ov-note">${note} A ◆ after the Activity ID marks a milestone; Float is total float in days.</p></div>`;

  return [
    { key: 'summary', label: 'Summary', html: summary },
    { key: 'gantt', label: 'Gantt chart by WBS', html: parts },
  ];
}
