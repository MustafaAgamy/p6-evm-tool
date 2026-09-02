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

// Bar fill % for a driver/WBS value against its max (0–100, clamped).
export function barPct(value, max) {
  const m = max || 1;
  return Math.max(0, Math.min(100, Math.round(100 * (value || 0) / m)));
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
  // Reveal the chosen analysis (the chooser gates this on import)
  document.getElementById('analysis-chooser').classList.add('hidden');
  document.getElementById('analysis-views').classList.remove('hidden');
  document.getElementById('evm-panel').classList.toggle('hidden', view !== 'evm');
  document.getElementById('audit-panel').classList.toggle('hidden', view !== 'audit');
  document.getElementById('oos-panel').classList.toggle('hidden', view !== 'oos');
  document.getElementById('calendar-panel').classList.toggle('hidden', view !== 'calendar');
  document.getElementById('construct-panel').classList.toggle('hidden', view !== 'construct');
  document.getElementById('compare-panel').classList.toggle('hidden', view !== 'compare');
  document.getElementById('lag-panel').classList.toggle('hidden', view !== 'lag');
  document.getElementById('period-panel').classList.toggle('hidden', view !== 'period');
  document.getElementById('critpath-panel').classList.toggle('hidden', view !== 'critpath');
  document.getElementById('update-panel').classList.toggle('hidden', view !== 'update');
  document.getElementById('special-panel').classList.toggle('hidden', view !== 'special');
  document.getElementById('dash-panel')?.classList.toggle('hidden', view !== 'dash');
  document.getElementById('narrative-panel')?.classList.toggle('hidden', view !== 'narrative');
  document.getElementById('forecast-panel')?.classList.toggle('hidden', view !== 'forecast');
  document.getElementById('overview-panel')?.classList.toggle('hidden', view !== 'overview');
  document.getElementById('wbs-panel')?.classList.toggle('hidden', view !== 'wbs');
  document.getElementById('schedule-panel')?.classList.toggle('hidden', view !== 'schedule');
  document.getElementById('tab-evm').classList.toggle('active', view === 'evm');
  document.getElementById('tab-audit').classList.toggle('active', view === 'audit');
  document.getElementById('tab-oos').classList.toggle('active', view === 'oos');
  document.getElementById('tab-calendar').classList.toggle('active', view === 'calendar');
  document.getElementById('tab-construct').classList.toggle('active', view === 'construct');
  document.getElementById('tab-compare').classList.toggle('active', view === 'compare');
  document.getElementById('tab-lag').classList.toggle('active', view === 'lag');
  document.getElementById('tab-period').classList.toggle('active', view === 'period');
  document.getElementById('tab-critpath').classList.toggle('active', view === 'critpath');
  document.getElementById('tab-update').classList.toggle('active', view === 'update');
  document.getElementById('tab-special').classList.toggle('active', view === 'special');
  // Highlight the active module in the Project Navigator (Aurora+ shell).
  document.querySelectorAll('#nav-tree .tnode[data-nav]').forEach(n =>
    n.classList.toggle('on', n.dataset.nav === view));
  // Out of Sequence and Lag Report are top-level views but reuse the module export path
  // (PDF/Excel) with a fixed module id.
  if (view === 'oos') state.currentModule = 'out_of_sequence';
  if (view === 'lag') state.currentModule = 'lag_lead';
}

