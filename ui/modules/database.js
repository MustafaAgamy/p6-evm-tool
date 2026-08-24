// Construction Database — a local library of P6 schedules grouped by project type.
// Every type offers generated example baselines (a clean one and a "with typical
// gaps" one); the user can also add their own imported schedules (which feed the
// learning engine). Reuses the KB-library layout classes. Private & local.

import { state }       from './state.js';
import { showError }   from './render.js';
import { escapeHtml }  from './format.js';

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
  document.getElementById('topbar-sub').textContent = 'Construction Database · Schedules';
  if (state.dbLibrary) renderTree(); else loadDatabase();
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
}
