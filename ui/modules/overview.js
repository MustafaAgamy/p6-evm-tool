// Project ▸ Overview and Project ▸ WBS views.
// Both render from the parsed result already held in state — no re-parse, no new
// API. Overview is a project-level "at a glance"; WBS is a summary of the WBS
// hierarchy on a calendar — the user picks a main branch (e.g. Engineering /
// Construction) and every WBS beneath it is shown, expanded to the level that
// holds activities, with weighted planned/actual % and a start→finish bar.
import { fmtEGP, fmtDate } from './format.js';

const pct = (v) => (v == null ? '—' : `${(v * 100).toFixed(2)}%`);
const bar = (planned, actual) => {
  const p = Math.max(0, Math.min(100, (planned || 0) * 100));
  const a = Math.max(0, Math.min(100, (actual || 0) * 100));
  return `<div class="ovb"><div class="ovb-plan" style="width:${p.toFixed(1)}%"></div>
    <div class="ovb-act" style="width:${a.toFixed(1)}%"></div></div>`;
};

export function renderOverview(result) {
  const el = document.getElementById('overview-body');
  if (!el || !result) return;
  const spi = result.spi != null ? result.spi.toFixed(2) : '—';
  const cpi = result.cpi != null ? result.cpi.toFixed(2) : '—';
  // Delay in working days from the finish-milestone float; when the schedule
  // carries no milestone float, fall back to forecast-finish minus baseline-finish.
  let delayDays = result.delay_days;
  if (delayDays == null && result.expected_finish && result.baseline_finish) {
    const d = Math.round((new Date(result.expected_finish) - new Date(result.baseline_finish)) / 86400000);
    if (!Number.isNaN(d)) delayDays = d;
  }
  const delay = delayDays != null ? `${delayDays} d` : '—';
  const delayCls = delayDays > 0 ? 'bad' : (delayDays < 0 ? 'good' : '');
  const cats = Object.entries(result.categories || {});
  const catRows = cats.map(([name, c]) => `
    <div class="ov-cat">
      <div class="ov-cat-name">${name}<span>${c.activity_count} activities${c.overridden ? ' · manual override' : ''}</span></div>
      ${bar(c.planned_pct, c.actual_pct)}
      <div class="ov-cat-val"><b>${pct(c.actual_pct)}</b><span>plan ${pct(c.planned_pct)}</span></div>
    </div>`).join('');

  el.innerHTML = `
    <div class="ov-head">
      <div class="ov-title">
        <h2>${result.project_name || 'Project overview'}</h2>
        <div class="ov-chips">
          <span class="ov-chip">data date <b>${fmtDate(result.data_date)}</b></span>
          <span class="ov-chip"><b>${result.activity_count ?? '—'}</b> activities</span>
          <span class="ov-chip"><b>${result.calendar_count ?? '—'}</b> calendars</span>
          <span class="ov-chip"><b>${cats.length}</b> WBS categories</span>
        </div>
      </div>
    </div>
    <div class="ov-kpis">
      <div class="ov-kpi"><div class="k">SPI · schedule</div><div class="v ${result.spi != null && result.spi < 1 ? 'bad' : ''}">${spi}</div></div>
      <div class="ov-kpi"><div class="k">Forecast finish</div><div class="v sm">${result.expected_finish ? fmtDate(result.expected_finish) : '—'}</div></div>
      <div class="ov-kpi"><div class="k">Delay</div><div class="v ${delayCls}">${delay}</div></div>
      <div class="ov-kpi"><div class="k">Baseline finish</div><div class="v sm">${result.baseline_finish ? fmtDate(result.baseline_finish) : '—'}</div></div>
      <div class="ov-kpi"><div class="k">Overall planned</div><div class="v">${pct(result.overall_planned_pct)}</div></div>
      <div class="ov-kpi"><div class="k">Overall actual</div><div class="v">${pct(result.overall_actual_pct)}</div></div>
      <div class="ov-kpi"><div class="k">Planned value</div><div class="v sm">${fmtEGP(result.pv)}</div></div>
      <div class="ov-kpi"><div class="k">Earned value</div><div class="v sm">${fmtEGP(result.ev)}</div></div>
      <div class="ov-kpi"><div class="k">Actual cost</div><div class="v sm">${fmtEGP(result.ac)}</div></div>
      <div class="ov-kpi"><div class="k">CPI · cost</div><div class="v">${cpi}</div></div>
    </div>
    <div class="ov-section-label">Progress by category <span class="ovl"><i class="dp"></i>planned <i class="da"></i>actual</span></div>
    <div class="ov-cats">${catRows || '<p class="ov-empty">No categories configured for this schedule.</p>'}</div>
    <p class="ov-note">A project summary from the imported update — the same figures the modules and PDF report use. Open a module from the navigator to drill in.</p>`;
}