// Show the "EVM vs Schedule Audit" choice; hide both analysis views until picked.
export function showChooser() {
  document.getElementById('analysis-chooser').classList.remove('hidden');
  document.getElementById('analysis-views').classList.add('hidden');
  document.querySelectorAll('#nav-tree .tnode[data-nav]').forEach(n => n.classList.remove('on'));
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

// Rail order for the Schedule Health Review checks. The diagnostic checks come
// first (the user reviews the individual schedule issues), and Summary sits at
// the very END as the executive roll-up / conclusion. Out of Sequence and Lag
// Report are separate top-level features, not tabs here.
const SHR_RAIL_ORDER = ['dangling', 'open_ends', 'leads', 'negative_float',
  'relationship_types', 'whole_day', 'hard_constraints', 'high_duration',
  'cpli', 'float', 'circular'];
const SUMMARY_KEY = '__summary__';

// The tab score shows the module's own score; CPLI can be "not computed" (null).
export function tabScore(m) {
  return (m.score === null || m.score === undefined) ? '—' : m.score;
}

// Render the Schedule Health Review: a Summary dashboard + one tab per check.
export function renderAudit(auditModules) {
  state.currentModules = auditModules || null;
  const body = document.getElementById('audit-body');
  const tabs = document.getElementById('module-tabs');
  // Always rebuild a fresh #module-body so repeated renders never hit a
  // container that a prior "no audit" render replaced.
  body.innerHTML = '<div id="module-body"></div>';
  const present = ((auditModules && auditModules.module_order) || [])
    .filter(k => k !== 'out_of_sequence' && k !== 'lag_lead');
  if (!present.length) {
    tabs.innerHTML = '';
    document.getElementById('module-body').innerHTML =
      '<p style="color:var(--muted);font-size:13px">No Schedule Health Review available for this schedule.</p>';
    return;
  }
  // Locked order first, then anything unexpected appended so nothing is dropped.
  const order = SHR_RAIL_ORDER.filter(k => present.includes(k))
    .concat(present.filter(k => !SHR_RAIL_ORDER.includes(k)));

  // Gate B — nothing in the review shows until the contract milestones are entered.
  const mcGate = auditModules.modules.hard_constraints;
  if (mcGate && mcGate.needs_input) {
    tabs.innerHTML = '';
    return renderMilestoneGate(auditModules);
  }

  const health = (auditModules && auditModules.health) || null;
  // Summary is the executive roll-up — placed LAST, after the diagnostic checks.
  const summaryTab = health
    ? `<button class="module-tab mt-summary" data-module="${SUMMARY_KEY}">
         <span class="mt-dot ${scoreColor(health.score ?? 0)}"></span>Summary
         <span class="mt-score">${health.score ?? '—'}</span></button>`
    : '';
  tabs.innerHTML = order.map(key => {
    const m = auditModules.modules[key];
    // Float shows its DCMA Float Health score + colour (no word-grade); others keep the grade dot.
    if (key === 'float' && m.mgmt) {
      const hasData = ((m.mgmt.stats || {}).total || 0) > 0;
      const dot = hasData ? `class="mt-dot ${scoreColor(m.mgmt.float_health)}"` : 'class="mt-dot" style="background:var(--muted)"';
      return `<button class="module-tab" data-module="float">
        <span ${dot}></span>${escapeHtml(m.name)}
        <span class="mt-score">${hasData ? m.mgmt.float_health : '—'}</span></button>`;
    }
    return `<button class="module-tab" data-module="${escapeHtml(key)}">
      <span class="mt-dot ${gradeClass(m.grade)}"></span>${escapeHtml(m.name)}
      <span class="mt-score">${tabScore(m)}</span></button>`;
  }).join('') + summaryTab;
  tabs.querySelectorAll('.module-tab').forEach(btn =>
    btn.addEventListener('click', () => selectModule(btn.dataset.module)));
  // Land on the first diagnostic check; the user reaches Summary at the end.
  selectModule(order[0]);
}

export function selectModule(key) {
  const am = state.currentModules;
  if (!am) return;
  document.querySelectorAll('.module-tab').forEach(b =>
    b.classList.toggle('active', b.dataset.module === key));
  _filters = { severity: '', check: '', wbs: '', query: '', area: '' };
  if (key === SUMMARY_KEY) {
    state.currentModule = SUMMARY_KEY;
    return renderSummary(am.health || null, am);
  }
  if (!am.modules[key]) return;
  state.currentModule = key;
  renderModuleBody(am.modules[key]);
}

// ── Small formatting + table-cell helpers (shared by every check view) ────
const num = v => (Number(v) || 0).toLocaleString();
const pctv = v => `${v ?? 0}%`;
const dnum = v => (v === null || v === undefined) ? '—' : `${v} d`;
const isoDate = v => v ? String(v).slice(0, 10) : '—';
const MON3 = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmtDate = v => {                       // ISO or already-nice → 9-Feb-2027
  if (!v) return '—';
  const p = String(v).slice(0, 10).split('-');
  return (p.length === 3 && +p[1]) ? `${+p[2]}-${MON3[+p[1]]}-${p[0]}` : String(v);
};
const td = v => `<td>${escapeHtml(v ?? '')}</td>`;
const tdNum = v => `<td class="num">${escapeHtml(String(v ?? ''))}</td>`;
const tdMono = v => `<td class="mono">${escapeHtml(v ?? '')}</td>`;
const tdMut = v => `<td class="mut">${escapeHtml(v ?? '')}</td>`;
const tdWbs = p => `<td title="${escapeHtml(p ?? '')}">${escapeHtml(shortWbs(p))}</td>`;
const tdSev = s => `<td><span class="sevtag ${severityClass(s)}">${escapeHtml(s ?? '')}</span></td>`;

// Pass / Review / Critical → colour + dot class (the roll-up's status semantics).
export function statusColor(status) {
  return { Pass: 'var(--success)', Review: 'var(--warning)', Critical: 'var(--danger)' }[status] || 'var(--muted)';
}
export function statusDot(status) {
  return { Pass: 'd-g', Review: 'd-a', Critical: 'd-c' }[status] || 'd-n';
}
export function verdictClass(verdict) {
  if (verdict === 'Ready to submit') return 'v-good';
  if (verdict === 'Acceptable to submit') return 'v-warn';   // 80–90: meets the standard
  return 'v-bad';   // Not ready / Blocked / Not computed
}

// The reusable gauge (120px ring + centred score). `score` may be null.
function gaugeHtml(score, label = '/ 100') {
  const C = 326.7;
  const shown = (score === null || score === undefined) ? '—' : score;
  return `<div class="gauge">
      <svg width="120" height="120" viewBox="0 0 120 120">
        <circle cx="60" cy="60" r="52" fill="none" stroke="var(--border)" stroke-width="12"/>
        <circle cx="60" cy="60" r="52" fill="none" stroke-width="12" stroke-linecap="round"
                stroke-dasharray="${C}" stroke-dashoffset="${gaugeDashoffset(score || 0, C)}"
                transform="rotate(-90 60 60)" class="gauge-arc ${scoreColor(score || 0)}"/>
      </svg>
      <div class="gauge-num"><b>${shown}</b><span>${escapeHtml(label)}</span></div>
    </div>`;
}

// Render one normalized presentation cell — mirrors report.py _pcell so the
// screen, the PDF and Excel draw identical cells from the one source.
function cellHtml(cell) {
  if (cell.badge) return `<td><span class="sevtag ${cell.badge}">${escapeHtml(cell.text)}</span></td>`;
  const cls = cell.cls ? ` class="${cell.cls}"` : '';
  const title = cell.title ? ` title="${escapeHtml(cell.title)}"` : '';
  return `<td${cls}${title}>${escapeHtml(cell.text)}</td>`;
}

function presentationTiles(p) {
  return (p.tiles || []).map(t =>
    `<div class="kpi"><div class="k">${escapeHtml(t.label)}</div><div class="v">${escapeHtml(t.value)}</div></div>`).join('');
}

// "How this score is calculated" — the transparent scoring legend every check
// shows (formula + this schedule's derivation + bands + the DCMA benchmark, which
// is deliberately kept separate from the 0-100 score).
function scoringLegendHtml(s) {
  if (!s) return '';
  const parts = [
    `<div class="sl-t">How this score is calculated</div>`,
    `<div class="sl-r"><b>Formula:</b> ${escapeHtml(s.formula)}</div>`,
    `<div class="sl-r"><b>This schedule:</b> ${escapeHtml(s.derivation)}</div>`,
  ];
  if (s.bands) parts.push(`<div class="sl-r"><b>Score bands:</b> ${escapeHtml(s.bands)}</div>`);
  if (s.benchmark) parts.push(`<div class="sl-r sl-bench"><b>Benchmark:</b> ${escapeHtml(s.benchmark)}</div>`);
  return `<div class="shr-legend score-legend">${parts.join('')}</div>`;
}

// "What the severity levels mean" — the criteria straight from the rule engine, so
// the user knows why a finding is Critical/High/Medium/Low (not just its colour).
function severityLegendHtml(sev) {
  if (!sev || !(sev.levels || []).length) return '';
  const rows = sev.levels.map(l =>
    `<div class="sl2-row"><span class="sevtag ${severityClass(l.level)}">${escapeHtml(l.level)}</span>` +
    `<span>${escapeHtml(l.criteria)}</span></div>`).join('');
  const basis = sev.basis ? `<div class="sl-r sl-bench">${escapeHtml(sev.basis)}</div>` : '';
  return `<div class="shr-legend sev-legend"><div class="sl-t">What the severity levels mean</div>` +
    `<div class="sl2">${rows}</div>${basis}</div>`;
}

// Per-check KPI tiles + table columns now live in ONE place — p6_audit/presentation.py
// (build_presentation) — and arrive on each module as `m.presentation`, so the screen,
// the PDF and Excel render identical tiles/columns/cells (see cellHtml/presentationTiles).

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

// ── Out of Sequence — Consultant Review Report (dashboard view) ───────────

export function oosPillClass(kind) {
  if (kind === 'same' || kind === 'na') return kind;
  return kind === 'remove' ? 'remove' : 'change';
}

function oosSug(text, kind) {
  return `<span class="oos-pill ${oosPillClass(kind)}">${escapeHtml(text || '')}</span>`;
}

export function oosCritLabel(c) {
  return c === 'Critical' ? 'Critical' : c === 'Near-Critical' ? 'Near-Critical' : '—';
}

function oosCrit(c) {
  if (c === 'Critical') return '<span class="oos-badge crit">Critical</span>';
  if (c === 'Near-Critical') return '<span class="oos-badge near">Near-Critical</span>';
  return '<span style="color:var(--muted)">—</span>';
}

function oosKpiTiles(k) {
  const tiles = [
    ['Total Activities', (k.total_activities || 0).toLocaleString(), '', ''],
    ['Out-of-Sequence Activities', k.oos_count || 0, '', ''],
    ['Out-of-Sequence %', `${k.oos_pct ?? 0}%`, '', 'of all activities'],
    ['Critical OOS', k.critical_oos || 0, 'crit', ''],
    ['Critical OOS %', `${k.critical_oos_pct ?? 0}%`, 'crit', 'of all activities'],
    ['Near-Critical OOS', k.near_critical_oos || 0, 'near', ''],
    ['Near-Critical OOS %', `${k.near_critical_oos_pct ?? 0}%`, 'near', 'of all activities'],
  ];
  return tiles.map(([lab, val, cls, note]) =>
    `<div class="kpi oos-tile ${cls}"><div class="k">${escapeHtml(lab)}</div><div class="v">${escapeHtml(String(val))}</div>${note ? `<div class="n">${escapeHtml(note)}</div>` : ''}</div>`).join('');
}

export function renderOutOfSequence(m) {
  const C = 326.7;
  const k = m.kpis || {};
  const dist = m.wbs_summary || [];
  const findings = m.findings || [];
  const cpi = k.critical_path_impact || 'No';
  const cdi = k.completion_date_impact || 'No Impact';
  const cpiCls = cpi === 'Yes' ? 'v-bad' : 'v-good';
  const cdiCls = cdi === 'Direct Impact' ? 'v-bad' : (cdi === 'Potential Impact' ? 'v-warn' : 'v-good');

  const cutoff = escapeHtml(k.data_date || '');

  const distRows = dist.map(r => `
    <tr><td>${escapeHtml(r.wbs)}</td>
      <td class="num">${r.activities}</td><td class="num">${r.oos}</td>
      <td class="num">${r.pct}%</td><td class="num">${r.critical_oos || 0}</td>
      <td class="num">${r.near_critical_oos || 0}</td></tr>`).join('');

  const logRows = findings.map((f, i) => `
    <tr><td class="num">${i + 1}</td><td class="mono">${escapeHtml(f.activity_id)}</td>
      <td>${escapeHtml(f.activity_name)}</td>
      <td title="${escapeHtml(f.wbs_path)}">${escapeHtml(shortWbs(f.wbs_path))}</td>
      <td>${escapeHtml(f.current_pred_rel)}</td>
      <td class="mut">${escapeHtml(f.current_pred_activity)}</td>
      <td>${escapeHtml(f.current_succ_rel)}</td>
      <td class="mut">${escapeHtml(f.current_succ_activity)}</td>
      <td class="mut">${cutoff}</td>
      <td>${oosSug(f.suggested_predecessor, f.suggested_predecessor_kind)}</td>
      <td>${oosSug(f.suggested_successor, f.suggested_successor_kind)}</td>
      <td class="mut">${escapeHtml(f.root_cause)}</td>
      <td class="mut">${escapeHtml(f.planning_review_comment)}</td>
      <td>${oosCrit(f.criticality)}</td></tr>`).join('');

  const logTable = findings.length ? `
    <div class="tblwrap" style="overflow-x:auto"><table class="audit-table oos-log"><thead><tr>
      <th>#</th><th>Activity ID</th><th>Activity Name</th><th>WBS Path</th>
      <th>Current Pred. Rel.</th><th>Current Predecessor Activity</th>
      <th>Current Succ. Rel.</th><th>Current Successor Activity</th><th>Cutoff Date</th>
      <th>Suggested Predecessor</th><th>Suggested Successor</th>
      <th>Root Cause</th><th>Planning Review Comment</th><th>Criticality</th>
    </tr></thead><tbody>${logRows}</tbody></table></div>`
    : `<p style="color:var(--muted);font-size:13px">No out-of-sequence activities — schedule progress is consistent with the network logic.</p>`;

  const conclusion = k.executive_conclusion ? `
    <div class="mod-sec">Executive Conclusion</div>
    <div class="oos-concl">${escapeHtml(k.executive_conclusion)}</div>` : '';

  document.getElementById('oos-body').innerHTML = `
    <div class="mod-sec">Executive Dashboard</div>
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
          <div class="coverage">${m.pct}% of activities progressed out of logical sequence.</div>
        </div>
      </div>
      <div class="kpi-tiles oos-k4">${oosKpiTiles(k)}</div>
    </div>

    <div class="oos-legend">
      <div class="t">How the Module Score is calculated</div>
      <div class="d">Driven by the Out-of-Sequence % (fewer out-of-sequence activities → higher score),
        mapped on the approved band curve (0%→100 · 2%→90 · 5%→75 · 8%→50 · 20%→0).
        This schedule: <b>${m.pct}% → ${escapeHtml(m.grade || '')} → ${m.score} / 100</b>.</div>
      <div class="bands">
        <span><i class="dot" style="background:var(--success)"></i>Excellent ≤ 2%</span>
        <span><i class="dot" style="background:var(--chart-2)"></i>Acceptable 2–5%</span>
        <span><i class="dot" style="background:var(--warning)"></i>Needs Attention 5–8%</span>
        <span><i class="dot" style="background:var(--danger)"></i>Critical &gt; 8%</span>
      </div>
    </div>
    <div class="oos-stdref"><b>Standard Reference:</b> Based on the <b>DCMA 14-Point Schedule Assessment</b>
      framework for schedule logic quality — the same methodology as the sibling modules (Dangling Logic → Metric 3,
      Float → Metric 5). Out-of-sequence is a recognised logic-quality check within this framework, complementing the
      14 core metrics. <b>Detection basis:</b> Primavera P6 out-of-sequence progress — Retained Logic / Progress Override,
      Schedule Log (F9); best-practice per GAO Schedule Assessment Guide, Best Practice 4.</div>

    <div class="mod-sec">Distribution by WBS Category</div>
    <div class="tblwrap"><table class="audit-table"><thead><tr>
      <th>WBS Category</th><th class="num">Activities</th><th class="num">Out-of-Sequence</th>
      <th class="num">%</th><th class="num">Critical OOS</th><th class="num">Near-Critical OOS</th></tr></thead>
      <tbody>${distRows}</tbody></table></div>

    <div class="mod-sec">Out-of-Sequence Review Log</div>
    ${logTable}

    <div class="mod-sec">Critical Path Impact Assessment</div>
    <div class="oos-cpi">
      <table class="audit-table oos-cpi-tbl"><thead><tr><th>Indicator</th><th class="num">Result</th></tr></thead>
        <tbody>
          <tr><td>Total Out-of-Sequence Activities</td><td class="num">${k.oos_count || 0}</td></tr>
          <tr><td>Critical Out-of-Sequence Activities</td><td class="num">${k.critical_oos || 0}</td></tr>
          <tr><td>Near-Critical Out-of-Sequence Activities</td><td class="num">${k.near_critical_oos || 0}</td></tr>
        </tbody></table>
      <div class="oos-vcards">
        <div class="oos-vcard ${cpiCls}"><div class="l">Critical Path Impact</div><div class="v2">${escapeHtml(cpi)}</div></div>
        <div class="oos-vcard ${cdiCls}"><div class="l">Completion Date Impact</div><div class="v2">${escapeHtml(cdi)}</div></div>
      </div>
    </div>
    <div style="font-size:11px;color:var(--muted);margin-top:6px">Classification only — the module does not predict a number of delay days.</div>

    ${conclusion}`;
}

// Out of Sequence is a top-level feature (its own panel), not a Schedule Audit module tab.
export function renderOosPanel(auditModules) {
  const body = document.getElementById('oos-body');
  if (!body) return;
  const m = auditModules && auditModules.modules && auditModules.modules.out_of_sequence;
  if (!m) {
    body.innerHTML = '<p style="color:var(--muted);font-size:13px">No out-of-sequence analysis for this schedule.</p>';
    return;
  }
  renderOutOfSequence(m);
}

function renderModuleBody(m) {
  if (m.module === 'float') return renderFloatModule(m);
  if (m.module === 'circular') return renderCircularModule(m);
  if (m.module === 'cpli') return renderCpliModule(m);
  if (m.module === 'hard_constraints') return renderMilestoneCheck(m);
  if (m.module === 'whole_day') return renderWholeDay(m);
  return renderStandardModule(m);
}

// Whole-day Durations — evidence view. Each flagged activity shows the calendar and
// hours/day it sits on and WHY the duration is a decimal (calendar-driven, a part-hours
// entry, or not determinable), expanding to Finding / Evidence / Root cause / Impact /
// Recommendation — so the user sees where the decimal comes from, not just a score.
function wdCauseClass(c) {
  return { cal: 'wd-cal', entry: 'wd-entry', nd: 'wd-nd' }[c] || 'wd-nd';
}
function renderWholeDay(m) {
  const p = m.presentation || {};
  const rows = (m.findings || []).map(f => {
    const nl = (k, v) => `<div class="ms-nl"><div class="mk">${escapeHtml(k)}</div><div class="mv">${escapeHtml(v || '')}</div></div>`;
    return `<div class="wd-row">
      <div class="wd-top">
        <div class="wd-id mono">${escapeHtml(f.activity_id)}</div>
        <div class="wd-nm" title="${escapeHtml(f.activity_name)}">${escapeHtml(f.activity_name)}</div>
        <div class="wd-dur"><b>${escapeHtml(String(f.original_days))} d</b> → ${escapeHtml(String(f.rounds_to))} d</div>
        <div class="wd-cal" title="${escapeHtml(f.calendar)}">${escapeHtml(f.calendar)}${f.day_hours ? ' · ' + escapeHtml(String(f.day_hours)) + 'h' : ''}</div>
        <div class="wd-cause ${wdCauseClass(f.cause)}">${escapeHtml(f.cause_label)}</div>
        <div class="wd-chev">›</div>
      </div>
      <div class="wd-det">
        ${nl('Finding', `Duration is ${f.original_days} working days — not a whole day.`)}
        ${nl('Evidence', f.evidence)}${nl('Root cause', f.root_cause)}${nl('Impact', f.impact)}
        <div class="ms-nl"><div class="mk">Recommendation</div><div class="mv rec">${escapeHtml(f.recommendation || '')}</div></div>
      </div>
    </div>`;
  }).join('') || '<p style="color:var(--muted);font-size:13px">No decimal durations — every activity is a whole number of days.</p>';

  document.getElementById('module-body').innerHTML = `
    <div class="audit-hero">
      <div class="score-card">
        ${gaugeHtml(m.score)}
        <div class="score-meta">
          <div class="grade-badge ${gradeClass(m.grade)}">${escapeHtml(m.grade || '')}</div>
          <div class="coverage">${escapeHtml(m.name)} — Sub-feature Score</div>
          <div class="coverage">${escapeHtml(p.verdict || '')}</div>
        </div>
      </div>
      <div class="kpi-tiles">${presentationTiles(p)}</div>
    </div>
    ${scoringLegendHtml(p.scoring)}
    <div class="wd-legend2">
      <span><i class="dot wd-cal"></i>Calendar hrs/day — likely contributing</span>
      <span><i class="dot wd-entry"></i>Part-hours entry — not the calendar</span>
      <span><i class="dot wd-nd"></i>Cause not determinable</span>
    </div>
    <div class="mod-sec">Decimal durations <span class="mod-sub">— where each comes from, and why (click a row)</span></div>
    <div class="wd-rows">${rows}</div>`;
  document.querySelectorAll('#module-body .wd-top').forEach(t =>
    t.addEventListener('click', () => t.parentNode.classList.toggle('open')));
}

// Standard check view: gauge hero + KPI tiles + filterable findings table,
// driven entirely by the module's spec so every check reads the same way.
function renderStandardModule(m) {
  const p = m.presentation || {};
  const body = document.getElementById('module-body');
  body.innerHTML = `
    <div class="audit-hero">
      <div class="score-card">
        ${gaugeHtml(m.score)}
        <div class="score-meta">
          <div class="grade-badge ${gradeClass(m.grade)}">${escapeHtml(m.grade || '')}</div>
          <div class="coverage">${escapeHtml(m.name)} — Sub-feature Score</div>
          <div class="coverage">${escapeHtml(p.verdict || '')}</div>
        </div>
      </div>
      <div class="kpi-tiles">${presentationTiles(p)}</div>
    </div>
    ${scoringLegendHtml(p.scoring)}
    ${wbsSummaryHtml(m)}
    <div class="mod-sec">Detailed Findings</div>
    ${(m.findings && m.findings.length) ? severityLegendHtml(p.severity) : ''}
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

// Circular Logic — the F9 gate. Loops block P6's calculation, so this reads as a
// gate banner (clear / blocking) with each loop's closing chain, not a table.
function renderCircularModule(m) {
  const k = m.kpis || {};
  const clear = (k.loops || 0) === 0;
  const banner = clear
    ? `<div class="shr-banner ok"><b>F9 clear — no circular logic.</b> P6 can calculate this schedule.</div>`
    : `<div class="shr-banner bad"><b>Blocking — a circular loop stops P6 from calculating (F9).</b> Break one link in each loop below, then re-run.</div>`;
  const tiles = [['Total Activities', num(k.total_activities)], ['Loops', k.loops || 0],
    ['Activities in Loops', k.activities_in_loops || 0], ['Longest Loop', k.longest_loop || 0], ['Circular %', pctv(k.circular_pct)]];
  const loopsHtml = (m.findings || []).map(f => {
    const chain = (f.chain || []).map((n, i) =>
      `${i ? '<span class="shr-arrow">→</span>' : ''}<span class="shr-node" title="${escapeHtml(n.name)}">${escapeHtml(n.id)}</span>`).join('');
    return `<div class="shr-loop">
      <div class="shr-loop-h">Loop ${f.loop_index} <span>· ${f.activity_count} activities</span></div>
      <div class="shr-chain">${chain}</div>
      <div class="shr-loop-rec">${escapeHtml(f.recommendation || '')}</div></div>`;
  }).join('');

  document.getElementById('module-body').innerHTML = `
    <div class="audit-hero">
      <div class="score-card">
        ${gaugeHtml(m.score)}
        <div class="score-meta">
          <div class="grade-badge ${gradeClass(m.grade)}">${escapeHtml(m.grade || '')}</div>
          <div class="coverage">${escapeHtml(m.name)} — F9 Gate</div>
          <div class="coverage">${clear ? 'No loops — the network calculates.' : `${k.loops} loop${k.loops === 1 ? '' : 's'} block F9.`}</div>
        </div>
      </div>
      <div class="kpi-tiles">${tiles.map(([lab, val]) => `<div class="kpi"><div class="k">${escapeHtml(lab)}</div><div class="v">${escapeHtml(String(val))}</div></div>`).join('')}</div>
    </div>
    ${banner}
    ${clear ? '' : `<div class="mod-sec">Loops to break</div><div class="shr-loops">${loopsHtml}</div>`}`;
}

// Critical Path / CPLI — DCMA Point 13. Gauge = CPLI %, a baseline-rule badge,
// and the driving path shown as a compact timeline + table. May be "not computed".
function renderCpliModule(m) {
  const k = m.kpis || {};
  const computable = k.computable !== false && k.critical_pct != null;   // density computable
  const ratioComputable = k.cpli != null;                                // CPLI ratio (context)
  const ratioPct = ratioComputable ? (k.cpli_pct != null ? k.cpli_pct : Math.round(k.cpli * 100)) : null;
  const ruleBadge = k.baseline_rule_met
    ? `<span class="shr-rule ok">Baseline rule met — total float ≥ 0</span>`
    : `<span class="shr-rule bad">Negative float — re-plan (baseline must be ≥ 0)</span>`;
  const fmTile = k.finish_date ? fmtDate(k.finish_date) : (k.finish_milestone_id || '—');
  const tiles = [
    ['Critical %', k.critical_pct == null ? '—' : `${k.critical_pct}%`],
    ['Critical Activities', k.critical_count == null ? '—' : Number(k.critical_count).toLocaleString()],
    ['CPLI', ratioComputable ? `${ratioPct}%` : '—'],
    ['Completion Total Float', dnum(k.project_total_float_days)],
    ['Critical Path Length', k.critical_path_length_days == null ? '—' : `${k.critical_path_length_days} d${k.cpl_basis === 'calendar' ? ' (cal)' : ''}`],
    ['Finish Milestone', fmTile],
  ];
  const verdict = computable
    ? `${k.critical_pct}% of activities are on the critical path → score ${m.score}. Fewer critical activities = a less fragile schedule.`
    : 'Critical-path density not computable — no task-dependent activities to assess.';

  document.getElementById('module-body').innerHTML = `
    <div class="audit-hero">
      <div class="score-card">
        ${gaugeHtml(m.score, computable ? '/ 100' : 'n/a')}
        <div class="score-meta">
          <div class="grade-badge ${gradeClass(m.grade)}">${escapeHtml(computable ? (m.grade || '') : 'Not computed')}</div>
          <div class="coverage">${escapeHtml(m.name)} — Sub-feature Score</div>
          <div class="coverage">${escapeHtml(verdict)}</div>
          ${ratioComputable ? `<div style="margin-top:8px">${ruleBadge}</div>` : ''}
        </div>
      </div>
      <div class="kpi-tiles">${tiles.map(([lab, val]) => `<div class="kpi"><div class="k">${escapeHtml(lab)}</div><div class="v">${escapeHtml(String(val))}</div></div>`).join('')}</div>
    </div>
    <div class="shr-legend">
      <b>How it's scored.</b> The score is the <b>critical-path density</b> — the share of task-dependent activities on the critical path. A schedule with many critical activities is fragile (small slips ripple), so fewer critical = a higher score.
      <div style="margin-top:5px">Band: ≤ 25% → 100 · ≤ 30% → 90 · ≤ 35% → 85 · ≤ 40% → 75 · &gt; 40% → 60.</div>
      <div style="margin-top:5px">Grade of the score: 100 = Excellent · 90 = Acceptable · below 90 (85 / 75 / 60) = Critical.</div>
    </div>
    <div class="shr-legend">
      <b>Context — CPLI ratio &amp; baseline rule (not the score).</b> CPLI = (CPL + TF) ÷ CPL = <b>${ratioComputable ? `${ratioPct}%` : '—'}</b> — DCMA 14-Point, Point 13 (target ≥ 95%). Completion total float = <b>${dnum(k.project_total_float_days)}</b>.
    </div>
    <div class="mod-sec">Driving path <span class="mod-sub">— the activities P6 flags critical, in sequence</span></div>
    ${cpliGantt(m.findings || [], m.kpis || {})}`;
}

// Driving-path Gantt: one row per critical activity — Activity ID · Name · Start ·
// Finish · Duration and a time-based bar on a shared month axis. Red = critical
// (the driving path); blue = near-critical (carries float). Every activity is
// reachable — the body scrolls, nothing is hidden behind a "+N more" (works at
// 1,500+). Replaces the old timeline AND the separate table (one view now).
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function cpliGantt(findings, kpis) {
  const dated = (findings || []).filter(f => f.start && f.finish);
  if (!dated.length) {
    return '<p style="color:var(--muted);font-size:13px">No dated critical activities to plot.</p>';
  }
  const t = d => new Date(d + 'T00:00:00').getTime();
  const lo = Math.min(...dated.map(f => t(f.start)));
  const hi = Math.max(...dated.map(f => t(f.finish)));
  const span = Math.max(1, hi - lo);
  const posOf = ms => Math.max(0, Math.min(100, 100 * (ms - lo) / span));
  const totalMonths = Math.max(1, Math.round((hi - lo) / (86400000 * 30.44)));
  const monthPct = 100 / totalMonths;                      // gridline + label spacing
  const step = Math.max(1, Math.ceil(totalMonths / 11));   // ~11 labels max

  const ticks = [];
  const first = new Date(lo);
  for (let mk = new Date(first.getFullYear(), first.getMonth(), 1); mk.getTime() <= hi; mk.setMonth(mk.getMonth() + step)) {
    const p = 100 * (mk.getTime() - lo) / span;
    if (p >= -1 && p <= 101) {
      ticks.push(`<span class="cg-m" style="left:${Math.max(0, Math.min(100, p))}%">${MONTHS[mk.getMonth()]} ${String(mk.getFullYear()).slice(2)}</span>`);
    }
  }
  // Data-date (amber) + finish (green) markers, as agreed.
  const ddIso = (kpis || {}).data_date;
  const ddPos = ddIso ? posOf(t(ddIso)) : 0;
  const markers = `<span class="cg-mk dd" style="left:${ddPos}%" title="Data date"></span>` +
                  `<span class="cg-mk fn" style="left:100%" title="Completion"></span>`;

  const rows = dated.map(f => {
    const x = posOf(t(f.start));
    const w = Math.max(0.5, 100 * (t(f.finish) - t(f.start)) / span);
    const crit = (f.total_float_days ?? 0) <= 0;    // red = critical; blue = near-critical (has float)
    const isMs = f.is_milestone === true;   // only genuine P6 milestones get a diamond, never a short Task
    const dur = f.duration_days == null ? '—' : `${f.duration_days} wd`;
    const bar = isMs
      ? `<span class="cg-ms" style="left:${x}%"></span>`
      : `<i class="${crit ? 'crit' : ''}" style="left:${x}%;width:${Math.min(w, 100 - x)}%"></i>`;
    return `<div class="cg-row" data-q="${escapeHtml((f.activity_id + ' ' + (f.activity_name || '')).toLowerCase())}">
      <div class="cg-c cg-id">${escapeHtml(f.activity_id)}</div>
      <div class="cg-c cg-nm" title="${escapeHtml(f.activity_name)}">${escapeHtml(f.activity_name)}</div>
      <div class="cg-c cg-dt">${escapeHtml(isoDate(f.start))}</div>
      <div class="cg-c cg-dt">${escapeHtml(isoDate(f.finish))}</div>
      <div class="cg-c cg-du">${escapeHtml(dur)}</div>
      <div class="cg-track">${bar}</div>
    </div>`;
  }).join('');

  // Search wiring runs after this HTML is placed into #module-body.
  setTimeout(() => {
    const s = document.getElementById('cg-search');
    if (!s) return;
    s.addEventListener('input', e => {
      const q = e.target.value.trim().toLowerCase();
      let shown = 0;
      document.querySelectorAll('#cg-body .cg-row').forEach(r => {
        const hit = !q || (r.dataset.q || '').includes(q);
        r.style.display = hit ? '' : 'none';
        if (hit) shown++;
      });
      const cnt = document.getElementById('cg-cnt');
      if (cnt) cnt.textContent = q ? `${shown.toLocaleString()} of ${dated.length.toLocaleString()} shown`
                                   : `${dated.length.toLocaleString()} critical activities · all shown (scroll)`;
    });
  }, 0);

  return `
    <div class="cg-tools">
      <input class="cg-search" id="cg-search" placeholder="🔍  Search activity ID or name…">
      <span class="cg-cnt" id="cg-cnt">${dated.length.toLocaleString()} critical activities · all shown (scroll)</span>
      <span class="cg-leg"><i class="sw r"></i>Critical <i class="sw b"></i>Near-critical <i class="sw dd"></i>Data date <i class="sw fn"></i>Finish</span>
    </div>
    <div class="cg-wrap" style="--m:${monthPct}%">
      <div class="cg-axis"><div class="cg-c">ID</div><div class="cg-c">Activity</div><div class="cg-c">Start</div>
        <div class="cg-c">Finish</div><div class="cg-c cg-du">Dur</div>
        <div class="cg-axtrack">${ticks.join('')}${markers}</div></div>
      <div class="cg-body" id="cg-body">${rows}</div>
    </div>`;
}

// ── Milestone Check (gate B) — contract milestones vs the baseline ─────────
function msDatalist(baseline) {
  return `<datalist id="ms-baseline">${(baseline || []).map(b =>
    `<option value="${escapeHtml(b.name)}">${escapeHtml(b.activity_id)}${b.finish ? ' · ' + escapeHtml(b.finish) : ''}</option>`).join('')}</datalist>`;
}
function msRowHtml(name = '', date = '') {
  return `<div class="ms-row">
    <input class="ms-name" list="ms-baseline" placeholder="Contract milestone (e.g. Mechanical Completion)" value="${escapeHtml(name)}">
    <input class="ms-date" type="date" value="${escapeHtml(date)}">
    <button class="ms-del" title="Remove">✕</button>
  </div>`;
}

// The gate screen shown before ANY check results (gate B). Pre-filled from the saved
// contract milestones when re-opening a project.
function renderMilestoneGate(am) {
  const mc = am.modules.hard_constraints || {};
  const baseline = mc.baseline_milestones || [];
  const saved = mc.contract_milestones || [];
  const body = document.getElementById('audit-body');
  body.innerHTML = `
    <div class="ms-gate">
      <div class="ms-gate-h">Step 1 · Enter your contract milestones</div>
      <div class="ms-gate-sub">The Schedule Health Review runs after you enter the project completion milestone (and any other contractual milestones). Each is matched to a real activity in this baseline — <b>${baseline.length}</b> milestone activit${baseline.length === 1 ? 'y' : 'ies'} found in the file (start typing to pick one).</div>
      ${msDatalist(baseline)}
      <div id="ms-rows"></div>
      <div class="ms-gate-actions">
        <button class="btn-secondary" id="ms-add">+ Add milestone</button>
        <button class="btn-primary" id="ms-run">Run Schedule Health Review ▸</button>
      </div>
      <div class="ms-gate-hint" id="ms-hint">Nothing is assessed until a milestone is matched — the tool never invents one.</div>
    </div>`;
  const rows = document.getElementById('ms-rows');
  const add = (n = '', d = '') => rows.insertAdjacentHTML('beforeend', msRowHtml(n, d));
  if (saved.length) saved.forEach(s => add(s.name, s.date)); else add();
  rows.addEventListener('click', e => {
    if (!e.target.classList.contains('ms-del')) return;
    const r = e.target.closest('.ms-row');
    if (rows.children.length > 1) r.remove();
    else { r.querySelector('.ms-name').value = ''; r.querySelector('.ms-date').value = ''; }
  });
  document.getElementById('ms-add').addEventListener('click', () => add());
  document.getElementById('ms-run').addEventListener('click', () => submitMilestones(am));
}

function collectMilestones() {
  return [...document.querySelectorAll('#ms-rows .ms-row')].map(r => ({
    name: r.querySelector('.ms-name').value.trim(),
    date: r.querySelector('.ms-date').value.trim(),
  })).filter(m => m.name && m.date);
}

async function submitMilestones(am) {
  const milestones = collectMilestones();
  const hint = document.getElementById('ms-hint');
  if (!milestones.length) { hint.textContent = 'Enter at least one milestone name and its contract date.'; return; }
  const runBtn = document.getElementById('ms-run');
  runBtn.disabled = true; runBtn.textContent = 'Evaluating…';
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/milestones/save`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot_id: state.currentSnapshotId, milestones }),
    }).then(r => r.json());
    if (resp.ok && resp.milestone_module) {
      am.modules.hard_constraints = resp.milestone_module;   // now carries the evals; needs_input=false
      if (resp.health) am.health = resp.health;              // keep the roll-up (donut/counts) in sync
      renderAudit(am);                                        // un-gated
      selectModule('hard_constraints');                      // land on the Milestone Check
    } else {
      hint.textContent = resp.error || 'Could not evaluate the milestones — please retry.';
      runBtn.disabled = false; runBtn.textContent = 'Run Schedule Health Review ▸';
    }
  } catch (e) {
    hint.textContent = 'Server error — please retry.';
    runBtn.disabled = false; runBtn.textContent = 'Run Schedule Health Review ▸';
  }
}

