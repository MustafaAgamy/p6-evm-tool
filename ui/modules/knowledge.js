// Knowledge Base — "Project Type Playbooks". A browsable, reference-first library:
// pick a project type and read how it is typically built (step-by-step construction
// sequence by discipline), take a suggested WBS, and download a baseline schedule
// file to start from. Offline; served from the bundled KB. Never scores or judges a
// schedule. Themed entirely through the app's appearance tokens (6 modes).

import { state }      from './state.js';
import { showError }  from './render.js';
import { escapeHtml } from './format.js';

let _lib = null;          // cached library payload
let _pb = null;           // cached open playbook
let _view = 'lib';        // 'lib' | 'pb'
const _detail = { open: false };   // sequence: step-by-step (false) vs detailed grid (true)
const TOUR_KEY = 'p6evm_kb_tour_seen';

const host = () => document.getElementById('kb-playbooks-section');
const api  = (p) => `http://localhost:${state.serverPort}${p}`;

// ── icons (explicit sizes) ──────────────────────────────────────────────────
const IC = {
  book:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0018 0V5"/><path d="M3 12a9 3 0 0018 0"/></svg>',
  search:'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg>',
  info:'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/></svg>',
  dl:'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12M8 11l4 4 4-4M4 21h16"/></svg>',
  back:'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M11 6l-6 6 6 6"/></svg>',
  shield:'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/></svg>',
  copy:'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 012-2h10"/></svg>',
};

// discipline → a categorical chart token (theme-aware, stable per label)
const DISC_CHART = { Electrical:1, Mechanical:2, 'Extra-Low Voltage':3, Finishes:4, Civil:5,
  Structural:6, Piping:2, Instrumentation:3, Plumbing:2, 'Fire Protection':1, Process:4,
  Utilities:5, 'Mechanical Piping':2, Commissioning:6, Unclassified:5 };
function discColor(label) {
  let n = DISC_CHART[label];
  if (!n) { let h = 0; for (const c of (label || '')) h = (h + c.charCodeAt(0)) % 6; n = h + 1; }
  return `var(--chart-${n})`;
}

const STATUS = {
  knowledge_available:['kbp-st-ok','Knowledge available'],
  potentially_relevant:['kbp-st-rel','Potentially relevant'],
  insufficient_evidence:['kbp-st-insuf','Insufficient evidence'],
  not_assessed:['kbp-st-na','Not assessed'],
  planner_review:['kbp-st-review','Planner review required'],
};
const covLabel = { Sequence:'Sequence', WBS:'WBS', 'Baseline file':'Baseline', Learned:'Learned' };
function statusChip(key, prefix) {
  const [cls, label] = STATUS[key] || STATUS.not_assessed;
  return `<span class="kbp-st ${cls}"><span class="kbp-dot"></span>${prefix ? prefix + ' · ' : ''}${label}</span>`;
}
const loading = (msg) => `<div class="kbp-loading">${escapeHtml(msg)}</div>`;

