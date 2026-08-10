// Constructability Review — rule-based, offline, powered by the local Knowledge
// Base (Decision 009). No AI, no key, no cost. Runs when the tab is opened.
// Reuses the approved review-report layout (.ai-* styles) and the shared helpers.

import { state }                                    from './state.js';
import { showError, clearError }                    from './render.js';
import { escapeHtml }                               from './format.js';
import { bandHex, kindClass, markerLeft, impactPill } from './aireview_helpers.js';

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

function _illogicalTable(rows) {
  if (!rows || !rows.length) {
    return '<p class="ai-empty">No illogical relationships flagged — the sequence logic matches the Knowledge Base rules.</p>';
  }
  const body = rows.map(r => `<tr>
    <td class="mono">${escapeHtml(r.activity_id)}</td>
    <td>${escapeHtml(r.activity_name)}</td>
    <td class="mut" title="${escapeHtml(r.wbs_path || '')}">${escapeHtml(r.wbs_path || '')}</td>
    <td class="sepL">${_idStack(r.current_preds)}</td><td>${_nameStack(r.current_preds)}</td>
    <td>${_idStack(r.current_succs)}</td><td>${_nameStack(r.current_succs)}</td>
    <td class="ai-why sepL">${escapeHtml(r.why || '')}</td>
    <td class="sepL">${_idStack(r.suggested_preds)}</td><td>${_nameStack(r.suggested_preds)}</td>
    <td>${_idStack(r.suggested_succs)}</td><td>${_nameStack(r.suggested_succs)}</td>
    <td>${impactPill(r.impact)}</td>
    <td><span class="ai-basis">${escapeHtml(r.source || '')}</span></td></tr>`).join('');
  return `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table ai-table">
    <thead>
      <tr><th rowspan="2">Activity ID</th><th rowspan="2">Activity Name</th><th rowspan="2">WBS Path</th>
        <th colspan="4" class="ai-gh-cur sepL">Current driving links</th>
        <th rowspan="2" class="sepL">Why it's illogical</th>
        <th colspan="4" class="ai-gh-sug sepL">Suggested links</th>
        <th rowspan="2">Impact</th><th rowspan="2">Source</th></tr>
      <tr><th class="sepL">Pred. ID</th><th>Pred. Name</th><th>Succ. ID</th><th>Succ. Name</th>
        <th class="sepL">Pred. ID</th><th>Pred. Name</th><th>Succ. ID</th><th>Succ. Name</th></tr>
    </thead><tbody>${body}</tbody></table></div>
    <div class="ai-foot">Activities can have several predecessors / successors — all listed.
      <span class="ai-tag-add" style="margin:0">ADD</span> add a link ·
      <span class="ai-tag-rem" style="margin:0">REMOVE</span> a redundant link to delete (struck through).</div>`;
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

function _score(s) {
  if (!s) return '';
  const hex = bandHex(s.band);
  const bar = (label, val) => `<div>
    <div class="ai-part-h"><span>${label}</span><b>${val} / 100</b></div>
    <div class="ai-bar"><i style="width:${markerLeft(val)}%;background:${hex}"></i></div></div>`;
  return `<div class="ai-score-hero">
    <div class="ai-score-main">
      <div class="ai-score-num" style="color:${hex}">${s.overall}<span>/100</span></div>
      <div class="ai-score-band" style="background:${hex}22;color:${hex}">${escapeHtml(s.band_label)}</div>
      <div class="ai-score-label">Constructability Score</div>
    </div>
    <div class="ai-score-parts">
      ${bar('① Sequence logic <em>(weight 45%)</em>', s.logic)}
      ${bar('② Completeness <em>(weight 45%)</em>', s.completeness)}
      ${bar('③ Structure &amp; load <em>(weight 10%)</em>', s.structure)}
      <div class="ai-how">Weighted <b>45% logic · 45% completeness · 10% structure</b>. Logic &amp; completeness
        = 100 − (their % × sensitivity); structure reflects missing WBS + how many fixes were suggested.
        Bands: 85+ Ready · 70–84 Minor gaps · 50–69 Significant · under 50 Major.</div>
    </div></div>`;
}

function _typeSelect(report) {
  const cur = report.detected ? report.detected.type : '';
  const opts = (report.available_types || []).map(t =>
    `<option value="${escapeHtml(t.type)}" ${t.type === cur ? 'selected' : ''}>${escapeHtml(t.category)} › ${escapeHtml(t.type)}</option>`).join('');
  return `<select id="ct-type" class="ct-select"><option value="">— auto-detect —</option>${opts}</select>`;
}

// ── report + prompt rendering ──────────────────────────────────────────────

function renderReport(report) {
  const body = document.getElementById('construct-body');
  if (!body) return;
  if (!report.detected) { renderPick(report); return; }
  const d = report.dashboard || {};
  const draft = (report.detected.status === 'draft')
    ? '<span class="ct-draft" title="Starter knowledge — confirm before relying on it">draft KB</span>' : '';
  body.innerHTML = `
    <div class="ai-filebar">
      <div class="fb"><span class="k">Detected project sub-type</span>
        <span class="v ai-type">${escapeHtml(report.project_type)}</span> ${draft}</div>
      <div class="fb"><span class="k">Engine</span><span class="v">Rule + Knowledge Base · offline</span></div>
      <div class="fb"><span class="k">Change sub-type</span>${_typeSelect(report)}</div>
    </div>
    <div class="ai-banner"><span class="spark">🧠</span>
      <span class="txt"><b>Findings from the local Knowledge Base + rule checks — offline, no AI, no cost.</b>
      Advisory: review before acting; it never changes your schedule. Kept separate from the exact rule-based audits.</span></div>

    <div class="ai-headline">
      <div class="hl"><div class="big">${d.illogical_count ?? 0} <span class="pct">${d.illogical_pct ?? 0}%</span></div>
        <div class="lbl">Illogical relationships</div><div class="sub">of ${d.total_relationships ?? 0} relationships</div></div>
      <div class="hl"><div class="big">${d.missing_count ?? 0} <span class="pct">${d.missing_pct ?? 0}%</span></div>
        <div class="lbl">Missing activities</div><div class="sub">of ${d.total_activities ?? 0} · vs standard</div></div>
      <div class="hl"><div class="big">${d.missing_wbs ?? 0}</div>
        <div class="lbl">Missing WBS branches</div><div class="sub">${d.critical_affected ? 'critical path affected' : 'vs standard WBS'}</div></div>
    </div>

    <div class="mod-sec">Constructability Score</div>
    ${_score(report.score)}
    <div class="mod-sec">Illogical relationships &amp; better logic</div>
    ${_illogicalTable(report.illogical)}
    <div class="mod-sec">Missing activities</div>
    ${_missingTable(report.missing)}
    <div class="mod-sec">WBS review &amp; missing WBS</div>
    ${_wbsReview(report.wbs_review, report.missing_wbs)}
    <div class="mod-sec">Executive conclusion</div>
    <div class="ai-concl"><div class="lead">Constructability — rule + knowledge base</div>${escapeHtml(report.conclusion || '')}</div>`;

  const sel = document.getElementById('ct-type');
  if (sel) sel.addEventListener('change', () => fetchAndRender(sel.value || null));
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
