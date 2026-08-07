/**
 * Unit tests for the in-app Help manual — pure helpers in ui/modules/help.js
 * and content invariants of ui/modules/help_content.js.
 * Run: node tests/js/test_help.js
 */
import assert from 'node:assert/strict';
import { MANUAL } from '../../ui/modules/help_content.js';
import { flattenTopics, topicById, filterTopics, topicHaystack, mdInline } from '../../ui/modules/help.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

console.log('\nMANUAL shape');
test('has a version and app name', () => {
  assert.ok(MANUAL.version, 'version missing');
  assert.ok(MANUAL.appName, 'appName missing');
});
test('has at least 4 groups', () => assert.ok(MANUAL.groups.length >= 4));
test('every group has a name and at least one topic', () => {
  for (const g of MANUAL.groups) {
    assert.ok(g.group, 'group name missing');
    assert.ok(Array.isArray(g.topics) && g.topics.length > 0, `group "${g.group}" has no topics`);
  }
});

console.log('\nflattenTopics');
const flat = flattenTopics(MANUAL);
test('flat count equals sum of group topics', () => {
  const sum = MANUAL.groups.reduce((a, g) => a + g.topics.length, 0);
  assert.equal(flat.length, sum);
});
test('every flat topic carries its group name', () =>
  flat.forEach(t => assert.ok(t.group, `topic ${t.id} missing group`)));

console.log('\ntopic invariants');
test('every topic has a unique id', () => {
  const ids = flat.map(t => t.id);
  assert.equal(new Set(ids).size, ids.length, 'duplicate topic id: ' + ids.filter((v, i) => ids.indexOf(v) !== i));
});
test('every topic has an id and a title', () =>
  flat.forEach(t => { assert.ok(t.id, 'missing id'); assert.ok(t.title, `topic ${t.id} missing title`); }));
test('every topic has real content (whatFor, how, or terms)', () =>
  flat.forEach(t => {
    const hasContent = t.whatFor || (t.how && t.how.length) || (t.terms && t.terms.length);
    assert.ok(hasContent, `topic ${t.id} has no content`);
  }));
test('every formula block that has a note also has a formula', () =>
  flat.forEach(t => (t.how || []).forEach(b => {
    if (b.note) assert.ok(b.formula || b.p, `topic ${t.id} note without formula/p`);
  })));

console.log('\ntopicById');
test('finds a known topic', () => assert.equal(topicById(MANUAL, 'spi').id, 'spi'));
test('returns null for an unknown id', () => assert.equal(topicById(MANUAL, 'no-such-topic'), null));
test('the manual includes the core EVM + audit topics', () => {
  for (const id of ['spi', 'cpi', 'planned-value', 'earned-value', 'finish-delay',
                    'dangling', 'float-analysis', 'calendar-audit', 'glossary']) {
    assert.ok(topicById(MANUAL, id), `missing expected topic: ${id}`);
  }
});

console.log('\nfilterTopics (search)');
test('empty query returns every group', () =>
  assert.equal(filterTopics(MANUAL, '').length, MANUAL.groups.length));
test('whitespace query returns every group', () =>
  assert.equal(filterTopics(MANUAL, '   ').length, MANUAL.groups.length));
test('a specific query narrows to matching topics', () => {
  const res = filterTopics(MANUAL, 'schedule performance');
  const ids = res.flatMap(g => g.topics.map(t => t.id));
  assert.ok(ids.includes('spi'), 'SPI should match "schedule performance"');
});
test('drops groups with no match', () => {
  const res = filterTopics(MANUAL, 'schedule performance index');
  res.forEach(g => assert.ok(g.topics.length > 0, 'empty group leaked through'));
});
test('nonsense query returns nothing', () =>
  assert.equal(filterTopics(MANUAL, 'zzzqqxnotarealword').length, 0));
test('search matches glossary term text', () => {
  const res = filterTopics(MANUAL, 'baseline');
  const ids = res.flatMap(g => g.topics.map(t => t.id));
  assert.ok(ids.length > 0, 'baseline should match at least one topic');
});

console.log('\ntopicHaystack');
test('haystack includes title and whatFor', () => {
  const t = topicById(MANUAL, 'spi');
  const hay = topicHaystack(t);
  assert.ok(hay.includes('spi'));
  assert.ok(hay === hay.toLowerCase(), 'haystack should be lowercased');
});

console.log('\nmdInline (safe inline formatting)');
test('escapes html', () => assert.equal(mdInline('a < b & c'), 'a &lt; b &amp; c'));
test('bold **x** → <b>', () => assert.equal(mdInline('a **bold** b'), 'a <b>bold</b> b'));
test('code `x` → <code>', () => assert.equal(mdInline('use `SPI` here'), 'use <code>SPI</code> here'));
test('no injection through bold', () =>
  assert.equal(mdInline('**<script>**'), '<b>&lt;script&gt;</b>'));
test('null-safe', () => assert.equal(mdInline(null), ''));

console.log(`\nHelp: ${passed} passed, ${failed} failed\n`);
if (failed) process.exit(1);