function msStatusClass(s) {
  return { 'Masked': 'st-mask', 'Late': 'st-late', 'On track': 'st-ok', 'Unmatched': 'st-un' }[s] || 'st-un';
}
function msCard(e) {
  const variance = e.variance_days == null ? '—'
    : (e.variance_days > 0 ? `+${e.variance_days} wd late` : `${Math.abs(e.variance_days)} wd on/early`);
  const facts = [
    ['Contract date', e.contract_date || '—'],
    ['Matched activity', e.matched_activity_id ? `${e.matched_activity_id} · ${e.matched_activity_name || ''}` : '— none —'],
    ['Scheduled finish', e.scheduled_finish || '—'],
    ['Variance', variance],
    ['Total float', dnum(e.total_float_days)],
    ['On driving path', e.on_driving_path == null ? '—' : (e.on_driving_path ? 'Yes' : 'No')],
  ].map(([k, v]) => `<div class="ms-fact"><div class="k">${escapeHtml(k)}</div><div class="v">${escapeHtml(String(v))}</div></div>`).join('');
  const nl = (k, v) => `<div class="ms-nl"><div class="mk">${escapeHtml(k)}</div><div class="mv">${escapeHtml(v || '')}</div></div>`;
  return `<div class="ms-card">
    <div class="ms-ct"><div class="ms-cn">${escapeHtml(e.contract_name)}</div><div class="ms-st ${msStatusClass(e.status)}">${escapeHtml(e.status)}</div></div>
    <div class="ms-facts">${facts}</div>
    <div class="ms-narr">${nl('Finding', e.finding)}${nl('Evidence', e.evidence)}${nl('Root cause', e.root_cause)}${nl('Impact', e.impact)}${nl('Recommendation', e.recommendation)}</div>
  </div>`;
}

