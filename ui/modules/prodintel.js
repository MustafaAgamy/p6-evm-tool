// Productivity & Resource Intelligence — knowledge base of construction productivity norms.
// Approved dashboard layout: cascading Work-item picker + search (no permanent tree),
// polished KPI tiles, smart MH-breakdown / rate-range / crew visuals, separated
// Labour/Equipment/Material, a full "Assign in Primavera P6" guidance section (read-only;
// export deferred), Basis of Estimate, Why, Assumptions/Exclusions, What-If, and a right rail
// (Knowledge reference / Project context / Evidence & confidence). Standalone page.
import { state } from './state.js';
import { escapeHtml } from './format.js';
import { printView } from './printview.js';

let _tree = null, _flat = [];
let _ctx = { 'Project type': 'Industrial', 'Location': 'Egypt', 'Methodology': 'Conventional', 'shift_hours': 8 };
let _quantity = 100;
let _itemId = null, _result = null, _print = null;

const PROJECT_TYPES = ['Industrial', 'Commercial', 'Residential', 'Hospital', 'Infrastructure', 'Oil & Gas', 'Marine/Port', 'Airport', 'Power Plant'];
const LOCATIONS = ['Egypt', 'KSA', 'GCC', 'Europe', 'Other'];
const METHODS = ['Conventional', 'Jump-form', 'Climbing form', 'Precast'];

const api = (path, body) => fetch(`http://localhost:${state.serverPort}${path}`, body
  ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  : undefined).then(r => r.json());
const num = (n) => (n == null ? '—' : Number(n).toLocaleString());
const round1 = (n) => Math.round(n * 10) / 10;

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
  try { const j = await api('/api/prodintel/tree'); _tree = (j && j.ok) ? j.tree : []; } catch (e) { _tree = []; }
  _flat = [];
  for (const d of _tree) for (const s of d.systems) for (const it of s.items)
    _flat.push({ item_id: it.item_id, item: it.item, discipline: d.name, system: s.name });
  if (!_itemId && _flat.length) {
    const rc = _flat.find(x => x.item_id === 'civil.structural.concrete.rc_column');
    _itemId = rc ? rc.item_id : _flat[0].item_id;
  }
  renderShell();
  if (_itemId) selectItem(_itemId);
}

function curItem() { return _flat.find(x => x.item_id === _itemId) || {}; }

function renderShell() {
  const host = document.getElementById('prodintel-section'); if (!host) return;
  host.innerHTML = `
    <div class="pi-wrap">
      <div class="pi-tbar">
        <h1 class="pi-h1">Productivity &amp; Resource Intelligence</h1>
        <div class="pi-searchwrap"><span class="pi-sic">⌕</span><input class="pi-search" id="pi-search" placeholder="Search ${_flat.length} items — columns, ductwork, cable tray, piling…" autocomplete="off">
          <div class="pi-suggest" id="pi-suggest"></div></div>
        <button class="pi-btn" id="pi-browse">▤ Browse library (${_flat.length})</button>
        <div class="pi-expwrap"><button class="pi-btn" id="pi-export">⭳ Export ▾</button>
          <div class="pi-expmenu" id="pi-expmenu">
            <div class="pi-expitem" id="pi-exp-pdf"><span class="di">▤</span><span><b>Export to PDF</b><span>Print preview + section picker</span></span></div>
            <div class="pi-expitem" id="pi-exp-xls"><span class="di">▦</span><span><b>Export to Excel</b><span>One sheet per report section</span></span></div>
          </div></div>
      </div>
      <div class="pi-selrow" id="pi-selrow"></div>
      <div class="pi-grid">
        <div class="pi-col" id="pi-main"></div>
        <div class="pi-rail" id="pi-rail"></div>
      </div>
      <div class="pi-overlay hidden" id="pi-overlay"></div>
    </div>`;
  renderSelRow();
  wireChrome();
}

