// Knowledge Base — "Construction Project Knowledge". Per project type, a 6-part
// playbook: (1) Brief & scope explained for a planner new to the type +
// components; (2) MEP systems; (3) construction sequence as a chart by trade with
// a live Focus filter (discipline / MEP); (4) suggested WBS in P6 tree style to
// Level 6+; (5) Basis of Planning (AACE 38R-06); baseline XER. Curated content is
// rendered verbatim where authored; otherwise a derived fallback from the system
// patterns. Reference-first: no score, no verdict. Offline; app tokens (6 modes).

import { state }      from './state.js';
import { showError }  from './render.js';
import { escapeHtml } from './format.js';
import { printView }  from './printview.js';

let _lib = null, _pb = null, _sector = null, _flat = [], _focus = 'all';
const host = () => document.getElementById('kb-playbooks-section');
const api = (p, body) => fetch(`http://localhost:${state.serverPort}${p}`, body
  ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  : undefined).then(r => r.json());
const loading = (m) => `<div class="kbp-loading">${escapeHtml(m)}</div>`;

// discipline label -> a categorical chart token (theme-aware, stable)
const DISC_CHART = { Electrical: 1, Mechanical: 2, 'Extra-Low Voltage': 3, Finishes: 4, Civil: 5,
  Structural: 6, Piping: 2, Instrumentation: 3, Plumbing: 2, 'Fire Protection': 1, Process: 4,
  Utilities: 5, 'Mechanical Piping': 2, Commissioning: 6, Unclassified: 5 };
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

// order disciplines by construction sequence (front to back)
const DISC_ORDER = ['Civil', 'Structural', 'Finishes', 'Process', 'Mechanical', 'Mechanical Piping',
  'Piping', 'Plumbing', 'Electrical', 'Extra-Low Voltage', 'Instrumentation', 'Fire Protection',
  'Utilities', 'Commissioning', 'Unclassified'];
const discOrder = (d) => { const i = DISC_ORDER.indexOf(d); return i < 0 ? 99 : i; };

function groupTrades(detail) {
  const map = new Map();
  for (const d of (detail || [])) {
    if (!(d.stages || []).length) continue;
    const key = d.discipline_label || 'Other';
    if (!map.has(key)) map.set(key, { discipline: key, primary: false, systems: [], stages: [], _score: -1 });
    const g = map.get(key);
    if (d.primary) g.primary = true;
    g.systems.push(shortName(d.name));
    const score = (d.primary ? 1000 : 0) + d.stages.length;
    if (score > g._score) { g._score = score; g.stages = d.stages.map(prettyStage); }
  }
  return [...map.values()].sort((a, b) => discOrder(a.discipline) - discOrder(b.discipline) || a.discipline.localeCompare(b.discipline));
}