// Hard-constraint findings (the merge) — rendered directly from the module findings.
function hardConstraintsTable(m) {
  const findings = m.findings || [];
  if (!findings.length) return '<p style="color:var(--muted);font-size:13px">No hard constraints in this baseline.</p>';
  const rows = findings.map((f, i) =>
    `<tr>${tdNum(i + 1)}${tdMono(f.activity_id)}${td(f.activity_name)}${tdWbs(f.wbs_path)}${td(f.constraint_type)}${tdMut(isoDate(f.constraint_date))}${tdSev(f.severity)}${tdMut(f.recommendation)}</tr>`).join('');
  return `<div class="tblwrap" style="overflow-x:auto"><table class="audit-table"><thead><tr>
    <th>#</th><th>Activity ID</th><th>Activity Name</th><th>WBS Path</th><th>Constraint Type</th><th>Constraint Date</th><th>Severity</th><th>Recommendation</th>
    </tr></thead><tbody>${rows}</tbody></table></div>`;
}

// The Milestone Check detail view: contract-milestone verdict cards (evidence-first)
// then the hard-constraint findings underneath.
function renderMilestoneCheck(m) {
  const p = m.presentation || {};
  const evals = m.milestones || [];
  const counts = m.milestone_counts || {};
  const cards = evals.map(msCard).join('')
    || '<p style="color:var(--muted);font-size:13px">No contract milestones entered yet — use “Edit contract milestones”.</p>';
  document.getElementById('module-body').innerHTML = `
    <div class="audit-hero">
      <div class="score-card">
        ${gaugeHtml(m.score)}
        <div class="score-meta">
          <div class="grade-badge ${gradeClass(m.grade)}">${escapeHtml(m.grade || '')}</div>
          <div class="coverage">${escapeHtml(m.name)} — Sub-feature Score</div>
          <div class="coverage">${['Masked', 'Late', 'On track', 'Unmatched'].filter(s => counts[s]).map(s => `${counts[s]} ${s.toLowerCase()}`).join(' · ') || 'No milestones matched'}</div>
          <div style="margin-top:8px"><button class="btn-secondary" id="ms-edit">Edit contract milestones</button></div>
        </div>
      </div>
      <div class="kpi-tiles">${presentationTiles(p)}</div>
    </div>
    <div class="mod-sec">Contract milestones <span class="mod-sub">— entered by you, matched to the baseline</span></div>
    <div class="ms-cards">${cards}</div>
    ${scoringLegendHtml(p.scoring)}`;
  const eb = document.getElementById('ms-edit');
  if (eb) eb.addEventListener('click', () => renderMilestoneGate(state.currentModules));
}

