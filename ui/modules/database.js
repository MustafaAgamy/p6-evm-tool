// Construction Database — a local library of P6 schedules grouped by project type.
// Every type offers generated example baselines (a clean one and a "with typical
// gaps" one); the user can also add their own imported schedules (which feed the
// learning engine). Reuses the KB-library layout classes. Private & local.

import { state }          from './state.js';
import { showError }      from './render.js';
import { escapeHtml }     from './format.js';
import { showKbLibrary }  from './kblib.js';

const CAT_ICON = {
  Buildings: '🏢', Infrastructure: '🛣️', Industrial: '🏭', Energy: '⚡', Landscape: '🌳',
};

// ── navigation (own page) ────────────────────────────────────────────────────

export function showDatabase() {
  document.getElementById('kb-database-section')?.classList.remove('hidden');
  document.querySelector('.import-section')?.classList.add('hidden');
  document.getElementById('results-section')?.classList.add('hidden');
  document.querySelector('.recent-section')?.classList.add('hidden');
  document.getElementById('kb-section')?.classList.add('hidden');
  document.getElementById('sb-home-btn')?.classList.remove('active');
  document.getElementById('sb-kb-btn')?.classList.remove('active');
  document.getElementById('sb-db-btn')?.classList.add('active');
  document.getElementById('topbar-sub').textContent = 'Knowledge Base';
  if (state.dbLibrary) renderTree(); else loadDatabase();
  loadKbProjects();
}

export function exitDatabase() {
  document.getElementById('kb-database-section')?.classList.add('hidden');
  document.querySelector('.import-section')?.classList.remove('hidden');
  document.querySelector('.recent-section')?.classList.remove('hidden');
  document.getElementById('sb-db-btn')?.classList.remove('active');
  document.getElementById('sb-home-btn')?.classList.add('active');
}

// ── data ─────────────────────────────────────────────────────────────────────

