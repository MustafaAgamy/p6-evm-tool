// ─────────────────────────────────────────────────────────────────────────────
// Global "Report Contents" registry — the tool-wide Print-Preview framework.
//
// One reusable, dependency-free ES module every report screen wires into. A module
// declares its report as a flat list of selectable COMPONENTS (a section, a table,
// a chart, any single output). The registry then gives the user a "Report Contents"
// selector — a checkbox per component, Select All / Clear All, and drag-or-button
// reorder — and renders the live on-screen Preview from ONLY the selected components,
// in the chosen order, with automatic 1,2,3… section numbering.
//
// The exact HTML the Preview shows is what the caller hands to its existing PDF path,
// and what the built-in print() helper prints — so Preview == PDF == Print by design.
// The user's tick-boxes and order are remembered per report `key` in localStorage.
//
// No imports, no build step, no external libraries. All chrome is injected once from
// this file via a <style> element, themed off the app's CSS variables (--card-bg,
// --border, --text, --muted, --accent …) with print-safe fallbacks so exported HTML
// still looks right on white paper.
//
// ── How a module wires it in ────────────────────────────────────────────────
//
//   import { createReportRegistry } from './report_registry.js';
//
//   const registry = createReportRegistry({
//     key: 'narrative',                       // localStorage namespace for this report
//     components: [
//       { id: 'cover',   label: 'Cover & parties', group: 'Front matter',
//         render: () => buildCoverEl() },                       // -> HTMLElement
//       { id: 'wbs',     label: 'WBS tree',        group: 'Structure',
//         render: () => wbsHtmlString(),                        // -> html string
//         hasData: doc.hasWbs },                                // false => empty-state, off by default
//       { id: 'seq',     label: 'Sequence flow',   group: 'Structure',
//         render: () => seqChartEl(), defaultOn: false },       // present but off by default
//     ],
//     onChange: ({ selectedIds }) => enableExport(selectedIds.length > 0),
//   });
//
//   registry.renderControls(document.getElementById('report-contents'));
//   registry.renderPreview(document.getElementById('report-preview'));
//
//   // Hand the SAME html to the existing PDF / print paths:
//   await fetch('/api/narrative/pdf', { ... body: JSON.stringify({ html: registry.getSelectedHtml() }) });
//   printBtn.onclick = () => registry.print();
//
//   // When the report is regenerated with fresh data, swap the component list —
//   // the user's selection and order are preserved for components that persist:
//   registry.setComponents(newComponents);
//
// ── Component shape ─────────────────────────────────────────────────────────
//   {
//     id:        string,   // stable, unique within this report — the persistence key
//     label:     string,   // shown in the checkbox list and as the numbered heading
//     group?:    string,   // optional heading the checkbox is filed under
//     render:    () => HTMLElement | string,   // called fresh for every render
//     defaultOn?: boolean, // first-use tick state (default true; ignored if hasData===false)
//     hasData?:  boolean,  // false => renders a labelled empty-state, off by default
//   }
//
// ── API returned by createReportRegistry(...) ───────────────────────────────
//   renderControls(el?)  -> render the Report Contents panel (defaults to container)
//   renderPreview(el?)   -> render the live numbered preview   (defaults to container)
//   getSelectedHtml()    -> string: the exact inner HTML the Preview shows (for PDF)
//   getSelectedIds()     -> string[]: selected component ids, in report order
//   getOrder()           -> string[]: all component ids, in report order
//   print()              -> open the selected content in a print view (isolated iframe)
//   setComponents(list)  -> replace the component list, preserving selection/order
//   getComponents()      -> the current component list
//   refresh()            -> re-render whatever controls/preview elements are bound
//   destroy()            -> unbind listeners (injected stylesheet is left in place)
// ─────────────────────────────────────────────────────────────────────────────

const LS_PREFIX = 'p6_report_registry::';
const STYLE_ID  = 'rr-registry-styles';

/**
 * Create a Report Contents registry for one report.
 * @param {Object}   opts
 * @param {string}   opts.key         localStorage namespace (one per report screen).
 * @param {Array}    opts.components   component descriptors (see module header).
 * @param {Element} [opts.container]  optional root; if given, a controls + preview
 *                                    layout is built inside it and both are rendered.
 * @param {Function}[opts.onChange]   called with { selectedIds, order } after any change.
 * @returns {Object} the API described in the module header.
 */