// ── Focus filter (curated). A trade/lane matches a group by its "kind" tags. ──
const FOCUS_GROUPS = [
  { key: 'all', label: 'All trades', kinds: null },
  { key: 'civil', label: 'Civil / Structural', kinds: ['civil'] },
  { key: 'electrical', label: 'Electrical', kinds: ['electrical'] },
  { key: 'mechanical', label: 'Mechanical', kinds: ['mechanical'] },
  { key: 'elvfirebms', label: 'ELV / Fire / BMS', kinds: ['elv', 'fire', 'bms'] },
  { key: 'comm', label: 'Commissioning', kinds: ['comm'] },
];
const groupOf = (k) => FOCUS_GROUPS.find(g => g.key === k) || FOCUS_GROUPS[0];
function kindMatches(kind, group) {
  if (!group || !group.kinds) return true;
  return (kind || []).some(k => group.kinds.includes(k));
}
// derived-fallback focus (discipline labels)
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
  // ONE selector: all types grouped by sector (sector shown as a chip)
  const typeOpts = sectors.map(s => `<optgroup label="${escapeHtml(s.label)}">` +
    (s.types || []).map(t => `<option value="${escapeHtml(t.archetype)}" ${t.archetype === pb.archetype ? 'selected' : ''}>${escapeHtml(t.name)}</option>`).join('') +
    `</optgroup>`).join('');

  h.innerHTML = `<div class="kbp-wrap">
    <div class="kbp-tbar">
      <h1 class="kbp-h1">Construction Project Knowledge</h1>
      <div class="kbp-searchwrap"><span class="kbp-sic">⌕</span>
        <input class="kbp-search" id="kbp-search" placeholder="Search ${_flat.length} project types — data center, refinery, metro, villa…" autocomplete="off">
        <div class="kbp-suggest" id="kbp-suggest"></div></div>
      <button class="kbp-btn" data-act="browse">▤ Browse library (${_flat.length})</button>
      <div class="kbp-expwrap"><button class="kbp-btn" data-act="export">⭳ Export ▾</button>
        <div class="kbp-expmenu" id="kbp-expmenu">
          <div class="kbp-expitem" data-act="exp-pdf"><span class="di">▤</span><span><b>Export to PDF</b><span>This project type — a submittal-ready document</span></span></div>
          <div class="kbp-expitem" data-act="exp-xls"><span class="di">▦</span><span><b>Export to Excel</b><span>Planned for a later version</span></span></div>
        </div></div>
    </div>

    <div class="kbp-selrow">
      <div class="kbp-selg kbp-selone"><span class="kbp-l">Project type</span>
        <div class="kbp-selbox">
          <select id="kbp-type">${typeOpts}</select>
          <span class="kbp-sct">${escapeHtml(pb.sector_label || '')}</span></div></div>
    </div>

    <div class="kbp-grid">
      <div class="kbp-col">
        ${cardHeader(pb, ov)}
        ${cardMep(pb)}
        ${cardOverviewSeq(pb)}
        ${cardSequence(pb)}
        ${cardWbs(pb)}
        ${cardBasisOfPlanning(pb)}
      </div>
      ${rail(pb, ov)}
    </div>
    <div class="kbp-overlay kbp-hide" id="kbp-ov"></div>
  </div>`;
  wire();
}

// ── 1 · Brief & scope + components ────────────────────────────────────────────
function briefScope(brief) {
  const l = (t) => `<div class="kbp-l" style="margin-top:16px">${t}</div>`;
  let out = brief.intro ? `<div class="kbp-callout">${escapeHtml(brief.intro)}</div>` : '';
  if ((brief.scope || []).length) {
    out += l('Scope of works — what the project includes, end to end');
    out += `<div class="kbp-scope">${brief.scope.map(s =>
      `<div class="kbp-si"><span class="sk">${escapeHtml(s.name)}</span>${escapeHtml(s.desc || '')}</div>`).join('')}</div>`;
  }
  if ((brief.glossary || []).length) {
    out += l('Key terms — in plain words (for a first-time planner)');
    out += `<div class="kbp-gloss">${brief.glossary.map(g =>
      `<div class="kbp-gi"><b>${escapeHtml(g.term)}</b> — ${escapeHtml(g.plain)}</div>`).join('')}</div>`;
  }
  if ((brief.must_get_right || []).length) {
    out += l('What you must get right in the plan');
    out += `<ul class="kbp-must">${brief.must_get_right.map(m => `<li>${escapeHtml(m)}</li>`).join('')}</ul>`;
  }
  return out;
}
function cardHeader(pb, ov) {
  const cur = pb.curated;
  const comps = (cur && cur.components) ? cur.components
    : (ov.primary_systems || []).map(s => ({ name: shortName(s.name), desc: s.discipline_label, primary: true }));
  const pills = comps.slice(0, 8).map(c =>
    `<div class="kbp-bpill"><div class="n">${escapeHtml(c.name)}${c.primary ? ' <span class="ct">PRIMARY</span>' : ''}</div><div class="d">${escapeHtml(c.desc || '')}</div></div>`).join('');
  const nPrim = (ov.primary_systems || []).length;
  const ctx = (cur && cur.context) ? cur.context : `${nPrim} primary disciplines`;

  let briefHtml = '';
  const b = cur && cur.brief;
  if (b && typeof b === 'object') briefHtml = briefScope(b);
  else { const text = (typeof b === 'string' && b) ? b : (ov.notes || ''); briefHtml = text ? `<div class="kbp-brief">${escapeHtml(text)}</div>` : ''; }

  return `<div class="kbp-card kbp-pad">
    <div class="kbp-ihead"><div>
      <div class="t">${escapeHtml(pb.name)}</div>
      <div class="c">${escapeHtml(pb.sector_label || '')} · ${escapeHtml(ctx)}</div></div>
      <span class="kbp-mode">▣ Project knowledge</span></div>
    ${briefHtml}
    <div class="kbp-l" style="margin-top:16px">Main components / disciplines</div>
    <div class="kbp-band">${pills || '<span class="kbp-muted">—</span>'}</div>
  </div>`;
}

