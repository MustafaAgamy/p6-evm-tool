// AI Constructability Review — the optional AI layer (Decision 003/004).
// Reviews the open baseline for construction-logic sense and scope completeness.
// Everything shown is clearly-labelled AI opinion; the only step that goes online
// is Run, which the user presses.

import { state }                                    from './state.js';
import { showError, clearError }                    from './render.js';
import { escapeHtml }                               from './format.js';
import { bandHex, kindClass, markerLeft, impactPill } from './aireview_helpers.js';

// ── Rendering ──────────────────────────────────────────────────────────────

function _idStack(list) {
  if (!list || !list.length) return '<span class="mut">—</span>';
  return list.map(l => {
    const cls = kindClass(l.kind);
    const rel = l.rel ? `<span class="ai-rel">${escapeHtml(l.rel)}</span>` : '';
    const id = escapeHtml(l.id || '');
    return `<div class="ai-stk ${cls}">${cls === 'ai-rem' ? `<s>${id}</s>` : id}${rel}` +
           (l.kind === 'remove' ? ' <span class="ai-tag-rem">REMOVE</span>'
            : l.kind === 'add' ? ' <span class="ai-tag-add">ADD</span>' : '') + `</div>`;
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
    return '<p class="ai-empty">No illogical relationships flagged — the AI found the sequence logic sound.</p>';
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
    <td>${impactPill(r.impact)}</td></tr>`).join('');
  return `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table ai-table">
    <thead>
      <tr><th rowspan="2">Activity ID</th><th rowspan="2">Activity Name</th><th rowspan="2">WBS Path</th>
        <th colspan="4" class="ai-gh-cur sepL">Current driving links</th>
        <th rowspan="2" class="sepL">Why it's illogical</th>
        <th colspan="4" class="ai-gh-sug sepL">Suggested links</th>
        <th rowspan="2">Impact</th></tr>
      <tr><th class="sepL">Pred. ID</th><th>Pred. Name</th><th>Succ. ID</th><th>Succ. Name</th>
        <th class="sepL">Pred. ID</th><th>Pred. Name</th><th>Succ. ID</th><th>Succ. Name</th></tr>
    </thead><tbody>${body}</tbody></table></div>
    <div class="ai-foot">Activities can have several predecessors / successors — all are listed.
      <span class="ai-tag-add" style="margin:0">ADD</span> add a link ·
      <span class="ai-tag-rem" style="margin:0">REMOVE</span> a redundant link to delete (struck through).</div>`;
}

function _missingTable(rows) {
  if (!rows || !rows.length) {
    return '<p class="ai-empty">No missing activities flagged — the scope looks complete for this project type.</p>';
  }
  const body = rows.map(r => `<tr>
    <td class="mono">${escapeHtml(r.suggested_id)}</td>
    <td>${escapeHtml(r.name)}</td>
    <td>${r.new_wbs ? '<span class="ai-newwbs">＋ new</span> ' : ''}${escapeHtml(r.wbs || '')}</td>
    <td>${_idStack(r.preds)}</td><td>${_nameStack(r.preds)}</td>
    <td>${_idStack(r.succs)}</td><td>${_nameStack(r.succs)}</td>
    <td class="ai-why">${escapeHtml(r.why || '')}</td>
    <td><span class="ai-basis">${escapeHtml(r.basis || 'AI knowledge')}</span></td></tr>`).join('');
  return `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table ai-table">
    <thead><tr><th>Suggested ID</th><th>Activity Name</th><th>Where it belongs (WBS)</th>
      <th>Pred. ID</th><th>Pred. Name</th><th>Succ. ID</th><th>Succ. Name</th>
      <th>Why it's normally needed</th><th>Basis</th></tr></thead>
    <tbody>${body}</tbody></table></div>
    <div class="ai-foot">Suggested IDs are checked against the baseline so none clash with an existing activity ID.
      <span class="ai-newwbs" style="margin:0">＋ new</span> = a WBS branch proposed where none suited.</div>`;
}

function _wbsReview(rows, missingWbs) {
  const items = (rows || []).map(w => {
    const miss = w.status === 'missing';
    const partial = w.status === 'partial';
    const mk = miss ? '<span class="ai-mk x">⚠</span>' : partial ? '<span class="ai-mk p">◐</span>' : '<span class="ai-mk ok">✓</span>';
    return `<div class="ai-wbs-row ${miss ? 'miss' : ''}">${mk}<span class="nm">${escapeHtml(w.name)}</span>
      <span class="rz">${escapeHtml(w.note || '')}</span></div>`;
  }).join('');
  const missing = (missingWbs || []).map(w => `<div class="ai-wbs-row miss">
    <span class="ai-mk x">⚠</span><span class="nm">${escapeHtml(w.name)} — <b>suggested new branch</b></span>
    <span class="rz">${escapeHtml(w.why || '')}</span></div>`).join('');
  if (!items && !missing) return '<p class="ai-empty">No WBS notes.</p>';
  return `<div class="ai-wbs">${items}${missing}</div>`;
}

function _score(s) {
  const hex = bandHex(s.band);
  const bar = (label, val) => `<div>
    <div class="ai-part-h"><span>${label}</span><b>${val} / 100</b></div>
    <div class="ai-bar"><i style="width:${markerLeft(val)}%;background:${hex}"></i></div></div>`;
  return `<div class="ai-score-hero">
    <div class="ai-score-main">
      <div class="ai-score-num" style="color:${hex}">${s.overall}<span>/100</span></div>
      <div class="ai-score-band" style="background:${hex}22;color:${hex}">${escapeHtml(s.band_label)}</div>
      <div class="ai-score-label">Baseline Constructability Score</div>
    </div>
    <div class="ai-score-parts">
      ${bar('① Sequence logic <em>(weight 45%)</em>', s.logic)}
      ${bar('② Completeness <em>(weight 45%)</em>', s.completeness)}
      ${bar('③ Structure &amp; advisory load <em>(weight 10%)</em>', s.structure)}
      <div class="ai-how">Weighted <b>45% logic · 45% completeness · 10% structure</b>. Logic &amp; completeness =
        100 − (their % × sensitivity); structure reflects missing WBS and how many fixes the AI had to suggest.
        Bands: 85+ Ready to baseline · 70–84 Minor gaps · 50–69 Significant · under 50 Major.</div>
    </div></div>
    <div class="ai-legend"><div class="ai-gauge">
      <div class="seg" style="width:50%;background:var(--danger)">0–49 Major</div>
      <div class="seg" style="width:20%;background:var(--chart-3)">50–69 Significant</div>
      <div class="seg" style="width:15%;background:var(--warning)">70–84 Minor</div>
      <div class="seg" style="width:15%;background:var(--success)">85–100 Ready</div>
      <div class="ai-marker" style="left:${markerLeft(s.overall)}%"><b>You: ${s.overall} · ${escapeHtml(s.band_label)}</b></div>
    </div></div>`;
}

export function renderAiReport(report) {
  const body = document.getElementById('aireview-body');
  if (!body) return;
  const d = report.dashboard || {};
  const u = report.understood || {};
  const chips = (u.phases || []).map(p =>
    `<span class="ai-chip ${p.present ? 'ok' : 'miss'}">${escapeHtml(p.name)} ${p.present ? '✓' : '— missing'}</span>`).join('');
  body.innerHTML = `
    <div class="ai-filebar">
      <div class="fb"><span class="k">Detected project type</span><span class="v ai-type">${escapeHtml(report.project_type || '—')}</span></div>
      <div class="fb"><span class="k">Mode</span><span class="v">${report.mode === 'reference' ? '② Reference-based' : '① Engineering review'}</span></div>
      <button class="btn-mini" id="ai-rerun">⟲ Re-run</button>
    </div>
    <div class="ai-banner"><span class="spark">✦</span>
      <span class="txt"><b>AI Engineering Observations — advisory opinion, not hard facts.</b> Every finding carries the AI's reasoning.
      Nothing here changes your schedule; you decide what to act on. Kept separate from the tool's exact rule-based checks.</span></div>

    <div class="ai-headline">
      <div class="hl"><div class="big">${d.illogical_count ?? 0} <span class="pct">${d.illogical_pct ?? 0}%</span></div>
        <div class="lbl">Illogical relationships</div><div class="sub">of ${d.total_relationships ?? 0} relationships</div></div>
      <div class="hl"><div class="big">${d.missing_count ?? 0} <span class="pct">${d.missing_pct ?? 0}%</span></div>
        <div class="lbl">Missing activities</div><div class="sub">of ${d.total_activities ?? 0} activities</div></div>
      <div class="hl"><div class="big">${d.missing_wbs ?? 0}</div>
        <div class="lbl">Missing WBS branches</div><div class="sub">${d.critical_affected ? 'critical path affected' : 'can be suggested'}</div></div>
    </div>

    <div class="mod-sec">Baseline Constructability Score</div>
    ${_score(report.score || {})}

    <div class="mod-sec">1 · What the AI understood</div>
    <div class="ai-understood">${escapeHtml(u.summary || '')}<div class="ai-chips">${chips}</div></div>

    <div class="mod-sec">2 · Illogical relationships &amp; better logic</div>
    ${_illogicalTable(report.illogical)}

    <div class="mod-sec">3 · Missing activities</div>
    ${_missingTable(report.missing)}

    <div class="mod-sec">4 · WBS review &amp; missing WBS</div>
    ${_wbsReview(report.wbs_review, report.missing_wbs)}

    <div class="mod-sec">Executive conclusion</div>
    <div class="ai-concl"><div class="lead">✦ AI engineering opinion — advisory</div>${escapeHtml(report.conclusion || '')}</div>`;

  const rerun = document.getElementById('ai-rerun');
  if (rerun) rerun.addEventListener('click', () => { state.aiReport = null; renderAiReviewPanel(); });
}

function renderLaunch() {
  const body = document.getElementById('aireview-body');
  if (!body) return;
  const refName = state.aiReferenceName
    ? `<b>${escapeHtml(state.aiReferenceName)}</b> attached — Mode 2`
    : 'none added — running Mode 1';
  body.innerHTML = `
    <div class="ai-prompt">
      <div class="ai-prompt-t">AI Constructability Review — is this baseline complete &amp; logical?</div>
      <div class="ai-prompt-d">The AI studies how the project is built for its type, then flags illogical links (and why),
        suggests better links, finds missing activities and missing WBS, and gives a Constructability Score.</div>
      <div class="ai-typelist">🏗️ Auto-detects the project type — Infrastructure, Industrial, Roads, Residential,
        Administrative, Hospital, Airport, Landscape — and works out any other type from the schedule.</div>
      <div class="ai-modes">
        <div class="ai-mode on"><div class="h">① AI Engineering Review <span class="badge">Always on</span></div>
          <div class="d">Uses the AI's own construction knowledge. No setup — reviews any baseline immediately.</div></div>
        <div class="ai-mode"><div class="h">② Reference-Based Validation <span class="badge opt">Optional</span></div>
          <div class="d">Add a proven baseline, template or standard WBS. It <b>outranks</b> general AI knowledge.</div>
          <div class="ai-mode-file"><button class="btn-mini" id="ai-add-ref">＋ Add reference file</button>
            <span class="fname">${refName}</span>${state.aiReferenceName ? ' <button class="btn-mini" id="ai-clear-ref">clear</button>' : ''}</div></div>
      </div>
      <div class="ai-privacy">🔒 <b>Private by default.</b> Nothing leaves your machine until you press Run.
        It then sends only the schedule's skeleton — activity names, durations, links and WBS — with costs and
        client name stripped first. Needs internet for this step; nothing stored online.</div>
      <div class="ai-run"><button class="btn-primary" id="ai-run-btn">✦ Run AI Review</button>
        <span class="hint">≈ 20–40 seconds</span></div>
    </div>`;
  document.getElementById('ai-run-btn').addEventListener('click', runAiReview);
  const addRef = document.getElementById('ai-add-ref');
  if (addRef) addRef.addEventListener('click', chooseReference);
  const clearRef = document.getElementById('ai-clear-ref');
  if (clearRef) clearRef.addEventListener('click', () => {
    state.aiReferencePath = null; state.aiReferenceName = null; renderLaunch();
  });
}

function renderSetup(note) {
  const body = document.getElementById('aireview-body');
  if (!body) return;
  body.innerHTML = `
    <div class="ai-prompt">
      <div class="ai-prompt-t">Set up the AI review</div>
      <div class="ai-prompt-d">This is the one feature that uses a cloud AI. Paste your <b>Anthropic API key</b> —
        it's stored only on this machine and used only for the review you run.
        Get one at <span class="mono">console.anthropic.com</span>.</div>
      <div class="ai-privacy">💡 <b>The app is free — you only pay for AI you run.</b> A review costs roughly
        <b>5–15¢</b> on a cost-efficient high-quality model, and nothing is charged unless you press Run.
        Tip: set a monthly spending cap on your Anthropic account so it can never surprise you.</div>
      ${note ? `<div class="ai-privacy" style="border-left-color:var(--warning)">${escapeHtml(note)}</div>` : ''}
      <div class="ai-key-row">
        <input type="password" id="ai-key-input" class="ai-key-input" placeholder="sk-ant-…" autocomplete="off">
        <button class="btn-primary" id="ai-key-save">Save key</button>
      </div>
      <div class="ai-privacy">🔒 The key is written to your per-user app folder, never to the app files or any project.</div>
    </div>`;
  document.getElementById('ai-key-save').addEventListener('click', saveKey);
}

async function saveKey() {
  const input = document.getElementById('ai-key-input');
  const key = (input && input.value || '').trim();
  if (!key) { showError('Paste your Anthropic API key first.'); return; }
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/ai/settings`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key }),
    });
    const data = await resp.json();
    if (data.has_key) { clearError(); renderLaunch(); }
    else showError('Could not save the key. Try again.');
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}

