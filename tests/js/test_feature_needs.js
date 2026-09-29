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
  needsGroups, requiredFileCount, UPDATE_NO_BASELINE_ADVICE, ATTACHED_BASELINE_PREFILL,
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
test('Update Analysis: baseline inside the file, else the one attached for it (XER or XML)', () => {
  const f = featureNeeds('update');
  assert.equal(f.files.filter(x => x.k === 'p6').length, 1);                 // one imported update …
  const bl = f.files.find(x => x.k === 'optional' && /baseline/i.test(x.role));
  assert.ok(bl, 'the attachable baseline is listed');                         // … + its attachable baseline
  assert.equal(bl.formats, 'XER or XML');
  // server: re-reads the update through the ONE baseline resolver (embedded > attached > self) …
  const h = serverSrc.slice(serverSrc.indexOf('def _handle_update_analyze'), serverSrc.indexOf('def _handle_update_counts'));
  assert.match(h, /_schedule_for\(curr_path, body\)/, 'Update Analysis no longer reads the attached baseline — update the help text');
  assert.match(h, /'no_baseline'/);
  const helper = serverSrc.slice(serverSrc.indexOf('def _schedule_for'), serverSrc.indexOf('class ', serverSrc.indexOf('def _schedule_for')));
  assert.match(helper, /attached_baseline_for\(/);
  assert.match(read('p6_evm', 'baseline.py'), /def resolve_baseline[\s\S]*'embedded'[\s\S]*'attached'/);
  // … and refuses a 'self' baseline (the update's own planned dates), XER or XML alike.
  const ua = read('p6_update', 'analysis.py');
  assert.match(ua, /has_baseline = \(src in \('embedded', 'attached'\)\)/);
  assert.match(xerSrc, /data\.baseline_source = 'self'/);
  assert.match(read('p6_evm', 'parser.py'), /data\.baseline_source = 'self'/);
  assert.match(f.files[0].note, /a normal XER update export does not, nor does an XML exported without it/);
  // An XER that includes its baseline project is read like the XML (p6_evm/xer.py, finding P1).
  assert.match(f.files[0].note, /so does an XER that includes the baseline project/);
  assert.match(xerSrc, /def _read_embedded_baseline/);
  assert.ok(!/not used here/.test(JSON.stringify(f)), 'Help still says the attached baseline is not used here');
});
test('Reporting Studio Update items follow the Update Analysis screen rule (R1 F1) and Help says so', () => {
  const prov = read('p6_special', 'providers', 'update.py');
  assert.match(prov, /return 'needs_input' if _no_baseline\(ctx\) else 'ready'/);
  assert.match(read('p6_special', 'feature_reports.py'), /update_has_baseline\(data\)/);
  assert.match(read('p6_update', 'analysis.py'), /has_baseline = update_has_baseline\(data\)/);
  assert.match(read('ui', 'modules', 'special.js'), /i\.availability !== 'ready' && i\.note/, 'the Studio no longer shows why an item is not ready');
  assert.match(featureNeeds('special').files[1].note, /Update Analysis results follow the Update Analysis screen[\s\S]*never measured against its own Planned dates/);
});
test('every screen that shows a baseline-derived value marks it approx under ONE rule (R1 F2)', () => {
  const ov = read('ui', 'modules', 'overview.js');
  assert.match(ov, /baselineApprox\(result, state\.currentXmlPath\)/);
  assert.match(ov, /Baseline finish\$\{ax\}/); assert.match(ov, /Overall planned\$\{ax\}/);
  assert.match(ov, /WBS_BL_COLS = new Set\(\['baseline_start', 'baseline_finish', 'planned', 'delay'\]\)/);
  const cal = read('ui', 'modules', 'calendar.js');
  assert.match(cal, /d\.baseline_approx \? 'Baseline \(approx\)' : 'plan of record'/);
  assert.match(read('p6_calendar', 'report.py'), /'Baseline \(approx\)' if d\.get\('baseline_approx'\) else 'plan of record'/);
  assert.match(read('ui', 'modules', 'critpath.js'), /BL finish\$\{_ax\(role\)\}/);
  assert.match(read('ui', 'modules', 'period.js'), /Baseline\$\{ax\}<\/th>/);
  assert.match(read('ui', 'modules', 'evm.js'), /noBaseline \? 'weighted table · approx' : 'weighted table'/);
});
test('Update Analysis: the screen and the server give the SAME advice as Help (SHELL-1)', () => {
  // The handler reads the baseline attached for the update (here or on Earned Value), so screen,
  // server and Help all say: attach the baseline (XER or XML), or re-export the XML with it.
  const upd = read('ui', 'modules', 'update.js');
  const at = upd.indexOf("data.code === 'no_baseline'");
  assert.ok(at > 0, 'no_baseline branch not found in update.js');
  const fnAt = upd.indexOf('function _noBaseline(');
  assert.ok(fnAt > 0, 'update.js _noBaseline (the no-baseline state) not found');
  const block = upd.slice(fnAt, upd.indexOf('\n}\n', fnAt));
  assert.match(block, /UPDATE_NO_BASELINE_ADVICE/, 'update.js should show the shared UPDATE_NO_BASELINE_ADVICE');
  assert.match(block, /ATTACH_BASELINE_LABEL/, 'the no-baseline state should offer the Attach button');
  assert.match(block, /attachBaselineFile\(\)/);
  assert.match(upd, /import[^;]*UPDATE_NO_BASELINE_ADVICE[^;]*['"]\.\/feature_needs\.js['"]/);
  const h = serverSrc.slice(serverSrc.indexOf('def _handle_update_analyze'), serverSrc.indexOf('def _handle_update_counts'));
  const lit = (h.match(/'code': 'no_baseline'[\s\S]{0,400}?'error':\s*((?:'[^']*'\s*)+)\}/) || [])[1] || '';
  const err = [...lit.matchAll(/'([^']*)'/g)].map(x => x[1]).join('');   // Python joins adjacent literals
  assert.ok(err, 'no_baseline error text not found in _handle_update_analyze');
  assert.match(err, /Attach the baseline \(XER or XML\)/);
  assert.match(err, /XML/); assert.match(err, /every feature/);
  assert.ok(!/import the update as an XER/i.test(err), 'server still sends the planner to the XER (its own dates)');
  assert.match(UPDATE_NO_BASELINE_ADVICE, /Attach the baseline \(XER or XML\)[\s\S]*re-export[\s\S]*XML[\s\S]*baseline/);
  assert.ok(!/import the update as an XER/i.test(UPDATE_NO_BASELINE_ADVICE));
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
test('Earned Value: an update without its baseline (XER or XML) is prompted for it and the upload route exists', () => {
  const evm = read('ui', 'modules', 'evm.js');
  assert.match(evm, /needsBaseline[\s\S]{0,200}hasBaseline/);
  assert.match(serverSrc, /'\/api\/baseline\/upload'/);
  assert.ok(featureNeeds('evm').files.some(x => x.k === 'optional' && /baseline/i.test(x.role)));
});
test('Earned Value: the prompt / Attach button follow baseline_source, so an XML without its baseline gets them too', () => {
  const evm = read('ui', 'modules', 'evm.js');
  // The prompt returns early only when the baseline is not 'self' (embedded or attached), or
  // when no baseline is assigned in P6 (its own dates ARE its baseline — review F3) …
  assert.match(evm, /const needsBaseline = baselineSource\(result, state\.currentXmlPath\) === 'self' && baselineExpected\(result\);/);
  assert.match(evm, /if \(src === 'self' && expected === false\)/, 'the no-baseline-assigned banner is gone — update Help');
  assert.match(read('p6_evm', 'baseline.py'), /'baseline_expected': info\.get\('expected'\)/);
  assert.match(evm, /if \(!needsBaseline \|\| hasBaseline \|\| _blPromptDone\) return;/,
    'maybePromptBaseline changed — update the evm entry in feature_needs.js');
  // … and the banner is null only for a baseline embedded in the file.
  assert.match(evm, /return null;\s*\/\/ embedded — the file carries its baseline, nothing to attach/,
    'baselineBannerState changed — update the evm entry in feature_needs.js');
  // the server accepts a baseline for any update that doesn't embed one (XER or XML) …
  const up = serverSrc.slice(serverSrc.indexOf('def _handle_baseline_upload'), serverSrc.indexOf('def _handle_baseline_clear'));
  assert.match(up, /baseline_source', None\) == 'embedded'/);
  assert.ok(!/endswith\('\.xer'\)/.test(up), 'baseline upload is XER-only again');
  // … and Help says so.
  const bl = featureNeeds('evm').files.find(x => x.k === 'optional' && /baseline/i.test(x.role));
  assert.match(bl.role, /an XML exported without its baseline project/);
  assert.ok(!/only for an XER update/.test(bl.role), 'Help still says the baseline is only for an XER');
  assert.ok(!/cannot be attached to an XML/.test(bl.note), 'Help still says a baseline cannot be attached to an XML');
  assert.match(bl.note, /remembered for this update and used by every feature/);
  assert.match(bl.note, /no baseline assigned in P6[\s\S]*own Planned dates are its baseline/);
});
test('No baseline assigned in P6: Update Analysis reads its own dates, Help says so (review F3)', () => {
  assert.match(read('p6_update', 'analysis.py'), /if src == 'self' and not expected:\s+has_baseline = True/);
  assert.match(featureNeeds('update').files[0].note, /no baseline assigned in P6[\s\S]*own Planned dates/);
});
test('Previous update inherits the current update’s baseline, inside the XML or attached (review F1)', () => {
  const h = serverSrc.slice(serverSrc.indexOf('def _handle_period_compare'), serverSrc.indexOf('def _handle_period_previous'));
  assert.match(h, /inherit_baseline\(data, curr\)/);
  const c = serverSrc.slice(serverSrc.indexOf('def _handle_critpath_analyze'), serverSrc.indexOf('def _handle_critpath_report'));
  assert.match(c, /inherit_baseline\(schedules\[role\], schedules\['current'\]\)/);
  assert.match(read('p6_special', 'context.py'), /inherit_baseline\(prev, self\.parsed\(\)\)/);
  for (const id of ['period', 'critpath']) {
    const f = featureNeeds(id).files.find(x => /Previous update/.test(x.role));
    assert.match(f.note, /current update’s baseline — the one inside the XML or the one attached/);
  }
});
test('Attach buttons say "XER or XML" (Earned Value, Update Analysis, Reporting Studio)', () => {
  const blj = read('ui', 'modules', 'baseline.js');
  assert.match(blj, /ATTACH_BASELINE_LABEL = '📎 Attach baseline \(XER or XML\)'/);
  const evm = read('ui', 'modules', 'evm.js');
  assert.ok(!/Attach baseline XER'|Import baseline XER/.test(evm), 'evm.js still labels the attach button XER-only');
  assert.match(evm, /attach: ATTACH_BASELINE_LABEL/);
  assert.match(read('p6_special', 'providers', 'twofile.py'), /'label': 'Baseline \(XER or XML\)'/);
});
test('Baseline slots start with the baseline attached to this update (R3 F9)', () => {
  const blj = read('ui', 'modules', 'baseline.js');
  assert.match(blj, /export function attachedBaselineSlot\(result\)/);
  assert.match(blj, /ATTACHED_BASELINE_TAG = 'attached to this update'/);
  assert.match(ATTACHED_BASELINE_PREFILL, /attached to this update/);
  assert.match(ATTACHED_BASELINE_PREFILL, /Change button picks another file/);
  const cpa = read('ui', 'modules', 'critpath.js');
  assert.match(cpa, /attachedBaselineSlot\(state\.currentResult\)/);
  assert.match(cpa, /payload\[`\$\{role\}_path`\] = _slotPath\(role\)/, 'critpath does not send the attached baseline');
  assert.match(cpa, /every\(r => _slotPath\(r\)\)/, 'critpath Run stays disabled with the attached baseline');
  const cmp = read('ui', 'modules', 'compare.js');
  assert.match(cmp, /function _reviewBaseline\(\)[\s\S]{0,400}attachedBaselineSlot\(state\.currentResult\)/);
  assert.match(cmp, /const bl = _reviewBaseline\(\);[\s\S]{0,200}state\.compareBaselinePath = path;/);
  const sr = read('ui', 'modules', 'special.js');
  assert.match(sr, /inputs: effInputs\(\)/);
  assert.match(sr, /api\('api\/special\/catalog', \{ snapshot_id: state\.currentSnapshotId, inputs: effInputs\(\) \}\)/);
  assert.equal(featureNeeds('critpath').files.find(f => /^Baseline/.test(f.role)).note, ATTACHED_BASELINE_PREFILL);
  assert.equal(featureNeeds('compare').files.find(f => /^Baseline/.test(f.role)).note, ATTACHED_BASELINE_PREFILL);
  assert.match(featureNeeds('special').files[1].note, /comparison item’s Baseline is filled in with that attached baseline/);
});
test('Knowledge Base: every file the screen saves is listed (SHELL-7)', () => {
  const kb = read('ui', 'modules', 'database.js');
  assert.match(kb, /example_with_gaps/);                                   // exportExample(…, gappy)
  assert.match(kb, /clean_baseline/);                                      // exportExample(…, clean)
  assert.match(kb, /function downloadContributed[\s\S]{0,120}filename\.split\('\.'\)\.pop\(\)/);   // own format
  assert.match(kb, /\/api\/kb\/raw\/download/);                            // raw learned project
  assert.match(kb, /\/api\/kb\/starter-xml/);
  assert.match(kb, /\/api\/kb\/knowledge\/export/);
  assert.match(read('p6_kb', 'pattern_learning.py'), /ext = os\.path\.splitext\(src_path\)\[1\]\.lower\(\)/);  // raw kept as learned
  const ex = featureNeeds('kb').exports.join(' | ');
  for (const w of ['Starter baseline', 'with typical gaps', 'Clean reference baseline', 'Contributed schedules', 'learned project', 'Knowledge file (.json)']) {
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
