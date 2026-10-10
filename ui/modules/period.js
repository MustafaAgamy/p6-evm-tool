// Update vs Update — Windows Analysis.
//
// The currently-open schedule is THIS period; the user picks LAST period (auto-
// suggested from history, or browsed). Renders progress vs last period's forecast,
// the activity % variance table and the period S-curve. Critical-path movement,
// what-moved buckets, the milestone trend and exports are added by later sections.
import { state }      from './state.js';
import { showError }  from './render.js';
import { escapeHtml, dateText } from './format.js';
import { getSavedMode } from './appearance.js';
import { showReportPreview } from './preview.js';
import { revealAndRun, revealStage, followRunStages } from './featurereveal.js';

let _shownReport = null;   // the report currently on screen (exports read this)
let _shownTrend = null;    // the milestone trend currently on screen (carried into the PDF)
let _prev = null;          // {prev_path} or {prev_cached_path} assigned for the comparison
let _prevName = null;       // display name of the assigned last-period file (for the inputs bar)
let _curr = null;          // {update_path} when a different CURRENT update was chosen (else the open schedule)
let _critGroup = [null, null];   // the two groupings of the critical-movement charts (null = the default)
let _cpStyle = 'chain';    // critical-path presentation: 'chain' | 'timeline' | 'table' (remembered)
let _perTheme = getSavedMode();   // report-appearance mode for this panel's PDF preview
let _cpMode = 'leaf-parent';   // critical-path grouping — reset to default on each fresh render
try { const s = localStorage.getItem('per_cp_style'); if (s) _cpStyle = s; } catch { /* no storage */ }

function _currName() {
  const p = (_curr && _curr.update_path) || state.currentXmlPath || state.currentCachedPath || '';
  return p.split(/[\\/]/).pop() || 'current schedule';
}

function _signPct(v) {
  if (v == null) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function _shortDate(s) {
  if (!s) return '—';
  return dateText(String(s).slice(0, 10)) || String(s).slice(0, 10);   // 03-Dec.2026 from a DB timestamp
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
    <div class="cmp-note">Two updates of the same project are compared — the tool shows what moved between the two data dates. Either one can be changed with <b>Choose a different file…</b>; nothing runs until you press <b>Run Comparison</b>.</div>
    <div class="per-inputs">
      <span class="per-filebox"><span class="k">Previous update</span>
        <span id="per-prev-suggest" class="per-suggest">Looking for last period…</span>
        <button class="btn-mini" id="per-choose-prev">Choose a different file…</button></span>
      <span class="cmp-vs">→</span>
      <span class="per-filebox"><span class="k">Current update</span>
        <b id="per-curr-name">${escapeHtml(_currName())}</b>
        <button class="btn-mini" id="per-choose-curr">Choose a different file…</button></span>
      <button class="btn-primary" id="per-run-compare" disabled>Run Comparison</button>
    </div>
    <div id="per-report"></div>`;
  document.getElementById('per-choose-prev').addEventListener('click', choosePrev);
  document.getElementById('per-choose-curr').addEventListener('click', chooseCurr);
  document.getElementById('per-run-compare').addEventListener('click', _runCompare);
  if (_prev) {
    // Re-entering with a last-period file already assigned: restore the "ready" inputs
    // state (Run enabled), and if a comparison was already run this session, jump
    // straight back to the cached results rather than forcing a re-run.
    _markPrevAssigned(_prevName);
    if (_shownReport) renderPeriodReport(_shownReport);
  } else {
    _fetchPreviousSuggestion();
  }
}

// Mark a last-period file as assigned: name it in the inputs bar and enable Run.
// Assign-only — the comparison never runs here; it fires only on the Run button.
function _markPrevAssigned(name) {
  if (name) _prevName = name;
  const el = document.getElementById('per-prev-suggest');
  if (el) el.innerHTML = `<b>Last period:</b>&nbsp;${escapeHtml(_prevName || 'selected file')} <span class="cmp-pill good">ready</span>`;
  const run = document.getElementById('per-run-compare');
  if (run) run.disabled = false;
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
    if (_prev) return;   // a file was assigned while we were fetching — don't clobber it
    if (data.ok && data.previous) {
      const p = data.previous;
      // Assign only — the earlier import is staged as the previous update straight away, so
      // Run Comparison is ready to press; the comparison itself runs only on that button.
      _prev = { prev_cached_path: p.cached_path };
      _markPrevAssigned(`${_shortDate(p.data_date)}${p.filename ? ' · ' + p.filename : ''}`);
    } else {
      el.innerHTML = `<span class="mut">No earlier import found for this project — pick the previous file →</span>`;
    }
  } catch {
    if (!_prev) el.innerHTML = `<span class="mut">Pick the previous update file →</span>`;
  }
}

// Assign only — stages the chosen previous update; the comparison runs on Run Comparison.
async function choosePrev() {
  const path = await window.pywebview.api.choose_file();
  if (!path) return;
  _prev = { prev_path: path };
  _markPrevAssigned(path.split(/[\\/]/).pop() || 'selected file');
  _fileChanged();
}

// The same for the CURRENT update (owner: 'one option to change either update') — assign only.
async function chooseCurr() {
  const path = await window.pywebview.api.choose_file();
  if (!path) return;
  _curr = { update_path: path };
  const el = document.getElementById('per-curr-name');
  if (el) el.textContent = _currName();
  _fileChanged();
}

// A file was changed while results are on screen: say so and offer Run — the figures shown
// still belong to the old pair until the comparison is run again.
function _fileChanged() {
  const note = document.getElementById('per-rerun-note');
  if (!note) return;
  note.innerHTML = `<span class="cmp-pill warn">File changed</span> previous: <b>${escapeHtml(_prevName || '—')}</b> · current: <b>${escapeHtml(_currName())}</b> — the results below are still the old pair. <button class="btn-primary" id="per-rerun">Run Comparison</button>`;
  const b = document.getElementById('per-rerun');
  if (b) b.addEventListener('click', _runCompare);
}

async function _runCompare() {
  const body = document.getElementById('period-body');
  const rep = document.getElementById('per-report');
  revealAndRun(body, 'Update vs Update', async () => {
    if (rep) rep.innerHTML = `<div class="cmp-loading">Comparing the two updates…</div>`;
    revealStage('Reading both updates and comparing them');
    const stages = followRunStages(state.serverPort);     // the bar names the server's real step
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/period/compare`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ..._prev,
          ...(_curr ? { update_path: _curr.update_path, cached_path: null }
                    : { update_path: state.currentXmlPath, cached_path: state.currentCachedPath }),
          run_id: stages.id,
        }),
      }).finally(stages.stop);
      const data = await resp.json();
      if (!data.ok) { if (rep) rep.innerHTML = `<div class="cmp-warn">${escapeHtml(data.error || 'Comparison failed.')}</div>`; return; }
      renderPeriodReport(data.report);
    } catch {
      if (rep) rep.innerHTML = `<div class="cmp-warn">Could not reach the local server to run the comparison.</div>`;
    }
  });
}

// ── Report render ───────────────────────────────────────────────────────────

function _kpi(label, value, sub, cls) {
  return `<div class="kpi"><div class="k">${escapeHtml(label)}</div>` +
         `<div class="v">${value}</div>` +
         (sub ? `<div class="per-kpi-sub ${cls || ''}">${sub}</div>` : '') + `</div>`;
}

const _shortDD = d => (d || '').replace(/-\d{4}$/, '');           // 30-Jun-2026 → 30-Jun
const _spiTxt = v => (v == null ? '—' : Math.round(v * 100) + '%');   // SPI as a whole percentage
const _wdTxt = v => (v == null ? '—' : `${v} wd`);

// A Previous → Current → Variance strip. `good` colours the variance cell (green/red).
function _trendStrip(pK, pWhen, pV, cK, cWhen, cV, varStr, good, badge) {
  const cls = good ? 'good' : 'bad';
  const cell = (k, when, v) => `<div class="per-tcell"><div class="per-tk">${escapeHtml(k)}` +
    (when ? ` <span class="per-twhen">· ${escapeHtml(when)}</span>` : '') + `</div><div class="per-tv">${v}</div></div>`;
  return `<div class="per-strip">
    ${cell(pK, pWhen, pV)}${cell(cK, cWhen, cV)}
    <div class="per-tcell per-tvar ${cls}"><div class="per-tk">Variance</div><div class="per-tv">${varStr}</div>` +
    (badge ? `<span class="per-tbadge ${cls}">${escapeHtml(badge)}</span>` : '') + `</div>
  </div>`;
}

const _byCost = report => ((report || {}).summary || {}).pct_basis === 'cost';
const _money = v => (v == null ? '—' : Math.round(v).toLocaleString('en-US'));
const _moneyShort = v => (Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(2) + ' B' : (Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + ' M' : _money(v)));
const _signNum = v => (v == null ? '—' : (v > 0 ? '+' : '') + Math.round(v).toLocaleString('en-US'));

function _dashboard(report) {
  const s = report.summary || {};
  const pw = `to ${_shortDD(report.data_date_prev)}`, cw = `to ${_shortDD(report.data_date_now)}`;
  const cutoff = `<div class="per-cutoff">Comparison window · <b>${escapeHtml(report.data_date_prev || '—')}</b> <span class="mut">(previous cutoff)</span> → <b>${escapeHtml(report.data_date_now || '—')}</b> <span class="mut">(current cutoff)</span></div>`;

  // % Complete (higher = better) — the Performance % of the cost-loaded activities when both carry cost
  const pctGood = (s.period_earned || 0) >= 0;
  const cost = _byCost(report);
  const pct = _trendStrip(cost ? 'Previous Performance %' : 'Previous % Complete', pw, `${s.actual_prev}%`,
    cost ? 'Current Performance %' : 'Current % Complete', cw, `${s.actual_now}%`,
    `${pctGood ? '▲' : '▼'} ${_signPct(s.period_earned)}`, pctGood, pctGood ? 'Progressed this period' : 'Went backwards');

  // SPI (higher = better)
  let spi = '';
  if (s.prev_spi != null || s.curr_spi != null) {
    const v = s.spi_variance, good = v == null ? true : v >= 0;
    const vs = v == null ? '—' : `${v > 0 ? '▲ +' : (v < 0 ? '▼ ' : '• ')}${Math.round(v * 100)}%`;
    spi = `<div class="per-striplabel">Schedule Performance Index (SPI)</div>` +
      _trendStrip('Previous SPI', pw, _spiTxt(s.prev_spi), 'Current SPI', cw, _spiTxt(s.curr_spi), vs, good,
        v == null ? '' : (good ? 'SPI improved' : 'SPI worsened'));
  }

  // Delay (lower = better)
  let delay = '';
  if (s.delay_prev != null || s.delay_now != null) {
    const v = s.delay_change, good = v == null ? true : v <= 0;
    const vs = v == null ? '—' : `${v > 0 ? '▲ +' : (v < 0 ? '▼ ' : '• ')}${v} wd`;
    delay = `<div class="per-striplabel">Delay vs baseline</div>` +
      _trendStrip('Previous delay', pw, _wdTxt(s.delay_prev), 'Current delay', cw, _wdTxt(s.delay_now), vs, good,
        v == null ? '' : (v > 0 ? 'Delay grew' : (v < 0 ? 'Delay reduced' : 'No change')));
  }

  // Forecast finish (both cutoffs; earlier finish = better)
  const slip = s.finish_slip_days;
  const fgood = (slip || 0) <= 0;
  const fvar = slip == null ? '—' : (slip > 0 ? `▼ slipped ${slip} d` : (slip < 0 ? `▲ pulled in ${-slip} d` : '• no change'));
  const finish = `<div class="per-striplabel">Forecast finish</div>` +
    _trendStrip('Previous forecast', pw, escapeHtml(s.forecast_finish_prev || '—'),
      'Current forecast', cw, escapeHtml(s.forecast_finish_now || '—'), fvar, fgood,
      slip == null ? '' : (fgood ? 'Held or pulled in' : 'Finish slipped'));

  return `${cutoff}
    <div class="per-striplabel">${cost ? 'Performance % (Earned Value ÷ Budget of the cost-loaded activities)' : 'Overall % Complete'} — Current vs Previous</div>${pct}
    ${spi}${delay}${finish}
    ${_recoveryHtml(report)}
    ${_factsHtml(report)}
    ${_defsHtml()}`;
}

// Plain-English definitions so a non-planner can read the report unaided.
function _defsHtml() {
  const defs = [
    ['Forecast achievement', 'how much of what you forecast last period you actually delivered (100% = hit your plan; 78% = about three-quarters).'],
    ['Schedule adherence', 'of the activities that were due to finish this period, how many actually finished (72% = 13 of 18).'],
    ['Started this period', 'activities that got underway this period (recorded their first progress).'],
    ['New critical activities', 'activities that became critical this period — any delay to them now pushes the project finish date.'],
  ];
  return `<div class="per-defs"><div class="per-defs-h">What these numbers mean</div>` +
    defs.map(([a, b]) => `<div class="per-def"><b>${escapeHtml(a)}</b> — ${escapeHtml(b)}</div>`).join('') + `</div>`;
}

