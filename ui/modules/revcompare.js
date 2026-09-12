// Baseline Revision Comparison — compare two approved baseline revisions (Rev.00 vs
// Rev.01) from a planning/consultant perspective. Workflow: assign both revisions →
// Run Comparison → review results across NINE sub-tabs (Executive Summary · Key Findings ·
// Critical Path & Float · Change Register [duration] · Milestones · Calendar ·
// Cost & Resources · Manpower · Scope & Structure). Neutral by design: Change detected →
// Potential impact → Planning review, never an automatic verdict. Nothing runs until Run
// is pressed. The scope / logic / duration / money activity-code selections carry into the
// PDF (a `filters` object flows client → server → render_html).

import { state } from './state.js';
import { showError, clearError } from './render.js';
import { escapeHtml } from './format.js';
import { getSavedMode } from './appearance.js';
import { showReportPreview } from './preview.js';
import { revealAndRun } from './featurereveal.js';
import { exportRevcompareExcel } from './api.js';

// Nine sub-tabs — the same keys are used for the PDF `data-sec` sections, the Excel
// sheets and the report-contents picker.
const RC_TABS = [
  ['summary', 'Executive Summary'], ['findings', 'Key Findings'],
  ['critical', 'Critical Path & Float'], ['register', 'Change Register'],
  ['ms', 'Milestones'], ['cal', 'Calendar'],
  ['cost', 'Cost & Resources'], ['manpower', 'Manpower'],
  ['scope', 'Scope & Structure'],
];

// ── Module-level activity-code filter state (carried into the PDF) ───────────────
// scope   → Executive Summary scope-by-code analysis
// logic   → Key Findings logic & sequence chart
// duration→ Change Register duration analysis + table
// money   → Cost & Resources "where the money moved"
const rcFilters = {
  scope:    { dim: null, val: 'All' },
  logic:    { dim: null, val: 'All' },
  duration: { dim: null, val: 'All' },
  money:    { dim: null },
};
function resetFilters() {
  rcFilters.scope = { dim: null, val: 'All' };
  rcFilters.logic = { dim: null, val: 'All' };
  rcFilters.duration = { dim: null, val: 'All' };
  rcFilters.money = { dim: null };
}
// The filters object sent to the PDF renderer. Each part is omitted when no dimension is
// active; a val of 'All' (or absent) means "no filter" on the server side.
function buildFilters() {
  const f = {};
  if (rcFilters.scope.dim) f.scope = { dim: rcFilters.scope.dim, val: rcFilters.scope.val };
  if (rcFilters.logic.dim) f.logic = { dim: rcFilters.logic.dim, val: rcFilters.logic.val };
  if (rcFilters.duration.dim) f.duration = { dim: rcFilters.duration.dim, val: rcFilters.duration.val };
  if (rcFilters.money.dim) f.money = { dim: rcFilters.money.dim };
  return f;
}

export function renderRevComparePanel() {
  const body = document.getElementById('revcompare-body');
  if (!body) return;
  if (state.revcompareReport) { renderResults(body); return; }
  renderInputs(body);
}

// ── 1. Inputs — assign both revisions, then Run ──────────────────────────────

function _slot(kind, label, sub, assigned) {
  const badge = kind === 'r0' ? 'Rev.00 · Original' : 'Rev.01 · Revised';
  const inner = assigned
    ? `<div class="rc-file">
         <span class="rc-fic">${IC.file}</span>
         <div class="rc-fmeta"><div class="rc-fn">${escapeHtml(assigned.name)}</div><div class="rc-fm">assigned</div></div>
         <span class="rc-chk">${IC.chk}</span>
       </div>`
    : `<div class="rc-empty"><span>${IC.file}</span><div class="rc-et">No file assigned</div></div>`;
  return `<div class="rc-slot ${kind} ${assigned ? 'filled' : ''}">
      <span class="rc-badge">${badge}</span>
      <h4>${label}</h4><div class="rc-sub">${sub}</div>
      ${inner}
      <button class="rc-assign" data-assign="${kind}">${assigned ? 'Change…' : 'Assign file'}</button>
    </div>`;
}

function renderInputs(body) {
  // Convenience: pre-fill Rev.01 with the currently-open schedule the first time in.
  if (!state.revcompareRev1 && state.currentXmlPath) {
    state.revcompareRev1 = { path: state.currentXmlPath, name: (state.currentXmlPath.split(/[\\/]/).pop() || 'current') };
  }
  const ready = state.revcompareRev0 && state.revcompareRev1;
  body.innerHTML = `
    <div class="rc-hd">
      <div class="rc-fi">${IC.flip}</div>
      <div><h2>Baseline Revision Comparison</h2>
        <p>Compare two approved baseline revisions and see what changed — and whether it materially affected the planned execution strategy, logic, sequence, critical path, milestones, scope or duration. Analytical, evidence-based and neutral: <b>Change detected → Potential impact → Planning review</b>, never an automatic verdict.</p></div>
    </div>
    <div class="rc-steps">
      <div class="rc-step done"><span class="rc-sn">${IC.chk}</span>Select feature</div><span class="rc-arw">›</span>
      <div class="rc-step ${ready ? 'done' : 'on'}"><span class="rc-sn">${ready ? IC.chk : '2'}</span>Assign required inputs</div><span class="rc-arw">›</span>
      <div class="rc-step ${ready ? 'on' : ''}"><span class="rc-sn">3</span>Run comparison</div><span class="rc-arw">›</span>
      <div class="rc-step"><span class="rc-sn">4</span>Review results</div>
    </div>
    <div class="rc-card">
      <div class="rc-sec">Required inputs — assign both, then run</div>
      <div class="rc-slots">
        ${_slot('r0', 'Original Baseline', 'The first approved baseline programme (the reference).', state.revcompareRev0)}
        ${_slot('r1', 'Revised Baseline', 'The re-submitted / revised baseline to compare against Rev.00.', state.revcompareRev1)}
      </div>
      <div style="display:flex;justify-content:center;margin-top:10px">
        <button class="rc-mini" id="rc-swap">${IC.flip} Swap Rev.00 ⇄ Rev.01</button>
      </div>
      <div class="rc-sec" style="margin-top:18px">Comparison options</div>
      <div class="rc-opts">
        <label class="rc-opt"><input type="checkbox" id="rc-opt-fuzzy" checked> Fuzzy activity matching <span class="rc-mut">(beyond Activity ID — name · WBS · dates · codes)</span></label>
        <label class="rc-opt"><input type="checkbox" id="rc-opt-cp" checked> Recompute critical path &amp; float</label>
      </div>
      <div class="rc-runbar">
        <button class="rc-run ${ready ? '' : 'disabled'}" id="rc-run" ${ready ? '' : 'disabled'}>${IC.run} Run Comparison</button>
        <div class="rc-rn">Nothing is analysed until you press <b>Run Comparison</b>. Assigning a file never triggers the comparison on its own.</div>
      </div>
    </div>
    <div class="rc-callout"><b>Matching before diffing.</b> Activities are first matched across the two revisions on the evidence — name, WBS, codes, dates and surrounding logic, not the Activity ID alone — so an activity that kept its work but changed ID reads as an <b>identity change</b>, not a false “removed + added”.</div>`;

  body.querySelectorAll('[data-assign]').forEach(b =>
    b.addEventListener('click', () => assignFile(b.dataset.assign)));
  const swap = body.querySelector('#rc-swap');
  if (swap) swap.addEventListener('click', () => {
    const t = state.revcompareRev0; state.revcompareRev0 = state.revcompareRev1; state.revcompareRev1 = t;
    renderInputs(body);
  });
  const run = body.querySelector('#rc-run');
  if (run) run.addEventListener('click', runComparison);
}

async function assignFile(kind) {
  const path = await window.pywebview.api.choose_file();
  if (!path) return;
  const rec = { path, name: (path.split(/[\\/]/).pop() || 'file') };
  if (kind === 'r0') state.revcompareRev0 = rec; else state.revcompareRev1 = rec;
  clearError();
  renderInputs(document.getElementById('revcompare-body'));
}

