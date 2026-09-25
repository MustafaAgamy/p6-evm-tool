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
    renderSelection();               // populate the milestone / key-date checklists (comments 4 & 5)
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

const NARRATIVE_BTN_IDS = { docx: 'narrative-word-btn', pdf: 'narrative-pdf-btn', html: 'narrative-html-btn' };
const NARRATIVE_OK_LABELS = { docx: '✓ Word saved', pdf: '✓ PDF saved', html: '✓ HTML saved' };

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
    const resp = await fetch(`http://localhost:${PORT()}/api/narrative/${kind}`, {
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
      `<select class="bn-seqsel" data-i="${i}" data-slot="0" title="Primary activity code (required)">${opt(a.codes[0] || '', '— pick a code —')}</select>` +
      `<span class="bn-seqarrow">&rarr;</span>` +
      `<select class="bn-seqsel" data-i="${i}" data-slot="1" title="Group-by second code (optional)">${opt(a.codes[1] || '', '— none (single) —')}</select>` +
      `<button type="button" class="bn-seqmv" data-seqrm="${i}" title="Remove">&#10005;</button>` +
      '</div>').join('');
    seqHtml =
      '<h4 style="margin:16px 0 3px">Sequence of Work — activity codes</h4>' +
      '<div class="hint">Add one or more <b>sequence analyses</b> for §11. Pick <b>one</b> code for a ' +
      'general execution sequence, or add a <b>second</b> code to sequence each building/group by ' +
      'that code (identical buildings are grouped, e.g. “Silos 1–10”). The order of work is read ' +
      'from the schedule’s dependency logic. Leave empty to auto-detect.</div>' +
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
const CHAT_STEPS = ['location', 'contract_type', 'revision', 'branding', 'milestones', 'scope', 'sequence', 'generate'];
const CHAT_Q = {
  location:      "I've read your schedule. Let's set up your Baseline Narrative Report together. First — where is the project?",
  contract_type: 'What type of contract is it?',
  revision:      "And which revision is this? (The contract value I'll take automatically from your cost loading — nothing to enter.)",
  branding:      'Add the party logos for the page header and your project layout drawing. These are optional — skip any you don’t have.',
  milestones:    'I found your milestones and key dates and ticked the main ones. Confirm what appears in sections 4 and 5.',
  scope:         'How should I describe the scope of work (section 7)? I detected this order — reorder it, or add an activity code above or below.',
  sequence:      'And the sequence of work (section 11)? Same idea — add or remove sequence analyses; each is one code, or two to sequence by building.',
  generate:      "That's everything I need. I'll build the full report — all sections plus the Critical Path and Mapping Sheet appendix — matched across Word, PDF and on screen.",
};
let _chatMeta = {};
let _chatCur = 0;

function chatCss() {
  return `<style>
    .bn-chat{max-width:760px;margin:0 auto;border:1px solid var(--border,#dadee4);border-radius:14px;background:var(--surface-2,#fff);overflow:hidden}
    .bn-chat-head{display:flex;align-items:center;gap:10px;padding:13px 18px;border-bottom:1px solid var(--border,#e4e8ee)}
    .bn-chat-av{width:30px;height:30px;border-radius:50%;background:#e8f1fb;color:#1F4E79;display:flex;align-items:center;justify-content:center;font-size:16px;flex:0 0 auto}
    .bn-chat-title{font-size:14px;font-weight:700;color:#1a1d21;line-height:1.15}
    .bn-chat-sub{font-size:11.5px;color:var(--text-secondary,#5a626b)}
    .bn-thread{padding:16px 18px 4px;max-height:none}
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
    .bn-srow{display:flex;align-items:center;gap:7px;border:1px solid var(--border,#dadee4);border-radius:8px;padding:6px 9px;background:var(--surface-2,#fff);max-width:520px}
    .bn-sq{flex:1;min-width:0;padding:5px 8px;border:1px solid #c7cdd4;border-radius:6px;font:inherit;font-size:12px;background:var(--surface-2,#fff);color:var(--text-primary,#1a1d21)}
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
  </style>`;
}

// One /api/narrative call that BUILDS the report server-side and returns meta (the detected
// choices) — used to seed the chat before showing any question. Does not mount the report.
async function fetchDetected() {
  if (!state.currentXmlPath && !state.currentCachedPath) return null;
  try {
    const resp = await fetch(`http://localhost:${PORT()}/api/narrative`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        xml_path: state.currentXmlPath, cached_path: state.currentCachedPath,
        snapshot_id: state.currentSnapshotId || null, setup: setupForSend(),
      }),
    });
    const data = await resp.json();
    if (!data.ok) return null;
    state.narrativeDoc = data.doc;                 // lets scopeDisciplines() + meta resolve
    _chatMeta = (data.doc && data.doc.meta) || {};
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
  if (step === 'branding') {
    const tile = (k, label) => `<label class="bn-tile${s[k] ? ' on' : ''}">${s[k] ? '✓ ' + label : label}<input type="file" accept="image/*" data-logo="${k}"></label>`;
    return `<div class="bn-tiles">${tile('owner_logo', 'Owner logo')}${tile('consultant_logo', 'Consultant logo')}${tile('contractor_logo', 'Contractor logo')}</div>` +
      `<label class="bn-tile${s.layout ? ' on' : ''}" style="max-width:460px;height:52px">${s.layout ? '✓ Layout drawing' : 'Project layout drawing — section 2'}<input type="file" accept="image/*" data-logo="layout"></label>`;
  }
  if (step === 'milestones') {
    const col = (title, items, key) => {
      const sel = Array.isArray(s[key]) ? new Set(s[key]) : null;
      const rows = items.map(l => `<label class="bn-ck"><input type="checkbox" data-sel="${key}" value="${esc(l)}"${(!sel || sel.has(l)) ? ' checked' : ''}> ${esc(l)}</label>`).join('');
      return `<div><div class="bn-cktitle">${title} — <a data-all="${key}">all</a> · <a data-none="${key}">none</a></div>${rows || '<span class="bn-hint2">none in the file</span>'}</div>`;
    };
    return `<div class="bn-cklist">${col('Major milestones', _chatMeta.milestone_choices || [], 'milestone_keys')}${col('Key dates', _chatMeta.key_date_choices || [], 'key_date_keys')}</div>`;
  }
  if (step === 'scope') {
    const sc = curScope(), codes = chatCodes();
    const remaining = codes.filter(c => !sc.includes(c));
    const chip = (c, i) => `<span class="bn-cchip"><b>${i + 1}</b> ${esc(c)}` +
      `<i class="bn-ch" data-smv="up" data-i="${i}" title="up"${i === 0 ? ' style="opacity:.3"' : ''}>▲</i>` +
      `<i class="bn-ch" data-smv="down" data-i="${i}" title="down"${i === sc.length - 1 ? ' style="opacity:.3"' : ''}>▼</i>` +
      `<i class="bn-ch" data-smv="rm" data-i="${i}" title="remove">✕</i></span>`;
    const chain = sc.map((c, i) => chip(c, i)).join('<span class="bn-carrow">›</span>') ||
      '<span class="bn-hint2">No codes — the report auto-detects a sensible breakdown.</span>';
    const addSel = pos => remaining.length
      ? `<select class="bn-addsel" data-addscope="${pos}"><option value="">+ add code ${pos === 'above' ? 'above' : 'below'}…</option>${remaining.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select>` : '';
    return `<div class="bn-cflow">${addSel('above')}<div class="bn-cchain">${chain}</div>${addSel('below')}</div>` +
      (sc.length ? `<div class="bn-hint2">The 1st code splits the contract value (section 6); each below drills one level deeper.</div>` : '');
  }
  if (step === 'sequence') {
    const list = curSeq(), codes = chatCodes();
    const opt = (sel, ph) => [`<option value="">${ph}</option>`].concat(codes.map(c => `<option value="${esc(c)}"${c === sel ? ' selected' : ''}>${esc(c)}</option>`)).join('');
    const rows = list.map((a, i) =>
      `<div class="bn-srow"><span class="bn-lvl2">${i + 1}</span>` +
      `<select class="bn-sq" data-si="${i}" data-slot="0">${opt(a.codes[0] || '', '— pick a code —')}</select>` +
      `<span class="bn-carrow">→</span>` +
      `<select class="bn-sq" data-si="${i}" data-slot="1">${opt(a.codes[1] || '', '— none (single) —')}</select>` +
      `<i class="bn-x" data-seqrm="${i}" title="remove">✕</i></div>`).join('');
    return `<button type="button" class="bn-add2" data-seqadd="above"><i class="ti ti-arrow-bar-to-up" aria-hidden="true"></i> add sequence above</button>` +
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
      row('Header', logos + ' logo(s)' + (s.layout ? ' · layout added' : '')) +
      row('Milestones · key dates', ms + ' · ' + kd) +
      row('Scope', sc.length ? sc.join(' › ') : 'auto-detected') +
      row('Sequence', (sq.length || 'auto') + (sq.length ? ' analysis(es)' : '')) +
      `</div><button type="button" class="bn-gen" id="bn-gen"><i class="ti ti-wand" style="vertical-align:-2px" aria-hidden="true"></i>&nbsp; Generate report</button>`;
  }
  return '';
}

