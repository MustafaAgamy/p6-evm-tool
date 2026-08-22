// Constructability Review — rule-based, offline, powered by the local Knowledge
// Base (Decision 009). No AI, no key, no cost. Runs when the tab is opened.
// Reuses the approved review-report layout (.ai-* styles) and the shared helpers.

import { state }                                    from './state.js';
import { showError, clearError }                    from './render.js';
import { escapeHtml }                               from './format.js';
import { bandHex, kindClass, markerLeft, impactPill } from './aireview_helpers.js';
import { showReportPreview }                        from './preview.js';

// ── shared cell/table renderers (same data shape as the report) ────────────

function _idStack(list) {
  if (!list || !list.length) return '<span class="mut">—</span>';
  return list.map(l => {
    const cls = kindClass(l.kind);
    const rel = l.rel ? `<span class="ai-rel">${escapeHtml(l.rel)}</span>` : '';
    const id = escapeHtml(l.id || '');
    const tag = l.kind === 'remove' ? ' <span class="ai-tag-rem">REMOVE</span>'
              : l.kind === 'add' ? ' <span class="ai-tag-add">ADD</span>' : '';
    return `<div class="ai-stk ${cls}">${cls === 'ai-rem' ? `<s>${id}</s>` : id}${rel}${tag}</div>`;
  }).join('');
}

function _nameStack(list) {
  if (!list || !list.length) return '<span class="mut">—</span>';
  return list.map(l => {
    const nm = escapeHtml(l.name || '');
    return `<div class="ai-stk">${l.kind === 'remove' ? `<s>${nm}</s>` : nm}</div>`;
  }).join('');
}

// One combined cell per link — ID over name — so the table needs far fewer
// columns and fits the window (and the landscape PDF) instead of being trimmed.
function _linkCell(list) {
  if (!list || !list.length) return '<span class="mut">—</span>';
  return list.map(l => {
    const cls = kindClass(l.kind);
    const id = escapeHtml(l.id || '');
    const nm = escapeHtml(l.name || '');
    const rel = l.rel ? ` <span class="ai-rel">${escapeHtml(l.rel)}</span>` : '';
    const tag = l.kind === 'remove' ? ' <span class="ai-tag-rem">REM</span>'
              : l.kind === 'add' ? ' <span class="ai-tag-add">ADD</span>' : '';
    return `<div class="ai-lk ${cls}"><b class="mono">${cls === 'ai-rem' ? `<s>${id}</s>` : id}</b>${rel}${tag}${nm ? `<div class="ai-lknm">${nm}</div>` : ''}</div>`;
  }).join('');
}

function _illogicalTable(rows) {
  if (!rows || !rows.length) {
    return '<p class="ai-empty">No illogical relationships flagged — the sequence logic matches the Knowledge Base rules.</p>';
  }
  const rank = { 'Critical': 0, 'Near-critical': 1 };   // major illogical relationships first
  const sorted = [...rows].sort((a, b) => (rank[a.impact] ?? 2) - (rank[b.impact] ?? 2));
  const body = sorted.map((r, i) => `<tr>
    <td class="ai-sn">${i + 1}</td>
    <td class="mono">${escapeHtml(r.activity_id)}</td>
    <td>${escapeHtml(r.activity_name)}</td>
    <td class="mut" title="${escapeHtml(r.wbs_path || '')}">${escapeHtml(r.wbs_path || '')}</td>
    <td class="sepL">${_linkCell(r.current_preds)}</td>
    <td>${_linkCell(r.current_succs)}</td>
    <td class="ai-why sepL">${escapeHtml(r.why || '')}</td>
    <td class="sepL">${_linkCell(r.suggested_preds)}</td>
    <td>${_linkCell(r.suggested_succs)}</td>
    <td>${impactPill(r.impact)}</td></tr>`).join('');
  return `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table ai-table ai-illog">
    <colgroup><col style="width:3%"><col style="width:9%"><col style="width:15%"><col style="width:13%">
      <col style="width:11%"><col style="width:11%"><col style="width:15%"><col style="width:11%"><col style="width:11%"><col style="width:6%"></colgroup>
    <thead>
      <tr><th rowspan="2">#</th><th rowspan="2">Activity ID</th><th rowspan="2">Activity Name</th><th rowspan="2">WBS Path</th>
        <th colspan="2" class="ai-gh-cur sepL">Current driving links</th>
        <th rowspan="2" class="sepL">Why it's illogical</th>
        <th colspan="2" class="ai-gh-sug sepL">Suggested links</th>
        <th rowspan="2">Impact</th></tr>
      <tr><th class="sepL">Predecessor</th><th>Successor</th>
        <th class="sepL">Predecessor</th><th>Successor</th></tr>
    </thead><tbody>${body}</tbody></table></div>
    <div class="ai-foot">Most critical first. Each cell shows the link's <b>ID</b> over its name; an activity can have several — all listed.
      <span class="ai-tag-add" style="margin:0">ADD</span> add a link ·
      <span class="ai-tag-rem" style="margin:0">REM</span> a redundant link to remove (struck through).</div>`;
}