function renderSelRow() {
  const el = document.getElementById('pi-selrow'); if (!el) return;
  const ci = curItem();
  const discs = _tree.map(d => d.name);
  const systems = (_tree.find(d => d.name === ci.discipline) || { systems: [] }).systems.map(s => s.name);
  const items = ((_tree.find(d => d.name === ci.discipline) || { systems: [] }).systems.find(s => s.name === ci.system) || { items: [] }).items;
  const opt = (arr, v) => arr.map(o => `<option ${o === v ? 'selected' : ''}>${escapeHtml(o)}</option>`).join('');
  el.innerHTML = `
    <div class="pi-selg"><span class="pi-l">Work item</span>
      <div class="pi-cascade">
        <select id="pi-disc">${opt(discs, ci.discipline)}</select><span class="pi-sep">▸</span>
        <select id="pi-sys">${opt(systems, ci.system)}</select><span class="pi-sep">▸</span>
        <select id="pi-item">${items.map(it => `<option value="${escapeHtml(it.item_id)}" ${it.item_id === _itemId ? 'selected' : ''}>${escapeHtml(it.item)}</option>`).join('')}</select>
      </div></div>
    <div class="pi-selg"><span class="pi-l">Project type</span>
      <div class="pi-ptchips">${PROJECT_TYPES.map(p => `<span class="pi-ptchip ${p === _ctx['Project type'] ? 'on' : ''}" data-pt="${escapeHtml(p)}">${escapeHtml(p)}</span>`).join('')}</div></div>
    <div class="pi-selg"><span class="pi-l">Location</span><select id="pi-loc">${opt(LOCATIONS, _ctx['Location'])}</select></div>
    <div class="pi-selg"><span class="pi-l">Methodology</span><select id="pi-meth">${opt(METHODS, _ctx['Methodology'])}</select></div>
    <div class="pi-selg"><span class="pi-l">Quantity ${_result ? '(' + escapeHtml(_result.primary_unit || '') + ')' : ''}</span>
      <input id="pi-qty" type="number" placeholder="optional" value="${_quantity != null ? _quantity : ''}" style="width:96px;text-align:right"></div>`;
  el.querySelector('#pi-disc').onchange = (e) => { const d = _tree.find(x => x.name === e.target.value); const s = d.systems[0]; _itemId = s.items[0].item_id; renderSelRow(); selectItem(_itemId); };
  el.querySelector('#pi-sys').onchange = (e) => { const d = _tree.find(x => x.name === curItem().discipline); const s = d.systems.find(y => y.name === e.target.value); _itemId = s.items[0].item_id; renderSelRow(); selectItem(_itemId); };
  el.querySelector('#pi-item').onchange = (e) => { _itemId = e.target.value; selectItem(_itemId); };
  el.querySelectorAll('.pi-ptchip').forEach(c => c.onclick = () => { _ctx['Project type'] = c.dataset.pt; renderSelRow(); selectItem(_itemId); });
  el.querySelector('#pi-loc').onchange = (e) => { _ctx['Location'] = e.target.value; selectItem(_itemId); };
  el.querySelector('#pi-meth').onchange = (e) => { _ctx['Methodology'] = e.target.value; selectItem(_itemId); };
  el.querySelector('#pi-qty').onchange = (e) => { const v = parseFloat(e.target.value); _quantity = (e.target.value === '' || isNaN(v)) ? null : v; selectItem(_itemId); };
}

function wireChrome() {
  const s = document.getElementById('pi-search'), sug = document.getElementById('pi-suggest');
  if (s) s.oninput = () => {
    const q = s.value.trim().toLowerCase();
    if (!q) { sug.classList.remove('on'); return; }
    const hits = _flat.filter(x => x.item.toLowerCase().includes(q)).slice(0, 10);
    sug.innerHTML = hits.map(h => `<div class="pi-sug" data-id="${escapeHtml(h.item_id)}">${escapeHtml(h.item)}<span>${escapeHtml(h.discipline)} › ${escapeHtml(h.system)}</span></div>`).join('') || '<div class="pi-sug pi-muted">No match</div>';
    sug.classList.add('on');
    sug.querySelectorAll('.pi-sug[data-id]').forEach(d => d.onclick = () => { _itemId = d.dataset.id; s.value = ''; sug.classList.remove('on'); renderSelRow(); selectItem(_itemId); });
  };
  document.getElementById('pi-browse').onclick = openBrowse;
  const expBtn = document.getElementById('pi-export'), expMenu = document.getElementById('pi-expmenu');
  expBtn.onclick = (e) => { e.stopPropagation(); expMenu.classList.toggle('on'); };
  document.addEventListener('click', () => expMenu && expMenu.classList.remove('on'));
  document.getElementById('pi-exp-pdf').onclick = () => { expMenu.classList.remove('on'); exportPDF(); };
  document.getElementById('pi-exp-xls').onclick = () => { expMenu.classList.remove('on'); exportXLS(); };
}

function exportPDF() {
  if (!_print || !_print.length) { alert('Open a work item first, then export.'); return; }
  const sub = _result ? [_result.item, (_result.context || {})['Project type'], (_result.context || {})['Location']].filter(Boolean).join(' · ') : '';
  printView({ module: 'prodintel', title: 'Productivity & Resource Intelligence', subtitle: sub, sections: _print });
}
async function exportXLS() {
  if (!_result || _result.found === false) { alert('Open a work item first, then export.'); return; }
  try {
    const name = (_result.item || 'productivity').replace(/[^a-z0-9]+/gi, '_').toLowerCase() + '.xlsx';
    const outputPath = await window.pywebview.api.choose_save_path(name, 'xlsx');
    if (!outputPath) return;
    const j = await api('/api/prodintel/excel', { item_id: _itemId, context: _ctx, quantity: _quantity, output_path: outputPath });
    if (!j || !j.ok) alert('Excel export failed: ' + ((j && j.error) || 'unknown'));
  } catch (e) { alert('Excel export needs the desktop app (save dialog unavailable in the browser).'); }
}

