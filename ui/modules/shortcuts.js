// Single source of truth for the app's keyboard shortcuts.
//
// The global key handler (app.js), the Help ▸ Keyboard Shortcuts list (help.js), the
// key hints printed beside the menu-bar items (app.js menu rendering) AND the Ctrl+K
// command palette (palette.js) are ALL generated from this one array — add or change a
// shortcut here and it fires, is documented in Help and shows in the menus with no
// second edit. That is the whole point of this module: nothing can drift out of sync.
//
// Fields:
//   id       — names the action; app.js maps each id to the function it runs (several
//              entries may share an id — e.g. Ctrl+P and Ctrl+S both print).
//   ctrl     — true if Ctrl is required (Meta/⌘ is never used — this is a Windows app).
//   alt      — true if Alt is required (default false). AltGr (= Ctrl+Alt) never matches.
//   shift    — true if Shift is required (default false).
//   anyShift — true to ignore the Shift state (punctuation such as '?' and '/', whose
//              Shift state depends on the keyboard layout; Esc).
//   key      — the KeyboardEvent.key to match, lower-cased (e.g. 'o', 'enter', 'escape', 'f1').
//   code     — optional KeyboardEvent.code matched INSTEAD of key — the physical key
//              ('Digit1', 'BracketLeft'…), so Alt+1 works on AZERTY and other layouts.
//   keys     — how the combo is shown to the user (Help list, menu hint, palette).
//   label    — the description shown in the Help list and the palette.
//   group    — the Help-list section the row sits in.
//   cmd      — optional menu-bar command (app.js MENUS data-cmd) this shortcut performs;
//              that menu item then shows the key hint. The FIRST entry per cmd wins.
//   nav      — for 'goto' entries: the navigator item (NAV id) to open.
//   guard    — true when the browser default is destructive (reload / print / save): it
//              is suppressed even while the planner is typing (when the action itself pauses).
export const SHORTCUTS = [
  // ── File & export ──────────────────────────────────────────────────────────
  { id: 'import', ctrl: true, key: 'o', keys: ['Ctrl', 'O'], label: 'Import a schedule (XER or XML)', group: 'File & export', cmd: 'import' },
  { id: 'pdf',    ctrl: true, key: 'p', keys: ['Ctrl', 'P'], label: 'Print / export to PDF',          group: 'File & export', cmd: 'print', guard: true },
  { id: 'pdf',    ctrl: true, key: 's', keys: ['Ctrl', 'S'], label: 'Save report (PDF)',              group: 'File & export', cmd: 'print', guard: true },
  { id: 'excel',  ctrl: true, key: 'e', keys: ['Ctrl', 'E'], label: 'Export report to Excel',         group: 'File & export', cmd: 'export-excel' },
  { id: 'excel',  ctrl: true, shift: true, key: 'e', keys: ['Ctrl', 'Shift', 'E'], label: 'Export to Excel (same as Ctrl+E)', group: 'File & export', cmd: 'export-excel' },
  { id: 'word',   ctrl: true, shift: true, key: 'w', keys: ['Ctrl', 'Shift', 'W'], label: 'Export to Word',    group: 'File & export', cmd: 'export-word' },
  { id: 'html',   ctrl: true, shift: true, key: 'h', keys: ['Ctrl', 'Shift', 'H'], label: 'Export to HTML',    group: 'File & export', cmd: 'export-html' },
  // ── Run ────────────────────────────────────────────────────────────────────
  { id: 'run',    ctrl: true, key: 'enter', keys: ['Ctrl', '↵'], label: 'Run the feature on screen',     group: 'Run' },
  { id: 'rerun',  ctrl: true, key: 'r',     keys: ['Ctrl', 'R'], label: 'Run the current feature again', group: 'Run', cmd: 'rerun', guard: true },
  // ── Navigate ───────────────────────────────────────────────────────────────
  { id: 'palette',     ctrl: true, key: 'k', keys: ['Ctrl', 'K'], label: 'Command palette — jump to any feature or command', group: 'Navigate', cmd: 'palette' },
  { id: 'recent',      ctrl: true, shift: true, key: 'r', keys: ['Ctrl', 'Shift', 'R'], label: 'Open Recent Projects', group: 'Navigate', cmd: 'recent', guard: true },
  { id: 'toggleNav',   ctrl: true, key: 'b', keys: ['Ctrl', 'B'], label: 'Show / hide Project Navigator', group: 'Navigate', cmd: 'nav-toggle' },
  // ── Jump straight to a feature — EVERY feature has one (owner comment 42) ──────
  // Same order as the navigator: Alt+1 … Alt+9, Alt+0 for the first ten features, then
  // Alt+Shift+1 … Alt+Shift+8 for the next eight; Alt+Shift+9 = AI Chat, Alt+Shift+0 = import screen.
  { id: 'goto', ctrl: false, alt: true, key: '1', code: 'Digit1', keys: ['Alt', '1'], label: 'Go to Overview', group: 'Jump to a feature', nav: 'overview' },
  { id: 'goto', ctrl: false, alt: true, key: '2', code: 'Digit2', keys: ['Alt', '2'], label: 'Go to WBS', group: 'Jump to a feature', nav: 'wbs' },
  { id: 'goto', ctrl: false, alt: true, key: '3', code: 'Digit3', keys: ['Alt', '3'], label: 'Go to Critical Activities (Gantt)', group: 'Jump to a feature', nav: 'schedule' },
  { id: 'goto', ctrl: false, alt: true, key: '4', code: 'Digit4', keys: ['Alt', '4'], label: 'Go to Schedule Health', group: 'Jump to a feature', nav: 'audit' },
  { id: 'goto', ctrl: false, alt: true, key: '5', code: 'Digit5', keys: ['Alt', '5'], label: 'Go to Baseline Narrative', group: 'Jump to a feature', nav: 'narrative' },
  { id: 'goto', ctrl: false, alt: true, key: '6', code: 'Digit6', keys: ['Alt', '6'], label: 'Go to Lag Report', group: 'Jump to a feature', nav: 'lag' },
  { id: 'goto', ctrl: false, alt: true, key: '7', code: 'Digit7', keys: ['Alt', '7'], label: 'Go to Earned Value', group: 'Jump to a feature', nav: 'evm' },
  { id: 'goto', ctrl: false, alt: true, key: '8', code: 'Digit8', keys: ['Alt', '8'], label: 'Go to Out of Sequence', group: 'Jump to a feature', nav: 'oos' },
  { id: 'goto', ctrl: false, alt: true, key: '9', code: 'Digit9', keys: ['Alt', '9'], label: 'Go to Update Analysis', group: 'Jump to a feature', nav: 'update' },
  { id: 'goto', ctrl: false, alt: true, key: '0', code: 'Digit0', keys: ['Alt', '0'], label: 'Go to Critical Path', group: 'Jump to a feature', nav: 'critpath' },
  { id: 'goto', ctrl: false, alt: true, shift: true, key: '1', code: 'Digit1', keys: ['Alt', 'Shift', '1'], label: 'Go to Update vs Update', group: 'Jump to a feature', nav: 'period' },
  { id: 'goto', ctrl: false, alt: true, shift: true, key: '2', code: 'Digit2', keys: ['Alt', 'Shift', '2'], label: 'Go to Consultant Review', group: 'Jump to a feature', nav: 'compare' },
  { id: 'goto', ctrl: false, alt: true, shift: true, key: '3', code: 'Digit3', keys: ['Alt', 'Shift', '3'], label: 'Go to Baseline Revision', group: 'Jump to a feature', nav: 'revcompare' },
  { id: 'goto', ctrl: false, alt: true, shift: true, key: '4', code: 'Digit4', keys: ['Alt', 'Shift', '4'], label: 'Go to P6 Calendar Audit', group: 'Jump to a feature', nav: 'calendar' },
  { id: 'goto', ctrl: false, alt: true, shift: true, key: '5', code: 'Digit5', keys: ['Alt', 'Shift', '5'], label: 'Go to Bad Weather', group: 'Jump to a feature', nav: 'weather' },
  { id: 'goto', ctrl: false, alt: true, shift: true, key: '6', code: 'Digit6', keys: ['Alt', 'Shift', '6'], label: 'Go to Reporting Studio', group: 'Jump to a feature', nav: 'special' },
  { id: 'goto', ctrl: false, alt: true, shift: true, key: '7', code: 'Digit7', keys: ['Alt', 'Shift', '7'], label: 'Go to Productivity & Resources', group: 'Jump to a feature', nav: 'prodintel' },
  { id: 'goto', ctrl: false, alt: true, shift: true, key: '8', code: 'Digit8', keys: ['Alt', 'Shift', '8'], label: 'Go to Knowledge Base', group: 'Jump to a feature', nav: 'kb' },
  { id: 'goto', ctrl: false, alt: true, shift: true, key: '9', code: 'Digit9', keys: ['Alt', 'Shift', '9'], label: 'Open AI Chat', group: 'Jump to a feature', nav: 'chat' },
  { id: 'goto', ctrl: false, alt: true, shift: true, key: '0', code: 'Digit0', keys: ['Alt', 'Shift', '0'], label: 'Back to the import screen', group: 'Jump to a feature', nav: 'home', cmd: 'load-another' },
  // ── View ───────────────────────────────────────────────────────────────────
  { id: 'cycleAppearance', ctrl: true, key: 'd', keys: ['Ctrl', 'D'], label: 'Cycle appearance mode (all 6)', group: 'View', cmd: 'cycle-appearance' },
  { id: 'appearance', ctrl: true, shift: true, key: 'a', keys: ['Ctrl', 'Shift', 'A'], label: 'Open the Appearance picker', group: 'View', cmd: 'appearance' },
  // ── Help ───────────────────────────────────────────────────────────────────
  { id: 'help',  ctrl: false, key: 'f1', keys: ['F1'], label: 'Open Help Center', group: 'Help', cmd: 'help-start' },
  { id: 'help',  ctrl: true, anyShift: true, key: '/', keys: ['Ctrl', '/'], label: 'Open Help Center (same as F1)', group: 'Help', cmd: 'help-start' },
  { id: 'guide', ctrl: true, key: 'f', keys: ['Ctrl', 'F'], label: 'Feature guide — what each feature needs', group: 'Help', cmd: 'help-features' },
  { id: 'keys',  ctrl: false, anyShift: true, key: '?', keys: ['?'], label: 'Show this shortcuts list', group: 'Help', cmd: 'help-keys' },
  { id: 'close', ctrl: false, anyShift: true, key: 'escape', keys: ['Esc'], label: 'Close menu / panel / palette', group: 'Help' },
];

// Rows for the Help ▸ Keyboard Shortcuts screen — [label, keys[]] pairs, derived
// straight from SHORTCUTS so the list is never hand-maintained.
export function shortcutRows() {
  return SHORTCUTS.map(s => [s.label, s.keys]);
}

// The same rows grouped by `group`, in first-appearance order — [{group, rows}].
export function shortcutGroups() {
  const out = [];
  const byName = new Map();
  for (const s of SHORTCUTS) {
    let g = byName.get(s.group);
    if (!g) { g = { group: s.group, rows: [] }; byName.set(s.group, g); out.push(g); }
    g.rows.push([s.label, s.keys]);
  }
  return out;
}

// A canonical, comparable signature of a shortcut's combo — used by the conflict test
// ('ctrl+shift+key:e', 'alt+code:Digit1', 'key:?', …).
export function comboSignature(s) {
  const mods = [s.ctrl ? 'ctrl' : '', s.alt ? 'alt' : '', s.anyShift ? '' : (s.shift ? 'shift' : '')]
    .filter(Boolean).join('+');
  const phys = s.code ? `code:${s.code}` : `key:${s.key}`;
  return (mods ? mods + '+' : '') + phys;
}

// "Ctrl+Shift+E" — the compact hint printed beside menu items and in the palette.
export function keysText(s) {
  return s && s.keys ? s.keys.join('+') : '';
}

// The shortcut a menu-bar command shows as its hint (first registry entry wins), or null.
export function shortcutForCmd(cmd) {
  return SHORTCUTS.find(s => s.cmd && s.cmd === cmd) || null;
}

// The Alt+number shortcut that opens a navigator item, or null.
export function shortcutForNav(navId) {
  return SHORTCUTS.find(s => s.id === 'goto' && s.nav === navId) || null;
}

// The registry entry a keydown event triggers, or null. Pure — reads only the
// KeyboardEvent fields below, so it is unit-tested with plain objects.
export function matchShortcut(e) {
  if (!e || e.metaKey || e.isComposing) return null;
  const k = String(e.key || '').toLowerCase();
  return SHORTCUTS.find(s =>
    !!s.ctrl === !!e.ctrlKey &&
    !!s.alt === !!e.altKey &&
    (s.anyShift || !!s.shift === !!e.shiftKey) &&
    (s.code ? e.code === s.code : s.key === k)) || null;
}

// True when `el` is a place the planner types text into — a text-like <input>, a
// <textarea> or anything contenteditable. Shortcuts pause there so Ctrl+A/C/V/Z, '?'
// and friends keep working exactly as a planner expects (Esc still works).
const NON_TEXT_INPUTS = new Set(['button', 'checkbox', 'radio', 'submit', 'reset', 'range',
  'color', 'file', 'image', 'hidden']);