function _missingTable(rows) {
  if (!rows || !rows.length) {
    return '<p class="ai-empty">No missing activities against this project type’s Knowledge Base.</p>';
  }
  const body = rows.map(r => `<tr>
    <td class="mono">${escapeHtml(r.suggested_id)}</td>
    <td>${escapeHtml(r.name)}</td>
    <td>${r.new_wbs ? '<span class="ai-newwbs">＋ new</span> ' : ''}${escapeHtml(r.wbs || '')}</td>
    <td>${_idStack(r.preds)}</td><td>${_nameStack(r.preds)}</td>
    <td>${_idStack(r.succs)}</td><td>${_nameStack(r.succs)}</td>
    <td class="ai-why">${escapeHtml(r.why || '')}</td>
    <td><span class="ai-basis">${escapeHtml(r.basis || '')}</span></td></tr>`).join('');
  return `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table ai-table">
    <thead><tr><th>Suggested ID</th><th>Activity Name</th><th>Where it belongs (WBS)</th>
      <th>Pred. ID</th><th>Pred. Name</th><th>Succ. ID</th><th>Succ. Name</th>
      <th>Why it's normally needed</th><th>Source</th></tr></thead>
    <tbody>${body}</tbody></table></div>
    <div class="ai-foot">Suggested IDs are checked against the schedule so none clash with an existing activity ID.
      <span class="ai-newwbs" style="margin:0">＋ new</span> = a WBS branch proposed where none suited.</div>`;
}

function _wbsReview(rows, missingWbs) {
  const items = (rows || []).map(w => {
    const miss = w.status === 'missing';
    const mk = miss ? '<span class="ai-mk x">⚠</span>' : '<span class="ai-mk ok">✓</span>';
    return `<div class="ai-wbs-row ${miss ? 'miss' : ''}">${mk}<span class="nm">${escapeHtml(w.name)}</span>
      <span class="rz">${escapeHtml(w.note || '')}</span></div>`;
  }).join('');
  const missing = (missingWbs || []).map(w => `<div class="ai-wbs-row miss">
    <span class="ai-mk x">⚠</span><span class="nm">${escapeHtml(w.name)} — <b>suggested new branch</b></span>
    <span class="rz">${escapeHtml(w.why || '')}</span></div>`).join('');
  if (!items && !missing) return '<p class="ai-empty">No WBS notes.</p>';
  // show the KB checklist (items) — the missing ones are already flagged inside it
  return `<div class="ai-wbs">${items || missing}</div>`;
}

// ── Execution-Readiness Dashboard ──────────────────────────────────────────

function _gauge(score, hex) {
  const p = markerLeft(score), a = Math.PI * (1 - p / 100);
  const x = (100 + 82 * Math.cos(a)).toFixed(1), y = (106 - 82 * Math.sin(a)).toFixed(1);
  return `<svg viewBox="0 0 200 118" class="xd-gsvg">
    <path d="M18 106 A82 82 0 0 1 182 106" fill="none" stroke="var(--border)" stroke-width="15" stroke-linecap="round"/>
    <path d="M18 106 A82 82 0 0 1 ${x} ${y}" fill="none" stroke="${hex}" stroke-width="15" stroke-linecap="round"/>
    <text x="100" y="88" text-anchor="middle" class="xd-gnum" style="fill:${hex}">${score}</text>
    <text x="100" y="105" text-anchor="middle" class="xd-gsuf">/ 100</text></svg>`;
}