// Progress bar (replaces the S-curve): fill to actual, marker at last-update forecast,
// plus the forecast-vs-actual bars for the period.
function _progressBarHtml(report) {
  const s = report.summary || {};
  const ap = s.actual_prev, an = s.actual_now, fn = s.forecast_at_now, pe = s.period_earned, pf = s.period_forecast;
  if (an == null) return '<p class="cmp-empty">No progress figures for this period.</p>';
  const d1 = v => (Math.round(v * 10) / 10).toFixed(1);
  const clamp = v => Math.max(0, Math.min(100, v));
  const fill = clamp(an);
  // the markers above the bar: labels that would sit on each other step up a line, and a label
  // near either end is anchored to that end so it is never cut off
  const tags = [];
  if (ap != null) tags.push([clamp(ap), `start ${d1(ap)}%`, 'var(--muted)']);
  if (fn != null) tags.push([clamp(fn), `planned ${d1(fn)}%`, 'var(--warning)']);
  const ach = s.forecast_achievement == null ? '—' : Math.round(s.forecast_achievement * 100) + '%';
  const behind = fn == null ? '' : ` — <b>${(fn - an) <= 0 ? 'on/ahead of' : d1(Math.abs(fn - an)) + '% behind'}</b> your plan`;
  const planTxt = fn == null ? '' : `Your last update planned <b>${d1(fn)}%</b> by now (${_signPct(pf)}). `;
  const bp = _byCost(report) ? s.planned_now : null;        // the baseline plan at this cut-off
  if (bp != null) tags.push([clamp(bp), `baseline plan ${d1(bp)}%`, 'var(--danger)']);
  tags.sort((a, b) => a[0] - b[0]);
  const lastAt = [];                                         // per line: the position of its last label
  let lines = 1;
  const marks = tags.map(([pos, txt, col]) => {
    let lv = 0;
    while (lastAt[lv] != null && pos - lastAt[lv] < 17) lv++;
    lastAt[lv] = pos; lines = Math.max(lines, lv + 1);
    const tr = pos > 86 ? 'translateX(-100%)' : (pos < 10 ? 'translateX(0)' : 'translateX(-50%)');
    return `<div class="per-pmark" style="left:${pos}%;background:${col};top:${-5 - 15 * lv}px"></div>`
      + `<span class="per-tag-above" style="left:${pos}%;color:${col};top:${-22 - 15 * lv}px;transform:${tr}">▾ ${txt}</span>`;
  }).join('');
  const what = _byCost(report) ? 'All are <b>Performance %</b> — Earned Value ÷ Budget of the cost-loaded activities, as P6 shows it'
    : 'All three are % of the whole project';
  const baseTxt = bp == null ? '' : ` The baseline planned <b>${d1(bp)}%</b> by this cut-off.`;
  return `<div class="cmp-scurve-card per-prog">
    <div class="per-pbtop"><span>0% — start</span><span>100% — finish</span></div>
    <div class="per-pbar" style="margin-top:${15 * (lines - 1)}px"><div class="per-pfill" style="width:${fill}%">${d1(an)}%</div>
      <span class="per-tag-below" style="left:${fill}%">▴ now ${d1(an)}%</span>${marks}</div>
    <div class="per-psent">On <b>${escapeHtml(report.data_date_prev || '—')}</b> you were at <b>${ap != null ? d1(ap) : '—'}%</b>. ${planTxt}You reached <b>${d1(an)}%</b> on <b>${escapeHtml(report.data_date_now || '—')}</b> (${_signPct(pe)}). ${what}${behind}; you did ${_signPct(pe)} of ${_signPct(pf)} = <b>${ach}</b>.${baseTxt}</div>
  </div>`;
}

// ── Earned Value — before, after and variance (comments 68–73, round 2) ──
function _evBridgeSvg(s, pdd, cdd) {
  const a = s.ev_prev, b = s.ev_now, top = Math.max(a, b, 1), base = 150, hh = 100;
  const y = v => base - hh * v / top, d = b - a, col = d >= 0 ? 'var(--success)' : 'var(--danger)';
  const ya = y(a), yb = y(b), dy = Math.min(ya, yb), dh = Math.max(Math.abs(ya - yb), 2);
  const t = (x, yy, txt, size = 11, fill = 'var(--muted)', w = 400) =>
    `<text x="${x}" y="${yy.toFixed(0)}" text-anchor="middle" font-size="${size}" font-weight="${w}" fill="${fill}">${txt}</text>`;
  const pct = v => (v == null ? '—' : v + '%');
  return `<svg viewBox="0 0 700 190" width="100%" style="max-height:250px" role="img" aria-label="Earned Value bridge">
    <line x1="40" y1="${base}" x2="660" y2="${base}" stroke="var(--border)" stroke-width="1.5"/>
    <rect x="70" y="${ya.toFixed(0)}" width="130" height="${(base - ya).toFixed(0)}" rx="2" fill="var(--muted)"/>
    <line x1="200" y1="${ya.toFixed(0)}" x2="285" y2="${ya.toFixed(0)}" stroke="var(--muted)" stroke-dasharray="4 4"/>
    <rect x="285" y="${dy.toFixed(0)}" width="130" height="${dh.toFixed(0)}" rx="2" fill="${col}"/>
    <line x1="415" y1="${yb.toFixed(0)}" x2="500" y2="${yb.toFixed(0)}" stroke="var(--muted)" stroke-dasharray="4 4"/>
    <rect x="500" y="${yb.toFixed(0)}" width="130" height="${(base - yb).toFixed(0)}" rx="2" fill="var(--chart-1)"/>`
    + t(135, ya - 6, _money(a), 12.5, 'var(--text)', 700) + t(350, dy - 6, _signNum(d), 12.5, col, 700) + t(565, yb - 6, _money(b), 12.5, 'var(--text)', 700)
    + t(135, base + 15, 'Earned Value — previous') + t(135, base + 29, `${escapeHtml(pdd)} · ${pct(s.actual_prev)}`)
    + t(350, base + 15, 'Earned this period') + t(350, base + 29, `${_signPct(s.period_earned)} of the budget`)
    + t(565, base + 15, 'Earned Value — current') + t(565, base + 29, `${escapeHtml(cdd)} · ${pct(s.actual_now)}`) + `</svg>`;
}
function _evHtml(report) {
  const s = report.summary || {};
  if (!_byCost(report) || s.ev_now == null || s.ev_prev == null) return '';
  const pdd = report.data_date_prev || '—', cdd = report.data_date_now || '—', pe = s.period_earned;
  const f2 = v => (v == null ? '—' : v.toFixed(2));
  const tile = (k, v, f, cls) => `<div class="kpi"><div class="k">${escapeHtml(k)}</div><div class="v ${cls || ''}">${v}</div><div class="per-kpi-sub mut">${escapeHtml(f)}</div></div>`;
  const vcell = (txt, good) => `<td class="num">${good == null ? txt : `<span class="${good ? 'per-slip-good' : 'per-slip-bad'}">${txt}</span>`}</td>`;
  const row = (l, a, b, v, bold) => `<tr><td>${bold ? `<b>${l}</b>` : l}</td><td class="num mono">${a}</td><td class="num mono">${b}</td>${v}</tr>`;
  const slip = s.finish_slip_days, spv = s.spi_variance;
  const slipTxt = slip == null ? '—' : (slip > 0 ? `${slip} days later` : (slip < 0 ? `${-slip} days earlier` : 'no change'));
  const budgetNote = (s.bac_prev != null && s.bac != null && Math.abs(s.bac_prev - s.bac) >= 1)
    ? `<div class="cmp-foot">The budget itself changed between the two updates: ${_money(s.bac_prev)} → ${_money(s.bac)}. Each Performance % is against its own update's budget.</div>` : '';
  const reading = (s.pv_variance > 0 && s.ev_of_pv_period != null)
    ? `<div class="cmp-foot"><b>Reading:</b> the plan asked for ${_moneyShort(s.pv_variance)} of work in this period; ${_moneyShort(s.ev_variance)} was earned — ${Math.round(s.ev_of_pv_period * 100)}% of what the period needed.</div>` : '';
  return `<div class="mod-sec">Earned Value — before, after and variance</div>
    <div class="cmp-foot" style="margin:0 0 8px"><b>Performance %</b> = Earned Value ÷ Budget of the cost-loaded activities (${_money(s.cost_activities)} of ${_money(s.all_activities)} activities; Budget <b>${_money(s.bac)}</b>) — the figure P6 shows as Performance % Complete. Activities without cost take no part.</div>${budgetNote}
    <div class="cmp-kpis">
      ${tile(`Performance % — previous · ${pdd}`, `${s.actual_prev}%`, 'Earned Value ÷ Budget')}
      ${tile(`Performance % — current · ${cdd}`, `${s.actual_now}%`, 'Earned Value ÷ Budget')}
      ${tile('Variance — earned this period', _signPct(pe), s.period_days != null ? `in ${s.period_days} calendar days` : 'between the two cut-offs', (pe || 0) >= 0 ? 'per-good' : 'per-bad')}
    </div>
    <div class="cmp-scurve-card" style="margin-top:10px">${_evBridgeSvg(s, pdd, cdd)}</div>
    <div class="tblwrap" style="overflow-x:auto;margin-top:10px"><table class="audit-table cmp-table">
      <thead><tr><th>Figure</th><th class="num">Previous · ${escapeHtml(pdd)}</th><th class="num">Current · ${escapeHtml(cdd)}</th><th class="num">Variance</th></tr></thead><tbody>
      ${row('Earned Value', _money(s.ev_prev), _money(s.ev_now), vcell(_signNum(s.ev_variance), s.ev_variance >= 0), true)}
      ${row('Planned Value', _money(s.pv_prev), _money(s.pv_now), vcell(_signNum(s.pv_variance)))}
      ${row('Performance % (Earned Value ÷ Budget)', `${s.actual_prev}%`, `${s.actual_now}%`, vcell(_signPct(pe), (pe || 0) >= 0), true)}
      ${row('Planned %', `${s.planned_prev}%`, `${s.planned_now}%`, vcell(_signPct(s.planned_variance)))}
      ${row('SPI (Earned Value ÷ Planned Value)', f2(s.prev_spi), f2(s.curr_spi), vcell(spv == null ? '—' : (spv > 0 ? '+' : '') + spv.toFixed(2), spv == null ? null : spv >= 0))}
      ${row('Forecast finish', escapeHtml(s.forecast_finish_prev || '—'), escapeHtml(s.forecast_finish_now || '—'), vcell(slipTxt, slip == null ? null : slip <= 0))}
      </tbody></table></div>${reading}
    <div class="cmp-foot"><b>Where each figure is in P6:</b> Earned Value = the sum of the column “Earned Value Cost” (each activity's Performance % Complete × its baseline budget); Budget = “Budget At Completion”, the baseline's Budgeted Total Cost; Performance % = one ÷ the other. Planned Value, Planned % and SPI are worked out by the tool from the baseline dates and budget — P6 does not write them into the exported file, so its own “Planned Value Cost” can differ slightly.</div>
    ${_evCodeHtml(report)}`;
}

