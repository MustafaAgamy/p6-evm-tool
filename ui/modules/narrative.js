// Baseline Narrative — auto-writes the Basis-of-Schedule document from the imported
// baseline (XER/XML). A thin view over the server assembler: fetch the document,
// show it as an editable "paper" sheet, and export it to editable Word or PDF.
// Recomputes nothing — every section is fed by an engine the tool already has.

import { state }               from './state.js';
import { showError, clearError } from './render.js';

const PORT = () => state.serverPort;

// ── fetch + render ──────────────────────────────────────────────────────────

async function fetchAndRender() {
  const body = document.getElementById('narrative-body');
  if (!body) return;
  if (!state.currentXmlPath && !state.currentCachedPath) {
    body.innerHTML = '<p class="ai-empty">Open a baseline schedule first — the narrative then generates automatically.</p>';
    return;
  }
  clearError();
  body.innerHTML = '<div class="cmp-loading">Assembling the baseline narrative from your file…</div>';
  try {
    const resp = await fetch(`http://localhost:${PORT()}/api/narrative`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        xml_path: state.currentXmlPath, cached_path: state.currentCachedPath,
        snapshot_id: state.currentSnapshotId || null,
      }),
    });
    const data = await resp.json();
    if (!data.ok) { showError(data.error || 'Narrative generation failed.'); body.innerHTML = ''; return; }
    state.narrativeDoc = data.doc;
    renderDoc(data.html, data.counts);
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  }
}

function renderDoc(html, counts) {
  const body = document.getElementById('narrative-body');
  if (!body) return;
  const c = counts || {};
  const toolbar = `
    <style>
      .bn-toolbar{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center;justify-content:space-between;
        margin:0 auto 14px;max-width:860px;font-size:13px;color:var(--text-muted,#8a9099)}
      .bn-toolbar .sum b{color:var(--accent,#265f7e)}
      .bn-edit{outline:none;border-bottom:1px dashed #b9c2cb;transition:background .15s}
      .bn-edit:hover{background:#eef4f8}
      .bn-edit:focus{background:#eaf3fb;border-bottom-color:#3487ae}
    </style>
    <div class="bn-toolbar">
      <span class="sum"><b>${(c.auto||0)+(c.calendar||0)}</b> sections from your file ·
        <b>${c.drafted||0}</b> drafted (editable) · <b>${c.fill||0}</b> for you</span>
      <span>✎ The highlighted text is editable — change it, then export. Word &amp; PDF carry your edits.</span>
    </div>`;
  body.innerHTML = toolbar + html;
  enableEditing(body);
}

function enableEditing(body) {
  body.querySelectorAll(
    '.bn-sec[data-editable] .bn-body > p, .bn-sec[data-editable] .bn-body > ul.bn-bul > li'
  ).forEach(el => { el.contentEditable = 'true'; el.classList.add('bn-edit'); el.spellcheck = false; });
}

// ── collect in-app edits back into the document before export ────────────────

// Gather the user's in-app prose edits into an {sectionNumber: {paragraphs, bullets}}
// map. The server merges it into the document via p6_narrative.builder.apply_edits,
// so the original document stays untouched here and only editable sections are read.
function collectEdits() {
  const doc = state.narrativeDoc;
  const body = document.getElementById('narrative-body');
  const edits = {};
  if (!doc || !body) return edits;
  for (const s of doc.sections) {
    if (!s.editable) continue;
    const sec = body.querySelector(`.bn-sec[data-num="${cssAttr(s.number)}"]`);
    if (!sec) continue;
    const bodyEl = sec.querySelector('.bn-body');
    if (!bodyEl) continue;
    const patch = {};
    const paras = [...bodyEl.querySelectorAll(':scope > p')]
      .map(p => p.innerText.trim()).filter(Boolean);
    const bullets = [...bodyEl.querySelectorAll(':scope > ul.bn-bul > li')]
      .map(li => li.innerText.trim()).filter(Boolean);
    if (paras.length)   patch.paragraphs = paras;
    if (bullets.length) patch.bullets = bullets;
    if (paras.length || bullets.length) edits[s.number] = patch;
  }
  return edits;
}

function cssAttr(v) { return String(v).replace(/"/g, '\\"'); }

// ── export ───────────────────────────────────────────────────────────────────

async function exportNarrative(kind) {
  if (!state.narrativeDoc) { showError('Generate the narrative first.'); return; }
  const btnId = kind === 'docx' ? 'narrative-word-btn' : 'narrative-pdf-btn';
  const btn = document.getElementById(btnId);
  const label = btn ? btn.textContent : '';
  const ext = kind === 'docx' ? 'docx' : 'pdf';
  const proj = (state.narrativeDoc.meta && state.narrativeDoc.meta.project_name) || 'Project';
  const safe = proj.replace(/[^\w.-]+/g, '_').slice(0, 60);
  try {
    const outputPath = await window.pywebview.api.choose_save_path(`${safe}_Baseline_Narrative.${ext}`, ext);
    if (!outputPath) return;
    if (btn) { btn.disabled = true; btn.textContent = 'Exporting…'; }
    const edits = collectEdits();
    const resp = await fetch(`http://localhost:${PORT()}/api/narrative/${kind}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc: state.narrativeDoc, edits, output_path: outputPath }),
    });
    const data = await resp.json();
    if (!data.ok) { showError(`Export failed: ${data.error}`); }
    else if (btn) { btn.textContent = kind === 'docx' ? '✓ Word saved' : '✓ PDF saved'; }
  } catch {
    showError('Export failed. Check the output path and try again.');
  } finally {
    if (btn) { btn.disabled = false; setTimeout(() => { btn.textContent = label; }, 2500); }
  }
}

// ── entry point (called by app.js on card/tab open) ──────────────────────────

let _wired = false;
export function renderNarrativePanel() {
  if (!_wired) {
    const w = document.getElementById('narrative-word-btn');
    const p = document.getElementById('narrative-pdf-btn');
    if (w) w.addEventListener('click', () => exportNarrative('docx'));
    if (p) p.addEventListener('click', () => exportNarrative('pdf'));
    _wired = true;
  }
  fetchAndRender();
}
