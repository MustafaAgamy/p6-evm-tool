// Report preview overlay — the ONE Report Contents picker every feature's File ▸ Print /
// "Generate … PDF" opens. The page is scaled to fit the window width.
//
// TWO LEVELS: the caller's SECTIONS (tick a whole sub-feature) and the PARTS inside each one
// (tick just one table / chart / summary) — parts are discovered from the rendered HTML
// ([data-sec] › [data-part], see docs/report-picker-adoption.md). Select all / Clear all,
// drag a section to reorder, remembered per storageKey. Unticked parts are REMOVED from the
// report (not hidden); a ticked part with nothing to show says "No data available".
//
// ONE DOCUMENT: the preview frame holds the exact final report (feature render for the
// ticked sections + appearance mode, pruned + ordered by report_parts.js). Save as PDF ·
// Word · HTML · Excel and Print are ALL made from that one HTML string (POST
// /api/export/<kind>), so the outputs cannot diverge.
//
// Backward compatible: showReportPreview({ title, subtitle, html, onSave, sections, selected,
// onRerender, storageKey, onThemeChange, initialMode }) works as before. New optional opts:
//   feature   — the name used in the Word header / Excel title (default: title minus "preview")
//   exportName— base file name for the save dialogs (default: from the title)
//   meta      — { project, data_date } for the Word header / Excel header block (else read
//               from the report's own "Project: / Data Date:" line)
//   legacyPdf — true = "PDF" calls the caller's onSave (its own server route) instead of the
//               generic one-document PDF. Default false: the generic PDF honours part ticks.
//   exports   — which Save buttons to offer. OPT-IN: default ['pdf'] (the legacy bar). Only an
//               ADOPTED feature (report annotated with data-sec / data-part, charts marked —
//               docs/report-picker-adoption.md) passes ['pdf','docx','html','xlsx']; an
//               unannotated report's CSS charts would reach Word / Excel as bare text.
//   serverOrder — true when onRerender honours the ORDER of the keys it is given. Without it
//               (and without [data-sec] wrappers the picker can reorder itself) drag-to-reorder
//               is not offered, because the new order could not reach the outputs.
import { escapeHtml } from './format.js';
import { buildAppearancePicker, getSavedMode, backdropColor } from './appearance.js';
import { state as appState } from './state.js';
import {
  scanReport, buildTree, restoreState, sectionCheck, partChecked, toggleSection, togglePart,
  selectAll, clearAll, moveSection, serverKeys, countTicked, pruneHtml, exportKinds,
  needsRerender, canReorder,
} from './report_parts.js';
import { takeDocExport, pendingExportPlan } from './export_intent.js';

const PAGE_W = 820;   // approximate print page content width (px); the page is scaled to fit

const EXPORTS = [
  { kind: 'pdf',  label: 'PDF',   ext: 'pdf'  },
  { kind: 'docx', label: 'Word',  ext: 'docx' },
  { kind: 'html', label: 'HTML',  ext: 'html' },
  { kind: 'xlsx', label: 'Excel', ext: 'xlsx' },
];

function _port() {
  return appState.serverPort || (typeof window !== 'undefined' && window.__SERVER_PORT__) || '';
}

function _slug(s) {
  return String(s || 'report').replace(/\s+preview$/i, '').replace(/[^\w\-]+/g, '_').replace(/^_+|_+$/g, '') || 'report';
}