// Critical-path comparison — the driving path to the finish, grouped by WBS level or
// activity code (dropdown), with the CURRENT path red from where it diverges.
function _cpKey(a, mode) {
  if (mode.indexOf('code:') === 0) return ((a.codes || {})[mode.slice(5)]) || '(no code)';
  const segs = (a.wbs_path || '').split(' > ').map(s => s.trim()).filter(Boolean);
  if (!segs.length) return '(no WBS)';
  if (mode.indexOf('wbs') === 0) { const i = parseInt(mode.slice(3), 10); return segs[i] || segs[segs.length - 1]; }
  return segs.length >= 2 ? segs[segs.length - 2] : segs[segs.length - 1];   // leaf-parent
}
// Group consecutive driving-path activities into dated segments (WBS level or code).
// Critical-path comparison as a connected chain of blocks (simpler than the date-axis
// timeline): ONE row when the route is unchanged, two aligned rows (old greyed, new red)
// only when it reroutes. The blocks sit end-to-end; each shows the months it spans.
function _cpSegments(acts, mode) {
  const segs = [];
  for (const a of acts) {
    const k = _cpKey(a, mode), st = a.start || null, fn = a.finish || null;
    const last = segs[segs.length - 1];
    if (last && last.key === k) {
      if (st && (!last.start || st < last.start)) last.start = st;
      if (fn && (!last.finish || fn > last.finish)) last.finish = fn;
    } else segs.push({ key: k, start: st, finish: fn });
  }
  return segs;
}
function _cpConclusion(prev, curr, div, summary) {
  const fn = summary.forecast_finish_now, slip = summary.finish_slip_days;
  const route = (segs, a) => segs.slice(a).map(s => s.key).join(' → ') || '—';
  if (div < curr.length || div < prev.length) {                 // the route rerouted
    const at = div > 0 ? curr[div - 1].key : 'the start';
    let h = `Your critical path <b>rerouted at ${escapeHtml(at)}</b> — it used to finish through <b>${escapeHtml(route(prev, div))}</b>; now it runs <b>${escapeHtml(route(curr, div))}</b>`;
    if (slip > 0) h += `, slipping the finish <b>+${slip} days to ${escapeHtml(fn || '—')}</b>.`;
    else if (slip < 0) h += `, pulling the finish in <b>${Math.abs(slip)} days to ${escapeHtml(fn || '—')}</b>.`;
    else if (fn) h += `, with the finish holding at <b>${escapeHtml(fn)}</b>.`;
    else h += '.';
    return h;
  }
  let h = `<b>Same critical path as last period.</b> It runs <b>${escapeHtml(route(curr, 0))}</b> and drives your finish on <b>${escapeHtml(fn || '—')}</b>`;
  if (slip > 0) h += ` (slipped ${slip} day${slip !== 1 ? 's' : ''} this period).`;
  else if (slip < 0) h += ` (pulled in ${Math.abs(slip)} day${Math.abs(slip) !== 1 ? 's' : ''} this period).`;
  else h += '.';
  return h;
}
function _cpTimelineData(prevA, currA, summary, mode) {
  if (!prevA.length && !currA.length) return null;
  const prev = _cpSegments(prevA, mode), curr = _cpSegments(currA, mode);
  let div = 0; while (div < prev.length && div < curr.length && prev[div].key === curr[div].key) div++;
  return { prev, curr, divergence: div, changed: div < prev.length || div < curr.length,
           finishPrev: summary.forecast_finish_prev, finishNow: summary.forecast_finish_now,
           slip: summary.finish_slip_days, conclusion: _cpConclusion(prev, curr, div, summary) };
}
function _spanLabel(aIso, bIso) {
  const p = iso => { const t = Date.parse(iso); return Number.isNaN(t) ? null : new Date(t); };
  let a = p(aIso), b = p(bIso);
  if (!a && !b) return '';
  a = a || b; b = b || a;
  const mon = d => d.toLocaleString('en', { month: 'short' }), yy = d => String(d.getFullYear()).slice(2);
  if (a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()) return `${mon(a)} ${a.getFullYear()}`;
  if (a.getFullYear() === b.getFullYear()) return `${mon(a)} – ${mon(b)} ${b.getFullYear()}`;
  return `${mon(a)} ${yy(a)} – ${mon(b)} ${yy(b)}`;
}
function _cpWidths(prev, curr, div) {
  const days = s => { const d = (Date.parse(s.finish) - Date.parse(s.start)) / 8.64e7; return (Number.isFinite(d) && d > 0) ? d : 30; };
  const pd = div <= curr.length ? div : curr.length;
  const prefix = curr.slice(0, pd).map(days), currTail = curr.slice(pd).map(days);
  const prevTail = (div <= prev.length ? prev.slice(div) : []).map(days);
  const sum = arr => arr.reduce((x, y) => x + y, 0);
  const widest = Math.max(sum(prefix) + sum(currTail), sum(prefix) + sum(prevTail), 1);
  // room for the block's own name on about two lines (it wraps inside the block) — the same
  // rule as the report (p6_period/exporters._cp_widths): a 58 px block used to cut a long name
  const floor = s => Math.min(150, Math.max(58, Math.floor(String(s.key || '').length * 6.2 / 2) + 14));
  const scale = 620 / widest, px = (w, s) => Math.max(floor(s), Math.round(w * scale));
  const prevSegs = div <= prev.length ? prev.slice(div) : [];
  const pre = prefix.map((w, i) => px(w, curr[i]));
  return [pre.concat(prevTail.map((w, i) => px(w, prevSegs[i]))), pre.concat(currTail.map((w, i) => px(w, curr[pd + i])))];
}
function _cpChainHtml(segs, widths, div, tailRole, flagRole, finishDate) {
  let out = '';
  segs.forEach((s, i) => {
    const role = i < div ? 'shared' : tailRole;
    const lab = _spanLabel(s.start, s.finish), sub = lab ? `<small>${escapeHtml(lab)}</small>` : '';
    const w = i < widths.length ? widths[i] : 80;
    out += `<div class="cpblk ${role}" style="width:${w}px">${escapeHtml(s.key)}${sub}</div>`;
    if (i < segs.length - 1) out += `<div class="cparw${tailRole === 'new' && i >= div - 1 ? ' new' : ''}">→</div>`;
  });
  out += `<div class="cparw${tailRole === 'new' && div < segs.length ? ' new' : ''}">→</div>`;
  out += `<div class="cpflag ${flagRole}"><span class="cpdia ${flagRole}"></span><b>${escapeHtml(finishDate || '—')}</b><span class="cpfl">finish</span></div>`;
  return `<div class="cpchain">${out}</div>`;
}
// --- Style 1: connected chain (the conclusion is added by _cpCompareBody) ---
function _cpChainBody(data) {
  const { prev, curr, divergence: div } = data;
  const [wprev, wcurr] = _cpWidths(prev, curr, div);
  if (!data.changed) {
    return `<div class="cprowlbl">This period's critical path</div>`
      + _cpChainHtml(curr, wcurr, curr.length, 'new', 'now', data.finishNow)
      + `<div class="cmp-foot">One row — the route is the same as last period. The blocks sit end-to-end as a chain, each labelled with the months it spans.</div>`;
  }
  const slip = data.slip;
  const slipnote = slip ? `<div class="cpslip">↳ the finish moved ${slip > 0 ? '+' : ''}${slip} working days (the Now chain runs ${slip > 0 ? 'longer' : 'shorter'} than the old one).</div>` : '';
  const legend = `<div class="cmp-foot"><span class="cpsw" style="background:var(--chart-1)"></span>shared route (unchanged) <span class="cpsw" style="background:var(--danger)"></span>new route (from the reroute) <span class="cpsw" style="background:var(--border)"></span>old route (dropped off)</div>`;
  return `<div class="cprowlbl">Was — last update</div>` + _cpChainHtml(prev, wprev, div, 'gone', 'was', data.finishPrev)
    + `<div class="cprowlbl" style="margin-top:9px">Now — this update</div>` + _cpChainHtml(curr, wcurr, div, 'new', 'now', data.finishNow)
    + slipnote + legend
    + `<div class="cmp-foot">Two rows because the route changed — they line up at the reroute point; the old route is greyed, the new route red, and the finish flags sit further apart the bigger the slip.</div>`;
}
// --- Style 2: date-axis Gantt timeline (mirrors the PDF exporter) ---
function _cpTimelineSvg(data, report) {
  const { prev, curr, divergence: div } = data;
  const ord = iso => { const t = Date.parse(iso); return Number.isNaN(t) ? null : Math.round(t / 8.64e7); };
  const UNIT = 20;
  const layout = segs => { const pos = []; let cur = null; segs.forEach(s => { let a = ord(s.start), b = ord(s.finish); let start = a != null ? a : (cur != null ? cur : 0); if (cur != null && start < cur) start = cur; const end = (b != null && b > start) ? b : start + UNIT; pos.push([start, end]); cur = end; }); return pos; };
  const pprev = layout(prev), pcurr = layout(curr);
  const xs = pprev.concat(pcurr).flat();
  if (!xs.length) return '<div class="cmp-foot">The driving path has no dates to place on a timeline.</div>';
  let tmin = Math.min(...xs), tmax = Math.max(...xs); if (tmax <= tmin) tmax = tmin + UNIT;
  const x0 = 160, x1 = 830, xat = t => x0 + (x1 - x0) * (t - tmin) / (tmax - tmin);
  const FILL = { same: 'var(--chart-1)', new: 'var(--danger)', gone: 'var(--border)' }, INK = { same: 'var(--text)', new: '#ffffff', gone: 'var(--muted)' };
  let p = '';
  for (let k = 0; k < 5; k++) { const t = tmin + (tmax - tmin) * k / 4, x = xat(t), d = new Date(t * 8.64e7); const lab = d.toLocaleString('en', { month: 'short' }) + '-' + String(d.getFullYear()).slice(2); p += `<line x1="${x.toFixed(0)}" y1="40" x2="${x.toFixed(0)}" y2="222" stroke="var(--chart-grid)"/><text x="${x.toFixed(0)}" y="238" text-anchor="middle" font-size="9" fill="var(--chart-axis)">${lab}</text>`; }
  const draw = (segs, pos, y, isCurr) => segs.forEach((s, i) => {
    const role = i < div ? 'same' : (isCurr ? 'new' : 'gone');
    const x = xat(pos[i][0]), w = Math.max(6, xat(pos[i][1]) - xat(pos[i][0]));
    p += `<rect x="${x.toFixed(0)}" y="${y}" width="${w.toFixed(0)}" height="24" rx="4" fill="${FILL[role]}"/>`;
    const cap = Math.floor(w / 6.5);
    if (w >= 34 && cap >= 3) { const lab = s.key.length <= cap ? s.key : s.key.slice(0, cap - 1) + '…'; p += `<text x="${(x + w / 2).toFixed(0)}" y="${y + 16}" text-anchor="middle" font-size="10" fill="${INK[role]}">${escapeHtml(lab)}</text>`; }
  });
  draw(prev, pprev, 60, false); draw(curr, pcurr, 120, true);
  p += `<text x="14" y="74" font-size="11" font-weight="700" fill="var(--muted)">WAS · ${escapeHtml(report.data_date_prev || '')}</text>`;
  p += `<text x="14" y="134" font-size="11" font-weight="700" fill="var(--text)">NOW · ${escapeHtml(report.data_date_now || '')}</text>`;
  if (pprev.length) { const fx = xat(pprev[pprev.length - 1][1]); p += `<path d="M${fx.toFixed(0)},72 l7,-7 l7,7 l-7,7 z" fill="var(--muted)"/><text x="${(fx + 18).toFixed(0)}" y="58" font-size="9.5" fill="var(--muted)">finish ${escapeHtml(data.finishPrev || '')}</text>`; }
  if (pcurr.length) { const gx = xat(pcurr[pcurr.length - 1][1]); p += `<path d="M${gx.toFixed(0)},132 l7,-7 l7,7 l-7,7 z" fill="var(--danger)"/><text x="${(gx + 18).toFixed(0)}" y="118" font-size="9.5" fill="var(--danger)" font-weight="700">finish ${escapeHtml(data.finishNow || '')}</text>`; }
  const slip = data.slip;
  if (pprev.length && pcurr.length && slip) { const a = xat(pprev[pprev.length - 1][1]), b = xat(pcurr[pcurr.length - 1][1]), lo = Math.min(a, b), hi = Math.max(a, b); p += `<line x1="${lo.toFixed(0)}" y1="196" x2="${hi.toFixed(0)}" y2="196" stroke="var(--danger)" stroke-width="1.5"/><line x1="${lo.toFixed(0)}" y1="192" x2="${lo.toFixed(0)}" y2="200" stroke="var(--danger)"/><line x1="${hi.toFixed(0)}" y1="192" x2="${hi.toFixed(0)}" y2="200" stroke="var(--danger)"/><text x="${((lo + hi) / 2).toFixed(0)}" y="212" text-anchor="middle" font-size="10.5" fill="var(--danger)" font-weight="700">${slip > 0 ? '+' : ''}${slip} wd</text>`; }
  if (div < curr.length || div < prev.length) { const src = div < pcurr.length ? pcurr[div][0] : (div < pprev.length ? pprev[div][0] : null); if (src != null) { const dx = xat(src); p += `<line x1="${dx.toFixed(0)}" y1="52" x2="${dx.toFixed(0)}" y2="168" stroke="var(--danger)" stroke-width="1" stroke-dasharray="3 3"/><text x="${dx.toFixed(0)}" y="182" text-anchor="middle" font-size="9.5" fill="var(--danger)" font-weight="700">rerouted here</text>`; } }
  const legend = `<div class="cmp-foot"><span class="cpsw" style="background:var(--chart-1)"></span>shared route (on both) <span class="cpsw" style="background:var(--danger)"></span>new critical route (from the reroute) <span class="cpsw" style="background:var(--border)"></span>old route (dropped off)</div>`;
  return `<svg viewBox="0 0 960 250" width="100%" role="img" aria-label="Critical path timeline">${p}</svg>${legend}<div class="cmp-foot">The finish-driving route on a real date axis — <b>WAS</b> (last update) over <b>NOW</b> (this update). The bracket at the right is the total finish movement.</div>`;
}
// --- Style 3: compact Was/Now table ---
function _cpTableHtml(data) {
  const { prev, curr, divergence: div } = data;
  const plain = segs => segs.map(s => escapeHtml(s.key)).join(' → ') || '—';
  const redtail = segs => segs.map((s, i) => i >= div ? `<span class="cpt-red">${escapeHtml(s.key)}</span>` : escapeHtml(s.key)).join(' → ') || '—';
  const slip = data.slip;
  let fintail = '';
  if (slip > 0) fintail = ` <span class="cpt-red">(+${slip} wd)</span>`;
  else if (slip < 0) fintail = ` <span class="cpt-red">(${slip} wd)</span>`;
  const rerouted = data.changed
    ? `<span class="cpt-red">${div > 0 ? escapeHtml(curr[div - 1].key) : 'the start'}</span> <span class="cpt-mut">(was: ${plain(prev.slice(div))})</span>`
    : '— <span class="cpt-mut">(unchanged this period)</span>';
  return `<table class="cptable"><tr><th></th><th>Was — last update</th><th>Now — this update</th></tr>`
    + `<tr><td class="cpt-k">Driving route</td><td>${plain(prev)}</td><td>${redtail(curr)}</td></tr>`
    + `<tr><td class="cpt-k">Forecast finish</td><td>${escapeHtml(data.finishPrev || '—')}</td><td class="cpt-fin">${escapeHtml(data.finishNow || '—')}${fintail}</td></tr>`
    + `<tr><td class="cpt-k">Rerouted at</td><td>—</td><td>${rerouted}</td></tr></table>`
    + `<div class="cmp-foot">The finish-driving route as text — the most compact style; the new part of the route is in red.</div>`;
}
// Conclusion + the chosen style live here, so the pickers just re-render this into #per-cp-chains.
function _cpCompareBody(report, mode, style) {
  const cp = report.critical_path || {};
  const data = _cpTimelineData(cp.previous || [], cp.current || [], report.summary || {}, mode);
  if (!data) return '<p class="cmp-empty">No driving path to the finish milestone could be derived.</p>';
  const concl = `<div class="cpconcl ${data.changed ? 'warn' : 'good'}"><span class="cpic">${data.changed ? '⚠' : '✓'}</span><div>${data.conclusion}</div></div>`;
  const body = style === 'timeline' ? _cpTimelineSvg(data, report)
    : style === 'table' ? _cpTableHtml(data)
    : _cpChainBody(data);
  return concl + body;
}
// The three ways the route can be drawn, what each shows and when to use it — the chosen one
// is outlined; a click picks it (owner: 'clarify the differences of the style types').
const _CP_STYLES = [
  ['chain', '1 · Connected chain', 'the route as blocks joined one after another; the new part in red.', 'you want to read the logic — what leads to what.',
   `<rect x="2" y="18" width="70" height="22" rx="4" fill="none" stroke="var(--chart-1)" stroke-width="1.5"/><rect x="90" y="18" width="70" height="22" rx="4" fill="none" stroke="var(--chart-1)" stroke-width="1.5"/><rect x="178" y="18" width="70" height="22" rx="4" fill="none" stroke="var(--danger)" stroke-width="1.5"/><path d="M72 29h18M160 29h18M248 29h22" stroke="var(--muted)" stroke-width="2"/><rect x="272" y="21" width="16" height="16" transform="rotate(45 280 29)" fill="var(--danger)"/>`],
  ['timeline', '2 · Date-axis timeline', 'last update over this update on real months.', 'you want to see WHEN the path runs and how many days the finish moved.',
   `<line x1="0" y1="52" x2="300" y2="52" stroke="var(--muted)"/><g stroke="var(--border)"><line x1="60" y1="4" x2="60" y2="52"/><line x1="130" y1="4" x2="130" y2="52"/><line x1="200" y1="4" x2="200" y2="52"/><line x1="270" y1="4" x2="270" y2="52"/></g><rect x="10" y="10" width="200" height="12" rx="2" fill="var(--muted)"/><rect x="10" y="30" width="200" height="12" rx="2" fill="var(--chart-1)"/><rect x="210" y="30" width="50" height="12" rx="2" fill="var(--danger)"/>`],
  ['table', '3 · Compact table', 'the two routes side by side as text.', 'space is short or the report goes into a letter.',
   `<g fill="none" stroke="var(--muted)"><rect x="4" y="6" width="292" height="46"/><line x1="4" y1="20" x2="296" y2="20"/><line x1="4" y1="36" x2="296" y2="36"/><line x1="90" y1="6" x2="90" y2="52"/><line x1="194" y1="6" x2="194" y2="52"/></g>`],
];
function _cpStyleCards() {
  return `<div class="per-stylecards">` + _CP_STYLES.map(([key, title, shows, when, svg]) =>
    `<div class="per-stylecard${key === _cpStyle ? ' sel' : ''}" data-style="${key}" role="button" tabindex="0">
      <div class="per-sc-h">${escapeHtml(title)}${key === _cpStyle ? '<span class="per-sc-on">selected</span>' : ''}</div>
      <svg viewBox="0 0 300 58" width="100%" style="max-height:62px">${svg}</svg>
      <div class="per-def"><b>Shows:</b> ${escapeHtml(shows)}</div><div class="per-def"><b>Use it when</b> ${escapeHtml(when)}</div></div>`).join('')
    + `</div><div class="cmp-foot">All three draw the same route from the same figures — only the drawing changes. Click a card to use it.</div>`;
}