function _legend(score) {
  const bands = [
    { w: 50, c: '#dc2626', t: 'Major gaps', r: '0–49' },
    { w: 20, c: '#ea580c', t: 'Significant', r: '50–69' },
    { w: 15, c: '#d97706', t: 'Minor gaps', r: '70–84' },
    { w: 15, c: '#16a34a', t: 'Ready', r: '85–100' },
  ];
  const segs = bands.map(b => `<div class="xd-lseg" style="width:${b.w}%;background:${b.c}"><b>${b.t}</b><span>${b.r}</span></div>`).join('');
  return `<div class="xd-legend"><div class="xd-lttl">How to read the score — Constructability bands</div>
    <div class="xd-lwrap">
      <div class="xd-lmark" style="left:${markerLeft(score)}%"><div class="bub">Your score · ${score}</div><div class="arw"></div></div>
      <div class="xd-lbar">${segs}</div>
    </div>
    <div class="xd-lfoot">Score = <b>45% sequence logic + 45% scope completeness + 10% structure</b>.
      Ready = sound to baseline · Minor = small tidy-ups · Significant = fix before execution · Major = rework the logic/scope.</div></div>`;
}

function _dims(s, hex) {
  const bar = (label, val) => `<div class="xd-dim"><div class="dh"><span>${label}</span><b>${val}/100</b></div>
    <div class="xd-track"><i style="width:${markerLeft(val)}%;background:${hex}"></i></div></div>`;
  return `<div class="xd-dims"><h4>Readiness by dimension</h4>
    ${bar('① Sequence logic <em>(45%)</em>', s.logic)}
    ${bar('② Scope completeness <em>(45%)</em>', s.completeness)}
    ${bar('③ Structure &amp; load <em>(10%)</em>', s.structure)}</div>`;
}

function _kpi(cls, big, pct, lbl, sub) {
  return `<div class="xd-kpi ${cls}"><div class="big">${big}${pct ? ` <span class="pct">${pct}</span>` : ''}</div>
    <div class="lbl">${lbl}</div><div class="sub">${sub}</div></div>`;
}

function _kpis(d) {
  return `<div class="xd-kpis">
    ${_kpi(d.illogical_count ? 'crit' : 'ok', d.illogical_count ?? 0, `${d.illogical_pct ?? 0}%`, 'Illogical links', `of ${d.total_relationships ?? 0} links`)}
    ${_kpi(d.missing_count ? 'warn' : 'ok', d.missing_count ?? 0, `${d.missing_pct ?? 0}%`, 'Missing activities', 'vs standard scope')}
    ${_kpi(d.missing_wbs ? 'warn' : 'ok', d.missing_wbs ?? 0, '', 'Missing WBS', 'standard branches')}
    ${_kpi(d.critical_affected ? 'crit' : 'ok', d.critical_affected ? 'Yes' : 'No', '', 'Critical path', `${d.critical_count ?? 0} on the CP`)}
    ${_kpi((d.coverage ?? 0) >= 85 ? 'ok' : 'warn', `${d.coverage ?? 0}%`, '', 'Scope coverage', 'standard activities present')}</div>`;
}

function _issuesByWbs(list) {
  if (!list || !list.length) return '<p class="ai-empty">No phase concentrations — few or no gaps.</p>';
  const max = Math.max(...list.map(x => x.count), 1);
  return list.map(x => `<div class="xd-wbsrow"><span class="nm" title="${escapeHtml(x.name)}">${escapeHtml(x.name)}</span>
    <span class="bar"><i style="width:${Math.round(100 * x.count / max)}%"></i></span><span class="n">${x.count}</span></div>`).join('');
}

