// Knowledge Base library — browse the project-type standards as a P6-style EPS.
// Category folders → project types; each type opens to its reference "baseline"
// standard (the same one a schedule is reviewed against). Three levels: browse,
// review a loaded schedule against a type, and export a type as a P6 starter
// baseline. Offline, no schedule needed to browse.

import { state }                    from './state.js';
import { showError }                from './render.js';
import { escapeHtml }               from './format.js';
import { switchView }               from './audit.js';
import { renderConstructPanel }     from './construct.js';

const CAT_ICON = {
  Buildings: '🏢', Infrastructure: '🛣️', Industrial: '🏭', Energy: '⚡', Landscape: '🌳',
  'Learned from your projects': '◆',
};

// ── navigation (KB is its own "page") ───────────────────────────────────────

export function showKbLibrary() {
  document.getElementById('kb-section').classList.remove('hidden');
  document.querySelector('.import-section')?.classList.add('hidden');
  document.getElementById('results-section')?.classList.add('hidden');
  document.querySelector('.recent-section')?.classList.add('hidden');
  document.getElementById('sb-home-btn')?.classList.remove('active');
  document.getElementById('sb-audit-btn')?.classList.remove('active');
  document.getElementById('sb-kb-btn')?.classList.add('active');
  document.getElementById('topbar-sub').textContent = 'Knowledge Base · Project Standards';
  if (state.kbLibrary) { renderTree(); }
  else { loadKb(); }
}

export function exitKbLibrary() {
  document.getElementById('kb-section')?.classList.add('hidden');
  document.querySelector('.import-section')?.classList.remove('hidden');
  document.querySelector('.recent-section')?.classList.remove('hidden');
  document.getElementById('sb-kb-btn')?.classList.remove('active');
  document.getElementById('sb-home-btn')?.classList.add('active');
}

// ── data ────────────────────────────────────────────────────────────────────

async function loadKb() {
  const tree = document.getElementById('kb-tree');
  if (tree) tree.innerHTML = '<div class="cmp-loading">Loading the Knowledge Base…</div>';
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/kb`);
    const data = await resp.json();
    if (!data.ok) { showError(data.error || 'Could not load the Knowledge Base.'); return; }
    state.kbLibrary = data;
    const first = data.categories[0];
    state.kbSelectedCat = state.kbSelectedCat || first?.category || null;
    if (!state.kbSelectedType && first?.types[0]) state.kbSelectedType = first.types[0].type;
    renderTree();
    renderDetail(findEntry(state.kbSelectedType));
    document.getElementById('kb-total').textContent = `${data.total} project types`;
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  }
}

function findEntry(type) {
  for (const c of state.kbLibrary?.categories || []) {
    const e = c.types.find(t => t.type === type);
    if (e) return e;
  }
  return null;
}

// ── EPS tree ─────────────────────────────────────────────────────────────────

function renderTree(filter = '') {
  const tree = document.getElementById('kb-tree');
  if (!tree || !state.kbLibrary) return;
  const f = filter.trim().toLowerCase();
  const html = state.kbLibrary.categories.map(c => {
    const types = c.types.filter(t => !f || t.type.toLowerCase().includes(f));
    if (!types.length) return '';
    const open = !!f || c.category === state.kbSelectedCat;
    const leaves = types.map(t => `
      <div class="kb-leaf ${t.type === state.kbSelectedType ? 'sel' : ''}" data-type="${escapeHtml(t.type)}">
        <span class="dot"></span><span class="nm">${escapeHtml(t.type)}</span>
        ${t.status === 'learned' ? `<span class="kb-db learned">${t.imports || ''} imports</span>`
          : t.status === 'draft' ? '<span class="kb-db">draft</span>' : ''}
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
  state.kbSelectedType = type;
  const entry = findEntry(type);
  if (entry) state.kbSelectedCat = entry.category;
  renderTree(document.getElementById('kb-search')?.value || '');
  renderDetail(entry);
}

// ── detail: the baseline standard ────────────────────────────────────────────

function chips(list, cls = '') {
  if (!list || !list.length) return '<span class="kb-mut">—</span>';
  return list.map(s => `<span class="kb-chip ${cls}">${escapeHtml(s)}</span>`).join('');
}

