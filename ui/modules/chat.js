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
    const qs = (t.questions || []).map((q) =>
      `<div class="pchat-q" data-q="${escapeHtml(q.q)}" data-status="${q.status}" data-roles="${(q.role_keys || []).join('|')}" data-text="${escapeHtml((q.q + ' ' + (q.grounds || '')).toLowerCase())}">
        <span class="pchat-sdot ${sdotClass(q.status)}"></span>
        <span class="qt">${escapeHtml(q.q)}<span class="qg">${escapeHtml(q.grounds || '')}</span></span>
      </div>`).join('');
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
