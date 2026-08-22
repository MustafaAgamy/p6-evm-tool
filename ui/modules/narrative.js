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

// The fuller report renumbers its sections 1..N, so we can no longer key off fixed
// section numbers. We drive editability from the document MODEL (kind + number) and
// locate each section's DOM node by its data-section number, which the renderer emits
// 1:1 with the model. Two `seq` sections (General Sequence + Sequence of Work) and one
// `wbs_tree` are handled the same way, each scoped to its own section subtree.
function sectionEl(host, number) {
  return host.querySelector(`section.sec[data-section="${cssAttr(number)}"]`);
}

function makeEditable(host) {
  const sections = (state.narrativeDoc && state.narrativeDoc.sections) || [];
  if (sections.length) {
    sections.forEach(s => { const el = sectionEl(host, s.number); if (el) wireSection(el, s); });
  } else {
    // Defensive fallback (doc missing): infer from the DOM only.
    host.querySelectorAll('section.sec').forEach(el => wireSection(el, null));
  }
}

// Wire one section's DOM for editing, according to its kind.
function wireSection(el, s) {
  const kind = s ? s.kind : inferKind(el);
  if (kind === 'seq') { el.querySelectorAll('.front').forEach(front => wireFront(front)); return; }
  if (kind === 'wbs_tree' || kind === 'wbs') {
    el.querySelectorAll('.wt-box:not(.wt-root):not(.wt-more), .it-box:not(.it-more)').forEach(editText);
    return;
  }
  // Prose-bearing sections: overview is always editable; scope is editable per the spec
  // (its builder flag is missing); honest-note `prose` sections stay read-only.
  const proseEditable = s ? (!!s.editable || kind === 'scope' || kind === 'overview') : true;
  if (proseEditable) {
    el.querySelectorAll('[data-field]').forEach(editText);   // renderer-hooked prose (overview)
    proseParas(el).forEach(editText);                        // scope intro + discipline prose
  }
}

// Body prose paragraphs eligible for inline editing: real <p> content that is not a
// renderer lead-in, not already a data-field hook, and not inside tabular/stat chrome.
function proseParas(el) {
  return [...el.querySelectorAll('p')].filter(p =>
    !p.hasAttribute('data-field') &&
    !p.classList.contains('lead') &&
    !p.closest('table, thead, tbody, .bn-statwrap, .stats, details, .ms-table') &&
    (p.textContent || '').trim() !== '');
}

// Best-effort kind inference when the model is unavailable (fallback path only).
function inferKind(el) {
  if (el.querySelector('.front')) return 'seq';
  if (el.querySelector('.wt-box, .it-box')) return 'wbs_tree';
  if (el.querySelector('.bn-disc')) return 'scope';
  if (el.querySelector('[data-field]')) return 'overview';
  return '';
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
  add.contentEditable = 'false';
  add.addEventListener('click', () => {
    const box = document.createElement('span');
    box.className = 'fl-box';
    box.textContent = 'New step';
    flow.insertBefore(box, add);          // new box always sits before the add control
    wirePackage(box, flow);
    refreshArrows(flow);                  // re-thread arrows so the new box gets one before it
    selectText(box);
  });
  flow.appendChild(add);
  refreshArrows(flow);                    // normalise the renderer-baked arrows to the dynamic rule
}

// DYNAMIC ARROWS (issue #6b). The renderer bakes ▶ separators as standalone `.fl-arr`
// spans between boxes; after any add / remove / reorder those baked spans go stale
// (missing before a new box, orphaned after a removed one, scrambled after a drag).
// refreshArrows() rebuilds them from the CURRENT box order every time: it deletes ALL
// existing `.fl-arr` separators, then inserts exactly one immediately BEFORE each box
// except the first. That guarantees exactly one arrow between each adjacent pair, none
// before the first box, and none after the last (arrows are only ever placed before a
// box, and the `.bn-add` control — not a box — stays at the tail). 0 or 1 box ⇒ no arrows.
function refreshArrows(flow) {
  if (!flow) return;
  flow.querySelectorAll('.fl-arr').forEach(a => a.remove());
  const boxes = [...flow.querySelectorAll('.fl-box')];
  boxes.forEach((box, idx) => {
    if (idx === 0) return;
    const arr = document.createElement('span');
    arr.className = 'fl-arr';
    arr.setAttribute('aria-hidden', 'true');
    arr.contentEditable = 'false';
    arr.textContent = '▶';
    flow.insertBefore(arr, box);
  });
}

