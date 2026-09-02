// Preview ▸ AI Copilot · TIA.
// Deterministic, offline core — a Time-Impact Analysis and prioritised insights
// built server-side (p6_evm/copilot) from the already-computed result. The
// optional AI narrative (the existing key-gated AI review) is layered underneath
// by reusing renderAiReviewPanel — so everything above works with no account.
import { state } from './state.js';
import { escapeHtml, fmtDate } from './format.js';
import { renderAiReviewPanel } from './aireview.js';

const SEV_LABEL = { high: 'High', med: 'Medium', low: 'Low' };
const dCls = (d) => (d == null ? '' : (d > 0 ? 'bad' : (d < 0 ? 'good' : '')));
const dTxt = (d) => (d == null ? '—' : `${d > 0 ? '+' : ''}${d} d`);

export async function renderCopilot() {
  const el = document.getElementById('copilot-body');
  if (!el) return;
  if (!state.currentResult) {
    el.innerHTML = `
      <div class="ov-head"><div class="ov-title"><h2>AI Copilot · TIA</h2></div></div>
      <p class="ov-note">Import a P6 schedule first — the copilot analyses that update's metrics.</p>`;
    return;
  }
  el.innerHTML = `<div class="cp-loading">Analysing the schedule…</div>`;

  let d;
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/copilot`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot_id: state.currentSnapshotId || null, result: state.currentResult }),
    });
    d = await resp.json();
  } catch (e) {
    el.innerHTML = `<div class="cp-empty">Couldn't run the copilot — ${escapeHtml(String((e && e.message) || e))}.</div>`;
    return;
  }
  if (!d || !d.ok) {
    el.innerHTML = `<div class="cp-empty">Couldn't run the copilot.${d && d.error ? ' ' + escapeHtml(d.error) : ''}</div>`;
    return;
  }

  const r = state.currentResult;
  const tia = d.tia || {};
  const comps = tia.components || [];
  const maxDays = Math.max(1, ...comps.map((c) => Math.abs(c.days || 0)));

  // ── Time-Impact Analysis ──
  let tiaHtml;
  if (comps.length) {
    const bars = comps.map((c) => `
      <div class="cp-tia-row">
        <div class="cp-tia-lbl">${escapeHtml(c.label)}<span>${escapeHtml(c.basis)}</span></div>
        <div class="cp-tia-track"><div class="cp-tia-fill ${c.days > 0 ? 'bad' : 'good'}" style="width:${(Math.abs(c.days) / maxDays * 100).toFixed(1)}%"></div></div>
        <div class="cp-tia-days ${dCls(c.days)}">${dTxt(c.days)}</div>
      </div>`).join('');
    tiaHtml = `
      <div class="cp-tia-head">
        <div><span class="cp-k">Baseline finish</span><b>${tia.baseline_finish ? fmtDate(tia.baseline_finish) : '—'}</b></div>
        <div class="cp-arrow">→</div>
        <div><span class="cp-k">Likely finish</span><b>${tia.likely_finish ? fmtDate(tia.likely_finish) : '—'}</b></div>
        <div class="cp-tia-total ${dCls(tia.likely_slip)}"><span class="cp-k">Total impact</span><b>${dTxt(tia.likely_slip)}</b></div>
      </div>
      <div class="cp-tia-rows">${bars}</div>
      <p class="cp-tia-note">The finish slip decomposed into what's driving it. Worst-case adds weather (${tia.worst_finish ? fmtDate(tia.worst_finish) + `, ${dTxt(tia.worst_slip)}` : 'run weather in Calendar Audit'}).</p>`;
  } else {
    tiaHtml = `<p class="ov-note">No finish forecast is available — the schedule needs a finish milestone and a baseline for a Time-Impact Analysis.</p>`;
  }

  // ── Insights ──
  const insights = (d.insights || []).map((i) => `
    <div class="cp-ins cp-${i.severity}">
      <div class="cp-ins-sev">${SEV_LABEL[i.severity] || ''}</div>
      <div class="cp-ins-body"><b>${escapeHtml(i.title)}</b><p>${escapeHtml(i.detail)}</p></div>
    </div>`).join('');

  el.innerHTML = `
    <div class="ov-head"><div class="ov-title">
      <h2>AI Copilot · TIA</h2>
      <div class="ov-chips">
        <span class="ov-chip">${escapeHtml(r.project_name || 'Project')}</span>
        <span class="ov-chip">${(d.insights || []).length} insight${(d.insights || []).length === 1 ? '' : 's'}</span>
        <span class="ov-chip cp-chip-offline">offline · deterministic</span>
      </div>
    </div></div>

    <div class="ov-section-label">Time-Impact Analysis</div>
    <div class="cp-card">${tiaHtml}</div>

    <div class="ov-section-label">Copilot insights <span class="cp-sub">most severe first</span></div>
    <div class="cp-insights">${insights}</div>

    <div class="ov-section-label">AI narrative <span class="cp-sub">optional · uses your Anthropic key</span></div>
    <div class="cp-ai">
      <p class="cp-ai-note">Everything above is generated on your machine with no account. For an AI-written deep-dive, add an Anthropic API key in <b>Tools ▸ Settings</b>; the panel below runs the cloud review only when you choose to.</p>
      <div id="aireview-body"></div>
    </div>
    <p class="ov-note">Deterministic Time-Impact Analysis and insights from this update's metrics — always available offline. The AI narrative is an optional layer, not a dependency.</p>`;

  // mount the existing (key-gated) AI review into the hosted container
  try { renderAiReviewPanel(); } catch { /* AI layer is optional */ }
}