// Short answer summary shown in the thread once a step is answered.
function chatSummary(step) {
  const s = getSetup();
  if (step === 'location') return s.location || 'Not specified';
  if (step === 'contract_type') return s.contract_type || 'Not specified';
  if (step === 'revision') return s.revision || 'Not specified';
  if (step === 'branding') {
    const n = ['owner_logo', 'consultant_logo', 'contractor_logo'].filter(k => s[k]).length;
    return (n ? n + ' logo(s)' : 'No logos') + (s.layout ? ' · layout added' : '');
  }
  if (step === 'milestones') {
    const ms = Array.isArray(s.milestone_keys) ? s.milestone_keys.length : (_chatMeta.milestone_choices || []).length;
    const kd = Array.isArray(s.key_date_keys) ? s.key_date_keys.length : (_chatMeta.key_date_choices || []).length;
    return ms + ' milestones · ' + kd + ' key dates';
  }
  if (step === 'scope') { const sc = curScope(); return sc.length ? sc.join(' › ') : 'Auto-detected'; }
  if (step === 'sequence') { const sq = curSeq(); return sq.length ? sq.length + ' analysis(es)' : 'Auto-detected'; }
  return '';
}

function paintActive() {
  const box = document.getElementById('bn-active');
  if (!box) return;
  box.innerHTML = chatControl(CHAT_STEPS[_chatCur]);
  wireActive();
}

