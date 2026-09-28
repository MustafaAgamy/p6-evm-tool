/**
 * Unit tests for ui/modules/shortcuts.js
 * (plus static guards that ui/modules/help.js derives its Keyboard Shortcuts list from the
 *  registry, and that ui/app.js dispatches through the registry and wires every action id.)
 * Run: node tests/js/test_shortcuts.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  SHORTCUTS, shortcutRows, shortcutGroups, comboSignature, keysText, shortcutForCmd,
  shortcutForNav, matchShortcut, isTextEntry, shortcutDecision, createShortcutHandler,
  KEEPS_HELP_OPEN, closesHelpFirst, withHelpClosedFirst,
} from '../../ui/modules/shortcuts.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..', '..');
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), 'utf8');

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (err) {
    console.error(`  ✗ ${name}`);
    console.error(`    ${err.message}`);
    failed++;
  }
}

// A minimal KeyboardEvent stand-in.
const ev = (key, o = {}) => ({
  key, code: o.code || '', ctrlKey: !!o.ctrl, altKey: !!o.alt, shiftKey: !!o.shift,
  metaKey: !!o.meta, isComposing: false,
  _prevented: false, preventDefault() { this._prevented = true; },
});
const el = (tagName, extra = {}) => ({ tagName, ...extra });

// ── #1 SHORTCUTS shape ──────────────────────────────────────────────────────
console.log('\nSHORTCUTS shape');

test('SHORTCUTS is an array',        () => assert.ok(Array.isArray(SHORTCUTS)));
test('SHORTCUTS has grown well past the original 10', () => assert.ok(SHORTCUTS.length >= 25, `only ${SHORTCUTS.length}`));
test('every entry has string id',    () => SHORTCUTS.forEach(s => assert.equal(typeof s.id, 'string', `id on ${JSON.stringify(s)}`)));
test('every entry has string key',   () => SHORTCUTS.forEach(s => assert.equal(typeof s.key, 'string', `key on ${JSON.stringify(s)}`)));
test('every key is lower-case',      () => SHORTCUTS.forEach(s => assert.equal(s.key, s.key.toLowerCase(), `key on ${s.label}`)));
test('every entry has boolean ctrl', () => SHORTCUTS.forEach(s => assert.equal(typeof s.ctrl, 'boolean', `ctrl on ${JSON.stringify(s)}`)));
test('every entry has non-empty string label', () => SHORTCUTS.forEach(s => {
  assert.equal(typeof s.label, 'string', `label on ${JSON.stringify(s)}`);
  assert.ok(s.label.length > 0, `empty label on ${JSON.stringify(s)}`);
}));
test('every entry has a group',      () => SHORTCUTS.forEach(s => assert.ok(typeof s.group === 'string' && s.group, `group on ${s.label}`)));
test('every entry has non-empty keys array of strings', () => SHORTCUTS.forEach(s => {
  assert.ok(Array.isArray(s.keys), `keys not array on ${JSON.stringify(s)}`);
  assert.ok(s.keys.length > 0, `empty keys on ${JSON.stringify(s)}`);
  s.keys.forEach(k => assert.equal(typeof k, 'string', `non-string key token on ${JSON.stringify(s)}`));
}));
test('the displayed keys agree with the modifiers', () => SHORTCUTS.forEach(s => {
  assert.equal(s.keys.includes('Ctrl'), !!s.ctrl, `Ctrl display vs ctrl flag on ${s.label}`);
  assert.equal(s.keys.includes('Alt'), !!s.alt, `Alt display vs alt flag on ${s.label}`);
  assert.equal(s.keys.includes('Shift'), !!s.shift, `Shift display vs shift flag on ${s.label}`);
}));
test('no Meta/⌘ shortcuts and no AltGr (Ctrl+Alt) combos', () => SHORTCUTS.forEach(s => {
  assert.ok(!(s.ctrl && s.alt), `Ctrl+Alt (= AltGr) combo on ${s.label}`);
  assert.ok(!('meta' in s), `meta on ${s.label}`);
}));
test('no single printable key without a modifier except "?"', () => SHORTCUTS.forEach(s => {
  if (s.ctrl || s.alt || /^f\d+$/.test(s.key) || s.key === 'escape') return;
  assert.equal(s.key, '?', `bare printable shortcut "${s.key}" would fire while typing`);
}));

// ── #2 No combo conflicts (the whole point of the registry) ────────────────
console.log('\nunique combos');

test('every combo signature is unique', () => {
  const seen = new Map();
  SHORTCUTS.forEach(s => {
    const sig = comboSignature(s);
    if (seen.has(sig)) throw new Error(`duplicate combo "${sig}" ("${seen.get(sig)}" and "${s.label}")`);
    seen.set(sig, s.label);
  });
});
test('Ctrl+P and Ctrl+S are distinct combos (not a collision)', () => {
  const p = SHORTCUTS.find(s => s.ctrl && s.key === 'p');
  const sSave = SHORTCUTS.find(s => s.ctrl && s.key === 's');
  assert.ok(p && sSave);
  assert.notEqual(comboSignature(p), comboSignature(sSave));
});
test('Ctrl+E and Ctrl+Shift+E are distinct combos', () => {
  assert.notEqual(comboSignature({ ctrl: true, key: 'e' }), comboSignature({ ctrl: true, shift: true, key: 'e' }));
});
test('no two entries collide through the matcher (each combo resolves to itself)', () => {
  SHORTCUTS.forEach(s => {
    const e = ev(s.key === 'escape' ? 'Escape' : s.key, { ctrl: s.ctrl, alt: s.alt, shift: !!s.shift, code: s.code });
    assert.equal(matchShortcut(e), s, `${s.keys.join('+')} resolved to a different entry`);
  });
});
test('text-editing chords are never taken (Ctrl+A/C/V/X/Z/Y, Ctrl+Backspace/Delete/Home/End)', () => {
  for (const k of ['a', 'c', 'v', 'x', 'z', 'y', 'backspace', 'delete', 'home', 'end', 'arrowleft', 'arrowright']) {
    assert.equal(matchShortcut(ev(k, { ctrl: true })), null, `Ctrl+${k} is registered`);
    // Ctrl+Shift+A = the Appearance picker (asked for); it is not an edit-box chord on Windows,
    // and like every non-Esc shortcut it pauses while the planner is typing (checked below).
    if (k === 'a') continue;
    assert.equal(matchShortcut(ev(k, { ctrl: true, shift: true })), null, `Ctrl+Shift+${k} is registered`);
  }
  assert.equal(shortcutDecision(matchShortcut(ev('A', { ctrl: true, shift: true })), el('INPUT', { type: 'text' })), 'pass');
});
test('browser/WebView2 combos we must not hijack stay free (Ctrl+W/T/N/Tab, Ctrl+Shift+I, Alt+F4, Alt+Left/Right)', () => {
  assert.equal(matchShortcut(ev('w', { ctrl: true })), null);
  assert.equal(matchShortcut(ev('t', { ctrl: true })), null);
  assert.equal(matchShortcut(ev('n', { ctrl: true })), null);
  assert.equal(matchShortcut(ev('tab', { ctrl: true })), null);
  assert.equal(matchShortcut(ev('i', { ctrl: true, shift: true })), null);
  assert.equal(matchShortcut(ev('F4', { alt: true })), null);
  assert.equal(matchShortcut(ev('ArrowLeft', { alt: true })), null);
  assert.equal(matchShortcut(ev('ArrowRight', { alt: true })), null);
});

// ── #3 The planner shortcuts that were asked for ───────────────────────────
console.log('\nrequested shortcuts are registered');

const find = (id, pred = () => true) => SHORTCUTS.find(s => s.id === id && pred(s));
test('Ctrl+E excel export (kept)', () => {
  const x = SHORTCUTS.find(s => s.key === 'e' && s.ctrl && !s.shift);
  assert.ok(x); assert.equal(x.id, 'excel'); assert.deepEqual(x.keys, ['Ctrl', 'E']); assert.match(x.label, /excel/i);
});
test('Ctrl+D cycle appearance (kept)', () => {
  const x = SHORTCUTS.find(s => s.key === 'd' && s.ctrl);
  assert.ok(x); assert.equal(x.id, 'cycleAppearance'); assert.deepEqual(x.keys, ['Ctrl', 'D']); assert.match(x.label, /appearance/i);
});
test('Ctrl+K command palette', () => assert.equal(matchShortcut(ev('k', { ctrl: true })).id, 'palette'));
test('Ctrl+Shift+E / W / H export Excel / Word / HTML', () => {
  assert.equal(matchShortcut(ev('E', { ctrl: true, shift: true })).id, 'excel');
  assert.equal(matchShortcut(ev('W', { ctrl: true, shift: true })).id, 'word');
  assert.equal(matchShortcut(ev('H', { ctrl: true, shift: true })).id, 'html');
});
test('F1 opens Help', () => assert.equal(matchShortcut(ev('F1')).id, 'help'));
test('Ctrl+R re-runs the current feature (and guards the reload)', () => {
  const s = matchShortcut(ev('r', { ctrl: true }));
  assert.equal(s.id, 'rerun'); assert.equal(s.guard, true);
});
test('Ctrl+Shift+R opens Recent Projects', () => assert.equal(matchShortcut(ev('R', { ctrl: true, shift: true })).id, 'recent'));
test('Ctrl+[ / Ctrl+] previous / next feature (by physical key)', () => {
  assert.equal(matchShortcut(ev('[', { ctrl: true, code: 'BracketLeft' })).id, 'prevFeature');
  assert.equal(matchShortcut(ev(']', { ctrl: true, code: 'BracketRight' })).id, 'nextFeature');
});
test('Ctrl+Shift+A opens the Appearance picker', () => assert.equal(matchShortcut(ev('A', { ctrl: true, shift: true })).id, 'appearance'));
test('? (Shift+/) shows the shortcuts list', () => assert.equal(matchShortcut(ev('?', { shift: true })).id, 'keys'));
test('Ctrl+/ still opens Help on layouts where "/" needs Shift', () => assert.equal(matchShortcut(ev('/', { ctrl: true, shift: true })).id, 'help'));
test('Alt+1…Alt+9 and Alt+0 jump to the planned features', () => {
  const want = { Digit1: 'evm', Digit2: 'audit', Digit3: 'update', Digit4: 'critpath', Digit5: 'revcompare',
    Digit6: 'calendar', Digit7: 'special', Digit8: 'chat', Digit9: 'recent', Digit0: 'home' };
  for (const [code, nav] of Object.entries(want)) {
    const s = matchShortcut(ev(code.slice(-1), { alt: true, code }));
    assert.ok(s, `no Alt+${code}`); assert.equal(s.id, 'goto'); assert.equal(s.nav, nav, `Alt+${code}`);
  }
});
test('Alt+digit matches by physical key even when the layout changes e.key (AZERTY "&")', () => {
  assert.equal(matchShortcut(ev('&', { alt: true, code: 'Digit1' })).nav, 'evm');
});
test('AltGr (Ctrl+Alt) + digit never triggers a jump', () => {
  assert.equal(matchShortcut(ev('@', { ctrl: true, alt: true, code: 'Digit2' })), null);
});
test('numpad digits with Alt (Windows Alt-codes) are left alone', () => {
  assert.equal(matchShortcut(ev('1', { alt: true, code: 'Numpad1' })), null);
});
test('Shift changes the combo: Ctrl+Shift+P is not Ctrl+P', () => assert.equal(matchShortcut(ev('P', { ctrl: true, shift: true })), null));
test('Meta (⌘/Win) combos never match', () => assert.equal(matchShortcut(ev('o', { ctrl: true, meta: true })), null));
test('Esc matches with or without Shift', () => {
  assert.equal(matchShortcut(ev('Escape')).id, 'close');
  assert.equal(matchShortcut(ev('Escape', { shift: true })).id, 'close');
});

// ── #4 Typing guard ─────────────────────────────────────────────────────────
console.log('\ntyping guard');

test('text inputs / textareas / contenteditable are text entry', () => {
  assert.ok(isTextEntry(el('INPUT', { type: 'text' })));
  assert.ok(isTextEntry(el('INPUT', { type: 'search' })));
  assert.ok(isTextEntry(el('INPUT', { type: 'date' })));
  assert.ok(isTextEntry(el('INPUT', {})));
  assert.ok(isTextEntry(el('TEXTAREA')));
  assert.ok(isTextEntry(el('DIV', { isContentEditable: true })));
});
test('buttons, checkboxes, body and selects are not text entry', () => {
  assert.ok(!isTextEntry(el('INPUT', { type: 'checkbox' })));
  assert.ok(!isTextEntry(el('INPUT', { type: 'button' })));
  assert.ok(!isTextEntry(el('BUTTON')));
  assert.ok(!isTextEntry(el('BODY')));
  assert.ok(!isTextEntry(el('SELECT')));
  assert.ok(!isTextEntry(null));
});
test('while typing: shortcuts pause (pass), Esc still runs', () => {
  const box = el('INPUT', { type: 'text' });
  assert.equal(shortcutDecision(matchShortcut(ev('e', { ctrl: true })), box), 'pass');
  assert.equal(shortcutDecision(matchShortcut(ev('?', { shift: true })), box), 'pass');
  assert.equal(shortcutDecision(matchShortcut(ev('1', { alt: true, code: 'Digit1' })), box), 'pass');
  assert.equal(shortcutDecision(matchShortcut(ev('k', { ctrl: true })), box), 'pass');
  assert.equal(shortcutDecision(matchShortcut(ev('Escape')), box), 'run');
});
test('while typing: reload / print / save defaults are blocked, not run', () => {
  const box = el('TEXTAREA');
  assert.equal(shortcutDecision(matchShortcut(ev('r', { ctrl: true })), box), 'block');
  assert.equal(shortcutDecision(matchShortcut(ev('R', { ctrl: true, shift: true })), box), 'block');
  assert.equal(shortcutDecision(matchShortcut(ev('p', { ctrl: true })), box), 'block');
  assert.equal(shortcutDecision(matchShortcut(ev('s', { ctrl: true })), box), 'block');
});
test('on a focused <select>: chords and F-keys run, a bare "?" types ahead', () => {
  const sel = el('SELECT');
  assert.equal(shortcutDecision(matchShortcut(ev('d', { ctrl: true })), sel), 'run');
  assert.equal(shortcutDecision(matchShortcut(ev('F1')), sel), 'run');
  assert.equal(shortcutDecision(matchShortcut(ev('?', { shift: true })), sel), 'pass');
});
test('outside inputs everything runs', () => {
  SHORTCUTS.forEach(s => assert.equal(shortcutDecision(s, el('BODY')), 'run', s.label));
});

// ── #5 Dispatch ─────────────────────────────────────────────────────────────
console.log('\ncreateShortcutHandler dispatch');

test('runs the action with the matched entry and prevents the default', () => {
  let got = null; let focused = el('BODY');
  const h = createShortcutHandler({ goto: s => { got = s.nav; } }, () => focused);
  const e = ev('3', { alt: true, code: 'Digit3' }); h(e);
  assert.equal(got, 'update'); assert.equal(e._prevented, true);
});
test('unregistered keys are untouched', () => {
  let ran = false;
  const h = createShortcutHandler({ excel: () => { ran = true; } }, () => el('BODY'));
  const e = ev('q', { ctrl: true }); h(e);
  assert.equal(ran, false); assert.equal(e._prevented, false);
});
test('a registered combo without a wired action is untouched', () => {
  const h = createShortcutHandler({}, () => el('BODY'));
  const e = ev('e', { ctrl: true }); h(e);
  assert.equal(e._prevented, false);
});
test('typing in a box: Ctrl+E does nothing and keeps the default', () => {
  let ran = false;
  const h = createShortcutHandler({ excel: () => { ran = true; } }, () => el('INPUT', { type: 'text' }));
  const e = ev('e', { ctrl: true }); h(e);
  assert.equal(ran, false); assert.equal(e._prevented, false);
});
test('typing in a box: Ctrl+R is blocked (no reload) but the re-run does not fire', () => {
  let ran = false;
  const h = createShortcutHandler({ rerun: () => { ran = true; } }, () => el('INPUT', { type: 'text' }));
  const e = ev('r', { ctrl: true }); h(e);
  assert.equal(ran, false); assert.equal(e._prevented, true);
});
test('typing in a box: Esc still closes', () => {
  let ran = false;
  const h = createShortcutHandler({ close: () => { ran = true; } }, () => el('TEXTAREA'));
  h(ev('Escape'));
  assert.equal(ran, true);
});

// ── SHELL-4: shortcuts that act on the screen close the Help Center first ────
console.log('\nHelp Center is closed before a screen action (SHELL-4)');
test('only Help / guide / shortcuts list / Esc / Ctrl+D keep Help open', () => {
  assert.deepEqual([...KEEPS_HELP_OPEN].sort(), ['close', 'cycleAppearance', 'guide', 'help', 'keys']);
  for (const id of ['pdf', 'excel', 'word', 'html', 'run', 'rerun', 'appearance', 'import', 'toggleNav',
                    'goto', 'palette', 'prevFeature', 'nextFeature', 'recent']) {
    assert.equal(closesHelpFirst(id), true, id);
  }
  // every registry id is decided one way or the other
  [...new Set(SHORTCUTS.map(s => s.id))].forEach(id => assert.equal(typeof closesHelpFirst(id), 'boolean'));
});
test('withHelpClosedFirst: closes Help BEFORE the action runs, with the matched entry', () => {
  const log = [];
  const wrapped = withHelpClosedFirst({
    pdf: (s) => log.push(['pdf', s.key]), help: () => log.push(['help']), cycleAppearance: () => log.push(['cycle']),
  }, () => log.push(['closeHelp']));
  wrapped.pdf({ key: 'p' });
  wrapped.help();
  wrapped.cycleAppearance();
  assert.deepEqual(log, [['closeHelp'], ['pdf', 'p'], ['help'], ['cycle']]);
});
test('withHelpClosedFirst: a failing close never stops the action', () => {
  let ran = false;
  withHelpClosedFirst({ excel: () => { ran = true; } }, () => { throw new Error('no overlay'); }).excel({});
  assert.equal(ran, true);
});
test('through the real handler: Ctrl+Shift+W with Help open → close Help, then export', () => {
  const log = [];
  const h = createShortcutHandler(withHelpClosedFirst({ word: () => log.push('word') }, () => log.push('closeHelp')), () => el('BODY'));
  h(ev('W', { ctrl: true, shift: true }));
  assert.deepEqual(log, ['closeHelp', 'word']);
});

// ── #6 Derived views of the registry ───────────────────────────────────────
console.log('\nderived rows, groups, hints');

const rows = shortcutRows();
test('shortcutRows() mirrors SHORTCUTS', () => {
  assert.equal(rows.length, SHORTCUTS.length);
  rows.forEach((row, i) => { assert.equal(row[0], SHORTCUTS[i].label); assert.deepEqual(row[1], SHORTCUTS[i].keys); });
});
test('shortcutGroups() covers every row exactly once, in registry order', () => {
  const flat = shortcutGroups().flatMap(g => g.rows);
  assert.deepEqual(flat.map(r => r[0]).sort(), SHORTCUTS.map(s => s.label).sort());
  const names = shortcutGroups().map(g => g.group);
  assert.equal(new Set(names).size, names.length);
});
test('keysText joins with "+"', () => assert.equal(keysText({ keys: ['Ctrl', 'Shift', 'E'] }), 'Ctrl+Shift+E'));
test('shortcutForCmd: the first entry per menu command wins', () => {
  assert.deepEqual(shortcutForCmd('print').keys, ['Ctrl', 'P']);
  assert.deepEqual(shortcutForCmd('export-excel').keys, ['Ctrl', 'E']);
  assert.deepEqual(shortcutForCmd('help-start').keys, ['F1']);
  assert.deepEqual(shortcutForCmd('recent').keys, ['Ctrl', 'Shift', 'R']);
  assert.equal(shortcutForCmd('no-such-cmd'), null);
});
test('shortcutForNav finds the Alt+number for a feature', () => {
  assert.deepEqual(shortcutForNav('evm').keys, ['Alt', '1']);
  assert.equal(shortcutForNav('lag'), null);
});

// ── #7 Static guards: help.js + app.js stay wired to the registry ──────────
console.log('\nstatic wiring guards');

const helpSrc = read('ui', 'modules', 'help.js');
const appSrc = read('ui', 'app.js');
test('help.js imports from ./shortcuts.js', () =>
  assert.match(helpSrc, /import[^;]*['"][^'"]*shortcuts\.js['"]/, 'help.js does not import from ./shortcuts.js'));
test('help.js has no hardcoded shortcut row literal', () =>
  assert.ok(!helpSrc.includes("['Ctrl', 'O']") && !helpSrc.includes("['Ctrl','O']")));
test('app.js dispatches through createShortcutHandler on WINDOW in the CAPTURE phase', () => {
  assert.match(appSrc, /createShortcutHandler\(/);
  assert.match(appSrc, /window\.addEventListener\(\s*'keydown'\s*,\s*[^,]+,\s*true\s*\)/);
});
test('app.js closes the Help Center before screen actions (SHELL-4)', () => {
  assert.match(appSrc, /createShortcutHandler\(\s*withHelpClosedFirst\(\s*SHORTCUT_ACTIONS\s*,\s*closeHelp\s*\)\s*\)/,
    'the key handler must be built from withHelpClosedFirst(SHORTCUT_ACTIONS, closeHelp)');
});
test('app.js: Ctrl+P / File ▸ Print on the Baseline Narrative runs its own PDF export', () => {
  // narrativePrint() returns null (the narrative prints through its own Export PDF button), so
  // without this mapping Ctrl+P always said "Open this view and let it finish loading".
  const m = appSrc.match(/\n\s*narrative:\{([^}]*)\},/);
  assert.ok(m, 'REPORT_BTN.narrative not found');
  assert.match(m[1], /pdf:\s*'narrative-pdf-btn'/);
  assert.match(m[1], /docx:\s*'narrative-word-btn'/);
  assert.match(read('ui', 'index.html'), /id="narrative-pdf-btn"/);
  assert.match(read('ui', 'modules', 'narrative.js'), /if \(!state\.narrativeDoc\) \{ showError\('Generate the narrative first\.'\); return; \}/);
});
test('app.js: Ctrl+R never re-renders the Baseline Narrative (SHELL-3)', () => {
  const m = appSrc.match(/const NO_GENERIC_RERUN = \{([\s\S]*?)\};/);
  assert.ok(m, 'NO_GENERIC_RERUN not found in app.js');
  assert.match(m[1], /narrative\s*:/);
  const fn = appSrc.slice(appSrc.indexOf('function runCurrentFeature'), appSrc.indexOf('function cycleAppearance'));
  assert.ok(fn.indexOf('NO_GENERIC_RERUN') > 0 && fn.indexOf('NO_GENERIC_RERUN') < fn.indexOf('runFeature(view)'),
    'runCurrentFeature must check NO_GENERIC_RERUN before the generic runFeature(view)');
});
test('app.js wires an action for every shortcut id', () => {
  const m = appSrc.match(/const SHORTCUT_ACTIONS = \{([\s\S]*?)\n  \};/);
  assert.ok(m, 'SHORTCUT_ACTIONS block not found');
  const wired = new Set([...m[1].matchAll(/^\s{4}(\w+)\s*:/gm)].map(x => x[1]));
  const ids = [...new Set(SHORTCUTS.map(s => s.id))];
  const missing = ids.filter(id => !wired.has(id));
  assert.deepEqual(missing, [], `no action wired for: ${missing.join(', ')}`);
});
test('app.js handles every menu command a shortcut claims', () => {
  const cmds = [...new Set(SHORTCUTS.map(s => s.cmd).filter(Boolean))];
  const missing = cmds.filter(c => !appSrc.includes(`cmd === '${c}'`));
  assert.deepEqual(missing, [], `runMenuCmd does not handle: ${missing.join(', ')}`);
});
test('every Alt+number target is a real navigator id or chat/home', () => {
  const navIds = new Set([...appSrc.matchAll(/\['([a-z]+)','/g)].map(m => m[1]));
  navIds.add('home'); navIds.add('chat');
  SHORTCUTS.filter(s => s.id === 'goto').forEach(s => assert.ok(navIds.has(s.nav), `unknown nav "${s.nav}"`));
});

// ── Summary ─────────────────────────────────────────────────────────────────
console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
