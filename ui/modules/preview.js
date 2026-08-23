// Report preview — shows the exact report HTML (what the PDF will contain) scaled to FIT
// the window width, with an Appearance picker, Save as PDF / Close. Used by the EVM, Audit,
// Calendar and Constructability report flows. Picking an appearance re-renders the preview
// (server-side) and tints the backdrop; the same mode is sent when saving, so preview == PDF.
//
// Optional in-preview "Include sections" picker (Report Contents): pass `sections` as
// [{key,label,checked}]. It renders the standard .per-pick checklist beside the page, toggles
// the report's [data-sec] blocks live, and hands the ticked keys to onSave / onThemeChange —
// the same experience the newer modules (Critical Path / Update / Period) already use.
import { escapeHtml } from './format.js';
import { buildAppearancePicker, getSavedMode, backdropColor } from './appearance.js';

const PAGE_W = 820;   // approximate print page content width (px); the page is scaled to fit

export function showReportPreview({ title, subtitle, html, onSave, onThemeChange, initialMode, sections }) {
  let mode = initialMode || getSavedMode();
  const hasSections = Array.isArray(sections) && sections.length > 0;

  const pickPanel = hasSections ? `
      <div class="per-preview-pick rpv-pick">
        <div class="per-pick-h">Include sections</div>
        ${sections.map(s => `<label class="per-pick"><input type="checkbox" class="rpv-sec-cb" value="${escapeHtml(s.key)}"${s.checked === false ? '' : ' checked'}> ${escapeHtml(s.label)}</label>`).join('')}
        <div class="per-pick-controls"><button class="btn-mini" id="rpv-pick-all">All</button><button class="btn-mini" id="rpv-pick-none">None</button></div>
      </div>` : '';

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
      <div class="rpv-body">
        ${pickPanel}
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

  // Report-Contents selection (only when a picker is shown).
  const secCbs = () => Array.from(overlay.querySelectorAll('.rpv-sec-cb'));
  const selected = () => secCbs().filter(c => c.checked).map(c => c.value);
  const applySections = () => {
    if (!hasSections) return;
    const doc = frame.contentDocument;
    if (!doc) return;
    const on = new Set(selected());
    doc.querySelectorAll('[data-sec]').forEach(el => {
      el.style.display = on.has(el.getAttribute('data-sec')) ? '' : 'none';
    });
  };

  let contentH = 1100;
  const relayout = () => {
    const avail = scroll.clientWidth - 32;              // minus padding
    const scale = Math.min(1, avail / PAGE_W);
    page.style.transform = `scale(${scale})`;
    // reserve the SCALED footprint so the scroll area sizes correctly (transform doesn't)
    canvas.style.width = (PAGE_W * scale) + 'px';
    canvas.style.height = (contentH * scale) + 'px';
  };
  const measure = () => {
    try {
      const doc = frame.contentDocument;
      contentH = Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight) || 1100;
    } catch { contentH = 1100; }
    page.style.height = frame.style.height = contentH + 'px';
    relayout();
  };
  frame.addEventListener('load', () => { applySections(); measure(); });
  frame.srcdoc = html;
  window.addEventListener('resize', relayout);

  if (hasSections) {
    // hiding/showing sections changes the page height → re-measure after each toggle
    const onToggle = () => { applySections(); measure(); };
    secCbs().forEach(c => c.addEventListener('change', onToggle));
    overlay.querySelector('#rpv-pick-all').addEventListener('click', () => { secCbs().forEach(c => { c.checked = true; }); onToggle(); });
    overlay.querySelector('#rpv-pick-none').addEventListener('click', () => { secCbs().forEach(c => { c.checked = false; }); onToggle(); });
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
          const newHtml = await onThemeChange(m);            // re-render keeps the current selection (re-applied on load)
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
      const ok = await onSave(mode, hasSections ? selected() : undefined);   // returns true → saved, close; false → keep open
      if (ok !== false) { saveBtn.textContent = '✓ Saved'; setTimeout(close, 900); }
      else { saveBtn.disabled = false; saveBtn.textContent = label; }
    } catch {
      saveBtn.disabled = false; saveBtn.textContent = label;
    }
  });
}
