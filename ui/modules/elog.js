/* Engineering-log confirmation panel (Earned Value ▸ Engineering Progress).

   After the planner picks the log file(s) the server PROPOSES how to read them
   (/api/e1/inspect): which sheets are drawing lists, what each column means and how sure
   the reader is, the review codes the log uses and a preview of the counts per discipline.
   This panel shows exactly that and lets the planner correct any column or code. Nothing
   is counted until "Confirm and count". No window.alert/confirm (no-ops in WebView2) —
   every message is shown inside the panel.

   The pure helpers (sureLevel, setColumnField, setCodeVerdict, firstCheckColumn,
   codeGroups, previewTotals, readableLayouts) are unit-tested in tests/js/test_elog.js. */
import { escapeHtml } from './format.js';

export const SURE_LABEL = { high: 'High', medium: 'Medium', check: 'Check' };
export const VERDICT_LABEL = {
  approved: 'Approved', not_approved: 'Not approved', under_review: 'Under review', ignore: 'Ignore',
};
const VERDICT_ORDER = ['approved', 'not_approved', 'under_review', 'ignore'];

// ── pure helpers ───────────────────────────────────────────────────────────────────────
export function sureLevel(conf) {
  const c = Number(conf) || 0;
  return c >= 0.75 ? 'high' : c >= 0.5 ? 'medium' : 'check';
}

function fieldLabel(layout, key) {
  const f = (layout.fields || []).find((x) => x.key === key);
  return f ? f.label : key;
}

/** The planner picks what a column means. One column per meaning: any other column of the
 *  same sheet that held that meaning becomes "Ignore" (with the reason). Returns layout. */
export function setColumnField(layout, sheetName, index, field) {
  const sh = (layout.sheets || []).find((s) => s.sheet === sheetName);
  if (!sh) return layout;
  const col = (sh.columns || []).find((c) => c.index === index);
  if (!col) return layout;
  for (const c of sh.columns) {
    if (c !== col && field !== 'ignore' && c.field === field) {
      c.field = 'ignore';
      c.confidence = 0.6;
      c.level = 'medium';
      c.reason = `Now Ignore — you chose column ${col.letter || ''} for ${fieldLabel(layout, field)}.`;
      c.userSet = true;
    }
  }
  col.field = field;
  col.confidence = 1;
  col.level = 'high';
  col.reason = 'Your choice.';
  col.userSet = true;
  return layout;
}

/** The planner says what a review code means (approved / not_approved / under_review / ignore). */
export function setCodeVerdict(layout, value, verdict) {
  if (!VERDICT_ORDER.includes(verdict)) return layout;
  layout.code_map = layout.code_map || {};
  layout.code_map[value] = verdict;
  for (const c of layout.codes || []) if (c.value === value) c.verdict = verdict;
  return layout;
}

/** Where "Change a column" should take the planner: the first unsure column of a counted
 *  sheet ('check' first, then 'medium'), else the first column. null when nothing to show. */
export function firstCheckColumn(layout) {
  const sheets = (layout.sheets || []).filter((s) => s.include && (s.columns || []).length);
  for (const lvl of ['check', 'medium']) {
    for (const s of sheets) {
      const c = s.columns.find((x) => (x.level || sureLevel(x.confidence)) === lvl && !x.userSet);
      if (c) return { sheet: s.sheet, index: c.index };
    }
  }
  return sheets.length ? { sheet: sheets[0].sheet, index: sheets[0].columns[0].index } : null;
}

/** Review codes grouped by what they currently mean, most-used first inside each group. */
export function codeGroups(codes) {
  const g = { approved: [], not_approved: [], under_review: [], ignore: [] };
  for (const c of codes || []) (g[c.verdict] || g.ignore).push(c);
  for (const k of Object.keys(g)) g[k].sort((a, b) => (b.count - a.count) || String(a.value).localeCompare(String(b.value)));
  return g;
}

/** Totals row of the preview (distinct drawings per discipline, summed). */
export function previewTotals(byTrade) {
  const t = { req: 0, submitted_rows: 0, approved_rows: 0, not_approved_rows: 0, under_review_rows: 0 };
  for (const r of byTrade || []) for (const k of Object.keys(t)) t[k] += Number(r[k]) || 0;
  t.approved_pct = t.req ? Math.round(1000 * t.approved_rows / t.req) / 10 : 0;
  t.submitted_pct = t.req ? Math.round(1000 * (t.submitted_rows - t.not_approved_rows) / t.req) / 10 : 0;
  return t;
}