function _severity(sev) {
  const c = sev.critical || 0, n = sev.near_critical || 0, tot = c + n;
  if (!tot) return '<p class="ai-empty">No illogical links flagged.</p>';
  const cp = Math.round(100 * c / tot);
  return `<div class="xd-sevbar"><i style="width:${cp}%;background:#dc2626"></i><i style="width:${100 - cp}%;background:#d97706"></i></div>
    <div class="xd-sevleg"><span><span class="dot" style="background:#dc2626"></span>Critical <b>${c}</b></span>
      <span><span class="dot" style="background:#d97706"></span>Near-critical <b>${n}</b></span></div>
    <div class="xd-sevnote">Critical = on / near the critical path (float ≤ 10 working days)</div>`;
}

function _priorityFixes(list) {
  if (!list || !list.length) return '<p class="ai-empty">Nothing critical to fix first — the schedule matches the standard.</p>';
  return list.map((p, i) => {
    const cls = /crit/i.test(p.severity) ? 'c' : (/scope/i.test(p.severity) ? 's' : 'n');
    return `<div class="xd-fix"><div class="rank ${cls}">${i + 1}</div>
      <div class="fx"><div class="ft">${escapeHtml(p.title)}</div><div class="fd">${escapeHtml(p.detail)}</div></div>
      <span class="xd-fw ${cls}">${escapeHtml(p.severity)}</span></div>`;
  }).join('');
}

function _confidenceChip(c) {
  if (!c) return '';
  if (c.forced) return `<span class="xd-conf manual" title="You chose this type — detection bypassed">Type: manual override</span>`;
  const cls = { High: 'high', Medium: 'med', Low: 'low' }[c.level] || 'med';
  return `<span class="xd-conf ${cls}" title="${c.hits} of ${c.signatures} keywords matched · runner-up ${c.runner_up_hits}">Detection confidence: ${c.level}</span>`;
}

function _projectedRow(p) {
  if (!p) return '';
  return `<div class="xd-proj">💡 <b>What-if:</b> correct the flagged logic and this schedule would score
    <b>~${p.overall}</b> (${escapeHtml(p.band_label)}) — ${escapeHtml(p.basis)}.</div>`;
}

function _dashboard(report) {
  const s = report.score;
  if (!s) return '';
  const hex = bandHex(s.band);
  const v = report.verdict || {};
  const flag = { ready: '✅', minor: '🟡', significant: '⚠️', major: '⛔' }[v.kind] || '⚠️';
  return `<div class="xd">
    <div class="xd-verdict ${v.kind || ''}">
      <span class="flag">${flag}</span>
      <div class="vmain"><div class="vt">${escapeHtml(v.title || '')}</div><div class="vd">${escapeHtml(v.detail || v.text || '')}</div></div>
      <div class="vtype"><b>${escapeHtml(report.project_type || '')}</b>${_confidenceChip(report.confidence)}</div>
    </div>
    <div class="xd-hero">
      <div class="xd-gauge">${_gauge(s.overall, hex)}
        <div class="xd-gband" style="background:${hex}22;color:${hex}">${escapeHtml(s.band_label)}</div>
        <div class="xd-glbl">Constructability Score</div></div>
      ${_dims(s, hex)}
    </div>
    ${_legend(s.overall)}
    ${_projectedRow(report.projected)}
    ${_kpis(report.dashboard || {})}
    <div class="xd-cols">
      <div class="xd-panel"><h4>Where the gaps are — issues by WBS phase</h4>${_issuesByWbs(report.issues_by_wbs)}</div>
      <div class="xd-panel"><h4>Severity of illogical links</h4>${_severity(report.severity || {})}</div>
    </div>
  </div>`;
}