export function createReportRegistry({ key, components, container, onChange } = {}) {
  if (!key) throw new Error('createReportRegistry: a unique `key` is required.');

  ensureStyles();

  const state = {
    key,
    components: normalizeComponents(components),
    onChange: typeof onChange === 'function' ? onChange : null,
    order: [],                 // flat list of component ids, in report order
    selected: {},              // { id: boolean }
    controlsEl: null,          // bound Report Contents panel element
    previewEl: null,           // bound live-preview element
    windowRefs: [],            // [ [target, type, handler] ] for destroy()
  };

  reconcileState(state, loadPersisted(key));

  // Optional convenience: build a default two-pane layout inside `container`.
  if (container instanceof Element) {
    container.classList.add('rr-layout');
    container.innerHTML =
      '<aside class="rr-layout-controls" data-rr-controls></aside>' +
      '<div class="rr-layout-preview" data-rr-preview></div>';
    renderControls(container.querySelector('[data-rr-controls]'));
    renderPreview(container.querySelector('[data-rr-preview]'));
  }

  // ── public API ─────────────────────────────────────────────────────────────

  function renderControls(el) {
    if (el instanceof Element) state.controlsEl = el;
    const host = state.controlsEl;
    if (!host) return api;
    host.classList.add('rr-panel');
    host.innerHTML = buildControlsHtml(state);
    wireControls(host, state, onAnyChange, rerenderControls, rerenderPreview);
    return api;
  }

  function renderPreview(el) {
    if (el instanceof Element) state.previewEl = el;
    const host = state.previewEl;
    if (!host) return api;
    host.classList.add('rr-report-host');
    host.innerHTML = '';
    host.appendChild(buildSelectedFragment(state, /* live */ true));
    return api;
  }

  function getSelectedHtml() {
    // Serialize a FRESH build so the returned markup exactly mirrors the preview,
    // and prepend the section chrome so the HTML is self-contained for PDF/print.
    const holder = document.createElement('div');
    holder.className = 'rr-report';
    holder.appendChild(buildSelectedFragment(state, /* live */ false));
    return sectionStyleTag() + holder.outerHTML;
  }

  function getSelectedIds() {
    return state.order.filter((id) => state.selected[id]);
  }

  function getOrder() {
    return state.order.slice();
  }

  function print() {
    const doc = fullPrintDoc(getSelectedHtml());
    const frame = document.createElement('iframe');
    frame.setAttribute('aria-hidden', 'true');
    frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden;';
    frame.onload = () => {
      try {
        frame.contentWindow.focus();
        frame.contentWindow.print();
      } catch (e) { /* print blocked — nothing to clean up beyond removal */ }
      setTimeout(() => { try { frame.remove(); } catch (e) { /* ignore */ } }, 1500);
    };
    document.body.appendChild(frame);
    frame.srcdoc = doc;
    return api;
  }

  function setComponents(list) {
    state.components = normalizeComponents(list);
    reconcileState(state, { order: state.order, selected: state.selected });
    persist(state);
    rerenderControls();
    rerenderPreview();
    return api;
  }

  function getComponents() {
    return state.components.slice();
  }

  function refresh() {
    rerenderControls();
    rerenderPreview();
    return api;
  }

  function destroy() {
    state.windowRefs.forEach(([t, type, h]) => t.removeEventListener(type, h));
    state.windowRefs = [];
    return api;
  }

  // ── internal glue ────────────────────────────────────────────────────────────

  function onAnyChange() {
    persist(state);
    if (state.onChange) {
      try { state.onChange({ selectedIds: getSelectedIds(), order: getOrder() }); }
      catch (e) { /* caller callback errors must not break the UI */ }
    }
  }
  function rerenderControls() { if (state.controlsEl) renderControls(state.controlsEl); }
  function rerenderPreview()  { if (state.previewEl)  renderPreview(state.previewEl); }

  const api = {
    renderControls, renderPreview, getSelectedHtml, getSelectedIds, getOrder,
    print, setComponents, getComponents, refresh, destroy,
  };
  return api;
}

// ─────────────────────────────────────────────────────────────────────────────
// State: normalize, reconcile, persist
// ─────────────────────────────────────────────────────────────────────────────

