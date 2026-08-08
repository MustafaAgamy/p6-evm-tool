// Calendar Audit renderer — Sections 1-9 & 11 (Slice A, offline/P6).
// Weather (Section 10) + location picker are wired in a later slice.

// ── Pure helpers (unit-tested in tests/js/test_calendar.js) ───────────────

const _MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function fmtCalDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return '—';
  return `${String(d.getUTCDate()).padStart(2, '0')} ${_MON[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function statusClass(status) {
  return { work: 'cs-work', weekend: 'cs-weekend', holiday: 'cs-holiday',
           shutdown: 'cs-shutdown', special: 'cs-special' }[status] || 'cs-work';
}

// Build a Mon-first grid: `first_weekday` leading blanks, then one cell per day.
export function monthGridCells(month) {
  const cells = [];
  const pad = ((month.first_weekday % 7) + 7) % 7;
  for (let i = 0; i < pad; i++) cells.push({ blank: true });
  for (const day of (month.days || [])) cells.push({ d: day.d, status: day.status });
  return cells;
}

export function conflictSeverityClass(sev) {
  return { High: 'cf-high', Medium: 'cf-med', Low: 'cf-low' }[sev] || 'cf-low';
}

// ── DOM rendering (browser only) ──────────────────────────────────────────

import { escapeHtml } from './format.js';

let _ca = null;
let _sel = null;

export function renderCalendar(ca) {
  _ca = ca || null;
  const body = document.getElementById('calendar-body');
  if (!body) return;
  if (!_ca || !_ca.dashboard) {
    body.innerHTML = '<p style="color:var(--muted);font-size:13px">No calendar data for this schedule.</p>';
    return;
  }
  _sel = _ca.primary_calendar_id;
  _render();
}

function _render() {
  const body = document.getElementById('calendar-body');
  body.innerHTML =
    _dashboard(_ca.dashboard) +
    _timelineSection() +
    _monthlyStatsSection() +
    _monthlyViewSection() +
    _exceptionsSection() +
    _hoursSection() +
    _comparisonSection(_ca.comparison) +
    _usageSection(_ca.usage) +
    _conflictsSection(_ca.conflicts) +
    _conclusionSection(_ca.conclusion);
  _wire();
}

function _sec(n, title, extra = '') {
  return `<div class="cal-sec-label"><span class="cal-num">${n}</span> ${escapeHtml(title)}
    ${extra ? `<span class="cal-sec-extra">${extra}</span>` : ''}</div>`;
}

function _tile(lab, val, sub = '') {
  return `<div class="cal-kpi"><div class="cal-k">${escapeHtml(lab)}</div>
    <div class="cal-v">${escapeHtml(String(val))}</div>
    ${sub ? `<div class="cal-k2">${escapeHtml(sub)}</div>` : ''}</div>`;
}

function _dashboard(d) {
  const dates = [
    _tile('Project Start', fmtCalDate(d.project_start)),
    _tile('Project Finish', fmtCalDate(d.project_finish)),
    _tile('Baseline Start', fmtCalDate(d.baseline_start)),
    _tile('Baseline Finish', fmtCalDate(d.baseline_finish)),
    _tile('Data Date', fmtCalDate(d.data_date)),
  ].join('');
  const stats = [
    _tile('Total Calendar Days', d.total_calendar_days),
    _tile('Working Days', d.total_working_days),
    _tile('Non-Working Days', d.total_nonworking_days),
    _tile('Holidays', d.total_holidays),
    _tile('Exceptions', d.total_exceptions),
    _tile('Shutdown Periods', d.shutdown_periods),
    _tile('Avg Working Days / Month', d.avg_working_days_per_month),
    _tile('Avg Working Hours / Day', `${d.avg_working_hours_per_day} hrs`),
  ].join('');
  return _sec(1, 'Executive Dashboard') +
    `<div class="cal-subhead">Key Dates</div><div class="cal-dates-grid">${dates}</div>
     <div class="cal-subhead">Calendar Statistics</div><div class="cal-kpi-grid">${stats}</div>`;
}

function _calPicker() {
  const opts = (_ca.assigned_calendars || []).map(c =>
    `<option value="${escapeHtml(c.object_id)}" ${c.object_id === _sel ? 'selected' : ''}>
      ${escapeHtml(c.name)}${c.is_default ? ' — default' : ''} (${c.activity_count})</option>`).join('');
  return `<select class="cal-picker" id="cal-picker">${opts}</select>`;
}

function _selMonths() {
  const bc = (_ca.by_calendar || {})[_sel];
  return (bc && bc.monthly_stats) || [];
}

function _timelineSection() {
  const months = _selMonths();
  const strips = months.map(m => {
    const cells = (m.days || []).map(day => `<i class="${statusClass(day.status)}"></i>`).join('');
    const flag = m.flag
      ? `<div class="cal-tl-flag ${m.flag.startsWith('Shutdown') ? 'f-sh' : 'f-sp'}">${escapeHtml(m.flag)}</div>`
      : '';
    return `<div class="cal-tl-month"><h4>${escapeHtml(m.label)}<span>${m.working_days}d</span></h4>
      <div class="cal-daygrid">${cells}</div>${flag}</div>`;
  }).join('');
  const legend = `<div class="cal-legend">
    <span><i class="dot cs-work"></i>Working</span>
    <span><i class="dot cs-weekend"></i>Weekend</span>
    <span><i class="dot cs-holiday"></i>Holiday</span>
    <span><i class="dot cs-shutdown"></i>Shutdown</span>
    <span><i class="dot cs-special"></i>Special hours</span></div>`;
  return _sec(2, 'Calendar Timeline',
      `<span class="cal-showing">Showing: ${_calPicker()}</span>`) +
    legend + `<div class="cal-timeline">${strips || '<span style="color:var(--muted)">No months.</span>'}</div>`;
}

function _monthlyStatsSection() {
  const rows = _selMonths().map(m =>
    `<tr><td>${escapeHtml(m.label)}</td><td class="num">${m.working_days}</td>
     <td class="num">${m.holidays}</td><td class="num">${m.exceptions}</td>
     <td class="num">${m.working_hours}</td></tr>`).join('');
  return _sec(3, 'Monthly Calendar Statistics') +
    `<div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Month</th><th class="num">Working Days</th><th class="num">Holidays</th>
      <th class="num">Exceptions</th><th class="num">Working Hours</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
}

