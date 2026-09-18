// the window width. Optional report-content selector (tick which sections to include) AND an
// Appearance picker (6 modes) — both re-render the preview server-side from one source, so
// Preview = PDF = Print. Save as PDF / Print / Close. Used by the EVM, Calendar,
// Constructability and Schedule Health Review report flows.
import { escapeHtml } from './format.js';
import { buildAppearancePicker, getSavedMode, backdropColor } from './appearance.js';

const PAGE_W = 820;   // approximate print page content width (px); the page is scaled to fit

export function showReportPreview({ title, subtitle, html, onSave, sections, selected, onRerender, storageKey, onThemeChange, initialMode }) {
  const hasSel = Array.isArray(sections) && sections.length > 0;
  const defaultKeys = (sections || []).filter(s => !s.empty).map(s => s.key);
  const sel = new Set(selected && selected.length ? selected.filter(k => (sections || []).some(s => s.key === k && !s.empty)) : defaultKeys);
  let mode = initialMode || getSavedMode();

  const overlay = document.createElement('div');
  overlay.className = 'rpv-overlay';
  const sidebar = hasSel ? `
    <div class="rpv-sidebar">
      <div class="rpv-sh">Report contents</div>
      <div class="rpv-tools"><a id="rpv-all">Select all</a><i>·</i><a id="rpv-none">Clear all</a></div>
      <div id="rpv-secs">${sections.map(s => `
        <label class="rpv-sec${s.empty ? ' empty' : ''}">
          <input type="checkbox" data-key="${escapeHtml(s.key)}"${sel.has(s.key) ? ' checked' : ''}${s.empty ? ' disabled' : ''}>
          <span>${escapeHtml(s.label)}</span>${s.empty ? '<i class="rpv-skip">no data</i>' : ''}
        </label>`).join('')}</div>
      <div class="rpv-note">Ticked = in the report. <b>Preview = PDF = Print.</b> Empty sections are skipped.</div>
    </div>` : '';
  overlay.innerHTML = `
    <div class="rpv-shell" role="dialog" aria-label="${escapeHtml(title)}">
      <div class="rpv-bar">
        <div class="rpv-title"><i class="ti ti-file-text" aria-hidden="true"></i>
          <span>${escapeHtml(title)}</span>
          ${subtitle ? `<span class="rpv-sub">${escapeHtml(subtitle)} · fit to width</span>` : ''}</div>
        <div class="rpv-appearance-slot"></div>
        <div class="rpv-actions">
          <button class="btn-mini" id="rpv-close">Close</button>
          <button class="btn-mini" id="rpv-print">🖨 Print</button>
          <button class="btn-mini primary" id="rpv-save">⬇ Save as PDF</button>
        </div>
      </div>
      <div class="rpv-main">
        ${sidebar}
        <div class="rpv-scroll">
          <div class="rpv-canvas"><div class="rpv-page"><iframe class="rpv-frame" title="Report preview"></iframe></div></div>
        </div>
      </div>
    </div>`;
  document.body.appendChild(overlay);

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
  frame.srcdoc = html;
  window.addEventListener('resize', relayout);

  // Appearance picker — only when the caller can re-render the preview for a new mode.
  if (typeof onThemeChange === 'function') {
    const picker = buildAppearancePicker({
      current: mode,
      compact: true,
      onChange: async (m) => {
        mode = m;
        paintBackdrop();
        try {
          const newHtml = await onThemeChange(m, hasSel ? [...sel] : undefined);
          if (typeof newHtml === 'string') frame.srcdoc = newHtml;
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

  // ── Content selector (optional) — toggling re-renders the preview from the same source ──
  if (hasSel) {
    const persist = () => { if (storageKey) { try { localStorage.setItem(storageKey, JSON.stringify([...sel])); } catch { /* ignore */ } } };
    const rerender = async () => {
      persist();
      try {
        const newHtml = await onRerender([...sel], mode);
        if (newHtml) { frame.srcdoc = newHtml; }
      } catch { /* keep current preview */ }
    };
    const syncChecks = () => overlay.querySelectorAll('#rpv-secs input').forEach(cb => { cb.checked = sel.has(cb.dataset.key); });
    overlay.querySelectorAll('#rpv-secs input').forEach(cb => cb.addEventListener('change', () => {
      if (cb.checked) sel.add(cb.dataset.key); else sel.delete(cb.dataset.key);
      rerender();
    }));
    overlay.querySelector('#rpv-all').addEventListener('click', () => { defaultKeys.forEach(k => sel.add(k)); syncChecks(); rerender(); });
    overlay.querySelector('#rpv-none').addEventListener('click', () => { sel.clear(); syncChecks(); rerender(); });
  }

  // ── Print — prints the same HTML the preview shows (Preview = Print) ──
  overlay.querySelector('#rpv-print').addEventListener('click', () => {
    try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch { /* pop-up blocked */ }
  });

  const saveBtn = overlay.querySelector('#rpv-save');
  saveBtn.addEventListener('click', async () => {
    saveBtn.disabled = true;
    const label = saveBtn.textContent;
    saveBtn.textContent = 'Saving…';
    try {
      const ok = await onSave(mode, hasSel ? [...sel] : undefined);   // mode + current selection → the PDF
      if (ok !== false) { saveBtn.textContent = '✓ Saved'; setTimeout(close, 900); }
      else { saveBtn.disabled = false; saveBtn.textContent = label; }
    } catch {
      saveBtn.disabled = false; saveBtn.textContent = label;
    }
  });
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
