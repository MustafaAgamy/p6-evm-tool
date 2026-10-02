/**
 * Baseline Narrative ▸ activity codes in order (owner comment 45) — ui/modules/narrative.js.
 * The planner picks e.g. "Type of Works" then "Type of Civil Works" for a Sequence of Work
 * analysis and can swap them (⇄) so "Type of Civil Works" comes 1st, and move whole analyses
 * up / down (▲ ▼) — in the setup panel and in the guided (chat) setup. The Scope list keeps its
 * own ▲ ▼. The report (p6_narrative/seqflow.py) reads the codes in the order given.
 * Run: node tests/js/test_narrative_code_order.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { swapSeqCodes, moveItem } from '../../ui/modules/narrative.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'ui', 'modules', 'narrative.js'), 'utf8');

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

const L = [{ codes: ['Type of Works', 'Type of Civil Works'] }, { codes: ['Silos Area Name'] }, { codes: ['Phase', 'Main WBS'] }];

test('⇄ makes the 2nd code 1st and the 1st code 2nd — only on that analysis', () => {
  const out = swapSeqCodes(L, 0);
  assert.deepEqual(out[0].codes, ['Type of Civil Works', 'Type of Works']);
  assert.deepEqual(out[2].codes, ['Phase', 'Main WBS']);
  assert.deepEqual(L[0].codes, ['Type of Works', 'Type of Civil Works'], 'the input is not changed');
  assert.deepEqual(swapSeqCodes(swapSeqCodes(L, 0), 0), L, 'swapping twice restores it');
  assert.deepEqual(swapSeqCodes(L, 1), L, 'a single-code analysis has nothing to swap');
});

test('▲ ▼ move a whole analysis; the ends stay put', () => {
  assert.deepEqual(moveItem(L, 2, 'up').map(a => a.codes[0]), ['Type of Works', 'Phase', 'Silos Area Name']);
  assert.deepEqual(moveItem(L, 0, 'down').map(a => a.codes[0]), ['Silos Area Name', 'Type of Works', 'Phase']);
  assert.deepEqual(moveItem(L, 0, 'up'), L);
  assert.deepEqual(moveItem(L, 2, 'down'), L);
});

test('both setups show ⇄ between the two codes and ▲ ▼ on every analysis, wired to the helpers', () => {
  // setup panel
  assert.ok(src.includes('data-seqswap="${i}"') && src.includes('data-seqmv="up"') && src.includes('data-seqmv="down"'));
  assert.ok(src.includes('seqAnalyses = swapSeqCodes(seqAnalyses, +b.dataset.seqswap); reSeq();'));
  assert.ok(src.includes("seqAnalyses = moveItem(seqAnalyses, +b.dataset.i, b.dataset.seqmv); reSeq();"));
  // guided (chat) setup
  assert.ok(src.includes('data-sqswap="${i}"') && src.includes('data-sqmv="up"') && src.includes('data-sqmv="down"'));
  assert.ok(src.includes('setSeq(swapSeqCodes(curSeq(), +b.dataset.sqswap))'));
  assert.ok(src.includes('setSeq(moveItem(curSeq(), +b.dataset.i, b.dataset.sqmv))'));
  // the Scope list keeps its own order arrows
  assert.ok(src.includes('data-mv="up"') && src.includes('data-smv="up"'));
});

console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