// ── Project ▸ WBS summary timeline ──────────────────────────────────────
const DAY = 86400000;
const WBS_LEFT = 540;              // fixed left columns: 260+52+52+88+88
let wbsMainId = null;              // remembers the picked main branch across re-renders

const toMs = (s) => { if (!s) return NaN; const d = new Date(s.length <= 10 ? s + 'T00:00:00' : s); const t = d.getTime(); return Number.isNaN(t) ? NaN : t; };
const fmtShort = (ms) => new Date(ms).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' });
const pctVal = (v) => (v == null ? '—' : `${v.toFixed(1)}%`);   // backend already gives 0–100

export function renderWbs(result) {
  const el = document.getElementById('wbs-body');
  if (!el || !result) return;
  const nodes = result.wbs_summary || [];
  const mains = result.wbs_main || [];

  if (!nodes.length) {
    el.innerHTML = `
      <div class="ov-head"><div class="ov-title"><h2>WBS — summary</h2></div></div>
      <p class="ov-note">No WBS breakdown is available.${result.activity_count
        ? ' Re-import this schedule to build the WBS summary — a re-opened project loads rolled-up metrics from the database rather than the WBS tree.'
        : ''}</p>`;
    return;
  }

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

  // time scale over the branch's dated nodes (+ data date)
  let min = Infinity, max = -Infinity;
  for (const n of subset) {
    const s = toMs(n.start), f = toMs(n.finish);
    if (!Number.isNaN(s)) min = Math.min(min, s);
    if (!Number.isNaN(f)) max = Math.max(max, f);
  }
  const dd = toMs(result.data_date);
  if (!Number.isNaN(dd)) { min = Math.min(min, dd); max = Math.max(max, dd); }
  const dated = Number.isFinite(min) && Number.isFinite(max) && max > min;
  if (!dated) { min = Date.now(); max = min + DAY; }

  const totalDays = Math.max(1, Math.round((max - min) / DAY));
  const trackW = Math.max(680, Math.min(Math.round(totalDays * 3), 3600));
  const ppd = trackW / totalDays;
  const xOf = (ms) => ((ms - min) / DAY) * ppd;

  // month ticks / gridlines / year markers
  const monthPx = ppd * 30.4;
  const step = monthPx >= 60 ? 1 : Math.ceil(60 / monthPx);
  let ticks = '', grid = '', k = 0;
  const t = new Date(min); t.setDate(1); t.setHours(0, 0, 0, 0);
  for (; t.getTime() <= max; t.setMonth(t.getMonth() + 1), k++) {
    const x = xOf(t.getTime());
    if (x < -0.5 || x > trackW + 0.5) continue;
    const lbl = k % step === 0 ? `<span>${t.toLocaleDateString('en-GB', { month: 'short' })}</span>` : '';
    ticks += `<div class="wbst-tk" style="left:${x.toFixed(1)}px">${lbl}</div>`;
    grid  += `<div class="wbst-gl" style="left:calc(${WBS_LEFT}px + ${x.toFixed(1)}px)"></div>`;
    if (t.getMonth() === 0) ticks += `<div class="wbst-yr" style="left:${(x + 3).toFixed(1)}px">${t.getFullYear()}</div>`;
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
      const left = xOf(sMs), w = Math.max(5, xOf(fMs) - left);
      const ac = n.actual == null ? null : Math.max(0, Math.min(100, n.actual));
      const pl = n.planned == null ? null : Math.max(0, Math.min(100, n.planned));
      const behind = ac != null && pl != null && pl > ac
        ? `<div class="wbst-behind" style="left:${ac}%;width:${(pl - ac).toFixed(1)}%"></div>` : '';
      const tick = pl != null ? `<div class="wbst-tick" style="left:${pl}%"></div>` : '';
      bar = `<div class="wbst-bar${leaf ? '' : ' sum'}" style="left:${left.toFixed(1)}px;width:${w.toFixed(1)}px">
          ${ac != null ? `<div class="wbst-act" style="width:${ac}%"></div>` : ''}${behind}${tick}
          <div class="wbst-cap"></div></div>`;
    }
    return `<div class="wbst-row ${leaf ? 'leaf' : 'sum'} d${rd}">
      <div class="wc-wbs"><div class="wbst-nm" style="padding-left:${rd * 16}px">${marker}<span class="nm" title="${escapeAttr(n.name)}">${escapeHtml(n.name)}</span></div></div>
      <div class="wc-pl">${pctVal(n.planned)}</div><div class="wc-ac"><b>${pctVal(n.actual)}</b></div>
      <div class="wc-st">${Number.isNaN(sMs) ? '—' : fmtShort(sMs)}</div>
      <div class="wc-fn">${Number.isNaN(fMs) ? '—' : fmtShort(fMs)}</div>
      <div class="wc-tl">${bar}</div>
    </div>`;
  }).join('');

  const seg = mains.length > 1
    ? `<div class="wbst-seg" id="wbst-seg">${mains.map((m) =>
        `<button data-mw="${escapeAttr(m.id)}" class="${m.id === wbsMainId ? 'on' : ''}">${escapeHtml(m.name)}</button>`).join('')}</div>`
    : '';

  el.innerHTML = `
    <div class="ov-head"><div class="ov-title"><h2>WBS — summary</h2>
      <div class="ov-chips">
        <span class="ov-chip"><b>${branch.activities ?? '—'}</b> activities</span>
        ${dated ? `<span class="ov-chip">${fmtShort(min)} → ${fmtShort(max)}</span>` : ''}
        <span class="ov-chip">overall <b>${pctVal(branch.planned)}</b> planned · <b>${pctVal(branch.actual)}</b> actual</span>
      </div></div></div>
    <div class="wbst-toolbar">${seg}
      <div class="wbst-legend">
        <span><i class="wbst-lg dur"></i>duration → finish</span>
        <span><i class="wbst-lg act"></i>actual %</span>
        <span><i class="wbst-lg beh"></i>behind plan</span>
        <span><i class="wbst-lg tgt"></i>plan target</span>
      </div></div>
    <div class="wbst-wrap"><div class="wbst-inner" style="--trackw:${trackW}px">
      <div class="wbst-scale">
        <div class="wc-wbs wbst-h">WBS</div><div class="wc-pl wbst-h" style="justify-content:flex-end">Plan</div>
        <div class="wc-ac wbst-h" style="justify-content:flex-end">Act</div>
        <div class="wc-st wbst-h">Start</div><div class="wc-fn wbst-h">Finish</div>
        <div class="wc-tl wbst-scale-track">${ticks}</div>
      </div>
      <div class="wbst-grids">${grid}${ddx != null ? `<div class="wbst-dd" style="left:calc(${WBS_LEFT}px + ${ddx.toFixed(1)}px)"></div>` : ''}</div>
      <div class="wbst-rows">${rows}</div>
    </div></div>
    <p class="ov-note">Pick the <b>main WBS</b> — every branch beneath it is shown, expanded to the level that holds activities (●). Each bar is the full rolled-up <b>duration</b>: its right edge lands on the <b>Finish</b> column. The deep fill is actual % complete, the amber segment is the gap still behind plan, and the tick marks the plan target. Weighted the same way as Overall % and SPI.</p>`;

  const segEl = document.getElementById('wbst-seg');
  if (segEl) segEl.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-mw]');
    if (!b || b.dataset.mw === wbsMainId) return;
    wbsMainId = b.dataset.mw;
    renderWbs(result);
  });
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }
