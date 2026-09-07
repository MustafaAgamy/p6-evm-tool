// Single source of truth for the app's keyboard shortcuts.
//
// BOTH the global key handler (app.js) and the Help ▸ Keyboard Shortcuts list
// (help.js) are generated from this one array — add or change a shortcut here
// and it takes effect AND is documented in the Help menu automatically, with no
// second edit. That is the whole point of this module: the menu can never drift
// out of sync with the real shortcuts.
//
// Fields:
//   id    — names the action; app.js maps each id to the function it runs.
//   ctrl  — true if the Ctrl modifier is required (alt/meta are never used).
//   key   — the KeyboardEvent.key to match, lower-cased (e.g. 'o', 'enter', 'escape').
//   keys  — how the combo is shown to the user in the Help list.
//   label — the human description shown in the Help list.
export const SHORTCUTS = [
  { id: 'import',          ctrl: true,  key: 'o',      keys: ['Ctrl', 'O'], label: 'Import a schedule' },
  { id: 'run',             ctrl: true,  key: 'enter',  keys: ['Ctrl', '↵'], label: 'Run the selected feature' },
  { id: 'pdf',             ctrl: true,  key: 'p',      keys: ['Ctrl', 'P'], label: 'Print / export to PDF' },
  { id: 'pdf',             ctrl: true,  key: 's',      keys: ['Ctrl', 'S'], label: 'Save report (PDF)' },
  { id: 'excel',           ctrl: true,  key: 'e',      keys: ['Ctrl', 'E'], label: 'Export report to Excel' },
  { id: 'guide',           ctrl: true,  key: 'f',      keys: ['Ctrl', 'F'], label: 'Search the feature guide' },
  { id: 'cycleAppearance', ctrl: true,  key: 'd',      keys: ['Ctrl', 'D'], label: 'Cycle appearance mode (all 6)' },
  { id: 'help',            ctrl: false, key: 'f1',     keys: ['F1'],        label: 'Open Help Center' },
  { id: 'close',           ctrl: false, key: 'escape', keys: ['Esc'],       label: 'Close menu / panel' },
];

// Rows for the Help ▸ Keyboard Shortcuts screen — [label, keys[]] pairs, derived
// straight from SHORTCUTS so the list is never hand-maintained.
export function shortcutRows() {
  return SHORTCUTS.map(s => [s.label, s.keys]);
}