// ── page lifecycle ──────────────────────────────────────────────────────────
export function showPlaybooks() {
  hideOthers();
  const h = host(); if (!h) return;
  h.classList.remove('hidden');
  if (!_lib) { h.innerHTML = loading('Loading the Knowledge Base…'); fetchLibrary(); }
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

async function fetchLibrary() {
  try {
    const r = await fetch(api('/api/kb/playbooks'));
    const d = await r.json();
    if (!d.ok) { showError(d.error || 'Could not load the Knowledge Base.'); return; }
    _lib = d; _view = 'lib'; render();
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}
async function openPlaybook(archetype) {
  const h = host(); if (h) h.innerHTML = loading('Opening the Playbook…');
  try {
    const r = await fetch(api('/api/kb/playbook'), {
      method:'POST', headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ archetype }) });
    const d = await r.json();
    if (!d.ok) { showError(d.error || 'Could not open the Playbook.'); render(); return; }
    _pb = d.playbook; _view = 'pb'; _detail.open = false; render();
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}

function render() {
  const h = host(); if (!h) return;
  h.innerHTML = _view === 'pb' && _pb ? renderPlaybook() : renderLibrary();
  h.scrollTop = 0;
  wire();
  if (_view === 'lib') maybeTour();
}

// ── LIBRARY ─────────────────────────────────────────────────────────────────
function renderLibrary() {
  const secs = (_lib.sectors || []);
  const counts = _lib.counts || {};
  const card = (c) => {
    const cov = (c.coverage || []).map(x => statusChip(x.status, covLabel[x.area] || x.area)).join('');
    return `<button class="kbp-card" data-pb="${escapeHtml(c.archetype)}">
      <div class="kbp-card-h"><span class="kbp-card-name">${escapeHtml(c.name)}</span>
        <span class="kbp-sector">${escapeHtml(c.sector_label || '')}</span></div>
      <div class="kbp-drv">${escapeHtml(c.driver || '')}</div>
      <div class="kbp-stat"><span><b>${c.system_count}</b> systems</span>${c.baseline_available
        ? `<span><b>${c.wbs_count}</b> WBS pkgs</span><span><b>1</b> baseline file</span>`
        : `<span class="kbp-thin-note">reference only</span>`}</div>
      <div class="kbp-cov">${cov}</div></button>`;
  };
  const sectors = secs.map(s => `<section class="kbp-secblock">
    <h3>${escapeHtml(s.label)} <span class="kbp-n">${s.count} type${s.count === 1 ? '' : 's'}</span></h3>
    <div class="kbp-cards">${(s.types || []).map(card).join('')}</div></section>`).join('');
  return `<div class="kbp-wrap">
    <div class="kbp-hero">
      <div class="kbp-hero-top"><span class="kbp-hero-ic">${IC.book}</span>
        <div><h2>Construction Knowledge Base</h2>
          <p>Learn how each <b>type of construction project</b> is normally built — the typical construction
          sequence across the disciplines, a suggested work breakdown, and ready baseline files to start from.
          A reference for planners; it never checks, scores or judges your schedule.</p></div>
        <button class="kbp-help" data-act="tour">${IC.info} Take the tour</button></div>
      <div class="kbp-steps">
        <div class="kbp-step"><span class="kbp-sn">1</span><b>Pick your project type</b><span>Browse by sector, or search — ${counts.types || ''} project types.</span></div>
        <div class="kbp-step"><span class="kbp-sn">2</span><b>See how it's built</b><span>Its step-by-step construction sequence by discipline, the hold points, and a suggested WBS.</span></div>
        <div class="kbp-step"><span class="kbp-sn">3</span><b>Start faster</b><span>Copy the WBS into P6 and download a baseline schedule file to build on.</span></div>
      </div>
    </div>
    <div class="kbp-searchbar">${IC.search}<input id="kbp-search" type="text" placeholder="Find a project type — refinery, villa, metro, data center, hospital…" autocomplete="off"></div>
    <div id="kbp-lib-body">${sectors}</div>
  </div>`;
}

function filterLibrary(q) {
  q = (q || '').trim().toLowerCase();
  const body = document.getElementById('kbp-lib-body'); if (!body || !_lib) return;
  const match = (c) => !q || (c.name + ' ' + (c.sector_label || '') + ' ' + (c.driver || '')).toLowerCase().includes(q);
  const secs = (_lib.sectors || []).map(s => ({ ...s, types: (s.types || []).filter(match) })).filter(s => s.types.length);
  const card = (c) => `<button class="kbp-card" data-pb="${escapeHtml(c.archetype)}">
    <div class="kbp-card-h"><span class="kbp-card-name">${escapeHtml(c.name)}</span>
      <span class="kbp-sector">${escapeHtml(c.sector_label || '')}</span></div>
    <div class="kbp-drv">${escapeHtml(c.driver || '')}</div>
    <div class="kbp-stat"><span><b>${c.system_count}</b> systems</span>${c.baseline_available
      ? `<span><b>${c.wbs_count}</b> WBS pkgs</span><span><b>1</b> baseline file</span>` : `<span class="kbp-thin-note">reference only</span>`}</div>
    <div class="kbp-cov">${(c.coverage || []).map(x => statusChip(x.status, covLabel[x.area] || x.area)).join('')}</div></button>`;
  body.innerHTML = secs.length
    ? secs.map(s => `<section class="kbp-secblock"><h3>${escapeHtml(s.label)} <span class="kbp-n">${s.types.length}</span></h3><div class="kbp-cards">${s.types.map(card).join('')}</div></section>`).join('')
    : `<div class="kbp-empty">No project type matches “${escapeHtml(q)}”. Try a shorter word, or browse the sectors.</div>`;
}

// ── PLAYBOOK ────────────────────────────────────────────────────────────────
function sysChip(s) {
  return `<span class="kbp-sysch ${s.primary ? 'pri' : ''}"><span class="kbp-cdot" style="background:${discColor(s.discipline_label)}"></span>${escapeHtml(s.name)}</span>`;
}
function renderPlaybook() {
  const pb = _pb, ov = pb.overview || {};
  const sub = ['Overview','Sequence','WBS','Baseline Files','Interfaces','Evidence']
    .map((s, i) => `<button data-sec="kbp-s${i}"${i === 0 ? ' class="on"' : ''}>${s}</button>`).join('');
  return `<div class="kbp-wrap">
    <div class="kbp-pbhead">
      <div><button class="kbp-bk" data-act="lib">${IC.back} All project types</button>
        <div class="kbp-pbtitle"><h2>${escapeHtml(pb.name)}</h2>
          <span class="kbp-sector">${escapeHtml(pb.sector_label || '')}</span></div></div>
    </div>
    <div class="kbp-pbintro">${IC.info}<span>A <b>Playbook</b> shows how a <b>${escapeHtml(pb.name)}</b> is typically built — read it as a reference while you plan. Jump to any section below.</span></div>
    <div class="kbp-subnav">${sub}</div>
    ${secOverview(pb, ov)}${secSequence(pb)}${secWbs(pb)}${secFiles(pb)}${secInterfaces(pb)}${secEvidence(pb)}
  </div>`;
}

function secOverview(pb, ov) {
  const mix = (ov.discipline_mix || []).slice(0, 8).map(m =>
    `<span class="kbp-mix"><span class="kbp-cdot" style="background:${discColor(m.label)}"></span>${escapeHtml(m.label)}</span>`).join('');
  const civ = (ov.civil_interfaces || []).map(x => `<li>${escapeHtml(x)}</li>`).join('');
  const comm = (ov.commissioning_focus || []).map(x => `<li>${escapeHtml(x)}</li>`).join('');
  const cov = (pb.coverage || []).map(x => statusChip(x.status, covLabel[x.area] || x.area)).join('');
  return `<section class="kbp-sec" id="kbp-s0"><div class="kbp-sech"><span class="kbp-snum">1</span><h3>Overview &amp; Shape</h3></div>
    <div class="kbp-secintro">The shape of this project type in 30 seconds — what dominates it, which disciplines lead, and the key civil gates.</div>
    <div class="kbp-ovgrid">
      <div class="kbp-card2">
        <div class="kbp-expert"><div class="kbp-el">${IC.info} Expert read</div><p>${escapeHtml(ov.notes || '')}</p></div>
        <div class="kbp-lbl">Primary systems</div><div class="kbp-syschips">${(ov.primary_systems || []).map(sysChip).join('') || '<span class="kbp-muted">—</span>'}</div>
        <div class="kbp-lbl">Secondary systems</div><div class="kbp-syschips">${(ov.secondary_systems || []).map(sysChip).join('') || '<span class="kbp-muted">—</span>'}</div>
      </div>
      <div class="kbp-card2">
        <div class="kbp-lbl">Discipline mix</div><div class="kbp-syschips">${mix}</div>
        <div class="kbp-lbl">Civil interfaces (the gates)</div><ul class="kbp-bullets">${civ || '<li class="kbp-muted">—</li>'}</ul>
        <div class="kbp-lbl">Commissioning focus</div><ul class="kbp-bullets">${comm || '<li class="kbp-muted">—</li>'}</ul>
        <div class="kbp-lbl">Coverage</div><div class="kbp-cov">${cov}</div>
      </div>
    </div></section>`;
}

function secSequence(pb) {
  const seq = pb.sequence || {}, steps = seq.steps || [], detail = seq.detail || [];
  const stepper = steps.map(s => `<div class="kbp-sstep"><div class="kbp-sl"><div class="kbp-sn2">${s.n}</div><div class="kbp-sline"></div></div>
    <div class="kbp-sc"><b>${escapeHtml(s.name)}</b><div class="kbp-sd">${escapeHtml(s.desc)}</div>
      ${(s.disciplines || []).length ? `<div class="kbp-sdisc">${s.disciplines.map(d => `<span class="kbp-dchip"><span class="kbp-cdot" style="background:${discColor(d)}"></span>${escapeHtml(d)}</span>`).join('')}</div>` : ''}
      ${(s.systems || []).length ? `<div class="kbp-ssys">Systems: ${s.systems.map(escapeHtml).join(' · ')}</div>` : ''}
      ${s.gate ? `<div class="kbp-sgate">⚑ Hold point — ${escapeHtml(s.gate)}</div>` : ''}</div></div>`).join('');
  const grid = detail.map(d => `<div class="kbp-lane"><div class="kbp-lane-h"><span class="kbp-cdot" style="background:${discColor(d.discipline_label)}"></span><b class="${d.primary ? 'kbp-pri' : ''}">${escapeHtml(d.name)}</b><span class="kbp-lane-d">${escapeHtml(d.discipline_label)}</span></div>
    <div class="kbp-lane-stages">${(d.stages || []).map(st => `<span class="kbp-stg">${escapeHtml(st || '')}</span>`).join('') || '<span class="kbp-muted">—</span>'}</div></div>`).join('');
  return `<section class="kbp-sec" id="kbp-s1"><div class="kbp-sech"><span class="kbp-snum">2</span><h3>Construction Sequence</h3>
      <span class="kbp-cap">logic order — not a timeline · no dates or durations</span></div>
    <div class="kbp-secintro"><b>The heart of the Playbook.</b> How this type of project is normally built — step by step, from first works to handover, with the disciplines that lead each step and the hold points that gate the work.</div>
    <div class="kbp-seqctrl"><div class="kbp-toggle"><button class="${_detail.open ? '' : 'on'}" data-seq="steps">Step-by-step</button><button class="${_detail.open ? 'on' : ''}" data-seq="grid">Detailed by system</button></div></div>
    <div id="kbp-seq-steps" class="${_detail.open ? 'kbp-hide' : ''}"><div class="kbp-card2"><div class="kbp-stepper">${stepper}</div></div></div>
    <div id="kbp-seq-grid" class="${_detail.open ? '' : 'kbp-hide'}">
      <div class="kbp-howread">${IC.info}<div><b>Each system's stages, in sequence.</b> The bold systems dominate this project type. This is the same construction sequence as the steps, broken down system by system.</div></div>
      <div class="kbp-grid">${grid}</div></div>
  </section>`;
}

function secWbs(pb) {
  const wbs = pb.wbs || {}, branches = wbs.branches || [];
  const rows = branches.map(b => `<div class="kbp-wbsrow"><span class="kbp-wcode">${escapeHtml(b.code)}</span><span class="kbp-wname">${escapeHtml(b.name || '')}</span></div>`).join('');
  const tag = wbs.source === 'curated'
    ? `<span class="kbp-chip kbp-src-cur">${IC.shield} Curated standard</span>`
    : `<span class="kbp-chip kbp-src-comp">Composed from systems</span>`;
  return `<section class="kbp-sec" id="kbp-s2"><div class="kbp-sech"><span class="kbp-snum">3</span><h3>Suggested WBS</h3><span class="kbp-spacer"></span>${tag}</div>
    <div class="kbp-secintro">A suggested work breakdown for this project type — copy it into P6 and adapt it to your job.</div>
    <div class="kbp-card2">
      <div class="kbp-wbsbar"><span class="kbp-muted">${branches.length} branches</span><span class="kbp-spacer"></span>
        <button class="kbp-btn" data-act="copy-wbs">${IC.copy} Copy for P6</button></div>
      <div class="kbp-wbstree" id="kbp-wbstree">${rows || '<div class="kbp-muted">—</div>'}</div>
      <div class="kbp-note">${escapeHtml(wbs.note || '')}</div>
    </div></section>`;
}

function secFiles(pb) {
  const bl = pb.baseline || {};
  let card;
  if (bl.available) {
    const ms = (bl.milestones || []).slice(0, 6).map(m => `<span class="kbp-ms">${escapeHtml(m)}</span>`).join('');
    card = `<div class="kbp-filecard">
      <div class="kbp-ft"><span class="kbp-fic">${IC.book}</span><h4>Starter Baseline</h4><span class="kbp-fmt">P6 XML</span></div>
      <div class="kbp-counts"><span><b>${bl.wbs_count}</b> WBS branches</span><span><b>${bl.activity_count}</b> key activities</span><span><b>${(bl.milestones || []).length}</b> milestones</span></div>
      ${ms ? `<div class="kbp-mslist">${ms}</div>` : ''}
      <div class="kbp-whatnot"><b>Inside:</b> the full WBS, a placeholder activity per branch, the key/often-missing activities, and milestones — logically FS-linked so it schedules cleanly on F9. <b>Not inside:</b> durations are neutral placeholders; <b>no productivity, crews or resource loading</b> (a separate feature). A starter skeleton — never a certified schedule.</div>
      <div class="kbp-fileact"><button class="kbp-btn primary" data-act="download-baseline" data-type="${escapeHtml(bl.type || '')}">${IC.dl} Download baseline (P6 XML)</button></div>
    </div>`;
  } else {
    card = `<div class="kbp-filecard kbp-thin">
      <div class="kbp-ft"><span class="kbp-fic">${IC.info}</span><h4>No baseline file yet</h4><span class="kbp-fmt kbp-na">${STATUS.not_assessed[1]}</span></div>
      <div class="kbp-whatnot">A ready starter file isn't available for this type yet. Use the sequence and the suggested WBS above as your reference, and structure your own baseline in P6. <b>“Not available” does not mean your schedule is wrong</b> — it means the tool has no curated starter to hand you here.</div>
    </div>`;
  }
  return `<section class="kbp-sec" id="kbp-s3"><div class="kbp-sech"><span class="kbp-snum">4</span><h3>Baseline File Library</h3>
      <span class="kbp-cap">a head start — import &amp; F9, never a certified schedule</span></div>
    <div class="kbp-secintro">Ready-made P6 starter schedules for this project type — download one, open it in P6, and build your own programme on top. Structure and logic only.</div>
    <div class="kbp-filegrid">${card}</div>
    <div class="kbp-prodnote"><span class="kbp-cdot" style="background:var(--accent)"></span>Durations, resources, crews &amp; productivity are added by the <b>separate Productivity Knowledge Base</b> — these files carry logic &amp; structure only.</div>
  </section>`;
}

function secInterfaces(pb) {
  const holds = pb.hold_points || [], comm = pb.commissioning || {};
  const rows = holds.map(h => `<div class="kbp-hprow"><span class="kbp-ba">${escapeHtml(h.before || '')}</span>
    <span class="kbp-ar">→</span><span class="kbp-af">${escapeHtml(h.after || '')}</span>
    <span class="kbp-rs">${escapeHtml(h.reason || '')}</span>
    <span class="kbp-wt ${(h.strength || '').toLowerCase() === 'strong' ? 'strong' : 'mod'}">${(h.strength || '').toLowerCase() === 'strong' ? 'strong' : 'moderate'}</span></div>`).join('');
  const rungs = (comm.rungs || []).map((r, i) => `<div class="kbp-rung"><div class="kbp-rl"><div class="kbp-rn">${i + 1}</div><div class="kbp-rline"></div></div>
    <div class="kbp-rc"><b>${escapeHtml(r.title)}</b></div></div>`).join('');
  const tests = (comm.testing_requirements || []).map(t => `<span class="kbp-tg">${escapeHtml(t)}</span>`).join('');
  return `<section class="kbp-sec" id="kbp-s4"><div class="kbp-sech"><span class="kbp-snum">5</span><h3>Interfaces &amp; Hold Points</h3>
      <span class="kbp-cap">reference to eyeball your draft against · never a finding, never a score</span></div>
    <div class="kbp-secintro">The cross-discipline gates where baselines usually go wrong — one discipline must finish before another can start. Check your own draft against them.</div>
    <div class="kbp-card2">
      <div class="kbp-hpboard">${rows || '<div class="kbp-muted">No cross-discipline gates recorded for this type yet.</div>'}</div>
      <div class="kbp-note">Weight = how important the gate typically is (an <b>importance weight, not a correctness grade</b>). Strong gates are near-physical; moderate gates are usual practice that can flex by methodology.</div>
    </div>
    ${(comm.rungs || []).length ? `<div class="kbp-sech" style="margin-top:16px"><span class="kbp-snum kbp-alt">6</span><h3>Testing &amp; Commissioning Ladder</h3><span class="kbp-cap">typical, not mandatory</span></div>
    <div class="kbp-card2"><div class="kbp-ladder">${rungs}</div>${tests ? `<div class="kbp-lbl">Typical tests across the systems</div><div class="kbp-tags">${tests}</div>` : ''}</div>` : ''}
  </section>`;
}

function secEvidence(pb) {
  const ev = pb.evidence || {};
  const pats = (ev.patterns || []).map(p => `<span class="kbp-patch"><span class="kbp-dot ok"></span>${escapeHtml(p.name)} · <span class="kbp-muted">${escapeHtml(p.source)} · ${escapeHtml(p.status)}</span></span>`).join('');
  const vocab = (ev.status_vocab || []).map(v => `<div class="kbp-leg"><span class="kbp-ld ${STATUS[v.key] ? STATUS[v.key][0] : ''}"></span><div><b>${escapeHtml(v.label)}</b><span>${escapeHtml(v.desc)}</span></div></div>`).join('');
  return `<section class="kbp-sec" id="kbp-s5"><div class="kbp-sech"><span class="kbp-snum kbp-alt">7</span><h3>Evidence &amp; Provenance</h3></div>
    <div class="kbp-secintro">Where this knowledge comes from, and what the honest status labels mean — full transparency.</div>
    <div class="kbp-card2">
      <div class="kbp-lbl">Knowledge powering this Playbook</div><div class="kbp-patlist">${pats || '<span class="kbp-muted">—</span>'}</div>
      <div class="kbp-lbl" style="margin-top:12px">What the status labels mean</div>${vocab}
      <div class="kbp-trust">${IC.shield}<div><b>Absence of knowledge never means your schedule is correct.</b> This Playbook is a typical reference for a ${escapeHtml(pb.name)}; the right sequence, WBS and hold points for <i>your</i> project depend on methodology, site, procurement, packaging and client requirements.</div></div>
    </div></section>`;
}

// ── guided tour ─────────────────────────────────────────────────────────────
function maybeTour() {
  let seen = false;
  try { seen = localStorage.getItem(TOUR_KEY) === '1'; } catch {}
  if (!seen) openTour();
}
function openTour() {
  if (document.getElementById('kbp-tour')) return;
  const el = document.createElement('div');
  el.className = 'kbp-tour-backdrop'; el.id = 'kbp-tour';
  el.innerHTML = `<div class="kbp-tour-card">
    <span class="kbp-tour-badge">GUIDED TOUR · first time here</span>
    <div class="kbp-tour-h"><span class="kbp-tour-ic">${IC.book}</span>
      <div><h2>Welcome to your Construction Knowledge Base</h2>
        <p>A simple reference that shows you how any type of construction project is normally built — so you plan faster and don't miss the usual steps. Three things you can do:</p></div></div>
    <div class="kbp-tour-steps">
      <div class="kbp-tstep"><span class="kbp-tn">1</span><div><b>Pick your project type</b><p>Browse by sector or search — dozens of project types.</p></div></div>
      <div class="kbp-tstep"><span class="kbp-tn">2</span><div><b>See how it's built</b><p>The step-by-step construction sequence across every discipline, the hold points, and a suggested WBS.</p></div></div>
      <div class="kbp-tstep"><span class="kbp-tn">3</span><div><b>Start your schedule faster</b><p>Copy the WBS into P6 and download a ready baseline file.</p></div></div>
    </div>
    <div class="kbp-tour-not">${IC.shield}<span>It's a reference to <b>learn from</b> — it never checks, scores, or judges your own schedule.</span></div>
    <div class="kbp-tour-foot"><label><input type="checkbox" id="kbp-tour-dismiss" checked> Don't show this again</label><span class="kbp-spacer"></span>
      <button class="kbp-btn primary" id="kbp-tour-go">Start exploring →</button></div>
  </div>`;
  host().appendChild(el);
  el.querySelector('#kbp-tour-go').addEventListener('click', () => {
    if (document.getElementById('kbp-tour-dismiss')?.checked) { try { localStorage.setItem(TOUR_KEY, '1'); } catch {} }
    el.remove();
  });
}

// ── baseline download + WBS copy ────────────────────────────────────────────
async function downloadBaseline(type) {
  if (!type) return;
  let path = null;
  const slug = type.replace(/[^\w]+/g, '_').replace(/^_+|_+$/g, '');
  try { path = await window.pywebview.api.choose_save_path(`${slug}_starter_baseline.xml`, 'xml'); }
  catch { showError('Could not open the save dialog.'); return; }
  if (!path) return;
  try {
    const r = await fetch(api('/api/kb/starter-xml'), {
      method:'POST', headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ type, output_path: path }) });
    const d = await r.json();
    if (!d.ok) showError(d.error || 'Could not generate the baseline file.');
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}
function copyWbs() {
  if (!_pb || !_pb.wbs) return;
  const text = (_pb.wbs.branches || []).map((b, i) => `${i + 1}\t${b.name}`).join('\n');
  try { navigator.clipboard.writeText(text); } catch {}
  const btn = document.querySelector('[data-act="copy-wbs"]');
  if (btn) { const t = btn.innerHTML; btn.innerHTML = '✓ Copied'; setTimeout(() => { btn.innerHTML = t; }, 1400); }
}

