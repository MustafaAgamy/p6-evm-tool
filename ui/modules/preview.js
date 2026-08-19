// Report preview — shows the exact report HTML (what the PDF will contain) scaled to FIT
// the window width. Optional report-content selector (tick which sections to include) so
// Preview = PDF = Print from one source. Save as PDF / Print / Close. Used by the EVM,
// Calendar and Schedule Health Review report flows.
import { escapeHtml } from './format.js';

const PAGE_W = 820;   // approximate print page content width (px); the page is scaled to fit

export function showReportPreview({ title, subtitle, html, onSave, sections, selected, onRerender, storageKey }) {
  const hasSel = Array.isArray(sections) && sections.length > 0;
  const defaultKeys = (sections || []).filter(s => !s.empty).map(s => s.key);
  const sel = new Set(selected && selected.length ? selected.filter(k => (sections || []).some(s => s.key === k && !s.empty)) : defaultKeys);

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
        const newHtml = await onRerender([...sel]);
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
      const ok = await onSave(hasSel ? [...sel] : undefined);   // pass the current selection to the PDF
      if (ok !== false) { saveBtn.textContent = '✓ Saved'; setTimeout(close, 900); }
      else { saveBtn.disabled = false; saveBtn.textContent = label; }
    } catch {
      saveBtn.disabled = false; saveBtn.textContent = label;
    }
  });
}