function normalizeComponents(list) {
  const out = [];
  const seen = new Set();
  (Array.isArray(list) ? list : []).forEach((c) => {
    if (!c || c.id == null) return;
    const id = String(c.id);
    if (seen.has(id)) return;                       // ids must be unique — first wins
    seen.add(id);
    out.push({
      id,
      label: c.label != null ? String(c.label) : id,
      group: c.group != null ? String(c.group) : '',
      render: typeof c.render === 'function' ? c.render : () => '',
      defaultOn: c.defaultOn !== false,             // default true unless explicitly false
      hasData: c.hasData !== false,                 // default true unless explicitly false
    });
  });
  return out;
}

function defaultSelected(comp) {
  if (comp.hasData === false) return false;         // no-data components start off
  return comp.defaultOn !== false;
}

// Merge current components with any persisted order/selection: keep the stored order
// for ids that still exist, append newly-declared ids in declaration order, and use
// the stored tick for known ids or the component default for first-seen ids.
function reconcileState(state, persisted) {
  const byId = new Map(state.components.map((c) => [c.id, c]));
  const prevOrder = (persisted && Array.isArray(persisted.order)) ? persisted.order : [];
  const prevSel   = (persisted && persisted.selected) ? persisted.selected : {};

  const order = [];
  prevOrder.forEach((id) => { if (byId.has(id) && !order.includes(id)) order.push(id); });
  state.components.forEach((c) => { if (!order.includes(c.id)) order.push(c.id); });

  const selected = {};
  order.forEach((id) => {
    const comp = byId.get(id);
    selected[id] = Object.prototype.hasOwnProperty.call(prevSel, id)
      ? !!prevSel[id]
      : defaultSelected(comp);
  });

  state.order = order;
  state.selected = selected;
}

function loadPersisted(key) {
  try { return JSON.parse(localStorage.getItem(LS_PREFIX + key) || 'null'); }
  catch (e) { return null; }
}

function persist(state) {
  try {
    localStorage.setItem(LS_PREFIX + state.key,
      JSON.stringify({ order: state.order, selected: state.selected }));
  } catch (e) { /* storage full / disabled — selection just won't persist */ }
}

// ─────────────────────────────────────────────────────────────────────────────
// Preview build (shared by on-screen preview, getSelectedHtml, and print)
// ─────────────────────────────────────────────────────────────────────────────

// Build a fragment of the selected components in report order, each wrapped in a
// numbered section. `live` true keeps real nodes (with their event handlers) for the
// on-screen preview; false is used for serialization but is otherwise identical.
function buildSelectedFragment(state, live) {
  const frag = document.createDocumentFragment();
  const byId = new Map(state.components.map((c) => [c.id, c]));
  let n = 0;

  state.order.forEach((id) => {
    if (!state.selected[id]) return;
    const comp = byId.get(id);
    if (!comp) return;
    n += 1;
    frag.appendChild(buildSection(comp, n, live));
  });

  if (n === 0) {
    const empty = document.createElement('div');
    empty.className = 'rr-report-empty';
    empty.textContent = 'Nothing selected. Tick components in Report Contents to build the report.';
    frag.appendChild(empty);
  }
  return frag;
}

function buildSection(comp, num, live) {
  const section = document.createElement('section');
  section.className = 'rr-section';
  section.setAttribute('data-rr-id', comp.id);
  section.setAttribute('data-rr-num', String(num));

  const head = document.createElement('h2');
  head.className = 'rr-sec-head';
  head.innerHTML =
    '<span class="rr-sec-num">' + num + '</span>' +
    '<span class="rr-sec-title">' + esc(comp.label) + '</span>';
  section.appendChild(head);

  const body = document.createElement('div');
  body.className = 'rr-sec-body';

  if (comp.hasData === false) {
    body.appendChild(emptyState(comp.label));
  } else {
    let out;
    try { out = comp.render(); }
    catch (e) { out = null; }
    body.appendChild(toNode(out, comp.label));
  }
  section.appendChild(body);
  return section;
}

function emptyState(label) {
  const el = document.createElement('div');
  el.className = 'rr-empty';
  el.innerHTML =
    '<span class="rr-empty-icon" aria-hidden="true">∅</span>' +
    '<span class="rr-empty-text">No data available for <b>' + esc(label) + '</b>' +
    ' in this schedule.</span>';
  return el;
}

// Accept an HTMLElement or an HTML string (or null) from a component's render().
function toNode(out, label) {
  if (out instanceof Node) return out;
  const wrap = document.createElement('div');
  wrap.className = 'rr-sec-html';
  if (out == null || out === '') {
    wrap.appendChild(emptyState(label));
  } else {
    wrap.innerHTML = String(out);
  }
  return wrap;
}

