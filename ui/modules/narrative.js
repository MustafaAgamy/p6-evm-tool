// Baseline Narrative — auto-writes the Basis-of-Schedule document from the imported
// baseline (XER/XML). A thin view over the server assembler: fetch the document,
// show it as an editable "paper" sheet, and export it to editable Word or PDF.
// Recomputes nothing — every section is fed by an engine the tool already has.

import { state }               from './state.js';
import { showError, clearError } from './render.js';

const PORT = () => state.serverPort;

// ── fetch + render ──────────────────────────────────────────────────────────

async function fetchAndRender() {
  const host = document.getElementById('narrative-doc');
  if (!host) return;
  if (!state.currentXmlPath && !state.currentCachedPath) {
    host.innerHTML = '<p class="ai-empty">Open a baseline schedule first — the narrative then generates.</p>';
    return;
  }
  clearError();
  host.innerHTML = '<div class="cmp-loading">Assembling the baseline narrative from your file…</div>';
  try {
    const resp = await fetch(`http://localhost:${PORT()}/api/narrative`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        xml_path: state.currentXmlPath, cached_path: state.currentCachedPath,
        snapshot_id: state.currentSnapshotId || null, setup: setupForSend(),
      }),
    });
    const data = await resp.json();
    if (!data.ok) { showError(data.error || 'Narrative generation failed.'); host.innerHTML = ''; return; }
    state.narrativeDoc = data.doc;
    renderDoc(data.html, data.counts);
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  }
}