function openBrowse() {
  const ov = document.getElementById('pi-overlay'); if (!ov) return;
  ov.innerHTML = `<div class="pi-modal"><div class="pi-modal-h"><b>Browse the knowledge library — ${_flat.length} items</b><button class="pi-x" id="pi-ovx">✕</button></div>
    <div class="pi-modal-b">${_tree.map(d => `<div class="pi-bd"><div class="pi-bd-h">${escapeHtml(d.name)} <span>${d.count}</span></div>
      ${d.systems.map(s => `<div class="pi-bs">${escapeHtml(s.name)}</div>${s.items.map(it => `<button class="pi-bi ${it.item_id === _itemId ? 'on' : ''}" data-id="${escapeHtml(it.item_id)}">${escapeHtml(it.item)}</button>`).join('')}`).join('')}
    </div>`).join('')}</div></div>`;
  ov.classList.remove('hidden');
  ov.querySelector('#pi-ovx').onclick = () => ov.classList.add('hidden');
  ov.onclick = (e) => { if (e.target === ov) ov.classList.add('hidden'); };
  ov.querySelectorAll('.pi-bi').forEach(b => b.onclick = () => { _itemId = b.dataset.id; ov.classList.add('hidden'); renderSelRow(); selectItem(_itemId); });
}

async function selectItem(id) {
  _itemId = id;
  const main = document.getElementById('pi-main');
  if (main) main.innerHTML = '<div class="pi-loading">Looking up the knowledge base…</div>';
  try { const j = await api('/api/prodintel/query', { item_id: id, context: _ctx, quantity: _quantity }); _result = (j && j.ok) ? j.result : null; }
  catch (e) { _result = null; }
  renderResult();
}

// ---- helpers for the smart visuals + P6 ----
const CONF = { high: ['pi-good', 'High'], moderate: ['pi-warn', 'Moderate'], draft: ['pi-warn', 'Draft'], none: ['pi-mut', 'Insufficient'] };
const SEG = ['pi-s-ctrl', 'pi-s-a', 'pi-s-b', 'pi-s-c', 'pi-s-d'];
function stateChip(st, conf) {
  if (st === 'no_reference') return `<span class="pi-st pi-mut">○ No reference</span>`;
  if (st === 'validated') return `<span class="pi-st pi-good">● Validated</span>`;
  return `<span class="pi-st pi-warn">◆ ${escapeHtml((CONF[conf] || CONF.draft)[1])}</span>`;
}
function aggregate(r) {
  const labour = {}, equip = {}, material = {};
  const hasQ = r.has_quantity, shift = (r.context && r.context.shift_hours) || 8;
  (r.components || []).forEach(c => {
    if (!c.rate) return;
    const n = c.n_gangs || 1;
    (c.gang || []).forEach(g => {
      const mh = (hasQ && c.man_hours && c.gang_persons) ? c.man_hours * g.count / c.gang_persons : 0;
      const cur = labour[g.trade] || { persons: 0, mh: 0 }; cur.persons += g.count * n; cur.mh += mh; labour[g.trade] = cur;
    });
    (c.equipment || []).forEach(e => { if (!equip[e.name]) equip[e.name] = { name: e.name, hours: (hasQ && c.duration_days) ? Math.round(c.duration_days * shift) : null, shared: /shar/i.test(e.name) }; });
    (c.material || []).forEach(m => { const q = (hasQ && c.component_qty && m.qty_per_unit != null) ? c.component_qty * m.qty_per_unit : null; const cur = material[m.name] || { unit: m.unit, qty: 0, known: false }; if (q != null) { cur.qty += q; cur.known = true; } material[m.name] = cur; });
  });
  return { labour, equip, material, shift };
}

// Express a component's rate as a production norm: per-gang output + per-primary-resource.
function ratePhrase(c) {
  const rate = c.rate; if (!rate) return null;
  const g0 = (c.gang && c.gang[0]) || { count: 1, trade: 'crew' };
  const unitNoun = ((rate.output_unit || c.unit || '').split('/')[0].trim()) || c.unit || '';
  if (rate.output_per_day) {
    const per = Math.round((rate.output_per_day / (g0.count || 1)) * 10) / 10;
    return { gangRate: `${rate.output_per_day} ${rate.output_unit || (unitNoun + '/day')}`,
             big: `${per} ${unitNoun} / ${(g0.trade || 'crew').toLowerCase()}·day`, unitNoun };
  }
  return { gangRate: `${rate.mh_per_unit} MH/${c.unit}`, big: `${rate.mh_per_unit} MH/${c.unit}`, unitNoun };
}

