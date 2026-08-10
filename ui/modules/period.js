// Update vs Update — Windows Analysis.
//
// The currently-open schedule is THIS period; the user picks LAST period (auto-
// suggested from history, or browsed). Renders progress vs last period's forecast,
// the activity % variance table and the period S-curve. Critical-path movement,
// what-moved buckets, the milestone trend and exports are added by later sections.
import { state }      from './state.js';
import { showError }  from './render.js';
import { escapeHtml } from './format.js';

let _shownReport = null;   // the report currently on screen (exports read this)
let _prev = null;          // {prev_path} or {prev_cached_path} chosen for the comparison

function _currName() {
  const p = state.currentXmlPath || state.currentCachedPath || '';
  return p.split(/[\\/]/).pop() || 'current schedule';
}

function _signPct(v) {
  if (v == null) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function _shortDate(s) {
  if (!s) return '—';
  return String(s).slice(0, 10);   // YYYY-MM-DD from a DB timestamp
}

// ── Panel entry: input flow ─────────────────────────────────────────────────

export function renderPeriodPanel() {
  const body = document.getElementById('period-body');
  if (!body) return;
  if (!state.currentXmlPath && !state.currentCachedPath) {
    body.innerHTML = `<div class="cmp-empty">Import a schedule first, then open Update vs Update.</div>`;
    return;
  }
  body.innerHTML = `
    <div class="mod-sec">Update vs Update — Windows Analysis</div>
    <div class="cmp-note">The current schedule is <b>this period</b>. Choose <b>last period's</b> update to compare against — the tool shows what moved between the two data dates.</div>
    <div class="per-inputs">
      <span class="cmp-file"><span class="k">This period</span> <b>${escapeHtml(_currName())}</b></span>
      <span class="cmp-vs">vs</span>
      <span id="per-prev-suggest" class="per-suggest">Looking for last period…</span>
      <button class="btn-mini" id="per-choose-prev">Choose a different file…</button>
    </div>
    <div id="per-report"></div>`;
  document.getElementById('per-choose-prev').addEventListener('click', choosePrevAndCompare);
  _fetchPreviousSuggestion();
}

async function _fetchPreviousSuggestion() {
  const el = document.getElementById('per-prev-suggest');
  if (!el) return;
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/period/previous`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot_id: state.currentSnapshotId }),
    });
    const data = await resp.json();
    if (data.ok && data.previous) {
      const p = data.previous;
      el.innerHTML = `<button class="btn-secondary" id="per-use-prev">Use last period · ${escapeHtml(_shortDate(p.data_date))}${p.filename ? ' · ' + escapeHtml(p.filename) : ''}</button>`;
      document.getElementById('per-use-prev').addEventListener('click', () => {
        _prev = { prev_cached_path: p.cached_path };
        _runCompare();
      });
    } else {
      el.innerHTML = `<span class="mut">No earlier import found for this project — pick the previous file →</span>`;
    }
  } catch {
    el.innerHTML = `<span class="mut">Pick the previous update file →</span>`;
  }
}

async function choosePrevAndCompare() {
  const path = await window.pywebview.api.choose_file();
  if (!path) return;
  _prev = { prev_path: path };
  _runCompare();
}

async function _runCompare() {
  const rep = document.getElementById('per-report');
  if (rep) rep.innerHTML = `<div class="cmp-loading">Comparing the two updates…</div>`;
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/period/compare`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ..._prev,
        update_path: state.currentXmlPath,
        cached_path: state.currentCachedPath,
      }),
    });
    const data = await resp.json();
    if (!data.ok) { if (rep) rep.innerHTML = `<div class="cmp-warn">${escapeHtml(data.error || 'Comparison failed.')}</div>`; return; }
    renderPeriodReport(data.report);
  } catch {
    if (rep) rep.innerHTML = `<div class="cmp-warn">Could not reach the local server to run the comparison.</div>`;
  }
}

// ── Report render ───────────────────────────────────────────────────────────

function _kpi(label, value, sub, cls) {
  return `<div class="kpi"><div class="k">${escapeHtml(label)}</div>` +
         `<div class="v">${value}</div>` +
         (sub ? `<div class="per-kpi-sub ${cls || ''}">${sub}</div>` : '') + `</div>`;
}