function _criticalCompareHtml(report) {
  const cp = report.critical_path || {};
  const prevA = cp.previous || [], currA = cp.current || [];
  if (!prevA.length && !currA.length) return '<p class="cmp-empty">No driving path to the finish milestone could be derived.</p>';
  _cpMode = 'leaf-parent';                              // fresh render → default grouping
  const maxDepth = Math.max(1, ...prevA.concat(currA).map(a => (a.wbs_path || '').split(' > ').filter(Boolean).length));
  let modeOpts = `<option value="leaf-parent">WBS — floor / zone (default)</option>`;
  for (let i = 1; i < maxDepth; i++) modeOpts += `<option value="wbs${i}">WBS level ${i + 1}</option>`;
  (report.code_types || []).forEach(t => { modeOpts += `<option value="code:${escapeHtml(t)}">Activity code: ${escapeHtml(t)}</option>`; });
  const so = (v, l) => `<option value="${v}"${_cpStyle === v ? ' selected' : ''}>${l}</option>`;
  const styleSel = `<select id="per-cp-style">${so('chain', 'Connected chain')}${so('timeline', 'Date-axis timeline')}${so('table', 'Compact table')}</select>`;
  return `<div class="per-slicer"><span class="per-slicer-lbl">Critical-path style</span>${styleSel}<span class="per-slicer-lbl" style="margin-left:16px">Group by</span><select id="per-cp-mode">${modeOpts}</select></div>
    <div id="per-cp-style-help">${_cpStyleCards()}</div>
    <div id="per-cp-chains">${_cpCompareBody(report, _cpMode, _cpStyle)}</div>`;
}
function _wireCriticalCompare(report) {
  const styleSel = document.getElementById('per-cp-style'), modeSel = document.getElementById('per-cp-mode'), box = document.getElementById('per-cp-chains');
  if (!box) return;
  const rerender = () => { box.innerHTML = _cpCompareBody(report, _cpMode, _cpStyle); };
  const help = document.getElementById('per-cp-style-help');
  const setStyle = v => {
    _cpStyle = v; try { localStorage.setItem('per_cp_style', _cpStyle); } catch { /* no storage */ }
    if (styleSel) styleSel.value = v;
    if (help) { help.innerHTML = _cpStyleCards(); wireCards(); }
    rerender();
  };
  const wireCards = () => { if (help) help.querySelectorAll('.per-stylecard').forEach(c => c.addEventListener('click', () => setStyle(c.getAttribute('data-style')))); };
  wireCards();
  if (styleSel) styleSel.addEventListener('change', () => setStyle(styleSel.value));
  if (modeSel) modeSel.addEventListener('change', () => { _cpMode = modeSel.value; rerender(); });
}

// What moved — planned vs actual, counts always shown as text.
function _whatMovedHtml(report) {
  const c = (report.buckets || {}).counts || {}, pc = report.plan_counts || {};
  const fin = c.finished || 0, sta = c.started || 0, slip = c.slipped || 0, stal = c.stalled || 0, res = c.re_sequenced || 0;
  const pfin = pc.planned_finish || 0, psta = pc.planned_start || 0;
  const mx = Math.max(pfin, psta, fin, sta, slip, stal, res, 1);
  const w = n => Math.max(2, Math.round(100 * n / mx));
  const row = (lbl, planned, actual, cls, txt) =>
    `<div class="per-wmrow"><span class="per-wml">${lbl}</span><div class="per-wmtrack">${planned ? `<div class="per-wmp" style="width:${w(planned)}%"></div>` : ''}<div class="per-wma ${cls}" style="width:${w(actual)}%"></div></div><span class="per-wmnum">${txt}</span></div>`;
  return `${row('Finished', pfin, fin, 'g', `<b>${fin}</b> done / ${pfin} due`)}
    ${row('Started', psta, sta, 'g', `<b>${sta}</b> done / ${psta} due`)}
    ${row('Slipped', 0, slip, 'b', `<b>${slip}</b> activities`)}
    ${row('Stalled', 0, stal, 'w', `<b>${stal}</b> activities`)}
    ${row('Re-sequenced', 0, res, 'n', `<b>${res}</b> activities`)}
    <div class="cmp-foot"><b>Grey</b> = planned (due to finish/start), <b>coloured</b> = actual; count on the right is always shown. Slipped/stalled/re-sequenced have no plan.</div>`;
}

// Milestone section: every finish milestone in a table (names in full), then the drift chart.
function _milestoneSection(report) {
  const ms = report.milestones || {};
  const overall = ms.overall;                 // project completion — bold in the table
  const rows = (ms.rows || []).length ? ms.rows : (overall ? [overall] : []);
  if (!rows.length || !overall) return '<p class="cmp-empty">No project-completion milestone found in the update.</p>';
  const moved = sp => sp == null ? '—'
    : (sp > 0 ? `<span class="per-slip-bad">${sp} wd later</span>`
      : (sp < 0 ? `<span class="per-slip-good">${Math.abs(sp)} wd earlier</span>` : `<span class="per-slip-good">no change</span>`));
  const vsBase = sb => sb == null ? '—'
    : (sb > 0 ? `<span class="per-slip-bad">${sb} wd late</span>`
      : (sb < 0 ? `<span class="per-slip-good">${Math.abs(sb)} wd early</span>` : `<span class="per-slip-good">on baseline</span>`));
  const ax = report.baseline_approx ? ' · approx' : '';   // own Planned dates stand in for the baseline
  const body = rows.map((r, i) => `<tr><td class="num mut">${i + 1}</td>
      <td>${r.activity_id && r.activity_id === overall.activity_id || r === overall ? `<b>${escapeHtml(r.name)}</b> <span class="mut">(project completion)</span>` : escapeHtml(r.name)}</td>
      <td class="num mono">${escapeHtml(r.baseline_finish)}</td><td class="num mono">${escapeHtml(r.prev_forecast)}</td>
      <td class="num mono">${escapeHtml(r.curr_forecast)}</td><td class="num">${moved(r.slip_period_days)}</td>
      <td class="num">${vsBase(r.slip_baseline_days)}</td></tr>`).join('');
  const table = `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-table">
    <thead><tr><th class="num">S/N</th><th>Milestone</th><th class="num">Baseline${ax}</th><th class="num">Previous forecast</th>
      <th class="num">Current forecast</th><th class="num">Moved this period</th><th class="num">Against baseline${ax}</th></tr></thead>
    <tbody>${body}</tbody></table></div>`;
  return table + `<div class="cmp-scurve-card" style="margin-top:10px">${_milestoneDriftSvg(rows, !!report.baseline_approx)}</div>`;
}

// Break a name onto lines of at most `width` characters, at the spaces — never cut.
function _wrapText(s, width) {
  const out = []; let line = '';
  String(s || '').split(/\s+/).filter(Boolean).forEach(w => {
    if (line && (line + ' ' + w).length > width) { out.push(line); line = w; } else line = line ? line + ' ' + w : w;
  });
  if (line) out.push(line);
  return out.length ? out : [''];
}

function _milestoneDriftSvg(rows, approx = false) {
  const od = iso => Date.parse(iso);
  const all = [];
  rows.forEach(r => ['baseline_iso', 'prev_iso', 'curr_iso'].forEach(k => { if (r[k]) all.push(od(r[k])); }));
  if (all.length < 2) return '<span class="mut">Not enough milestone dates to draw the drift chart.</span>';
  let tmin = Math.min(...all), tmax = Math.max(...all);
  if (tmin === tmax) { tmin -= 8.64e7 * 15; tmax += 8.64e7 * 15; }
  // the name in full, wrapped onto as many lines as it needs (owner: 'the milestones seem trimmed')
  const x0 = 250, x1 = 620, top = 14;
  const names = rows.map(r => _wrapText(r.name, 38));
  const heights = names.map(ls => Math.max(32, 13 * ls.length + 12));
  const ytops = heights.map((_, i) => top + heights.slice(0, i).reduce((a, b) => a + b, 0));
  const bodyH = heights.reduce((a, b) => a + b, 0), h = top + bodyH + 26;
  const xAt = t => x0 + (x1 - x0) * ((t - tmin) / (tmax - tmin));
  let parts = '';
  for (let k = 0; k < 5; k++) {
    const t = tmin + (tmax - tmin) * k / 4, x = xAt(t), d = new Date(t);
    const lab = d.toLocaleString('en', { month: 'short' }) + '-' + String(d.getFullYear()).slice(2);
    parts += `<line x1="${x.toFixed(0)}" y1="${top}" x2="${x.toFixed(0)}" y2="${top + bodyH}" stroke="var(--border)"/><text x="${x.toFixed(0)}" y="${top + bodyH + 15}" text-anchor="middle" font-size="9.5" fill="var(--muted)">${lab}</text>`;
  }
  rows.forEach((r, i) => {
    const y = Math.round(ytops[i] + heights[i] / 2), ls = names[i];
    ls.forEach((ln, j) => {
      parts += `<text x="${x0 - 8}" y="${Math.round(y + 4 + 13 * (j - (ls.length - 1) / 2))}" text-anchor="end" font-size="11" fill="var(--text)">${escapeHtml(ln)}</text>`;
    });
    const xs = ['baseline_iso', 'prev_iso', 'curr_iso'].filter(k => r[k]).map(k => xAt(od(r[k])));
    if (xs.length >= 2) parts += `<line x1="${Math.min(...xs).toFixed(0)}" y1="${y}" x2="${Math.max(...xs).toFixed(0)}" y2="${y}" stroke="var(--border)"/>`;
    if (r.baseline_iso) parts += `<circle cx="${xAt(od(r.baseline_iso)).toFixed(0)}" cy="${y}" r="5" fill="var(--card-bg)" stroke="var(--muted)" stroke-width="2"/>`;
    if (r.prev_iso) parts += `<circle cx="${xAt(od(r.prev_iso)).toFixed(0)}" cy="${y}" r="4.5" fill="var(--warning)"/>`;
    if (r.curr_iso) parts += `<circle cx="${xAt(od(r.curr_iso)).toFixed(0)}" cy="${y}" r="5" fill="var(--danger)"/>`;
  });
  return `<div class="cmp-scurve-legend"><span><i style="background:var(--card-bg);border:2px solid var(--muted);border-radius:50%;width:10px;height:10px"></i>Baseline${approx ? ' · approx' : ''}</span><span><i style="background:var(--warning);border-radius:50%;width:11px;height:11px"></i>Previous forecast</span><span><i style="background:var(--danger);border-radius:50%;width:11px;height:11px"></i>Current forecast</span></div>
    <svg viewBox="0 0 640 ${h}" width="100%" role="img" aria-label="Milestone drift chart">${parts}</svg>`;
}

// Recovery outlook (planning-manager projection — indicative, not a P6 CPM result).
function _recoveryHtml(report) {
  const r = report.recovery;
  if (!r) return '';
  let left = `Work remaining <b>${r.work_remaining == null ? '—' : r.work_remaining + '%'}</b> · this period earned <b>${r.current_rate == null ? '—' : r.current_rate + '%'}</b>.`;
  if (r.required_rate != null) {
    const ra = r.required_achievement;
    left += `<br>To still hit the <b>baseline finish (${escapeHtml(r.baseline_finish || '—')}${report.baseline_approx ? ' · approx' : ''})</b> you'd need about <b>${r.required_rate}%/period</b>${ra != null ? ` (≈${Math.round(ra * 100)}% achievement)` : ''}.`;
  } else if (r.note) {
    left += `<br>${escapeHtml(r.note)}`;
  }
  const feas = r.feasible;
  const verdict = feas === false ? 'Recovery to baseline unlikely at the current rate'
    : (feas === true ? 'Recovery to baseline achievable' : 'Indicative projection');
  const vcls = feas === false ? 'bad' : (feas === true ? 'good' : 'warn');
  return `<div class="per-striplabel">Recovery outlook</div>
    <div class="per-recov"><div class="per-rl">${left}
        <div class="cmp-foot" style="margin-top:5px">Indicative planning projection — not a P6 reschedule.</div></div>
      <div class="per-rr"><div class="per-rr-h">At the current rate</div>
        <div class="per-rr-big">Projected finish ≈ ${escapeHtml(r.projected_finish || '—')}</div>
        <div class="per-rr-v ${vcls}">${escapeHtml(verdict)}</div></div></div>`;
}

// Key facts row (achievement, schedule adherence, started, new critical).
function _factsHtml(report) {
  const s = report.summary || {}, adh = report.schedule_adherence || {},
        cm = report.critical_movement || {}, counts = (report.buckets || {}).counts || {},
        pc = (report.progress || {}).counts || {};
  const ach = s.forecast_achievement == null ? '—' : `${Math.round(s.forecast_achievement * 100)}%`;
  const adhP = adh.pct == null ? '—' : `${Math.round(adh.pct)}%`;
  const fact = (l, v, sub) => `<div class="kpi"><div class="k">${escapeHtml(l)}</div><div class="v">${v}</div>${sub ? `<div class="per-kpi-sub mut">${escapeHtml(sub)}</div>` : ''}</div>`;
  return `<div class="cmp-kpis per-facts">
    ${fact('Activities completed', pc.finished || 0, 'reached 100% this period')}
    ${fact('Activities in progress', pc.increased || 0, 'positive % variance')}
    ${fact('Forecast achievement', ach, 'earned vs forecast')}
    ${fact('Schedule adherence', adhP, `${adh.hit || 0} of ${adh.planned || 0} due finishes`)}
    ${fact('Started this period', counts.started || 0, 'first progress')}
    ${fact('New critical items', cm.new_critical || 0, 'became critical in P6 this period')}
  </div>`;
}

// Status verdict banner (reads the engine-computed verdict).
function _verdictBanner(report) {
  const v = report.verdict;
  if (!v) return '';
  return `<div class="per-banner ${v.level}"><span class="per-dot ${v.level}"></span>
    <div><div class="per-b1">${escapeHtml(v.headline)}</div><div class="per-b2">${escapeHtml(v.detail || '')}</div></div></div>`;
}

