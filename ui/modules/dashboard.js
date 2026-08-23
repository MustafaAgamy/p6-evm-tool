// Professional Dashboard — a user-composed aggregation view.
// It never computes anything: it fetches the catalog of components each feature
// registered, fetches payloads for the ones the user selected, and renders them.
// Layout (selection + order + custom + titles + sizes + header) is saved per project.

import { state } from './state.js';
import { showError, clearError } from './render.js';
import { escapeHtml } from './format.js';
import { showReportPreview } from './preview.js';

// ── local server helper ─────────────────────────────────────────────────────
async function post(path, body) {
  const resp = await fetch(`http://localhost:${state.serverPort}/${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  if (!resp.ok) throw new Error(`Server error ${resp.status}`);
  return resp.json();
}

// ── module state ────────────────────────────────────────────────────────────
const D = {
  catalog: [], projectId: null,
  selected: [],          // ordered component ids on the board
  custom: {},            // {id: {id, source:'Custom', type, title, size, data}}
  titles: {}, sizes: {}, // per-id overrides
  header: { title: '', subtitle: '', logo_left: null, logo_right: null },
  payloads: {},          // {id: {type, data}}
  editing: false, loaded: false,
};

const CUSTOM_KINDS = [
  { kind: 'text',  label: 'Text / Project Brief', type: 'text' },
  { kind: 'chart', label: 'Custom chart',          type: 'chart' },
  { kind: 'kpi',   label: 'Custom KPI',            type: 'kpi' },
  { kind: 'image', label: 'Image / sketch',        type: 'image' },
];

function ctxParams() {
  return {
    snapshot_id: state.currentSnapshotId,
    project_id: D.projectId,
    xml_path: state.currentXmlPath,
    cached_path: state.currentCachedPath,
  };
}

function comp(id) {
  return D.custom[id] || D.catalog.find(c => c.id === id) || null;
}
function titleOf(c) { return D.titles[c.id] != null ? D.titles[c.id] : c.title; }
function sizeOf(c) { return D.sizes[c.id] != null ? D.sizes[c.id] : (c.size || 1); }

// ── entry ────────────────────────────────────────────────────────────────────
export async function renderDashboardPanel() {
  const host = document.getElementById('dashboard-body');
  if (!host) return;
  if (!state.currentResult) {
    host.innerHTML = `<div class="pd-empty-state">Import a P6 schedule first — the dashboard aggregates that project's results.</div>`;
    return;
  }
  host.innerHTML = `<div class="pd-loading">Building your dashboard…</div>`;
  try {
    const cat = await post('api/dashboard/catalog', ctxParams());
    if (!cat.ok) { showError(cat.error || 'Could not load the dashboard.'); host.innerHTML = ''; return; }
    D.catalog = cat.catalog || [];
    D.projectId = cat.project_id || null;
    initComposition(cat.layout);
    await fetchPayloads();
    renderShell(host);
    renderBoard();
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
    host.innerHTML = '';
  }
}

function initComposition(layout) {
  D.custom = {}; D.titles = {}; D.sizes = {};
  if (layout && Array.isArray(layout.components)) {
    D.custom = layout.custom || {};
    D.header = Object.assign(defaultHeader(), layout.header || {});
    D.selected = [];
    for (const c of layout.components) {
      D.selected.push(c.id);
      if (c.title != null) D.titles[c.id] = c.title;
      if (c.size != null) D.sizes[c.id] = c.size;
    }
  } else {
    // Fresh board — sensible defaults: the components each feature marked default_on.
    D.header = defaultHeader();
    D.selected = D.catalog.filter(c => c.default_on).map(c => c.id);
  }
}

function defaultHeader() {
  const r = state.currentResult || {};
  const bits = [];
  if (r.data_date) bits.push(`Data date ${escapeHtml(String(r.data_date).slice(0, 10))}`);
  if (r.activity_count) bits.push(`${r.activity_count} activities`);
  return { title: r.project_name || 'Project Dashboard', subtitle: bits.join('  ·  '),
           logo_left: null, logo_right: null };
}

async function fetchPayloads() {
  const featIds = D.selected.filter(id => !D.custom[id]);
  D.payloads = {};
  if (featIds.length) {
    try {
      const res = await post('api/dashboard/render', Object.assign(ctxParams(), { ids: featIds }));
      if (res.ok) D.payloads = res.payloads || {};
    } catch { /* board still renders with placeholders */ }
  }
  for (const id of Object.keys(D.custom)) {
    D.payloads[id] = { type: D.custom[id].type, data: D.custom[id].data || {} };
  }
}

