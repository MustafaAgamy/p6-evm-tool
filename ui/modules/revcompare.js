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
};
function resetFilters() {
  rcFilters.scope = { dim: null, val: 'All' };
  rcFilters.logic = { dim: null, val: 'All' };
  rcFilters.duration = { dim: null, val: 'All' };
  rcFilters.money = { dim: null, val: 'All' };
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
    const label = opts.money ? fmtMoney(v) : fmtInt(v) + (opts.suffix || '');
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
    + `<text x="${cx}" y="${cy + 13}" font-size="15" font-weight="800" fill="var(--text)" text-anchor="middle">${fmtInt(tot)}</text>`;
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
  const { dims, state: fs, valuesFor, onChange, label = 'Activity code' } = spec;
  if (!dims || !dims.length) { host.innerHTML = ''; onChange(); return; }
  const firstDim = dims[0];
  // Normalise: an absent / stale dimension resets to the first dimension's default breakdown.
  if (!fs.dim || !dims.includes(fs.dim)) { fs.dim = firstDim; fs.val = 'All'; }
  const isAll = !fs.val || fs.val === 'All';
  const groups = dims.map(d => {
    const vals = valuesFor(d) || [];
    if (!vals.length) return '';
    const opts = vals.map(v => {
      const sel = (!isAll && d === fs.dim && v === fs.val) ? ' selected' : '';
      return `<option value="${escapeHtml(String(v))}"${sel}>${esc(v)}</option>`;
    }).join('');
    return `<optgroup label="${escapeHtml(String(d))}">${opts}</optgroup>`;
  }).join('');
  host.innerHTML = `<div class="rc-fbar"><div class="rc-fld"><label>${escapeHtml(label)}</label>`
    + `<select class="rc-fsel rc-fsel-grouped">`
    + `<option value="__all"${isAll ? ' selected' : ''}>All activity codes</option>${groups}</select></div></div>`;
  const sel = host.querySelector('select');
  sel.addEventListener('change', () => {
    const opt = sel.options[sel.selectedIndex];
    if (!opt || opt.value === '__all') { fs.dim = firstDim; fs.val = 'All'; }
    else {
      const og = opt.parentElement;
      fs.dim = (og && og.label) ? og.label : firstDim;
      fs.val = opt.value;
    }
    onChange();
  });
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
function logicLane(l, idx) {
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
  const beforeLink = kind === 'added' ? linkW('no link', 'none', '⋯') : linkW(esc(l.before), '', '→');
  const afterLink = kind === 'removed' ? linkW('removed', 'rem', '✕')
    : linkW(esc(l.after), kind === 'added' ? 'add' : 'chg', '→');
  return `<div class="rc-lane">
      <div class="rc-lanehdr"><span class="rc-lanenum">#${idx}</span><span class="rc-lanetag ${tag}">${esc(l.change)}</span>${sub ? `<span class="rc-lanesub">${sub}</span>` : ''}</div>
      <div class="rc-rev2lab">Rev.00 — before</div>${chain(beforeLink)}
      <div class="rc-rev2lab r1">Rev.01 — after</div>${chain(afterLink)}
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
  host.innerHTML = `<div class="rc-lanes">${rows.map((l, i) => logicLane(l, i + 1)).join('')}</div>`;
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

function calendarView(r) {
  const cc = r.calendar_changes || {};
  const patterns = cc.patterns || [];
  const reass = cc.reassignments || [];
  let paperAccel = false;

  // One row per calendar: name · Rev.00 pattern · Rev.01 pattern · activities. The engine's
  // patterns fix the old 24-hour-calendar 0-days bug — we just render them.
  const rows = patterns.map(p => {
    const p0 = fmtPattern(p.rev0), p1 = fmtPattern(p.rev1);
    const changed = p.change && p.change !== 'unchanged';
    if (p.rev0 && p.rev1 && p.rev0.hpw != null && p.rev1.hpw != null && p.rev1.hpw > p.rev0.hpw) paperAccel = true;
    const sub = p.change === 'added' ? 'calendar added' : p.change === 'removed' ? 'calendar removed' : '';
    return `<div class="rc-calrow">
        <div class="rc-calname">${esc(p.name)}${sub ? `<span class="rc-cals">${esc(sub)}</span>` : ''}</div>
        <div>${p0 ? `<span class="rc-pattern">${escapeHtml(p0)}</span>` : '<span class="rc-mut">—</span>'}</div>
        <div>${p1 ? `<span class="rc-pattern${changed ? ' r1' : ''}">${escapeHtml(p1)}</span>` : '<span class="rc-mut">—</span>'}</div>
        <div class="rc-calact">${fmtInt(p.activities || 0)}</div>
      </div>`;
  }).join('');
  const table = patterns.length
    ? `<div class="rc-caltbl">
         <div class="rc-calrow rc-calhdr"><div>Calendar</div><div>Rev.00 pattern</div><div>Rev.01 pattern</div><div class="rc-calact">Activities</div></div>
         ${rows}</div>`
    : noData('No calendar definitions available for these revisions.');

  // Per-activity reassignment summary (kept from before — the "N activities moved A → B" signal).
  const totalReass = reass.reduce((s, g) => s + (g.count || 0), 0);
  let reassBlock = '';
  if (reass.length) {
    const items = reass.map(g => {
      if (g.from_wd != null && g.to_wd != null && g.to_wd > g.from_wd) paperAccel = true;
      const shift = (g.from_wd != null && g.to_wd != null && g.to_wd !== g.from_wd)
        ? ` <span class="rc-mut">(${g.from_wd} → ${g.to_wd} d/wk)</span>` : '';
      return `<li>${fmtInt(g.count)} activit${g.count === 1 ? 'y' : 'ies'} moved <b>${esc(g.from)} → ${esc(g.to)}</b>${shift}</li>`;
    }).join('');
    reassBlock = `<div class="rc-calreass"><div class="rc-sec" style="margin:12px 0 4px">Per-activity calendar reassignments <span class="rc-mut">(${fmtInt(totalReass)} total)</span></div><ul class="rc-callist">${items}</ul></div>`;
  }
  const callout = paperAccel
    ? '<div class="rc-callout warn">A calendar moved to a longer working week (more hours/week) — durations shorten <b>on paper</b> without changing the work. A paper acceleration to confirm (approved basis vs inadvertent reassignment).</div>'
    : '';

  const card = `<div class="rc-card"><h3>Working pattern per calendar <span class="rc-n">Rev.00 → Rev.01</span></h3>
    <div class="rc-sec">Each calendar as a plain working pattern — days/week · hours/day · hours/week — before and after. A 24-hour calendar reads 7 d/wk · 24 h/day · 168 h/wk.</div>
    ${table}${reassBlock}${callout}</div>`;
  return secmark('6', 'Calendar', 'working pattern per calendar · per-activity reassignments') + card;
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
  const W = Math.max(760, n * 60), plotL = 52, plotR = W - 30, plotT = 46, plotB = 250;
  const colW = (plotR - plotL) / n;
  const bw = Math.min(26, colW * 0.5);
  const byMonth0 = {}, byMonth1 = {};
  vm.forEach(x => { byMonth0[x.month] = x.rev0 || 0; byMonth1[x.month] = x.rev1 || 0; });
  const maxMonthly = Math.max(1, ...vm.map(x => Math.max(x.rev0 || 0, x.rev1 || 0)));
  // Cumulative lookup first — the value label must clear whichever is higher, the bar top or
  // the cumulative curve at that month, so late months (bar low, curve high) aren't clipped.
  const cumByMonth = {}; vc.forEach(x => { cumByMonth[x.month] = x; });
  const maxCum = Math.max(1, ...vc.map(x => Math.max(x.rev0 || 0, x.rev1 || 0)));
  let bars = '';
  months.forEach((m, i) => {
    const cx = plotL + (i + 0.5) * colW;
    const v1 = byMonth1[m] || 0;
    const h1 = (v1 / maxMonthly) * (plotB - plotT), y1 = plotB - h1;
    bars += `<rect x="${(cx - bw / 2).toFixed(1)}" y="${y1.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0, h1).toFixed(1)}" rx="2" fill="var(--accent)" opacity=".85"/>`;
    if (v1 > 0) {
      const cm = cumByMonth[m] || {};
      const cumMax = Math.max(cm.rev0 || 0, cm.rev1 || 0);
      const curveY = plotB - (cumMax / maxCum) * (plotB - plotT);
      const labelY = Math.min(y1, curveY) - 6;   // above the higher of (bar top, curve point)
      bars += `<text x="${cx.toFixed(1)}" y="${labelY.toFixed(1)}" font-size="9" font-weight="700" fill="var(--ink-soft)" text-anchor="middle">${escapeHtml(fmtMoney(v1))}</text>`;
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
    const tx = Math.min(endX + 6, W - 4);
    const anchor = endX + 90 > W ? 'end' : 'start';
    finishLabel = `<circle cx="${endX.toFixed(1)}" cy="${endY.toFixed(1)}" r="3.2" fill="var(--accent-dark)"/>`
      + `<text x="${(anchor === 'end' ? endX - 6 : tx).toFixed(1)}" y="${(endY - 7).toFixed(1)}" font-size="10" font-weight="800" fill="var(--accent-dark)" text-anchor="${anchor}">${esc(rev1finish)}</text>`
      + `<text x="${(anchor === 'end' ? endX - 6 : tx).toFixed(1)}" y="${(endY + 5).toFixed(1)}" font-size="8" fill="var(--muted)" text-anchor="${anchor}">Rev.01 finish</text>`;
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
        <div class="rc-legend"><span><i style="background:var(--accent)"></i>Rev.01 value/mo</span><span><i class="rc-line" style="background:var(--muted)"></i>Rev.00 cumulative</span><span><i class="rc-line" style="background:var(--accent-dark)"></i>Rev.01 cumulative</span></div>
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
  const costRows = costChanges.slice(0, 40).map(c => {
    const id = pick(c, ['code', 'activity_id', 'id']), name = pick(c, ['name', 'activity_name']);
    const before = pick(c, ['rev0']), after = pick(c, ['rev1']), delta = c.delta;
    const isNew = before == null || before === '—';
    let varCell;
    if (typeof delta === 'number') {
      varCell = `<span class="rc-d ${delta > 0 ? 'up' : delta < 0 ? 'down' : 'zero'}">${delta > 0 ? '+' : ''}${fmtNum(delta)}</span>`;
    } else if (delta != null && delta !== '') {
      varCell = `<span class="rc-d">${esc(delta)}</span>`;
    } else {
      varCell = '—';
    }
    return `<tr><td class="rc-aid">${esc(id)}</td><td>${esc(name)}${isNew ? '<span class="rc-tag add" style="margin-left:6px">NEW</span>' : ''}</td>
      <td class="n rc-mut">${before != null ? esc(before) : '—'}</td><td class="n rc-new">${after != null ? esc(after) : '—'}</td>
      <td class="n">${varCell}</td></tr>`;
  }).join('');
  const costTblCard = hasCostTbl
    ? `<div class="rc-card"><h3>Cost changed <span class="rc-n">activity-level · budget total cost · variance</span></h3>
        ${costRows ? `<div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Activity ID</th><th>Activity Name</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr></thead><tbody>${costRows}</tbody></table></div>` : noData('No activity-level cost changes.')}</div>`
    : '';

  return secmark('7', 'Cost & Resources', 'planned value, where the money moved, cost changes')
    + scurve + moneyCard + costTblCard;
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
    increased: ['chg', 'Increased'], decreased: ['chg', 'Decreased'],
    unchanged: ['', 'Unchanged'],
  };
  return map[k] || ['chg', String(kind || 'Changed')];
}

function resourceView(r) {
  const rc = r.resource_changes || {};
  const curves = r.curves || {};
  const byTrade = curves.manhours_by_trade || [];
  const assign = rc.assignment_changes || [];
  const hasResTbl = !!(rc.resource_available || byTrade.length || assign.length);
  if (!hasResTbl) {
    return secmark('8', 'Resources', 'resource-by-resource comparison')
      + `<div class="rc-card"><h3>Resources <span class="rc-n">optional</span></h3>${noData('Neither revision carries resource assignments — this section is reported as not applicable rather than "no change".')}</div>`;
  }
  const pick = (row, keys) => { for (const k of keys) { if (row[k] != null && row[k] !== '') return row[k]; } return null; };

  // "Assigned to" — distinct activities per resource, grouped from the assignment changes.
  const assignedBy = {};
  assign.forEach(a => {
    const key = a.resource || a.resource_name || a.resource_id;
    if (key == null || key === '') return;
    if (!assignedBy[key]) assignedBy[key] = new Set();
    const act = pick(a, ['code', 'activity_id', 'id', 'name']);
    if (act != null && act !== '') assignedBy[key].add(String(act));
  });

  // Lead card — resource-by-resource man-hour comparison.
  const byRows = byTrade.map(t => {
    const name = t.name || t.trade || t.resource || t.resource_id || '—';
    const b = t.rev0, a = t.rev1;
    const v = (t.var != null) ? t.var : ((Number(a) || 0) - (Number(b) || 0));
    const [kTag, kLabel] = resourceKindMeta(t.kind, b, a);
    const key = t.name || t.resource || t.resource_id;
    const cnt = (key != null && assignedBy[key]) ? assignedBy[key].size : 0;
    const vNum = typeof v === 'number' ? v : Number(v);
    return `<tr><td>${esc(name)}${t.resource_id ? ` <span class="rc-mut">${esc(t.resource_id)}</span>` : ''}</td>
      <td class="n rc-mut">${b != null ? fmtInt(b) : '—'}</td>
      <td class="n rc-new">${a != null ? fmtInt(a) : '—'}</td>
      <td class="n">${isFinite(vNum) ? `<span class="rc-d ${vNum > 0 ? 'up' : vNum < 0 ? 'down' : 'zero'}">${vNum > 0 ? '+' : ''}${fmtInt(vNum)}</span>` : '—'}</td>
      <td>${typeTag(kTag, kLabel)}</td>
      <td class="rc-mut">${cnt ? `${fmtInt(cnt)} activit${cnt === 1 ? 'y' : 'ies'}` : '—'}</td></tr>`;
  }).join('');
  const byCard = `<div class="rc-card"><h3>Resource comparison <span class="rc-n">man-hours by resource · Rev.00 → Rev.01</span></h3>
      <div class="rc-sec">One row per resource / trade — planned man-hours before and after, the variance, a neutral change tag, and how many activities it is assigned to</div>
      ${byRows ? `<div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Resource</th><th class="n">Before (mh)</th><th class="n">After (mh)</th><th class="n">Variance</th><th>Change</th><th>Assigned to</th></tr></thead><tbody>${byRows}</tbody></table></div>` : noData('No resource man-hour totals available to compare.')}</div>`;

  // Supporting detail — the raw per-activity assignment changes (kept below the lead card).
  const resRows = assign.map(a => {
    const id = pick(a, ['activity_id', 'code', 'id']), name = pick(a, ['activity_name', 'name']);
    const [kTag, kLabel] = resourceKindMeta(a.kind, a.rev0, a.rev1);
    return `<tr><td class="rc-aid">${esc(id)}</td><td>${esc(name)}</td>
      <td class="rc-aid">${esc(a.resource_id)}</td><td>${esc(a.resource || a.resource_name)}</td>
      <td class="n rc-mut">${esc(a.rev0)}</td><td class="n rc-new">${esc(a.rev1)}</td><td>${typeTag(kTag, kLabel)}</td></tr>`;
  }).join('');
  const detailCard = assign.length
    ? `<div class="rc-card"><h3>Assignment detail <span class="rc-n">per-activity assignment before / after</span></h3>
        <div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Activity ID</th><th>Activity Name</th><th>Resource ID</th><th>Resource Name</th><th class="n">Before</th><th class="n">After</th><th>Change</th></tr></thead><tbody>${resRows}</tbody></table></div></div>`
    : '';

  return secmark('8', 'Resources', 'resource-by-resource comparison') + byCard + detailCard;
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

function wireCost(body) {
  const host = body.querySelector('#rc-money-filter');
  if (!host) return;
  const r = state.revcompareReport || {};
  const dims = moneyDims(r.curves || {});
  if (!dims.length) return;
  groupedFilterControl(host, {
    dims,
    state: rcFilters.money,
    valuesFor: (dim) => moneyValues(r.curves || {}, dim),
    onChange: () => renderMoneyChart(body),
  });
}

// ══ 9 · Manpower (comment 11 — combo: stacked-by-trade histogram + total line) ══

function manpowerView(r) {
  const curves = r.curves || {};
  const trades = curves.manpower_by_trade || [];
  const months = curves.months || [];
  if (!curves.resource_available || !trades.length || !months.length) {
    return secmark('9', 'Manpower', 'monthly man-hours, stacked by trade')
      + `<div class="rc-card"><h3>Manpower histogram</h3>${noData('Neither revision carries resource (man-hour) loading — manpower histogram not applicable.')}</div>`;
  }
  // Monthly totals across all trades.
  const total = months.map((_, i) => trades.reduce((s, t) => s + ((t.monthly || [])[i] || 0), 0));
  const n = months.length;
  const W = Math.max(760, n * 68), h = 304, L = 48, B = 56, T = 32;
  const pw = W - L - 16, ph = h - T - B, step = pw / n, bw = Math.min(40, step * 0.62);
  const mx = Math.max(1, ...total);
  const showEvery = n > 10 ? 2 : 1;
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
    // Month labels angled (~-40°) and thinned (every 2nd when crowded); last always kept.
    if (i % showEvery === 0 || i === n - 1) {
      const ly = T + ph + 13;
      s += `<text x="${x.toFixed(1)}" y="${ly.toFixed(1)}" font-size="9" fill="var(--muted)" text-anchor="end" transform="rotate(-40 ${x.toFixed(1)} ${ly.toFixed(1)})">${escapeHtml(String(mo))}</text>`;
    }
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
  return secmark('9', 'Manpower', 'monthly man-hours, stacked by trade') + card;
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