/** {path: layout} for the files that could be read (a file that failed to open is skipped). */
export function readableLayouts(files) {
  const out = {};
  for (const f of files || []) if (f && !f.error && f.path && (f.sheets || []).length) out[f.path] = f;
  return out;
}

// ── panel ──────────────────────────────────────────────────────────────────────────────
const esc = escapeHtml;

function chip(text, cls = '') { return `<span class="elog-chip ${cls}">${esc(text)}</span>`; }

function sourceText(sh) {
  const t = sh.trade_source, y = sh.type_source;
  const bits = [];
  if (t) bits.push(t.kind === 'column' ? `Discipline from column “${t.value}”`
    : t.kind === 'section' ? `Discipline from the section titles (${t.value})`
      : `Discipline from the sheet name: ${t.value}`);
  if (y) bits.push(y.kind === 'column' ? `type from column “${y.value}”`
    : y.kind === 'sheet-name' ? `type from the sheet name: ${y.value}`
      : `type: ${y.value}`);
  return bits.join(' · ');
}

function colRow(layout, sh, c, aiReady) {
  const lvl = c.level || sureLevel(c.confidence);
  const opts = (layout.fields || []).map((f) =>
    `<option value="${esc(f.key)}"${f.key === c.field ? ' selected' : ''}>${esc(f.label)}</option>`).join('');
  const samp = (c.samples || []).slice(0, 3).map(esc).join(' · ');
  const ai = c.ai_suggestion && c.ai_suggestion !== c.field
    ? `<div class="elog-ai"><span class="elog-ai-tag">Offline AI</span> suggests
        <b>${esc(fieldLabel(layout, c.ai_suggestion))}</b>
        <button class="elog-link" data-ai-use="${c.index}" data-field="${esc(c.ai_suggestion)}">Use it</button></div>` : '';
  return `<tr class="elog-lvl-${lvl}${c.field === 'ignore' ? ' elog-ign' : ''}" data-row="${c.index}">
    <td class="elog-colname"><span class="elog-letter">${esc(c.letter || '')}</span>
      <b>${c.header ? esc(c.header) : '<i>(no heading)</i>'}</b>
      ${samp ? `<div class="elog-samp">${samp}</div>` : ''}</td>
    <td><select class="elog-sel" data-idx="${c.index}" aria-label="Read column ${esc(c.letter || '')} as">${opts}</select>${ai}</td>
    <td><span class="elog-pill ${lvl}" title="${esc(c.reason || '')}">${SURE_LABEL[lvl]}</span>
      <div class="elog-why">${esc(c.reason || '')}</div></td></tr>`;
}

function codesHtml(layout) {
  const codes = layout.codes || [];
  if (!codes.length) {
    return '<p class="elog-empty">No review codes found yet — pick the column that holds the consultant\'s code or status.</p>';
  }
  const groups = codeGroups(codes);
  const opts = (v) => VERDICT_ORDER.map((k) =>
    `<option value="${k}"${k === v ? ' selected' : ''}>${VERDICT_LABEL[k]}</option>`).join('');
  return `<div class="elog-codegrid">${VERDICT_ORDER.map((k) => `
    <div class="elog-codecol"><div class="elog-codehead v-${k}">${VERDICT_LABEL[k]}</div>
      ${groups[k].map((c) => `<div class="elog-code v-${k}${c.known ? '' : ' unknown'}">
        <span class="elog-code-val">${esc(c.value)}</span><span class="elog-code-n">×${c.count}</span>
        <select class="elog-codesel" data-code="${esc(c.value)}" aria-label="What code ${esc(c.value)} means">${opts(c.verdict)}</select>
        <div class="elog-code-m">${esc(c.meaning || '')}${c.source === 'legend' ? ' · the log\'s legend' : ''}</div>
      </div>`).join('') || '<div class="elog-code-none">—</div>'}</div>`).join('')}</div>`;
}

