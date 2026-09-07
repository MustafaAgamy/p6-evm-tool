// Productivity & Resource Intelligence — a browsable knowledge base of construction
// productivity norms. Pick a work item (and project context); see the rate as a standard
// resource norm per component, the separated labour / equipment / material, and — when a
// quantity is entered — man-hours, crew and an indicative duration, all evidence-graded.
// Standalone page (no imported schedule required), like the Knowledge Base page.
import { state } from './state.js';
import { escapeHtml } from './format.js';

let _tree = null;
let _ctx = { 'Project type': 'Industrial', 'Location': 'Egypt', 'Methodology': 'Conventional', 'shift_hours': 8 };
let _quantity = null;
let _itemId = null;
let _result = null;
let _print = null;               // print-sections provider for File ▸ Print

const PROJECT_TYPES = ['Industrial', 'Commercial', 'Residential', 'Hospital', 'Infrastructure', 'Oil & Gas', 'Marine/Port', 'Airport', 'Power Plant'];
const LOCATIONS = ['Egypt', 'KSA', 'GCC', 'Europe', 'Other'];
const METHODS = ['Conventional', 'Jump-form', 'Climbing form', 'Precast'];

const api = (path, body) => fetch(`http://localhost:${state.serverPort}${path}`, body
  ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  : undefined).then(r => r.json());

export function prodintelPrint() { return _print; }

export function showProdIntel() {
  document.getElementById('prodintel-section')?.classList.remove('hidden');
  document.querySelector('.import-section')?.classList.add('hidden');
  document.getElementById('results-section')?.classList.add('hidden');
  document.getElementById('kb-database-section')?.classList.add('hidden');
  document.querySelector('.recent-section')?.classList.add('hidden');
  if (!_tree) loadTree(); else renderShell();
}

export function exitProdIntel() {
  document.getElementById('prodintel-section')?.classList.add('hidden');
  document.querySelector('.import-section')?.classList.remove('hidden');
}

async function loadTree() {
  const host = document.getElementById('prodintel-section');
  if (host) host.innerHTML = '<div class="pi-loading">Loading the productivity knowledge base…</div>';
  try {
    const j = await api('/api/prodintel/tree');
    _tree = (j && j.ok) ? j.tree : [];
  } catch (e) { _tree = []; }
  // default to the first item so the page never lands empty
  if (!_itemId) {
    outer: for (const d of _tree) for (const s of d.systems) for (const it of s.items) { _itemId = it.item_id; break outer; }
  }
  renderShell();
  if (_itemId) selectItem(_itemId);
}

function renderShell() {
  const host = document.getElementById('prodintel-section');
  if (!host) return;
  host.innerHTML = `
    <div class="pi-wrap">
      <div class="pi-head">
        <div>
          <div class="section-label">Productivity &amp; Resource Intelligence</div>
          <div class="pi-sub">A referenced knowledge base of construction productivity norms — a rate is a crew per unit of work; add a quantity to convert it to man-hours, crew and duration. Every value carries its basis and confidence.</div>
        </div>
      </div>
      <div class="pi-ctxbar" id="pi-ctxbar"></div>
      <div class="pi-body">
        <aside class="pi-tree" id="pi-tree"></aside>
        <main class="pi-main" id="pi-main"></main>
        <aside class="pi-rail" id="pi-rail"></aside>
      </div>
    </div>`;
  renderCtxBar();
  renderTree();
}

