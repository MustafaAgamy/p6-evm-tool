// Calendar Audit renderer — Calendar Timeline & Audit + Weather Impact.

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
import { state } from './state.js';
import { geocodePlace, computeWeather, saveCalendarSettings } from './api.js';

const DEFAULT_THRESHOLDS = { rain_mm: 5, temp_max_c: 42, wind_kmh: null, dust: true };

let _ca = null;
let _sel = null;
let _weather = null;      // last computed weather impact
let _pendingLoc = null;   // location chosen in the picker, not yet applied
let _thresholds = null;   // stop-work limits (rain/heat/wind/dust)
const _openMonths = new Set();

export function renderCalendar(ca) {
  _ca = ca || null;
  _weather = null;
  _pendingLoc = null;
  _thresholds = { ...DEFAULT_THRESHOLDS };
  _openMonths.clear();
  const body = document.getElementById('calendar-body');
  if (!body) return;
  if (!_ca || !_ca.dashboard) {
    body.innerHTML = '<p style="color:var(--muted);font-size:13px">No calendar data for this schedule.</p>';
    return;
  }
  _sel = _ca.primary_calendar_id;
  const settings = (state.currentResult && state.currentResult.calendar_settings) || {};
  if (settings.location) _pendingLoc = settings.location;
  if (settings.weather_thresholds) _thresholds = { ...DEFAULT_THRESHOLDS, ...settings.weather_thresholds };
  if (settings.last_weather) _weather = settings.last_weather;   // show the last saved estimate on re-open
  _render();
}

function _render() {
  const body = document.getElementById('calendar-body');
  body.innerHTML =
    _locationCard() +
    _dashboard(_ca.dashboard) +
    _timelineSection() +
    _monthlyStatsSection() +
    _exceptionsSection() +
    _hoursSection() +
    _comparisonSection(_ca.comparison) +
    _usageSection(_ca.usage) +
    _conflictsSection(_ca.conflicts) +
    _weatherSection() +
    _conclusionSection(_ca.conclusion);
  _wire();
}

function _sec(n, title, extra = '') {
  return `<div class="cal-sec-label"><span class="cal-num">${n}</span> ${escapeHtml(title)}
    ${extra ? `<span class="cal-sec-extra">${extra}</span>` : ''}</div>`;
}

function _tile(lab, val, sub = '', cls = '') {
  return `<div class="cal-kpi ${cls}"><div class="cal-k">${lab}</div>
    <div class="cal-v">${escapeHtml(String(val))}</div>
    ${sub ? `<div class="cal-k2">${sub}</div>` : ''}</div>`;
}

// ── Location picker (top — drives the Weather-Adjusted Finish + Section 9) ──
function _locationCard() {
  const loc = _pendingLoc;
  const mapSrc = loc
    ? `https://www.openstreetmap.org/export/embed.html?bbox=${loc.lon - 0.15},${loc.lat - 0.1},${loc.lon + 0.15},${loc.lat + 0.1}&layer=mapnik&marker=${loc.lat},${loc.lon}`
    : '';
  const readout = loc
    ? `<div class="cal-loc-read">📌 <b>${escapeHtml(loc.name || 'Selected location')}</b><br>
        <span class="cal-muted">Coordinates: ${(+loc.lat).toFixed(4)}° , ${(+loc.lon).toFixed(4)}°</span></div>`
    : '<div class="cal-loc-read cal-muted">No location set yet — search for the project site.</div>';
  const map = loc
    ? `<iframe class="cal-map" src="${escapeHtml(mapSrc)}" title="Project location" loading="lazy"></iframe>`
    : '<div class="cal-map cal-map-empty">Search a place to preview it on the map</div>';
  return `
    <div class="cal-loc-card">
      <div class="cal-loc-left">
        <div class="cal-loc-title">📍 Project Location <span class="cal-pill mini warn">required for weather</span></div>
        <div class="cal-muted" style="font-size:12px;margin-bottom:8px">Set this first — the Weather-Adjusted Finish and the Weather Impact section are calculated from it. Saved with the project.</div>
        <div class="cal-loc-search">
          <input id="cal-loc-q" placeholder="Search a place or address… (e.g. Jubail, Saudi Arabia)" value="">
          <button class="cal-btn pri" id="cal-loc-search-btn">Search</button>
        </div>
        <div id="cal-loc-results" class="cal-loc-results"></div>
        ${readout}
        <button class="cal-btn pri" id="cal-loc-use" style="margin-top:10px" ${loc ? '' : 'disabled'}>✓ Use this location &amp; calculate weather</button>
        <span id="cal-loc-status" class="cal-muted" style="font-size:12px;margin-left:8px"></span>
      </div>
      <div class="cal-loc-right">${map}</div>
    </div>`;
}