// The Summary dashboard — the weighted Schedule Health roll-up, rendered from the
// `health` payload (score, verdict, checks-status, composition, problem areas, fixes).
function renderSummary(health, am) {
  const body = document.getElementById('module-body');
  if (!health) {
    body.innerHTML = '<p style="color:var(--muted);font-size:13px">No Summary available for this schedule.</p>';
    return;
  }
  const score = health.score, grade = health.grade || '', verdict = health.verdict || '', statement = health.statement || '';
  const counts = health.counts || {};
  const subs = health.sub_features || [];
  const gate = health.gate || {};
  const gateClear = !gate.blocking;
  const total = health.total_count || subs.length || 1;
  const p = counts.Pass || 0, r = counts.Review || 0, c = counts.Critical || 0, n = counts['Not computed'] || 0;
  const a1 = 100 * p / total, a2 = a1 + 100 * r / total, a3 = a2 + 100 * c / total;
  const donutGrad = `conic-gradient(var(--success) 0 ${a1}%, var(--warning) ${a1}% ${a2}%, var(--danger) ${a2}% ${a3}%, var(--muted) ${a3}% 100%)`;
  const cpliK = (am && am.modules && am.modules.cpli && am.modules.cpli.kpis) || {};
  const compFloat = cpliK.project_total_float_days;

  const tone = s => (s == null ? '' : s >= 85 ? 'shr-green' : s >= 60 ? 'shr-amber' : 'shr-red');

  const compRows = subs.map(s => {
    const barW = s.score == null ? 0 : Math.max(0, Math.min(100, s.score));
    const etag = (s.modules || []).some(k => k === 'dangling' || k === 'float') ? '<span class="shr-etag">existing</span>' : '';
    const prov = s.provisional ? '<span class="shr-prov">provisional</span>' : '';
    // Highlight the sub-features the user must review (below the 80% standard).
    const needsReview = s.status === 'Review' || s.status === 'Critical';
    const reviewTag = needsReview
      ? `<span class="shr-review ${s.status === 'Critical' ? 'crit' : ''}">${s.status === 'Critical' ? 'needs review' : 'review'}</span>` : '';
    return `<div class="shr-crow${needsReview ? ' needs-review' : ''}">
      <div class="shr-nm"><span class="dot ${statusDot(s.status)}"></span>${escapeHtml(s.name)} ${etag}${prov}${reviewTag}</div>
      <div class="shr-bar"><i style="width:${barW}%;background:${statusColor(s.status)}"></i></div>
      <div class="shr-sc">${s.score == null ? '—' : s.score + '%'}</div>
      <div class="shr-wt">${s.weight}</div>
      <div class="shr-pt">${s.points == null ? '—' : s.points}</div>
    </div>`;
  }).join('');
  const gateRow = `<div class="shr-crow">
      <div class="shr-nm"><span class="dot ${gateClear ? 'd-g' : 'd-c'}"></span>Circular logic <span class="shr-gate ${gateClear ? 'ok' : 'bad'}">gate · ${gateClear ? 'clear' : 'blocking'}</span></div>
      <div class="shr-bar"><i style="width:${gateClear ? 100 : 0}%;background:${gateClear ? 'var(--success)' : 'var(--danger)'}"></i></div>
      <div class="shr-sc">—</div><div class="shr-wt">—</div><div class="shr-pt">—</div>
    </div>`;

  const areas = (health.problem_areas || {}).areas || [];
  const paMax = Math.max(1, ...areas.map(a => a.pct || 0));
  const paRows = areas.slice(0, 6).map((a, i) => `
    <div class="shr-wb"><div class="l" title="${escapeHtml(a.name)}">${escapeHtml(a.name)}</div>
      <div class="shr-wbt"><i style="width:${Math.round(100 * (a.pct || 0) / paMax)}%;background:${i === 0 ? 'var(--danger)' : i < 3 ? 'var(--warning)' : 'var(--accent)'}"></i></div>
      <div class="c">${a.pct}%</div></div>`).join('') || '<div class="shr-empty">No findings to place — the logic is clean.</div>';

  const fixRows = (health.fix_first || []).map((f, i) => `
    <div class="shr-fix"><div class="rk">${i + 1}</div>
      <div><b>${escapeHtml(f.name)} ${f.score}%</b> <span class="sub">(wt ${f.weight})</span>
        <div class="sub">${escapeHtml(f.recommendation || '')}</div></div>
      <span class="shr-lift">+~${f.lift}</span></div>`).join('') || '<div class="shr-empty">Every check is at target — nothing to fix first.</div>';

  body.innerHTML = `
    <div class="shr-dash">
      <div class="shr-top">
        <div class="card shr-gaugecard">
          ${gaugeHtml(score, `/ 100 · ${grade}`)}
          <div class="shr-gmeta">
            <div class="shr-verdict ${verdictClass(verdict)}">${escapeHtml(verdict)}</div>
            <div class="shr-gl">Overall <b>Schedule Health</b> — the weighted roll-up of every sub-feature.<br>${escapeHtml(statement)}</div>
          </div>
        </div>

        <div class="card">
          <div class="shr-ct">Checks status <span class="r">${total} sub-features</span></div>
          <div class="shr-donutwrap">
            <div class="shr-donut" style="background:${donutGrad}"><div class="dh"><b>${p}</b><span>of ${total} pass</span></div></div>
            <div class="shr-dleg">
              <div class="dl"><span class="sw" style="background:var(--success)"></span>Pass <b>${p}</b></div>
              <div class="dl"><span class="sw" style="background:var(--warning)"></span>Review <b>${r}</b></div>
              <div class="dl"><span class="sw" style="background:var(--danger)"></span>Critical <b>${c}</b></div>
              ${n ? `<div class="dl"><span class="sw" style="background:var(--muted)"></span>Not computed <b>${n}</b></div>` : ''}
              <div class="dl"><span class="sw" style="background:${gateClear ? 'var(--success)' : 'var(--danger)'}"></span>Circular gate <b>${gateClear ? 'clear' : 'blocking'}</b></div>
            </div>
          </div>
          <div class="shr-bands">
            <div class="lab">How status is decided — each check's score against the per-check bands</div>
            <div class="bands"><div class="bd bd-c">Critical &lt; 90</div><div class="bd bd-r">Review 90–95</div><div class="bd bd-p">Pass ≥ 95</div></div>
            <div class="note">A check below 95 needs review; below 90 is critical. Per-check targets adjust where DCMA differs — e.g. FS ≥ 90%. The overall baseline is submit-ready at ≥ 80%.</div>
          </div>
        </div>

        <div class="card">
          <div class="shr-ct">Headline</div>
          <div class="shr-statcol">
            <div class="stat"><div class="sv ${tone(score)}">${score ?? '—'}<span>/100</span></div><div class="sk">Baseline health score</div></div>
            <div class="stat"><div class="sv ${c ? 'shr-red' : 'shr-green'}">${c}</div><div class="sk">Critical sub-features</div></div>
            <div class="stat"><div class="sv ${compFloat == null ? '' : compFloat < 0 ? 'shr-red' : 'shr-green'}">${compFloat == null ? '—' : compFloat + ' d'}</div><div class="sk">Completion total float (rule ≥ 0)</div></div>
          </div>
        </div>
      </div>

      <div class="card shr-comp">
        <div class="shr-ct">Sub-feature scores × your weights <span class="r">worst first</span></div>
        <div class="shr-chead"><span>Sub-feature</span><span>Score</span><span>Score</span><span>Wt</span><span>Pts</span></div>
        ${compRows}
        ${gateRow}
        <div class="shr-comptot"><div class="tl">Overall Schedule Health</div><div class="tw">${health.weight_covered ?? 100}</div><div class="tv ${tone(score)}">${score ?? '—'}</div></div>
      </div>

      <div class="shr-grid2">
        <div class="card">
          <div class="shr-ct">Where the problems are <span class="r">defect share by discipline</span></div>
          ${paRows}
        </div>
        <div class="card">
          <div class="shr-ct">Fix these first <span class="r">biggest lift</span></div>
          ${fixRows}
        </div>
      </div>

      <div class="card shr-concl">
        <div class="shr-ct">Conclusion</div>
        <p>${escapeHtml(statement)}</p>
      </div>
    </div>`;
}

