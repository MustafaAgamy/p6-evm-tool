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
  document.getElementById('copilot-panel').classList.toggle('hidden', view !== 'copilot');
  document.getElementById('tab-evm').classList.toggle('active', view === 'evm');
  document.getElementById('tab-audit').classList.toggle('active', view === 'audit');
  document.getElementById('tab-oos').classList.toggle('active', view === 'oos');
  document.getElementById('tab-calendar').classList.toggle('active', view === 'calendar');
  document.getElementById('tab-construct').classList.toggle('active', view === 'construct');
  document.getElementById('tab-copilot').classList.toggle('active', view === 'copilot');
  // Keep exactly one sidebar item highlighted: shield on the Audit view, Home otherwise.
  document.getElementById('sb-audit-btn').classList.toggle('active', view === 'audit');
  document.getElementById('sb-home-btn').classList.toggle('active', view !== 'audit');
  // Out of Sequence exports reuse the module export path with a fixed module id.
  if (view === 'oos') state.currentModule = 'out_of_sequence';
}

// Show the "EVM vs Schedule Audit" choice; hide both analysis views until picked.
export function showChooser() {
  document.getElementById('analysis-chooser').classList.remove('hidden');
  document.getElementById('analysis-views').classList.add('hidden');
  document.getElementById('sb-audit-btn').classList.remove('active');
  document.getElementById('sb-home-btn').classList.add('active');
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
  // Out of Sequence is shown as its own top-level feature, not a Schedule Audit tab.
  const order = ((auditModules && auditModules.module_order) || []).filter(k => k !== 'out_of_sequence');
  if (!order.length) {
    tabs.innerHTML = '';
    document.getElementById('module-body').innerHTML =
      '<p style="color:var(--muted);font-size:13px">No audit available for this schedule.</p>';
    return;
  }
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
      <span class="mt-score">${m.score}</span></button>`;
  }).join('');
  tabs.querySelectorAll('.module-tab').forEach(btn =>
    btn.addEventListener('click', () => selectModule(btn.dataset.module)));
  selectModule(order[0]);
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
       ['Dangling Start', k.start_dangling || 0],
       ['Dangling Finish', k.finish_dangling || 0],
       ['Dangling Start + Dangling Finish', k.both_dangling || 0]]
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
        <span><i class="dot" style="background:#2e8b57"></i>Excellent ≤ 2%</span>
        <span><i class="dot" style="background:#c9a227"></i>Acceptable 2–5%</span>
        <span><i class="dot" style="background:#e07b1a"></i>Needs Attention 5–8%</span>
        <span><i class="dot" style="background:#c0392b"></i>Critical &gt; 8%</span>
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
                     `DCMA target < ${fhFmt(high.target ?? 5)}% · penalty maxes at ${fhFmt(high.max_pct ?? 20)}%`,
                     high.pct ?? 0, high.max_pct ?? 20, high.penalty ?? 0, 'var(--danger)')}
          ${fhDriver('Negative Float — whole schedule',
                     `DCMA target ${fhFmt(neg.target ?? 0)}% · penalty maxes at ${fhFmt(neg.max_pct ?? 5)}%`,
                     neg.pct ?? 0, neg.max_pct ?? 5, neg.penalty ?? 0, 'var(--warning)')}
        </div>
      </div>
    </div>
    <div class="scorelegend">
      <div class="sl-title">How the Float Health score is calculated <span>— anchored to the DCMA 14-Point float targets</span></div>
      <div class="sl-formula">Float Health = 100 − High-Float penalty − Negative-Float penalty</div>
      <div class="sl-row"><b>High Float</b> — construction activities with total float &gt; ${thr} WD · <span class="sl-t">DCMA target &lt; ${fhFmt(high.target ?? 5)}%</span> · penalty 0 at ≤ ${fhFmt(high.target ?? 5)}%, rising to −${high.max_penalty ?? 60} at ${fhFmt(high.max_pct ?? 20)}%.</div>
      <div class="sl-row"><b>Negative Float</b> — activities with total float &lt; 0 (whole schedule) · <span class="sl-t">DCMA target ${fhFmt(neg.target ?? 0)}%</span> · penalty 0 at ${fhFmt(neg.target ?? 0)}%, rising to −${neg.max_penalty ?? 40} at ${fhFmt(neg.max_pct ?? 5)}%.</div>
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
  if (!am || !key || !tbody) return;
  const m = am.modules[key];
  const rows = filterFindings(m.findings, { severity: _filters.severity, query: _filters.query });

  const cols = m.module === 'dangling'
    ? ['#', 'Activity ID', 'Activity Name', 'WBS Path', 'Severity', 'Logic Issue', 'Predecessor(s)', 'Successor(s)', 'Suggested Logic Fix', 'Suggested Logic Fix 2']
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
        <td class="mut">${escapeHtml(f.suggested_fix_2)}</td></tr>`;
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