async function runComparison() {
  if (!state.revcompareRev0 || !state.revcompareRev1) { showError('Assign both baseline revisions first.'); return; }
  const body = document.getElementById('revcompare-body');
  clearError();
  const options = {
    fuzzy: document.getElementById('rc-opt-fuzzy')?.checked !== false,
    recompute_cp: document.getElementById('rc-opt-cp')?.checked !== false,
  };
  // Branded feature-open presentation (Loading → 100%) plays over the panel, then the
  // comparison computes + renders — same experience as every other feature.
  revealAndRun(body, 'Baseline Revision Comparison', async () => {
    body.innerHTML = '<div class="rc-loading">Comparing Rev.00 vs Rev.01…</div>';
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/revcompare`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rev0_path: state.revcompareRev0.path, rev1_path: state.revcompareRev1.path, options }),
      });
      const data = await resp.json();
      if (!data.ok) { showError(data.error || 'Comparison failed.'); renderInputs(body); return; }
      state.revcompareReport = data.report;
      state.revcompareTab = 'summary';
      resetFilters();
      renderResults(body);
    } catch {
      showError('Could not reach the local server. Try restarting the app.');
      renderInputs(body);
    }
  });
}

// ── 2. Results shell + sub-tabs ──────────────────────────────────────────────

function renderResults(body) {
  const r = state.revcompareReport;
  const tab = state.revcompareTab || 'summary';
  const tabs = RC_TABS.map(([k, l]) =>
    `<button class="rc-tab ${k === tab ? 'on' : ''}" data-rctab="${k}">${escapeHtml(l)}</button>`).join('');
  const view = ({
    summary: summaryView, findings: findingsView, critical: criticalView,
    register: registerView, ms: milestonesView, cal: calendarView,
    cost: costView, manpower: manpowerView, scope: scopeView,
  }[tab] || summaryView)(r);
  body.innerHTML = `
    <div class="rc-bar">
      <div class="rc-revtags">
        <span class="rc-revtag r0"><b>Rev.00</b> ${escapeHtml(r.rev0.file || '—')} · ${escapeHtml(String(r.rev0.activities ?? '—'))} act</span>
        <span class="rc-revtag r1"><b>Rev.01</b> ${escapeHtml(r.rev1.file || '—')} · ${escapeHtml(String(r.rev1.activities ?? '—'))} act</span>
      </div>
      <div class="rc-seg">${tabs}</div>
      <button class="rc-mini" id="rc-reset">${IC.flip} New comparison</button>
      <button class="rc-mini" id="rc-preview-pdf">⬇ PDF</button>
      <button class="rc-mini" id="rc-export-xlsx">⬇ Excel</button>
    </div>
    ${r.warnings && r.warnings.length ? `<div class="rc-warn">${IC.warn} ${r.warnings.map(escapeHtml).join(' · ')}</div>` : ''}
    <div id="rc-view">${view}</div>`;
  body.querySelectorAll('[data-rctab]').forEach(b =>
    b.addEventListener('click', () => { state.revcompareTab = b.dataset.rctab; renderResults(body); }));
  body.querySelector('#rc-reset').addEventListener('click', () => {
    state.revcompareReport = null; resetFilters(); renderInputs(body);
  });
  body.querySelector('#rc-preview-pdf').addEventListener('click', openRevcompareReport);
  body.querySelector('#rc-export-xlsx').addEventListener('click', exportRevcompareExcel);
  if (tab === 'summary') wireSummary(body);
  else if (tab === 'findings') wireFindings(body);
  else if (tab === 'register') wireRegister(body);
  else if (tab === 'cost') wireCost(body);
}

// ── shared helpers ─────────────────────────────────────────────────────────────

const IC = {
  flip: svg('<path d="M17 3l4 4-4 4M21 7H9M7 21l-4-4 4-4M3 17h12"/>'),
  file: svg('<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6"/>'),
  chk: svg('<path d="M20 6L9 17l-5-5"/>', 2.4),
  run: svg('<path d="M5 3l14 9-14 9z"/>'),
  warn: svg('<path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'),
};
function svg(p, w = 1.9) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
}
function typeTag(kind, label) {
  return `<span class="rc-tag ${kind}">${escapeHtml(String(label ?? kind ?? ''))}</span>`;
}
export function num(n, sign) {
  if (n == null) return '—';
  if (sign && n > 0) return `+${n}`;
  return String(n);
}
export function deltaCell(d) {
  if (d == null) return '<span class="rc-d zero">—</span>';
  if (typeof d === 'string') return `<span class="rc-d">${escapeHtml(d)}</span>`;
  const cls = d > 0 ? 'up' : d < 0 ? 'down' : 'zero';
  return `<span class="rc-d ${cls}">${d > 0 ? '+' : ''}${d}</span>`;
}
// Section marker heading (mirrors the report's numbered sections).
function secmark(n, title, sub) {
  return `<div class="rc-secmark"><span class="rc-sn2">${n}</span><h2>${escapeHtml(title)}</h2>${sub ? `<span class="rc-subm">${escapeHtml(sub)}</span>` : ''}</div>`;
}
// Graceful "no data / not applicable" note — never crashes, never a verdict.
function noData(msg) { return `<div class="rc-nodata">${escapeHtml(msg)}</div>`; }

// ── Shared number formatter (comment 9) ─────────────────────────────────────────
// One formatter for every value / money / cost figure: thousands separators + 2 decimals
// (124563 → "124,563.00"). Counts stay integer via fmtInt (no decimals where natural).
function fmtNum(n, d = 2) {
  if (n == null || (typeof n === 'number' && !isFinite(n))) return '—';
  const v = Number(n);
  if (isNaN(v)) return escapeHtml(String(n));
  return v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}
function fmtInt(n) {
  if (n == null || (typeof n === 'number' && !isFinite(n))) return '—';
  const v = Number(n);
  if (isNaN(v)) return escapeHtml(String(n));
  return Math.round(v).toLocaleString('en-US');
}
// Compact money label for a chart bar (£1.2M / £300K / value). Small, above-bar friendly.
function fmtMoney(n) {
  if (n == null || !isFinite(Number(n))) return '—';
  const v = Number(n), a = Math.abs(v), s = v < 0 ? '-' : '';
  if (a >= 1e6) return `${s}${(a / 1e6).toFixed(a / 1e6 >= 10 ? 1 : 2)}M`;
  if (a >= 1e3) return `${s}${(a / 1e3).toFixed(0)}K`;
  return `${s}${Math.round(a)}`;
}
function esc(v) { return escapeHtml(v != null ? String(v) : '—'); }
// Normalise a date-ish string to a 'Mon YYYY' month key (matches curves.months labels).
function monthLabel(str) {
  if (!str) return null;
  const d = new Date(str);
  if (isNaN(d.getTime())) return null;
  return d.toLocaleString('en-US', { month: 'short', year: 'numeric' });
}
// Thin an axis label list down to ~6 readable ticks.
function thinLabels(months) {
  const n = months.length;
  if (!n) return [];
  const step = Math.max(1, Math.ceil(n / 6));
  const out = [];
  months.forEach((m, i) => { if (i % step === 0 || i === n - 1) out.push({ i, m }); });
  return out;
}

// Deterministic theme-token colour for a code value (by first-seen order). No hardcoded
// hex — every colour resolves through the appearance-mode chart tokens.
const CHART_TOKENS = ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5', '--chart-6'];
function tokenColor(value, order) {
  const i = Array.isArray(order) ? order.indexOf(value) : -1;
  return i < 0 ? 'var(--accent)' : `var(${CHART_TOKENS[i % CHART_TOKENS.length]})`;
}

// Vertical histogram with a data label above every bar (comments 1, 3, 8, 10, 11).
// items: [{ label, v, color }]. opts.money → compact money labels; else integer counts.
// Scrolls horizontally inside .rc-chartwrap; SVG uses theme tokens only.
function barsSvg(items, opts = {}) {
  if (!items || !items.length) return noData(opts.emptyMsg || 'No data to chart.');
  const w = Math.max(560, items.length * 74), h = 234, L = 46, B = 42, T = 28;
  const pw = w - L - 16, ph = h - T - B, step = pw / items.length, bw = Math.min(40, step * 0.6);
  const mx = Math.max(1, ...items.map(i => Math.abs(i.v || 0)));
  let s = '';
  items.forEach((it, i) => {
    const x = L + i * step + step / 2;
    const bh = Math.abs(it.v || 0) / mx * ph, y = T + ph - bh;
    const label = opts.money ? fmtMoney(it.v) : fmtInt(it.v) + (opts.suffix || '');
    s += `<rect x="${(x - bw / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, bh).toFixed(1)}" rx="3" fill="${it.color || 'var(--accent)'}"/>`;
    s += `<text x="${x.toFixed(1)}" y="${(y - 6).toFixed(1)}" font-size="10" font-weight="700" fill="var(--ink-soft)" text-anchor="middle">${escapeHtml(label)}</text>`;
    s += `<text x="${x.toFixed(1)}" y="${(T + ph + 15).toFixed(1)}" font-size="9" fill="var(--muted)" text-anchor="middle">${escapeHtml(String(it.label ?? ''))}</text>`;
  });
  return `<div class="rc-chartwrap"><svg viewBox="0 0 ${w} ${h}" class="rc-svg" style="min-width:${w}px" role="img" aria-label="Bar chart">
    <line x1="${L}" y1="${T + ph}" x2="${w - 16}" y2="${T + ph}" stroke="var(--border)"/>${s}</svg></div>`;
}

// Distinct code values for a dimension across a set of rows carrying a `.codes` map.
function codeValues(rows, dim) {
  return [...new Set((rows || []).map(x => (x.codes || {})[dim]).filter(v => v != null && v !== ''))];
}
// Small chip-row builder (dimension picker + value picker share this look).
function chipRow(labelHtml, items, cur, attr) {
  return labelHtml + items.map(v =>
    `<button class="rc-fchip ${v === cur ? 'on' : ''}" data-${attr}="${escapeHtml(String(v))}">${esc(v)}</button>`).join('');
}

// ══ 1 · Executive Summary ══════════════════════════════════════════════════════

function kv(k, v, hot) {
  return `<div class="rc-kv"><span class="rc-kvk">${escapeHtml(k)}</span><span class="rc-kvv ${hot ? 'hot' : ''}">${esc(v)}</span></div>`;
}

function summaryView(r) {
  const rev0 = r.rev0 || {}, rev1 = r.rev1 || {};
  const slip = r.slip || {};
  const slipWd = slip.total_wd != null ? slip.total_wd : (r.summary && r.summary.finish_shift_days);
  const bl = r.bottom_line
    ? `<div class="rc-bottomline"><span class="rc-blpin">📌</span><span><b>Bottom line:</b> ${escapeHtml(r.bottom_line)}</span></div>`
    : '';

  const sameDD = rev0.data_date != null && rev1.data_date != null && rev0.data_date === rev1.data_date;
  const snapFoot = `Like-for-like: both files 0% complete (baselines, no actuals)${sameDD ? ' · same data date verified' : ''} · Rev.01 governing finish is <b>logic-driven</b>.`;
  const snap = `
    <div class="rc-card"><h3>Revision snapshot <span class="rc-n">Rev.00 → Rev.01</span></h3>
      <div class="rc-snap">
        <div class="rc-snapcol r0"><div class="rc-snaptag">Rev.00 · Original</div><div class="rc-snapfile">${esc(rev0.file)}</div>
          ${kv('Data date', rev0.data_date)}${kv('Governing finish', rev0.finish)}${kv('Activities', rev0.activities != null ? fmtInt(rev0.activities) : null)}</div>
        <div class="rc-snapmid"><div class="rc-big">${slipWd != null ? num(slipWd, true) + 'd' : '—'}</div><div class="rc-biglbl">Finish slip</div></div>
        <div class="rc-snapcol r1"><div class="rc-snaptag">Rev.01 · Revised</div><div class="rc-snapfile">${esc(rev1.file)}</div>
          ${kv('Data date', rev1.data_date)}${kv('Governing finish', rev1.finish, slipWd > 0)}${kv('Activities', rev1.activities != null ? fmtInt(rev1.activities) : null)}</div>
      </div>
      <div class="rc-foot" style="margin-top:10px">${snapFoot}</div></div>`;

  // Comparison ledger — a composite measure renders as one centered cell spanning both
  // revision columns, total in the Change column.
  const ledgerRows = (r.ledger || []).map(l => {
    const composite = l.rev1 == null && typeof l.delta === 'string' && l.delta;
    if (composite) {
      return `<tr><td>${esc(l.label)}</td>
        <td class="n rc-mut" colspan="2" style="text-align:center">${esc(l.delta)}</td>
        <td class="n">${l.rev0 != null ? `<span class="rc-d">${esc(l.rev0)}</span>` : '—'}</td></tr>`;
    }
    return `<tr><td>${esc(l.label)}</td>
      <td class="n rc-mut">${l.rev0 != null ? esc(l.rev0) : '—'}</td>
      <td class="n rc-new">${l.rev1 != null ? esc(l.rev1) : '—'}</td>
      <td class="n">${deltaCell(l.delta)}</td></tr>`;
  }).join('');
  const ledgerCard = `<div class="rc-card"><h3>Comparison ledger</h3>
    ${ledgerRows ? `<table class="rc-t"><thead><tr><th>Measure</th><th class="n">Rev.00</th><th class="n">Rev.01</th><th class="n">Change</th></tr></thead><tbody>${ledgerRows}</tbody></table>`
                 : noData('No comparison measures available.')}</div>`;

  // Credibility / red flags (constraint row removed per comment 6).
  const q = r.quality || {};
  const cc = r.calendar_changes || {};
  const credRow = (label, o) => {
    if (!o) return '';
    const d = (o.rev1 != null && o.rev0 != null) ? o.rev1 - o.rev0 : null;
    return `<tr><td>${escapeHtml(label)}</td><td class="n rc-mut">${o.rev0 != null ? esc(o.rev0) : '—'}</td><td class="n rc-new">${o.rev1 != null ? esc(o.rev1) : '—'}</td><td class="n">${deltaCell(d)}</td></tr>`;
  };
  const calDefs = Array.isArray(cc.calendars) ? cc.calendars.length : 0;
  const calReassign = Array.isArray(cc.reassignments) ? cc.reassignments.reduce((s, g) => s + (g.count || 0), 0) : 0;
  const calRow = (calDefs || calReassign)
    ? `<tr><td>Calendars changed</td><td class="n rc-mut" colspan="2" style="text-align:center">${calDefs} definition(s) · ${calReassign} activities reassigned</td><td class="n">${deltaCell('!')}</td></tr>`
    : '';
  const credRows = [
    credRow('Negative-float activities', q.negative_float),
    credRow('Open ends (dangling)', q.open_ends),
    calRow,
    credRow('Leads (negative lags)', q.leads),
  ].filter(Boolean).join('');
  const credCard = `<div class="rc-card rc-flag"><h3 class="rc-flagh">Schedule-quality signals <span class="rc-n">signals to review</span></h3>
    ${credRows ? `<table class="rc-t"><thead><tr><th>Signal</th><th class="n">Rev.00</th><th class="n">Rev.01</th><th class="n">Δ</th></tr></thead><tbody>${credRows}</tbody></table>`
               : noData('No schedule-quality signals available.')}</div>`;

  return secmark('1', 'Executive Summary') + bl + snap
    + `<div class="rc-split">${ledgerCard}${credCard}</div>`
    + scopeAnalysisCard(r);
}

// Scope change — activity-code ANALYSIS (comment 1). No Building column: pick a dimension,
// click a code value → the count, the bar chart (added activities per code value) and the
// itemised list all update; the {dim,val} carries into the PDF.
function scopeDims(r) {
  const codes = r.codes || {};
  const added = codes.added || [], removed = codes.removed || [];
  const all = [...added, ...removed];
  const declared = codes.dimensions || [];
  const dims = declared.filter(d => all.some(x => (x.codes || {})[d] != null && (x.codes || {})[d] !== ''));
  if (all.some(x => (x.codes || {}).WBS)) { if (!dims.includes('WBS')) dims.push('WBS'); }
  return dims;
}

function scopeAnalysisCard(r) {
  const codes = r.codes || {};
  if (!codes || (!(codes.added || []).length && !(codes.removed || []).length)) {
    return `<div class="rc-card"><h3>Scope change <span class="rc-n">added &amp; removed, by activity code</span></h3>${noData('No added or removed activities to analyse by activity code.')}</div>`;
  }
  const dims = scopeDims(r);
  if (!dims.length) {
    return `<div class="rc-card"><h3>Scope change <span class="rc-n">added &amp; removed, by activity code</span></h3>${noData('No activity-code dimensions available for a scope breakdown.')}</div>`;
  }
  if (!rcFilters.scope.dim || !dims.includes(rcFilters.scope.dim)) { rcFilters.scope.dim = dims[0]; rcFilters.scope.val = 'All'; }
  return `<div class="rc-card"><h3>Scope change — analysis by activity code
      <span class="rc-n">click a code to filter</span> <span class="rc-pdfnote">🔵 reflects in PDF</span></h3>
    <div class="rc-sec">How many activities were added / removed, by activity code — pick a dimension, then a code value; the count, chart and list update</div>
    <div class="rc-filters" id="rc-scope-dim"></div>
    <div class="rc-filters" id="rc-scope-vals"></div>
    <div id="rc-scope-chart"></div>
    <div id="rc-scope-tbl" style="margin-top:10px"></div></div>`;
}

function renderScopeChart(body) {
  const host = body.querySelector('#rc-scope-chart');
  const tbl = body.querySelector('#rc-scope-tbl');
  if (!host || !tbl) return;
  const r = state.revcompareReport || {};
  const codes = r.codes || {};
  const dim = rcFilters.scope.dim, val = rcFilters.scope.val;
  const added = (codes.added || []).map(x => ({ ...x, k: 'Added' }));
  const removed = (codes.removed || []).map(x => ({ ...x, k: 'Removed' }));
  const all = [...added, ...removed];
  // Chart: added activities per value of the selected dimension.
  const vals = [...new Set(all.map(x => (x.codes || {})[dim]).filter(v => v != null && v !== ''))];
  const items = vals.map(v => ({
    label: v,
    v: added.filter(x => (x.codes || {})[dim] === v).length,
    color: tokenColor(v, vals),
  }));
  host.innerHTML = `<div class="rc-sec" style="margin-bottom:4px">Added activities by ${escapeHtml(dim)}</div>` + barsSvg(items, { emptyMsg: 'No added activities to chart for this dimension.' });
  // Itemised list filtered by the selected value — no Building column (comment 1).
  const rows = all.filter(x => val === 'All' || (x.codes || {})[dim] === val);
  const addedN = rows.filter(x => x.k === 'Added').length, removedN = rows.filter(x => x.k === 'Removed').length;
  const dimCol = dim === 'WBS' ? 'Discipline' : dim;
  const dimColHdr = dim === 'WBS' ? (scopeDims(r).includes('Discipline') ? 'Discipline' : dim) : dim;
  const cellDim = (x) => dim === 'WBS'
    ? esc((x.codes || {}).Discipline || x.scope)
    : esc((x.codes || {})[dim]);
  const list = rows.map(x => `<tr>
      <td class="rc-aid">${esc(x.id)}</td><td>${esc(x.name)}</td>
      <td><span class="rc-tag ${x.k === 'Added' ? 'add' : 'rem'}">${x.k}</span></td>
      <td class="rc-mut">${esc(x.wbs)}</td><td>${cellDim(x)}</td></tr>`).join('');
  tbl.innerHTML = `<div class="rc-callout">Showing <b>${esc(val)}</b>: <b>${fmtInt(addedN)} added</b> · <b>${fmtInt(removedN)} removed</b>.</div>
    <div class="rc-tblscroll" style="margin-top:8px"><table class="rc-t">
      <thead><tr><th>Activity ID</th><th>Activity Name</th><th>Change</th><th>WBS</th><th>${escapeHtml(dimColHdr)}</th></tr></thead>
      <tbody>${list || `<tr><td colspan="5" class="rc-mut">None for this code.</td></tr>`}</tbody></table></div>`;
}

function renderScopeVals(body) {
  const host = body.querySelector('#rc-scope-vals');
  if (!host) return;
  const r = state.revcompareReport || {};
  const codes = r.codes || {};
  const all = [...(codes.added || []), ...(codes.removed || [])];
  const vals = ['All', ...codeValues(all, rcFilters.scope.dim)];
  host.innerHTML = chipRow('<b class="rc-fblbl">Activity code:</b>', vals, rcFilters.scope.val, 'scopeval');
  host.querySelectorAll('[data-scopeval]').forEach(c => c.addEventListener('click', () => {
    rcFilters.scope.val = c.dataset.scopeval;
    renderScopeVals(body);
    renderScopeChart(body);
  }));
}

function wireSummary(body) {
  const dimHost = body.querySelector('#rc-scope-dim');
  if (!dimHost) return;
  const r = state.revcompareReport || {};
  const dims = scopeDims(r);
  if (!dims.length) return;
  dimHost.innerHTML = chipRow('<b class="rc-fblbl">Dimension:</b>', dims, rcFilters.scope.dim, 'scopedim');
  dimHost.querySelectorAll('[data-scopedim]').forEach(c => c.addEventListener('click', () => {
    dimHost.querySelectorAll('[data-scopedim]').forEach(x => x.classList.toggle('on', x === c));
    rcFilters.scope.dim = c.dataset.scopedim;
    rcFilters.scope.val = 'All';
    renderScopeVals(body);
    renderScopeChart(body);
  }));
  renderScopeVals(body);
  renderScopeChart(body);
}

// ══ 2 · Key Findings ═════════════════════════════════════════════════════════

// Shared, theme-token palette. The finish-slip waterfall bars and the contribution
// breakdown list index into it identically, so a cause keeps ONE colour in both.
const SLIP_PALETTE = ['--chart-3', '--warning', '--chart-1', '--chart-4', '--chart-5', '--chart-2', '--chart-6'];
const slipColor = (i) => `var(${SLIP_PALETTE[i % SLIP_PALETTE.length]})`;

function slipWaterfall(slip) {
  const cs = (slip && slip.contributions) || [];
  if (!cs.length) return noData('No finish-slip attribution available.');
  const total = slip.total_wd != null ? slip.total_wd : cs.reduce((s, c) => s + (c.wd || 0), 0);
  const W = 900, base = 200, top = 46;
  const sumPos = cs.reduce((s, c) => s + Math.max(0, c.wd || 0), 0);
  const maxV = Math.max(Math.abs(total), sumPos, 1);
  const scale = (base - top) / maxV;
  const n = cs.length;
  const leftPad = 90, rightPad = 110;
  const plotW = W - leftPad - rightPad;
  const colStep = plotW / (n + 1);
  const bw = Math.min(66, colStep * 0.55);
  const xc = (i) => leftPad + (i + 1) * colStep;

  let cum = 0, bars = '', conns = '', labels = '';
  cs.forEach((c, i) => {
    const before = cum; cum += (c.wd || 0); const after = cum;
    const hiV = Math.max(before, after), loV = Math.min(before, after);
    const y = base - hiV * scale, h = Math.max(1, (hiV - loV) * scale);
    const cx = xc(i), col = slipColor(i);
    bars += `<rect x="${(cx - bw / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="${col}"/>`;
    labels += `<text x="${cx.toFixed(1)}" y="${(y - 6).toFixed(1)}" font-size="11" fill="var(--ink-soft)" text-anchor="middle" font-weight="700">${num(c.wd || 0, true)}</text>`;
    labels += `<text x="${cx.toFixed(1)}" y="${(base + 18).toFixed(1)}" font-size="9" fill="var(--muted)" text-anchor="middle">${escapeHtml(String(c.cause || ''))}</text>`;
    if (i > 0) {
      const py = base - before * scale;
      conns += `<line x1="${(xc(i - 1) + bw / 2).toFixed(1)}" y1="${py.toFixed(1)}" x2="${(cx - bw / 2).toFixed(1)}" y2="${py.toFixed(1)}"/>`;
    }
  });
  const tx = leftPad + (n + 1) * colStep;
  const th = Math.max(1, Math.abs(total) * scale);
  bars += `<rect x="${(tx - bw / 2).toFixed(1)}" y="${(base - th).toFixed(1)}" width="${bw.toFixed(1)}" height="${th.toFixed(1)}" rx="2" fill="var(--danger)" opacity=".9"/>`;
  labels += `<text x="${tx.toFixed(1)}" y="${(base - th - 6).toFixed(1)}" font-size="12" fill="var(--danger)" text-anchor="middle" font-weight="800">${num(total, true)}</text>`;
  labels += `<text x="${tx.toFixed(1)}" y="${(base + 18).toFixed(1)}" font-size="9" fill="var(--ink-soft)" text-anchor="middle" font-weight="700">Rev.01 · ${esc(slip.rev1_finish)}</text>`;

  return `<svg viewBox="0 0 ${W} 235" class="rc-svg" style="min-width:720px" role="img" aria-label="Finish-slip attribution waterfall">
    <line x1="${leftPad}" y1="${base}" x2="${W - rightPad + 40}" y2="${base}" stroke="var(--border)"/>
    <line x1="${leftPad}" y1="${base - 5}" x2="${leftPad}" y2="${base + 5}" stroke="var(--muted)"/>
    <text x="${leftPad}" y="${base + 18}" font-size="9" fill="var(--muted)" text-anchor="middle">Rev.00 finish</text>
    <text x="${leftPad}" y="${base + 30}" font-size="9" fill="var(--muted)" text-anchor="middle">${esc(slip.rev0_finish)}</text>
    <g stroke="var(--border)" stroke-dasharray="3 3">${conns}</g>
    ${bars}${labels}
  </svg>`;
}