function renderResult() {
  const main = document.getElementById('pi-main'); if (!main) return;
  const r = _result;
  document.getElementById('pi-qty') && renderSelRow();
  if (!r || r.found === false) {
    main.innerHTML = `<div class="pi-card pi-pad"><div class="pi-noref"><div class="pi-noref-i">○</div><h3>No validated reference available</h3><p>The knowledge base has no entry for this selection. It won't invent one — pick another item or import project evidence.</p></div></div>`;
    document.getElementById('pi-rail').innerHTML = ''; _print = null; return;
  }
  const hasQ = r.has_quantity, roll = r.rollup;
  const comps = (r.components || []);
  const priced = comps.filter(c => c.man_hours != null);
  const maxMH = Math.max(1, ...priced.map(c => c.man_hours));

  // component band
  const band = comps.map(c => `<div class="pi-bpill ${c.controls ? 'ctrl' : ''}"><div class="n">${escapeHtml(c.name)}${c.controls ? ' <span class="ct">CONTROLS</span>' : ''}</div><div class="d">${c.rate ? (c.rate.mh_per_unit + ' MH/' + escapeHtml(c.unit) + (hasQ ? ' · ' + num(c.man_hours) + ' MH' : '')) : 'no reference'}</div></div>`).join('');

  // KPIs
  const ctrlComp = comps.find(c => c.controls) || priced[0] || null;
  const ctrlRate = ctrlComp ? ratePhrase(ctrlComp) : null;
  let kpis;
  if (hasQ && roll) {
    kpis = `
      <div class="pi-kpi hero"><span class="ic">◷</span><div class="l">Estimated duration</div><div class="v mono">~${roll.duration_days}</div><div class="u">working days</div><div class="sub">bottleneck · line-of-balance</div></div>
      <div class="pi-kpi pi-ratekpi"><span class="ic">▮</span><div class="l">Productivity rate · controlling</div><div class="v mono" style="font-size:16px">${ctrlRate ? escapeHtml(ctrlRate.big) : '—'}</div><div class="u">${ctrlComp ? escapeHtml(ctrlComp.name) : ''}</div><div class="pi-conv mono">→ converts to ${num(roll.total_mh)} MH total</div></div>
      <div class="pi-kpi"><span class="ic">▤</span><div class="l">Blended rate</div><div class="v mono">${roll.blended_mh_per_primary}</div><div class="u">MH/${escapeHtml(r.primary_unit || '')}</div><div class="sub">across components</div></div>
      <div class="pi-kpi"><span class="ic">◈</span><div class="l">Controlling</div><div class="v" style="font-size:16px;margin-top:8px">${escapeHtml(roll.controlling_component || '—')}</div><div class="sub">sets the duration</div></div>`;
  } else {
    kpis = `
      <div class="pi-kpi hero"><span class="ic">▣</span><div class="l">Work item</div><div class="v" style="font-size:17px;margin-top:8px">${escapeHtml(r.item)}</div><div class="sub">${escapeHtml(r.discipline || '')} · ${escapeHtml(r.system || '')}</div></div>
      <div class="pi-kpi"><span class="ic">▦</span><div class="l">Components</div><div class="v mono">${comps.length}</div><div class="u">each its own norm</div></div>
      <div class="pi-kpi"><span class="ic">✓</span><div class="l">Confidence</div><div class="v" style="font-size:17px;margin-top:8px">${(CONF[r.overall_confidence] || CONF.none)[1]}</div></div>
      <div class="pi-kpi"><span class="ic">＋</span><div class="l">Add a quantity</div><div class="v" style="font-size:17px;margin-top:8px">to estimate</div><div class="sub">man-hours &amp; duration</div></div>`;
  }

  // MH breakdown bar (quantity mode)
  let mh = '';
  if (hasQ && priced.length) {
    const total = roll.total_mh || 1;
    const segs = priced.map((c, i) => `<div class="pi-mhseg ${c.controls ? 'pi-s-ctrl' : SEG[(i % 4) + 1]}" style="width:${c.man_hours / total * 100}%" title="${escapeHtml(c.name)}">${c.man_hours / total > 0.12 ? escapeHtml(c.name.split(' ')[0]) + ' ' + num(c.man_hours) : ''}</div>`).join('');
    const leg = priced.map((c, i) => `<span><span class="pi-d ${c.controls ? 'pi-s-ctrl' : SEG[(i % 4) + 1]}"></span>${escapeHtml(c.name)} ${num(c.man_hours)} MH</span>`).join('');
    mh = `<div class="pi-mhbar">${segs}</div><div class="pi-mhleg">${leg}</div>`;
  }

  // rate-first component cards: productivity rate → convert to man-hours
  const shift = (r.context && r.context.shift_hours) || 8;
  const rows = comps.map(c => {
    if (!c.rate) return `<div class="pi-ccard"><div class="pi-cch"><span class="nm">${escapeHtml(c.name)}</span>${stateChip(c.state, c.confidence)}</div><div class="pi-cbody"><div class="pi-muted">No validated reference — not estimated.</div></div></div>`;
    const rp = ratePhrase(c);
    const gang = (c.gang || []).map(g => `<span class="g">${g.count}× ${escapeHtml(g.trade)}</span>`).join('');
    let range = '';
    if (c.rate.low != null && c.rate.high != null && c.rate.high > c.rate.low) {
      const pin = Math.max(0, Math.min(100, (((c.rate.likely != null ? c.rate.likely : c.rate.mh_per_unit) - c.rate.low) / (c.rate.high - c.rate.low)) * 100));
      range = `<div class="pi-rr" style="max-width:280px"><div class="fill"></div><div class="pin" style="left:${pin}%"></div></div><div class="pi-rrl">range ${c.rate.low}–${c.rate.high} MH/${escapeHtml(c.unit)} · ${c.rate.mh_per_unit} selected</div>`;
    }
    let convert;
    if (hasQ && c.man_hours != null) {
      const gd = c.rate.output_per_day ? Math.round(c.component_qty / c.rate.output_per_day * 10) / 10 : null;
      const chain = gd != null
        ? `<span class="chip">${num(c.component_qty)} ${escapeHtml(c.unit)}</span><span class="op">÷</span><span class="chip">${c.rate.output_per_day} ${escapeHtml(rp.unitNoun)}/day</span><span class="op">=</span><span class="chip">${gd} gang-days</span><span class="op">×</span><span class="chip">${c.gang_persons} × ${shift} h</span><span class="op">=</span><span class="chip res">${num(c.man_hours)} MH</span>`
        : `<span class="chip">${num(c.component_qty)} ${escapeHtml(c.unit)}</span><span class="op">×</span><span class="chip">${c.rate.mh_per_unit} MH/${escapeHtml(c.unit)}</span><span class="op">=</span><span class="chip res">${num(c.man_hours)} MH</span>`;
      const dur = (c.duration_days != null)
        ? `Duration: ${gd != null ? gd + ' gang-days ÷ ' + c.n_gangs + ' gangs = ' : ''}~${c.duration_days} days · equivalent ${c.rate.mh_per_unit} MH/${escapeHtml(c.unit)}`
        : `equivalent ${c.rate.mh_per_unit} MH/${escapeHtml(c.unit)}`;
      convert = `<div class="pi-convert"><div class="cvh">Convert to man-hours</div><div class="pi-chain">${chain}</div><div class="pi-dur">${dur}</div></div>`;
    } else {
      convert = `<div class="pi-addq">Add a quantity above to convert this rate into man-hours and duration.</div>`;
    }
    return `<div class="pi-ccard ${c.controls ? 'ctrl' : ''}">
      <div class="pi-cch"><span class="nm">${escapeHtml(c.name)}${c.controls ? ' <span class="ct">CONTROLS</span>' : ''}</span>${stateChip(c.state, c.confidence)}</div>
      <div class="pi-cbody">
        <div class="pi-rateblock"><span class="lab">Productivity rate</span><span class="big mono">${escapeHtml(rp.gangRate)}</span>${rp.big !== rp.gangRate ? `<span class="per">≈ ${escapeHtml(rp.big)}</span>` : ''}</div>
        <div class="pi-gang">Standard ${(c.gang && c.gang.length > 2) ? 'crew' : 'gang'}: ${gang}${range}</div>
        ${convert}
      </div></div>`;
  }).join('');

  const compCard = `<div class="pi-card pi-pad pi-smart">
    <div class="pi-ch"><h3>Productivity rate → man-hours — by component</h3><span class="m">rate first, then converted</span></div>
    ${mh}
    ${rows}
    <div class="pi-formula">Man-hours = (Quantity ÷ productivity rate) × crew × shift${hasQ && roll ? ` · Total <b>${num(roll.total_mh)} MH</b> → ~${roll.duration_days} days (${escapeHtml(roll.controlling_component || '')} controls)` : ''}${r.basis_incomplete ? ' · <b>basis incomplete</b>' : ''}</div></div>`;

  main.innerHTML = `
    <div class="pi-card pi-pad">
      <div class="pi-ihead"><div><div class="t">${escapeHtml(r.item)}</div><div class="c">${escapeHtml(r.discipline || '')} › ${escapeHtml(r.work_type || '')} › ${escapeHtml(r.system || '')} · ${escapeHtml((r.context || {})['Project type'] || '')} · ${escapeHtml((r.context || {})['Location'] || '')}</div></div>
      <span class="pi-mode">${hasQ ? '◆ Quantity estimate' : '▣ Knowledge lookup'}</span></div>
      <div class="pi-band">${band}</div>
    </div>
    <div class="pi-kpis">${kpis}</div>
    ${compCard}
    ${renderResources(r)}
    ${renderP6(r)}
    ${renderBasis(r)}
    ${renderWhy(r)}
    ${renderWhatIf(r)}`;

  renderRail(r);
  wireWhatIf(r);
  buildPrint(r);
}