function renderChat() {
  const thread = document.getElementById('bn-thread');
  if (!thread) return;
  let h = '';
  for (let i = 0; i < _chatCur; i++) {
    h += `<div class="bn-row"><div class="bn-av"><i class="ti ti-sparkles" aria-hidden="true"></i></div><div class="bn-bub">${_esc(CHAT_Q[CHAT_STEPS[i]])}</div></div>`;
    const sum = chatSummary(CHAT_STEPS[i]);
    if (sum) h += `<div class="bn-row me"><div class="bn-ans">${_esc(sum)}</div></div>`;
  }
  h += `<div class="bn-row"><div class="bn-av"><i class="ti ti-sparkles" aria-hidden="true"></i></div><div class="bn-bub">${_esc(CHAT_Q[CHAT_STEPS[_chatCur]])}</div></div>`;
  h += `<div class="bn-ctl" id="bn-active"></div>`;
  thread.innerHTML = h;
  paintActive();
  const prog = document.getElementById('bn-prog');
  if (prog) prog.textContent = 'Question ' + (_chatCur + 1) + ' of ' + CHAT_STEPS.length;
  const back = document.getElementById('bn-back');
  if (back) back.style.visibility = _chatCur === 0 ? 'hidden' : 'visible';
  const cont = document.getElementById('bn-continue');
  if (cont) cont.style.display = CHAT_STEPS[_chatCur] === 'generate' ? 'none' : 'inline-block';
}

