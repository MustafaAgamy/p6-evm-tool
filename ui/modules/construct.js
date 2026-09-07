// Construction Logic & Buildability Intelligence — Edition 1 (reference-first).
//
// Two capabilities, no verdict:
//   • Knowledge Base   — browse/search the construction knowledge (sequences,
//                        logic, interfaces, evidence). A professional reference.
//   • Activity Intelligence — planner-INITIATED: pick an activity and the system
//                        SURFACES the relevant knowledge. It never checks, scores
//                        or validates the schedule; an empty result never means
//                        the schedule is correct (see the status vocabulary).
//
// There is no automatic Constructability Review, no /100 score and no findings
// register in Edition 1 (the R1–R7 engine stays in the codebase, unexposed).
// Resources / crew / productivity live in the separate Productivity KB feature.

import { state }        from './state.js';
import { showError, clearError } from './render.js';
import { escapeHtml }   from './format.js';

// ── module-local state (persists while the SPA module is loaded) ─────────────
let _ref = null;          // cached /api/kb/reference payload
let _view = 'kb';         // 'kb' | 'activity'
let _sysSel = null;       // selected system id (KB view)
let _kbSearch = '';
let _actSel = null;       // selected activity index (Activity view)
let _actSearch = '';
let _actKnow = {};        // cache: activity key -> activity-knowledge result

// ── icons (sized via CSS .ci-ic, never bare) ─────────────────────────────────
const _SVG = {
  book:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0018 0V5"/><path d="M3 12a9 3 0 0018 0"/></svg>',
  spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.8 4.4L18 9l-4.2 1.6L12 15l-1.8-4.4L6 9z"/></svg>',
  flip:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M17 2l4 4-4 4"/><path d="M3 11V9a4 4 0 014-4h14"/><path d="M7 22l-4-4 4-4"/><path d="M21 13v2a4 4 0 01-4 4H3"/></svg>',
  info:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/></svg>',
  shield:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/></svg>',
  pin:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12h4l2-5 3 10 2-5h7"/></svg>',
  search:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg>',
};
const ic = (k, cls) => `<span class="ci-ic${cls ? ' ' + cls : ''}">${_SVG[k] || ''}</span>`;

// ── canonical discipline grouping (the raw KB discipline codes are fragmented;
//    a planner thinks in ~6 disciplines). system-id → {group, order}. ──────────
const _GROUPS = [
  ['Structural & Civil',                 ['structural_steel', 'pipe_racks', 'civil_interface']],
  ['Architectural & Finishes',           ['architectural_finishing', 'floor_tiling_stone', 'joinery_fitout', 'sanitary_fixtures', 'waterproofing']],
  ['Mechanical & HVAC',                  ['chilled_water', 'hvac', 'plumbing', 'fire_fighting', 'mechanical_equipment', 'rotating_equipment', 'process_equipment', 'skids_packaged', 'tanks_vessels', 'utilities', 'conveying', 'insulation_coating']],
  ['Piping & Fabrication',               ['process_piping', 'utility_piping', 'pipe_spool_fabrication', 'local_fabrication']],
  ['Electrical, Instrumentation & Controls', ['electrical_power', 'containment_cabling', 'earthing', 'lighting', 'instrumentation', 'bms', 'fire_alarm']],
  ['Commissioning',                      ['commissioning']],
];
const _GROUP_OF = {};
_GROUPS.forEach(([name, ids], gi) => ids.forEach(id => { _GROUP_OF[id] = { name, order: gi }; }));
const groupOf = (sid) => _GROUP_OF[sid] || { name: 'Other systems', order: 99 };