function renderDoc(html, counts) {
  const body = document.getElementById('narrative-doc');
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
      .bn-seqbtn{font:inherit;font-size:12px;padding:4px 12px;border:1px solid var(--border,#dadee4);
        background:var(--surface-2,#fff);border-radius:14px;cursor:pointer;color:var(--text-primary,#1a1d21)}
      .bn-seqbtn.on{background:#3487ae;color:#fff;border-color:#3487ae}
    </style>
    <div class="bn-toolbar">
      <span class="sum"><b>${(c.auto||0)+(c.calendar||0)}</b> from your file ·
        <b>${c.drafted||0}</b> drafted · <b>${c.fill||0}</b> for you · ✎ highlighted text &amp; chart values are editable</span>
      <span style="display:inline-flex;align-items:center;gap:7px">Sequence chart:
        <button class="bn-seqbtn on" data-seq="flow">Flow</button>
        <button class="bn-seqbtn" data-seq="timeline">Timeline</button></span>
    </div>`;
  body.innerHTML = toolbar + html;
  enableEditing(body);
  wireSeqChooser(body);
  wireEditableCharts(body);
}

function wireSeqChooser(body) {
  const doc = state.narrativeDoc;
  if (doc && !doc.meta) doc.meta = {};
  const apply = (style) => {
    body.querySelectorAll('.bn-view-flow').forEach(e => { e.style.display = style === 'flow' ? '' : 'none'; });
    body.querySelectorAll('.bn-view-timeline').forEach(e => { e.style.display = style === 'timeline' ? '' : 'none'; });
    body.querySelectorAll('.bn-seqbtn').forEach(b => b.classList.toggle('on', b.dataset.seq === style));
    if (doc && doc.meta) doc.meta.sequence_style = style;
  };
  body.querySelectorAll('.bn-seqbtn').forEach(b => b.addEventListener('click', () => apply(b.dataset.seq)));
  apply((doc && doc.meta && doc.meta.sequence_style) || 'flow');
}

// Editable chart values: edit a cost-loading % → the bar redraws and the number is
// written back into the document, so it flows to the Word / PDF export.
function wireEditableCharts(body) {
  const doc = state.narrativeDoc;
  const sec = body.querySelector('.bn-sec[data-num="13"]');
  if (!sec) return;
  const payload = sectionPayload(doc, '13');
  sec.querySelectorAll('.bn-bar').forEach((row, i) => {
    const bv = row.querySelector('.bn-bv');
    const fill = row.querySelector('.bn-fill');
    if (!bv || !fill) return;
    bv.contentEditable = 'true';
    bv.classList.add('bn-edit');
    bv.spellcheck = false;
    bv.addEventListener('input', () => {
      const v = Math.max(0, Math.min(100, parseFloat(bv.innerText.replace(/[^0-9.]/g, '')) || 0));
      fill.style.width = v + '%';
      if (payload && payload.rows && payload.rows[i]) payload.rows[i].pct = v;
    });
  });
}

function sectionPayload(doc, num) {
  const s = doc && doc.sections && doc.sections.find(x => x.number === num);
  return s ? s.payload : null;
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
  const body = document.getElementById('narrative-doc');
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

// ── project setup (parties, logos, layout) ───────────────────────────────────

function setupStoreKey() {
  return 'bn_setup_' + (state.currentSnapshotId || state.currentProjectId || 'default');
}
function getSetup() {
  if (!state.narrativeSetup) {
    try { state.narrativeSetup = JSON.parse(localStorage.getItem(setupStoreKey()) || '{}'); }
    catch { state.narrativeSetup = {}; }
  }
  return state.narrativeSetup;
}
function saveSetup() {
  try { localStorage.setItem(setupStoreKey(), JSON.stringify(state.narrativeSetup || {})); } catch (e) { /* ignore */ }
}

function fileToDataUrl(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result);
    r.onerror = rej;
    r.readAsDataURL(file);
  });
}

function setupFormHtml() {
  const s = getSetup();
  const party = (key, label) => `
    <div class="bn-party">
      <label>${label}</label>
      <input type="text" data-k="${key}" placeholder="${label} name" value="${(s[key] || '').replace(/"/g, '&quot;')}"/>
      <label class="bn-file">${s[key + '_logo'] ? '✓ logo' : '＋ logo'}<input type="file" accept="image/*" data-logo="${key}_logo"></label>
    </div>`;
  return `
    <style>
      .bn-setup{border:1px dashed #3487ae;border-radius:12px;padding:14px 16px;margin:0 auto 16px;max-width:900px;background:var(--surface-2,#fff)}
      .bn-setup h4{margin:0 0 3px;font-size:13.5px;color:#265f7e}
      .bn-setup .hint{font-size:12px;color:var(--text-muted,#8a9099);margin:0 0 12px}
      .bn-setup-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
      .bn-party{border:1px solid var(--border,#dadee4);border-radius:9px;padding:10px}
      .bn-party>label{font-size:11px;font-weight:600;color:var(--text-secondary,#565c64);display:block;margin-bottom:6px}
      .bn-party input[type=text]{width:100%;box-sizing:border-box;padding:6px 9px;border:1px solid var(--border,#dadee4);border-radius:6px;font:inherit;font-size:12.5px;margin-bottom:7px;background:var(--surface-2,#fff);color:var(--text-primary,#1a1d21)}
      .bn-file{display:inline-block;font-size:12px;border:1px solid #3487ae;color:#3487ae;border-radius:6px;padding:5px 11px;cursor:pointer}
      .bn-file input{display:none}
      #bn-setup-gen{margin-top:12px;font:inherit;font-size:13px;font-weight:600;background:#265f7e;color:#fff;border:none;border-radius:7px;padding:8px 18px;cursor:pointer}
    </style>
    <div class="bn-setup">
      <h4>Project setup — parties, logos &amp; layout</h4>
      <div class="hint">The details P6 doesn't hold. Saved with the project; the three logos become the Word page header on every page.</div>
      <div class="bn-setup-grid">
        ${party('owner', 'Owner')}${party('consultant', 'Consultant')}${party('contractor', 'Contractor')}
        <div class="bn-party"><label>Project layout</label>
          <label class="bn-file">${s.layout ? '✓ layout image' : '＋ layout image'}<input type="file" accept="image/*" data-logo="layout"></label>
        </div>
      </div>
      <div style="margin-top:11px;font-size:12.5px;color:var(--text-secondary,#565c64)">
        <label style="cursor:pointer"><input type="checkbox" id="bn-inc-logos" ${s.include_logos === false ? '' : 'checked'} style="vertical-align:-1px;margin-right:6px">Include the logos as the Word page header</label>
        <span style="color:var(--text-muted,#8a9099);margin-left:6px">— logos are optional; untick to generate without them.</span>
      </div>
      <button id="bn-setup-gen">Generate narrative</button>
    </div>`;
}

// Setup to send when generating: honours the "include logos" toggle so the user can
// deliberately generate a clean report without the logo header even if logos exist.
function setupForSend() {
  const s = { ...getSetup() };
  const inc = document.getElementById('bn-inc-logos');
  const include = inc ? inc.checked : (s.include_logos !== false);
  if (!include) {
    delete s.owner_logo;
    delete s.consultant_logo;
    delete s.contractor_logo;
  }
  return s;
}

function wireSetupForm(root) {
  const s = getSetup();
  root.querySelectorAll('.bn-setup input[type=text]').forEach(inp =>
    inp.addEventListener('input', () => { s[inp.dataset.k] = inp.value; saveSetup(); }));
  root.querySelectorAll('.bn-setup input[type=file]').forEach(inp =>
    inp.addEventListener('change', async () => {
      if (!inp.files || !inp.files[0]) return;
      s[inp.dataset.logo] = await fileToDataUrl(inp.files[0]);
      saveSetup();
      const lab = inp.closest('.bn-file');
      if (lab) lab.childNodes[0].nodeValue = '✓ ' + (inp.dataset.logo === 'layout' ? 'layout image' : 'logo');
    }));
  const inc = root.querySelector('#bn-inc-logos');
  if (inc) inc.addEventListener('change', () => { s.include_logos = inc.checked; saveSetup(); });
  const gen = root.querySelector('#bn-setup-gen');
  if (gen) gen.addEventListener('click', () => fetchAndRender());
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
  state.narrativeSetup = null;                 // reload setup for the current project
  const panel = document.getElementById('narrative-body');
  if (panel) {
    panel.innerHTML = setupFormHtml() + '<div id="narrative-doc"></div>';
    wireSetupForm(panel);
  }
  fetchAndRender();
}