// ── Float Analysis management dashboard (V2 redesign) ─────────────────────
function fhFmt(v) {
  const n = Number(v);
  return Number.isFinite(n) ? String(+n.toFixed(2)) : escapeHtml(String(v ?? ''));
}

function fhTile(k, v, note = '', hot = false, amber = false, noteCls = '') {
  const n = note ? `<div class="n${noteCls ? ' ' + noteCls : ''}">${escapeHtml(note)}</div>` : '';
  return `<div class="kpi${hot ? ' hot' : ''}"><div class="k">${escapeHtml(k)}</div>` +
         `<div class="v${amber ? ' amber' : ''}">${v}</div>${n}</div>`;
}

function fhDriver(label, sub, pct, maxPct, penalty, colorVar) {
  return `<div class="fh-d">
      <div class="fh-dl">${escapeHtml(label)}<span>${escapeHtml(sub)}</span></div>
      <div class="fh-bar2"><i style="width:${barPct(pct, maxPct)}%;background:${colorVar}"></i></div>
      <div class="fh-dv">${fhFmt(pct)}% <small>−${penalty}</small></div>
    </div>`;
}

function renderFloatModule(m) {
  const g = m.mgmt || {};
  const total = (g.stats || {}).total || 0;
  if (!m.mgmt || !total) {
    const msg = !m.mgmt
      ? 'This schedule was imported before the Float dashboard was added — re-import it to see the management report.'
      : 'No activities with assessable total float were found in this schedule.';
    document.getElementById('module-body').innerHTML =
      `<div class="fh-concl" style="border-left-color:var(--warning);margin-top:8px"><b>Float dashboard unavailable.</b><br>${escapeHtml(msg)}</div>`;
    return;
  }
  const stats = g.stats || {}, ind = g.indicators || {}, high = g.high || {}, neg = g.neg || {};
  const C = 326.7;
  const thr = ind.threshold ?? 44;
  const score = g.float_health ?? 0;

  const statsTiles = [
    fhTile(stats.total_label || 'Total Activities', (stats.total || 0).toLocaleString(), 'task-dependent'),
    fhTile('Critical Activities', String(stats.critical ?? 0), 'flagged Critical in P6'),
    fhTile('Critical %', `${fhFmt(stats.critical_pct ?? 0)}%`),
    fhTile('Near-Critical Activities', String(stats.near_critical ?? 0), `float 1–${stats.near_band ?? 10} working days`),
    fhTile('Near-Critical %', `${fhFmt(stats.near_critical_pct ?? 0)}%`),
  ].join('');

  const indTiles = [
    fhTile(`Construction · Float > ${thr} WD`, String(ind.constr_over ?? 0),
           `of ${(ind.constr_total || 0).toLocaleString()} construction activities`, true, true),
    fhTile(`% of Construction > ${thr} WD`, `${fhFmt(ind.constr_over_pct ?? 0)}%`,
           `threshold = ${thr} working days`, true, true),
    fhTile('Top WBS by Float Concentration', `<span class="tw">${escapeHtml(ind.top_wbs || '—')}</span>`,
           `${fhFmt(ind.top_wbs_pct ?? 0)}% of its activities > ${thr} WD`),
    fhTile('Highest Float (single activity)', `${fhFmt(ind.highest_float ?? 0)} WD`,
           ind.highest_float_wbs || '', false, false, 'wbs'),
  ].join('');

  const wbsRows = (g.wbs || []).slice(0, 40).map(r => {
    const tag = r.is_construction ? '<span class="ftag con">Constr.</span>' : '<span class="ftag non">Excl.</span>';
    return `<tr>
      <td title="${escapeHtml(r.wbs || '')}">${escapeHtml(shortWbs(r.wbs, 3))} ${tag}</td>
      <td class="num">${r.activities ?? 0}</td>
      <td class="num">${fhFmt(r.avg_float ?? 0)} WD</td>
      <td class="num">${fhFmt(r.max_float ?? 0)} WD</td>
      <td class="num">${r.over_44 ?? 0}</td>
      <td class="num">${fhFmt(r.pct ?? 0)}%</td></tr>`;
  }).join('') || `<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:18px">No activities with assessable float.</td></tr>`;

  document.getElementById('module-body').innerHTML = `
    <div class="fh-hero">
      <div class="fh-gaugecard">
        <div class="gauge">
          <svg width="120" height="120" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="52" fill="none" stroke="var(--border)" stroke-width="12"/>
            <circle cx="60" cy="60" r="52" fill="none" stroke-width="12" stroke-linecap="round"
                    stroke-dasharray="${C}" stroke-dashoffset="${gaugeDashoffset(score, C)}"
                    transform="rotate(-90 60 60)" class="gauge-arc ${scoreColor(score)}"/>
          </svg>
          <div class="gauge-num"><b>${score}</b><span>Float Health</span></div>
        </div>
        <div class="fh-drivers">
          ${fhDriver(`High Float > ${thr} WD — construction`,
                     'the score driver — 100 − this %',
                     high.pct ?? 0, 25, high.penalty ?? 0, 'var(--danger)')}
          <div class="fh-note">Score = 100 − the construction High-Float defect above.</div>
        </div>
      </div>
    </div>
    <div class="scorelegend">
      <div class="sl-title">How the Float Health score is calculated <span>— Schedule Health Review linear model</span></div>
      <div class="sl-formula">Float Health = 100 − construction excess-float defect%</div>
      <div class="sl-row"><b>Defect%</b> = construction activities with total float &gt; ${thr} WD ÷ all construction activities. Each 1% of defect costs 1 point — here ${fhFmt(high.pct ?? 0)}% → <b>${score}</b>.</div>
      <div class="sl-row sl-ref"><b>DCMA reference — not the score.</b> DCMA Metric 5 benchmark: at least ${fhFmt(high.dcma_within_pct ?? 95)}% of activities within the float threshold (high float &lt; ${fhFmt(high.dcma_max_pct ?? 5)}%). Shown for reference; it does not set the score.</div>
      <div class="sl-colours"><span><i class="g"></i>Green ≥ 85</span><span><i class="a"></i>Amber 60–84</span><span><i class="r"></i>Red &lt; 60</span></div>
    </div>
    <div class="mod-sec">Schedule Statistics <span class="mod-sub">— whole schedule</span></div>
    <div class="fh-tiles five">${statsTiles}</div>
    <div class="mod-sec">Float Indicators <span class="mod-sub">— Construction scope only (Engineering / Procurement / Design excluded)</span></div>
    <div class="fh-tiles four">${indTiles}</div>
    <div class="mod-sec">Float Distribution by WBS</div>
    <div class="tblwrap" style="overflow-x:auto"><table class="audit-table fh-wbs"><thead><tr>
      <th>WBS Package</th><th class="num">Activities</th><th class="num">Average Float</th>
      <th class="num">Maximum Float</th><th class="num">Activities &gt; ${thr} WD</th><th class="num">% &gt; ${thr} WD</th>
    </tr></thead><tbody>${wbsRows}</tbody></table></div>
    <div class="mod-sec">Executive Conclusion</div>
    <div class="fh-concl">${escapeHtml(g.conclusion || 'No conclusion available for this schedule.')}</div>`;
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
  if (!am || !key || !tbody || !am.modules[key]) return;
  const m = am.modules[key];
  const p = m.presentation || {};
  const cols = p.columns || [];
  const prows = p.rows || [];
  thead.innerHTML = `<tr><th>#</th>${cols.map(c =>
    c.align === 'num' ? `<th class="num">${escapeHtml(c.label)}</th>` : `<th>${escapeHtml(c.label)}</th>`).join('')}</tr>`;
  // Filter by the raw finding; render the PARALLEL presentation row (same index),
  // so the on-screen table shows the exact cells the PDF and Excel do.
  const sev = _filters.severity, q = (_filters.query || '').trim().toLowerCase();
  const visible = [];
  (m.findings || []).forEach((f, idx) => {
    if (sev && f.severity !== sev) return;
    if (q && !`${f.activity_id || ''} ${f.activity_name || ''}`.toLowerCase().includes(q)) return;
    if (prows[idx]) visible.push(prows[idx]);
  });
  if (!visible.length) {
    tbody.innerHTML = `<tr><td colspan="${cols.length + 1}" style="text-align:center;color:var(--muted);padding:20px">No findings match.</td></tr>`;
    return;
  }
  tbody.innerHTML = visible.map((row, i) =>
    `<tr><td class="num">${i + 1}</td>${row.map(cellHtml).join('')}</tr>`).join('');
}