// ── shell ─────────────────────────────────────────────────────────────────────
function renderShell(host) {
  host.innerHTML = `
    <div class="pd-wrap${D.editing ? ' editing' : ''}" id="pd-wrap">
      <div class="pd-toolbar">
        <span class="pd-mode" id="pd-mode">${D.editing ? 'Edit mode — add, rename, reorder, resize' : 'View mode'}</span>
        <div class="pd-actions">
          <button class="btn-secondary" id="pd-pdf">Export PDF</button>
          <button class="btn-secondary" id="pd-xlsx">Export Excel</button>
          <button class="btn-primary" id="pd-edit">${D.editing ? '✓ Done' : '⚙ Edit Dashboard'}</button>
        </div>
      </div>
      <div class="pd-layout">
        <div class="pd-board">
          <div class="pd-sheet">
            <div class="pd-letterhead" id="pd-letterhead"></div>
            <div class="pd-kpirow" id="pd-kpirow"></div>
            <div class="pd-grid" id="pd-grid"></div>
          </div>
        </div>
        <aside class="pd-catalog" id="pd-catalog"></aside>
      </div>
    </div>`;
  document.getElementById('pd-edit').addEventListener('click', toggleEdit);
  document.getElementById('pd-pdf').addEventListener('click', exportPdf);
  document.getElementById('pd-xlsx').addEventListener('click', exportExcel);
}

function renderLetterhead() {
  const el = document.getElementById('pd-letterhead');
  if (!el) return;
  const logo = (side, src) => src
    ? `<img class="pd-logo" src="${src}" alt="" data-side="${side}">`
    : `<div class="pd-logo-slot" data-side="${side}">${D.editing ? 'Set logo' : ''}</div>`;
  el.innerHTML = `
    ${logo('left', D.header.logo_left)}
    <div class="pd-ttl">
      <div class="pd-h-title" id="pd-h-title" contenteditable="${D.editing}">${escapeHtml(D.header.title || '')}</div>
      <div class="pd-h-sub" id="pd-h-sub" contenteditable="${D.editing}">${escapeHtml(D.header.subtitle || '')}</div>
    </div>
    ${logo('right', D.header.logo_right)}`;
  if (D.editing) {
    document.getElementById('pd-h-title').addEventListener('blur', e => { D.header.title = e.target.textContent.trim(); });
    document.getElementById('pd-h-sub').addEventListener('blur', e => { D.header.subtitle = e.target.textContent.trim(); });
    el.querySelectorAll('.pd-logo-slot, .pd-logo').forEach(n =>
      n.addEventListener('click', () => pickLogo(n.dataset.side)));
  }
}

// ── board ─────────────────────────────────────────────────────────────────────
function renderBoard() {
  renderLetterhead();
  const kpirow = document.getElementById('pd-kpirow');
  const grid = document.getElementById('pd-grid');
  if (!kpirow || !grid) return;
  kpirow.innerHTML = ''; grid.innerHTML = '';
  const chosen = D.selected.map(comp).filter(Boolean);
  const kpis = chosen.filter(c => (c.type === 'kpi'));
  const cards = chosen.filter(c => (c.type !== 'kpi'));

  kpis.forEach(c => {
    const el = document.createElement('div');
    el.className = 'pd-kpi';
    el.innerHTML =
      `<div class="pd-k-head" contenteditable="${D.editing}" data-id="${c.id}">${escapeHtml(titleOf(c))}</div>
       <div class="pd-k-body">${renderPayload(c)}</div>
       <span class="pd-ctl">${ctlBtns(c.id)}</span>`;
    kpirow.appendChild(el);
    wireCard(el, c);
  });
  if (!kpis.length && D.editing) kpirow.innerHTML = '<div class="pd-hint">No KPI tiles yet — add some from the catalog.</div>';

  if (!cards.length && !kpis.length) {
    grid.innerHTML = '<div class="pd-empty">Your board is empty. Open <b>Edit Dashboard</b> and tick components to add them.</div>';
  }
  cards.forEach(c => {
    const el = document.createElement('div');
    el.className = 'pd-panel' + (sizeOf(c) === 2 ? ' span2' : '');
    el.innerHTML =
      `<div class="pd-p-head"><span class="pd-p-title" contenteditable="${D.editing}" data-id="${c.id}">${escapeHtml(titleOf(c))}</span>
        <span class="pd-src">${escapeHtml(c.source || '')}</span><span class="pd-ctl">${ctlBtns(c.id)}</span></div>
       <div class="pd-p-body">${renderPayload(c)}</div>`;
    grid.appendChild(el);
    wireCard(el, c);
  });

  if (D.editing) renderCatalog();
}

