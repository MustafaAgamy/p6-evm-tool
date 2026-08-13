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
let _shownTrend = null;    // the milestone trend currently on screen (carried into the PDF)
let _prev = null;          // {prev_path} or {prev_cached_path} chosen for the comparison
let _cpStyle = 'chain';    // critical-path presentation: 'chain' | 'timeline' | 'table' (remembered)
let _cpMode = 'leaf-parent';   // critical-path grouping — reset to default on each fresh render
try { const s = localStorage.getItem('per_cp_style'); if (s) _cpStyle = s; } catch { /* no storage */ }

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

function _dashboard(report) {
  const s = report.summary || {};
  const pw = `to ${_shortDD(report.data_date_prev)}`, cw = `to ${_shortDD(report.data_date_now)}`;
  const cutoff = `<div class="per-cutoff">Comparison window · <b>${escapeHtml(report.data_date_prev || '—')}</b> <span class="mut">(previous cutoff)</span> → <b>${escapeHtml(report.data_date_now || '—')}</b> <span class="mut">(current cutoff)</span></div>`;

  // % Complete (higher = better)
  const pctGood = (s.period_earned || 0) >= 0;
  const pct = _trendStrip('Previous % Complete', pw, `${s.actual_prev}%`, 'Current % Complete', cw, `${s.actual_now}%`,
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
    <div class="per-striplabel">Overall % Complete — Current vs Previous</div>${pct}
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
  const startM = ap == null ? '' :
    `<div class="per-pmark" style="left:${clamp(ap)}%;background:#94a3b8"></div><span class="per-tag-above" style="left:${clamp(ap)}%;color:#64748b">▾ start ${d1(ap)}%</span>`;
  const planM = fn == null ? '' :
    `<div class="per-pmark" style="left:${clamp(fn)}%"></div><span class="per-tag-above" style="left:${clamp(fn)}%">▾ planned ${d1(fn)}%</span>`;
  const ach = s.forecast_achievement == null ? '—' : Math.round(s.forecast_achievement * 100) + '%';
  const behind = fn == null ? '' : ` — <b>${(fn - an) <= 0 ? 'on/ahead of' : d1(Math.abs(fn - an)) + '% behind'}</b> your plan`;
  const planTxt = fn == null ? '' : `Your last update planned <b>${d1(fn)}%</b> by now (${_signPct(pf)}). `;
  return `<div class="cmp-scurve-card per-prog">
    <div class="per-pbtop"><span>0% — start</span><span>100% — finish</span></div>
    <div class="per-pbar">${startM}<div class="per-pfill" style="width:${fill}%">${d1(an)}%</div>
      <span class="per-tag-below" style="left:${fill}%">▴ now ${d1(an)}%</span>${planM}</div>
    <div class="per-psent">On <b>${escapeHtml(report.data_date_prev || '—')}</b> you were at <b>${ap != null ? d1(ap) : '—'}%</b>. ${planTxt}You reached <b>${d1(an)}%</b> on <b>${escapeHtml(report.data_date_now || '—')}</b> (${_signPct(pe)}). All three are % of the whole project${behind}; you did ${_signPct(pe)} of ${_signPct(pf)} = <b>${ach}</b>.</div>
  </div>`;
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
  const scale = 620 / widest, px = w => Math.max(58, Math.round(w * scale));
  const pre = prefix.map(px);
  return [pre.concat(prevTail.map(px)), pre.concat(currTail.map(px))];
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
  const legend = `<div class="cmp-foot"><span class="cpsw" style="background:#bcd6f5"></span>shared route (unchanged) <span class="cpsw" style="background:#f4a3a3"></span>new route (from the reroute) <span class="cpsw" style="background:#e9edf2"></span>old route (dropped off)</div>`;
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
  const FILL = { same: '#93c5fd', new: '#f87171', gone: '#e2e8f0' }, INK = { same: '#1e3a8a', new: '#ffffff', gone: '#64748b' };
  let p = '';
  for (let k = 0; k < 5; k++) { const t = tmin + (tmax - tmin) * k / 4, x = xat(t), d = new Date(t * 8.64e7); const lab = d.toLocaleString('en', { month: 'short' }) + '-' + String(d.getFullYear()).slice(2); p += `<line x1="${x.toFixed(0)}" y1="40" x2="${x.toFixed(0)}" y2="222" stroke="#f1f5f9"/><text x="${x.toFixed(0)}" y="238" text-anchor="middle" font-size="9" fill="#94a3b8">${lab}</text>`; }
  const draw = (segs, pos, y, isCurr) => segs.forEach((s, i) => {
    const role = i < div ? 'same' : (isCurr ? 'new' : 'gone');
    const x = xat(pos[i][0]), w = Math.max(6, xat(pos[i][1]) - xat(pos[i][0]));
    p += `<rect x="${x.toFixed(0)}" y="${y}" width="${w.toFixed(0)}" height="24" rx="4" fill="${FILL[role]}"/>`;
    const cap = Math.floor(w / 6.5);
    if (w >= 34 && cap >= 3) { const lab = s.key.length <= cap ? s.key : s.key.slice(0, cap - 1) + '…'; p += `<text x="${(x + w / 2).toFixed(0)}" y="${y + 16}" text-anchor="middle" font-size="10" fill="${INK[role]}">${escapeHtml(lab)}</text>`; }
  });
  draw(prev, pprev, 60, false); draw(curr, pcurr, 120, true);
  p += `<text x="14" y="74" font-size="11" font-weight="700" fill="#64748b">WAS · ${escapeHtml(report.data_date_prev || '')}</text>`;
  p += `<text x="14" y="134" font-size="11" font-weight="700" fill="#1e293b">NOW · ${escapeHtml(report.data_date_now || '')}</text>`;
  if (pprev.length) { const fx = xat(pprev[pprev.length - 1][1]); p += `<path d="M${fx.toFixed(0)},72 l7,-7 l7,7 l-7,7 z" fill="#94a3b8"/><text x="${(fx + 18).toFixed(0)}" y="58" font-size="9.5" fill="#64748b">finish ${escapeHtml(data.finishPrev || '')}</text>`; }
  if (pcurr.length) { const gx = xat(pcurr[pcurr.length - 1][1]); p += `<path d="M${gx.toFixed(0)},132 l7,-7 l7,7 l-7,7 z" fill="#dc2626"/><text x="${(gx + 18).toFixed(0)}" y="118" font-size="9.5" fill="#b91c1c" font-weight="700">finish ${escapeHtml(data.finishNow || '')}</text>`; }
  const slip = data.slip;
  if (pprev.length && pcurr.length && slip) { const a = xat(pprev[pprev.length - 1][1]), b = xat(pcurr[pcurr.length - 1][1]), lo = Math.min(a, b), hi = Math.max(a, b); p += `<line x1="${lo.toFixed(0)}" y1="196" x2="${hi.toFixed(0)}" y2="196" stroke="#dc2626" stroke-width="1.5"/><line x1="${lo.toFixed(0)}" y1="192" x2="${lo.toFixed(0)}" y2="200" stroke="#dc2626"/><line x1="${hi.toFixed(0)}" y1="192" x2="${hi.toFixed(0)}" y2="200" stroke="#dc2626"/><text x="${((lo + hi) / 2).toFixed(0)}" y="212" text-anchor="middle" font-size="10.5" fill="#b91c1c" font-weight="700">${slip > 0 ? '+' : ''}${slip} wd</text>`; }
  if (div < curr.length || div < prev.length) { const src = div < pcurr.length ? pcurr[div][0] : (div < pprev.length ? pprev[div][0] : null); if (src != null) { const dx = xat(src); p += `<line x1="${dx.toFixed(0)}" y1="52" x2="${dx.toFixed(0)}" y2="168" stroke="#dc2626" stroke-width="1" stroke-dasharray="3 3"/><text x="${dx.toFixed(0)}" y="182" text-anchor="middle" font-size="9.5" fill="#b91c1c" font-weight="700">rerouted here</text>`; } }
  const legend = `<div class="cmp-foot"><span class="cpsw" style="background:#93c5fd"></span>shared route (on both) <span class="cpsw" style="background:#f87171"></span>new critical route (from the reroute) <span class="cpsw" style="background:#e2e8f0"></span>old route (dropped off)</div>`;
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
    <div id="per-cp-chains">${_cpCompareBody(report, _cpMode, _cpStyle)}</div>`;
}
function _wireCriticalCompare(report) {
  const styleSel = document.getElementById('per-cp-style'), modeSel = document.getElementById('per-cp-mode'), box = document.getElementById('per-cp-chains');
  if (!box) return;
  const rerender = () => { box.innerHTML = _cpCompareBody(report, _cpMode, _cpStyle); };
  if (styleSel) styleSel.addEventListener('change', () => { _cpStyle = styleSel.value; try { localStorage.setItem('per_cp_style', _cpStyle); } catch { /* no storage */ } rerender(); });
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

// Where progress came from — by activity code (slicer over the precomputed code types).
function _byCodeHtml(report) {
  const bc = report.progress_by_code || {};
  const types = Object.keys(bc);
  if (!types.length) return '<p class="cmp-empty">No activity codes in this schedule to break progress down by.</p>';
  const sel = `<div class="per-slicer"><span class="per-slicer-lbl">Activity code</span><select id="per-bycode-type">${types.map(t => `<option>${escapeHtml(t)}</option>`).join('')}</select></div>`;
  const note = `<div class="cmp-foot" style="margin:2px 0 6px"><b>Grey</b> = planned this period (last update), <b>blue</b> = actual — weighted by each activity's cost/duration share. Planned sums to your period plan, actual to what you earned.</div>`;
  return sel + note + `<div id="per-bycode-bars">${_byCodeBars(bc[types[0]])}</div>`;
}
function _byCodeBars(rows) {
  rows = (rows || []).slice(0, 12);
  if (!rows.length) return '<p class="cmp-empty">No progress to attribute for this code.</p>';
  const mx = Math.max(...rows.map(r => Math.max(r.planned || 0, r.actual || 0)), 1);
  const w = v => Math.max(2, Math.round(100 * (v || 0) / mx));
  return rows.map(r => {
    const gap = Math.round(((r.actual || 0) - (r.planned || 0)) * 10) / 10;
    const tag = gap >= -0.05 ? '<span class="per-slip-good">on/above plan</span>' : `<span class="per-slip-bad">${gap.toFixed(1)}% vs plan</span>`;
    return `<div class="per-bar2r"><div class="per-bar2r-h"><b>${escapeHtml(r.value)}</b> ${tag}</div>
      <div class="per-bar2r-t"><div class="per-bar2r-pl" style="width:${w(r.planned)}%"></div><div class="per-bar2r-ac" style="width:${w(r.actual)}%"></div></div>
      <div class="per-bar2r-n">planned ${_signPct(r.planned)} · actual ${_signPct(r.actual)}</div></div>`;
  }).join('');
}
function _wireByCode(report) {
  const sel = document.getElementById('per-bycode-type');
  const box = document.getElementById('per-bycode-bars');
  if (!sel || !box) return;
  sel.addEventListener('change', () => { box.innerHTML = _byCodeBars((report.progress_by_code || {})[sel.value]); });
}

// Milestone section: a table (baseline / prev / current / slippage) then a drift chart.
function _milestoneSection(report) {
  const ms = report.milestones || {};
  const rows = ms.rows || [];
  const overall = ms.overall;                 // project completion — the only row in the table
  if (!rows.length || !overall) return '<p class="cmp-empty">No project-completion milestone found in the update.</p>';
  const slip = (sp, sb) => sp == null ? '—'
    : (sp > 0 ? `<span class="per-slip-bad">▼ +${sp} d${sb != null ? ` (→ +${sb} d vs baseline)` : ''}</span>`
      : (sp < 0 ? `<span class="per-slip-good">▲ ${Math.abs(sp)} d earlier</span>` : `<span class="per-slip-good">• on track</span>`));
  const r = overall;
  const table = `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-table">
    <thead><tr><th>Project completion milestone</th><th class="num">Baseline</th><th class="num">Previous forecast</th>
      <th class="num">Current forecast</th><th>Slippage this period</th></tr></thead>
    <tbody><tr><td>${escapeHtml(r.name)}</td>
      <td class="num mono">${escapeHtml(r.baseline_finish)}</td><td class="num mono">${escapeHtml(r.prev_forecast)}</td>
      <td class="num mono">${escapeHtml(r.curr_forecast)}</td><td>${slip(r.slip_period_days, r.slip_baseline_days)}</td></tr></tbody></table></div>`;
  // chart shows ALL finish milestones
  return table + `<div class="cmp-scurve-card" style="margin-top:10px">${_milestoneDriftSvg(rows)}</div>`;
}

function _milestoneDriftSvg(rows) {
  const od = iso => Date.parse(iso);
  const all = [];
  rows.forEach(r => ['baseline_iso', 'prev_iso', 'curr_iso'].forEach(k => { if (r[k]) all.push(od(r[k])); }));
  if (all.length < 2) return '<span class="mut">Not enough milestone dates to draw the drift chart.</span>';
  let tmin = Math.min(...all), tmax = Math.max(...all);
  if (tmin === tmax) { tmin -= 8.64e7 * 15; tmax += 8.64e7 * 15; }
  const x0 = 150, x1 = 590, rowh = 30, top = 14, n = rows.length, h = top + n * rowh + 26;
  const xAt = t => x0 + (x1 - x0) * ((t - tmin) / (tmax - tmin));
  let parts = '';
  for (let k = 0; k < 5; k++) {
    const t = tmin + (tmax - tmin) * k / 4, x = xAt(t), d = new Date(t);
    const lab = d.toLocaleString('en', { month: 'short' }) + '-' + String(d.getFullYear()).slice(2);
    parts += `<line x1="${x.toFixed(0)}" y1="${top}" x2="${x.toFixed(0)}" y2="${top + n * rowh}" stroke="var(--border)"/><text x="${x.toFixed(0)}" y="${top + n * rowh + 15}" text-anchor="middle" font-size="9.5" fill="var(--muted)">${lab}</text>`;
  }
  rows.forEach((r, i) => {
    const y = top + i * rowh + 15;
    parts += `<text x="${x0 - 10}" y="${y + 4}" text-anchor="end" font-size="11" fill="var(--text)">${escapeHtml(r.name)}</text>`;
    const xs = ['baseline_iso', 'prev_iso', 'curr_iso'].filter(k => r[k]).map(k => xAt(od(r[k])));
    if (xs.length >= 2) parts += `<line x1="${Math.min(...xs).toFixed(0)}" y1="${y}" x2="${Math.max(...xs).toFixed(0)}" y2="${y}" stroke="var(--border)"/>`;
    if (r.baseline_iso) parts += `<circle cx="${xAt(od(r.baseline_iso)).toFixed(0)}" cy="${y}" r="5" fill="var(--card-bg)" stroke="#94a3b8" stroke-width="2"/>`;
    if (r.prev_iso) parts += `<circle cx="${xAt(od(r.prev_iso)).toFixed(0)}" cy="${y}" r="4.5" fill="#d97706"/>`;
    if (r.curr_iso) parts += `<circle cx="${xAt(od(r.curr_iso)).toFixed(0)}" cy="${y}" r="5" fill="#ef4444"/>`;
  });
  return `<div class="cmp-scurve-legend"><span><i style="background:var(--card-bg);border:2px solid #94a3b8;border-radius:50%;width:10px;height:10px"></i>Baseline</span><span><i style="background:#d97706;border-radius:50%;width:11px;height:11px"></i>Previous forecast</span><span><i style="background:#ef4444;border-radius:50%;width:11px;height:11px"></i>Current forecast</span></div>
    <svg viewBox="0 0 620 ${h}" width="100%" role="img" aria-label="Milestone drift chart">${parts}</svg>`;
}

// Recovery outlook (planning-manager projection — indicative, not a P6 CPM result).
function _recoveryHtml(report) {
  const r = report.recovery;
  if (!r) return '';
  let left = `Work remaining <b>${r.work_remaining == null ? '—' : r.work_remaining + '%'}</b> · this period earned <b>${r.current_rate == null ? '—' : r.current_rate + '%'}</b>.`;
  if (r.required_rate != null) {
    const ra = r.required_achievement;
    left += `<br>To still hit the <b>baseline finish (${escapeHtml(r.baseline_finish || '—')})</b> you'd need about <b>${r.required_rate}%/period</b>${ra != null ? ` (≈${Math.round(ra * 100)}% achievement)` : ''}.`;
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
    ${fact('New critical items', cm.new_critical || 0, 'entered critical path')}
  </div>`;
}

// Status verdict banner (reads the engine-computed verdict).
function _verdictBanner(report) {
  const v = report.verdict;
  if (!v) return '';
  return `<div class="per-banner ${v.level}"><span class="per-dot ${v.level}"></span>
    <div><div class="per-b1">${escapeHtml(v.headline)}</div><div class="per-b2">${escapeHtml(v.detail || '')}</div></div></div>`;
}

// Next-period watch list table.
function _watchTable(report) {
  const rows = (report.watch_list || {}).rows || [];
  if (!rows.length) return '<p class="cmp-empty">No near-critical work is queued for the next window.</p>';
  const body = rows.map(r => `<tr><td class="mono">${escapeHtml(r.activity_id)}</td>
    <td>${escapeHtml(r.activity_name)}</td><td class="num">${r.float_days} wd</td>
    <td class="num mono">${escapeHtml(r.due_to_start)}</td><td>${escapeHtml(r.reason)}</td></tr>`).join('');
  return `<div class="cmp-foot" style="margin:0 0 6px">The near-critical construction activities <b>most likely to drive the next reporting window</b> — not yet finished, with little spare time — tightest float first. Watch these to protect the finish date.</div>
    <div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-table">
    <thead><tr><th>Activity ID</th><th>Activity name</th><th class="num">Float</th>
      <th class="num">Due to start</th><th>Why watch it</th></tr></thead>
    <tbody>${body}</tbody></table></div>
    <div class="per-defs"><div class="per-defs-h">Columns</div>
      <div class="per-def"><b>Float</b> — spare working days before this activity would delay the project finish (0 = on the critical path; ≤ 10 wd = near-critical).</div>
      <div class="per-def"><b>Due to start</b> — the activity's forecast start date, from the current update.</div>
      <div class="per-def"><b>Why watch it</b> — why it's near-critical: on the critical path, a successor to something slipping, or newly near-critical.</div></div>`;
}

function _progressRows(rows) {
  return rows.map(r => {
    const cls = r.reversal ? 'cmp-pill bad' : 'cmp-pill good';
    const arrow = r.reversal ? '▼' : '▲';
    const flag = r.reversal ? ' ⚠' : '';
    const stCls = r.status === 'Completed' ? 'cmp-pill good' : 'cmp-pill';
    const status = `<span class="${stCls}">${escapeHtml(r.status || '')}</span>${r.reversal ? ' <span class="cmp-pill bad">reversed</span>' : ''}`;
    const codes = escapeHtml(JSON.stringify(r.codes || {}));   // per-row activity codes, for the slicer
    return `<tr data-codes="${codes}">
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
  const types = report.code_types || [];
  const slicer = types.length ? `<div class="per-slicer">
      <span class="per-slicer-lbl">Filter by activity code</span>
      <select id="per-code-type"><option value="">— all activities —</option>${types.map(t => `<option>${escapeHtml(t)}</option>`).join('')}</select>
      <span id="per-code-chips" class="per-chips"></span>
    </div>` : '';
  return `${slicer}
    <div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-table" id="per-prog-table">
      <thead><tr><th>Activity ID</th><th>Activity name</th><th>Status</th>
        <th class="num">Prev % <span style="font-weight:400">(${ph})</span></th>
        <th class="num">Current % <span style="font-weight:400">(${ch})</span></th>
        <th class="num">Variance</th></tr></thead>
      <tbody>${_progressRows(rows)}</tbody></table></div>
    <div class="cmp-foot">Pick an activity code to see just those activities’ current vs previous % complete. Biggest gain first; <span class="cmp-pill bad">▼</span> = progress declared backwards vs last update.</div>`;
}

// Wire the activity-code slicer: pick a code type → value chips → filter the table rows.
function _wireSlicer() {
  const sel = document.getElementById('per-code-type');
  const chipsEl = document.getElementById('per-code-chips');
  const table = document.getElementById('per-prog-table');
  if (!sel || !chipsEl || !table) return;
  const rows = Array.from(table.querySelectorAll('tbody tr'));
  const codesOf = tr => { try { return JSON.parse(tr.getAttribute('data-codes') || '{}'); } catch { return {}; } };
  const applyVal = (type, val) => rows.forEach(tr => {
    const c = codesOf(tr);
    tr.style.display = (!type || val === '__all__' || c[type] === val) ? '' : 'none';
  });
  const renderChips = type => {
    if (!type) { chipsEl.innerHTML = ''; rows.forEach(tr => { tr.style.display = ''; }); return; }
    const vals = Array.from(new Set(rows.map(tr => codesOf(tr)[type]).filter(Boolean))).sort();
    chipsEl.innerHTML = [`<span class="per-chip on" data-v="__all__">All</span>`]
      .concat(vals.map(v => `<span class="per-chip" data-v="${escapeHtml(v)}">${escapeHtml(v)}</span>`)).join('');
    chipsEl.querySelectorAll('.per-chip').forEach(chip => chip.addEventListener('click', () => {
      chipsEl.querySelectorAll('.per-chip').forEach(x => x.classList.remove('on'));
      chip.classList.add('on');
      applyVal(type, chip.getAttribute('data-v'));
    }));
    applyVal(type, '__all__');
  };
  sel.addEventListener('change', () => renderChips(sel.value));
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

function _criticalTable(cm, codeTypesArg) {
  const rows = (cm && cm.rows) || [];
  const newTxt = (cm && cm.new_critical)
    ? `<div class="cmp-foot"><b>${cm.new_critical}</b> activit${cm.new_critical === 1 ? 'y' : 'ies'} entered the critical path this window.</div>` : '';
  if (!rows.length) return `<p class="cmp-empty">No critical or near-critical activity moved this window.</p>${newTxt}`;
  const codeTypes = codeTypesArg || [];
  const body = rows.map(r => `<tr data-codes="${escapeHtml(JSON.stringify(r.codes || {}))}">
    <td class="mono">${escapeHtml(r.activity_id)}</td>
    <td>${escapeHtml(r.activity_name)}</td>
    <td>${escapeHtml(r.wbs || '')}</td>
    <td class="num mono mut">${escapeHtml(r.prev_finish)}</td>
    <td class="num mono">${escapeHtml(r.curr_finish)}</td>
    <td class="num">${r.slip_days > 0 ? `<span class="cmp-pill bad">+${r.slip_days} wd</span>` : '<span class="cmp-pill">—</span>'}</td>
    <td class="num">${r.float_days == null ? '—' : r.float_days + ' d'}</td>
    <td>${_driverTag(r.driver)}</td>
    <td>${_critStatus(r.critical_status)}</td>
  </tr>`).join('');
  const slicer = codeTypes.length ? `<div class="per-slicer">
      <span class="per-slicer-lbl">Filter by activity code</span>
      <select id="per-crit-type"><option value="">— all activities —</option>${codeTypes.map(t => `<option>${escapeHtml(t)}</option>`).join('')}</select>
      <span id="per-crit-chips" class="per-chips"></span></div>` : '';
  return `${slicer}<div class="tblwrap" style="overflow-x:auto"><table class="audit-table cmp-table" id="per-crit-table">
    <thead><tr><th>Activity ID</th><th>Activity name</th><th>WBS</th><th class="num">Finish (prev)</th>
      <th class="num">Finish (now)</th><th class="num">Slip</th><th class="num">Float</th>
      <th>Driver this period</th><th>Critical</th></tr></thead>
    <tbody>${body}</tbody></table></div>
    <div class="cmp-foot">Construction / execution activities only. Slip = working-day movement of the finish between the two updates. <b>▶ new</b> = entered the critical path this window.</div>${newTxt}`;
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

export function renderPeriodReport(report) {
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
    <div class="mod-sec">Progress — where you are vs where you said you’d be</div>
    ${_progressBarHtml(report)}
    <div class="mod-sec">Execution Dashboard — progress this period</div>
    ${_dashboard(report)}
    <div class="mod-sec">Critical-path comparison — the finish-driving route</div>
    ${_criticalCompareHtml(report)}
    <div class="mod-sec">Progress by activity — % complete this period</div>
    ${_progressSection(report)}
    <div class="mod-sec">Critical-path movement in this window</div>
    ${_criticalTable(report.critical_movement, report.code_types)}
    <div class="mod-sec">Next-period watch list</div>
    ${_watchTable(report)}
    <div class="mod-sec">What moved this period — planned vs actual</div>
    ${_whatMovedHtml(report)}
    <div class="mod-sec">Where this period’s progress came from — by activity code</div>
    ${_byCodeHtml(report)}
    <div class="mod-sec">Milestones — project completion &amp; all finish milestones</div>
    ${_milestoneSection(report)}
    <div class="mod-sec">Executive conclusion — this period</div>
    <div class="cmp-reco">${escapeHtml(report.conclusion || '')}</div>
    <div class="mod-sec">Project conclusion &amp; outlook</div>
    <div class="cmp-reco per-project-reco">${escapeHtml(report.project_conclusion || '')}</div>`;
  const epdf = document.getElementById('per-export-pdf');
  if (epdf) epdf.addEventListener('click', exportPeriodPdf);
  const exls = document.getElementById('per-export-xlsx');
  if (exls) exls.addEventListener('click', exportPeriodExcel);
  _wireSlicer();
  _wireCodeSlicer('per-crit-type', 'per-crit-chips', 'per-crit-table');
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

// Export PDF now PREVIEWS the report first (renders the exact HTML the PDF uses), then
// offers Save. Addresses "no preview during export".
export async function exportPeriodPdf() {
  if (!_shownReport) { showError('Run the comparison first, then export.'); return; }
  await _withBtn('per-export-pdf', 'Export PDF', async () => {
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/period/report`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report: _shownReport, trend: _shownTrend, preview: true, critical_style: _cpStyle, critical_mode: _cpMode }),
      });
      const data = await resp.json();
      if (!data.ok) { showError(`Preview failed: ${data.error || 'unknown error'}`); return; }
      _showPdfPreview(data.html);
    } catch { showError('Could not reach the local server for the preview.'); }
  });
}

const PER_SECTIONS = [
  ['verdict', 'Status verdict'], ['progress', 'Progress chart'], ['dashboard', 'Execution Dashboard'],
  ['recommendation', 'Management recommendation'], ['critical_compare', 'Critical-path comparison'],
  ['critical', 'Critical-path movement table'], ['progress_table', 'Progress by activity'],
  ['watch', 'Next-period watch list'], ['whatmoved', 'What moved this period'],
  ['bycode', 'Progress by activity code'], ['milestones', 'Milestones (table + chart)'], ['conclusions', 'Conclusions'],
];

function _showPdfPreview(reportHtml) {
  const existing = document.getElementById('per-preview-overlay');
  if (existing) existing.remove();
  const ov = document.createElement('div');
  ov.id = 'per-preview-overlay';
  ov.className = 'per-preview-overlay';
  const picks = PER_SECTIONS.map(([k, l]) =>
    `<label class="per-pick"><input type="checkbox" class="per-sec-cb" value="${k}" checked> ${escapeHtml(l)}</label>`).join('');
  const codeTypes = _shownReport.code_types || [];
  const fltUi = codeTypes.length ? `<div class="per-pick-h" style="margin-top:14px">Filter by activity code</div>
      <select id="per-flt-type" style="width:100%;margin-bottom:6px"><option value="">— none (all activities) —</option>${codeTypes.map(t => `<option>${escapeHtml(t)}</option>`).join('')}</select>
      <select id="per-flt-val" style="width:100%" disabled></select>` : '';
  const cpOpt = (v, l) => `<option value="${v}"${_cpStyle === v ? ' selected' : ''}>${l}</option>`;
  const cpStyleUi = `<div class="per-pick-h" style="margin-top:14px">Critical-path style</div>
      <select id="per-pdf-cp-style" style="width:100%">${cpOpt('chain', 'Connected chain')}${cpOpt('timeline', 'Date-axis timeline')}${cpOpt('table', 'Compact table')}</select>`;
  ov.innerHTML = `<div class="per-preview-box">
      <div class="per-preview-bar"><span class="per-preview-title">Report preview — choose what to include, then print or save</span>
        <span class="per-preview-actions">
          <button class="btn-secondary" id="per-preview-close">Close</button>
          <button class="btn-secondary" id="per-preview-print">🖨 Print…</button>
          <button class="btn-primary" id="per-preview-save">Save as PDF</button></span></div>
      <div class="per-preview-body">
        <div class="per-preview-pick"><div class="per-pick-h">Include sections</div>${picks}
          <div class="per-pick-controls"><button class="btn-mini" id="per-pick-all">All</button><button class="btn-mini" id="per-pick-none">None</button></div>
          ${fltUi}${cpStyleUi}</div>
        <iframe class="per-preview-frame" id="per-preview-frame" title="Report preview"></iframe>
      </div>
    </div>`;
  document.body.appendChild(ov);
  const frame = document.getElementById('per-preview-frame');
  const close = () => ov.remove();
  ov.addEventListener('click', e => { if (e.target === ov) close(); });
  document.getElementById('per-preview-close').addEventListener('click', close);

  const cbs = () => Array.from(ov.querySelectorAll('.per-sec-cb'));
  const selected = () => cbs().filter(c => c.checked).map(c => c.value);
  const typeSel = document.getElementById('per-flt-type');
  const valSel = document.getElementById('per-flt-val');
  const codeFilter = () => (typeSel && typeSel.value && valSel && valSel.value) ? { type: typeSel.value, value: valSel.value } : null;
  const cpStyleSel = document.getElementById('per-pdf-cp-style');
  const cpStyle = () => cpStyleSel ? cpStyleSel.value : _cpStyle;
  const applyToFrame = () => {
    const doc = frame.contentDocument;
    if (!doc) return;
    const on = new Set(selected());
    doc.querySelectorAll('[data-sec]').forEach(el => { el.style.display = on.has(el.getAttribute('data-sec')) ? '' : 'none'; });
  };
  // Re-render server-side when the activity-code filter changes (so preview == PDF).
  const refresh = async () => {
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/period/report`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report: _shownReport, trend: _shownTrend, preview: true, code_filter: codeFilter(), critical_style: cpStyle(), critical_mode: _cpMode }),
      });
      const data = await resp.json();
      if (data.ok) { frame.onload = applyToFrame; frame.srcdoc = data.html; }
    } catch { showError('Could not refresh the preview.'); }
  };
  frame.onload = applyToFrame;
  frame.srcdoc = reportHtml;

  cbs().forEach(c => c.addEventListener('change', applyToFrame));
  document.getElementById('per-pick-all').addEventListener('click', () => { cbs().forEach(c => { c.checked = true; }); applyToFrame(); });
  document.getElementById('per-pick-none').addEventListener('click', () => { cbs().forEach(c => { c.checked = false; }); applyToFrame(); });
  if (typeSel) typeSel.addEventListener('change', () => {
    const t = typeSel.value;
    if (!t) { valSel.innerHTML = ''; valSel.disabled = true; refresh(); return; }
    const vals = Array.from(new Set(((_shownReport.progress || {}).rows || []).map(r => (r.codes || {})[t]).filter(Boolean))).sort();
    valSel.innerHTML = vals.map(v => `<option>${escapeHtml(v)}</option>`).join('');
    valSel.disabled = !vals.length;
    refresh();
  });
  if (valSel) valSel.addEventListener('change', refresh);
  if (cpStyleSel) cpStyleSel.addEventListener('change', () => { _cpStyle = cpStyleSel.value; try { localStorage.setItem('per_cp_style', _cpStyle); } catch { /* no storage */ } refresh(); });

  document.getElementById('per-preview-print').addEventListener('click', () => {
    applyToFrame();
    try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch { showError('Could not open the print dialog.'); }
  });
  document.getElementById('per-preview-save').addEventListener('click', async () => {
    const outputPath = await window.pywebview.api.choose_save_path('update_vs_update.pdf', 'pdf');
    if (!outputPath) return;
    const btn = document.getElementById('per-preview-save');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/period/report`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report: _shownReport, trend: _shownTrend, output_path: outputPath, sections: selected(), code_filter: codeFilter(), critical_style: cpStyle(), critical_mode: _cpMode }),
      });
      const data = await resp.json();
      if (!data.ok) showError(`PDF export failed: ${data.error || 'unknown error'}`);
      else close();
    } catch { showError('Could not reach the local server to export the PDF.'); }
    finally { if (btn) { btn.disabled = false; btn.textContent = 'Save as PDF'; } }
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
        body: JSON.stringify({ report: _shownReport, trend: _shownTrend, output_path: outputPath }),
      });
      const data = await resp.json();
      if (!data.ok) showError(`Excel export failed: ${data.error || 'unknown error'}`);
    } catch { showError('Could not reach the local server to export to Excel.'); }
  });
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
    _shownTrend = data.ok ? data.trend : null;
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
export { _signPct as signPct, _shortDate as shortDate, _progressBarHtml as progressBarHtml,
         _milestoneSection as milestoneSection, _dashboard as dashboardHtml,
         _cpTimelineData as criticalTimelineData, _cpCompareBody as criticalCompareBody };