// ── chip helpers ─────────────────────────────────────────────────────────────
function evChip(grade) {
  if (!grade) return '';
  const cls = { strong: 'ci-ev-strong', moderate: 'ci-ev-mod', emerging: 'ci-ev-emerg' }[grade.key] || 'ci-ev-emerg';
  return `<span class="ci-chip ${cls}">${escapeHtml(grade.label)}</span>`;
}
const _ST_CLS = {
  knowledge_available: 'ci-st-avail', potentially_relevant: 'ci-st-rel',
  insufficient_evidence: 'ci-st-insuf', not_assessed: 'ci-st-na', planner_review: 'ci-st-review',
};
const _ST_LABEL = {
  knowledge_available: 'Knowledge available', potentially_relevant: 'Potentially relevant',
  insufficient_evidence: 'Insufficient evidence', not_assessed: 'Not assessed', planner_review: 'Planner review',
};
function stChip(key, labelOverride) {
  const cls = _ST_CLS[key] || 'ci-st-na';
  return `<span class="ci-st ${cls}"><span class="ci-dot"></span>${escapeHtml(labelOverride || _ST_LABEL[key] || key)}</span>`;
}
const provChip = (p) => p
  ? `<span class="ci-chip ${p.status === 'curated' ? 'ci-src-cur' : 'ci-src-gen'}">${ic('shield', 'sm')}${escapeHtml(p.label || 'Reference')}</span>`
  : '';

// ── shell + toggle ───────────────────────────────────────────────────────────
export function renderConstructPanel() {
  const body = document.getElementById('construct-body');
  if (!body) return;
  body.innerHTML = `
    <div class="ci">
      <div class="ci-head">
        <span class="ci-hic">${ic('book', 'lg')}</span>
        <div class="ci-htx">
          <h2>Construction Logic &amp; Buildability Intelligence</h2>
          <p>A professional construction reference and a planner-initiated way to surface it against your activities.
             It <b>never checks, scores or validates your schedule</b> — you bring the judgement, this brings the reference and the reasoning.</p>
        </div>
      </div>
      <div class="ci-seg" id="ci-seg">
        <button data-ci="kb" class="${_view === 'kb' ? 'on' : ''}">${ic('book')} Knowledge Base</button>
        <button data-ci="activity" class="${_view === 'activity' ? 'on' : ''}">${ic('spark')} Activity Intelligence</button>
      </div>
      <div id="ci-view"></div>
    </div>`;
  document.getElementById('ci-seg').addEventListener('click', (e) => {
    const b = e.target.closest('[data-ci]'); if (!b) return;
    _view = b.dataset.ci;
    document.querySelectorAll('#ci-seg button').forEach(x => x.classList.toggle('on', x.dataset.ci === _view));
    renderView();
  });
  renderView();
}

function renderView() {
  const host = document.getElementById('ci-view');
  if (!host) return;
  if (_view === 'kb') renderKB(host); else renderActivity(host);
}

