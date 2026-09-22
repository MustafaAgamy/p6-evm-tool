// Offline AI Chat — a Claude-style chat that answers as a senior planning manager,
// grounded in the open project's real analysis and running on the user's PC.
//
// The screen: a visible question library categorised by JOB ROLE (Project Manager,
// Planning Manager, …), a search + status filter, a thread that streams answers
// word-by-word, and a composer. Answers come from the local brain via
// /api/chat/ask; when the brain isn't set up yet a clear setup card is shown and
// questions return an honest grounded snapshot instead of a canned answer.
//
// All styling is self-contained here (a single injected <style>) and reads the
// app's appearance tokens (--card-bg / --border / --text / --accent / --muted),
// so it themes correctly in all six looks with no edits to style.css.
import { state } from './state.js';
import { escapeHtml } from './format.js';

let LIB = null;         // {themes, roles, gaps, counts}
let BRAIN = null;       // brain status
let ROLE = 'all';       // active role filter
let SFILT = 'all';      // active status filter (all/today/in-progress/gap)
let BUSY = false;
let POLL = null;        // setup status-poll timer

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

  .pchat-lib{border:1px solid var(--border);background:var(--card-bg);border-radius:12px;padding:14px 16px}
  .pchat-lib .lh{font-size:13.5px;font-weight:750;color:var(--text);text-align:center}
  .pchat-lib .lh b{color:var(--accent-dark)}
  .pchat-lib .lsub{font-size:12px;color:var(--muted);text-align:center;margin:2px 0 12px}
  .pchat-rolelbl{display:block;text-align:center;font-size:10.5px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;color:var(--muted);margin-bottom:7px}
  .pchat-chips{display:flex;gap:7px;flex-wrap:wrap;justify-content:center;margin-bottom:10px}
  .pchat-chip{border:1px solid var(--border);background:transparent;border-radius:999px;padding:5px 11px;font-size:12px;cursor:pointer;color:var(--ink-soft);font-family:inherit}
  .pchat-chip:hover{border-color:var(--accent);color:var(--accent-dark)}
  .pchat-chip.on{background:var(--accent);color:#fff;border-color:var(--accent)}
  .pchat-chip.role.on{background:var(--accent-dark);border-color:var(--accent-dark)}
  .pchat-search{width:100%;border:1px solid var(--border);border-radius:10px;padding:9px 12px;font:inherit;font-size:13px;background:var(--bg);color:var(--text);outline:0;margin-bottom:8px}
  .pchat-search:focus{border-color:var(--accent)}
  .pchat-legend{display:flex;gap:14px;justify-content:center;font-size:11px;color:var(--muted);margin-bottom:6px;flex-wrap:wrap}
  .pchat-sdot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px}
  .pchat-sdot.today{background:#1f8a5b}.pchat-sdot.prog{background:#c98a1e}.pchat-sdot.gap{background:#9aa5b1}
  .pchat-theme{margin-top:14px}
  .pchat-theme h4{font-size:12px;font-weight:800;color:var(--accent-dark);margin:0 0 3px;text-transform:uppercase;letter-spacing:.4px}
  .pchat-theme .tb{font-size:11.5px;color:var(--muted);margin:0 0 6px}
  .pchat-q{display:flex;align-items:flex-start;gap:8px;padding:7px 9px;border-radius:9px;cursor:pointer;border:1px solid transparent}
  .pchat-q:hover{background:var(--hair);border-color:var(--border)}
  .pchat-q .pchat-sdot{margin-top:6px;flex:0 0 auto}
  .pchat-q .qt{flex:1;font-size:13px;color:var(--text)}
  .pchat-q .qg{display:block;color:var(--muted);font-size:11px;margin-top:1px}
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
    ? `<ul class="pcp-insights">${ins.map((x) => `<li>${mdInline(String(x && x.text != null ? x.text : x))}</li>`).join('')}</ul>`
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
            + ((im.base_finish || im.impacted_finish) ? `<div class="pcp-wi-basis">${escapeHtml(im.base_finish || '?')} → ${escapeHtml(im.impacted_finish || '?')}</div>` : ''));
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

