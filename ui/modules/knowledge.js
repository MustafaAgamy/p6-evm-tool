// Knowledge Base — "Construction Project Knowledge", presented in the same style
// as Productivity & Resource Intelligence: a toolbar (title + search + browse),
// a cascading Sector ▸ Project-type selector row, and a main-column + right-rail
// layout of cards. Per project type it shows a brief + components, the overview
// construction sequence, a suggested WBS (copy / download baseline), and the
// suggested sequence of work BY DISCIPLINE / TRADE. Reference-first: no score,
// no verdict. Offline; themed through the app appearance tokens (6 modes).

import { state }      from './state.js';
import { showError }  from './render.js';
import { escapeHtml } from './format.js';

let _lib = null;          // library payload (sectors -> project-type cards)
let _pb = null;           // open playbook
let _sector = null;       // current sector key
let _flat = [];           // flat [{archetype,name,sector,sector_label}] for search
const host = () => document.getElementById('kb-playbooks-section');
const api = (p, body) => fetch(`http://localhost:${state.serverPort}${p}`, body
  ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  : undefined).then(r => r.json());
const loading = (m) => `<div class="kbp-loading">${escapeHtml(m)}</div>`;
function prettyStage(s) { s = (s || '').replace(/_/g, ' ').trim(); return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

// discipline label -> a categorical chart token (theme-aware, stable)
const DISC_CHART = { Electrical:1, Mechanical:2, 'Extra-Low Voltage':3, Finishes:4, Civil:5,
  Structural:6, Piping:2, Instrumentation:3, Plumbing:2, 'Fire Protection':1, Process:4,
  Utilities:5, 'Mechanical Piping':2, Commissioning:6, Unclassified:5 };
function discColor(label) {
  let n = DISC_CHART[label];
  if (!n) { let h = 0; for (const c of (label || '')) h = (h + c.charCodeAt(0)) % 6; n = h + 1; }
  return `var(--chart-${n})`;
}

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
    _lib = d;
    _flat = [];
    for (const s of (_lib.sectors || [])) for (const t of (s.types || []))
      _flat.push({ archetype: t.archetype, name: t.name, sector: s.key, sector_label: s.label });
    let pick = _flat.find(x => x.archetype === 'data_center') || _flat[0];
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
    _pb = d.playbook;
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

  h.innerHTML = `<div class="kbp-wrap">
    <div class="kbp-tbar">
      <h1 class="kbp-h1">Construction Project Knowledge</h1>
      <div class="kbp-searchwrap"><span class="kbp-sic">⌕</span>
        <input class="kbp-search" id="kbp-search" placeholder="Search ${_flat.length} project types — data center, refinery, metro, villa…" autocomplete="off">
        <div class="kbp-suggest" id="kbp-suggest"></div></div>
      <button class="kbp-btn" data-act="browse">▤ Browse library (${_flat.length})</button>
    </div>

    <div class="kbp-selrow">
      <div class="kbp-selg"><span class="kbp-l">Project type</span>
        <div class="kbp-cascade">
          <select id="kbp-sector">${sectorOpts}</select><span class="kbp-sep">▸</span>
          <select id="kbp-type">${typeOpts}</select></div></div>
      <div class="kbp-selg"><span class="kbp-l">Sector</span><div class="kbp-ptchips">${sectorChips}</div></div>
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
  const pills = [...(ov.primary_systems || []).map(s => [s, true]), ...(ov.secondary_systems || []).map(s => [s, false])]
    .slice(0, 8).map(([s, pri]) => `<div class="kbp-bpill"><div class="n">${escapeHtml(s.name)}${pri ? ' <span class="ct">PRIMARY</span>' : ''}</div><div class="d">${escapeHtml(s.discipline_label || '')}</div></div>`).join('');
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
  const steps = (pb.sequence || {}).steps || [];
  const flow = steps.map((s, i) => `<div class="kbp-seqstep ${i === steps.length - 1 ? 'hold' : ''}"><div class="sn">Step ${s.n}</div><div class="st">${escapeHtml(s.name)}</div></div>`).join('');
  return `<div class="kbp-card kbp-pad">
    <div class="kbp-ch"><h3>Sequence of work — overview</h3><span class="m">how this type is built, at a glance · logic order, not dates</span></div>
    <div class="kbp-seqflow">${flow || '<span class="kbp-muted">—</span>'}</div>
    <div class="kbp-formula">Full step-by-step detail for each discipline / trade is below.</div>
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
    <div class="kbp-fileact"><button class="kbp-btn" data-act="copywbs">⧉ Copy for P6</button>${dl}</div>
    <div class="kbp-formula" style="margin-top:12px">${escapeHtml(wbs.note || '')}</div>
  </div>`;
}

function cardTradeSeq(pb) {
  const detail = (pb.sequence || {}).detail || [];
  const holds = pb.hold_points || [];
  const withStages = detail.filter(d => (d.stages || []).length);
  const primary = withStages.filter(d => d.primary);
  const secondary = withStages.filter(d => !d.primary);
  const lead = primary.length ? primary : withStages;      // fall back if none flagged primary
  const rest = primary.length ? secondary : [];
  const cardFor = (d) => {
    const chain = d.stages.map((s, i) => `${i ? '<span class="op">→</span>' : ''}<span class="chip">${escapeHtml(prettyStage(s))}</span>`).join('');
    return `<div class="kbp-ccard"><div class="kbp-cch"><span class="nm"><span class="kbp-cdot" style="background:${discColor(d.discipline_label)}"></span>${escapeHtml(d.name)}</span><span class="kbp-st kbp-good">● Curated</span></div>
      <div class="kbp-cbody"><div class="kbp-chain">${chain}</div></div></div>`;
  };
  const cards = lead.map(cardFor).join('');
  const more = rest.length ? `<details style="margin-bottom:10px"><summary style="cursor:pointer;font-size:12px;font-weight:600;color:var(--accent);padding:4px 0">Show ${rest.length} secondary trade${rest.length === 1 ? '' : 's'}</summary><div style="margin-top:8px">${rest.map(cardFor).join('')}</div></details>` : '';
  const hp = holds.length ? `<div class="kbp-l" style="margin-top:6px">Key cross-discipline hold points</div>
    <div class="kbp-hp">${holds.slice(0, 8).map(h => `<div class="kbp-hprow"><b>${escapeHtml(h.before || '')}</b> <span class="op">→</span> <b>${escapeHtml(h.after || '')}</b><span class="kbp-hpr">${escapeHtml(h.reason || '')}</span></div>`).join('')}</div>` : '';
  return `<div class="kbp-card kbp-pad kbp-smart">
    <div class="kbp-ch"><h3>Suggested sequence of work — by discipline / trade</h3><span class="m">the typical order each trade builds in</span></div>
    ${cards || '<div class="kbp-muted">—</div>'}
    ${more}
    ${hp}
    <div class="kbp-formula">Sequences are typical references from the construction knowledge base — adapt to your methodology, access &amp; packaging. Never a check or score of your schedule.</div>
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
    if (a === 'browse') { const ov = document.getElementById('kbp-ov'); ov.innerHTML = browseModal(); ov.classList.remove('kbp-hide'); }
    else if (a === 'closebrowse') document.getElementById('kbp-ov')?.classList.add('kbp-hide');
    else if (a === 'copywbs') copyWbs(act);
    else if (a === 'baseline') downloadBaseline(act.dataset.type);
  };
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