function renderCtxBar() {
  const el = document.getElementById('pi-ctxbar'); if (!el) return;
  const sel = (label, opts, val) =>
    `<label class="pi-field"><span>${label}</span><select data-ctx="${label}">${opts.map(o => `<option ${o === val ? 'selected' : ''}>${escapeHtml(o)}</option>`).join('')}</select></label>`;
  el.innerHTML =
    sel('Project type', PROJECT_TYPES, _ctx['Project type']) +
    sel('Location', LOCATIONS, _ctx['Location']) +
    sel('Methodology', METHODS, _ctx['Methodology']) +
    `<label class="pi-field pi-qty"><span>Quantity ${_result ? '(' + escapeHtml(_result.primary_unit || '') + ')' : ''}</span>
       <input type="number" id="pi-qty" placeholder="optional" value="${_quantity != null ? _quantity : ''}"></label>
     <span class="pi-hint">Leave blank for a knowledge lookup · enter a quantity to estimate man-hours &amp; duration</span>`;
  el.querySelectorAll('select[data-ctx]').forEach(s => s.addEventListener('change', () => {
    _ctx[s.dataset.ctx] = s.value; if (_itemId) selectItem(_itemId);
  }));
  const qi = el.querySelector('#pi-qty');
  if (qi) qi.addEventListener('change', () => {
    const v = parseFloat(qi.value); _quantity = (qi.value === '' || isNaN(v)) ? null : v; if (_itemId) selectItem(_itemId);
  });
}

function renderTree() {
  const el = document.getElementById('pi-tree'); if (!el) return;
  if (!_tree || !_tree.length) { el.innerHTML = '<div class="pi-muted">No knowledge base found.</div>'; return; }
  const mixbar = (m) => {
    const t = (m.validated + m.draft + m.none) || 1;
    return `<span class="pi-mini"><i style="width:${m.validated / t * 100}%;background:var(--success)"></i><i style="width:${m.draft / t * 100}%;background:var(--warning)"></i><i style="width:${m.none / t * 100}%;background:var(--muted)"></i></span>`;
  };
  el.innerHTML = `<div class="pi-tree-h">Knowledge base</div>` + _tree.map(d => `
    <div class="pi-disc">
      <div class="pi-disc-h">${escapeHtml(d.name)} <span class="pi-count">${d.count}</span></div>
      ${d.systems.map(s => `
        <div class="pi-sys-h">${escapeHtml(s.name)}</div>
        ${s.items.map(it => `<button class="pi-item ${it.item_id === _itemId ? 'on' : ''}" data-item="${escapeHtml(it.item_id)}">
            <span class="pi-item-n">${escapeHtml(it.item)}</span>${mixbar(it.mix)}</button>`).join('')}
      `).join('')}
    </div>`).join('');
  el.querySelectorAll('.pi-item').forEach(b => b.addEventListener('click', () => selectItem(b.dataset.item)));
}

async function selectItem(itemId) {
  _itemId = itemId;
  const main = document.getElementById('pi-main');
  if (main) main.innerHTML = '<div class="pi-loading">Looking up the knowledge base…</div>';
  document.querySelectorAll('#pi-tree .pi-item').forEach(b => b.classList.toggle('on', b.dataset.item === itemId));
  try {
    const j = await api('/api/prodintel/query', { item_id: itemId, context: _ctx, quantity: _quantity });
    _result = (j && j.ok) ? j.result : null;
  } catch (e) { _result = null; }
  renderResult();
  // keep the quantity-unit label current
  renderCtxBar();
}

// ── render the result dashboard ──────────────────────────────────────────────
const CONF = { high: ['pi-good', 'High'], moderate: ['pi-warn', 'Moderate'], draft: ['pi-warn', 'Draft'], none: ['pi-mut', 'Insufficient'] };
const stateChip = (st, conf) => {
  if (st === 'no_reference') return `<span class="pi-chip pi-mut">○ No reference</span>`;
  if (st === 'validated') return `<span class="pi-chip pi-good">● Validated</span>`;
  return `<span class="pi-chip pi-warn">◆ ${escapeHtml((CONF[conf] || CONF.draft)[1])} · reference</span>`;
};
const num = (n) => (n == null ? '—' : Number(n).toLocaleString());

