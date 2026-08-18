// Report preview — shows the exact report HTML (what the PDF will contain) scaled to FIT
// the window width, with Save as PDF / Close. Used by both the EVM and Audit report flows.
import { escapeHtml } from './format.js';

const PAGE_W = 820;   // approximate print page content width (px); the page is scaled to fit

export function showReportPreview({ title, subtitle, html, onSave }) {
  const overlay = document.createElement('div');
  overlay.className = 'rpv-overlay';
  overlay.innerHTML = `
    <div class="rpv-shell" role="dialog" aria-label="${escapeHtml(title)}">
      <div class="rpv-bar">
        <div class="rpv-title"><i class="ti ti-file-text" aria-hidden="true"></i>
          <span>${escapeHtml(title)}</span>
          ${subtitle ? `<span class="rpv-sub">${escapeHtml(subtitle)} · fit to width</span>` : ''}</div>
        <div class="rpv-actions">
          <button class="btn-mini" id="rpv-close">Close</button>
          <button class="btn-mini primary" id="rpv-save">⬇ Save as PDF</button>
        </div>
      </div>
      <div class="rpv-scroll">
        <div class="rpv-canvas"><div class="rpv-page"><iframe class="rpv-frame" title="Report preview"></iframe></div></div>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const scroll = overlay.querySelector('.rpv-scroll');
  const canvas = overlay.querySelector('.rpv-canvas');
  const page   = overlay.querySelector('.rpv-page');
  const frame  = overlay.querySelector('.rpv-frame');
  page.style.width = frame.style.width = PAGE_W + 'px';
  page.style.transformOrigin = 'top left';

  let contentH = 1100;
  const relayout = () => {
    const avail = scroll.clientWidth - 32;              // minus padding
    const scale = Math.min(1, avail / PAGE_W);
    page.style.transform = `scale(${scale})`;
    // reserve the SCALED footprint so the scroll area sizes correctly (transform doesn't)
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

  const close = () => { window.removeEventListener('resize', relayout); overlay.remove(); };
  overlay.querySelector('#rpv-close').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  document.addEventListener('keydown', function esc(e) {
    if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); }
  });

  const saveBtn = overlay.querySelector('#rpv-save');
  saveBtn.addEventListener('click', async () => {
    saveBtn.disabled = true;
    const label = saveBtn.textContent;
    saveBtn.textContent = 'Saving…';
    try {
      const ok = await onSave();                        // returns true → saved, close; false → keep open
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
        const data = await api('/api/report/render', { feature, report, selected_ids, order });
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
      const data = await api('/api/report/render', { feature, report, selected_ids, order, output_path: path });
      if (data.ok) { saveBtn.textContent = '✓ Saved'; setTimeout(() => { saveBtn.disabled = false; saveBtn.textContent = label; }, 1200); }
      else { onError(data.error || 'PDF failed.'); saveBtn.disabled = false; saveBtn.textContent = label; }
    } catch { onError('Could not reach the local server.'); saveBtn.disabled = false; saveBtn.textContent = label; }
  });

  overlay.querySelector('#rpv-print').addEventListener('click', () => {
    try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch { onError('Print is unavailable here.'); }
  });

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