async function loadDatabase() {
  const tree = document.getElementById('db-tree');
  if (tree) tree.innerHTML = '<div class="cmp-loading">Loading the Construction Database…</div>';
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/database`);
    const data = await resp.json();
    if (!data.ok) { showError(data.error || 'Could not load the Construction Database.'); return; }
    state.dbLibrary = data;
    const first = data.categories[0];
    state.dbSelectedCat = state.dbSelectedCat || first?.category || null;
    if (!state.dbSelectedType && first?.types[0]) state.dbSelectedType = first.types[0].type;
    renderTree();
    renderDetail(findType(state.dbSelectedType));
    const el = document.getElementById('db-total');
    if (el) el.textContent = `${data.types_total} types · ${data.contributed_total} of your schedules`;
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  }
}

function findType(type) {
  for (const c of state.dbLibrary?.categories || []) {
    const t = c.types.find(x => x.type === type);
    if (t) return t;
  }
  return null;
}

// ── EPS tree ─────────────────────────────────────────────────────────────────

function renderTree(filter = '') {
  const tree = document.getElementById('db-tree');
  if (!tree || !state.dbLibrary) return;
  const f = filter.trim().toLowerCase();
  const html = state.dbLibrary.categories.map(c => {
    const types = c.types.filter(t => !f || t.type.toLowerCase().includes(f));
    if (!types.length) return '';
    const open = !!f || c.category === state.dbSelectedCat;
    const leaves = types.map(t => `
      <div class="kb-leaf ${t.type === state.dbSelectedType ? 'sel' : ''}" data-type="${escapeHtml(t.type)}">
        <span class="dot"></span><span class="nm">${escapeHtml(t.type)}</span>
        ${t.contributed_count ? `<span class="kb-db learned">${t.contributed_count}</span>` : ''}
      </div>`).join('');
    return `<div class="kb-node">
      <div class="kb-cat ${open ? 'open' : ''}" data-cat="${escapeHtml(c.category)}">
        <span class="caret">${open ? '▾' : '▸'}</span>
        <span class="ico">${CAT_ICON[c.category] || '📁'}</span>
        <span class="ct">${escapeHtml(c.category)}</span>
        <span class="count">${types.length}</span>
      </div>
      <div class="kb-children" ${open ? '' : 'style="display:none"'}>${leaves}</div>
    </div>`;
  }).join('');
  tree.innerHTML = html || '<p class="kb-empty">No project types match your search.</p>';
}

function selectType(type) {
  state.dbSelectedType = type;
  const t = findType(type);
  if (t) state.dbSelectedCat = t.category;
  renderTree(document.getElementById('db-search')?.value || '');
  renderDetail(t);
}

// ── detail ───────────────────────────────────────────────────────────────────

function renderDetail(t) {
  const box = document.getElementById('db-detail');
  if (!box) return;
  if (!t) { box.innerHTML = '<p class="kb-empty">Pick a project type from the list.</p>'; return; }
  const type = escapeHtml(t.type);

  const files = (t.contributed || []).map(f => `
    <div class="db-file">
      <span class="fic">📄</span>
      <div class="fmeta"><div class="fn">${escapeHtml(f.filename)}</div>
        <div class="fm">Your schedule · ${f.activities} activities · ${f.wbs} WBS · added ${escapeHtml(f.added || '')}</div></div>
      <button class="btn-secondary db-act" data-act="download" data-type="${type}" data-file="${escapeHtml(f.filename)}">⬇ Download</button>
    </div>`).join('')
    || '<p class="db-empty">None yet — import a schedule of this type and use <b>＋ Add to Database</b> in the review to add your own.</p>';

  box.innerHTML = `
    <div class="kb-crumb">${escapeHtml(t.category)} &nbsp;›&nbsp; <b>${type}</b></div>
    <div class="kb-dhead"><h2>${type}</h2>
      <span class="kb-learned">${(t.contributed || []).length} of your schedules</span></div>
    <div class="kb-callout">Download a ready-made P6 baseline for a <b>${type}</b> — a <b>clean</b> reference, or one carrying
      <b>typical gaps</b> so you can import it and watch the Constructability review flag them. Add your own real schedules to
      grow this library and teach the tool your organisation's practice. <b>Local &amp; private.</b></div>

    <div class="kb-sec"><h3>Generated example baselines <span class="n">P6 XML · import &amp; F9</span></h3>
      <div class="db-file">
        <span class="fic">🧩</span>
        <div class="fmeta"><div class="fn">Example baseline — with typical gaps</div>
          <div class="fm">Deliberately leaves a few illogical links &amp; missing activities — a ready demo of what the review catches.</div></div>
        <button class="btn-secondary db-act" data-act="gappy" data-type="${type}">⬇ Download</button>
      </div>
      <div class="db-file">
        <span class="fic">✅</span>
        <div class="fmeta"><div class="fn">Clean reference baseline</div>
          <div class="fm">Full logic &amp; scope — scores ~100. A tidy starting point to build from.</div></div>
        <button class="btn-secondary db-act" data-act="clean" data-type="${type}">⬇ Download</button>
      </div>
    </div>

    <div class="kb-sec"><h3>Your contributed schedules <span class="n">${(t.contributed || []).length}</span></h3>${files}</div>
    <div class="kb-actnote" id="db-actnote"></div>`;
}

// ── actions ──────────────────────────────────────────────────────────────────

async function exportExample(type, gappy, btn) {
  const safe = type.replace(/[^\w]+/g, '_').replace(/^_+|_+$/g, '');
  const name = `${safe}_${gappy ? 'example_with_gaps' : 'clean_baseline'}.xml`;
  let path = null;
  try { path = await window.pywebview.api.choose_save_path(name, 'xml'); }
  catch { showError('Could not open the save dialog.'); return; }
  if (!path) return;
  await _post('/api/database/example', { type, gappy, output_path: path }, btn,
    (d) => `✓ Saved — ${gappy ? `${d.illogical_seeded} illogical + ${d.missing_seeded} missing seeded. ` : ''}Import the XML into P6 as a new project and F9.`);
}

async function downloadContributed(type, filename, btn) {
  const ext = (filename.split('.').pop() || 'xml').toLowerCase();
  let path = null;
  try { path = await window.pywebview.api.choose_save_path(filename, ext); }
  catch { showError('Could not open the save dialog.'); return; }
  if (!path) return;
  await _post('/api/database/download', { type, filename, output_path: path }, btn,
    () => `✓ Saved — open it in Primavera P6.`);
}

async function _post(url, payload, btn, okMsg) {
  const orig = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}${url}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!data.ok) { showError(data.error || 'Download failed.'); return; }
    note(okMsg(data), true);
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = orig; }
  }
}

function note(msg, ok = false) {
  const n = document.getElementById('db-actnote');
  if (n) { n.textContent = msg; n.className = 'kb-actnote' + (ok ? ' ok' : ' info'); }
}

// ── unified Knowledge Base projects list ─────────────────────────────────────

export async function loadKbProjects() {
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/kb/knowledge`);
    const d = await resp.json();
    if (!d.ok) return;
    renderKbTable(d.projects || []);
    const c = document.getElementById('kbp-count');
    if (c) c.textContent = `${d.projects_learned} knowledge project(s) · ${d.pattern_count} generalized pattern(s)`;
  } catch { /* offline; leave as-is */ }
}

