/**
 * Unit tests for ui/modules/feature_needs.js — the ONE data structure behind Help ▸ Feature
 * guide, the "Needs: …" hints in the Analysis menu and the navigator tooltips.
 * Also guards that (a) every navigator item has an entry, so a future feature without one
 * fails here, and (b) the entries still tell the truth about what the code accepts — when
 * the server behaviour changes these tests point at the help text that must change with it.
 * Run: node tests/js/test_feature_needs.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  FEATURE_NEEDS, featureNeeds, needsHint, needsTooltip, needsSearchText, filterNeeds,
  needsGroups, requiredFileCount,
} from '../../ui/modules/feature_needs.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..', '..');
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), 'utf8');

let passed = 0;
let failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}`); console.error(`    ${err.message}`); failed++; }
}

// ── Parse the navigator (NAV) straight out of ui/app.js ────────────────────
const appSrc = read('ui', 'app.js');
const navBlock = (appSrc.match(/const NAV = \[([\s\S]*?)\n  \];/) || [])[1] || '';
const navRoot = [...navBlock.matchAll(/node:\s*\{\s*id:'([a-z]+)'/g)].map(m => m[1]);
const navGroups = [];      // [{group, items:[[id,label]]}]
for (const g of navBlock.matchAll(/\{ group:'([^']+)', items:\[([\s\S]*?)\]\}/g)) {
  navGroups.push({ group: g[1], items: [...g[2].matchAll(/\['([a-z]+)','([^']+)'/g)].map(m => [m[1], m[2]]) });
}
const navItems = navGroups.flatMap(g => g.items.map(([id, label]) => ({ id, label, group: g.group })));

console.log('\nnavigator coverage');
test('NAV parsed from app.js (root + groups)', () => {
  assert.deepEqual(navRoot, ['home']);
  assert.ok(navItems.length >= 20, `only ${navItems.length} navigator items parsed`);
});
test('EVERY navigator id has a FEATURE_NEEDS entry', () => {
  const missing = [...navRoot, ...navItems.map(n => n.id)].filter(id => !featureNeeds(id));
  assert.deepEqual(missing, [], `no feature-needs entry for: ${missing.join(', ')}`);
});
test('the menu-bar AI Chat has an entry too', () => assert.ok(featureNeeds('chat')));
test('no stale entries: every entry is a navigator id, the root, or chat', () => {
  const known = new Set([...navRoot, ...navItems.map(n => n.id), 'chat']);
  const stale = FEATURE_NEEDS.map(f => f.id).filter(id => !known.has(id));
  assert.deepEqual(stale, []);
});
test('ids are unique', () => {
  const ids = FEATURE_NEEDS.map(f => f.id);
  assert.equal(new Set(ids).size, ids.length);
});
test('names and groups match the navigator labels exactly', () => {
  for (const n of navItems) {
    const f = featureNeeds(n.id);
    assert.equal(f.name, n.label, `name of ${n.id}`);
    assert.equal(f.group, n.group, `group of ${n.id}`);
  }
});
test('entries follow navigator order (so Help reads like the navigator)', () => {
  const order = [...navRoot, ...navItems.map(n => n.id)];
  const ours = FEATURE_NEEDS.map(f => f.id).filter(id => order.includes(id));
  assert.deepEqual(ours, order);
});

console.log('\nentry shape');
const FORMATS = new Set(['XER or XML', 'XML', 'XER']);
const KINDS = new Set(['p6', 'extra', 'optional']);
test('every entry states what / hint / produces / start', () => FEATURE_NEEDS.forEach(f => {
  for (const k of ['name', 'what', 'hint', 'produces', 'start']) {
    assert.ok(typeof f[k] === 'string' && f[k].trim(), `${f.id}.${k}`);
  }
  assert.ok(Array.isArray(f.files) && Array.isArray(f.other) && Array.isArray(f.exports), `${f.id} arrays`);
}));
test('every schedule file states count, role, an accepted format and its kind', () => FEATURE_NEEDS.forEach(f => f.files.forEach(x => {
  assert.ok(Number.isInteger(x.n) && x.n >= 1, `${f.id} n`);
  assert.ok(x.role && x.role.trim(), `${f.id} role`);
  assert.ok(FORMATS.has(x.formats), `${f.id} formats "${x.formats}"`);
  assert.ok(KINDS.has(x.k), `${f.id} kind "${x.k}"`);
})));
test('hints are compact (fit under a menu item)', () => FEATURE_NEEDS.forEach(f =>
  assert.ok(f.hint.length <= 90, `${f.id} hint is ${f.hint.length} chars`)));
test('every "how to start" names a menu path', () => FEATURE_NEEDS.forEach(f =>
  assert.match(f.start, /▸/, `${f.id} start "${f.start}"`)));
test('features that analyse a schedule export at least one file', () => FEATURE_NEEDS
  .filter(f => !['home', 'recent'].includes(f.id))
  .forEach(f => assert.ok(f.exports.length > 0, `${f.id} has no exports listed`)));

console.log('\nhelpers');
test('needsHint prefixes "Needs:"', () => assert.equal(needsHint('overview'), 'Needs: 1 P6 schedule (XER or XML)'));
test('needsHint is empty for unknown ids', () => assert.equal(needsHint('nope'), ''));
test('needsTooltip = what + needs', () => assert.match(needsTooltip('evm'), /^Planned vs earned[\s\S]*\nNeeds: /));
test('search text covers roles, formats, other inputs and exports', () => {
  const t = needsSearchText(featureNeeds('weather'));
  for (const w of ['internet', 'site type', 'location', 'xer or xml', 'pdf']) assert.ok(t.includes(w), w);
});
test('filterNeeds: blank → all, words are AND-ed', () => {
  assert.equal(filterNeeds('').length, FEATURE_NEEDS.length);
  assert.deepEqual(filterNeeds('weather internet').map(f => f.id), ['weather']);
  assert.ok(filterNeeds('rev.00').some(f => f.id === 'revcompare'));
  assert.ok(filterNeeds('e1').some(f => f.id === 'evm'));
  assert.ok(filterNeeds('contract milestones').some(f => f.id === 'audit'));
  assert.deepEqual(filterNeeds('zzzz-nothing'), []);
});
test('needsGroups keeps navigator group order', () => {
  const gs = needsGroups().map(g => g.group).filter(Boolean);
  assert.deepEqual(gs.slice(0, navGroups.length), navGroups.map(g => g.group));
});
test('requiredFileCount', () => {
  assert.equal(requiredFileCount(featureNeeds('overview')), 1);
  assert.equal(requiredFileCount(featureNeeds('revcompare')), 2);
  assert.equal(requiredFileCount(featureNeeds('period')), 2);
  assert.equal(requiredFileCount(featureNeeds('prodintel')), 0);
});

// ── The owner's examples, stated as the code actually behaves ──────────────
console.log('\ntruth vs the code');
const serverSrc = read('server.py');
const xerSrc = read('p6_evm', 'xer.py');
const appPy = read('app.py');
test('every schedule picker accepts BOTH formats (app.py choose_file) → "XER or XML"', () => {
  assert.match(appPy, /P6 Schedule Files \(\*\.xml;\*\.xer\)/);
});
test('Baseline Revision needs TWO baselines, each XER or XML (not "2 XERs")', () => {
  const f = featureNeeds('revcompare');
  assert.equal(f.files.length, 2);
  f.files.forEach(x => assert.equal(x.formats, 'XER or XML'));
  assert.match(serverSrc, /rev0_path[\s\S]{0,400}rev1_path/);
});
test('Update Analysis reads ONE file — the baseline must be inside it', () => {
  const f = featureNeeds('update');
  assert.equal(f.files.length, 1);
  // server: re-parses the one update file and refuses when it carries no baseline …
  const h = serverSrc.slice(serverSrc.indexOf('def _handle_update_analyze'), serverSrc.indexOf('def _handle_update_counts'));
  assert.match(h, /'no_baseline'/);
  assert.ok(!/apply_baseline/.test(h), 'Update Analysis now applies an attached baseline — update the help text (feature_needs.js update entry)');
  // … and an XER fills its "baseline" from the update's own planned (target) dates.
  assert.match(xerSrc, /planned_start = _dt\(t\.get\('target_start_date'\)\)/);
  assert.match(xerSrc, /data\.baseline_by_id\[task_code\]/);
  assert.match(f.files[0].note, /XER never carries its baseline/);
});
test('Consultant Review: the but-for file needs an XML update (server extension check)', () => {
  const h = serverSrc.slice(serverSrc.indexOf('def _handle_corrected_xml'), serverSrc.indexOf('def _handle_before_after'));
  assert.match(h, /endswith\('\.xml'\)/);
  assert.match(featureNeeds('compare').files[0].note, /XML update/);
});
test('Earned Value: a XER update is prompted for its baseline (evm.js) and the upload route exists', () => {
  const evm = read('ui', 'modules', 'evm.js');
  assert.match(evm, /isXer[\s\S]{0,200}hasBaseline/);
  assert.match(serverSrc, /'\/api\/baseline\/upload'/);
  assert.ok(featureNeeds('evm').files.some(x => x.k === 'optional' && /baseline/i.test(x.role)));
});
test('Earned Value: the E1 log picker is Excel (.xlsx / .xlsm)', () => {
  assert.match(appPy, /Excel Files \(\*\.xlsx;\*\.xlsm\)/);
  assert.ok(featureNeeds('evm').other.some(o => /\.xlsx/.test(o) && /\.xlsm/.test(o)));
});
test('Bad Weather needs the internet (geocode + weather are online calls)', () => {
  assert.match(serverSrc, /nominatim\.openstreetmap\.org/);
  assert.ok(featureNeeds('weather').other.some(o => /internet/i.test(o)));
});
test('Schedule Health is gated on contract milestones (audit.js gate B)', () => {
  assert.match(read('ui', 'modules', 'audit.js'), /Enter your contract milestones/);
  assert.ok(featureNeeds('audit').other.some(o => /contract milestones/i.test(o)));
});

// ── Static wiring guards: Help, menu and navigator all read this module ────
console.log('\nstatic wiring guards');
const helpSrc = read('ui', 'modules', 'help.js');
test('help.js renders the Feature guide from feature_needs.js (no private FEATURES list)', () => {
  assert.ok(/import[^;]*['"]\.\/feature_needs\.js['"]/.test(helpSrc), 'help.js does not import ./feature_needs.js');
  assert.ok(!/const FEATURES = \[/.test(helpSrc), 'help.js still has its own FEATURES list');
});
test('app.js uses needsHint in the Analysis menu and needsTooltip on the navigator', () => {
  assert.ok(/import[^;]*needsHint[^;]*['"]\.\/modules\/feature_needs\.js['"]/.test(appSrc), 'app.js does not import needsHint from ./modules/feature_needs.js');
  assert.ok(/needsHint\(it\[0\]\)/.test(appSrc), 'Analysis menu items do not show needsHint(it[0])');
  assert.ok(/needsTooltip\(/.test(appSrc), 'navigator items do not use needsTooltip()');
});

console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
