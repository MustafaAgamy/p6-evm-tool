// Baseline Narrative Report — a senior planning study auto-written from the imported
// baseline. Fetches the v5 document from the server, shows it as an editable "paper"
// sheet, lets the planner restructure it (rename packages, reorder / add / remove steps,
// rename WBS nodes, edit the overview prose), and exports the edited report to Word / PDF.
// A "Report Contents" panel (the tool-wide framework) chooses exactly which sections
// appear — identically in Preview, PDF and Print.

import { state }                 from './state.js';
import { showError, clearError } from './render.js';
import { createReportRegistry }  from './report_registry.js';

const PORT = () => state.serverPort;
let registry = null;

// ── fetch + mount ─────────────────────────────────────────────────────────────
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
    mountReport(data.html);
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  }
}

function mountReport(html) {
  const host = document.getElementById('narrative-doc');
  host.innerHTML = editStyles() + html;
  makeEditable(host);
  mountContents(host);
}

// ── structural editability ────────────────────────────────────────────────────
function editText(el) {
  if (!el) return;
  el.contentEditable = 'true';
  el.classList.add('bn-edit');
  el.spellcheck = false;
}

function makeEditable(host) {
  // 1) Overview prose
  host.querySelectorAll('[data-section="1"] [data-field^="paragraphs"]').forEach(editText);
  // 2) Sequence of Work — rename front title, edit/reorder/add/remove packages
  host.querySelectorAll('.front').forEach(wireFront);
  // 3) WBS — rename any node (not the world root)
  host.querySelectorAll('.wt-box:not(.wt-root), .it-box').forEach(el => {
    if (!el.classList.contains('wt-more') && !el.classList.contains('it-more')) editText(el);
  });
}

function wireFront(front) {
  editText(front.querySelector('.fr-title'));
  const flow = front.querySelector('.flow');
  if (!flow) return;
  flow.querySelectorAll('.fl-box').forEach(box => wirePackage(box, flow));
  const add = document.createElement('button');
  add.className = 'bn-add';
  add.type = 'button';
  add.textContent = '+ step';
  add.title = 'Add a work-package step';
  add.addEventListener('click', () => {
    const box = document.createElement('span');
    box.className = 'fl-box';
    box.textContent = 'New step';
    flow.insertBefore(box, add);
    wirePackage(box, flow);
    selectText(box);
  });
  flow.appendChild(add);
}

function wirePackage(box, flow) {
  editText(box);
  box.setAttribute('draggable', 'true');
  box.addEventListener('dragstart', e => { box.classList.add('bn-drag'); e.dataTransfer.setData('text/plain', ''); });
  box.addEventListener('dragend', () => box.classList.remove('bn-drag'));
  box.addEventListener('dragover', e => {
    e.preventDefault();
    const dragging = flow.querySelector('.bn-drag');
    if (!dragging || dragging === box) return;
    const r = box.getBoundingClientRect();
    flow.insertBefore(dragging, (e.clientX - r.left) < r.width / 2 ? box : box.nextSibling);
  });
  const del = document.createElement('span');
  del.className = 'bn-del';
  del.textContent = '×';
  del.title = 'Remove this step';
  del.contentEditable = 'false';
  del.addEventListener('click', () => box.remove());
  box.appendChild(del);
}

function selectText(el) {
  el.focus();
  const r = document.createRange();
  r.selectNodeContents(el);
  const s = window.getSelection();
  s.removeAllRanges();
  s.addRange(r);
}

// Serialise the (edited) DOM back into the document model, matching model order to DOM
// order 1:1 (the renderer is deterministic, so the fronts/nodes line up).
function boxText(box) {
  const c = box.cloneNode(true);
  c.querySelectorAll('.bn-del').forEach(d => d.remove());
  return c.innerText.trim();
}

function serializeDoc() {
  const doc = state.narrativeDoc;
  const host = document.getElementById('narrative-doc');
  if (!doc || !host) return doc;
  const sec = num => doc.sections.find(s => s.number === num);

  const ov = sec('1');
  if (ov) {
    const paras = [...host.querySelectorAll('[data-section="1"] [data-field^="paragraphs"]')]
      .map(p => p.innerText.trim()).filter(Boolean);
    if (paras.length) ov.payload.paragraphs = paras;
  }

  const sq = sec('4');
  if (sq && sq.payload.worlds) {
    const cards = [...host.querySelectorAll('.front')];
    let i = 0;
    for (const w of sq.payload.worlds) {
      for (const f of w.fronts) {
        const card = cards[i++];
        if (!card) continue;
        const t = card.querySelector('.fr-title');
        if (t) f.title = t.innerText.trim();
        f.sequence = [...card.querySelectorAll('.fl-box')].map(boxText).filter(Boolean);
      }
    }
  }

  const wb = sec('3');
  if (wb && wb.payload.worlds) {
    const nodes = [...host.querySelectorAll('.wt-box:not(.wt-root):not(.wt-more), .it-box:not(.it-more)')];
    let i = 0;
    const walk = n => {
      if (n.more) return;
      const el = nodes[i++];
      if (el) n.name = el.innerText.trim() || n.name;
      (n.children || []).forEach(walk);
    };
    // the world roots are rendered but not editable; recurse their children in order
    for (const world of wb.payload.worlds) (world.root.children || []).forEach(walk);
  }
  return doc;
}