function _dashboard(s) {
  const earned = _signPct(s.period_earned);
  const ach = s.forecast_achievement == null ? '—' : `${Math.round(s.forecast_achievement * 100)}%`;
  const slip = s.finish_slip_days;
  const slipTxt = slip == null ? '—' : (slip > 0 ? `▼ slipped ${slip} d` : (slip < 0 ? `▲ pulled in ${-slip} d` : 'no change'));
  const dch = s.delay_change;
  const dchTxt = dch == null ? '' : (dch > 0 ? `▼ +${dch} wd this period` : (dch < 0 ? `▲ ${dch} wd this period` : 'no change'));
  return `
    <div class="cmp-kpis">
      ${_kpi('Overall complete', `${s.actual_prev}% <span class="per-flow">→</span> ${s.actual_now}%`, `${earned} earned this period`, s.period_earned >= 0 ? 'up' : 'down')}
      ${_kpi('Vs last period’s forecast', `${s.actual_now}% <span class="mut">/ ${s.forecast_at_now}%</span>`, `${s.shortfall_pct > 0 ? '▼ ' + s.shortfall_pct.toFixed(1) + '% short' : '▲ on/ahead'} · achievement ${ach}`, s.shortfall_pct > 0 ? 'down' : 'up')}
      ${_kpi('Forecast finish', escapeHtml(s.forecast_finish_now || '—'), slipTxt, slip > 0 ? 'down' : 'up')}
      ${_kpi('Delay vs baseline', s.delay_now == null ? '—' : `${s.delay_now} wd`, dchTxt, dch > 0 ? 'down' : 'up')}
    </div>`;
}

function _progressTable(prog, s) {
  const rows = (prog && prog.rows) || [];
  if (!rows.length) return '<p class="cmp-empty">No activity changed its % complete between the two updates.</p>';
  const ph = escapeHtml((s.data_date_prev || '').replace(/-\d{4}$/, ''));   // e.g. 30-Jun
  const ch = escapeHtml((s.data_date_now || '').replace(/-\d{4}$/, ''));
  const body = rows.map(r => {
    const tag = r.finished ? '<span class="cmp-tag">finished</span>'
              : r.started ? '<span class="cmp-tag">started</span>' : '';
    const cls = r.reversal ? 'cmp-pill bad' : 'cmp-pill good';
    const arrow = r.reversal ? '▼' : '▲';
    const flag = r.reversal ? ' ⚠' : '';
    return `<tr>
      <td class="mono">${escapeHtml(r.activity_id)}</td>
      <td>${escapeHtml(r.activity_name)} ${tag}</td>
      <td class="num mut">${r.prev_pct}%</td>
      <td class="num">${r.curr_pct}%</td>
      <td class="num"><span class="${cls}">${arrow} ${_signPct(r.variance)}${flag}</span></td>
    </tr>`;
  }).join('');
  return `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-table">
    <thead><tr><th>Activity ID</th><th>Activity name</th>
      <th class="num">Prev % <span style="font-weight:400">(${ph})</span></th>
      <th class="num">Current % <span style="font-weight:400">(${ch})</span></th>
      <th class="num">Variance</th></tr></thead>
    <tbody>${body}</tbody></table></div>
    <div class="cmp-foot">Every activity whose progress moved between the two updates, biggest gain first. Uses the % Complete that drives Earned Value. <span class="cmp-pill bad">▼</span> = progress declared backwards vs last update — worth checking.</div>`;
}

