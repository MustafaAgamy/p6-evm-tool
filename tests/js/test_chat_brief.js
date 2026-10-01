/**
 * AI Chat — every answer opens with a short plain brief (owner comment 14): the problem, where it
 * is, why, what to do. The long analysis is folded under "Show the full analysis".
 * ui/modules/chat.js: briefOf / briefHtml / answerV2Html / answerPlainText.
 * Run: node tests/js/test_chat_brief.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { briefOf, briefHtml, answerV2Html, answerPlainText, BRIEF_HEADS } from '../../ui/modules/chat.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'ui', 'modules', 'chat.js'), 'utf8');

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}
const count = (s, re) => (s.match(re) || []).length;

const BRIEF = {
  problem: 'The project is **60 working days late**. 41% of the work is done.',
  where: ['The critical path starts at **Drilling For Piles** (CONS.PL.S9.1000), in Phase C, Silo 9.', '**Construction Works** is 95% of the project.'],
  why: ['The first critical activity has not started. Everything after it waits.'],
  do: ['Start **Drilling For Piles** (CONS.PL.S9.1000) now.', 'Write to the client today about **Layout Approval** (INP.EMP.1010).'],
};
const ANSWER = {
  id: 'q01', question: 'Where do we stand?', group: 'Status & finish',
  thinking: ['Read 1,466 activities', 'Traced the critical path'],
  verdict: 'Behind: about 60 working days late.',
  pills: [{ text: 'SPI 0.66', tone: 'danger' }],
  covers: ['Are we ahead or behind?'],
  sections: [{ label: 'Time and cost', paras: ['You are behind.'], table: { cols: ['Discipline', 'Weight'], rows: [['Construction', '95%']] } }],
  specific: [{ id: 's1', q: 'Are we ahead or behind?', headline: 'Behind.', body: ['Earned 41%.'], advice: [] }],
  measured: 'SPI = EV ÷ PV.', actions: ['Report the position.'], evidence: [{ k: 'SPI', v: '0.66' }],
  drilldowns: [{ to: 'q05', text: 'How do I recover the delay?' }], tools: [{ cap: 'dashboard', label: 'Build the dashboard' }],
  brief: BRIEF,
};

console.log('\nAI Chat — the short plain answer first');
test('a brief needs a problem and at least one action; anything less falls back to the old layout', () => {
  assert.deepEqual(briefOf(ANSWER), BRIEF);
  assert.equal(briefOf({ brief: { problem: 'x', where: [], why: [], do: [] } }), null);
  assert.equal(briefOf({ brief: { where: ['a'], do: ['b'] } }), null);
  assert.equal(briefOf({}), null);
  assert.equal(briefOf(null), null);
  assert.deepEqual(briefOf({ brief: { problem: 'p', where: ['', null, 'w'], do: ['d'] } }), { problem: 'p', where: ['w'], why: [], do: ['d'] });
});
test('four labelled parts, in the order a planner reads them', () => {
  assert.deepEqual(BRIEF_HEADS, { problem: 'The problem', where: 'Where it is', why: 'Why', do: 'What to do' });
  const h = briefHtml(briefOf(ANSWER));
  const order = ['The problem', 'Where it is', 'Why', 'What to do'].map((t) => h.indexOf(`>${t}<`));
  assert.ok(order.every((i) => i > 0) && order.join() === [...order].sort((a, b) => a - b).join(), order.join());
  assert.equal(count(h, /<li class="pv2-rv">/g), 5);                       // 2 where + 1 why + 2 actions
  assert.ok(h.includes('<ol class="pv2-bl">') && count(h, /<ul class="pv2-bl">/g) === 2);   // actions are numbered
  assert.ok(h.includes('<b>60 working days late</b>') && h.includes('<b>Drilling For Piles</b> (CONS.PL.S9.1000)'));
  // a part with nothing to say is not shown as an empty box
  const noWhy = briefHtml({ problem: 'p', where: ['w'], why: [], do: ['d'] });
  assert.ok(!noWhy.includes('>Why<') && noWhy.includes('>Where it is<'));
});
test('the answer opens with the brief; the long analysis is folded underneath', () => {
  const h = answerV2Html(ANSWER, {});
  const iBrief = h.indexOf('class="pv2-brief"'), iMore = h.indexOf('<details class="pv2-more">'), iVerdict = h.indexOf('pv2-verdict');
  assert.ok(iBrief > 0 && iMore > iBrief && iVerdict > iMore, [iBrief, iMore, iVerdict].join());
  assert.ok(h.includes('Show the full analysis'));
  const end = h.lastIndexOf('</details>');                                  // the fold closes last (sub-questions nest inside)
  const more = h.slice(iMore, end);
  for (const part of ['pv2-verdict', 'pv2-pills', 'pv2-covers', 'pv2-sec', 'pv2-spec', 'pv2-measured', 'pv2-evi', 'More I would do']) {
    assert.ok(more.includes(part), part);                                   // nothing of the analysis is lost
  }
  // outside the fold: the tool button and the follow-up questions stay one click away
  const outside = h.slice(0, iMore) + h.slice(end);
  assert.ok(outside.includes('data-v2tool="dashboard"') && outside.includes('data-v2ask="q05"'));
  assert.ok(!outside.includes('pv2-pills'));                                // the shorthand chips are not on top any more
});
test('a sub-question the planner clicked opens the full analysis for him', () => {
  const h = answerV2Html({ ...ANSWER, focus: 's1' }, {});
  assert.ok(h.includes('<details class="pv2-more" open>') && h.includes('You asked:'));
});
test('an answer without a brief reads exactly as before', () => {
  const { brief, ...old } = ANSWER;
  const h = answerV2Html(old, {});
  assert.ok(!h.includes('pv2-brief') && !h.includes('pv2-more'));
  assert.ok(h.indexOf('pv2-verdict') < h.indexOf('pv2-pills') && h.includes("What I'd do"));
});
test('only what is on screen is written out; list lines flow in like paragraphs', () => {
  const rv = src.slice(src.indexOf('function revealV2(card, anchor)'), src.indexOf('function libCount()'));
  assert.ok(rv.includes("filter((u) => !u.closest('details.pv2-more:not([open])'))"));
  assert.ok(rv.includes("u.tagName === 'P' || u.tagName === 'LI'"));
});
test('Copy gives the short answer first, then the full analysis', () => {
  const t = answerPlainText(ANSWER);
  const lines = t.split('\n');
  assert.equal(lines[0], 'Where do we stand?');
  assert.equal(lines[1], 'THE PROBLEM');
  assert.equal(lines[2], 'The project is 60 working days late. 41% of the work is done.');
  assert.ok(t.includes('WHERE IT IS\n- The critical path starts at Drilling For Piles (CONS.PL.S9.1000), in Phase C, Silo 9.'));
  assert.ok(t.includes('WHY\n- The first critical activity has not started.'));
  assert.ok(t.includes('WHAT TO DO\n1. Start Drilling For Piles (CONS.PL.S9.1000) now.\n2. Write to the client today about Layout Approval (INP.EMP.1010).'));
  assert.ok(t.indexOf('THE FULL ANALYSIS') > t.indexOf('WHAT TO DO') && t.indexOf('Behind: about 60 working days late.') > t.indexOf('THE FULL ANALYSIS'));
  assert.ok(t.includes('Discipline\tWeight\nConstruction\t95%') && !t.includes('**'));
});

console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