function renderResources(r) {
  const { labour, equip, material } = aggregate(r);
  const hasQ = r.has_quantity;
  const li = Object.entries(labour).map(([t, v]) => `<div class="pi-rr2"><span>${escapeHtml(t)}</span><b>${v.persons}${hasQ && v.mh ? ' · ' + num(Math.round(v.mh)) + ' MH' : ''}</b></div>`).join('') || '<div class="pi-muted">—</div>';
  const ei = Object.values(equip).map(e => `<div class="pi-rr2"><span>${escapeHtml(e.name)}</span><b>${e.shared ? 'shared' : (e.hours != null ? e.hours + ' h' : '—')}</b></div>`).join('') || '<div class="pi-muted">—</div>';
  const mi = Object.entries(material).map(([n, v]) => `<div class="pi-rr2"><span>${escapeHtml(n)}</span><b>${v.known ? num(Math.round(v.qty)) + ' ' + escapeHtml((v.unit || '').split('/')[0]) : '—'}</b></div>`).join('') || '<div class="pi-muted">—</div>';
  const peak = {}; Object.entries(labour).forEach(([t, v]) => peak[t] = v.persons);
  const totP = Object.values(peak).reduce((a, b) => a + b, 0) || 1;
  const palette = ['var(--accent)', '#3b82f6', 'var(--mat,#12936a)', 'var(--equip,#7c5cff)', '#8792a5', 'var(--warning)'];
  const crewbar = Object.entries(peak).map(([t, n], i) => `<i style="width:${n / totP * 100}%;background:${palette[i % palette.length]}">${n / totP > 0.08 ? n + ' ' + escapeHtml(t.split(' ')[0]) : ''}</i>`).join('');
  return `<div class="pi-card pi-pad">
    <div class="pi-ch"><h3>Required resources</h3><span class="m">labour · equipment · material — kept separate</span></div>
    <div class="pi-res3">
      <div class="pi-res"><div class="pi-resh lab">Labour <span>persons</span></div>${li}</div>
      <div class="pi-res"><div class="pi-resh eq">Equipment <span>units</span></div>${ei}</div>
      <div class="pi-res"><div class="pi-resh mt">Material <span>quantity</span></div>${mi}</div>
    </div>
    ${hasQ ? `<div class="pi-crewwrap"><div class="pi-l" style="margin-bottom:6px">Peak crew mix</div><div class="pi-crewbar">${crewbar}</div></div>` : ''}</div>`;
}

