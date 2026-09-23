// Baseline Revision Comparison — compare two approved baseline revisions (Rev.00 vs
// Rev.01) from a planning/consultant perspective. Workflow: assign both revisions →
// Run Comparison → review results across TEN sub-tabs (Executive Summary · Key Findings ·
// Critical Path & Float · Change Register [duration] · Milestones · Calendar ·
// Cost & Resources · Resources · Manpower · Scope & Structure). Neutral by design: Change detected →
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

// Ten sub-tabs — the same keys are used for the PDF `data-sec` sections, the Excel
// sheets and the report-contents picker. `resource` (Resources) sits after `cost`.
const RC_TABS = [
  ['summary', 'Executive Summary'], ['findings', 'Key Findings'],
  ['critical', 'Critical Path & Float'], ['register', 'Change Register'],
  ['ms', 'Milestones'], ['cal', 'Calendar'],
  ['cost', 'Cost & Resources'], ['resource', 'Resources'],
  ['manpower', 'Manpower'], ['scope', 'Scope & Structure'],
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
  money:    { dim: null, val: 'All' },
  cost:     { dim: null, val: 'All' },
};
function resetFilters() {
  rcFilters.scope = { dim: null, val: 'All' };
  rcFilters.logic = { dim: null, val: 'All' };
  rcFilters.duration = { dim: null, val: 'All' };
  rcFilters.money = { dim: null, val: 'All' };
  rcFilters.cost = { dim: null, val: 'All' };
}
// The filters object sent to the PDF renderer. Each part is omitted when no dimension is
// active; a val of 'All' (or absent) means "no filter" on the server side.
function buildFilters() {
  const f = {};
  if (rcFilters.scope.dim) f.scope = { dim: rcFilters.scope.dim, val: rcFilters.scope.val };
  if (rcFilters.logic.dim) f.logic = { dim: rcFilters.logic.dim, val: rcFilters.logic.val };
  if (rcFilters.duration.dim) f.duration = { dim: rcFilters.duration.dim, val: rcFilters.duration.val };
  if (rcFilters.money.dim) f.money = { dim: rcFilters.money.dim };
  if (rcFilters.cost.dim) f.cost = { dim: rcFilters.cost.dim };
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
    cost: costView, resource: resourceView, manpower: manpowerView, scope: scopeView,
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
  else if (tab === 'cal') wireCalendar(body);
}

