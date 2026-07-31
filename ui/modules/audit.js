// ── Pure helpers (unit-tested in tests/js/test_audit.js) ──────────────────

export function filterFindings(findings, { severity, check, wbs, query } = {}) {
  const q = (query || '').trim().toLowerCase();
  return findings.filter(f => {
    if (severity && f.severity !== severity) return false;
    if (check && f.check_name !== check) return false;
    if (wbs && !(f.wbs_path || '').toLowerCase().includes(wbs.toLowerCase())) return false;
    if (q) {
      const hay = `${f.activity_id || ''} ${f.activity_name || ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

export function severityClass(sev) {
  return { Critical: 't-crit', High: 't-high', Medium: 't-med', Low: 't-low' }[sev] || 't-low';
}

export function scoreColor(score) {
  if (score >= 85) return 'color-green';
  if (score >= 60) return 'color-amber';
  return 'color-red';
}

export function gaugeDashoffset(score, circumference) {
  const s = Math.max(0, Math.min(100, score || 0));
  return circumference * (1 - s / 100);
}

export function uniqueValues(findings, key) {
  return [...new Set(findings.map(f => f[key]).filter(Boolean))].sort();
}

// ── DOM rendering + wiring (browser only) ─────────────────────────────────

import { state } from './state.js';
import { escapeHtml } from './format.js';

const SEV_ORDER = ['Critical', 'High', 'Medium', 'Low'];
let _filters = { severity: '', check: '', wbs: '', query: '' };

export function switchView(view) {
  document.getElementById('evm-panel').classList.toggle('hidden', view !== 'evm');
  document.getElementById('audit-panel').classList.toggle('hidden', view !== 'audit');
  document.getElementById('tab-evm').classList.toggle('active', view === 'evm');
  document.getElementById('tab-audit').classList.toggle('active', view === 'audit');
  // Keep exactly one sidebar item highlighted: shield on the Audit view, Home otherwise.
  document.getElementById('sb-audit-btn').classList.toggle('active', view === 'audit');
  document.getElementById('sb-home-btn').classList.toggle('active', view !== 'audit');
}

export function renderAudit(audit) {
  state.currentAudit = audit || null;
  _filters = { severity: '', check: '', wbs: '', query: '' };
  const body = document.getElementById('audit-body');
  if (!audit || !audit.findings) {
    body.innerHTML = '<p style="color:var(--muted);font-size:13px">No audit available for this schedule.</p>';
    return;
  }
  const ov = audit.scores.overall;
  const areas = audit.total_review_areas || 5;
  const C = 326.7; // 2πr, r=52
  body.innerHTML = `
    <div class="audit-hero">
      <div class="score-card">
        <div class="gauge">
          <svg width="120" height="120" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="52" fill="none" stroke="var(--border)" stroke-width="12"/>
            <circle cx="60" cy="60" r="52" fill="none" stroke-width="12"
                    stroke-linecap="round" stroke-dasharray="${C}"
                    stroke-dashoffset="${gaugeDashoffset(ov.score, C)}"
                    transform="rotate(-90 60 60)" class="gauge-arc ${scoreColor(ov.score)}"/>
          </svg>
          <div class="gauge-num"><b>${ov.score ?? '—'}</b><span>/ 100</span></div>
        </div>
        <div class="score-meta">
          <div class="grade ${scoreColor(ov.score)}">${escapeHtml(ov.grade || '')}</div>
          <div class="coverage">Schedule Health Score</div>
          <div class="coverage">Based on <b>${ov.categories_evaluated} of ${areas}</b> review areas built so far — Schedule Logic &amp; Float Analysis.</div>
        </div>
      </div>
      <div class="catcards">${renderCatCards(audit.scores.categories)}</div>
    </div>
    <div class="sevrow">${renderSevChips(audit.counts.by_severity)}</div>
    <div class="filters">${renderFilterBar(audit.findings)}</div>
    <div class="tblwrap"><table class="audit-table"><thead><tr>
      <th style="width:76px">Severity</th><th style="width:100px">Check</th>
      <th>Activity / WBS</th><th>Issue &amp; recommendation</th></tr></thead>
      <tbody id="audit-tbody"></tbody></table></div>`;

  wireFilters();
  renderRows();
}

function renderCatCards(categories) {
  return Object.entries(categories || {}).map(([name, c]) => `
    <div class="catcard">
      <div class="cn">${escapeHtml(name)}</div>
      <div class="cv ${scoreColor(c.score)}">${c.score}</div>
      <div class="cvbar"><div class="cvfill ${scoreColor(c.score)}" style="width:${Math.max(0, Math.min(100, c.score))}%"></div></div>
    </div>`).join('');
}

function renderSevChips(bySev) {
  return SEV_ORDER.map(s => `
    <div class="sevchip" data-sev="${s}">
      <span class="sevdot d-${severityClass(s).slice(2)}"></span>
      <b>${bySev?.[s] || 0}</b><small>${s}</small>
    </div>`).join('');
}

function renderFilterBar(findings) {
  const opts = (vals) => ['<option value="">All</option>',
    ...vals.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`)].join('');
  return `
    <label class="selbox"><span>Severity</span>
      <select id="f-sev">${opts(SEV_ORDER.filter(s => findings.some(f => f.severity === s)))}</select></label>
    <label class="selbox"><span>Check</span>
      <select id="f-check">${opts(uniqueValues(findings, 'check_name'))}</select></label>
    <label class="selbox"><span>WBS</span>
      <select id="f-wbs">${opts(uniqueValues(findings, 'wbs_path'))}</select></label>
    <input class="searchbox" id="f-search" placeholder="🔍  Search activity ID or name…">`;
}

function wireFilters() {
  const set = (k, el, ev) => document.getElementById(el).addEventListener(ev, e => {
    _filters[k] = e.target.value; syncChips(); renderRows();
  });
  set('severity', 'f-sev', 'change');
  set('check', 'f-check', 'change');
  set('wbs', 'f-wbs', 'change');
  set('query', 'f-search', 'input');
  document.querySelectorAll('.sevchip').forEach(chip =>
    chip.addEventListener('click', () => {
      const s = chip.dataset.sev;
      _filters.severity = (_filters.severity === s) ? '' : s;
      document.getElementById('f-sev').value = _filters.severity;
      syncChips(); renderRows();
    }));
}

function syncChips() {
  document.querySelectorAll('.sevchip').forEach(c =>
    c.classList.toggle('on', _filters.severity === c.dataset.sev));
}

function renderRows() {
  const audit = state.currentAudit;
  const tbody = document.getElementById('audit-tbody');
  if (!audit || !tbody) return;
  const rows = filterFindings(audit.findings, _filters);
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:20px">No findings match these filters.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(f => `
    <tr>
      <td><span class="sevtag ${severityClass(f.severity)}">${escapeHtml(f.severity)}</span></td>
      <td><span class="checktag">${escapeHtml(f.check_name)}</span></td>
      <td><div class="actid">${escapeHtml(f.activity_id)}</div>
          <div class="actname">${escapeHtml(f.activity_name)}</div>
          <div class="wbs">${escapeHtml(f.wbs_path)}</div></td>
      <td><div class="issue">${escapeHtml(f.summary)}</div>
          <div class="rec">${escapeHtml(f.recommendation)}</div>
          <div class="fid">#${escapeHtml(f.finding_id || '')}</div></td>
    </tr>`).join('');
}
