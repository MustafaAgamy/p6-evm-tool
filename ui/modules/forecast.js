// Preview ▸ Weather → Forecast.
// A finish-date forecast page. It does NOT recompute weather — it reuses the
// weather impact Calendar Audit already saved — and combines it with the
// schedule's forecast finish and SPI to project best / likely / worst finish
// dates. Built server-side (p6_evm/forecast.build_forecast) from the result +
// saved weather; this module renders it.
import { state } from './state.js';
import { fmtDate, escapeHtml } from './format.js';

const DAY = 86400000;
const toMs = (s) => { if (!s) return NaN; const t = new Date(String(s).slice(0, 10) + 'T00:00:00').getTime(); return Number.isNaN(t) ? NaN : t; };
const deltaTxt = (d) => (d == null ? '' : (d > 0 ? `+${d} d late` : (d < 0 ? `${d} d early` : 'on baseline')));
const deltaCls = (d) => (d == null ? '' : (d > 0 ? 'bad' : (d < 0 ? 'good' : '')));

export async function renderForecast() {
  const el = document.getElementById('forecast-body');
  if (!el) return;
  if (!state.currentResult) {
    el.innerHTML = `
      <div class="ov-head"><div class="ov-title"><h2>Weather → Forecast</h2></div></div>
      <p class="ov-note">Import a P6 schedule first — the forecast is built from that update's finish date and performance.</p>`;
    return;
  }
  el.innerHTML = `<div class="fc-loading">Building the forecast…</div>`;

  let d;
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/forecast`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot_id: state.currentSnapshotId || null, result: state.currentResult }),
    });
    d = await resp.json();
  } catch (e) {
    el.innerHTML = `<div class="fc-empty">Couldn't build the forecast — ${escapeHtml(String((e && e.message) || e))}.</div>`;
    return;
  }
  if (!d || !d.ok) {
    el.innerHTML = `<div class="fc-empty">Couldn't build the forecast.${d && d.error ? ' ' + escapeHtml(d.error) : ''}</div>`;
    return;
  }

  const r = state.currentResult;
  const scen = d.scenarios || [];
  if (!scen.length) {
    el.innerHTML = `
      <div class="ov-head"><div class="ov-title"><h2>Weather → Forecast</h2></div></div>
      <p class="ov-note">No forecast finish is available for this schedule — it needs a finish milestone (and a baseline) to project a completion date. Earned Value ▸ set the finish milestone, then return here.</p>`;
    return;
  }

  const likely = scen.find((s) => s.key === 'likely') || scen[0];

  // timeline across baseline + every scenario date
  const marks = [];
  const bms = toMs(d.baseline_finish);
  if (!Number.isNaN(bms)) marks.push({ ms: bms, cls: 'base', label: 'Baseline' });
  for (const s of scen) { const ms = toMs(s.date); if (!Number.isNaN(ms)) marks.push({ ms, cls: s.key, label: s.label }); }
  let timeline = '';
  if (marks.length >= 2) {
    const lo = Math.min(...marks.map((m) => m.ms)), hi = Math.max(...marks.map((m) => m.ms));
    const span = hi - lo || DAY;
    const pos = (ms) => `${(((ms - lo) / span) * 100).toFixed(1)}%`;
    timeline = `<div class="fc-timeline">
      <div class="fc-axis"></div>
      ${marks.map((m) => `<div class="fc-mark fc-${m.cls}" style="left:${pos(m.ms)}">
          <span class="fc-mark-dot"></span><span class="fc-mark-lbl">${m.label}<b>${fmtDate(new Date(m.ms).toISOString())}</b></span>
        </div>`).join('')}
    </div>`;
  }

  const cards = scen.map((s) => `
    <div class="fc-card fc-card-${s.key}">
      <div class="fc-card-h">${escapeHtml(s.label)}</div>
      <div class="fc-card-date">${fmtDate(s.date)}</div>
      ${s.delta_days != null ? `<div class="fc-card-delta ${deltaCls(s.delta_days)}">${deltaTxt(s.delta_days)}</div>` : ''}
      <div class="fc-card-basis">${escapeHtml(s.basis)}</div>
    </div>`).join('');

  const weatherLine = d.has_weather
    ? `<div class="fc-weather on"><span class="fc-wx-ic">🌧️</span> Worst case includes <b>+${d.weather_days} day${d.weather_days === 1 ? '' : 's'}</b> of expected weather impact, reused from <b>Calendar Audit</b>'s weather estimate.</div>`
    : `<div class="fc-weather off"><span class="fc-wx-ic">☀️</span> No weather impact applied yet. Set the <b>project location</b> and run weather in <b>Calendar Audit</b> to add a weather-adjusted worst case here — this page reuses that estimate rather than asking twice.</div>`;

  el.innerHTML = `
    <div class="ov-head"><div class="ov-title">
      <h2>Weather → Forecast</h2>
      <div class="ov-chips">
        <span class="ov-chip">${escapeHtml(r.project_name || 'Project')}</span>
        ${d.data_date ? `<span class="ov-chip">data date <b>${escapeHtml(String(d.data_date).slice(0, 10))}</b></span>` : ''}
        ${d.spi != null ? `<span class="ov-chip">SPI <b>${Number(d.spi).toFixed(2)}</b></span>` : ''}
      </div>
    </div></div>

    <div class="fc-hero">
      <div class="fc-hero-k">Likely finish</div>
      <div class="fc-hero-v">${fmtDate(likely.date)}</div>
      ${likely.delta_days != null ? `<div class="fc-hero-delta ${deltaCls(likely.delta_days)}">${deltaTxt(likely.delta_days)} vs baseline ${d.baseline_finish ? fmtDate(d.baseline_finish) : '—'}</div>` : ''}
    </div>
    ${timeline}
    <div class="ov-section-label">Scenarios</div>
    <div class="fc-cards">${cards}</div>
    ${weatherLine}
    <p class="ov-note">Best case is the schedule's own forecast finish. Likely stretches the remaining time by the current <b>SPI</b> (${d.spi != null ? Number(d.spi).toFixed(2) : '—'}). Worst case adds the weather impact from Calendar Audit. A forecast, not a commitment — it moves as you import updates.</p>`;
}
