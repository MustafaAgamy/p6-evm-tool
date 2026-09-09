// Baseline Revision Comparison — compare two approved baseline revisions (Rev.00 vs
// Rev.01) from a planning/consultant perspective. Workflow: assign both revisions →
// Run Comparison → review results across six sub-tabs (Executive Summary · Key Findings ·
// Critical Path & Float · Change Register · Cost & Resources · Scope & Structure).
// Neutral by design: Change detected → Potential impact → Planning review, never an
// automatic verdict. Nothing runs until Run is pressed.

import { state } from './state.js';
import { showError, clearError } from './render.js';
import { escapeHtml } from './format.js';
import { getSavedMode } from './appearance.js';
import { showReportPreview } from './preview.js';
import { revealAndRun } from './featurereveal.js';
import { exportRevcompareExcel } from './api.js';

const RC_TABS = [
  ['summary', 'Executive Summary'], ['findings', 'Key Findings'],
  ['critical', 'Critical Path & Float'], ['register', 'Change Register'],
  ['cost', 'Cost & Resources'], ['scope', 'Scope & Structure'],
];

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
    register: registerView, cost: costView, scope: scopeView,
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
    state.revcompareReport = null; renderInputs(body);
  });
  body.querySelector('#rc-preview-pdf').addEventListener('click', openRevcompareReport);
  body.querySelector('#rc-export-xlsx').addEventListener('click', exportRevcompareExcel);
  if (tab === 'summary') wireSummary(body);
  else if (tab === 'findings') wireFindings(body);
  else if (tab === 'register') wireRegister(body);
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
function sevPill(sev) {
  const label = { crit: 'Critical', hi: 'High', med: 'Review', low: 'Info' }[sev] || sev;
  return `<span class="rc-sev ${sev}">${escapeHtml(String(label))}</span>`;
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
function fmt(n) {
  if (n == null || (typeof n === 'number' && !isFinite(n))) return '—';
  const v = Number(n);
  if (isNaN(v)) return escapeHtml(String(n));
  return v.toLocaleString();
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

  const snap = `
    <div class="rc-card"><h3>Revision snapshot <span class="rc-n">Rev.00 → Rev.01</span></h3>
      <div class="rc-snap">
        <div class="rc-snapcol r0"><div class="rc-snaptag">Rev.00 · Original</div><div class="rc-snapfile">${esc(rev0.file)}</div>
          ${kv('Data date', rev0.data_date)}${kv('Governing finish', rev0.finish)}${kv('Activities', rev0.activities != null ? fmt(rev0.activities) : null)}</div>
        <div class="rc-snapmid"><div class="rc-big">${slipWd != null ? num(slipWd, true) + 'd' : '—'}</div><div class="rc-biglbl">Finish slip</div></div>
        <div class="rc-snapcol r1"><div class="rc-snaptag">Rev.01 · Revised</div><div class="rc-snapfile">${esc(rev1.file)}</div>
          ${kv('Data date', rev1.data_date)}${kv('Governing finish', rev1.finish, slipWd > 0)}${kv('Activities', rev1.activities != null ? fmt(rev1.activities) : null)}</div>
      </div></div>`;

  // Comparison ledger
  const ledgerRows = (r.ledger || []).map(l => `
    <tr><td>${esc(l.label)}</td>
      <td class="n rc-mut">${l.rev0 != null ? esc(l.rev0) : '—'}</td>
      <td class="n rc-new">${l.rev1 != null ? esc(l.rev1) : '—'}</td>
      <td class="n">${deltaCell(l.delta)}</td></tr>`).join('');
  const ledgerCard = `<div class="rc-card"><h3>Comparison ledger</h3>
    ${ledgerRows ? `<table class="rc-t"><thead><tr><th>Measure</th><th class="n">Rev.00</th><th class="n">Rev.01</th><th class="n">Change</th></tr></thead><tbody>${ledgerRows}</tbody></table>`
                 : noData('No comparison measures available.')}</div>`;

  // Credibility / red flags
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
    credRow('Constraints (hard)', q.hard_constraints),
    credRow('Leads (negative lags)', q.leads),
    calRow,
  ].filter(Boolean).join('');
  const credCard = `<div class="rc-card rc-flag"><h3 class="rc-flagh">Schedule-quality signals <span class="rc-n">signals to review</span></h3>
    ${credRows ? `<table class="rc-t"><thead><tr><th>Signal</th><th class="n">Rev.00</th><th class="n">Rev.01</th><th class="n">Δ</th></tr></thead><tbody>${credRows}</tbody></table>`
               : noData('No schedule-quality signals available.')}</div>`;

  return secmark('1', 'Executive Summary') + bl + snap
    + `<div class="rc-split">${ledgerCard}${credCard}</div>`
    + scopeByCode(r.codes);
}