// Ask a question — streams the answer live (NDJSON) so long, detailed answers
// appear as they're written, then renders charts + the grounded footer.
async function ask(question) {
  if (BUSY || !question || !question.trim()) return;
  if (isDashboardIntent(question)) { return askDashboard(question.trim()); }
  BUSY = true; setSendEnabled(false);
  try {
    addUser(question.trim());
    const bodyEl = addAiShell();
    if (!bodyEl) return;
    const think = bodyEl.querySelector('.pchat-think');
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
        body: JSON.stringify({ question: question.trim(), role: ROLE === 'all' ? null : ROLE,
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
  } catch (_) {
    /* best-effort — the finally still frees the composer even if rendering threw */
  } finally {
    BUSY = false; setSendEnabled(true);
  }
}

// ── brain status / setup ─────────────────────────────────────────────────────
function renderBrainPill() {
  const ready = BRAIN && BRAIN.ready;
  const cls = 'pchat-pill ' + (ready ? 'ready' : 'off');
  const html = `<span class="dot"></span>${ready ? 'AI brain ready' : 'AI brain not set up'}`;
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
    <h3>Switch on your offline AI brain (one-time)</h3>
    <p>The chat answers with a real AI that runs entirely on your PC — no internet, no key, no cost, and <b>nothing to install</b>. It just needs a one-time model download, which it does right here. After that it works fully offline. Charts and a grounded snapshot of your schedule already work below.</p>
    <div class="pchat-rolelbl" style="text-align:left">Choose the AI brain — bigger is smarter &amp; more detailed, smaller is faster</div>
    <div class="pchat-models" id="pchat-models"></div>
    <div class="row">
      <button class="pchat-btn" id="pchat-setup-btn">Download the AI brain now</button>
      <span class="pchat-pill" id="pchat-brainpill"><span class="dot"></span>checking…</span>
    </div>
    <p id="pchat-setup-note" style="margin-top:9px;font-size:12px">${escapeHtml(b.detail || '')}</p>
  </div>`;
}

// ── library ──────────────────────────────────────────────────────────────────
function sdotClass(s) { return s === 'today' ? 'today' : s === 'in-progress' ? 'prog' : 'gap'; }

function renderRoles() {
  const el = document.getElementById('pchat-roles'); if (!el) return;
  const chips = [`<button class="pchat-chip role ${ROLE === 'all' ? 'on' : ''}" data-role="all">Everyone</button>`]
    .concat((LIB.roles || []).map((r) =>
      `<button class="pchat-chip role ${ROLE === r.key ? 'on' : ''}" data-role="${r.key}">${escapeHtml(r.title)} <b style="opacity:.6">${r.count}</b></button>`));
  el.innerHTML = chips.join('');
}

function renderLibBody() {
  const el = document.getElementById('pchat-libbody'); if (!el) return;
  el.innerHTML = (LIB.themes || []).map((t) => {
    const qs = (t.questions || []).map((q) => {
      // Copilot "expert analysis" questions carry a capability + question id + mode
      // (library.js sets q.cap/q.qid/q.mode). Emit them only when present so the
      // click handler can route them to the deterministic Copilot backend.
      const cap = q.cap ? ` data-cap="${escapeHtml(q.cap)}"` : '';
      const qid = q.qid ? ` data-qid="${escapeHtml(q.qid)}"` : '';
      const mode = q.mode ? ` data-mode="${escapeHtml(q.mode)}"` : '';
      return `<div class="pchat-q" data-q="${escapeHtml(q.q)}" data-status="${q.status}" data-roles="${(q.role_keys || []).join('|')}" data-text="${escapeHtml((q.q + ' ' + (q.grounds || '')).toLowerCase())}"${cap}${qid}${mode}>
        <span class="pchat-sdot ${sdotClass(q.status)}"></span>
        <span class="qt">${escapeHtml(q.q)}<span class="qg">${escapeHtml(q.grounds || '')}</span></span>
      </div>`;
    }).join('');
    return `<div class="pchat-theme"><h4>${escapeHtml(t.theme)}</h4><div class="tb">${escapeHtml(t.blurb || '')}</div>${qs}</div>`;
  }).join('') + `<div class="pchat-nomatch" id="pchat-nomatch" hidden>No questions match your search.</div>`;
  applyFilter();
}

function applyFilter() {
  const q = (document.getElementById('pchat-search')?.value || '').toLowerCase().trim();
  let any = false;
  document.querySelectorAll('#pchat-libbody .pchat-theme').forEach((theme) => {
    let vis = 0;
    theme.querySelectorAll('.pchat-q').forEach((row) => {
      const okR = ROLE === 'all' || (row.dataset.roles || '').split('|').indexOf(ROLE) >= 0;
      const okS = SFILT === 'all' || row.dataset.status === SFILT;
      const okQ = !q || row.dataset.text.indexOf(q) >= 0;
      const show = okR && okS && okQ;
      row.hidden = !show; if (show) { vis++; any = true; }
    });
    theme.hidden = vis === 0;
  });
  const nm = document.getElementById('pchat-nomatch'); if (nm) nm.hidden = any;
}

// ── main render ──────────────────────────────────────────────────────────────
export async function renderChat() {
  const host = document.getElementById('chat-body'); if (!host) return;
  ensureCss();
  const loaded = !!state.currentResult;
  host.innerHTML = `
    <div class="pchat">
      <div class="pchat-head">
        <div class="pchat-mark">✦</div>
        <div><h2>AI Chat</h2><div class="sub">Your offline planning manager · reads your schedule, answers grounded</div></div>
        <span class="spring"></span>
        <span class="pchat-pill" id="pchat-brainpill-top"><span class="dot"></span>checking…</span>
      </div>
      ${setupCardHtml()}
      <div class="pchat-thread" id="pchat-thread">
        <div class="pchat-empty">${loaded
          ? '<b>Ask me anything about this schedule.</b><br>Pick a question below (choose your job role to focus it), or type your own.'
          : '<b>Import a P6 schedule first.</b><br>Then I can read it and answer — the library of questions is below.'}</div>
      </div>
      <div class="pchat-composer">
        <textarea id="pchat-input" rows="1" placeholder="Ask anything about your schedule…"></textarea>
        <button class="send" id="pchat-send" title="Send">↑</button>
      </div>
      <div class="pchat-lib">
        <div class="lh">📚 Question Library — <b id="pchat-total">…</b> questions a PM might ask</div>
        <div class="lsub">Click any question to answer it — grounded in your data + a planning manager's read.</div>
        <span class="pchat-rolelbl">Show questions for</span>
        <div class="pchat-chips" id="pchat-roles"></div>
        <div class="pchat-chips" id="pchat-status">
          <button class="pchat-chip on" data-s="all">All</button>
          <button class="pchat-chip" data-s="today"><span class="pchat-sdot today"></span>Ready today</button>
          <button class="pchat-chip" data-s="in-progress"><span class="pchat-sdot prog"></span>In progress</button>
          <button class="pchat-chip" data-s="gap"><span class="pchat-sdot gap"></span>Future</button>
        </div>
        <div class="pchat-legend" id="pchat-legend"></div>
        <input class="pchat-search" id="pchat-search" placeholder="Search… (delay, float, EOT, manpower, cost)">
        <div id="pchat-libbody"></div>
      </div>
    </div>`;

  // events (delegated) — wired once per host so re-opening the panel doesn't stack listeners
  if (!host._pchatWired) {
    host._pchatWired = true;
    host.addEventListener('click', (e) => {
      const cop = e.target.closest('.pchat-q[data-cap]'); if (cop) { askCopilot(cop.dataset.cap, cop.dataset.qid, cop.dataset.mode, cop.dataset.q); return; }
      const q = e.target.closest('.pchat-q'); if (q) { ask(q.dataset.q); return; }
      const rc = e.target.closest('[data-role]'); if (rc) { ROLE = rc.dataset.role; renderRoles(); applyFilter(); return; }
      const sc = e.target.closest('#pchat-status [data-s]'); if (sc) {
        SFILT = sc.dataset.s;
        host.querySelectorAll('#pchat-status .pchat-chip').forEach((c) => c.classList.toggle('on', c.dataset.s === SFILT));
        applyFilter(); return;
      }
      const mc = e.target.closest('[data-model]'); if (mc) { selectModel(mc.dataset.model); return; }
      const setupBtn = e.target.closest('#pchat-setup-btn'); if (setupBtn) { setupBrain(); return; }
    });
    host.addEventListener('input', (e) => { if (e.target && e.target.id === 'pchat-search') applyFilter(); });
  }
  const input = document.getElementById('pchat-input');
  input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 120) + 'px'; });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); const v = input.value; input.value = ''; input.style.height = 'auto'; ask(v); } });
  document.getElementById('pchat-send').addEventListener('click', () => { const v = input.value; input.value = ''; input.style.height = 'auto'; ask(v); });

  // load library + status
  try {
    const d = await getJSON('/api/chat/library');
    if (d && d.ok) {
      LIB = d;
      document.getElementById('pchat-total').textContent = (d.counts && d.counts.total) || '';
      document.getElementById('pchat-legend').innerHTML =
        `<span><span class="pchat-sdot today"></span>${d.counts.today} ready today</span>` +
        `<span><span class="pchat-sdot prog"></span>${d.counts.in_progress} in progress</span>` +
        `<span><span class="pchat-sdot gap"></span>${d.counts.gap} future</span>`;
      renderRoles(); renderLibBody();
    }
  } catch { /* library missing */ }
  await refreshStatus();
}