// ── Lag Report — standalone report (charts + register + editable justification) ──

let _lagFilter = { query: '', flaggedOnly: false };

function lagBar(pct) {
  const w = Math.max(0, Math.min(100, Math.round(pct || 0)));
  return `<div class="lag-dbar"><i style="width:${w}%"></i></div>`;
}

function lagRelHtml(rel, isLead, isLong) {
  const cls = isLead ? 'rel-lead' : (isLong ? 'rel-long' : '');
  return `<span class="mono ${cls}">${escapeHtml(rel || '—')}</span>`;
}

function lagFlagChips(f) {
  let c = '';
  if (f.is_lead) c += '<span class="lag-chip lead">Lead</span>';
  if (f.is_long) c += '<span class="lag-chip long">Long</span>';
  if (f.criticality === 'Critical') c += '<span class="lag-chip crit">Crit</span>';
  else if (f.criticality === 'Near-Critical') c += '<span class="lag-chip near">Near</span>';
  return c;   // empty when clean — chips sit inline in the relationship cell
}

// Save one justification to the server (per project). Raw fetch keeps audit.js free of an
// api.js import cycle; a failed save is silent — the typed text stays in the in-memory copy.
async function saveLagJustification(relKey, text) {
  if (!state.currentSnapshotId) return;
  try {
    await fetch(`http://localhost:${state.serverPort}/api/lag/justification`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot_id: state.currentSnapshotId, rel_key: relKey, text }),
    });
  } catch { /* offline / server down — keep the local edit, retry on next blur */ }
}

