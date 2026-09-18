// Report appearance modes — ONE reusable picker shared by every report preview flow
// (EVM, Audit, Consultant Review, Update Analysis, Update-vs-Update, Calendar,
// Constructability, and any future report). It chooses which named palette the report
// renders in; the same mode is sent to the server so the on-screen preview and the
// exported PDF match exactly.
//
// The palette hexes live in report_theme.py (the single source of truth). The small
// swatch/label metadata below is a display mirror — keep the id list in sync with
// report_theme.MODES.

export const REPORT_MODES = [
  { id: 'light',     label: 'Light',         desc: 'Clean default — prints cleanly',          page: '#ffffff', accent: '#2563eb', tile: '#eef2f7' },
  { id: 'dark',      label: 'Dark',          desc: 'Slate reading mode for screens',          page: '#131922', accent: '#5b9bff', tile: '#1a212c' },
  { id: 'midnight',  label: 'Midnight',      desc: 'Deep navy — boardroom presenting',        page: '#0f1830', accent: '#6ea8ff', tile: '#14203f' },
  { id: 'sepia',     label: 'Sepia',         desc: 'Warm paper — low glare',                  page: '#f8f2e6', accent: '#a8631f', tile: '#f1e9d8' },
  { id: 'contrast',  label: 'High-contrast', desc: 'Max legibility / ink-safe',               page: '#ffffff', accent: '#0033cc', tile: '#f2f2f2' },
  { id: 'blueprint', label: 'Blueprint',     desc: 'Engineering-drawing look',                page: '#0f3560', accent: '#7fdfff', tile: '#0d2e53' },
];

const STORAGE_KEY = 'p6_report_appearance';
export const DEFAULT_MODE = 'light';

const _ids = REPORT_MODES.map(m => m.id);

/** The user's last-picked appearance (remembered; themes both the app screen and reports).
 *  Falls back to the legacy 2-mode key, then Light. */
export function getSavedMode() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (_ids.includes(v)) return v;
    const legacy = localStorage.getItem('p6_evm_theme');   // old light/dark-only key
    if (legacy === 'light' || legacy === 'dark') return legacy;
    return DEFAULT_MODE;
  } catch { return DEFAULT_MODE; }
}

export function setSavedMode(mode) {
  if (!_ids.includes(mode)) return;
  try { localStorage.setItem(STORAGE_KEY, mode); } catch { /* no storage — session only */ }
}

/** Paint the whole app in a mode by stamping the root — CSS `:root[data-appearance="…"]` does the rest. */
export function applyAppMode(mode) {
  const m = _ids.includes(mode) ? mode : DEFAULT_MODE;
  try { document.documentElement.setAttribute('data-appearance', m); } catch { /* no DOM */ }
}

/** The unified setter: persist the choice, retheme the whole app screen, and sync the toolbar control.
 *  Report previews/PDFs read the same saved mode, so one call themes everything. */
export function setAppMode(mode) {
  const m = _ids.includes(mode) ? mode : DEFAULT_MODE;
  setSavedMode(m);
  applyAppMode(m);
  try {
    const sel = document.getElementById('report-appearance');
    if (sel && sel.value !== m) sel.value = m;
  } catch { /* no DOM */ }
  return m;
}

/** The report page background for a mode — used to tint the preview letterbox so a dark
 *  report doesn't sit on a white backdrop. */
export function backdropColor(mode) {
  const m = REPORT_MODES.find(x => x.id === mode) || REPORT_MODES[0];
  return m.page;
}

/**
 * Build the reusable appearance picker.
 *   opts.current  — selected mode id (defaults to the remembered one)
 *   opts.onChange — (modeId) => void, called on selection (also persists the choice)
 *   opts.compact  — true → toolbar row (no heading); false → labelled block for a pick pane
 * Returns the root element; also exposes .setMode(id) and .getMode().
 */
export function buildAppearancePicker(opts = {}) {
  const onChange = opts.onChange || (() => {});
  let current = _ids.includes(opts.current) ? opts.current : getSavedMode();

  const root = document.createElement('div');
  root.className = 'rpt-appearance' + (opts.compact ? ' rpt-appearance--compact' : '');

  const h = document.createElement('span');
  h.className = 'rpt-appearance-h';
  h.textContent = 'Appearance';
  root.appendChild(h);

  const row = document.createElement('div');
  row.className = 'rpt-chip-row';
  root.appendChild(row);

  const chips = REPORT_MODES.map(m => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'rpt-chip';
    b.dataset.mode = m.id;
    b.title = m.desc;
    b.setAttribute('aria-pressed', String(m.id === current));
    b.innerHTML =
      `<span class="rpt-chip-sw" style="background:${m.page}">` +
      `<i style="background:${m.tile}"></i><i style="background:${m.accent}"></i></span>` +
      `<span class="rpt-chip-lb">${m.label}</span>`;
    b.addEventListener('click', () => setMode(m.id));
    row.appendChild(b);
    return b;
  });

  function setMode(id, silent) {
    if (!_ids.includes(id)) return;
    current = id;
    chips.forEach(c => c.setAttribute('aria-pressed', String(c.dataset.mode === id)));
    setAppMode(id);                 // persist + retheme the whole app + sync the toolbar control
    if (!silent) onChange(id);
  }

  root.setMode = setMode;
  root.getMode = () => current;
  return root;
}

/**
 * Wire the always-visible toolbar "Report look" <select> to the remembered mode.
 * Populates it with the six modes, reflects the saved choice, and persists changes so
 * every report preview/PDF picks it up. `onChange(modeId)` is optional (e.g. to re-theme
 * an open preview). Returns the element, or null if not found.
 */
export function initReportAppearanceControl(sel, onChange) {
  const el = typeof sel === 'string' ? document.getElementById(sel) : sel;
  if (!el) return null;
  el.innerHTML = REPORT_MODES.map(m => `<option value="${m.id}">${m.label}</option>`).join('');
  el.value = getSavedMode();
  el.addEventListener('change', () => {
    setAppMode(el.value);                       // persist + retheme the whole app screen
    if (typeof onChange === 'function') onChange(el.value);
  });
  return el;
}
