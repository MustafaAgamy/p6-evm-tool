// Project ▸ Professional Dashboard.
// A portfolio + trend read-model rendered entirely from the database
// (`/api/dashboard` → db.get_dashboard) — never a re-parse, per the
// "DB is the read path" rule. It shows every imported project's latest health
// at a glance, and — for the project currently open — a week-over-week trend
// built from that project's stored snapshots.
import { state } from './state.js';
import { fmtEGP, fmtDate, escapeHtml } from './format.js';

let _print = null;   // printable sections for the global File ▸ Print flow
export function dashboardPrint() { return _print; }

const spiFmt = (v) => (v == null ? '—' : Number(v).toFixed(2));
// metrics.overall_*_pct is stored as a fraction (0–1); show it as a percent.
const pct1   = (v) => (v == null ? '—' : `${(Number(v) * 100).toFixed(1)}%`);
const asPct  = (v) => (v == null || Number.isNaN(Number(v)) ? null : Number(v) * 100);
const hasData = (ys) => ys.some((y) => y != null && !Number.isNaN(y));
const toMs = (s) => { if (!s) return NaN; const t = new Date(s.length <= 10 ? s + 'T00:00:00' : s).getTime(); return Number.isNaN(t) ? NaN : t; };

// planned-vs-actual mini bar (same two-tone idea as Overview's category bars)
function miniBar(planned, actual) {
  const p = Math.max(0, Math.min(100, planned == null ? 0 : planned * 100));
  const a = Math.max(0, Math.min(100, actual == null ? 0 : actual * 100));
  return `<div class="dash-mbar" title="planned ${pct1(planned)} · actual ${pct1(actual)}">
    <div class="dash-mbar-plan" style="width:${p.toFixed(1)}%"></div>
    <div class="dash-mbar-act" style="width:${a.toFixed(1)}%"></div></div>`;
}

// A compact multi-series line chart in inline SVG (no chart lib — matches the
// app's other charts). xs are shared timestamps; each series carries ys aligned
// to xs (null = gap). An optional reference line (e.g. SPI = 1.00) is drawn behind.
function lineChart(xs, series, { w = 360, h = 132, fmtY = (v) => String(v), ref = null } = {}) {
  const padL = 8, padR = 10, padT = 12, padB = 20;
  const vals = [];
  for (const s of series) for (const y of s.ys) if (y != null && !Number.isNaN(y)) vals.push(y);
  if (ref != null) vals.push(ref);
  if (!vals.length) return `<div class="dash-chart-empty">No data</div>`;
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (lo === hi) { lo -= 1; hi += 1; }                 // flat series → give it room
  const pad = (hi - lo) * 0.12; lo -= pad; hi += pad;
  const xlo = Math.min(...xs), xhi = Math.max(...xs);
  const xspan = xhi - xlo || 1;
  const X = (ms) => padL + ((ms - xlo) / xspan) * (w - padL - padR);
  const Y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (h - padT - padB);

  let refEl = '';
  if (ref != null) {
    const y = Y(ref).toFixed(1);
    refEl = `<line x1="${padL}" y1="${y}" x2="${w - padR}" y2="${y}" class="dash-ref"/>
      <text x="${w - padR}" y="${(+y - 4).toFixed(1)}" class="dash-ref-lbl" text-anchor="end">${fmtY(ref)}</text>`;
  }
  const paths = series.map((s) => {
    // break the polyline at nulls so gaps don't draw straight through
    let d = '', pen = false, lastPt = null;
    s.ys.forEach((y, i) => {
      if (y == null || Number.isNaN(y)) { pen = false; return; }
      const x = X(xs[i]), yy = Y(y);
      d += `${pen ? 'L' : 'M'}${x.toFixed(1)} ${yy.toFixed(1)} `;
      pen = true; lastPt = { x, y: yy, v: y };
    });
    const dots = s.ys.map((y, i) => (y == null || Number.isNaN(y)) ? ''
      : `<circle cx="${X(xs[i]).toFixed(1)}" cy="${Y(y).toFixed(1)}" r="2.4" fill="${s.color}"/>`).join('');
    const end = lastPt
      ? `<text x="${Math.min(lastPt.x + 6, w - padR)}" y="${(lastPt.y - 5).toFixed(1)}" class="dash-endlbl" fill="${s.color}" text-anchor="end">${fmtY(lastPt.v)}</text>`
      : '';
    return `<path d="${d.trim()}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>${dots}${end}`;
  }).join('');

  const x0 = fmtDate(new Date(xlo).toISOString()), x1 = fmtDate(new Date(xhi).toISOString());
  return `<svg class="dash-chart" viewBox="0 0 ${w} ${h}" role="img">
    ${refEl}${paths}
    <text x="${padL}" y="${h - 5}" class="dash-axlbl">${x0}</text>
    <text x="${w - padR}" y="${h - 5}" class="dash-axlbl" text-anchor="end">${x1}</text>
  </svg>`;
}

