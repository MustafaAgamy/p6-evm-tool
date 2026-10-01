/**
 * AI Chat behaves like Claude (owner comment 15) — ui/modules/chat.js.
 * The question appears as your message, a thinking indicator, the answer is revealed formatted,
 * follow-up suggestions — and now: Stop while an answer is in flight, and Copy on every answer.
 * Run: node tests/js/test_chat_stop_copy.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { answerPlainText, sendButtonState, failNote, STOP_NOTE, COPY_BAR, revealPace } from '../../ui/modules/chat.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'ui', 'modules', 'chat.js'), 'utf8');
const fnBody = (name, until) => src.slice(src.indexOf(name), src.indexOf(until, src.indexOf(name) + name.length));

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

const ANSWER = {
  id: 'q01', question: 'Where do we stand?',
  verdict: 'Behind: about **60 working days** late.',
  pills: [{ text: 'SPI 0.66', tone: 'danger' }, { text: 'CPI 1.00', tone: 'neutral' }],
  sections: [
    { label: 'Time and cost', paras: ["You're **behind** on time.", 'Cost is derived from progress.'], table: null },
    { label: 'Which discipline is worst', paras: [],
      table: { cols: ['Discipline', 'Weight', 'Finish'], rows: [['Construction', '95%', '02-May-2027'], ['Design', '1%', '09-Feb-2027']], note: 'Weights by cost.' } },
    { label: 'Empty', paras: [], table: null },
  ],
  specific: [{ id: 's1', q: 'Are we ahead or behind?', headline: 'Behind — SPI 0.66.', body: ['Earned 41% vs 63% planned.'], advice: ['Chase the silos.'] }],
  measured: 'SPI = earned ÷ planned value.',
  actions: ['Recover the **Silos** chain.', 'Close the client inputs.'],
  evidence: [{ k: 'Data date', v: '19-Jul-2026' }, { k: 'Activities', v: '1,466' }],
  drilldowns: [{ to: 'q02', text: 'How do I recover?' }],
};

console.log('\nAI Chat — Stop and Copy');
test('the Send button becomes Stop while an answer is fetched or revealed', () => {
  assert.deepEqual(sendButtonState(false, false), { mode: 'send', glyph: '↑', label: 'Send' });
  assert.equal(sendButtonState(true, false).mode, 'stop');       // waiting for the engine
  assert.equal(sendButtonState(false, true).mode, 'stop');       // the answer is being revealed
  assert.equal(sendButtonState(true, true).label, 'Stop');
  assert.ok(src.includes("addEventListener('click', () => { if (BUSY || REVEAL) stopAnswer(); else send(); })"));
});
test('Stop cancels the request in flight and ends the reveal with the WHOLE answer', () => {
  const stop = fnBody('export function stopAnswer()', 'export function sendButtonState');
  assert.ok(stop.includes('ABORT.abort()') && stop.includes('REVEAL.finish()') && stop.includes('STOPPED = true'));
  assert.ok(src.includes('signal: ABORT ? ABORT.signal : undefined'));
  assert.equal((src.match(/signal: ABORT \? ABORT\.signal : undefined/g) || []).length, 2);   // JSON calls + the brain stream
  // every answer flow opens / closes the stoppable window through the one helper
  const set = fnBody('function setSendEnabled(on)', 'async function ask(');
  assert.ok(set.includes('if (on) endAnswer(); else beginAnswer();') && set.includes('refreshSendButton()'));
  for (const f of ['async function askV2(', 'async function ask(', 'async function askDashboard(', 'async function askCopilot(']) {
    const body = src.slice(src.indexOf(f), src.indexOf('\n}\n', src.indexOf(f)));
    assert.ok(body.includes('BUSY = true; setSendEnabled(false);') && body.includes('BUSY = false; setSendEnabled(true);'), f);
  }
});
test('a stopped request says so plainly; a real failure keeps its reason', () => {
  assert.equal(failNote({ name: 'AbortError', message: 'The user aborted a request.' }, false, 'x: '), STOP_NOTE);
  assert.equal(failNote(new Error('boom'), true, 'x: '), STOP_NOTE);
  assert.equal(failNote(new Error('boom'), false, 'The answer engine was unreachable: '), 'The answer engine was unreachable: boom');
  assert.match(STOP_NOTE, /^Stopped\./);
  assert.equal((src.match(/failNote\(e, STOPPED/g) || []).length, 5);
});
test('Copy gives the answer as clean text, tables tab-separated', () => {
  const t = answerPlainText(ANSWER);
  const lines = t.split('\n');
  assert.equal(lines[0], 'Where do we stand?');
  assert.equal(lines[1], 'Behind: about 60 working days late.');           // no ** markers
  assert.equal(lines[2], 'SPI 0.66 · CPI 1.00');
  assert.ok(t.includes("Time and cost\nYou're behind on time.\nCost is derived from progress."));
  assert.ok(t.includes('Discipline\tWeight\tFinish\nConstruction\t95%\t02-May-2027\nDesign\t1%\t09-Feb-2027\nWeights by cost.'));
  assert.ok(!t.includes('Empty'));                                          // a section with nothing is skipped
  assert.ok(t.includes("Q: Are we ahead or behind?\nBehind — SPI 0.66.\nEarned 41% vs 63% planned.\nWhat I'd do: Chase the silos."));
  assert.ok(t.includes('How this is measured: SPI = earned ÷ planned value.'));
  assert.ok(t.includes("What I'd do\n- Recover the Silos chain.\n- Close the client inputs."));
  assert.ok(t.endsWith('Data date 19-Jul-2026 · Activities 1,466'));
  assert.ok(!t.includes('**') && !t.includes('How do I recover?'));         // follow-up chips are not the answer
  assert.equal(answerPlainText(null), '');
  assert.equal(answerPlainText({ verdict: 'Only a verdict.' }), 'Only a verdict.');
});
test('every finished answer carries a Copy button; feedback is in the page', () => {
  assert.ok(COPY_BAR.includes('data-copy="1"') && COPY_BAR.includes('⧉ Copy'));
  assert.ok(src.includes("addCopyBar(card, answerPlainText(a), 'pv2-rv');"));           // the grounded answers
  assert.ok(src.includes("addCopyBar(bodyEl, raw.replace("));                           // the AI-brain answers
  assert.ok(src.includes("const cp = e.target.closest('[data-copy]'); if (cp) { copyAnswer(cp); return; }"));
  const copy = fnBody('async function copyText(text)', 'async function copyAnswer(btn)');
  assert.ok(copy.includes('navigator.clipboard.writeText(text)') && copy.includes("document.execCommand('copy')"));   // + fallback
  const ans = fnBody('async function copyAnswer(btn)', '\n}\n');
  assert.ok(ans.includes('✓ Copied') && ans.includes('Could not copy'));
  assert.ok(!/\balert\(/.test(ans));
});
test('the rest of the Claude-like flow is still there', () => {
  assert.ok(src.includes('<div class="pchat-who">You</div><div class="pchat-user">'));   // the question as your message
  assert.ok(src.includes('class="pchat-think"') && src.includes('Reading your schedule…'));   // thinking indicator
  assert.ok(src.includes('function revealV2(card, anchor)'));                            // the answer is revealed in steps
  assert.ok(src.includes('<span class="pv2-chiplbl">Drill in</span>'));                  // follow-up suggestions
  assert.ok(src.includes("if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }"));
});

test('it visibly analyses first, then writes the answer a few words at a time', () => {
  // thinking: one step at a time, slow enough to read, about 2.4 s for a normal answer
  const p = revealPace(4, 300, 6);
  assert.equal(p.stepMs, 560);
  assert.ok(p.settleMs > 0);
  assert.equal(revealPace(8, 300, 6).stepMs, 320);            // many steps: quicker, never a blur
  assert.equal(revealPace(0, 300, 6).stepMs, 0);              // nothing to think about → straight to the answer
  // writing: a few words per tick, a tick people can follow
  assert.ok(p.chunk >= 2 && p.tickMs >= 12 && p.tickMs <= 55);
  // a long answer writes faster, so the writing stays within about six seconds
  for (const [w, b] of [[60, 2], [300, 6], [1200, 10], [5000, 30]]) {
    const q = revealPace(4, w, b);
    const total = 4 * q.stepMs + q.settleMs + b * q.blockMs + Math.ceil(w / q.chunk) * q.tickMs;
    assert.ok(total <= 4 * 560 + 420 + 9000 + 5000 * 12 / 6 + 1, `${w} words → ${total} ms`);
    if (w <= 1200) assert.ok(total <= 12500, `${w} words → ${total} ms`);
  }
  assert.ok(revealPace(4, 5000, 30).chunk > revealPace(4, 60, 2).chunk);
  // wired: words are hidden then shown; Stop / finish shows them all
  const rv = src.slice(src.indexOf('function revealV2(card, anchor)'), src.indexOf('function libCount()'));
  assert.ok(rv.includes("wrapWords(u, w)") && rv.includes("classList.add('pv2-wp')"));
  assert.ok(rv.includes("card.querySelectorAll('.pv2-wp').forEach((x) => x.classList.remove('pv2-wp'))"));
  assert.ok(rv.includes('Analysing your P6 file…'));
  assert.ok(rv.includes('if (reducedMotion()) { followTo(anchor); return; }'));      // no animation when the PC asks for none
  assert.ok(src.includes('.pv2-wp{display:none}'));
});

console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