function renderP6(r) {
  if (!r.has_quantity) return `<div class="pi-card pi-pad pi-smart"><div class="pi-ch"><h3>Assign in Primavera P6</h3></div><div class="pi-muted">Enter a quantity to see the budgeted units and units/time to assign on the P6 activity.</div></div>`;
  const { labour, equip, material, shift } = aggregate(r);
  const roll = r.rollup;
  const rowsL = Object.entries(labour).map(([t, v]) => `<tr><td>${escapeHtml(t)}</td><td><span class="pi-rt lab">Labor</span></td><td class="r">${num(Math.round(v.mh))} MH</td><td class="r">${v.persons * shift} h/d</td></tr>`).join('');
  const rowsE = Object.values(equip).map(e => `<tr><td>${escapeHtml(e.name)}</td><td><span class="pi-rt non">Nonlabor</span></td><td class="r">${e.shared ? 'shared' : (e.hours != null ? e.hours + ' h' : '—')}</td><td class="r">per method</td></tr>`).join('');
  const rowsM = Object.entries(material).filter(([, v]) => v.known).map(([n, v]) => `<tr><td>${escapeHtml(n)}</td><td><span class="pi-rt mat">Material</span></td><td class="r">${num(Math.round(v.qty))} ${escapeHtml((v.unit || '').split('/')[0])}</td><td class="r">—</td></tr>`).join('');
  const totNon = Object.values(equip).reduce((a, e) => a + (e.hours || 0), 0);
  return `<div class="pi-card pi-pad pi-smart">
    <div class="pi-ch"><h3>Assign in Primavera P6</h3><span class="m">how to load these onto the activity</span></div>
    <div class="pi-p6intro">On the P6 activity <b>${escapeHtml(r.item)}</b>, set <b>Duration Type = Fixed Units/Time</b>, then assign each resource below with its <b>Budgeted Units</b> and <b>Units/Time</b>. P6 schedules the activity at ~${roll.duration_days} working days from the crew capacity. <i>Automatic export to a P6 file is a future version — this is planning guidance.</i></div>
    <div class="pi-p6grid">
      <table class="pi-p6t"><thead><tr><th>Resource</th><th>P6 type</th><th class="r">Budgeted units</th><th class="r">Units / time</th></tr></thead><tbody>${rowsL}${rowsE}${rowsM}</tbody></table>
      <div>
        <div class="pi-p6set">
          <div class="st">Activity settings for P6</div>
          <div class="sr"><span>Activity</span><b>${escapeHtml(r.item)}</b></div>
          <div class="sr"><span>Duration type</span><b>Fixed Units/Time</b></div>
          <div class="sr"><span>Original duration</span><b>${Math.ceil(roll.duration_days)} d</b></div>
          <div class="sr"><span>Total budgeted labor</span><b>${num(roll.total_mh)} MH</b></div>
          <div class="sr"><span>Total nonlabor</span><b>${totNon ? totNon + ' h' : '—'}</b></div>
          <div class="sr"><span>Activity calendar</span><b>${escapeHtml((r.context || {})['Location'] || 'project')} · ${shift} h</b></div>
          <div class="sr"><span>Resource curve</span><b>Uniform</b></div>
        </div>
        <div class="pi-p6how"><div class="st">How to assign (5 steps)</div><ol>
          <li>In the Resource dictionary, ensure each resource exists, typed <b>Labor / Nonlabor / Material</b> (map to your IDs).</li>
          <li>On the activity, set <b>Duration Type = Fixed Units/Time</b>.</li>
          <li>Assign each <b>Labor</b> resource with its Budgeted Units (MH) and Units/Time (h/day).</li>
          <li>Assign <b>Nonlabor</b> (equipment) and <b>Material</b> resources with their budgeted units.</li>
          <li>P6 schedules ~${Math.ceil(roll.duration_days)} days — review against your calendar.</li>
        </ol></div>
      </div>
    </div></div>`;
}

