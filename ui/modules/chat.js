// Offline AI Chat — a Claude-style chat that answers as a senior planning manager,
// grounded in the open project's real analysis and running on the user's PC.
//
// The screen: a slide-in library of the 15 merged questions (grouped, searchable —
// the search also finds the 182 original library questions inside them), a thread
// and a composer. A clicked question is answered by /api/chat/qa2; typed text goes
// through the special intents (dashboard / what-if / time impact / manager's
// briefing) and then /api/chat/ask2, which routes it to the right merged answer and
// sub-question and remembers the thread (last_qid). Only when nothing matches does
// the chat fall back to the optional offline AI brain — or, without it, ask
// "did you mean…?" with clickable suggestions. Every v2 answer is rendered like a
// thinking assistant: the analysis steps first, then the answer revealed section by
// section (instant under prefers-reduced-motion).
//
// All styling is self-contained here (injected <style> blocks) and reads the
// app's appearance tokens (--card-bg / --border / --text / --accent / --muted),
// so it themes correctly in all six looks with no edits to style.css.
import { state } from './state.js';
import { escapeHtml, fmtDate } from './format.js';
import { importFile } from './api.js';

let LIB2 = null;        // the 15 merged questions {groups, questions[{id,group,q,covers,originals}], counts}
let BRAIN = null;       // brain status
let BUSY = false;
let POLL = null;        // setup status-poll timer
let LAST_QID = null;    // merged question of the last v2 answer — sent as last_qid so "why?" continues the thread
let REVEAL = null;      // the in-flight progressive reveal {card, finish()}
const V2_MODE = 'planning';   // the role split is gone — every answer uses the one planning-manager voice

const api = (path) => `http://localhost:${state.serverPort}${path}`;