// ── MEP systems ───────────────────────────────────────────────────────────────
function cardMep(pb) {
  const mep = pb.curated && pb.curated.mep_systems;
  if (!(mep && mep.length)) return '';
  const boxes = mep.map(m => `<div class="kbp-mepbox"><div class="hd" style="background:${discColor(m.discipline)}">${escapeHtml(m.discipline)}</div>
    <ul>${(m.items || []).map(it => `<li>${escapeHtml(it)}</li>`).join('')}</ul></div>`).join('');
  return `<div class="kbp-card kbp-pad">
    <div class="kbp-ch"><h3>MEP systems</h3><span class="m">the building-services breakdown, by discipline</span></div>
    <div class="kbp-mepgrid">${boxes}</div>
  </div>`;
}

// ── 2 · Sequence — overview strip ─────────────────────────────────────────────
function cardOverviewSeq(pb) {
  const names = (pb.curated && pb.curated.overview_phases) ? pb.curated.overview_phases : ((pb.sequence || {}).phases || []).map(p => p.name);
  const flow = names.map((n, i) => `<div class="kbp-seqstep ${i === names.length - 1 ? 'hold' : ''}"><div class="sn">Phase ${i + 1}</div><div class="st">${escapeHtml(n)}</div></div>`).join('');
  return `<div class="kbp-card kbp-pad">
    <div class="kbp-ch"><h3>Sequence of work — overview</h3><span class="m">how this type is built, at a glance · logic order, not dates</span></div>
    <div class="kbp-seqflow">${flow || '<span class="kbp-muted">—</span>'}</div>
  </div>`;
}

// ── 2b · Sequence — chart by trade + live Focus filter ────────────────────────
function cardSequence(pb) {
  const cur = pb.curated;
  if (cur && cur.trades && cur.sequence_chart) return curatedSequence(cur);
  return derivedSequence(pb);
}