function _dashboard(d) {
  const adj = _weather ? fmtCalDate(_weather.weather_adjusted_finish) : '—';
  const adjSub = _weather
    ? `<span style="color:var(--warning)">+${_weather.net_finish_delay} wd from weather</span>`
    : '<span class="cal-muted">set location</span>';
  const dates = [
    _tile('Baseline Start', fmtCalDate(d.baseline_start)),
    _tile('Baseline Finish', fmtCalDate(d.baseline_finish), 'plan of record'),
    _tile('Data Date', fmtCalDate(d.data_date)),
    _tile('Forecast Finish <span class="cal-tag-exact">P6</span>', fmtCalDate(d.project_finish)),
    _tile('Weather-Adjusted Finish <span class="cal-tag-est">estimate</span>', adj, adjSub, _weather ? 'hl-amber' : ''),
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
    `<div class="cal-subhead">Key Dates &amp; Forecast</div><div class="cal-dates-grid">${dates}</div>
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

// Section 2 — timeline strips; clicking a month expands its full calendar grid inline
// (this replaces the old separate "Monthly Calendar View", which duplicated the timeline).
function _timelineSection() {
  const dows = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const strips = _selMonths().map((m, i) => {
    const cells = (m.days || []).map(day => `<i class="${statusClass(day.status)}"></i>`).join('');
    const flag = m.flag
      ? `<div class="cal-tl-flag ${m.flag.startsWith('Shutdown') ? 'f-sh' : 'f-sp'}">${escapeHtml(m.flag)}</div>`
      : '';
    const open = _openMonths.has(i);
    return `<div class="cal-tl-month ${open ? 'open' : ''}" data-month="${i}">
      <h4>${escapeHtml(m.label)}<span>${m.working_days}d</span></h4>
      <div class="cal-daygrid">${cells}</div>${flag}
      <div class="cal-tl-expand">${open ? '▾ hide' : '▸ open'}</div></div>`;
  }).join('');
  const detail = _monthDetailHtml();
  const legend = `<div class="cal-legend">
    <span><i class="dot cs-work"></i>Working</span>
    <span><i class="dot cs-weekend"></i>Weekend</span>
    <span><i class="dot cs-holiday"></i>Holiday</span>
    <span><i class="dot cs-shutdown"></i>Shutdown</span>
    <span><i class="dot cs-special"></i>Special hours</span></div>`;
  return _sec(2, 'Calendar Timeline',
      `<span class="cal-sec-note">baseline window, full months · click a month to open its calendar</span>
       <span class="cal-showing">Showing: ${_calPicker()}</span>`) +
    legend + `<div class="cal-timeline">${strips || '<span class="cal-muted">No months.</span>'}</div>` +
    `<div id="cal-month-detail">${detail}</div>`;
}

function _monthDetailHtml() {
  if (!_openMonths.size) return '';
  const dows = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const months = _selMonths();
  return [..._openMonths].sort((a, b) => a - b).map(i => {
    const m = months[i];
    if (!m) return '';
    const head = dows.map(d => `<div class="cal-mh">${d}</div>`).join('');
    const cells = monthGridCells(m).map(c => c.blank
      ? '<div class="cal-mcell blank"></div>'
      : `<div class="cal-mcell ${statusClass(c.status)}">${c.d}</div>`).join('');
    return `<div class="cal-month-open"><div class="cal-month-open-t">${escapeHtml(m.label)} —
      ${m.working_days} working · ${m.holidays} holiday${m.holidays === 1 ? '' : 's'} · ${m.working_hours} hrs</div>
      <div class="cal-month-grid">${head}${cells}</div></div>`;
  }).join('');
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

function _excGroup(title, cls, meta, headHtml, rowsHtml, extra = '') {
  return `<div class="cal-grp"><span class="cal-pill ${cls}">${escapeHtml(title)}</span>
    <span class="cal-grp-meta">${escapeHtml(meta)}</span>${extra}</div>
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
     <td>${s.source === 'manual' ? '<span class="cal-pill mini warn">Added</span> ' : ''}
       <input class="cal-reason" data-key="${escapeHtml(s.key || '')}" value="${escapeHtml(s.reason || '')}" placeholder="type a reason…"></td></tr>`).join('');
  const addBtn = '<button class="cal-btn sec mini" id="cal-add-shutdown-btn">+ Add shutdown</button>';
  const addForm = `<div id="cal-add-shutdown" class="cal-addform hidden">
      <input type="date" id="cal-sd-start"><span>→</span><input type="date" id="cal-sd-end">
      <input id="cal-sd-reason" placeholder="reason (e.g. Plant turnaround)">
      <button class="cal-btn pri mini" id="cal-sd-save">Add</button></div>`;
  return _sec(4, 'Calendar Exceptions', '<span class="cal-sec-note">separated by type</span>') +
    _excGroup('Holidays & Vacations', 'holiday', `${exc.holidays.length} events · ${hDays} days`,
      '<tr><th>Date</th><th class="num">Days</th><th>Description</th></tr>', holRows) +
    _excGroup('Reduced / Special Working Hours', 'special', `${exc.special.length} periods`,
      '<tr><th>Date</th><th class="num">Days</th><th>Hours</th><th>Description</th></tr>', spRows) +
    _excGroup('Shutdowns', 'shutdown', `${exc.shutdowns.length} periods · ${sDays} days`,
      '<tr><th>Date</th><th class="num">Days</th><th>Reason (stored)</th></tr>', shRows, addBtn) +
    addForm;
}

function _hoursSection() {
  const bc = (_ca.by_calendar || {})[_sel] || {};
  const profs = bc.hours_profiles || [];
  const cards = profs.map(p =>
    `<div class="cal-hprof"><div class="t">${escapeHtml(p.name)}</div>
     <div class="h">${escapeHtml(p.hours)}</div>
     <div class="sub">${escapeHtml(String(p.hours_per_day))} hrs · ${escapeHtml(p.sub || '')}</div></div>`).join('');
  return _sec(5, 'Working Hours Profile') + `<div class="cal-hours-grid">${cards}</div>`;
}

function _comparisonSection(cmp) {
  const rows = (cmp || []).map(c =>
    `<tr><td>${escapeHtml(c.name)}${c.is_default ? ' <span class="cal-pill mini def">Default</span>' : ''}</td>
     <td class="num">${c.hours_per_day}</td><td class="num">${c.days_per_week}</td>
     <td class="num">${c.activities}</td><td class="num">${c.exceptions}</td></tr>`).join('');
  return _sec(6, 'Calendar Comparison') +
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
  return _sec(7, 'Calendar Usage') +
    `<div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Calendar</th><th class="num">Activities</th><th>% of Activities</th><th>Role</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
}

// Section 8 — concise summary (no repeated detail).
function _conflictsSection(conflicts) {
  conflicts = conflicts || [];
  if (!conflicts.length) {
    return _sec(8, 'Calendar Conflicts') +
      '<div class="cal-card"><p style="color:var(--success);font-size:13px;margin:0">✓ No calendar conflicts detected — assignments look clean.</p></div>';
  }
  const counts = { mixed_wbs: 0, not_default: 0, unused: 0 };
  conflicts.forEach(c => { counts[c.type] = (counts[c.type] || 0) + 1; });
  const chips = [];
  if (counts.mixed_wbs) chips.push(`<span class="cal-pill warn">${counts.mixed_wbs} WBS with mixed calendars</span>`);
  if (counts.not_default) chips.push(`<span class="cal-pill warn">activities off the default calendar</span>`);
  if (counts.unused) chips.push(`<span class="cal-pill warn">${counts.unused} unused calendar${counts.unused === 1 ? '' : 's'}</span>`);
  const lines = conflicts.map(c => `<li><b>${escapeHtml(c.title)}</b> — ${escapeHtml(c.detail)}</li>`).join('');
  return _sec(8, 'Calendar Conflicts') +
    `<div class="cal-card">
      <div style="margin-bottom:8px">${chips.join(' ')} <span class="cal-muted">— ${conflicts.length} issue${conflicts.length === 1 ? '' : 's'} total</span></div>
      <ul class="cal-conf-sum">${lines}</ul></div>`;
}

// Section 9 — Weather Impact (estimate).
function _thr() { return _thresholds || DEFAULT_THRESHOLDS; }

function _weatherControls() {
  const t = _thr();
  const connected = _weather
    ? `<span class="dot-ok"></span> <b>Weather source: ${escapeHtml((_weather.source || 'Open-Meteo').split(' (')[0])}</b>
       <span class="cal-muted">— live forecast + historical + air-quality (dust)</span>
       <span class="cal-pill ok" style="margin-left:auto">connected ✓</span>`
    : '<span class="cal-muted">Weather source: Open-Meteo (free) — will connect when you calculate.</span>';
  const from = _weather && _weather.from_date ? ` · upcoming from cutoff <b>${fmtCalDate(_weather.from_date)}</b>` : '';
  const num = (id, lab, val) =>
    `<div class="thr-f"><label>${lab}</label><input type="number" id="${id}" value="${val == null ? '' : val}" placeholder="${val == null ? 'off' : ''}"></div>`;
  return `<div class="cal-src">${connected}</div>
    <div class="cal-muted" style="font-size:12px;margin:6px 0 10px">Location: <b>${escapeHtml((_pendingLoc && _pendingLoc.name) || '')}</b>${from} · <span class="loc-change" onclick="window.scrollTo(0,0)">change ↑</span></div>
    <div class="cal-grp" style="margin-top:0"><span class="cal-pill warn">Stop-work limits</span>
      <span class="cal-grp-meta">a day is lost when ANY apply — edit to match your site</span></div>
    <div class="cal-thr">
      ${num('thr-rain', '🌧 Rain ≥ (mm)', t.rain_mm)}
      ${num('thr-heat', '🌡 Heat ≥ (°C)', t.temp_max_c)}
      ${num('thr-wind', '💨 Wind ≥ (km/h)', t.wind_kmh)}
      <div class="thr-f"><label>🌫 Dust</label><span class="thr-sw"><input type="checkbox" id="thr-dust" ${t.dust ? 'checked' : ''}> count sandstorm days</span></div>
      <button class="cal-btn pri" id="thr-apply">Apply &amp; recalculate</button>
      <span id="thr-status" class="cal-muted" style="font-size:12px"></span>
    </div>`;
}

function _weatherSection() {
  const head = _sec(9, 'Weather Impact', '<span class="cal-pill warn">Estimate · not a P6 figure</span>');
  if (!_pendingLoc) {
    return head + `<div class="cal-card"><p style="color:var(--muted);font-size:13px;margin:0">
      Set the <b>Project Location</b> at the top and click <b>Use this location</b> to calculate the expected bad-weather days, milestone impact and recovery options.</p></div>`;
  }
  const controls = `<div class="cal-card" style="margin-bottom:12px">${_weatherControls()}</div>`;
  if (!_weather) {
    return head + controls + `<div class="cal-card"><p style="color:var(--muted);font-size:13px;margin:0">
      Adjust the stop-work limits above if needed, then click <b>Apply &amp; recalculate</b> (or <b>Use this location</b> at the top).</p></div>`;
  }
  const w = _weather;
  const kpis = `<div class="cal-kpi-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:12px">
    ${_tile('Bad-weather days (remaining)', w.expected_bad_days_total, '', 'hl-amber')}
    ${_tile('Net weather delay to finish', `+${w.net_finish_delay} wd`, '', 'hl-amber')}
    ${_tile('Weather-adjusted finish', fmtCalDate(w.weather_adjusted_finish))}</div>`;
  const maxc = Math.max(1, ...(w.monthly || []).map(x => x.count));
  const bars = (w.monthly || []).map(x =>
    `<div class="cal-wxbar"><div class="cal-wxbar-v">${x.count || ''}</div>
      <div class="cal-wxbar-b" style="height:${Math.max(4, x.count / maxc * 70)}px;${x.count >= 3 ? 'background:var(--warning)' : ''}"></div>
      <div class="cal-wxbar-l">${escapeHtml(x.label)}</div></div>`).join('');
  const bar = `<div class="cal-card" style="margin-bottom:12px">
    <div class="cal-muted" style="font-size:12px;margin-bottom:10px">Expected bad-weather days per month — historical climate at the location, applied to construction phases only</div>
    <div class="cal-wxbars">${bars || '<span class="cal-muted">No data.</span>'}</div></div>`;
  const dayRows = (w.bad_days || []).slice(0, 200).map(d =>
    `<tr><td>${fmtCalDate(d.date)}</td><td>${escapeHtml(d.day_name)}</td>
      <td>${escapeHtml(d.condition)}</td>
      <td><span class="cal-pill mini ${d.confidence === 'forecast' ? 'def' : 'warn'}">${d.confidence === 'forecast' ? 'Forecast' : 'Expected'}</span></td>
      <td>${escapeHtml(d.effect)}</td></tr>`).join('');
  const dayTable = `<div class="cal-grp"><span class="cal-pill special">Upcoming Bad-Weather Days</span>
      <span class="cal-grp-meta">each day shows the measured value &amp; why it counts · next ~16 days = live forecast · beyond = expected from historical climate</span></div>
    <div class="cal-card p0" style="max-height:300px;overflow-y:auto"><table class="cal-table"><thead><tr>
      <th>Date</th><th>Day</th><th>Why it's a lost day (measured)</th><th>Confidence</th><th>Effect</th></tr></thead>
      <tbody>${dayRows || '<tr><td colspan="5" class="cal-empty">No bad-weather days expected.</td></tr>'}</tbody></table></div>`;
  const msRows = (w.milestones || []).map(m =>
    `<tr><td>${escapeHtml(m.name)}</td><td>${fmtCalDate(m.planned)}</td>
      <td class="num">${m.bad_days_before}</td><td class="num">${m.already_allowed}</td>
      <td class="num"><span class="cal-pill mini ${m.net_delay > 0 ? 'shutdown' : 'def'}">+${m.net_delay} d</span></td>
      <td>${fmtCalDate(m.adjusted)}</td></tr>`).join('');
  const msTable = `<div class="cal-grp"><span class="cal-pill shutdown">Milestone Impact</span></div>
    <div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Milestone</th><th>Planned date</th><th class="num">Bad-weather days before</th>
      <th class="num">Already in calendar</th><th class="num">Net weather delay</th><th>Weather-adjusted date</th></tr></thead>
      <tbody>${msRows || '<tr><td colspan="6" class="cal-empty">No milestones found.</td></tr>'}</tbody></table></div>`;
  const recRows = (w.recovery || []).map(r =>
    `<tr><td>${escapeHtml(r.period)}</td><td class="num"><span class="cal-pill mini shutdown">${r.days} d</span></td>
      <td>${escapeHtml(r.option_longer_days)}</td><td>${escapeHtml(r.option_extra_days)}</td><td>${escapeHtml(r.option_shift)}</td></tr>`).join('');
  const recTable = `<div class="cal-grp"><span class="cal-pill def">Recovery Recommendations</span>
      <span class="cal-grp-meta">advisory — one option per period, computed from the estimated lost hours</span></div>
    <div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Period / milestone</th><th class="num">Days</th><th>Longer days</th><th>Extra working days</th><th>Add shift</th></tr></thead>
      <tbody>${recRows || '<tr><td colspan="5" class="cal-empty">No recovery needed — no net weather delay.</td></tr>'}</tbody></table></div>`;
  const note = '<div class="cal-note">Applies to construction activities only (auto-detected), and only to Finish/completion milestones. Estimated from the location\'s historical climate + live forecast — a forward-looking risk, kept separate from the exact P6 Delay. Needs an internet connection.</div>';
  return head + controls + kpis + bar + dayTable + msTable + recTable + note;
}

// Read the stop-work-limit inputs → thresholds object (blank = off).
function _readThresholds() {
  const n = id => {
    const v = document.getElementById(id);
    if (!v || v.value === '') return null;
    const f = parseFloat(v.value);
    return isNaN(f) ? null : f;
  };
  return {
    rain_mm: n('thr-rain'), temp_max_c: n('thr-heat'), wind_kmh: n('thr-wind'),
    dust: !!(document.getElementById('thr-dust') && document.getElementById('thr-dust').checked),
  };
}

function _conclusionSection(bullets) {
  const items = (bullets || []).map(b => `<li>${escapeHtml(b)}</li>`).join('');
  const wx = _weather
    ? `<li><b>Weather:</b> ~${_weather.expected_bad_days_total} bad-weather days expected; net estimated +${_weather.net_finish_delay} working days to the finish (see Weather Impact).</li>`
    : '';
  return _sec(10, 'Executive Conclusion') +
    `<div class="cal-concl"><ul>${items}${wx}</ul>
      <div class="cal-note">Generated automatically from the numbers above.</div></div>`;
}

// ── wiring ─────────────────────────────────────────────────────────────────
function _wire() {
  const picker = document.getElementById('cal-picker');
  if (picker) picker.addEventListener('change', e => { _sel = e.target.value; _openMonths.clear(); _render(); });

  document.querySelectorAll('#calendar-body .cal-tl-month').forEach(card =>
    card.addEventListener('click', () => {
      const i = +card.dataset.month;
      if (_openMonths.has(i)) _openMonths.delete(i); else _openMonths.add(i);
      _render();
    }));

  _wireLocation();
  _wireWeather();
  _wireShutdowns();
}

function _wireLocation() {
  const q = document.getElementById('cal-loc-q');
  const searchBtn = document.getElementById('cal-loc-search-btn');
  const results = document.getElementById('cal-loc-results');
  const useBtn = document.getElementById('cal-loc-use');
  const statusEl = document.getElementById('cal-loc-status');
  const doSearch = async () => {
    const term = (q.value || '').trim();
    if (!term) return;
    results.innerHTML = '<div class="cal-muted" style="font-size:12px">Searching…</div>';
    const resp = await geocodePlace(term);
    if (!resp.ok || !(resp.results || []).length) {
      results.innerHTML = `<div class="cal-muted" style="font-size:12px">No matches (offline?).</div>`;
      return;
    }
    results.innerHTML = resp.results.map((r, i) =>
      `<div class="cal-loc-hit" data-i="${i}">${escapeHtml(r.name)}</div>`).join('');
    results.querySelectorAll('.cal-loc-hit').forEach(el =>
      el.addEventListener('click', () => {
        const r = resp.results[+el.dataset.i];
        _pendingLoc = { lat: r.lat, lon: r.lon, name: r.name };
        _render();
      }));
  };
  if (searchBtn) searchBtn.addEventListener('click', doSearch);
  if (q) q.addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });
  if (useBtn) useBtn.addEventListener('click', () => _runWeather(useBtn, statusEl));
}