function renderResult() {
  const main = document.getElementById('pi-main'); if (!main) return;
  const r = _result;
  if (!r || r.found === false) {
    main.innerHTML = `<div class="pi-noref"><div class="pi-noref-i">○</div><h3>No validated reference available</h3>
      <p>The knowledge base has no entry for this selection in this context. It won't invent one — pick another item, or import project evidence to grow the library.</p></div>`;
    _print = null; return;
  }
  const hasQ = r.has_quantity;
  const roll = r.rollup;

  // KPI strip
  let kpis;
  if (hasQ && roll) {
    kpis = [
      ['Total man-hours', num(roll.total_mh), 'MH', roll.total_mh_low != null ? `band ${num(roll.total_mh_low)}–${num(roll.total_mh_high)}` : ''],
      ['Estimated duration', roll.duration_days != null ? '~' + roll.duration_days : '—', 'working days', 'bottleneck / line-of-balance'],
      ['Blended productivity', roll.blended_mh_per_primary != null ? roll.blended_mh_per_primary : '—', 'MH/' + (r.primary_unit || ''), 'across components'],
      ['Controlling', roll.controlling_component || '—', 'sets the duration', ''],
    ];
  } else {
    kpis = [
      ['Work item', r.item, r.discipline + ' · ' + (r.system || ''), ''],
      ['Components', String((r.components || []).length), 'each its own norm', ''],
      ['Overall confidence', (CONF[r.overall_confidence] || CONF.none)[1], '', ''],
      ['Add a quantity', '＋', 'to estimate man-hours', ''],
    ];
  }
  const kpiHtml = `<div class="pi-kpis">${kpis.map(k => `<div class="pi-kpi"><div class="pi-kl">${escapeHtml(k[0])}</div>
      <div class="pi-kv">${escapeHtml(String(k[1]))}</div><div class="pi-ku">${escapeHtml(k[2])}</div>${k[3] ? `<div class="pi-kb">${escapeHtml(k[3])}</div>` : ''}</div>`).join('')}</div>`;

  // Component productivity table (the heart — norm → man-hours)
  const compRows = (r.components || []).map(c => {
    if (c.state === 'no_reference' || !c.rate) {
      return `<tr class="pi-norow"><td><b>${escapeHtml(c.name)}</b><div class="pi-u">${escapeHtml(c.unit || '')}</div></td>
        <td colspan="4" class="pi-muted">No validated reference — not estimated</td><td>${stateChip(c.state, c.confidence)}</td></tr>`;
    }
    const gang = (c.gang || []).map(g => `${g.count}× ${escapeHtml(g.trade)}`).join(' + ');
    const out = c.rate.output_per_day ? ` · ${c.rate.output_per_day} ${escapeHtml(c.rate.output_unit || '')}` : '';
    const adj = c.rate.mh_per_unit_adjusted != null && c.rate.mh_per_unit_adjusted !== c.rate.mh_per_unit;
    const rateCell = `${adj ? `<span class="pi-strike">${c.rate.mh_per_unit}</span> ` : ''}${adj ? c.rate.mh_per_unit_adjusted : c.rate.mh_per_unit} MH/${escapeHtml(c.unit)}`;
    return `<tr class="${c.controls ? 'pi-ctrl' : ''}">
      <td><b>${escapeHtml(c.name)}</b>${c.controls ? ' <span class="pi-ctrltag">CONTROLS</span>' : ''}<div class="pi-u">per ${escapeHtml(c.unit)}</div></td>
      <td class="pi-r">${hasQ ? num(c.component_qty) + ' ' + escapeHtml(c.unit) : '—'}</td>
      <td><div class="pi-norm">gang ${escapeHtml(gang)}${out}</div><div class="pi-u">${escapeHtml((c.provenance || {}).basis || '')}</div></td>
      <td class="pi-r pi-mono">${rateCell}</td>
      <td class="pi-r pi-mono"><b>${hasQ ? num(c.man_hours) + ' MH' : '—'}</b></td>
      <td>${stateChip(c.state, c.confidence)}</td></tr>`;
  }).join('');
  const totRow = (hasQ && roll) ? `<tr class="pi-tot"><td><b>${escapeHtml(r.item)} total</b></td>
      <td class="pi-r">${num(r.quantity)} ${escapeHtml(r.primary_unit || '')}</td>
      <td>blended standard rate</td><td class="pi-r pi-mono">${roll.blended_mh_per_primary} MH/${escapeHtml(r.primary_unit || '')}</td>
      <td class="pi-r pi-mono"><b>${num(roll.total_mh)} MH</b></td><td></td></tr>` : '';
  const compTable = `<div class="pi-card"><div class="pi-card-h">Productivity rate &amp; man-hours — by component</div>
    <div class="pi-card-sub">Standard norm per unit → ${hasQ ? '× quantity = man-hours' : 'add a quantity to convert to man-hours'}</div>
    <table class="pi-table"><thead><tr><th>Work component</th><th class="pi-r">Quantity</th><th>Productivity rate (standard norm)</th><th class="pi-r">Rate</th><th class="pi-r">Man-hours</th><th>Basis</th></tr></thead>
    <tbody>${compRows}${totRow}</tbody></table>
    <div class="pi-formula">Man-hours = Quantity × Productivity rate&nbsp;&nbsp;·&nbsp;&nbsp;Duration = Man-hours ÷ (crew × shift hours)${r.basis_incomplete ? ' &nbsp;·&nbsp; <b>basis incomplete</b> — one or more components have no validated reference' : ''}</div></div>`;

  // Required resources (separated) + P6 planning view
  const resCard = renderResources(r);

  // Productivity intelligence (basis + ledger) + Basis of Estimate
  const piCard = renderBasis(r);

  // Why + assumptions/exclusions
  const whyCard = `<div class="pi-pair">
    <div class="pi-card"><div class="pi-card-h">Why this recommendation</div><div class="pi-why">${escapeHtml(r.why || '')}</div></div>
    <div class="pi-card"><div class="pi-card-h">Assumptions &amp; exclusions</div><div class="pi-ae">
      <div><div class="pi-ae-h">Assumptions</div><ul>${(r.assumptions || []).map(a => `<li><span class="pi-ok">✓</span>${escapeHtml(a)}</li>`).join('')}</ul></div>
      <div><div class="pi-ae-h">Exclusions</div><ul>${(r.exclusions || []).map(a => `<li><span class="pi-no">✕</span>${escapeHtml(a)}</li>`).join('')}</ul></div>
    </div></div></div>`;

  // What-if
  const whatif = renderWhatIf(r);

  main.innerHTML = `
    <div class="pi-item-head">
      <div><div class="pi-item-title">${escapeHtml(r.item)}</div>
      <div class="pi-crumb">${escapeHtml(r.discipline || '')} › ${escapeHtml(r.work_type || '')} › ${escapeHtml(r.system || '')}${hasQ ? '' : ' · <b>Knowledge lookup</b>'}</div></div>
      <span class="pi-mode">${hasQ ? '◆ Quantity estimate' : '▣ Knowledge lookup'}</span>
    </div>
    ${kpiHtml}${compTable}${resCard}${piCard}${whyCard}${whatif}`;

  renderRail(r);
  wireWhatIf(r);
  buildPrint(r);
}