function _learnedPanel(l) {
  if (!l || !l.activities || !l.activities.length) return '';
  const rows = l.activities.map(a => `<tr>
    <td>${escapeHtml(a.name)}</td>
    <td class="lp-seen">${a.seen}/${a.imports}<span class="lp-bar"><i style="width:${Math.round(100 * a.seen / a.imports)}%"></i></span></td>
    <td class="lp-dur">${a.avg_duration != null ? a.avg_duration + ' d' : '—'}</td>
    <td>${a.in_schedule ? '<span class="lp-yes">✓ Yes</span>'
      : '<span class="lp-no">✗ Missing</span> <span class="lp-add">consider adding</span>'}</td></tr>`).join('');
  const wbs = (l.wbs || []).map(w => `<span class="lp-chip">${escapeHtml(w.name)} · ${w.seen}/${w.imports}</span>`).join('');
  const t = escapeHtml(l.type);
  return `<div class="mod-sec">Learned from your projects</div>
    <div class="lpanel">
      <div class="lp-h"><h4>Commonly seen in your ${t} projects</h4>
        <span class="lp-badge">◆ Learned · ${l.imports} of your imports</span></div>
      <div class="lp-intro">On top of the curated standard, these activities recur across the
        <b>${l.imports} ${t} schedules you've imported</b> on this PC.
        ${l.missing_count ? `<b>${l.missing_count}</b> ${l.missing_count === 1 ? 'is' : 'are'} not in this schedule — consider adding.`
          : 'All are present in this schedule.'} This sharpens with every project you import.</div>
      <div class="tblwrap" style="overflow-x:auto"><table class="audit-table lp-table">
        <thead><tr><th>Commonly-seen activity (learned)</th><th>Seen in</th><th>Avg duration</th><th>In this schedule?</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      ${wbs ? `<div class="lp-wbs"><span class="lp-lbl">WBS branches your ${t} projects usually have</span>
        <div class="lp-chips">${wbs}</div></div>` : ''}
      <div class="lp-actions">
        <button class="btn-secondary lp-act" data-lact="starter" data-type="${t}">📥 Export as P6 starter baseline</button>
        <button class="btn-secondary lp-act" data-lact="file" data-type="${t}">⬇ Download learned standard</button>
        <span class="lp-note">Advisory · kept separate from the curated findings · reflects only projects imported on this PC.</span>
      </div>
    </div>`;
}

function _typeSelect(report) {
  const cur = report.detected ? report.detected.type : '';
  const opts = (report.available_types || []).map(t =>
    `<option value="${escapeHtml(t.type)}" ${t.type === cur ? 'selected' : ''}>${escapeHtml(t.category)} › ${escapeHtml(t.type)}</option>`).join('');
  return `<select id="ct-type" class="ct-select"><option value="">— auto-detect —</option>${opts}</select>`;
}

// Type dropdown with a caller-chosen id, pre-selected to the detected type (used
// by the "Add to Database" EPS picker so the user confirms/changes the filing).
function _typeSelectFor(report, id) {
  const cur = state.constructForcedType || (report.detected ? report.detected.type : '');
  const opts = (report.available_types || []).map(t =>
    `<option value="${escapeHtml(t.type)}" ${t.type === cur ? 'selected' : ''}>${escapeHtml(t.category)} › ${escapeHtml(t.type)}</option>`).join('');
  return `<select id="${id}" class="ct-select">${opts}</select>`;
}

// ── report + prompt rendering ──────────────────────────────────────────────