// Wire the events for the ACTIVE step's control (targeted re-render keeps the thread stable).
function wireActive() {
  const box = document.getElementById('bn-active');
  if (!box) return;
  const s = getSetup();
  box.querySelectorAll('input[data-k]').forEach(inp => inp.addEventListener('input', () => { s[inp.dataset.k] = inp.value; saveSetup(); }));
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
  box.querySelectorAll('input[data-sel]').forEach(c => c.addEventListener('change', () => { s[c.dataset.sel] = collect(c.dataset.sel); saveSetup(); }));
  box.querySelectorAll('[data-all]').forEach(a => a.addEventListener('click', () => { box.querySelectorAll(`input[data-sel="${a.dataset.all}"]`).forEach(c => { c.checked = true; }); s[a.dataset.all] = collect(a.dataset.all); saveSetup(); }));
  box.querySelectorAll('[data-none]').forEach(a => a.addEventListener('click', () => { box.querySelectorAll(`input[data-sel="${a.dataset.none}"]`).forEach(c => { c.checked = false; }); s[a.dataset.none] = []; saveSetup(); }));
  // scope — reorder / remove / add above|below
  box.querySelectorAll('[data-smv]').forEach(b => b.addEventListener('click', () => {
    const sc = curScope(), i = +b.dataset.i, mv = b.dataset.smv;
    if (mv === 'rm') sc.splice(i, 1);
    else if (mv === 'up' && i > 0) [sc[i - 1], sc[i]] = [sc[i], sc[i - 1]];
    else if (mv === 'down' && i < sc.length - 1) [sc[i + 1], sc[i]] = [sc[i], sc[i + 1]];
    setScope(sc); paintActive();
  }));
  box.querySelectorAll('[data-addscope]').forEach(sel => sel.addEventListener('change', () => {
    if (!sel.value) return;
    const sc = curScope();
    if (!sc.includes(sel.value)) { if (sel.dataset.addscope === 'above') sc.unshift(sel.value); else sc.push(sel.value); setScope(sc); }
    paintActive();
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
  box.querySelectorAll('[data-seqadd]').forEach(b => b.addEventListener('click', () => {
    const list = curSeq(), codes = chatCodes();
    const auto = (_chatMeta.scope_codes_auto || []).filter(c => codes.includes(c));
    const na = { codes: [auto[0] || codes[0]] };
    if (b.dataset.seqadd === 'above') list.unshift(na); else list.push(na);
    setSeq(list); paintActive();
  }));
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
  fetchAndRender();
}

// Open (or re-open) the guided interview.
async function startSetupChat() {
  const chat = document.getElementById('bn-chat-wrap');
  const rep = document.getElementById('bn-report-wrap');
  if (rep) rep.style.display = 'none';
  if (!chat) return;
  chat.style.display = '';
  chat.innerHTML = chatCss() +
    `<div class="bn-chat">
       <div class="bn-chat-head"><div class="bn-chat-av"><i class="ti ti-sparkles" aria-hidden="true"></i></div>
         <div><div class="bn-chat-title">Report setup</div><div class="bn-chat-sub" id="bn-readnote">reading your schedule…</div></div></div>
       <div class="bn-thread" id="bn-thread"><div class="cmp-loading" style="padding:18px">Reading your schedule…</div></div>
       <div class="bn-chat-foot"><button class="bn-back" id="bn-back">← Back</button><span class="bn-chat-sub" id="bn-prog"></span><button class="bn-continue" id="bn-continue">Continue →</button></div>
     </div>`;
  document.getElementById('bn-continue').addEventListener('click', () => { if (_chatCur < CHAT_STEPS.length - 1) { _chatCur++; renderChat(); } });
  document.getElementById('bn-back').addEventListener('click', () => { if (_chatCur > 0) { _chatCur--; renderChat(); } });
  const meta = await fetchDetected();
  const note = document.getElementById('bn-readnote');
  if (!meta) { document.getElementById('bn-thread').innerHTML = '<p class="ai-empty" style="padding:16px">Open a baseline schedule first — the setup then reads it.</p>'; if (note) note.textContent = ''; return; }
  const proj = meta.project_name || 'your project';
  const acts = meta.activity_count ? (' · ' + meta.activity_count + ' activities') : '';
  if (note) note.textContent = 'read ' + proj + acts;
  _chatCur = 0;
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
    _wired = true;
  }
  state.narrativeSetup = null;
  _chatMeta = {}; _chatCur = 0;
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
    if (edit) edit.addEventListener('click', () => startSetupChat());
    startSetupChat();
  }
}

// Aurora+ shell entry points — the shell opens the narrative view via renderNarrative()
// and drives File ▸ Print via narrativePrint(); our report has its own Word/PDF/HTML
// toolbar buttons, so narrativePrint returns null (nothing for the shell's PDF flow).
export function renderNarrative() { return renderNarrativePanel(); }
export function narrativePrint() { return null; }