// Activities to watch before the next update (was 'Next-period watch list' — owner asked what it means).
function _watchTable(report) {
  const rows = (report.watch_list || {}).rows || [];
  const heading = `<div class="cmp-reco" style="margin:0 0 8px">These are the <b>unfinished construction activities most likely to delay the finish date before your next update</b> — the ones with a Total Float of 10 working days or less, tightest first. The last column says why each one is listed: <b>1)</b> it is on the critical path · <b>2)</b> its float dropped to 10 working days or less in this period · <b>3)</b> it follows an activity that slipped this period. Any other was already near-critical in the previous update.</div>`;
  if (!rows.length) return heading + '<p class="cmp-empty">No near-critical work is queued before the next update.</p>';
  const body = rows.map((r, i) => `<tr><td class="num mut">${i + 1}</td><td class="mono">${escapeHtml(r.activity_id)}</td>
    <td>${escapeHtml(r.activity_name)}</td><td class="num mono">${escapeHtml(r.due_to_start)}</td>
    <td class="num">${r.float_days}</td><td>${escapeHtml(r.reason)}</td></tr>`).join('');
  return `${heading}
    <div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-table">
    <thead><tr><th class="num">S/N</th><th>Activity ID</th><th>Activity name</th><th class="num">Due to start</th>
      <th class="num">Total Float (working days)</th><th>Why it is listed</th></tr></thead>
    <tbody>${body}</tbody></table></div>
    <div class="per-defs"><div class="per-defs-h">Columns</div>
      <div class="per-def"><b>Total Float</b> — spare working days before this activity would delay the project finish (0 or less = on the critical path; up to 10 = near-critical).</div>
      <div class="per-def"><b>Due to start</b> — the activity's forecast start date, from the current update.</div>
      <div class="per-def"><b>Why it is listed</b> — the reason this activity needs attention before the next update.</div></div>`;
}

function _progressRows(rows) {
  let sn = 0;
  return rows.map(r => {
    const cls = r.reversal ? 'cmp-pill bad' : 'cmp-pill good';
    const arrow = r.reversal ? '▼' : '▲';
    const flag = r.reversal ? ' ⚠' : '';
    const stCls = r.status === 'Completed' ? 'cmp-pill good' : 'cmp-pill';
    const status = `<span class="${stCls}">${escapeHtml(r.status || '')}</span>${r.reversal ? ' <span class="cmp-pill bad">reversed</span>' : ''}`;
    const codes = escapeHtml(JSON.stringify(r.codes || {}));   // per-row activity codes, for the slicer
    return `<tr data-codes="${codes}">
      <td class="num mut">${++sn}</td>
      <td class="mono">${escapeHtml(r.activity_id)}</td>
      <td>${escapeHtml(r.activity_name)}</td>
      <td>${status}</td>
      <td class="num mut">${r.prev_pct}%</td>
      <td class="num">${r.curr_pct}%</td>
      <td class="num"><span class="${cls}">${arrow} ${_signPct(r.variance)}${flag}</span></td>
    </tr>`;
  }).join('');
}