function renderReport(report) {
  const body = document.getElementById('construct-body');
  if (!body) return;
  if (!report.detected) { renderPick(report); return; }
  const draft = (report.detected.status === 'draft')
    ? '<span class="ct-draft" title="Starter knowledge — confirm before relying on it">draft KB</span>' : '';
  body.innerHTML = `
    <div class="ai-filebar">
      <div class="fb"><span class="k">Detected project sub-type</span>
        <span class="v ai-type">${escapeHtml(report.project_type)}</span> ${draft}</div>
      <div class="fb"><span class="k">Engine</span><span class="v">Rule + Knowledge Base · offline</span></div>
      ${report.knowledge_enhanced ? `<div class="fb"><span class="k">Knowledge</span>
        <span class="v ai-enh" title="Checking against the standard plus what the tool learned from schedules you added for this type">✦ Standard + your ${(report.learned && report.learned.imports) || 0} schedule(s)</span></div>` : ''}
      <div class="fb"><span class="k">Change sub-type</span>${_typeSelect(report)}</div>
    </div>
    <div class="ai-banner"><span class="spark">🧠</span>
      <span class="txt"><b>Findings from the local Knowledge Base + rule checks — offline, no AI, no cost.</b>
      Advisory: review before acting; it never changes your schedule. Kept separate from the exact rule-based audits.</span></div>

    <div class="xd-exportbar">
      <button class="btn-secondary" id="cx-adddb">➕ Add to Database</button>
      <button class="btn-secondary" id="cx-xls">📊 Export Excel</button>
      <button class="btn-primary" id="cx-pdf">📄 Print Preview</button>
    </div>
    <div class="cx-eps hidden" id="cx-eps-row">
      <label for="cx-eps-select">Add this schedule to the Database under (EPS):</label>
      ${_typeSelectFor(report, 'cx-eps-select')}
      <button class="btn-primary" id="cx-eps-save">Save to Database</button>
      <span id="cx-eps-note" class="cx-eps-note"></span>
    </div>
    ${_dashboard(report)}
    <div class="mod-sec">Illogical relationships &amp; better logic</div>
    ${_illogicalTable(report.illogical)}
    <div class="mod-sec">Missing activities</div>
    ${_missingTable(report.missing)}
    <div class="mod-sec">WBS review &amp; missing WBS</div>
    ${_wbsReview(report.wbs_review, report.missing_wbs)}
    ${_learnedPanel(report.learned)}
    <div class="mod-sec">Executive conclusion</div>
    <div class="ai-concl"><div class="lead">Constructability — rule + knowledge base</div>${escapeHtml(report.conclusion || '')}</div>`;

  const sel = document.getElementById('ct-type');
  if (sel) sel.addEventListener('change', () => fetchAndRender(sel.value || null));
  const pdf = document.getElementById('cx-pdf');
  if (pdf) pdf.addEventListener('click', () => previewReport(pdf));
  const xls = document.getElementById('cx-xls');
  if (xls) xls.addEventListener('click', () => exportReport('excel', xls));
  const adb = document.getElementById('cx-adddb');
  if (adb) adb.addEventListener('click', () => {
    document.getElementById('cx-eps-row')?.classList.toggle('hidden');
  });
  const save = document.getElementById('cx-eps-save');
  if (save) save.addEventListener('click', () => {
    const s = document.getElementById('cx-eps-select');
    addToDatabase((s && s.value) || null, save);
  });
  document.querySelectorAll('.lp-act').forEach(b =>
    b.addEventListener('click', () => exportLearned(b.dataset.lact, b.dataset.type, b)));
}

async function exportLearned(kind, type, btn) {
  const slug = (type || 'learned').replace(/[^\w]+/g, '_').replace(/^_+|_+$/g, '');
  const isStarter = kind === 'starter';
  const ext = isStarter ? 'xml' : 'json';
  const name = isStarter ? `${slug}_learned_starter.xml` : `${slug}_learned_standard.json`;
  let path = null;
  try { path = await window.pywebview.api.choose_save_path(name, ext); }
  catch { showError('Could not open the save dialog.'); return; }
  if (!path) return;
  const orig = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try {
    const url = isStarter ? '/api/kb/starter-xml' : '/api/kb/learned-file';
    const resp = await fetch(`http://localhost:${state.serverPort}${url}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, output_path: path }),
    });
    const data = await resp.json();
    if (!data.ok) showError(data.error || 'Export failed.');
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = orig; }
  }
}

async function previewReport(btn) {
  const rep = state.constructReport;
  if (!rep || !rep.detected) return;
  const orig = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Preparing preview…'; }
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/constructability/report`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report: rep, preview: true }),
    });
    const data = await resp.json();
    if (!data.ok || !data.html) { showError(data.error || 'Preview failed.'); return; }
    showReportPreview({
      title: 'Constructability Review — print preview',
      subtitle: rep.project_type || '',
      html: data.html,
      onSave: () => saveReportPdf(rep),
    });
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = orig; }
  }
}