function renderDetail(entry) {
  const box = document.getElementById('kb-detail');
  if (!box) return;
  if (!entry) { box.innerHTML = '<p class="kb-empty">Pick a project type from the list.</p>'; return; }

  const learned = entry.status === 'learned' || entry.source === 'learned';
  const draft = learned
    ? `<span class="kb-learned" title="Learned from your own imports — private, this PC">◆ Learned · ${entry.imports || 0} imports</span>`
    : (entry.status === 'draft'
      ? '<span class="kb-draft" title="Starter knowledge — confirm before relying on it">◆ draft standard</span>' : '');

  const wbs = (entry.wbs || []).map(w =>
    `<div class="kb-wbsitem"><span class="ic">▸</span>${escapeHtml(w.name)}</div>`).join('')
    || '<span class="kb-mut">—</span>';

  const acts = (entry.activities || []).map(a => `<tr>
    <td><b>${escapeHtml(a.name || '')}</b></td>
    <td class="kb-mut">${escapeHtml(a.wbs || '')}</td>
    <td class="kb-flow">${a.typical_pred ? `<b>${escapeHtml(a.typical_pred)}</b> → ` : ''}${escapeHtml(a.typical_succ || a.name || '')}</td>
    <td class="kb-dur">${a.duration_days ?? '—'}</td>
    <td class="kb-why">${escapeHtml(a.why || '')}</td></tr>`).join('')
    || '<tr><td colspan="5" class="kb-mut">No key activities listed.</td></tr>';

  const rules = (entry.logic_rules || []).map(r => {
    const bt = (r.before_keywords || [])[0] || '';
    const at = (r.after_keywords || [])[0] || '';
    const imp = /crit/i.test(r.impact || '') ? 'c' : 'n';
    return `<div class="kb-rule">
      <div class="seq"><b>${escapeHtml(bt)}</b> → ${escapeHtml(at)}</div>
      <div class="rz">${escapeHtml(r.reason || '')}</div>
      <span class="kb-imp ${imp}">${escapeHtml((r.impact || 'Minor').toUpperCase())}</span></div>`;
  }).join('') || '<span class="kb-mut">—</span>';

  const issues = (entry.common_issues || []).map(i => `<li>${escapeHtml(i)}</li>`).join('')
    || '<li class="kb-mut">—</li>';

  const loaded = !!state.currentResult;
  const reviewBtn = loaded
    ? `<button class="btn-primary kb-act" data-act="review" data-type="${escapeHtml(entry.type)}">📥 Review my schedule against this</button>`
    : `<button class="btn-secondary kb-act" data-act="review-hint" title="Import a schedule first">📥 Review a schedule against this</button>`;

  box.innerHTML = `
    <div class="kb-crumb">${escapeHtml(entry.category)} &nbsp;›&nbsp; <b>${escapeHtml(entry.type)}</b></div>
    <div class="kb-dhead"><h2>${escapeHtml(entry.type)}</h2>${draft}</div>
    <div class="kb-callout">${learned
      ? `Learned from <b>${entry.imports || 0} of your own imported ${escapeHtml(entry.type)} schedules</b> — the recurring activities, typical durations and WBS your projects actually use. Private &amp; local, never sent anywhere. Compare it to the curated standard, and export it as a P6 starter or a file.`
      : `This is the <b>baseline standard</b> for a ${escapeHtml(entry.type)}. When you import a schedule, nPace auto-detects the type and checks your logic, activities and WBS against what's below — and you can export this standard as a P6 starter schedule to build your own baseline from.`}</div>

    ${learned ? '' : `<div class="kb-sec"><h3>Detected by <span class="n">${(entry.signatures || []).length} keywords</span></h3>
      <div class="kb-chips">${chips((entry.signatures || []).slice(0, 18), 'k')}</div></div>`}

    <div class="kb-sec"><h3>Standard WBS <span class="n">${(entry.wbs || []).length} branches</span></h3>
      <div class="kb-wbslist">${wbs}</div></div>

    <div class="kb-sec"><h3>Standard activities <span class="n">key / often-missing</span></h3>
      <div class="kb-tblwrap"><table class="kb-acts">
        <thead><tr><th>Activity</th><th>WBS</th><th>Typical sequence</th><th>Dur (d)</th><th>Why it matters</th></tr></thead>
        <tbody>${acts}</tbody></table></div></div>

    ${learned ? '' : `<div class="kb-sec"><h3>Construction logic rules <span class="n">${(entry.logic_rules || []).length}</span></h3>${rules}</div>

    <div class="kb-sec"><h3>Milestones</h3><div class="kb-chips">${chips(entry.milestones)}</div></div>

    <div class="kb-sec"><h3>Common issues it catches</h3><ul class="kb-issues">${issues}</ul></div>`}

    <div class="kb-actions">
      ${reviewBtn}
      <button class="btn-secondary kb-act" data-act="export" data-type="${escapeHtml(entry.type)}">📤 Export as P6 starter baseline</button>
      ${learned ? `<button class="btn-secondary kb-act" data-act="download" data-type="${escapeHtml(entry.type)}">⬇ Download learned standard</button>` : ''}
    </div>
    <div class="kb-actnote" id="kb-actnote"></div>`;
}

// ── actions ──────────────────────────────────────────────────────────────────

function reviewAgainst(type) {
  if (!state.currentResult) { note('Import a schedule first (Home → Import), then come back and click Review.'); return; }
  state.constructForcedType = type;
  state.constructReport = null;
  exitKbLibrary();
  document.getElementById('results-section')?.classList.remove('hidden');
  switchView('construct');
  renderConstructPanel();
  document.getElementById('results-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function exportStarter(type, btn) {
  const safe = type.replace(/[^\w]+/g, '_').replace(/^_+|_+$/g, '');
  let path = null;
  try {
    path = await window.pywebview.api.choose_save_path(`${safe}_starter_baseline.xml`, 'xml');
  } catch { showError('Could not open the save dialog.'); return; }
  if (!path) return;
  const orig = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/kb/starter-xml`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, output_path: path }),
    });
    const data = await resp.json();
    if (!data.ok) { showError(data.error || 'Export failed.'); return; }
    note(`✓ Starter baseline saved — ${data.activities} activities across ${data.wbs} WBS branches. ` +
         `Import the XML into Primavera P6 as a new project, then press F9 to schedule it.`, true);
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = orig; }
  }
}

