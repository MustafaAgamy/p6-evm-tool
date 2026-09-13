// Knowledge Base — "Construction Project Knowledge", in the Productivity &
// Resource Intelligence style: toolbar (title + search + browse + export),
// a Sector ▸ Project-type cascade selector row, and a main-column + right-rail
// layout of cards. Per project type: a brief + components, the overview
// construction sequence, a suggested WBS (copy / download baseline), and the
// suggested sequence of work BY DISCIPLINE / TRADE (systems grouped into clean
// trades). Reference-first: no score, no verdict. Offline; app tokens (6 modes).

import { state }      from './state.js';
import { showError }  from './render.js';
import { escapeHtml } from './format.js';

let _lib = null, _pb = null, _sector = null, _flat = [], _focus = 'all';
const host = () => document.getElementById('kb-playbooks-section');
const api = (p, body) => fetch(`http://localhost:${state.serverPort}${p}`, body
  ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  : undefined).then(r => r.json());
const loading = (m) => `<div class="kbp-loading">${escapeHtml(m)}</div>`;

// discipline label -> a categorical chart token (theme-aware, stable)
const DISC_CHART = { Electrical:1, Mechanical:2, 'Extra-Low Voltage':3, Finishes:4, Civil:5,
  Structural:6, Piping:2, Instrumentation:3, Plumbing:2, 'Fire Protection':1, Process:4,
  Utilities:5, 'Mechanical Piping':2, Commissioning:6, Unclassified:5 };
