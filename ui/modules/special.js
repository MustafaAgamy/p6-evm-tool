// Special Report — build a report from detailed results across any feature.
// The user picks results (granular), orders them, names the report, and exports
// to Word or PDF (identical style). Results that need an extra file highlight it
// and let the user attach it; Special Report then runs that feature itself.
import { state } from './state.js';
import { getSavedMode, buildAppearancePicker } from './appearance.js';
import { showReportPreview } from './preview.js';
import { showError } from './render.js';

const S = {
  catalog: [],          // [{feature, feature_title, items:[{id,title,ctype,availability,requires}]}]
  selected: [],         // ordered list of item ids
  name: '',
  inputs: {},           // {role: path}
  templateId: null,
};

function api(path, body) {
  return fetch(`http://localhost:${state.serverPort}/${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  }).then(r => r.json());
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function reqBody(extra) {
  return Object.assign({
    snapshot_id: state.currentSnapshotId,
    item_ids: S.selected,
    report_name: S.name,
    theme: getSavedMode(),
    inputs: S.inputs,
    meta: {},
  }, extra || {});
}

export async function renderSpecialPanel() {
  const host = document.getElementById('special-body');
  if (!state.currentSnapshotId) {
    host.innerHTML = `<div class="sr-empty">Import a schedule first, then build a Special Report from its results.</div>`;
    return;
  }
  if (!S.name) S.name = `Special Report — ${(state.currentResult && state.currentResult.project_name) || 'Project'}`;
  host.innerHTML = `<div class="sr-loading">Loading available results…</div>`;
  const [cat, tpl] = await Promise.all([
    api('api/special/catalog', { snapshot_id: state.currentSnapshotId, inputs: S.inputs }),
    api('api/special/templates/list', { snapshot_id: state.currentSnapshotId }),
  ]);
  if (!cat.ok) { host.innerHTML = `<div class="sr-empty">${esc(cat.error || 'Could not load results.')}</div>`; return; }
  S.catalog = cat.groups || [];
  drawBuilder(host, (tpl && tpl.templates) || []);
}

function itemById(id) {
  for (const g of S.catalog) for (const it of g.items) if (it.id === id) return it;
  return null;
}

function drawBuilder(host, templates) {
  host.innerHTML = `
    <div class="sr-tplbar" id="sr-tplbar"></div>
    <div class="sr-grid">
      <div class="sr-col">
        <div class="sr-colhead"><span>Available results — pick what to include</span><span class="sr-hint">tick to add</span></div>
        <div class="sr-colbody" id="sr-catalog"></div>
      </div>
      <div class="sr-col">
        <div class="sr-colhead"><span>Report contents — in order</span><span class="sr-hint" id="sr-count"></span></div>
        <div class="sr-colbody">
          <div class="sr-namewrap">
            <label>Report name (printed on the cover)</label>
            <input type="text" id="sr-name" value="${esc(S.name)}">
          </div>
          <div id="sr-selected"></div>
        </div>
        <div class="sr-foot">
          <button class="btn-secondary" id="sr-save-tpl">💾 Save as template</button>
          <span class="sr-appear" id="sr-appear"></span>
          <button class="btn-secondary" id="sr-preview">👁 Preview</button>
          <button class="btn-secondary" id="sr-word">⬇ Word</button>
          <button class="btn-primary" id="sr-pdf">⬇ PDF</button>
        </div>
      </div>
    </div>`;

  drawTemplates(templates);
  drawCatalog();
  drawSelected();

  document.getElementById('sr-name').addEventListener('input', e => { S.name = e.target.value; });
  document.getElementById('sr-appear').appendChild(buildAppearancePicker({ current: getSavedMode(), compact: true }));
  document.getElementById('sr-preview').addEventListener('click', doPreview);
  document.getElementById('sr-word').addEventListener('click', () => doExport('doc'));
  document.getElementById('sr-pdf').addEventListener('click', () => doExport('pdf'));
  document.getElementById('sr-save-tpl').addEventListener('click', doSaveTemplate);
}

function drawTemplates(templates) {
  const bar = document.getElementById('sr-tplbar');
  const chips = (templates || []).map(t =>
    `<button class="sr-chip${t.id === S.templateId ? ' active' : ''}" data-tpl="${esc(t.id)}">${esc(t.name)}</button>`).join('');
  bar.innerHTML = `<span class="sr-tpllabel">Saved reports:</span>${chips}<button class="sr-chip sr-new" data-tpl="__new">+ New report</button>`;
  bar.querySelectorAll('[data-tpl]').forEach(b => b.addEventListener('click', () => {
    const id = b.dataset.tpl;
    if (id === '__new') { S.templateId = null; S.selected = []; S.name = ''; renderSpecialPanel(); return; }
    const t = (templates || []).find(x => x.id === id);
    if (t) { S.templateId = t.id; S.selected = (t.item_ids || []).slice(); S.name = t.name; renderSpecialPanel(); }
  }));
}

function availBadge(av) {
  if (av === 'ready') return `<span class="sr-badge ok">Ready</span>`;
  if (av === 'needs_input') return `<span class="sr-badge warn">Needs input</span>`;
  return `<span class="sr-badge muted">No data</span>`;
}

function drawCatalog() {
  const box = document.getElementById('sr-catalog');
  box.innerHTML = S.catalog.map(g => {
    const need = g.items.find(i => i.availability === 'needs_input' && (i.requires || []).length);
    const attachBox = need ? attachHtml(g, need) : '';
    const items = g.items.map(it => {
      const on = S.selected.includes(it.id);
      const disabled = it.availability !== 'ready';
      return `<label class="sr-item${disabled ? ' off' : ''}">
        <input type="checkbox" data-add="${esc(it.id)}" ${on ? 'checked' : ''} ${disabled ? 'disabled' : ''}>
        <span class="sr-il">${esc(it.title)}</span>
        <span class="sr-typ ${it.availability === 'needs_input' ? 'need' : ''}">${it.availability === 'needs_input' ? 'needs input' : esc(it.ctype)}</span>
      </label>`;
    }).join('');
    const gavail = g.items.every(i => i.availability === 'ready') ? 'ready'
      : (g.items.some(i => i.availability === 'needs_input') ? 'needs_input' : 'no_data');
    return `<div class="sr-feat">
      <div class="sr-fh"><span class="sr-fname">${esc(g.feature_title)}</span>${availBadge(gavail)}</div>
      ${attachBox}${items}</div>`;
  }).join('');

  box.querySelectorAll('[data-add]').forEach(cb => cb.addEventListener('change', () => {
    const id = cb.dataset.add;
    if (cb.checked) { if (!S.selected.includes(id)) S.selected.push(id); }
    else { S.selected = S.selected.filter(x => x !== id); }
    drawSelected();
  }));
  box.querySelectorAll('[data-attach]').forEach(b => b.addEventListener('click', () => attach(b.dataset.attach)));
}

function attachHtml(g, need) {
  const roles = {};
  g.items.forEach(i => (i.requires || []).forEach(r => { roles[r.role] = r; }));
  return Object.values(roles).map(r => {
    const got = S.inputs[r.role];
    return `<div class="sr-need">
      <div class="sr-needtxt">This result needs a <b>${esc(r.label)}</b>. Attach it and Special Report runs the analysis for you — no need to open the ${esc(g.feature_title)} tab.</div>
      <button class="sr-attach${got ? ' done' : ''}" data-attach="${esc(r.role)}">${got ? '✓ ' + esc(fileName(got)) : '📎 Attach ' + esc(r.label)}</button>
    </div>`;
  }).join('');
}

function fileName(p) { return String(p).split(/[\\/]/).pop(); }

async function attach(role) {
  const path = await window.pywebview.api.choose_file();
  if (!path) return;
  S.inputs[role] = path;
  renderSpecialPanel();   // re-fetch catalog → availability turns ready
}

function drawSelected() {
  const box = document.getElementById('sr-selected');
  document.getElementById('sr-count').textContent = `${S.selected.length} item${S.selected.length === 1 ? '' : 's'}`;
  if (!S.selected.length) {
    box.innerHTML = `<div class="sr-selempty">Tick results on the left to add them here, numbered in order.</div>`;
    return;
  }
  box.innerHTML = S.selected.map((id, i) => {
    const it = itemById(id);
    const title = it ? it.title : id;
    const src = it ? it.feature_title : '';
    return `<div class="sr-srow">
      <span class="sr-num">${i + 1}</span>
      <span class="sr-meta"><span class="sr-l1">${esc(title)}</span><span class="sr-l2">${esc(src)}</span></span>
      <span class="sr-ord">
        <button data-up="${i}" ${i === 0 ? 'disabled' : ''} title="Move up">▲</button>
        <button data-down="${i}" ${i === S.selected.length - 1 ? 'disabled' : ''} title="Move down">▼</button>
        <button data-rm="${esc(id)}" title="Remove">✕</button>
      </span></div>`;
  }).join('');
  box.querySelectorAll('[data-up]').forEach(b => b.addEventListener('click', () => move(+b.dataset.up, -1)));
  box.querySelectorAll('[data-down]').forEach(b => b.addEventListener('click', () => move(+b.dataset.down, +1)));
  box.querySelectorAll('[data-rm]').forEach(b => b.addEventListener('click', () => {
    S.selected = S.selected.filter(x => x !== b.dataset.rm);
    const cb = document.querySelector(`[data-add="${CSS.escape(b.dataset.rm)}"]`);
    if (cb) cb.checked = false;
    drawSelected();
  }));
}

function move(i, d) {
  const j = i + d;
  if (j < 0 || j >= S.selected.length) return;
  const t = S.selected[i]; S.selected[i] = S.selected[j]; S.selected[j] = t;
  drawSelected();
}

async function doPreview() {
  if (!S.selected.length) { showError('Pick at least one result first.'); return; }
  const first = await api('api/special/render', reqBody({ theme: getSavedMode() }));
  if (!first.ok) { showError(first.error || 'Preview failed.'); return; }
  showReportPreview({
    title: S.name, subtitle: 'Special Report', html: first.html, initialMode: getSavedMode(),
    onThemeChange: async (mode) => {
      const r = await api('api/special/render', reqBody({ theme: mode }));
      return r.ok ? r.html : `<p>${esc(r.error || 'error')}</p>`;
    },
    onSave: (mode) => saveFile('pdf', mode),
  });
}

async function doExport(ext) {
  if (!S.selected.length) { showError('Pick at least one result first.'); return; }
  await saveFile(ext, getSavedMode());
}

async function saveFile(ext, mode) {
  const safe = (S.name || 'special-report').replace(/[^\w\- ]+/g, '').trim() || 'special-report';
  const out = await window.pywebview.api.choose_save_path(`${safe}.${ext}`, ext);
  if (!out) return false;
  const route = ext === 'doc' ? 'api/special/doc' : 'api/special/pdf';
  const res = await api(route, reqBody({ theme: mode, output_path: out }));
  if (!res.ok) { showError(res.error || 'Export failed.'); return false; }
  return true;
}

async function doSaveTemplate() {
  const name = (S.name || '').trim();
  if (!name) { showError('Give the report a name before saving it as a template.'); return; }
  const res = await api('api/special/templates/save', {
    snapshot_id: state.currentSnapshotId,
    template: { id: S.templateId, name, item_ids: S.selected, mode: getSavedMode() },
  });
  if (!res.ok) { showError(res.error || 'Save failed.'); return; }
  S.templateId = res.template && res.template.id;
  renderSpecialPanel();
}