function curatedSequence(cur) {
  const trades = cur.trades, chart = cur.sequence_chart;
  const present = FOCUS_GROUPS.filter(g => g.key === 'all' || trades.some(t => kindMatches(t.kind, g)));
  const pills = present.map(g => `<span class="kbp-fpill ${g.key === _focus ? 'on' : ''}" data-focus="${g.key}">${escapeHtml(g.label)}</span>`).join('');
  const g = groupOf(_focus);

  const nph = (chart.phases || []).length || 7;                       // chart column count varies by type
  const gcol = `grid-template-columns:150px repeat(${nph},1fr)`;
  const glcol = `grid-template-columns:repeat(${nph},1fr)`;
  const cols = `<div class="kbp-ccols" style="${gcol}"><div class="ch">Trade</div>${(chart.phases || []).map(p => `<div class="ch">${escapeHtml(p)}</div>`).join('')}</div>`;
  const gl = (chart.phases || []).map(() => '<i></i>').join('');
  const lanes = (chart.lanes || []).map(l => {
    const dim = _focus !== 'all' && !kindMatches(l.kind, g);
    const flags = (l.holds || []).map(h => `<span class="kbp-flag" style="left:${h}%">⚑</span>`).join('');
    return `<div class="kbp-lane ${dim ? 'dim' : ''}" style="${gcol}"><div class="ln"><span class="kbp-cdot" style="background:${discColor(l.disc)}"></span>${escapeHtml(l.trade)}</div>
      <div class="track"><div class="kbp-gl" style="${glcol}">${gl}</div>
        <div class="kbp-bar" style="left:${+l.start}%;width:${+l.width}%;background:${discColor(l.disc)}">${escapeHtml(l.label || '')}</div>${flags}</div></div>`;
  }).join('');

  const shown = _focus === 'all' ? trades : trades.filter(t => kindMatches(t.kind, g));
  let detail;
  if (_focus === 'all') {
    detail = shown.map(t => {
      const holds = t.holds || [];
      const chain = (t.steps || []).map((s, i) => `${i ? '<span class="op">→</span>' : ''}<span class="chip ${holds.includes(i) ? 'hold' : ''}">${holds.includes(i) ? '⚑ ' : ''}${escapeHtml(s)}</span>`).join('');
      return `<div class="kbp-ccard"><div class="kbp-cch"><span class="nm"><span class="kbp-cdot" style="background:${discColor(t.disc)}"></span>${escapeHtml(t.name)}</span></div>
        <div class="kbp-cbody"><div class="kbp-chain">${chain}</div></div></div>`;
    }).join('');
  } else {
    detail = `<div class="kbp-tsteps">${shown.map(t => {
      const holds = t.holds || [];
      const li = (t.steps || []).map((s, i) => `<li>${escapeHtml(s)}${holds.includes(i) ? ' <span class="kbp-hold">⚑ hold</span>' : ''}</li>`).join('');
      return `<div class="kbp-tstepcard"><div class="th"><span class="kbp-cdot" style="background:${discColor(t.disc)}"></span>Detailed steps — ${escapeHtml(t.name)}</div><ol class="kbp-steps">${li}</ol></div>`;
    }).join('') || '<div class="kbp-muted">No trades match this focus.</div>'}</div>`;
  }

  return `<div class="kbp-card kbp-pad kbp-smart">
    <div class="kbp-ch"><h3>Sequence of work — chart by trade</h3><span class="m">how the trades run &amp; overlap · pick a focus to filter</span></div>
    <div class="kbp-focus"><span class="kbp-fl">Focus</span>${pills}</div>
    <div class="kbp-chart">${cols}${lanes}</div>
    <div class="kbp-seqdetail">${detail}</div>
    <div class="kbp-formula">⚑ marks a typical hold / inspection point — that step usually completes before the next can start. Typical references from the construction knowledge base — adapt to your methodology, access &amp; packaging. Never a check or score of your schedule.</div>
  </div>`;
}

function derivedSequence(pb) {
  const trades = groupTrades((pb.sequence || {}).detail);
  const allow = FOCUS[_focus] || null;
  const shown = allow ? trades.filter(t => allow.includes(t.discipline)) : trades;
  const primary = shown.filter(t => t.primary), secondary = shown.filter(t => !t.primary);
  const lead = primary.length ? primary : shown;
  const rest = primary.length ? secondary : [];
  const pills = Object.keys(FOCUS).map(k => `<span class="kbp-fpill ${k === _focus ? 'on' : ''}" data-focus="${k}">${FOCUS_LABEL[k]}</span>`).join('');
  const cardFor = (t) => {
    const gi = gateIndex(t.stages);
    const chain = t.stages.map((s, i) => `${i ? '<span class="op">→</span>' : ''}<span class="chip ${i === gi ? 'hold' : ''}">${i === gi ? '⚑ ' : ''}${escapeHtml(s)}</span>`).join('');
    const sub = t.systems.length > 1 ? `<span class="kbp-tsub">${escapeHtml(t.systems.slice(0, 3).join(' · '))}${t.systems.length > 3 ? ' · +' + (t.systems.length - 3) : ''}</span>` : '';
    return `<div class="kbp-ccard"><div class="kbp-cch"><span class="nm"><span class="kbp-cdot" style="background:${discColor(t.discipline)}"></span>${escapeHtml(t.discipline)}${sub}</span></div>
      <div class="kbp-cbody"><div class="kbp-chain">${chain}</div></div></div>`;
  };
  const more = rest.length ? `<details style="margin-bottom:10px"><summary style="cursor:pointer;font-size:12px;font-weight:600;color:var(--accent);padding:4px 0">Show ${rest.length} secondary trade${rest.length === 1 ? '' : 's'}</summary><div style="margin-top:8px">${rest.map(cardFor).join('')}</div></details>` : '';
  return `<div class="kbp-card kbp-pad kbp-smart">
    <div class="kbp-ch"><h3>Suggested sequence of work — by discipline / trade</h3><span class="m">the typical order each trade builds in</span></div>
    <div class="kbp-focus"><span class="kbp-fl">Focus</span>${pills}</div>
    ${lead.map(cardFor).join('') || '<div class="kbp-muted">No trades match this filter.</div>'}
    ${more}
    <div class="kbp-formula">⚑ marks a typical hold point. Typical references from the construction knowledge base — adapt to your methodology. Never a check or score of your schedule.</div>
  </div>`;
}