function _progressSection(report) {
  const s = report.summary || {};
  const rows = (report.progress && report.progress.rows) || [];
  if (!rows.length) return '<p class="cmp-empty">No activity changed its % complete between the two updates.</p>';
  const ph = escapeHtml(_shortDD(s.data_date_prev)), ch = escapeHtml(_shortDD(s.data_date_now));
  const slicer = _pickHost(report, 'pick a code, then tick any of its values — e.g. Type of Civil Work → Pile Works, Columns Works');
  return `${slicer}
    <div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-table" id="per-prog-table">
      <thead><tr><th class="num">S/N</th><th>Activity ID</th><th>Activity name</th><th>Status</th>
        <th class="num">Prev % <span style="font-weight:400">(${ph})</span></th>
        <th class="num">Current % <span style="font-weight:400">(${ch})</span></th>
        <th class="num">Variance</th></tr></thead>
      <tbody>${_progressRows(rows.filter(_fltMatch))}</tbody></table></div>
    <div class="cmp-foot">Pick an activity code and tick its values to see just those activities’ current vs previous % complete. Biggest gain first; <span class="cmp-pill bad">▼</span> = progress declared backwards vs last update. Prev % / Current % are each activity's own Performance % Complete, as P6 holds it.</div>`;
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
  const markers = `<circle cx="${xAt(nIdx).toFixed(1)}" cy="${yAt(sc.forecast_now).toFixed(1)}" r="3.5" fill="var(--chart-3)"/>` +
                  `<circle cx="${xAt(nIdx).toFixed(1)}" cy="${yAt(sc.actual_now).toFixed(1)}" r="3.5" fill="var(--chart-1)"/>`;
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
    ${line(sc.forecast, 'var(--chart-3)', '5 3')}
    ${line(sc.actual, 'var(--chart-1)')}
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

// The two 'By …' charts: the owner's pick, else the activity code covering most critical
// activities in the fewest values, and WBS (the same rule as p6_period/exporters.crit_group_choice).
function _critGroupChoice(cs, chosen) {
  const groups = (cs || {}).groups || {};
  const codes = Object.keys(groups).filter(k => k !== 'WBS' && (groups[k].groups || 0) >= 2);
  const wbsLike = k => (k.toLowerCase().includes('wbs') ? 1 : 0);
  codes.sort((a, b) => (wbsLike(a) - wbsLike(b)) || ((groups[b].covered || 0) - (groups[a].covered || 0))
    || ((groups[a].groups || 0) - (groups[b].groups || 0)) || (a < b ? -1 : 1));
  let g1 = (chosen && chosen[0] && groups[chosen[0]]) ? chosen[0] : (codes[0] || null);
  const g2 = (chosen && chosen[1] && groups[chosen[1]]) ? chosen[1] : (groups.WBS ? 'WBS' : null);
  if (g1 === g2) g1 = null;
  return [g1, g2];
}
function _hbars(rows, label, value, text, cls) {
  const mx = Math.max(1, ...rows.map(value));
  return rows.map(r => `<div class="per-hb"><span class="per-hbl">${escapeHtml(label(r))}</span>
    <div class="per-hbt"><i class="${cls || ''}" style="width:${Math.max(1, Math.round(100 * value(r) / mx))}%"></i></div>
    <span class="per-hbn">${text(r)}</span></div>`).join('');
}
function _critGroupChart(cs, g, slot) {
  const groups = cs.groups || {}, grp = groups[g] || {}, rows = grp.rows || [];
  const opts = Object.keys(groups).map(k => `<option${k === g ? ' selected' : ''}>${escapeHtml(k)}</option>`).join('');
  const n = grp.groups || rows.length, worst = cs.max_slip || 0;
  const text = r => {
    const ms = r.max_slip || 0;
    return `<b>${r.count}</b> <span class="per-slip ${ms > 0 && ms >= worst ? 'worst' : (ms > 0 ? '' : 'none')}">${ms > 0 ? `worst slip ${ms} wd` : 'no slip'}</span>`;
  };
  const note = `Bar = how many critical activities sit in the group. Badge = the largest slip of any of them between the two updates (working days); red = the worst in the project.${g !== 'WBS' && grp.covered != null ? ` ${grp.covered} of the ${cs.total} critical activities carry this code.` : ''}`;
  return `<div class="per-crit-sub">Where the critical activities are, and the worst slip in each — Group by <select class="per-crit-group" data-slot="${slot}">${opts}</select>${n > rows.length ? ` (top ${rows.length} of ${n})` : ''}</div>`
    + (rows.length ? `<div class="per-hbs-wide">${_hbars(rows, r => r.value, r => r.count, text)}</div><div class="cmp-foot">${note}</div>` : '<p class="cmp-empty">No critical activity carries this code.</p>');
}
function _critSummaryHtml(report) {
  const picked = _fltOn();
  const cs = (picked && _fltCrit ? _fltCrit.critical_summary : report.critical_summary) || {}, s = report.summary || {};
  const logic = picked && _fltCrit ? _fltCrit.logic_changes : report.logic_changes;
  const total = cs.total || 0;
  const banner = !picked ? '' : (_fltCrit
    ? `<div class="cmp-foot per-flt-note"><b>Included:</b> ${escapeHtml(_fltText())} — every count and chart below is for these only.</div>`
    : `<div class="cmp-foot per-flt-note">The picked values could not be applied here — the whole project is shown.</div>`);
  if (!total) return picked && _fltCrit ? `${banner}<p class="cmp-empty">No critical activity carries the picked values.</p>` : '';
  const slip = s.finish_slip_days;
  const fin = slip == null ? '—' : (slip > 0 ? `+${slip} d` : (slip < 0 ? `${slip} d` : 'no change'));
  const tile = (k, v, f, cls) => `<div class="kpi"><div class="k">${escapeHtml(k)}</div><div class="v ${cls || ''}">${v}</div><div class="per-kpi-sub mut">${escapeHtml(f)}</div></div>`;
  const left = cs.left, fnd = cs.left_finished || 0;
  const tiles = `<div class="cmp-kpis per-kpis5">
    ${tile('Critical now', total, cs.prev_total != null ? `previous update: ${cs.prev_total}` : 'in the current update')}
    ${tile('Stayed critical', cs.stayed || 0, 'critical in both updates')}
    ${tile('New critical', cs.new || 0, 'became critical this period', cs.new ? 'per-bad' : '')}
    ${tile('No longer critical', left == null ? '—' : left, left == null ? '' : `${fnd} finished · ${left - fnd} gained float`)}
    ${tile('Finish of the path', fin, `${s.forecast_finish_prev || '—'} → ${s.forecast_finish_now || '—'}`, slip > 0 ? 'per-bad' : '')}
  </div>
  <div class="cmp-foot" style="margin:6px 0 10px"><b>Critical</b> = P6's own Critical flag, read with the file's setting (Total Float less than or equal to the critical limit — 0 unless the project changed it — or the Longest Path). The count is the one P6 gives under the filter Critical = Yes; finished activities are never critical.</div>`;
  const bands = cs.bands || [], mx = Math.max(1, ...bands.map(b => b.count));
  const hist = `<div class="per-hist">${bands.map(b => `<div class="per-hcol"><b>${b.count}</b><i style="height:${Math.max(2, Math.round(100 * b.count / mx))}%"></i></div>`).join('')}</div>
    <div class="per-hl">${bands.map(b => `<span>${escapeHtml(b.label)}</span>`).join('')}</div>`;
  const slipped = bands.filter(b => (b.lo || 0) >= 1);
  const big = slipped.length ? slipped.reduce((a, b) => (b.count > a.count ? b : a)) : null;
  const reading = big ? `<div class="per-def"><b>Reading:</b> ${big.count} of ${total} moved ${escapeHtml(big.label.replace(' days', ''))} working days${s.period_days != null ? ` in this period of ${s.period_days} calendar days` : ''}; the largest slip is ${cs.max_slip} working days.</div>` : '';
  const ex = cs.example;
  const example = ex ? `<div class="per-def mut">Example: ${escapeHtml(ex.activity_id)} ${escapeHtml(ex.activity_name)} — ${escapeHtml(ex.prev_finish)} → ${escapeHtml(ex.curr_finish)} = ${ex.slip_days} working days.</div>` : '';
  const how = `<div class="per-defs"><div class="per-defs-h">How to read this chart</div>
    <div class="per-def"><b>Slip</b> = the activity's finish in the current update − its finish in the previous update, in working days. It is not measured against the baseline and it is not the Total Float.</div>
    <div class="per-def"><b>Each bar</b> = the number of critical activities whose finish moved by that many working days.</div>${reading}${example}</div>`;
  const [g1, g2] = _critGroupChoice(cs, _critGroup);
  const g = g1 || g2;
  const dmx = Math.max(1, ...(cs.drivers || []).map(d => d.count));
  const why = `<div class="per-crit-sub">Why they moved</div>` + (cs.drivers || []).map(d => `<div class="per-hb"><span class="per-hbl"><b>${escapeHtml(d.label)}</b></span>
    <div class="per-hbt"><i class="w" style="width:${Math.max(1, Math.round(100 * d.count / dmx))}%"></i></div><span class="per-hbn"><b>${d.count}</b></span></div>
    ${_DRIVER_MEANING[d.key] ? `<div class="per-hbm">${_DRIVER_MEANING[d.key]}</div>` : ''}`).join('');
  const newRows = cs.new_rows || [];
  const newT = newRows.length ? `<div class="per-crit-sub">The ${newRows.length} activit${newRows.length === 1 ? 'y' : 'ies'} that became critical this period</div>
    <div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-table"><thead><tr><th class="num">S/N</th><th>Activity ID</th><th>Activity name</th>
      <th class="num">Slip (working days)</th><th class="num">Total Float — previous (working days)</th><th class="num">Total Float — current (working days)</th></tr></thead>
    <tbody>${newRows.map((r, i) => `<tr><td class="num mut">${i + 1}</td><td class="mono">${escapeHtml(r.activity_id)}</td><td>${escapeHtml(r.activity_name)}</td>
      <td class="num">${r.slip_days == null ? '—' : (r.slip_days > 0 ? '+' : '') + r.slip_days}</td><td class="num">${r.prev_float_days == null ? '—' : r.prev_float_days}</td>
      <td class="num">${r.float_days == null ? '—' : r.float_days}</td></tr>`).join('')}</tbody></table></div>` : '';
  return `${banner}${tiles}<div class="per-crit-split">
      <div><div class="per-crit-sub">How far the critical activities slipped (working days)</div>${hist}${how}</div>
      <div>${why}</div></div>
    ${g ? _critGroupChart(cs, g, 0) : ''}${_logicHtml(logic)}${newT}
    <div class="cmp-foot">The full list of critical activities (one row each) is in the Word and Excel exports.</div>`;
}
// A grouping picker changed → redraw the summary with it (the PDF / Word follow the same pick).
function _wireCritSummary(report) {
  const box = document.getElementById('per-crit-summary');
  if (!box) return;
  box.querySelectorAll('.per-crit-group').forEach(sel => sel.addEventListener('change', () => {
    _critGroup = [sel.value, null];      // one chart now: its grouping (the PDF / Word follow it)
    box.innerHTML = _critSummaryHtml(report);
    _wireCritSummary(report);
  }));
}

function _criticalTable(cm, codeTypesArg) {
  const rows = (cm && cm.rows) || [];
  if (!rows.length) return `<p class="cmp-empty">No activity is critical in the current update.</p>`;
  const codeTypes = codeTypesArg || [];
  const slipCell = v => (v > 0 ? `<span class="cmp-pill bad">+${v} wd</span>` : (v < 0 ? `<span class="cmp-pill good">${v} wd</span>` : '<span class="cmp-pill">—</span>'));
  const body = rows.map((r, idx) => `<tr data-codes="${escapeHtml(JSON.stringify(r.codes || {}))}">
    <td class="num mut">${idx + 1}</td>
    <td class="mono">${escapeHtml(r.activity_id)}</td>
    <td>${escapeHtml(r.activity_name)}</td>
    <td>${escapeHtml(r.wbs || '')}</td>
    <td class="num mono mut">${escapeHtml(r.prev_finish)}</td>
    <td class="num mono">${escapeHtml(r.curr_finish)}</td>
    <td class="num">${slipCell(r.slip_days)}</td>
    <td class="num">${r.float_days == null ? '—' : r.float_days}</td>
    <td>${_driverTag(r.driver)}</td>
    <td>${_critStatus(r.critical_status)}</td>
  </tr>`).join('');
  const slicer = codeTypes.length ? `<div class="per-slicer">
      <span class="per-slicer-lbl">Filter by activity code</span>
      <select id="per-crit-type"><option value="">— all activities —</option>${codeTypes.map(t => `<option>${escapeHtml(t)}</option>`).join('')}</select>
      <span id="per-crit-chips" class="per-chips"></span></div>` : '';
  return `<div class="per-crit-sub">Full table — every activity P6 flags Critical in the current update, worst slip first</div>
    ${slicer}<div class="tblwrap" style="overflow-x:auto;max-height:520px;overflow-y:auto"><table class="audit-table cmp-table" id="per-crit-table">
    <thead><tr><th class="num">S/N</th><th>Activity ID</th><th>Activity name</th><th>WBS</th><th class="num">Finish (prev)</th>
      <th class="num">Finish (now)</th><th class="num">Slip (wd)</th><th class="num">Total Float (wd)</th>
      <th>Driver this period</th><th>Critical</th></tr></thead>
    <tbody>${body}</tbody></table></div>
    <div class="cmp-foot">Slip = working-day movement of the finish between the two updates. Total Float = P6's Total Float in the current update. <b>▶ new</b> = not critical in the previous update.</div>`;
}

// Generic activity-code slicer wiring for a table with data-codes rows.
function _wireCodeSlicer(selId, chipsId, tableId) {
  const sel = document.getElementById(selId), chipsEl = document.getElementById(chipsId), table = document.getElementById(tableId);
  if (!sel || !chipsEl || !table) return;
  const rows = Array.from(table.querySelectorAll('tbody tr'));
  const codesOf = tr => { try { return JSON.parse(tr.getAttribute('data-codes') || '{}'); } catch { return {}; } };
  const applyVal = (type, val) => rows.forEach(tr => { const c = codesOf(tr); tr.style.display = (!type || val === '__all__' || c[type] === val) ? '' : 'none'; });
  const renderChips = type => {
    if (!type) { chipsEl.innerHTML = ''; rows.forEach(tr => { tr.style.display = ''; }); return; }
    const vals = Array.from(new Set(rows.map(tr => codesOf(tr)[type]).filter(Boolean))).sort();
    chipsEl.innerHTML = [`<span class="per-chip on" data-v="__all__">All</span>`].concat(vals.map(v => `<span class="per-chip" data-v="${escapeHtml(v)}">${escapeHtml(v)}</span>`)).join('');
    chipsEl.querySelectorAll('.per-chip').forEach(chip => chip.addEventListener('click', () => {
      chipsEl.querySelectorAll('.per-chip').forEach(x => x.classList.remove('on')); chip.classList.add('on'); applyVal(type, chip.getAttribute('data-v'));
    }));
    applyVal(type, '__all__');
  };
  sel.addEventListener('change', () => renderChips(sel.value));
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

// ── One activity-code picker shared by three sections (round 3, points 03–05) ──
// Step 1 = the activity code (or WBS), step 2 = tick any of its values. The same pick narrows
// the activities that moved, the Earned Value by code and the critical-path movement, on
// screen and in the PDF / Word / Excel.
const _NOVAL = '(no value)';
let _flt = { type: '', values: [] };   // the picked code and its ticked values ([] = every value)
let _fltCrit = null;                   // the critical summary of the picked values (worked out by the server)
let _fltSeq = 0;
let _byGroup = null;                   // activity code of the planned-vs-actual histogram (null = the default)

const _fltOn = () => !!(_flt.type && _flt.values.length);
const _fltVal = (r, t) => (t === 'WBS' ? (r.wbs || _NOVAL) : ((r.codes || {})[t] || _NOVAL));
const _fltMatch = r => !_fltOn() || (_flt.type === 'WBS' && !('wbs' in r)) || _flt.values.includes(_fltVal(r, _flt.type));
const _codeFilter = () => (_flt.type ? { type: _flt.type, values: _flt.values.slice() } : null);
const _fltText = () => (_fltOn() ? `${_flt.type}: ${_flt.values.slice(0, 6).join(', ')}${_flt.values.length > 6 ? ` … (+${_flt.values.length - 6} more)` : ''}` : '');

function _fltTypes(report) {
  const types = (report.code_types || []).slice();
  if (((report.ev_by_code || {}).WBS || []).length || ((report.critical_movement || {}).rows || []).some(r => r.wbs)) types.push('WBS');
  return types;
}
function _fltValues(report, t) {
  const set = new Set();
  ((report.ev_by_code || {})[t] || []).forEach(e => set.add(e.value));
  [(report.progress || {}).rows, (report.critical_movement || {}).rows].forEach(rows => (rows || []).forEach(r => {
    if (t !== 'WBS' || 'wbs' in r) set.add(_fltVal(r, t));
  }));
  return Array.from(set).sort((a, b) => ((a === _NOVAL) - (b === _NOVAL)) || String(a).localeCompare(String(b)));
}
function _pickHtml(report, note) {
  const types = _fltTypes(report);
  if (!types.length) return '';
  const opts = ['<option value="">— all activities —</option>']
    .concat(types.map(t => `<option value="${escapeHtml(t)}"${t === _flt.type ? ' selected' : ''}>${escapeHtml(t)}</option>`)).join('');
  let step2 = '';
  if (_flt.type) {
    const vals = _fltValues(report, _flt.type);
    const n = _flt.values.length;
    step2 = `<div class="per-cpick-row"><span class="per-slicer-lbl">Step 2 — values</span>
        <button type="button" class="per-cpick-btn" data-act="all">Select all</button>
        <button type="button" class="per-cpick-btn" data-act="clear">Clear</button>
        <span class="per-cpick-n">${n ? `${n} of ${vals.length} picked` : `all ${vals.length} shown — tick the ones you want`}</span></div>
      <div class="per-chips per-cpick-vals">${vals.map(v => {
        const on = _flt.values.includes(v);
        return `<span class="per-chip${on ? ' on' : ''}" data-v="${escapeHtml(v)}">${on ? '✓ ' : ''}${escapeHtml(v)}</span>`;
      }).join('')}</div>`;
  }
  return `<div class="per-cpick"><div class="per-cpick-row"><span class="per-slicer-lbl">Step 1 — activity code</span>
      <select class="per-cpick-type">${opts}</select>${note ? `<span class="per-cpick-n">${escapeHtml(note)}</span>` : ''}</div>${step2}</div>`;
}
const _pickHost = (report, note) => `<div class="per-cpick-host" data-note="${escapeHtml(note || '')}">${_pickHtml(report, note)}</div>`;

function _wirePickers(report) {
  document.querySelectorAll('.per-cpick-host').forEach(host => {
    host.innerHTML = _pickHtml(report, host.getAttribute('data-note') || '');
    const sel = host.querySelector('.per-cpick-type');
    if (sel) sel.addEventListener('change', () => { _flt = { type: sel.value, values: [] }; _applyFilter(report); });
    host.querySelectorAll('.per-chip').forEach(chip => chip.addEventListener('click', () => {
      const v = chip.getAttribute('data-v'), i = _flt.values.indexOf(v);
      if (i >= 0) _flt.values.splice(i, 1); else _flt.values.push(v);
      _applyFilter(report);
    }));
    host.querySelectorAll('.per-cpick-btn').forEach(b => b.addEventListener('click', () => {
      _flt.values = b.getAttribute('data-act') === 'all' ? _fltValues(report, _flt.type) : [];
      _applyFilter(report);
    }));
  });
}
// The pick changed → every picker shows it, and the three sections follow.
async function _applyFilter(report) {
  _wirePickers(report);
  const tb = document.querySelector('#per-prog-table tbody');
  if (tb) {
    const rows = ((report.progress || {}).rows || []).filter(_fltMatch);
    tb.innerHTML = rows.length ? _progressRows(rows)
      : '<tr><td colspan="7" class="mut">No activity of the picked values changed its % complete in this period.</td></tr>';
  }
  const ev = document.getElementById('per-ev-code');
  if (ev) ev.innerHTML = _evCodeTable(report);
  const seq = ++_fltSeq;
  _fltCrit = null;
  if (_fltOn()) {
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/period/filter`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ critical_movement: report.critical_movement, code_types: report.code_types,
          logic_changes: report.logic_changes, code_filter: _codeFilter() }),
      });
      const data = await resp.json();
      if (seq !== _fltSeq) return;
      if (data.ok) _fltCrit = data;
    } catch { /* the whole-project summary stays, and says so */ }
  }
  if (seq !== _fltSeq) return;
  const box = document.getElementById('per-crit-summary');
  if (box) { box.innerHTML = _critSummaryHtml(report); _wireCritSummary(report); }
}

// Earned Value in the two updates for each value of the picked code (point 04).
function _evCodeTable(report) {
  const t = _flt.type, s = report.summary || {};
  if (!t) return '<p class="cmp-empty">Pick an activity code above to see the Earned Value of each of its values in the two updates.</p>';
  const all = (report.ev_by_code || {})[t] || [];
  const rows = _flt.values.length ? all.filter(e => _flt.values.includes(e.value)) : all;
  if (!rows.length) return '<p class="cmp-empty">No cost-loaded activity carries the picked values.</p>';
  const sum = k => rows.reduce((a, e) => a + (e[k] || 0), 0);
  const vcell = v => `<td class="num"><span class="${v >= 0 ? 'per-slip-good' : 'per-slip-bad'}">${_signNum(v)}</span></td>`;
  // the same money as a share of that value's own budget (= its Performance % in each update)
  const pc = (v, bac) => bac ? `${(100 * (v || 0) / bac).toFixed(1)}%` : '—';
  const pcell = e => {
    if (!e.bac) return '<td class="num">—</td>';
    const v = 100 * (e.variance || 0) / e.bac;
    return `<td class="num"><span class="${v >= 0 ? 'per-slip-good' : 'per-slip-bad'}">${v >= 0 ? '+' : ''}${v.toFixed(1)}%</span></td>`;
  };
  const tr = (sn, name, e, bold) => `<tr><td class="num mut">${sn}</td><td>${bold ? `<b>${escapeHtml(name)}</b>` : escapeHtml(name)}</td>
    <td class="num">${_money(e.activities)}</td><td class="num mono">${_money(e.bac)}</td><td class="num mono">${_money(e.ev_prev)}</td>
    <td class="num mono">${_money(e.ev_now)}</td>${vcell(e.variance || 0)}
    <td class="num">${pc(e.ev_prev, e.bac)}</td><td class="num">${pc(e.ev_now, e.bac)}</td>${pcell(e)}</tr>`;
  const tot = { activities: sum('activities'), bac: sum('bac'), ev_prev: sum('ev_prev'), ev_now: sum('ev_now'), variance: sum('variance') };
  const share = (_flt.values.length && s.ev_variance)
    ? `<div class="cmp-foot">The picked values earned ${_money(tot.variance)} of the project's ${_money(s.ev_variance)} in this period (${Math.round(100 * tot.variance / s.ev_variance)}%).</div>` : '';
  return `<div class="tblwrap" style="overflow-x:auto;max-height:460px;overflow-y:auto"><table class="audit-table cmp-table">
      <thead><tr><th class="num">S/N</th><th>${escapeHtml(t)}</th><th class="num">Cost-loaded activities</th><th class="num">Budget</th>
        <th class="num">Earned Value — previous · ${escapeHtml(report.data_date_prev || '')}</th>
        <th class="num">Earned Value — current · ${escapeHtml(report.data_date_now || '')}</th><th class="num">Variance</th>
        <th class="num">Performance % — previous</th><th class="num">Performance % — current</th><th class="num">Variance %</th></tr></thead>
      <tbody>${rows.map((e, i) => tr(i + 1, e.value, e)).join('')}${tr('', _flt.values.length ? 'Total — the picked values' : 'Total — all cost-loaded activities', tot, true)}</tbody></table></div>
      <div class="cmp-foot">Performance % = Earned Value ÷ Budget of that value; Variance % = the progress it gained between the two updates (Variance ÷ Budget).</div>${share}`;
}
function _evCodeHtml(report) {
  if (!report.ev_by_code) return '';
  return `<div class="per-crit-sub">Earned Value by activity code — previous, current and variance</div>
    ${_pickHost(report, 'the same pick is used in the three sections')}
    <div id="per-ev-code">${_evCodeTable(report)}</div>`;
}

// ── Rate of progress carried forward (point 06) ─────────────────────────────
function _rateSvg(r) {
  const d = iso => (iso ? Date.parse(iso + 'T00:00:00Z') : null);
  const d0 = d(r.dd_prev), d1 = d(r.dd_now), bf = d(r.baseline_finish), rf = d(r.rate_finish), pf = d(r.p6_finish);
  if (!d0 || !d1) return '';
  const last = Math.max(d1, ...[bf, rf, pf].filter(Boolean));
  const span = Math.max(1, last - d0);
  const W = 1000, H = 324, L = 44, Rm = 22, T = 62, B = 54;
  const X = t => L + (W - L - Rm) * (t - d0) / span;
  const Y = p => T + (H - T - B) * (1 - Math.max(0, Math.min(100, p)) / 100);
  const acc = 'var(--accent)', warn = 'var(--warning)', bad = 'var(--danger)', good = 'var(--success)', mut = 'var(--muted)';
  const f = n => n.toFixed(0);
  let p = '';
  [0, 25, 50, 75, 100].forEach(g => {
    p += `<line x1="${L}" y1="${f(Y(g))}" x2="${W - Rm}" y2="${f(Y(g))}" stroke="var(--border)" stroke-width="1"/>
      <text x="${L - 6}" y="${f(Y(g) + 3)}" text-anchor="end" font-size="10" fill="${mut}">${g}%</text>`;
  });
  const a0 = r.actual_prev || 0, a1 = r.actual_now || 0;
  const marks = [];
  if (bf) marks.push([bf, mut, `Baseline finish ${r.baseline_finish_label}`]);
  if (rf) {
    const dab = r.days_after_baseline;
    marks.push([rf, acc, `At the current rate ${r.rate_finish_label}${dab == null ? '' : (dab > 0 ? ` (+${dab} days)` : (dab < 0 ? ` (${dab} days)` : ''))}`]);
  }
  if (pf) {
    const lg = r.logic_days;
    marks.push([pf, bad, `P6 forecast ${r.p6_finish_label}${!lg ? '' : (lg > 0 ? ` (+${lg} days more — sequence of the critical path)` : ` (${lg} days)`)}`]);
  }
  marks.sort((a, b) => a[0] - b[0]);
  marks.forEach(([t, col, txt], i) => {
    const x = X(t), ty = 13 + 15 * i, end = x > W * 0.55;
    p += `<line x1="${f(x)}" y1="${ty + 4}" x2="${f(x)}" y2="${f(Y(0))}" stroke="${col}" stroke-width="1.4" stroke-dasharray="4 3"/>
      <text x="${f(end ? x - 5 : x + 5)}" y="${ty}" text-anchor="${end ? 'end' : 'start'}" font-size="11" font-weight="700" fill="${col}">${escapeHtml(txt)}</text>`;
  });
  const pp = r.planned_prev, pn = r.planned_now;
  if (pn != null) {
    if (pp != null) p += `<line x1="${f(X(d0))}" y1="${f(Y(pp))}" x2="${f(X(d1))}" y2="${f(Y(pn))}" stroke="${warn}" stroke-width="2.5"/>`;
    const gap = Math.round((pn - a1) * 10) / 10;
    let gt = `baseline plan ${pn.toFixed(1)}%` + (gap > 0 ? ` — gap ${gap.toFixed(1)}%` : '');
    if (gap > 0 && r.gap_money) gt += ` = ${_money(r.gap_money)}`;
    p += `<circle cx="${f(X(d1))}" cy="${f(Y(pn))}" r="4" fill="${warn}"/>
      <text x="${f(X(d1) + 9)}" y="${f(Y(pn) - 7)}" font-size="10.5" font-weight="700" fill="${warn}">${escapeHtml(gt)}</text>`;
  }
  if (bf && bf > d1) p += `<line x1="${f(X(d1))}" y1="${f(Y(a1))}" x2="${f(X(bf))}" y2="${f(Y(100))}" stroke="${good}" stroke-width="2" stroke-dasharray="7 4"/>`;
  if (rf) p += `<line x1="${f(X(d1))}" y1="${f(Y(a1))}" x2="${f(X(rf))}" y2="${f(Y(100))}" stroke="${acc}" stroke-width="2" stroke-dasharray="7 4"/>
    <circle cx="${f(X(rf))}" cy="${f(Y(100))}" r="4" fill="${acc}"/>`;
  p += `<line x1="${f(X(d0))}" y1="${f(Y(a0))}" x2="${f(X(d1))}" y2="${f(Y(a1))}" stroke="${acc}" stroke-width="4" stroke-linecap="round"/>
    <circle cx="${f(X(d0))}" cy="${f(Y(a0))}" r="4.5" fill="${acc}"/><circle cx="${f(X(d1))}" cy="${f(Y(a1))}" r="4.5" fill="${acc}"/>
    <text x="${f(X(d0) + 2)}" y="${f(Y(a0) + 17)}" font-size="10.5" font-weight="700" fill="${acc}">${a0.toFixed(1)}%</text>
    <text x="${f(X(d1) + 9)}" y="${f(Y(a1) + 15)}" font-size="10.5" font-weight="700" fill="${acc}">${a1.toFixed(1)}% (${_signPct(r.rate_pct)} in ${r.period_days} days)</text>
    <line x1="${L}" y1="${f(Y(0))}" x2="${W - Rm}" y2="${f(Y(0))}" stroke="${mut}" stroke-width="1.5"/>
    <text x="${f(X(d0) - 4)}" y="${H - B + 30}" font-size="10" fill="${mut}">▲ ${escapeHtml(r.dd_prev_label || '')}</text>
    <text x="${f(X(d1) - 4)}" y="${H - B + 44}" font-size="10" fill="${mut}">▲ ${escapeHtml(r.dd_now_label || '')} · current data date</text>`;
  // the months along the time axis — a tick at every month start, the month named under its span
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const segs = [], s0 = new Date(d0);
  for (let y = s0.getUTCFullYear(), m = s0.getUTCMonth(); Date.UTC(y, m, 1) < last; m++) {
    const a = Date.UTC(y, m, 1), mm = new Date(a);
    segs.push([Math.max(a, d0), Math.min(Date.UTC(y, m + 1, 1), last), `${MON[mm.getUTCMonth()]}.${mm.getUTCFullYear()}`, a > d0]);
  }
  const step = Math.max(1, Math.ceil(segs.length * 58 / (W - L - Rm)));
  segs.forEach(([a, b, txt, tick], i) => {
    if (tick) p += `<line x1="${f(X(a))}" y1="${f(Y(0))}" x2="${f(X(a))}" y2="${f(Y(0) + 6)}" stroke="${mut}" stroke-width="1.2"/>`;
    if (i % step === 0 && X(b) - X(a) >= 36) p += `<text x="${f((X(a) + X(b)) / 2)}" y="${H - B + 15}" text-anchor="middle" font-size="10.5" font-weight="700" fill="${mut}">${txt}</text>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-height:${H + 40}px">${p}</svg>`;
}
function _rateHtml(report) {
  const r = report.rate_outlook;
  if (!r) return '';
  const cost = r.by_cost, days = r.period_days, rate = r.rate_pct || 0, lost = r.days_lost || 0;
  const pct1 = v => (v == null ? '—' : `${Number(v).toFixed(1)}%`);
  const intro = cost
    ? `Between the two updates (${days} calendar days) the project earned <b>${_money(r.rate_money)} = ${pct1(rate)}</b> — against ${_money(r.planned_money)} = ${pct1(r.planned_pct)} in the baseline plan for the same days. The chart carries that rate forward.`
    : `Between the two updates (${days} calendar days) the project earned <b>${pct1(rate)}</b> — against ${pct1(r.planned_pct)} planned for the same days. The chart carries that rate forward.`;
  const sw = (col, dash) => `<i style="${dash ? `border-top:3px dashed ${col};height:0` : `background:${col};height:4px`}"></i>`;
  const legend = `<div class="per-lg"><span>${sw('var(--accent)')}Actual between the two updates</span>
    <span>${sw('var(--accent)', 1)}Carried forward at the current rate</span><span>${sw('var(--success)', 1)}Rate needed to finish on the baseline date</span>
    <span>${sw('var(--warning)')}Baseline plan</span><span>${sw('var(--danger)', 1)}P6 forecast finish</span></div>`;
  const tile = (k, v, f, cls) => `<div class="kpi"><div class="k">${escapeHtml(k)}</div><div class="v ${cls || ''}">${v}</div><div class="per-kpi-sub mut">${escapeHtml(f)}</div></div>`;
  const t1 = cost ? `${_moneyShort(r.rate_money || 0)} per ${days} days = ${_moneyShort(r.daily_money || 0)} per day` : `${r.daily_pct}% per day`;
  const t2 = lost > 0 ? (cost ? `Shortfall ${_money(r.shortfall_money)} against the plan ÷ ${_moneyShort(r.daily_money || 0)} per day` : 'Shortfall against the plan ÷ the rate per day')
    : 'The period earned what the plan asked for';
  const dab = r.days_after_baseline;
  const t3 = r.rate_finish_label
    ? `${r.remaining_pct}% still to earn ÷ ${pct1(rate)} per ${days} days = ${r.days_to_go} days${dab == null ? '' : (dab > 0 ? ` · ${dab} days after the baseline` : (dab < 0 ? ` · ${-dab} days before the baseline` : ' · on the baseline date'))}`
    : 'No progress was earned in this period — no date can be projected';
  const req = r.required_pct, more = r.required_more_pct;
  const t4 = req == null ? 'The baseline finish has already passed'
    : (r.required_money ? `${_moneyShort(r.required_money)} per ${days} days` : `per ${days} days`) + (more == null ? '' : (more > 0 ? ` — ${more}% more than now` : ' — the present rate is enough'));
  const lg = r.logic_days || 0, rf = escapeHtml(r.rate_finish_label || ''), pf = escapeHtml(r.p6_finish_label || '');
  let read = '';
  if (rf && pf && lg > 0) read = `Volume of work alone would finish on <b>${rf}</b>, but P6 forecasts <b>${pf}</b>: the extra ${lg} days come from the <b>sequence of the critical activities</b>, not from the amount of work. So recovery needs both — a higher rate and shortening the critical chain. `;
  else if (rf && pf && lg < 0) read = `P6 forecasts <b>${pf}</b>, ${-lg} days before the date the present rate gives (${rf}): the remaining work is planned at a faster rate than this period achieved — the forecast holds only if the rate rises. `;
  read += `Rate = ${cost ? 'Earned Value variance' : '% complete variance'} ÷ calendar days between the two data dates; it assumes the same rate continues.`;
  return `<div class="mod-sec">Rate of progress and where it lands</div>
    <div class="cmp-foot" style="margin:0 0 8px">${intro}</div>
    <div class="cmp-scurve-card">${legend}${_rateSvg(r)}</div>
    <div class="cmp-kpis" style="margin-top:10px">
      ${tile('Current rate', `${pct1(rate)} / period`, t1)}
      ${tile('Time lost this period', `${Math.max(lost, 0)} days`, t2, lost > 0 ? 'per-bad' : '')}
      ${tile('Finish at this rate', escapeHtml(r.rate_finish_label || '—'), t3)}
      ${tile(`Rate needed for ${r.baseline_finish_label || 'the baseline finish'}`, req == null ? '—' : `${pct1(req)} / period`, t4, (more || 0) > 0 ? 'per-bad' : '')}
    </div>
    <div class="per-defs"><div class="per-defs-h">How to read it</div><div class="per-def">${read}</div></div>`;
}

// ── Where the period's progress came from — planned vs actual histogram (point 09) ──
function _byGroupOf(report) {
  const bc = report.progress_by_code || {};
  if (_byGroup && bc[_byGroup]) return _byGroup;
  const def = (report.advice || {}).front_type;
  return (def && bc[def]) ? def : (Object.keys(bc)[0] || null);
}
function _byCodeHtml(report) {
  const bc = report.progress_by_code || {};
  const types = Object.keys(bc);
  if (!types.length) return '<p class="cmp-empty">No activity codes in this schedule to break progress down by.</p>';
  const g = _byGroupOf(report);
  const sel = `<div class="per-slicer"><span class="per-slicer-lbl">Group by</span><select id="per-bycode-type">${types.map(t => `<option${t === g ? ' selected' : ''}>${escapeHtml(t)}</option>`).join('')}</select>
    <span class="per-cpick-n">the conclusion's “fronts” follow this choice</span></div>`;
  return sel + `<div id="per-bycode-bars">${_byCodeBars(bc[g])}</div>`;
}
function _byCodeBars(allRows) {
  allRows = allRows || [];
  let rows = allRows.filter(r => (r.planned || 0) > 0 || (r.actual || 0) > 0).slice(0, 10);
  if (!rows.length) rows = allRows.slice(0, 10);
  if (!rows.length) return '<p class="cmp-empty">No progress to attribute for this code.</p>';
  const mx = Math.max(...rows.map(r => Math.max(r.planned || 0, r.actual || 0)), 0.0001);
  const h = v => Math.max(1, Math.round(86 * (v || 0) / mx));
  const col = r => {
    const pl = r.planned || 0, ac = r.actual || 0, low = ac < pl - 0.05;
    return `<div class="per-vg"><div class="per-vb"><b>${pl.toFixed(1)}%</b><i class="pl" style="height:${h(pl)}%"></i></div>
      <div class="per-vb"><b class="${low ? 'per-slip-bad' : ''}">${ac.toFixed(1)}%</b><i class="ac" style="height:${h(ac)}%"></i></div></div>`;
  };
  const more = allRows.length - rows.length;
  return `<div class="cmp-scurve-card"><div class="per-lg"><span><i style="background:var(--warning);height:9px;width:12px"></i>Planned for the period</span>
      <span><i style="background:var(--accent);height:9px;width:12px"></i>Actual in the period</span>
      <span>% of the whole project · a red label = earned less than planned${more > 0 ? ` · the ${rows.length} values that moved most` : ''}</span></div>
    <div class="per-vhist">${rows.map(col).join('')}</div>
    <div class="per-vl-row">${rows.map(r => `<span>${escapeHtml(r.value)}</span>`).join('')}</div></div>
    <div class="cmp-foot">Each value has two columns with its figure above it — weighted by each activity's cost / duration share of the project. Planned sums to your period plan, actual to what you earned.</div>`;
}
function _wireByCode(report) {
  const sel = document.getElementById('per-bycode-type');
  const box = document.getElementById('per-bycode-bars');
  if (!sel || !box) return;
  sel.addEventListener('change', () => {
    _byGroup = sel.value;
    box.innerHTML = _byCodeBars((report.progress_by_code || {})[sel.value]);
    const adv = document.getElementById('per-advice');
    if (adv) adv.innerHTML = _adviceHtml(report);
  });
}

// ── Conclusion and recommended actions (point 10) ───────────────────────────
function _adviceHtml(report) {
  const adv = report.advice;
  if (!adv) return '';
  const tone = { bad: 'per-bad', good: 'per-good' };
  const tiles = `<div class="cmp-kpis">${(adv.tiles || []).map(t => `<div class="kpi"><div class="k">${escapeHtml(t.label)}</div>
    <div class="v ${tone[t.tone] || ''}">${escapeHtml(t.value)}</div><div class="per-kpi-sub mut">${escapeHtml(t.sub || '')}</div></div>`).join('')}</div>`;
  const fr = adv.pm_fronts || {}, g = _byGroupOf(report);
  const pm = adv.pm_head ? (adv.pm_head || []).concat(fr[g] || fr[adv.front_type] || [], adv.pm_tail || []) : (adv.project_manager || []);
  const col = (title, items, cls) => `<div class="per-adv ${cls}"><div class="per-adv-h">${title}</div>${items.map((it, i) =>
    `<div class="per-adv-i"><b>${i + 1} · ${escapeHtml(it.title)}</b><div>${escapeHtml(it.text)}</div></div>`).join('')}</div>`;
  return `${tiles}${col('For Top Management', adv.top_management || [], 'tm')}${col('For the Project Manager', pm, 'pm')}
    <div class="cmp-foot">${escapeHtml(adv.rules || '')} The wording adapts to the result of each pair of updates.</div>`;
}

// "Relationships changed" — what it means, and what changed for each of those activities (point 07).
function _logicHtml(rows) {
  if (!rows || !rows.length) return '';
  const moved = n => (n == null ? '—' : (n > 0 ? `<span class="cmp-pill bad">${n} wd later</span>` : (n < 0 ? `<span class="cmp-pill good">${-n} wd earlier</span>` : '<span class="cmp-pill">no change</span>')));
  return `<div class="per-crit-sub">Relationships changed — the ${rows.length} critical activit${rows.length === 1 ? 'y' : 'ies'}</div>
    <div class="per-defs" style="margin-top:0"><div class="per-defs-h">“Relationships changed” — what it means</div>
      <div class="per-def">Between the previous and the current update, the <b>relationships</b> of the activity were edited: a predecessor or successor was added or removed, the relationship type changed (FS / SS / FF / SF), or the lag changed. For these activities the finish date moved because the planner changed the logic — not because of progress on site. Only construction activities are counted.</div></div>
    <div class="tblwrap" style="overflow-x:auto;margin-top:8px"><table class="audit-table cmp-table"><thead><tr><th class="num">S/N</th><th>Activity ID</th><th>Activity name</th>
      <th class="num">Finish — previous</th><th class="num">Finish — current</th><th class="num">Finish moved</th><th>What changed in the relationships (previous → current)</th></tr></thead>
    <tbody>${rows.map((r, i) => `<tr><td class="num mut">${i + 1}</td><td class="mono">${escapeHtml(r.activity_id)}</td><td>${escapeHtml(r.activity_name)}</td>
      <td class="num mono mut">${escapeHtml(r.prev_finish || '')}</td><td class="num mono">${escapeHtml(r.curr_finish || '')}</td><td class="num">${moved(r.slip_days)}</td>
      <td>${(r.changes || []).map(c => escapeHtml(c)).join('<br>') || '—'}</td></tr>`).join('')}</tbody></table></div>`;
}
const _DRIVER_MEANING = {
  'progress shortfall': 'the finish moved later because the work did not progress as the previous update planned',
  held: 'the finish stayed where it was, or moved earlier',
  'logic changed': 'the planner edited the relationships of the activity — a link added or removed, its type or its lag changed',
  'duration extended': 'the remaining duration was made longer than the previous update had',
};

export function renderPeriodReport(report) {
  if (report !== _shownReport) { _flt = { type: '', values: [] }; _fltCrit = null; _byGroup = null; }
  _shownReport = report;
  const rep = document.getElementById('per-report');
  if (!rep) return;
  const s = report.summary || {};
  const mismatch = (report.matched_activities === 0)
    ? `<div class="cmp-warn">No activities matched by ID between the two files — is this the right previous update? Nothing can be compared until they line up.</div>` : '';
  rep.innerHTML = `
    ${_fileBar(report)}
    <div class="cmp-exports">
      <button class="btn-secondary" id="per-export-pdf">Export PDF</button>
      <button class="btn-secondary" id="per-export-xlsx">Export Excel</button>
    </div>
    ${mismatch}
    ${_verdictBanner(report)}
    <div class="mod-sec">${_byCost(report) ? 'Performance %' : 'Progress'} — where you are vs where you said you’d be</div>
    ${_progressBarHtml(report)}
    ${_evHtml(report)}
    ${_rateHtml(report)}
    <div class="mod-sec">Execution Dashboard — progress this period</div>
    ${_dashboard(report)}
    <div class="mod-sec">Critical-path comparison — the finish-driving route</div>
    ${_criticalCompareHtml(report)}
    <div class="mod-sec">Progress by activity — % complete this period</div>
    ${_progressSection(report)}
    <div class="mod-sec">Critical-path movement in this window</div>
    ${_pickHost(report, 'the counts, the charts and the tables below follow the pick')}
    <div id="per-crit-summary">${_critSummaryHtml(report)}</div>
    <div class="mod-sec">Activities to watch before the next update</div>
    ${_watchTable(report)}
    <div class="mod-sec">What moved this period — planned vs actual</div>
    ${_whatMovedHtml(report)}
    <div class="mod-sec">Where this period’s progress came from — by activity code</div>
    ${_byCodeHtml(report)}
    <div class="mod-sec">Milestones — every finish milestone, names in full</div>
    ${_milestoneSection(report)}
    <div class="mod-sec">Executive conclusion — this period</div>
    <div class="cmp-reco">${escapeHtml(report.conclusion || '')}</div>
    <div class="mod-sec">Project conclusion &amp; outlook</div>
    <div class="cmp-reco per-project-reco">${escapeHtml(report.project_conclusion || '')}</div>
    ${report.advice ? `<div class="mod-sec">Conclusion and recommended actions</div><div id="per-advice">${_adviceHtml(report)}</div>` : ''}`;
  const epdf = document.getElementById('per-export-pdf');
  if (epdf) epdf.addEventListener('click', exportPeriodPdf);
  const exls = document.getElementById('per-export-xlsx');
  if (exls) exls.addEventListener('click', exportPeriodExcel);
  // either update can be changed from the results too — assign only; Run Comparison re-runs
  const chgPrev = document.getElementById('per-change-prev-inline');
  if (chgPrev) chgPrev.addEventListener('click', choosePrev);
  const chgCurr = document.getElementById('per-change-curr-inline');
  if (chgCurr) chgCurr.addEventListener('click', chooseCurr);
  _wireCritSummary(report);
  _wirePickers(report);
  _wireByCode(report);
  _wireCriticalCompare(report);
}

// ── Exports (PDF + Excel) ───────────────────────────────────────────────────

async function _withBtn(id, idle, fn) {
  const btn = document.getElementById(id);
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try { await fn(); }
  finally { if (btn) { btn.disabled = false; btn.textContent = idle; } }
}

const PER_SECTIONS = [
  ['verdict', 'Status verdict'], ['progress', 'Progress chart'],
  ['earned_value', 'Earned Value — before, after and variance'], ['dashboard', 'Execution Dashboard'],
  ['recommendation', 'Management recommendation'], ['critical_compare', 'Critical-path comparison'],
  ['critical', 'Critical-path movement (summary + table)'], ['progress_table', 'Progress by activity'],
  ['watch', 'Activities to watch before the next update'], ['whatmoved', 'What moved this period'],
  ['bycode', 'Progress by activity code'], ['milestones', 'Milestones (table + chart)'], ['conclusions', 'Conclusions'],
  ['rate', 'Rate of progress and where it lands'], ['advice', 'Conclusion and recommended actions'],
];

// Export PDF opens the ONE shared preview (preview.js): tick whole sections or single tables /
// charts inside them, reorder, then Print or Save (owner comment 1). This report's own options
// — the activity-code filter and the critical-path style — sit under the contents tree.
export async function exportPeriodPdf() {
  if (!_shownReport) { showError('Run the comparison first, then export.'); return; }
  await _withBtn('per-export-pdf', 'Export PDF', async () => {
    _perTheme = getSavedMode();
    let codeFilter = _codeFilter();                          // { type, values } — the pick made on screen
    const fetchPreview = async (keys, theme) => {
      try {
        const resp = await fetch(`http://localhost:${state.serverPort}/api/period/report`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ report: _shownReport, trend: _shownTrend, preview: true, code_filter: codeFilter,
            critical_style: _cpStyle, critical_mode: _cpMode, critical_group: _critGroup, bycode_group: _byGroupOf(_shownReport),
            theme: theme || _perTheme }),
        });
        const data = await resp.json();
        if (!data.ok) { showError(`Preview failed: ${data.error || 'unknown error'}`); return null; }
        return data.html || null;
      } catch { showError('Could not reach the local server for the preview.'); return null; }
    };
    const html = await fetchPreview(null, _perTheme);
    if (!html) return;
    const sections = PER_SECTIONS.map(([key, label]) => ({ key, label }));
    const codeTypes = _fltTypes(_shownReport);
    showReportPreview({
      title: 'Update vs Update preview', subtitle: _shownReport.update_file || _shownReport.project_name || '', html,
      sections, selected: sections.map(x => x.key), storageKey: 'p6_report_sections_period', initialMode: _perTheme,
      feature: 'Update vs Update', exportName: 'update_vs_update',
      exports: ['pdf', 'docx', 'html', 'xlsx'], onExcel: () => exportPeriodExcel(),
      meta: { project: _shownReport.project_name || '', data_date: _shownReport.data_date_now || '' },
      onRerender:    (keys, theme) => fetchPreview(keys, theme),
      onThemeChange: (theme, keys) => { _perTheme = theme; return fetchPreview(keys, theme); },
      extras: (host, { rerender }) => {
        const cpOpt = (v, l) => `<option value="${v}"${_cpStyle === v ? ' selected' : ''}>${l}</option>`;
        const tOpt = t => `<option value="${escapeHtml(t)}"${t === _flt.type ? ' selected' : ''}>${escapeHtml(t)}</option>`;
        host.innerHTML = (codeTypes.length ? `<div class="rpv-xh">Filter by activity code</div>
            <select id="per-flt-type"><option value="">— none (all activities) —</option>${codeTypes.map(tOpt).join('')}</select>
            <select id="per-flt-val" multiple size="6" title="Ctrl + click to pick several values"></select>
            <div class="rpv-xnote">Ctrl + click picks several values; none picked = all.</div>` : '')
          + `<div class="rpv-xh">Critical-path style</div>
            <select id="per-pdf-cp-style">${cpOpt('chain', 'Connected chain')}${cpOpt('timeline', 'Date-axis timeline')}${cpOpt('table', 'Compact table')}</select>`;
        const typeSel = host.querySelector('#per-flt-type');
        const valSel = host.querySelector('#per-flt-val');
        const styleSel = host.querySelector('#per-pdf-cp-style');
        const fillVals = () => {
          const vals = _flt.type ? _fltValues(_shownReport, _flt.type) : [];
          valSel.innerHTML = vals.map(v => `<option value="${escapeHtml(v)}"${_flt.values.includes(v) ? ' selected' : ''}>${escapeHtml(v)}</option>`).join('');
          valSel.disabled = !vals.length;
        };
        // the preview's filter and the pickers on the screen are the same pick
        const setFilter = () => { codeFilter = _codeFilter(); _applyFilter(_shownReport); rerender(); };
        if (typeSel) {
          fillVals();
          typeSel.addEventListener('change', () => { _flt = { type: typeSel.value, values: [] }; fillVals(); setFilter(); });
          valSel.addEventListener('change', () => { _flt.values = Array.from(valSel.selectedOptions).map(o => o.value); setFilter(); });
        }
        if (styleSel) styleSel.addEventListener('change', () => {
          _cpStyle = styleSel.value;
          try { localStorage.setItem('per_cp_style', _cpStyle); } catch { /* no storage */ }
          rerender();
        });
      },
    });
  });
}

export async function exportPeriodExcel() {
  if (!_shownReport) { showError('Run the comparison first, then export.'); return; }
  const outputPath = await window.pywebview.api.choose_save_path('update_vs_update.xlsx', 'xlsx');
  if (!outputPath) return;
  await _withBtn('per-export-xlsx', 'Export Excel', async () => {
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/period/excel`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report: _shownReport, trend: _shownTrend, output_path: outputPath, critical_group: _critGroup,
          code_filter: _codeFilter(), bycode_group: _byGroupOf(_shownReport) }),
      });
      const data = await resp.json();
      if (!data.ok) showError(`Excel export failed: ${data.error || 'unknown error'}`);
    } catch { showError('Could not reach the local server to export to Excel.'); }
  });
}

const _TREND_PALETTE = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)'];

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
    _shownTrend = data.ok ? data.trend : null;
    el.innerHTML = data.ok ? _milestoneTrendSvg(data.trend)
                           : `<p class="cmp-empty">${escapeHtml(data.error || 'Trend unavailable.')}</p>`;
  } catch {
    el.innerHTML = '<p class="cmp-empty">Could not load the milestone trend.</p>';
  }
}

// The two files of the comparison, each with its own 'Choose a different file…' (comment 68).
function _fileBar(report) {
  return `<div class="cmp-files">
    <span class="cmp-file"><span class="k">Previous update</span> <b>${escapeHtml(report.prev_file || '—')}</b> · ${escapeHtml(report.data_date_prev || '')}
      <button class="btn-mini" id="per-change-prev-inline">Choose a different file…</button></span>
    <span class="cmp-vs">→</span>
    <span class="cmp-file"><span class="k">Current update</span> <b>${escapeHtml(report.update_file || '—')}</b> · ${escapeHtml(report.data_date_now || '')}
      <button class="btn-mini" id="per-change-curr-inline">Choose a different file…</button></span>
  </div><div id="per-rerun-note" class="per-rerun-note"></div>${report.baseline_approx ? `<div class="per-cutoff" data-baseline-approx>Baseline: ${escapeHtml(report.baseline_label || 'not in the file and none attached — the update’s own Planned dates stand in (approximate)')}</div>` : ''}`;
}

// Pure helpers exposed for unit tests.
export { _signPct as signPct, _shortDate as shortDate, _progressBarHtml as progressBarHtml,
         _milestoneSection as milestoneSection, _dashboard as dashboardHtml,
         _cpTimelineData as criticalTimelineData, _cpCompareBody as criticalCompareBody,
         _evHtml as earnedValueHtml, _critSummaryHtml as criticalSummaryHtml, _critGroupChoice as critGroupChoice,
         _watchTable as watchTable, _criticalTable as criticalTable, _wrapText as wrapText,
         _rateHtml as rateHtml, _adviceHtml as adviceHtml, _byCodeHtml as byCodeHtml, _logicHtml as logicHtml,
         _evCodeTable as evCodeTable };