function renderKbTable(rows) {
  const t = document.getElementById('kbp-table');
  if (!t) return;
  if (!rows.length) {
    t.innerHTML = '<tbody><tr><td class="kbp-empty">No knowledge projects yet. Click <b>＋ Add Project XER</b> to add a real project — its generalized sequencing patterns become supporting knowledge for future reviews.</td></tr></tbody>';
    return;
  }
  const head = '<thead><tr><th>Project</th><th>Type</th><th>Source</th><th>Added</th><th>Patterns</th><th>Enabled</th><th></th></tr></thead>';
  const body = rows.map(r => `<tr>
    <td class="kbp-nm">${escapeHtml(r.name)}</td>
    <td>${escapeHtml(r.type || '—')}</td>
    <td><span class="kbp-src ${r.source === 'curated' ? 'curated' : 'user'}">${r.source === 'curated' ? 'Curated' : 'User'}</span></td>
    <td>${escapeHtml(r.date || '')}</td>
    <td class="kbp-num">${r.patterns}</td>
    <td><label class="kbp-toggle"><input type="checkbox" data-kb="enable" data-id="${escapeHtml(r.id)}" ${r.enabled ? 'checked' : ''}><span></span></label></td>
    <td class="kbp-acts">
      ${r.raw ? `<button class="kbp-mini" data-kb="download" data-raw="${escapeHtml(r.raw)}" data-name="${escapeHtml(r.name)}">⬇ XER</button>` : ''}
      <button class="kbp-mini danger" data-kb="remove" data-id="${escapeHtml(r.id)}" data-name="${escapeHtml(r.name)}">Remove</button>
    </td></tr>`).join('');
  t.innerHTML = head + '<tbody>' + body + '</tbody>';
}

async function kbAddXer(btn) {
  let path = null;
  try { path = await window.pywebview.api.choose_file(); } catch { showError('Could not open the file dialog.'); return; }
  if (!path) return;
  const orig = btn.textContent; btn.disabled = true; btn.textContent = 'Learning…';
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/kb/knowledge/import-xer`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ input_path: path }),
    });
    const d = await resp.json();
    if (!d.ok) { showError(d.error || 'Could not learn from that XER.'); return; }
    renderKbTable(d.projects || []);
    const c = document.getElementById('kbp-count');
    if (c) c.textContent = `${d.projects_learned} knowledge project(s) · ${d.pattern_count} generalized pattern(s) — added "${d.project}"`;
  } catch { showError('Could not reach the local server.'); }
  finally { btn.disabled = false; btn.textContent = orig; }
}

async function kbExport(btn) {
  let path = null;
  try { path = await window.pywebview.api.choose_save_path('constructability_knowledge.json', 'json'); }
  catch { showError('Could not open the save dialog.'); return; }
  if (!path) return;
  await _post('/api/kb/knowledge/export', { output_path: path }, btn, (d) => `✓ Exported ${d.projects || 0} project(s) of knowledge.`);
}

async function kbImport(btn) {
  let path = null;
  try { path = await window.pywebview.api.choose_open_path('json'); }
  catch { showError('Could not open the file dialog.'); return; }
  if (!path) return;
  const orig = btn.textContent; btn.disabled = true; btn.textContent = 'Importing…';
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/kb/knowledge/import`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ input_path: path }),
    });
    const d = await resp.json();
    if (!d.ok) { showError(d.error || 'Import failed.'); return; }
    loadKbProjects();
  } catch { showError('Could not reach the local server.'); }
  finally { btn.disabled = false; btn.textContent = orig; }
}