function trendBlock(title, legend, svg) {
  return `<div class="dash-trend">
    <div class="dash-trend-h"><h4>${title}</h4><div class="dash-leg">${legend}</div></div>
    ${svg}</div>`;
}

export async function renderDashboard() {
  const el = document.getElementById('dash-body');
  if (!el) return;
  _print = null;
  el.innerHTML = `<div class="dash-loading">Loading portfolio…</div>`;

  let data;
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/dashboard`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot_id: state.currentSnapshotId || null }),
    });
    data = await resp.json();
  } catch (e) {
    el.innerHTML = `<div class="dash-empty">Couldn't load the dashboard — ${escapeHtml(String((e && e.message) || e))}.</div>`;
    return;
  }
  if (!data || !data.ok) {
    el.innerHTML = `<div class="dash-empty">Couldn't load the dashboard.${data && data.error ? ' ' + escapeHtml(data.error) : ''}</div>`;
    return;
  }

  const portfolio = data.portfolio || [];
  const activePid = data.active ? data.active.project_id : null;
  if (!portfolio.length) {
    el.innerHTML = `
      <div class="ov-head"><div class="ov-title"><h2>Professional Dashboard</h2></div></div>
      <p class="ov-note">No projects yet. Import a P6 schedule and it will appear here — the dashboard reads your saved history from the database, so it fills in as you import updates.</p>`;
    return;
  }

  const behind = portfolio.filter((r) => r.spi != null && r.spi < 1).length;
  const onTrack = portfolio.filter((r) => r.spi != null && r.spi >= 1).length;
  const updates = portfolio.reduce((s, r) => s + (r.snapshot_count || 1), 0);

  const cards = portfolio.map((r) => {
    const spiCls = r.spi == null ? '' : (r.spi < 1 ? 'bad' : 'good');
    const dcls = r.delay_days == null ? '' : (r.delay_days > 0 ? 'bad' : (r.delay_days < 0 ? 'good' : ''));
    const delay = r.delay_days == null ? '—' : `${r.delay_days > 0 ? '+' : ''}${r.delay_days} d`;
    const isActive = r.project_id === activePid;
    return `<div class="dash-card${isActive ? ' active' : ''}" data-pid="${r.project_id}">
      <div class="dash-card-top">
        <div class="dash-card-name" title="${escapeHtml(r.name || '')}">${escapeHtml(r.name || '(project)')}</div>
        ${isActive ? '<span class="dash-badge">open</span>' : ''}
      </div>
      <div class="dash-card-sub">${r.data_date ? fmtDate(r.data_date) : '—'} · ${r.snapshot_count || 1} update${(r.snapshot_count || 1) === 1 ? '' : 's'} · ${r.activity_count ?? '—'} act.</div>
      <div class="dash-kpis">
        <div class="dash-kpi"><span>SPI</span><b class="${spiCls}">${spiFmt(r.spi)}</b></div>
        <div class="dash-kpi"><span>CPI</span><b>${spiFmt(r.cpi)}</b></div>
        <div class="dash-kpi"><span>Delay</span><b class="${dcls}">${delay}</b></div>
      </div>
      <div class="dash-prog">
        ${miniBar(r.overall_planned_pct, r.overall_actual_pct)}
        <div class="dash-prog-lbl"><b>${pct1(r.overall_actual_pct)}</b> actual <span>· plan ${pct1(r.overall_planned_pct)}</span></div>
      </div>
    </div>`;
  }).join('');

  // active project's trend (needs ≥2 snapshots to draw a line)
  let trends = '', trendInner = '';
  const trend = data.active && Array.isArray(data.active.trend) ? data.active.trend : [];
  const dated = trend.filter((t) => !Number.isNaN(toMs(t.data_date)));
  if (data.active && dated.length >= 2) {
    const xs = dated.map((t) => toMs(t.data_date));
    const spiC = 'var(--accent)', planC = 'var(--muted)', actC = 'var(--accent)', delC = 'var(--warning)';
    const spiYs  = dated.map((t) => t.spi);
    const planYs = dated.map((t) => asPct(t.overall_planned_pct));
    const actYs  = dated.map((t) => asPct(t.overall_actual_pct));
    const delYs  = dated.map((t) => t.delay_days);
    const blocks = [];
    if (hasData(spiYs))
      blocks.push(trendBlock('Schedule Performance Index', `<i style="background:${spiC}"></i>SPI <em>· 1.00 on plan</em>`,
        lineChart(xs, [{ ys: spiYs, color: spiC }], { ref: 1, fmtY: (v) => Number(v).toFixed(2) })));
    if (hasData(planYs) || hasData(actYs))
      blocks.push(trendBlock('Overall progress', `<i style="background:${actC}"></i>actual <i style="background:${planC}"></i>planned`,
        lineChart(xs, [{ ys: planYs, color: planC }, { ys: actYs, color: actC }], { fmtY: (v) => `${Number(v).toFixed(0)}%` })));
    if (hasData(delYs))
      blocks.push(trendBlock('Finish delay', `<i style="background:${delC}"></i>days <em>· 0 on baseline</em>`,
        lineChart(xs, [{ ys: delYs, color: delC }], { ref: 0, fmtY: (v) => `${Math.round(v)}d` })));
    if (blocks.length) {
      trendInner = `<div class="dash-trends">${blocks.join('')}</div>`;
      trends = `
      <div class="ov-section-label">Trend · ${escapeHtml(data.active.name || 'current project')} <span class="dash-trend-sub">${dated.length} updates</span></div>
      ${trendInner}`;
    }
  } else if (data.active) {
    trends = `<p class="ov-note dash-trend-note">Import another update for <b>${escapeHtml(data.active.name || 'this project')}</b> to see its week-over-week trend — the dashboard charts SPI, progress and delay across every stored snapshot.</p>`;
  }

  _print = [{ key: 'portfolio', label: 'Portfolio', html: `<div class="dash-grid">${cards}</div>` }];
  if (trendInner) _print.push({ key: 'trend', label: `Trend · ${data.active.name || 'current project'}`, html: trendInner });

  el.innerHTML = `
    <div class="ov-head"><div class="ov-title">
      <h2>Professional Dashboard</h2>
      <div class="ov-chips">
        <span class="ov-chip"><b>${portfolio.length}</b> project${portfolio.length === 1 ? '' : 's'}</span>
        <span class="ov-chip"><b>${updates}</b> update${updates === 1 ? '' : 's'}</span>
        <span class="ov-chip"><b class="good">${onTrack}</b> on track · <b class="bad">${behind}</b> behind</span>
      </div>
    </div></div>
    <div class="ov-section-label">Portfolio <span class="dash-trend-sub">latest update per project</span></div>
    <div class="dash-grid">${cards}</div>
    ${trends}
    <p class="ov-note">A portfolio view of every schedule you've imported, read from the saved database — no re-parse. Open a project from Recent Projects to load its detail; the project currently open is highlighted and its trend is charted above.</p>`;
}