function lagRowsFiltered(m) {
  const q = (_lagFilter.query || '').trim().toLowerCase();
  return (m.findings || []).filter(f => {
    if (_lagFilter.flaggedOnly && !(f.is_lead || f.is_long)) return false;
    if (q) {
      const hay = `${f.activity_id || ''} ${f.activity_name || ''} ${f.pred_name || ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function renderLagRows(m) {
  const tbody = document.getElementById('lag-tbody');
  if (!tbody) return;
  const rows = lagRowsFiltered(m);
  if (!rows.length) {
    const empty = !(m.findings || []).length
      ? 'No lags or leads in this schedule — every relationship drives directly.'
      : 'No lags match your search.';
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:20px">${empty}</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map((f, i) => `
    <tr>
      <td class="num">${i + 1}</td>
      <td class="mono">${escapeHtml(f.activity_id)}</td>
      <td>${escapeHtml(f.activity_name)}</td>
      <td class="lag-relcell">${lagRelHtml(f.pred_rel, f.is_lead, f.is_long)} ${lagFlagChips(f)}</td>
      <td class="mut">${escapeHtml(f.pred_name)}</td>
      <td><span class="mono">${escapeHtml(f.succ_rel || '—')}</span></td>
      <td class="mut">${escapeHtml(f.succ_name || '—')}</td>
      <td><textarea class="lag-just" data-relkey="${escapeHtml(f.rel_key)}" rows="1" placeholder="Add reason…">${escapeHtml(f.justification || '')}</textarea></td>
    </tr>`).join('');

  tbody.querySelectorAll('.lag-just').forEach(ta => {
    const relKey = ta.dataset.relkey;
    const sync = () => { const f = (m.findings || []).find(x => x.rel_key === relKey); if (f) f.justification = ta.value; };
    ta.addEventListener('input', sync);
    ta.addEventListener('change', () => { sync(); saveLagJustification(relKey, ta.value); });
  });
}

// Lag makeup donut: normal (grey) · long positive (amber) · leads (red). Centre = to-justify count.
function lagDonut(k) {
  const normal = k.normal_count || 0, longp = k.long_positive_count || 0, leads = k.leads_count || 0;
  const total = normal + longp + leads;
  const need = k.need_justification_count ?? (longp + leads);
  const thr = k.long_threshold_days || 14;
  const C = 251.33;
  let off = 0;
  const seg = (val, color) => {
    if (!val || !total) return '';
    const len = C * val / total;
    const s = `<circle cx="50" cy="50" r="40" fill="none" stroke="${color}" stroke-width="15" ` +
      `stroke-dasharray="${len.toFixed(1)} ${C}" stroke-dashoffset="${(-off).toFixed(1)}"/>`;
    off += len; return s;
  };
  return `<div class="lag-donut">
    <svg width="90" height="90" viewBox="0 0 100 100" aria-hidden="true">
      <g transform="rotate(-90 50 50)">${seg(normal, 'var(--muted)')}${seg(longp, 'var(--warning)')}${seg(leads, 'var(--danger)')}</g>
      <text x="50" y="48" text-anchor="middle" font-size="18" font-weight="800" fill="currentColor">${need}</text>
      <text x="50" y="62" text-anchor="middle" font-size="8" fill="var(--muted)">to justify</text>
    </svg>
    <div class="lag-leg">
      <div><span class="ld-dot" style="background:var(--muted)"></span>Normal &le;${thr} wd <b>${normal}</b></div>
      <div><span class="ld-dot" style="background:var(--warning)"></span>Long &gt;${thr} wd <b>${longp}</b></div>
      <div><span class="ld-dot" style="background:var(--danger)"></span>Leads <b>${leads}</b></div>
      <div><span class="ld-dot" style="background:var(--accent)"></span>On critical path <b>${k.critical_count || 0}</b></div>
    </div>
  </div>`;
}

// Lag Report — a standalone top-level report (register of all project lags + charts), not a
// Schedule Audit tab. Renders into #lag-body. No verdict/score — that's the separate scoring feature.
export function renderLagPanel(auditModules) {
  const body = document.getElementById('lag-body');
  if (!body) return;
  const m = auditModules && auditModules.modules && auditModules.modules.lag_lead;
  if (!m) {
    body.innerHTML = '<p style="color:var(--muted);font-size:13px">No lag report for this schedule.</p>';
    return;
  }
  const k = m.kpis || {};
  const byType = k.by_type || [];
  const ws = m.wbs_summary || [];
  const typeMax = Math.max(1, ...byType.map(t => t.count || 0));
  const wbsMax = Math.max(1, ...ws.map(r => r.lagged || 0));
  const thr = k.long_threshold_days || 14;
  _lagFilter = { query: '', flaggedOnly: false };

  const typeRows = byType.map(t =>
    `<div class="lag-drow"><span class="lag-dk">${escapeHtml(t.type)}</span>` +
    `${lagBar(100 * (t.count || 0) / typeMax)}<span class="lag-dv">${t.count} · ${t.pct}%</span></div>`).join('')
    || '<div style="color:var(--muted);font-size:12px">No lags to distribute.</div>';
  const wbsRows = ws.slice(0, 10).map(r =>
    `<div class="lag-wrow"><div class="lag-wname">${escapeHtml(r.wbs)}</div>` +
    `<div class="lag-wline">${lagBar(100 * (r.lagged || 0) / wbsMax)}<span class="lag-dv">${r.lagged} · ${r.pct}%</span></div></div>`).join('')
    || '<div style="color:var(--muted);font-size:12px">No lags to distribute.</div>';

  const total = k.lagged_count || 0;
  const need = k.need_justification_count ?? ((k.leads_count || 0) + (k.long_positive_count || 0));

  body.innerHTML = `
    <div class="lag-rpt-head">
      <div class="lag-rpt-title">Lag report</div>
      <div class="lag-rpt-meta"><b>${total.toLocaleString()}</b> lags across the schedule · ` +
        `<b>${need}</b> need a justification (lag over ${thr} working days, or a lead) · listed worst first</div>
    </div>

    <div class="lag-charts">
      <div class="lag-panel"><div class="lag-ph">Lags by relationship type</div>${typeRows}</div>
      <div class="lag-panel"><div class="lag-ph">Lags by WBS area</div>${wbsRows}</div>
      <div class="lag-panel"><div class="lag-ph">Lag makeup</div>${lagDonut(k)}</div>
    </div>

    <div class="lag-hint">Every relationship carrying a lag or a lead is listed. The <b class="lag-hl">highlighted</b> ones &mdash; lag over ${thr} working days, or a lead &mdash; are the ones to explain: <b>type a reason in the Justification column</b>. It saves with the project and prints into the PDF and Excel.</div>

    <div class="filters">
      <input class="searchbox" id="lag-search" placeholder="🔍  Search activity ID, name or predecessor…">
      <label class="lag-toggle"><input type="checkbox" id="lag-flagged"> Flagged only (leads &amp; long lags)</label>
    </div>
    <div class="tblwrap" style="overflow-x:auto"><table class="audit-table lag-table"><thead><tr>
      <th>#</th><th>Activity ID</th><th>Activity Name</th>
      <th>Pred. Relationship</th><th>Pred. Name</th>
      <th>Succ. Relationship</th><th>Succ. Name</th>
      <th class="lag-jcol">Justification</th>
    </tr></thead><tbody id="lag-tbody"></tbody></table></div>`;

  document.getElementById('lag-search').addEventListener('input', e => {
    _lagFilter.query = e.target.value; renderLagRows(m);
  });
  document.getElementById('lag-flagged').addEventListener('change', e => {
    _lagFilter.flaggedOnly = e.target.checked; renderLagRows(m);
  });
  renderLagRows(m);
}
