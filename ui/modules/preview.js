// Report preview — shows the exact report HTML (what the PDF will contain) scaled to FIT
// the window width, with an Appearance picker, Save as PDF / Close. Used by the EVM, Audit,
// Calendar and Constructability report flows. Picking an appearance re-renders the preview
// (server-side) and tints the backdrop; the same mode is sent when saving, so preview == PDF.
import { escapeHtml } from './format.js';
import { buildAppearancePicker, getSavedMode, backdropColor } from './appearance.js';

const PAGE_W = 820;   // approximate print page content width (px); the page is scaled to fit

export function showReportPreview({ title, subtitle, html, onSave, onThemeChange, initialMode }) {
  let mode = initialMode || getSavedMode();

  const overlay = document.createElement('div');
  overlay.className = 'rpv-overlay';
  overlay.innerHTML = `
    <div class="rpv-shell" role="dialog" aria-label="${escapeHtml(title)}">
      <div class="rpv-bar">
        <div class="rpv-title"><i class="ti ti-file-text" aria-hidden="true"></i>
          <span>${escapeHtml(title)}</span>
          ${subtitle ? `<span class="rpv-sub">${escapeHtml(subtitle)} · fit to width</span>` : ''}</div>
        <div class="rpv-appearance-slot"></div>
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

  const paintBackdrop = () => { page.style.background = frame.style.background = backdropColor(mode); };
  paintBackdrop();

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

  // Appearance picker — only when the caller can re-render the preview for a new mode.
  if (typeof onThemeChange === 'function') {
    const picker = buildAppearancePicker({
      current: mode,
      compact: true,
      onChange: async (m) => {
        mode = m;
        paintBackdrop();
        try {
          const newHtml = await onThemeChange(m);
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

  const saveBtn = overlay.querySelector('#rpv-save');
  saveBtn.addEventListener('click', async () => {
    saveBtn.disabled = true;
    const label = saveBtn.textContent;
    saveBtn.textContent = 'Saving…';
    try {
      const ok = await onSave(mode);                    // returns true → saved, close; false → keep open
      if (ok !== false) { saveBtn.textContent = '✓ Saved'; setTimeout(close, 900); }
      else { saveBtn.disabled = false; saveBtn.textContent = label; }
    } catch {
      saveBtn.disabled = false; saveBtn.textContent = label;
    }
  });
}