function aggregateResources(r) {
  const labour = {}, equip = {}, material = {};
  const hasQ = r.has_quantity;
  (r.components || []).forEach(c => {
    if (!c.rate) return;
    const n = c.n_gangs || 1;
    (c.gang || []).forEach(g => {
      const key = g.trade;
      const persons = g.count * n;
      const mh = (hasQ && c.man_hours && c.gang_persons) ? c.man_hours * g.count / c.gang_persons : null;
      const cur = labour[key] || { persons: 0, mh: 0 };
      cur.persons += persons; if (mh) cur.mh += mh; labour[key] = cur;
    });
    (c.equipment || []).forEach(e => { equip[e.name] = equip[e.name] || e; });
    (c.material || []).forEach(m => {
      const q = (hasQ && c.component_qty && m.qty_per_unit != null) ? c.component_qty * m.qty_per_unit : null;
      const cur = material[m.name] || { unit: m.unit, qty: 0, known: false };
      if (q != null) { cur.qty += q; cur.known = true; } material[m.name] = cur;
    });
  });
  return { labour, equip, material };
}

function renderResources(r) {
  const { labour, equip, material } = aggregateResources(r);
  const hasQ = r.has_quantity;
  const lab = Object.entries(labour).map(([t, v]) => `<div class="pi-res-row"><span>${escapeHtml(t)}</span><span class="pi-mono">${v.persons}${hasQ && v.mh ? ' · ' + num(Math.round(v.mh)) + ' MH' : ''}</span></div>`).join('') || '<div class="pi-muted">—</div>';
  const eq = Object.values(equip).map(e => `<div class="pi-res-row"><span>${escapeHtml(e.name)}</span><span class="pi-mono">${e.value != null ? e.value + ' ' + escapeHtml(e.unit || '') : '—'}</span></div>`).join('') || '<div class="pi-muted">—</div>';
  const mat = Object.entries(material).map(([n, v]) => `<div class="pi-res-row"><span>${escapeHtml(n)}</span><span class="pi-mono">${v.known ? num(Math.round(v.qty)) + ' ' + escapeHtml((v.unit || '').split('/')[0]) : '—'}</span></div>`).join('') || '<div class="pi-muted">—</div>';

  // P6 planning view (read-only) — how these resources would be assigned in P6
  let p6 = '';
  if (hasQ) {
    const shift = (r.context && r.context.shift_hours) || 8;
    const rowsL = Object.entries(labour).map(([t, v]) => `<tr><td>${escapeHtml(t)}</td><td><span class="pi-rt pi-rt-lab">Labor</span></td><td class="pi-r pi-mono">${v.mh ? num(Math.round(v.mh)) + ' MH' : '—'}</td><td class="pi-r pi-mono">${v.persons * shift} h/d</td></tr>`).join('');
    const rowsE = Object.values(equip).map(e => `<tr><td>${escapeHtml(e.name)}</td><td><span class="pi-rt pi-rt-non">Nonlabor</span></td><td class="pi-r pi-mono">${e.value != null ? e.value + ' ' + escapeHtml(e.unit || '') : '—'}</td><td class="pi-r">per method</td></tr>`).join('');
    const rowsM = Object.entries(material).filter(([, v]) => v.known).map(([n, v]) => `<tr><td>${escapeHtml(n)}</td><td><span class="pi-rt pi-rt-mat">Material</span></td><td class="pi-r pi-mono">${num(Math.round(v.qty))} ${escapeHtml((v.unit || '').split('/')[0])}</td><td class="pi-r">—</td></tr>`).join('');
    p6 = `<div class="pi-p6"><div class="pi-card-sub">P6 planning view — budgeted units &amp; units/time, ready to assign on the activity (Duration Type: Fixed Units/Time). <span class="pi-muted">Export to P6 arrives in a future version.</span></div>
      <table class="pi-table pi-p6t"><thead><tr><th>Resource</th><th>P6 type</th><th class="pi-r">Budgeted units</th><th class="pi-r">Units/time</th></tr></thead>
      <tbody>${rowsL}${rowsE}${rowsM}</tbody></table></div>`;
  }
  return `<div class="pi-card"><div class="pi-card-h">Required resources</div>
    <div class="pi-res3">
      <div class="pi-res"><div class="pi-res-h pi-lab">Labour <span>persons</span></div>${lab}</div>
      <div class="pi-res"><div class="pi-res-h pi-eq">Equipment <span>units</span></div>${eq}</div>
      <div class="pi-res"><div class="pi-res-h pi-mt">Material / supporting <span>quantity</span></div>${mat}</div>
    </div>
    <div class="pi-note">Labour in persons · equipment in units · material in quantity — never merged into one resource figure.</div>
    ${p6}</div>`;
}