// Wire the Weather-Impact "Apply & recalculate" (edited stop-work limits).
function _wireWeather() {
  const applyBtn = document.getElementById('thr-apply');
  if (applyBtn) applyBtn.addEventListener('click', () => {
    _thresholds = _readThresholds();
    _runWeather(applyBtn, document.getElementById('thr-status'));
  });
}

async function _runWeather(btn, statusEl) {
  if (!_pendingLoc) return;
  if (btn) btn.disabled = true;
  if (statusEl) statusEl.textContent = 'Calculating weather…';
  try {
    const resp = await computeWeather(_pendingLoc.lat, _pendingLoc.lon, _pendingLoc.name, _thresholds);
    if (resp.ok) {
      _weather = resp.weather;
      _pendingLoc = resp.location || _pendingLoc;
      if (resp.weather && resp.weather.thresholds) _thresholds = resp.weather.thresholds;
      if (resp.offline && statusEl) statusEl.textContent = 'No weather data (offline) — location saved.';
      _render();
    } else if (statusEl) {
      statusEl.textContent = resp.error || 'Weather failed.'; if (btn) btn.disabled = false;
    }
  } catch {
    if (statusEl) statusEl.textContent = 'Weather failed (offline?).';
    if (btn) btn.disabled = false;
  }
}