function previewHtml(layout) {
  const pv = layout.preview || {};
  const rows = pv.by_trade || [];
  if (!rows.length) return '<p class="elog-empty">Nothing to count with this reading yet.</p>';
  const t = previewTotals(rows);
  const tr = (r, cls = '') => `<tr class="${cls}"><td>${esc(r.trade)}</td><td>${r.req}</td><td>${r.submitted_rows}</td>
    <td>${r.approved_rows}</td><td>${r.not_approved_rows}</td><td>${r.under_review_rows}</td><td>${r.approved_pct}%</td></tr>`;
  return `<table class="elog-prev"><thead><tr><th>Discipline</th><th>Drawings</th><th>Submitted</th>
    <th>Approved</th><th>Not approved</th><th>Under review</th><th>% Approved</th></tr></thead>
    <tbody>${rows.map((r) => tr(r)).join('')}${rows.length > 1 ? tr({ trade: 'Total', ...t }, 'elog-tot') : ''}</tbody></table>
    <div class="elog-foot">${pv.rows_read || 0} rows read → ${pv.drawings || 0} drawings (each drawing counted once; once approved it stays approved).</div>`;
}

/** What the planner must see without opening every tab: the notes of the OTHER counted
 *  sheets (each prefixed with its sheet name) and the registers switched off because
 *  nothing on them is submitted yet. */
export function otherSheetNotes(layout, openSheet) {
  const sheets = (layout && layout.sheets) || [];
  return {
    notes: sheets.filter((s) => s.include && s.sheet !== openSheet)
      .flatMap((s) => (s.warnings || []).map((w) => `${s.sheet}: ${w}`)),
    switchedOff: sheets.filter((s) => !s.include && s.auto_off === 'untracked').map((s) => s.sheet),
  };
}

