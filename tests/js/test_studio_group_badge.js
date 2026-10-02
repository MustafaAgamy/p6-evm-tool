// Reporting Studio: a feature with only SOME results available said "No data" on its heading,
// as if nothing could be ticked. It now says how many are ready.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert';
import { fileURLToPath } from 'node:url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const src = fs.readFileSync(path.join(root, 'ui', 'modules', 'special.js'), 'utf8');
const a = src.indexOf('export function groupBadgeText');
const body = src.slice(a, src.indexOf('\n}', a) + 2).replace('export function', 'function');
const groupBadgeText = new Function(body + '\nreturn groupBadgeText;')();
const it = (n, av) => Array.from({ length: n }, () => ({ availability: av }));

let passed = 0;
function test(name, fn) { fn(); passed += 1; console.log('  ok  ' + name); }

test('a partly available feature says how many results are ready', () => {
  assert.equal(groupBadgeText([...it(18, 'ready'), ...it(3, 'no_data')], 'no_data'), '18 of 21 ready');
  assert.equal(groupBadgeText([...it(5, 'ready'), ...it(7, 'needs_input')], 'needs_input'), '5 of 12 ready');
});
test('fully ready, nothing ready: the plain badges', () => {
  assert.equal(groupBadgeText(it(19, 'ready'), 'ready'), 'Ready');
  assert.equal(groupBadgeText(it(7, 'needs_input'), 'needs_input'), 'Needs input');
  assert.equal(groupBadgeText(it(4, 'no_data'), 'no_data'), 'No data');
});
test('the heading uses it', () => {
  assert.ok(src.includes('${groupBadge(g.items, gavail)}'));
});
console.log(`\n${passed} passed`);