// Each calendar card's activity-code dimension selector shows one dimension's chips at a time.
function wireCalendar(body) {
  body.querySelectorAll('.rc-caldimsel').forEach(sel => {
    const card = sel.dataset.card;
    sel.addEventListener('change', () => {
      body.querySelectorAll(`.rc-acrow[data-card="${card}"]`).forEach(row => {
        row.style.display = (row.dataset.dim === sel.value) ? '' : 'none';
      });
    });
  });
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
// Compact whole-number label for a chart bar/axis (147,000 → "147k", 12,400 → "12.4k",
// 1,200,000 → "1.2M"). Never trims: a small, readable label that fits above a bar. Used by every
// chart's value labels so numbers are shown in full without collision (round-16: all charts).
function fmtCompact(n) {
  if (n == null || !isFinite(Number(n))) return '';
  const v = Number(n), a = Math.abs(v), s = v < 0 ? '-' : '';
  if (a >= 1e6) return `${s}${(a / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, '')}M`;
  if (a >= 1e3) return `${s}${(a >= 1e5 ? Math.round(a / 1e3) : (a / 1e3).toFixed(1).replace(/\.0$/, ''))}k`;
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
// Wrap a label into a multi-line <text> (tspans) so long SVG labels don't collide with
// their neighbours. `max` = chars/line budget (from the available column width). Escapes
// each line. Returns one <text> element anchored at (x, y).
function wrapSvgText(text, x, y, opts = {}) {
  const { max = 14, lh = 10, maxLines = 3, anchor = 'middle', size = 9, fill = 'var(--muted)', weight = null } = opts;
  const words = String(text || '').split(/\s+/).filter(Boolean);
  const lines = [];
  let cur = '';
  for (const w of words) {
    if (!cur) { cur = w; }
    else if ((cur + ' ' + w).length <= max) { cur += ' ' + w; }
    else { lines.push(cur); cur = w; if (lines.length >= maxLines) break; }
  }
  if (cur && lines.length < maxLines) lines.push(cur);
  if (!lines.length) lines.push('');
  // If content overflowed the line budget, ellipsise the last kept line.
  const consumed = lines.join(' ').length;
  if (consumed < String(text || '').replace(/\s+/g, ' ').trim().length) {
    lines[lines.length - 1] = lines[lines.length - 1].replace(/.{0,1}$/, '…');
  }
  const tspans = lines.map((ln, i) =>
    `<tspan x="${x}" dy="${i === 0 ? 0 : lh}">${escapeHtml(ln)}</tspan>`).join('');
  return `<text x="${x}" y="${y}" font-size="${size}" fill="${fill}" text-anchor="${anchor}"${weight ? ` font-weight="${weight}"` : ''}>${tspans}</text>`;
}

// Deterministic theme-token colour for a code value (by first-seen order). No hardcoded
// hex — every colour resolves through the appearance-mode chart tokens.
const CHART_TOKENS = ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5', '--chart-6'];
function tokenColor(value, order) {
  const i = Array.isArray(order) ? order.indexOf(value) : -1;
  return i < 0 ? 'var(--accent)' : `var(${CHART_TOKENS[i % CHART_TOKENS.length]})`;
}

// By-code bar chart — HORIZONTAL bars so category names never collide (see the approved
// chart-fix mockup). items: [{ label, v, color }]. opts.money → compact money labels;
// opts.suffix (e.g. '%') → appended to integer counts. Each category name sits on its own
// line (right-aligned, truncated with a title=fullname tooltip); the value sits at the end
// of its bar (inside when the bar is wide, just after it otherwise); the list scrolls when
// there are many categories. Colours resolve through theme tokens only.
function barsSvg(items, opts = {}) {
  if (!items || !items.length) return noData(opts.emptyMsg || 'No data to chart.');
  const mx = Math.max(1, ...items.map(i => Math.abs(i.v || 0)));
  const rows = items.map(it => {
    const v = it.v || 0;
    const w = Math.max(2, Math.abs(v) / mx * 100);
    const label = opts.money ? fmtMoney(v) : fmtCompact(v) + (opts.suffix || '');
    const name = escapeHtml(String(it.label ?? ''));
    const inside = w > 20;
    const valStyle = inside
      ? `left:calc(${w.toFixed(2)}% - 6px);transform:translateX(-100%)`
      : `left:calc(${w.toFixed(2)}% + 6px)`;
    return `<div class="rc-hrow">
        <div class="rc-hlbl" title="${name}">${name}</div>
        <div class="rc-htrack"><div class="rc-hfill" style="width:${w.toFixed(2)}%;background:${it.color || 'var(--accent)'}"></div><div class="${inside ? 'rc-hval in' : 'rc-hval'}" style="${valStyle}">${escapeHtml(label)}</div></div>
      </div>`;
  }).join('');
  return `<div class="rc-hbars" role="img" aria-label="Bar chart">${rows}</div>`;
}

// Donut / pie chart with a centre total and a percentage legend (Scope §1). items:
// [{ label, v, color }] — each slice is v / Σv of the ring. A single 100% category draws a
// full ring; the legend lists every value with its share. Colours resolve through theme
// tokens only. opts.centerLabel — the word under the centre count (default 'Added').
function donutSvg(items, opts = {}) {
  const clean = (items || []).filter(x => (x.v || 0) > 0);
  if (!clean.length) return noData(opts.emptyMsg || 'No added activities to chart for this dimension.');
  const tot = clean.reduce((a, x) => a + (x.v || 0), 0);
  const cx = 100, cy = 100, R = 78, RI = 46;
  let a0 = -Math.PI / 2, arcs = '', hole = '';
  if (clean.length === 1) {
    // One category = 100% → a full ring (an arc from/to the same point draws nothing).
    arcs = `<circle cx="${cx}" cy="${cy}" r="${((R + RI) / 2).toFixed(1)}" fill="none" stroke="${clean[0].color || 'var(--accent)'}" stroke-width="${(R - RI).toFixed(1)}"/>`;
  } else {
    clean.forEach(it => {
      const a1 = a0 + (it.v || 0) / tot * 2 * Math.PI;
      const x0 = cx + R * Math.cos(a0), y0 = cy + R * Math.sin(a0);
      const x1 = cx + R * Math.cos(a1), y1 = cy + R * Math.sin(a1);
      const large = (a1 - a0) > Math.PI ? 1 : 0;
      arcs += `<path d="M${cx},${cy} L${x0.toFixed(1)},${y0.toFixed(1)} A${R},${R} 0 ${large} 1 ${x1.toFixed(1)},${y1.toFixed(1)} Z" fill="${it.color || 'var(--accent)'}"/>`;
      a0 = a1;
    });
    hole = `<circle cx="${cx}" cy="${cy}" r="${RI}" fill="var(--card-bg)"/>`;
  }
  const center = `<text x="${cx}" y="${cy - 4}" font-size="11" fill="var(--muted)" text-anchor="middle">${escapeHtml(opts.centerLabel || 'Added')}</text>`
    + `<text x="${cx}" y="${cy + 13}" font-size="15" font-weight="800" fill="var(--text)" text-anchor="middle">${escapeHtml(fmtCompact(tot))}</text>`;
  const svg = `<svg viewBox="0 0 200 200" class="rc-donut" role="img" aria-label="Share of added activities by activity code">${arcs}${hole}${center}</svg>`;
  const legend = `<div class="rc-pleg">${clean.map(it =>
    `<div class="rc-plegrow"><span class="rc-plegsw" style="background:${it.color || 'var(--accent)'}"></span>`
    + `<span class="rc-plegnm" title="${escapeHtml(String(it.label ?? ''))}">${esc(it.label)}</span>`
    + `<span class="rc-plegpct">${Math.round((it.v || 0) / tot * 100)}%</span></div>`).join('')}</div>`;
  return `<div class="rc-piewrap">${svg}${legend}</div>`;
}

// Distinct code values for a dimension across a set of rows carrying a `.codes` map.
function codeValues(rows, dim) {
  return [...new Set((rows || []).map(x => (x.codes || {})[dim]).filter(v => v != null && v !== ''))];
}
// ONE grouped activity-code control (comment 1). Replaces the old "Dimension" + "Activity
// code" dropdown pair everywhere — Scope, Key-Findings logic, Duration and Money each get a
// single <select>:
//   <option>All activity codes</option>
//   <optgroup label="<dimension>"><option>value</option>…</optgroup> …
// "All" shows the default breakdown (by the first dimension); picking a specific value
// filters the WHOLE sub-feature to it (dimension = its optgroup label). The selection lives
// in rcFilters.<x> ({dim, val}), so it feeds the PDF `filters` unchanged. `spec`:
//   dims       — [dimension names]
//   state      — the rcFilters.<x> object ({dim, val})
//   valuesFor  — (dim) => [distinct values] for that dimension's optgroup
//   onChange   — () => redraw the chart / count / list from the updated state
//   label      — the control's field label (default "Activity code")
function groupedFilterControl(host, spec) {
  if (!host) return;
  const { dims, state: fs, onChange, label = 'Activity code', withValues = false, valuesFor } = spec;
  if (!dims || !dims.length) { host.innerHTML = ''; onChange(); return; }
  // A FLAT list of the activity codes themselves (the dimensions) — the user picks one code and
  // the chart / pie breaks down by it. No nested values, no grouping (comment: "the user picks
  // only the activity code itself"). The selection lives in rcFilters.<x> as {dim, val}. For the
  // money/cost breakdowns val stays 'All' (full breakdown feeds the PDF); when `withValues` is set
  // (Executive Summary scope) a SECOND dropdown lets the planner drill to a specific code value so
  // the added/removed list + counts update on selection (comment: click a specific code → updates).
  if (!fs.dim || !dims.includes(fs.dim)) { fs.dim = dims[0]; fs.val = 'All'; }
  const dimOpts = dims.map(d =>
    `<option value="${escapeHtml(String(d))}"${d === fs.dim ? ' selected' : ''}>${esc(d)}</option>`).join('');
  if (!withValues) {
    fs.val = 'All';
    host.innerHTML = `<div class="rc-fbar"><div class="rc-fld"><label>${escapeHtml(label)}</label>`
      + `<select class="rc-fsel rc-fdim">${dimOpts}</select></div></div>`;
    const sel = host.querySelector('.rc-fdim');
    sel.addEventListener('change', () => { fs.dim = sel.value; fs.val = 'All'; onChange(); });
    onChange();
    return;
  }
  // Two-level: dimension + value. Rebuild the value list whenever the dimension changes.
  const valOptions = () => {
    const vals = (valuesFor ? valuesFor(fs.dim) : []) || [];
    if (!vals.includes(fs.val)) fs.val = 'All';
    return ['All', ...vals].map(v =>
      `<option value="${escapeHtml(String(v))}"${v === fs.val ? ' selected' : ''}>${v === 'All' ? 'All codes' : esc(v)}</option>`).join('');
  };
  const paint = () => {
    host.innerHTML = `<div class="rc-fbar">`
      + `<div class="rc-fld"><label>${escapeHtml(label)}</label><select class="rc-fsel rc-fdim">${dimOpts}</select></div>`
      + `<div class="rc-fld"><label>Value</label><select class="rc-fsel rc-fval">${valOptions()}</select></div></div>`;
    host.querySelector('.rc-fdim').addEventListener('change', (e) => { fs.dim = e.target.value; fs.val = 'All'; paint(); onChange(); });
    host.querySelector('.rc-fval').addEventListener('change', (e) => { fs.val = e.target.value; onChange(); });
  };
  paint();
  onChange();
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
    <div id="rc-scope-filter"></div>
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
  // Donut: % of ADDED activities by each value of the selected dimension — from the engine's
  // codes.scope_by_code[dim] (added counts per value). Re-slices on every selector change.
  const sbc = (codes.scope_by_code || {})[dim] || [];
  const order = sbc.map(x => x.category);
  const items = sbc.map(x => ({ label: x.category, v: x.added || 0, color: tokenColor(x.category, order) }));
  host.innerHTML = `<div class="rc-sec" style="margin-bottom:4px">Share of added activities by ${escapeHtml(dim)}</div>`
    + donutSvg(items, { centerLabel: 'Added', emptyMsg: 'No added activities to chart for this dimension.' });
  // Itemised list filtered by the selected value — no trailing dimension column; the WBS
  // column shows the full path and is labelled "WBS Path" (comment 1).
  const rows = all.filter(x => val === 'All' || (x.codes || {})[dim] === val);
  const addedN = rows.filter(x => x.k === 'Added').length, removedN = rows.filter(x => x.k === 'Removed').length;
  const list = rows.map(x => `<tr>
      <td class="rc-aid">${esc(x.id)}</td><td>${esc(x.name)}</td>
      <td><span class="rc-tag ${x.k === 'Added' ? 'add' : 'rem'}">${x.k}</span></td>
      <td class="rc-mut">${esc(x.wbs)}</td></tr>`).join('');
  tbl.innerHTML = `<div class="rc-callout">Showing <b>${esc(val)}</b>: <b>${fmtInt(addedN)} added</b> · <b>${fmtInt(removedN)} removed</b>.</div>
    <div class="rc-tblscroll" style="margin-top:8px"><table class="rc-t">
      <thead><tr><th>Activity ID</th><th>Activity Name</th><th>Change</th><th>WBS Path</th></tr></thead>
      <tbody>${list || `<tr><td colspan="4" class="rc-mut">None for this code.</td></tr>`}</tbody></table></div>`;
}

function wireSummary(body) {
  const host = body.querySelector('#rc-scope-filter');
  if (!host) return;
  const r = state.revcompareReport || {};
  const dims = scopeDims(r);
  if (!dims.length) return;
  const all = [...((r.codes || {}).added || []), ...((r.codes || {}).removed || [])];
  groupedFilterControl(host, {
    dims,
    state: rcFilters.scope,
    withValues: true,   // Exec Summary: drill to a specific code value → added/removed list updates (comment 1)
    valuesFor: (dim) => codeValues(all, dim),
    onChange: () => renderScopeChart(body),
  });
}

// ══ 2 · Key Findings ═════════════════════════════════════════════════════════

// Shared, theme-token palette. The finish-slip waterfall bars and the contribution
// breakdown list index into it identically, so a cause keeps ONE colour in both.
const SLIP_PALETTE = ['--chart-3', '--warning', '--chart-1', '--chart-4', '--chart-5', '--chart-2', '--chart-6'];
const slipColor = (i) => `var(${SLIP_PALETTE[i % SLIP_PALETTE.length]})`;

// Finish-slip waterfall with the axis CENTRED on 0 (comment 3). Up = delay (positive wd),
// down = pull-in (negative wd). The scale covers the full running-cumulative range AND the
// total, and top/bottom padding is reserved for value labels, so a negative step (e.g. a
// −104d calendar interaction) and its label are never clipped.
function slipWaterfall(slip) {
  const cs = (slip && slip.contributions) || [];
  if (!cs.length) return noData('No finish-slip attribution available.');
  const total = slip.total_wd != null ? slip.total_wd : cs.reduce((s, c) => s + (c.wd || 0), 0);
  // Running cumulative path (starts at 0) — its extremes bound the centred axis.
  let cum = 0; const cums = [0];
  cs.forEach(c => { cum += (c.wd || 0); cums.push(cum); });
  const maxAbs = Math.max(1, ...cums.map(Math.abs), Math.abs(total));

  const W = 900, H = 300, L = 90, R = 110, T = 42, B = 82;
  const plotW = W - L - R, plotH = H - T - B;
  const zeroY = T + plotH / 2;
  const scale = (plotH / 2 - 10) / maxAbs;          // 10px head-room for the value label
  const y = (v) => zeroY - v * scale;                // positive → up (smaller y)
  const n = cs.length;
  const colStep = plotW / (n + 1);
  const bw = Math.min(60, colStep * 0.55);
  const xc = (i) => L + (i + 1) * colStep;
  const causeMax = Math.max(8, Math.floor(colStep / 5.5));
  const causeY = T + plotH + 16;

  let bars = '', conns = '', labels = '';
  cs.forEach((c, i) => {
    const before = cums[i], after = cums[i + 1], wd = c.wd || 0;
    const yb = y(before), ya = y(after);
    const yTop = Math.min(yb, ya), h = Math.max(1, Math.abs(ya - yb));
    const cx = xc(i), col = slipColor(i);
    bars += `<rect x="${(cx - bw / 2).toFixed(1)}" y="${yTop.toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="${col}"/>`;
    // Delay steps label above the bar; pull-in steps below — always clear of the bar.
    const ly = wd >= 0 ? (yTop - 6) : (yTop + h + 13);
    labels += `<text x="${cx.toFixed(1)}" y="${ly.toFixed(1)}" font-size="11" fill="var(--ink-soft)" text-anchor="middle" font-weight="700">${num(wd, true)}</text>`;
    labels += wrapSvgText(c.cause || '', cx.toFixed(1), causeY.toFixed(1), { max: causeMax, size: 9, maxLines: 3 });
    if (i > 0) {
      const py = y(before);
      conns += `<line x1="${(xc(i - 1) + bw / 2).toFixed(1)}" y1="${py.toFixed(1)}" x2="${(cx - bw / 2).toFixed(1)}" y2="${py.toFixed(1)}"/>`;
    }
  });
  // Total bar (from the 0 axis to the total), highlighted.
  const tx = xc(n), ty = Math.min(zeroY, y(total)), th = Math.max(1, Math.abs(y(total) - zeroY));
  bars += `<rect x="${(tx - bw / 2).toFixed(1)}" y="${ty.toFixed(1)}" width="${bw.toFixed(1)}" height="${th.toFixed(1)}" rx="2" fill="var(--danger)" opacity=".9"/>`;
  const tly = total >= 0 ? (ty - 6) : (ty + th + 13);
  labels += `<text x="${tx.toFixed(1)}" y="${tly.toFixed(1)}" font-size="12" fill="var(--danger)" text-anchor="middle" font-weight="800">${num(total, true)}</text>`;
  labels += wrapSvgText(`Rev.01 · ${slip.rev1_finish || ''}`, tx.toFixed(1), causeY.toFixed(1), { max: causeMax, size: 9, maxLines: 2, fill: 'var(--ink-soft)', weight: 700 });
  // Connector from the last cumulative onto the total's baseline.
  conns += `<line x1="${(xc(n - 1) + bw / 2).toFixed(1)}" y1="${y(cums[n]).toFixed(1)}" x2="${(tx - bw / 2).toFixed(1)}" y2="${y(cums[n]).toFixed(1)}"/>`;

  return `<svg viewBox="0 0 ${W} ${H}" class="rc-svg" style="min-width:720px" role="img" aria-label="Finish-slip attribution waterfall">
    <line x1="${L}" y1="${zeroY.toFixed(1)}" x2="${W - R + 40}" y2="${zeroY.toFixed(1)}" stroke="var(--border)"/>
    <line x1="${L}" y1="${(zeroY - 6).toFixed(1)}" x2="${L}" y2="${(zeroY + 6).toFixed(1)}" stroke="var(--muted)"/>
    <text x="${L}" y="${(zeroY - 11).toFixed(1)}" font-size="9" fill="var(--muted)" text-anchor="middle">Rev.00 finish</text>
    <text x="${L}" y="${(zeroY + 19).toFixed(1)}" font-size="9" fill="var(--muted)" text-anchor="middle">${esc(slip.rev0_finish)}</text>
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
      <span class="rc-n">Critical-Path-Analyzer lanes — one compact row per change</span> <span class="rc-pdfnote">🔵 reflects in PDF</span></h3>
    <div class="rc-sec">Each changed relationship is a single-row lane: predecessor → link → successor, with the WBS breadcrumb inside each node — pick an activity code to filter</div>
    <div id="rc-logic-filter"></div>
    <div id="rc-logic-chart"></div></div>`;

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

// A single compact "lane" (Critical-Path-Analyzer style, comment 2): a numbered header
// (#N + change tag + on-CP / context sub-label), an explicit "Before: … → After: …" link line,
// then a one-row chain predecessor → link → successor. Each node carries the activity name,
// its WBS breadcrumb "@ seg @ seg" and the id; the chain link is a single arrow (or '✕' for a
// removed link) — the wording of the change lives in the explicit line above. Lanes sit in a
// responsive grid (2-up on a normal window, 1-up when narrow); nothing scrolls sideways.
function logicLane(l, idx, addedBySucc = {}) {
  const change = String(l.change || '');
  const kind = /added/i.test(change) ? 'added' : /removed/i.test(change) ? 'removed' : 'changed';
  const tag = kind === 'added' ? 'add' : kind === 'removed' ? 'rem' : 'chg';
  const pSegs = crumbSegs(l, 'pred_wbs'), sSegs = crumbSegs(l, 'succ_wbs');
  const ctx = [l.codes && (l.codes.Discipline || l.codes.scope), l.codes && l.codes.Building].filter(Boolean).map(esc).join(' · ');
  const subParts = [];
  if (l.on_cp) subParts.push('on critical path');
  if (l.is_lead) subParts.push('lead');
  if (ctx) subParts.push(ctx);
  const sub = subParts.join(' · ');
  const cnode = (name, id, segs, crit) =>
    `<div class="rc-cnode${crit ? ' crit' : ''}"><div class="rc-cn" title="${esc(name)}">${esc(name)}</div>`
    + `<div class="rc-cw">@ ${segs.map(esc).join(' @ ')}</div><div class="rc-cid">${esc(id)}</div></div>`;
  // Show the relationship BEFORE and AFTER as two chains, so the change is a visible comparison
  // (Rev.00 link → Rev.01 link) — not just a text line. The link widget carries the type+lag.
  const chain = linkHtml =>
    `<div class="rc-chain2">${cnode(l.pred_name, l.pred_id, pSegs, false)}${linkHtml}${cnode(l.succ_name, l.succ_id, sSegs, !!l.on_cp)}</div>`;
  const linkW = (label, cls, arrow) =>
    `<div class="rc-clink"><span class="rc-clt ${cls}">${label}</span><span class="rc-ar2 ${cls}">${arrow}</span></div>`;
  const beforeLink = kind === 'added' ? linkW('not linked in Rev.00', 'none', '⋯') : linkW(esc(l.before), '', '→');
  const afterLink = kind === 'removed' ? linkW('link removed', 'rem', '✕')
    : linkW(esc(l.after), kind === 'added' ? 'add' : 'chg', '→');
  // For a REMOVED link, clarify what replaced it: any NEW predecessor the successor gained in Rev.01.
  let replBlock = '';
  if (kind === 'removed') {
    const repl = (addedBySucc[l.succ_id] || []).filter(a => a.pred_id !== l.pred_id);
    replBlock = repl.length
      ? `<div class="rc-lrepl">↳ ${esc(l.succ_name)} is now driven instead by ${repl.map(a => `<b>${esc(a.pred_name)}</b> (${esc(a.after)})`).join(', ')}.</div>`
      : `<div class="rc-lrepl mut">↳ ${esc(l.succ_name)} lost this predecessor with no replacement link added — it may now be an open end.</div>`;
  }
  return `<div class="rc-lane">
      <div class="rc-lanehdr"><span class="rc-lanenum">#${idx}</span><span class="rc-lanetag ${tag}">${esc(l.change)}</span>${sub ? `<span class="rc-lanesub">${sub}</span>` : ''}</div>
      <div class="rc-rev2lab">Rev.00 — before</div>${chain(beforeLink)}
      <div class="rc-rev2lab r1">Rev.01 — after</div>${chain(afterLink)}${replBlock}
    </div>`;
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
  // Map each successor to the NEW predecessor links it gained, so a removed link can name its replacement.
  const addedBySucc = {};
  all.forEach(l => { if (/added/i.test(l.change || '')) (addedBySucc[l.succ_id] = addedBySucc[l.succ_id] || []).push(l); });
  host.innerHTML = `<div class="rc-lanes">${rows.map((l, i) => logicLane(l, i + 1, addedBySucc)).join('')}</div>`;
}

function wireFindings(body) {
  const host = body.querySelector('#rc-logic-filter');
  if (!host) return;
  const r = state.revcompareReport || {};
  const dims = logicDims(r);
  if (!dims.length) { const chart = body.querySelector('#rc-logic-chart'); if (chart) chart.innerHTML = noData('No activity-code dimensions available to filter the logic changes.'); return; }
  groupedFilterControl(host, {
    dims,
    state: rcFilters.logic,
    withValues: true,   // drill to a specific code value → the logic lanes filter live (comment 1)
    valuesFor: (dim) => codeValues(r.logic_register, dim),
    onChange: () => renderLogicChart(body),
  });
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
    ? `<div class="rc-card"><h3>Duration-change analysis <span class="rc-n">by activity code</span> <span class="rc-pdfnote">🔵 reflects in PDF</span></h3>
        <div class="rc-sec">Average duration change (%) by code — pick a dimension, then (optionally) an activity code; the chart and the table below both update</div>
        <div id="rc-dur-filter"></div>
        <div id="rc-dur-chart"></div></div>`
    : '';
  const tableCard = `<div class="rc-card"><h3>Duration changed <span class="rc-n">working days · filter by activity code</span></h3>
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
    // Prefer the engine-supplied % (report.duration_table[].pct); fall back to a local calc.
    const pct = (typeof d.pct === 'number') ? d.pct
      : ((bNum && aNum && d.before) ? Math.round((d.after - d.before) / d.before * 100) : null);
    // A > ±200% swing (engine flag, or |pct| > 200) usually means the activity type /
    // relationship type changed — flag it neutrally for justification, never as "wrong".
    const big = (d.big_variance === true) || (typeof pct === 'number' && Math.abs(pct) > 200);
    // ADDED activity rows carry no "before" duration (before === '—') — flag them as new work.
    const isAdded = d.before === '—' || d.before == null;
    const note = isAdded
      ? '<span class="rc-tag add" title="This activity is new in Rev.01 — it has no Rev.00 duration to compare against.">New activity</span>'
      : big
        ? `<span class="rc-tag warn" title="A > ±200% swing usually means the activity type or relationship type changed — it warrants a justification. Not a judgement that the change is wrong.">⚠ needs justification</span>`
        : '<span class="rc-mut">—</span>';
    return `<tr><td class="rc-aid">${esc(d.id)}</td><td>${esc(d.name)}${isAdded ? '<span class="rc-tag add" style="margin-left:6px">New activity</span>' : ''}</td><td class="rc-mut">${esc(d.wbs)}</td>
      <td class="n">${bNum ? d.before + ' d' : esc(d.before)}</td>
      <td class="n rc-new">${aNum ? d.after + ' d' : esc(d.after)}</td>
      <td class="n">${v != null ? `<span class="rc-d ${v > 0 ? 'up' : v < 0 ? 'down' : 'zero'}">${v > 0 ? '+' : ''}${v} d</span>` : (d.before == null || d.after == null ? '<span class="rc-tag add">Added</span>' : '—')}</td>
      <td class="n">${pct != null ? `<span class="rc-d ${pct > 0 ? 'up' : pct < 0 ? 'down' : 'zero'}">${pct > 0 ? '+' : ''}${pct}%</span>` : '—'}</td>
      <td>${note}</td></tr>`;
  }).join('');
  host.innerHTML = `<div class="rc-tblscroll"><table class="rc-t">
    <thead><tr><th>Activity ID</th><th>Activity Name</th><th>WBS</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th><th class="n">% change</th><th>Note</th></tr></thead>
    <tbody>${body_ || '<tr><td colspan="8" class="rc-mut">No duration changes for this code.</td></tr>'}</tbody></table></div>`;
}

function wireRegister(body) {
  const r = state.revcompareReport || {};
  const dims = durationDims(r);
  const host = body.querySelector('#rc-dur-filter');
  if (dims.length && host) {
    // One grouped control drives both the by-code chart and the filtered duration table.
    groupedFilterControl(host, {
      dims,
      state: rcFilters.duration,
      withValues: true,   // drill to a specific code value → the duration table filters live (comment 2)
      valuesFor: (dim) => codeValues(r.duration_table, dim),
      onChange: () => { renderDurChart(body); renderDurTable(body); },
    });
  } else {
    rcFilters.duration.dim = null; rcFilters.duration.val = 'All';
    renderDurChart(body);
    renderDurTable(body);
  }
}

// ══ 5 · Milestones (comment 4 — Type column removed) ════════════════════════════

function milestonesView(r) {
  const rows = (r.milestones || []).filter(m => m.kind !== 'unchanged').map(m => {
    const id = m.id != null ? m.id : (m.activity_id != null ? m.activity_id : m.code);
    const name = m.name || m.activity_name || id;
    // An ID-only change (engine kind 'idchange') is one reconciled row: id "OLD → NEW", both
    // dates, a neutral "ID changed" tag, and the +N d slip only when change_days is set.
    let varCell;
    if (m.kind === 'idchange') {
      const slip = (m.change_days != null && m.change_days !== 0)
        ? ' ' + deltaCell(`${m.change_days > 0 ? '+' : ''}${m.change_days} d`) : '';
      varCell = `<span class="rc-tag idchange">ID changed</span>${slip}`;
    } else if (m.change_days != null) {
      varCell = deltaCell(`${m.change_days > 0 ? '+' : ''}${m.change_days} d`);
    } else {
      varCell = m.kind === 'new' ? '<span class="rc-tag add">Added</span>'
        : m.kind === 'removed' ? '<span class="rc-tag rem">Removed</span>' : '—';
    }
    return `<tr><td class="rc-aid">${esc(id)}</td><td>${esc(name)}${(m.kind === 'new') ? '<span class="rc-tag add" style="margin-left:6px">NEW</span>' : ''}</td>
      <td class="n rc-mut">${esc(m.rev0)}</td><td class="n rc-new">${esc(m.rev1)}</td><td class="n">${varCell}</td></tr>`;
  }).join('');
  const card = `<div class="rc-card"><h3>Milestone changed <span class="rc-n">finish-milestone date changes</span></h3>
    ${rows ? `<div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Activity ID</th><th>Activity Name</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr></thead><tbody>${rows}</tbody></table></div>`
           : noData('No milestone changes between the two revisions.')}</div>`;
  return secmark('5', 'Milestones', 'finish-milestone date changes') + card;
}

// ══ 6 · Calendar (comment 5 — working pattern per calendar, 0-days bug fixed) ════

// A plain working pattern label: "N d/wk · H h/day · HPW h/wk" from {days, hours, hpw}.
function fmtPattern(p) {
  if (!p) return null;
  const parts = [];
  if (p.days != null) parts.push(`${p.days} d/wk`);
  if (p.hours != null) parts.push(`${p.hours} h/day`);
  if (p.hpw != null) parts.push(`${p.hpw} h/wk`);
  return parts.length ? parts.join(' · ') : null;
}

// ══ 6 · Calendar (round-14 redesign — one card per calendar) ═══════════════════
// Each calendar that changed is its own card: the working-week change, a timeline strip that
// shows WHERE in the project the changes fall, a plain list of only the REAL differences
// (non-working ⇄ working, and reduced/restored hours), and which activities use it broken down
// by activity code. Identical dates are summarised, never listed. Renamed/added/removed calendars
// explain what happened to their activities.
function calTimeline(flips) {
  if (!flips.length) return '';
  const times = flips.flatMap(e => [Date.parse(e.iso), Date.parse(e.iso_end || e.iso)]).filter(t => !isNaN(t));
  if (!times.length) return '';
  let lo = Math.min(...times), hi = Math.max(...times);
  if (hi <= lo) { lo -= 20 * 864e5; hi += 20 * 864e5; }
  const span = hi - lo || 1, pos = t => Math.max(0, Math.min(100, (t - lo) / span * 100));
  const ticks = flips.map(e => {
    const cls = e.change === 'now working' ? 'g' : e.change === 'now non-working' ? 'r' : 'a';
    const t0 = Date.parse(e.iso), t1 = Date.parse(e.iso_end || e.iso);
    if (isNaN(t0)) return '';
    if (t1 > t0) return `<div class="rc-tlrange ${cls}" style="left:${pos(t0).toFixed(1)}%;width:${Math.max(1, pos(t1) - pos(t0)).toFixed(1)}%" title="${esc(e.date)}"></div>`;
    return `<div class="rc-tltick ${cls}" style="left:${pos(t0).toFixed(1)}%" title="${esc(e.date)}"></div>`;
  }).join('');
  const lab = ms => { try { return new Date(ms).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' }); } catch (e) { return ''; } };
  return `<div class="rc-tl"><div class="rc-tllab"><span>${lab(lo)}</span><span>${lab(hi)}</span></div><div class="rc-tltrack">${ticks}</div></div>`;
}

function calAssigned(p, pi) {
  const a = p.assigned || {}, byDim = a.by_dim || {};
  const dims = Object.keys(byDim);
  if (!a.count) return '';
  const rev = p.assigned_rev === 'rev0' ? 'Rev.00' : 'Rev.01';
  const hdr = p.change === 'removed' ? 'Activities that used it in Rev.00'
    : p.change === 'added' ? 'Activities using it in Rev.01' : 'Assigned activities';
  const sel = dims.length > 1
    ? `<select class="rc-caldimsel" data-card="${pi}">${dims.map(d => `<option>${esc(d)}</option>`).join('')}</select>`
    : (dims[0] ? `<span class="rc-mut">${esc(dims[0])}</span>` : '');
  const rows = dims.map((d, di) => {
    const chips = (byDim[d] || []).map(x => `<span class="rc-acchip">${esc(x.value)} <span class="cnt">${fmtInt(x.count)}</span></span>`).join('');
    return `<div class="rc-acrow" data-card="${pi}" data-dim="${esc(d)}" style="${di === 0 ? '' : 'display:none'}">${chips || '<span class="rc-mut">no activity codes on these activities</span>'}</div>`;
  }).join('');
  const ids = a.ids || [];
  const idsBlock = ids.length
    ? `<div class="rc-acids"><details><summary>see the ${fmtInt(ids.length)} activity ID${ids.length === 1 ? '' : 's'}</summary><div class="rc-idlist">${ids.slice(0, 60).map(esc).join(' · ')}${ids.length > 60 ? ` · … (${fmtInt(ids.length - 60)} more)` : ''}</div></details></div>`
    : '';
  return `<div class="rc-assign"><div class="rc-assignh">${hdr} — by activity code ${sel} <span class="rc-mut">(${fmtInt(a.count)} activit${a.count === 1 ? 'y' : 'ies'} in ${rev})</span></div>${rows}${idsBlock}</div>`;
}

// Round-15 Option A — one plain-language BRIEF sentence per calendar (self-explaining for a
// planner who did not build the baseline), built from the engine's counts.
function calBrief(p, reassFrom) {
  const name = esc(p.name);
  const acts = p.activities || 0;
  const byDim = (p.assigned || {}).by_dim || {};
  const firstDim = Object.keys(byDim)[0];
  const top = firstDim && (byDim[firstDim] || [])[0];
  const usedBy = acts ? ` Used by ${fmtInt(acts)} activities${top ? `, mostly ${esc(top.value)}` : ''}.` : '';
  if (p.change === 'removed') {
    const dest = (reassFrom[p.name] || []).slice().sort((x, y) => (y.count || 0) - (x.count || 0))[0];
    return `<b>${name}</b> — retired in Rev.01.${dest ? ` The ${fmtInt(dest.count)} activities that used it now run on <b>${esc(dest.to)}</b>.` : ` ${fmtInt(acts)} activities no longer carry this calendar.`}`;
  }
  if (p.change === 'added') {
    const pat = fmtPattern(p.rev1);
    const longer = p.rev1 && p.rev1.hpw != null && p.rev1.hpw >= 60 ? ' A longer working week shortens those durations on paper.' : '';
    return `<b>${name}</b> — new${pat ? ` ${esc(pat)}` : ''} calendar, now used by ${fmtInt(acts)} activities.${longer}`;
  }
  const flips = (p.date_exceptions || []).filter(e => e.change !== 'unchanged');
  const nowW = flips.filter(e => e.change === 'now working').length;
  const nowN = flips.filter(e => e.change === 'now non-working').length;
  const hrs = flips.filter(e => !String(e.change).startsWith('now')).length;
  const bits = [];
  if (nowW) bits.push(`<span class="rc-hl-g">${nowW} day${nowW > 1 ? 's' : ''} made working</span>`);
  if (nowN) bits.push(`<span class="rc-hl-r">${nowN} day${nowN > 1 ? 's' : ''} made non-working</span>`);
  if (hrs) bits.push(`<span class="rc-hl-a">${hrs} reduced-hours ${hrs > 1 ? 'periods' : 'period'} re-houred</span>`);
  const weekChanged = fmtPattern(p.rev0) !== fmtPattern(p.rev1);
  let lead;
  if (bits.length) {
    lead = (bits.length === 1 ? bits[0] : bits.slice(0, -1).join(', ') + ' and ' + bits.slice(-1)) + '.';
    lead += weekChanged ? ' Working week also changed.' : ' Working week itself unchanged.';
  } else if (weekChanged) {
    lead = `working week changed ${esc(fmtPattern(p.rev0) || '—')} → ${esc(fmtPattern(p.rev1) || '—')}.`;
  } else {
    lead = 'no material change to the working calendar.';
  }
  return `<b>${name}</b> — ${lead}${usedBy}`;
}

// The P6-shaped ledger — Attribute | Rev.00 | Rev.01 | Change. Reads like Primavera's calendar
// dialog: fixed working-pattern rows, then only the CHANGED exception dates, then one collapse
// row proving the identical dates were compared. Every on-screen row is already a spreadsheet row.
function calLedger(p) {
  const r0 = p.rev0 || {}, r1 = p.rev1 || {};
  const cell = (v, suf) => (v == null ? '—' : `${v}${suf || ''}`);
  const wkChange = (a, b) => (a == null && b == null) ? '' : (a === b ? 'unchanged' : a == null ? 'added' : b == null ? 'removed' : 'changed');
  const wkCls = c => c === 'unchanged' ? 'n' : c === 'removed' ? 'r' : c === 'added' ? 'g' : 'a';
  const wkRow = (lbl, a, b, suf) => {
    const c = wkChange(a, b);
    return `<tr><td class="rc-lattr">${lbl}</td><td class="rc-lrev">${cell(a, suf)}</td><td class="rc-lrev">${cell(b, suf)}</td><td class="rc-lchg rc-chg-${wkCls(c)}">${c || '—'}</td></tr>`;
  };
  let rows = wkRow('Working days / week', r0.days, r1.days, ' d/wk')
    + wkRow('Hours / day', r0.hours, r1.hours, ' h')
    + wkRow('Hours / week', r0.hpw, r1.hpw, ' h');
  const flips = (p.date_exceptions || []).filter(e => e.change !== 'unchanged');
  const identical = (p.date_exceptions || []).filter(e => e.change === 'unchanged').length;
  let exc = '';
  if (flips.length) {
    exc = `<tr class="rc-lband"><td colspan="4">Exception dates — changed only</td></tr>`
      + flips.map(e => {
        const c = e.change, cls = c === 'now working' ? 'g' : c === 'now non-working' ? 'r' : 'a';
        const note = c === 'now working' ? 'made working' : c === 'now non-working' ? 'made non-working' : `hours ${esc(c)}`;
        return `<tr><td class="rc-lattr"><span class="rc-dot ${cls}"></span>${esc(e.date)}</td><td class="rc-lrev">${esc(e.rev0)}</td><td class="rc-lrev">${esc(e.rev1)}</td><td class="rc-lchg rc-chg-${cls}">${note}</td></tr>`;
      }).join('');
  }
  if (identical) {
    exc += `<tr class="rc-lident"><td colspan="3">${fmtInt(identical)} non-working day${identical > 1 ? 's are' : ' is'} <b>identical</b> in both revisions — no change</td><td class="rc-lchg">not listed</td></tr>`;
  }
  return `<table class="rc-ldg"><thead><tr><th class="rc-lattr">Attribute</th><th class="rc-lrev">Rev.00</th><th class="rc-lrev">Rev.01</th><th class="rc-lchg">Change</th></tr></thead><tbody>${rows}${exc}</tbody></table>`;
}

// Round-16 #03c — an ADDED (or removed) calendar has no other revision to diff against, so its own
// non-working days are listed in a TABLE (Date | Status) rather than only implied by the pattern.
function calNonworkingTable(p) {
  if (p.change !== 'added' && p.change !== 'removed') return '';
  const nd = p.nonworking_dates || [];
  const isRemoved = p.change === 'removed';
  const rev = isRemoved ? 'Rev.00' : 'Rev.01';
  const title = isRemoved ? `Non-working days it had in ${rev}` : 'Non-working days of this new calendar';
  const sub = isRemoved ? '' : ' — no prior revision to compare, so the pattern is listed in full';
  if (!nd.length) {
    return `<div class="rc-nwtbl"><div class="rc-nwh">${title}</div><div class="rc-sec rc-mut" style="margin:4px 0 0">No dated non-working days — this calendar works every day in its weekly pattern (shown above).</div></div>`;
  }
  const trows = nd.map(d => `<tr><td class="rc-lattr">${esc(d.date)}</td><td class="rc-lchg rc-chg-r">${esc(d.status)}</td></tr>`).join('');
  return `<div class="rc-nwtbl"><div class="rc-nwh">${title}<span class="rc-mut">${sub}</span></div>
    <table class="rc-ldg rc-nwld"><thead><tr><th class="rc-lattr">Date</th><th class="rc-lchg">Status</th></tr></thead><tbody>${trows}</tbody></table></div>`;
}

function calendarView(r) {
  const cc = r.calendar_changes || {};
  const patterns = cc.patterns || [];
  const reass = cc.reassignments || [];
  if (!patterns.length) {
    return secmark('6', 'Calendar', 'working pattern · exception dates · assigned activities')
      + `<div class="rc-card"><h3>Calendar</h3>${noData('No calendar definitions available for these revisions.')}</div>`;
  }
  const reassFrom = {};
  reass.forEach(g => { (reassFrom[g.from] = reassFrom[g.from] || []).push(g); });
  let paperAccel = false;
  const TAG = { modified: ['chg', 'modified'], renamed: ['ren', 'renamed'], added: ['add', 'added'], removed: ['rem', 'retired'] };

  // Round-16 #03a — an added OR removed calendar with 0 activities assigned has no schedule impact
  // and only adds noise for the planner, so it is dropped from the detailed cards and the counts
  // (a small note records how many were hidden).
  const isEmptyZero = p => (p.change === 'added' || p.change === 'removed') && !(p.activities > 0);
  const emptyZero = patterns.filter(isEmptyZero);
  const changed = patterns.filter(p => p.change !== 'unchanged' && !isEmptyZero(p));
  const unchanged = patterns.filter(p => p.change === 'unchanged');

  // Section digest — the whole-section headline before any single calendar.
  const nMod = changed.filter(p => p.change === 'modified' || p.change === 'renamed').length;
  const nAdd = changed.filter(p => p.change === 'added').length;
  const nRem = changed.filter(p => p.change === 'removed').length;
  const totFlips = changed.reduce((s, p) => s + (p.date_exceptions || []).filter(e => e.change !== 'unchanged').length, 0);
  const legend = '<span class="rc-legend"><span><i style="background:var(--success)"></i>made working</span><span><i style="background:var(--danger)"></i>made non-working</span><span><i style="background:var(--warning)"></i>hours changed</span></span>';
  const digest = `<div class="rc-caldigest"><span><b>${nMod} modified · ${nAdd} added · ${nRem} retired · ${unchanged.length} unchanged</b> — ${totFlips} exception date${totFlips === 1 ? '' : 's'} changed.</span>${legend}</div>`;
  const dropNote = emptyZero.length
    ? `<div class="rc-caldrop">${fmtInt(emptyZero.length)} calendar${emptyZero.length > 1 ? 's' : ''} with <b>0 activities</b> assigned (added or retired) ${emptyZero.length > 1 ? 'are' : 'is'} not detailed — no schedule impact.</div>`
    : '';

  const cards = changed.map((p, pi) => {
    const [tagcls, taglbl] = TAG[p.change] || ['chg', p.change || 'changed'];
    if (p.rev0 && p.rev1 && p.rev0.hpw != null && p.rev1.hpw != null && p.rev1.hpw > p.rev0.hpw) paperAccel = true;
    const nameHtml = p.change === 'renamed' ? `${esc(p.name)} <span class="rc-mut">→ ${esc(p.renamed_to)}</span>` : esc(p.name);
    const meta = p.activities ? `${fmtInt(p.activities)} activities` : '';
    let ctx = '';
    if (p.change === 'removed') {
      const dest = (reassFrom[p.name] || []).slice().sort((x, y) => (y.count || 0) - (x.count || 0))[0];
      ctx = `<div class="rc-calctx">Retired in Rev.01.${dest ? ` The ${fmtInt(dest.count)} activities that used it now use <b>${esc(dest.to)}</b> — consolidated, no work left without a calendar.` : ''} <span class="rc-flag">Flagged for review.</span></div>`;
    } else if (p.change === 'added') {
      const longer = p.rev1 && p.rev1.hpw != null && p.rev1.hpw >= 60;
      ctx = `<div class="rc-calctx">New in Rev.01 — now used by <b>${fmtInt(p.activities || 0)}</b> activities.${longer ? ' A longer working week shortens those durations on paper.' : ''} <span class="rc-flag">Flagged for review.</span></div>`;
    }
    return `<div class="rc-calcard">
      <div class="rc-calhead"><span class="rc-calname">${nameHtml}</span><span class="rc-caltag ${tagcls}">${esc(taglbl)}</span><span class="rc-calmeta">${meta}</span></div>
      <div class="rc-calbrief">${calBrief(p, reassFrom)}</div>
      ${ctx}${calLedger(p)}${calNonworkingTable(p)}${calAssigned(p, pi)}</div>`;
  }).join('');

  const unchangedLine = unchanged.length
    ? `<div class="rc-calunchanged"><b>${unchanged.length} calendar${unchanged.length > 1 ? 's' : ''} unchanged</b> — ${unchanged.map(p => `${esc(p.name)}${p.activities ? ` (${fmtInt(p.activities)})` : ''}`).join(', ')}. Identical working pattern and non-working dates in both revisions.</div>`
    : '';
  const callout = paperAccel
    ? '<div class="rc-callout warn">A calendar moved to a longer working week (more hours/week) — durations shorten <b>on paper</b> without changing the work. A paper acceleration to confirm.</div>'
    : '';
  return secmark('6', 'Calendar', 'working pattern · exception dates · assigned activities by code')
    + `<div class="rc-card">${digest}${dropNote}${cards}${unchangedLine}${callout}</div>`;
}

// ══ 7 · Cost & Resources (comments 8, 9, 10) ═══════════════════════════════════

// Planned-value chart — monthly Rev.01 bars with a value LABEL above each (comment 8),
// plus the Rev.00/Rev.01 cumulative curves. Value labels use the compact money formatter.
function scurveSvg(curves, rev0finish, rev1finish) {
  const vm = curves.value_monthly || [];
  const vc = curves.value_cumulative || [];
  const months = curves.months || vm.map(x => x.month);
  const n = months.length;
  if (!n || !vm.length) return noData('No planned-value spread available.');
  // Extra top padding (plotT) so the tallest bar's value label is never clipped (comment 6a).
  const W = Math.max(760, n * 66), plotL = 56, plotR = W - 116, plotT = 58, plotB = 250;
  const colW = (plotR - plotL) / n;
  const bw = Math.min(13, colW * 0.32);   // narrower — two grouped bars per month
  const byMonth0 = {}, byMonth1 = {};
  vm.forEach(x => { byMonth0[x.month] = x.rev0 || 0; byMonth1[x.month] = x.rev1 || 0; });
  const maxMonthly = Math.max(1, ...vm.map(x => Math.max(x.rev0 || 0, x.rev1 || 0)));
  const cumByMonth = {}; vc.forEach(x => { cumByMonth[x.month] = x; });
  const maxCum = Math.max(1, ...vc.map(x => Math.max(x.rev0 || 0, x.rev1 || 0)));
  let bars = '';
  months.forEach((m, i) => {
    const cx = plotL + (i + 0.5) * colW;
    const v0 = byMonth0[m] || 0, v1 = byMonth1[m] || 0;
    // BOTH the Rev.00 (before, grey) and Rev.01 (after, accent) monthly bars are drawn side by side
    // (comment 3 — "the before histogram must be shown"); a non-zero month keeps a min height.
    const h0 = v0 > 0 ? Math.max(3, (v0 / maxMonthly) * (plotB - plotT)) : 0;
    const h1 = v1 > 0 ? Math.max(3, (v1 / maxMonthly) * (plotB - plotT)) : 0;
    const x0 = cx - bw - 1, x1 = cx + 1;
    if (h0 > 0) bars += `<rect x="${x0.toFixed(1)}" y="${(plotB - h0).toFixed(1)}" width="${bw.toFixed(1)}" height="${h0.toFixed(1)}" rx="2" fill="var(--rc-b0)"/>`;
    if (h1 > 0) bars += `<rect x="${x1.toFixed(1)}" y="${(plotB - h1).toFixed(1)}" width="${bw.toFixed(1)}" height="${h1.toFixed(1)}" rx="2" fill="var(--accent)" opacity=".9"/>`;
    if (v1 > 0 || v0 > 0) {
      // Value angled up off the bar top so adjacent labels never overlap or get trimmed (round-16 #02).
      const labelY = plotB - Math.max(h0, h1) - 6;
      bars += `<text x="${cx.toFixed(1)}" y="${labelY.toFixed(1)}" font-size="9" font-weight="700" fill="var(--ink-soft)" text-anchor="start" transform="rotate(-55 ${cx.toFixed(1)} ${labelY.toFixed(1)})">${escapeHtml(fmtMoney(v1))}</text>`;
    }
  });
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
  // Month label under EVERY bar (angled ~-42°), so none is missing (comment 6a).
  const xlabels = months.map((m, i) => {
    const cx = plotL + (i + 0.5) * colW;
    const ly = plotB + 12;
    return `<text x="${cx.toFixed(1)}" y="${ly}" font-size="8.5" fill="var(--muted)" text-anchor="end" transform="rotate(-42 ${cx.toFixed(1)} ${ly})">${escapeHtml(String(m))}</text>`;
  }).join('');
  // Completion-date label at the END of the Rev.01 cumulative curve (comment 5) — e.g.
  // "09 Feb 2027" pinned just past the final cumulative point, with a small marker dot.
  let finishLabel = '';
  if (rev1finish && n) {
    const lastM = months[n - 1];
    const endX = plotL + (n - 1 + 0.5) * colW;
    const endVal = cumByMonth[lastM] ? (cumByMonth[lastM].rev1 || 0) : 0;
    const endY = plotB - (endVal / maxCum) * (plotB - plotT);
    // The right margin (plotR = W-108) leaves room for the completion label past the curve end.
    const tx = endX + 8;
    finishLabel = `<circle cx="${endX.toFixed(1)}" cy="${endY.toFixed(1)}" r="3.2" fill="var(--accent-dark)"/>`
      + `<text x="${tx.toFixed(1)}" y="${(endY - 7).toFixed(1)}" font-size="10" font-weight="800" fill="var(--accent-dark)" text-anchor="start">${esc(rev1finish)}</text>`
      + `<text x="${tx.toFixed(1)}" y="${(endY + 5).toFixed(1)}" font-size="8" fill="var(--muted)" text-anchor="start">Rev.01 finish</text>`;
  }
  return `<div class="rc-chartwrap"><svg viewBox="0 0 ${W} 300" class="rc-svg" style="min-width:${W}px" role="img" aria-label="Planned value chart">
    <line x1="${plotL}" y1="${plotB}" x2="${plotR}" y2="${plotB}" stroke="var(--border)"/>
    <line x1="${plotL}" y1="${plotT}" x2="${plotL}" y2="${plotB}" stroke="var(--border)"/>
    ${bars}
    ${line('rev0', 'var(--muted)', 2.2)}
    ${line('rev1', 'var(--accent-dark)', 2.6)}
    ${origLine}${xlabels}${finishLabel}
  </svg></div>`;
}

function moneyDims(curves) {
  const bbd = (curves && curves.budget_by_dim) || {};
  return Object.keys(bbd).filter(d => Array.isArray(bbd[d]) && bbd[d].length);
}
function moneyValues(curves, dim) {
  const bbd = (curves && curves.budget_by_dim) || {};
  const rows = Array.isArray(bbd[dim]) ? bbd[dim] : [];
  return [...new Set(rows.map(x => x.category).filter(v => v != null && v !== ''))];
}

function costView(r) {
  const curves = r.curves || {};
  const rc = r.resource_changes || {};
  const costChanges = rc.activity_cost_changes || [];
  const hasCostTbl = !!(rc.cost_available || costChanges.length);
  const mdims = moneyDims(curves);
  if (!curves.cost_available && !hasCostTbl && !mdims.length) {
    return secmark('7', 'Cost & Resources', 'planned value, where the money moved, cost changes')
      + `<div class="rc-card"><h3>Cost &amp; resources <span class="rc-n">optional</span></h3>${noData('Neither revision carries cost loading — this section is reported as not applicable rather than "no change".')}</div>`;
  }

  // Planned value of work — value labels above each bar, clear of the cumulative curve (comment 4).
  const scurve = curves.cost_available
    ? `<div class="rc-card"><h3>Planned value of work <span class="rc-n">monthly value (label above each bar) + cumulative</span></h3>
        ${scurveSvg(curves, r.rev0 && r.rev0.finish, r.rev1 && r.rev1.finish)}
        <div class="rc-legend"><span><i style="background:var(--rc-b0)"></i>Rev.00 value/mo</span><span><i style="background:var(--accent)"></i>Rev.01 value/mo</span><span><i class="rc-line" style="background:var(--muted)"></i>Rev.00 cumulative</span><span><i class="rc-line" style="background:var(--accent-dark)"></i>Rev.01 cumulative</span></div>
        ${Number(curves.value_after_orig_finish) > 0 ? `<div class="rc-callout warn"><b>${fmtNum(curves.value_after_orig_finish)} of planned value now falls after the original finish (${esc(r.rev0 && r.rev0.finish)})</b> — potential extended-works exposure (prolongation, prelims, plant hire). Surfaced for review.</div>` : ''}
      </div>`
    : `<div class="rc-card"><h3>Planned value of work</h3>${noData('No cost loading — planned-value chart not applicable.')}</div>`;

  // Where the money moved — activity-code selector + variance bar chart.
  const moneyCard = mdims.length
    ? `<div class="rc-card"><h3>Where the money moved <span class="rc-n">by activity code</span> <span class="rc-pdfnote">🔵 reflects in PDF</span></h3>
        <div id="rc-money-filter"></div>
        <div id="rc-money-chart"></div>
        <div id="rc-money-tbl" style="margin-top:8px"></div></div>`
    : `<div class="rc-card"><h3>Where the money moved</h3>${noData('No budget-by-code breakdown available.')}</div>`;

  // Itemised activity-level cost table — returns to Cost & Resources (comment 6). The by-WBS
  // roll-up (report.cost_by_wbs) is no longer rendered anywhere.
  const pick = (row, keys) => { for (const k of keys) { if (row[k] != null && row[k] !== '') return row[k]; } return null; };
  // Rows are resource_changes.activity_cost_changes: rev0/rev1 are pre-formatted money
  // STRINGS and delta carries the variance (comment 6) — read them directly, never coerce
  // to Number (that produced the previously-blank Before/After/Variance columns).
  // All changed activities (no row cap — the table scrolls; the Total must sum what is shown).
  // Money is formatted from the NUMERIC rev0_num/rev1_num so every row and the Total read the same
  // 2dp format (comment: itemised rows and the total disagreed on decimals).
  const costRows = costChanges.map(c => {
    const id = pick(c, ['code', 'activity_id', 'id']), name = pick(c, ['name', 'activity_name']);
    const b0 = typeof c.rev0_num === 'number' ? c.rev0_num : null;
    const a1 = typeof c.rev1_num === 'number' ? c.rev1_num : null;
    const delta = c.delta;
    const isNew = (b0 === 0 || b0 == null) && (a1 || 0) > 0;
    let varCell;
    if (typeof delta === 'number') {
      varCell = `<span class="rc-d ${delta > 0 ? 'up' : delta < 0 ? 'down' : 'zero'}">${delta > 0 ? '+' : ''}${fmtNum(delta)}</span>`;
    } else if (delta != null && delta !== '') {
      varCell = `<span class="rc-d">${esc(delta)}</span>`;
    } else {
      varCell = '—';
    }
    return `<tr><td class="rc-aid">${esc(id)}</td><td>${esc(name)}${isNew ? '<span class="rc-tag add" style="margin-left:6px">NEW</span>' : ''}</td>
      <td class="n rc-mut">${b0 != null ? fmtNum(b0) : '—'}</td><td class="n rc-new">${a1 != null ? fmtNum(a1) : '—'}</td>
      <td class="n">${varCell}</td></tr>`;
  }).join('');
  // Total row (comment 4) — sum of the changed activities; the Variance is After − Before so it
  // always ties to the Before/After totals (not Σ per-row delta, which could drift).
  const sum0 = costChanges.reduce((s, c) => s + (c.rev0_num || 0), 0);
  const sum1 = costChanges.reduce((s, c) => s + (c.rev1_num || 0), 0);
  const sumD = sum1 - sum0;
  const totalRow = costChanges.length
    ? `<tr class="rc-costtot"><td colspan="2"><b>Total — changed activities</b></td><td class="n">${fmtNum(sum0)}</td><td class="n">${fmtNum(sum1)}</td><td class="n"><span class="rc-d ${sumD > 0 ? 'up' : sumD < 0 ? 'down' : 'zero'}">${sumD > 0 ? '+' : ''}${fmtNum(sumD)}</span></td></tr>`
    : '';
  // Activity-code filter + pie (comment 4) — only when the cost changes carry codes.
  const cdims = [...new Set(costChanges.flatMap(c => Object.keys(c.codes || {})))];
  const costFilterPie = cdims.length ? `<div id="rc-cost-filter"></div><div id="rc-cost-pie"></div>` : '';
  const costTblCard = hasCostTbl
    ? `<div class="rc-card"><h3>Cost changed <span class="rc-n">activity-level · budget total cost · variance</span> ${cdims.length ? '<span class="rc-pdfnote">🔵 reflects in PDF</span>' : ''}</h3>
        ${costFilterPie}
        ${costRows ? `<div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Activity ID</th><th>Activity Name</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr></thead><tbody>${costRows}${totalRow}</tbody></table></div>` : noData('No activity-level cost changes.')}</div>`
    : '';

  // Cost reconciliation (comment 3) — where the rest of the budget sits: the changed-activity
  // total is only part of the whole budget; account for every unit (changed + unchanged + new
  // scope − removed scope = budget total), so "where does the remaining budget go" is answered.
  const recon = rc.cost_reconciliation || [];
  const reconCard = recon.length
    ? `<div class="rc-card"><h3>Cost reconciliation <span class="rc-n">where the budget sits — changed vs the whole total</span></h3>
        <div class="rc-sec">The changed-activity total is only part of the whole budget. This accounts for every unit — nothing is unexplained.</div>
        <div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Bucket</th><th>What it is</th><th class="n">Rev.00</th><th class="n">Rev.01</th><th class="n">Variance</th></tr></thead><tbody>
        ${recon.map(b => {
          const d = typeof b.delta === 'number' ? b.delta : 0;
          const isTot = b.bucket === 'total';
          return `<tr class="${isTot ? 'rc-costtot' : ''}"><td>${isTot ? `<b>${esc(b.label)}</b>` : esc(b.label)}</td><td class="rc-mut">${esc(b.note)}</td>
            <td class="n${isTot ? '' : ' rc-mut'}">${b.rev0 ? fmtNum(b.rev0) : '—'}</td><td class="n">${b.rev1 ? fmtNum(b.rev1) : '—'}</td>
            <td class="n"><span class="rc-d ${d > 0 ? 'up' : d < 0 ? 'down' : 'zero'}">${d > 0 ? '+' : ''}${fmtNum(d)}</span></td></tr>`;
        }).join('')}
        </tbody></table></div></div>`
    : '';

  return secmark('7', 'Cost & Resources', 'planned value, where the money moved, cost changes')
    + scurve + moneyCard + costTblCard + reconCard;
}

// ══ 8 · Resources (comment 5 — resource-changed table on its own tab) ═══════════

// Resource-by-resource comparison (comment 7). Leads with ONE row per resource / trade —
// man-hours Before → After (from curves.manhours_by_trade rev0/rev1/var), a neutral kind tag
// (Added / Removed / Increased / Decreased) and "Assigned to" (distinct activities that
// resource touches, grouped from resource_changes.assignment_changes). The raw per-activity
// assignment list follows as supporting detail rather than leading the section.
function resourceKindMeta(kind, before, after) {
  let k = String(kind || '').toLowerCase();
  if (!k || k === 'changed') {
    const b = Number(before) || 0, a = Number(after) || 0;
    k = (b === 0 && a > 0) ? 'added' : (a === 0 && b > 0) ? 'removed'
      : a > b ? 'increased' : a < b ? 'decreased' : 'unchanged';
  }
  const map = {
    added: ['add', 'Added'], removed: ['rem', 'Removed'],
    increased: ['chg', 'Increased'], decreased: ['chg', 'Reduced'],
    unchanged: ['', 'Unchanged'],
  };
  return map[k] || ['chg', String(kind || 'Changed')];
}

// Compact man-hours label (42,000 → "42k") for the horizontal before/after bars.
function fmtK(x) {
  const n = Number(x) || 0, a = Math.abs(n);
  if (a >= 1000) return `${n < 0 ? '-' : ''}${Math.round(a / 1000)}k`;
  return fmtInt(n);
}

// One before/after horizontal row — Rev.00 bar over Rev.01 bar, variance chip, optional
// Added/Removed/Increased/Reduced tag. Shared by the manpower resource-mix and resource
// comparison views (comments 5 & 6). `mx` is the shared scale across all rows.
function baBar(name, v0, v1, mx, opts = {}) {
  const a = Number(v0) || 0, b = Number(v1) || 0, v = b - a;
  const added = a === 0 && b > 0, removed = b === 0 && a > 0;
  const wa = mx > 0 ? Math.max(a / mx * 100, a > 0 ? 2 : 0) : 0;
  const wb = mx > 0 ? Math.max(b / mx * 100, b > 0 ? 2 : 0) : 0;
  const fmt = opts.fmt || fmtInt;
  const code = opts.code ? `<span class="rc-hcode">${esc(opts.code)}</span>` : '';
  let tag = '';
  if (opts.tag) {
    tag = added ? '<span class="rc-rchip add sm">Added</span>'
      : removed ? '<span class="rc-rchip rem sm">Removed</span>'
      : v > 0 ? '<span class="rc-rchip chg sm">Increased</span>'
      : v < 0 ? '<span class="rc-rchip chg sm">Reduced</span>'
      : '<span class="rc-rchip sm">Unchanged</span>';
  }
  // Value label sits INSIDE the bar when it is wide enough, otherwise just past the bar end so it
  // is never trimmed (comment: the number inside the bars is trimmed). Each bar is labelled
  // Rev.00 / Rev.01 so a before/after pair never reads as duplicated work.
  const val = (w, val, inside) => `<span class="rc-bval" style="${w > 26
    ? `left:calc(${w.toFixed(1)}% - 6px);transform:translateX(-100%);color:${inside}`
    : `left:calc(${w.toFixed(1)}% + 6px);color:var(--ink-soft)`}">${val ? fmt(val) : ''}</span>`;
  return `<div class="rc-hrow2"><div class="rc-hlbl">${esc(name)}${code}</div>
    <div class="rc-ba"><div class="rc-babars">
      <div class="rc-brow"><span class="rc-blab">Rev.00</span><div class="rc-btrack"><div class="rc-bfill b0${removed ? ' rem' : ''}" style="width:${wa.toFixed(1)}%"></div>${val(wa, a, 'var(--ink-soft)')}</div></div>
      <div class="rc-brow"><span class="rc-blab r1">Rev.01</span><div class="rc-btrack"><div class="rc-bfill b1${added ? ' add' : ''}" style="width:${wb.toFixed(1)}%"></div>${val(wb, b, '#fff')}</div></div>
    </div><span class="rc-hvar ${v >= 0 ? 'up' : 'down'}">${v >= 0 ? '+' : ''}${fmt(v)}</span>${tag}</div></div>`;
}

function resourceView(r) {
  const rc = r.resource_changes || {};
  const curves = r.curves || {};
  const totals = rc.resource_totals || [];
  const byTrade = curves.manhours_by_trade || [];
  const assign = rc.assignment_changes || [];
  const hasRes = !!(rc.resource_available || totals.length || byTrade.length || assign.length);
  if (!hasRes) {
    return secmark('8', 'Resources', 'before vs after, at a glance')
      + `<div class="rc-card"><h3>Resources <span class="rc-n">optional</span></h3>${noData('Neither revision carries resource assignments — this section is reported as not applicable rather than "no change".')}</div>`;
  }

  // Summary chips — how many resources were added / removed / re-sized.
  const sm = rc.summary || {};
  const nAdd = sm.res_added != null ? sm.res_added : totals.filter(t => t.kind === 'added').length;
  const nRem = sm.res_removed != null ? sm.res_removed : totals.filter(t => t.kind === 'removed').length;
  const nChg = sm.res_resized != null ? sm.res_resized : totals.filter(t => t.kind === 'increased' || t.kind === 'decreased').length;
  const chips = `<div class="rc-rsum"><span class="rc-rchip add">${fmtInt(nAdd)} added</span>`
    + `<span class="rc-rchip rem">${fmtInt(nRem)} removed</span>`
    + `<span class="rc-rchip chg">${fmtInt(nChg)} re-sized</span></div>`;

  // Before/after comparison bars — assigned units per resource, biggest movers first.
  const mx = Math.max(1, ...totals.flatMap(t => [Number(t.rev0) || 0, Number(t.rev1) || 0]));
  const bars = totals.map(t => baBar(t.name, t.rev0, t.rev1, mx, { tag: true, fmt: fmtInt, code: t.id })).join('');
  const legend = `<div class="rc-legend">
      <span><i style="background:var(--rc-b0)"></i>Rev.00 units</span>
      <span><i style="background:var(--accent)"></i>Rev.01 units</span>
      <span><i style="background:var(--success)"></i>Added</span>
      <span><i style="background:var(--danger)"></i>Removed</span></div>`;
  const compCard = `<div class="rc-card"><h3>Resource comparison <span class="rc-n">assigned units before vs after, per resource</span></h3>
      <div class="rc-sec">Every resource, Rev.00 vs Rev.01, sorted by the biggest change — <b class="rc-add">Added</b> (new in Rev.01, 0 → N), <b class="rc-rem">Removed</b> (gone in Rev.01, N → 0), and re-sized are all called out.</div>
      ${chips}
      ${bars ? `<div class="rc-hbars">${bars}</div>${legend}` : noData('No resource assignments to compare.')}</div>`;

  // Enhanced detail table — grouped by resource (not scattered per activity).
  const tblRows = totals.map(t => {
    const [kTag, kLabel] = resourceKindMeta(t.kind, t.rev0, t.rev1);
    const v = Number(t.var != null ? t.var : (t.rev1 - t.rev0)) || 0;
    return `<tr><td class="rc-aid">${esc(t.id || '—')}</td><td>${esc(t.name)}</td><td class="rc-mut">${esc(t.type || '—')}</td>
      <td class="n rc-mut">${t.rev0 ? fmtInt(t.rev0) : '—'}</td><td class="n rc-new">${t.rev1 ? fmtInt(t.rev1) : '—'}</td>
      <td class="n"><span class="rc-d ${v > 0 ? 'up' : v < 0 ? 'down' : 'zero'}">${v > 0 ? '+' : ''}${fmtInt(v)}</span></td>
      <td class="n rc-mut">${fmtInt(t.activities || 0)}</td><td>${typeTag(kTag, kLabel)}</td></tr>`;
  }).join('');
  const tblCard = totals.length ? `<div class="rc-card"><h3>Resource changes — detail <span class="rc-n">grouped by resource</span></h3>
      <div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Resource ID</th><th>Resource</th><th>Type</th><th class="n">Rev.00 (units)</th><th class="n">Rev.01 (units)</th><th class="n">Variance</th><th class="n">Activities</th><th>Change</th></tr></thead><tbody>${tblRows}</tbody></table></div>
      <div class="rc-callout">Units before/after, variance, how many activities each resource is on, and a clear Added / Removed / Increased / Reduced tag — one row per resource rather than scattered per activity.</div></div>` : '';

  // Per-activity assignment changes kept as an expandable supporting detail.
  const pick = (row, keys) => { for (const k of keys) { if (row[k] != null && row[k] !== '') return row[k]; } return null; };
  const asgRows = assign.map(a => {
    const id = pick(a, ['activity_id', 'code', 'id']), name = pick(a, ['activity_name', 'name']);
    const [kTag, kLabel] = resourceKindMeta(a.kind, a.rev0, a.rev1);
    return `<tr><td class="rc-aid">${esc(id)}</td><td>${esc(name)}</td>
      <td class="rc-aid">${esc(a.resource_id)}</td><td>${esc(a.resource || a.resource_name)}</td>
      <td class="n rc-mut">${esc(a.rev0)}</td><td class="n rc-new">${esc(a.rev1)}</td><td>${typeTag(kTag, kLabel)}</td></tr>`;
  }).join('');
  const asgCard = assign.length ? `<div class="rc-card"><details class="rc-details"><summary>Per-activity assignment detail <span class="rc-n">${assign.length} change${assign.length === 1 ? '' : 's'}</span></summary>
      <div class="rc-tblscroll" style="margin-top:10px"><table class="rc-t"><thead><tr><th>Activity ID</th><th>Activity Name</th><th>Resource ID</th><th>Resource</th><th class="n">Before</th><th class="n">After</th><th>Change</th></tr></thead><tbody>${asgRows}</tbody></table></div></details></div>` : '';

  return secmark('8', 'Resources', 'before vs after, at a glance') + compCard + tblCard + asgCard;
}

function renderMoneyChart(body) {
  const chart = body.querySelector('#rc-money-chart');
  const tbl = body.querySelector('#rc-money-tbl');
  if (!chart || !tbl) return;
  const r = state.revcompareReport || {};
  const bbd = (r.curves && r.curves.budget_by_dim) || {};
  const dim = rcFilters.money.dim, val = rcFilters.money.val || 'All';
  const allRows = Array.isArray(bbd[dim]) ? bbd[dim] : [];
  // Picking a specific code value filters the whole sub-feature to it; "All" shows every value.
  const rows = allRows.filter(x => val === 'All' || x.category === val);
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

// Cost-changed pie (comment 4) — share of the total budget variance by the selected activity code.
function renderCostPie(body) {
  const chart = body.querySelector('#rc-cost-pie');
  if (!chart) return;
  const cc = ((state.revcompareReport || {}).resource_changes || {}).activity_cost_changes || [];
  const dim = rcFilters.cost.dim;
  const byVal = {};
  cc.forEach(c => { const v = (c.codes || {})[dim]; if (v == null || v === '') return; byVal[v] = (byVal[v] || 0) + Math.abs(typeof c.delta === 'number' ? c.delta : 0); });
  // One distinct colour per code value, so each pie slice + legend swatch is readable (like the scope donut).
  const order = Object.keys(byVal);
  const items = Object.entries(byVal).map(([k, v]) => ({ label: k, v, color: tokenColor(k, order) })).filter(x => x.v > 0);
  chart.innerHTML = `<div class="rc-sec" style="margin-bottom:4px">Cost variance by ${escapeHtml(String(dim))} <span class="rc-mut">— share of the total change</span></div>`
    + donutSvg(items, { centerLabel: '|Δ| cost', emptyMsg: 'No coded cost changes for this dimension.' });
}

function wireCost(body) {
  const r = state.revcompareReport || {};
  const host = body.querySelector('#rc-money-filter');
  if (host) {
    const dims = moneyDims(r.curves || {});
    if (dims.length) groupedFilterControl(host, {
      dims, state: rcFilters.money,
      valuesFor: (dim) => moneyValues(r.curves || {}, dim),
      onChange: () => renderMoneyChart(body),
    });
  }
  // Cost-changed activity-code filter + pie.
  const chost = body.querySelector('#rc-cost-filter');
  if (chost) {
    const cc = (r.resource_changes || {}).activity_cost_changes || [];
    const cdims = [...new Set(cc.flatMap(c => Object.keys(c.codes || {})))];
    if (cdims.length) groupedFilterControl(chost, { dims: cdims, state: rcFilters.cost, onChange: () => renderCostPie(body) });
  }
}

// ══ 9 · Manpower (round 15 — LABOUR man-hours only, difference-first) ════════════
// Man-hours = P6 Budgeted LABOUR Units. Equipment-hours and material quantities (m³/t) are a
// different unit of measure and are reported separately, never summed into man-hours (summing
// them made the total balloon into a cost-like 243M). The section LEADS with the difference
// (Rev.01 − Rev.00); the two absolute totals are supporting context.

// Per-trade exact figures — the numbers a planner reconciles to P6, kept as supporting detail.
function mpTradeTable(rows) {
  const tr = rows.map(t => `<tr><td class="rc-aid">${esc(t.resource_id || '—')}</td><td>${esc(t.name)}</td>
      <td class="n rc-mut">${fmtInt(t.rev0 || 0)}</td><td class="n rc-new">${fmtInt(t.rev1 || 0)}</td>
      <td class="n"><span class="rc-d ${t.v > 0 ? 'up' : t.v < 0 ? 'down' : 'zero'}">${t.v > 0 ? '+' : ''}${fmtInt(t.v)}</span></td></tr>`).join('');
  return `<details class="rc-details" style="margin-top:10px"><summary>Per-trade man-hours — exact figures <span class="rc-n">${rows.length} labour resource${rows.length === 1 ? '' : 's'}</span></summary>
    <div class="rc-tblscroll" style="margin-top:10px"><table class="rc-t"><thead><tr><th>Resource ID</th><th>Resource</th><th class="n">Rev.00 (mh)</th><th class="n">Rev.01 (mh)</th><th class="n">Change</th></tr></thead><tbody>${tr}</tbody></table></div></details>`;
}

// Equipment / material / untyped — shown honestly beside man-hours, never added in.
function mpOtherResources(other) {
  const label = { equipment: ['Equipment', 'equipment-hours'], material: ['Material', 'quantities (m³ / t / m²)'],
    untyped: ['Untyped', 'units — no resource type in the P6 export'] };
  const boxes = Object.entries(other).map(([k, v]) => {
    const [nm, unit] = label[k] || [k, 'units'];
    const dv = (v.var != null) ? v.var : ((v.rev1 || 0) - (v.rev0 || 0));
    return `<div class="rc-obox"><div class="rc-k">${nm}</div><div class="rc-ov">${fmtInt(v.rev0 || 0)} → ${fmtInt(v.rev1 || 0)}</div>
      <div class="rc-ou">${esc(unit)} · ${dv > 0 ? '+' : ''}${fmtInt(dv)}${v.n1 ? ` · ${fmtInt(v.n1)} assignments` : ''}</div></div>`;
  }).join('');
  const matWarn = other.material ? `<div class="rc-warn">Material quantities are shown as one figure because this export doesn't carry each resource's unit of measure — they can't be safely labelled per material (m³ vs t) or summed.</div>` : '';
  const untypedWarn = other.untyped ? `<div class="rc-warn">${fmtInt(other.untyped.n1 || other.untyped.n0 || 0)} assignment(s) carry no resource type in the P6 export — excluded from man-hours (never guessed as labour). Populate the P6 resource dictionary to include them.</div>` : '';
  return `<div class="rc-card"><h3>Other resources <span class="rc-n">reported separately · never added to man-hours</span></h3>
    <div class="rc-sec">Equipment and material carry their own units of measure, so nothing is dropped from the comparison — but they do not belong in a man-hours total.</div>
    <div class="rc-other">${boxes}</div>${matWarn}${untypedWarn}</div>`;
}

function manpowerView(r) {
  const curves = r.curves || {};
  const months = curves.months || [];
  const mix = curves.manhours_by_trade || [];
  const mt = curves.manhours_total || {};
  const other = curves.other_resources || {};
  const hasOther = Object.keys(other).length > 0;

  if (!curves.resource_available || !months.length) {
    return secmark('9', 'Manpower', 'labour man-hours, before vs after')
      + `<div class="rc-card"><h3>Manpower</h3>${noData('Neither revision carries LABOUR resource loading — man-hours are reported as not applicable rather than "no change".' + (hasOther ? ' Equipment / material resources are listed below.' : ''))}</div>`
      + (hasOther ? mpOtherResources(other) : '');
  }

  // ── Hero: the man-hours DIFFERENCE (Rev.01 − Rev.00), labour only ──
  const v0 = mt.rev0 || 0, v1 = mt.rev1 || 0;
  const diff = (mt.var != null) ? mt.var : (v1 - v0);
  const pct = mt.pct;
  const dcls = diff > 0 ? 'up' : diff < 0 ? 'down' : 'zero';
  const pctTxt = (v0 === 0 && v1 > 0) ? 'new' : (pct == null ? '—' : (pct > 0 ? '+' : '') + fmtNum(pct, 1) + '%');
  const line = diff === 0
    ? `Rev.01 plans the <b>same</b> labour man-hours as Rev.00.`
    : `Rev.01 plans <b>${fmtInt(Math.abs(diff))} ${diff > 0 ? 'more' : 'fewer'}</b> labour man-hours than Rev.00 — change detected; review the trade and monthly breakdown below.`;
  const hero = `<div class="rc-card"><h3>Labour man-hours — Rev.00 → Rev.01 <span class="rc-n">the change is the headline</span></h3>
    <div class="rc-mp-herorow">
      <div class="rc-mp-big ${dcls}">${diff > 0 ? '+' : ''}${fmtInt(diff)}<div class="rc-mp-biglbl">labour man-hours change</div></div>
      <div class="rc-mp-chips">
        <div class="rc-mp-chip"><div class="rc-k">Labour · Rev.00</div><div class="rc-v soft">${fmtInt(v0)}</div></div>
        <div class="rc-mp-arrow">→</div>
        <div class="rc-mp-chip"><div class="rc-k">Labour · Rev.01</div><div class="rc-v soft">${fmtInt(v1)}</div></div>
        <div class="rc-mp-chip"><div class="rc-k">Change</div><div class="rc-v ${dcls}">${pctTxt}</div></div>
      </div>
    </div>
    <div class="rc-sec">${line}</div>
    <div class="rc-cap"><b>Man-hours = sum of P6 Budgeted Labor Units</b> (resource type = Labour). Equipment and material are reported separately below and are <b>not</b> in this number, so it ties to P6's Labor Units total for each revision.</div>
  </div>`;

  // ── Monthly labour man-hours — Before & After grouped bars (round-16 #01), a compact value
  //    labelled on EVERY bar, nothing trimmed; the variance lives in the hero + by-trade chart.
  const mm = curves.manpower_monthly || [];
  const r0map = {}, r1map = {};
  mm.forEach(m => { r0map[m.month] = m.rev0; r1map[m.month] = m.rev1; });
  const rev0v = months.map(mo => Number(r0map[mo]) || 0);
  const rev1v = months.map(mo => Number(r1map[mo]) || 0);
  const n = months.length;
  const W = Math.max(760, n * 58), h = 300, L = 40, Rp = 14, T = 48, B = 54;
  const ph = h - T - B;
  const mx = Math.max(1, ...rev0v, ...rev1v);
  const step = (W - L - Rp) / n, bw = Math.min(16, step * 0.30), gap = 3;
  let s = `<line x1="${L}" y1="${T + ph}" x2="${W - Rp}" y2="${T + ph}" stroke="var(--border)"/>`;
  // Value label angled up-right off the bar top so adjacent labels never overlap or clip.
  const vlabel = (cxb, val, hb, col) => val > 0
    ? `<text x="${cxb.toFixed(1)}" y="${(T + ph - hb - 5).toFixed(1)}" font-size="9" font-weight="700" fill="${col}" text-anchor="start" transform="rotate(-55 ${cxb.toFixed(1)} ${(T + ph - hb - 5).toFixed(1)})">${escapeHtml(fmtCompact(val))}</text>`
    : '';
  months.forEach((mo, i) => {
    const cx = L + i * step + step / 2;
    const h0 = rev0v[i] / mx * ph, h1 = rev1v[i] / mx * ph;
    const x0 = cx - bw - gap / 2, x1 = cx + gap / 2;
    if (rev0v[i] > 0) s += `<rect x="${x0.toFixed(1)}" y="${(T + ph - h0).toFixed(1)}" width="${bw}" height="${Math.max(1, h0).toFixed(1)}" rx="2" fill="var(--rc-b0)"/>`;
    if (rev1v[i] > 0) s += `<rect x="${x1.toFixed(1)}" y="${(T + ph - h1).toFixed(1)}" width="${bw}" height="${Math.max(1, h1).toFixed(1)}" rx="2" fill="var(--accent)"/>`;
    s += vlabel(x0 + bw / 2, rev0v[i], h0, 'var(--ink-soft)');
    s += vlabel(x1 + bw / 2, rev1v[i], h1, 'var(--accent-dark)');
    const ly = T + ph + 14;
    s += `<text x="${cx.toFixed(1)}" y="${ly}" font-size="9" fill="var(--muted)" text-anchor="end" transform="rotate(-40 ${cx.toFixed(1)} ${ly})">${escapeHtml(String(mo))}</text>`;
  });
  const peak = curves.peak || {};
  const peakNote = (peak.rev0 || peak.rev1)
    ? `<div class="rc-sec" style="margin-top:2px">Peak labour: <b>${fmtInt(peak.rev0 || 0)}</b> mh/month${peak.rev0_month ? ' in ' + esc(peak.rev0_month) : ''} (Rev.00) → <b>${fmtInt(peak.rev1 || 0)}</b> mh/month${peak.rev1_month ? ' in ' + esc(peak.rev1_month) : ''} (Rev.01). Peak is man-hours per month, not headcount.</div>`
    : '';
  const monthCard = `<div class="rc-card"><h3>Labour man-hours by month <span class="rc-n">Before &amp; After — Rev.00 vs Rev.01, every bar labelled</span></h3>
    <div class="rc-sec"><b>Rev.00 (grey)</b> and <b>Rev.01 (blue)</b> labour man-hours side by side, every month, with the value on each bar. The variance is the hero above and the by-trade chart below.</div>
    ${peakNote}
    <div class="rc-chartwrap" style="overflow:visible"><svg viewBox="0 0 ${W} ${h}" class="rc-svg" style="width:100%;height:auto" role="img" aria-label="Monthly labour man-hours before and after">${s}</svg></div>
    <div class="rc-legend"><span><i style="background:var(--rc-b0)"></i>Rev.00 (before)</span><span><i style="background:var(--accent)"></i>Rev.01 (after)</span></div></div>`;

  // ── Labour man-hours by trade — diverging delta bars (the change is drawn) ──
  let tradeCard = '';
  if (mix.length) {
    const rows = mix.map(t => ({ ...t, v: (t.var != null) ? t.var : ((t.rev1 || 0) - (t.rev0 || 0)) }))
      .sort((a, b) => Math.abs(b.v) - Math.abs(a.v));
    const tmx = Math.max(1, ...rows.map(t => Math.abs(t.v)));
    const bars = rows.map(t => {
      const up = t.v > 0, w = Math.abs(t.v) / tmx * 50;
      const fill = up ? `left:50%;background:var(--rc-up)` : `right:50%;background:var(--rc-down)`;
      return `<div class="rc-trow"><div class="rc-tn">${esc(t.name)}${t.resource_id ? `<small>${esc(t.resource_id)}</small>` : ''}</div>
        <div class="rc-tbar"><span class="rc-tmid"></span><span class="rc-tfill" style="${fill};width:${w.toFixed(1)}%"></span></div>
        <div class="rc-tval ${up ? 'up' : t.v < 0 ? 'down' : 'zero'}">${t.v > 0 ? '+' : ''}${fmtInt(t.v)}</div></div>`;
    }).join('');
    tradeCard = `<div class="rc-card"><h3>Labour man-hours by trade <span class="rc-n">which trades grew or shrank (Rev.01 − Rev.00)</span></h3>
      <div class="rc-sec">One row per labour resource, biggest change first — the same P6 Resource Id you see in Primavera. The <b>change</b> is drawn; before/after are in the table below.</div>
      <div class="rc-tdiv">${bars}</div>
      <div class="rc-legend"><span><i style="background:var(--rc-up)"></i>increased</span><span><i style="background:var(--rc-down)"></i>decreased</span><span>net across all labour trades: <b>${diff > 0 ? '+' : ''}${fmtInt(diff)} mh</b></span></div>
      ${mpTradeTable(rows)}</div>`;
  }

  return secmark('9', 'Manpower', 'labour man-hours, before vs after')
    + hero + monthCard + tradeCard + (hasOther ? mpOtherResources(other) : '');
}

// ══ 10 · Scope & Structure ═════════════════════════════════════════════════════

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

  return secmark('10', 'Scope & Structure', 'WBS in Primavera colour-grouping + largest date shifts')
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
  { key: 'resource', label: 'Resources' },
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
    cal: !!(((cc.patterns || []).length) || ((cc.reassignments || []).length) || ((cc.calendars || []).length)),
    cost: !!(c.cost_available || rc.cost_available || ((rc.activity_cost_changes || []).length)
      || Object.keys(c.budget_by_dim || {}).length),
    resource: !!(rc.resource_available || ((rc.assignment_changes || []).length)),
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
