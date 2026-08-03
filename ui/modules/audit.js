// ── Pure helpers (unit-tested in tests/js/test_audit.js) ──────────────────

export function areaOf(finding) {
  const id = finding.check_id || '';
  if (id.startsWith('FLOAT')) return 'Float Analysis';
  if (id.startsWith('LOGIC')) return 'Schedule Logic';
  return '';
}

export function filterFindings(findings, { severity, check, wbs, query, area } = {}) {
  const q = (query || '').trim().toLowerCase();
  return findings.filter(f => {
    if (area && areaOf(f) !== area) return false;
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
let _filters = { severity: '', check: '', wbs: '', query: '', area: '' };

export function switchView(view) {
  document.getElementById('evm-panel').classList.toggle('hidden', view !== 'evm');
  document.getElementById('audit-panel').classList.toggle('hidden', view !== 'audit');
  document.getElementById('tab-evm').classList.toggle('active', view === 'evm');
  document.getElementById('tab-audit').classList.toggle('active', view === 'audit');
  // Keep exactly one sidebar item highlighted: shield on the Audit view, Home otherwise.
  document.getElementById('sb-audit-btn').classList.toggle('active', view === 'audit');
  document.getElementById('sb-home-btn').classList.toggle('active', view !== 'audit');
}

export function shortWbs(path, n = 3) {
  if (!path) return '';
  const parts = path.split('>').map(s => s.trim());
  return parts.slice(-n).join(' > ');
}

export function gradeClass(grade) {
  return { 'Excellent': 'g-exc', 'Acceptable': 'g-acc',
           'Needs Attention': 'g-need', 'Critical': 'g-crit' }[grade] || 'g-need';
}

// Render the isolated-modules audit view: a module selector + one module's report.
export function renderAudit(auditModules) {
  state.currentModules = auditModules || null;
  const body = document.getElementById('audit-body');
  const tabs = document.getElementById('module-tabs');
  // Always rebuild a fresh #module-body so repeated renders never hit a
  // container that a prior "no audit" render replaced.
  body.innerHTML = '<div id="module-body"></div>';
  if (!auditModules || !auditModules.module_order || !auditModules.module_order.length) {
    tabs.innerHTML = '';
    document.getElementById('module-body').innerHTML =
      '<p style="color:var(--muted);font-size:13px">No audit available for this schedule.</p>';
    return;
  }
  tabs.innerHTML = auditModules.module_order.map(key => {
    const m = auditModules.modules[key];
    return `<button class="module-tab" data-module="${escapeHtml(key)}">
      <span class="mt-dot ${gradeClass(m.grade)}"></span>${escapeHtml(m.name)}
      <span class="mt-score">${m.score}</span></button>`;
  }).join('');
  tabs.querySelectorAll('.module-tab').forEach(btn =>
    btn.addEventListener('click', () => selectModule(btn.dataset.module)));
  selectModule(auditModules.module_order[0]);
}

export function selectModule(key) {
  const am = state.currentModules;
  if (!am || !am.modules[key]) return;
  state.currentModule = key;
  document.querySelectorAll('.module-tab').forEach(b =>
    b.classList.toggle('active', b.dataset.module === key));
  _filters = { severity: '', check: '', wbs: '', query: '', area: '' };
  renderModuleBody(am.modules[key]);
}

function kpiTiles(m) {
  const k = m.kpis || {};
  const tiles = m.module === 'dangling'
    ? [['Total Activities', (k.total_activities || 0).toLocaleString()],
       ['Total Dangling', k.total_dangling || 0],
       ['Dangling %', `${k.dangling_pct ?? 0}%`],
       ['Start', k.start_dangling || 0],
       ['Finish', k.finish_dangling || 0],
       ['Start + Finish', k.both_dangling || 0]]
    : [['Total Activities', (k.total_activities || 0).toLocaleString()],
       ['Above Threshold', k.above_threshold || 0],
       ['Float %', `${k.float_pct ?? 0}%`],
       ['Max Float', `${k.max_float ?? 0} d`],
       ['Average Float', `${k.avg_float ?? 0} d`],
       ['Threshold', `${k.threshold ?? 44} d`]];
  return tiles.map(([lab, val]) =>
    `<div class="kpi"><div class="k">${escapeHtml(lab)}</div><div class="v">${escapeHtml(val)}</div></div>`).join('');
}

function wbsSummaryHtml(m) {
  const ws = m.wbs_summary || [];
  if (!ws.length) return '';
  const rows = ws.slice(0, 12).map(r => `
    <tr><td title="${escapeHtml(r.wbs)}">${escapeHtml(shortWbs(r.wbs, 4))}</td>
      <td class="num">${r.activities}</td><td class="num">${r.high}</td>
      <td class="num">${r.pct}%</td>
      <td><span class="gbadge ${gradeClass(r.grade)}">${escapeHtml(r.grade)}</span></td></tr>`).join('');
  return `
    <div class="mod-sec">WBS Summary — where the excessive float concentrates</div>
    <div class="tblwrap"><table class="audit-table"><thead><tr>
      <th>WBS Package</th><th class="num">Activities</th><th class="num">High-Float</th>
      <th class="num">% of Package</th><th>Concentration</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
}

function renderModuleBody(m) {
  const C = 326.7;
  const verdict = m.module === 'dangling'
    ? `${m.pct}% of activities have broken start/finish logic.`
    : `${m.pct}% of activities carry total float above the threshold.`;
  const body = document.getElementById('module-body');
  body.innerHTML = `
    <div class="audit-hero">
      <div class="score-card">
        <div class="gauge">
          <svg width="120" height="120" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="52" fill="none" stroke="var(--border)" stroke-width="12"/>
            <circle cx="60" cy="60" r="52" fill="none" stroke-width="12" stroke-linecap="round"
                    stroke-dasharray="${C}" stroke-dashoffset="${gaugeDashoffset(m.score, C)}"
                    transform="rotate(-90 60 60)" class="gauge-arc ${scoreColor(m.score)}"/>
          </svg>
          <div class="gauge-num"><b>${m.score ?? '—'}</b><span>/ 100</span></div>
        </div>
        <div class="score-meta">
          <div class="grade-badge ${gradeClass(m.grade)}">${escapeHtml(m.grade || '')}</div>
          <div class="coverage">${escapeHtml(m.name)} — Module Score</div>
          <div class="coverage">${escapeHtml(verdict)}</div>
        </div>
      </div>
      <div class="kpi-tiles">${kpiTiles(m)}</div>
    </div>
    ${wbsSummaryHtml(m)}
    <div class="mod-sec">Detailed Findings</div>
    <div class="filters">
      ${renderSevChips(m.findings)}
      <input class="searchbox" id="f-search" placeholder="🔍  Search activity ID or name…">
    </div>
    <div class="tblwrap" style="overflow-x:auto"><table class="audit-table findings-table">
      <thead id="find-head"></thead><tbody id="audit-tbody"></tbody></table></div>`;

  document.getElementById('f-search').addEventListener('input', e => {
    _filters.query = e.target.value; renderRows();
  });
  document.querySelectorAll('.sevchip').forEach(chip =>
    chip.addEventListener('click', () => {
      const s = chip.dataset.sev;
      _filters.severity = (_filters.severity === s) ? '' : s;
      syncChips(); renderRows();
    }));
  renderRows();
}

function renderSevChips(findings) {
  const counts = {};
  for (const f of findings || []) counts[f.severity] = (counts[f.severity] || 0) + 1;
  return SEV_ORDER.filter(s => counts[s]).map(s => `
    <div class="sevchip" data-sev="${s}">
      <span class="sevdot d-${severityClass(s).slice(2)}"></span>
      <b>${counts[s]}</b><small>${s}</small>
    </div>`).join('');
}

function syncChips() {
  document.querySelectorAll('.sevchip').forEach(c =>
    c.classList.toggle('on', _filters.severity === c.dataset.sev));
}

function renderRows() {
  const am = state.currentModules;
  const key = state.currentModule;
  const tbody = document.getElementById('audit-tbody');
  const thead = document.getElementById('find-head');
  if (!am || !key || !tbody) return;
  const m = am.modules[key];
  const rows = filterFindings(m.findings, { severity: _filters.severity, query: _filters.query });

  const cols = m.module === 'dangling'
    ? ['#', 'Activity ID', 'Activity Name', 'WBS Path', 'Severity', 'Logic Issue', 'Predecessor(s)', 'Successor(s)', 'Suggested Logic Fix', 'Recommendation']
    : ['#', 'Activity ID', 'Activity Name', 'WBS Path', 'Total Float', 'Threshold', 'Impact', 'Status', 'Severity', 'Recommendation'];
  thead.innerHTML = `<tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr>`;

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="${cols.length}" style="text-align:center;color:var(--muted);padding:20px">No findings match.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map((f, i) => {
    const wbs = `<td title="${escapeHtml(f.wbs_path)}">${escapeHtml(shortWbs(f.wbs_path))}</td>`;
    const sev = `<td><span class="sevtag ${severityClass(f.severity)}">${escapeHtml(f.severity)}</span></td>`;
    if (m.module === 'dangling') {
      return `<tr><td class="num">${i + 1}</td>
        <td class="mono">${escapeHtml(f.activity_id)}</td>
        <td>${escapeHtml(f.activity_name)}</td>${wbs}${sev}
        <td>${escapeHtml(f.logic_issue)}</td>
        <td class="mut">${escapeHtml(f.predecessors)}</td>
        <td class="mut">${escapeHtml(f.successors)}</td>
        <td>${escapeHtml(f.suggested_fix)}</td>
        <td class="mut">${escapeHtml(f.recommendation)}</td></tr>`;
    }
    const impact = f.impact != null ? `${f.impact}×` : '—';
    return `<tr><td class="num">${i + 1}</td>
      <td class="mono">${escapeHtml(f.activity_id)}</td>
      <td>${escapeHtml(f.activity_name)}</td>${wbs}
      <td class="num">${escapeHtml(f.total_float_days)} d</td>
      <td class="num">${escapeHtml(f.threshold)} d</td>
      <td class="num">${impact}</td>
      <td>${escapeHtml(f.status)}</td>${sev}
      <td class="mut">${escapeHtml(f.recommendation)}</td></tr>`;
  }).join('');
}
