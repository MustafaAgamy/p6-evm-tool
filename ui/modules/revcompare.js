// Baseline Revision Comparison — compare two approved baseline revisions (Rev.00 vs
// Rev.01) from a planning/consultant perspective. Workflow: assign both revisions →
// Run Comparison → review results (Executive Summary · Change Register · Critical Path
// & Sequence · Milestones). Neutral by design: Change detected → Potential impact →
// Planning review, never an automatic verdict. Nothing runs until Run is pressed.

import { state } from './state.js';
import { showError, clearError } from './render.js';
import { escapeHtml } from './format.js';
import { getSavedMode } from './appearance.js';
import { showReportPreview } from './preview.js';

const RC_TABS = [
  ['summary', 'Executive Summary'], ['register', 'Change Register'],
  ['cp', 'Critical Path & Sequence'], ['struct', 'Scope & Structure'], ['ms', 'Milestones'],
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
  body.innerHTML = '<div class="rc-loading">Comparing Rev.00 vs Rev.01…</div>';
  const options = {
    fuzzy: document.getElementById('rc-opt-fuzzy')?.checked !== false,
    recompute_cp: document.getElementById('rc-opt-cp')?.checked !== false,
  };
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
}

// ── 2. Results shell + sub-tabs ──────────────────────────────────────────────

function renderResults(body) {
  const r = state.revcompareReport;
  const tab = state.revcompareTab || 'summary';
  const tabs = RC_TABS.map(([k, l]) =>
    `<button class="rc-tab ${k === tab ? 'on' : ''}" data-rctab="${k}">${l}</button>`).join('');
  const view = { summary: summaryView, register: registerView, cp: cpView, struct: structView, ms: msView }[tab](r);
  body.innerHTML = `
    <div class="rc-bar">
      <div class="rc-revtags">
        <span class="rc-revtag r0"><b>Rev.00</b> ${escapeHtml(r.rev0.file || '—')} · ${r.rev0.activities} act</span>
        <span class="rc-revtag r1"><b>Rev.01</b> ${escapeHtml(r.rev1.file || '—')} · ${r.rev1.activities} act</span>
      </div>
      <div class="rc-seg">${tabs}</div>
      <button class="rc-mini" id="rc-reset">${IC.flip} New comparison</button>
      <button class="rc-hidden-report" id="rc-preview-pdf" aria-hidden="true" tabindex="-1"></button>
    </div>
    ${r.warnings && r.warnings.length ? `<div class="rc-warn">${IC.warn} ${r.warnings.map(escapeHtml).join(' · ')}</div>` : ''}
    <div id="rc-view">${view}</div>`;
  body.querySelectorAll('[data-rctab]').forEach(b =>
    b.addEventListener('click', () => { state.revcompareTab = b.dataset.rctab; renderResults(body); }));
  body.querySelector('#rc-reset').addEventListener('click', () => {
    state.revcompareReport = null; renderInputs(body);
  });
  body.querySelector('#rc-preview-pdf').addEventListener('click', openRevcompareReport);
  if (tab === 'register') wireRegister(body);
}