export function showReportPreview({ title, subtitle, html, onSave, sections, selected, onRerender, storageKey,
  onThemeChange, initialMode, feature, exportName, meta, legacyPdf, exports, serverOrder }) {
  let mode = initialMode || getSavedMode();
  const offered = EXPORTS.filter(e => exportKinds(exports).includes(e.kind));
  const featureName = feature || String(title || 'Report').replace(/\s+(report\s+)?preview$/i, '').replace(/^Report\s+—\s+/i, '');
  const baseName = exportName || _slug(featureName);

  // ── picker model ──
  let serverHtml = html || '';
  let lastKeys = Array.isArray(selected) && selected.length ? selected.slice()
    : (sections || []).filter(s => !s.empty).map(s => s.key);
  let scan = scanReport(serverHtml);
  let wraps = scan.sections.length > 0;                  // the renderer wraps sections in [data-sec]
  let tree = buildTree(sections || [], scan);
  const hasSel = tree.length > 0;
  let saved = null;
  if (storageKey) { try { saved = JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch { saved = null; } }
  let st = restoreState(saved, tree, selected);
  const expanded = new Set();
  const finalHtml = () => (hasSel ? pruneHtml(serverHtml, st, { knownSections: tree.map(s => s.key) }) : serverHtml);

  const overlay = document.createElement('div');
  overlay.className = 'rpv-overlay';
  const sidebar = hasSel ? `
    <div class="rpv-sidebar rpv-tree-side">
      <div class="rpv-sh">Report contents</div>
      <div class="rpv-tools"><a id="rpv-all" role="button" tabindex="0">Select all</a><i>·</i><a id="rpv-none" role="button" tabindex="0">Clear all</a></div>
      <ul class="rpv-tree" id="rpv-secs"></ul>
      <div class="rpv-note">Tick a whole section, or open it (▸) and tick single tables / charts.<span class="rpv-drag-hint"></span>
        <b>${['Preview', ...offered.map(e => e.label), 'Print'].join(' = ')}.</b></div>
    </div>` : '';
  overlay.innerHTML = `
    <div class="rpv-shell" role="dialog" aria-label="${escapeHtml(title)}">
      <div class="rpv-bar">
        <div class="rpv-title"><i class="ti ti-file-text" aria-hidden="true"></i>
          <span>${escapeHtml(title)}</span>
          ${subtitle ? `<span class="rpv-sub">${escapeHtml(subtitle)} · fit to width</span>` : ''}</div>
        <div class="rpv-appearance-slot"></div>
        <div class="rpv-actions rpv-export-bar" role="toolbar" aria-label="Save or print the report">
          <button class="btn-mini" id="rpv-close">Close</button>
          <button class="btn-mini" id="rpv-print" title="Print exactly what the preview shows">🖨 Print</button>
          ${offered.map(e => `<button class="btn-mini${e.kind === 'pdf' ? ' primary' : ''}" data-exp="${e.kind}" id="rpv-save-${e.kind}"
            title="Save the previewed report as ${e.label}">⬇ ${e.label}</button>`).join('')}
        </div>
      </div>
      <div class="rpv-main">
        ${sidebar}
        <div class="rpv-scroll">
          <div class="rpv-canvas"><div class="rpv-page"><iframe class="rpv-frame" title="Report preview"></iframe></div></div>
        </div>
      </div>
      <div class="rpv-toast" role="status" aria-live="polite"></div>
    </div>`;
  document.body.appendChild(overlay);

  const scroll = overlay.querySelector('.rpv-scroll');
  const canvas = overlay.querySelector('.rpv-canvas');
  const page   = overlay.querySelector('.rpv-page');
  const frame  = overlay.querySelector('.rpv-frame');
  const toastEl = overlay.querySelector('.rpv-toast');
  page.style.width = frame.style.width = PAGE_W + 'px';
  page.style.transformOrigin = 'top left';

  let toastTimer = null;
  const toast = (msg, kind = 'ok') => {
    toastEl.textContent = msg;
    toastEl.className = `rpv-toast show ${kind}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastEl.className = 'rpv-toast'; }, kind === 'err' ? 7000 : 3500);
  };

  const paintBackdrop = () => { page.style.background = frame.style.background = backdropColor(mode); };
  paintBackdrop();

  let contentH = 1100;
  const relayout = () => {
    const avail = scroll.clientWidth - 32;              // minus padding
    const scale = Math.min(1, avail / PAGE_W);
    page.style.transform = `scale(${scale})`;
    canvas.style.width = (PAGE_W * scale) + 'px';
    canvas.style.height = (contentH * scale) + 'px';
  };
  frame.addEventListener('load', () => {
    try {
      const doc = frame.contentDocument;
      contentH = Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight) || 1100;
    } catch { contentH = 1100; }
    page.style.height = frame.style.height = contentH + 'px';
    relayout();
  });
  const showFinal = () => { frame.srcdoc = finalHtml(); };
  window.addEventListener('resize', relayout);

  const persist = () => { if (storageKey) { try { localStorage.setItem(storageKey, JSON.stringify(st)); } catch { /* ignore */ } } };
  const adopt = (newHtml, keys) => {
    serverHtml = newHtml;
    lastKeys = keys.slice();
    scan = scanReport(serverHtml);
    wraps = wraps || scan.sections.length > 0;
    tree = buildTree(sections || [], scan, tree);
    st = restoreState(st, tree);                         // keep ticks/order; learn new parts
  };
  // Server re-render only when the report needs a section it has not rendered yet (or the
  // renderer cannot be pruned client-side); part ticks + reordering are instant.
  // A renderer that honours key order (serverOrder) also refetches on a pure reorder.
  const needFetch = (keys) => typeof onRerender === 'function'
    && needsRerender(keys, lastKeys, { wraps, serverOrder: !!serverOrder });
  let busy = 0;
  const refresh = async () => {
    persist();
    paintTree();
    const keys = serverKeys(st);
    if (needFetch(keys)) {
      const ticket = ++busy;
      try {
        const newHtml = await onRerender(keys, mode);
        if (ticket !== busy) return;                    // a newer request superseded this one
        if (typeof newHtml === 'string' && newHtml) { adopt(newHtml, keys); paintTree(); }
      } catch { /* keep the current preview */ }
    }
    showFinal();
  };

  // ── the two-level tree (sections ▸ parts) ──
  const listEl = overlay.querySelector('#rpv-secs');
  let dragKey = null;
  function paintTree() {
    if (!listEl) return;
    const counter = overlay.querySelector('.rpv-sh');
    if (counter) counter.textContent = `Report contents · ${countTicked(st, tree)} selected`;
    listEl.innerHTML = '';
    // Drag-to-reorder only when the new order reaches every output (F2): [data-sec] wrappers
    // (pruneHtml reorders them) or a server render that honours the key order.
    const reorder = canReorder(wraps, serverOrder);
    const hint = overlay.querySelector('.rpv-drag-hint');
    if (hint) hint.textContent = reorder ? ' Drag ⋮⋮ to reorder.' : '';
    st.order.forEach(key => {
      const s = tree.find(x => x.key === key);
      if (!s) return;
      const chk = sectionCheck(st, tree, key);
      const li = document.createElement('li');
      li.className = 'rpv-node' + (s.empty ? ' empty' : '') + (chk === 'none' ? ' off' : '');
      li.dataset.key = key;
      li.draggable = reorder && !s.empty;
      const open = expanded.has(key);
      const hasParts = s.parts.length > 0;
      li.innerHTML = `
        <div class="rpv-sec-row">
          ${reorder ? '<span class="rpv-grip" aria-hidden="true" title="Drag to reorder">⋮⋮</span>' : ''}
          <button class="rpv-twisty${hasParts ? '' : ' none'}" aria-label="Show parts" aria-expanded="${open}" ${hasParts ? '' : 'tabindex="-1"'}>${hasParts ? (open ? '▾' : '▸') : ''}</button>
          <label class="rpv-sec"><input type="checkbox" class="rpv-sec-cb" data-key="${escapeHtml(key)}"${chk !== 'none' ? ' checked' : ''}${s.empty ? ' disabled' : ''}>
            <span>${escapeHtml(s.label)}</span></label>
          ${s.empty ? '<i class="rpv-skip">no data</i>' : (hasParts ? `<i class="rpv-count">${s.parts.filter(p => partChecked(st, tree, p.id)).length}/${s.parts.length}</i>` : '')}
        </div>
        ${hasParts && open ? `<ul class="rpv-parts">${s.parts.map(p => `
          <li><label class="rpv-part${p.empty ? ' empty' : ''}"><input type="checkbox" class="rpv-part-cb" data-part="${escapeHtml(p.id)}"${partChecked(st, tree, p.id) ? ' checked' : ''}${s.empty ? ' disabled' : ''}>
            <span>${escapeHtml(p.label)}</span>${p.empty ? '<i class="rpv-skip">no data</i>' : ''}</label></li>`).join('')}</ul>` : ''}`;
      const cb = li.querySelector('.rpv-sec-cb');
      cb.indeterminate = chk === 'some';
      cb.addEventListener('change', () => { st = toggleSection(st, tree, key, cb.checked); refresh(); });
      li.querySelector('.rpv-twisty').addEventListener('click', (e) => {
        e.preventDefault();
        if (!hasParts) return;
        if (expanded.has(key)) expanded.delete(key); else expanded.add(key);
        paintTree();
      });
      li.querySelectorAll('.rpv-part-cb').forEach(pcb => pcb.addEventListener('change', () => {
        st = togglePart(st, tree, pcb.dataset.part, pcb.checked); refresh();
      }));
      if (reorder) {
      li.addEventListener('dragstart', (e) => { dragKey = key; li.classList.add('drag'); try { e.dataTransfer.setData('text/plain', key); } catch { /* ignore */ } });
      li.addEventListener('dragend', () => { dragKey = null; li.classList.remove('drag'); });
      li.addEventListener('dragover', (e) => { e.preventDefault(); li.classList.add('drop'); });
      li.addEventListener('dragleave', () => li.classList.remove('drop'));
      li.addEventListener('drop', (e) => {
        e.preventDefault(); li.classList.remove('drop');
        let from = dragKey;
        try { from = e.dataTransfer.getData('text/plain') || dragKey; } catch { /* ignore */ }
        if (!from || from === key) return;
        st = moveSection(st, from, key); refresh();
      });
      }
      listEl.appendChild(li);
    });
  }

  if (hasSel) {
    const all = overlay.querySelector('#rpv-all');
    const none = overlay.querySelector('#rpv-none');
    const act = (el, fn) => {
      el.addEventListener('click', fn);
      el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(); } });
    };
    act(all, () => { st = selectAll(st, tree); refresh(); });
    act(none, () => { st = clearAll(st); refresh(); });
  }

  // Appearance picker — only when the caller can re-render the preview for a new mode.
  if (typeof onThemeChange === 'function') {
    const picker = buildAppearancePicker({
      current: mode,
      compact: true,
      onChange: async (m) => {
        mode = m;
        paintBackdrop();
        try {
          const keys = hasSel ? serverKeys(st) : undefined;
          const newHtml = await onThemeChange(m, keys);
          if (typeof newHtml === 'string' && newHtml) {
            if (hasSel) adopt(newHtml, keys); else serverHtml = newHtml;
            paintTree();
            showFinal();
          }
        } catch { /* keep the current preview if the re-render fails */ }
      },
    });
    overlay.querySelector('.rpv-appearance-slot').appendChild(picker);
  }

  const close = () => { window.removeEventListener('resize', relayout); overlay.remove(); };
  overlay.querySelector('#rpv-close').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  document.addEventListener('keydown', function esc(e) {
    if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); }
  });

  // ── Print — prints the same final HTML the preview shows (Preview = Print) ──
  overlay.querySelector('#rpv-print').addEventListener('click', () => {
    if (hasSel && !serverKeys(st).length) { toast('Tick at least one section to print.', 'err'); return; }
    try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch { toast('Print is unavailable here.', 'err'); }
  });

  // ── Save as PDF · Word · HTML · Excel — all from the ONE final HTML ──
  const choosePath = async (ext) => {
    const api = typeof window !== 'undefined' && window.pywebview && window.pywebview.api;
    if (!api || typeof api.choose_save_path !== 'function') {
      toast('Saving files is available in the desktop app.', 'err');
      return null;
    }
    return api.choose_save_path(`${baseName}.${ext}`, ext);
  };
  const exportDoc = async (kind, ext, btn) => {
    if (hasSel && !serverKeys(st).length) { toast('Tick at least one section for the report.', 'err'); return; }
    const label = btn.textContent;
    btn.disabled = true;
    try {
      if (kind === 'pdf' && legacyPdf && typeof onSave === 'function') {
        btn.textContent = 'Saving…';
        const ok = await onSave(mode, hasSel ? serverKeys(st) : undefined);
        if (ok !== false) toast('PDF saved.');
        return;
      }
      const outputPath = await choosePath(ext);
      if (!outputPath) return;
      btn.textContent = 'Saving…';
      const resp = await fetch(`http://localhost:${_port()}/api/export/${kind}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          html: finalHtml(), output_path: outputPath, title: featureName,
          meta: { feature: featureName, ...(meta || {}) },
          sections: tree.map(s => ({ key: s.key, label: s.label })),
        }),
      });
      const data = await resp.json();
      if (data && data.ok) toast(`Saved ${ext.toUpperCase()} — ${String(outputPath).split(/[\\/]/).pop()}`);
      else toast(`${ext.toUpperCase()} export failed: ${(data && data.error) || 'unknown error'}`, 'err');
    } catch (e) {
      toast(`${ext.toUpperCase()} export failed: ${e && e.message ? e.message : 'could not reach the local server'}`, 'err');
    } finally {
      btn.disabled = false; btn.textContent = label;
    }
  };
  overlay.querySelectorAll('[data-exp]').forEach(btn => {
    const e = EXPORTS.find(x => x.kind === btn.dataset.exp);
    btn.addEventListener('click', () => exportDoc(e.kind, e.ext, btn));
  });

  // first paint: the tree, then the final (pruned + ordered) report — refetching only if the
  // remembered selection needs a section the caller did not render
  paintTree();
  const firstPaint = refresh();
  // File ▸ Export to Word / HTML opened this preview (export_intent.js): press this bar's own
  // ⬇ Word / ⬇ HTML once the report is painted — or say, in the page, that this report has
  // no Word / HTML export yet.
  const plan = pendingExportPlan(takeDocExport(), offered.map(e => e.kind), featureName);
  if (plan && plan.click) {
    toast(`Saving as ${plan.click === 'docx' ? 'Word' : 'HTML'} — choose where to save it.`);
    Promise.resolve(firstPaint).catch(() => {}).then(() => {
      const b = overlay.isConnected && overlay.querySelector(`#rpv-save-${plan.click}`);
      if (b && !b.disabled) b.click();
    });
  } else if (plan && plan.message) {
    toast(plan.message, 'err');
  }
  return { close, finalHtml, getState: () => st };
}