function _periodScurveSvg(sc) {
  const periods = (sc && sc.periods) || [];
  if (periods.length < 2) return '<p class="cmp-empty">Not enough dated activities to draw the period S-curve.</p>';
  const x0 = 45, x1 = 600, y0 = 180, y1 = 20, n = periods.length;
  const xAt = i => x0 + (x1 - x0) * (i / (n - 1));
  const yAt = p => y0 - (y0 - y1) * (Math.max(0, Math.min(100, p || 0)) / 100);
  const line = (arr, color, dash) => {
    const pts = [];
    (arr || []).forEach((p, i) => { if (p != null) pts.push(`${xAt(i).toFixed(1)},${yAt(p).toFixed(1)}`); });
    if (pts.length < 2) return '';
    return `<polyline points="${pts.join(' ')}" fill="none" stroke="${color}" stroke-width="2"${dash ? ` stroke-dasharray="${dash}"` : ''} stroke-linejoin="round"/>`;
  };
  const pIdx = sc.dd_prev_idx ?? 0, nIdx = sc.dd_now_idx ?? (n - 1);
  const band = `<rect x="${xAt(pIdx).toFixed(1)}" y="${y1}" width="${Math.max(0, xAt(nIdx) - xAt(pIdx)).toFixed(1)}" height="${y0 - y1}" fill="rgba(59,130,246,0.08)"/>`;
  const markers = `<circle cx="${xAt(nIdx).toFixed(1)}" cy="${yAt(sc.forecast_now).toFixed(1)}" r="3.5" fill="#f59e0b"/>` +
                  `<circle cx="${xAt(nIdx).toFixed(1)}" cy="${yAt(sc.actual_now).toFixed(1)}" r="3.5" fill="#3b82f6"/>`;
  const step = Math.max(1, Math.round(n / 6));
  let xlabels = '';
  for (let i = 0; i < n; i += step) {
    xlabels += `<text x="${xAt(i).toFixed(1)}" y="198" text-anchor="middle" style="fill:var(--muted);font-size:10px">${escapeHtml(periods[i])}</text>`;
  }
  return `<svg viewBox="0 0 620 214" width="100%" role="img" aria-label="Period S-curve: actual vs last period's forecast">
    ${band}
    <line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y0}" stroke="var(--border)"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="var(--border)"/>
    <text x="${x0 - 6}" y="${y1 + 4}" text-anchor="end" style="fill:var(--muted);font-size:10px">100%</text>
    <text x="${x0 - 6}" y="${(y0 + y1) / 2 + 4}" text-anchor="end" style="fill:var(--muted);font-size:10px">50%</text>
    <text x="${x0 - 6}" y="${y0 + 4}" text-anchor="end" style="fill:var(--muted);font-size:10px">0%</text>
    ${line(sc.forecast, '#f59e0b', '5 3')}
    ${line(sc.actual, '#3b82f6')}
    ${markers}
    ${xlabels}
  </svg>`;
}

function _driverTag(d) { return `<span class="cmp-tag">${escapeHtml(d)}</span>`; }

function _critStatus(st) {
  return st === 'new'
    ? '<span class="cmp-pill bad">▶ new</span>'
    : '<span class="cmp-pill bad">▶ stayed</span>';
}

function _criticalTable(cm) {
  const rows = (cm && cm.rows) || [];
  const newTxt = (cm && cm.new_critical)
    ? `<div class="cmp-foot"><b>${cm.new_critical}</b> activit${cm.new_critical === 1 ? 'y' : 'ies'} entered the critical path this window.</div>` : '';
  if (!rows.length) return `<p class="cmp-empty">No critical or near-critical activity moved this window.</p>${newTxt}`;
  const body = rows.map(r => `<tr>
    <td class="mono">${escapeHtml(r.activity_id)}</td>
    <td>${escapeHtml(r.activity_name)}</td>
    <td class="num mono mut">${escapeHtml(r.prev_finish)}</td>
    <td class="num mono">${escapeHtml(r.curr_finish)}</td>
    <td class="num">${r.slip_days > 0 ? `<span class="cmp-pill bad">+${r.slip_days} wd</span>` : '<span class="cmp-pill">—</span>'}</td>
    <td class="num">${r.float_days == null ? '—' : r.float_days + ' d'}</td>
    <td>${_driverTag(r.driver)}</td>
    <td>${_critStatus(r.critical_status)}</td>
  </tr>`).join('');
  return `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-table">
    <thead><tr><th>Activity ID</th><th>Activity name</th><th class="num">Finish (prev)</th>
      <th class="num">Finish (now)</th><th class="num">Slip</th><th class="num">Float</th>
      <th>Driver this period</th><th>Critical</th></tr></thead>
    <tbody>${body}</tbody></table></div>
    <div class="cmp-foot">Critical &amp; near-critical (float ≤ 10 wd) activities whose finish moved this window. Slip = working-day movement of the finish between the two updates. <b>▶ new</b> = entered the critical path this window.</div>${newTxt}`;
}

