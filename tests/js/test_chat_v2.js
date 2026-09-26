/**
 * Unit tests for the Offline AI Chat v2 display (the 15 merged questions) in ui/modules/chat.js:
 * the pure HTML builders answerV2Html / thinkingHtml / libraryHtml / clarifyHtml / welcomeHtml,
 * the numeric-column detector and the typed special-intent router.
 * Run: node tests/js/test_chat_v2.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  answerV2Html, thinkingHtml, libraryHtml, clarifyHtml, welcomeHtml, numericCols, copilotIntent,
} from '../../ui/modules/chat.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}
const count = (s, re) => (s.match(re) || []).length;

// A generic answer shaped like /api/chat/qa2 → answer (no real project names).
function sample(over) {
  return Object.assign({
    id: 'q01', question: 'Where do we stand?', group: 'Status & finish',
    covers: ['Are we ahead or behind?', 'Over or under budget?'],
    thinking: ['Read 1,466 activities from your P6 file (data date 19-Jul-2026)', 'Weighted 6 disciplines', 'Traced the driving chain (53 activities)'],
    verdict: 'Behind: about **60 working days** late.',
    pills: [{ text: 'SPI 0.66', tone: 'danger' }, { text: 'CPI 1.00', tone: 'neutral' }, { text: 'odd', tone: 'weird' }],
    sections: [
      { label: 'Time and cost', paras: ["You're **behind** on time.", 'Cost is derived from progress.'], table: null },
      { label: 'Which discipline is worst', paras: ['Construction carries the weight.'],
        table: { cols: ['Discipline', 'Weight', 'Done / planned', 'Finish'], rows: [['Construction', '95%', '40% / 61%', '02-May-2027'], ['Design', '1%', '0% / 74%', '10-Feb-2026']], note: 'Weighted by **value**.' } },
    ],
    specific: [
      { id: 't00q00', q: 'Are we ahead or behind? Give me SPI and CPI.', headline: 'Behind — SPI 0.66.', body: ['Earned 41% vs 63% planned.'], advice: ['Chase the driving chain.'], tool: null },
      { id: 't00q01', q: 'Run a what-if on the piling.', headline: 'Pick a lever.', body: ['The levers are…'], advice: [], tool: 'whatif' },
      { id: 't00q02', q: 'Covered elsewhere?', headline: 'Covered in the answer above.', body: [], advice: [], tool: null },
    ],
    focus: null, followup: null,
    measured: 'SPI = EV ÷ PV at the data date.',
    actions: ['Recover on the driving chain.', 'Report cost honestly.'],
    evidence: [{ k: 'SPI', v: '0.66' }, { k: 'Delay', v: '+60 wd' }],
    drilldowns: [{ to: 'q03', text: 'Why are we late?' }],
    tools: [{ cap: 'dashboard', label: 'Build the dashboard' }, { cap: 'bogus', label: 'Nope' }],
    also: [{ id: 'q02', q: 'When will we finish?' }],
  }, over || {});
}

// ── thinkingHtml ───────────────────────────────────────────────────────────
console.log('\nthinkingHtml');
test('no steps → empty string', () => { assert.equal(thinkingHtml([]), ''); assert.equal(thinkingHtml(null), ''); assert.equal(thinkingHtml(['', '  ']), ''); });
test('collapsed summary names the step count', () => {
  const h = thinkingHtml(['a', 'b', 'c']);
  assert.ok(h.startsWith('<details class="pv2-think"'));
  assert.ok(!/<details[^>]*\sopen/.test(h), 'final state is collapsed');
  assert.ok(h.includes('Analysed your file · 3 steps'));
  assert.equal(count(h, /class="pv2-step"/g), 3);
  assert.equal(count(h, /✓/g), 3);
});
test('one step is singular', () => assert.ok(thinkingHtml(['only']).includes('· 1 step<')));
test('steps are escaped', () => { const h = thinkingHtml(['<img src=x onerror=1>']); assert.ok(!h.includes('<img')); assert.ok(h.includes('&lt;img')); });

// ── answerV2Html ───────────────────────────────────────────────────────────
console.log('\nanswerV2Html');
test('empty / null answer does not throw and still ends with the grounded footer', () => {
  for (const a of [null, undefined, {}]) {
    const h = answerV2Html(a);
    assert.ok(h.includes('Grounded'));
    assert.ok(!h.includes('undefined') && !h.includes('[object'));
  }
});
test('thinking comes first', () => { const h = answerV2Html(sample()); assert.ok(h.indexOf('pv2-think') < h.indexOf('pv2-verdict')); });
test('verdict is strong and **bold** becomes <b>', () => {
  const h = answerV2Html(sample());
  assert.ok(h.includes('<p class="pv2-verdict pv2-rv">Behind: about <b>60 working days</b> late.</p>'));
});
test('pills carry their tone; an unknown tone falls back to neutral', () => {
  const h = answerV2Html(sample());
  assert.ok(h.includes('<span class="pv2-pill danger">SPI 0.66</span>'));
  assert.ok(h.includes('<span class="pv2-pill neutral">CPI 1.00</span>'));
  assert.ok(h.includes('<span class="pv2-pill neutral">odd</span>'));
});
test('covers box lists the topics', () => {
  const h = answerV2Html(sample());
  assert.ok(h.includes('Answers these topics'));
  assert.ok(h.includes('<li>Are we ahead or behind?</li>') && h.includes('<li>Over or under budget?</li>'));
  assert.ok(answerV2Html(sample({ covers: ['One'] })).includes('Answers this topic'));
});
test('sections keep their labels in order; every paragraph is its own reveal unit', () => {
  const h = answerV2Html(sample());
  assert.ok(h.indexOf('Time and cost') < h.indexOf('Which discipline is worst'));
  assert.ok(h.includes("<p class=\"pv2-rv\">You're <b>behind</b> on time.</p>"));
  assert.ok(h.includes('<p class="pv2-rv">Cost is derived from progress.</p>'));
});
test('a table renders whole (one reveal unit) with header, rows and note', () => {
  const h = answerV2Html(sample());
  assert.equal(count(h, /class="pv2-tablewrap pv2-rv"/g), 1);
  assert.ok(h.includes('<th scope="col">Discipline</th>'));
  assert.equal(count(h, /<tr>/g), 3);
  assert.ok(h.includes('<div class="pv2-tnote">Weighted by <b>value</b>.</div>'));
});
test('numeric columns right-align; label and date columns do not', () => {
  const h = answerV2Html(sample());
  assert.ok(h.includes('<th scope="col" class="n">Weight</th>'));
  assert.ok(h.includes('<td class="n">40% / 61%</td>'));
  assert.ok(h.includes('<td class="nw">02-May-2027</td>'), 'a date is left-aligned and never breaks at its hyphens');
  assert.ok(!/<td[^>]*class="n"[^>]*>02-May-2027/.test(h));
});
test('a section with no paragraphs and no table is dropped', () => {
  const h = answerV2Html(sample({ sections: [{ label: 'Empty', paras: [], table: null }] }));
  assert.ok(!h.includes('Empty'));
});
test('"Your questions, one by one" lists each sub-question with its headline', () => {
  const h = answerV2Html(sample());
  assert.ok(h.includes('Your questions, one by one — 3 from the library'));
  assert.equal(count(h, /<details class="pv2-sq/g), 2);          // two expandable rows
  assert.equal(count(h, /pv2-sq pv2-sq-flat/g), 1);              // nothing to expand → flat row
  assert.ok(h.includes('<span class="pv2-sqq">Are we ahead or behind? Give me SPI and CPI.</span><span class="pv2-sqa">Behind — SPI 0.66.</span>'));
  assert.ok(h.includes("<b>What I'd do:</b> Chase the driving chain."));
});
test('rows are keyboard-native <details>/<summary>', () => {
  const h = answerV2Html(sample());
  assert.equal(count(h, /<summary>/g), count(h, /<details/g));
});
test('a sub-question with a tool gets a real "Run it" button', () => {
  const h = answerV2Html(sample());
  assert.ok(/<button type="button" class="pv2-run" data-v2tool="whatif"[^>]*>Run it ▸<\/button>/.test(h));
  assert.equal(count(h, /class="pv2-run"/g), 1);
});
test('answer tools render as buttons; unknown caps are dropped', () => {
  const h = answerV2Html(sample({ tools: [{ cap: 'dashboard', label: 'Build the dashboard' }, { cap: 'tia', label: 'Run the time-impact analysis' }, { cap: 'report', label: "Manager's briefing" }, { cap: 'bogus', label: 'Nope' }] }));
  assert.ok(h.includes('data-v2tool="dashboard"') && h.includes('data-v2tool="tia"') && h.includes('data-v2tool="report"'));
  assert.ok(!h.includes('bogus') && !h.includes('Nope'));
});
test('measured, "What I\'d do", evidence, drill-in, also-related and footer follow in order', () => {
  const h = answerV2Html(sample());
  const order = ['Your questions, one by one', 'pv2-tools', 'How this is measured — from your P6', "What I'd do</div>", 'pv2-evi', 'Drill in', 'Also related', 'Grounded'];
  let last = -1;
  order.forEach((k) => { const i = h.indexOf(k); assert.ok(i > last, `"${k}" out of order`); last = i; });
  assert.ok(h.includes('<span class="pv2-chip"><b>SPI</b> 0.66</span>'));
  assert.ok(h.includes('data-v2ask="q03" data-q="Why are we late?"'));
  assert.ok(h.includes('data-v2ask="q02" data-q="When will we finish?"'));
});
test('kicker shows the group and the merged question', () => {
  const h = answerV2Html(sample());
  assert.ok(h.includes('<span class="g">Status &amp; finish</span> · Where do we stand?'));
});
test('kicker does not repeat the question when the user asked it in the same words', () => {
  const h = answerV2Html(sample(), { asked: 'where do we stand' });
  assert.ok(!h.includes(' · Where do we stand?'));
  assert.ok(h.includes('Status &amp; finish'));
});

console.log('\nanswerV2Html — focus & follow-ups');
test('focus: a highlighted "You asked" callout comes first with the direct answer', () => {
  const h = answerV2Html(sample({ focus: 't00q00' }));
  const callout = h.indexOf('pv2-focus pv2-rv');
  assert.ok(callout > h.indexOf('pv2-think') && callout < h.indexOf('pv2-verdict'));
  assert.ok(h.includes('<span class="k">You asked:</span> Are we ahead or behind? Give me SPI and CPI.'));
  assert.ok(h.includes('<p class="pv2-focus-h">Behind — SPI 0.66.</p>'));
  assert.ok(h.slice(callout, h.indexOf('pv2-verdict')).includes('Earned 41% vs 63% planned.'));
  assert.ok(h.includes('The full answer — Where do we stand?'));
});
test('focus: the matching sub-question is opened in the list, the others stay closed', () => {
  const h = answerV2Html(sample({ focus: 't00q00' }));
  assert.ok(/<details class="pv2-sq pv2-sq-focus" data-sid="t00q00" open>/.test(h));
  assert.ok(/<details class="pv2-sq" data-sid="t00q01">/.test(h));
});
test('focus on an unknown id → no callout', () => {
  const h = answerV2Html(sample({ focus: 'nope' }));
  assert.ok(!h.includes('You asked'));
  assert.ok(!/ open>/.test(h));
});
test("followup 'cause' leads with \"Here's why:\"", () => {
  const h = answerV2Html(sample({ followup: 'cause' }));
  assert.ok(h.includes("Here's why:"));
  assert.ok(h.indexOf("Here's why:") < h.indexOf('pv2-verdict'));
});
test("followup 'expand' leads with \"Here's the full picture:\"", () => {
  assert.ok(answerV2Html(sample({ followup: 'expand' })).includes("Here's the full picture:"));
  assert.ok(!answerV2Html(sample({ followup: 'topic' })).includes("Here's"));
});

console.log('\nanswerV2Html — safety');
test('every text field is escaped (no live markup from the payload)', () => {
  const bad = '<script>x()</script>';
  const h = answerV2Html(sample({
    verdict: bad, question: bad, group: bad, covers: [bad], pills: [{ text: bad, tone: 'danger' }],
    sections: [{ label: bad, paras: [bad], table: { cols: [bad], rows: [[bad]], note: bad } }],
    specific: [{ id: '"x', q: bad, headline: bad, body: [bad], advice: [bad] }],
    measured: bad, actions: [bad], evidence: [{ k: bad, v: bad }], drilldowns: [{ to: 'q"1', text: bad }], also: [{ id: 'q2', q: bad }],
  }));
  assert.ok(!h.includes('<script>'));
  assert.ok(!/data-v2ask="q"1"/.test(h));
});
test('the source never uses native alert / confirm / prompt (no-ops in WebView2)', () => {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const src = fs.readFileSync(path.join(here, '..', '..', 'ui', 'modules', 'chat.js'), 'utf8');
  assert.ok(!/\b(?:window\.)?(?:alert|confirm|prompt)\s*\(/.test(src));
});

// ── numericCols ─────────────────────────────────────────────────────────────
console.log('\nnumericCols');
test('first column is always a label', () => assert.deepEqual(numericCols(['#', 'x'], [['1', '2']]), [false, true]));
test('numbers, percents, signed working days and ranges are numeric', () => {
  assert.deepEqual(numericCols(['a', 'b', 'c', 'd', 'e'], [['r', '+60 wd (behind)', '370.4M', '−61', '+39 to +122 wd']]), [false, true, true, true, true]);
});
test('dates, ids and prose are not numeric; em-dash cells are ignored', () => {
  assert.deepEqual(numericCols(['a', 'b', 'c', 'd'], [['r', '02-May-2027', 'CM.1020', '—'], ['s', '10-Feb-2026', 'KD.1000', '5']]), [false, false, false, true]);
});

// ── libraryHtml ─────────────────────────────────────────────────────────────
console.log('\nlibraryHtml');
const LIB = {
  groups: ['Status & finish', 'Recovery'],
  questions: [
    { id: 'q01', group: 'Status & finish', q: 'Where do we stand — are we ahead or behind?', covers: ['Are we ahead or behind?'],
      originals: [{ id: 't00q00', q: 'Give me SPI and CPI.' }, { id: 't00q01', q: 'Plain-English status please.' }] },
    { id: 'q02', group: 'Status & finish', q: 'When will we finish?', covers: ['Contract & sectional dates', "What's slipping this window"],
      originals: [{ id: 't01q00', q: 'Are we going to hit the handover date?' }] },
    { id: 'q05', group: 'Recovery', q: 'How do I recover the delay?', covers: ['Crash, crew, shift'],
      originals: Array.from({ length: 9 }, (_, i) => ({ id: 't05q0' + i, q: 'Recovery option ' + i + ' with overtime' })) },
  ],
  counts: { questions: 3, originals: 12 },
};
test('groups in order, every question a real button with its topics line', () => {
  const h = libraryHtml(LIB, '');
  assert.ok(h.indexOf('Status &amp; finish') < h.indexOf('Recovery'));
  assert.equal(count(h, /<button type="button" class="pv2-lqb" data-v2ask="q0\d"/g), 3);
  assert.ok(h.includes("<span class=\"pv2-lqc\">Contract &amp; sectional dates · What's slipping this window</span>"));
});
test('a topic that just repeats the question falls back to the question count', () => {
  assert.ok(libraryHtml(LIB, '').includes('Answers 2 questions from the library'));
});
test('no role chips, role selector or status filter', () => {
  const h = libraryHtml(LIB, '');
  assert.ok(!/data-role|data-s="|pchat-roleselect|Ready today|Everyone/.test(h));
});
test('search matches the merged questions (all words, any order) and highlights them', () => {
  const h = libraryHtml(LIB, 'finish when');
  assert.equal(count(h, /class="pv2-lqb"/g), 1);
  assert.ok(h.includes('<mark>When</mark> will we <mark>finish</mark>?'));
});
test('search matches an original sub-question → shown under its parent, opening it in focus', () => {
  const h = libraryHtml(LIB, 'handover');
  assert.equal(count(h, /class="pv2-lqb"/g), 1);
  assert.ok(h.includes('data-v2ask="q02" data-focus="t01q00" data-q="Are we going to hit the handover date?"'));
  assert.ok(h.includes('<mark>handover</mark>'));
});
test('many matching sub-questions are capped with a "+N more" hint', () => {
  const h = libraryHtml(LIB, 'overtime');
  assert.equal(count(h, /class="pv2-lsub"/g), 6);
  assert.ok(h.includes('+ 3 more'));
});
test('no match → an honest message and an "ask it anyway" button', () => {
  const h = libraryHtml(LIB, 'zebra crossing');
  assert.ok(h.includes('Nothing in the library matches'));
  assert.ok(h.includes('data-asktext="zebra crossing"'));
});
test('search text is escaped and regex characters are safe', () => {
  const h = libraryHtml(LIB, '<b>(x');
  assert.ok(!h.includes('<b>(x'));
});
test('empty library does not throw', () => { assert.ok(libraryHtml(null, '').includes('empty')); });

// ── clarifyHtml ─────────────────────────────────────────────────────────────
console.log('\nclarifyHtml');
test('unmatched → "I\'m not sure which you mean — did you mean…?" with clickable chips', () => {
  const h = clarifyHtml([{ id: 'q01', q: 'Where do we stand?' }, { id: 'q05', q: 'How do I recover?' }]);
  assert.ok(h.includes("I'm not sure which you mean — did you mean one of these?"));
  assert.equal(count(h, /<button type="button" class="pv2-sug" data-v2ask="q0\d"/g), 2);
  assert.ok(h.includes('data-browse="1"'));
});
test('no suggestions → still helpful, with the library link and count', () => {
  const h = clarifyHtml([], { count: 15 });
  assert.ok(h.includes("I'm not sure which you mean"));
  assert.ok(h.includes('browse all 15 questions'));
});
test('an engine error is stated once, escaped', () => {
  assert.ok(clarifyHtml([], { error: '<oops>' }).includes('(&lt;oops&gt;)'));
});
test('related mode: a short chip row, or nothing', () => {
  assert.ok(clarifyHtml([{ id: 'q02', q: 'When?' }], { related: true }).includes('From your file I can also answer'));
  assert.equal(clarifyHtml([], { related: true }), '');
});

// ── welcomeHtml ─────────────────────────────────────────────────────────────
console.log('\nwelcomeHtml');
test('clean welcome: one "Browse all 15 questions" button, no cards, no role picker', () => {
  const h = welcomeHtml(15);
  assert.ok(/Browse all <span class="pchat-browsecount">15<\/span> questions/.test(h));
  assert.ok(!/pchat-sugcard|pchat-roleselect|Show questions for/.test(h));
});

// ── copilotIntent ───────────────────────────────────────────────────────────
console.log('\ncopilotIntent');
test('time impact → tia', () => {
  assert.equal(copilotIntent('Run a time impact analysis'), 'tia');
  assert.equal(copilotIntent("What's the time-impact of the late layout approval?"), 'tia');
  assert.equal(copilotIntent('show me the TIA'), 'tia');
});
test("manager's briefing → report", () => {
  assert.equal(copilotIntent("Give me a manager's briefing"), 'report');
  assert.equal(copilotIntent('Give me a manager’s briefing'), 'report');
  assert.equal(copilotIntent('prepare the weekly briefing'), 'report');
  assert.equal(copilotIntent('briefing'), 'report');
});
test('what-if → whatif', () => {
  assert.equal(copilotIntent('Run the what-if'), 'whatif');
  assert.equal(copilotIntent('what if we delay the piling by 10 days?'), 'whatif');
  assert.equal(copilotIntent('What if we add a crew to the raft?'), 'whatif');
  assert.equal(copilotIntent('what-if'), 'whatif');
});
test('ordinary questions go to the answer engine', () => {
  for (const q of ['Why are we late?', 'Are we going to finish on time?', 'Is the briefing date at risk?', 'What is our float?', '', null]) {
    assert.equal(copilotIntent(q), null, String(q));
  }
});

console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