function findingsView(r) {
  const slip = r.slip || {};
  const slipHead = slip.total_wd != null ? `What drove the ${num(slip.total_wd, true)} days` : 'What drove the slip';
  const contribs = slip.contributions || [];
  const contribList = contribs.length
    ? `<div class="rc-contribs">${contribs.map((c, i) => `
        <div class="rc-contrib">
          <span class="rc-cswatch" style="background:${slipColor(i)}"></span>
          <span class="rc-ccause">${esc(c.cause)}</span>
          <span class="rc-cwd">${num(c.wd || 0, true)} d</span>
          <span class="rc-cmean">${esc(c.detail)}</span>
        </div>`).join('')}</div>`
    : '';
  const slipCard = `<div class="rc-card"><h3>${escapeHtml(slipHead)} <span class="rc-n">finish-slip bridge · neutral attribution</span></h3>
    <div class="rc-sec">Reads left → right: starts at the Rev.00 finish; each step adds the working days that cause pushed the finish out; the last bar is the Rev.01 finish</div>
    <div class="rc-chartwrap">${slipWaterfall(r.slip)}</div>
    <div class="rc-howto"><b>How to read it —</b> each coloured step is a <b>cause</b>; its height is the <b>working days it added</b>. A bigger step is a bigger driver. The tool only <b>attributes</b> the movement — it never says a change is wrong.</div>
    ${contribList}</div>`;

  const logicCard = `<div class="rc-card"><h3>Logic &amp; Sequence Changes
      <span class="rc-n">each box shows the full WBS path — like the Critical Path Analyzer</span> <span class="rc-pdfnote">🔵 reflects in PDF</span></h3>
    <div class="rc-sec">Bigger boxes, side by side, with big arrows — pick a dimension, then a code to filter</div>
    <div class="rc-filters" id="rc-logic-dim"></div>
    <div class="rc-filters" id="rc-logic-vals"></div>
    <div id="rc-logic-chart" class="rc-chartwrap"></div></div>`;

  return secmark('2', 'Key Findings') + slipCard + logicCard;
}