// ── Global Print-Preview framework: preview WITH a Report Contents selector ──
// One reusable overlay for every feature registered in the p6_report framework.
// The user ticks which sections go in the report and drags them into order; the
// same selection drives the live preview, the saved PDF and Print — Preview == PDF
// == Print, because all three render the one document the server assembler returns.
//
// opts: { feature, report, title, subtitle, serverPort, choosePath, onError }
//   choosePath(defaultName) -> path|null   (Save-as-PDF file dialog)
export function showReportContentsPreview(opts) {
  const { feature, report, title, subtitle, serverPort } = opts;
  const onError = opts.onError || (() => {});
  const LS_KEY = `p6_report_sel_${feature}`;
  // File ▸ Export to Word / HTML opened this preview: it saves PDF only (export_intent.js)
  const pendDoc = pendingExportPlan(takeDocExport(), ['pdf'], title || feature);
  if (pendDoc && pendDoc.message) onError(pendDoc.message);
  let mode = getSavedMode();                       // shared appearance mode (6 themes)
  const api = (path, body) => fetch(`http://localhost:${serverPort}${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }).then(r => r.json());

  const overlay = document.createElement('div');
  overlay.className = 'rpv-overlay';
  overlay.innerHTML = `
    <div class="rpv-shell rpv-wide" role="dialog" aria-label="${escapeHtml(title)}">
      <div class="rpv-bar">
        <div class="rpv-title"><i class="ti ti-file-text" aria-hidden="true"></i>
          <span>${escapeHtml(title)}</span>
          ${subtitle ? `<span class="rpv-sub">${escapeHtml(subtitle)}</span>` : ''}</div>
        <div class="rpv-appearance-slot"></div>
        <div class="rpv-actions">
          <button class="btn-mini" id="rpv-close">Close</button>
          <button class="btn-mini" id="rpv-print">🖨 Print</button>
          <button class="btn-mini primary" id="rpv-save">⬇ Save as PDF</button>
        </div>
      </div>
      <div class="rpv-body">
        <aside class="rpv-side">
          <div class="rpv-side-head">
            <span>Report Contents</span>
            <span class="rpv-side-tools">
              <button class="rpv-link" id="rpv-all">Select all</button>
              <button class="rpv-link" id="rpv-none">Clear all</button>
            </span>
          </div>
          <div class="rpv-hint">Tick what goes in the report. Drag to reorder.</div>
          <ul class="rpv-list" id="rpv-list"></ul>
        </aside>
        <div class="rpv-scroll">
          <div class="rpv-canvas"><div class="rpv-page"><iframe class="rpv-frame" title="Report preview"></iframe></div></div>
        </div>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const listEl = overlay.querySelector('#rpv-list');
  const scroll = overlay.querySelector('.rpv-scroll');
  const canvas = overlay.querySelector('.rpv-canvas');
  const page   = overlay.querySelector('.rpv-page');
  const frame  = overlay.querySelector('.rpv-frame');
  page.style.width = frame.style.width = PAGE_W + 'px';
  page.style.transformOrigin = 'top left';
  const paintBackdrop = () => { page.style.background = frame.style.background = backdropColor(mode); };
  paintBackdrop();

  let contentH = 1100;
  const relayout = () => {
    const avail = scroll.clientWidth - 32;
    const scale = Math.min(1, avail / PAGE_W);
    page.style.transform = `scale(${scale})`;
    canvas.style.width = (PAGE_W * scale) + 'px';
    canvas.style.height = (contentH * scale) + 'px';
  };
  frame.addEventListener('load', () => {
    try {
      const doc = frame.contentDocument;
      contentH = Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight) || 1100;
    } catch { contentH = 1100; }
    page.style.height = frame.style.height = contentH + 'px';
    relayout();
  });
  window.addEventListener('resize', relayout);

  // ── selection state ──
  let components = [];       // [{id,title,type,description,default,has_data}]
  let selected = new Set();  // ticked ids
  let order = [];            // display order of ids (drives the report order)

  const saveSelection = () => {
    try { localStorage.setItem(LS_KEY, JSON.stringify({ selected: [...selected], order })); } catch {}
  };
  const loadSelection = () => {
    try {
      const s = JSON.parse(localStorage.getItem(LS_KEY) || 'null');
      if (s && Array.isArray(s.order) && Array.isArray(s.selected)) return s;
    } catch {}
    return null;
  };

  const TYPE_ICON = { summary: '▤', chart: '▦', table: '▥', text: '☰', findings: '⚑', recommendations: '✔' };

  let renderTimer = null;
  const refreshPreview = () => {
    clearTimeout(renderTimer);
    renderTimer = setTimeout(async () => {
      const selected_ids = order.filter(id => selected.has(id));
      try {
        const data = await api('/api/report/render', { feature, report, selected_ids, order, theme: mode });
        if (data.ok) frame.srcdoc = data.html;
        else onError(data.error || 'Preview failed.');
      } catch { onError('Could not reach the local server.'); }
    }, 120);
  };

  const paintList = () => {
    listEl.innerHTML = '';
    order.forEach(id => {
      const c = components.find(x => x.id === id);
      if (!c) return;
      const li = document.createElement('li');
      li.className = 'rpv-item' + (selected.has(id) ? '' : ' off');
      li.draggable = true;
      li.dataset.id = id;
      const noData = c.has_data ? '' : '<span class="rpv-empty" title="This section has no data; it will show “No data available”">empty</span>';
      li.innerHTML = `
        <span class="rpv-grip" aria-hidden="true">⋮⋮</span>
        <input type="checkbox" class="rpv-cb" ${selected.has(id) ? 'checked' : ''} aria-label="${escapeHtml(c.title)}">
        <span class="rpv-ico" aria-hidden="true">${TYPE_ICON[c.type] || '☰'}</span>
        <span class="rpv-item-txt"><span class="rpv-item-title">${escapeHtml(c.title)}</span>
          ${c.description ? `<span class="rpv-item-desc">${escapeHtml(c.description)}</span>` : ''}</span>
        ${noData}`;
      li.querySelector('.rpv-cb').addEventListener('change', (e) => {
        if (e.target.checked) selected.add(id); else selected.delete(id);
        li.classList.toggle('off', !selected.has(id));
        saveSelection(); refreshPreview();
      });
      // drag reorder
      li.addEventListener('dragstart', (e) => { li.classList.add('drag'); e.dataTransfer.setData('text/plain', id); });
      li.addEventListener('dragend', () => li.classList.remove('drag'));
      li.addEventListener('dragover', (e) => { e.preventDefault(); });
      li.addEventListener('drop', (e) => {
        e.preventDefault();
        const from = e.dataTransfer.getData('text/plain');
        if (!from || from === id) return;
        order.splice(order.indexOf(from), 1);
        order.splice(order.indexOf(id), 0, from);
        saveSelection(); paintList(); refreshPreview();
      });
      listEl.appendChild(li);
    });
  };

  overlay.querySelector('#rpv-all').addEventListener('click', () => {
    components.forEach(c => selected.add(c.id)); saveSelection(); paintList(); refreshPreview();
  });
  overlay.querySelector('#rpv-none').addEventListener('click', () => {
    selected.clear(); saveSelection(); paintList(); refreshPreview();
  });

  const saveBtn = overlay.querySelector('#rpv-save');
  saveBtn.addEventListener('click', async () => {
    const selected_ids = order.filter(id => selected.has(id));
    if (!selected_ids.length) { onError('Select at least one section for the report.'); return; }
    const path = await opts.choosePath();
    if (!path) return;
    saveBtn.disabled = true; const label = saveBtn.textContent; saveBtn.textContent = 'Saving…';
    try {
      const data = await api('/api/report/render', { feature, report, selected_ids, order, output_path: path, theme: mode });
      if (data.ok) { saveBtn.textContent = '✓ Saved'; setTimeout(() => { saveBtn.disabled = false; saveBtn.textContent = label; }, 1200); }
      else { onError(data.error || 'PDF failed.'); saveBtn.disabled = false; saveBtn.textContent = label; }
    } catch { onError('Could not reach the local server.'); saveBtn.disabled = false; saveBtn.textContent = label; }
  });

  overlay.querySelector('#rpv-print').addEventListener('click', () => {
    try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch { onError('Print is unavailable here.'); }
  });

  // Appearance picker — one of the 6 shared modes; re-renders the report server-side
  // so Preview == PDF == Print stays true in every mode.
  const picker = buildAppearancePicker({
    current: mode,
    compact: true,
    onChange: (m) => { mode = m; paintBackdrop(); refreshPreview(); },
  });
  overlay.querySelector('.rpv-appearance-slot').appendChild(picker);

  const close = () => { window.removeEventListener('resize', relayout); overlay.remove(); };
  overlay.querySelector('#rpv-close').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  document.addEventListener('keydown', function esc(e) {
    if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); }
  });

  // ── boot: fetch the manifest, restore saved selection, first render ──
  (async () => {
    try {
      const data = await api('/api/report/manifest', { feature, report });
      if (!data.ok) { onError(data.error || 'Could not load report contents.'); close(); return; }
      components = data.components || [];
      const saved = loadSelection();
      const validIds = new Set(components.map(c => c.id));
      if (saved) {
        order = saved.order.filter(id => validIds.has(id));
        components.forEach(c => { if (!order.includes(c.id)) order.push(c.id); });   // new sections append
        selected = new Set(saved.selected.filter(id => validIds.has(id)));
      } else {
        order = components.map(c => c.id);
        selected = new Set(components.filter(c => c.default).map(c => c.id));
      }
      paintList();
      refreshPreview();
    } catch { onError('Could not reach the local server.'); close(); }
  })();
}