// ── KNOWLEDGE BASE (flagship reference) ──────────────────────────────────────
async function renderKB(host) {
  if (!_ref) {
    host.innerHTML = '<div class="cmp-loading">Loading the construction Knowledge Base…</div>';
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/kb/reference`);
      const d = await resp.json();
      if (!d.ok) { showError(d.error || 'Could not load the Knowledge Base.'); host.innerHTML = ''; return; }
      _ref = d;
    } catch { showError('Could not reach the local server. Try restarting the app.'); host.innerHTML = ''; return; }
  }
  if (_view !== 'kb') return;               // user toggled away while loading
  const details = _ref.details || {};
  const systems = Object.keys(details).filter(id => details[id]);
  if (!_sysSel || !details[_sysSel]) _sysSel = pickDefaultSystem(systems);
  const counts = (_ref.index && _ref.index.counts) || {};
  host.innerHTML = `
    <div class="ci-trust">${ic('shield')}<div><b>Reference knowledge — typical patterns, not rules.</b>
      Everything below is what is <i>usually</i> true. Whether it applies to your project depends on methodology, access,
      procurement, work packaging, means-and-methods and site conditions.</div></div>
    <div class="ci-kbbar">
      <div class="ci-search">${ic('search')}<input id="ci-kbsearch" type="text" placeholder="Search systems, work, aliases…" value="${escapeHtml(_kbSearch)}"></div>
      <div class="ci-counts"><b>${counts.systems || systems.length}</b> systems · <b>${counts.relationships || 0}</b> typical relationships · <b>${counts.archetypes || 0}</b> project types</div>
    </div>
    <div class="ci-kbgrid">
      <div class="ci-tax" id="ci-tax">${kbTaxonomy(details, systems)}</div>
      <div class="ci-detail" id="ci-detail">${kbDetail(details[_sysSel])}</div>
    </div>`;
  const s = document.getElementById('ci-kbsearch');
  if (s) s.addEventListener('input', () => {
    _kbSearch = s.value;
    const tax = document.getElementById('ci-tax');
    if (tax) tax.innerHTML = kbTaxonomy(details, systems);
  });
  wireTax();
}

function pickDefaultSystem(systems) {
  return systems.includes('process_piping') ? 'process_piping' : (systems[0] || null);
}

function kbMatch(det, q) {
  if (!q) return true;
  q = q.toLowerCase();
  if ((det.name || '').toLowerCase().includes(q)) return true;
  if ((det.system || '').toLowerCase().includes(q)) return true;
  if ((det.aliases || []).some(a => (a || '').toLowerCase().includes(q))) return true;
  if (groupOf(det.system).name.toLowerCase().includes(q)) return true;
  return false;
}

function kbTaxonomy(details, systems) {
  const q = _kbSearch.trim();
  const shown = systems.filter(id => kbMatch(details[id], q));
  if (!shown.length) return '<div class="ci-empty">No systems match your search.</div>';
  // group → systems, ordered
  const byGroup = new Map();
  shown.forEach(id => {
    const g = groupOf(id);
    if (!byGroup.has(g.name)) byGroup.set(g.name, { order: g.order, ids: [] });
    byGroup.get(g.name).ids.push(id);
  });
  const groups = [...byGroup.entries()].sort((a, b) => a[1].order - b[1].order);
  return groups.map(([name, g]) => {
    const rows = g.ids
      .sort((a, b) => (details[a].name || '').localeCompare(details[b].name || ''))
      .map(id => `<button class="ci-sys${id === _sysSel ? ' on' : ''}" data-sys="${escapeHtml(id)}">
        <span class="ci-sysn">${escapeHtml(details[id].name)}</span></button>`).join('');
    return `<div class="ci-taxg"><div class="ci-taxh">${escapeHtml(name)} <span class="ci-taxc">${g.ids.length}</span></div>${rows}</div>`;
  }).join('');
}

function wireTax() {
  const tax = document.getElementById('ci-tax');
  if (!tax) return;
  tax.addEventListener('click', (e) => {
    const b = e.target.closest('[data-sys]'); if (!b) return;
    _sysSel = b.dataset.sys;
    tax.querySelectorAll('.ci-sys').forEach(x => x.classList.toggle('on', x.dataset.sys === _sysSel));
    const det = document.getElementById('ci-detail');
    if (det) { det.innerHTML = kbDetail((_ref.details || {})[_sysSel]); det.scrollTop = 0; }
  });
}

// snake_case KB stage keys → readable titles; leave already-spaced titles alone.
function prettyStage(s) {
  s = s || '';
  if (s.indexOf(' ') === -1 && s.indexOf('_') !== -1) { s = s.replace(/_/g, ' '); s = s.charAt(0).toUpperCase() + s.slice(1); }
  return s;
}

function seqFlow(seq) {
  if (!seq || !seq.length) return '';
  const steps = seq.map((st, i) => {
    const acts = (st.activities || []).slice(0, 3).map(escapeHtml).join(' · ');
    return `<div class="ci-step"><div class="ci-stn">STAGE ${i + 1}</div>
      <div class="ci-stt">${escapeHtml(prettyStage(st.stage))}</div>${acts ? `<div class="ci-std">${acts}</div>` : ''}
      ${st.note ? `<div class="ci-stnote">${escapeHtml(st.note)}</div>` : ''}</div>`;
  }).join('<span class="ci-separr">›</span>');
  return `<div class="ci-seqflow">${steps}</div>`;
}

function relRows(rels) {
  if (!rels || !rels.length) return '<div class="ci-empty">No typical relationships recorded.</div>';
  return rels.map(r => `<div class="ci-rel">
      <span class="ci-relarr">${escapeHtml(r.before || '')}</span>
      <span class="ci-reldash">→</span>
      <div class="ci-relc"><b>${escapeHtml(r.after || '')}</b>
        ${r.reason ? `<div class="ci-relwhy">${escapeHtml(r.reason)}</div>` : ''}</div>
      <div class="ci-relmeta">${evChip(r.strength_grade)}${r.rel ? `<span class="ci-relt">${escapeHtml(r.rel)}</span>` : ''}</div>
    </div>`).join('');
}

function ifaceRows(ifs) {
  if (!ifs || !ifs.length) return '<div class="ci-empty">No cross-system interfaces recorded.</div>';
  return ifs.map(f => `<div class="ci-rel">
      <span class="ci-relarr ci-relwith">${escapeHtml(f.with_name || f.with || '')}</span>
      <div class="ci-relc"><b>${escapeHtml(f.requirement || '')}</b>
        <div class="ci-relwhy">${escapeHtml([f.type, f.phase].filter(Boolean).join(' · '))}</div></div>
      <div class="ci-relmeta">${evChip(f.strength_grade)}</div>
    </div>`).join('');
}

function chipList(items) {
  if (!items || !items.length) return '<div class="ci-empty">— none recorded —</div>';
  return `<div class="ci-reslist">${items.map(x => `<span class="ci-res">${escapeHtml(typeof x === 'string' ? x : (x.wp || ''))}</span>`).join('')}</div>`;
}

function bulletList(items) {
  if (!items || !items.length) return '<div class="ci-empty">— none recorded —</div>';
  return `<ul class="ci-ul">${items.map(x => `<li>${escapeHtml(x)}</li>`).join('')}</ul>`;
}

function kbDetail(det) {
  if (!det) return '<div class="ci-empty">Select a system on the left to see its construction knowledge.</div>';
  const tags = [groupOf(det.system).name, det.discipline_label || det.discipline, 'System · ' + det.name]
    .filter(Boolean).map(t => `<span class="ci-tag">${escapeHtml(t)}</span>`).join('');
  const aliases = (det.aliases || []).length ? `<span class="ci-tag">Aliases · ${escapeHtml((det.aliases || []).slice(0, 6).join(', '))}</span>` : '';
  return `
    <div class="ci-entry">
      <div class="ci-etop">
        <span class="ci-eic">${ic('pin', 'lg')}</span>
        <div class="ci-etx"><h3>${escapeHtml(det.name)}</h3><div class="ci-etags">${tags}${aliases}</div></div>
        <div class="ci-emeta">${provChip(det.provenance)}${stChip('knowledge_available')}</div>
      </div>
    </div>

    ${blk('spark', 'Typical construction sequence', 'the usual backbone — methodology, packaging &amp; tie-ins reshape it', stChip('knowledge_available'), seqFlow(det.sequence))}

    ${blk('spark', 'Typical relationships', 'before → after, with the reasoning and its strength', '', relRows(det.relationships))}

    ${blk('flip', 'Interfaces with other systems', 'where this work meets other disciplines', '', ifaceRows(det.interfaces))}

    <div class="ci-two">
      ${blk('book', 'Work components', '', '', chipList(det.work_components))}
      ${blk('info', 'Context that changes this', 'the planner decides which apply', stChip('planner_review'), bulletList(det.typical_exceptions))}
    </div>

    <div class="ci-two">
      ${blk('info', 'Testing requirements', '', '', bulletList(det.testing_requirements))}
      ${blk('info', 'Commissioning dependencies', '', '', bulletList(det.commissioning_dependencies))}
    </div>

    ${blk('info', 'Evidence, provenance &amp; assumptions', '', '', `
      <div class="ci-prov"><b>Evidence.</b> ${escapeHtml(det.evidence || '—')}<br><br>
      <b>Provenance.</b> ${provChip(det.provenance)} <span class="ci-mut">— patterns are generalized to concepts; no project IDs, activity names or WBS terms are embedded.</span>
      ${(det.zones || []).length ? `<br><br><b>Typical zones.</b> ${escapeHtml((det.zones || []).join(' · '))}` : ''}</div>`)}

    <div class="ci-prov ci-prodptr"><span class="ci-dotprod"></span>Resources, crew, durations &amp; productivity for this work are handled in the <b>separate Productivity Knowledge Base</b> feature — not part of this reference.</div>`;
}

function blk(icon, title, lead, statusChip, inner) {
  return `<div class="ci-blk">
    <div class="ci-blkh">${ic(icon)}<span class="ci-blkt">${title}</span>${lead ? `<span class="ci-blklead">${lead}</span>` : ''}<span class="ci-sp"></span>${statusChip || ''}</div>
    <div class="ci-blkb">${inner}</div></div>`;
}

// ── ACTIVITY INTELLIGENCE (planner-initiated) ────────────────────────────────
function currentActivities() {
  const r = state.currentResult;
  return (r && Array.isArray(r.activities)) ? r.activities : [];
}

function renderActivity(host) {
  const acts = currentActivities();
  if (!acts.length) {
    host.innerHTML = `<div class="ci-disc">${ic('info')}<div><b>Open a schedule to use Activity Intelligence.</b>
      Import a P6 schedule, then come back here — pick any activity and this surfaces the relevant construction knowledge.
      The Knowledge Base tab works without a schedule.</div></div>`;
    return;
  }
  if (_actSel == null || _actSel >= acts.length) _actSel = 0;
  host.innerHTML = `
    <div class="ci-disc">${ic('info')}<div><b>This does not validate your schedule.</b>
      It surfaces reference knowledge for the activity you pick — never a check, a score or a verdict, and
      <b>an empty result never means your logic is correct.</b> See the status key below.</div></div>
    <div class="ci-actgrid">
      <div class="ci-actlist">
        <div class="ci-search ci-actsearch">${ic('search')}<input id="ci-actsearch" type="text" placeholder="Filter activities…" value="${escapeHtml(_actSearch)}"></div>
        <div id="ci-acts">${activityList(acts)}</div>
      </div>
      <div class="ci-actdetail" id="ci-actdetail"><div class="cmp-loading">Select an activity…</div></div>
    </div>
    <div class="ci-legend" id="ci-legend">${statusLegend()}</div>`;
  const s = document.getElementById('ci-actsearch');
  if (s) s.addEventListener('input', () => { _actSearch = s.value; const l = document.getElementById('ci-acts'); if (l) l.innerHTML = activityList(currentActivities()); });
  document.getElementById('ci-acts').addEventListener('click', (e) => {
    const b = e.target.closest('[data-act]'); if (!b) return;
    _actSel = parseInt(b.dataset.act, 10);
    document.querySelectorAll('#ci-acts .ci-act').forEach(x => x.classList.toggle('on', x.dataset.act === b.dataset.act));
    loadActivityKnowledge(acts[_actSel]);
  });
  loadActivityKnowledge(acts[_actSel]);
}

function activityList(acts) {
  const q = _actSearch.trim().toLowerCase();
  const rows = acts
    .map((a, i) => ({ a, i }))
    .filter(({ a }) => !q || (a.name || '').toLowerCase().includes(q) || (a.id || '').toLowerCase().includes(q))
    .slice(0, 400);
  if (!rows.length) return '<div class="ci-empty">No activities match.</div>';
  return rows.map(({ a, i }) => `<button class="ci-act${i === _actSel ? ' on' : ''}" data-act="${i}">
      <span class="ci-actid">${escapeHtml(a.id || '—')}</span>
      <span class="ci-actn">${escapeHtml(a.name || '(unnamed)')}</span></button>`).join('')
    + (acts.length > rows.length && !q ? `<div class="ci-mut ci-actmore">Showing ${rows.length} of ${acts.length} — filter to narrow.</div>` : '');
}

async function loadActivityKnowledge(act) {
  const host = document.getElementById('ci-actdetail');
  if (!host || !act) return;
  const key = (act.id || '') + '¦' + (act.name || '');
  if (_actKnow[key]) { host.innerHTML = activityKnowledgeView(act, _actKnow[key]); return; }
  host.innerHTML = '<div class="cmp-loading">Surfacing construction knowledge…</div>';
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/kb/activity-knowledge`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: act.name || '', wbs_path: act.wbs || '', activity_codes: {} }),
    });
    const d = await resp.json();
    if (!d.ok) { host.innerHTML = `<div class="ci-empty">${escapeHtml(d.error || 'Could not surface knowledge.')}</div>`; return; }
    _actKnow[key] = d;
    host.innerHTML = activityKnowledgeView(act, d);
  } catch { host.innerHTML = '<div class="ci-empty">Could not reach the local server.</div>'; }
}

