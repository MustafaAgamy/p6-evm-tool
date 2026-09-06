// Project ▸ Baseline Narrative.
// A deterministic, plain-English status narrative for the open project, built
// server-side (p6_evm/narrative.build_narrative) from the already-computed
// result — no LLM, no re-parse. Reads the DB result for the current snapshot,
// falling back to the result already in state.
import { state } from './state.js';
import { escapeHtml } from './format.js';

const TONE_WORD = { good: 'On track', warn: 'Watch', bad: 'Action needed', neutral: '' };

let _print = null;   // printable sections for the global File ▸ Print flow
export function narrativePrint() { return _print; }

export async function renderNarrative() {
  const el = document.getElementById('narrative-body');
  if (!el) return;
  if (!state.currentResult) {
    el.innerHTML = `
      <div class="ov-head"><div class="ov-title"><h2>Baseline Narrative</h2></div></div>
      <p class="ov-note">Import a P6 schedule first — the narrative is written from that update's metrics.</p>`;
    return;
  }
  el.innerHTML = `<div class="narr-loading">Writing the narrative…</div>`;

  let data;
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/narrative`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot_id: state.currentSnapshotId || null, result: state.currentResult }),
    });
    data = await resp.json();
  } catch (e) {
    el.innerHTML = `<div class="narr-empty">Couldn't build the narrative — ${escapeHtml(String((e && e.message) || e))}.</div>`;
    return;
  }
  if (!data || !data.ok) {
    el.innerHTML = `<div class="narr-empty">Couldn't build the narrative.${data && data.error ? ' ' + escapeHtml(data.error) : ''}</div>`;
    return;
  }

  const r = state.currentResult;
  const sections = data.sections || [];
  const toneWord = TONE_WORD[data.tone] || '';
  _print = sections.map((s) => ({
    key: s.key, label: s.title,
    html: `<div class="narr-sec${s.tone && s.tone !== 'neutral' ? ' narr-' + s.tone : ''}">${(s.paragraphs || []).map((p) => `<p>${escapeHtml(p)}</p>`).join('')}</div>`,
  }));
  const secHtml = sections.map((s) => {
    const paras = (s.paragraphs || []).map((p) => `<p>${escapeHtml(p)}</p>`).join('');
    const tone = s.tone && s.tone !== 'neutral' ? ` narr-${s.tone}` : '';
    return `<section class="narr-sec${tone}">
      <h3>${escapeHtml(s.title)}</h3>${paras}</section>`;
  }).join('');

  el.innerHTML = `
    <div class="ov-head"><div class="ov-title">
      <h2>Baseline Narrative</h2>
      <div class="ov-chips">
        <span class="ov-chip">${escapeHtml(r.project_name || 'Project')}</span>
        ${r.data_date ? `<span class="ov-chip">data date <b>${escapeHtml(String(r.data_date).slice(0, 10))}</b></span>` : ''}
        ${toneWord ? `<span class="ov-chip narr-chip-${data.tone}"><b>${toneWord}</b></span>` : ''}
      </div>
    </div></div>
    <div class="narr-doc">${secHtml}</div>
    <p class="ov-note">A plain-English status summary generated from this update's metrics (SPI, CPI, delay and category progress) — the same figures the dashboards and PDF use. Deterministic and offline; no AI or account needed.</p>`;
}