function ctlBtns(id) {
  return `<button class="pd-cbtn" data-act="up" data-id="${id}" title="Move up">↑</button>
          <button class="pd-cbtn" data-act="down" data-id="${id}" title="Move down">↓</button>
          <button class="pd-cbtn" data-act="size" data-id="${id}" title="Toggle width">⇔</button>
          <button class="pd-cbtn rm" data-act="rm" data-id="${id}" title="Remove">✕</button>`;
}

function wireCard(el, c) {
  el.querySelectorAll('.pd-ctl .pd-cbtn').forEach(b => b.addEventListener('click', () => {
    const act = b.dataset.act, id = b.dataset.id;
    if (act === 'up') move(id, -1);
    else if (act === 'down') move(id, 1);
    else if (act === 'size') { D.sizes[id] = sizeOf(comp(id)) === 2 ? 1 : 2; renderBoard(); }
    else if (act === 'rm') { D.selected = D.selected.filter(x => x !== id); renderBoard(); }
  }));
  el.querySelectorAll('[contenteditable="true"][data-id]').forEach(t =>
    t.addEventListener('blur', e => {
      const v = e.target.textContent.trim();
      if (v) D.titles[e.target.dataset.id] = v; else delete D.titles[e.target.dataset.id];
    }));
}

function move(id, dir) {
  const i = D.selected.indexOf(id), j = i + dir;
  if (i < 0 || j < 0 || j >= D.selected.length) return;
  [D.selected[i], D.selected[j]] = [D.selected[j], D.selected[i]];
  renderBoard();
}

// ── payload rendering (mirrors p6_dashboard/exporters.py) ───────────────────
function renderPayload(c) {
  const p = D.payloads[c.id] || { type: c.type, data: {} };
  const d = p.data || {};
  switch (p.type) {
    case 'kpi': return kpiHtml(d);
    case 'score': return scoreHtml(d);
    case 'status': return statusHtml(d);
    case 'summary': return summaryHtml(d);
    case 'findings': return findingsHtml(d);
    case 'table': return tableHtml(d);
    case 'chart': case 'trend': return chartHtml(d);
    case 'text': return `<div class="pd-usertext">${escapeHtml(d.text || '')}</div>`;
    case 'image': return d.src ? `<img class="pd-userimg" src="${d.src}" alt="">` : '<div class="pd-na">No image</div>';
    default: return '<div class="pd-na">—</div>';
  }
}
const sc = s => ({ good: 'pd-good', warn: 'pd-warn', bad: 'pd-bad' }[s] || 'pd-neutral');

