// Baseline Narrative Report — a senior planning study auto-written from the imported
// baseline. Fetches the v5 document from the server, shows it as an editable "paper"
// sheet, lets the planner restructure it (rename packages, reorder / add / remove steps,
// rename WBS nodes, edit the overview prose), and exports the edited report to Word / PDF.
// A "Report Contents" panel (the tool-wide framework) chooses exactly which sections
// appear — identically in Preview, PDF and Print.

import { state }                 from './state.js';
import { showError, clearError } from './render.js';
import { createReportRegistry }  from './report_registry.js';
import { revealAndRun, revealStage } from './featurereveal.js';

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
    renderSelection();               // populate the milestone / key-date checklists (comments 4 & 5)
    mountReport(data.html);
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  }
}

// The server renders ONE html for the screen and the PDF / HTML exports, so its stylesheet
// is written for a standalone page: its `body`, `p`, `table` and `*` rules, mounted inside
// the app, restyled EVERY feature from the moment the report was generated (Times New Roman
// text, a grey page, dark text in the dark modes, the menu bar jumping). On screen those
// page-level rules apply to the report container only; :where() keeps each rule's
// specificity exactly as written, so the report itself renders the same. (Exports send the
// document model, never this DOM, so they are unaffected.)
const DOC_SCOPE = ':where(#narrative-doc)';
export function scopeReportCss(html) {
  return String(html || '').replace(/<style>([\s\S]*?)<\/style>/, (m, css) => '<style>' +
    css.replace(/(^|[{}])(\s*)(body|p|table|\*)(?=\s*\{)/g,
      (r, brace, ws, sel) => brace + ws + (sel === 'body' ? DOC_SCOPE : DOC_SCOPE + ' ' + sel)) +
    '</style>');
}

function mountReport(html) {
  const host = document.getElementById('narrative-doc');
  host.innerHTML = editStyles() + scopeReportCss(html);
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
// re-order the selected ones, and renumber their headings so Preview == PDF == Print.
// The report renders one A4 `.page` per section (after the cover + TOC front-matter pages),
// so selection operates on whole section pages, never on loose blocks inside one page.
function applySelection(host) {
  if (!registry) return;
  const selected = registry.getSelectedIds();
  const sel = new Set(selected);
  // Map every section number → its enclosing `.page`.
  const pageByNum = new Map();
  host.querySelectorAll('section.sec').forEach(secEl => {
    const num = secEl.getAttribute('data-section');
    const pg = secEl.closest('.page');
    if (pg) pageByNum.set(num, pg);
  });
  // Hide / show each section's whole page (border, header and footer included).
  pageByNum.forEach((pg, num) => { pg.style.display = sel.has(num) ? '' : 'none'; });
  // Reorder the selected section pages into the chosen order, anchored after the last
  // front-matter page (cover / TOC — any `.page` that has no section block).
  const allPages = [...host.querySelectorAll('.page')];
  const frontPages = allPages.filter(pg => !pg.querySelector('section.sec'));
  let anchor = frontPages[frontPages.length - 1] || null;
  const parent = (anchor && anchor.parentNode) || (allPages[0] && allPages[0].parentNode) || host;
  selected.forEach((num, idx) => {
    const pg = pageByNum.get(num);
    if (!pg) return;
    const nextTo = anchor ? anchor.nextSibling : parent.firstChild;
    if (nextTo !== pg) parent.insertBefore(pg, nextTo);
    anchor = pg;
    // Renumber the on-screen heading ("N) Title") so numbering stays 1..k after reorder.
    const h = pg.querySelector('h1.sec');
    if (h) h.textContent = h.textContent.replace(/^\s*[^)]*\)/, String(idx + 1) + ')');
  });
}