function fileHtml(layout, ui, aiReady) {
  if (layout.error) {
    return `<div class="elog-file"><div class="elog-fname">${esc(layout.file || '')}</div>
      <div class="elog-err">This file could not be read: ${esc(layout.error)}</div></div>`;
  }
  const sheets = layout.sheets || [];
  const regs = sheets.filter((s) => s.kind === 'register');
  const counted = sheets.filter((s) => s.include);
  if (!ui.sheet || !sheets.some((s) => s.sheet === ui.sheet)) ui.sheet = (counted[0] || regs[0] || sheets[0] || {}).sheet;
  const sh = sheets.find((s) => s.sheet === ui.sheet) || {};
  const legendCodes = Object.keys(layout.legend || {});
  const chips = [
    chip(`${sheets.length} sheet${sheets.length === 1 ? '' : 's'} found`),
    chip(`${counted.length} counted${counted.length ? ': ' + counted.map((s) => s.sheet).join(', ') : ''}`, counted.length ? '' : 'warn'),
    sh.header_rows && sh.header_rows.length ? chip(`${sh.sheet}: headings on row ${sh.header_rows.join(' + ')}`) : '',
    legendCodes.length ? chip(`Code legend found: ${legendCodes.join(' ')}`, 'ok') : '',
    layout.remembered ? chip(`Layout remembered from ${layout.remembered.file || 'an earlier log'}`, 'ok') : '',
  ];
  const other = otherSheetNotes(layout, ui.sheet);
  if (other.switchedOff.length) {
    chips.push(chip(`${other.switchedOff.length} switched off — nothing submitted yet: ${other.switchedOff.join(', ')}`, 'warn'));
  }
  const tabs = sheets.map((s) => {
    const can = s.kind === 'register' || s.include;
    const why = s.reason || '';
    return `<div class="elog-sheet${s.sheet === ui.sheet ? ' active' : ''}${s.include ? '' : ' off'}${can ? '' : ' muted'}" title="${esc(why)}">
      ${can ? `<input type="checkbox" class="elog-inc" data-sheet="${esc(s.sheet)}" ${s.include ? 'checked' : ''} aria-label="Count sheet ${esc(s.sheet)}">` : ''}
      <button class="elog-sheetbtn" data-sheet="${esc(s.sheet)}"${can ? '' : ' disabled'}>${esc(s.sheet)}</button>
      <small>${can ? `${s.row_count} rows` : esc(s.kind === 'summary' ? 'summary — not counted' : s.kind === 'legend-only' ? 'legend only' : 'not a list')}</small></div>`;
  }).join('');
  const cols = (sh.columns || []).map((c) => colRow(layout, sh, c, aiReady)).join('');
  const notes = [sh.reason, ...(sh.warnings || [])].filter(Boolean);
  return `<div class="elog-file">
    <div class="elog-fname"><span class="elog-ficon" aria-hidden="true">▤</span>${esc(layout.file || '')}</div>
    <div class="elog-chips">${chips.join('')}</div>
    ${other.notes.length ? `<ul class="elog-notes elog-othernotes" aria-label="Notes on the other counted sheets">${other.notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul>` : ''}
    <div class="elog-sheets">${tabs}</div>
    ${sh.columns && sh.columns.length ? `
    <div class="elog-src">${esc(sourceText(sh))}</div>
    <div class="elog-tablewrap"><table class="elog-cols"><thead><tr><th>Your column</th><th>Read as</th><th>How sure</th></tr></thead>
      <tbody>${cols}</tbody></table></div>` : ''}
    ${notes.length ? `<ul class="elog-notes">${notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul>` : ''}
    <div class="elog-h">Review codes <small>— change what a code means if the log uses its own scheme</small></div>
    ${codesHtml(layout)}
    <div class="elog-h">Preview per discipline</div>
    <div class="elog-prevwrap">${previewHtml(layout)}</div>
  </div>`;
}

/** Show the confirmation panel inside `host`. opts: {port, aiReady, onConfirm(layouts) →
 *  Promise, onCancel()}. Returns a small handle (for tests / the live check). */
export function openElogConfirm(host, files, opts = {}) {
  const ui = { file: 0, sheets: {}, timer: null, seq: 0, busy: false };
  const port = opts.port;
  files = (files || []).map((f) => f);

  function cur() { return files[ui.file]; }
  function uiFor(i) { return (ui.sheets[i] = ui.sheets[i] || { sheet: null }); }

  function msg(text, kind = '') {
    const m = host.querySelector('#elog-msg');
    if (m) { m.className = `elog-msg ${kind}`; m.textContent = text || ''; }
  }

  function render(focusSel) {
    const tabs = files.length > 1 ? `<div class="elog-filetabs" role="tablist">${files.map((f, i) =>
      `<button class="elog-filetab${i === ui.file ? ' active' : ''}" data-file="${i}">${esc(f.file || `File ${i + 1}`)}</button>`).join('')}</div>` : '';
    host.innerHTML = `<div class="elog-panel" id="elog-panel" tabindex="-1" role="region" aria-label="Check how the log was read">
      <div class="elog-top"><div class="elog-title">Check how the log was read</div>
        <div class="elog-lead">Nothing is counted until you confirm. The log is read on this PC — nothing leaves it.</div></div>
      ${tabs}
      <div id="elog-body">${fileHtml(cur(), uiFor(ui.file), opts.aiReady)}</div>
      <div class="elog-msg" id="elog-msg" role="status" aria-live="polite"></div>
      <div class="elog-actions">
        <button class="btn-mini" id="elog-change">Change a column</button>
        ${opts.aiReady ? '<button class="btn-mini" id="elog-ai">Ask the offline AI about unsure columns</button>' : ''}
        <span class="elog-spacer"></span>
        <button class="btn-mini" id="elog-cancel">Cancel</button>
        <button class="btn-mini primary" id="elog-confirm"${Object.keys(readableLayouts(files)).length ? '' : ' disabled'}>Confirm and count</button>
      </div></div>`;
    wire();
    if (focusSel) { const el = host.querySelector(focusSel); if (el) el.focus(); }
  }

  function scheduleRefresh() {
    clearTimeout(ui.timer);
    ui.timer = setTimeout(refresh, 250);
  }

  async function refresh() {
    const f = cur();
    if (!f || f.error || !port) return;
    const seq = ++ui.seq, idx = ui.file;
    msg('Re-counting…');
    try {
      const resp = await fetch(`http://localhost:${port}/api/e1/preview`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: f.path, layout: f }),
      });
      const data = await resp.json();
      if (seq !== ui.seq) return;                         // a newer change is on its way
      if (!data.ok) { msg(`Could not re-count: ${data.error || 'unknown error'}`, 'err'); return; }
      files[idx] = data.layout;
      const active = document.activeElement;
      const keep = active && host.contains(active) && active.dataset
        ? (active.dataset.idx != null ? `.elog-sel[data-idx="${active.dataset.idx}"]`
          : active.dataset.code != null ? `.elog-codesel[data-code="${CSS.escape(active.dataset.code)}"]` : null) : null;
      render(keep);
      msg('Preview updated.', 'ok');
    } catch (e) {
      msg(`Could not re-count: ${e.message || e}`, 'err');
    }
  }

  function wire() {
    const f = cur();
    host.querySelectorAll('.elog-filetab').forEach((b) => b.addEventListener('click', () => {
      ui.file = Number(b.dataset.file); render();
    }));
    host.querySelectorAll('.elog-sheetbtn').forEach((b) => b.addEventListener('click', () => {
      uiFor(ui.file).sheet = b.dataset.sheet; render();
    }));
    host.querySelectorAll('.elog-inc').forEach((cb) => cb.addEventListener('change', () => {
      const sh = (f.sheets || []).find((s) => s.sheet === cb.dataset.sheet);
      if (sh) { sh.include = cb.checked; uiFor(ui.file).sheet = sh.sheet; render(); scheduleRefresh(); }
    }));
    host.querySelectorAll('.elog-sel').forEach((sel) => sel.addEventListener('change', () => {
      setColumnField(f, uiFor(ui.file).sheet, Number(sel.dataset.idx), sel.value);
      render(`.elog-sel[data-idx="${sel.dataset.idx}"]`); scheduleRefresh();
    }));
    host.querySelectorAll('[data-ai-use]').forEach((b) => b.addEventListener('click', () => {
      setColumnField(f, uiFor(ui.file).sheet, Number(b.dataset.aiUse), b.dataset.field);
      render(`.elog-sel[data-idx="${b.dataset.aiUse}"]`); scheduleRefresh();
    }));
    host.querySelectorAll('.elog-codesel').forEach((sel) => sel.addEventListener('change', () => {
      setCodeVerdict(f, sel.dataset.code, sel.value);
      render(`.elog-codesel[data-code="${CSS.escape(sel.dataset.code)}"]`); scheduleRefresh();
    }));
    const q = (id) => host.querySelector(id);
    q('#elog-change').addEventListener('click', () => {
      const target = firstCheckColumn(f || {});
      if (!target) { msg('This file has no columns to change.', 'err'); return; }
      uiFor(ui.file).sheet = target.sheet;
      render(`.elog-sel[data-idx="${target.index}"]`);
      const row = host.querySelector(`tr[data-row="${target.index}"]`);
      if (row) { row.classList.add('elog-flash'); row.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
      msg('Pick what this column holds — the preview re-counts as you change it.');
    });
    const ai = q('#elog-ai');
    if (ai) ai.addEventListener('click', async () => {
      msg('Asking the offline AI (on this PC)…');
      try {
        const resp = await fetch(`http://localhost:${port}/api/e1/ai-suggest`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ layout: f }),
        });
        const data = await resp.json();
        if (!data.ok) { msg(data.error || 'The offline AI could not answer.', 'err'); return; }
        files[ui.file] = data.layout; render();
        msg('Suggestions shown under the unsure columns — nothing changes until you pick one.', 'ok');
      } catch (e) { msg(`The offline AI could not answer: ${e.message || e}`, 'err'); }
    });
    q('#elog-cancel').addEventListener('click', () => { clearTimeout(ui.timer); if (opts.onCancel) opts.onCancel(); });
    q('#elog-confirm').addEventListener('click', async () => {
      if (ui.busy) return;
      const layouts = readableLayouts(files);
      if (!Object.keys(layouts).length) { msg('None of the chosen files could be read.', 'err'); return; }
      if (!Object.values(layouts).some((l) => (l.sheets || []).some((s) => s.include))) {
        msg('Switch on at least one sheet to count.', 'err'); return;
      }
      ui.busy = true; clearTimeout(ui.timer);
      host.querySelectorAll('.elog-actions button').forEach((b) => { b.disabled = true; });
      msg('Counting…');
      try {
        await opts.onConfirm(layouts);
      } catch (e) {
        ui.busy = false;
        host.querySelectorAll('.elog-actions button').forEach((b) => { b.disabled = false; });
        msg(`The log could not be counted: ${e.message || e}`, 'err');
      }
    });
  }

  render();
  const panel = host.querySelector('#elog-panel');
  if (panel) { panel.scrollIntoView({ block: 'start', behavior: 'smooth' }); panel.focus({ preventScroll: true }); }
  return { files: () => files, refresh };
}