async function chooseReference() {
  const path = await window.pywebview.api.choose_file();
  if (!path) return;
  state.aiReferencePath = path;
  state.aiReferenceName = path.split(/[\\/]/).pop();
  renderLaunch();
}

export async function runAiReview() {
  if (!state.currentXmlPath && !state.currentCachedPath) {
    showError('Open a schedule first, then run the AI review.');
    return;
  }
  clearError();
  const body = document.getElementById('aireview-body');
  if (body) body.innerHTML = '<div class="cmp-loading">Running AI review… this takes 20–40 seconds.</div>';
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/ai-review`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        xml_path: state.currentXmlPath,
        cached_path: state.currentCachedPath,
        reference_path: state.aiReferencePath,
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      if (data.code === 'no_key') { renderSetup('No API key is set — add one to run the review.'); return; }
      showError(data.error || 'The AI review failed.');
      renderLaunch();
      return;
    }
    state.aiReport = data.report;
    renderAiReport(data.report);
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
    renderLaunch();
  }
}

export async function renderAiReviewPanel() {
  const body = document.getElementById('aireview-body');
  if (!body) return;
  if (state.aiReport) { renderAiReport(state.aiReport); return; }
  body.innerHTML = '<div class="cmp-loading">Checking AI setup…</div>';
  let hasKey = false;
  try {
    const r = await fetch(`http://localhost:${state.serverPort}/api/ai/settings`);
    hasKey = (await r.json()).has_key;
  } catch { /* offline — still show launch; the run will surface the error */ hasKey = true; }
  if (!hasKey) { renderSetup(); return; }
  renderLaunch();
}