function confWord(c) { return { high: 'High', medium: 'Medium', low: 'Low', none: 'None' }[c] || c; }

function activityKnowledgeView(act, d) {
  const m = d.match || {}, k = d.knowledge;
  const matched = !!(m.concept && k);
  const head = `<div class="ci-match${matched ? '' : ' nomatch'}">
      <span class="ci-mo">${ic(matched ? 'spark' : 'info', 'lg')}</span>
      <div class="ci-mc"><div class="ci-ml">${matched ? 'Mapped to knowledge concept' : 'Semantic Mapping Layer'}</div>
        <b>${escapeHtml(matched ? (m.concept_name || m.concept) : 'No confident concept match')}</b></div>
      <div class="ci-mr">${matched
        ? `<div class="ci-mut">match confidence · <b>${confWord(m.confidence)}</b>${m.method ? ' · ' + escapeHtml(m.method) : ''}</div>`
        : stChip('not_assessed')}</div>
    </div>
    <div class="ci-mut ci-matchnote">Selected: <b>${escapeHtml(act.id || '')}</b> ${escapeHtml(act.name || '')}
      ${matched ? '· matched via the Semantic Mapping Layer (name + WBS). Corrections will be remembered.' : ''}</div>`;

  if (!matched) {
    return head + `<div class="ci-emptycard">
        <div class="ci-emptyrow">${stChip('insufficient_evidence')} ${stChip('not_assessed')}</div>
        <p><b class="ci-danger">This does not mean the activity is correct.</b> The system has no confident knowledge to show —
        the name is generic, or this work isn't covered yet. You can search the Knowledge Base tab or refine the activity name.</p></div>`;
  }
  // condensed surfaced knowledge from the mapped concept
  const seq = (k.sequence || []).map(s => escapeHtml(prettyStage(s.stage))).slice(0, 6).join(' → ');
  const preds = (k.relationships || []).slice(0, 3).map(r => escapeHtml(r.before)).join(' · ');
  const succs = (k.relationships || []).slice(0, 3).map(r => escapeHtml(r.after)).join(' · ');
  const ctx = (k.typical_exceptions || []).slice(0, 3).map(escapeHtml).join(' · ');
  return head + `
    <div class="ci-blk"><div class="ci-blkh">${ic('spark')}<span class="ci-blkt">Surfaced for this activity</span><span class="ci-sp"></span>${provChip(k.provenance)}${stChip(d.status)}</div>
      <div class="ci-blkb">
        ${seq ? `<div class="ci-kv"><span class="ci-k">Typical sequence</span><span class="ci-v">${seq}</span></div>` : ''}
        ${preds ? `<div class="ci-kv"><span class="ci-k">Typical preceding</span><span class="ci-v">${preds}</span></div>` : ''}
        ${succs ? `<div class="ci-kv"><span class="ci-k">Typical following</span><span class="ci-v">${succs}</span></div>` : ''}
        ${ctx ? `<div class="ci-kv"><span class="ci-k">Context that changes it</span><span class="ci-v">${ctx} <b class="ci-mut">— only you know which apply</b></span></div>` : ''}
        <div class="ci-openkb"><button class="btn-secondary" id="ci-openkb" type="button">${ic('book')} Open full entry in Knowledge Base ›</button></div>
      </div></div>
    <div class="ci-prov ci-prodptr"><span class="ci-dotprod"></span>Resources, crew &amp; productivity are handled in the separate <b>Productivity Knowledge Base</b> feature — not shown here.</div>`;
}