function kpiHtml(d) {
  const tr = d.trend ? `<span class="pd-trend">${escapeHtml(d.trend)}</span>` : '';
  return `<div class="pd-kv ${sc(d.status)}">${escapeHtml(d.value)}${tr}</div><div class="pd-note">${escapeHtml(d.note || '')}</div>`;
}
function scoreHtml(d) {
  return `<div class="pd-score">${gauge(d.value || 0, sc(d.status))}<div><div class="pd-band">${escapeHtml(d.band || '')}</div><div class="pd-note">${escapeHtml(d.detail || '')}</div></div></div>`;
}
function statusHtml(d) {
  return `<div class="pd-status ${sc(d.status)}">${escapeHtml(d.label || '')}</div><div class="pd-note">${escapeHtml(d.note || '')}</div>`;
}
function summaryHtml(d) {
  return `<div class="pd-stats">${(d.stats || []).map(s =>
    `<div class="pd-stat"><div class="pd-stat-l">${escapeHtml(s.label)}</div><div class="pd-stat-v ${sc(s.status)}">${escapeHtml(s.value)}</div></div>`).join('')}</div>`;
}
function findingsHtml(d) {
  const items = d.items || [];
  if (!items.length) return '<div class="pd-na">No findings</div>';
  return `<div class="pd-finds">${items.map(i =>
    `<div class="pd-find"><span class="pd-dot ${sc(i.severity)}"></span><div><div>${escapeHtml(i.text)}</div><div class="pd-fsrc">${escapeHtml(i.source || '')}</div></div></div>`).join('')}</div>`;
}
function tableHtml(d) {
  const rows = d.rows || [];
  if (!rows.length) return '<div class="pd-na">No rows</div>';
  const th = (d.headers || []).map(h => `<th>${escapeHtml(h)}</th>`).join('');
  const tb = rows.map(r => '<tr>' + r.map(c => `<td>${escapeHtml(c)}</td>`).join('') + '</tr>').join('');
  return `<table class="pd-tbl"><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table>`;
}
function chartHtml(d) {
  if (d.kind === 'bars') return barsHtml(d);
  if (d.kind === 'grouped') return groupedHtml(d);
  if (d.kind === 'line') return lineHtml(d);
  return '<div class="pd-na">—</div>';
}
function barsHtml(d) {
  const rows = d.rows || [];
  const mx = Math.max(...rows.map(r => Math.abs(r.value || 0)), 1);
  return rows.map(r => {
    const pct = Math.min(100, 100 * Math.abs(r.value || 0) / mx);
    const disp = r.display != null ? r.display : r.value;
    return `<div class="pd-bar"><div class="pd-bl">${escapeHtml(r.label)}</div><div class="pd-trk"><div class="pd-fl" style="width:${pct.toFixed(1)}%;background:${r.color || '#3b6fa8'}"></div></div><div class="pd-bv">${escapeHtml(disp)}</div></div>`;
  }).join('');
}
function lineHtml(d) {
  const series = d.series || [];
  const n = Math.max(...series.map(s => (s.points || []).length), 0);
  if (n < 2) return '<div class="pd-na">—</div>';
  const W = 280, H = 118, pad = 22;
  const ymax = d.y_max || Math.max(...series.flatMap(s => s.points || [0]), 1) || 100;
  const x = i => pad + (W - pad - 6) * (i / (n - 1));
  const y = p => H - 18 - (H - 30) * (Math.min(p, ymax) / ymax);
  const axes = `<line x1="${pad}" y1="${H - 18}" x2="${W - 4}" y2="${H - 18}" stroke="var(--border)"></line><line x1="${pad}" y1="6" x2="${pad}" y2="${H - 18}" stroke="var(--border)"></line>`;
  const lines = series.map(s => {
    const pts = (s.points || []).map((p, i) => `${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(' ');
    return `<polyline points="${pts}" fill="none" stroke="${s.color || '#3b6fa8'}" stroke-width="2"${s.dash ? ` stroke-dasharray="${s.dash}"` : ''} stroke-linejoin="round"></polyline>`;
  }).join('');
  const leg = series.map(s => `<span><i style="background:${s.color || '#3b6fa8'}"></i>${escapeHtml(s.name)}</span>`).join('');
  return `<svg width="100%" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">${axes}${lines}</svg><div class="pd-legend">${leg}</div>`;
}
function groupedHtml(d) {
  const labels = d.labels || [], groups = d.groups || [];
  const n = labels.length;
  if (!n || !groups.length) return '<div class="pd-na">—</div>';
  const W = 300, H = 150, padL = 24, padB = 24, padT = 8;
  const mx = Math.max(...groups.flatMap(g => (g.values || []).map(v => Math.abs(v))), 1);
  const bw = (W - padL - 6) / n, gap = bw * 0.15, slot = (bw - gap * 2) / groups.length;
  const yb = v => (H - padB) - (H - padB - padT) * (Math.abs(v) / mx);
  let bars = '';
  for (let i = 0; i < n; i++) {
    const x0 = padL + bw * i + gap;
    groups.forEach((g, gi) => {
      const v = (g.values || [])[i] || 0, x = x0 + slot * gi;
      bars += `<rect x="${x.toFixed(1)}" y="${yb(v).toFixed(1)}" width="${(slot * 0.86).toFixed(1)}" height="${((H - padB) - yb(v)).toFixed(1)}" fill="${g.color || '#3b6fa8'}"></rect>`;
    });
  }
  const labs = labels.map((l, i) => `<text x="${(padL + bw * i + bw / 2).toFixed(1)}" y="${H - 8}" font-size="7" fill="var(--muted)" text-anchor="middle">${escapeHtml(l)}</text>`).join('');
  const axis = `<line x1="${padL}" y1="${H - padB}" x2="${W - 2}" y2="${H - padB}" stroke="var(--border)"></line>`;
  const leg = groups.map(g => `<span><i style="background:${g.color || '#3b6fa8'}"></i>${escapeHtml(g.name)}</span>`).join('');
  return `<svg width="100%" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">${axis}${bars}${labs}</svg><div class="pd-legend">${leg}</div>`;
}
function gauge(score, cls) {
  const R = 30, C = 2 * Math.PI * R, off = C * (1 - (score || 0) / 100);
  return `<svg width="80" height="80" viewBox="0 0 80 80" class="pd-gauge ${cls}"><circle cx="40" cy="40" r="${R}" fill="none" stroke="var(--track)" stroke-width="9"></circle><circle cx="40" cy="40" r="${R}" fill="none" stroke="currentColor" stroke-width="9" stroke-linecap="round" stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}" transform="rotate(-90 40 40)"></circle><text x="40" y="46" text-anchor="middle" font-size="20" font-weight="800" fill="currentColor">${Math.round(score || 0)}</text></svg>`;
}

// ── catalog (edit mode) ─────────────────────────────────────────────────────
function renderCatalog() {
  const el = document.getElementById('pd-catalog');
  if (!el) return;
  const avail = { true: 'Ready', false: 'Run to enable' };
  const groups = {};
  D.catalog.forEach(c => { (groups[c.source] = groups[c.source] || []).push(c); });
  let html = `<div class="pd-cat-h"><div class="pd-cat-t">Component catalog</div><div class="pd-cat-d">Tick to add · grouped by the feature that produces it.</div></div>
    <div class="pd-cat-tools"><button class="pd-lnk" id="pd-selall">Select available</button> · <button class="pd-lnk" id="pd-clrall">Clear all</button></div>
    <div class="pd-cat-body">`;
  // + Add custom
  html += `<div class="pd-grp pd-custom"><div class="pd-grp-h">＋ Add custom content</div>` +
    CUSTOM_KINDS.map(k => `<div class="pd-citem pd-add" data-kind="${k.kind}"><span class="pd-plus">＋</span><span class="pd-ci-t">${k.label}<div class="pd-ty">${k.type}</div></span></div>`).join('') +
    `<div class="pd-note-i">Your own brief, chart, KPI or image — saved with the board.</div></div>`;
  for (const [src, items] of Object.entries(groups)) {
    html += `<div class="pd-grp"><div class="pd-grp-h">${escapeHtml(src)}<span class="pd-badge">${items.length}</span></div>`;
    for (const c of items) {
      const on = D.selected.includes(c.id);
      html += `<label class="pd-citem"><input type="checkbox" data-id="${c.id}" ${on ? 'checked' : ''}>
        <span class="pd-ci-t">${escapeHtml(c.title)}<div class="pd-ty">${c.type}</div></span>
        <span class="pd-avail ${c.available ? 'a-ready' : 'a-run'}">${c.available ? avail.true : avail.false}</span></label>`;
    }
    html += `</div>`;
  }
  html += `</div>`;
  el.innerHTML = html;
  el.querySelectorAll('.pd-citem input[data-id]').forEach(cb =>
    cb.addEventListener('change', () => toggle(cb.dataset.id, cb.checked)));
  el.querySelectorAll('.pd-add').forEach(n =>
    n.addEventListener('click', () => addCustom(n.dataset.kind)));
  document.getElementById('pd-selall').addEventListener('click', () => selectAll(true));
  document.getElementById('pd-clrall').addEventListener('click', () => selectAll(false));
}

async function toggle(id, on) {
  if (on) { if (!D.selected.includes(id)) { D.selected.push(id); await ensurePayload(id); } }
  else D.selected = D.selected.filter(x => x !== id);
  renderBoard();
}
async function ensurePayload(id) {
  if (D.payloads[id] || D.custom[id]) return;
  try {
    const res = await post('api/dashboard/render', Object.assign(ctxParams(), { ids: [id] }));
    if (res.ok && res.payloads[id]) D.payloads[id] = res.payloads[id];
  } catch { /* placeholder shown */ }
}
async function selectAll(on) {
  if (on) {
    D.selected = D.catalog.filter(c => c.available).map(c => c.id);
    await fetchPayloads();
  } else D.selected = [];
  renderBoard();
}

// ── custom content ───────────────────────────────────────────────────────────
let customSeq = 0;
function addCustom(kind) {
  const id = 'custom_' + (Date.now().toString(36)) + '_' + (++customSeq);
  let c;
  if (kind === 'text') c = { id, source: 'Custom', type: 'text', size: 2, title: 'Project Brief', data: { text: 'Double-click to edit this text.' } };
  else if (kind === 'kpi') c = { id, source: 'Custom', type: 'kpi', size: 1, title: 'My KPI', data: { value: '—', note: 'set your own value', status: 'neutral' } };
  else if (kind === 'image') c = { id, source: 'Custom', type: 'image', size: 1, title: 'Image', data: { src: null } };
  else c = { id, source: 'Custom', type: 'chart', size: 1, title: 'My Chart', data: { kind: 'bars', rows: [{ label: 'A', value: 60, color: '#3b6fa8' }, { label: 'B', value: 40, color: '#d0725f' }] } };
  D.custom[id] = c;
  D.payloads[id] = { type: c.type, data: c.data };
  D.selected.push(id);
  renderBoard();
  if (kind === 'image') pickImage(id);
  else if (kind === 'text') editCustomText(id);
}
function editCustomText(id) {
  const cur = D.custom[id]?.data?.text || '';
  const v = window.prompt('Panel text', cur);
  if (v != null) { D.custom[id].data.text = v; D.payloads[id] = { type: 'text', data: D.custom[id].data }; renderBoard(); }
}
function pickImage(id) { pickFileAsDataUrl(url => { D.custom[id].data.src = url; D.payloads[id] = { type: 'image', data: D.custom[id].data }; renderBoard(); }); }
function pickLogo(side) { pickFileAsDataUrl(url => { D.header['logo_' + side] = url; renderLetterhead(); }); }
function pickFileAsDataUrl(cb) {
  const inp = document.createElement('input');
  inp.type = 'file'; inp.accept = 'image/*'; inp.style.display = 'none';
  inp.addEventListener('change', () => {
    const f = inp.files && inp.files[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => cb(rd.result);
    rd.readAsDataURL(f);
  });
  document.body.appendChild(inp); inp.click(); setTimeout(() => inp.remove(), 1000);
}

// ── edit toggle + save ───────────────────────────────────────────────────────
function toggleEdit() {
  if (D.editing) { D.editing = false; saveLayout(); }
  else D.editing = true;
  const host = document.getElementById('dashboard-body');
  renderShell(host);
  renderBoard();
}
function currentLayout() {
  return {
    components: D.selected.map(id => {
      const o = { id };
      if (D.titles[id] != null) o.title = D.titles[id];
      if (D.sizes[id] != null) o.size = D.sizes[id];
      return o;
    }),
    custom: D.custom,
    header: D.header,
  };
}
async function saveLayout() {
  if (!D.projectId) return;
  try { await post('api/dashboard/save', { project_id: D.projectId, layout: currentLayout() }); }
  catch { /* non-fatal */ }
}

// ── composition for export ────────────────────────────────────────────────────
function composition() {
  return {
    header: D.header,
    components: D.selected.map(comp).filter(Boolean).map(c => ({
      id: c.id, type: (D.payloads[c.id]?.type) || c.type, title: titleOf(c),
      source: c.source, size: sizeOf(c), payload: D.payloads[c.id] || { type: c.type, data: {} },
    })),
  };
}
async function exportPdf(e) {
  const btn = e?.currentTarget;
  clearError();
  try {
    const res = await post('api/dashboard/report', { composition: composition(), preview: true });
    if (!res.ok || !res.html) { showError(res.error || 'Preview failed.'); return; }
    showReportPreview({
      title: 'Professional Dashboard — print preview',
      subtitle: D.header.title || '',
      html: res.html,
      onSave: saveDashboardPdf,
    });
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}
async function saveDashboardPdf() {
  const path = await window.pywebview.api.choose_save_path('professional_dashboard.pdf', 'pdf');
  if (!path) return false;
  const res = await post('api/dashboard/report', { composition: composition(), output_path: path });
  if (!res.ok) { showError(res.error || 'PDF generation failed.'); return false; }
  return true;
}
async function exportExcel() {
  clearError();
  const path = await window.pywebview.api.choose_save_path('professional_dashboard.xlsx', 'xlsx');
  if (!path) return;
  try {
    const res = await post('api/dashboard/excel', { composition: composition(), output_path: path });
    if (!res.ok) showError(res.error || 'Excel export failed.');
  } catch { showError('Could not reach the local server. Try restarting the app.'); }
}