function renderBasis(r) {
  const ledger = (r.context_ledger || []).map(f => `<div class="pi-lrow ${f.applied ? '' : 'na'}"><span>${escapeHtml(f.factor)}${f.choice ? ' · ' + escapeHtml(f.choice) : ''}</span><span>${f.applied ? '×' + f.multiplier : 'not adjusted — insufficient evidence'}</span></div>`).join('');
  const pi = `<div class="pi-card pi-pad"><h3 class="pi-h3">Productivity intelligence</h3>
    <div class="pi-dl"><span>Primary unit</span><b>${escapeHtml(r.primary_unit || '')}</b></div>
    <div class="pi-dl"><span>Project context</span><b>${escapeHtml((r.context || {})['Project type'] || '')} · ${escapeHtml((r.context || {})['Location'] || '')}</b></div>
    <div class="pi-dl"><span>Shift basis</span><b>${escapeHtml(String((r.context || {}).shift_hours || 8))} hr/day</b></div>
    <div class="pi-dl"><span>Overall confidence</span><b>${(CONF[r.overall_confidence] || CONF.none)[1]}</b></div>
    <div class="pi-l" style="margin-top:10px">Context adjustment ledger</div><div class="pi-ledger">${ledger}</div></div>`;
  let boe = '';
  if (r.has_quantity && r.rollup) {
    boe = `<div class="pi-card pi-pad"><h3 class="pi-h3">Basis of estimate</h3>
      <div class="pi-dl"><span>Quantity</span><b>${num(r.quantity)} ${escapeHtml(r.primary_unit || '')}</b></div>
      <div class="pi-dl"><span>Blended productivity</span><b>${r.rollup.blended_mh_per_primary} MH/${escapeHtml(r.primary_unit || '')}</b></div>
      <div class="pi-dl"><span>Estimated man-hours</span><b>${num(r.rollup.total_mh)} MH</b></div>
      <div class="pi-dl"><span>Controlling</span><b>${escapeHtml(r.rollup.controlling_component || '—')}</b></div>
      <div class="pi-dl"><span>Estimated duration</span><b>~${r.rollup.duration_days} working days</b></div>
      <div class="pi-calc">${num(r.rollup.total_mh)} MH · bottleneck ${escapeHtml(r.rollup.controlling_component || '')} → ~${r.rollup.duration_days} days (line-of-balance); ${r.rollup.duration_days_sequential} days if sequential.</div></div>`;
  }
  return `<div class="pi-pair">${pi}${boe}</div>`;
}

function renderWhy(r) {
  return `<div class="pi-pair">
    <div class="pi-card pi-pad"><h3 class="pi-h3">Why this recommendation</h3><div class="pi-why">${escapeHtml(r.why || '')}</div></div>
    <div class="pi-card pi-pad"><h3 class="pi-h3">Assumptions &amp; exclusions</h3><div class="pi-ae">
      <div><h5>Assumptions</h5><ul>${(r.assumptions || []).map(a => `<li><span class="pi-ok">✓</span>${escapeHtml(a)}</li>`).join('')}</ul></div>
      <div><h5>Exclusions</h5><ul>${(r.exclusions || []).map(a => `<li><span class="pi-no">✕</span>${escapeHtml(a)}</li>`).join('')}</ul></div></div></div></div>`;
}