function scopeByCode(codes) {
  if (!codes) return `<div class="rc-card"><h3>Scope change <span class="rc-n">added &amp; removed, by activity code</span></h3>${noData('No activity-code scope breakdown available.')}</div>`;
  const dims = codes.dimensions || [];
  const sbc = codes.scope_by_code || {};
  const dimKeys = dims.filter(d => Array.isArray(sbc[d]) && sbc[d].length);
  const added = codes.added || [], removed = codes.removed || [];

  const barsFor = (dim) => {
    const arr = sbc[dim] || [];
    if (!arr.length) return noData('No scope changes for this code dimension.');
    const maxTot = Math.max(1, ...arr.map(x => (x.added || 0) + (x.removed || 0)));
    return arr.map(x => {
      const aw = Math.round((x.added || 0) / maxTot * 100);
      const rw = Math.round((x.removed || 0) / maxTot * 100);
      return `<div class="rc-sbar"><div class="rc-sbl">${esc(x.category)}</div>
        <div class="rc-track"><div class="rc-fa" style="width:${aw}%"></div><div class="rc-fr" style="width:${rw}%"></div></div>
        <div class="rc-sbv">${x.added || 0} / ${x.removed || 0}</div></div>`;
    }).join('');
  };

  const chips = dimKeys.map((d, i) => `<button class="rc-fchip ${i === 0 ? 'on' : ''}" data-scopedim="${escapeHtml(d)}">${escapeHtml(d)}</button>`).join('');
  const barGroups = dimKeys.map((d, i) => `<div class="rc-sbars" data-scopedimbars="${escapeHtml(d)}" ${i === 0 ? '' : 'hidden'}>${barsFor(d)}</div>`).join('');

  const itemRow = (x, label, cls) => `<tr>
      <td class="rc-aid">${esc(x.id)}</td><td>${esc(x.name)}</td>
      <td><span class="rc-tag ${cls}">${label}</span></td>
      <td class="rc-mut">${esc(x.building)}</td><td class="rc-mut">${esc(x.wbs)}</td>
      <td>${x.scope ? `<span class="rc-tag">${esc(x.scope)}</span>` : '—'}</td></tr>`;
  const CAP = 60;
  const invRows = [
    ...added.slice(0, CAP).map(x => itemRow(x, 'Added', 'add')),
    ...removed.slice(0, CAP).map(x => itemRow(x, 'Removed', 'rem')),
  ].join('');
  const overflow = (added.length > CAP || removed.length > CAP)
    ? `<tr><td colspan="6" class="rc-mut">… full itemised list in the report</td></tr>` : '';
  const invTable = (added.length || removed.length)
    ? `<div class="rc-tblscroll" style="margin-top:10px"><table class="rc-t">
        <thead><tr><th>Activity ID</th><th>Activity Name</th><th>Change</th><th>Building</th><th>WBS (under)</th><th>Scope</th></tr></thead>
        <tbody>${invRows}${overflow}</tbody></table></div>`
    : noData('No added or removed activities to itemise.');

  const bars = dimKeys.length
    ? `<div class="rc-filters" style="margin-bottom:10px">${chips}</div>${barGroups}
       <div class="rc-legend"><span><i style="background:var(--success)"></i>Added (${added.length})</span><span><i style="background:var(--danger)"></i>Removed (${removed.length})</span></div>`
    : noData('No activity-code dimensions available for a scope breakdown.');

  return `<div class="rc-card"><h3>Scope change <span class="rc-n">added &amp; removed, by activity code</span></h3>
    ${bars}${invTable}</div>`;
}

function wireSummary(body) {
  const chips = [...body.querySelectorAll('[data-scopedim]')];
  chips.forEach(chip => chip.addEventListener('click', () => {
    chips.forEach(c => c.classList.toggle('on', c === chip));
    const dim = chip.dataset.scopedim;
    body.querySelectorAll('[data-scopedimbars]').forEach(g => { g.hidden = (g.dataset.scopedimbars !== dim); });
  }));
}