// ── Logic & Sequence Changes — BIG side-by-side WBS-breadcrumb boxes (comment 2) ──

function logicDims(r) {
  const declared = (r.codes && r.codes.dimensions) || [];
  const seen = new Set();
  (r.logic_register || []).forEach(l => Object.keys(l.codes || {}).forEach(k => seen.add(k)));
  const dims = declared.filter(d => seen.has(d));
  seen.forEach(k => { if (!dims.includes(k)) dims.push(k); });
  return dims;
}

// WBS breadcrumb segments (deepest → shallowest) for an activity end. Prefers a full
// per-end wbs path when the row carries one; falls back to the row's WBS top-branch code
// plus discipline/building context so the box always reads like the CPA breadcrumb.
function crumbSegs(l, wbsKey) {
  const full = l[wbsKey];
  if (full && typeof full === 'string') {
    const segs = full.split(/\s*[›>]\s*/).filter(Boolean);
    if (segs.length) return segs.reverse();
  }
  const codes = l.codes || {};
  const segs = [];
  if (codes.WBS) segs.push(codes.WBS);
  if (codes.Discipline && codes.Discipline !== codes.WBS) segs.push(codes.Discipline);
  if (codes.Building && codes.Building !== codes.WBS) segs.push(codes.Building);
  return segs.length ? segs : ['(no WBS)'];
}

function crumbBox(name, id, segs, moved) {
  return `<div class="rc-lnode${moved ? ' moved' : ''}">
    <div class="rc-ln">${esc(name)}</div>
    <div class="rc-lb">@ ${segs.map(esc).join(' @ ')}</div>
    <div class="rc-lid">${esc(id)}</div></div>`;
}

function logicBlock(l) {
  const change = String(l.change || '');
  const kind = /added/i.test(change) ? 'added' : /removed/i.test(change) ? 'removed' : 'changed';
  const tag = kind === 'added' ? 'add' : kind === 'removed' ? 'rem' : 'chg';
  const pSegs = crumbSegs(l, 'pred_wbs'), sSegs = crumbSegs(l, 'succ_wbs');
  const ctx = [l.codes && (l.codes.Discipline || l.codes.scope), l.codes && l.codes.Building].filter(Boolean).map(esc).join(' · ');
  const arrow = (label, cls) => `<div class="rc-larw ${cls}"><span class="rc-lt">${esc(label)}</span><span class="rc-ar">→</span></div>`;
  return `<div class="rc-relhd">
      <span class="rc-tag ${tag}">${esc(l.change)}</span>
      ${l.on_cp ? '<span class="rc-cpbadge">on critical path</span>' : ''}
      ${l.is_lead ? '<span class="rc-sev crit">lead</span>' : ''}
      ${ctx ? `<span class="rc-mut" style="font-size:10.5px">${ctx}</span>` : ''}</div>
    <div class="rc-rrow">Rev.00 — before</div>
    <div class="rc-lchain">${crumbBox(l.pred_name, l.pred_id, pSegs)}${arrow(l.before, '')}${crumbBox(l.succ_name, l.succ_id, sSegs)}</div>
    <div class="rc-rrow r1">Rev.01 — after</div>
    <div class="rc-lchain">${crumbBox(l.pred_name, l.pred_id, pSegs, kind === 'changed')}${arrow(l.after, kind)}${crumbBox(l.succ_name, l.succ_id, sSegs, kind === 'changed')}</div>`;
}

function renderLogicChart(body) {
  const host = body.querySelector('#rc-logic-chart');
  if (!host) return;
  const r = state.revcompareReport || {};
  const all = r.logic_register || [];
  const dim = rcFilters.logic.dim, val = rcFilters.logic.val || 'All';
  if (!all.length) { host.innerHTML = noData('No relationship changes to chart.'); return; }
  const rows = all.filter(l => val === 'All' || ((l.codes || {})[dim]) === val);
  if (!rows.length) { host.innerHTML = noData('No relationship changes for this code.'); return; }
  const groups = {}, order = [];
  rows.forEach(l => { const g = (l.codes || {})[dim] || '(no code)'; if (!(g in groups)) { groups[g] = []; order.push(g); } groups[g].push(l); });
  host.innerHTML = order.map(g => {
    const rs = groups[g];
    return `<div class="rc-loghd" style="background:${tokenColor(g, order)}">${esc(g)}<span class="rc-loghd-ct">${rs.length} change${rs.length > 1 ? 's' : ''}</span></div>`
      + rs.map(logicBlock).join('');
  }).join('');
}

function renderLogicVals(body) {
  const host = body.querySelector('#rc-logic-vals');
  if (!host) return;
  const r = state.revcompareReport || {};
  const vals = ['All', ...codeValues(r.logic_register, rcFilters.logic.dim)];
  host.innerHTML = chipRow('<b class="rc-fblbl">Activity code:</b>', vals, rcFilters.logic.val || 'All', 'logicval');
  host.querySelectorAll('[data-logicval]').forEach(c => c.addEventListener('click', () => {
    rcFilters.logic.val = c.dataset.logicval;
    renderLogicVals(body);
    renderLogicChart(body);
  }));
}

function wireFindings(body) {
  const dimHost = body.querySelector('#rc-logic-dim');
  if (!dimHost) return;
  const r = state.revcompareReport || {};
  const dims = logicDims(r);
  if (!dims.length) { const chart = body.querySelector('#rc-logic-chart'); if (chart) chart.innerHTML = noData('No activity-code dimensions available to group the logic changes.'); return; }
  if (!rcFilters.logic.dim || !dims.includes(rcFilters.logic.dim)) { rcFilters.logic.dim = dims[0]; rcFilters.logic.val = 'All'; }
  dimHost.innerHTML = chipRow('<b class="rc-fblbl">Group by:</b>', dims, rcFilters.logic.dim, 'logicdim');
  dimHost.querySelectorAll('[data-logicdim]').forEach(c => c.addEventListener('click', () => {
    dimHost.querySelectorAll('[data-logicdim]').forEach(x => x.classList.toggle('on', x === c));
    rcFilters.logic.dim = c.dataset.logicdim;
    rcFilters.logic.val = 'All';
    renderLogicVals(body);
    renderLogicChart(body);
  }));
  renderLogicVals(body);
  renderLogicChart(body);
}