const _BUCKETS = [
  ['finished', 'good', 'Completed this period'],
  ['started', 'good', 'First progress recorded this period'],
  ['slipped', 'bad', 'Finish date moved later vs last update'],
  ['stalled', 'warn', 'Scheduled to progress, but 0% earned this period'],
  ['re_sequenced', 'neu', 'Logic / lag changed vs last period'],
];

function _bucketsTable(buck) {
  const counts = (buck && buck.counts) || {};
  const body = _BUCKETS.map(([key, cls, detail]) =>
    `<tr><td><span class="cmp-pill ${cls === 'neu' ? '' : cls}">${escapeHtml(key.replace('_', '-'))}</span></td>
       <td class="num"><b>${counts[key] || 0}</b></td><td class="mut">${escapeHtml(detail)}</td></tr>`).join('');
  return `<div class="tblwrap"><table class="audit-table cmp-table">
    <thead><tr><th>What moved</th><th class="num">Count</th><th>Meaning</th></tr></thead>
    <tbody>${body}</tbody></table></div>
    <div class="cmp-foot">“Re-sequenced” reuses the sibling’s logic/lag engine, measured against <b>last period</b> — it catches quiet mid-stream re-planning.</div>`;
}

export function renderPeriodReport(report) {
  _shownReport = report;
  const rep = document.getElementById('per-report');
  if (!rep) return;
  const s = report.summary || {};
  const mismatch = (report.matched_activities === 0)
    ? `<div class="cmp-warn">No activities matched by ID between the two files — is this the right previous update? Nothing can be compared until they line up.</div>` : '';
  rep.innerHTML = `
    ${_fileBar(report)}
    ${mismatch}
    <div class="mod-sec">Executive dashboard — progress this period</div>
    ${_dashboard(s)}
    <div class="mod-sec">Period S-curve — actual vs last period’s forecast</div>
    <div class="cmp-scurve-card">
      <div class="cmp-scurve-legend">
        <span><i style="background:#3b82f6"></i>Actual to date</span>
        <span><i style="background:#f59e0b"></i>Where last period said you’d be</span>
      </div>
      ${_periodScurveSvg(report.scurve)}
      <div class="cmp-scurve-note">The amber line is the previous update’s own forecast; the gap at this data date is the shortfall against your own commitment.</div>
    </div>
    <div class="mod-sec">Progress by activity — % complete this period</div>
    ${_progressTable(report.progress, s)}
    <div class="mod-sec">Critical-path movement in this window</div>
    ${_criticalTable(report.critical_movement)}
    <div class="mod-sec">What moved this period</div>
    ${_bucketsTable(report.buckets)}
    <div class="mod-sec">Milestone finish trend — every update so far</div>
    <div id="per-trend" class="cmp-scurve-card"><div class="cmp-loading">Loading milestone trend…</div></div>
    <div class="mod-sec">Executive conclusion</div>
    <div class="cmp-reco">${escapeHtml(report.conclusion || '')}</div>`;
  _fetchTrend();
}

const _TREND_PALETTE = ['#f87171', '#4ade80', '#3b82f6', '#fbbf24', '#a78bfa', '#f472b6', '#22d3ee', '#fb923c'];

function _fmtMon(ts) {
  const d = new Date(ts);
  return d.toLocaleString('en', { month: 'short' }) + '-' + String(d.getFullYear()).slice(2);
}