function renderBasis(r) {
  const ledger = (r.context_ledger || []).map(f => `<div class="pi-lrow ${f.applied ? '' : 'pi-na'}"><span>${escapeHtml(f.factor)}${f.choice ? ' · ' + escapeHtml(f.choice) : ''}</span><span>${f.applied ? '×' + f.multiplier : 'not adjusted — insufficient evidence'}</span></div>`).join('');
  const pi = `<div class="pi-card"><div class="pi-card-h">Productivity intelligence</div>
    <div class="pi-deflist">
      <div class="pi-dl"><span>Primary unit</span><b>${escapeHtml(r.primary_unit || '')}</b></div>
      <div class="pi-dl"><span>Project context</span><b>${escapeHtml((r.context || {})['Project type'] || '')} · ${escapeHtml((r.context || {})['Location'] || '')}</b></div>
      <div class="pi-dl"><span>Shift basis</span><b>${escapeHtml(String((r.context || {}).shift_hours || 8))} hr/day</b></div>
      <div class="pi-dl"><span>Overall confidence</span><b>${escapeHtml((CONF[r.overall_confidence] || CONF.none)[1])}</b></div>
    </div>
    <div class="pi-ledger-h">Context adjustment ledger</div>
    <div class="pi-ledger">${ledger}</div></div>`;
  let boe = '';
  if (r.has_quantity && r.rollup) {
    const shift = (r.context && r.context.shift_hours) || 8;
    boe = `<div class="pi-card"><div class="pi-card-h">Basis of estimate</div>
      <div class="pi-deflist">
        <div class="pi-dl"><span>Quantity</span><b>${num(r.quantity)} ${escapeHtml(r.primary_unit || '')}</b></div>
        <div class="pi-dl"><span>Blended productivity</span><b>${r.rollup.blended_mh_per_primary} MH/${escapeHtml(r.primary_unit || '')}</b></div>
        <div class="pi-dl"><span>Estimated man-hours</span><b>${num(r.rollup.total_mh)} MH</b></div>
        <div class="pi-dl"><span>Controlling component</span><b>${escapeHtml(r.rollup.controlling_component || '—')}</b></div>
        <div class="pi-dl"><span>Estimated duration</span><b>~${r.rollup.duration_days} working days</b></div>
      </div>
      <div class="pi-calc">Total ${num(r.rollup.total_mh)} MH · bottleneck ${escapeHtml(r.rollup.controlling_component || '')} · shift ${escapeHtml(String(shift))} hr/day → ~${r.rollup.duration_days} days (line-of-balance); ${r.rollup.duration_days_sequential} days if fully sequential.</div></div>`;
  }
  return `<div class="pi-pair">${pi}${boe}</div>`;
}