// ══ 3 · Critical Path & Float ══════════════════════════════════════════════════

function cpNode(n) {
  const cls = n.state === 'enter' ? 'enter' : n.state === 'leave' ? 'leave' : (n.tf != null && n.tf <= 0 ? 'crit' : '');
  let dates = '';
  if (n.is_ms) {
    dates = n.finish ? esc(n.finish) : '';
  } else {
    const s = n.start ? esc(n.start) : '';
    const f = n.finish ? esc(n.finish) : '';
    dates = (s && f) ? `${s} – ${f}` : (s || f);
  }
  const sub = dates ? `<span class="rc-nf">${dates}</span>` : '';
  return `<div class="rc-node ${cls}">${esc(n.name)}${sub}</div>`;
}
function cpChain(nodes) {
  if (!nodes || !nodes.length) return '<div class="rc-mut">No driving path available for this revision.</div>';
  return nodes.map(cpNode).join('<span class="rc-arw">→</span>');
}

function criticalView(r) {
  const cp = r.critical_path || {};
  const entered = cp.entered || [], left = cp.left || [];
  const leftNames = left.map(e => esc(e.name)).join(', ');
  const cpLabel = (side) => {
    const rev = (side === 'r0' ? r.rev0 : r.rev1) || {};
    const len = side === 'r0' ? cp.rev0_len : cp.rev1_len;
    const tf = side === 'r0' ? cp.rev0_tf_finish : cp.rev1_tf_finish;
    const tag = side === 'r0' ? 'Rev.00' : 'Rev.01';
    const parts = [];
    if (rev.finish) parts.push(`ends ${esc(rev.finish)}`);
    if (len != null) parts.push(`path length ${esc(len)} wd`);
    if (tf != null) parts.push(`TF on finish ${esc(tf)}`);
    return `<div class="rc-cklab${side === 'r1' ? ' r1' : ''}">${tag}${parts.length ? ' — ' + parts.join(' · ') : ''}</div>`;
  };
  const cpCard = `<div class="rc-card"><h3>Driving chain <span class="rc-n">${cp.length_change_wd != null ? `Rev.01 critical path ${num(cp.length_change_wd, true)} wd · dates on each node` : 'driving chain · dates on each node'}</span></h3>
    ${cpLabel('r0')}
    <div class="rc-chainwrap"><div class="rc-chain">${cpChain(cp.rev0)}</div></div>
    ${cpLabel('r1')}
    <div class="rc-chainwrap"><div class="rc-chain">${cpChain(cp.rev1)}</div></div>
    <div class="rc-leg">
      <span><span class="rc-ld enter"></span>Entered CP (${entered.length})</span>
      <span><span class="rc-ld crit"></span>Critical in both</span>
      <span><span class="rc-ld leave"></span>Left CP (${left.length})${left.length ? ': ' + leftNames : ''}</span>
    </div></div>`;

  const q = r.quality || {};
  const bands = q.float_bands || [];
  const maxBand = Math.max(1, ...bands.map(b => Math.max(b.rev0 || 0, b.rev1 || 0)));
  const bandBars = bands.map(b => {
    const neg = String(b.band).startsWith('<0') || String(b.band).includes('negative');
    return `<div class="rc-sbar"><div class="rc-sbl ${neg ? 'rc-negband' : ''}">${esc(b.band)}${neg ? ' (negative)' : ''}</div>
      <div class="rc-track"><div class="rc-f0" style="width:${Math.round((b.rev0 || 0) / maxBand * 100)}%"></div><div class="rc-f1" style="width:${Math.round((b.rev1 || 0) / maxBand * 100)}%"></div></div>
      <div class="rc-sbv">${b.rev0 || 0} / ${b.rev1 || 0}</div></div>`;
  }).join('');
  const bandCard = `<div class="rc-card"><h3>Total-float band shift <span class="rc-n">Rev.00 vs Rev.01</span></h3>
    <div class="rc-sec">How float is distributed across the two revisions${q.near_critical ? ` · near-critical ${esc(q.near_critical.rev0)} → ${esc(q.near_critical.rev1)}` : ''}</div>
    ${bands.length ? bandBars + `<div class="rc-legend"><span><i style="background:var(--muted)"></i>Rev.00</span><span><i style="background:var(--accent)"></i>Rev.01</span></div>` : noData('No float-band distribution available.')}</div>`;

  const nf = q.negative_float || {};
  const reg = nf.register || [];
  const nfRows = reg.map(a => `<tr><td class="rc-aid">${esc(a.id)}</td><td>${esc(a.name)}</td>
      <td class="n">${a.tf != null ? `<span class="rc-d up">${a.tf} d</span>` : '—'}</td><td class="rc-mut">${esc(a.wbs)}</td></tr>`).join('');
  const nfCard = `<div class="rc-card rc-flag"><h3 class="rc-flagh">Negative-float register <span class="rc-n">${reg.length} activities</span></h3>
    ${reg.length ? `<div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Activity ID</th><th>Activity Name</th><th class="n">Total Float</th><th>WBS</th></tr></thead><tbody>${nfRows}</tbody></table></div>`
                 : noData('No activities carry negative float in Rev.01.')}</div>`;

  return secmark('3', 'Critical Path & Float') + cpCard + `<div class="rc-split">${bandCard}${nfCard}</div>`;
}

// ══ 4 · Change Register — Duration only (comment 3) ═════════════════════════════

export const REG_BUCKET = {
  added: 'scope', removed: 'scope', renamed: 'scope', idchange: 'identity',
  moved_wbs: 'wbs', wbs_add: 'wbs', wbs_remove: 'wbs', wbs_rename: 'wbs',
};
export function bucketOf(t) { return REG_BUCKET[t] || t; }

function durationDims(r) {
  const rows = r.duration_table || [];
  const declared = (r.codes && r.codes.dimensions) || [];
  const seen = new Set();
  rows.forEach(d => Object.keys(d.codes || {}).forEach(k => seen.add(k)));
  const dims = declared.filter(d => seen.has(d));
  seen.forEach(k => { if (!dims.includes(k)) dims.push(k); });
  return dims;
}

function registerView(r) {
  const rows = r.duration_table || [];
  if (!rows.length) {
    return secmark('4', 'Change Register', 'activity-duration changes only')
      + `<div class="rc-card"><h3>Duration changed</h3>${noData('No activity duration changes.')}</div>`;
  }
  const dims = durationDims(r);
  const analysis = dims.length
    ? `<div class="rc-card"><h3>Duration-change analysis <span class="rc-n">by activity code</span></h3>
        <div class="rc-sec">Average duration change (%) by code — pick a dimension</div>
        <div class="rc-filters" id="rc-dur-dim"></div>
        <div id="rc-dur-chart"></div></div>`
    : '';
  const tableCard = `<div class="rc-card"><h3>Duration changed <span class="rc-n">working days · filter by activity code</span></h3>
      ${dims.length ? '<div class="rc-filters" id="rc-dur-vals"></div>' : ''}
      <div id="rc-dur-tbl"></div></div>`;
  return secmark('4', 'Change Register', 'activity-duration changes only · separate ID / Name columns · filter by activity code')
    + analysis + tableCard;
}

function renderDurChart(body) {
  const host = body.querySelector('#rc-dur-chart');
  if (!host) return;
  const r = state.revcompareReport || {};
  const rows = r.duration_table || [];
  const dim = rcFilters.duration.dim;
  const vals = codeValues(rows, dim);
  const items = vals.map(v => {
    const g = rows.filter(d => (d.codes || {})[dim] === v && typeof d.before === 'number' && typeof d.after === 'number' && d.before);
    if (!g.length) return { label: v, v: 0, color: tokenColor(v, vals) };
    const avg = g.reduce((s, d) => s + Math.abs((d.after - d.before) / d.before * 100), 0) / g.length;
    return { label: v, v: Math.round(avg), color: tokenColor(v, vals) };
  });
  host.innerHTML = `<div class="rc-sec" style="margin-bottom:4px">Average duration change (%) by ${escapeHtml(dim)}</div>`
    + barsSvg(items, { suffix: '%', emptyMsg: 'No measurable duration changes for this dimension.' });
}

function renderDurTable(body) {
  const host = body.querySelector('#rc-dur-tbl');
  if (!host) return;
  const r = state.revcompareReport || {};
  const rows = r.duration_table || [];
  const dim = rcFilters.duration.dim, val = rcFilters.duration.val;
  const filtered = rows.filter(d => !dim || val === 'All' || (d.codes || {})[dim] === val);
  // Columns: Activity ID · Name · WBS · Before · After · Variance · % change.
  // (Calendar and "TF After" columns removed — comment 3.)
  const body_ = filtered.map(d => {
    const bNum = typeof d.before === 'number', aNum = typeof d.after === 'number';
    const v = (bNum && aNum) ? d.after - d.before : (typeof d.variance === 'number' ? d.variance : null);
    const pct = (bNum && aNum && d.before) ? Math.round((d.after - d.before) / d.before * 100) : null;
    return `<tr><td class="rc-aid">${esc(d.id)}</td><td>${esc(d.name)}</td><td class="rc-mut">${esc(d.wbs)}</td>
      <td class="n">${bNum ? d.before + ' d' : esc(d.before)}</td>
      <td class="n rc-new">${aNum ? d.after + ' d' : esc(d.after)}</td>
      <td class="n">${v != null ? `<span class="rc-d ${v > 0 ? 'up' : v < 0 ? 'down' : 'zero'}">${v > 0 ? '+' : ''}${v} d</span>` : (d.before == null || d.after == null ? '<span class="rc-tag add">Added</span>' : '—')}</td>
      <td class="n">${pct != null ? `<span class="rc-d ${pct > 0 ? 'up' : pct < 0 ? 'down' : 'zero'}">${pct > 0 ? '+' : ''}${pct}%</span>` : '—'}</td></tr>`;
  }).join('');
  host.innerHTML = `<div class="rc-tblscroll"><table class="rc-t">
    <thead><tr><th>Activity ID</th><th>Activity Name</th><th>WBS</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th><th class="n">% change</th></tr></thead>
    <tbody>${body_ || '<tr><td colspan="7" class="rc-mut">No duration changes for this code.</td></tr>'}</tbody></table></div>`;
}