// ── event wiring (delegated within the section) ─────────────────────────────
let _wired = false;
function wire() {
  const search = document.getElementById('kbp-search');
  if (search) search.addEventListener('input', () => filterLibrary(search.value));
  if (_wired) return; _wired = true;
  host().addEventListener('click', (e) => {
    const pbBtn = e.target.closest('[data-pb]'); if (pbBtn) { openPlaybook(pbBtn.dataset.pb); return; }
    const sq = e.target.closest('[data-seq]'); if (sq) { _detail.open = sq.dataset.seq === 'grid';
      document.getElementById('kbp-seq-steps')?.classList.toggle('kbp-hide', _detail.open);
      document.getElementById('kbp-seq-grid')?.classList.toggle('kbp-hide', !_detail.open);
      sq.parentElement.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === sq)); return; }
    const sn = e.target.closest('.kbp-subnav button'); if (sn) {
      document.querySelectorAll('.kbp-subnav button').forEach(b => b.classList.toggle('on', b === sn));
      document.getElementById(sn.dataset.sec)?.scrollIntoView({ behavior:'smooth', block:'start' }); return; }
    const act = e.target.closest('[data-act]'); if (act) {
      const a = act.dataset.act;
      if (a === 'lib') { _view = 'lib'; render(); }
      else if (a === 'tour') openTour();
      else if (a === 'copy-wbs') copyWbs();
      else if (a === 'download-baseline') downloadBaseline(act.dataset.type);
    }
  });
}