export function isTextEntry(el) {
  if (!el) return false;
  if (el.isContentEditable) return true;
  const tag = String(el.tagName || '').toUpperCase();
  if (tag === 'TEXTAREA') return true;
  if (tag === 'INPUT') return !NON_TEXT_INPUTS.has(String(el.type || 'text').toLowerCase());
  return false;
}

// What the global handler does with a matched shortcut while focus is on `el`:
//   'run'   — prevent the browser default and run the action;
//   'block' — the planner is typing: don't run it, but suppress a destructive browser
//             default (reload / print / save) so a stray key never throws the page away;
//   'pass'  — leave the key completely alone (normal typing / text editing).
export function shortcutDecision(s, el) {
  if (!s) return 'pass';
  if (s.id === 'close') return 'run';                                   // Esc always works
  const tag = String((el && el.tagName) || '').toUpperCase();
  const typing = isTextEntry(el) ||
    // a focused <select> type-aheads on plain characters — keep those; chords/F-keys still run
    (tag === 'SELECT' && !s.ctrl && !s.alt && !/^f\d+$/.test(s.key));
  if (!typing) return 'run';
  return s.guard ? 'block' : 'pass';
}

// The Help Center (help.js) is a full-screen overlay on top of everything (z-index 99999). A
// shortcut that acts on the SCREEN — print / export, run, jump, the Appearance picker, import —
// would otherwise open its result (PDF preview, in-page message, picker, feature) UNDERNEATH
// Help, so nothing seems to happen. Those close Help first. Kept open: the Help shortcuts
// themselves, Esc (Help closes itself), and Ctrl+D — the appearance change re-themes the Help
// Center itself, so its result is visible without leaving Help.
export const KEEPS_HELP_OPEN = new Set(['help', 'guide', 'keys', 'close', 'cycleAppearance']);

export function closesHelpFirst(id) {
  return !KEEPS_HELP_OPEN.has(id);
}

// Wrap an actions map (id → fn) so every action that works on the screen behind the Help
// Center calls `closeOverlay()` (help.js closeHelp) before it runs. A failing close never
// stops the action.
export function withHelpClosedFirst(actions, closeOverlay) {
  const out = {};
  for (const [id, fn] of Object.entries(actions || {})) {
    out[id] = !closesHelpFirst(id) ? fn : (s) => {
      try { if (closeOverlay) closeOverlay(); } catch (e) { /* no overlay to close */ }
      return fn(s);
    };
  }
  return out;
}

// Build the window-level keydown handler. `actions` maps a shortcut id to a function
// (called with the matched entry); `getActive` returns the focused element (injectable
// for tests). app.js attaches the result on WINDOW in the CAPTURE phase.
export function createShortcutHandler(actions, getActive) {
  const active = getActive || (() => (typeof document !== 'undefined' ? document.activeElement : null));
  return function handleShortcut(e) {
    const s = matchShortcut(e);
    if (!s) return;
    const run = actions && actions[s.id];
    if (!run) return;
    const decision = shortcutDecision(s, active());
    if (decision === 'pass') return;
    if (typeof e.preventDefault === 'function') e.preventDefault();
    if (decision === 'block') return;
    run(s);
  };
}