function renderDurVals(body) {
  const host = body.querySelector('#rc-dur-vals');
  if (!host) return;
  const r = state.revcompareReport || {};
  const vals = ['All', ...codeValues(r.duration_table, rcFilters.duration.dim)];
  host.innerHTML = chipRow('<b class="rc-fblbl">Filter:</b>', vals, rcFilters.duration.val, 'durval');
  host.querySelectorAll('[data-durval]').forEach(c => c.addEventListener('click', () => {
    rcFilters.duration.val = c.dataset.durval;
    renderDurVals(body);
    renderDurTable(body);
  }));
}

function wireRegister(body) {
  const r = state.revcompareReport || {};
  const dims = durationDims(r);
  const dimHost = body.querySelector('#rc-dur-dim');
  if (dims.length) {
    if (!rcFilters.duration.dim || !dims.includes(rcFilters.duration.dim)) { rcFilters.duration.dim = dims[0]; rcFilters.duration.val = 'All'; }
    if (dimHost) {
      dimHost.innerHTML = chipRow('<b class="rc-fblbl">Dimension:</b>', dims, rcFilters.duration.dim, 'durdim');
      dimHost.querySelectorAll('[data-durdim]').forEach(c => c.addEventListener('click', () => {
        dimHost.querySelectorAll('[data-durdim]').forEach(x => x.classList.toggle('on', x === c));
        rcFilters.duration.dim = c.dataset.durdim;
        rcFilters.duration.val = 'All';
        renderDurChart(body);
        renderDurVals(body);
        renderDurTable(body);
      }));
    }
    renderDurChart(body);
    renderDurVals(body);
  } else {
    rcFilters.duration.dim = null; rcFilters.duration.val = 'All';
  }
  renderDurTable(body);
}

// ══ 5 · Milestones (comment 5 — Activity ID + Type columns) ═════════════════════

function milestonesView(r) {
  const rows = (r.milestones || []).filter(m => m.kind !== 'unchanged').map(m => {
    const id = m.id != null ? m.id : (m.activity_id != null ? m.activity_id : m.code);
    const name = m.name || m.activity_name || id;
    const varCell = m.change_days != null
      ? deltaCell(`${m.change_days > 0 ? '+' : ''}${m.change_days} d`)
      : (m.kind === 'new' ? '<span class="rc-tag add">Added</span>' : m.kind === 'removed' ? '<span class="rc-tag rem">Removed</span>' : '—');
    const type = m.type || (m.hard ? 'Contract' : '');
    return `<tr><td class="rc-aid">${esc(id)}</td><td>${esc(name)}${(m.kind === 'new') ? '<span class="rc-tag add" style="margin-left:6px">NEW</span>' : ''}</td>
      <td>${type ? `<span class="rc-tag">${esc(type)}</span>` : '<span class="rc-mut">—</span>'}</td>
      <td class="n rc-mut">${esc(m.rev0)}</td><td class="n rc-new">${esc(m.rev1)}</td><td class="n">${varCell}</td></tr>`;
  }).join('');
  const card = `<div class="rc-card"><h3>Milestone changed <span class="rc-n">with Activity ID &amp; Type</span></h3>
    ${rows ? `<div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Activity ID</th><th>Activity Name</th><th>Type</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr></thead><tbody>${rows}</tbody></table></div>`
           : noData('No milestone changes between the two revisions.')}
    <div class="rc-foot" style="margin-top:8px">Type is a best-effort label from the milestone name (Contract vs Internal); a planner can reclassify. Neutral label, not a judgement.</div></div>`;
  return secmark('5', 'Milestones', 'finish-milestone date changes') + card;
}

// ══ 6 · Calendar (comment 7 — chart of working-days-per-week per calendar) ══════

// Parse "workweek 5-day → 6-day" out of a calendar-definition detail string.
function parseWorkweek(detail) {
  const m = /workweek\s+(\d+)\s*-?\s*day\s*(?:→|->|to)\s*(\d+)\s*-?\s*day/i.exec(String(detail || ''));
  if (!m) return null;
  return { before: Number(m[1]), after: Number(m[2]) };
}

function calWeekBar(name, before, after, note) {
  const mx = 7;
  const seg = (v, cls, dark) => v == null
    ? '<div class="rc-mut" style="align-self:center">—</div>'
    : `<div class="${cls}" style="width:${Math.max(6, v / mx * 45)}%;border-radius:4px;display:flex;align-items:center;justify-content:flex-end;padding-right:5px;color:${dark ? 'var(--rc-l-ink)' : 'var(--text)'};font-size:10px;font-weight:700">${v}d</div>`;
  const delta = (before != null && after != null && after !== before)
    ? `<span class="rc-d ${after > before ? 'up' : 'down'}">${after > before ? '+' : ''}${after - before}d/wk</span>`
    : '<span class="rc-mut">same</span>';
  return `<div class="rc-sbar" style="grid-template-columns:170px 1fr 96px">
      <div>${esc(name)}${note ? `<div class="rc-mut" style="font-size:10px">${esc(note)}</div>` : ''}</div>
      <div class="rc-track" style="height:22px;background:transparent;gap:6px">${seg(before, 'rc-f0-solid', false)}${seg(after, 'rc-f1', true)}</div>
      <div class="rc-sbv">${delta}</div></div>`;
}

function calendarView(r) {
  const cc = r.calendar_changes || {};
  const defs = cc.calendars || [], reass = cc.reassignments || [];
  const bars = [];
  let paperAccel = false;

  // Calendar-definition changes with a parseable workweek shift.
  defs.forEach(c => {
    if (c.change === 'added') { bars.push(calWeekBar(c.name, null, null, 'calendar added')); return; }
    if (c.change === 'removed') { bars.push(calWeekBar(c.name, null, null, 'calendar removed')); return; }
    const ww = parseWorkweek(c.detail);
    if (ww) {
      bars.push(calWeekBar(c.name, ww.before, ww.after, esc(c.detail)));
      if (ww.after > ww.before) paperAccel = true;
    } else {
      bars.push(calWeekBar(c.name, null, null, c.detail || 'definition changed'));
    }
  });
  // Per-activity reassignments (from → to) with their working-day/week change and count.
  reass.forEach(g => {
    const note = `${g.count} activit${g.count === 1 ? 'y' : 'ies'} · ${esc(g.from)} → ${esc(g.to)}`;
    bars.push(calWeekBar(`${g.from} → ${g.to}`, g.from_wd, g.to_wd, note));
    if (g.from_wd != null && g.to_wd != null && g.to_wd > g.from_wd) paperAccel = true;
  });

  const chart = bars.length
    ? `${bars.join('')}
       <div class="rc-legend"><span><i class="rc-f0-solid" style="display:inline-block;width:11px;height:11px;border-radius:3px"></i>Rev.00 days/week</span><span><i style="background:var(--accent)"></i>Rev.01 days/week</span></div>
       ${paperAccel ? '<div class="rc-callout warn">A calendar moved to a longer working week — durations shorten <b>on paper</b> without changing the work. A paper acceleration to confirm (approved basis vs inadvertent reassignment).</div>' : ''}`
    : noData('No calendar definition or reassignment changes between the two revisions.');

  const card = `<div class="rc-card"><h3>Working days per week — Rev.00 vs Rev.01 <span class="rc-n">per calendar</span></h3>
    <div class="rc-sec">A calendar switched to a longer week shortens durations on paper — shown here as a before → after chart</div>
    ${chart}</div>`;
  return secmark('6', 'Calendar', 'calendar-definition & per-activity reassignment changes') + card;
}

// ══ 7 · Cost & Resources (comments 8, 9, 10) ═══════════════════════════════════