function _wireShutdowns() {
  const addBtn = document.getElementById('cal-add-shutdown-btn');
  const form = document.getElementById('cal-add-shutdown');
  if (addBtn && form) addBtn.addEventListener('click', () => form.classList.toggle('hidden'));
  const saveBtn = document.getElementById('cal-sd-save');
  if (saveBtn) saveBtn.addEventListener('click', async () => {
    const start = document.getElementById('cal-sd-start').value;
    const end = document.getElementById('cal-sd-end').value;
    const reason = document.getElementById('cal-sd-reason').value;
    if (!start) return;
    const existing = _existingManualShutdowns();
    existing.push({ start, end: end || start, reason });
    const resp = await saveCalendarSettings({ manual_shutdowns: existing });
    if (resp.ok && resp.calendar_audit) { _ca = resp.calendar_audit; _render(); }
  });
  // reason inline-edit (both P6 and manual shutdowns) → store per project
  document.querySelectorAll('#calendar-body .cal-reason').forEach(inp =>
    inp.addEventListener('change', async () => {
      const key = inp.dataset.key; if (!key) return;
      const reasons = {}; reasons[key] = inp.value;
      const resp = await saveCalendarSettings({ shutdown_reasons: reasons });
      if (resp.ok && resp.calendar_audit) { _ca = resp.calendar_audit; _render(); }
    }));
}

function _existingManualShutdowns() {
  const out = [];
  Object.values(_ca.by_calendar || {}).forEach(bc =>
    (bc.exceptions && bc.exceptions.shutdowns || []).forEach(s => {
      if (s.source === 'manual') out.push({ start: s.start, end: s.end, reason: s.reason || '' });
    }));
  // de-dup by start
  const seen = new Set();
  return out.filter(s => (seen.has(s.start) ? false : seen.add(s.start)));
}
