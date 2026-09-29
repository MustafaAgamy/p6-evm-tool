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
  needsGroups, requiredFileCount, UPDATE_NO_BASELINE_ADVICE,
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
  assert.ok(navItems.length >= 19, `only ${navItems.length} navigator items parsed`);
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
test('Update Analysis: the screen and the server give the SAME advice as Help (SHELL-1)', () => {
  // The handler never reads an attached / saved baseline, so "attach a baseline on the EVM tab"
  // is advice that changes nothing. Screen, server and Help must all say: re-export the XML
  // with its baseline, or import the XER.
  const upd = read('ui', 'modules', 'update.js');
  const at = upd.indexOf("data.code === 'no_baseline'");
  assert.ok(at > 0, 'no_baseline branch not found in update.js');
  const block = upd.slice(at, upd.indexOf('return;', at));
  assert.ok(!/EVM|Earned Value/.test(block), 'update.js no_baseline text still sends the planner to the EVM tab');
  assert.ok(!/Attach a baseline/i.test(block), 'update.js no_baseline text still says "Attach a baseline"');
  assert.match(block, /UPDATE_NO_BASELINE_ADVICE/, 'update.js should show the shared UPDATE_NO_BASELINE_ADVICE');
  assert.match(upd, /import[^;]*UPDATE_NO_BASELINE_ADVICE[^;]*['"]\.\/feature_needs\.js['"]/);
  const h = serverSrc.slice(serverSrc.indexOf('def _handle_update_analyze'), serverSrc.indexOf('def _handle_update_counts'));
  const lit = (h.match(/'code': 'no_baseline'[\s\S]{0,160}?'error':\s*((?:'[^']*'\s*)+)\}/) || [])[1] || '';
  const err = [...lit.matchAll(/'([^']*)'/g)].map(x => x[1]).join('');   // Python joins adjacent literals
  assert.ok(err, 'no_baseline error text not found in _handle_update_analyze');
  assert.ok(!/Attach a baseline/i.test(err), `server no_baseline error still says "Attach a baseline": ${err}`);
  assert.match(err, /XML/); assert.match(err, /XER/);
  assert.match(UPDATE_NO_BASELINE_ADVICE, /Re-export[\s\S]*XML[\s\S]*baseline[\s\S]*XER/);
  assert.ok(featureNeeds('update').files[0].note.includes(UPDATE_NO_BASELINE_ADVICE),
    'the Help note should carry the same advice the screen shows');
});
test('Consultant Review: the but-for file needs an XML update (server extension check)', () => {
  const h = serverSrc.slice(serverSrc.indexOf('def _handle_corrected_xml'), serverSrc.indexOf('def _handle_before_after'));
  assert.match(h, /endswith\('\.xml'\)/);
  assert.match(featureNeeds('compare').files[0].note, /XML update/);
});
test('Consultant Review: the RESCHEDULED but-for file is read as XER or XML (SHELL-5)', () => {
  const impact = read('p6_compare', 'impact.py');
  const at = impact.indexOf('def before_after_from_paths');
  assert.match(impact.slice(at, at + 900), /corrected = parse_file\(corrected_path\)/);   // parse_file takes .xer and .xml
  assert.match(read('ui', 'modules', 'compare.js'),
    /loadRescheduledAndCompare\(\)\s*\{\s*const path = await window\.pywebview\.api\.choose_file\(\)/);   // the *.xml;*.xer picker
  const f = featureNeeds('compare').files[2];
  assert.match(f.role, /rescheduled in P6/);
  assert.equal(f.formats, 'XER or XML');
  const studio = featureNeeds('special').files[1].note;
  assert.ok(!/needs the rescheduled corrected file as XML/.test(studio), 'Reporting Studio note still says the rescheduled file must be XML');
  assert.match(studio, /XER or XML/);
});
test('Earned Value: a XER update is prompted for its baseline (evm.js) and the upload route exists', () => {
  const evm = read('ui', 'modules', 'evm.js');
  assert.match(evm, /isXer[\s\S]{0,200}hasBaseline/);
  assert.match(serverSrc, /'\/api\/baseline\/upload'/);
  assert.ok(featureNeeds('evm').files.some(x => x.k === 'optional' && /baseline/i.test(x.role)));
});
test('Earned Value: no baseline prompt / Attach button for an XML — Help says so (SHELL-2)', () => {
  const evm = read('ui', 'modules', 'evm.js');
  // The prompt returns early unless the file is an XER; the banner is null for every XML.
  assert.match(evm, /if \(!isXer \|\| hasBaseline \|\| _blPromptDone\) return;/,
    'maybePromptBaseline changed — if an XML can now get a baseline, update the evm entry in feature_needs.js');
  assert.match(evm, /return null;\s*\/\/ XML — baseline is embedded, nothing to attach/,
    'baselineBannerState changed — if an XML can now get an Attach button, update the evm entry in feature_needs.js');
  const bl = featureNeeds('evm').files.find(x => x.k === 'optional' && /baseline/i.test(x.role));
  assert.match(bl.role, /only for an XER update/);
  assert.ok(!/or an XML exported without its baseline/.test(bl.role), 'still claims the tool asks for a baseline for an XML');
  assert.match(bl.note, /cannot be attached to an XML/);
});
test('Knowledge Base: every file the Playbooks screen saves is listed (SHELL-7)', () => {
  const kb = read('ui', 'modules', 'knowledge.js');
  assert.match(kb, /\/api\/kb\/detailed-xer/);
  assert.match(kb, /\/api\/kb\/starter-xer/);
  assert.match(kb, /\/api\/kb\/excel/);
  assert.match(kb, /data-act="exp-pdf"/);
  const ex = featureNeeds('kb').exports.join(' | ');
  for (const w of ['PDF', 'Excel', 'Detailed baseline (XER', 'Skeleton baseline (XER)']) {
    assert.ok(ex.includes(w), `kb exports missing "${w}": ${ex}`);
  }
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