function cssAttr(v) { return String(v).replace(/"/g, '\\"'); }

// ── export (Word / PDF) — respects the edits and the Report-Contents selection ──
function exportDoc() {
  const doc = JSON.parse(JSON.stringify(serializeDoc()));
  const all = Array.isArray(doc.sections) ? doc.sections : [];
  const order = registry ? registry.getSelectedIds() : [];
  // Safety net: only apply the selection when it actually resolves to sections that
  // exist in the document. If the registry is unavailable, empty, or its ids don't
  // match (e.g. a renderer/UI structure change), export the full document rather than
  // silently blank it — a blank report is never the intended output.
  const keep = new Set(order);
  const filtered = all.filter(s => keep.has(s.number));
  if (filtered.length) {
    doc.sections = filtered.sort((a, b) => order.indexOf(a.number) - order.indexOf(b.number));
  }
  return doc;
}

const NARRATIVE_BTN_IDS = { docx: 'narrative-word-btn', pdf: 'narrative-pdf-btn', html: 'narrative-html-btn', xlsx: 'narr-excel-btn' };
const NARRATIVE_OK_LABELS = { docx: '✓ Word saved', pdf: '✓ PDF saved', html: '✓ HTML saved', xlsx: '✓ Excel saved' };
// the server route of each export kind (Excel = the whole report as a workbook, one sheet per section)
const NARRATIVE_ROUTES = { xlsx: 'excel' };

async function exportNarrative(kind) {
  if (!state.narrativeDoc) { showError('Generate the narrative first.'); return; }
  const btn = document.getElementById(NARRATIVE_BTN_IDS[kind] || 'narrative-pdf-btn');
  const label = btn ? btn.textContent : '';
  const ext = kind;
  const proj = (state.narrativeDoc.meta && state.narrativeDoc.meta.project_name) || 'Project';
  const safe = proj.replace(/[^\w.-]+/g, '_').slice(0, 60);
  try {
    const outputPath = await window.pywebview.api.choose_save_path(`${safe}_Baseline_Narrative.${ext}`, ext);
    if (!outputPath) return;
    if (btn) { btn.disabled = true; btn.textContent = 'Exporting…'; }
    const resp = await fetch(`http://localhost:${PORT()}/api/narrative/${NARRATIVE_ROUTES[kind] || kind}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc: exportDoc(), edits: {}, output_path: outputPath }),
    });
    const data = await resp.json();
    if (!data.ok) showError(`Export failed: ${data.error}`);
    else if (btn) btn.textContent = NARRATIVE_OK_LABELS[kind] || '✓ Saved';
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
// The setup is SAVED in the app database per imported schedule (POST /api/narrative/setup):
// the web view's own storage is empty after every restart and too small for the logos and
// layout drawing. The browser copy above is only this session's cache. [startup:F3] SET-2
const SETUP_RETRY_MS = [1000, 3000, 8000];
let _setupSaveT = null;
let _setupPending = null;
const _setupSeq = {};                          // per schedule: the newest save wins
function postSetup(payload) {
  return fetch(`http://localhost:${PORT()}/api/narrative/setup`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }).then(r => r.json());
}
/** Load the saved setup of the open schedule into state (before the setup chat starts). */
export async function loadSavedSetup(timeoutMs = 5000) {
  const sid = state.currentSnapshotId;
  if (!sid) return null;
  try {
    const d = await Promise.race([postSetup({ snapshot_id: sid }),
      new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), timeoutMs))]);
    if (sid !== state.currentSnapshotId || !d || !d.ok) return null;
    if (d.setup && typeof d.setup === 'object') {
      state.narrativeSetup = d.setup;
      try { localStorage.setItem(setupStoreKey(), JSON.stringify(d.setup)); } catch { /* too big for the browser copy */ }
      return d.setup;
    }
    const local = getSetup();                  // typed earlier this session, not saved yet
    if (local && Object.keys(local).length) saveSetup();
  } catch { /* the app did not answer: this session's copy; saved on the next change */ }
  return null;
}
function sendSetup(payload, seq, attempt) {
  const sid = payload.snapshot_id;
  if (seq !== _setupSeq[sid]) return;          // a newer change is on its way
  postSetup(payload).then(d => {
    if (d && d.ok) return;
    if (d && d.error && !/busy/i.test(d.error)) { showError('Narrative setup not saved — ' + d.error); return; }
    throw new Error((d && d.error) || 'not saved');
  }).catch(() => {
    if (seq !== _setupSeq[sid]) return;
    if (attempt < SETUP_RETRY_MS.length) setTimeout(() => sendSetup(payload, seq, attempt + 1), SETUP_RETRY_MS[attempt]);
    else showError('Narrative setup not saved — the app did not answer. Change any setup field to try again.');
  });
}
function saveSetup() {
  try { localStorage.setItem(setupStoreKey(), JSON.stringify(state.narrativeSetup || {})); } catch (e) { /* ignore */ }
  const sid = state.currentSnapshotId;
  if (!sid) return;
  const payload = { snapshot_id: sid, setup: state.narrativeSetup || {} };
  const seq = _setupSeq[sid] = (_setupSeq[sid] || 0) + 1;
  if (_setupPending && _setupPending.sid !== sid) flushSetupSave();   // never drop another schedule's
  clearTimeout(_setupSaveT);
  _setupPending = { sid, run: () => sendSetup(payload, seq, 0) };
  _setupSaveT = setTimeout(flushSetupSave, 300);
}
function flushSetupSave() {
  clearTimeout(_setupSaveT);
  const p = _setupPending;
  _setupPending = null;
  if (p) p.run();
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
  const attr = v => String(v == null ? '' : v).replace(/"/g, '&quot;');
  const party = (key, label) => `
    <div class="bn-party">
      <label>${label}</label>
      <input type="text" data-k="${key}" placeholder="${label} name" value="${attr(s[key])}"/>
      <label class="bn-file">${s[key + '_logo'] ? '✓ logo' : '＋ logo'}<input type="file" accept="image/*" data-logo="${key}_logo"></label>
    </div>`;
  // Free-text before-run inputs P6 doesn't hold. `data-k` is picked up verbatim by
  // wireSetupForm, so each posts under the exact setup key the model reads
  // (location, contract_type, contract_value → §3 Project Brief / §6 total banner).
  const field = (key, label, ph) => `
    <div class="bn-fld"><label>${label}</label>
      <input type="text" data-k="${key}" placeholder="${ph}" value="${attr(s[key])}"></div>`;
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
      .bn-details{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
      .bn-fld>label{font-size:11px;font-weight:600;color:var(--text-secondary,#565c64);display:block;margin-bottom:6px}
      .bn-fld input{width:100%;box-sizing:border-box;padding:6px 9px;border:1px solid var(--border,#dadee4);border-radius:6px;font:inherit;font-size:12.5px;background:var(--surface-2,#fff);color:var(--text-primary,#1a1d21)}
      #bn-setup-gen{margin-top:12px;font:inherit;font-size:13px;font-weight:600;background:#265f7e;color:#fff;border:none;border-radius:7px;padding:8px 18px;cursor:pointer}
      .bn-layout{display:flex;gap:18px;align-items:flex-start}
      .bn-contents{flex:0 0 220px}
      .bn-select{margin-top:6px}
      .bn-selgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
      .bn-selcol{border:1px solid var(--border,#dadee4);border-radius:9px;padding:9px 11px;max-height:190px;overflow:auto}
      .bn-seltitle{font-size:11px;font-weight:700;color:#265f7e;margin-bottom:5px}
      .bn-seltitle a{font-size:11px;font-weight:500;color:#3487ae;cursor:pointer;text-decoration:underline}
      .bn-chk{display:block;font-size:12px;color:var(--text-primary,#1a1d21);padding:2px 0;cursor:pointer}
      .bn-chk input{margin-right:6px}
      .bn-codegrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
      .bn-codecol{border:1px solid var(--border,#dadee4);border-radius:9px;padding:9px 11px}
      .bn-elgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px;margin-top:6px}
      .bn-elrow{display:flex;align-items:center;gap:8px}
      .bn-elrow>label{flex:0 0 42%;font-size:12px;color:var(--text-primary,#1a1d21);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .bn-code{padding:5px 8px;border:1px solid var(--border,#dadee4);border-radius:6px;font:inherit;font-size:12px;background:var(--surface-2,#fff);color:var(--text-primary,#1a1d21)}
      .bn-codecol .bn-code{width:100%;box-sizing:border-box;margin-top:5px}
      .bn-elrow .bn-code{flex:1;min-width:0}
      .bn-scopelist{display:flex;flex-direction:column;gap:6px;margin:8px 0}
      .bn-scoperow{display:flex;align-items:center;gap:10px;border:1px solid var(--border,#dadee4);border-radius:8px;padding:7px 10px;background:var(--surface-2,#fff)}
      .bn-lvl{flex:0 0 auto;width:22px;height:22px;border-radius:50%;background:#1F4E79;color:#fff;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center}
      .bn-scopename{flex:1;font-size:13px;font-weight:600;color:var(--text-primary,#1a1d21);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .bn-scopeacts{flex:0 0 auto;display:flex;gap:4px}
      .bn-mv{width:26px;height:26px;border:1px solid var(--border,#dadee4);border-radius:6px;background:var(--surface,#f6f8fb);color:#265f7e;font-size:11px;cursor:pointer;line-height:1;padding:0}
      .bn-mv:hover:not(:disabled){background:#e6eef6;border-color:#1F4E79}
      .bn-mv:disabled{opacity:.35;cursor:default}
      .bn-mv[data-mv="rm"]{color:#b3402f}
      .bn-scopeadd{margin-top:2px;padding:6px 9px;border:1px dashed #7aa3c7;border-radius:7px;font:inherit;font-size:12px;background:var(--surface-2,#fff);color:#1F4E79;cursor:pointer}
      .bn-scopepath{margin-top:8px;font-size:11.5px;color:#4a5560;background:#f2f6fb;border-left:3px solid #1F4E79;border-radius:0 5px 5px 0;padding:6px 10px}
      .bn-seqlist{display:flex;flex-direction:column;gap:6px;margin:8px 0}
      .bn-seqrow{display:flex;align-items:center;gap:8px;border:1px solid var(--border,#dadee4);border-radius:8px;padding:7px 10px;background:var(--surface-2,#fff)}
      .bn-seqsel{flex:1;min-width:0;padding:5px 8px;border:1px solid var(--border,#dadee4);border-radius:6px;font:inherit;font-size:12px;background:var(--surface-2,#fff);color:var(--text-primary,#1a1d21)}
      .bn-seqarrow{flex:0 0 auto;color:#1F4E79;font-weight:700}
      .bn-seqmv{width:26px;height:26px;border:1px solid var(--border,#dadee4);border-radius:6px;background:var(--surface,#f6f8fb);font-size:11px;cursor:pointer;line-height:1;padding:0;flex:0 0 auto;color:#b3402f}
      .bn-seqmv:hover{background:#f6e6e6;border-color:#b3402f}
      .bn-seqord{width:26px;height:26px;border:1px solid var(--border,#dadee4);border-radius:6px;background:var(--surface,#f6f8fb);font-size:12px;cursor:pointer;line-height:1;padding:0;flex:0 0 auto;color:#1F4E79}
      .bn-seqord:hover:not(:disabled){background:#e8f0f8;border-color:#1F4E79}
      .bn-seqord:disabled{opacity:.35;cursor:default}
      .bn-seqadd{margin-top:2px;padding:6px 9px;border:1px dashed #7aa3c7;border-radius:7px;font:inherit;font-size:12px;background:var(--surface-2,#fff);color:#1F4E79;cursor:pointer}
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
      <h4 style="margin:14px 0 3px">Contract details</h4>
      <div class="hint">P6 doesn't hold these — enter them before generating. Contract value pre-fills from the schedule's cost loading.</div>
      <div class="bn-details">
        ${field('location', 'Project Location', 'e.g. Riyadh, Saudi Arabia')}
        ${field('contract_type', 'Contract Type', 'e.g. Lump-Sum')}
        ${field('contract_value', 'Contract Value', 'from cost loading')}
      </div>
      <div id="bn-select" class="bn-select"></div>
      <button id="bn-setup-gen">Generate narrative</button>
    </div>`;
}

// Comments 4 & 5 — pick which Major Milestones and Key Dates to include (before Run).
// Populated from the generated doc's meta.*_choices; the selection is stored in the
// setup and posted with the next generate/export, which the server filters on.
// Comment 45 — the planner orders the activity codes freely: swap the two codes of a sequence
// analysis (e.g. 'Type of Works' → 'Type of Civil Works' becomes 'Type of Civil Works' →
// 'Type of Works') and move whole analyses up / down. Pure: return new arrays.
export function swapSeqCodes(list, i) {
  return (list || []).map((a, k) => (k === i && a && Array.isArray(a.codes) && a.codes.length === 2)
    ? { ...a, codes: [a.codes[1], a.codes[0]] } : a);
}
export function moveItem(list, i, dir) {
  const out = (list || []).slice();
  const j = dir === 'up' ? i - 1 : i + 1;
  if (i < 0 || i >= out.length || j < 0 || j >= out.length) return out;
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}

function _esc(x) {
  return String(x == null ? '' : x).replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
// The §7 discipline names (from the generated Scope section's payload) — the keys the
// model's `element_codes` map is looked up by, so the per-discipline element selectors
// rebuild to match whatever the current type-of-work code produced.
function scopeDisciplines() {
  const secs = (state.narrativeDoc && state.narrativeDoc.sections) || [];
  const scope = secs.find(x => x && x.kind === 'scope');
  const list = (scope && scope.payload && scope.payload.disciplines) || [];
  return list.map(d => d && d.name).filter(Boolean);
}

// Pre-fill the Contract Value text field from the cost-loading sum the server surfaces on
// meta.contract_value — only when the planner hasn't set one (never clobbers a typed value
// or a deliberate clear). The field posts under the `contract_value` key the model reads.
function prefillContractValue(meta) {
  const inp = document.querySelector('.bn-setup input[data-k="contract_value"]');
  if (!inp) return;
  const cv = meta && meta.contract_value;
  if (cv == null || cv === '') return;
  const num = Math.round(Number(cv));
  if (!isFinite(num)) return;
  const str = String(num);
  inp.placeholder = str;
  const s = getSetup();
  if (!inp.value && s.contract_value == null) {
    inp.value = str;
    s.contract_value = str;
    saveSetup();
  }
}

function renderSelection() {
  const box = document.getElementById('bn-select');
  if (!box) return;
  const meta = (state.narrativeDoc && state.narrativeDoc.meta) || {};
  const ms = meta.milestone_choices || [];
  const kd = meta.key_date_choices || [];
  const codes = meta.code_choices || [];        // activity-code STRUCTURES in the file
  const disciplines = scopeDisciplines();
  prefillContractValue(meta);
  if (!ms.length && !kd.length && !codes.length && !disciplines.length) { box.innerHTML = ''; return; }
  const s = getSetup();

  // ── Scope analysis — FLEXIBLE ordered activity-code picker (§6 + §7) ───────────
  // The planner picks ANY NUMBER of the file's activity codes, IN ORDER. The 1st code is
  // the top level of the breakdown and drives the §6 Contract Value split; each code added
  // below nests one level deeper, cost-weighted. Stored as s.scope_codes (ordered array);
  // empty = auto-detect (server falls back to its built-in hint matching).
  let scopeCodes;
  const rawScope = Array.isArray(s.scope_codes) ? s.scope_codes : null;
  if (rawScope === null) {                       // first open → seed the picker from auto-detect
    scopeCodes = (meta.scope_codes_auto || []).filter(c => codes.includes(c));
    s.scope_codes = scopeCodes.slice(); saveSetup();
  } else {
    scopeCodes = rawScope.filter(c => codes.includes(c));
    if (!scopeCodes.length && rawScope.length) { // stale picks from another file → re-seed
      scopeCodes = (meta.scope_codes_auto || []).filter(c => codes.includes(c));
      s.scope_codes = scopeCodes.slice(); saveSetup();
    }
  }
  let codeHtml = '';
  if (codes.length) {
    const rows = scopeCodes.map((c, i) =>
      `<div class="bn-scoperow"><span class="bn-lvl">${i + 1}</span>` +
      `<span class="bn-scopename">${_esc(c)}</span><span class="bn-scopeacts">` +
      `<button type="button" class="bn-mv" data-mv="up" data-i="${i}" title="Move up"${i === 0 ? ' disabled' : ''}>&#9650;</button>` +
      `<button type="button" class="bn-mv" data-mv="down" data-i="${i}" title="Move down"${i === scopeCodes.length - 1 ? ' disabled' : ''}>&#9660;</button>` +
      `<button type="button" class="bn-mv" data-mv="rm" data-i="${i}" title="Remove">&#10005;</button>` +
      '</span></div>').join('');
    const remaining = codes.filter(c => !scopeCodes.includes(c));
    const addOpts = ['<option value="">+ Add an activity code…</option>']
      .concat(remaining.map(c => `<option value="${_esc(c)}">${_esc(c)}</option>`)).join('');
    codeHtml =
      '<h4 style="margin:14px 0 3px">Scope analysis — activity codes</h4>' +
      '<div class="hint">Choose which activity codes to analyse the Scope of Work by, <b>in order</b>. ' +
      'The 1st code is the top level of the breakdown and splits the Contract Value; each code you add ' +
      'below drills one level deeper, weighted by cost. Pick as many as you like — reorder with the ' +
      'arrows, remove with ✕. Leave empty to auto-detect a sensible breakdown.</div>' +
      `<div class="bn-scopelist">${rows ||
        '<div class="hint" style="padding:6px 2px">No codes picked — the report will auto-detect the breakdown.</div>'}</div>` +
      (remaining.length ? `<select class="bn-scopeadd">${addOpts}</select>` : '') +
      (scopeCodes.length
        ? `<div class="bn-scopepath"><b>Cascade:</b> ${scopeCodes.map(_esc).join(' &rarr; ')}</div>` : '');
  }

  // ── Sequence of Work — flexible 1-or-2 activity-code sequence analyses (§11) ────
  // Each analysis is ONE code (a general execution sequence) or TWO codes — a group-by code
  // and a work-type code — for a per-building sequence (identical buildings grouped). The order
  // is read from the schedule's dependency logic. Stored as s.sequence_codes = [{codes:[a]|[a,b]}].
  const cleanSeq = a => {
    const cc = (a && Array.isArray(a.codes) ? a.codes : []).filter(c => codes.includes(c));
    const dedup = [];
    cc.forEach(c => { if (!dedup.includes(c)) dedup.push(c); });
    return dedup.slice(0, 2);
  };
  const seedSeq = () => {
    const auto = (meta.scope_codes_auto || []).filter(c => codes.includes(c));
    const seeded = [];
    if (auto[0]) seeded.push({ codes: [auto[0]] });              // general sequence
    if (auto.length >= 3) seeded.push({ codes: [auto[1], auto[2]] }); // per-building pair
    return seeded;
  };
  let seqAnalyses;
  const rawSeq = Array.isArray(s.sequence_codes) ? s.sequence_codes : null;
  if (rawSeq === null) {                          // first open → seed from the auto cascade
    seqAnalyses = seedSeq();
    s.sequence_codes = seqAnalyses.map(a => ({ codes: a.codes.slice() })); saveSetup();
  } else {
    seqAnalyses = rawSeq.map(a => ({ codes: cleanSeq(a) })).filter(a => a.codes.length);
  }
  let seqHtml = '';
  if (codes.length) {
    const opt = (sel, placeholder) =>
      [`<option value="">${placeholder}</option>`].concat(
        codes.map(c => `<option value="${_esc(c)}"${c === sel ? ' selected' : ''}>${_esc(c)}</option>`)
      ).join('');
    const rows = seqAnalyses.map((a, i) =>
      `<div class="bn-seqrow"><span class="bn-lvl">${i + 1}</span>` +
      `<select class="bn-seqsel" data-i="${i}" data-slot="0" title="1st activity code (required)">${opt(a.codes[0] || '', '— pick a code —')}</select>` +
      `<button type="button" class="bn-seqord" data-seqswap="${i}" title="Swap: make the 2nd code 1st and the 1st code 2nd"${a.codes.length === 2 ? '' : ' disabled'}>&#8644;</button>` +
      `<select class="bn-seqsel" data-i="${i}" data-slot="1" title="2nd activity code (optional)">${opt(a.codes[1] || '', '— none (single) —')}</select>` +
      `<button type="button" class="bn-seqord" data-seqmv="up" data-i="${i}" title="Move this analysis up"${i === 0 ? ' disabled' : ''}>&#9650;</button>` +
      `<button type="button" class="bn-seqord" data-seqmv="down" data-i="${i}" title="Move this analysis down"${i === seqAnalyses.length - 1 ? ' disabled' : ''}>&#9660;</button>` +
      `<button type="button" class="bn-seqmv" data-seqrm="${i}" title="Remove">&#10005;</button>` +
      '</div>').join('');
    seqHtml =
      '<h4 style="margin:16px 0 3px">Sequence of Work — activity codes</h4>' +
      '<div class="hint">Add one or more <b>sequence analyses</b> for §11. Pick <b>one</b> code for a ' +
      'general execution sequence, or add a <b>second</b> code to sequence each building/group by ' +
      'that code (identical buildings are grouped, e.g. “Silos 1–10”). The order of work is read ' +
      'from the schedule’s dependency logic. <b>&#8644;</b> swaps which code comes 1st and 2nd; ' +
      '<b>&#9650; &#9660;</b> reorder the analyses. Leave empty to auto-detect.</div>' +
      `<div class="bn-seqlist">${rows ||
        '<div class="hint" style="padding:6px 2px">No analyses — §11 will auto-detect a sensible sequence.</div>'}</div>` +
      '<button type="button" class="bn-seqadd">+ Add sequence analysis</button>';
  }

  // ── §4 / §5 include checklists (unchanged behaviour) ─────────────────────────
  const col = (title, items, key) => {
    const sel = Array.isArray(s[key]) ? new Set(s[key]) : null;    // null = all included
    const rows = items.map(label =>
      `<label class="bn-chk"><input type="checkbox" data-sel="${key}" value="${_esc(label)}"${(!sel || sel.has(label)) ? ' checked' : ''}> ${_esc(label)}</label>`).join('');
    return `<div class="bn-selcol"><div class="bn-seltitle">${title} — <a data-all="${key}">all</a> · <a data-none="${key}">none</a></div>${rows || '<span class="hint">none in the file</span>'}</div>`;
  };
  let selHtml = '';
  if (ms.length || kd.length) {
    selHtml =
      '<h4 style="margin:14px 0 3px">Choose what to include</h4>' +
      '<div class="hint">Tick the Major Milestones and Key Dates to show, then Generate. All included by default.</div>' +
      `<div class="bn-selgrid">${col('Major Milestones', ms, 'milestone_keys')}${col('Key Dates', kd, 'key_date_keys')}</div>`;
  }

  box.innerHTML = codeHtml + seqHtml + selHtml;

  // Wire the §11 sequence-analyses picker → s.sequence_codes ([{codes:[a]|[a,b]}]).
  const reSeq = () => {
    s.sequence_codes = seqAnalyses.map(a => ({ codes: a.codes.filter(Boolean).slice(0, 2) }));
    saveSetup(); renderSelection();
  };
  box.querySelectorAll('.bn-seqsel').forEach(sel => sel.addEventListener('change', () => {
    const i = +sel.dataset.i, slot = +sel.dataset.slot;
    if (!seqAnalyses[i]) return;
    const cc = seqAnalyses[i].codes.slice();
    if (slot === 0) {
      if (!sel.value) { seqAnalyses.splice(i, 1); reSeq(); return; }   // primary cleared → drop
      seqAnalyses[i].codes = [sel.value].concat(cc[1] && cc[1] !== sel.value ? [cc[1]] : []);
    } else {
      const first = cc[0];
      if (!first) { reSeq(); return; }
      seqAnalyses[i].codes = sel.value && sel.value !== first ? [first, sel.value] : [first];
    }
    reSeq();
  }));
  box.querySelectorAll('[data-seqrm]').forEach(b => b.addEventListener('click', () => {
    seqAnalyses.splice(+b.dataset.seqrm, 1); reSeq();
  }));
  box.querySelectorAll('[data-seqswap]').forEach(b => b.addEventListener('click', () => {
    seqAnalyses = swapSeqCodes(seqAnalyses, +b.dataset.seqswap); reSeq();
  }));
  box.querySelectorAll('[data-seqmv]').forEach(b => b.addEventListener('click', () => {
    seqAnalyses = moveItem(seqAnalyses, +b.dataset.i, b.dataset.seqmv); reSeq();
  }));
  const seqAdd = box.querySelector('.bn-seqadd');
  if (seqAdd) seqAdd.addEventListener('click', () => {
    const auto = (meta.scope_codes_auto || []).filter(c => codes.includes(c));
    seqAnalyses.push({ codes: [auto[0] || codes[0]] });
    reSeq();
  });

  // Wire the flexible scope-code picker (reorder / remove / add) → s.scope_codes (ordered).
  const reScope = () => { s.scope_codes = scopeCodes.slice(); saveSetup(); renderSelection(); };
  box.querySelectorAll('.bn-mv').forEach(b => b.addEventListener('click', () => {
    const i = +b.dataset.i, mv = b.dataset.mv;
    if (mv === 'rm') scopeCodes.splice(i, 1);
    else if (mv === 'up' && i > 0) [scopeCodes[i - 1], scopeCodes[i]] = [scopeCodes[i], scopeCodes[i - 1]];
    else if (mv === 'down' && i < scopeCodes.length - 1)
      [scopeCodes[i + 1], scopeCodes[i]] = [scopeCodes[i], scopeCodes[i + 1]];
    reScope();
  }));
  const addSel = box.querySelector('.bn-scopeadd');
  if (addSel) addSel.addEventListener('change', () => {
    if (addSel.value && !scopeCodes.includes(addSel.value)) { scopeCodes.push(addSel.value); reScope(); }
  });

  const collect = key => Array.from(box.querySelectorAll(`input[data-sel="${key}"]`))
    .filter(c => c.checked).map(c => c.value);
  box.querySelectorAll('input[data-sel]').forEach(c => c.addEventListener('change', () => {
    s[c.dataset.sel] = collect(c.dataset.sel); saveSetup();
  }));
  box.querySelectorAll('[data-all]').forEach(a => a.addEventListener('click', () => {
    box.querySelectorAll(`input[data-sel="${a.dataset.all}"]`).forEach(c => { c.checked = true; });
    s[a.dataset.all] = collect(a.dataset.all); saveSetup();
  }));
  box.querySelectorAll('[data-none]').forEach(a => a.addEventListener('click', () => {
    box.querySelectorAll(`input[data-sel="${a.dataset.none}"]`).forEach(c => { c.checked = false; });
    s[a.dataset.none] = []; saveSetup();
  }));
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

// ══ Conversational guided setup — the smart interview ══════════════════════════
// Instead of a wall of controls, the planner is walked through the report's inputs one
// question at a time. The tool pre-reads the file (an initial /api/narrative call returns
// meta.*_choices + scope_codes_auto) and pre-fills every answer it can detect, so the
// planner mostly CONFIRMS. It writes into the SAME setup object the classic form used
// (location, contract_type, revision, *_logo, layout, milestone_keys, key_date_keys,
// scope_codes, sequence_codes) and, when finished, calls the unchanged generate path.
// The contract value is never asked — the report derives it automatically from the cost
// loading — matching the planner's steer that it needs no input.

const CONTRACT_TYPES = ['Lump sum', 'Remeasurable', 'EPC / turnkey', 'Cost plus', 'Unit rate', 'Design and build'];
// AI Assistant (Ibrahim, 20-Oct): the setup is a chat with "your AI Planning Engineer" - 10
// questions, typed answers or one-click suggestions, and for the scope / sequence questions live
// examples from the planner's own file ("if you pick this code, section 7 reads like this").
const CHAT_STEPS = ['location', 'contract_type', 'revision', 'parties', 'layout', 'milestones', 'key_dates', 'scope', 'sequence', 'generate'];
const CHAT_Q = {
  location:      'Where is the project? It goes on the cover and in section 3 (Project Brief).',
  contract_type: 'What type of contract is it? (section 3)',
  revision:      'Which revision is this baseline? It goes on the cover and in every page header. (The contract value I take from your cost loading — nothing to enter.)',
  parties:       'Who are the parties? Their names go in section 3 and their logos in the page header. Skip any you don’t have.',
  layout:        'Add your project layout drawings for section 2 — one or several. Give each a title; it becomes the figure caption (Figure 2.1, 2.2 …), one drawing per page.',
  milestones:    'I found your milestones and ticked the main ones. Confirm what appears in section 4 (Contract Milestones).',
  key_dates:     'And the key dates for section 5 — the client inputs and deliveries the works depend on. Keep, untick or add.',
  scope:         'Now the Scope of Work (section 7). I describe the scope in detail from your activity codes, weighted by the baseline cost. Each analysis is ONE code (what the scope consists of, e.g. Type of Work: Civil Works · Steel Works · MEP …) or TWO codes combined (e.g. Type of Work + Building: Civil Works and under it every building that has civil works, then Steel Works and its buildings, and so on). Add one or more analyses, like the Sequence of Work. Below is exactly what section 7 says for each choice, from your own file. Tip: pick codes that every construction activity carries — a code that only a few activities carry leaves the rest as “Unclassified”.',
  sequence:      'Next the Sequence of Work (section 11). Each analysis puts the work in the order your baseline logic runs it (read from the relationships, not assumed), drawn as a chevron flow: ONE code = the order of the whole project (e.g. which trade comes first); TWO codes = the order inside each area (e.g. per building, which work comes first) — areas with the same order are grouped. Below is exactly what section 11 shows for each choice, from your own file. Pick one or more analyses.',
  generate:      'That’s everything I need. Here is your setup — click Back to change any answer. Shall I build the report?',
};
const CHAT_TITLE = { location: 'Location', contract_type: 'Contract type', revision: 'Revision', parties: 'Parties & logos (optional)',
  layout: 'Project layout drawings (optional)', milestones: 'Contract milestones', key_dates: 'Key dates', scope: 'Scope of Work (section 7)',
  sequence: 'Sequence of Work (section 11)', generate: 'Build the report' };
// The opening message: who the assistant is + what it read from the file.
function chatIntro() {
  const m = _chatMeta || {};
  const facts = [m.activity_count ? `<b>${Number(m.activity_count).toLocaleString()} activities</b>` : '',
    m.contract_value ? `contract value from the cost loading <b>${(m.contract_value / 1e6).toLocaleString(undefined, { maximumFractionDigits: 1 })} M</b>` : ''].filter(Boolean).join(', ');
  return `<b>I am your AI Planning Engineer and I will build for you the narrative report for the baseline — but let me ask you some questions.</b><br><br>`
    + `I've read <b>${_esc(m.project_name || 'your schedule')}</b>${facts ? ': ' + facts : ''}. Most answers are already filled in from the file — you mostly confirm. `
    + `There are ${CHAT_STEPS.length} short questions. Type your answer below, click a suggestion, or say <i>skip</i>, <i>go back</i> or <i>change …</i> at any time.`;
}
let _chatMeta = {};
let _chatMetaFor = null;   // which file the detected choices were read from (Edit setup reuses them)
let _chatCur = 0;
const chatFileKey = () => [state.currentXmlPath || '', state.currentCachedPath || '', state.currentSnapshotId || ''].join('|');

function chatCss() {
  return `<style>
    .bn-chat{max-width:900px;margin:0 auto;border:1px solid var(--border,#dadee4);border-radius:14px;background:var(--surface-2,#fff);overflow:hidden}
    .bn-chat-head{display:flex;align-items:center;gap:10px;padding:13px 18px;border-bottom:1px solid var(--border,#e4e8ee)}
    .bn-chat-av{width:30px;height:30px;border-radius:50%;background:#e8f1fb;color:#1F4E79;display:flex;align-items:center;justify-content:center;font-size:16px;flex:0 0 auto}
    .bn-chat-title{font-size:14px;font-weight:700;color:#1a1d21;line-height:1.15}
    .bn-chat-sub{font-size:11.5px;color:var(--text-secondary,#5a626b)}
    .bn-thread{padding:16px 18px 4px;flex:1 1 auto;min-height:0;overflow-y:auto;overflow-x:hidden;scroll-behavior:smooth;position:relative}
    .bn-chat{display:flex;flex-direction:column;height:calc(100vh - 190px);min-height:460px}
    .bn-row{display:flex;gap:9px;margin-bottom:14px}
    .bn-row.me{justify-content:flex-end}
    .bn-av{width:26px;height:26px;border-radius:50%;background:#e8f1fb;color:#1F4E79;flex:0 0 auto;display:flex;align-items:center;justify-content:center;font-size:14px}
    .bn-bub{background:var(--surface,#f5f8fb);border:1px solid var(--border,#e4e8ee);border-radius:13px;border-top-left-radius:3px;padding:10px 13px;font-size:13.5px;line-height:1.5;color:var(--text-primary,#1a1d21);max-width:84%}
    .bn-ans{background:#1F4E79;color:#fff;border-radius:13px;border-top-right-radius:3px;padding:8px 13px;font-size:13px;max-width:84%}
    .bn-ctl{margin:2px 0 6px 35px}
    .bn-ci{width:80%;max-width:420px;box-sizing:border-box;padding:9px 12px;border:1px solid var(--border,#c7cdd4);border-radius:8px;font:inherit;font-size:13.5px;background:var(--surface-2,#fff);color:var(--text-primary,#1a1d21)}
    .bn-chip2{font:inherit;font-size:12.5px;border:1px solid var(--border,#c7cdd4);background:var(--surface-2,#fff);color:var(--text-primary,#1a1d21);border-radius:18px;padding:6px 13px;margin:0 6px 6px 0;cursor:pointer}
    .bn-chip2:hover{border-color:#1F4E79}
    .bn-chip2.on{background:#1F4E79;color:#fff;border-color:#1F4E79}
    .bn-tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;max-width:460px;margin-bottom:9px}
    .bn-tile{border:1px dashed #9bb6cc;border-radius:9px;height:56px;display:flex;align-items:center;justify-content:center;text-align:center;font-size:11.5px;color:#3487ae;cursor:pointer;padding:0 6px;position:relative}
    .bn-tile.on{border-style:solid;border-color:#1F8f5f;color:#1F8f5f;background:#eef8f1}
    .bn-tile input{position:absolute;inset:0;opacity:0;cursor:pointer}
    .bn-cklist{display:grid;grid-template-columns:1fr 1fr;gap:14px;max-width:520px}
    .bn-cktitle{font-size:11px;font-weight:700;color:#265f7e;margin-bottom:5px}
    .bn-cktitle a{font-size:11px;font-weight:500;color:#3487ae;cursor:pointer;text-decoration:underline}
    .bn-ck{display:flex;align-items:center;gap:7px;font-size:12.5px;padding:3px 0;cursor:pointer}
    .bn-ck input{width:15px;height:15px}
    .bn-add2{display:inline-flex;align-items:center;gap:5px;font:inherit;font-size:12px;color:#1F4E79;background:#eaf1f9;border:none;border-radius:16px;padding:6px 12px;cursor:pointer;margin:3px 0}
    .bn-add2:hover{background:#dbe7f5}
    .bn-addsel{font:inherit;font-size:12px;border:1px solid #c7cdd4;border-radius:16px;padding:5px 10px;background:var(--surface-2,#fff);color:#1F4E79;margin:3px 0}
    .bn-cflow{display:flex;flex-direction:column;gap:7px;align-items:flex-start;margin:4px 0}
    .bn-cchain{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
    .bn-cchip{display:inline-flex;align-items:center;gap:5px;background:var(--surface-2,#fff);border:1px solid #b7c3d1;color:#1a2b3d;font-size:12px;padding:5px 9px;border-radius:16px}
    .bn-cchip b{font-weight:700;color:#1F4E79}
    .bn-ch{color:#7c8794;cursor:pointer;font-size:12px}
    .bn-ch:hover{color:#1F4E79}
    .bn-carrow{color:#9aa4b0;font-size:12px}
    .bn-sw{font-size:15px;color:#1F4E79}
    .bn-srow{display:flex;align-items:center;gap:7px;border:1px solid var(--border,#dadee4);border-radius:8px;padding:6px 9px;background:var(--surface-2,#fff);max-width:520px}
    .bn-sq,.bn-sc{flex:1;min-width:0;padding:5px 8px;border:1px solid #c7cdd4;border-radius:6px;font:inherit;font-size:12px;background:var(--surface-2,#fff);color:var(--text-primary,#1a1d21)}
    .bn-lvl2{flex:0 0 auto;width:20px;height:20px;border-radius:50%;background:#1F4E79;color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center}
    .bn-x{color:#b3402f;cursor:pointer;font-size:14px;flex:0 0 auto}
    .bn-hint2{font-size:11.5px;color:var(--text-muted,#8a9099);margin:4px 0 2px}
    .bn-sum{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;font-size:12.5px;max-width:520px;margin:4px 0 12px}
    .bn-sum .k{color:var(--text-secondary,#5a626b)}
    .bn-gen{height:40px;padding:0 20px;background:#1F4E79;color:#fff;border:none;border-radius:8px;font:inherit;font-size:13.5px;font-weight:600;cursor:pointer}
    .bn-gen:disabled{opacity:.6;cursor:default}
    .bn-chat-foot{display:flex;align-items:center;justify-content:space-between;padding:11px 18px 15px;border-top:1px solid var(--border,#e4e8ee)}
    .bn-back{font:inherit;font-size:12.5px;background:none;border:none;color:var(--text-secondary,#5a626b);cursor:pointer}
    .bn-back:hover{color:#1F4E79}
    .bn-continue{font:inherit;font-size:13px;font-weight:600;background:#265f7e;color:#fff;border:none;border-radius:7px;padding:8px 20px;cursor:pointer}
    .bn-report-bar{max-width:900px;margin:0 auto 10px;text-align:right}
    .bn-edit-setup{font:inherit;font-size:12.5px;border:1px solid #3487ae;color:#3487ae;background:transparent;border-radius:7px;padding:6px 13px;cursor:pointer}
    .bn-edit-setup:hover{background:rgba(52,135,174,.08)}
  
    .bn-ai .bn-bub{background:transparent;border:0;padding:2px 0;max-width:100%}
    .bn-who{font-size:11.5px;font-weight:700;color:var(--muted,#6b7686);margin-bottom:2px}
    .bn-say{font-size:13.5px;line-height:1.6;color:var(--text,#1a1d21)}
    .bn-w{opacity:0;transition:opacity .18s}.bn-w.on{opacity:1}
    .bn-think{display:flex;align-items:center;gap:4px;font-size:12px;color:var(--muted,#6b7686)}
    .bn-think span{width:6px;height:6px;border-radius:50%;background:var(--muted,#9aa6b5);animation:bnth 1s infinite}
    .bn-think span:nth-child(2){animation-delay:.2s}.bn-think span:nth-child(3){animation-delay:.4s}
    @keyframes bnth{0%,100%{opacity:.25}50%{opacity:1}}
    .bn-chap{align-self:center;margin:6px auto;font-size:11px;font-weight:700;color:#fff;background:var(--accent,#1F4E79);border-radius:10px;padding:2px 12px;width:max-content}
    .bn-type{display:flex;gap:8px;padding:10px 16px;border-top:1px solid var(--border,#e4e8ee)}
    .bn-type input{flex:1;border:1px solid var(--border,#dadee4);border-radius:20px;padding:8px 14px;font:inherit;font-size:13px;background:var(--bg,#fff);color:var(--text,#1a1d21);outline:0}
    .bn-type input:focus{border-color:var(--accent,#1F4E79)}
    .bn-type button{width:36px;height:36px;border-radius:50%;border:0;background:var(--accent,#1F4E79);color:#fff;cursor:pointer;font-size:14px}
    .bn-pv{display:flex;flex-direction:column;gap:10px;margin-bottom:6px}
    .bn-ex{border:1px solid var(--border,#dadee4);border-radius:10px;padding:8px 10px;background:var(--surface-2,#fff)}
    .bn-exh{font-size:12.5px;font-weight:700;color:var(--accent,#1F4E79);margin-bottom:5px}
    .bn-rep{border:1px solid #c9d2de;border-radius:6px;background:#fff;padding:8px 10px;font-size:12px;color:#1a1d21}
    .bn-rh{color:#1F4E79;font-weight:800;border-bottom:2px solid #1F4E79;padding-bottom:2px;margin-bottom:5px}
    .bn-rh2{color:#1F4E79;font-weight:700;margin:6px 0 3px}
    .bn-hb{display:flex;align-items:center;gap:6px;margin:2px 0}.bn-hb span{width:190px;font-size:11.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .bn-hb i{display:block;height:10px;background:#1F4E79;border-radius:2px}.bn-hb b{font-size:11px;color:#3b4656;white-space:nowrap;font-weight:600}
    .bn-pt{border-collapse:collapse;width:100%;font-size:11.5px}.bn-pt td{padding:2px 6px;border-bottom:1px solid #edf0f4;vertical-align:top}
    .bn-chev{display:flex;flex-wrap:wrap;gap:3px;margin:3px 0}
    .bn-chev span{background:#1F4E79;color:#fff;font-size:10.5px;padding:3px 13px 3px 11px;clip-path:polygon(0 0,calc(100% - 8px) 0,100% 50%,calc(100% - 8px) 100%,0 100%,6px 50%)}
    .bn-grp{font-size:11px;font-weight:700;margin-top:4px}
    .bn-warn{border-left:3px solid #d68a1c;background:#fff8ea;padding:4px 8px;margin-top:5px;font-size:11.5px;color:#5a4a1a}
    .bn-lays{display:flex;flex-wrap:wrap;gap:10px}
    .bn-lay{width:190px;border:1px solid var(--border,#dadee4);border-radius:9px;overflow:hidden;background:#fff}
    .bn-lay img{display:block;width:100%;height:110px;object-fit:cover;background:#eef2f7}
    .bn-lay .bn-ci{width:100%;box-sizing:border-box;border:0;border-top:1px solid var(--border,#dadee4);border-radius:0;margin:0}
    .bn-layact{display:flex;align-items:center;gap:8px;padding:4px 8px;border-top:1px solid var(--border,#dadee4);font-size:12px}
    .bn-layadd{width:190px;min-height:170px;border:2px dashed #9fb3c8;border-radius:9px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--accent,#1F4E79);font-weight:700;cursor:pointer;position:relative}
    .bn-layadd span{font-weight:400;font-size:11.5px;color:var(--muted,#6b7686)}
    .bn-layadd input{position:absolute;inset:0;opacity:0;cursor:pointer}

    .bn-cklist:has(.bn-msbox){display:block;width:100%;max-width:none}
    .bn-msbox{width:100%;box-sizing:border-box;border:1px solid var(--border,#dadee4);border-radius:10px;background:var(--surface-2,#fff);overflow:hidden;max-width:100%}
    .bn-mshead{display:flex;align-items:center;gap:10px;padding:7px 10px;border-bottom:1px solid var(--border,#e4e8ee);font-size:12.5px;flex-wrap:wrap}
    .bn-mshead a{color:var(--accent,#1F4E79);cursor:pointer;font-weight:600}
    .bn-mscount{color:var(--muted,#6b7686);font-size:12px}
    .bn-mssearch{margin-left:auto;border:1px solid var(--border,#dadee4);border-radius:14px;padding:3px 10px;font:inherit;font-size:12px;width:150px;background:var(--bg,#fff);color:var(--text,#1a1d21)}
    .bn-mslist{max-height:min(46vh,330px);overflow-y:auto;overflow-x:hidden;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:0 14px;padding:6px 10px}
    @media (max-width:760px){.bn-mslist{grid-template-columns:minmax(0,1fr)}}
    .bn-msrow{min-width:0;display:flex;align-items:center;gap:7px;padding:3px 0;font-size:12.5px;border-bottom:1px dashed var(--border,#eef0f3);cursor:pointer}
    .bn-msrow .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .bn-msrow .dt{color:var(--muted,#6b7686);font-size:11.5px;white-space:nowrap}

    .bn-cons{font-size:11.5px;margin:2px 0;color:#1a1d21}.bn-cons b{color:#1F4E79}
    .bn-combo{font-size:11.5px;margin:4px 0 4px 4px}.bn-combo b{color:#1F4E79}.bn-combo div{color:#3b4656;margin:1px 0 0 14px}
</style>`;
}

// The toolbar Word/PDF/HTML export bar only makes sense once a report is mounted; hide it during
// the interview so a premature export can't write an empty/stale report.
function exportBar(show) {
  document.querySelectorAll('.bn-exportbar').forEach(b => { b.style.display = show ? 'flex' : 'none'; });
}

// One LIGHTWEIGHT /api/narrative/choices call that returns ONLY the detected choices (no
// section building) — used to seed the chat before showing any question. Does not mount the
// report. The full report is built once, later, at the Generate step (POST /api/narrative).
async function fetchDetected() {
  if (!state.currentXmlPath && !state.currentCachedPath) return null;
  try {
    const resp = await fetch(`http://localhost:${PORT()}/api/narrative/choices`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        xml_path: state.currentXmlPath, cached_path: state.currentCachedPath,
        snapshot_id: state.currentSnapshotId || null, setup: setupForSend(),
      }),
    });
    const data = await resp.json();
    if (!data.ok) return null;
    // NB: do NOT set state.narrativeDoc here — the toolbar export buttons gate on it, so setting it
    // mid-interview (before the report is mounted) would let a premature export write an empty/stale
    // report. Detection only needs the meta (the detected choices); the real generate path sets it.
    // The choices endpoint returns {ok, meta} (no doc), unlike /api/narrative which returns {ok, doc}.
    _chatMeta = data.meta || {};
    _chatMetaFor = chatFileKey();
    return _chatMeta;
  } catch { return null; }
}

function chatCodes() { return (_chatMeta.code_choices || []); }

// Current ordered scope codes from the setup (seeded from auto-detect on first open).
function curScope() {
  const s = getSetup(), codes = chatCodes();
  const raw = Array.isArray(s.scope_codes) ? s.scope_codes : null;
  let sc;
  if (raw === null) { sc = (_chatMeta.scope_codes_auto || []).filter(c => codes.includes(c)); s.scope_codes = sc.slice(); saveSetup(); }
  else { sc = raw.filter(c => codes.includes(c)); }
  return sc;
}
function setScope(sc) { const s = getSetup(); s.scope_codes = sc.slice(); saveSetup(); }

// Scope analyses (comment 103 - the same as the Sequence of Work): each one code, or a combination.
function curScopeAn() {
  const s = getSetup(), codes = chatCodes();
  if (Array.isArray(s.scope_analyses)) {
    return s.scope_analyses.map(a => ({ codes: (Array.isArray(a.codes) ? a.codes : []).filter(c => codes.includes(c)).slice(0, 2) }))
      .filter(a => a.codes.length);
  }
  const sc = curScope();
  const seeded = sc.length ? [{ codes: sc.slice(0, 2) }] : [];
  if (sc.length >= 3) seeded.push({ codes: [sc[1], sc[2]] });
  return seeded;
}
function setScopeAn(list) {
  const s = getSetup();
  s.scope_analyses = list.map(a => ({ codes: a.codes.filter(Boolean).slice(0, 2) })).filter(a => a.codes.length);
  s.scope_codes = s.scope_analyses.length ? s.scope_analyses[0].codes.slice() : [];
  saveSetup();
}

// Current sequence analyses ([{codes:[a]|[a,b]}]) from the setup (seeded from auto-detect).
function curSeq() {
  const s = getSetup(), codes = chatCodes();
  const raw = Array.isArray(s.sequence_codes) ? s.sequence_codes : null;
  if (raw === null) {
    const auto = (_chatMeta.scope_codes_auto || []).filter(c => codes.includes(c));
    const seeded = [];
    if (auto[0]) seeded.push({ codes: [auto[0]] });
    if (auto.length >= 3) seeded.push({ codes: [auto[1], auto[2]] });
    s.sequence_codes = seeded.map(a => ({ codes: a.codes.slice() })); saveSetup();
    return seeded;
  }
  return raw.map(a => ({ codes: (Array.isArray(a.codes) ? a.codes : []).filter(c => codes.includes(c)).slice(0, 2) }))
            .filter(a => a.codes.length);
}
function setSeq(list) { const s = getSetup(); s.sequence_codes = list.map(a => ({ codes: a.codes.filter(Boolean).slice(0, 2) })); saveSetup(); }

// The interactive control for the current step (returned as an HTML string).
function chatControl(step) {
  const s = getSetup();
  const esc = _esc;
  if (step === 'location') return `<input class="bn-ci" data-k="location" placeholder="e.g. Ain Sokhna, Egypt" value="${esc(s.location)}">`;
  if (step === 'contract_type') {
    const chips = CONTRACT_TYPES.map(t => `<button type="button" class="bn-chip2${s.contract_type === t ? ' on' : ''}" data-ct="${esc(t)}">${esc(t)}</button>`).join('');
    const custom = CONTRACT_TYPES.includes(s.contract_type) ? '' : (s.contract_type || '');
    return chips + `<div style="margin-top:4px"><input class="bn-ci" data-k="contract_type" style="width:60%" placeholder="or type another contract type" value="${esc(custom)}"></div>`;
  }
  if (step === 'revision') return `<input class="bn-ci" data-k="revision" style="width:40%" placeholder="e.g. REV.03" value="${esc(s.revision)}">`;
  if (step === 'parties') {
    // Each party: its NAME (feeds the §3 Project Brief owner/consultant/contractor rows — the report
    // can't derive these) plus its logo (the Word page header).
    const row = (k, label) => `<div style="display:flex;gap:8px;align-items:center;margin-bottom:7px;max-width:480px">` +
      `<input class="bn-ci" data-k="${k}" style="flex:1;width:auto" placeholder="${label} name" value="${esc(s[k])}">` +
      `<label class="bn-tile${s[k + '_logo'] ? ' on' : ''}" style="width:116px;height:38px;margin:0;font-size:11px">${s[k + '_logo'] ? '✓ logo' : '+ logo'}<input type="file" accept="image/*" data-logo="${k}_logo"></label></div>`;
    return row('owner', 'Owner') + row('consultant', 'Consultant') + row('contractor', 'Contractor') +
      `<label class="bn-ck"><input type="checkbox" data-incl="1"${s.include_logos === false ? '' : ' checked'}> show the logos in the page header</label>`;
  }
  if (step === 'layout') {
    // Several layout drawings (comment 103-01): title = figure caption; order = report order.
    const lays = layoutsOf(s);
    const cards = lays.map((l, i) => `<div class="bn-lay"><img src="${l.image}" alt=""><input class="bn-ci" data-lay="${i}" value="${esc(l.caption || '')}" placeholder="Drawing title">` +
      `<div class="bn-layact"><i class="bn-ch" data-laymv="up" data-i="${i}"${i === 0 ? ' style="opacity:.3"' : ''}>◀</i><i class="bn-ch" data-laymv="down" data-i="${i}"${i === lays.length - 1 ? ' style="opacity:.3"' : ''}>▶</i>` +
      `<span style="flex:1"></span><i class="bn-x" data-layrm="${i}" title="remove">✕ remove</i></div></div>`).join('');
    return `<div class="bn-lays">${cards}<label class="bn-layadd">＋ Add layout drawings<span>one or several · PNG / JPG</span><input type="file" accept="image/*" multiple data-layadd="1"></label></div>`;
  }
  if (step === 'milestones' || step === 'key_dates') {
    const dates = _chatMeta.milestone_dates || {};
    const col = (title, items, key) => {
      const sel = Array.isArray(s[key]) ? new Set(s[key]) : null;
      const n = items.filter(l => !sel || sel.has(l)).length;
      const rows = items.map(l => `<label class="bn-msrow" data-q="${esc(String(l).toLowerCase())}"><input type="checkbox" data-sel="${key}" value="${esc(l)}"${(!sel || sel.has(l)) ? ' checked' : ''}>` +
        `<span class="nm">${esc(l)}</span><span class="dt">${esc(dates[l] || '')}</span></label>`).join('');
      return `<div class="bn-msbox"><div class="bn-mshead"><b>${title}</b><span class="bn-mscount" data-cnt="${key}">${n} of ${items.length} ticked</span>` +
        `<input class="bn-mssearch" placeholder="Search…" data-msq="${key}"><a data-all="${key}">All</a><a data-none="${key}">None</a></div>` +
        `<div class="bn-mslist">${rows || '<span class="bn-hint2">none in the file</span>'}</div></div>`;
    };
    return step === 'milestones'
      ? `<div class="bn-cklist">${col('Major milestones', _chatMeta.milestone_choices || [], 'milestone_keys')}</div>`
      : `<div class="bn-cklist">${col('Key dates', _chatMeta.key_date_choices || [], 'key_date_keys')}</div>`;
  }
  if (step === 'scope') {
    // Same input as the Sequence of Work (comment 103): one row per analysis - one activity code,
    // or two to combine them (e.g. Type of Work + Building) - reorder, swap, remove, add above/below.
    const list = curScopeAn(), codes = chatCodes();
    const opt = (sel, ph) => [`<option value="">${ph}</option>`].concat(codes.map(c => `<option value="${esc(c)}"${c === sel ? ' selected' : ''}>${esc(c)}</option>`)).join('');
    const rows = list.map((a, i) =>
      `<div class="bn-srow"><span class="bn-lvl2">${i + 1}</span>` +
      `<select class="bn-sq bn-sa" data-sai="${i}" data-saslot="0" title="1st activity code">${opt(a.codes[0] || '', '— pick a code —')}</select>` +
      `<i class="bn-ch bn-sw" data-saswap="${i}" title="swap: make the 2nd code 1st"${a.codes.length === 2 ? '' : ' style="opacity:.3"'}>⇄</i>` +
      `<select class="bn-sq bn-sa" data-sai="${i}" data-saslot="1" title="2nd activity code - combines with the 1st">${opt(a.codes[1] || '', '— none (single) —')}</select>` +
      `<i class="bn-ch" data-samv="up" data-i="${i}" title="move up"${i === 0 ? ' style="opacity:.3"' : ''}>▲</i>` +
      `<i class="bn-ch" data-samv="down" data-i="${i}" title="move down"${i === list.length - 1 ? ' style="opacity:.3"' : ''}>▼</i>` +
      `<i class="bn-x" data-sarm="${i}" title="remove">✕</i></div>`).join('');
    return `<div class="bn-pv" id="bn-pv"><div class="bn-hint2">Working out the examples from your file…</div></div>` +
      `<div class="bn-cktitle" style="margin-top:8px">Your scope analyses — each one code, or two to combine them</div>` +
      `<button type="button" class="bn-add2" data-saadd="above"><i class="ti ti-arrow-bar-to-up" aria-hidden="true"></i> add analysis above</button>` +
      `<div class="bn-cflow" style="gap:6px;width:100%">${rows || '<span class="bn-hint2">No analyses — section 7 auto-detects a sensible breakdown.</span>'}</div>` +
      `<button type="button" class="bn-add2" data-saadd="below"><i class="ti ti-arrow-bar-to-down" aria-hidden="true"></i> add analysis below</button>` +
      `<div class="bn-hint2">The 1st analysis also gives the scope overview chart (7.1); each further analysis gets its own sub-section (7.3, 7.4 …).</div>`;
  }
  if (step === 'sequence') {
    const list = curSeq(), codes = chatCodes();
    const opt = (sel, ph) => [`<option value="">${ph}</option>`].concat(codes.map(c => `<option value="${esc(c)}"${c === sel ? ' selected' : ''}>${esc(c)}</option>`)).join('');
    const rows = list.map((a, i) =>
      `<div class="bn-srow"><span class="bn-lvl2">${i + 1}</span>` +
      `<select class="bn-sq" data-si="${i}" data-slot="0" title="1st activity code">${opt(a.codes[0] || '', '— pick a code —')}</select>` +
      `<i class="bn-ch bn-sw" data-sqswap="${i}" title="swap: make the 2nd code 1st"${a.codes.length === 2 ? '' : ' style="opacity:.3"'}>⇄</i>` +
      `<select class="bn-sq" data-si="${i}" data-slot="1" title="2nd activity code">${opt(a.codes[1] || '', '— none (single) —')}</select>` +
      `<i class="bn-ch" data-sqmv="up" data-i="${i}" title="move up"${i === 0 ? ' style="opacity:.3"' : ''}>▲</i>` +
      `<i class="bn-ch" data-sqmv="down" data-i="${i}" title="move down"${i === list.length - 1 ? ' style="opacity:.3"' : ''}>▼</i>` +
      `<i class="bn-x" data-seqrm="${i}" title="remove">✕</i></div>`).join('');
    return `<div class="bn-pv" id="bn-pv"><div class="bn-hint2">Working out the examples from your file…</div></div>` +
      `<div class="bn-cktitle" style="margin-top:8px">Your analyses</div>` +
      `<button type="button" class="bn-add2" data-seqadd="above"><i class="ti ti-arrow-bar-to-up" aria-hidden="true"></i> add sequence above</button>` +
      `<div class="bn-cflow" style="gap:6px;width:100%">${rows || '<span class="bn-hint2">No analyses — section 11 auto-detects a sensible sequence.</span>'}</div>` +
      `<button type="button" class="bn-add2" data-seqadd="below"><i class="ti ti-arrow-bar-to-down" aria-hidden="true"></i> add sequence below</button>`;
  }
  if (step === 'generate') {
    const codes = chatCodes();
    const ms = Array.isArray(s.milestone_keys) ? s.milestone_keys.length : (_chatMeta.milestone_choices || []).length;
    const kd = Array.isArray(s.key_date_keys) ? s.key_date_keys.length : (_chatMeta.key_date_choices || []).length;
    const sc = curScope(), sq = curSeq();
    const logos = ['owner_logo', 'consultant_logo', 'contractor_logo'].filter(k => s[k]).length;
    const row = (k, v) => `<div class="k">${k}</div><div>${esc(v)}</div>`;
    return `<div class="bn-sum">` +
      row('Location', s.location || '—') +
      row('Contract type', s.contract_type || '—') +
      row('Revision', s.revision || '—') +
      row('Parties', ['owner', 'consultant', 'contractor'].filter(k => s[k]).length + ' name(s) · ' + logos + ' logo(s)') +
      row('Layout drawings', layoutsOf(s).length ? layoutsOf(s).map(l => l.caption || 'drawing').join(' · ') : 'none') +
      row('Milestones · key dates', ms + ' · ' + kd) +
      row('Scope', curScopeAn().length ? curScopeAn().map(a => a.codes.join(' → ')).join(' · ') : 'auto-detected') +
      row('Sequence', (sq.length || 'auto') + (sq.length ? ' analysis(es)' : '')) +
      `</div><button type="button" class="bn-gen" id="bn-gen"><i class="ti ti-wand" style="vertical-align:-2px" aria-hidden="true"></i>&nbsp; Build the report</button>`;
  }
  return '';
}

// Short answer summary shown in the thread once a step is answered.
function chatSummary(step) {
  const s = getSetup();
  if (step === 'location') return s.location || 'Not specified';
  if (step === 'contract_type') return s.contract_type || 'Not specified';
  if (step === 'revision') return s.revision || 'Not specified';
  if (step === 'parties') {
    const nm = ['owner', 'consultant', 'contractor'].filter(k => s[k]).map(k => s[k]);
    const n = ['owner_logo', 'consultant_logo', 'contractor_logo'].filter(k => s[k]).length;
    return (nm.length ? nm.join(' · ') : 'No parties') + (n ? ' · ' + n + ' logo(s)' : '');
  }
  if (step === 'layout') { const l = layoutsOf(s); return l.length ? l.length + ' drawing(s): ' + l.map(x => x.caption || 'drawing').join(' · ') : 'No drawings'; }
  if (step === 'milestones') return (Array.isArray(s.milestone_keys) ? s.milestone_keys.length : (_chatMeta.milestone_choices || []).length) + ' milestones';
  if (step === 'key_dates') return (Array.isArray(s.key_date_keys) ? s.key_date_keys.length : (_chatMeta.key_date_choices || []).length) + ' key dates';
  if (step === 'scope') { const sa = curScopeAn(); return sa.length ? sa.map(a => a.codes.join(' → ')).join(' · ') : 'Auto-detected'; }
  if (step === 'sequence') { const sq = curSeq(); return sq.length ? sq.length + ' analysis(es)' : 'Auto-detected'; }
  return '';
}

function paintActive() {
  const box = document.getElementById('bn-active');
  if (!box) return;
  box.innerHTML = chatControl(CHAT_STEPS[_chatCur]);
  wireActive();
  const st = CHAT_STEPS[_chatCur];
  if (st === 'scope' || st === 'sequence') loadExamples(st);
}

// Like Claude: the new question sits at the TOP of the chat, with its answer box right under it,
// so the planner never scrolls to find the question or the items the tool found.
function scrollToQuestion(thread, smooth) {
  const tags = thread.querySelectorAll('.bn-chap');
  const tag = tags[tags.length - 1];
  const top = tag ? tag.getBoundingClientRect().top - thread.getBoundingClientRect().top + thread.scrollTop - 6 : thread.scrollHeight;
  thread.style.scrollBehavior = 'auto';
  thread.scrollTop = Math.max(0, top);
}

// Like AI Chat: the newest assistant message "thinks" for a moment, then appears word by word.
let _lastStreamed = '';
function streamLatest(thread) {
  const says = thread.querySelectorAll('.bn-ai .bn-say');
  const last = says[says.length - 1];
  if (!last) return;
  const key = _chatCur + '|' + last.textContent.length;
  if (key === _lastStreamed) return;                       // a re-paint of the same message: no replay
  _lastStreamed = key;
  const ctl = document.getElementById('bn-active');
  const words = [];
  (function wrap(node) {
    [...node.childNodes].forEach(ch => {
      if (ch.nodeType === 3) {
        const frag = document.createDocumentFragment();
        ch.textContent.split(/(\s+)/).forEach(w => {
          if (!w) return;
          if (/^\s+$/.test(w)) { frag.appendChild(document.createTextNode(w)); return; }
          const sp = document.createElement('span'); sp.className = 'bn-w'; sp.textContent = w; frag.appendChild(sp); words.push(sp);
        });
        node.replaceChild(frag, ch);
      } else if (ch.nodeType === 1) wrap(ch);
    });
  })(last);
  const think = document.createElement('div'); think.className = 'bn-think'; think.innerHTML = '<span></span><span></span><span></span> thinking…';
  last.parentNode.insertBefore(think, last);
  last.style.display = 'none'; if (ctl) ctl.style.opacity = '0';
  setTimeout(() => {
    think.remove(); last.style.display = '';
    const step = Math.max(8, Math.min(28, 1800 / Math.max(words.length, 1)));
    words.forEach((w, i) => setTimeout(() => w.classList.add('on'), i * step));
    setTimeout(() => { if (ctl) { ctl.style.transition = 'opacity .25s'; ctl.style.opacity = '1'; } if (_shownUpTo > 0) scrollToQuestion(thread, true); }, words.length * step + 60);
  }, 450);
}

// ── live "if you pick … this is the result" examples (from the planner's own file) ──
let _pvSeq = 0;
async function loadExamples(kind) {
  const box = document.getElementById('bn-pv');
  if (!box) return;
  const my = ++_pvSeq;
  const codes = chatCodes();
  const auto = (_chatMeta.scope_codes_auto || []).filter(c => codes.includes(c));
  const picks = kind === 'scope' ? curScopeAn().map(a => a.codes) : curSeq().map(a => a.codes);
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/narrative/preview`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ xml_path: state.currentXmlPath || '', cached_path: state.currentCachedPath || '', kind, auto_codes: auto, picks }),
    });
    const data = await resp.json();
    if (my !== _pvSeq || !document.getElementById('bn-pv')) return;
    if (!data.ok || !(data.examples || []).length) { box.innerHTML = '<div class="bn-hint2">No example could be worked out from this file\'s activity codes.</div>'; return; }
    box.innerHTML = data.examples.map((ex, i) => (kind === 'scope' ? scopeExample(ex, i) : seqExample(ex, i))).join('');
  } catch { box.innerHTML = '<div class="bn-hint2">Could not reach the local server for the examples.</div>'; }
}
const _codesTxt = codes => codes.map(c => `“${_esc(c)}”`).join(' → ');
function scopeExample(ex, i) {
  const n = ex.codes.length;
  const head = `If you pick ${n === 1 ? 'the activity code' : 'these ' + n + ' codes'} ${_codesTxt(ex.codes)}, section 7 reads:`;
  const bars = (ex.top || []).map(t => `<div class="bn-hb"><span>${_esc(t.name)}</span><i style="width:${Math.max(2, Math.round((t.pct || 0) * 2.2))}px"></i><b>${_esc(t.value)} · ${t.pct}%</b></div>`).join('');
  let drill = '';
  if (ex.drill && ex.drill.rows && ex.drill.rows.length) {
    drill = `<div class="bn-rh2">7.2 ${_esc(ex.drill.parent)} by ${_esc(ex.codes[1])}${n >= 3 ? ' → ' + _esc(ex.codes[2]) : ''}</div><table class="bn-pt">`
      + ex.drill.rows.map(r => `<tr><td><b>${_esc(r.name)}</b>${r.count ? ` (${r.count})` : ''}</td><td>${_esc(r.value)} · ${r.pct}%</td>`
        + (r.parts ? `<td>${r.parts.map(p => `${_esc(p.name)} ${p.pct}%`).join(' · ')}</td>` : '') + '</tr>').join('') + '</table>';
  }
  // what each picked code consists of + how they combine - exactly as section 7 now opens
  const lists = (ex.lists || []).map(l => `<div class="bn-cons"><b>${_esc(l.code)}</b> consists of: ${l.values.map(_esc).join(' · ')}${l.more ? ` · +${l.more} more` : ''}</div>`).join('');
  const combo = (ex.combo || []).length ? `<div class="bn-rh2">7.2 ${_esc(ex.codes[0])} → ${_esc(ex.codes[1])} — each with what it consists of</div>`
    + ex.combo.map(c => `<div class="bn-combo"><b>➢ ${_esc(c.name)}</b> (${c.pct}%)<div>${c.parts.map(x => '• ' + _esc(x)).join('&nbsp;&nbsp; ')}${c.more ? `&nbsp;&nbsp; +${c.more} more` : ''}</div></div>`).join('') : '';
  const warn = ex.unclassified && ex.unclassified > 10 ? `<div class="bn-warn">${ex.unclassified}% of the cost carries no value of “${_esc(ex.codes[0])}” — it would show as Unclassified.</div>` : '';
  return `<div class="bn-ex"><div class="bn-exh">${i + 1}. ${head}</div><div class="bn-rep"><div class="bn-rh">7) Scope of Work</div>`
    + lists + `<div class="bn-rh2">7.1 Scope by ${_esc(ex.codes[0])} — share of the baseline cost (${_esc(ex.total)})</div>${bars}${combo || drill}</div>${warn}</div>`;
}
function seqExample(ex, i) {
  const chev = steps => `<div class="bn-chev">${steps.map(x => `<span>${_esc(x)}</span>`).join('')}</div>`;
  const head = ex.codes.length === 1
    ? `If you pick ONE code ${_codesTxt(ex.codes)}, section 11 shows the order of the whole project:`
    : `If you pick TWO codes ${_codesTxt(ex.codes)}, section 11 shows the order inside each ${_esc(ex.codes[0])}:`;
  let body = '';
  if (ex.kind === 'single') body = chev(ex.steps || []);
  else body = (ex.groups || []).map(g => `<div class="bn-grp">${_esc(g.label)}${g.count > 1 ? ` (${g.count}, same order)` : ''}</div>${chev(g.steps || [])}`).join('')
    + (ex.more_groups ? `<div class="bn-hint2">+ ${ex.more_groups} more in the report</div>` : '')
    + ((ex.no_code || []).length ? `<div class="bn-warn">${ex.no_code.map(_esc).join(', ')} carry no “${_esc(ex.codes[1])}” — they are listed as “no code”. Add another analysis to cover them.</div>` : '');
  return `<div class="bn-ex"><div class="bn-exh">${i + 1}. ${head}</div><div class="bn-rep"><div class="bn-rh">11) Sequence of Work</div><div class="bn-rh2">${_esc(ex.title || '')}</div>${body}</div></div>`;
}

// ── several project layout drawings (setup.layouts; the legacy single setup.layout still reads) ──
function layoutsOf(s) {
  if (Array.isArray(s.layouts)) return s.layouts.filter(l => l && l.image);
  return s.layout ? [{ image: s.layout, caption: 'Project general layout' }] : [];
}
function setLayouts(s, list) { s.layouts = list; delete s.layout; saveSetup(); }

// ── typed answers: the planner can answer in words, like AI Chat ──
let _chatNote = '';
function _findCodes(txt) {
  const codes = chatCodes(), low = txt.toLowerCase();
  return codes.map(c => ({ c, at: low.indexOf(c.toLowerCase()) })).filter(x => x.at >= 0).sort((a, b) => a.at - b.at).map(x => x.c);
}
function chatTyped(raw) {
  const txt = (raw || '').trim(), low = txt.toLowerCase(), s = getSetup();
  const step = CHAT_STEPS[_chatCur];
  if (!txt) {                                    // send with nothing typed = "my answer is what is set above"
    if (step === 'generate') { const g = document.getElementById('bn-gen'); if (g) g.click(); return; }
    _chatCur = Math.min(CHAT_STEPS.length - 1, _chatCur + 1); renderChat(); return;
  }
  _chatNote = '';
  const go = d => { _chatCur = Math.max(0, Math.min(CHAT_STEPS.length - 1, _chatCur + d)); renderChat(); };
  if (/^(go )?back$|^previous$/.test(low)) return go(-1);
  if (/^(skip|next|ok|okay|confirm(ed)?|yes|keep( it)?|continue)$/.test(low)) return go(1);
  const ch = /^change (the )?(.+)$/.exec(low);
  if (ch) {
    const k = Object.keys(CHAT_TITLE).find(k => CHAT_TITLE[k].toLowerCase().includes(ch[2].split(' ')[0]) || k.replace('_', ' ').includes(ch[2].split(' ')[0]));
    if (k) { _chatCur = CHAT_STEPS.indexOf(k); renderChat(); return; }
  }
  if (step === 'location') { s.location = txt; saveSetup(); return go(1); }
  if (step === 'contract_type') {
    const rv = /rev\.?\s*0*(\d+)/i.exec(txt);
    const ct = CONTRACT_TYPES.find(t => low.includes(t.toLowerCase().split(' ')[0])) || txt.replace(/,?\s*rev.*$/i, '').trim();
    s.contract_type = ct; if (rv) s.revision = 'REV.' + rv[1].padStart(2, '0'); saveSetup();
    if (rv) { _chatNote = `Noted both: <b>${_esc(ct)}</b> and <b>${_esc(s.revision)}</b> — I'll skip the revision question.`; _chatCur += 2; renderChat(); return; }
    return go(1);
  }
  if (step === 'revision') { const rv = /(\d+)/.exec(txt); s.revision = rv ? 'REV.' + rv[1].padStart(2, '0') : txt.toUpperCase(); saveSetup(); return go(1); }
  if (step === 'milestones' || step === 'key_dates') {
    const key = step === 'milestones' ? 'milestone_keys' : 'key_date_keys';
    if (/^all$/.test(low)) s[key] = (_chatMeta[step === 'milestones' ? 'milestone_choices' : 'key_date_choices'] || []).slice();
    if (/^none$/.test(low)) s[key] = [];
    saveSetup(); return go(1);
  }
  if (step === 'scope') {
    const parts = txt.split(/,|;|\band\b/i).map(p => _findCodes(p)).filter(p => p.length).map(p => ({ codes: p.slice(0, 2) }));
    if (parts.length) { setScopeAn(parts); _chatNote = `Section 7 will have <b>${parts.length}</b> scope analysis(es): ${parts.map(p => p.codes.map(_esc).join(' → ')).join(' · ')}.`; return go(1); }
  }
  if (step === 'sequence') {
    const parts = txt.split(/,|;|\band\b/i).map(p => _findCodes(p)).filter(p => p.length).map(p => ({ codes: p.slice(0, 2) }));
    if (parts.length) { setSeq(parts); _chatNote = `Section 11 will have <b>${parts.length}</b> analysis(es): ${parts.map(p => p.codes.map(_esc).join(' → ')).join(' · ')}.`; return go(1); }
  }
  if (step === 'generate' && /build|generate|yes/.test(low)) { const g = document.getElementById('bn-gen'); if (g) g.click(); return; }
  _chatNote = `I didn't catch that for this question. You can use the options below, type <i>skip</i> to move on, <i>go back</i>, or <i>change location / revision / scope …</i>`;
  renderChat();
}

// The thread GROWS like AI Chat: moving forward appends your answer and the next question below
// what is already there (no re-draw, no blank screen); only going back redraws it.
let _shownUpTo = -1;
const _bot = html => `<div class="bn-row bn-ai"><div class="bn-av">✦</div><div class="bn-bub"><div class="bn-who">AI Assistant</div><div class="bn-say">${html}</div></div></div>`;
const _tagOf = i => `<div class="bn-chap">Question ${i + 1} of ${CHAT_STEPS.length} — ${_esc(CHAT_TITLE[CHAT_STEPS[i]] || '')}</div>`;
const _ansOf = i => { const sum = chatSummary(CHAT_STEPS[i]); return sum ? `<div class="bn-row me"><div class="bn-ans">${_esc(sum)}</div></div>` : ''; };
function renderChat() {
  const thread = document.getElementById('bn-thread');
  if (!thread) return;
  const old = document.getElementById('bn-active');
  const grow = old && _shownUpTo >= 0 && _chatCur >= _shownUpTo;
  if (grow) {
    old.remove();
    let h = '';
    for (let i = _shownUpTo; i < _chatCur; i++) {
      if (i > _shownUpTo) h += _tagOf(i) + _bot(_esc(CHAT_Q[CHAT_STEPS[i]]));
      h += _ansOf(i);
    }
    if (_chatCur > _shownUpTo) h += _tagOf(_chatCur) + _bot(_esc(CHAT_Q[CHAT_STEPS[_chatCur]]));
    if (_chatNote) h += _bot(_chatNote);
    h += `<div class="bn-ctl" id="bn-active"></div>`;
    thread.insertAdjacentHTML('beforeend', h);
    paintActive();
    streamLatest(thread);
  } else {
    let h = _bot(chatIntro());
    for (let i = 0; i < _chatCur; i++) h += _tagOf(i) + _bot(_esc(CHAT_Q[CHAT_STEPS[i]])) + _ansOf(i);
    h += _tagOf(_chatCur) + _bot(_esc(CHAT_Q[CHAT_STEPS[_chatCur]]));
    if (_chatNote) h += _bot(_chatNote);
    h += `<div class="bn-ctl" id="bn-active"></div>`;
    thread.innerHTML = h;
    paintActive();
    if (_shownUpTo < 0) streamLatest(thread);              // first open: the greeting streams in
  }
  _shownUpTo = _chatCur;
  _chatNote = '';
  scrollToQuestion(thread, grow);
  const prog = document.getElementById('bn-prog');
  if (prog) prog.textContent = 'Question ' + (_chatCur + 1) + ' of ' + CHAT_STEPS.length;
  const back = document.getElementById('bn-back');
  if (back) back.style.visibility = _chatCur === 0 ? 'hidden' : 'visible';
}

// Wire the events for the ACTIVE step's control (targeted re-render keeps the thread stable).
function wireActive() {
  const box = document.getElementById('bn-active');
  if (!box) return;
  const s = getSetup();
  box.querySelectorAll('input[data-k]').forEach(inp => inp.addEventListener('input', () => { s[inp.dataset.k] = inp.value; saveSetup(); }));
  // Enter in an answer field = send the answer and move on (like the box below)
  box.querySelectorAll('input.bn-ci').forEach(inp => inp.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    if (inp.dataset.k) { s[inp.dataset.k] = inp.value; saveSetup(); }
    chatTyped('');
  }));
  box.querySelectorAll('[data-ct]').forEach(b => b.addEventListener('click', () => {
    s.contract_type = b.dataset.ct; saveSetup();
    box.querySelectorAll('[data-ct]').forEach(x => x.classList.toggle('on', x === b));
    const ci = box.querySelector('input[data-k="contract_type"]'); if (ci) ci.value = '';
  }));
  box.querySelectorAll('input[type=file][data-logo]').forEach(inp => inp.addEventListener('change', async () => {
    if (!inp.files || !inp.files[0]) return;
    s[inp.dataset.logo] = await fileToDataUrl(inp.files[0]); saveSetup(); paintActive();
  }));
  // milestone / key-date checklists
  const collect = key => Array.from(box.querySelectorAll(`input[data-sel="${key}"]`)).filter(c => c.checked).map(c => c.value);
  const recount = key => { const el = box.querySelector(`[data-cnt="${key}"]`); if (el) { const all = box.querySelectorAll(`input[data-sel="${key}"]`); el.textContent = collect(key).length + ' of ' + all.length + ' ticked'; } };
  box.querySelectorAll('input[data-msq]').forEach(q => q.addEventListener('input', () => {
    const v = q.value.toLowerCase();
    box.querySelectorAll('.bn-msrow').forEach(r => { r.style.display = !v || r.dataset.q.includes(v) ? '' : 'none'; });
  }));
  box.querySelectorAll('input[data-sel]').forEach(c => c.addEventListener('change', () => { s[c.dataset.sel] = collect(c.dataset.sel); saveSetup(); recount(c.dataset.sel); }));
  box.querySelectorAll('[data-all]').forEach(a => a.addEventListener('click', () => { box.querySelectorAll(`input[data-sel="${a.dataset.all}"]`).forEach(c => { c.checked = true; }); s[a.dataset.all] = collect(a.dataset.all); saveSetup(); recount(a.dataset.all); }));
  box.querySelectorAll('[data-none]').forEach(a => a.addEventListener('click', () => { box.querySelectorAll(`input[data-sel="${a.dataset.none}"]`).forEach(c => { c.checked = false; }); s[a.dataset.none] = []; saveSetup(); recount(a.dataset.none); }));
  // scope analyses — same handlers as the sequence analyses
  box.querySelectorAll('.bn-sa').forEach(sel => sel.addEventListener('change', () => {
    const list = curScopeAn(), i = +sel.dataset.sai, slot = +sel.dataset.saslot;
    if (!list[i]) return;
    const cc = list[i].codes.slice();
    if (slot === 0) {
      if (!sel.value) list.splice(i, 1);
      else list[i].codes = [sel.value].concat(cc[1] && cc[1] !== sel.value ? [cc[1]] : []);
    } else {
      const first = cc[0];
      list[i].codes = first ? (sel.value && sel.value !== first ? [first, sel.value] : [first]) : [];
    }
    setScopeAn(list.filter(a => a.codes.length)); paintActive();
  }));
  box.querySelectorAll('[data-sarm]').forEach(b => b.addEventListener('click', () => { const list = curScopeAn(); list.splice(+b.dataset.sarm, 1); setScopeAn(list); paintActive(); }));
  box.querySelectorAll('[data-saswap]').forEach(b => b.addEventListener('click', () => { setScopeAn(swapSeqCodes(curScopeAn(), +b.dataset.saswap)); paintActive(); }));
  box.querySelectorAll('[data-samv]').forEach(b => b.addEventListener('click', () => { setScopeAn(moveItem(curScopeAn(), +b.dataset.i, b.dataset.samv)); paintActive(); }));
  box.querySelectorAll('[data-saadd]').forEach(b => b.addEventListener('click', () => {
    const list = curScopeAn(), codes = chatCodes();
    const auto = (_chatMeta.scope_codes_auto || []).filter(c => codes.includes(c));
    const used = new Set(list.map(a => a.codes.join('|')));
    const cand = [[auto[0], auto[1]], [auto[1], auto[2]], [auto[0]], [auto[1]], [codes[0]]].map(x => x.filter(Boolean)).find(x => x.length && !used.has(x.join('|'))) || [codes[0]];
    const na = { codes: cand };
    if (b.dataset.saadd === 'above') list.unshift(na); else list.push(na);
    setScopeAn(list); paintActive();
  }));
  // sequence — per-analysis code selects, remove, add above|below
  box.querySelectorAll('.bn-sq').forEach(sel => sel.addEventListener('change', () => {
    const list = curSeq(), i = +sel.dataset.si, slot = +sel.dataset.slot;
    if (!list[i]) return;
    const cc = list[i].codes.slice();
    if (slot === 0) {
      if (!sel.value) { list.splice(i, 1); }
      else list[i].codes = [sel.value].concat(cc[1] && cc[1] !== sel.value ? [cc[1]] : []);
    } else {
      const first = cc[0];
      list[i].codes = first ? (sel.value && sel.value !== first ? [first, sel.value] : [first]) : [];
    }
    setSeq(list.filter(a => a.codes.length)); paintActive();
  }));
  box.querySelectorAll('[data-seqrm]').forEach(b => b.addEventListener('click', () => { const list = curSeq(); list.splice(+b.dataset.seqrm, 1); setSeq(list); paintActive(); }));
  box.querySelectorAll('[data-sqswap]').forEach(b => b.addEventListener('click', () => { setSeq(swapSeqCodes(curSeq(), +b.dataset.sqswap)); paintActive(); }));
  box.querySelectorAll('[data-sqmv]').forEach(b => b.addEventListener('click', () => { setSeq(moveItem(curSeq(), +b.dataset.i, b.dataset.sqmv)); paintActive(); }));
  box.querySelectorAll('[data-seqadd]').forEach(b => b.addEventListener('click', () => {
    const list = curSeq(), codes = chatCodes();
    const auto = (_chatMeta.scope_codes_auto || []).filter(c => codes.includes(c));
    const na = { codes: [auto[0] || codes[0]] };
    if (b.dataset.seqadd === 'above') list.unshift(na); else list.push(na);
    setSeq(list); paintActive();
  }));
  box.querySelectorAll('input[data-incl]').forEach(c => c.addEventListener('change', () => { s.include_logos = c.checked; saveSetup(); }));
  box.querySelectorAll('input[data-layadd]').forEach(inp => inp.addEventListener('change', async () => {
    const list = layoutsOf(s).slice();
    for (const f of Array.from(inp.files || [])) list.push({ image: await fileToDataUrl(f), caption: f.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ') });
    setLayouts(s, list); paintActive();
  }));
  box.querySelectorAll('input[data-lay]').forEach(inp => inp.addEventListener('input', () => { const list = layoutsOf(s).slice(); if (list[+inp.dataset.lay]) { list[+inp.dataset.lay].caption = inp.value; setLayouts(s, list); } }));
  box.querySelectorAll('[data-layrm]').forEach(b => b.addEventListener('click', () => { const list = layoutsOf(s).slice(); list.splice(+b.dataset.layrm, 1); setLayouts(s, list); paintActive(); }));
  box.querySelectorAll('[data-laymv]').forEach(b => b.addEventListener('click', () => { setLayouts(s, moveItem(layoutsOf(s).slice(), +b.dataset.i, b.dataset.laymv)); paintActive(); }));
  const gen = document.getElementById('bn-gen');
  if (gen) gen.addEventListener('click', () => finishSetup(gen));
}

// The planner is done — hide the chat, show the report shell, generate.
function finishSetup(gen) {
  if (gen) { gen.disabled = true; gen.innerHTML = 'Building your report…'; }
  saveSetup();
  const chat = document.getElementById('bn-chat-wrap');
  const rep = document.getElementById('bn-report-wrap');
  if (chat) chat.style.display = 'none';
  if (rep) rep.style.display = '';
  exportBar(true);                                 // the report is now being mounted — exports apply
  // Shared Run presentation: the report builds + mounts UNDER the bar, which reaches 100%
  // only once it is on screen (owner comment 36 — no wait after 100%, no visible jump).
  return revealAndRun(document.getElementById('narrative-body'), 'Baseline Narrative', () => {
    revealStage('Writing the baseline narrative');
    return fetchAndRender();
  });
}

// Open (or re-open) the guided interview. "Edit setup" passes { reuse: true }: the choices
// already read from THIS file are shown at once (they are properties of the file — no second
// whole-file read behind a bare "Reading your schedule…" wait); a new Run always reads afresh.
async function startSetupChat(opts) {
  const reuse = !!(opts && opts.reuse) && _chatMetaFor === chatFileKey() && _chatMeta.project_name != null;
  const chat = document.getElementById('bn-chat-wrap');
  const rep = document.getElementById('bn-report-wrap');
  if (rep) rep.style.display = 'none';
  exportBar(false);                                // interview is showing — no exports until generate
  if (!chat) return;
  chat.style.display = '';
  chat.innerHTML = chatCss() +
    `<div class="bn-chat">
       <div class="bn-chat-head"><div class="bn-chat-av"><i class="ti ti-sparkles" aria-hidden="true"></i></div>
         <div><div class="bn-chat-title">AI Assistant</div><div class="bn-chat-sub" id="bn-readnote">I am your AI Planning Engineer · reading your schedule…</div></div></div>
       <div class="bn-thread" id="bn-thread"><div class="cmp-loading" style="padding:18px">Reading your schedule…</div></div>
       <div class="bn-type"><input id="bn-typed" placeholder="Type your answer, or just send to keep what is set above — “go back” / “change …” work too" autocomplete="off"><button id="bn-send" title="Send">➤</button></div>
       <div class="bn-chat-foot"><button class="bn-back" id="bn-back">← Back</button><span class="bn-chat-sub" id="bn-prog"></span><span></span></div>
     </div>`;
  document.getElementById('bn-back').addEventListener('click', () => { _chatNote = ''; if (_chatCur > 0) { _chatCur--; renderChat(); } });
  const typed = document.getElementById('bn-typed');
  const send = () => { const v = typed.value; typed.value = ''; chatTyped(v); typed.focus(); };
  document.getElementById('bn-send').addEventListener('click', send);
  typed.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); send(); } });
  // A fresh read is a whole-file read: the open Run bar names that step (RUNUX-R2).
  if (!reuse) revealStage('Reading your schedule');
  const meta = reuse ? _chatMeta : await fetchDetected();
  const note = document.getElementById('bn-readnote');
  if (!meta) { document.getElementById('bn-thread').innerHTML = '<p class="ai-empty" style="padding:16px">Open a baseline schedule first — the setup then reads it.</p>'; if (note) note.textContent = ''; return; }
  const proj = meta.project_name || 'your project';
  const acts = meta.activity_count ? (' · ' + meta.activity_count + ' activities') : '';
  if (note) note.textContent = 'I am your AI Planning Engineer · read ' + proj + acts;
  _chatCur = 0; _chatNote = ''; _shownUpTo = -1; _lastStreamed = '';
  renderChat();
}

// ── entry point (called by app.js on card/tab open) ────────────────────────────
let _wired = false;
export function renderNarrativePanel() {
  if (!_wired) {
    const w = document.getElementById('narrative-word-btn');
    const p = document.getElementById('narrative-pdf-btn');
    if (w) w.addEventListener('click', () => exportNarrative('docx'));
    if (p) p.addEventListener('click', () => exportNarrative('pdf'));
    // Export HTML — the same self-contained HTML the PDF export builds, without
    // the Chrome print step. Injected beside the Word/PDF buttons.
    let h = document.getElementById('narrative-html-btn');
    if (!h && p && p.parentNode) {
      h = document.createElement('button');
      h.className = 'btn-secondary';
      h.id = 'narrative-html-btn';
      h.textContent = 'Export HTML';
      p.parentNode.insertBefore(h, p.nextSibling);
    }
    if (h) h.addEventListener('click', () => exportNarrative('html'));
    // Export Excel — the same report as a workbook: one sheet per section, every table with all
    // its rows, every chart as its numbers (owner comment 29). It follows the Report-Contents
    // selection like the other three.
    let x = document.getElementById('narr-excel-btn');
    if (!x && p && p.parentNode) {
      x = document.createElement('button');
      x.className = 'btn-secondary';
      x.id = 'narr-excel-btn';
      x.textContent = 'Export Excel';
      (h || p).parentNode.insertBefore(x, (h || p).nextSibling);
    }
    if (x) x.addEventListener('click', () => exportNarrative('xlsx'));
    _wired = true;
  }
  flushSetupSave();                                // the previous schedule's last edit is sent
  state.narrativeSetup = null;
  state.narrativeDoc = null; registry = null;      // drop any prior project's report + selection
  _chatMeta = {}; _chatMetaFor = null; _chatCur = 0;
  exportBar(false);                                // exports appear only once a report is mounted
  const panel = document.getElementById('narrative-body');
  if (panel) {
    panel.innerHTML =
      '<div id="bn-chat-wrap"></div>' +
      '<div id="bn-report-wrap" style="display:none">' +
        '<div class="bn-report-bar"><button type="button" id="bn-edit-setup" class="bn-edit-setup">⚙ Edit setup</button></div>' +
        '<div class="bn-layout"><div id="narrative-contents" class="bn-contents"></div>' +
        '<div id="narrative-doc" style="flex:1;min-width:0"></div></div>' +
      '</div>';
    const edit = document.getElementById('bn-edit-setup');
    if (edit) edit.addEventListener('click', () => startSetupChat({ reuse: true }));
    // the saved setup (database) first, so a restarted app pre-fills parties/logos/layout;
    // loadSavedSetup never rejects (it falls back to this session's copy).
    const sid = state.currentSnapshotId;
    return loadSavedSetup().then(() => {
      if (sid !== state.currentSnapshotId || !document.getElementById('bn-chat-wrap')) return null;
      return startSetupChat();          // the Run presentation waits for the first question
    });
  }
}

// Aurora+ shell entry points — the shell opens the narrative view via renderNarrative()
// and drives File ▸ Print via narrativePrint(); our report has its own Word/PDF/HTML
// toolbar buttons, so narrativePrint returns null (nothing for the shell's PDF flow).
export function renderNarrative() { return renderNarrativePanel(); }
export function narrativePrint() { return null; }