function renderWhatIf(r) {
  if (!r.has_quantity) return '';
  return `<div class="pi-card pi-pad"><div class="pi-ch"><h3>What-if planning</h3><span class="m">quantity · crew · shift</span></div>
    <div class="pi-wf">
      <div class="pi-selg"><span class="pi-l">Quantity (${escapeHtml(r.primary_unit || '')})</span><input id="wf-qty" type="number" value="${r.quantity}" style="width:110px"></div>
      <div class="pi-selg"><span class="pi-l">Crew factor ×</span><input id="wf-crew" type="number" step="0.5" value="1" style="width:90px"></div>
      <div class="pi-selg"><span class="pi-l">Shift (hr/day)</span><select id="wf-shift"><option>8</option><option>10</option><option>16</option></select></div>
      <div class="pi-wfout"><div class="pi-l">Scenario</div><div class="v mono" id="wf-days">~${r.rollup.duration_days} d</div><div class="u" id="wf-mh">${num(r.rollup.total_mh)} MH</div></div></div></div>`;
}
function wireWhatIf(r) {
  if (!r.has_quantity || !r.rollup) return;
  const bQ = r.quantity, bMH = r.rollup.total_mh, bD = r.rollup.duration_days;
  const rc = () => {
    const q = parseFloat(document.getElementById('wf-qty').value) || bQ, cr = parseFloat(document.getElementById('wf-crew').value) || 1, sh = parseFloat(document.getElementById('wf-shift').value) || 8;
    document.getElementById('wf-days').textContent = '~' + round1(bD * (q / bQ) / cr * (8 / sh)) + ' d';
    document.getElementById('wf-mh').textContent = Math.round(bMH * (q / bQ)).toLocaleString() + ' MH';
  };
  ['wf-qty', 'wf-crew', 'wf-shift'].forEach(id => document.getElementById(id)?.addEventListener('input', rc));
}

function renderRail(r) {
  const el = document.getElementById('pi-rail'); if (!el) return;
  const ev = r.evidence || {}, conf = CONF[r.overall_confidence] || CONF.none;
  el.innerHTML = `
    <div class="pi-rc"><h4>▣ Knowledge reference</h4><div class="sub">${escapeHtml(r.discipline || '')} › ${escapeHtml(r.system || '')} › <b>${escapeHtml(r.item || '')}</b></div>
      <div class="pi-l">Applies to project types</div><div class="pi-refchips">${(r.project_types || []).slice(0, 8).map(p => `<span class="pi-refchip">${escapeHtml(p)}</span>`).join('')}</div>
      <div class="pi-l">Knowledge coverage</div><div class="pi-cov"><i style="width:64%;background:var(--success)"></i><i style="width:31%;background:var(--warning)"></i><i style="width:5%;background:var(--muted)"></i></div>
      <div style="font-size:11px;color:var(--ink-soft)">${(CONF[r.overall_confidence] || CONF.none)[1]} — built-in norms; validate with your XER</div></div>
    <div class="pi-rc"><h4>◪ Project context</h4>
      <div class="pi-rrow"><span>Project type</span><b>${escapeHtml((r.context || {})['Project type'] || '')}</b></div>
      <div class="pi-rrow"><span>Location</span><b>${escapeHtml((r.context || {})['Location'] || '')}</b></div>
      <div class="pi-rrow"><span>Methodology</span><b>${escapeHtml((r.context || {})['Methodology'] || '')}</b></div>
      <div class="pi-rrow"><span>Shift basis</span><b>${escapeHtml(String((r.context || {}).shift_hours || 8))} hr/day</b></div></div>
    <div class="pi-rc pi-smart"><h4>✓ Evidence &amp; confidence</h4>
      <div class="pi-rrow"><span>Confidence</span><span class="pi-st ${conf[0]}">● ${conf[1]}</span></div>
      <div class="pi-rrow"><span>Source type</span><b>${escapeHtml(ev.source_type || 'Industry reference')}</b></div>
      <div class="pi-rrow"><span>Supporting records</span><b>${num(ev.records || 0)}</b></div>
      <div class="pi-rrow"><span>Reference period</span><b>${escapeHtml(ev.period || 'Built-in')}</b></div>
      <div style="font-size:10.5px;color:var(--muted);margin-top:8px">Built-in standard norms carry no project records until you import validated project evidence — nothing is fabricated.</div></div>`;
}

function buildPrint(r) {
  if (!r || r.found === false) { _print = null; return; }
  const main = document.getElementById('pi-main'); const sec = [];
  sec.push({ key: 'header', label: 'Header', html: `<h1 style="font-size:18px;margin:0 0 4px">${escapeHtml(r.item)}</h1><div style="color:#555;font-size:12px">${escapeHtml(r.discipline || '')} › ${escapeHtml(r.system || '')} · ${escapeHtml((r.context || {})['Project type'] || '')} · ${escapeHtml((r.context || {})['Location'] || '')}${r.has_quantity ? ' · Quantity ' + num(r.quantity) + ' ' + escapeHtml(r.primary_unit || '') : ' · Knowledge lookup'}</div>` });
  (main ? main.querySelectorAll('.pi-card') : []).forEach((card, i) => { const h = card.querySelector('h3,h4'); sec.push({ key: 'card' + i, label: h ? h.textContent : ('Section ' + (i + 1)), html: card.outerHTML }); });
  _print = sec;
}