function renderWhatIf(r) {
  if (!r.has_quantity) return `<div class="pi-card pi-whatif-empty">Enter a quantity above to open What-If planning (crew · shift · productivity scenarios).</div>`;
  return `<div class="pi-card"><div class="pi-card-h">What-if planning</div>
    <div class="pi-wf">
      <label class="pi-field"><span>Quantity (${escapeHtml(r.primary_unit || '')})</span><input type="number" id="wf-qty" value="${r.quantity}"></label>
      <label class="pi-field"><span>Crew factor ×</span><input type="number" step="0.5" id="wf-crew" value="1"></label>
      <label class="pi-field"><span>Shift (hr/day)</span><select id="wf-shift"><option>8</option><option>10</option><option>16</option></select></label>
      <div class="pi-wf-out"><div class="pi-kl">Scenario duration</div><div class="pi-kv" id="wf-days">~${r.rollup.duration_days}</div><div class="pi-ku" id="wf-mh">${num(r.rollup.total_mh)} MH</div></div>
    </div>
    <div class="pi-note" id="wf-note">Adjust quantity, crew or shift to see the effect on duration. Man-hours scale with quantity; duration scales with crew and shift.</div></div>`;
}

function wireWhatIf(r) {
  if (!r.has_quantity || !r.rollup) return;
  const baseQty = r.quantity, baseMH = r.rollup.total_mh, baseDur = r.rollup.duration_days;
  const recompute = () => {
    const q = parseFloat(document.getElementById('wf-qty').value) || baseQty;
    const crew = parseFloat(document.getElementById('wf-crew').value) || 1;
    const shift = parseFloat(document.getElementById('wf-shift').value) || 8;
    const mh = baseMH * (q / baseQty);
    const dur = baseDur * (q / baseQty) / crew * (8 / shift);
    document.getElementById('wf-days').textContent = '~' + (Math.round(dur * 10) / 10);
    document.getElementById('wf-mh').textContent = Math.round(mh).toLocaleString() + ' MH';
  };
  ['wf-qty', 'wf-crew', 'wf-shift'].forEach(id => document.getElementById(id)?.addEventListener('input', recompute));
}

