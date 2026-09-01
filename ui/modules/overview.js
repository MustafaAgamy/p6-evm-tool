// Project ▸ Overview and Project ▸ WBS views.
// Both render from the parsed result already held in state — no re-parse, no new
// API. Overview is a project-level "at a glance"; WBS is the category/WBS
// progress breakdown. (A full activity Gantt needs per-activity dates that the
// parse response strips, so Schedule (Gantt) is a separate follow-up.)
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

export function renderWbs(result) {
  const el = document.getElementById('wbs-body');
  if (!el || !result) return;
  const cats = Object.entries(result.categories || {});
  const rows = cats.map(([name, c]) => `
    <tr>
      <td>${name}</td>
      <td class="n">${(c.weight * 100).toFixed(1)}%</td>
      <td class="n">${pct(c.planned_pct)}</td>
      <td class="n">${pct(c.actual_pct)}</td>
      <td class="n">${c.activity_count}</td>
      <td class="n">${c.bac ? fmtEGP(c.bac) : '—'}</td>
      <td>${c.overridden ? 'Manual override' : 'From XML'}</td>
    </tr>`).join('');
  el.innerHTML = `
    <div class="ov-head"><div class="ov-title"><h2>WBS — category breakdown</h2>
      <div class="ov-chips"><span class="ov-chip"><b>${cats.length}</b> categories</span>
        <span class="ov-chip">overall <b>${pct(result.overall_actual_pct)}</b> actual</span></div></div></div>
    <div class="ov-tablewrap"><table class="ov-table">
      <thead><tr><th>WBS category</th><th class="n">Weight</th><th class="n">Planned %</th><th class="n">Actual %</th><th class="n">Activities</th><th class="n">BAC</th><th>Source</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="7" class="ov-empty">No categories configured.</td></tr>'}</tbody>
      <tfoot><tr><td>Overall</td><td class="n">100%</td><td class="n">${pct(result.overall_planned_pct)}</td><td class="n">${pct(result.overall_actual_pct)}</td>
        <td class="n">${cats.reduce((s, [, c]) => s + (c.activity_count || 0), 0)}</td><td class="n">${fmtEGP(result.pv != null ? (result.categories ? Object.values(result.categories).reduce((s, c) => s + (c.bac || 0), 0) : 0) : 0)}</td><td>—</td></tr></tfoot>
    </table></div>
    <p class="ov-note">The WBS-category structure the schedule is classified into, with weighted progress — the basis for Overall % and SPI.</p>`;
}