async function downloadLearned(type, btn) {
  const safe = type.replace(/[^\w]+/g, '_').replace(/^_+|_+$/g, '');
  let path = null;
  try {
    path = await window.pywebview.api.choose_save_path(`${safe}_learned_standard.json`, 'json');
  } catch { showError('Could not open the save dialog.'); return; }
  if (!path) return;
  const orig = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/kb/learned-file`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, output_path: path }),
    });
    const data = await resp.json();
    if (!data.ok) { showError(data.error || 'Download failed.'); return; }
    note(`✓ Learned standard saved — ${data.activities} recurring activities across ${data.wbs} WBS branches.`, true);
  } catch {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = orig; }
  }
}

function note(msg, ok = false) {
  const n = document.getElementById('kb-actnote');
  if (n) { n.textContent = msg; n.className = 'kb-actnote' + (ok ? ' ok' : ' info'); }
}

// ── init (delegated listeners, set up once) ──────────────────────────────────

export function initKbLibrary() {
  const tree = document.getElementById('kb-tree');
  if (tree) tree.addEventListener('click', (e) => {
    const cat = e.target.closest('.kb-cat');
    if (cat) {
      const name = cat.dataset.cat;
      state.kbSelectedCat = (state.kbSelectedCat === name) ? null : name;
      renderTree(document.getElementById('kb-search')?.value || '');
      return;
    }
    const leaf = e.target.closest('.kb-leaf');
    if (leaf) selectType(leaf.dataset.type);
  });

  const search = document.getElementById('kb-search');
  if (search) search.addEventListener('input', () => renderTree(search.value));

  const detail = document.getElementById('kb-detail');
  if (detail) detail.addEventListener('click', (e) => {
    const btn = e.target.closest('.kb-act');
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === 'review') reviewAgainst(btn.dataset.type);
    else if (act === 'review-hint') note('Import a schedule first (Home → Import), then come back and click Review.');
    else if (act === 'export') exportStarter(btn.dataset.type, btn);
    else if (act === 'download') downloadLearned(btn.dataset.type, btn);
  });
}
