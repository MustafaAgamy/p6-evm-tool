// Duration & Resources — Standalone Activity Calculator (offline, draft KB).
// Quantity -> Driver -> Productivity Rate -> Duration -> Man-hours -> MNP -> typed resources.
// Two distinct statuses: "Knowledge Not Available" (KB gap) vs "Needs Planner Input" (missing qty).

const PT_SUGGEST = ['Residential/Villa', 'Industrial', 'Oil & Gas', 'Commercial', 'Infrastructure'];

function api(path, body) {
  return fetch(`http://localhost:${window.__SERVER_PORT__}/${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }).then(r => r.json());
}

function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

function driverLabel(d) {
  return ({ production_rate: 'Production-rate', manpower_driven: 'Manpower', resource_driven: 'Equipment',
    lead_time: 'Lead-time', typical: 'Typical duration' }[d]) || d || '—';
}

function injectStyles() {
  if (document.getElementById('pk-styles')) return;
  const s = document.createElement('style');
  s.id = 'pk-styles';
  s.textContent = `
    #prodkb-section{padding:8px 4px 40px}
    .pk-banner{font-size:12.5px;background:var(--bg-accent,#fff7e6);border:1px solid #f2d8b6;color:#8a5a00;border-radius:8px;padding:9px 13px;margin-bottom:14px}
    .pk-form{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;background:var(--surface-1,#fff);border:1px solid var(--border,#e3e7ec);border-radius:12px;padding:14px 16px;margin-bottom:14px}
    .pk-form label{display:block;font-size:11px;color:var(--text-secondary,#667080);margin-bottom:3px}
    .pk-form input{width:100%;padding:6px 8px;border:1px solid var(--border,#cdd4dc);border-radius:6px;font-size:12.5px;background:var(--surface-2,#fff);color:inherit}
    .pk-actions{grid-column:1/-1;display:flex;gap:10px;align-items:center;margin-top:2px}
    .pk-btn{background:var(--text-accent,#1f6feb);color:#fff;border:none;font-weight:600;font-size:12.5px;padding:8px 16px;border-radius:8px;cursor:pointer}
    .pk-btn.ghost{background:transparent;color:var(--text-secondary,#667080);border:1px solid var(--border,#cdd4dc)}
    .pk-scroll{overflow-x:auto}
    .pk-table{border-collapse:collapse;font-size:11.5px;min-width:1120px;width:100%}
    .pk-table th{text-align:left;color:var(--text-secondary,#667080);font-weight:500;padding:7px 6px;border-bottom:1px solid var(--border-strong,#cdd4dc);white-space:nowrap}
    .pk-table td{padding:8px 6px;border-bottom:1px solid var(--border,#eef);vertical-align:top}
    .pk-pill{font-size:9.5px;padding:1px 7px;border-radius:11px;border:1px solid var(--border,#cdd4dc);color:var(--text-secondary,#667080);white-space:nowrap}
    .pk-st-ok{background:#eef7f0;border-color:#c7e6d1;color:#1a7f4b}
    .pk-st-need{background:#fdf0e2;border-color:#f2d8b6;color:#b25b00}
    .pk-st-gap{background:#fdecec;border-color:#f2c0c0;color:#b23838}
    .pk-na{color:#8a93a0;font-weight:600}
    .pk-detail{background:var(--surface-2,#fafbfc);border:1px dashed var(--border-strong,#cdd4dc);border-radius:6px;padding:7px 10px;margin-top:5px;font-size:10.5px;color:var(--text-secondary,#667080)}
    .pk-back{background:none;border:none;color:var(--text-accent,#1f6feb);cursor:pointer;font-size:12.5px;margin-bottom:8px}
  `;
  document.head.appendChild(s);
}

const HEAD = ['Activity ID', 'Activity Name', 'Type of Work', 'Project Type', 'Method', 'Quantity',
  'Unit', 'Productivity Rate', 'Duration', 'Man-hours', 'MNP', 'Resources', 'Confidence', 'Status'];

function resourcesCell(res) {
  const eq = (res.equipment || []).map(e => `${esc(e.name)}${e.quantity ? ' ×' + e.quantity : ''}`);
  const mat = (res.material || []).map(m => `${esc(m.name)} ${m.quantity} ${esc(m.unit || '')}`.trim());
  const parts = [];
  if (eq.length) parts.push('<b>Equip:</b> ' + eq.join(', '));
  if (mat.length) parts.push('<b>Mat:</b> ' + mat.join(', '));
  return parts.join('<br>') || '<span class="pk-na">—</span>';
}

function rowHtml(row) {
  const inp = row.input || {};
  const res = row.result;
  const status = row.status || (res ? 'ok' : 'knowledge_not_available');
  const cell = (v) => `<td>${v == null || v === '' ? '<span class="pk-na">—</span>' : v}</td>`;

  let stClass = 'pk-st-ok', stText = 'Calculated';
  if (status === 'needs_input') { stClass = 'pk-st-need'; stText = 'Needs Planner Input'; }
  if (status === 'knowledge_not_available') { stClass = 'pk-st-gap'; stText = 'Knowledge Not Available'; }

  let rate = '—', dur = '—', mh = '—', mnp = '—', resc = '—', conf = '—',
    work = esc(inp.work_type), meth = esc(inp.method), detail = '';

  if (res) {
    const r = res.rate || {};
    rate = r.value != null ? `${r.value} <span class="pk-na">${esc(r.unit || '')}</span>` : '—';
    dur = res.duration_days != null ? res.duration_days + ' wd' : '—';
    mh = res.labor && res.labor.man_hours != null ? res.labor.man_hours + ' MH' : '—';
    mnp = res.labor && res.labor.mnp != null ? res.labor.mnp : '<span class="pk-na">N/A</span>';
    resc = resourcesCell(res);
    conf = r.confidence ? esc(r.confidence) : '—';
    work = esc(res.work_type || inp.work_type);
    meth = esc(res.method || inp.method);
    detail = `<div class="pk-detail">Driver: <b>${driverLabel(res.driver)}</b> · Source: ${esc(r.source || '')}`
      + ` · Basis: ${esc(r.basis || '')} · Conditions: ${esc(r.conditions || '')}`
      + ` · ${r.draft ? 'Draft starter rate' : 'Validated'}`
      + (res.match_confidence != null ? ` · match ${res.match_confidence}` : '') + `</div>`;
  } else if (row.status_detail) {
    const d = row.status_detail;
    detail = `<div class="pk-detail">${esc(d.reason || '')}`
      + (d.project_type ? ` · Project Type: ${esc(d.project_type)}` : '')
      + (d.work_type ? ` · Work Type: ${esc(d.work_type)}` : '')
      + (d.method ? ` · Method: ${esc(d.method)}` : '')
      + ` · Missing: ${esc(d.missing || '')} · Action: ${esc(d.action || '')}</div>`;
  }

  return `<tr>
    ${cell(esc(inp.activity_id))}${cell(esc(inp.name) + detail)}${cell(work)}${cell(esc(inp.project_type))}
    ${cell(meth)}${cell(inp.quantity != null && inp.quantity !== '' ? esc(inp.quantity) : '')}${cell(esc(inp.unit))}
    ${cell(rate)}${cell(dur)}${cell(mh)}${cell(mnp)}${cell(resc)}${cell(conf)}
    <td><span class="pk-pill ${stClass}">${stText}</span></td>
  </tr>`;
}

export function initProdkb() {
  const sec = document.getElementById('prodkb-section');
  if (!sec || sec.dataset.ready) return;
  sec.dataset.ready = '1';
  injectStyles();

  sec.innerHTML = `
    <button class="pk-back" id="pk-back">← Back to import</button>
    <div class="section-label">Duration &amp; Resources — Activity Calculator</div>
    <div class="pk-banner">⚠ Draft starter rates — an engine proof, not validated industry benchmarks. Every rate shows its source, basis, conditions and confidence.</div>
    <div class="pk-form">
      <div><label>Activity ID</label><input id="pk-id" placeholder="optional"></div>
      <div><label>Activity Name</label><input id="pk-name" placeholder="e.g. RC Columns L3"></div>
      <div><label>Project Type</label><input id="pk-ptype" list="pk-ptypes" placeholder="e.g. Industrial"></div>
      <div><label>Type of Work / Discipline</label><input id="pk-work" list="pk-works" placeholder="optional"></div>
      <div><label>Construction Method</label><input id="pk-method" placeholder="optional"></div>
      <div><label>Quantity (BOQ)</label><input id="pk-qty" type="number" step="any" placeholder="e.g. 220"></div>
      <div><label>Unit</label><input id="pk-unit" placeholder="e.g. m3"></div>
      <div><label>Conditions</label><input id="pk-cond" placeholder="optional"></div>
      <div><label>Calendar hours/day</label><input id="pk-hpd" type="number" step="any" placeholder="8"></div>
      <datalist id="pk-ptypes"></datalist><datalist id="pk-works"></datalist>
      <div class="pk-actions">
        <button class="pk-btn" id="pk-calc">Calculate</button>
        <button class="pk-btn ghost" id="pk-clear">Clear table</button>
        <span style="font-size:11px;color:var(--text-secondary,#667080)">Excel batch upload &amp; template, and rate export — next increment.</span>
      </div>
    </div>
    <div class="pk-scroll"><table class="pk-table">
      <thead><tr>${HEAD.map(h => `<th>${h}</th>`).join('')}</tr></thead>
      <tbody id="pk-rows"></tbody>
    </table></div>`;

  document.getElementById('pk-back').addEventListener('click', hideProdkb);
  document.getElementById('pk-clear').addEventListener('click', () => { document.getElementById('pk-rows').innerHTML = ''; });
  document.getElementById('pk-calc').addEventListener('click', calc);

  PT_SUGGEST.forEach(p => document.getElementById('pk-ptypes').insertAdjacentHTML('beforeend', `<option value="${esc(p)}">`));
  api('api/prodkb/templates', {}).then(d => {
    if (!d || !d.ok) return;
    const works = [...new Set((d.templates || []).map(t => t.work_type).filter(Boolean))];
    const dl = document.getElementById('pk-works');
    works.forEach(w => dl.insertAdjacentHTML('beforeend', `<option value="${esc(w)}">`));
  }).catch(() => {});
}

function calc() {
  const val = id => document.getElementById(id).value.trim();
  const name = val('pk-name');
  if (!name) { document.getElementById('pk-name').focus(); return; }
  const qtyRaw = val('pk-qty');
  const hpdRaw = val('pk-hpd');
  const input = {
    activity_id: val('pk-id'), name, work_type: val('pk-work') || null,
    project_type: val('pk-ptype') || null, method: val('pk-method') || null,
    unit: val('pk-unit') || null,
    quantity: qtyRaw === '' ? null : Number(qtyRaw),
    calendar_hours: hpdRaw === '' ? null : Number(hpdRaw),
  };
  const btn = document.getElementById('pk-calc');
  btn.disabled = true; btn.textContent = '…';
  api('api/prodkb/calc', { project_type: input.project_type, activities: [input] })
    .then(d => {
      const row = (d && d.ok && d.rows && d.rows[0]) || { input, result: null, status: 'knowledge_not_available' };
      row.input = Object.assign({}, input, row.input);
      document.getElementById('pk-rows').insertAdjacentHTML('afterbegin', rowHtml(row));
    })
    .catch(() => {
      document.getElementById('pk-rows').insertAdjacentHTML('afterbegin',
        rowHtml({ input, result: null, status: 'knowledge_not_available',
          status_detail: { reason: 'Calculation service unavailable.', missing: '', action: 'Restart the app.' } }));
    })
    .finally(() => { btn.disabled = false; btn.textContent = 'Calculate'; });
}

export function showProdkb() {
  initProdkb();
  document.querySelectorAll('.import-section, #results-section').forEach(el => el && el.classList.add('hidden'));
  const sec = document.getElementById('prodkb-section');
  if (sec) sec.classList.remove('hidden');
  document.querySelectorAll('.sb-item').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('sb-prodkb-btn');
  if (btn) btn.classList.add('active');
  const sub = document.getElementById('topbar-sub');
  if (sub) sub.textContent = 'Duration & Resources';
}

export function hideProdkb() {
  const sec = document.getElementById('prodkb-section');
  if (sec) sec.classList.add('hidden');
  const imp = document.querySelector('.import-section');
  if (imp) imp.classList.remove('hidden');
  document.querySelectorAll('.sb-item').forEach(b => b.classList.remove('active'));
  const home = document.getElementById('sb-home-btn');
  if (home) home.classList.add('active');
  const sub = document.getElementById('topbar-sub');
  if (sub) sub.textContent = 'Home · Import';
}