// ── helpers ──────────────────────────────────────────────────────────────────

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
  return `<span class="rc-sev ${sev}">${label}</span>`;
}
function impPill(imp) {
  return `<span class="rc-imp ${imp}">${imp === 'material' ? 'Material' : 'Minor'}</span>`;
}
function typeTag(kind, label) {
  return `<span class="rc-tag ${kind}">${escapeHtml(label)}</span>`;
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

// ── Executive Summary ─────────────────────────────────────────────────────────

function kpi(k, v, cls, d, dc) {
  return `<div class="rc-kpi"><div class="rc-k">${k}</div><div class="rc-v ${cls || ''}">${v}</div>${d ? `<div class="rc-dd ${dc || ''}">${d}</div>` : ''}</div>`;
}

function summaryView(r) {
  const s = r.summary;
  const maxCount = Math.max(1, ...r.profile.map(p => p.count));
  const bars = r.profile.map(p => `
    <div class="rc-pbar"><div class="rc-pl"><span class="rc-pdot" style="background:${p.color}"></span>${escapeHtml(p.label)}</div>
      <div class="rc-pt"><div class="rc-pf" style="width:${Math.round(p.count / maxCount * 100)}%;background:${p.color}"></div></div>
      <div class="rc-pv">${p.count}</div></div>`).join('');
  const ledger = r.ledger.map(l => `
    <tr><td>${escapeHtml(l.label)}</td>
      <td class="n">${l.rev0 != null ? escapeHtml(String(l.rev0)) : '—'}${l.rev1 != null ? ` <span class="rc-new">${escapeHtml(String(l.rev1))}</span>` : ''}</td>
      <td class="n">${deltaCell(l.delta)}</td></tr>`).join('');
  const findings = r.findings.map(f => `
    <div class="rc-finding"><div class="rc-fsev ${f.severity}"></div>
      <div><div class="rc-ftitle">${escapeHtml(f.title)} ${typeTag(f.change_type, f.type_label)} ${sevPill(f.severity)}</div>
        <div class="rc-fbody">${escapeHtml(f.body || '')}</div>
        <div class="rc-flow"><span class="rc-fk det">Change detected</span><span class="rc-arw">→</span><span class="rc-fk imp">${escapeHtml(f.flow_impact || 'Potential schedule impact')}</span><span class="rc-arw">→</span><span class="rc-fk rev">Planning review</span></div>
      </div></div>`).join('');
  return `
    <div class="rc-kpis">
      ${kpi('Activities', `${s.activities0}→${s.activities1}`, '', `${num(s.net, true)} net`, s.net > 0 ? 'up' : s.net < 0 ? 'down' : '')}
      ${kpi('New', s.added, 'add', 'added in Rev.01')}
      ${kpi('Removed', s.removed, 'rem', 'not in Rev.01')}
      ${kpi('Modified', s.modified, 'chg', `+ ${s.id_changes} ID changes`)}
      ${kpi('Project duration', s.duration_change_wd != null ? `${num(s.duration_change_wd, true)} wd` : '—', 'crit', 'critical-path length', s.duration_change_wd > 0 ? 'up' : '')}
      ${kpi('Finish date', r.rev1.finish || '—', 'crit', s.finish_shift_days != null ? `${num(s.finish_shift_days, true)} days` : '', s.finish_shift_days > 0 ? 'up' : 'down')}
    </div>
    <div class="rc-split">
      <div class="rc-card"><h3>Change profile <span class="rc-n">by category</span></h3>
        <div class="rc-sec">Detected changes classified into planning categories</div>
        <div class="rc-profile">${bars}</div></div>
      <div class="rc-card"><h3>Comparison ledger <span class="rc-n">Rev.00 → Rev.01</span></h3>
        <table class="rc-t"><tbody>${ledger}</tbody></table></div>
    </div>
    <div class="rc-card"><h3>Key findings — material changes <span class="rc-n">ranked · for planning review</span></h3>
      <div class="rc-sec">The differences most likely to affect the execution strategy. Each is an observation, not a verdict.</div>
      ${findings || '<div class="rc-empty2">No material changes detected between the two revisions.</div>'}</div>`;
}

// ── Change Register ────────────────────────────────────────────────────────────

export const REG_BUCKET = {
  added: 'scope', removed: 'scope', renamed: 'scope', idchange: 'identity',
  moved_wbs: 'wbs', wbs_add: 'wbs', wbs_remove: 'wbs', wbs_rename: 'wbs',
};
export function bucketOf(t) { return REG_BUCKET[t] || t; }

function registerView(r) {
  const rows = r.register.map((row, i) => registerRow(row, i)).join('');
  // Build filter chips from what's actually present, with live counts.
  const count = (pred) => r.register.filter(pred).length;
  const chips = [
    ['all', 'All', r.register.length],
    ['material', 'Material', count(x => x.impact === 'material')],
    ['crit', 'Critical only', count(x => x.severity === 'crit')],
    ['logic', 'Logic', count(x => x.change_type === 'logic')],
    ['sequence', 'Sequence', count(x => x.change_type === 'sequence')],
    ['scope', 'Scope', count(x => bucketOf(x.change_type) === 'scope')],
    ['milestone', 'Milestones', count(x => x.change_type === 'milestone')],
    ['criticality', 'Criticality', count(x => x.change_type === 'criticality')],
    ['calendar', 'Calendar', count(x => x.change_type === 'calendar')],
    ['constraint', 'Constraints', count(x => x.change_type === 'constraint')],
    ['wbs', 'WBS', count(x => bucketOf(x.change_type) === 'wbs')],
  ].filter(c => c[0] === 'all' || c[2] > 0);
  const chipsHtml = chips.map(([k, l, n], idx) =>
    `<button class="rc-fchip ${idx === 0 ? 'on' : ''}" data-filter="${k}">${l} <span class="rc-fc">${n}</span></button>`).join('');
  return `
    <div class="rc-filters">${chipsHtml}</div>
    <div class="rc-card" style="padding:0;overflow:hidden">
      <div class="rc-reghead"><b>Change Register</b><span class="rc-mut" id="rc-regcount"> ${r.register.length} changes · ranked by impact then severity</span></div>
      <div class="rc-tblscroll"><table class="rc-t rc-reg">
        <thead><tr><th>Activity ID</th><th>Activity name</th><th>Change type</th><th>Rev.00</th><th>Rev.01</th><th>Change</th><th>Impact</th><th>Severity</th><th>Status</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="9" class="rc-empty2">No material changes detected between the two revisions.</td></tr>'}</tbody>
      </table></div>
    </div>
    <div class="rc-foot">▸ Rows with a triangle expand to the full Rev.00 ⇄ Rev.01 comparison and the four-part planning analysis. Severity reflects <b>schedule impact</b>, never a judgement that a change is wrong.</div>`;
}

function registerRow(row, i) {
  const hasDetail = !!row.detail;
  const idText = row.orig_id && row.orig_id !== row.activity_id ? row.orig_id : row.activity_id;
  const display = idText.replace(/^(MS:|SCOPE:)/, '');
  return `
    <tr class="${hasDetail ? 'rc-rowx' : ''}" data-i="${i}" data-bucket="${bucketOf(row.change_type)}" data-type="${row.change_type}" data-imp="${row.impact}" data-sev="${row.severity}">
      <td>${hasDetail ? '<span class="rc-exp">▸</span> ' : '<span class="rc-noexp"></span>'}<span class="rc-aid">${escapeHtml(display)}</span></td>
      <td><b>${escapeHtml(row.activity_name)}</b></td>
      <td>${typeTag(row.change_type, row.type_label)}</td>
      <td class="rc-mut">${escapeHtml(String(row.rev0 ?? '—'))}</td>
      <td class="rc-new">${escapeHtml(String(row.rev1 ?? '—'))}</td>
      <td>${escapeHtml(String(row.change ?? ''))}</td>
      <td>${impPill(row.impact)}</td>
      <td>${sevPill(row.severity)}</td>
      <td><span class="rc-status">${escapeHtml(row.status)}</span></td>
    </tr>
    ${hasDetail ? `<tr class="rc-drawer hidden" id="rc-dr-${i}"><td colspan="9">${detailDrawer(row.detail)}</td></tr>` : ''}`;
}

function detailDrawer(d) {
  const col = (cls, head, v) => {
    if (!v) return `<div class="rc-ddcol ${cls}"><div class="rc-ch">${head}</div><div class="rc-ddrow"><span class="rc-dk">—</span></div></div>`;
    const K = [['Activity ID', v.id], ['Activity name', v.name], ['WBS', v.wbs], ['Start', v.start], ['Finish', v.finish], ['Duration', v.duration], ['Total float', v.total_float], ['Criticality', v.criticality]];
    return `<div class="rc-ddcol ${cls}"><div class="rc-ch">${head}</div>${K.map(([k, val], i) =>
      `<div class="rc-ddrow"><span class="rc-dk">${k}</span><span class="rc-dv ${i >= 6 && cls === 'c1' ? 'hot' : ''}">${escapeHtml(String(val ?? '—'))}</span></div>`).join('')}</div>`;
  };
  return `<div class="rc-dd">
    ${col('c0', 'Rev.00 · Original', d.rev0)}
    ${col('c1', 'Rev.01 · Revised', d.rev1)}
    <div class="rc-analysis">
      <div class="rc-abox det"><div class="rc-at">Change detected</div><p>${escapeHtml(d.detected || '')}</p></div>
      <div class="rc-abox why"><div class="rc-at">Why it matters</div><p>${escapeHtml(d.why || '')}</p></div>
      <div class="rc-abox imp2"><div class="rc-at">Potential impact</div><p>${escapeHtml(d.impact || '')}</p></div>
      <div class="rc-abox rev"><div class="rc-at">Planning review</div><p>${escapeHtml(d.review || '')}</p></div>
    </div></div>`;
}

function wireRegister(body) {
  body.querySelectorAll('.rc-rowx').forEach(tr => tr.addEventListener('click', () => {
    const i = tr.dataset.i;
    const dr = document.getElementById(`rc-dr-${i}`);
    if (!dr) return;
    tr.classList.toggle('open');
    dr.classList.toggle('hidden');
  }));
  const rows = [...body.querySelectorAll('tbody tr[data-i]')];
  const matches = (tr, f) => f === 'all'
    || (f === 'material' && tr.dataset.imp === 'material')
    || (f === 'crit' && tr.dataset.sev === 'crit')
    || (['scope', 'wbs'].includes(f) && tr.dataset.bucket === f)
    || (['logic', 'sequence', 'milestone', 'criticality', 'calendar', 'constraint'].includes(f) && tr.dataset.type === f);
  body.querySelectorAll('.rc-fchip').forEach(chip => chip.addEventListener('click', () => {
    body.querySelectorAll('.rc-fchip').forEach(c => c.classList.toggle('on', c === chip));
    const f = chip.dataset.filter;
    let shown = 0;
    rows.forEach(tr => {
      const vis = matches(tr, f);
      if (vis) shown++;
      tr.hidden = !vis;
      const dr = document.getElementById(`rc-dr-${tr.dataset.i}`);
      if (dr) { dr.hidden = !vis; if (!vis) { dr.classList.add('hidden'); tr.classList.remove('open'); } }
    });
    const cnt = document.getElementById('rc-regcount');
    if (cnt) cnt.textContent = ` ${shown} of ${rows.length} changes shown`;
  }));
}

// ── Critical Path & Sequence ───────────────────────────────────────────────────

function node(n) {
  const cls = n.state === 'enter' ? 'enter' : n.state === 'leave' ? 'leave' : (n.tf != null && n.tf <= 0 ? 'crit' : '');
  const code = n.code ? `<span class="rc-nf">${escapeHtml(n.code)}</span>` : '';
  return `<div class="rc-node ${cls}">${escapeHtml(n.name)}${code}</div>`;
}
function chain(nodes) {
  if (!nodes || !nodes.length) return '<div class="rc-mut">No driving path available for this revision.</div>';
  return nodes.map(node).join('<span class="rc-lnk"><span class="rc-lt">FS</span>→</span>');
}

function cpView(r) {
  const cp = r.critical_path;
  const seqCards = (r.sequence || []).map(s => `
    <div class="rc-card"><h3>Sequence change detected <span class="rc-n">${escapeHtml(s.shared_wbs || 'logic order')}</span></h3>
      <div class="rc-sec">Read from logic &amp; execution relationships — not from sorting by start date</div>
      <div class="rc-cklab">Rev.00 — planned order</div>
      <div class="rc-chain">${(s.chain0 || []).map(nm => `<div class="rc-node ${nm === s.a_name || nm === s.b_name ? 'moved' : ''}">${escapeHtml(nm)}</div>`).join('<span class="rc-lnk">→</span>')}</div>
      <div class="rc-cklab r1">Rev.01 — revised order</div>
      <div class="rc-chain">${(s.chain1 || []).map(nm => `<div class="rc-node ${nm === s.a_name || nm === s.b_name ? 'moved' : ''}">${escapeHtml(nm)}</div>`).join('<span class="rc-lnk">→</span>')}</div>
      <div class="rc-finding" style="margin-top:12px"><div class="rc-fsev ${s.severity || 'hi'}"></div>
        <div><div class="rc-ftitle">${escapeHtml(s.a_name)} re-sequenced relative to ${escapeHtml(s.b_name)}</div>
          <div class="rc-fbody">Was planned <b>${escapeHtml(s.rev0)}</b>; now <b>${escapeHtml(s.rev1)}</b>. Flagged for review, not marked incorrect.</div>
          <div class="rc-flow"><span class="rc-fk det">Change detected</span><span class="rc-arw">→</span><span class="rc-fk imp">Execution-order change</span><span class="rc-arw">→</span><span class="rc-fk rev">Planning review</span></div></div>
      </div></div>`).join('');

  const floats = (r.float_movement || []).map(f => `
    <tr><td><span class="rc-aid">${escapeHtml(f.activity_id)}</span> ${escapeHtml(f.name)}</td>
      <td class="n">${f.rev0_tf} d</td><td class="n">${f.rev1_tf} d</td><td class="n">${deltaCell(f.delta)}</td>
      <td>${typeTag(f.movement_cls === 'add' ? 'add' : f.movement_cls === 'rem' ? 'rem' : 'chg', f.movement)}</td></tr>`).join('');

  return `
    <div class="rc-card"><h3>Critical path — Rev.00 vs Rev.01 <span class="rc-n">driving chain · longest path</span></h3>
      <div class="rc-sec">${cp.length_change_wd != null ? `Rev.01 critical path is ${num(cp.length_change_wd, true)} working days ${cp.length_change_wd >= 0 ? 'longer' : 'shorter'}.` : 'Driving chain to the governing finish milestone.'}</div>
      <div class="rc-chainrow"><div class="rc-clab r0"><div class="rc-ck">Rev.00</div><div class="rc-cv">ends ${escapeHtml(r.rev0.finish || '—')}</div></div>
        <div class="rc-chainwrap"><div class="rc-chain">${chain(cp.rev0)}</div></div></div>
      <div class="rc-chainrow"><div class="rc-clab r1"><div class="rc-ck">Rev.01</div><div class="rc-cv">ends ${escapeHtml(r.rev1.finish || '—')}</div></div>
        <div class="rc-chainwrap"><div class="rc-chain">${chain(cp.rev1)}</div></div></div>
      <div class="rc-leg">
        <span><span class="rc-ld enter"></span>Entered critical path (${cp.entered.length})</span>
        <span><span class="rc-ld leave"></span>Left critical path (${cp.left.length})</span>
        <span><span class="rc-ld crit"></span>Critical in both</span>
        ${cp.entered.length ? `<span class="rc-mut">Entering: ${cp.entered.slice(0, 4).map(e => escapeHtml(e.name)).join(', ')}${cp.entered.length > 4 ? '…' : ''}</span>` : ''}
      </div></div>
    <div class="rc-split">
      ${seqCards || '<div class="rc-card"><h3>Sequence changes</h3><div class="rc-sec">No execution-order reversals detected from the logic.</div></div>'}
      <div class="rc-card"><h3>Float / criticality movement <span class="rc-n">total float, working days</span></h3>
        <div class="rc-sec">Activities whose criticality changed most between revisions</div>
        <table class="rc-t"><thead><tr><th>Activity</th><th class="n">Rev.00 TF</th><th class="n">Rev.01 TF</th><th class="n">Δ</th><th>Movement</th></tr></thead>
          <tbody>${floats || '<tr><td colspan="5" class="rc-mut">No material float movement.</td></tr>'}</tbody></table></div>
    </div>`;
}

// ── Scope & Structure (WBS · Calendar · Constraint) ────────────────────────────

function structView(r) {
  const w = r.wbs_changes || { added: [], removed: [], renamed: [], moved_activities: 0 };
  const cc = r.calendar_changes || { calendars: [], reassignments: [] };
  const con = r.constraint_changes || [];

  const wbsRows = [
    ...w.added.map(x => `<tr><td>${typeTag('wbs_add', 'Added')}</td><td class="rc-mut">—</td><td class="rc-new">${escapeHtml(x.path)}</td></tr>`),
    ...w.removed.map(x => `<tr><td>${typeTag('wbs_remove', 'Removed')}</td><td class="rc-mut">${escapeHtml(x.path)}</td><td class="rc-mut">—</td></tr>`),
    ...w.renamed.map(x => `<tr><td>${typeTag('wbs_rename', 'Renamed')}</td><td class="rc-mut">${escapeHtml(x.from)}</td><td class="rc-new">${escapeHtml(x.to)}</td></tr>`),
  ].join('');
  const wbsCard = `
    <div class="rc-card"><h3>WBS / scope structure <span class="rc-n">branches &amp; work packages</span></h3>
      <div class="rc-sec">${w.added.length} added · ${w.removed.length} removed · ${w.renamed.length} renamed · ${w.moved_activities} activities moved between WBS</div>
      ${wbsRows ? `<table class="rc-t"><thead><tr><th>Change</th><th>Rev.00</th><th>Rev.01</th></tr></thead><tbody>${wbsRows}</tbody></table>`
                : '<div class="rc-mut">No WBS branches added, removed or renamed.</div>'}</div>`;

  const reassign = cc.reassignments.map(g => `
    <tr><td class="rc-mut">${escapeHtml(g.from)}</td><td class="rc-new">${escapeHtml(g.to)}</td>
      <td class="n">${g.from_wd != null && g.to_wd != null ? `${g.from_wd}-day → ${g.to_wd}-day` : '—'}</td>
      <td class="n">${g.count}</td></tr>`).join('');
  const calLevel = cc.calendars.map(c =>
    `<div class="rc-callrow">${typeTag(c.change === 'added' ? 'added' : c.change === 'removed' ? 'removed' : 'chg', c.change)} <b>${escapeHtml(c.name)}</b> <span class="rc-mut">${escapeHtml(c.detail)}</span></div>`).join('');
  const calCard = `
    <div class="rc-card"><h3>Calendar comparison <span class="rc-n">assignments &amp; workweek</span></h3>
      <div class="rc-sec">Per-activity calendar reassignments and calendar-level changes</div>
      ${reassign ? `<table class="rc-t"><thead><tr><th>From</th><th>To</th><th class="n">Workweek</th><th class="n">Activities</th></tr></thead><tbody>${reassign}</tbody></table>` : ''}
      ${calLevel || (reassign ? '' : '<div class="rc-mut">No calendar assignment or workweek changes.</div>')}
      ${reassign && cc.reassignments.some(g => g.from_wd !== g.to_wd && g.from_wd != null) ? '<div class="rc-foot">A workweek change shortens planned durations even where the work content is identical — confirm the basis (approved acceleration vs. an inadvertent reassignment).</div>' : ''}</div>`;

  const conRows = con.map(c => {
    const kindLabel = { added: 'Added', removed: 'Removed', type: 'Type changed', date: 'Date changed' }[c.kind] || c.kind;
    return `<tr><td><span class="rc-aid">${escapeHtml(c.activity_id)}</span> ${escapeHtml(c.name)}</td>
      <td>${typeTag('constraint', kindLabel)}${c.hard ? ' <span class="rc-sev hi">Hard</span>' : ''}</td>
      <td class="rc-mut">${escapeHtml(c.rev0)}</td><td class="rc-new">${escapeHtml(c.rev1)}</td></tr>`;
  }).join('');
  const conCard = `
    <div class="rc-card"><h3>Constraint comparison <span class="rc-n">primary constraints</span></h3>
      <div class="rc-sec">Constraints added, removed or changed on matched activities</div>
      ${conRows ? `<table class="rc-t"><thead><tr><th>Activity</th><th>Change</th><th>Rev.00</th><th>Rev.01</th></tr></thead><tbody>${conRows}</tbody></table>`
                : '<div class="rc-mut">No primary-constraint changes.</div>'}</div>`;

  return `<div class="rc-split">${wbsCard}${calCard}</div>${conCard}
    <div class="rc-callout"><b>Neutral by design.</b> A workweek change, a new constraint or a re-packaged WBS may all be legitimate, approved decisions. These are surfaced for <b>planning review</b> — the tool flags what changed and its potential effect, never that the revision is wrong.</div>`;
}

// ── Milestones ─────────────────────────────────────────────────────────────────

function msView(r) {
  const rows = (r.milestones || []).map(m => {
    const kindPill = { delayed: 'rc-sev hi', advanced: 'rc-sev adv', unchanged: 'rc-status', new: 'rc-tag add', removed: 'rc-tag rem' }[m.kind] || 'rc-status';
    const kindLabel = { delayed: 'Delayed', advanced: 'Advanced', unchanged: 'Unchanged', new: 'New', removed: 'Removed' }[m.kind] || m.kind;
    const chg = m.change_days != null ? deltaCell(`${m.change_days > 0 ? '+' : ''}${m.change_days} d`) : (m.kind === 'new' ? '<span class="rc-tag add">New</span>' : m.kind === 'removed' ? '<span class="rc-tag rem">Removed</span>' : '—');
    return `<tr><td><b>${escapeHtml(m.name)}</b></td>
      <td class="rc-mut">${escapeHtml(m.rev0 || '—')}</td>
      <td class="rc-new">${escapeHtml(m.rev1 || '—')}</td>
      <td class="n">${chg}</td>
      <td><span class="${kindPill}">${kindLabel}</span></td></tr>`;
  }).join('');
  return `
    <div class="rc-card"><h3>Milestone comparison <span class="rc-n">finish milestones</span></h3>
      <div class="rc-sec">Delayed, advanced, unchanged, new and removed milestones between the two revisions</div>
      <table class="rc-t"><thead><tr><th>Milestone</th><th>Rev.00</th><th>Rev.01</th><th class="n">Change</th><th>Impact</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="5" class="rc-mut">No finish milestones found in the revisions.</td></tr>'}</tbody></table></div>
    <div class="rc-callout"><b>Report output.</b> Executive Summary, Revision Overview, Milestone Comparison, Critical Path Comparison, Sequence &amp; Logic changes and the Change Register assemble into one consultant-grade PDF via the global <b>File ▸ Print / Export to PDF</b> — no separate export button lives inside this feature.</div>`;
}

// ── Report (PDF) — invoked by the global File ▸ Print / Export action ─────────

export async function openRevcompareReport() {
  const r = state.revcompareReport;
  if (!r) { showError('Run the comparison first, then print.'); return; }
  const mode = getSavedMode();
  const meta = {
    rev0_file: r.rev0.file, rev1_file: r.rev1.file,
    report_date: new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }),
  };
  const fetchPreview = async (theme) => {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/revcompare/report`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report: r, meta, preview: true, theme: theme || mode }),
    });
    const data = await resp.json();
    return (data.ok && data.html) ? data.html : null;
  };
  try {
    const html = await fetchPreview(mode);
    if (!html) { showError('Preview failed — please retry.'); return; }
    showReportPreview({
      title: 'Baseline Revision Comparison', subtitle: `${r.rev0.file || 'Rev.00'} vs ${r.rev1.file || 'Rev.01'}`,
      html, initialMode: mode,
      onThemeChange: (theme) => fetchPreview(theme),
      onSave: async (m) => {
        const outputPath = await window.pywebview.api.choose_save_path('Baseline_Revision_Comparison.pdf', 'pdf');
        if (!outputPath) return false;
        const resp = await fetch(`http://localhost:${state.serverPort}/api/revcompare/report`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ report: r, meta, theme: m, output_path: outputPath }),
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