function _monthlyViewSection() {
  const dows = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const rows = _selMonths().map((m, i) => {
    const head = dows.map(d => `<div class="cal-mh">${d}</div>`).join('');
    const cells = monthGridCells(m).map(c => c.blank
      ? '<div class="cal-mcell blank"></div>'
      : `<div class="cal-mcell ${statusClass(c.status)}">${c.d}</div>`).join('');
    const stat = `${m.working_days} working · ${m.holidays} holiday${m.holidays === 1 ? '' : 's'} · ${m.working_hours} hrs`;
    return `<div class="cal-acc">
      <div class="cal-acc-head ${i === 0 ? 'open' : ''}" data-acc>
        <span class="cal-chev">▶</span><span class="cal-m">${escapeHtml(m.label)}</span>
        <span class="cal-acc-stat">${escapeHtml(stat)}</span></div>
      <div class="cal-acc-body" style="display:${i === 0 ? 'block' : 'none'}">
        <div class="cal-month-grid">${head}${cells}</div></div></div>`;
  }).join('');
  return _sec(4, 'Monthly Calendar View', '<span class="cal-sec-note">click a month to expand</span>') +
    `<div>${rows}</div>`;
}

function _excGroup(title, cls, meta, headHtml, rowsHtml) {
  return `<div class="cal-grp"><span class="cal-pill ${cls}">${escapeHtml(title)}</span>
    <span class="cal-grp-meta">${escapeHtml(meta)}</span></div>
    <div class="cal-card p0"><table class="cal-table"><thead>${headHtml}</thead>
      <tbody>${rowsHtml || `<tr><td colspan="6" class="cal-empty">None.</td></tr>`}</tbody></table></div>`;
}