function wirePackage(box, flow) {
  editText(box);
  box.setAttribute('draggable', 'true');
  box.addEventListener('dragstart', e => { box.classList.add('bn-drag'); if (e.dataTransfer) e.dataTransfer.setData('text/plain', ''); });
  box.addEventListener('dragend', () => { box.classList.remove('bn-drag'); refreshArrows(flow); });
  box.addEventListener('dragover', e => {
    e.preventDefault();
    const dragging = flow.querySelector('.bn-drag');
    if (!dragging || dragging === box) return;
    const r = box.getBoundingClientRect();
    flow.insertBefore(dragging, (e.clientX - r.left) < r.width / 2 ? box : box.nextSibling);
    refreshArrows(flow);                 // keep the flow correctly threaded during the drag
  });
  const del = document.createElement('span');
  del.className = 'bn-del';
  del.textContent = '×';
  del.title = 'Remove this step';
  del.contentEditable = 'false';
  del.addEventListener('click', () => { box.remove(); refreshArrows(flow); });
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

// Serialise the (edited) DOM back into the document model. We walk the model in order
// and, for each section, locate its DOM node by data-section number (the renderer emits
// them 1:1) and fold that section's edits into ITS OWN payload. This is number-order
// independent, so it survives the fuller report's 1..N renumbering and correctly handles
// the two `seq` sections and the single `wbs_tree`, each scoped to its own subtree.
function boxText(box) {
  const c = box.cloneNode(true);
  c.querySelectorAll('.bn-del').forEach(d => d.remove());
  return c.innerText.trim();
}

// Write a value into a dotted payload path (e.g. "paragraphs.0", "blocks.2.paragraph"),
// creating arrays/objects as needed but preferring existing containers.
function setByPath(obj, path, value) {
  const parts = String(path).split('.');
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const k = parts[i];
    if (cur[k] == null) cur[k] = /^\d+$/.test(parts[i + 1]) ? [] : {};
    cur = cur[k];
  }
  cur[parts[parts.length - 1]] = value;
}

// Honour any renderer-emitted data-field hooks in a section, writing each element's text
// back to its payload path. Returns true if at least one hook was found (overview, and
// any future hook-carrying prose). Precise + renderer-driven, so it needs no assumptions.
function applyFieldHooks(el, payload) {
  let any = false;
  el.querySelectorAll('[data-field]').forEach(node => {
    const path = node.getAttribute('data-field');
    if (!path) return;
    setByPath(payload, path, node.innerText.trim());
    any = true;
  });
  return any;
}

function serializeDoc() {
  const doc = state.narrativeDoc;
  const host = document.getElementById('narrative-doc');
  if (!doc || !host || !Array.isArray(doc.sections)) return doc;
  for (const s of doc.sections) {
    const el = sectionEl(host, s.number);
    if (!el) continue;
    switch (s.kind) {
      case 'overview':
      case 'prose':    serializeProse(el, s); break;
      case 'scope':    serializeScope(el, s); break;
      case 'seq':      serializeSeq(el, s);   break;
      case 'wbs_tree':
      case 'wbs':      serializeWbs(el, s);   break;
      default: break;
    }
  }
  return doc;
}

// Overview + editable prose. Prefer precise data-field hooks; otherwise fold the editable
// body paragraphs into payload.paragraphs (the shape the prose/overview renderers use).
function serializeProse(el, s) {
  if (s.kind === 'prose' && !s.editable) return;   // honest-note prose is never edited
  const p = s.payload || (s.payload = {});
  if (applyFieldHooks(el, p)) return;
  const paras = proseParas(el).map(x => x.innerText.trim()).filter(Boolean);
  if (paras.length) p.paragraphs = paras;
}

