// Project ▸ Schedule (Gantt). Renders a time-scaled bar chart from the slim
// activity list the parse response now carries (result.activities). Current-
// schedule bars (planned start → finish) with % complete, critical highlighting,
// month gridlines and a data-date line, grouped by top-level WBS.
import { fmtDate, escapeHtml } from './format.js';

const DAY = 86400000;
const LBLW = 248;
const ROW_H = 30, GRP_H = 26;   // = .g-row / .g-grp heights in style.css (border-box)
const GANTT_BLOCK = 60;         // rows per lazily laid-out block

export function renderSchedule(result) {
  const el = document.getElementById('schedule-body');
  if (!el) return;
  const acts = (result && result.activities) || [];
  if (!acts.length) {
    el.innerHTML = `
      <div class="ov-head"><div class="ov-title"><h2>Schedule (Gantt)</h2></div></div>
      <p class="ov-note">No activity timeline is available.${result && result.activity_count
        ? ' Re-import this schedule to build the Gantt — a re-opened project loads from the database, which stores rolled-up metrics rather than per-activity dates.'
        : ''}</p>`;
    return;
  }

  const toMs = (s) => new Date(s).getTime();
  let min = Infinity, max = -Infinity;
  for (const a of acts) { const s = toMs(a.start), f = toMs(a.finish); if (s < min) min = s; if (f > max) max = f; }
  const dd = result.data_date ? toMs(result.data_date) : null;
  if (dd != null && !Number.isNaN(dd)) { min = Math.min(min, dd); max = Math.max(max, dd); }
  const totalDays = Math.max(1, Math.round((max - min) / DAY));
  const trackW = Math.max(720, Math.min(Math.round(totalDays * 4), 4400));
  const ppd = trackW / totalDays;
  const xOf = (ms) => ((ms - min) / DAY) * ppd;

  // month ticks + full-height gridlines
  let ticks = '', grid = '';
  const t = new Date(min); t.setDate(1); t.setHours(0, 0, 0, 0);
  for (; t.getTime() <= max; t.setMonth(t.getMonth() + 1)) {
    const x = xOf(t.getTime());
    if (x < -0.5 || x > trackW + 0.5) continue;
    const lbl = t.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
    ticks += `<div class="g-tick" style="left:${x.toFixed(1)}px"><span>${lbl}</span></div>`;
    grid  += `<div class="g-grid-line" style="left:calc(${LBLW}px + ${x.toFixed(1)}px)"></div>`;
  }
  const ddx = (dd != null && !Number.isNaN(dd)) ? xOf(dd) : null;

  // group by top-level WBS, ordered by earliest start (each date parsed ONCE, not per compare)
  const groups = {}, first = {};
  for (const a of acts) {
    const g = a.wbs_top || 'Ungrouped', sMs = toMs(a.start);
    (groups[g] ??= []).push({ a, sMs, fMs: toMs(a.finish) });
    if (!(first[g] <= sMs)) first[g] = sMs;
  }
  const order = Object.keys(groups).sort((ga, gb) => first[ga] - first[gb]);

  // Rows are built in blocks of GANTT_BLOCK lines; each block carries its exact height, so
  // the browser lays out only the blocks on screen (content-visibility) — a 6,000-activity
  // schedule then opens without a long freeze of the Run bar (owner comment 36).
  const blocks = [];
  let blk = '', blkH = 0, blkN = 0;
  const push = (html, h) => {
    blk += html; blkH += h; blkN++;
    if (blkN >= GANTT_BLOCK) { blocks.push(`<div class="g-blk" style="contain-intrinsic-size:auto ${blkH}px">${blk}</div>`); blk = ''; blkH = 0; blkN = 0; }
  };
  for (const g of order) {
    push(`<div class="g-grp"><div class="g-lbl g-grp-lbl">${escapeHtml(g)}</div><div class="g-track"></div></div>`, GRP_H);
    for (const { a, sMs, fMs } of groups[g].sort((x, y) => x.sMs - y.sMs)) {
      const left = xOf(sMs);
      const w = Math.max(3, xOf(fMs) - left);
      const lbl = `<div class="g-lbl"><b>${escapeHtml(a.id)}</b><span>${escapeHtml(a.name)}</span></div>`;
      const bar = a.milestone
        ? `<div class="g-ms" style="left:${(left - 6).toFixed(1)}px" title="Milestone"></div>`
        : `<div class="g-bar${a.critical ? ' crit' : ''}" style="left:${left.toFixed(1)}px;width:${w.toFixed(1)}px">
             <span class="g-fill" style="width:${Math.max(0, Math.min(100, a.pct))}%"></span></div>
           <span class="g-plabel" style="left:${(left + w + 6).toFixed(1)}px">${a.pct}%</span>`;
      push(`<div class="g-row">${lbl}<div class="g-track">${bar}</div></div>`, ROW_H);
    }
  }
  if (blkN) blocks.push(`<div class="g-blk" style="contain-intrinsic-size:auto ${blkH}px">${blk}</div>`);
  const rows = blocks.join('');

  el.innerHTML = `
    <div class="ov-head"><div class="ov-title"><h2>Schedule (Gantt)</h2>
      <div class="ov-chips">
        <span class="ov-chip"><b>${acts.length}</b> activities</span>
        <span class="ov-chip">data date <b>${fmtDate(result.data_date)}</b></span>
        <span class="ov-chip"><i class="g-key"></i>on track &nbsp;<i class="g-key crit"></i>critical</span>
      </div></div></div>
    <div class="g-wrap"><div class="g-inner g-lazy" style="--trackw:${trackW}px">
      <div class="g-scale"><div class="g-lbl g-scale-lbl">Activity</div>
        <div class="g-track g-scale-track">${ticks}${ddx != null ? `<div class="g-dd" style="left:${ddx.toFixed(1)}px"><span>data date</span></div>` : ''}</div></div>
      <div class="g-grids">${grid}${ddx != null ? `<div class="g-dd-line" style="left:calc(${LBLW}px + ${ddx.toFixed(1)}px)"></div>` : ''}</div>
      <div class="g-rows">${rows}</div>
    </div></div>
    <p class="ov-note">Current-schedule bars (planned start → finish) with % complete fill; critical activities (total float ≤ 0) in red; milestones as diamonds; the data-date line marks the cut-off. Grouped by top-level WBS.</p>
    <div class="action-buttons"><button class="btn-secondary" id="sched-excel-btn">Export to Excel</button></div>`;
}