// ── 3 · Suggested WBS — P6 tree ───────────────────────────────────────────────
function cardWbs(pb) {
  const wbs = pb.wbs || {}, bl = pb.baseline || {};
  const cur = pb.curated && pb.curated.wbs;
  const xer = (pb.curated && pb.curated.baseline && pb.curated.baseline.xer) || bl.available;
  const dl = xer ? `<button class="kbp-btn" data-act="baseline" data-type="${escapeHtml(pb.archetype || '')}">⭳ Download baseline (XER)</button>` : '';
  const copy = `<button class="kbp-btn" data-act="copywbs">⧉ Copy for P6</button><button class="kbp-btn" data-act="exp-xls">⭳ Export WBS (Excel)</button>`;

  if (cur && cur.length) {
    const hasLevels = cur.some(w => w.level);
    const rows = cur.map(w => {
      const lv = w.level || 1;
      return `<div class="kbp-p6r ${lv === 1 ? 'l1' : (lv === 2 ? 'l2' : '')}"><div class="c">${escapeHtml(w.code || '')}</div><div class="n" style="padding-left:${(lv - 1) * 18}px">${lv > 1 ? '<span class="car">▾</span>' : ''}${escapeHtml(w.name || '')}</div><div class="lv">${lv}</div></div>`;
    }).join('');
    return `<div class="kbp-card kbp-pad">
      <div class="kbp-ch"><h3>Suggested WBS — Primavera P6 style</h3><span class="m">${hasLevels ? 'coded to UNIFORMAT II + MasterFormat · expandable past Level 6' : 'curated standard'}</span></div>
      <div class="kbp-p6"><div class="kbp-p6h"><div>WBS Code</div><div>WBS Name</div><div>Level</div></div>${rows}</div>
      <div class="kbp-fileact">${copy}${dl}</div>
    </div>`;
  }
  // derived / legacy flat branches
  const branches = wbs.branches || [];
  const rows = branches.map(b => `<div class="kbp-wbsrow"><span class="kbp-wc">${escapeHtml(b.code)}</span><span class="kbp-wn">${escapeHtml(b.name || '')}</span></div>`).join('');
  const tag = wbs.source === 'curated' ? '<span class="kbp-tag">Curated standard</span>' : '<span class="kbp-tag">Composed from systems</span>';
  return `<div class="kbp-card kbp-pad">
    <div class="kbp-ch"><h3>Suggested WBS</h3><span class="m">${tag}</span></div>
    <div>${rows || '<div class="kbp-muted">—</div>'}</div>
    <div class="kbp-fileact">${copy}${dl}</div>
    <div class="kbp-formula" style="margin-top:12px">${escapeHtml(wbs.note || '')}</div>
  </div>`;
}