// ─────────────────────────────────────────────────────────────────────────────
// Controls (Report Contents panel): checkboxes grouped, Select/Clear All, reorder
// ─────────────────────────────────────────────────────────────────────────────

function buildControlsHtml(state) {
  const byId = new Map(state.components.map((c) => [c.id, c]));
  const total = state.order.length;
  const on = state.order.filter((id) => state.selected[id]).length;

  let rows = '';
  let lastGroup = null;
  state.order.forEach((id, idx) => {
    const comp = byId.get(id);
    if (!comp) return;
    const group = comp.group || '';
    if (group !== lastGroup) {
      if (group) rows += '<div class="rr-group">' + esc(group) + '</div>';
      lastGroup = group;
    }
    const checked = state.selected[id] ? 'checked' : '';
    const noData = comp.hasData === false;
    const first = idx === 0 ? 'disabled' : '';
    const last  = idx === state.order.length - 1 ? 'disabled' : '';
    rows +=
      '<div class="rr-item" draggable="true" data-rr-id="' + esc(id) + '">' +
        '<span class="rr-handle" title="Drag to reorder" aria-hidden="true">⋮⋮</span>' +
        '<label class="rr-check">' +
          '<input type="checkbox" data-rr-check="' + esc(id) + '" ' + checked + '>' +
          '<span class="rr-label">' + esc(comp.label) + '</span>' +
          (noData ? '<span class="rr-badge rr-badge-nodata">no data</span>' : '') +
        '</label>' +
        '<span class="rr-move">' +
          '<button type="button" class="rr-mv" data-rr-up="' + esc(id) + '" ' + first +
            ' title="Move up" aria-label="Move up">▲</button>' +
          '<button type="button" class="rr-mv" data-rr-down="' + esc(id) + '" ' + last +
            ' title="Move down" aria-label="Move down">▼</button>' +
        '</span>' +
      '</div>';
  });

  if (!total) rows = '<div class="rr-none">No components registered for this report.</div>';

  return '' +
    '<div class="rr-panel-head">' +
      '<div class="rr-panel-title">Report Contents</div>' +
      '<div class="rr-count">' + on + '/' + total + ' shown</div>' +
    '</div>' +
    '<div class="rr-panel-actions">' +
      '<button type="button" class="rr-act" data-rr-all>Select all</button>' +
      '<button type="button" class="rr-act" data-rr-none>Clear all</button>' +
    '</div>' +
    '<div class="rr-list">' + rows + '</div>' +
    '<div class="rr-hint">Drag rows or use ▲▼ to reorder. Sections are numbered automatically in the report.</div>';
}

function wireControls(host, state, onAnyChange, rerenderControls, rerenderPreview) {
  // checkbox toggles — update in place (no re-render, so focus is not lost)
  host.querySelectorAll('input[data-rr-check]').forEach((cb) => {
    cb.addEventListener('change', () => {
      const id = cb.getAttribute('data-rr-check');
      state.selected[id] = cb.checked;
      updateCount(host, state);
      onAnyChange();
      rerenderPreview();
    });
  });

  const selectAll = (val) => {
    state.order.forEach((id) => { state.selected[id] = val; });
    onAnyChange();
    rerenderControls();
    rerenderPreview();
  };
  const allBtn = host.querySelector('[data-rr-all]');
  const noneBtn = host.querySelector('[data-rr-none]');
  if (allBtn)  allBtn.addEventListener('click', () => selectAll(true));
  if (noneBtn) noneBtn.addEventListener('click', () => selectAll(false));

  // up / down buttons
  host.querySelectorAll('[data-rr-up]').forEach((b) =>
    b.addEventListener('click', () => { moveBy(state, b.getAttribute('data-rr-up'), -1); onAnyChange(); rerenderControls(); rerenderPreview(); }));
  host.querySelectorAll('[data-rr-down]').forEach((b) =>
    b.addEventListener('click', () => { moveBy(state, b.getAttribute('data-rr-down'), 1); onAnyChange(); rerenderControls(); rerenderPreview(); }));

  // drag-and-drop reorder
  let dragId = null;
  host.querySelectorAll('.rr-item').forEach((row) => {
    row.addEventListener('dragstart', (e) => {
      dragId = row.getAttribute('data-rr-id');
      row.classList.add('rr-dragging');
      if (e.dataTransfer) { e.dataTransfer.effectAllowed = 'move'; try { e.dataTransfer.setData('text/plain', dragId); } catch (x) {} }
    });
    row.addEventListener('dragend', () => {
      dragId = null;
      host.querySelectorAll('.rr-item').forEach((r) => r.classList.remove('rr-dragging', 'rr-drag-over'));
    });
    row.addEventListener('dragover', (e) => {
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
      if (row.getAttribute('data-rr-id') !== dragId) row.classList.add('rr-drag-over');
    });
    row.addEventListener('dragleave', () => row.classList.remove('rr-drag-over'));
    row.addEventListener('drop', (e) => {
      e.preventDefault();
      const targetId = row.getAttribute('data-rr-id');
      const from = dragId || (e.dataTransfer && e.dataTransfer.getData('text/plain'));
      row.classList.remove('rr-drag-over');
      if (from && targetId && from !== targetId) {
        moveBefore(state, from, targetId);
        onAnyChange();
        rerenderControls();
        rerenderPreview();
      }
    });
  });
}