async function kbTableClick(e) {
  const btn = e.target.closest('[data-kb]');
  if (!btn || btn.dataset.kb === 'enable') return;
  if (btn.dataset.kb === 'download') {
    let path = null;
    try { path = await window.pywebview.api.choose_save_path(btn.dataset.raw, 'xml'); }
    catch { showError('Could not open the save dialog.'); return; }
    if (!path) return;
    await _post('/api/kb/raw/download', { filename: btn.dataset.raw, output_path: path }, btn, () => '✓ Saved the raw project XER.');
  } else if (btn.dataset.kb === 'remove') {
    if (!window.confirm(`Remove "${btn.dataset.name}" from the Knowledge Base? Its supporting patterns will no longer corroborate findings.`)) return;
    try {
      const resp = await fetch(`http://localhost:${state.serverPort}/api/kb/knowledge/remove`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: btn.dataset.id }),
      });
      const d = await resp.json();
      if (d.ok) { renderKbTable(d.projects || []); loadKbProjects(); }
    } catch { showError('Could not reach the local server.'); }
  }
}

async function kbToggle(e) {
  const cb = e.target.closest('input[data-kb="enable"]');
  if (!cb) return;
  try {
    await fetch(`http://localhost:${state.serverPort}/api/kb/knowledge/enable`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: cb.dataset.id, enabled: cb.checked }),
    });
  } catch { showError('Could not reach the local server.'); cb.checked = !cb.checked; }
}

// Called by the review after a successful "Add to Database" so the view refreshes.
export function invalidateDatabase() { state.dbLibrary = null; }

// ── init ─────────────────────────────────────────────────────────────────────

export function initDatabase() {
  const tree = document.getElementById('db-tree');
  if (tree) tree.addEventListener('click', (e) => {
    const cat = e.target.closest('.kb-cat');
    if (cat) {
      state.dbSelectedCat = (state.dbSelectedCat === cat.dataset.cat) ? null : cat.dataset.cat;
      renderTree(document.getElementById('db-search')?.value || '');
      return;
    }
    const leaf = e.target.closest('.kb-leaf');
    if (leaf) selectType(leaf.dataset.type);
  });

  const search = document.getElementById('db-search');
  if (search) search.addEventListener('input', () => renderTree(search.value));

  const detail = document.getElementById('db-detail');
  if (detail) detail.addEventListener('click', (e) => {
    const btn = e.target.closest('.db-act');
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === 'gappy') exportExample(btn.dataset.type, true, btn);
    else if (act === 'clean') exportExample(btn.dataset.type, false, btn);
    else if (act === 'download') downloadContributed(btn.dataset.type, btn.dataset.file, btn);
  });

  // unified Knowledge Base list toolbar + row actions
  document.getElementById('kbp-addxer')?.addEventListener('click', (e) => kbAddXer(e.currentTarget));
  document.getElementById('kbp-export')?.addEventListener('click', (e) => kbExport(e.currentTarget));
  document.getElementById('kbp-import')?.addEventListener('click', (e) => kbImport(e.currentTarget));
  document.getElementById('kbp-standards')?.addEventListener('click', () => { exitDatabase(); showKbLibrary(); });
  const kbt = document.getElementById('kbp-table');
  if (kbt) { kbt.addEventListener('click', kbTableClick); kbt.addEventListener('change', kbToggle); }
}