function statusLegend() {
  const defs = {
    knowledge_available: 'Relevant, evidence-graded knowledge exists for this concept.',
    potentially_relevant: 'Partial or lower-confidence match — read with care.',
    insufficient_evidence: 'Concept known, but the knowledge is too thin to rely on.',
    not_assessed: 'No confident match. NOT a statement that the schedule is right.',
    planner_review: 'Context-dependent — only you can decide if it applies.',
  };
  const items = Object.keys(_ST_LABEL).map(k =>
    `<div class="ci-leg"><span class="ci-legd ${_ST_CLS[k]}"></span><div><b>${escapeHtml(_ST_LABEL[k])}</b><span>${escapeHtml(defs[k])}</span></div></div>`).join('');
  return `<div class="ci-legh">${ic('info')} Status key — what each state means, and does not mean</div><div class="ci-legrow">${items}</div>`;
}

// delegated: "Open full entry in Knowledge Base" jumps to the KB tab on that system
document.addEventListener('click', (e) => {
  if (!e.target.closest('#ci-openkb')) return;
  const key = _actSel != null ? currentActivities()[_actSel] : null;
  const k = key && _actKnow[(key.id || '') + '¦' + (key.name || '')];
  const concept = k && k.match && k.match.concept;
  if (!concept) return;
  _sysSel = concept; _view = 'kb';
  renderConstructPanel();
});