async function saveReportPdf(rep) {
  const slug = (rep.detected.type || 'constructability').replace(/[^\w]+/g, '_').replace(/^_+|_+$/g, '');
  const path = await window.pywebview.api.choose_save_path(`${slug}_constructability.pdf`, 'pdf');
  if (!path) return false;
  const resp = await fetch(`http://localhost:${state.serverPort}/api/constructability/report`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ report: rep, output_path: path }),
  });
  const data = await resp.json();
  if (!data.ok) { showError(data.error || 'PDF generation failed.'); return false; }
  return true;
}

async function addToDatabase(type, btn) {
  const rep = state.constructReport;
  const note = document.getElementById('cx-eps-note');
  if (!rep || (!state.currentXmlPath && !state.currentCachedPath)) return;
  if (!type) { if (note) { note.textContent = 'Pick a project type first.'; note.className = 'cx-eps-note warn'; } return; }
  const orig = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  if (note) { note.textContent = ''; note.className = 'cx-eps-note'; }
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/database/add`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        xml_path: state.currentXmlPath, cached_path: state.currentCachedPath, forced_type: type,
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      showError(data.error || 'Could not add to the Construction Database.');
      if (note) { note.textContent = data.error || 'Failed.'; note.className = 'cx-eps-note warn'; }
    } else {
      state.dbLibrary = null;   // force the Database + learned views to reload
      if (note) {
        note.textContent = `✓ Added to ${data.type} — ${data.activities} activities. It now also teaches the tool this project type.`;
        note.className = 'cx-eps-note ok';
      }
    }
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = orig; }
  }
}

async function exportReport(kind, btn) {
  const rep = state.constructReport;
  if (!rep || !rep.detected) return;
  const slug = (rep.detected.type || 'constructability').replace(/[^\w]+/g, '_').replace(/^_+|_+$/g, '');
  const ext = kind === 'pdf' ? 'pdf' : 'xlsx';
  let path = null;
  try { path = await window.pywebview.api.choose_save_path(`${slug}_constructability.${ext}`, ext); }
  catch { showError('Could not open the save dialog.'); return; }
  if (!path) return;
  const orig = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try {
    const url = kind === 'pdf' ? '/api/constructability/report' : '/api/constructability/excel';
    const resp = await fetch(`http://localhost:${state.serverPort}${url}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report: rep, output_path: path }),
    });
    const data = await resp.json();
    if (!data.ok) showError(data.error || 'Export failed.');
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = orig; }
  }
}

function renderPick(report) {
  const body = document.getElementById('construct-body');
  if (!body) return;
  body.innerHTML = `
    <div class="ai-prompt">
      <div class="ai-prompt-t">Pick the project type to review against</div>
      <div class="ai-prompt-d">${escapeHtml(report.conclusion || 'Choose the sub-type from the Knowledge Base.')}</div>
      <div class="ct-pickrow">${_typeSelect(report)}
        <button class="btn-primary" id="ct-go">Review</button></div>
    </div>`;
  const go = document.getElementById('ct-go');
  if (go) go.addEventListener('click', () => {
    const sel = document.getElementById('ct-type');
    fetchAndRender((sel && sel.value) || null);
  });
}

async function fetchAndRender(forcedType) {
  const body = document.getElementById('construct-body');
  if (!state.currentXmlPath && !state.currentCachedPath) {
    if (body) body.innerHTML = '<p class="ai-empty">Open a schedule first, then the Constructability Review runs automatically.</p>';
    return;
  }
  clearError();
  if (body) body.innerHTML = '<div class="cmp-loading">Reviewing against the Knowledge Base…</div>';
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/constructability`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        xml_path: state.currentXmlPath, cached_path: state.currentCachedPath,
        forced_type: forcedType || null,
      }),
    });
    const data = await resp.json();
    if (!data.ok) { showError(data.error || 'Constructability review failed.'); return; }
    state.constructReport = data.report;
    state.constructForcedType = forcedType || null;
    renderReport(data.report);
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  }
}

export function renderConstructPanel() {
  if (state.constructReport) { renderReport(state.constructReport); return; }
  fetchAndRender(state.constructForcedType || null);
}