// ── 4 · Basis of Planning (AACE 38R-06) ───────────────────────────────────────
function bopTable(t) {
  if (!t || !(t.rows || []).length) return '';
  const head = (t.columns || []).map(c => `<th>${escapeHtml(c)}</th>`).join('');
  const body = t.rows.map(r => `<tr>${r.map(c => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`).join('');
  return `<table class="kbp-lltab"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}
function cardBasisOfPlanning(pb) {
  const bop = pb.curated && pb.curated.basis_of_planning;
  if (!(bop && (bop.sections || []).length)) return '';
  const secs = bop.sections.map((s, i) =>
    `<div class="kbp-bh"><span class="bn">${i + 1}</span><h5>${escapeHtml(s.heading)}</h5></div>
     <p class="kbp-bp">${escapeHtml(s.body || '')}</p>${bopTable(s.table)}`).join('');
  return `<div class="kbp-card kbp-pad kbp-bop">
    <div class="kbp-ch"><h3>Basis of Planning</h3><span class="m">${escapeHtml(bop.standard || 'AACE 38R-06 — Documenting the Schedule Basis')}</span></div>
    <div class="kbp-formula" style="margin:0 0 10px">Your methodology conclusion, written as the recognised Basis of Planning document — read it on screen, or export it to PDF.</div>
    ${secs}
  </div>`;
}

// ── right rail ────────────────────────────────────────────────────────────────
function rail(pb, ov) {
  const cur = pb.curated;
  const ev = pb.evidence || {};
  const pats = (ev.patterns || []).slice(0, 10).map(p => `<span class="kbp-refchip">${escapeHtml(p.system)}</span>`).join('');
  const bl = pb.baseline || {};
  const xer = (cur && cur.baseline && cur.baseline.xer) || bl.available;
  const stds = (cur && cur.standards) || [];
  const stdCard = stds.length ? `<div class="kbp-rc"><h4>▤ Standards used</h4>
    ${stds.map(s => `<div class="kbp-std"><span class="sc">${escapeHtml(s.code || '')}</span>${escapeHtml(s.text || '')}</div>`).join('')}</div>` : '';
  const nTrades = cur && cur.trades ? cur.trades.length : (ov.primary_systems || []).length;
  const nWbs = (cur && cur.wbs) ? cur.wbs.length : ((pb.wbs && pb.wbs.branches) || []).length;
  return `<div class="kbp-rail">
    <div class="kbp-rc"><h4>◪ Project context</h4>
      <div class="kbp-rrow"><span>Sector</span><b>${escapeHtml(pb.sector_label || '')}</b></div>
      <div class="kbp-rrow"><span>${cur && cur.trades ? 'Trades covered' : 'Primary disciplines'}</span><b>${nTrades}</b></div>
      <div class="kbp-rrow"><span>WBS rows</span><b>${nWbs}</b></div>
      <div class="kbp-rrow"><span>Baseline file</span><b>${xer ? 'Available (XER)' : 'Not available'}</b></div></div>
    ${stdCard}
    <div class="kbp-rc"><h4>▣ Knowledge reference</h4>
      <div class="sub">${escapeHtml(pb.sector_label || '')} › <b>${escapeHtml(pb.name)}</b></div>
      <div class="kbp-l" style="margin-top:8px">Powered by knowledge patterns</div>
      <div class="kbp-refchips" style="margin-top:6px">${pats || '<span class="kbp-muted">—</span>'}</div>
      <div class="kbp-l" style="margin-top:10px">Knowledge coverage</div>
      <div class="kbp-cov"><i style="width:74%;background:var(--success)"></i><i style="width:20%;background:var(--warning)"></i><i style="width:6%;background:var(--muted)"></i></div>
      <div style="font-size:11px;color:var(--ink-soft)">Curated reference — a typical guide, not a validation of your schedule.</div></div>
    <div class="kbp-rc"><h4>✓ Evidence &amp; confidence</h4>
      <div class="kbp-rrow"><span>Source</span><span class="kbp-st kbp-good">● Curated reference</span></div>
      <div class="kbp-rrow"><span>Learned from your projects</span><b>none yet</b></div>
      <div style="font-size:10.5px;color:var(--muted);margin-top:8px">Absence of knowledge never implies your schedule is correct. Nothing is fabricated.</div></div>
  </div>`;
}

function browseModal() {
  const groups = (_lib.sectors || []).map(s => `<div class="kbp-bd"><div class="kbp-bd-h">${escapeHtml(s.label)} <span>${(s.types || []).length}</span></div>${(s.types || []).map(t => `<button class="kbp-bi ${t.archetype === _pb.archetype ? 'on' : ''}" data-open="${escapeHtml(t.archetype)}">${escapeHtml(t.name)}</button>`).join('')}</div>`).join('');
  return `<div class="kbp-modal"><div class="kbp-modal-h"><b>Browse the project-type library — ${_flat.length} types</b><button class="kbp-x" data-act="closebrowse">✕</button></div>
    <div class="kbp-modal-b">${groups}</div></div>`;
}

// ── interaction ─────────────────────────────────────────────────────────────
function wire() {
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
    const foc = e.target.closest('[data-focus]');
    if (foc) { _focus = foc.dataset.focus; render(); return; }
    const act = e.target.closest('[data-act]'); if (!act) return;
    const a = act.dataset.act;
    const menu = document.getElementById('kbp-expmenu');
    if (a === 'browse') { const ov = document.getElementById('kbp-ov'); ov.innerHTML = browseModal(); ov.classList.remove('kbp-hide'); }
    else if (a === 'closebrowse') document.getElementById('kbp-ov')?.classList.add('kbp-hide');
    else if (a === 'export') { e.stopPropagation(); menu?.classList.toggle('on'); }
    else if (a === 'exp-pdf') { menu?.classList.remove('on'); exportPdf(); }
    else if (a === 'exp-xls') { menu?.classList.remove('on'); exportExcel(); }
    else if (a === 'copywbs') copyWbs(act);
    else if (a === 'baseline') downloadBaseline(act.dataset.type);
  };
  document.addEventListener('click', () => document.getElementById('kbp-expmenu')?.classList.remove('on'));
}

// ── Export: build clean report sections from the playbook, then PDF / Excel ──
function playbookSections(pb) {
  const cur = pb.curated || {}, e = escapeHtml, secs = [];
  const b = cur.brief;
  if (b && typeof b === 'object') {
    let h = `<p>${e(b.intro || '')}</p>`;
    if ((b.scope || []).length) h += `<h3 style="margin:12px 0 4px">Scope of works</h3><ul>${b.scope.map(s => `<li><b>${e(s.name)}</b> — ${e(s.desc || '')}</li>`).join('')}</ul>`;
    if ((b.glossary || []).length) h += `<h3 style="margin:12px 0 4px">Key terms — in plain words</h3><ul>${b.glossary.map(g => `<li><b>${e(g.term)}</b> — ${e(g.plain)}</li>`).join('')}</ul>`;
    if ((b.must_get_right || []).length) h += `<h3 style="margin:12px 0 4px">What you must get right</h3><ul>${b.must_get_right.map(m => `<li>${e(m)}</li>`).join('')}</ul>`;
    if ((cur.components || []).length) h += `<h3 style="margin:12px 0 4px">Main components</h3><ul>${cur.components.map(c => `<li><b>${e(c.name)}</b> — ${e(c.desc || '')}${c.primary ? ' <i>(primary)</i>' : ''}</li>`).join('')}</ul>`;
    secs.push({ key: 'brief', label: 'Project brief & scope', html: h });
  } else {
    const t = (pb.overview || {}).notes || '';
    if (t) secs.push({ key: 'brief', label: 'Project brief', html: `<p>${e(t)}</p>` });
  }
  if ((cur.mep_systems || []).length)
    secs.push({ key: 'mep', label: 'MEP systems', html: cur.mep_systems.map(m => `<h3 style="margin:10px 0 4px">${e(m.discipline)}</h3><ul>${(m.items || []).map(i => `<li>${e(i)}</li>`).join('')}</ul>`).join('') });
  const trades = cur.trades;
  if ((trades || []).length)
    secs.push({ key: 'sequence', label: 'Sequence of work — by trade', html: trades.map(t => { const hd = t.holds || []; return `<h3 style="margin:10px 0 4px">${e(t.name)}</h3><ol>${(t.steps || []).map((s, i) => `<li>${e(s)}${hd.includes(i) ? ' <b>⚑ hold point</b>' : ''}</li>`).join('')}</ol>`; }).join('') });
  const wbs = cur.wbs;
  if ((wbs || []).length) {
    const rows = wbs.map(w => `<tr><td style="font-family:monospace;color:#4338ca">${e(w.code)}</td><td style="padding-left:${((w.level || 1) - 1) * 14}px">${e(w.name)}</td><td style="text-align:center">${w.level}</td></tr>`).join('');
    secs.push({ key: 'wbs', label: 'Suggested WBS (Primavera P6)', html: `<table border="1" cellspacing="0" cellpadding="5" style="border-collapse:collapse;font-size:12px;width:100%"><thead><tr><th align="left">WBS Code</th><th align="left">WBS Name</th><th>Level</th></tr></thead><tbody>${rows}</tbody></table>` });
  }
  const bop = cur.basis_of_planning;
  if (bop && (bop.sections || []).length)
    secs.push({ key: 'bop', label: `Basis of Planning — ${e(bop.standard || 'AACE 38R-06')}`, html: bop.sections.map((s, i) => {
      let t = `<h3 style="margin:12px 0 3px">${i + 1}. ${e(s.heading)}</h3><p>${e(s.body || '')}</p>`;
      if (s.table && (s.table.rows || []).length) t += `<table border="1" cellspacing="0" cellpadding="4" style="border-collapse:collapse;font-size:12px;margin-top:4px"><thead><tr>${(s.table.columns || []).map(c => `<th align="left">${e(c)}</th>`).join('')}</tr></thead><tbody>${s.table.rows.map(r => `<tr>${r.map(c => `<td>${e(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
      return t;
    }).join('') });
  return secs;
}
function exportPdf() {
  if (!_pb) { showError('Open a project type first.'); return; }
  const secs = playbookSections(_pb);
  if (!secs.length) { showError('Nothing to export for this project type yet.'); return; }
  printView({ module: 'kb', title: _pb.name, subtitle: `${_pb.sector_label || ''} · Construction Project Knowledge`, sections: secs });
}
async function exportExcel() {
  if (!_pb) { showError('Open a project type first.'); return; }
  const slug = (_pb.archetype || 'playbook').replace(/[^\w]+/g, '_').replace(/^_+|_+$/g, '');
  let path = null;
  try { path = await window.pywebview.api.choose_save_path(`${slug}_knowledge.xlsx`, 'xlsx'); }
  catch { showError('Could not open the save dialog.'); return; }
  if (!path) return;
  try {
    const d = await api('/api/kb/excel', { archetype: _pb.archetype, output_path: path });
    if (!d.ok) showError(d.error || 'Could not create the Excel file.');
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}

function copyWbs(btn) {
  if (!_pb) return;
  const cur = _pb.curated && _pb.curated.wbs;
  let text;
  if (cur && cur.length) text = cur.map(w => `${'\t'.repeat(Math.max(0, (w.level || 1) - 1))}${w.code}\t${w.name}`).join('\n');
  else text = ((_pb.wbs && _pb.wbs.branches) || []).map((b, i) => `${i + 1}\t${b.name}`).join('\n');
  try { navigator.clipboard.writeText(text); } catch {}
  const t = btn.innerHTML; btn.innerHTML = '✓ Copied'; setTimeout(() => { btn.innerHTML = t; }, 1400);
}
async function downloadBaseline(type) {
  if (!type) return;
  const slug = type.replace(/[^\w]+/g, '_').replace(/^_+|_+$/g, '');
  let path = null;
  try { path = await window.pywebview.api.choose_save_path(`${slug}_baseline.xer`, 'xer'); }
  catch { showError('Could not open the save dialog.'); return; }
  if (!path) return;
  try {
    const d = await api('/api/kb/starter-xer', { type, output_path: path });
    if (!d.ok) showError(d.error || 'Could not generate the baseline file.');
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}