// ══ 2 · Key Findings ═════════════════════════════════════════════════════════

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
  const palette = ['--chart-3', '--warning', '--chart-1', '--chart-4', '--chart-5', '--chart-2', '--chart-6'];
  const xc = (i) => leftPad + (i + 1) * colStep;

  let cum = 0, bars = '', conns = '', labels = '';
  cs.forEach((c, i) => {
    const before = cum; cum += (c.wd || 0); const after = cum;
    const hiV = Math.max(before, after), loV = Math.min(before, after);
    const y = base - hiV * scale, h = Math.max(1, (hiV - loV) * scale);
    const cx = xc(i), col = `var(${palette[i % palette.length]})`;
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
  labels += `<text x="${tx.toFixed(1)}" y="${(base + 18).toFixed(1)}" font-size="9" fill="var(--ink-soft)" text-anchor="middle" font-weight="700">${esc(slip.rev1_finish)}</text>`;

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
  const slipCard = `<div class="rc-card"><h3>What drove the slip <span class="rc-n">finish-slip bridge · neutral attribution</span></h3>
    <div class="rc-sec">Each contribution attributes part of the finish movement along the driving path</div>
    <div class="rc-chartwrap">${slipWaterfall(r.slip)}</div>
    <div class="rc-callout">Each contribution links back to the change that caused it. Neutral: this attributes the slip, it does not judge the revision.</div></div>`;

  // Sequence roll-up — grouped, expandable chains
  const groups = r.sequence_rollup || [];
  let idx = 0;
  const seqInner = groups.map(g => {
    const items = (g.items || []).map(it => {
      const i = idx++;
      const chain = (nodes) => (nodes && nodes.length)
        ? nodes.map(nm => `<span class="rc-node">${esc(nm)}</span>`).join('<span class="rc-arw">→</span>')
        : '<span class="rc-mut">—</span>';
      return `<div class="rc-seqitem" data-seq="${i}"><span class="rc-seqexp">▸</span>
          <span>${esc(it.a_name)}${it.b_name ? ` vs ${esc(it.b_name)}` : ''}</span>
          ${it.direction ? `<span class="rc-dirtag">${esc(it.direction)}</span>` : ''}</div>
        <div class="rc-seqbody hidden" id="rc-seq-${i}">
          <div class="rc-cklab">Rev.00 order</div><div class="rc-chain">${chain(it.chain0)}</div>
          <div class="rc-cklab r1">Rev.01 order</div><div class="rc-chain">${chain(it.chain1)}</div>
        </div>`;
    }).join('');
    return `<div class="rc-grouplab">${esc(g.group)}${g.count != null ? ` — ${g.count} activities` : ''}</div>${items}`;
  }).join('');
  const seqCard = `<div class="rc-card"><h3>Re-sequenced activities <span class="rc-n">grouped by WBS / zone</span></h3>
    ${groups.length ? seqInner : noData('No execution-order changes detected from the logic.')}</div>`;

  // Findings list
  const findings = (r.findings || []).map(f => `
    <div class="rc-finding"><div class="rc-fsev ${escapeHtml(String(f.severity || 'med'))}"></div>
      <div><div class="rc-ftitle">${esc(f.title)} ${typeTag(f.change_type, f.type_label)} ${sevPill(f.severity)}</div>
        <div class="rc-fbody">${esc(f.body)}</div>
        <div class="rc-flow"><span class="rc-fk det">Change detected</span><span class="rc-arw">→</span><span class="rc-fk imp">${esc(f.flow_impact || 'Potential schedule impact')}</span><span class="rc-arw">→</span><span class="rc-fk rev">Planning review</span></div>
      </div></div>`).join('');
  const findCard = `<div class="rc-card"><h3>Key findings <span class="rc-n">ranked · for planning review</span></h3>
    <div class="rc-sec">The differences most likely to affect the execution strategy — each is an observation, not a verdict</div>
    ${findings || noData('No material findings detected between the two revisions.')}</div>`;

  return secmark('2', 'Key Findings') + slipCard + seqCard + findCard;
}

function wireFindings(body) {
  body.querySelectorAll('.rc-seqitem').forEach(it => it.addEventListener('click', () => {
    const b = document.getElementById(`rc-seq-${it.dataset.seq}`);
    if (!b) return;
    it.classList.toggle('open');
    b.classList.toggle('hidden');
  }));
}

// ══ 3 · Critical Path & Float ══════════════════════════════════════════════════

function cpNode(n) {
  const cls = n.state === 'enter' ? 'enter' : n.state === 'leave' ? 'leave' : (n.tf != null && n.tf <= 0 ? 'crit' : '');
  const code = n.code ? `<span class="rc-nf">${esc(n.code)}</span>` : '';
  return `<div class="rc-node ${cls}">${esc(n.name)}${code}</div>`;
}
function cpChain(nodes) {
  if (!nodes || !nodes.length) return '<div class="rc-mut">No driving path available for this revision.</div>';
  return nodes.map(cpNode).join('<span class="rc-lnk"><span class="rc-lt">FS</span>→</span>');
}

function criticalView(r) {
  const cp = r.critical_path || {};
  const entered = cp.entered || [], left = cp.left || [];
  const cpCard = `<div class="rc-card"><h3>Driving chain <span class="rc-n">Rev.00 vs Rev.01 · longest path</span></h3>
    <div class="rc-sec">${cp.length_change_wd != null ? `Rev.01 critical path is ${num(cp.length_change_wd, true)} working days ${cp.length_change_wd >= 0 ? 'longer' : 'shorter'}` : 'Driving chain to the governing finish milestone'}</div>
    <div class="rc-chainrow"><div class="rc-clab r0"><div class="rc-ck">Rev.00</div><div class="rc-cv">ends ${esc(r.rev0 && r.rev0.finish)}</div></div>
      <div class="rc-chainwrap"><div class="rc-chain">${cpChain(cp.rev0)}</div></div></div>
    <div class="rc-chainrow"><div class="rc-clab r1"><div class="rc-ck">Rev.01</div><div class="rc-cv">ends ${esc(r.rev1 && r.rev1.finish)}</div></div>
      <div class="rc-chainwrap"><div class="rc-chain">${cpChain(cp.rev1)}</div></div></div>
    <div class="rc-leg">
      <span><span class="rc-ld enter"></span>Entered critical path (${entered.length})</span>
      <span><span class="rc-ld leave"></span>Left critical path (${left.length})</span>
      <span><span class="rc-ld crit"></span>Critical in both</span>
      ${entered.length ? `<span class="rc-mut">Entering: ${entered.slice(0, 4).map(e => esc(e.name)).join(', ')}${entered.length > 4 ? '…' : ''}</span>` : ''}
      ${left.length ? `<span class="rc-mut">Leaving: ${left.slice(0, 4).map(e => esc(e.name)).join(', ')}${left.length > 4 ? '…' : ''}</span>` : ''}
    </div></div>`;

  // Float-band bars
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

  // Negative-float register
  const nf = q.negative_float || {};
  const reg = nf.register || [];
  const nfRows = reg.map(a => `<tr><td class="rc-aid">${esc(a.id)}</td><td>${esc(a.name)}</td>
      <td class="n">${a.tf != null ? `<span class="rc-d up">${a.tf} d</span>` : '—'}</td><td class="rc-mut">${esc(a.wbs)}</td></tr>`).join('');
  const nfCard = `<div class="rc-card rc-flag"><h3 class="rc-flagh">Negative-float register <span class="rc-n">${reg.length} activities</span></h3>
    ${reg.length ? `<div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Activity ID</th><th>Activity Name</th><th class="n">Total Float</th><th>WBS</th></tr></thead><tbody>${nfRows}</tbody></table></div>`
                 : noData('No activities carry negative float in Rev.01.')}</div>`;

  return secmark('3', 'Critical Path & Float') + cpCard + `<div class="rc-split">${bandCard}${nfCard}</div>`;
}

// ══ 4 · Change Register ════════════════════════════════════════════════════════

export const REG_BUCKET = {
  added: 'scope', removed: 'scope', renamed: 'scope', idchange: 'identity',
  moved_wbs: 'wbs', wbs_add: 'wbs', wbs_remove: 'wbs', wbs_rename: 'wbs',
};
export function bucketOf(t) { return REG_BUCKET[t] || t; }

// Render an ID + Name pair from a row that may name its fields differently.
function idName(row, idKeys, nameKeys) {
  const pick = (keys) => { for (const k of keys) { if (row[k] != null && row[k] !== '') return row[k]; } return null; };
  return { id: pick(idKeys), name: pick(nameKeys) };
}

function registerView(r) {
  // Code filter bar — lists the activity-code dimensions present (added/removed are
  // inventoried in the Executive Summary, not repeated here).
  const dims = (r.codes && r.codes.dimensions) || [];
  const dimChips = dims.length
    ? dims.map(d => `<span class="rc-codechip">${escapeHtml(d)}</span>`).join('')
    : '<span class="rc-mut">no activity-code dimensions</span>';
  const filterBar = `<div class="rc-card rc-filterbar"><div class="rc-filterrow"><b>Activity-code dimensions:</b> ${dimChips}
    <span class="rc-foot" style="margin-left:auto">Added &amp; removed activities are inventoried in the Executive Summary.</span></div></div>`;

  return secmark('4', 'Change Register', 'one table per change type · separate ID / Name columns · Before → After → Variance')
    + filterBar
    + regDuration(r) + regMilestone(r) + regLogic(r)
    + regConstraint(r) + regCalendar(r) + regResource(r) + regCost(r);
}

function regTableCard(title, note, head, rows, foot) {
  return `<div class="rc-card"><h3>${title}</h3>${note ? `<div class="rc-sec">${note}</div>` : ''}
    ${rows ? `<div class="rc-tblscroll"><table class="rc-t"><thead>${head}</thead><tbody>${rows}</tbody></table></div>` : noData('No changes of this type.')}
    ${foot && rows ? `<div class="rc-foot">${foot}</div>` : ''}</div>`;
}

function regDuration(r) {
  const rows = (r.duration_table || []).map(d => {
    const flag = d.calendar_flag;
    const cal = (d.calendar_before && d.calendar_after && d.calendar_before !== d.calendar_after)
      ? `<span class="rc-tag chg">${esc(d.calendar_before)} → ${esc(d.calendar_after)}</span>`
      : `<span class="rc-mut">${esc(d.calendar_after || d.calendar_before)}</span>`;
    return `<tr><td class="rc-aid">${esc(d.id)}</td><td>${esc(d.name)}</td>
      <td class="n">${d.before != null ? esc(d.before) + (typeof d.before === 'number' ? ' d' : '') : '—'}</td>
      <td class="n rc-new">${d.after != null ? esc(d.after) + (typeof d.after === 'number' ? ' d' : '') : '—'}</td>
      <td class="n">${deltaCell(typeof d.variance === 'number' ? d.variance : (d.variance ?? null))}</td>
      <td>${cal}${flag ? ' <span class="rc-sev hi">calendar</span>' : ''}</td>
      <td class="n">${d.tf_after != null ? esc(d.tf_after) + ' d' : '—'}</td></tr>`;
  }).join('');
  const anyFlag = (r.duration_table || []).some(d => d.calendar_flag);
  return regTableCard('Duration changed <span class="rc-n">working days · + calendar &amp; float context</span>', '',
    '<tr><th>Activity ID</th><th>Activity Name</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th><th>Calendar</th><th class="n">TF After</th></tr>',
    rows, anyFlag ? 'A calendar change (e.g. 5→6-day week) shortens durations on paper without changing the work — flagged, not judged.' : '');
}

function regMilestone(r) {
  const rows = (r.milestones || []).filter(m => m.kind !== 'unchanged').map(m => {
    const { id, name } = idName(m, ['id', 'activity_id', 'code'], ['name', 'activity_name']);
    const varCell = m.change_days != null
      ? deltaCell(`${m.change_days > 0 ? '+' : ''}${m.change_days} d`)
      : (m.kind === 'new' ? '<span class="rc-tag add">Added</span>' : m.kind === 'removed' ? '<span class="rc-tag rem">Removed</span>' : '—');
    const type = m.type || m.constraint || (m.hard ? 'Contract' : '');
    return `<tr><td class="rc-aid">${esc(id)}</td><td>${esc(name)}</td>
      <td>${type ? `<span class="rc-tag ${m.hard ? 'hard' : ''}">${esc(type)}</span>` : '<span class="rc-mut">—</span>'}</td>
      <td class="n rc-mut">${esc(m.rev0)}</td><td class="n rc-new">${esc(m.rev1)}</td><td class="n">${varCell}</td></tr>`;
  }).join('');
  return regTableCard('Milestone changed', '',
    '<tr><th>Activity ID</th><th>Activity Name</th><th>Type</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr>',
    rows, '');
}

function regLogic(r) {
  const rows = (r.logic_register || []).map(l => {
    const changeTag = { 'Type changed': 'chg', 'Lag changed': 'chg', 'Link added': 'add', 'Link removed': 'rem' }[l.change] || 'chg';
    return `<tr>
      <td class="rc-aid">${esc(l.pred_id)}</td><td class="rc-cellsep">${esc(l.pred_name)}</td>
      <td class="rc-aid">${esc(l.succ_id)}</td><td class="rc-cellsep">${esc(l.succ_name)}</td>
      <td class="${/no link/i.test(String(l.before)) ? 'rc-mut' : ''}">${esc(l.before)}</td>
      <td class="${/no link|removed/i.test(String(l.after)) ? 'rc-mut' : 'rc-new'}">${esc(l.after)}</td>
      <td><span class="rc-tag ${changeTag}">${esc(l.change)}</span>${l.is_lead ? ' <span class="rc-sev crit">lead</span>' : ''}</td>
      <td class="n">${l.on_cp ? '<span class="rc-d up">Yes</span>' : '<span class="rc-mut">No</span>'}</td></tr>`;
  }).join('');
  const head = `<tr><th colspan="2" class="rc-grouphd">Predecessor (drives)</th><th colspan="2" class="rc-grouphd">Successor (driven)</th><th>Link Before</th><th>Link After</th><th>Change</th><th class="n">On CP?</th></tr>
    <tr><th>ID</th><th>Name</th><th>ID</th><th>Name</th><th></th><th></th><th></th><th></th></tr>`;
  return regTableCard('Logic / relationship changed <span class="rc-n">each row is one link — predecessor drives successor</span>', '',
    head, rows, '“On CP?” triages the logic changes to the few that moved the finish; new leads (negative lags) are flagged.');
}

function regConstraint(r) {
  const rows = (r.constraint_changes || []).map(c => {
    const { id, name } = idName(c, ['activity_id', 'id', 'code'], ['name', 'activity_name']);
    const kindLabel = { added: 'Added', removed: 'Removed', type: 'Type changed', date: 'Date changed' }[c.kind] || c.kind || 'Changed';
    const kindTag = { added: 'add', removed: 'rem', type: 'chg', date: 'chg' }[c.kind] || 'chg';
    return `<tr><td class="rc-aid">${esc(id)}</td><td>${esc(name)}</td><td class="rc-mut">${esc(c.wbs)}</td>
      <td class="rc-mut">${esc(c.rev0)}</td><td class="rc-new">${esc(c.rev1)}</td>
      <td><span class="rc-tag ${kindTag}">${escapeHtml(String(kindLabel))}</span>${c.hard ? ' <span class="rc-tag hard">Hard</span>' : ''}${c.on_cp ? ' <span class="rc-sev crit">on CP</span>' : ''}</td></tr>`;
  }).join('');
  return regTableCard('Constraint changed <span class="rc-n">a hidden lever on the finish date</span>', '',
    '<tr><th>Activity ID</th><th>Activity Name</th><th>WBS</th><th>Constraint Before</th><th>Constraint After</th><th>Change</th></tr>',
    rows, 'A hard constraint on the driving path can pin or move the finish independently of logic. Surfaced for review.');
}

function regCalendar(r) {
  const cc = r.calendar_changes || {};
  const reassign = (cc.reassignments || []).map(g => `<tr><td class="rc-mut">${esc(g.from)}</td><td class="rc-new">${esc(g.to)}</td>
      <td class="n">${g.from_wd != null && g.to_wd != null ? `${g.from_wd}-day → ${g.to_wd}-day` : '—'}</td><td class="n">${esc(g.count)}</td></tr>`).join('');
  const defs = (cc.calendars || []).map(c => `<tr><td>${esc(c.name)}</td><td class="n rc-mut" colspan="2">${esc(c.detail)}</td>
      <td>${typeTag(c.change === 'added' ? 'add' : c.change === 'removed' ? 'rem' : 'chg', c.change)}</td></tr>`).join('');
  const left = reassign
    ? `<div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Calendar From</th><th>Calendar To</th><th class="n">Workweek</th><th class="n">Activities</th></tr></thead><tbody>${reassign}</tbody></table></div>`
    : noData('No per-activity calendar reassignments.');
  const right = defs
    ? `<div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Calendar</th><th class="n" colspan="2">Definition change</th><th>Change</th></tr></thead><tbody>${defs}</tbody></table></div>`
    : noData('No calendar-definition changes.');
  const hasAny = reassign || defs;
  return `<div class="rc-card"><h3>Calendar changed <span class="rc-n">reassignments &amp; definition changes</span></h3>
    ${hasAny ? `<div class="rc-split">${left}${right}</div>
      <div class="rc-callout warn">A 5→6-day week or an hours/day change shortens durations on paper without changing the work — confirm the basis (approved acceleration vs inadvertent reassignment).</div>`
             : noData('No calendar assignment or definition changes.')}</div>`;
}

function regResource(r) {
  const rc = r.resource_changes || {};
  if (!rc.resource_available && !(rc.assignment_changes && rc.assignment_changes.length)) {
    return `<div class="rc-card"><h3>Resource changed <span class="rc-n">assignment before / after</span></h3>${noData('Neither revision carries resource loading — reported as not applicable rather than "no change".')}</div>`;
  }
  const rows = (rc.assignment_changes || []).map(a => {
    const { id, name } = idName(a, ['activity_id', 'code', 'id'], ['activity_name', 'name']);
    const kindLabel = { added: 'Added', removed: 'Removed', units: 'Units', rate: 'Rate' }[a.kind] || a.kind || 'Changed';
    const kindTag = { added: 'add', removed: 'rem' }[a.kind] || 'chg';
    return `<tr><td class="rc-aid">${esc(id)}</td><td>${esc(name)}</td>
      <td class="rc-aid">${esc(a.resource_id)}</td><td>${esc(a.resource || a.resource_name)}</td>
      <td class="n rc-mut">${esc(a.rev0)}</td><td class="n rc-new">${esc(a.rev1)}</td>
      <td>${typeTag(kindTag, kindLabel)}</td></tr>`;
  }).join('');
  return regTableCard('Resource changed <span class="rc-n">assignment before / after · one line per swap</span>', '',
    '<tr><th>Activity ID</th><th>Activity Name</th><th>Resource ID</th><th>Resource Name</th><th class="n">Before</th><th class="n">After</th><th>Change</th></tr>',
    rows, '');
}

function regCost(r) {
  const rc = r.resource_changes || {};
  const curves = r.curves || {};
  const costChanges = rc.activity_cost_changes || [];
  if (!rc.cost_available && !costChanges.length) {
    return `<div class="rc-card"><h3>Cost changed <span class="rc-n">budget total cost · variance</span></h3>${noData('Neither revision carries cost loading — reported as not applicable rather than "no change".')}</div>`;
  }
  const pct = (b, a) => {
    if (b == null || a == null || !isFinite(b) || b === 0) return '—';
    return `${((a - b) / Math.abs(b) * 100 >= 0 ? '+' : '')}${Math.round((a - b) / Math.abs(b) * 100)}%`;
  };
  const rows = costChanges.slice(0, 40).map(c => {
    const { id, name } = idName(c, ['code', 'activity_id', 'id'], ['name', 'activity_name']);
    const b = typeof c.rev0 === 'number' ? c.rev0 : null, a = typeof c.rev1 === 'number' ? c.rev1 : null;
    return `<tr><td class="rc-aid">${esc(id)}</td><td>${esc(name)}</td>
      <td class="n rc-mut">${b != null ? fmt(b) : esc(c.rev0)}</td><td class="n rc-new">${a != null ? fmt(a) : esc(c.rev1)}</td>
      <td class="n">${deltaCell(typeof c.delta === 'number' ? c.delta : (b != null && a != null ? a - b : null))}</td>
      <td class="n rc-mut">${b != null && a != null ? pct(b, a) : '—'}</td></tr>`;
  }).join('');
  // Subtotal rows from budget_by_dim (first dimension) + overall total budget.
  let subRows = '';
  const bbd = curves.budget_by_dim || {};
  const firstDim = Object.keys(bbd)[0];
  if (firstDim && Array.isArray(bbd[firstDim])) {
    subRows += bbd[firstDim].map(x => `<tr class="rc-subtot"><td colspan="2">${esc(x.category)} <span class="rc-mut">(${escapeHtml(firstDim)})</span></td>
      <td class="n">${fmt(x.rev0)}</td><td class="n">${fmt(x.rev1)}</td><td class="n">${deltaCell(typeof x.var === 'number' ? x.var : null)}</td><td class="n rc-mut">${pct(x.rev0, x.rev1)}</td></tr>`).join('');
  }
  const tb = rc.total_budget;
  if (tb) {
    subRows += `<tr class="rc-grandtot"><td colspan="2">Total budget</td><td class="n">${fmt(tb.rev0)}</td><td class="n">${fmt(tb.rev1)}</td>
      <td class="n">${deltaCell(typeof tb.delta === 'number' ? tb.delta : null)}</td><td class="n">${pct(tb.rev0, tb.rev1)}</td></tr>`;
  }
  return regTableCard('Cost changed <span class="rc-n">budget total cost · variance % · subtotals</span>', '',
    '<tr><th>Activity ID</th><th>Activity Name</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th><th class="n">%</th></tr>',
    rows + subRows, '');
}

// The register has no expandable drawers now; kept as a hook + code-chip context only.
function wireRegister() { /* per-type tables need no row wiring */ }

// ══ 5 · Cost & Resources ═══════════════════════════════════════════════════════

function scurveSvg(curves, rev0finish) {
  const vm = curves.value_monthly || [];
  const vc = curves.value_cumulative || [];
  const months = curves.months || vm.map(x => x.month);
  const n = months.length;
  if (!n || !vm.length) return noData('No planned-value spread available.');
  const W = 860, plotL = 52, plotR = 830, plotT = 20, plotB = 250;
  const colW = (plotR - plotL) / n;
  const bw = Math.min(14, colW * 0.32);
  const maxMonthly = Math.max(1, ...vm.map(x => Math.max(x.rev0 || 0, x.rev1 || 0)));
  const maxCum = Math.max(1, ...vc.map(x => Math.max(x.rev0 || 0, x.rev1 || 0)));
  const byMonth0 = {}, byMonth1 = {};
  vm.forEach(x => { byMonth0[x.month] = x.rev0 || 0; byMonth1[x.month] = x.rev1 || 0; });
  let bars = '';
  months.forEach((m, i) => {
    const cx = plotL + (i + 0.5) * colW;
    const v0 = byMonth0[m] || 0, v1 = byMonth1[m] || 0;
    const h0 = (v0 / maxMonthly) * (plotB - plotT), h1 = (v1 / maxMonthly) * (plotB - plotT);
    bars += `<rect x="${(cx - bw - 1).toFixed(1)}" y="${(plotB - h0).toFixed(1)}" width="${bw.toFixed(1)}" height="${h0.toFixed(1)}" fill="var(--muted)" opacity=".55"/>`;
    bars += `<rect x="${(cx + 1).toFixed(1)}" y="${(plotB - h1).toFixed(1)}" width="${bw.toFixed(1)}" height="${h1.toFixed(1)}" fill="var(--accent)" opacity=".85"/>`;
  });
  const cumByMonth = {}; vc.forEach(x => { cumByMonth[x.month] = x; });
  const line = (key, stroke, sw) => {
    const pts = months.map((m, i) => {
      const cx = plotL + (i + 0.5) * colW;
      const val = cumByMonth[m] ? (cumByMonth[m][key] || 0) : 0;
      const y = plotB - (val / maxCum) * (plotB - plotT);
      return `${cx.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    return `<polyline points="${pts}" fill="none" stroke="${stroke}" stroke-width="${sw}"/>`;
  };
  // Original finish marker
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
  return `<svg viewBox="0 0 ${W} 280" class="rc-svg" style="min-width:680px" role="img" aria-label="Planned value S-curve">
    <line x1="${plotL}" y1="${plotB}" x2="${plotR}" y2="${plotB}" stroke="var(--border)"/>
    <line x1="${plotL}" y1="${plotT}" x2="${plotL}" y2="${plotB}" stroke="var(--border)"/>
    <text x="${plotR + 2}" y="${plotT + 6}" font-size="9" fill="var(--accent)">100%</text>
    ${bars}
    ${line('rev0', 'var(--muted)', 2.2)}
    ${line('rev1', 'var(--accent)', 2.6)}
    ${origLine}${xlabels}
  </svg>`;
}

function manpowerSvg(curves) {
  const mm = curves.manpower_monthly || [];
  const months = curves.months || mm.map(x => x.month);
  const n = months.length;
  if (!n || !mm.length) return noData('No manpower spread available.');
  const W = 860, plotL = 52, plotR = 830, plotT = 20, plotB = 190;
  const colW = (plotR - plotL) / n;
  const bw = Math.min(13, colW * 0.32);
  const byM0 = {}, byM1 = {};
  mm.forEach(x => { byM0[x.month] = x.rev0 || 0; byM1[x.month] = x.rev1 || 0; });
  const maxV = Math.max(1, ...mm.map(x => Math.max(x.rev0 || 0, x.rev1 || 0)));
  let bars = '';
  months.forEach((m, i) => {
    const cx = plotL + (i + 0.5) * colW;
    const h0 = ((byM0[m] || 0) / maxV) * (plotB - plotT), h1 = ((byM1[m] || 0) / maxV) * (plotB - plotT);
    bars += `<rect x="${(cx - bw - 1).toFixed(1)}" y="${(plotB - h0).toFixed(1)}" width="${bw.toFixed(1)}" height="${h0.toFixed(1)}" fill="var(--muted)" opacity=".55"/>`;
    bars += `<rect x="${(cx + 1).toFixed(1)}" y="${(plotB - h1).toFixed(1)}" width="${bw.toFixed(1)}" height="${h1.toFixed(1)}" fill="var(--accent)"/>`;
  });
  const peak = curves.peak || {};
  let peakLbls = '';
  if (peak.rev0 != null) peakLbls += `<text x="${plotL + 6}" y="${plotT + 2}" font-size="9" fill="var(--muted)">Rev.00 peak ${esc(peak.rev0)}${peak.rev0_month ? ` (${esc(peak.rev0_month)})` : ''}</text>`;
  if (peak.rev1 != null) peakLbls += `<text x="${plotL + 6}" y="${plotT + 14}" font-size="9" fill="var(--accent)" font-weight="700">Rev.01 peak ${esc(peak.rev1)}${peak.rev1_month ? ` (${esc(peak.rev1_month)})` : ''}</text>`;
  const xlabels = thinLabels(months).map(({ i, m }) => {
    const cx = plotL + (i + 0.5) * colW;
    return `<text x="${cx.toFixed(1)}" y="${plotB + 14}" font-size="8" fill="var(--muted)" text-anchor="middle">${escapeHtml(String(m))}</text>`;
  }).join('');
  return `<svg viewBox="0 0 ${W} 210" class="rc-svg" style="min-width:680px" role="img" aria-label="Manpower histogram">
    <line x1="${plotL}" y1="${plotB}" x2="${plotR}" y2="${plotB}" stroke="var(--border)"/>
    <line x1="${plotL}" y1="${plotT}" x2="${plotL}" y2="${plotB}" stroke="var(--border)"/>
    ${bars}${peakLbls}${xlabels}
  </svg>`;
}

function costView(r) {
  const curves = r.curves || {};
  if (!curves.cost_available && !curves.resource_available) {
    return secmark('5', 'Cost & Resources')
      + `<div class="rc-card"><h3>Cost &amp; resources <span class="rc-n">optional</span></h3>${noData('Neither revision carries cost or resource loading — this section is reported as not applicable rather than "no change".')}</div>`;
  }

  // S-curve
  const scurve = curves.cost_available
    ? `<div class="rc-card"><h3>Planned value of work <span class="rc-n">monthly bars + cumulative curves · Rev.00 vs Rev.01</span></h3>
        <div class="rc-chartwrap">${scurveSvg(curves, r.rev0 && r.rev0.finish)}</div>
        <div class="rc-legend"><span><i style="background:var(--muted)"></i>Rev.00 value/mo</span><span><i style="background:var(--accent)"></i>Rev.01 value/mo</span><span><i class="rc-line" style="background:var(--muted)"></i>Rev.00 cum</span><span><i class="rc-line" style="background:var(--accent)"></i>Rev.01 cum</span></div>
        ${Number(curves.value_after_orig_finish) > 0 ? `<div class="rc-callout warn"><b>${fmt(curves.value_after_orig_finish)} of planned value now falls after the original finish (${esc(r.rev0 && r.rev0.finish)})</b> — potential extended-works exposure (prolongation, prelims, plant hire). Surfaced for review.</div>` : ''}
      </div>`
    : `<div class="rc-card"><h3>Planned value of work</h3>${noData('No cost loading — planned-value S-curve not applicable.')}</div>`;

  // Value tables (monthly & cumulative)
  const vm = curves.value_monthly || [];
  const vc = curves.value_cumulative || [];
  const cumByMonth = {}; vc.forEach(x => { cumByMonth[x.month] = x; });
  const CAP = 30;
  const valRows = vm.slice(0, CAP).map(x => {
    const c = cumByMonth[x.month] || {};
    return `<tr><td>${esc(x.month)}</td><td class="n rc-mut">${fmt(x.rev0)}</td><td class="n rc-new">${fmt(x.rev1)}</td>
      <td class="n">${deltaCell(typeof x.var === 'number' ? x.var : null)}</td>
      <td class="n rc-mut">${c.var != null ? fmt(c.var) : '—'}</td></tr>`;
  }).join('');
  const valTable = vm.length
    ? `<div class="rc-card"><h3>Planned value table <span class="rc-n">monthly &amp; cumulative</span></h3>
        <div class="rc-tblscroll"><table class="rc-t"><thead><tr><th>Month</th><th class="n">Rev.00</th><th class="n">Rev.01</th><th class="n">Var</th><th class="n">Cum Var</th></tr></thead>
        <tbody>${valRows}${vm.length > CAP ? '<tr><td colspan="5" class="rc-mut">… full monthly series in the report</td></tr>' : ''}</tbody></table></div></div>`
    : `<div class="rc-card"><h3>Planned value table</h3>${noData('No monthly value series available.')}</div>`;

  // Budget by dimension
  const bbd = curves.budget_by_dim || {};
  const dimKeys = Object.keys(bbd).filter(d => Array.isArray(bbd[d]) && bbd[d].length);
  const bdInner = dimKeys.map(d => {
    const rows = bbd[d].map(x => `<tr><td>${esc(x.category)}</td><td class="n rc-mut">${fmt(x.rev0)}</td><td class="n rc-new">${fmt(x.rev1)}</td><td class="n">${deltaCell(typeof x.var === 'number' ? x.var : null)}</td></tr>`).join('');
    return `<div class="rc-cklab">By ${escapeHtml(d)}</div><table class="rc-t"><thead><tr><th>${escapeHtml(d)}</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr></thead><tbody>${rows}</tbody></table>`;
  }).join('');
  const bdCard = `<div class="rc-card"><h3>Budget by dimension <span class="rc-n">where the money moved</span></h3>
    ${dimKeys.length ? bdInner : noData('No budget-by-dimension breakdown available.')}</div>`;

  // Manpower histogram + man-hours by trade
  const trade = curves.manhours_by_trade || [];
  const mt = curves.manhours_total || {};
  const tradeRows = trade.map(t => {
    const kindTag = { added: 'add', removed: 'rem', changed: 'chg' }[t.kind] || 'chg';
    const kindLabel = { added: 'Added', removed: 'Removed', changed: 'Changed' }[t.kind] || (t.kind || '');
    return `<tr><td class="rc-aid">${esc(t.resource_id)}</td><td>${esc(t.name)}</td>
      <td class="n rc-mut">${t.rev0 != null ? fmt(t.rev0) : '—'}</td><td class="n rc-new">${t.rev1 != null ? fmt(t.rev1) : '—'}</td>
      <td class="n">${deltaCell(typeof t.var === 'number' ? t.var : null)}</td><td>${typeTag(kindTag, kindLabel)}</td></tr>`;
  }).join('');
  const totRow = (mt.rev0 != null || mt.rev1 != null)
    ? `<tr class="rc-grandtot"><td colspan="2">Total man-hours</td><td class="n">${fmt(mt.rev0)}</td><td class="n">${fmt(mt.rev1)}</td>
        <td class="n">${deltaCell(typeof mt.var === 'number' ? mt.var : null)}${mt.pct != null ? ` <span class="rc-mut">(${mt.pct > 0 ? '+' : ''}${mt.pct}%)</span>` : ''}</td><td></td></tr>`
    : '';
  const manCard = curves.resource_available
    ? `<div class="rc-card"><h3>Manpower histogram <span class="rc-n">man-hours/month · Rev.00 vs Rev.01</span></h3>
        <div class="rc-chartwrap">${manpowerSvg(curves)}</div>
        ${(tradeRows || totRow) ? `<div class="rc-tblscroll" style="margin-top:8px"><table class="rc-t">
          <thead><tr><th>Resource ID</th><th>Trade</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th><th>Change</th></tr></thead>
          <tbody>${tradeRows}${totRow}</tbody></table></div>` : noData('No man-hours-by-trade breakdown available.')}</div>`
    : `<div class="rc-card"><h3>Manpower histogram</h3>${noData('No resource loading — manpower histogram not applicable.')}</div>`;

  return secmark('5', 'Cost & Resources') + scurve + `<div class="rc-split">${valTable}${bdCard}</div>` + manCard;
}

// ══ 6 · Scope & Structure ══════════════════════════════════════════════════════

function wbsColumn(nodes, side) {
  if (!nodes || !nodes.length) return noData('No WBS structure available for this revision.');
  return nodes.map(nd => {
    const lvl = Math.min(Math.max(parseInt(nd.level, 10) || 1, 1), 5);
    const state = nd.state && nd.state !== 'unchanged' ? nd.state : '';
    const badge = state ? `<span class="rc-p6badge">${escapeHtml(state)}</span>` : '';
    return `<div class="rc-p6band rc-l${lvl} ${state}" style="margin-left:${(lvl - 1) * 14}px">${esc(nd.name)}${badge}</div>`;
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

  return secmark('6', 'Scope & Structure') + wbsCard + dsCard;
}

// ── Report (PDF) — invoked by the ⬇ PDF button (global preview picker) ─────────

// The Report-Contents sections the Baseline Revision PDF can print (tool-wide picker
// standard). Keys + order mirror the six on-screen sub-tabs; a section is offered as
// empty (disabled "no data" pick) when its underlying data is absent.
export const REVCOMPARE_SECTIONS = [
  { key: 'summary',  label: 'Executive Summary' },
  { key: 'findings', label: 'Key Findings' },
  { key: 'critical', label: 'Critical Path & Float' },
  { key: 'register', label: 'Change Register' },
  { key: 'cost',     label: 'Cost & Resources' },
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
  const has = {
    findings: !!((r.slip && r.slip.contributions && r.slip.contributions.length)
      || (r.sequence_rollup && r.sequence_rollup.length) || (r.findings && r.findings.length)),
    critical: !!((cp.rev0 && cp.rev0.length) || (cp.rev1 && cp.rev1.length) || (q.float_bands && q.float_bands.length)),
    register: !!((r.duration_table && r.duration_table.length) || (r.logic_register && r.logic_register.length)
      || (r.milestones && r.milestones.some(m => m.kind !== 'unchanged'))
      || (r.constraint_changes && r.constraint_changes.length)
      || (r.calendar_changes && (((r.calendar_changes.reassignments || []).length) || ((r.calendar_changes.calendars || []).length)))
      || (((r.resource_changes || {}).assignment_changes || []).length)
      || (((r.resource_changes || {}).activity_cost_changes || []).length)),
    cost: !!(c.cost_available || c.resource_available),
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
      body: JSON.stringify({ report: r, meta, preview: true, sections: keys || null, theme: theme || mode }),
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
          body: JSON.stringify({ report: r, meta, theme: m, sections: keys || null, output_path: outputPath }),
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
