// Ctrl+K command palette — type to jump to any feature or run any menu command.
//
// The list is BUILT, not hand-written: features come from the navigator (app.js NAV) plus
// the menu-bar AI Chat, commands from the menu bar (app.js MENUS), the key hints from the
// SHORTCUTS registry and the "Needs: …" line from FEATURE_NEEDS — so the palette can never
// disagree with the menus, the navigator or Help ▸ Keyboard shortcuts.
//
// Pure helpers (buildPaletteItems / filterPaletteItems / movePaletteIndex) are unit-tested in
// tests/js/test_palette.js; openPalette() renders a themed in-page dialog (app CSS tokens —
// every appearance mode) with ↑/↓ to move, Enter to run, Esc or a click outside to close.
import { shortcutForCmd, shortcutForNav, keysText } from './shortcuts.js';
import { needsHint } from './feature_needs.js';

const MENU_TITLES = { file: 'File', view: 'View', analysis: 'Analysis', tools: 'Tools', help: 'Help' };
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// nav:   [{ node:{id,label} } | { group, items:[[id,label,…]] }]  (app.js NAV, as-is)
// menus: { file:[[label, cmd] | ['sep']], … }                       (app.js MENUS, as-is)
// extraFeatures: [{ id, label, group }] — features outside the navigator (the AI Chat).
// → [{ kind:'feature'|'command', id|cmd, label, sub, keys }]
export function buildPaletteItems({ nav = [], menus = {}, extraFeatures = [] } = {}) {
  const items = [];
  const seenFeature = new Set();
  const addFeature = (id, label, group) => {
    if (!id || seenFeature.has(id)) return;
    seenFeature.add(id);
    const sc = shortcutForNav(id);
    items.push({ kind: 'feature', id, label, sub: [group, needsHint(id)].filter(Boolean).join(' · '),
      keys: sc ? keysText(sc) : '' });
  };
  for (const sec of nav) {
    if (sec.node) addFeature(sec.node.id, sec.node.label, '');
    else (sec.items || []).forEach(it => addFeature(it[0], it[1], sec.group));
  }
  extraFeatures.forEach(f => addFeature(f.id, f.label, f.group || ''));

  // A menu command whose cmd IS a feature id (Tools ▸ Knowledge Base / Productivity & Resources,
  // File ▸ Recent projects) only re-opens that feature — it is already listed as the feature row,
  // so it is skipped rather than shown twice.
  const seenCmd = new Set();
  for (const [menu, list] of Object.entries(menus)) {
    for (const it of list || []) {
      const [label, cmd] = it;
      if (label === 'sep' || !cmd || seenCmd.has(cmd) || seenFeature.has(cmd)) continue;
      seenCmd.add(cmd);
      const sc = shortcutForCmd(cmd);
      items.push({ kind: 'command', cmd, label: String(label).replace(/…$/, ''),
        sub: MENU_TITLES[menu] || menu, keys: sc ? keysText(sc) : '' });
    }
  }
  return items;
}

// Rank items for a query: every word must appear (label or sub); a label that STARTS with
// the query ranks first, then a word in the label starting with it, then anywhere. Features
// win ties over commands. Blank query → the list unchanged.
export function filterPaletteItems(items, query) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return items.slice();
  const words = q.split(/\s+/);
  const scored = [];
  items.forEach((it, i) => {
    const label = it.label.toLowerCase();
    const hay = label + ' ' + String(it.sub || '').toLowerCase();
    if (!words.every(w => hay.includes(w))) return;
    let score = 3;
    if (label.startsWith(q)) score = 0;
    else if (label.split(/[\s/&()·—-]+/).some(w => w.startsWith(words[0]))) score = 1;
    else if (label.includes(words[0])) score = 2;
    scored.push({ it, i, score: score * 2 + (it.kind === 'feature' ? 0 : 1) });
  });
  scored.sort((a, b) => a.score - b.score || a.i - b.i);
  return scored.map(s => s.it);
}