function _milestoneTrendSvg(trend) {
  const periods = (trend && trend.periods) || [];
  const series = (trend && trend.series) || [];
  const allTs = [];
  series.forEach(s => (s.finishes || []).forEach(f => { if (f) allTs.push(new Date(f).getTime()); }));
  if (periods.length < 2 || allTs.length < 2) {
    return '<p class="cmp-empty">Not enough stored updates yet to plot a milestone trend — it fills in as you import each period.</p>';
  }
  let tmin = Math.min(...allTs), tmax = Math.max(...allTs);
  if (tmin === tmax) { const pad = 86400000 * 30; tmin -= pad; tmax += pad; }
  const x0 = 60, x1 = 600, y0 = 200, y1 = 24, n = periods.length;
  const xAt = i => x0 + (x1 - x0) * (n <= 1 ? 0 : i / (n - 1));
  const yAt = ts => y0 - (y0 - y1) * ((ts - tmin) / (tmax - tmin));
  let lines = '', dots = '';
  series.forEach((s, si) => {
    const color = _TREND_PALETTE[si % _TREND_PALETTE.length];
    const pts = [];
    (s.finishes || []).forEach((f, i) => { if (f) pts.push(`${xAt(i).toFixed(1)},${yAt(new Date(f).getTime()).toFixed(1)}`); });
    if (pts.length > 1) lines += `<polyline points="${pts.join(' ')}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>`;
    const idxs = (s.finishes || []).map((f, i) => (f ? i : -1)).filter(i => i >= 0);
    if (idxs.length) { const li = idxs[idxs.length - 1]; dots += `<circle cx="${xAt(li).toFixed(1)}" cy="${yAt(new Date(s.finishes[li]).getTime()).toFixed(1)}" r="3.5" fill="${color}"/>`; }
  });
  let yticks = '';
  for (let k = 0; k <= 3; k++) {
    const ts = tmin + (tmax - tmin) * k / 3, y = yAt(ts);
    yticks += `<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" stroke="var(--border)" stroke-dasharray="2 4" opacity="0.5"/>` +
              `<text x="${x0 - 6}" y="${(y + 3).toFixed(1)}" text-anchor="end" style="fill:var(--muted);font-size:9.5px">${_fmtMon(ts)}</text>`;
  }
  const step = Math.max(1, Math.round(n / 6));
  let xlabels = '';
  for (let i = 0; i < n; i += step) {
    xlabels += `<text x="${xAt(i).toFixed(1)}" y="${y0 + 16}" text-anchor="middle" style="fill:var(--muted);font-size:9.5px">${escapeHtml((periods[i] || '').slice(5))}</text>`;
  }
  const svg = `<svg viewBox="0 0 620 232" width="100%" role="img" aria-label="Milestone finish trend across updates">
    ${yticks}
    <line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y0}" stroke="var(--border)"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="var(--border)"/>
    ${lines}${dots}${xlabels}
  </svg>`;
  const legend = series.map((s, si) => `<span><i style="background:${_TREND_PALETTE[si % _TREND_PALETTE.length]}"></i>${escapeHtml(s.name)}</span>`).join('');
  return `<div class="cmp-scurve-legend">${legend}</div>${svg}<div class="cmp-scurve-note">Each line is a milestone’s forecast finish across your imported updates. <b>Rising = slipping later</b>, flat = holding. Fills in as you import more periods.</div>`;
}

async function _fetchTrend() {
  const el = document.getElementById('per-trend');
  if (!el) return;
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/period/trend`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot_id: state.currentSnapshotId }),
    });
    const data = await resp.json();
    el.innerHTML = data.ok ? _milestoneTrendSvg(data.trend)
                           : `<p class="cmp-empty">${escapeHtml(data.error || 'Trend unavailable.')}</p>`;
  } catch {
    el.innerHTML = '<p class="cmp-empty">Could not load the milestone trend.</p>';
  }
}

function _fileBar(report) {
  return `<div class="cmp-files">
    <span class="cmp-file"><span class="k">Previous</span> <b>${escapeHtml(report.prev_file || '—')}</b> · ${escapeHtml(report.data_date_prev || '')}</span>
    <span class="cmp-vs">→</span>
    <span class="cmp-file"><span class="k">Current</span> <b>${escapeHtml(report.update_file || '—')}</b> · ${escapeHtml(report.data_date_now || '')}</span>
  </div>`;
}

// Pure helpers exposed for unit tests.
export { _signPct as signPct, _shortDate as shortDate, _periodScurveSvg as periodScurveSvg,
         _milestoneTrendSvg as milestoneTrendSvg };