function renderRail(r) {
  const el = document.getElementById('pi-rail'); if (!el) return;
  const ev = r.evidence || {};
  const conf = CONF[r.overall_confidence] || CONF.none;
  el.innerHTML = `
    <div class="pi-railcard"><div class="pi-rc-h">Knowledge reference</div>
      <div class="pi-rc-sub">${escapeHtml(r.discipline || '')} › ${escapeHtml(r.system || '')} › <b>${escapeHtml(r.item || '')}</b></div>
      <div class="pi-rc-lbl">Applies to project types</div>
      <div class="pi-refchips">${(r.project_types || []).slice(0, 8).map(p => `<span class="pi-refchip">${escapeHtml(p)}</span>`).join('')}</div>
    </div>
    <div class="pi-railcard"><div class="pi-rc-h">Project context</div>
      <div class="pi-rc-row"><span>Project type</span><b>${escapeHtml((r.context || {})['Project type'] || '')}</b></div>
      <div class="pi-rc-row"><span>Location</span><b>${escapeHtml((r.context || {})['Location'] || '')}</b></div>
      <div class="pi-rc-row"><span>Methodology</span><b>${escapeHtml((r.context || {})['Methodology'] || '')}</b></div>
      <div class="pi-rc-row"><span>Shift basis</span><b>${escapeHtml(String((r.context || {}).shift_hours || 8))} hr/day</b></div>
    </div>
    <div class="pi-railcard"><div class="pi-rc-h">Evidence &amp; confidence</div>
      <div class="pi-rc-row"><span>Confidence</span><span class="pi-chip ${conf[0]}">● ${escapeHtml(conf[1])}</span></div>
      <div class="pi-rc-row"><span>Source type</span><b>${escapeHtml(ev.source_type || 'Industry reference')}</b></div>
      <div class="pi-rc-row"><span>Supporting records</span><b>${num(ev.records || 0)}</b></div>
      <div class="pi-rc-row"><span>Reference period</span><b>${escapeHtml(ev.period || 'Built-in')}</b></div>
      <div class="pi-rc-note">Built-in standard norms carry no project records until you import validated project evidence — nothing is fabricated.</div>
    </div>`;
}

// ── print provider (File ▸ Print / Export to PDF) ────────────────────────────
function buildPrint(r) {
  if (!r || r.found === false) { _print = null; return; }
  const sec = [];
  const main = document.getElementById('pi-main');
  const head = `<h1 style="font-size:18px;margin:0 0 4px">${escapeHtml(r.item)}</h1><div style="color:#555;font-size:12px">${escapeHtml(r.discipline || '')} › ${escapeHtml(r.system || '')} · ${escapeHtml((r.context || {})['Project type'] || '')} · ${escapeHtml((r.context || {})['Location'] || '')}${r.has_quantity ? ' · Quantity ' + num(r.quantity) + ' ' + escapeHtml(r.primary_unit || '') : ' · Knowledge lookup'}</div>`;
  sec.push({ key: 'header', label: 'Header', html: head });
  (main ? main.querySelectorAll('.pi-card') : []).forEach((card, i) => {
    const h = card.querySelector('.pi-card-h');
    sec.push({ key: 'card' + i, label: h ? h.textContent : ('Section ' + (i + 1)), html: card.outerHTML });
  });
  _print = sec;
}