// Planned-value chart — monthly Rev.01 bars with a value LABEL above each (comment 8),
// plus the Rev.00/Rev.01 cumulative curves. Value labels use the compact money formatter.
function scurveSvg(curves, rev0finish) {
  const vm = curves.value_monthly || [];
  const vc = curves.value_cumulative || [];
  const months = curves.months || vm.map(x => x.month);
  const n = months.length;
  if (!n || !vm.length) return noData('No planned-value spread available.');
  const W = Math.max(760, n * 60), plotL = 52, plotR = W - 30, plotT = 28, plotB = 250;
  const colW = (plotR - plotL) / n;
  const bw = Math.min(26, colW * 0.5);
  const byMonth0 = {}, byMonth1 = {};
  vm.forEach(x => { byMonth0[x.month] = x.rev0 || 0; byMonth1[x.month] = x.rev1 || 0; });
  const maxMonthly = Math.max(1, ...vm.map(x => Math.max(x.rev0 || 0, x.rev1 || 0)));
  let bars = '';
  months.forEach((m, i) => {
    const cx = plotL + (i + 0.5) * colW;
    const v1 = byMonth1[m] || 0;
    const h1 = (v1 / maxMonthly) * (plotB - plotT), y1 = plotB - h1;
    bars += `<rect x="${(cx - bw / 2).toFixed(1)}" y="${y1.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0, h1).toFixed(1)}" rx="2" fill="var(--accent)" opacity=".85"/>`;
    if (v1 > 0) bars += `<text x="${cx.toFixed(1)}" y="${(y1 - 5).toFixed(1)}" font-size="9" font-weight="700" fill="var(--ink-soft)" text-anchor="middle">${escapeHtml(fmtMoney(v1))}</text>`;
  });
  const cumByMonth = {}; vc.forEach(x => { cumByMonth[x.month] = x; });
  const maxCum = Math.max(1, ...vc.map(x => Math.max(x.rev0 || 0, x.rev1 || 0)));
  const line = (key, stroke, sw) => {
    const pts = months.map((m, i) => {
      const cx = plotL + (i + 0.5) * colW;
      const val = cumByMonth[m] ? (cumByMonth[m][key] || 0) : 0;
      const y = plotB - (val / maxCum) * (plotB - plotT);
      return `${cx.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    return `<polyline points="${pts}" fill="none" stroke="${stroke}" stroke-width="${sw}"/>`;
  };
  let origLine = '';
  const ml = monthLabel(rev0finish);
  const fi = ml != null ? months.indexOf(ml) : -1;
  if (fi >= 0) {
    const x = plotL + (fi + 1) * colW;
    origLine = `<line x1="${x.toFixed(1)}" y1="${plotT}" x2="${x.toFixed(1)}" y2="${plotB}" stroke="var(--danger)" stroke-dasharray="4 3"/>
      <text x="${(x + 4).toFixed(1)}" y="${plotT + 12}" font-size="9" fill="var(--danger)">orig finish ${esc(rev0finish)}</text>`;
  }
  const xlabels = thinLabels(months).map(({ i, m }) => {
    const cx = plotL + (i + 0.5) * colW;
    return `<text x="${cx.toFixed(1)}" y="${plotB + 14}" font-size="8" fill="var(--muted)" text-anchor="middle">${escapeHtml(String(m))}</text>`;
  }).join('');
  return `<div class="rc-chartwrap"><svg viewBox="0 0 ${W} 280" class="rc-svg" style="min-width:${W}px" role="img" aria-label="Planned value chart">
    <line x1="${plotL}" y1="${plotB}" x2="${plotR}" y2="${plotB}" stroke="var(--border)"/>
    <line x1="${plotL}" y1="${plotT}" x2="${plotL}" y2="${plotB}" stroke="var(--border)"/>
    ${bars}
    ${line('rev0', 'var(--muted)', 2.2)}
    ${line('rev1', 'var(--accent-dark)', 2.6)}
    ${origLine}${xlabels}
  </svg></div>`;
}

function moneyDims(curves) {
  const bbd = (curves && curves.budget_by_dim) || {};
  return Object.keys(bbd).filter(d => Array.isArray(bbd[d]) && bbd[d].length);
}

function costView(r) {
  const curves = r.curves || {};
  const rc = r.resource_changes || {};
  const hasCostTbl = !!(rc.cost_available || (rc.activity_cost_changes && rc.activity_cost_changes.length));
  const hasResTbl = !!(rc.resource_available || (rc.assignment_changes && rc.assignment_changes.length));
  if (!curves.cost_available && !curves.resource_available && !hasCostTbl && !hasResTbl) {
    return secmark('7', 'Cost & Resources', 'planned value, where the money moved, cost & resource changes')
      + `<div class="rc-card"><h3>Cost &amp; resources <span class="rc-n">optional</span></h3>${noData('Neither revision carries cost or resource loading — this section is reported as not applicable rather than "no change".')}</div>`;
  }

  // Planned value of work — value labels above each bar (comment 8).
  const scurve = curves.cost_available
    ? `<div class="rc-card"><h3>Planned value of work <span class="rc-n">monthly value (label above each bar) + cumulative</span></h3>
        ${scurveSvg(curves, r.rev0 && r.rev0.finish)}
        <div class="rc-legend"><span><i style="background:var(--accent)"></i>Rev.01 value/mo</span><span><i class="rc-line" style="background:var(--muted)"></i>Rev.00 cumulative</span><span><i class="rc-line" style="background:var(--accent-dark)"></i>Rev.01 cumulative</span></div>
        ${Number(curves.value_after_orig_finish) > 0 ? `<div class="rc-callout warn"><b>${fmtNum(curves.value_after_orig_finish)} of planned value now falls after the original finish (${esc(r.rev0 && r.rev0.finish)})</b> — potential extended-works exposure (prolongation, prelims, plant hire). Surfaced for review.</div>` : ''}
      </div>`
    : `<div class="rc-card"><h3>Planned value of work</h3>${noData('No cost loading — planned-value chart not applicable.')}</div>`;

  // Where the money moved — activity-code selector + variance bar chart (comment 10).
  const mdims = moneyDims(curves);
  const moneyCard = mdims.length
    ? `<div class="rc-card"><h3>Where the money moved <span class="rc-n">by activity code</span> <span class="rc-pdfnote">🔵 reflects in PDF</span></h3>
        <div class="rc-filters" id="rc-money-dim"></div>
        <div id="rc-money-chart"></div>
        <div id="rc-money-tbl" style="margin-top:8px"></div></div>`
    : `<div class="rc-card"><h3>Where the money moved</h3>${noData('No budget-by-code breakdown available.')}</div>`;

  // Cost changed table (comment 9 — thousands + 2 decimals).
  const costChanges = rc.activity_cost_changes || [];
  const pick = (row, keys) => { for (const k of keys) { if (row[k] != null && row[k] !== '') return row[k]; } return null; };
  const costRows = costChanges.slice(0, 40).map(c => {
    const id = pick(c, ['code', 'activity_id', 'id']), name = pick(c, ['name', 'activity_name']);
    const b = typeof c.rev0 === 'number' ? c.rev0 : null, a = typeof c.rev1 === 'number' ? c.rev1 : null;
    return `<tr><td class="rc-aid">${esc(id)}</td><td>${esc(name)}${(b == null || a == null) ? '<span class="rc-tag add" style="margin-left:6px">NEW</span>' : ''}</td>
      <td class="n rc-mut">${b != null ? fmtNum(b) : '—'}</td><td class="n rc-new">${a != null ? fmtNum(a) : '—'}</td>
      <td class="n">${(b != null && a != null) ? `<span class="rc-d ${a - b >= 0 ? 'up' : 'down'}">${a - b >= 0 ? '+' : ''}${fmtNum(a - b)}</span>` : '<span class="rc-tag add">Added</span>'}</td></tr>`;
  }).join('');
  const costCard = (hasCostTbl)
    ? `<div class="rc-card"><h3>Cost changed <span class="rc-n">budget total cost · variance</span></h3>
        ${costRows ? `<div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Activity ID</th><th>Activity Name</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr></thead><tbody>${costRows}</tbody></table></div>` : noData('No activity-level cost changes.')}</div>`
    : '';

  // Resource changed table.
  const resRows = (rc.assignment_changes || []).map(a => {
    const id = pick(a, ['activity_id', 'code', 'id']), name = pick(a, ['activity_name', 'name']);
    const kindTag = { added: 'add', removed: 'rem' }[a.kind] || 'chg';
    const kindLabel = { added: 'Added', removed: 'Removed', units: 'Units', rate: 'Rate' }[a.kind] || a.kind || 'Changed';
    return `<tr><td class="rc-aid">${esc(id)}</td><td>${esc(name)}</td>
      <td class="rc-aid">${esc(a.resource_id)}</td><td>${esc(a.resource || a.resource_name)}</td>
      <td class="n rc-mut">${esc(a.rev0)}</td><td class="n rc-new">${esc(a.rev1)}</td><td>${typeTag(kindTag, kindLabel)}</td></tr>`;
  }).join('');
  const resCard = hasResTbl
    ? `<div class="rc-card"><h3>Resource changed <span class="rc-n">assignment before / after</span></h3>
        ${resRows ? `<div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Activity ID</th><th>Activity Name</th><th>Resource ID</th><th>Resource Name</th><th class="n">Before</th><th class="n">After</th><th>Change</th></tr></thead><tbody>${resRows}</tbody></table></div>` : noData('No resource assignment changes.')}</div>`
    : '';

  return secmark('7', 'Cost & Resources', 'planned value, where the money moved, cost & resource changes')
    + scurve + moneyCard + costCard + resCard;
}

function renderMoneyChart(body) {
  const chart = body.querySelector('#rc-money-chart');
  const tbl = body.querySelector('#rc-money-tbl');
  if (!chart || !tbl) return;
  const r = state.revcompareReport || {};
  const bbd = (r.curves && r.curves.budget_by_dim) || {};
  const dim = rcFilters.money.dim;
  const rows = Array.isArray(bbd[dim]) ? bbd[dim] : [];
  const items = rows.map(x => {
    const v = (x.var != null) ? x.var : ((x.rev1 || 0) - (x.rev0 || 0));
    return { label: x.category, v, color: v >= 0 ? 'var(--accent)' : 'var(--muted)' };
  });
  chart.innerHTML = `<div class="rc-sec" style="margin-bottom:4px">Budget variance by ${escapeHtml(dim)}</div>`
    + barsSvg(items, { money: true, emptyMsg: 'No budget breakdown for this dimension.' });
  const trows = rows.map(x => {
    const v = (x.var != null) ? x.var : ((x.rev1 || 0) - (x.rev0 || 0));
    return `<tr><td>${esc(x.category)}</td><td class="n rc-mut">${fmtNum(x.rev0)}</td><td class="n rc-new">${fmtNum(x.rev1)}</td>
      <td class="n"><span class="rc-d ${v >= 0 ? 'up' : 'down'}">${v >= 0 ? '+' : ''}${fmtNum(v)}</span></td></tr>`;
  }).join('');
  tbl.innerHTML = `<div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>${escapeHtml(dim)}</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr></thead>
    <tbody>${trows || '<tr><td colspan="4" class="rc-mut">No data.</td></tr>'}</tbody></table></div>`;
}

function wireCost(body) {
  const dimHost = body.querySelector('#rc-money-dim');
  if (!dimHost) return;
  const r = state.revcompareReport || {};
  const dims = moneyDims(r.curves || {});
  if (!dims.length) return;
  if (!rcFilters.money.dim || !dims.includes(rcFilters.money.dim)) rcFilters.money.dim = dims[0];
  dimHost.innerHTML = chipRow('<b class="rc-fblbl">By:</b>', dims, rcFilters.money.dim, 'moneydim');
  dimHost.querySelectorAll('[data-moneydim]').forEach(c => c.addEventListener('click', () => {
    dimHost.querySelectorAll('[data-moneydim]').forEach(x => x.classList.toggle('on', x === c));
    rcFilters.money.dim = c.dataset.moneydim;
    renderMoneyChart(body);
  }));
  renderMoneyChart(body);
}

// ══ 8 · Manpower (comment 11 — combo: stacked-by-trade histogram + total line) ══

function manpowerView(r) {
  const curves = r.curves || {};
  const trades = curves.manpower_by_trade || [];
  const months = curves.months || [];
  if (!curves.resource_available || !trades.length || !months.length) {
    return secmark('8', 'Manpower', 'monthly man-hours, stacked by trade')
      + `<div class="rc-card"><h3>Manpower histogram</h3>${noData('Neither revision carries resource (man-hour) loading — manpower histogram not applicable.')}</div>`;
  }
  // Monthly totals across all trades.
  const total = months.map((_, i) => trades.reduce((s, t) => s + ((t.monthly || [])[i] || 0), 0));
  const n = months.length;
  const W = Math.max(760, n * 68), h = 288, L = 48, B = 44, T = 32;
  const pw = W - L - 16, ph = h - T - B, step = pw / n, bw = Math.min(40, step * 0.62);
  const mx = Math.max(1, ...total);
  let s = '';
  months.forEach((mo, i) => {
    let y = T + ph;
    const x = L + i * step + step / 2;
    trades.forEach((t, ti) => {
      const val = (t.monthly || [])[i] || 0;
      const segH = val / mx * ph;
      y -= segH;
      if (segH > 0) s += `<rect x="${(x - bw / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${segH.toFixed(1)}" fill="${tokenColor(t.trade, trades.map(z => z.trade))}"/>`;
    });
    // Monthly total label above the stacked bar (comment 11).
    const topY = T + ph - total[i] / mx * ph;
    if (total[i] > 0) s += `<text x="${x.toFixed(1)}" y="${(topY - 6).toFixed(1)}" font-size="10" font-weight="800" fill="var(--ink-soft)" text-anchor="middle">${escapeHtml(fmtInt(total[i]))}</text>`;
    s += `<text x="${x.toFixed(1)}" y="${(T + ph + 14).toFixed(1)}" font-size="8" fill="var(--muted)" text-anchor="middle">${escapeHtml(String(mo))}</text>`;
  });
  // Total-headcount line across the stacked tops.
  s += `<polyline points="${months.map((_, i) => `${(L + i * step + step / 2).toFixed(1)},${(T + ph - total[i] / mx * ph).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--danger)" stroke-width="2.4"/>`;

  const legend = trades.map(t => `<span><i style="background:${tokenColor(t.trade, trades.map(z => z.trade))}"></i>${esc(t.trade)}</span>`).join('')
    + '<span><i class="rc-line" style="background:var(--danger)"></i>Total headcount</span>';
  const peakVal = Math.max(0, ...total);
  const peakMonth = months[total.indexOf(peakVal)];
  const totalsByTrade = trades.map(t => `${esc(t.trade)} <b>${fmtInt(t.total)}</b>`).join(' · ');

  const card = `<div class="rc-card"><h3>Manpower histogram — combo by trade <span class="rc-n">total above each month · line = total headcount</span></h3>
    <div class="rc-sec">Monthly planned man-hours, stacked by trade — Rev.01</div>
    <div class="rc-chartwrap"><svg viewBox="0 0 ${W} ${h}" class="rc-svg" style="min-width:${W}px" role="img" aria-label="Manpower combo chart">
      <line x1="${L}" y1="${T + ph}" x2="${W - 16}" y2="${T + ph}" stroke="var(--border)"/>${s}</svg></div>
    <div class="rc-legend">${legend}</div>
    <div class="rc-callout">Peak <b>${fmtInt(peakVal)}</b>${peakMonth ? ` in ${esc(peakMonth)}` : ''}. Totals by trade: ${totalsByTrade} man-hours.</div></div>`;
  return secmark('8', 'Manpower', 'monthly man-hours, stacked by trade') + card;
}

// ══ 9 · Scope & Structure ══════════════════════════════════════════════════════

function wbsColumn(nodes, side) {
  if (!nodes || !nodes.length) return noData('No WBS structure available for this revision.');
  return nodes.map(nd => {
    const lvl = Math.min(Math.max(parseInt(nd.level, 10) || 1, 1), 5);
    const st = nd.state && nd.state !== 'unchanged' ? nd.state : '';
    let badgeText = st;
    if (st === 'moved') badgeText = side === 'r0' ? 'moved →' : '← moved here';
    const badge = st ? `<span class="rc-p6badge">${escapeHtml(badgeText)}</span>` : '';
    return `<div class="rc-p6band rc-l${lvl} ${st}" style="margin-left:${(lvl - 1) * 14}px">${esc(nd.name)}${badge}</div>`;
  }).join('');
}

function scopeView(r) {
  const wv = r.wbs_view || {};
  const sum = wv.summary || {};
  const wbsCard = `<div class="rc-card"><h3>WBS comparison <span class="rc-n">Primavera colour-grouping · a colour per level</span></h3>
    <div class="rc-split">
      <div><div class="rc-cklab">Rev.00 — original WBS</div>${wbsColumn(wv.rev0, 'r0')}</div>
      <div><div class="rc-cklab r1">Rev.01 — revised WBS</div>${wbsColumn(wv.rev1, 'r1')}</div>
    </div>
    <div class="rc-legend">
      <span><i class="rc-l1"></i>L1</span><span><i class="rc-l2"></i>L2</span><span><i class="rc-l3"></i>L3</span><span><i class="rc-l4"></i>L4</span>
      <span><i style="outline:2px solid var(--success);background:transparent"></i>added</span>
      <span><i style="outline:2px solid var(--danger);background:transparent"></i>removed</span>
      <span><i style="outline:2px solid var(--warning);background:transparent"></i>moved</span>
    </div>
    ${(wv.rev0 || wv.rev1) ? `<div class="rc-callout">${sum.added ?? 0} branch(es) added · ${sum.removed ?? 0} removed · ${sum.moved ?? 0} moved · ${sum.reparented ?? 0} activities re-parented.</div>` : ''}</div>`;

  const ds = r.date_shifts || [];
  const dsRows = ds.map(d => `<tr><td class="rc-aid">${esc(d.id)}</td><td>${esc(d.name)}</td><td class="rc-mut">${esc(d.wbs)}</td>
      <td>${esc(d.start0)} → ${esc(d.start1)}</td><td>${esc(d.finish0)} → ${esc(d.finish1)}</td>
      <td class="n">${deltaCell(typeof d.shift_wd === 'number' ? d.shift_wd : null)}${typeof d.shift_wd === 'number' ? ' d' : ''}</td></tr>`).join('');
  const dsCard = `<div class="rc-card"><h3>Largest date shifts <span class="rc-n">activities whose dates moved</span></h3>
    ${ds.length ? `<div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Activity ID</th><th>Activity Name</th><th>WBS</th><th>Start (before → after)</th><th>Finish (before → after)</th><th class="n">Shift</th></tr></thead><tbody>${dsRows}</tbody></table></div>`
                : noData('No material date shifts detected.')}</div>`;

  return secmark('9', 'Scope & Structure', 'WBS in Primavera colour-grouping + largest date shifts')
    + wbsCard + dsCard;
}

// ── Report (PDF) — invoked by the ⬇ PDF button (global preview picker) ─────────

// The Report-Contents sections the Baseline Revision PDF can print (tool-wide picker
// standard). Keys + order mirror the nine on-screen sub-tabs; a section is offered as
// empty (disabled "no data" pick) when its underlying data is absent.
export const REVCOMPARE_SECTIONS = [
  { key: 'summary',  label: 'Executive Summary' },
  { key: 'findings', label: 'Key Findings' },
  { key: 'critical', label: 'Critical Path & Float' },
  { key: 'register', label: 'Change Register' },
  { key: 'ms',       label: 'Milestones' },
  { key: 'cal',      label: 'Calendar' },
  { key: 'cost',     label: 'Cost & Resources' },
  { key: 'manpower', label: 'Manpower' },
  { key: 'scope',    label: 'Scope & Structure' },
];
const _RC_STORAGE_KEY = 'p6_report_sections_revcompare';

export async function openRevcompareReport() {
  const r = state.revcompareReport;
  if (!r) { showError('Run the comparison first, then print.'); return; }
  const mode = getSavedMode();
  const meta = {
    rev0_file: r.rev0.file, rev1_file: r.rev1.file,
    report_date: new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }),
  };
  // Which sections have data (drives the "no data" disabled pick in the picker).
  const c = r.curves || {};
  const q = r.quality || {};
  const cp = r.critical_path || {};
  const wv = r.wbs_view || {};
  const rc = r.resource_changes || {};
  const cc = r.calendar_changes || {};
  const has = {
    findings: !!((r.slip && r.slip.contributions && r.slip.contributions.length)
      || (r.logic_register && r.logic_register.length)),
    critical: !!((cp.rev0 && cp.rev0.length) || (cp.rev1 && cp.rev1.length) || (q.float_bands && q.float_bands.length)),
    register: !!(r.duration_table && r.duration_table.length),
    ms: !!(r.milestones && r.milestones.some(m => m.kind !== 'unchanged')),
    cal: !!(((cc.reassignments || []).length) || ((cc.calendars || []).length)),
    cost: !!(c.cost_available || c.resource_available || rc.cost_available || rc.resource_available
      || ((rc.assignment_changes || []).length) || ((rc.activity_cost_changes || []).length)),
    manpower: !!(c.resource_available && (c.manpower_by_trade || []).length),
    scope: !!((wv.rev0 && wv.rev0.length) || (wv.rev1 && wv.rev1.length) || (r.date_shifts && r.date_shifts.length)),
  };
  const sections = REVCOMPARE_SECTIONS.map(s => ({ ...s, empty: (s.key in has) ? !has[s.key] : false }));
  let selected = sections.filter(s => !s.empty).map(s => s.key);
  try {
    const saved = JSON.parse(localStorage.getItem(_RC_STORAGE_KEY) || 'null');
    if (Array.isArray(saved)) selected = saved.filter(k => sections.some(s => s.key === k && !s.empty));
  } catch { /* default: every non-empty section */ }
  const fetchPreview = async (keys, theme) => {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/revcompare/report`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report: r, meta, preview: true, sections: keys || null, theme: theme || mode, filters: buildFilters() }),
    });
    const data = await resp.json();
    return (data.ok && data.html) ? data.html : null;
  };
  try {
    const html = await fetchPreview(selected, mode);
    if (!html) { showError('Preview failed — please retry.'); return; }
    showReportPreview({
      title: 'Baseline Revision Comparison', subtitle: `${r.rev0.file || 'Rev.00'} vs ${r.rev1.file || 'Rev.01'}`,
      html, sections, selected, storageKey: _RC_STORAGE_KEY, initialMode: mode,
      onRerender:    (keys, theme) => fetchPreview(keys, theme),
      onThemeChange: (theme, keys) => fetchPreview(keys, theme),
      onSave: async (m, keys) => {
        const outputPath = await window.pywebview.api.choose_save_path('Baseline_Revision_Comparison.pdf', 'pdf');
        if (!outputPath) return false;
        const resp = await fetch(`http://localhost:${state.serverPort}/api/revcompare/report`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ report: r, meta, theme: m, sections: keys || null, output_path: outputPath, filters: buildFilters() }),
        });
        const data = await resp.json();
        if (!data.ok) { showError(`PDF generation failed: ${data.error}`); return false; }
        return true;
      },
    });
  } catch {
    showError('Preview failed. Try again.');
  }
}