// Arrow-key movement inside a list of `count` rows, wrapping round.
export function movePaletteIndex(index, delta, count) {
  if (!count) return -1;
  const i = (index < 0 ? (delta > 0 ? -1 : 0) : index) + delta;
  return ((i % count) + count) % count;
}

// ── DOM ────────────────────────────────────────────────────────────────────
const ID = 'cmdk';
let _onPick = null;
let _prevFocus = null;

export function isPaletteOpen() {
  return typeof document !== 'undefined' && !!document.getElementById(ID);
}

export function closePalette() {
  const el = typeof document !== 'undefined' ? document.getElementById(ID) : null;
  if (!el) return false;
  el.remove();
  _onPick = null;
  try { if (_prevFocus && _prevFocus.focus) _prevFocus.focus(); else document.body.focus(); } catch (e) { /* best effort */ }
  _prevFocus = null;
  return true;
}

// Open the palette over the app. `onPick(item)` runs the chosen row (after closing).
// Calling it while open just refocuses the search box.
export function openPalette(items, onPick) {
  if (isPaletteOpen()) { document.querySelector(`#${ID} input`)?.focus(); return; }
  _onPick = onPick;
  _prevFocus = document.activeElement;
  const back = document.createElement('div');
  back.id = ID;
  back.className = 'cmdk-back';
  back.innerHTML = `
    <div class="cmdk" role="dialog" aria-modal="true" aria-label="Command palette">
      <div class="cmdk-search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
        <input type="text" class="cmdk-input" placeholder="Jump to a feature or run a command…" autocomplete="off" spellcheck="false" aria-label="Search features and commands">
        <kbd class="cmdk-esc">Esc</kbd>
      </div>
      <div class="cmdk-list" role="listbox"></div>
      <div class="cmdk-foot"><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>↵</kbd> open</span><span><kbd>Esc</kbd> close</span></div>
    </div>`;
  document.body.appendChild(back);

  const input = back.querySelector('.cmdk-input');
  const list = back.querySelector('.cmdk-list');
  let shown = items.slice();
  let sel = shown.length ? 0 : -1;

  const paint = () => {
    list.innerHTML = shown.length ? shown.map((it, i) => `
      <div class="cmdk-row${i === sel ? ' on' : ''}" role="option" data-i="${i}" aria-selected="${i === sel}">
        <span class="cmdk-kind ${it.kind}">${it.kind === 'feature' ? 'Feature' : 'Command'}</span>
        <span class="cmdk-txt"><span class="cmdk-lbl">${esc(it.label)}</span>${it.sub ? `<span class="cmdk-sub">${esc(it.sub)}</span>` : ''}</span>
        ${it.keys ? `<span class="cmdk-keys">${it.keys.split('+').map(k => `<kbd>${esc(k)}</kbd>`).join('')}</span>` : ''}
      </div>`).join('')
      : '<div class="cmdk-empty">Nothing matches — try “baseline”, “excel” or “weather”.</div>';
    list.querySelector('.cmdk-row.on')?.scrollIntoView({ block: 'nearest' });
  };
  const pick = (i) => {
    const it = shown[i];
    const cb = _onPick;
    closePalette();
    if (it && cb) cb(it);
  };

  input.addEventListener('input', () => { shown = filterPaletteItems(items, input.value); sel = shown.length ? 0 : -1; paint(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      sel = movePaletteIndex(sel, e.key === 'ArrowDown' ? 1 : -1, shown.length);
      paint();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (sel >= 0) pick(sel);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closePalette();
    }
  });
  list.addEventListener('mousemove', (e) => {
    const r = e.target.closest('.cmdk-row'); if (!r) return;
    const i = Number(r.dataset.i);
    if (i !== sel) { sel = i; list.querySelectorAll('.cmdk-row').forEach(x => x.classList.toggle('on', Number(x.dataset.i) === sel)); }
  });
  list.addEventListener('click', (e) => { const r = e.target.closest('.cmdk-row'); if (r) pick(Number(r.dataset.i)); });
  back.addEventListener('mousedown', (e) => { if (e.target === back) closePalette(); });

  paint();
  setTimeout(() => { try { input.focus(); } catch (e) { /* best effort */ } }, 0);
}