function updateCount(host, state) {
  const el = host.querySelector('.rr-count');
  if (!el) return;
  const on = state.order.filter((id) => state.selected[id]).length;
  el.textContent = on + '/' + state.order.length + ' shown';
}

function moveBy(state, id, delta) {
  const i = state.order.indexOf(id);
  if (i < 0) return;
  const j = i + delta;
  if (j < 0 || j >= state.order.length) return;
  const [item] = state.order.splice(i, 1);
  state.order.splice(j, 0, item);
}

function moveBefore(state, fromId, targetId) {
  const from = state.order.indexOf(fromId);
  if (from < 0) return;
  state.order.splice(from, 1);
  const target = state.order.indexOf(targetId);
  const insertAt = target < 0 ? state.order.length : target;
  state.order.splice(insertAt, 0, fromId);
}

// ─────────────────────────────────────────────────────────────────────────────
// Print helper
// ─────────────────────────────────────────────────────────────────────────────

function fullPrintDoc(innerHtml) {
  // A self-contained white-paper document. innerHtml already carries the section
  // chrome <style> from getSelectedHtml(); we add page + base typography here.
  return '<!doctype html><html><head><meta charset="utf-8">' +
    '<title>Report</title>' +
    '<style>' +
      '@page{margin:16mm;}' +
      'html,body{background:#fff;color:#1e293b;}' +
      'body{font-family:system-ui,-apple-system,sans-serif;font-size:13px;margin:0;padding:0;}' +
    '</style>' +
    '</head><body>' + innerHtml + '</body></html>';
}

// ─────────────────────────────────────────────────────────────────────────────
// Injected chrome — themed off the app's CSS variables with print-safe fallbacks.
// Injected once per document; safe to call repeatedly.
// ─────────────────────────────────────────────────────────────────────────────

function ensureStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = PANEL_CSS + SECTION_CSS;
  document.head.appendChild(style);
}

// Only the section/report chrome — embedded in getSelectedHtml() so exported HTML
// and the print view are styled identically to the on-screen preview.
function sectionStyleTag() {
  return '<style>' + SECTION_CSS + '</style>';
}

const SECTION_CSS = `
.rr-report{max-width:860px;margin:0 auto;color:var(--text,#1e293b);}
.rr-report-host{overflow:auto;}
.rr-section{margin:0 0 26px;page-break-inside:avoid;break-inside:avoid;}
.rr-sec-head{display:flex;align-items:baseline;gap:10px;margin:0 0 10px;
  font-size:16px;font-weight:700;color:var(--text,#1e293b);
  border-bottom:1px solid var(--border,#e2e8f0);padding-bottom:6px;}
.rr-sec-num{display:inline-flex;align-items:center;justify-content:center;
  min-width:24px;height:24px;padding:0 6px;border-radius:6px;
  background:var(--accent,#1d4ed8);color:#fff;font-size:12px;font-weight:800;
  flex:0 0 auto;}
.rr-sec-title{flex:1 1 auto;}
.rr-sec-body{font-size:13px;line-height:1.5;color:var(--text,#1e293b);}
.rr-sec-html{}
.rr-empty{display:flex;align-items:center;gap:10px;padding:16px 18px;
  border:1px dashed var(--border,#e2e8f0);border-radius:9px;
  color:var(--muted,#94a3b8);font-size:12.5px;
  background:var(--row-hover,rgba(0,0,0,0.02));}
.rr-empty-icon{font-size:18px;opacity:.7;}
.rr-empty-text b{color:var(--text,#1e293b);font-weight:600;}
.rr-report-empty{padding:40px 18px;text-align:center;color:var(--muted,#94a3b8);
  font-size:13px;border:1px dashed var(--border,#e2e8f0);border-radius:10px;}
@media print{
  .rr-report{max-width:none;}
  .rr-sec-num{background:#1d4ed8 !important;-webkit-print-color-adjust:exact;print-color-adjust:exact;}
}
`;