// Scope of Work: {intro, blocks:[{paragraph,...}]}. Prefer hooks; else map positionally
// from the recovered DOM — the first non-discipline body paragraph is the intro, and each
// `.bn-disc` block's paragraph feeds the matching blocks[i].paragraph. Guarded so an
// unexpected structure never corrupts the payload.
function serializeScope(el, s) {
  const p = s.payload || (s.payload = {});
  if (applyFieldHooks(el, p)) return;
  const bodyParas = proseParas(el);
  if (typeof p.intro === 'string') {
    const introEl = bodyParas.find(x => !x.closest('.bn-disc'));
    if (introEl) p.intro = introEl.innerText.trim();
  }
  if (Array.isArray(p.blocks)) {
    const discParas = [...el.querySelectorAll('.bn-disc')].map(d => d.querySelector('p'));
    p.blocks.forEach((b, i) => {
      const dp = discParas[i];
      if (dp && b && typeof b === 'object') b.paragraph = dp.innerText.trim();
    });
  }
}

// Sequence of Work: zip this section's DOM `.front` cards to its own payload.worlds/fronts
// in DOM order (front title + the flow's `.fl-box` steps). Scoped to `el` so each of the
// two seq sections serialises into its own payload.
function serializeSeq(el, s) {
  const p = s.payload;
  if (!p || !Array.isArray(p.worlds)) return;
  const cards = [...el.querySelectorAll('.front')];
  let i = 0;
  for (const w of p.worlds) {
    for (const f of (w.fronts || [])) {
      const card = cards[i++];
      if (!card) continue;
      const t = card.querySelector('.fr-title');
      if (t) f.title = t.innerText.trim();
      f.sequence = [...card.querySelectorAll('.fl-box')].map(boxText).filter(Boolean);
    }
  }
}

// WBS: rename nodes in pre-order, matching the renderer's document order. World roots are
// rendered but not editable, so we recurse only their children — exactly as they appear.
function serializeWbs(el, s) {
  const p = s.payload;
  if (!p || !Array.isArray(p.worlds)) return;
  const nodes = [...el.querySelectorAll('.wt-box:not(.wt-root):not(.wt-more), .it-box:not(.it-more)')];
  let i = 0;
  const walk = n => {
    if (!n || n.more) return;
    const node = nodes[i++];
    if (node) n.name = node.innerText.trim() || n.name;
    (n.children || []).forEach(walk);
  };
  for (const world of p.worlds) ((world.root || {}).children || []).forEach(walk);
}

// ── Report Contents (the tool-wide selection framework) ─────────────────────────
function mountContents(host) {
  const panel = document.getElementById('narrative-contents');
  if (!panel) return;
  const titleByNum = {};
  ((state.narrativeDoc && state.narrativeDoc.sections) || []).forEach(s => { titleByNum[s.number] = s.title; });
  const sections = [...host.querySelectorAll('section.sec')];
  const components = sections.map(el => {
    const num = el.getAttribute('data-section');
    const h2 = el.querySelector('h2');
    const label = titleByNum[num]
      || (h2 ? h2.textContent.replace(/^\s*\d+[.\s]*/, '').trim() : '')
      || ('Section ' + num);
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
  // Reorder ANCHOR: the footer is the last child of `.page`, so append-to-page would drop
  // sections after it. Insert before the footer instead so it always stays at the bottom.
  const foot = page.querySelector(':scope > .foot');
  host.querySelectorAll('section.sec').forEach(el => {
    el.style.display = sel.has(el.getAttribute('data-section')) ? '' : 'none';
  });
  selected.forEach((num, idx) => {
    const el = sectionEl(host, num);
    if (!el) return;
    if (foot && foot.parentNode === page) page.insertBefore(el, foot);   // keep footer last
    else page.appendChild(el);                                           // reorder to the selected order
    // Renumber the on-screen heading chip. Cover both the v5 header (`h2 .num`) and the
    // recovered header markup (a `.bn-n` chip beside the h2) so numbering stays 1..k.
    const chip = el.querySelector('h2 .num, .bn-n');
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