// ── Report Contents (the tool-wide selection framework) ─────────────────────────
function mountContents(host) {
  const panel = document.getElementById('narrative-contents');
  if (!panel) return;
  const sections = [...host.querySelectorAll('section.sec')];
  const components = sections.map(el => {
    const num = el.getAttribute('data-section');
    const h2 = el.querySelector('h2');
    const label = h2 ? h2.textContent.replace(/^\s*\d+\s*/, '').trim() : ('Section ' + num);
    return { id: num, label, render: () => el, defaultOn: true, hasData: true };
  });
  registry = createReportRegistry({
    key: 'narrative_' + (state.currentProjectId || 'default'),
    components,
    onChange: () => applySelection(host),
  });
  registry.renderControls(panel);
  applySelection(host);
}

// Reflect the Report-Contents selection in the on-screen paper: hide de-selected sections,
// re-order the selected ones, and renumber their heading chips so Preview == PDF == Print.
function applySelection(host) {
  if (!registry) return;
  const selected = registry.getSelectedIds();
  const sel = new Set(selected);
  const page = host.querySelector('.page') || host;
  host.querySelectorAll('section.sec').forEach(el => {
    el.style.display = sel.has(el.getAttribute('data-section')) ? '' : 'none';
  });
  selected.forEach((num, idx) => {
    const el = host.querySelector(`section.sec[data-section="${cssAttr(num)}"]`);
    if (!el) return;
    if (page) page.appendChild(el);                 // reorder to the selected order
    const chip = el.querySelector('h2 .num');
    if (chip) chip.textContent = String(idx + 1);
  });
}

function cssAttr(v) { return String(v).replace(/"/g, '\\"'); }

// ── export (Word / PDF) — respects the edits and the Report-Contents selection ──
function exportDoc() {
  const doc = JSON.parse(JSON.stringify(serializeDoc()));
  if (registry) {
    const order = registry.getSelectedIds();
    const keep = new Set(order);
    doc.sections = doc.sections
      .filter(s => keep.has(s.number))
      .sort((a, b) => order.indexOf(a.number) - order.indexOf(b.number));
  }
  return doc;
}

async function exportNarrative(kind) {
  if (!state.narrativeDoc) { showError('Generate the narrative first.'); return; }
  const btn = document.getElementById(kind === 'docx' ? 'narrative-word-btn' : 'narrative-pdf-btn');
  const label = btn ? btn.textContent : '';
  const ext = kind === 'docx' ? 'docx' : 'pdf';
  const proj = (state.narrativeDoc.meta && state.narrativeDoc.meta.project_name) || 'Project';
  const safe = proj.replace(/[^\w.-]+/g, '_').slice(0, 60);
  try {
    const outputPath = await window.pywebview.api.choose_save_path(`${safe}_Baseline_Narrative.${ext}`, ext);
    if (!outputPath) return;
    if (btn) { btn.disabled = true; btn.textContent = 'Exporting…'; }
    const resp = await fetch(`http://localhost:${PORT()}/api/narrative/${kind}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc: exportDoc(), edits: {}, output_path: outputPath }),
    });
    const data = await resp.json();
    if (!data.ok) showError(`Export failed: ${data.error}`);
    else if (btn) btn.textContent = kind === 'docx' ? '✓ Word saved' : '✓ PDF saved';
  } catch {
    showError('Export failed. Check the output path and try again.');
  } finally {
    if (btn) { btn.disabled = false; setTimeout(() => { btn.textContent = label; }, 2500); }
  }
}

function editStyles() {
  return `<style>
    .bn-edit{outline:none;border-radius:4px;transition:background .12s}
    .bn-edit:hover{background:rgba(52,135,174,.10)}
    .bn-edit:focus{background:rgba(52,135,174,.16);box-shadow:0 0 0 1px rgba(52,135,174,.45)}
    .fl-box{position:relative}
    .fl-box[draggable]{cursor:grab}
    .fl-box.bn-drag{opacity:.45}
    .bn-del{display:none;margin-left:7px;color:#c0392b;font-weight:700;cursor:pointer;user-select:none}
    .fl-box:hover .bn-del{display:inline}
    .bn-add{margin-left:6px;font:inherit;font-size:11.5px;border:1px dashed #9bb6cc;background:transparent;
      color:#3487ae;border-radius:12px;padding:2px 9px;cursor:pointer}
    .bn-add:hover{background:rgba(52,135,174,.10)}
  </style>`;
}

// ── project setup (parties, logos, layout) — unchanged behaviour ───────────────
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
      .bn-layout{display:flex;gap:18px;align-items:flex-start}
      .bn-contents{flex:0 0 220px}
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
      <button id="bn-setup-gen">Generate narrative</button>
    </div>`;
}
function setupForSend() {
  const s = { ...getSetup() };
  if (s.include_logos === false) { delete s.owner_logo; delete s.consultant_logo; delete s.contractor_logo; }
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
  const gen = root.querySelector('#bn-setup-gen');
  if (gen) gen.addEventListener('click', () => fetchAndRender());
}

// ── entry point (called by app.js on card/tab open) ────────────────────────────
let _wired = false;
export function renderNarrativePanel() {
  if (!_wired) {
    const w = document.getElementById('narrative-word-btn');
    const p = document.getElementById('narrative-pdf-btn');
    if (w) w.addEventListener('click', () => exportNarrative('docx'));
    if (p) p.addEventListener('click', () => exportNarrative('pdf'));
    _wired = true;
  }
  state.narrativeSetup = null;
  const panel = document.getElementById('narrative-body');
  if (panel) {
    panel.innerHTML = setupFormHtml() +
      '<div class="bn-layout"><div id="narrative-contents" class="bn-contents"></div>' +
      '<div id="narrative-doc" style="flex:1;min-width:0"></div></div>';
    wireSetupForm(panel);
  }
  fetchAndRender();
}
