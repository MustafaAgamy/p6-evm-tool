// ── In-app Help manual — logic + rendering ────────────────────────────────
// Pure helpers (unit-tested in tests/js/test_help.js) sit at the top; the DOM
// rendering below runs only in the browser. Content lives in help_content.js.

import { MANUAL } from './help_content.js';
import { escapeHtml } from './format.js';

// ── Pure helpers ──────────────────────────────────────────────────────────

export function flattenTopics(manual) {
  const out = [];
  for (const g of manual.groups) for (const t of g.topics) out.push({ ...t, group: g.group });
  return out;
}

export function topicById(manual, id) {
  for (const g of manual.groups) for (const t of g.topics) if (t.id === id) return t;
  return null;
}

// Lowercased searchable text for a topic — title, intro, steps, mechanics, terms.
export function topicHaystack(t) {
  const parts = [t.id, t.title, t.whatFor, t.where];
  for (const b of (t.how || [])) parts.push(b.p, b.formula, b.note);
  for (const s of (t.steps || [])) parts.push(s);
  for (const term of (t.terms || [])) parts.push(term.term, term.def);
  if (t.reading) parts.push(t.reading.good, t.reading.bad);
  return parts.filter(Boolean).join(' ').toLowerCase();
}

// Filter the manual by a search string. Empty/whitespace query → every group.
// Groups with no matching topic are dropped.
export function filterTopics(manual, query) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return manual.groups.map(g => ({ group: g.group, topics: g.topics.slice() }));
  const out = [];
  for (const g of manual.groups) {
    const topics = g.topics.filter(t => topicHaystack(t).includes(q));
    if (topics.length) out.push({ group: g.group, topics });
  }
  return out;
}

// Safe inline formatting: escape first, then a tiny **bold** / `code` subset.
export function mdInline(s) {
  if (s == null) return '';
  let out = escapeHtml(String(s));
  out = out.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  out = out.replace(/`([^`]+?)`/g, '<code>$1</code>');
  return out;
}

// ── DOM rendering (browser only) ──────────────────────────────────────────

let _selectedId = null;
let _query = '';
let _wired = false;

function _groupOf(id) {
  for (const g of MANUAL.groups) if (g.topics.some(t => t.id === id)) return g.group;
  return '';
}

function _railHtml(groups) {
  if (!groups.length) return '<div class="help-empty">No matches. Try another word.</div>';
  return groups.map(g =>
    `<div class="help-rg">${escapeHtml(g.group)}</div>` +
    g.topics.map(t =>
      `<button class="help-item${t.id === _selectedId ? ' active' : ''}" data-id="${escapeHtml(t.id)}">${escapeHtml(t.title)}</button>`
    ).join('')
  ).join('');
}

function _section(label, inner) {
  return `<div class="doc-h"><span class="dot"></span>${escapeHtml(label)}</div>${inner}`;
}

function _renderDoc(topic) {
  const doc = document.getElementById('help-doc');
  if (!doc) return;
  if (!topic) { doc.innerHTML = ''; return; }
  const parts = [
    `<div class="doc-crumb">${escapeHtml(_groupOf(topic.id))}</div>`,
    `<h1 class="doc-title">${escapeHtml(topic.title)}</h1>`,
  ];
  if (topic.whatFor)
    parts.push(_section('What it’s for', `<p class="doc-p">${mdInline(topic.whatFor)}</p>`));
  if (topic.steps && topic.steps.length) {
    const lis = topic.steps.map(s => `<li>${mdInline(s)}</li>`).join('');
    parts.push(_section(`How to use it in ${MANUAL.appName}`, `<ol class="doc-steps">${lis}</ol>`));
  }
  if (topic.how && topic.how.length) {
    const blocks = topic.how.map(b => b.formula
      ? `<div class="doc-formula"><code>${mdInline(b.formula)}</code>${b.note ? `<p class="doc-formula-note">${mdInline(b.note)}</p>` : ''}</div>`
      : `<p class="doc-p">${mdInline(b.p || '')}</p>`).join('');
    parts.push(_section(topic.howLabel || 'How it works', blocks));
  }
  if (topic.reading) {
    parts.push(_section('Reading the result',
      `<div class="doc-read">
        <div class="rb good"><div class="rl">Healthy</div><p>${mdInline(topic.reading.good)}</p></div>
        <div class="rb bad"><div class="rl">Watch out</div><p>${mdInline(topic.reading.bad)}</p></div>
      </div>`));
  }
  if (topic.terms && topic.terms.length) {
    const dl = topic.terms.map(t =>
      `<div class="doc-term"><dt>${escapeHtml(t.term)}</dt><dd>${mdInline(t.def)}</dd></div>`).join('');
    parts.push(`<dl class="doc-terms">${dl}</dl>`);
  }
  if (topic.where)
    parts.push(`<div class="doc-where"><span class="dw-tag">Where this lives</span><p>${mdInline(topic.where)}</p></div>`);
  parts.push(`<p class="doc-edit">One entry in the manual — if this feature changes, only this page is updated. · ${escapeHtml(MANUAL.appName)} manual v${escapeHtml(MANUAL.version)}</p>`);
  doc.innerHTML = parts.join('');
  doc.scrollTop = 0;
}

export function selectTopic(id) {
  _selectedId = id;
  const list = document.getElementById('help-rail-list');
  if (list) list.innerHTML = _railHtml(filterTopics(MANUAL, _query));
  _renderDoc(topicById(MANUAL, id));
}

function _ensureWired() {
  if (_wired) return;
  const input = document.getElementById('help-search-input');
  const list = document.getElementById('help-rail-list');
  if (input) input.addEventListener('input', (e) => {
    _query = e.target.value;
    if (list) list.innerHTML = _railHtml(filterTopics(MANUAL, _query));
  });
  if (list) list.addEventListener('click', (e) => {
    const btn = e.target.closest('.help-item');
    if (btn) selectTopic(btn.dataset.id);
  });
  _wired = true;
}

export function renderHelp() {
  _ensureWired();
  const list = document.getElementById('help-rail-list');
  if (list) list.innerHTML = _railHtml(filterTopics(MANUAL, _query));
  const foot = document.getElementById('help-rail-foot');
  if (foot) foot.textContent = `${MANUAL.appName} · Manual v${MANUAL.version}`;
  if (!_selectedId) _selectedId = (MANUAL.groups[0].topics[0] || {}).id;
  _renderDoc(topicById(MANUAL, _selectedId));
}

export function isHelpOpen() {
  const view = document.getElementById('help-view');
  return !!(view && !view.classList.contains('hidden'));
}

export function openHelp() {
  const view = document.getElementById('help-view');
  if (!view) return;
  const content = document.querySelector('.content');
  if (content) content.classList.add('hidden');
  view.classList.remove('hidden');
  const sub = document.getElementById('topbar-sub');
  if (sub) sub.textContent = 'Help · Manual';
  ['sb-home-btn', 'sb-audit-btn'].forEach(id => {
    const el = document.getElementById(id); if (el) el.classList.remove('active');
  });
  const h = document.getElementById('sb-help-btn'); if (h) h.classList.add('active');
  renderHelp();
}

export function closeHelp() {
  const view = document.getElementById('help-view');
  if (view) view.classList.add('hidden');
  const content = document.querySelector('.content');
  if (content) content.classList.remove('hidden');
  const h = document.getElementById('sb-help-btn'); if (h) h.classList.remove('active');
}