async function getJSON(path) {
  const r = await fetch(api(path));
  return r.json();
}
async function postJSON(path, body) {
  const r = await fetch(api(path), {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}

// ── one-time CSS (uses the app's appearance tokens) ──────────────────────────
function ensureCss() {
  if (document.getElementById('pchat-css')) return;
  const s = document.createElement('style');
  s.id = 'pchat-css';
  s.textContent = `
  .pchat{display:flex;flex-direction:column;gap:14px}
  .pchat-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
  .pchat-mark{width:38px;height:38px;border-radius:10px;background:linear-gradient(150deg,var(--accent),var(--accent-dark));display:grid;place-items:center;color:#fff;font-size:18px}
  .pchat-head h2{margin:0;font-size:17px;font-weight:750;color:var(--text)}
  .pchat-head .sub{color:var(--muted);font-size:12.5px}
  .pchat-head .spring{flex:1}
  .pchat-pill{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;font-weight:650;padding:5px 10px;border-radius:999px;border:1px solid var(--border);background:var(--card-bg);color:var(--muted)}
  .pchat-pill .dot{width:7px;height:7px;border-radius:50%;background:var(--muted)}
  .pchat-pill.ready{color:#1f8a5b;border-color:#cfe9d8}.pchat-pill.ready .dot{background:#1f8a5b}
  .pchat-pill.off{color:#b5761f;border-color:#f0dcb6}.pchat-pill.off .dot{background:#c98a1e}

  .pchat-setup{border:1px solid var(--border);background:var(--card-bg);border-radius:12px;padding:14px 16px}
  .pchat-setup h3{margin:0 0 4px;font-size:14.5px;color:var(--text)}
  .pchat-setup p{margin:0 0 10px;color:var(--ink-soft);font-size:13px}
  .pchat-setup .row{display:flex;gap:9px;flex-wrap:wrap;align-items:center}
  .pchat-btn{border:1px solid var(--accent);background:var(--accent);color:#fff;font-weight:700;font-size:12.5px;border-radius:9px;padding:8px 14px;cursor:pointer;font-family:inherit}
  .pchat-btn:hover{background:var(--accent-dark)}
  .pchat-btn.ghost{background:transparent;color:var(--accent-dark);border-color:var(--border)}
  .pchat-btn:disabled{opacity:.55;cursor:default}
  .pchat-setup code{background:var(--hair);padding:1px 6px;border-radius:5px;font-size:12px}

  .pchat-thread{border:1px solid var(--border);background:var(--card-bg);border-radius:12px;padding:16px;min-height:220px;max-height:56vh;overflow:auto;display:flex;flex-direction:column;gap:20px}
  .pchat-empty{color:var(--muted);text-align:center;padding:26px 8px}
  .pchat-empty b{color:var(--text)}
  .pchat-turn{display:flex;gap:11px}
  .pchat-av{width:28px;height:28px;flex:0 0 28px;border-radius:8px;display:grid;place-items:center;font-size:13px;font-weight:700;margin-top:1px}
  .pchat-av.ai{background:linear-gradient(150deg,var(--accent),var(--accent-dark));color:#fff}
  .pchat-av.me{background:var(--accent-soft);color:var(--accent-dark);font-size:11px}
  .pchat-who{font-size:11.5px;font-weight:700;color:var(--muted);margin-bottom:4px}
  .pchat-body{min-width:0;flex:1;color:var(--text);font-size:14px;line-height:1.6}
  .pchat-body p{margin:0 0 9px}.pchat-body ul{margin:0 0 9px;padding-left:20px}.pchat-body li{margin:3px 0}
  .pchat-user{background:var(--hair);border:1px solid var(--border);border-radius:11px;padding:10px 13px;color:var(--text)}
  .pchat-foot{display:flex;align-items:center;gap:8px;margin-top:7px;padding-top:8px;border-top:1px dashed var(--border);color:var(--muted);font-size:11px}
  .pchat-foot b{color:#1f8a5b}
  .pchat-think{display:flex;gap:5px;align-items:center;color:var(--muted);font-size:12.5px;padding:2px 0}
  .pchat-think .d{width:7px;height:7px;border-radius:50%;background:var(--accent);opacity:.35;animation:pchatbob 1s infinite}
  .pchat-think .d:nth-child(2){animation-delay:.15s}.pchat-think .d:nth-child(3){animation-delay:.3s}
  @keyframes pchatbob{0%,100%{opacity:.3;transform:translateY(0)}40%{opacity:1;transform:translateY(-3px)}}
  .pchat-w{opacity:0}.pchat-w.on{opacity:1;transition:opacity .12s ease}
  .pchat-caret{display:inline-block;width:6px;height:14px;vertical-align:-2px;background:var(--accent);margin-left:1px;border-radius:1px;animation:pchatblink 1.05s steps(1) infinite}
  @keyframes pchatblink{50%{opacity:0}}

  .pchat-composer{display:flex;align-items:flex-end;gap:9px;border:1px solid var(--border);background:var(--card-bg);border-radius:13px;padding:9px 10px 9px 13px}
  .pchat-composer:focus-within{border-color:var(--accent)}
  .pchat-composer textarea{flex:1;border:0;outline:0;resize:none;background:transparent;color:var(--text);font:inherit;font-size:14px;max-height:120px;min-height:22px;padding:5px 0}
  .pchat-composer .send{flex:0 0 auto;width:34px;height:34px;border-radius:9px;border:0;background:var(--accent);color:#fff;font-size:16px;cursor:pointer}
  .pchat-composer .send:hover{background:var(--accent-dark)}.pchat-composer .send:disabled{opacity:.5;cursor:default}
  .pchat-composer .attach{flex:0 0 auto;width:34px;height:34px;border-radius:9px;border:1px solid var(--border);background:var(--card-bg);color:var(--ink-soft);font-size:15px;cursor:pointer}
  .pchat-composer .attach:hover{border-color:var(--accent);color:var(--accent)}
  .pchat-dropcta{display:flex;flex-direction:column;align-items:center;gap:7px;padding:30px 18px}
  .pchat-dropcta .pchat-cta-mk{width:46px;height:46px;border-radius:13px;display:grid;place-items:center;color:#fff;font-size:22px;background:linear-gradient(135deg,var(--accent),#7c5cff);margin-bottom:2px}
  .pchat-dropcta b{color:var(--text);font-size:15px}
  .pchat-dropcta .pchat-cta-sub{font-size:12.5px;color:var(--muted)}
  .pchat-dropcta .pchat-cta-btn{border:1px solid var(--accent);background:var(--accent);color:#fff;font-weight:700;font-size:13px;border-radius:10px;padding:9px 16px;cursor:pointer;font-family:inherit;margin-top:2px}
  .pchat-dropcta .pchat-cta-btn:hover{background:var(--accent-dark)}
  .pchat-dropcta .pchat-cta-note{font-size:11px;color:var(--muted);max-width:340px;line-height:1.5;margin-top:4px}
  .pchat.dragging,.pchat-dragging .pchat-thread{outline:2px dashed var(--accent);outline-offset:3px;background:var(--accent-soft)}

  .pchat-lib{border:1px solid var(--border);background:var(--card-bg);border-radius:12px;padding:14px 16px}
  .pchat-lib .lh{font-size:13.5px;font-weight:750;color:var(--text);text-align:center}
  .pchat-lib .lh b{color:var(--accent-dark)}
  .pchat-lib .lsub{font-size:12px;color:var(--muted);text-align:center;margin:2px 0 12px}
  .pchat-rolelbl{display:block;text-align:center;font-size:10.5px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;color:var(--muted);margin-bottom:7px}
  .pchat-chips{display:flex;gap:7px;flex-wrap:wrap;justify-content:center;margin-bottom:10px}
  .pchat-chip{border:1px solid var(--border);background:transparent;border-radius:999px;padding:5px 11px;font-size:12px;cursor:pointer;color:var(--ink-soft);font-family:inherit}
  .pchat-chip:hover{border-color:var(--accent);color:var(--accent-dark)}
  .pchat-chip.on{background:var(--accent);color:#fff;border-color:var(--accent)}
  .pchat-search{width:100%;border:1px solid var(--border);border-radius:10px;padding:9px 12px;font:inherit;font-size:13px;background:var(--bg);color:var(--text);outline:0;margin-bottom:8px}
  .pchat-search:focus{border-color:var(--accent)}
  .pchat-theme{margin-top:14px}
  .pchat-theme h4{font-size:12px;font-weight:800;color:var(--accent-dark);margin:0 0 3px;text-transform:uppercase;letter-spacing:.4px}
  .pchat-theme .tb{font-size:11.5px;color:var(--muted);margin:0 0 6px}
  .pchat-nomatch{color:var(--muted);text-align:center;padding:18px 4px;font-size:13px}
  .pchat-charts{display:flex;flex-direction:column;gap:12px;margin:8px 0 4px}
  .pchat-chart{border:1px solid var(--border);border-radius:10px;padding:10px 12px;background:var(--bg)}
  .pchat-chart .ct{font-size:11px;font-weight:700;color:var(--muted);margin-bottom:9px;text-transform:uppercase;letter-spacing:.3px}
  .pchat-kpis{display:flex;gap:9px;flex-wrap:wrap}
  .pchat-kpi{flex:1;min-width:92px;border:1px solid var(--border);border-radius:9px;padding:8px 10px;background:var(--card-bg)}
  .pchat-kpi .k{font-size:11px;color:var(--muted)}
  .pchat-kpi .v{font-size:19px;font-weight:800;line-height:1.15;color:var(--text)}
  .pchat-kpi .h{font-size:10.5px;color:var(--muted)}
  .pchat-kpi.good .v{color:#1f8a5b}.pchat-kpi.warn .v{color:#c98a1e}.pchat-kpi.bad .v{color:#c0392b}
  .pchat-bar{display:grid;grid-template-columns:118px 1fr auto;gap:9px;align-items:center;margin:6px 0}
  .pchat-bar .bn{font-size:12px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .pchat-bar .bt{position:relative;height:15px;border-radius:5px;background:var(--hair);overflow:hidden}
  .pchat-bar .bp{position:absolute;left:0;top:0;bottom:0;background:var(--accent-soft)}
  .pchat-bar .ba{position:absolute;left:0;top:0;bottom:0;background:var(--accent);opacity:.92}
  .pchat-bar .bv{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
  .pchat-barlegend{font-size:10.5px;color:var(--muted);margin-top:5px}
  .pchat-stream{white-space:pre-wrap;color:var(--text);font-size:14px;line-height:1.6}
  .pchat-models{display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 10px}
  .pchat-mchip{border:1px solid var(--border);background:var(--card-bg);border-radius:9px;padding:7px 11px;font-size:12.5px;cursor:pointer;color:var(--ink-soft);font-family:inherit;text-align:left}
  .pchat-mchip:hover{border-color:var(--accent)}
  .pchat-mchip.on{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}
  .pchat-mchip .sz{display:block;font-size:10.5px;color:var(--muted)}

  /* ── Claude-style standalone layout (drawer library + greeting + suggestion strip) ── */
  .pchat{height:100%;min-height:0}
  .pchat-head .sub{margin-top:1px}
  .pchat-setuplink{border:1px solid var(--border);background:transparent;color:var(--accent-dark);font:inherit;font-size:11.5px;font-weight:650;border-radius:999px;padding:5px 11px;cursor:pointer}
  .pchat-setuplink:hover{border-color:var(--accent);color:var(--accent)}
  .pchat-setupwrap{margin-top:-2px}
  /* thread fills the remaining height; caps to the viewport so the composer stays in view */
  .pchat-thread{flex:1 1 auto;min-height:240px;max-height:calc(100vh - 320px)}

  /* greeting / empty state */
  .pchat-welcome{display:flex;flex-direction:column;align-items:center;gap:11px;text-align:center;padding:20px 8px 6px}
  .pchat-welcome .pchat-cta-mk{width:46px;height:46px;border-radius:13px;display:grid;place-items:center;color:#fff;font-size:22px;background:linear-gradient(135deg,var(--accent),#7c5cff)}
  .pchat-greet{font-size:20px;font-weight:750;color:var(--text);letter-spacing:-.2px}
  .pchat-greet-sub{font-size:13px;color:var(--muted);max-width:540px;line-height:1.55}
  .pchat-greet-sub b{color:var(--ink-soft)}
  .pchat-linkbtn{border:0;background:transparent;color:var(--accent-dark);font:inherit;font-size:13px;font-weight:700;cursor:pointer;padding:0;text-decoration:underline;text-underline-offset:2px}
  .pchat-linkbtn:hover{color:var(--accent)}
  .pchat-sugcards{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;width:100%;max-width:660px;margin-top:6px}
  .pchat-sugcard{text-align:left;border:1px solid var(--border);background:var(--card-bg);border-radius:12px;padding:12px 13px;cursor:pointer;display:flex;flex-direction:column;gap:4px;font-family:inherit;transition:border-color .15s,transform .15s,box-shadow .15s}
  .pchat-sugcard:hover{border-color:var(--accent);transform:translateY(-1px);box-shadow:0 6px 18px rgba(0,0,0,.08)}
  .pchat-sugcard .ic{font-size:18px;line-height:1}
  .pchat-sugcard .t{font-size:13px;font-weight:700;color:var(--text);line-height:1.3}
  .pchat-sugcard .s{font-size:11.5px;color:var(--muted);line-height:1.35}
  .pchat-welcome-foot{display:flex;align-items:center;gap:12px;flex-wrap:wrap;justify-content:center;margin-top:14px}
  .pchat-browse{border:1px solid var(--accent);background:var(--accent-soft);color:var(--accent-dark);font:inherit;font-size:12.5px;font-weight:700;border-radius:999px;padding:7px 15px;cursor:pointer}
  .pchat-browse:hover{background:var(--accent);color:#fff}

  /* suggestion strip (just above the composer) */
  .pchat-strip{display:flex;gap:8px;overflow-x:auto;padding:1px 1px 3px;scrollbar-width:thin}
  .pchat-strip::-webkit-scrollbar{height:6px}
  .pchat-strip::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
  .pchat-chipsug{flex:0 0 auto;display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border);background:var(--card-bg);border-radius:999px;padding:6px 12px;font-size:12px;color:var(--ink-soft);cursor:pointer;font-family:inherit;white-space:nowrap}
  .pchat-chipsug:hover{border-color:var(--accent);color:var(--accent-dark)}
  .pchat-chipsug .ic{font-size:13px;line-height:1}
  .pchat-chipsug.browse{border-style:dashed;color:var(--accent-dark);font-weight:700}
  .pchat-chipsug.browse:hover{background:var(--accent-soft)}

  /* slide-in question-library drawer + scrim */
  .pchat-scrim{position:fixed;inset:0;background:rgba(10,15,25,.42);opacity:0;visibility:hidden;transition:opacity .28s ease;z-index:59}
  .pchat-scrim.on{opacity:1;visibility:visible}
  .pchat-drawer{position:fixed;top:0;right:0;bottom:0;width:min(440px,92vw);background:var(--card-bg);border-left:1px solid var(--border);box-shadow:-14px 0 44px rgba(0,0,0,.20);transform:translateX(102%);transition:transform .28s cubic-bezier(.4,0,.2,1);z-index:60;display:flex;flex-direction:column}
  .pchat-drawer.on{transform:translateX(0)}
  .pchat-drawer-head{display:flex;align-items:center;gap:10px;padding:15px 16px;border-bottom:1px solid var(--border);font-size:14px;font-weight:750;color:var(--text);flex:0 0 auto}
  .pchat-drawer-head b{color:var(--accent-dark)}
  .pchat-drawer-head .sp{flex:1}
  .pchat-drawer-close{border:1px solid var(--border);background:transparent;color:var(--muted);width:30px;height:30px;border-radius:8px;cursor:pointer;font-size:13px;line-height:1;font-family:inherit}
  .pchat-drawer-close:hover{border-color:var(--accent);color:var(--accent)}
  .pchat-drawer-body{flex:1 1 auto;min-height:0;overflow:auto;padding:14px 16px}
  .pchat-drawer-body .lsub{font-size:12px;color:var(--muted);text-align:center;margin:0 0 12px}
  @media (max-width:560px){.pchat-sugcards{grid-template-columns:repeat(2,1fr)}}

  [hidden]{display:none!important}
  `;
  document.head.appendChild(s);
}

// ── markdown-lite → safe HTML ────────────────────────────────────────────────
function mdInline(s) { return escapeHtml(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>'); }
function mdToHtml(text) {
  const out = [];
  for (const block of String(text || '').split(/\n{2,}/)) {
    const lines = block.split('\n').map((l) => l.trim()).filter(Boolean);
    if (!lines.length) continue;
    const bullets = lines.every((l) => /^([•\-*]|\d+[.)])\s+/.test(l));
    if (bullets && lines.length > 1) {
      out.push('<ul>' + lines.map((l) => '<li>' + mdInline(l.replace(/^([•\-*]|\d+[.)])\s+/, '')) + '</li>').join('') + '</ul>');
    } else {
      out.push('<p>' + mdInline(lines.join(' ')) + '</p>');
    }
  }
  return out.join('') || ('<p>' + mdInline(text) + '</p>');
}

// wrap every word in a span so the answer can be revealed word-by-word
function wrapWords(node, words) {
  [...node.childNodes].forEach((ch) => {
    if (ch.nodeType === 3) {
      const frag = document.createDocumentFragment();
      ch.textContent.split(/(\s+)/).forEach((w) => {
        if (w === '') return;
        if (/^\s+$/.test(w)) { frag.appendChild(document.createTextNode(w)); return; }
        const sp = document.createElement('span'); sp.className = 'pchat-w'; sp.textContent = w;
        frag.appendChild(sp); words.push(sp);
      });
      node.replaceChild(frag, ch);
    } else if (ch.nodeType === 1) {
      wrapWords(ch, words);
    }
  });
}

const thread = () => document.getElementById('pchat-thread');
function scrollThread() { const t = thread(); if (t) t.scrollTop = t.scrollHeight; }

function addUser(text) {
  const t = thread(); if (!t) return;
  const empty = t.querySelector('.pchat-empty'); if (empty) empty.remove();
  const turn = document.createElement('div'); turn.className = 'pchat-turn';
  turn.innerHTML = `<div class="pchat-av me">IG</div><div class="pchat-body">
    <div class="pchat-who">You</div><div class="pchat-user">${escapeHtml(text)}</div></div>`;
  t.appendChild(turn); scrollThread();
}

function addAiShell() {
  const t = thread(); if (!t) return null;
  const turn = document.createElement('div'); turn.className = 'pchat-turn';
  turn.innerHTML = `<div class="pchat-av ai">✦</div><div class="pchat-body">
    <div class="pchat-who">AI Chat</div>
    <div class="pchat-think"><span class="d"></span><span class="d"></span><span class="d"></span> Reading your schedule…</div></div>`;
  t.appendChild(turn); scrollThread();
  return turn.querySelector('.pchat-body');
}

function addAiMessage(html) {
  const t = thread(); if (!t) return;
  const empty = t.querySelector('.pchat-empty'); if (empty) empty.remove();
  const turn = document.createElement('div'); turn.className = 'pchat-turn';
  turn.innerHTML = `<div class="pchat-av ai">✦</div><div class="pchat-body">
    <div class="pchat-who">AI Chat</div><div class="pchat-stream"></div></div>`;
  turn.querySelector('.pchat-stream').innerHTML = html;
  t.appendChild(turn); scrollThread();
}

// Send a P6 file INSIDE the chat: reuse the app's parse+compute (importFile) but stay in the
// chat and re-render it grounded — no separate "import first" step, no jump to the EVM panel.
async function sendFile(path) {
  if (!path || BUSY) return;
  BUSY = true; setSendEnabled(false);
  try {
    const nm = String(path).split(/[\\/]/).pop();
    const t = thread();
    if (t) t.innerHTML = `<div class="pchat-empty"><div class="pchat-think"><span class="d"></span><span class="d"></span><span class="d"></span> Reading ${escapeHtml(nm)}…</div></div>`;
    let data;
    try { data = await importFile(path, { showSpinner: false, onLoaded: () => {} }); }
    catch (e) { data = { ok: false, error: String((e && e.message) || e) }; }
    if (!data || !data.ok) {
      if (t) t.innerHTML = `<div class="pchat-empty">I couldn’t read that file. ${escapeHtml((data && data.error) || 'Send a .xer or .xml exported from Primavera P6.')}</div>`;
      return;
    }
    await renderChat();                       // re-render grounded (thread + library + composer)
    const r = data.result || {};
    const bits = [];
    if (r.data_date) { try { bits.push('data date ' + fmtDate(r.data_date)); } catch (_) { /* leave out */ } }
    if (r.spi != null) bits.push('SPI ' + Number(r.spi).toFixed(2));
    if (r.delay_days != null) bits.push((r.delay_days > 0 ? '+' : '') + r.delay_days + ' wd vs baseline');
    addAiMessage(`✓ Loaded <b>${escapeHtml(nm)}</b>${bits.length ? ' — ' + escapeHtml(bits.join(' · ')) : ''}.<br>Ask me anything, or pick a question from the library below.`);
  } finally {
    BUSY = false; setSendEnabled(true);
  }
}

// Open the native file picker and send the chosen P6 file (WebView2/pywebview).
async function pickAndSend() {
  try {
    if (!(window.pywebview && window.pywebview.api && window.pywebview.api.choose_file)) {
      addAiMessage('File picker isn’t available here — drag a <b>.xer</b>/<b>.xml</b> onto the chat instead.');
      return;
    }
    const path = await window.pywebview.api.choose_file();
    if (path) sendFile(path);
  } catch (_) { /* cancelled / unavailable */ }
}

function renderCharts(charts) {
  const wrap = document.createElement('div'); wrap.className = 'pchat-charts';
  (charts || []).forEach((c) => {
    const card = document.createElement('div'); card.className = 'pchat-chart';
    card.innerHTML = `<div class="ct">${escapeHtml(c.title || '')}</div>`;
    if (c.type === 'kpi') {
      const row = document.createElement('div'); row.className = 'pchat-kpis';
      (c.items || []).forEach((it) => {
        const t = document.createElement('div'); t.className = 'pchat-kpi ' + (it.tone || '');
        t.innerHTML = `<div class="k">${escapeHtml(it.label)}</div><div class="v">${escapeHtml(it.value)}</div><div class="h">${escapeHtml(it.hint || '')}</div>`;
        row.appendChild(t);
      });
      card.appendChild(row);
    } else if (c.type === 'bars') {
      (c.items || []).forEach((it) => {
        const pl = Math.max(0, Math.min(100, it.planned || 0));
        const aa = Math.max(0, Math.min(100, it.actual || 0));
        const b = document.createElement('div'); b.className = 'pchat-bar';
        b.innerHTML = `<div class="bn" title="${escapeHtml(it.name)}">${escapeHtml(it.name)}</div>
          <div class="bt"><div class="bp" style="width:${pl}%"></div><div class="ba" style="width:${aa}%"></div></div>
          <div class="bv">${aa}% / ${pl}%</div>`;
        card.appendChild(b);
      });
      const lg = document.createElement('div'); lg.className = 'pchat-barlegend'; lg.textContent = 'actual / planned';
      card.appendChild(lg);
    }
    wrap.appendChild(card);
  });
  return wrap;
}

// ── professional dashboard (in-chat) ─────────────────────────────────────────
// A self-contained "command board" with its own three visual FORMATS the planner
// can switch between (Executive / Midnight / Blueprint). It has its own colour
// system (independent of the app's appearance tokens) so it always looks like the
// approved design; every number is grounded — built by /api/chat/dashboard from a
// re-parse of the open schedule, never invented.
function ensureDashCss() {
  if (document.getElementById('pdash-css')) return;
  const s = document.createElement('style');
  s.id = 'pdash-css';
  s.textContent = `
  .pdash{
    --ground:#eef1f6;--panel:#fff;--panel2:#f7f9fc;--line:#e3e8f0;--grid:#eaeef4;
    --ink:#16202e;--ink2:#5a6b80;--mut:#8695a8;
    --accent:#1f4e79;--accent2:#2f6fb8;--accentsoft:#dceaf6;
    --good:#1f8a5b;--warn:#c17d16;--bad:#c0392b;
    --s-plan:#2f6fb8;--s-earn:#1f8a5b;--s-fore:#c17d16;
    --shadow:0 1px 2px rgba(16,32,55,.05),0 8px 24px rgba(16,32,55,.07);
    background:var(--ground);color:var(--ink);border-radius:14px;padding:16px 16px 18px;
    font-family:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;transition:background .25s,color .25s}
  .pdash[data-style="midnight"]{
    --ground:#0a1120;--panel:#111b2e;--panel2:#0e1728;--line:#243247;--grid:#1b2740;
    --ink:#eaf1fb;--ink2:#9fb2cd;--mut:#6b7d99;
    --accent:#5b9bff;--accent2:#7fb2ff;--accentsoft:#16294a;
    --good:#3fd18a;--warn:#e0a83a;--bad:#ff6b5e;
    --s-plan:#5b9bff;--s-earn:#3fd18a;--s-fore:#e0a83a;
    --shadow:0 1px 2px rgba(0,0,0,.3),0 12px 30px rgba(0,0,0,.35)}
  .pdash[data-style="blueprint"]{
    --ground:#08213c;--panel:#0c2c50;--panel2:#0a2647;--line:#1e4a76;--grid:#123f68;
    --ink:#eaf6ff;--ink2:#a9d0ec;--mut:#6c9cc2;
    --accent:#57d2ff;--accent2:#8ae1ff;--accentsoft:#0e3a5f;
    --good:#5be6c0;--warn:#ffcf6b;--bad:#ff8a7a;
    --s-plan:#57d2ff;--s-earn:#5be6c0;--s-fore:#ffcf6b;
    --shadow:0 1px 2px rgba(0,0,0,.35),0 12px 34px rgba(3,20,40,.5)}
  .pdash *{box-sizing:border-box}
  .pdash .mono{font-family:"IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}
  .pdash h1,.pdash h3{margin:0}
  .pdash .dhead{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:14px}
  .pdash .lead{flex:1;min-width:220px}
  .pdash .kick{font-family:"IBM Plex Mono",monospace;font-size:10.5px;letter-spacing:2px;text-transform:uppercase;color:var(--accent2);font-weight:600}
  .pdash h1{font-size:22px;font-weight:700;letter-spacing:-.4px;text-wrap:balance;color:var(--ink)}
  .pdash .dmeta{color:var(--ink2);font-size:12px;margin-top:3px}
  .pdash .dmeta b{color:var(--ink);font-weight:600}
  .pdash .styleseg{display:inline-flex;background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:3px;gap:2px}
  .pdash .styleseg button{border:0;background:transparent;color:var(--ink2);font:inherit;font-size:12px;font-weight:600;padding:6px 12px;border-radius:8px;cursor:pointer}
  .pdash .styleseg button.on{background:var(--accent);color:#fff}
  .pdash[data-style="blueprint"] .styleseg button.on,.pdash[data-style="midnight"] .styleseg button.on{color:#04121f}
  .pdash .health{display:flex;align-items:center;gap:16px;flex-wrap:wrap;border:1px solid var(--line);border-left:4px solid var(--mut);background:var(--panel);border-radius:12px;padding:13px 15px;box-shadow:var(--shadow);margin-bottom:13px}
  .pdash .health.bad{border-left-color:var(--bad)}.pdash .health.warn{border-left-color:var(--warn)}.pdash .health.good{border-left-color:var(--good)}
  .pdash .health .badge{font-family:"IBM Plex Mono",monospace;font-weight:600;font-size:12px;letter-spacing:.5px;color:#fff;background:var(--mut);padding:5px 11px;border-radius:999px;white-space:nowrap}
  .pdash .health.bad .badge{background:var(--bad)}.pdash .health.warn .badge{background:var(--warn)}.pdash .health.good .badge{background:var(--good)}
  .pdash .health .msg{flex:1;min-width:230px;font-size:13.5px;line-height:1.5;color:var(--ink)}
  .pdash .health .msg b{font-weight:600}
  .pdash .health .fin{text-align:right}
  .pdash .health .fin .k{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.6px}
  .pdash .health .fin .v{font-size:16px;font-weight:700;color:var(--ink)}
  .pdash .health .fin .v.bad{color:var(--bad)}.pdash .health .fin .v.good{color:var(--good)}
  .pdash .dkpis{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:13px}
  .pdash .dkpi{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:11px 12px;box-shadow:var(--shadow);position:relative;overflow:hidden}
  .pdash .dkpi::after{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--accent2);opacity:0}
  .pdash .dkpi.good::after{background:var(--good);opacity:1}.pdash .dkpi.warn::after{background:var(--warn);opacity:1}.pdash .dkpi.bad::after{background:var(--bad);opacity:1}
  .pdash .dkpi .k{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px}
  .pdash .dkpi .v{font-size:21px;font-weight:700;line-height:1.15;margin-top:2px;color:var(--ink)}
  .pdash .dkpi.good .v{color:var(--good)}.pdash .dkpi.warn .v{color:var(--warn)}.pdash .dkpi.bad .v{color:var(--bad)}
  .pdash .dkpi .h{font-size:10.5px;color:var(--ink2);margin-top:1px}
  .pdash .dgrid{display:grid;grid-template-columns:1.55fr 1fr;gap:12px}
  .pdash .dcard{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:14px 15px;box-shadow:var(--shadow)}
  .pdash .dcard h3{font-size:13px;font-weight:600;display:flex;align-items:center;gap:8px;color:var(--ink)}
  .pdash .dcard .sub{font-size:11px;color:var(--mut);margin:2px 0 11px}
  .pdash .tag{font-family:"IBM Plex Mono",monospace;font-size:9.5px;font-weight:600;color:var(--accent2);background:var(--accentsoft);padding:2px 7px;border-radius:5px;letter-spacing:.3px}
  .pdash .legend{display:flex;gap:14px;flex-wrap:wrap;font-size:10.5px;color:var(--ink2);margin-top:8px}
  .pdash .legend i{display:inline-block;width:11px;height:3px;border-radius:2px;vertical-align:middle;margin-right:5px}
  .pdash svg .axt{fill:var(--mut);font-family:"IBM Plex Mono",monospace;font-size:9px}
  .pdash svg .gl{stroke:var(--grid);stroke-width:1}
  .pdash svg .plan-l{stroke:var(--s-plan);stroke-width:2;fill:none}
  .pdash svg .plan-a{fill:var(--s-plan);opacity:.09}
  .pdash svg .earn-l{stroke:var(--s-earn);stroke-width:2.5;fill:none}
  .pdash svg .earn-a{fill:var(--s-earn);opacity:.12}
  .pdash svg .fore-l{stroke:var(--s-fore);stroke-width:2;stroke-dasharray:5 4;fill:none}
  .pdash svg .ddl{stroke:var(--ink2);stroke-width:1;stroke-dasharray:3 3}
  .pdash svg .dot{fill:var(--panel);stroke-width:2.5}
  .pdash .gauges{display:flex;gap:12px}
  .pdash .gauge{flex:1;text-align:center}
  .pdash .gauge .gl2{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px}
  .pdash .gauge .num{font-size:19px;font-weight:700;color:var(--ink)}
  .pdash .gauge .num.good{color:var(--good)}.pdash .gauge .num.warn{color:var(--warn)}.pdash .gauge .num.bad{color:var(--bad)}
  .pdash .tl{position:relative;height:22px;background:var(--panel2);border:1px solid var(--line);border-radius:999px;margin:22px 0 6px}
  .pdash .tl .fill{position:absolute;left:0;top:0;bottom:0;border-radius:999px;background:linear-gradient(90deg,var(--accent2),var(--accent))}
  .pdash .tl .mk{position:absolute;top:-19px;transform:translateX(-50%);font-size:9.5px;color:var(--ink2);white-space:nowrap;text-align:center}
  .pdash .tl .mk::after{content:"";position:absolute;left:50%;top:17px;width:1px;height:14px;background:var(--line)}
  .pdash .tl .now{position:absolute;top:-2px;bottom:-2px;width:2px;background:var(--bad)}
  .pdash .tstat{display:flex;justify-content:space-between;font-size:11px;color:var(--ink2);margin-top:12px}
  .pdash .tstat b{color:var(--ink);font-weight:600}
  .pdash .disc{display:flex;flex-direction:column;gap:9px;margin-top:4px}
  .pdash .drow{display:grid;grid-template-columns:112px 1fr auto;gap:9px;align-items:center}
  .pdash .dn{font-size:12px;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .pdash .dtrack{position:relative;height:15px;border-radius:5px;background:var(--panel2);overflow:hidden}
  .pdash .dtrack .pl{position:absolute;inset:0 auto 0 0;background:var(--accentsoft)}
  .pdash .dtrack .ac{position:absolute;inset:0 auto 0 0;background:var(--accent2)}
  .pdash .dvv{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--ink2);white-space:nowrap}
  .pdash .gap{display:flex;flex-direction:column;gap:8px;margin-top:4px}
  .pdash .grow{display:grid;grid-template-columns:150px 1fr auto;gap:10px;align-items:center}
  .pdash .gn{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .pdash .gtrack{position:relative;height:17px;background:var(--panel2);border-radius:5px}
  .pdash .gbar{position:absolute;top:0;bottom:0;left:50%;background:var(--bad);border-radius:3px}
  .pdash .gbar.ahead{background:var(--good)}
  .pdash .gmid{position:absolute;top:-3px;bottom:-3px;left:50%;width:1px;background:var(--line)}
  .pdash .gv{font-family:"IBM Plex Mono",monospace;font-size:11px;font-weight:600;color:var(--bad);white-space:nowrap}
  .pdash .gv.ahead{color:var(--good)}
  .pdash .gaptot{display:flex;justify-content:space-between;align-items:center;margin-top:11px;padding-top:11px;border-top:1px dashed var(--line);font-size:12px;color:var(--ink2)}
  .pdash .gaptot b{font-family:"IBM Plex Mono",monospace;font-size:15px;color:var(--bad);font-weight:600}
  .pdash .gaptot b.good{color:var(--good)}
  .pdash .dfoot{margin-top:14px;font-size:11px;color:var(--mut)}
  .pdash .dfoot .off{color:var(--good);font-weight:600}
  @media (max-width:820px){ .pdash .dkpis{grid-template-columns:repeat(3,1fr)} .pdash .dgrid{grid-template-columns:1fr} }
  @media (max-width:480px){ .pdash .dkpis{grid-template-columns:repeat(2,1fr)} .pdash .drow{grid-template-columns:88px 1fr auto} .pdash .grow{grid-template-columns:120px 1fr auto} }
  `;
  document.head.appendChild(s);
}

// £M money magnitude (sign is applied by the caller).
function money(v) { return '£' + Math.abs(Number(v) || 0).toFixed(1) + 'M'; }

function dashScurveSvg(sc) {
  const months = sc.months || [], plan = sc.plan || [], earn = sc.earn || [], fore = sc.fore || [];
  const n = months.length;
  if (n < 2) return '<div class="sub">Not enough dated activities to draw the value curve.</div>';
  const W = 560, H = 210, L = 30, R = 12, T = 12, B = 26, iw = W - L - R, ih = H - T - B;
  const x = (i) => L + iw * (i / (n - 1));
  const y = (v) => T + ih * (1 - Math.max(0, Math.min(100, v)) / 100);
  const line = (arr) => {
    let d = '';
    for (let i = 0; i < arr.length; i++) { if (arr[i] == null) continue; d += (d ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(arr[i]).toFixed(1); }
    return d;
  };
  const area = (arr) => {
    const pts = [];
    for (let i = 0; i < arr.length; i++) { if (arr[i] != null) pts.push([x(i), y(arr[i])]); }
    if (pts.length < 2) return '';
    let d = 'M' + pts[0][0].toFixed(1) + ' ' + (T + ih) + 'L';
    d += pts.map((p) => p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('L');
    return d + 'L' + pts[pts.length - 1][0].toFixed(1) + ' ' + (T + ih) + 'Z';
  };
  const lastIdx = (arr) => { for (let i = arr.length - 1; i >= 0; i--) if (arr[i] != null) return i; return -1; };
  let grid = '';
  for (let g = 0; g <= 100; g += 25) grid += `<line class="gl" x1="${L}" y1="${y(g)}" x2="${W - R}" y2="${y(g)}"/><text class="axt" x="${L - 4}" y="${y(g) + 3}" text-anchor="end">${g}</text>`;
  // ~7 evenly-spaced x-labels, always including first, last and the data date
  const ddi = (sc.dd_index == null ? -1 : sc.dd_index);
  const ticks = new Set([0, n - 1]); if (ddi >= 0) ticks.add(ddi);
  const step = Math.max(1, Math.round((n - 1) / 6));
  for (let i = 0; i < n; i += step) ticks.add(i);
  let xlab = '';
  [...ticks].sort((a, b) => a - b).forEach((i) => { xlab += `<text class="axt" x="${x(i)}" y="${H - 8}" text-anchor="middle">${escapeHtml(String(months[i] || ''))}</text>`; });
  let ddMark = '';
  if (ddi >= 0) { const ddx = x(ddi); ddMark = `<line class="ddl" x1="${ddx}" y1="${T}" x2="${ddx}" y2="${T + ih}"/><text class="axt" x="${ddx + 3}" y="${T + 9}">data date</text>`; }
  const ei = lastIdx(earn), pi = lastIdx(plan);
  const earnDot = ei >= 0 ? `<circle class="dot" cx="${x(ei)}" cy="${y(earn[ei])}" r="4" style="stroke:var(--s-earn)"/>` : '';
  const planDot = pi >= 0 ? `<circle class="dot" cx="${x(pi)}" cy="${y(plan[pi])}" r="4" style="stroke:var(--s-plan)"/>` : '';
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block">${grid}${xlab}${ddMark}`
    + `<path class="plan-a" d="${area(plan)}"/><path class="plan-l" d="${line(plan)}"/>`
    + `<path class="earn-a" d="${area(earn)}"/><path class="fore-l" d="${line(fore)}"/>`
    + `<path class="earn-l" d="${line(earn)}"/>${earnDot}${planDot}</svg>`;
}

function dashGaugesSvg(gauges) {
  const MAXV = 1.5;
  const arc = (cx, cy, r, a0, a1) => {
    const p = (a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
    const s = p(a0), e = p(a1), large = (a1 - a0) > Math.PI ? 1 : 0;
    return `M${s[0].toFixed(1)} ${s[1].toFixed(1)}A${r} ${r} 0 ${large} 1 ${e[0].toFixed(1)} ${e[1].toFixed(1)}`;
  };
  return (gauges || []).map((g) => {
    const cx = 52, cy = 52, r = 40, a0 = Math.PI, a1 = Math.PI * 2;
    const val = g.value == null ? 0 : g.value;
    const frac = Math.max(0, Math.min(1, val / MAXV));
    const av = a0 + (a1 - a0) * frac;
    const col = g.tone === 'bad' ? 'var(--bad)' : g.tone === 'warn' ? 'var(--warn)' : 'var(--good)';
    const ta = a0 + (a1 - a0) * (1 / MAXV);                 // the "1.0" target tick
    const tick = `<line x1="${(cx + r * Math.cos(ta)).toFixed(1)}" y1="${(cy + r * Math.sin(ta)).toFixed(1)}" x2="${(cx + (r - 13) * Math.cos(ta)).toFixed(1)}" y2="${(cy + (r - 13) * Math.sin(ta)).toFixed(1)}" stroke="var(--ink2)" stroke-width="1.4"/>`;
    return `<div class="gauge"><svg viewBox="0 0 104 66" width="100%" style="max-width:118px">`
      + `<path d="${arc(cx, cy, r, a0, a1)}" fill="none" stroke="var(--grid)" stroke-width="9" stroke-linecap="round"/>`
      + `<path d="${arc(cx, cy, r, a0, av)}" fill="none" stroke="${col}" stroke-width="9" stroke-linecap="round"/>${tick}</svg>`
      + `<div class="num ${g.tone || ''}">${g.value == null ? '—' : Number(g.value).toFixed(2)}</div><div class="gl2">${escapeHtml(g.label || '')}</div></div>`;
  }).join('');
}

let DASH_SEQ = 0;
function renderDashboard(p) {
  const meta = p.meta || {}, health = p.health || {}, ts = p.time_status || {}, sc = p.scurve || {};
  const wrap = document.createElement('div');
  wrap.className = 'pchat-dashwrap';
  const metaBits = [];
  if (meta.data_date) metaBits.push(`Data date <b>${escapeHtml(meta.data_date)}</b>`);
  if (meta.baseline_finish) metaBits.push(`Baseline finish <b>${escapeHtml(meta.baseline_finish)}</b>`);
  if (meta.forecast_finish) metaBits.push(`Forecast <b>${escapeHtml(meta.forecast_finish)}</b>`);
  metaBits.push(meta.cost_loaded ? 'Cost-loaded schedule' : 'Duration-weighted (not cost-loaded)');

  const kpis = (p.kpis || []).map((k) =>
    `<div class="dkpi ${k.t || ''}"><div class="k">${escapeHtml(k.k)}</div><div class="v">${escapeHtml(k.v)}</div><div class="h">${escapeHtml(k.h || '')}</div></div>`).join('');

  const sv = health.schedule_variance_m;
  const svCls = sv == null ? '' : (sv < 0 ? 'bad' : 'good');
  const finBlock = sv == null ? '' :
    `<div class="fin"><div class="k">Schedule variance</div><div class="v ${svCls}">${sv < 0 ? '−' : '+'}${money(sv)}</div></div>`;

  // time bar positions (clamped)
  const el = Math.max(0, Math.min(100, ts.elapsed_pct || 0));
  const ea = Math.max(0, Math.min(100, ts.earned_pct || 0));

  const disc = (p.disciplines || []).map((d) => {
    const pl = Math.max(0, Math.min(100, d.planned || 0)), ac = Math.max(0, Math.min(100, d.actual || 0));
    return `<div class="drow"><div class="dn" title="${escapeHtml(d.name)}">${escapeHtml(d.name)}</div>`
      + `<div class="dtrack"><div class="pl" style="width:${pl}%"></div><div class="ac" style="width:${ac}%"></div></div>`
      + `<div class="dvv">${Math.round(ac)} / ${Math.round(pl)}</div></div>`;
  }).join('');

  const grows = (p.gap_by_code && p.gap_by_code.rows) || [];
  const gmax = grows.reduce((m, g) => Math.max(m, Math.abs(g.gap_m || 0)), 0) || 1;
  const gapHtml = grows.map((g) => {
    const v = g.gap_m || 0, ahead = v < 0, w = (Math.abs(v) / gmax * 48).toFixed(1);
    // .gbar sets left:50% by default; the ahead bar must anchor its RIGHT edge at the
    // centre and grow left, so clear the inherited left (left+right+width is over-constrained).
    const st = ahead ? `left:auto;right:50%;width:${w}%` : `left:50%;width:${w}%`;
    return `<div class="grow"><div class="gn" title="${escapeHtml(g.code)}">${escapeHtml(g.code)}</div>`
      + `<div class="gtrack"><div class="gmid"></div><div class="gbar${ahead ? ' ahead' : ''}" style="${st}"></div></div>`
      + `<div class="gv${ahead ? ' ahead' : ''}">${ahead ? '+' : '−'}${money(v)}</div></div>`;
  }).join('');
  const gtot = (p.gap_by_code && p.gap_by_code.total_m) || 0;

  const styleId = 'pdash-seg-' + (++DASH_SEQ);
  wrap.innerHTML = `
  <div class="pdash" data-style="exec">
    <div class="dhead">
      <div class="lead">
        <div class="kick">Professional Dashboard · generated from your P6 file</div>
        <h1>${escapeHtml(meta.project || 'Project')} — Earned Value Command Board</h1>
        <div class="dmeta">${metaBits.join(' · ')}</div>
      </div>
      <div class="styleseg" data-seg="${styleId}">
        <button data-dstyle="exec" class="on">Executive</button>
        <button data-dstyle="midnight">Midnight</button>
        <button data-dstyle="blueprint">Blueprint</button>
      </div>
    </div>

    <div class="health ${health.tone || ''}">
      <span class="badge">${escapeHtml(health.verdict || '—')}${health.spi != null ? ' · SPI ' + Number(health.spi).toFixed(2) : ''}</span>
      <div class="msg">${health.message ? mdInline(health.message) : ''}</div>
      ${finBlock}
    </div>

    <div class="dkpis">${kpis}</div>

    <div class="dgrid">
      <div class="dcard">
        <h3>Cost loading — value of work <span class="tag">S-CURVE</span></h3>
        <div class="sub">Cumulative planned value vs earned value, with the expected curve to completion${meta.bac_m ? '. % of ' + money(meta.bac_m) + ' budget' : ''}.</div>
        <div class="js-scurve">${dashScurveSvg(sc)}</div>
        <div class="legend">
          <span><i style="background:var(--s-plan)"></i>Planned value (baseline)</span>
          <span><i style="background:var(--s-earn)"></i>Earned value (actual)</span>
          <span><i style="background:var(--s-fore)"></i>Expected / forecast</span>
        </div>
      </div>

      <div class="dcard">
        <h3>Performance indices <span class="tag">EVM</span></h3>
        <div class="sub">Schedule (SPI) and cost (CPI) efficiency — 1.00 is on plan.</div>
        <div class="gauges">${dashGaugesSvg(p.gauges)}</div>
        <h3 style="margin-top:16px">Time status</h3>
        <div class="tl">
          <div class="fill" style="width:${el}%"></div>
          <div class="now" style="left:${el}%"></div>
          <div class="mk" style="left:0%">Start${ts.start ? '<br>' + escapeHtml(ts.start) : ''}</div>
          <div class="mk" style="left:${Math.max(6, Math.min(94, el))}%">Data date</div>
          <div class="mk" style="left:100%">Finish${ts.finish ? '<br>' + escapeHtml(ts.finish) : ''}</div>
        </div>
        <div class="tstat"><span><b>${Math.round(el)}%</b> of duration elapsed</span><span><b>${Math.round(ea)}%</b> value earned</span></div>
      </div>

      <div class="dcard">
        <h3>Planned vs actual — by discipline <span class="tag">PROGRESS</span></h3>
        <div class="sub">Where the physical progress gap sits. Bars: planned (light) vs actual (solid), %.</div>
        <div class="disc">${disc || '<div class="sub">No weighted disciplines found.</div>'}</div>
        <div class="legend"><span><i style="background:var(--accentsoft)"></i>Planned %</span><span><i style="background:var(--accent2)"></i>Actual %</span></div>
      </div>

      <div class="dcard">
        <h3>EV vs PV gap — by activity code <span class="tag">DRIVER</span></h3>
        <div class="sub">${escapeHtml((p.gap_by_code && p.gap_by_code.label) || 'The schedule variance, decomposed to the activity codes driving it (planned − earned).')}</div>
        <div class="gap">${gapHtml || '<div class="sub">No cost-loaded activity codes to decompose.</div>'}</div>
        ${grows.length ? `<div class="gaptot"><span>Total schedule variance (PV − EV)</span><b class="${gtot <= 0 ? 'good' : ''}">${gtot > 0 ? '−' : '+'}${money(gtot)}</b></div>` : ''}
      </div>
    </div>

    <div class="dfoot">Every figure is read from your imported schedule — <span class="off">offline · nothing invented</span>. Ask me to switch the format above, or open the Reporting Studio to add this to a formal report.</div>
  </div>`;

  // style switcher — delegated to this dashboard only (multiple can coexist in the thread)
  const seg = wrap.querySelector('.styleseg');
  const dash = wrap.querySelector('.pdash');
  seg.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-dstyle]'); if (!b) return;
    dash.setAttribute('data-style', b.dataset.dstyle);
    seg.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
  });
  return wrap;
}

// Ask the backend to build the grounded dashboard, then render it in the thread.
async function askDashboard(question) {
  if (BUSY) return;
  BUSY = true; setSendEnabled(false);
  try {
    addUser(question);
    const bodyEl = addAiShell();
    if (!bodyEl) return;
    const think = bodyEl.querySelector('.pchat-think');
    if (think) think.innerHTML = '<span class="d"></span><span class="d"></span><span class="d"></span> Building your professional dashboard…';
    let payload;
    try {
      payload = await postJSON('/api/chat/dashboard', {
        snapshot_id: state.currentSnapshotId || null,
        xml_path: state.currentXmlPath || '',
        cached_path: state.currentCachedPath || null,
      });
    } catch (e) {
      payload = { ok: false, error: 'The dashboard engine was unreachable: ' + String((e && e.message) || e) };
    }
    if (think) think.remove();
    if (!payload || !payload.ok) {
      const pe = document.createElement('div'); pe.className = 'pchat-stream';
      pe.textContent = (payload && payload.error) || 'I could not build the dashboard from this schedule.';
      bodyEl.appendChild(pe);
    } else {
      ensureDashCss();
      bodyEl.appendChild(renderDashboard(payload));
      const foot = document.createElement('div'); foot.className = 'pchat-foot';
      foot.innerHTML = `🔒 <span><b>Grounded</b> — every figure computed on your PC from this schedule.</span>`;
      bodyEl.appendChild(foot);
    }
    scrollThread();
  } catch (_) {
    /* best-effort — the finally still frees the composer even if rendering threw */
  } finally {
    BUSY = false; setSendEnabled(true);
  }
}

// "create me a professional dashboard", "make a dashboard", "command board"…
// Require a build/show verb next to the noun, OR the whole message being essentially just
// the noun — so a real question that merely MENTIONS "dashboard" still gets answered normally
// (it falls through to /api/chat/ask) instead of being hijacked into a canned dashboard build.
function isDashboardIntent(q) {
  const s = String(q || '');
  const noun = '(?:dashboard|command\\s*board|command\\s*cent(?:er|re)|cockpit)';
  return new RegExp('\\b(?:create|build|make|generate|show|give|open|produce|prepare|draw|need|want)\\b[\\s\\S]{0,40}\\b' + noun + '\\b', 'i').test(s)
      || new RegExp('^\\s*(?:a|an|the|my|professional|project)?\\s*' + noun + '\\s*[.!?]*\\s*$', 'i').test(s);
}

// ── Copilot "expert analysis" (in-chat) ──────────────────────────────────────
// The library's expert questions are tagged with a capability (cap) that routes
// them to the deterministic Copilot backend instead of the free-text /ask path.
// Every answer is grounded — computed on the user's PC from the open schedule.
// Colours read the app's appearance tokens so it themes with the rest of the app.
function ensureCopilotCss() {
  if (document.getElementById('pcp-css')) return;
  const s = document.createElement('style');
  s.id = 'pcp-css';
  s.textContent = `
  .pcp-card{border:1px solid var(--border);background:var(--card-bg);border-radius:12px;padding:14px 16px;color:var(--text);font-size:14px;line-height:1.6;display:flex;flex-direction:column;gap:11px}
  .pcp-lead{font-size:15px;font-weight:750;color:var(--text)}
  .pcp-lead b{color:var(--accent)}
  .pcp-body{color:var(--text)}
  .pcp-body p{margin:0 0 8px}.pcp-body p:last-child{margin:0}
  .pcp-advice{border:1px solid var(--border);background:var(--hair);border-radius:10px;padding:10px 12px}
  .pcp-advice h5{margin:0 0 6px;font-size:11px;font-weight:800;letter-spacing:.4px;text-transform:uppercase;color:var(--accent)}
  .pcp-advice ul{margin:0;padding-left:18px}.pcp-advice li{margin:3px 0}
  .pcp-evi{display:flex;gap:7px;flex-wrap:wrap}
  .pcp-chip{display:inline-flex;gap:5px;align-items:baseline;font-size:11.5px;border:1px solid var(--border);background:var(--accent-soft);color:var(--text);border-radius:999px;padding:4px 10px}
  .pcp-chip b{color:var(--accent);font-weight:700}
  .pcp-note{font-size:11.5px;color:var(--muted);font-style:italic}
  .pcp-insights{margin:0;padding-left:18px;font-size:12.5px;color:var(--text)}.pcp-insights li{margin:3px 0}
  .pcp-tia-head{display:flex;gap:10px;align-items:stretch;flex-wrap:wrap}
  .pcp-tia-fin{flex:1;min-width:118px;border:1px solid var(--border);border-radius:9px;padding:8px 10px;background:var(--hair)}
  .pcp-tia-fin .k{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted)}
  .pcp-tia-fin .v{display:block;font-size:15px;font-weight:750;color:var(--text)}
  .pcp-tia-fin .s{display:block;font-size:11px;color:var(--muted)}
  .pcp-tia-fin.worst .v{color:#c0392b}
  .pcp-wf{display:flex;height:20px;border-radius:6px;overflow:hidden;border:1px solid var(--border);background:var(--hair)}
  .pcp-wf-seg{height:100%}
  .pcp-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--muted)}
  .pcp-legend i{display:inline-block;width:11px;height:3px;border-radius:2px;vertical-align:middle;margin-right:5px}
  .pcp-legend b{color:var(--text)}
  .pcp-wi-note{font-size:12px;color:var(--muted)}
  .pcp-wi-controls{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
  .pcp-wi-field{display:flex;flex-direction:column;gap:4px;position:relative}
  .pcp-wi-field>span{font-weight:700;letter-spacing:.3px;text-transform:uppercase;font-size:10px;color:var(--muted)}
  .pcp-select,.pcp-input{border:1px solid var(--border);background:var(--bg);color:var(--text);border-radius:8px;padding:8px 10px;font:inherit;font-size:13px;outline:0}
  .pcp-select:focus,.pcp-input:focus{border-color:var(--accent)}
  .pcp-wi-act{min-width:220px;flex:1}.pcp-wi-act .pcp-input{width:100%}
  .pcp-wi-days .pcp-input{width:92px}
  .pcp-ta{position:absolute;top:100%;left:0;right:0;z-index:30;margin-top:3px;max-height:210px;overflow:auto;border:1px solid var(--border);background:var(--card-bg);border-radius:9px;box-shadow:0 8px 22px rgba(0,0,0,.14)}
  .pcp-ta-item{padding:7px 10px;font-size:12.5px;color:var(--text);cursor:pointer}
  .pcp-ta-item:hover{background:var(--hair)}
  .pcp-ta-item b{color:var(--accent)}
  .pcp-ta-ms{font-size:10px;color:var(--muted);border:1px solid var(--border);border-radius:4px;padding:0 4px;margin-left:4px}
  .pcp-btn{border:1px solid var(--accent);background:var(--accent);color:#fff;font-weight:700;font-size:12.5px;border-radius:9px;padding:9px 14px;cursor:pointer;font-family:inherit}
  .pcp-btn:hover{background:var(--accent-dark)}
  .pcp-btn:disabled{opacity:.55;cursor:default}
  .pcp-btn.ghost{background:transparent;color:var(--accent-dark);border-color:var(--border)}
  .pcp-wi-result{border-top:1px dashed var(--border);padding-top:11px;display:flex;flex-direction:column;gap:8px}
  .pcp-wi-impact{font-size:22px;font-weight:800;line-height:1.1}
  .pcp-wi-impact.good{color:#1f8a5b}.pcp-wi-impact.bad{color:#c0392b}.pcp-wi-impact.mut{color:var(--muted)}
  .pcp-wi-est{font-size:10.5px;font-weight:700;color:var(--muted);border:1px solid var(--border);border-radius:5px;padding:1px 6px;vertical-align:middle}
  .pcp-wi-basis{font-size:12.5px;color:var(--muted)}
  .pcp-wi-err{font-size:12.5px;color:#c0392b}
  .pcp-wi-ok{font-size:12.5px;color:#1f8a5b;font-weight:700}
  .pcp-wi-path{font-family:ui-monospace,monospace;font-size:11.5px;color:var(--text);word-break:break-all;background:var(--hair);border-radius:6px;padding:5px 8px}
  .pcp-wi-steps{margin:6px 0 0;padding-left:18px;font-size:12.5px;color:var(--text)}.pcp-wi-steps li{margin:3px 0}
  .pcp-wi-exactfig{font-size:14px;color:var(--text)}.pcp-wi-exactfig b{font-size:18px}
  .pcp-wi-exactfig b.good{color:#1f8a5b}.pcp-wi-exactfig b.bad{color:#c0392b}.pcp-wi-exactfig b.mut{color:var(--muted)}
  .pcp-disc{border-top:1px dashed var(--border);padding-top:8px}
  .pcp-disc-toggle{border:0;background:transparent;color:var(--accent-dark);font:inherit;font-size:12.5px;font-weight:700;cursor:pointer;padding:2px 0}
  .pcp-disc-body{margin-top:8px;display:flex;flex-direction:column;gap:9px}
  .pcp-disc-body .pcp-wi-exact{display:flex;flex-direction:column;gap:6px}
  .pcp-report-note{font-size:12px;color:var(--muted)}
  .pcp-report-frame{width:100%;min-height:560px;border:1px solid var(--border);border-radius:10px;background:#fff}
  `;
  document.head.appendChild(s);
}

// A slip figure like "+12 wd" / "−3 wd" (working days), with an em-dash when unknown.
function wdLabel(v) {
  if (v == null || v === '') return '—';
  const n = Number(v);
  if (isNaN(n)) return escapeHtml(String(v));
  return (n > 0 ? '+' : '') + n + ' wd';
}

// assistant → a grounded answer card (headline + body + advice + evidence chips)
function renderAssistant(a) {
  a = a || {};
  const wrap = document.createElement('div');
  wrap.className = 'pcp-card';
  let html = '';
  if (a.headline) html += `<div class="pcp-lead">${mdInline(String(a.headline))}</div>`;
  const body = Array.isArray(a.body) ? a.body : [];
  if (body.length) html += `<div class="pcp-body">${body.map((p) => `<p>${mdInline(String(p))}</p>`).join('')}</div>`;
  const advice = Array.isArray(a.advice) ? a.advice : [];
  if (advice.length) html += `<div class="pcp-advice"><h5>What I'd do</h5><ul>${advice.map((x) => `<li>${mdInline(String(x))}</li>`).join('')}</ul></div>`;
  const evidence = Array.isArray(a.evidence) ? a.evidence : [];
  if (evidence.length) html += `<div class="pcp-evi">${evidence.map((e) => e && `<span class="pcp-chip" title="${escapeHtml((e.module) || '')}"><b>${escapeHtml((e.plain) || '')}:</b> ${escapeHtml(e.value == null ? '' : String(e.value))}</span>`).filter(Boolean).join('')}</div>`;
  wrap.innerHTML = html || '<div class="pcp-body"><p>No analysis available for this question.</p></div>';
  return wrap;
}

// tia → time-impact decomposition (baseline→likely/worst header + waterfall bar)
function renderTia(tia, insights) {
  tia = tia || {};
  const wrap = document.createElement('div');
  wrap.className = 'pcp-card';
  const comps = Array.isArray(tia.components) ? tia.components : [];
  const colorFor = (key) =>
    key === 'to_date' ? 'var(--accent)' :
    key === 'performance' ? '#c17d16' :
    key === 'weather' ? '#2f9e8f' : 'var(--muted)';

  let head = '<div class="pcp-tia-head">';
  head += `<div class="pcp-tia-fin"><span class="k">Baseline finish</span><span class="v">${escapeHtml(tia.baseline_finish || '—')}</span></div>`;
  head += `<div class="pcp-tia-fin"><span class="k">Likely finish</span><span class="v">${escapeHtml(tia.likely_finish || '—')}</span><span class="s">${escapeHtml(wdLabel(tia.likely_slip))} vs baseline</span></div>`;
  if (tia.worst_finish != null && tia.worst_finish !== '')
    head += `<div class="pcp-tia-fin worst"><span class="k">Worst case</span><span class="v">${escapeHtml(tia.worst_finish)}</span><span class="s">${escapeHtml(wdLabel(tia.worst_slip))} vs baseline</span></div>`;
  head += '</div>';

  const total = comps.reduce((sum, c) => sum + Math.abs(Number(c && c.days) || 0), 0) || 1;
  const segs = comps.map((c) => {
    c = c || {};
    const w = (Math.abs(Number(c.days) || 0) / total * 100).toFixed(2);
    const tip = (c.label || c.key || '') + ': ' + wdLabel(c.days) + (c.basis ? ' — ' + c.basis : '');
    return `<div class="pcp-wf-seg" title="${escapeHtml(tip)}" style="width:${w}%;background:${colorFor(c.key)}"></div>`;
  }).join('');
  const wf = comps.length ? `<div class="pcp-wf">${segs}</div>` : '<div class="pcp-wi-note">No slip components to decompose.</div>';
  const legend = comps.map((c) => {
    c = c || {};
    return `<span><i style="background:${colorFor(c.key)}"></i>${escapeHtml(c.label || c.key || '')} <b>${escapeHtml(wdLabel(c.days))}</b></span>`;
  }).join('');

  const ins = Array.isArray(insights) ? insights : [];
  const insHtml = ins.length
    ? `<ul class="pcp-insights">${ins.map((x) => {
        x = x || {};
        const t = x.title != null ? x.title : (x.text != null ? x.text : x);
        const d = x.detail ? ' — ' + escapeHtml(String(x.detail)) : '';
        return `<li>${mdInline(String(t))}${d}</li>`;
      }).join('')}</ul>`
    : '';

  wrap.innerHTML =
    '<div class="pcp-lead">Time impact — where the slip comes from</div>'
    + head + wf
    + (legend ? `<div class="pcp-legend">${legend}</div>` : '')
    + insHtml
    + `<div class="pcp-note">This is an estimate from the schedule — the exact figure is P6's own via the what-if F9 path.</div>`;
  return wrap;
}

// whatif → an inline interactive lever/activity panel (no POST until "Estimate impact")
function renderWhatif() {
  const sid = state.currentSnapshotId || null;
  const xml = state.currentXmlPath || '';
  const cached = state.currentCachedPath || null;

  const panel = document.createElement('div');
  panel.className = 'pcp-card';
  // NOTE: data-* keys here are deliberately NOT data-role/data-s/data-model — those
  // collide with the chat-level delegated handler. Use data-wi + query within panel.
  panel.innerHTML = `
    <div class="pcp-lead">What-if — estimate the impact of a change</div>
    <div class="pcp-wi-note">Pick a lever and (for most) an activity, and I'll estimate the finish-date impact from the schedule. For the exact number, generate a scenario file and run F9 in Primavera.</div>
    <div class="pcp-wi-controls">
      <label class="pcp-wi-field">
        <span>Change</span>
        <select class="pcp-select" data-wi="kind">
          <option value="delay">Delay an activity</option>
          <option value="shorten">Shorten / crash an activity</option>
          <option value="add_crew">Add crew to an activity</option>
          <option value="overtime">Work overtime on an activity</option>
          <option value="remove_relationship">Remove a relationship</option>
          <option value="six_day">Switch to a six-day week</option>
        </select>
      </label>
      <label class="pcp-wi-field pcp-wi-act" data-wi="act-wrap">
        <span>Activity</span>
        <input class="pcp-input" data-wi="act" placeholder="Search by ID or name…" autocomplete="off">
        <div class="pcp-ta" data-wi="ta" hidden></div>
      </label>
      <label class="pcp-wi-field pcp-wi-days" data-wi="days-wrap">
        <span>Days</span>
        <input class="pcp-input" data-wi="days" type="number" min="1" value="5">
      </label>
      <button class="pcp-btn" data-wi="est">Estimate impact</button>
    </div>
    <div class="pcp-wi-result" data-wi="result" hidden></div>
    <div class="pcp-disc">
      <button class="pcp-disc-toggle" data-wi="disc-toggle" aria-expanded="false">▸ Get the exact figure (Primavera F9)</button>
      <div class="pcp-disc-body" data-wi="disc-body" hidden>
        <p class="pcp-wi-note">Generate a scenario XML with this change applied, open it in Primavera P6, press F9 to reschedule, re-export, then load it back here for the exact figure.</p>
        <div class="pcp-wi-controls">
          <button class="pcp-btn ghost" data-wi="gen">Generate scenario file…</button>
          <button class="pcp-btn ghost" data-wi="load">Load rescheduled file…</button>
        </div>
        <div class="pcp-wi-exact" data-wi="exact" hidden></div>
      </div>
    </div>`;

  const q = (k) => panel.querySelector(`[data-wi="${k}"]`);
  const kindSel = q('kind'), actWrap = q('act-wrap'), actInput = q('act'), ta = q('ta');
  const daysWrap = q('days-wrap'), daysInput = q('days'), resultEl = q('result'), exactEl = q('exact');

  let activities = null;   // cached activity list (fetched once)
  let taList = [];         // currently-shown typeahead subset
  let selectedAct = null;  // chosen {id,name,...}

  const needsActivity = (k) => k !== 'six_day';
  const needsDays = (k) => k === 'delay' || k === 'shorten';
  const syncControls = () => {
    const k = kindSel.value;
    actWrap.hidden = !needsActivity(k);
    daysWrap.hidden = !needsDays(k);
    ta.hidden = true;
  };
  syncControls();
  kindSel.addEventListener('change', syncControls);

  const loadActivities = async () => {
    if (activities) return activities;
    try {
      const r = await postJSON('/api/chat/copilot/activities', { snapshot_id: sid, xml_path: xml, cached_path: cached });
      activities = (r && r.ok && Array.isArray(r.activities)) ? r.activities : [];
    } catch (_) { activities = []; }
    return activities;
  };
  const paintTa = () => {
    if (!taList.length) { ta.hidden = true; ta.innerHTML = ''; return; }
    ta.innerHTML = taList.map((a, i) =>
      `<div class="pcp-ta-item" data-i="${i}"><b>${escapeHtml(a.id || '')}</b> ${escapeHtml(a.name || '')}${a.is_milestone ? '<span class="pcp-ta-ms">milestone</span>' : ''}</div>`).join('');
    ta.hidden = false;
  };
  actInput.addEventListener('input', async () => {
    selectedAct = null;
    const list = await loadActivities();
    const term = actInput.value.toLowerCase().trim();
    if (!term) { taList = []; paintTa(); return; }
    taList = list.filter((a) =>
      String(a.id || '').toLowerCase().indexOf(term) >= 0 ||
      String(a.name || '').toLowerCase().indexOf(term) >= 0).slice(0, 12);
    paintTa();
  });
  ta.addEventListener('click', (e) => {
    const it = e.target.closest('.pcp-ta-item'); if (!it) return;
    const a = taList[Number(it.dataset.i)]; if (!a) return;
    selectedAct = a;
    actInput.value = (a.id ? a.id + ' — ' : '') + (a.name || '');
    ta.hidden = true;
  });
  // Dismiss the typeahead on any click that isn't in the activity field (kept within
  // the panel — the task forbids document-wide listeners).
  panel.addEventListener('click', (e) => { if (!e.target.closest('.pcp-wi-act')) ta.hidden = true; });

  const showResult = (r) => {
    resultEl.hidden = false;
    if (!r || !r.ok) {
      resultEl.innerHTML = `<div class="pcp-wi-err">${escapeHtml((r && r.error) || 'Could not estimate this change.')}</div>`;
      return;
    }
    const res = r.result || {};
    const dir = res.direction || 'none';
    const dcls = dir === 'earlier' ? 'good' : dir === 'later' ? 'bad' : 'mut';
    const d = res.impact_days;
    const impact = d == null ? '—' : (Number(d) > 0 ? '+' : '') + d + ' wd';
    let adviceHtml = '';
    if (Array.isArray(res.advice) && res.advice.length)
      adviceHtml = `<div class="pcp-advice"><h5>What I'd do</h5><ul>${res.advice.map((x) => `<li>${mdInline(String(x))}</li>`).join('')}</ul></div>`;
    else if (res.advice) adviceHtml = `<div class="pcp-wi-basis">${mdInline(String(res.advice))}</div>`;
    resultEl.innerHTML =
      `<div class="pcp-wi-impact ${dcls}">${escapeHtml(impact)}${res.estimate ? ' <span class="pcp-wi-est">estimate</span>' : ''}</div>`
      + (res.headline ? `<div class="pcp-lead">${mdInline(String(res.headline))}</div>` : '')
      + (res.basis ? `<div class="pcp-wi-basis">${mdInline(String(res.basis))}</div>` : '')
      + adviceHtml;
  };

  q('est').addEventListener('click', async () => {
    const k = kindSel.value;
    if (needsActivity(k) && !selectedAct) { showResult({ ok: false, error: 'Choose an activity first.' }); return; }
    const btn = q('est'); const old = btn.textContent; btn.disabled = true; btn.textContent = 'Estimating…';
    let r;
    try {
      r = await postJSON('/api/chat/copilot/whatif', {
        snapshot_id: sid, xml_path: xml, cached_path: cached,
        kind: k, activity_id: selectedAct ? selectedAct.id : null,
        days: needsDays(k) ? (Number(daysInput.value) || 0) : null,
      });
    } catch (_) { r = { ok: false, error: 'The what-if engine was unreachable.' }; }
    btn.disabled = false; btn.textContent = old;
    showResult(r);
  });

  const discToggle = q('disc-toggle'), discBody = q('disc-body');
  discToggle.addEventListener('click', () => {
    const opening = discBody.hidden;
    discBody.hidden = !opening;
    discToggle.setAttribute('aria-expanded', String(opening));
    discToggle.textContent = (opening ? '▾' : '▸') + ' Get the exact figure (Primavera F9)';
  });

  const showExact = (html) => { exactEl.hidden = false; exactEl.innerHTML = html; };
  const hasPy = (fn) => !!(window.pywebview && window.pywebview.api && typeof window.pywebview.api[fn] === 'function');

  q('gen').addEventListener('click', async () => {
    if (!hasPy('choose_save_path')) { showExact('<div class="pcp-wi-err">File dialogs are only available in the desktop app.</div>'); return; }
    const k = kindSel.value;
    if (needsActivity(k) && !selectedAct) { showExact('<div class="pcp-wi-err">Choose an activity first.</div>'); return; }
    const btn = q('gen'); btn.disabled = true;
    try {
      const out = await window.pywebview.api.choose_save_path('scenario.xml', 'xml');
      if (out) {
        const r = await postJSON('/api/chat/copilot/scenario', {
          snapshot_id: sid, xml_path: xml, cached_path: cached,
          kind: k, activity_id: selectedAct ? selectedAct.id : null,
          days: needsDays(k) ? (Number(daysInput.value) || 0) : null,
          output_path: out,
        });
        if (r && r.ok) {
          showExact(`<div class="pcp-wi-ok">Scenario saved${r.activity_name ? ' — ' + escapeHtml(r.activity_name) : ''}:</div>`
            + `<div class="pcp-wi-path">${escapeHtml(r.output_path || out)}</div>`
            + `<ol class="pcp-wi-steps"><li>Open <b>${escapeHtml(r.label || 'the scenario file')}</b> in Primavera P6.</li><li>Press <b>F9</b> to reschedule.</li><li>Re-export the schedule to XML.</li><li>Load it below for the exact figure.</li></ol>`);
        } else {
          showExact(`<div class="pcp-wi-err">${escapeHtml((r && r.error) || 'Could not write the scenario file.')}</div>`);
        }
      }
    } catch (e) {
      showExact(`<div class="pcp-wi-err">${escapeHtml('Could not create the scenario: ' + String((e && e.message) || e))}</div>`);
    } finally { btn.disabled = false; }
  });

  q('load').addEventListener('click', async () => {
    if (!hasPy('choose_file')) { showExact('<div class="pcp-wi-err">File dialogs are only available in the desktop app.</div>'); return; }
    const btn = q('load'); btn.disabled = true;
    try {
      const f = await window.pywebview.api.choose_file();
      if (f) {
        const r = await postJSON('/api/chat/copilot/impact', { snapshot_id: sid, xml_path: xml, cached_path: cached, rescheduled_path: f });
        if (r && r.ok) {
          const im = r.impact || {};
          const d = im.impact_days;
          const dcls = d == null ? 'mut' : (Number(d) < 0 ? 'good' : Number(d) > 0 ? 'bad' : 'mut');
          const fig = d == null ? '—' : (Number(d) > 0 ? '+' : '') + d + ' wd';
          showExact(`<div class="pcp-wi-exactfig">Exact figure (Primavera F9): <b class="${dcls}">${escapeHtml(fig)}</b></div>`
            + ((im.before_finish || im.after_finish) ? `<div class="pcp-wi-basis">${escapeHtml(String(im.before_finish || '?'))} → ${escapeHtml(String(im.after_finish || '?'))}</div>` : ''));
        } else {
          showExact(`<div class="pcp-wi-err">${escapeHtml((r && r.error) || 'Could not read the rescheduled file.')}</div>`);
        }
      }
    } catch (e) {
      showExact(`<div class="pcp-wi-err">${escapeHtml('Could not load the file: ' + String((e && e.message) || e))}</div>`);
    } finally { btn.disabled = false; }
  });

  return panel;
}

// report → embed the returned one-page manager's briefing (full HTML) in an iframe
function renderManagerReport(html) {
  const wrap = document.createElement('div');
  wrap.className = 'pcp-card';
  const note = document.createElement('div');
  note.className = 'pcp-report-note';
  note.textContent = "One-page manager's briefing — export to PDF from the report.";
  wrap.appendChild(note);
  const frame = document.createElement('iframe');
  frame.className = 'pcp-report-frame';
  frame.srcdoc = String(html || '');
  wrap.appendChild(frame);
  return wrap;
}

// Route a tagged Copilot library question to its deterministic backend and render
// the answer in the thread — mirrors askDashboard (BUSY guard + try/finally).
async function askCopilot(cap, qid, mode, question) {
  if (BUSY) return;
  BUSY = true; setSendEnabled(false);
  try {
    addUser(question);
    const bodyEl = addAiShell();
    if (!bodyEl) return;
    const think = bodyEl.querySelector('.pchat-think');
    if (think) think.innerHTML = '<span class="d"></span><span class="d"></span><span class="d"></span> Analysing your schedule…';
    ensureCopilotCss();
    const sid = state.currentSnapshotId || null;
    const xml = state.currentXmlPath || '';
    const cached = state.currentCachedPath || null;

    let resp;
    try {
      if (cap === 'assistant') {
        resp = await postJSON('/api/chat/copilot/ask', { snapshot_id: sid, question_id: qid, mode: mode || 'management' });
      } else if (cap === 'tia') {
        resp = await postJSON('/api/chat/copilot/tia', { snapshot_id: sid });
      } else if (cap === 'report') {
        resp = await postJSON('/api/chat/copilot/report', { snapshot_id: sid, xml_path: xml, cached_path: cached, preview: true });
      } else if (cap === 'whatif') {
        resp = { ok: true };            // interactive — no immediate POST
      } else {
        resp = { ok: false, error: 'This analysis is not available.' };
      }
    } catch (e) {
      resp = { ok: false, error: 'The Copilot engine was unreachable: ' + String((e && e.message) || e) };
    }

    if (think) think.remove();
    if (!resp || !resp.ok) {
      const pe = document.createElement('div'); pe.className = 'pchat-stream';
      pe.textContent = (resp && resp.error) || 'I could not complete this analysis.';
      bodyEl.appendChild(pe);
    } else {
      if (cap === 'assistant') bodyEl.appendChild(renderAssistant(resp.answer || {}));
      else if (cap === 'tia') bodyEl.appendChild(renderTia(resp.tia || {}, resp.insights || []));
      else if (cap === 'report') bodyEl.appendChild(renderManagerReport(resp.html || ''));
      else if (cap === 'whatif') bodyEl.appendChild(renderWhatif());
      const foot = document.createElement('div'); foot.className = 'pchat-foot';
      foot.innerHTML = `🔒 <span><b>Grounded</b> — computed on your PC from this project.</span>`;
      bodyEl.appendChild(foot);
    }
    scrollThread();
  } catch (_) {
    /* best-effort — the finally still frees the composer even if rendering threw */
  } finally {
    BUSY = false; setSendEnabled(true);
  }
}

// ── v2: the 15 merged questions ──────────────────────────────────────────────
// One comprehensive, grounded answer per merged question (/api/chat/qa2), rendered like a
// thinking assistant. The HTML is built by PURE functions (answerV2Html / thinkingHtml /
// libraryHtml / clarifyHtml — unit-tested in node); the DOM side only animates the reveal.
function ensureV2Css() {
  if (document.getElementById('pv2-css')) return;
  const s = document.createElement('style');
  s.id = 'pv2-css';
  s.textContent = `
  .pv2{color:var(--text);font-size:14px;line-height:1.6;min-width:0}
  .pv2 p{margin:0 0 9px}
  .pv2-think{border:1px solid var(--border);border-radius:10px;background:var(--hair);margin:0 0 12px;font-size:12.5px;color:var(--muted);max-width:660px}
  .pv2-think>summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:7px;padding:6px 11px;border-radius:10px;user-select:none}
  .pv2-think>summary::-webkit-details-marker{display:none}
  .pv2-think>summary::before{content:'\\25B8';font-size:11px;color:var(--muted)}
  .pv2-think[open]>summary::before{content:'\\25BE'}
  .pv2-think-sum{font-weight:650}
  .pv2-thinking .pv2-think-sum::after{content:'';display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--accent);margin-left:8px;vertical-align:1px;animation:pchatbob 1s infinite}
  .pv2-steps{list-style:none;margin:0;padding:0 12px 8px 27px}
  .pv2-step{display:flex;gap:8px;align-items:baseline;margin:2px 0;color:var(--ink-soft)}
  .pv2-tick{color:var(--success,#15803d);font-weight:800;flex:0 0 auto}
  .pv2-kicker{font-size:11.5px;color:var(--muted);margin:0 0 3px}
  .pv2-kicker .g{font-size:10.5px;font-weight:800;letter-spacing:.5px;text-transform:uppercase;color:var(--accent-dark)}
  .pv2-lead{font-weight:700;color:var(--text);margin:0 0 4px}
  .pv2-verdict{font-size:16px;font-weight:700;line-height:1.45;margin:0 0 2px;color:var(--text)}
  .pv2-pills{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 2px}
  .pv2-pill{display:inline-flex;align-items:center;font-size:12px;font-weight:650;padding:3px 10px;border-radius:999px;border:1px solid var(--border);background:var(--hair);color:var(--ink-soft)}
  .pv2-pill.danger{color:var(--danger,#c02626);background:color-mix(in srgb,var(--danger,#c02626) 12%,var(--card-bg));border-color:color-mix(in srgb,var(--danger,#c02626) 32%,var(--card-bg))}
  .pv2-pill.warning{color:var(--warning,#b45309);background:color-mix(in srgb,var(--warning,#b45309) 13%,var(--card-bg));border-color:color-mix(in srgb,var(--warning,#b45309) 32%,var(--card-bg))}
  .pv2-pill.success{color:var(--success,#15803d);background:color-mix(in srgb,var(--success,#15803d) 12%,var(--card-bg));border-color:color-mix(in srgb,var(--success,#15803d) 32%,var(--card-bg))}
  .pv2-pill.accent{color:var(--accent-dark);background:color-mix(in srgb,var(--accent) 12%,var(--card-bg));border-color:color-mix(in srgb,var(--accent) 32%,var(--card-bg))}
  .pv2-covers{margin:12px 0 4px;padding:8px 12px;background:var(--hair);border:1px solid var(--border);border-radius:9px;font-size:12.5px;color:var(--ink-soft);max-width:660px}
  .pv2-covers .ch{font-size:10.5px;font-weight:750;letter-spacing:.4px;text-transform:uppercase;color:var(--muted);margin-bottom:3px}
  .pv2-covers ol{margin:0;padding-left:18px}.pv2-covers li{margin:1px 0}
  .pv2-seclabel{font-size:12.5px;font-weight:750;color:var(--accent-dark);margin:16px 0 5px}
  .pv2-tablewrap{overflow-x:auto;margin:4px 0 10px}
  .pv2-table{width:100%;border-collapse:collapse;font-size:12.5px}
  .pv2-table th{text-align:left;font-weight:700;color:var(--muted);padding:5px 8px;font-size:11.5px;border-bottom:1px solid var(--border);white-space:nowrap}
  .pv2-table td{padding:6px 8px;border-top:1px solid var(--border);vertical-align:top;color:var(--text)}
  .pv2-table tbody tr:first-child td{border-top:0}
  .pv2-table .n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
  .pv2-table .nw{white-space:nowrap}
  .pv2-tnote{font-size:12px;color:var(--muted);margin:7px 2px 0}
  .pv2-focus{border:1px solid color-mix(in srgb,var(--accent) 40%,var(--border));border-left:4px solid var(--accent);background:color-mix(in srgb,var(--accent) 8%,var(--card-bg));border-radius:10px;padding:11px 14px;margin:0 0 14px}
  .pv2-focus-q{font-size:12.5px;color:var(--ink-soft);margin-bottom:5px}
  .pv2-focus-q .k{font-weight:800;color:var(--accent-dark)}
  .pv2-focus-h{font-weight:700;color:var(--text)}
  .pv2-focus p:last-child{margin-bottom:0}
  .pv2-divider{display:flex;align-items:center;gap:10px;font-size:11.5px;font-weight:700;color:var(--muted);margin:4px 0 10px}
  .pv2-divider::before,.pv2-divider::after{content:'';flex:1 1 24px;height:1px;background:var(--border)}
  .pv2-spec{margin:18px 0 6px}
  .pv2-sq{border:1px solid var(--border);border-radius:9px;margin:6px 0;background:var(--card-bg)}
  .pv2-sq>summary{cursor:pointer;list-style:none;padding:8px 12px 8px 30px;position:relative;display:flex;flex-direction:column;gap:2px;border-radius:9px}
  .pv2-sq>summary::-webkit-details-marker{display:none}
  .pv2-sq>summary::before{content:'\\25B8';position:absolute;left:12px;top:8px;color:var(--muted);font-size:12px}
  .pv2-sq[open]>summary::before{content:'\\25BE'}
  .pv2-sq[open]>summary{border-bottom:1px solid var(--border);border-radius:9px 9px 0 0}
  .pv2-sq-flat{padding:8px 12px 8px 30px;display:flex;flex-direction:column;gap:2px}
  .pv2-sq-focus{border-color:var(--accent);box-shadow:0 0 0 2px color-mix(in srgb,var(--accent) 22%,transparent)}
  .pv2-sqq{font-size:12.5px;font-weight:650;color:var(--ink-soft)}
  .pv2-sqa{font-size:13.5px;color:var(--text)}
  .pv2-sqbody{padding:9px 14px 11px}
  .pv2-sqbody p{font-size:13.5px}
  .pv2-sqdo{color:var(--ink-soft)}
  .pv2-run,.pv2-tool{border:1px solid var(--accent);background:var(--accent);color:#fff;font:inherit;font-size:12.5px;font-weight:700;border-radius:9px;padding:7px 13px;cursor:pointer}
  .pv2-run:hover,.pv2-tool:hover{background:var(--accent-dark)}
  .pv2-tools{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 4px}
  .pv2-measured{border-left:3px solid var(--accent);background:color-mix(in srgb,var(--accent) 8%,var(--card-bg));border-radius:0 8px 8px 0;padding:9px 13px;margin:16px 0 12px}
  .pv2-mh{font-size:12px;font-weight:750;color:var(--accent-dark);margin-bottom:2px}
  .pv2-mb{font-size:13px;color:var(--ink-soft)}
  .pv2-acth{font-size:13px;font-weight:750;margin:4px 0 4px;color:var(--text)}
  .pv2-actions{margin:0 0 12px;padding-left:20px}.pv2-actions li{margin:0 0 4px}
  .pv2-evi{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px}
  .pv2-chip{font-size:12px;padding:4px 10px;border-radius:7px;background:var(--hair);border:1px solid var(--border);color:var(--ink-soft)}
  .pv2-chip b{color:var(--text);font-weight:700}
  .pv2-chiprow{display:flex;gap:7px;flex-wrap:wrap;align-items:center;border-top:1px solid var(--border);padding-top:10px;margin-top:8px}
  .pv2-chiplbl{font-size:11.5px;font-weight:700;color:var(--muted);margin-right:2px}
  .pv2-drill,.pv2-also,.pv2-sug{border:1px solid var(--border);background:transparent;color:var(--accent-dark);font:inherit;font-size:12.5px;border-radius:8px;padding:5px 11px;cursor:pointer;text-align:left;line-height:1.4}
  .pv2-drill:hover,.pv2-also:hover,.pv2-sug:hover{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 10%,transparent)}
  .pv2-clarify .pv2-chiprow{border-top:0;padding-top:0;margin:4px 0 10px}
  .pv2-muted{color:var(--muted);font-size:12.5px}
  .pv2-lq{margin:2px 0}
  .pv2-lqb{display:flex;flex-direction:column;gap:2px;width:100%;text-align:left;border:1px solid transparent;background:transparent;border-radius:9px;padding:8px 10px;cursor:pointer;font:inherit;color:var(--text)}
  .pv2-lqb:hover{background:var(--hair);border-color:var(--border)}
  .pv2-lqt{font-size:13px;font-weight:650;color:var(--text);line-height:1.4}
  .pv2-lqc{font-size:11.5px;color:var(--muted);line-height:1.45}
  .pv2-lsubs{margin:0 0 6px 14px;border-left:2px solid var(--border);padding-left:8px;display:flex;flex-direction:column;gap:1px}
  .pv2-lsub{text-align:left;border:0;background:transparent;font:inherit;font-size:12.3px;color:var(--ink-soft);padding:5px 8px;border-radius:7px;cursor:pointer;line-height:1.4}
  .pv2-lsub:hover{background:var(--hair);color:var(--text)}
  .pv2-lmore{font-size:11px;color:var(--muted);padding:2px 8px}
  .pchat-drawer mark,.pv2 mark{background:color-mix(in srgb,var(--accent) 22%,transparent);color:inherit;border-radius:3px;padding:0 1px}
  .pchat button:focus-visible,.pchat summary:focus-visible,.pchat [tabindex]:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  .pv2-pending{display:none!important}
  .pv2-in{animation:pv2in .26s ease both}
  @keyframes pv2in{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:none}}
  @media (prefers-reduced-motion:reduce){.pv2-in{animation:none}.pv2-thinking .pv2-think-sum::after{animation:none}}
  `;
  document.head.appendChild(s);
}

// The interactive tools an answer can offer, and the words used for them.
const V2_TOOLS = {
  dashboard: 'Build the dashboard',
  whatif: 'Run the what-if',
  tia: 'Run the time-impact analysis',
  report: "Manager's briefing",
};
const V2_TONES = ['danger', 'warning', 'success', 'accent', 'neutral'];
const arr = (x) => (Array.isArray(x) ? x : []);
const md = (s) => mdInline(s == null ? '' : String(s));
const norm = (s) => String(s == null ? '' : s).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();

// "Analysed your file · N steps" — the analysis the answer builder actually did. Final
// (collapsed) state; revealV2 animates it open, one step at a time, then collapses it.
export function thinkingHtml(steps) {
  const s = arr(steps).filter((x) => x != null && String(x).trim() !== '');
  if (!s.length) return '';
  const n = s.length;
  return `<details class="pv2-think" data-steps="${n}">`
    + `<summary><span class="pv2-think-sum">Analysed your file · ${n} step${n === 1 ? '' : 's'}</span></summary>`
    + `<ol class="pv2-steps">${s.map((x) => `<li class="pv2-step"><span class="pv2-tick" aria-hidden="true">✓</span><span>${md(x)}</span></li>`).join('')}</ol>`
    + '</details>';
}

// A table cell that reads as a number ("95%", "40% / 61%", "+60 wd (behind)", "370.4M") —
// dates ("02-May-2027") and ids ("CM.1020") do not.
const NUM_CELL = /^[+\-−~≈<>]?\s*\d[\d.,]*\s*(%|wd|d|days?|weeks?|wks?|pts?|M|k|x)?(\s*(\/|→|–|to)\s*[+\-−~≈<>]?\s*\d[\d.,]*\s*(%|wd|d|days?|M|k)?)?(\s*\([^)]*\))?$/i;
export function numericCols(cols, rows) {
  const width = Math.max(arr(cols).length, ...arr(rows).map((r) => arr(r).length), 0);
  const out = [];
  for (let i = 0; i < width; i++) {
    if (i === 0) { out.push(false); continue; }           // the row label stays left-aligned
    let seen = 0, bad = 0;
    arr(rows).forEach((r) => {
      const c = String(arr(r)[i] == null ? '' : arr(r)[i]).replace(/\*\*/g, '').trim();
      if (c === '' || c === '—' || c === '-') return;
      if (NUM_CELL.test(c)) seen++; else bad++;
    });
    out.push(seen > 0 && bad === 0);
  }
  return out;
}

function tableHtml(t) {
  if (!t || !arr(t.cols).length) return '';
  const cols = arr(t.cols), rows = arr(t.rows).map(arr);
  const num = numericCols(cols, rows);
  const cls = (i) => (num[i] ? ' class="n"' : '');
  // a single token (a date like 02-May-2027, an activity id) never breaks at its hyphens
  const tdCls = (i, c) => {
    const k = [num[i] ? 'n' : '', (!num[i] && c != null && String(c).trim() && !/\s/.test(String(c).trim())) ? 'nw' : ''].filter(Boolean);
    return k.length ? ` class="${k.join(' ')}"` : '';
  };
  const head = num.map((_, i) => `<th scope="col"${cls(i)}>${md(cols[i])}</th>`).join('');
  const body = rows.map((r) => '<tr>' + num.map((_, i) => `<td${tdCls(i, r[i])}>${md(r[i])}</td>`).join('') + '</tr>').join('');
  return `<div class="pv2-tablewrap pv2-rv"><table class="pv2-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`
    + (t.note ? `<div class="pv2-tnote">${md(t.note)}</div>` : '') + '</div>';
}

function toolButton(cap, label, cls, text) {
  if (!V2_TOOLS[cap]) return '';
  const lab = label || V2_TOOLS[cap];
  return `<button type="button" class="${cls}" data-v2tool="${escapeHtml(cap)}" data-label="${escapeHtml(lab)}" title="${escapeHtml(lab)}">${escapeHtml(text || lab)} ▸</button>`;
}

function specificHtml(spec, focusId) {
  if (!spec.length) return '';
  const rows = spec.map((s) => {
    const body = arr(s.body).filter(Boolean).map((p) => `<p>${md(p)}</p>`).join('');
    const adv = arr(s.advice).filter(Boolean);
    const run = toolButton(s.tool, null, 'pv2-run', 'Run it');
    const focused = !!(focusId && s.id === focusId);
    const qa = `<span class="pv2-sqq">${md(s.q)}</span>${s.headline ? `<span class="pv2-sqa">${md(s.headline)}</span>` : ''}`;
    if (!body && !adv.length && !run) {                   // nothing to expand — a plain row
      return `<div class="pv2-sq pv2-sq-flat${focused ? ' pv2-sq-focus' : ''}" data-sid="${escapeHtml(s.id || '')}">${qa}</div>`;
    }
    return `<details class="pv2-sq${focused ? ' pv2-sq-focus' : ''}" data-sid="${escapeHtml(s.id || '')}"${focused ? ' open' : ''}>`
      + `<summary>${qa}</summary><div class="pv2-sqbody">${body}`
      + (adv.length ? `<p class="pv2-sqdo"><b>What I'd do:</b> ${adv.map(md).join(' ')}</p>` : '')
      + run + '</div></details>';
  }).join('');
  return `<div class="pv2-spec pv2-rv"><div class="pv2-seclabel">Your questions, one by one — ${spec.length} from the library</div>${rows}</div>`;
}

// The full v2 answer card. `opts.asked` = what the user typed/clicked (the kicker then
// skips repeating the question when it is the same words).
export function answerV2Html(a, opts) {
  a = a || {};
  opts = opts || {};
  const spec = arr(a.specific).filter((s) => s && typeof s === 'object');
  const focusItem = a.focus ? spec.find((s) => s.id === a.focus) : null;
  const h = [];
  h.push(thinkingHtml(a.thinking));

  if (focusItem) {
    h.push(`<div class="pv2-focus pv2-rv" role="note"><div class="pv2-focus-q"><span class="k">You asked:</span> ${md(focusItem.q)}</div>`
      + (focusItem.headline ? `<p class="pv2-focus-h">${md(focusItem.headline)}</p>` : '')
      + arr(focusItem.body).filter(Boolean).map((p) => `<p>${md(p)}</p>`).join('')
      + '</div>');
    if (a.question) h.push(`<div class="pv2-divider pv2-rv"><span>The full answer — ${md(a.question)}</span></div>`);
  } else if (a.group || a.question) {
    const same = opts.asked && norm(opts.asked) === norm(a.question);
    h.push(`<div class="pv2-kicker pv2-rv">${a.group ? `<span class="g">${md(a.group)}</span>` : ''}`
      + (a.question && !same ? `${a.group ? ' · ' : ''}${md(a.question)}` : '') + '</div>');
  }

  if (a.followup === 'cause') h.push(`<p class="pv2-lead pv2-rv">Here's why:</p>`);
  else if (a.followup === 'expand') h.push(`<p class="pv2-lead pv2-rv">Here's the full picture:</p>`);

  if (a.verdict) h.push(`<p class="pv2-verdict pv2-rv">${md(a.verdict)}</p>`);

  const pills = arr(a.pills).filter((p) => p && p.text);
  if (pills.length) {
    h.push(`<div class="pv2-pills pv2-rv">${pills.map((p) =>
      `<span class="pv2-pill ${V2_TONES.indexOf(p.tone) >= 0 ? p.tone : 'neutral'}">${md(p.text)}</span>`).join('')}</div>`);
  }

  const covers = arr(a.covers).filter(Boolean);
  if (covers.length) {
    h.push(`<div class="pv2-covers pv2-rv"><div class="ch">${covers.length === 1 ? 'Answers this topic' : 'Answers these topics'}</div>`
      + `<ol>${covers.map((c) => `<li>${md(c)}</li>`).join('')}</ol></div>`);
  }

  arr(a.sections).filter(Boolean).forEach((s) => {
    const paras = arr(s.paras).filter(Boolean);
    const table = tableHtml(s.table);
    if (!paras.length && !table) return;
    h.push('<div class="pv2-sec">'
      + (s.label ? `<div class="pv2-seclabel pv2-rv">${md(s.label)}</div>` : '')
      + paras.map((p) => `<p class="pv2-rv">${md(p)}</p>`).join('')
      + table + '</div>');
  });

  h.push(specificHtml(spec, focusItem ? focusItem.id : null));

  const tools = arr(a.tools).filter((t) => t && V2_TOOLS[t.cap]);
  if (tools.length) h.push(`<div class="pv2-tools pv2-rv">${tools.map((t) => toolButton(t.cap, t.label, 'pv2-tool')).join('')}</div>`);

  if (a.measured) {
    h.push(`<div class="pv2-measured pv2-rv"><div class="pv2-mh">How this is measured — from your P6</div><div class="pv2-mb">${md(a.measured)}</div></div>`);
  }
  const actions = arr(a.actions).filter(Boolean);
  if (actions.length) h.push(`<div class="pv2-rv"><div class="pv2-acth">What I'd do</div><ul class="pv2-actions">${actions.map((x) => `<li>${md(x)}</li>`).join('')}</ul></div>`);

  const evidence = arr(a.evidence).filter((e) => e && (e.k || e.v));
  if (evidence.length) h.push(`<div class="pv2-evi pv2-rv">${evidence.map((e) => `<span class="pv2-chip"><b>${md(e.k)}</b> ${md(e.v)}</span>`).join('')}</div>`);

  const drills = arr(a.drilldowns).filter((d) => d && d.to && d.text);
  if (drills.length) {
    h.push(`<div class="pv2-chiprow pv2-rv"><span class="pv2-chiplbl">Drill in</span>${drills.map((d) =>
      `<button type="button" class="pv2-drill" data-v2ask="${escapeHtml(d.to)}" data-q="${escapeHtml(d.text)}">${md(d.text)} →</button>`).join('')}</div>`);
  }
  const also = arr(a.also).filter((x) => x && x.id && x.q);
  if (also.length) {
    h.push(`<div class="pv2-chiprow pv2-rv"><span class="pv2-chiplbl">Also related</span>${also.map((x) =>
      `<button type="button" class="pv2-also" data-v2ask="${escapeHtml(x.id)}" data-q="${escapeHtml(x.q)}">${md(x.q)}</button>`).join('')}</div>`);
  }

  h.push('<div class="pchat-foot pv2-rv">🔒 <span><b>Grounded</b> — computed on your PC from this project · no AI model needed.</span></div>');
  return h.join('');
}

// Nothing matched a typed question — reply like an assistant would: say so, offer the
// closest merged questions as clickable chips, and point to the library. `opts.related`
// turns it into a short "I can also answer…" row under a model answer.
export function clarifyHtml(suggest, opts) {
  opts = opts || {};
  const items = arr(suggest).filter((x) => x && x.id && x.q);
  const n = opts.count || 15;
  const chips = items.length
    ? `<div class="pv2-chiprow">${items.map((x) =>
        `<button type="button" class="pv2-sug" data-v2ask="${escapeHtml(x.id)}" data-q="${escapeHtml(x.q)}">${md(x.q)}</button>`).join('')}</div>`
    : '';
  const browse = `<button type="button" class="pchat-linkbtn" data-browse="1">browse all ${n} questions</button>`;
  if (opts.related) {
    return items.length ? `<div class="pv2"><div class="pv2-chiprow"><span class="pv2-chiplbl">From your file I can also answer</span>${items.map((x) =>
      `<button type="button" class="pv2-sug" data-v2ask="${escapeHtml(x.id)}" data-q="${escapeHtml(x.q)}">${md(x.q)}</button>`).join('')}</div></div>` : '';
  }
  let html = '<div class="pv2 pv2-clarify">';
  if (opts.error) html += `<p class="pv2-muted">I couldn't reach the answer engine just now (${escapeHtml(opts.error)}).</p>`;
  if (items.length) {
    html += `<p>I'm not sure which you mean — did you mean${items.length === 1 ? ' this' : ' one of these'}?</p>${chips}`
      + `<p class="pv2-muted">Or say it another way — mention the finish, float, cost, manpower or a claim — or ${browse}.</p>`;
  } else {
    html += `<p>I'm not sure which you mean. Could you say it another way — for example mention the finish date, float, cost, manpower or a claim? Or ${browse} and pick the closest.</p>`;
  }
  return html + '</div>';
}

// ── the drawer library (15 questions, searchable down to their 182 sub-questions) ──
function searchWords(term) {
  return String(term || '').toLowerCase().replace(/[^\p{L}\p{N}%'’\-\s]+/gu, ' ').split(/\s+/).filter(Boolean);
}
const matchAll = (text, words) => { const t = String(text || '').toLowerCase(); return words.every((w) => t.indexOf(w) >= 0); };
const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
function highlight(text, re) {
  const s = String(text == null ? '' : text);
  if (!re) return escapeHtml(s);
  return s.split(re).map((p, i) => (i % 2 ? `<mark>${escapeHtml(p)}</mark>` : escapeHtml(p))).join('');
}
const SUB_HITS_SHOWN = 6;

export function libraryHtml(lib, term) {
  const qs = arr(lib && lib.questions).filter((q) => q && q.id);
  if (!qs.length) return '<div class="pchat-nomatch">The question library is empty.</div>';
  const groups = arr(lib && lib.groups).slice();
  qs.forEach((q) => { if (groups.indexOf(q.group || 'Other') < 0) groups.push(q.group || 'Other'); });
  const words = searchWords(term);
  const re = words.length ? new RegExp('(' + words.slice().sort((x, y) => y.length - x.length).map(reEsc).join('|') + ')', 'gi') : null;
  let shown = 0;
  const html = groups.map((g) => {
    const rows = qs.filter((q) => (q.group || 'Other') === g).map((q) => {
      const covers = arr(q.covers).filter((c) => c && norm(q.q).indexOf(norm(c)) < 0);
      const hitQ = !words.length || matchAll(q.q + ' ' + arr(q.covers).join(' '), words);
      const subs = words.length ? arr(q.originals).filter((o) => o && o.q && matchAll(o.q, words)) : [];
      if (!hitQ && !subs.length) return '';
      shown++;
      const line = covers.length ? highlight(covers.join(' · '), re)
        : escapeHtml(`Answers ${arr(q.originals).length} questions from the library`);
      const more = subs.length - SUB_HITS_SHOWN;
      return `<div class="pv2-lq"><button type="button" class="pv2-lqb" data-v2ask="${escapeHtml(q.id)}" data-q="${escapeHtml(q.q)}">`
        + `<span class="pv2-lqt">${highlight(q.q, re)}</span><span class="pv2-lqc">${line}</span></button>`
        + (subs.length ? `<div class="pv2-lsubs">${subs.slice(0, SUB_HITS_SHOWN).map((o) =>
            `<button type="button" class="pv2-lsub" data-v2ask="${escapeHtml(q.id)}" data-focus="${escapeHtml(o.id || '')}" data-q="${escapeHtml(o.q)}"><span aria-hidden="true">↳</span> ${highlight(o.q, re)}</button>`).join('')}`
          + (more > 0 ? `<div class="pv2-lmore">+ ${more} more — refine your search</div>` : '') + '</div>' : '')
        + '</div>';
    }).join('');
    return rows ? `<div class="pchat-theme"><h4>${escapeHtml(g)}</h4>${rows}</div>` : '';
  }).join('');
  if (shown) return html;
  const t = String(term || '').trim();
  return `<div class="pchat-nomatch">Nothing in the library matches “${escapeHtml(t)}”.<br>`
    + `<button type="button" class="pchat-linkbtn" data-asktext="${escapeHtml(t)}">Ask it in the chat anyway</button> — I'll work out which answer fits.</div>`;
}

// ── special typed intents (before the v2 router) ─────────────────────────────
// "run a time impact analysis", "what if we delay the piling 10 days?", "give me a manager's
// briefing" → the existing interactive Copilot tools. A question that merely mentions a word
// ("is the briefing date at risk?") still goes to the answer engine.
export function copilotIntent(q) {
  const s = String(q || '').trim();
  if (!s) return null;
  const verb = '\\b(?:run|do|start|open|create|build|make|generate|give|show|produce|prepare|draw|need|want|perform|try|launch)\\b[\\s\\S]{0,40}';
  const has = (noun) => new RegExp(verb + noun, 'i').test(s) || new RegExp('^\\s*(?:a|an|the|my)?\\s*' + noun + '\\s*[.!?]*\\s*$', 'i').test(s);
  if (/\btime[\s-]*impact\b/i.test(s) || /\bTIA\b/.test(s)) return 'tia';
  if (/\bmanager['’]?s?\s+briefing\b/i.test(s) || has('(?:\\b(?:management|executive|exec|weekly)\\s+)?\\bbriefing\\b')) return 'report';
  if (has('\\bwhat[\\s-]*if\\b')) return 'whatif';
  if (/^\s*what[\s-]*if\b[\s\S]*\b(?:delay|shorten|crash|add(?:ed)?\s+(?:a\s+|an?\s+extra\s+|more\s+)?crews?|more\s+crews?|overtime|six[\s-]*day|6[\s-]*day|remove|drop)\b/i.test(s)) return 'whatif';
  if (/^\s*what[\s-]*if(?:\s+(?:analysis|scenario|study))?\s*[.!?]*\s*$/i.test(s)) return 'whatif';
  return null;
}

// ── the reveal (DOM) ─────────────────────────────────────────────────────────
function reducedMotion() {
  try { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); } catch (_) { return false; }
}
// Keep the new content in view while it streams — but stop once the question reaches the
// top, so a long answer never scrolls its own start away.
function followTo(anchor) {
  const t = thread(); if (!t || !anchor) return;
  const top = t.scrollTop + anchor.getBoundingClientRect().top - t.getBoundingClientRect().top - 8;
  const bottom = t.scrollHeight - t.clientHeight;
  t.scrollTop = Math.max(t.scrollTop, Math.min(bottom, top));
}
function revealV2(card, anchor) {
  if (REVEAL) REVEAL.finish();
  if (reducedMotion()) { followTo(anchor); return; }
  const think = card.querySelector('.pv2-think');
  const steps = think ? [...think.querySelectorAll('.pv2-step')] : [];
  const sum = think ? think.querySelector('.pv2-think-sum') : null;
  const finalSum = sum ? sum.textContent : '';
  const units = [...card.querySelectorAll('.pv2-rv')];
  const timers = [];
  let done = false;
  const collapse = () => { if (think) { think.open = false; think.classList.remove('pv2-thinking'); if (sum) sum.textContent = finalSum; } };
  const finish = () => {
    if (done) return; done = true;
    timers.forEach(clearTimeout);
    steps.concat(units).forEach((u) => u.classList.remove('pv2-pending'));
    collapse();
    if (REVEAL && REVEAL.card === card) REVEAL = null;
  };
  REVEAL = { card, finish };
  units.forEach((u) => u.classList.add('pv2-pending'));
  if (think) {
    think.open = true; think.classList.add('pv2-thinking');
    steps.forEach((s) => s.classList.add('pv2-pending'));
    if (sum) sum.textContent = 'Analysing your file…';
  }
  const show = (u) => { u.classList.remove('pv2-pending'); u.classList.add('pv2-in'); followTo(anchor); };
  const at = (ms, fn) => timers.push(setTimeout(() => { if (!done) fn(); }, ms));
  let t = 0;
  steps.forEach((s) => { t += 220; at(t, () => show(s)); });
  if (think) { t += 280; at(t, collapse); }
  const gap = units.length ? Math.max(45, Math.min(120, Math.floor(4200 / units.length))) : 120;   // long answers stay under ~4 s
  units.forEach((u) => { t += gap; at(t, () => show(u)); });
  at(t + 20, finish);
  followTo(anchor);
}

function libCount() {
  return (LIB2 && LIB2.counts && LIB2.counts.questions) || (LIB2 && arr(LIB2.questions).length) || 15;
}

// Put a v2 answer into an AI turn and reveal it. Remembers the topic for follow-ups.
function showV2(bodyEl, resp, asked) {
  ensureV2Css();
  const a = (resp && resp.answer) || {};
  if (resp && resp.matched && a.id) LAST_QID = a.id;
  const card = document.createElement('div');
  card.className = 'pv2';
  card.innerHTML = answerV2Html(a, { asked });
  bodyEl.appendChild(card);
  const turn = bodyEl.closest('.pchat-turn');
  revealV2(card, (turn && turn.previousElementSibling) || turn);
}

// A merged question (drawer click, drill-in / also-related / suggestion chip) → /api/chat/qa2.
// `opts.focus` = the original sub-question id when the user picked a sub-question.
async function askV2(qid, text, opts) {
  if (BUSY || !qid) return;
  opts = opts || {};
  BUSY = true; setSendEnabled(false);
  try {
    const asked = text || qid;
    addUser(asked);
    const bodyEl = addAiShell();
    if (!bodyEl) return;
    const think = bodyEl.querySelector('.pchat-think');
    const body = { snapshot_id: state.currentSnapshotId || null, question_id: qid, mode: V2_MODE };
    if (opts.focus) body.focus = opts.focus;
    if (opts.followup) body.followup = opts.followup;
    let r;
    try { r = await postJSON('/api/chat/qa2', body); } catch (e) {
      r = { ok: false, error: 'The answer engine was unreachable: ' + String((e && e.message) || e) };
    }
    if (think) think.remove();
    if (!r || !r.ok || !r.answer) {
      const pe = document.createElement('div'); pe.className = 'pchat-stream';
      pe.textContent = (r && r.error) || 'I could not answer that one.';
      bodyEl.appendChild(pe);
      scrollThread();
    } else {
      showV2(bodyEl, r, asked);
    }
  } catch (_) {
    /* best-effort — finally frees the composer even if rendering threw */
  } finally {
    BUSY = false; setSendEnabled(true);
  }
}

// A tool button inside an answer → the existing dashboard / Copilot paths.
function runV2Tool(cap, label) {
  if (cap === 'dashboard') return askDashboard(label || 'Create a professional dashboard');
  if (cap === 'whatif' || cap === 'tia' || cap === 'report') return askCopilot(cap, null, V2_MODE, label || V2_TOOLS[cap]);
  return null;
}

function answerFooter(out) {
  const foot = document.createElement('div'); foot.className = 'pchat-foot';
  if (out.source === 'brain') {
    foot.innerHTML = `🔒 <span><b>Grounded</b> — answered on your PC from this project's analysis${out.brain && out.brain.model_name ? ' · ' + escapeHtml(out.brain.model_name) : ''}.</span>`;
  } else if (out.needs_setup) {
    foot.innerHTML = `<span>Set up the offline AI brain for full, detailed answers.</span>`;
    const b = document.createElement('button'); b.className = 'pchat-btn'; b.style.marginLeft = '8px';
    b.textContent = 'Set up the AI brain'; b.addEventListener('click', setupBrain);
    foot.appendChild(b);
  }
  return (foot.textContent || foot.querySelector('button')) ? foot : null;
}

function setSendEnabled(on) {
  const b = document.getElementById('pchat-send'); if (b) b.disabled = !on;
}

// Ask a typed question. Special intents first (dashboard → the dashboard; what-if / time
// impact / manager's briefing → the Copilot tools), then the v2 router (/api/chat/ask2),
// which lands it on one of the 15 merged answers — with the matching sub-question in focus,
// and short follow-ups ("why?", "more detail") continuing from LAST_QID. Unmatched: the
// offline AI brain if it's set up, otherwise an honest "did you mean…?" with suggestions.
async function ask(question) {
  if (BUSY || !question || !question.trim()) return;
  const question0 = question.trim();
  if (isDashboardIntent(question0)) { return askDashboard(question0); }
  const cap = copilotIntent(question0);
  if (cap) { return askCopilot(cap, null, V2_MODE, question0); }
  BUSY = true; setSendEnabled(false);
  try {
    addUser(question0);
    const bodyEl = addAiShell();
    if (!bodyEl) return;
    const think = bodyEl.querySelector('.pchat-think');

    let r;
    try {
      r = await postJSON('/api/chat/ask2', {
        snapshot_id: state.currentSnapshotId || null, question_text: question0,
        mode: V2_MODE, last_qid: LAST_QID,
      });
    } catch (e) {
      r = { ok: false, error: String((e && e.message) || e) };
    }
    if (r && r.ok && r.answer) {                     // routed — the full grounded answer
      if (think) think.remove();
      showV2(bodyEl, r, question0);
      return;
    }
    const suggest = (r && r.ok && Array.isArray(r.suggest)) ? r.suggest : [];
    if (BRAIN && BRAIN.ready) {                      // open-ended → the offline AI brain
      await streamModelAnswer(bodyEl, think, question0);
      const rel = clarifyHtml(suggest, { related: true });
      if (rel) { ensureV2Css(); const d = document.createElement('div'); d.innerHTML = rel; bodyEl.appendChild(d.firstElementChild); scrollThread(); }
      return;
    }
    if (think) think.remove();
    ensureV2Css();
    const d = document.createElement('div');
    d.innerHTML = clarifyHtml(suggest, { count: libCount(), error: (r && !r.ok) ? (r.error || 'no reply') : null });
    bodyEl.appendChild(d.firstElementChild);
    scrollThread();
  } catch (_) {
    /* best-effort — the finally still frees the composer even if rendering threw */
  } finally {
    BUSY = false; setSendEnabled(true);
  }
}

// The offline AI brain's free-form answer — streamed live (NDJSON) so long answers appear
// as they're written, then charts + the grounded footer. Caller holds BUSY.
async function streamModelAnswer(bodyEl, think, question0) {
  let ansEl = null, caret = null, raw = '', meta = null;
  const ensureAns = () => {
    if (ansEl) return;
    if (think) think.remove();
    ansEl = document.createElement('div'); ansEl.className = 'pchat-stream';
    bodyEl.appendChild(ansEl);
    caret = document.createElement('span'); caret.className = 'pchat-caret';
  };
  const paint = () => { ansEl.textContent = raw; ansEl.appendChild(caret); scrollThread(); };
  try {
    const resp = await fetch(api('/api/chat/ask'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: question0, role: null,
        snapshot_id: state.currentSnapshotId || null, result: state.currentResult || null }),
    });
    const ct = resp.headers.get('Content-Type') || '';
    if (ct.indexOf('ndjson') < 0) {                    // a plain JSON (e.g. validation) reply
      const j = await resp.json(); ensureAns();
      raw = (j && (j.answer || j.error)) || 'Something went wrong.'; meta = j; paint();
    } else {
      const reader = resp.body.getReader(); const dec = new TextDecoder(); let buf = '';
      for (;;) {
        const { value, done } = await reader.read(); if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
          if (!line) continue;
          let obj; try { obj = JSON.parse(line); } catch (_) { continue; }
          if (obj.delta != null) { ensureAns(); raw += obj.delta; paint(); }
          else if (obj.done) { meta = obj; }
        }
      }
    }
  } catch (e) {
    ensureAns(); raw += (raw ? '\n\n' : '') + 'Sorry — the local engine was unreachable: ' + String((e && e.message) || e);
  }
  ensureAns();
  if (caret) caret.remove();
  ansEl.className = ''; ansEl.innerHTML = mdToHtml(raw);
  const out = meta || {};
  if (out.charts && out.charts.length) bodyEl.appendChild(renderCharts(out.charts));
  const foot = answerFooter(out); if (foot) bodyEl.appendChild(foot);
  if (out.brain) { BRAIN = out.brain; renderBrainPill(); }
  scrollThread();
}

// ── brain status / setup ─────────────────────────────────────────────────────
function renderBrainPill() {
  const ready = BRAIN && BRAIN.ready;
  const cls = 'pchat-pill ' + (ready ? 'ready' : 'off');
  const html = `<span class="dot"></span>${ready ? 'AI brain ready' : 'AI brain — optional'}`;
  ['pchat-brainpill', 'pchat-brainpill-top'].forEach((id) => {
    const el = document.getElementById(id); if (el) { el.className = cls; el.innerHTML = html; }
  });
  const setup = document.getElementById('pchat-setup');
  if (setup) setup.hidden = !!ready;
  const note = document.getElementById('pchat-setup-note');
  if (note && BRAIN) {
    if (BRAIN.downloading) note.textContent = 'Downloading the AI model… ' + (BRAIN.progress != null ? BRAIN.progress + '%' : '');
    else if (BRAIN.detail) note.textContent = BRAIN.detail;
  }
  renderModels();
}

function renderModels() {
  const el = document.getElementById('pchat-models');
  if (!el || !BRAIN || !BRAIN.options) return;
  const dis = BRAIN.downloading ? ' disabled' : '';
  el.innerHTML = BRAIN.options.map((o) =>
    `<button class="pchat-mchip ${o.key === BRAIN.model_key ? 'on' : ''}" data-model="${o.key}"${dis}>${escapeHtml(o.label)}<span class="sz">${escapeHtml(o.size)}${o.downloaded ? ' · downloaded' : ''}</span></button>`).join('');
}

async function selectModel(key) {
  if (BRAIN && BRAIN.downloading) return;              // don't repoint the brain mid-download
  try {
    const d = await postJSON('/api/chat/settings', { model: key });
    if (d && d.brain) BRAIN = d.brain;
  } catch (_) { /* offline */ }
  renderBrainPill();
}

async function refreshStatus() {
  try { const d = await getJSON('/api/chat/status'); BRAIN = d.brain || BRAIN; } catch { /* offline */ }
  renderBrainPill();
}

async function setupBrain() {
  const btns = document.querySelectorAll('#pchat-setup .pchat-btn, .pchat-foot .pchat-btn');
  btns.forEach((b) => { b.disabled = true; });
  const note = document.getElementById('pchat-setup-note');
  try {
    const d = await postJSON('/api/chat/setup', {});
    if (note) note.textContent = d.note || 'Setting up the AI brain…';
  } catch {
    if (note) note.textContent = 'Could not start setup — is the local AI runtime installed?';
  }
  if (POLL) clearInterval(POLL);
  POLL = setInterval(async () => {
    await refreshStatus();
    if (BRAIN && BRAIN.ready) { clearInterval(POLL); POLL = null; btns.forEach((b) => { b.disabled = false; }); }
  }, 5000);
}

function setupCardHtml() {
  const b = BRAIN || {};
  return `<div class="pchat-setup" id="pchat-setup" ${b.ready ? 'hidden' : ''}>
    <h3>Optional — add the offline AI brain for free-form questions</h3>
    <p>The chat already answers the built-in analyses (why the project is delayed, risks, recovery, the dashboard, a time-impact analysis, a manager's briefing, EOT/claim…) with <b>no download</b>. Add the offline AI brain only if you also want to type <b>free-form</b> questions and get written answers — a real AI that runs entirely on your PC (no internet, no key, no cost, <b>nothing to install</b>) after a one-time model download here.</p>
    <div class="pchat-rolelbl" style="text-align:left">Choose the AI brain — bigger is smarter &amp; more detailed, smaller is faster</div>
    <div class="pchat-models" id="pchat-models"></div>
    <div class="row">
      <button class="pchat-btn" id="pchat-setup-btn">Download the AI brain now</button>
      <span class="pchat-pill" id="pchat-brainpill"><span class="dot"></span>checking…</span>
    </div>
    <p id="pchat-setup-note" style="margin-top:9px;font-size:12px">${escapeHtml(b.detail || '')}</p>
  </div>`;
}

// ── library (the 15 merged questions, in the drawer) ─────────────────────────
function renderLib2() {
  const el = document.getElementById('pchat-libbody'); if (!el) return;
  if (!LIB2) {
    el.innerHTML = `<div class="pchat-nomatch">The question library couldn't load just now — you can still type your question below and I'll find the right answer.</div>`;
    return;
  }
  el.innerHTML = libraryHtml(LIB2, (document.getElementById('pchat-search') || {}).value || '');
}

// ── suggestions (empty-state cards + strip chips) ────────────────────────────
// Exactly six curated starters. Each routes to a deterministic engine that matches
// a library entry: those with a `cap` go to askCopilot(cap,qid,mode,q); the rest to
// ask(q) — which covers "Create a professional dashboard" via the dashboard-intent.
const SUGGESTIONS = [
  { icon: '📉', q: 'Why is the project delayed?',          cap: 'assistant', qid: 'why_delayed', mode: 'management', sub: 'to-date / performance read' },
  { icon: '📊', q: 'Create a professional dashboard',       cap: null,                                                 sub: 'one-page EVM command board' },
  { icon: '⏱', q: 'Run a time impact analysis',            cap: 'tia',                                                sub: 'finish-slip decomposition' },
  { icon: '📋', q: "Give me a manager's briefing",          cap: 'report',                                             sub: 'exec one-pager + S-curve' },
  { icon: '⚠️', q: 'What are the biggest risks right now?', cap: 'assistant', qid: 'risks',       mode: 'management', sub: 'slip · out-of-sequence · float' },
  { icon: '⚖️', q: 'Is there an EOT / claim case?',         cap: 'assistant', qid: 'eot_likely',  mode: 'planning',   sub: 'honest indicators + method' },
];

// Shared data-* so the ONE delegated handler routes cards and chips identically.
function sugAttrs(x) {
  return 'data-sug="1"'
    + (x.cap ? ` data-cap="${escapeHtml(x.cap)}"` : '')
    + (x.qid ? ` data-qid="${escapeHtml(x.qid)}"` : '')
    + (x.mode ? ` data-mode="${escapeHtml(x.mode)}"` : '')
    + ` data-q="${escapeHtml(x.q)}"`;
}
function sugCardsHtml() {
  return SUGGESTIONS.map((x) =>
    `<button class="pchat-sugcard" ${sugAttrs(x)}>
       <span class="ic">${x.icon}</span>
       <span class="t">${escapeHtml(x.q)}</span>
       <span class="s">${escapeHtml(x.sub || '')}</span>
     </button>`).join('');
}
function sugStripHtml(count) {
  // Questions live only in the drawer now — the strip above the composer is just a
  // persistent opener for the full library (no on-screen question suggestions).
  return `<button type="button" class="pchat-chipsug browse" data-browse="1"><span>Browse all <span class="pchat-browsecount">${escapeHtml(count || 15)}</span> questions ▸</span></button>`;
}
// The greeting — clean: no question cards, no role picker; one way into the library.
export function welcomeHtml(count) {
  return `<div class="pchat-empty pchat-welcome">
    <div class="pchat-cta-mk">✦</div>
    <div class="pchat-greet">Hi — I'm your offline planning manager.</div>
    <div class="pchat-greet-sub">Drag a <b>.xer</b> or <b>.xml</b> P6 export anywhere here, or <button type="button" class="pchat-linkbtn" id="pchat-attach-cta">📎 choose a file</button>. Then ask me in your own words, or pick one of the questions from the library. Offline — nothing leaves your PC.</div>
    <div class="pchat-welcome-foot">
      <button type="button" class="pchat-browse pchat-browse-lg" data-browse="1">Browse all <span class="pchat-browsecount">${escapeHtml(count || 15)}</span> questions ▸</button>
    </div>
  </div>`;
}

// ── question-library drawer ──────────────────────────────────────────────────
// Closed = inert, so keyboard focus never lands on the off-screen drawer.
function openDrawer() {
  const d = document.getElementById('pchat-drawer'), s = document.getElementById('pchat-scrim');
  if (d) { d.classList.add('on'); d.inert = false; d.removeAttribute('aria-hidden'); }
  if (s) s.classList.add('on');
  const box = document.getElementById('pchat-search');
  if (box) setTimeout(() => { try { box.focus({ preventScroll: true }); } catch (_) { /* focus is a nicety */ } }, 60);
}
function closeDrawer() {
  const d = document.getElementById('pchat-drawer'), s = document.getElementById('pchat-scrim');
  if (d) {
    const hadFocus = d.classList.contains('on') && d.contains(document.activeElement);
    d.classList.remove('on'); d.inert = true; d.setAttribute('aria-hidden', 'true');
    if (hadFocus) { const inp = document.getElementById('pchat-input'); if (inp) inp.focus(); }
  }
  if (s) s.classList.remove('on');
}

// ── main render ──────────────────────────────────────────────────────────────
export async function renderChat() {
  const host = document.getElementById('chat-body'); if (!host) return;
  ensureCss(); ensureV2Css();
  if (REVEAL) REVEAL.finish();
  LAST_QID = null;                         // a fresh thread — follow-ups start over
  host.innerHTML = `
    <div class="pchat">
      <div class="pchat-head">
        <div class="pchat-mark">✦</div>
        <div><h2>AI Chat</h2><div class="sub">Your offline planning manager</div></div>
        <span class="spring"></span>
        <span class="pchat-pill" id="pchat-brainpill-top" title="Free-form typed answers use a one-time offline AI brain — click to set it up. The suggestions and analyses work now, no download."><span class="dot"></span>checking…</span>
      </div>
      <div class="pchat-setupwrap" id="pchat-setupwrap" hidden>${setupCardHtml()}</div>
      <div class="pchat-thread" id="pchat-thread">${welcomeHtml(libCount())}</div>
      <div class="pchat-strip" id="pchat-strip">${sugStripHtml(libCount())}</div>
      <div class="pchat-composer">
        <button type="button" class="attach" id="pchat-attach" title="Send a P6 file (.xer / .xml) to analyse" aria-label="Send a P6 file">📎</button>
        <textarea id="pchat-input" rows="1" placeholder="Ask anything about your schedule…" aria-label="Ask a question"></textarea>
        <button type="button" class="send" id="pchat-send" title="Send" aria-label="Send">↑</button>
      </div>
      <div class="pchat-scrim" id="pchat-scrim"></div>
      <aside class="pchat-drawer" id="pchat-drawer" aria-label="Question library" aria-hidden="true" inert>
        <div class="pchat-drawer-head"><span>📚 Question Library — <b id="pchat-total">${escapeHtml(libCount())}</b> questions</span><span class="sp"></span><button type="button" class="pchat-drawer-close" id="pchat-drawer-close" title="Close" aria-label="Close the library">✕</button></div>
        <div class="pchat-drawer-body">
          <div class="lsub" id="pchat-libsub">Each question is one full answer from your P6 file. Search also finds the library questions inside them.</div>
          <input class="pchat-search" id="pchat-search" type="search" aria-label="Search the questions and the library questions inside them" placeholder="Search… e.g. handover, float, EOT, manpower">
          <div id="pchat-libbody"></div>
        </div>
      </aside>
    </div>`;

  // events (delegated) — wired once per host so re-opening the panel doesn't stack listeners
  if (!host._pchatWired) {
    host._pchatWired = true;
    host.addEventListener('click', (e) => {
      const at = e.target.closest('#pchat-attach, #pchat-attach-cta'); if (at) { pickAndSend(); return; }
      // Browse-all + drawer open/close
      const br = e.target.closest('[data-browse]'); if (br) { openDrawer(); return; }
      const dx = e.target.closest('#pchat-drawer-close'); if (dx) { closeDrawer(); return; }
      const sm = e.target.closest('#pchat-scrim'); if (sm) { closeDrawer(); return; }
      // The brain pill reveals the (tucked-away) one-time setup panel.
      const bp = e.target.closest('#pchat-brainpill-top'); if (bp) { const w = document.getElementById('pchat-setupwrap'); if (w) w.hidden = !w.hidden; return; }
      // v2: a tool inside an answer (dashboard / what-if / time impact / briefing).
      const tl = e.target.closest('[data-v2tool]'); if (tl) { runV2Tool(tl.dataset.v2tool, tl.dataset.label); return; }
      // v2: a merged question — drawer row / sub-question (focus), drill-in, also-related,
      // "did you mean" chip. Close the drawer so the answer is visible.
      const va = e.target.closest('[data-v2ask]'); if (va) {
        closeDrawer();
        askV2(va.dataset.v2ask, va.dataset.q, { focus: va.dataset.focus || null });
        return;
      }
      // "Ask it in the chat anyway" from an empty library search.
      const tx = e.target.closest('[data-asktext]'); if (tx) { closeDrawer(); ask(tx.dataset.asktext); return; }
      // Suggestion card / strip chip — route like a library question (cap → Copilot, else ask).
      const sug = e.target.closest('[data-sug]'); if (sug) {
        closeDrawer();
        if (sug.dataset.cap) askCopilot(sug.dataset.cap, sug.dataset.qid, sug.dataset.mode, sug.dataset.q);
        else ask(sug.dataset.q);
        return;
      }
      const mc = e.target.closest('[data-model]'); if (mc) { selectModel(mc.dataset.model); return; }
      const setupBtn = e.target.closest('#pchat-setup-btn'); if (setupBtn) { setupBrain(); return; }
    });
    host.addEventListener('input', (e) => { if (e.target && e.target.id === 'pchat-search') renderLib2(); });
    // Esc closes the drawer.
    host.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });
    // Send a P6 file by dropping it anywhere on the chat (reuses the app's file.path drop).
    host.addEventListener('dragover', (e) => { e.preventDefault(); host.classList.add('pchat-dragging'); });
    host.addEventListener('dragleave', (e) => { if (!host.contains(e.relatedTarget)) host.classList.remove('pchat-dragging'); });
    host.addEventListener('drop', (e) => {
      e.preventDefault(); host.classList.remove('pchat-dragging');
      const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (!f) return;
      if (!/\.(xer|xml)$/i.test(f.name || '')) { addAiMessage('Please send a <b>.xer</b> or <b>.xml</b> file exported from Primavera P6.'); return; }
      if (f.path) sendFile(f.path);
      else addAiMessage('The drop didn’t expose the file path here — use the <b>📎</b> button to choose the file instead.');
    });
  }
  const input = document.getElementById('pchat-input');
  // Send the composer text — kept in the box while an answer is still being computed.
  const send = () => { if (BUSY) return; const v = input.value; input.value = ''; input.style.height = 'auto'; ask(v); };
  input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 120) + 'px'; });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
  document.getElementById('pchat-send').addEventListener('click', send);

  // load the 15-question library + brain status
  try {
    const d = await getJSON('/api/chat/library2');
    if (d && d.ok) LIB2 = d;
  } catch { /* library missing — renderLib2 says so */ }
  const n = libCount();
  const tot = document.getElementById('pchat-total'); if (tot) tot.textContent = n;
  host.querySelectorAll('.pchat-browsecount').forEach((el) => { el.textContent = n; });
  const sub = document.getElementById('pchat-libsub');
  const inner = LIB2 && LIB2.counts && LIB2.counts.originals;
  if (sub && inner) sub.textContent = `Each question is one full answer from your P6 file. Search also finds the ${inner} library questions inside them.`;
  renderLib2();
  await refreshStatus();
}