function _exceptionsSection() {
  const bc = (_ca.by_calendar || {})[_sel] || {};
  const exc = bc.exceptions || { holidays: [], special: [], shutdowns: [] };
  const hDays = exc.holidays.reduce((a, h) => a + h.days, 0);
  const sDays = exc.shutdowns.reduce((a, s) => a + s.days, 0);
  const holRows = exc.holidays.map(h =>
    `<tr><td>${escapeHtml(h.description)}</td><td class="num">${h.days}</td>
     <td>${escapeHtml(h.reason || '—')}</td></tr>`).join('');
  const spRows = exc.special.map(s =>
    `<tr><td>${escapeHtml(s.description)}</td><td class="num">${s.days}</td>
     <td>${escapeHtml(s.hours || '')}</td><td>${escapeHtml(s.description)}</td></tr>`).join('');
  const shRows = exc.shutdowns.map(s =>
    `<tr><td>${escapeHtml(s.description)}</td><td class="num">${s.days}</td>
     <td>${s.source === 'manual' ? '<span class="cal-pill mini warn">Added</span> ' : ''}${escapeHtml(s.reason || '—')}</td></tr>`).join('');
  return _sec(5, 'Calendar Exceptions', '<span class="cal-sec-note">separated by type</span>') +
    _excGroup('Holidays & Vacations', 'holiday', `${exc.holidays.length} events · ${hDays} days`,
      '<tr><th>Date</th><th class="num">Days</th><th>Description</th></tr>', holRows) +
    _excGroup('Reduced / Special Working Hours', 'special', `${exc.special.length} periods`,
      '<tr><th>Date</th><th class="num">Days</th><th>Hours</th><th>Description</th></tr>', spRows) +
    _excGroup('Shutdowns', 'shutdown', `${exc.shutdowns.length} periods · ${sDays} days`,
      '<tr><th>Date</th><th class="num">Days</th><th>Reason (stored)</th></tr>', shRows);
}

function _hoursSection() {
  const bc = (_ca.by_calendar || {})[_sel] || {};
  const profs = bc.hours_profiles || [];
  const cards = profs.map(p =>
    `<div class="cal-hprof"><div class="t">${escapeHtml(p.name)}</div>
     <div class="h">${escapeHtml(p.hours)}</div>
     <div class="sub">${escapeHtml(String(p.hours_per_day))} hrs · ${escapeHtml(p.sub || '')}</div></div>`).join('');
  return _sec(6, 'Working Hours Profile') + `<div class="cal-hours-grid">${cards}</div>`;
}

function _comparisonSection(cmp) {
  const rows = (cmp || []).map(c =>
    `<tr><td>${escapeHtml(c.name)}${c.is_default ? ' <span class="cal-pill mini def">Default</span>' : ''}</td>
     <td class="num">${c.hours_per_day}</td><td class="num">${c.days_per_week}</td>
     <td class="num">${c.activities}</td><td class="num">${c.exceptions}</td></tr>`).join('');
  return _sec(7, 'Calendar Comparison') +
    `<div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Calendar</th><th class="num">Hours/Day</th><th class="num">Days/Week</th>
      <th class="num">Activities</th><th class="num">Exceptions</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
}

function _usageSection(usage) {
  const rows = (usage || []).map(u => {
    const roleCls = u.role === 'Default' ? 'def' : (u.role === 'Unused' ? 'warn' : '');
    return `<tr><td>${escapeHtml(u.name)}</td><td class="num">${u.activities}</td>
      <td>${u.role === 'Unused' ? '—' : `${u.pct}%`}</td>
      <td><span class="cal-pill mini ${roleCls}">${escapeHtml(u.role)}</span></td></tr>`;
  }).join('');
  return _sec(8, 'Calendar Usage') +
    `<div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Calendar</th><th class="num">Activities</th><th>% of Activities</th><th>Role</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
}

function _conflictsSection(conflicts) {
  if (!conflicts || !conflicts.length) {
    return _sec(9, 'Calendar Conflicts') +
      '<div class="cal-card"><p style="color:var(--muted);font-size:13px;margin:0">No calendar conflicts detected.</p></div>';
  }
  const items = conflicts.map(c =>
    `<div class="cal-conf"><div class="cal-conf-ic ${conflictSeverityClass(c.severity)}">!</div>
      <div><div class="cal-conf-t">${escapeHtml(c.title)}</div>
        <div class="cal-conf-d">${escapeHtml(c.detail)}</div></div></div>`).join('');
  return _sec(9, 'Calendar Conflicts') + items;
}

function _conclusionSection(bullets) {
  const items = (bullets || []).map(b => `<li>${escapeHtml(b)}</li>`).join('');
  return _sec(11, 'Executive Conclusion') +
    `<div class="cal-concl"><ul>${items}</ul>
      <div class="cal-note">Generated automatically from the numbers above.</div></div>`;
}

function _wire() {
  const picker = document.getElementById('cal-picker');
  if (picker) picker.addEventListener('change', e => { _sel = e.target.value; _render(); });
  document.querySelectorAll('#calendar-body [data-acc]').forEach(head =>
    head.addEventListener('click', () => {
      const open = head.classList.toggle('open');
      const bodyEl = head.nextElementSibling;
      if (bodyEl) bodyEl.style.display = open ? 'block' : 'none';
    }));
}