const PANEL_CSS = `
.rr-layout{display:flex;gap:18px;align-items:flex-start;}
.rr-layout-controls{flex:0 0 280px;position:sticky;top:0;}
.rr-layout-preview{flex:1 1 auto;min-width:0;}
.rr-panel{background:var(--card-bg,#fff);border:1px solid var(--border,#e2e8f0);
  border-radius:12px;padding:14px 14px 12px;font-size:13px;color:var(--text,#1e293b);}
.rr-panel-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:10px;}
.rr-panel-title{font-size:11px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:var(--muted,#94a3b8);}
.rr-count{font-size:11px;color:var(--muted,#94a3b8);font-weight:600;}
.rr-panel-actions{display:flex;gap:8px;margin-bottom:10px;}
.rr-act{flex:1;background:transparent;border:1px solid var(--border,#e2e8f0);color:var(--text,#1e293b);
  border-radius:7px;padding:6px 8px;font:inherit;font-size:12px;cursor:pointer;transition:border-color .15s,background .15s;}
.rr-act:hover{border-color:var(--accent,#1d4ed8);color:var(--accent,#1d4ed8);}
.rr-list{display:flex;flex-direction:column;gap:4px;}
.rr-group{font-size:10px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;
  color:var(--muted,#94a3b8);margin:10px 2px 3px;}
.rr-group:first-child{margin-top:0;}
.rr-item{display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:8px;
  border:1px solid transparent;background:var(--row-hover,rgba(0,0,0,0.02));cursor:default;}
.rr-item:hover{border-color:var(--border,#e2e8f0);}
.rr-item.rr-dragging{opacity:.45;}
.rr-item.rr-drag-over{border-color:var(--accent,#1d4ed8);box-shadow:0 0 0 1px var(--accent,#1d4ed8) inset;}
.rr-handle{cursor:grab;color:var(--muted,#94a3b8);font-size:12px;line-height:1;letter-spacing:-2px;user-select:none;padding:0 2px;}
.rr-handle:active{cursor:grabbing;}
.rr-check{flex:1 1 auto;display:flex;align-items:center;gap:8px;min-width:0;cursor:pointer;margin:0;}
.rr-check input{flex:0 0 auto;width:15px;height:15px;accent-color:var(--accent,#1d4ed8);cursor:pointer;}
.rr-label{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12.5px;color:var(--text,#1e293b);}
.rr-badge{flex:0 0 auto;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;
  padding:2px 6px;border-radius:10px;}
.rr-badge-nodata{background:rgba(148,163,184,.18);color:var(--muted,#94a3b8);}
.rr-move{flex:0 0 auto;display:flex;flex-direction:column;gap:1px;}
.rr-mv{width:20px;height:14px;display:flex;align-items:center;justify-content:center;
  background:transparent;border:1px solid var(--border,#e2e8f0);color:var(--muted,#94a3b8);
  border-radius:4px;font-size:8px;line-height:1;cursor:pointer;padding:0;}
.rr-mv:hover:not(:disabled){border-color:var(--accent,#1d4ed8);color:var(--accent,#1d4ed8);}
.rr-mv:disabled{opacity:.3;cursor:not-allowed;}
.rr-hint{margin-top:10px;font-size:10.5px;line-height:1.4;color:var(--muted,#94a3b8);}
.rr-none{font-size:12px;color:var(--muted,#94a3b8);padding:8px 4px;}
@media (max-width:820px){
  .rr-layout{flex-direction:column;}
  .rr-layout-controls{flex-basis:auto;width:100%;position:static;}
}
`;

// ─────────────────────────────────────────────────────────────────────────────
// utils
// ─────────────────────────────────────────────────────────────────────────────

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