function discColor(label) {
  let n = DISC_CHART[label];
  if (!n) { let h = 0; for (const c of (label || '')) h = (h + c.charCodeAt(0)) % 6; n = h + 1; }
  return `var(--chart-${n})`;
}
function prettyStage(s) { s = (s || '').replace(/_/g, ' ').trim(); return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
function shortName(s) {
  let t = (s || '').split(' — ')[0].split(' (')[0].split(' – ')[0].trim();
  if (t.length > 46) t = t.slice(0, 46).trim() + '…';
  return t;
}
const GATE = /hydro|pressure test|flush|earth|energiz|mechanical completion|integrat|\bist\b|load[- ]bank|\bndt\b|\bweld|room[- ]integrity|inspection|\btest\b/i;
function gateIndex(stages) { for (let i = 0; i < stages.length; i++) { if (GATE.test(stages[i])) return i; } return -1; }

// order disciplines by construction sequence (front to back) so trades read in build order
const DISC_ORDER = ['Civil', 'Structural', 'Finishes', 'Process', 'Mechanical', 'Mechanical Piping',
  'Piping', 'Plumbing', 'Electrical', 'Extra-Low Voltage', 'Instrumentation', 'Fire Protection',
  'Utilities', 'Commissioning', 'Unclassified'];
const discOrder = (d) => { const i = DISC_ORDER.indexOf(d); return i < 0 ? 99 : i; };

// group the per-system sequence detail into clean discipline / trade cards. One
// representative sequence per discipline (the primary system with the most stages),
// so a discipline with many systems reads as one tidy chain rather than a merge.
function groupTrades(detail) {
  const map = new Map();
  for (const d of (detail || [])) {
    if (!(d.stages || []).length) continue;
    const key = d.discipline_label || 'Other';
    if (!map.has(key)) map.set(key, { discipline: key, primary: false, systems: [], stages: [], _score: -1 });
    const g = map.get(key);
    if (d.primary) g.primary = true;
    g.systems.push(shortName(d.name));
    const score = (d.primary ? 1000 : 0) + d.stages.length;   // prefer a primary system, then the most detailed
    if (score > g._score) { g._score = score; g.stages = d.stages.map(prettyStage); }
  }
  return [...map.values()].sort((a, b) => discOrder(a.discipline) - discOrder(b.discipline) || a.discipline.localeCompare(b.discipline));
}
const FOCUS = { all: null, civil: ['Civil', 'Structural'],
  mep: ['Mechanical', 'Electrical', 'Extra-Low Voltage', 'Instrumentation', 'Plumbing', 'Fire Protection', 'Piping', 'Mechanical Piping', 'Utilities', 'Process'],
  comm: ['Commissioning'] };
const FOCUS_LABEL = { all: 'All disciplines', civil: 'Civil / Structural', mep: 'MEP', comm: 'Commissioning' };

// ── page lifecycle ──────────────────────────────────────────────────────────
export function showPlaybooks() {
  hideOthers();
  const h = host(); if (!h) return;
  h.classList.remove('hidden');
  if (!_lib) { h.innerHTML = loading('Loading the Knowledge Base…'); load(); }
  else render();
}
export function exitPlaybooks() {
  host()?.classList.add('hidden');
  document.querySelector('.import-section')?.classList.remove('hidden');
}
function hideOthers() {
  document.querySelector('.import-section')?.classList.add('hidden');
  document.getElementById('results-section')?.classList.add('hidden');
  document.querySelector('.recent-section')?.classList.add('hidden');
  document.getElementById('kb-database-section')?.classList.add('hidden');
}

async function load() {
  try {
    const d = await api('/api/kb/playbooks');
    if (!d.ok) { showError(d.error || 'Could not load the Knowledge Base.'); return; }
    _lib = d; _flat = [];
    for (const s of (_lib.sectors || [])) for (const t of (s.types || []))
      _flat.push({ archetype: t.archetype, name: t.name, sector: s.key, sector_label: s.label });
    const pick = _flat.find(x => x.archetype === 'data_center') || _flat[0];
    if (!pick) { host().innerHTML = loading('The knowledge base is empty.'); return; }
    _sector = pick.sector;
    openType(pick.archetype);
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}
async function openType(archetype) {
  const h = host(); if (h && _pb) h.innerHTML = loading('Opening…');
  try {
    const d = await api('/api/kb/playbook', { archetype });
    if (!d.ok) { showError(d.error || 'Could not open this project type.'); return; }
    _pb = d.playbook; _focus = 'all';
    const f = _flat.find(x => x.archetype === archetype); if (f) _sector = f.sector;
    render();
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}

// ── render ──────────────────────────────────────────────────────────────────
function render() {
  const h = host(); if (!h || !_pb) return;
  const pb = _pb, ov = pb.overview || {};
  const sectors = _lib.sectors || [];
  const typesInSector = (sectors.find(s => s.key === _sector) || { types: [] }).types;
  const sectorOpts = sectors.map(s => `<option value="${escapeHtml(s.key)}" ${s.key === _sector ? 'selected' : ''}>${escapeHtml(s.label)}</option>`).join('');
  const typeOpts = typesInSector.map(t => `<option value="${escapeHtml(t.archetype)}" ${t.archetype === pb.archetype ? 'selected' : ''}>${escapeHtml(t.name)}</option>`).join('');
  const sectorChips = sectors.map(s => `<span class="kbp-ptchip ${s.key === _sector ? 'on' : ''}" data-sector="${escapeHtml(s.key)}">${escapeHtml(s.label.replace(/ &.*/, ''))}</span>`).join('');
  const focusOpts = Object.keys(FOCUS).map(k => `<option value="${k}" ${k === _focus ? 'selected' : ''}>${FOCUS_LABEL[k]}</option>`).join('');

  h.innerHTML = `<div class="kbp-wrap">
    <div class="kbp-tbar">
      <h1 class="kbp-h1">Construction Project Knowledge</h1>
      <div class="kbp-searchwrap"><span class="kbp-sic">⌕</span>
        <input class="kbp-search" id="kbp-search" placeholder="Search ${_flat.length} project types — data center, refinery, metro, villa…" autocomplete="off">
        <div class="kbp-suggest" id="kbp-suggest"></div></div>
      <button class="kbp-btn" data-act="browse">▤ Browse library (${_flat.length})</button>
      <div class="kbp-expwrap"><button class="kbp-btn" data-act="export">⭳ Export ▾</button>
        <div class="kbp-expmenu" id="kbp-expmenu">
          <div class="kbp-expitem" data-act="exp-pdf"><span class="di">▤</span><span><b>Export to PDF</b><span>Print this project type</span></span></div>
          <div class="kbp-expitem" data-act="exp-xls"><span class="di">▦</span><span><b>Export to Excel</b><span>Planned for a later version</span></span></div>
        </div></div>
    </div>

    <div class="kbp-selrow">
      <div class="kbp-selg"><span class="kbp-l">Project type</span>
        <div class="kbp-cascade">
          <select id="kbp-sector">${sectorOpts}</select><span class="kbp-sep">▸</span>
          <select id="kbp-type">${typeOpts}</select></div></div>
      <div class="kbp-selg"><span class="kbp-l">Sector</span><div class="kbp-ptchips">${sectorChips}</div></div>
      <div class="kbp-selg"><span class="kbp-l">Trade focus</span><select id="kbp-focus">${focusOpts}</select></div>
    </div>

    <div class="kbp-grid">
      <div class="kbp-col">
        ${cardHeader(pb, ov)}
        ${cardOverviewSeq(pb)}
        ${cardWbs(pb)}
        ${cardTradeSeq(pb)}
      </div>
      ${rail(pb, ov)}
    </div>
    <div class="kbp-overlay kbp-hide" id="kbp-ov"></div>
  </div>`;
  wire();
}

function cardHeader(pb, ov) {
  const pills = (ov.primary_systems || []).slice(0, 8).map(s =>
    `<div class="kbp-bpill"><div class="n">${escapeHtml(shortName(s.name))} <span class="ct">PRIMARY</span></div><div class="d">${escapeHtml(s.discipline_label || '')}</div></div>`).join('');
  const nPrim = (ov.primary_systems || []).length;
  return `<div class="kbp-card kbp-pad">
    <div class="kbp-ihead"><div>
      <div class="t">${escapeHtml(pb.name)}</div>
      <div class="c">${escapeHtml(pb.sector_label || '')} · ${nPrim} primary disciplines</div></div>
      <span class="kbp-mode">▣ Project knowledge</span></div>
    ${ov.notes ? `<div class="kbp-brief">${escapeHtml(ov.notes)}</div>` : ''}
    <div class="kbp-l" style="margin-top:14px">Main components / disciplines</div>
    <div class="kbp-band">${pills || '<span class="kbp-muted">—</span>'}</div>
  </div>`;
}

function cardOverviewSeq(pb) {
  const phases = (pb.sequence || {}).phases || [];
  const flow = phases.map((p, i) => `<div class="kbp-seqstep ${i === phases.length - 1 ? 'hold' : ''}"><div class="sn">Phase ${i + 1}</div><div class="st">${escapeHtml(p.name)}</div></div>`).join('');
  return `<div class="kbp-card kbp-pad">
    <div class="kbp-ch"><h3>Sequence of work — overview</h3><span class="m">how this type is built, at a glance · logic order, not dates</span></div>
    <div class="kbp-seqflow">${flow || '<span class="kbp-muted">—</span>'}</div>
    <div class="kbp-formula">The front is driven by engineering &amp; procurement; commissioning owns the tail. Full step-by-step detail for each discipline / trade is below.</div>
  </div>`;
}

function cardWbs(pb) {
  const wbs = pb.wbs || {}, bl = pb.baseline || {};
  const rows = (wbs.branches || []).map(b => `<div class="kbp-wbsrow"><span class="kbp-wc">${escapeHtml(b.code)}</span><span class="kbp-wn">${escapeHtml(b.name || '')}</span></div>`).join('');
  const tag = wbs.source === 'curated' ? '<span class="kbp-tag">Curated standard</span>' : '<span class="kbp-tag">Composed from systems</span>';
  const dl = bl.available ? `<button class="kbp-btn" data-act="baseline" data-type="${escapeHtml(bl.type || '')}">⭳ Download baseline (P6 XML)</button>` : '';
  return `<div class="kbp-card kbp-pad">
    <div class="kbp-ch"><h3>Suggested WBS</h3><span class="m">${tag}</span></div>
    <div>${rows || '<div class="kbp-muted">—</div>'}</div>
    <div class="kbp-fileact"><button class="kbp-btn" data-act="copywbs">⧉ Copy for P6</button><button class="kbp-btn" data-act="exp-xls">⭳ Export WBS (Excel)</button>${dl}</div>
    <div class="kbp-formula" style="margin-top:12px">${escapeHtml(wbs.note || '')}</div>
  </div>`;
}

function cardTradeSeq(pb) {
  const trades = groupTrades((pb.sequence || {}).detail);
  const allow = FOCUS[_focus];
  const shown = allow ? trades.filter(t => allow.includes(t.discipline)) : trades;
  const primary = shown.filter(t => t.primary), secondary = shown.filter(t => !t.primary);
  const lead = primary.length ? primary : shown;
  const rest = primary.length ? secondary : [];
  const cardFor = (t) => {
    const gi = gateIndex(t.stages);
    const chain = t.stages.map((s, i) => `${i ? '<span class="op">→</span>' : ''}<span class="chip ${i === gi ? 'hold' : ''}">${i === gi ? '⚑ ' : ''}${escapeHtml(s)}</span>`).join('');
    const sub = t.systems.length > 1 ? `<span class="kbp-tsub">${escapeHtml(t.systems.slice(0, 3).join(' · '))}${t.systems.length > 3 ? ' · +' + (t.systems.length - 3) : ''}</span>` : '';
    return `<div class="kbp-ccard"><div class="kbp-cch"><span class="nm"><span class="kbp-cdot" style="background:${discColor(t.discipline)}"></span>${escapeHtml(t.discipline)}${sub}</span><span class="kbp-st kbp-good">● Curated</span></div>
      <div class="kbp-cbody"><div class="kbp-chain">${chain}</div></div></div>`;
  };
  const cards = lead.map(cardFor).join('');
  const more = rest.length ? `<details style="margin-bottom:10px"><summary style="cursor:pointer;font-size:12px;font-weight:600;color:var(--accent);padding:4px 0">Show ${rest.length} secondary trade${rest.length === 1 ? '' : 's'}</summary><div style="margin-top:8px">${rest.map(cardFor).join('')}</div></details>` : '';
  return `<div class="kbp-card kbp-pad kbp-smart">
    <div class="kbp-ch"><h3>Suggested sequence of work — by discipline / trade</h3><span class="m">the typical order each trade builds in</span></div>
    ${cards || '<div class="kbp-muted">No trades match this filter.</div>'}
    ${more}
    <div class="kbp-formula">⚑ marks a typical hold point — that step usually completes before the next trade can start. Sequences are typical references from the construction knowledge base — adapt to your methodology, access &amp; packaging. Never a check or score of your schedule.</div>
  </div>`;
}

function rail(pb, ov) {
  const ev = pb.evidence || {};
  const pats = (ev.patterns || []).slice(0, 10).map(p => `<span class="kbp-refchip">${escapeHtml(p.system)}</span>`).join('');
  const bl = pb.baseline || {};
  return `<div class="kbp-rail">
    <div class="kbp-rc"><h4>▣ Knowledge reference</h4>
      <div class="sub">${escapeHtml(pb.sector_label || '')} › <b>${escapeHtml(pb.name)}</b></div>
      <div class="kbp-l">Powered by knowledge patterns</div>
      <div class="kbp-refchips" style="margin-top:6px">${pats || '<span class="kbp-muted">—</span>'}</div>
      <div class="kbp-l" style="margin-top:8px">Knowledge coverage</div>
      <div class="kbp-cov"><i style="width:74%;background:var(--success)"></i><i style="width:20%;background:var(--warning)"></i><i style="width:6%;background:var(--muted)"></i></div>
      <div style="font-size:11px;color:var(--ink-soft)">Curated reference — a typical guide, not a validation of your schedule.</div></div>
    <div class="kbp-rc"><h4>◪ Project context</h4>
      <div class="kbp-rrow"><span>Sector</span><b>${escapeHtml(pb.sector_label || '')}</b></div>
      <div class="kbp-rrow"><span>Primary disciplines</span><b>${(ov.primary_systems || []).length}</b></div>
      <div class="kbp-rrow"><span>WBS branches</span><b>${(pb.wbs && pb.wbs.branches || []).length}</b></div>
      <div class="kbp-rrow"><span>Baseline file</span><b>${bl.available ? 'Available (P6 XML)' : 'Not available'}</b></div></div>
    <div class="kbp-rc"><h4>✓ Evidence &amp; confidence</h4>
      <div class="kbp-rrow"><span>Source</span><span class="kbp-st kbp-good">● Curated reference</span></div>
      <div class="kbp-rrow"><span>Learned from your projects</span><b>none yet</b></div>
      <div style="font-size:10.5px;color:var(--muted);margin-top:8px">Absence of knowledge never implies your schedule is correct. Import your own schedules to grow the learned reference — nothing is fabricated.</div></div>
  </div>`;
}

function browseModal() {
  const groups = (_lib.sectors || []).map(s => `<div class="kbp-bd"><div class="kbp-bd-h">${escapeHtml(s.label)} <span>${(s.types || []).length}</span></div>${(s.types || []).map(t => `<button class="kbp-bi ${t.archetype === _pb.archetype ? 'on' : ''}" data-open="${escapeHtml(t.archetype)}">${escapeHtml(t.name)}</button>`).join('')}</div>`).join('');
  return `<div class="kbp-modal"><div class="kbp-modal-h"><b>Browse the project-type library — ${_flat.length} types</b><button class="kbp-x" data-act="closebrowse">✕</button></div>
    <div class="kbp-modal-b">${groups}</div></div>`;
}

// ── interaction ─────────────────────────────────────────────────────────────
function wire() {
  const sectorSel = document.getElementById('kbp-sector');
  if (sectorSel) sectorSel.onchange = () => {
    _sector = sectorSel.value;
    const first = (_lib.sectors.find(s => s.key === _sector) || { types: [] }).types[0];
    if (first) openType(first.archetype);
  };
  const typeSel = document.getElementById('kbp-type');
  if (typeSel) typeSel.onchange = () => openType(typeSel.value);
  const focusSel = document.getElementById('kbp-focus');
  if (focusSel) focusSel.onchange = () => { _focus = focusSel.value; render(); };

  const search = document.getElementById('kbp-search'), sug = document.getElementById('kbp-suggest');
  if (search) search.oninput = () => {
    const q = search.value.trim().toLowerCase();
    if (!q) { sug.classList.remove('on'); return; }
    const hits = _flat.filter(x => x.name.toLowerCase().includes(q)).slice(0, 10);
    sug.innerHTML = hits.map(h => `<div class="kbp-sug" data-open="${escapeHtml(h.archetype)}">${escapeHtml(h.name)}<span>${escapeHtml(h.sector_label)}</span></div>`).join('') || '<div class="kbp-sug kbp-muted">No match</div>';
    sug.classList.add('on');
  };

  host().onclick = (e) => {
    const open = e.target.closest('[data-open]');
    if (open) { document.getElementById('kbp-ov')?.classList.add('kbp-hide'); openType(open.dataset.open); return; }
    const chip = e.target.closest('[data-sector]');
    if (chip) { _sector = chip.dataset.sector; const first = (_lib.sectors.find(s => s.key === _sector) || { types: [] }).types[0]; if (first) openType(first.archetype); return; }
    const act = e.target.closest('[data-act]'); if (!act) return;
    const a = act.dataset.act;
    const menu = document.getElementById('kbp-expmenu');
    if (a === 'browse') { const ov = document.getElementById('kbp-ov'); ov.innerHTML = browseModal(); ov.classList.remove('kbp-hide'); }
    else if (a === 'closebrowse') document.getElementById('kbp-ov')?.classList.add('kbp-hide');
    else if (a === 'export') { e.stopPropagation(); menu?.classList.toggle('on'); }
    else if (a === 'exp-pdf') { menu?.classList.remove('on'); try { window.print(); } catch {} }
    else if (a === 'exp-xls') { menu?.classList.remove('on'); showError('Excel export for the Knowledge Base is planned for a later version.'); }
    else if (a === 'copywbs') copyWbs(act);
    else if (a === 'baseline') downloadBaseline(act.dataset.type);
  };
  document.addEventListener('click', () => document.getElementById('kbp-expmenu')?.classList.remove('on'));
}

function copyWbs(btn) {
  if (!_pb || !_pb.wbs) return;
  const text = (_pb.wbs.branches || []).map((b, i) => `${i + 1}\t${b.name}`).join('\n');
  try { navigator.clipboard.writeText(text); } catch {}
  const t = btn.innerHTML; btn.innerHTML = '✓ Copied'; setTimeout(() => { btn.innerHTML = t; }, 1400);
}
async function downloadBaseline(type) {
  if (!type) return;
  const slug = type.replace(/[^\w]+/g, '_').replace(/^_+|_+$/g, '');
  let path = null;
  try { path = await window.pywebview.api.choose_save_path(`${slug}_starter_baseline.xml`, 'xml'); }
  catch { showError('Could not open the save dialog.'); return; }
  if (!path) return;
  try {
    const d = await api('/api/kb/starter-xml', { type, output_path: path });
    if (!d.ok) showError(d.error || 'Could not generate the baseline file.');
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}
