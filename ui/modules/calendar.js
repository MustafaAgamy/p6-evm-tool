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
  for (const day of (month.days || [])) cells.push({ d: day.d, status: day.status, name: day.name });
  return cells;
}

export function conflictSeverityClass(sev) {
  return { High: 'cf-high', Medium: 'cf-med', Low: 'cf-low' }[sev] || 'cf-low';
}

// ── Site-type presets — mirror of p6_calendar/weather.py SITE_TYPES ──────────
// One pick loads the stop-work limits that fit that kind of work. DESERT equals the
// app default (wind off / heat 42), so a project that never picks a type is unchanged.
// Keep the numbers in sync with weather.py (tests guard both sides).
export const SITE_TYPES = {
  desert:   { label: 'Desert / inland civil', icon: '🏜️',
              blurb: 'Heat & dust drive stoppages; wind rarely halts inland civil work.',
              thresholds: { rain_mm: 5, temp_max_c: 42, wind_kmh: null, dust: true } },
  marine:   { label: 'Marine / Port', icon: '⚓',
              blurb: 'Cranes & marine works stop for high wind — the main risk for a port / terminal.',
              thresholds: { rain_mm: 5, temp_max_c: 40, wind_kmh: 35, dust: true } },
  coastal:  { label: 'Coastal / general', icon: '🌊',
              blurb: 'A mix of wind and rain; heat reaches the limit less often than inland.',
              thresholds: { rain_mm: 5, temp_max_c: 42, wind_kmh: 40, dust: true } },
  building: { label: 'Building / enclosed', icon: '🏢',
              blurb: 'Least weather-exposed once enclosed; only heavy rain / extreme heat stop work.',
              thresholds: { rain_mm: 10, temp_max_c: 45, wind_kmh: null, dust: false } },
};
export const SITE_TYPE_ORDER = ['marine', 'desert', 'coastal', 'building'];

const _eqLim = (a, b) => (a == null ? null : a) === (b == null ? null : b);

// Do these limits exactly match a site-type preset? null → the user has a Custom set.
export function matchSiteType(t) {
  if (!t) return null;
  for (const key of SITE_TYPE_ORDER) {
    const p = SITE_TYPES[key].thresholds;
    if (_eqLim(p.rain_mm, t.rain_mm) && _eqLim(p.temp_max_c, t.temp_max_c) &&
        _eqLim(p.wind_kmh, t.wind_kmh) && !!p.dust === !!t.dust) return key;
  }
  return null;
}

// The 'criteria in full' rows — mirror of build_criteria() in weather.py. Wind first
// (the dominant driver on a port). Reflects the ACTUAL limits, so Custom shows truly.
export function buildSiteCriteria(siteType, t) {
  const marine = siteType === 'marine';
  const num = (key, icon, label, v, unit, expl) => ({
    key, icon, label, value: (v == null ? 'off' : `≥ ${v} ${unit}`), on: v != null, explain: expl });
  return [
    num('wind', '💨', 'Wind', t.wind_kmh, 'km/h',
        marine ? 'High wind stops crane lifts, tower-crane and marine works'
               : 'High wind stops crane lifts and work at height'),
    num('heat', '🌡', 'Heat', t.temp_max_c, '°C', 'Extreme heat halts outdoor labour'),
    num('rain', '🌧', 'Rain', t.rain_mm, 'mm', 'Work-stopping rain (light drizzle below the limit is ignored)'),
    { key: 'dust', icon: '🌫', label: 'Dust / sandstorm', value: (t.dust ? 'on' : 'off'),
      on: !!t.dust, explain: 'Sandstorm days (near-term air-quality PM10) counted as a lost day' },
  ];
}

// ── DOM rendering (browser only) ──────────────────────────────────────────

import { escapeHtml } from './format.js';
import { state } from './state.js';
import { geocodePlace, reverseGeocode, computeWeather, saveCalendarSettings } from './api.js';

const DEFAULT_THRESHOLDS = { rain_mm: 5, temp_max_c: 42, wind_kmh: null, dust: true };

let _ca = null;
let _sel = null;
let _weather = null;      // last computed weather impact
let _pendingLoc = null;   // location chosen in the picker, not yet applied
let _thresholds = null;   // stop-work limits (rain/heat/wind/dust)
let _siteType = null;     // chosen site type (marine/desert/coastal/building/custom); null = default
let _map = null;          // Leaflet map instance (location picker)
let _marker = null;       // the draggable location pin
let _leafletPromise = null;
let _mapRO = null;        // ResizeObserver that re-measures the map when the tab is shown
const _openMonths = new Set();

export function renderCalendar(ca) {
  _ca = ca || null;
  _weather = null;
  _pendingLoc = null;
  _thresholds = { ...DEFAULT_THRESHOLDS };
  _siteType = null;
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
  if (settings.site_type) _siteType = settings.site_type;        // restore the picked site type
  else if (settings.weather_thresholds) _siteType = matchSiteType(_thresholds);  // infer from saved limits
  if (settings.last_weather) _weather = settings.last_weather;   // show the last saved estimate on re-open
  _renderCalendarBody();
}

// Feature 1 — P6 Calendar Audit → its own tab (calendar-body). No weather here.
function _renderCalendarBody() {
  const body = document.getElementById('calendar-body');
  if (!body) return;
  body.innerHTML =
    _dashboard(_ca.dashboard) +
    _timelineSection() +
    _monthlyStatsSection() +
    _exceptionsSection() +
    _hoursSection() +
    _comparisonSection(_ca.comparison) +
    _conflictsSection(_ca.conflicts) +
    _conclusionSection(_ca.conclusion);
  _wireCalendar();
}

// Feature 2 — Bad Weather effect on Forecast Finish → its own tab (weather-body).
export function renderWeatherView(ca) {
  if (ca) _ca = ca;
  const body = document.getElementById('weather-body');
  if (!body) return;
  if (!_ca || !_ca.dashboard) {
    body.innerHTML = '<p style="color:var(--muted);font-size:13px">No schedule loaded — import a file first.</p>';
    return;
  }
  _renderWeatherBody();
}

function _renderWeatherBody() {
  const body = document.getElementById('weather-body');
  if (!body) return;
  body.innerHTML = _locationCard() + _weatherSection();
  _wireWeatherView();
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

// ── Report Contents (#06) — the sections the Calendar Audit PDF can print. Shown as the
// in-preview "Include sections" picker (shared showReportPreview), matching every other
// module's report picker. ──
// Feature 1 — P6 Calendar Audit PDF (no weather; that's the Bad Weather report).
export const CAL_SECTIONS = [
  ['dashboard', '1 Executive Dashboard'], ['timeline', '2 Calendar Timeline'],
  ['stats', '3 Monthly Statistics'], ['exceptions', '4 Calendar Exceptions'],
  ['hours', '5 Working Hours Profile'], ['comparison', '6 Calendar Comparison'],
  ['usage', '7 Calendar Usage'], ['conflicts', '8 Calendar Conflicts'],
  ['conclusion', '9 Executive Conclusion'],
];
// Feature 2 — Bad Weather effect on Forecast Finish PDF (weather-only).
export const WEATHER_SECTIONS = [
  ['weather', 'Bad Weather Impact'],
];

// ── Location picker (top — drives the Weather-Adjusted Finish + Section 9) ──
function _locationReadoutHtml() {
  const loc = _pendingLoc;
  return loc
    ? `<div class="cal-loc-read">📌 <b>${escapeHtml(loc.name || 'Selected location')}</b><br>
        <span class="cal-muted">Coordinates: ${(+loc.lat).toFixed(4)}° , ${(+loc.lon).toFixed(4)}°</span></div>`
    : '<div class="cal-loc-read cal-muted">No location set yet — search, or click the map to drop a pin.</div>';
}

function _locationCard() {
  const loc = _pendingLoc;
  return `
    <div class="cal-loc-card">
      <div class="cal-loc-left">
        <div class="cal-loc-title">📍 Project Location <span class="cal-pill mini warn">required for weather</span></div>
        <div class="cal-muted" style="font-size:12px;margin-bottom:8px">Set this first — the Weather-Adjusted Finish and the Weather Impact section are calculated from it. <b>Search a place, or click the map to drop a pin on the exact site</b> (drag it to fine-tune). Saved with the project.</div>
        <div class="cal-loc-search">
          <input id="cal-loc-q" placeholder="Search a place or address… (e.g. Jubail, Saudi Arabia)" value="">
          <button class="cal-btn pri" id="cal-loc-search-btn">Search</button>
        </div>
        <div id="cal-loc-results" class="cal-loc-results"></div>
        <div id="cal-loc-readout">${_locationReadoutHtml()}</div>
        <button class="cal-btn pri" id="cal-loc-use" style="margin-top:10px" ${loc ? '' : 'disabled'}>✓ Use this location &amp; calculate weather</button>
        <span id="cal-loc-status" class="cal-muted" style="font-size:12px;margin-left:8px"></span>
      </div>
      <div class="cal-loc-right">
        <div id="cal-map" class="cal-map"></div>
        <div class="cal-map-hint cal-muted">🖱️ Click the map to place the pin · drag to fine-tune</div>
      </div>
    </div>`;
}

function _dashboard(d) {
  const dates = [
    _tile('Baseline Start', fmtCalDate(d.baseline_start)),
    _tile('Baseline Finish / Completion', fmtCalDate(d.baseline_finish), 'plan of record'),
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

// Section 2 — the timeline is a working vs non-working days-per-month histogram
// (Ibrahim's restructure — replaces the crude colour strip; §3 has the numbers).
// Clicking a month's bar opens its full calendar grid (holiday names in the cells).
function _timelineSection() {
  const months = _selMonths();
  const mx = Math.max(1, ...months.map(m => (m.working_days || 0) + (m.nonworking_days || 0)));
  const bars = months.map((m, i) => {
    const wd = m.working_days || 0, nw = m.nonworking_days || 0, tot = wd + nw;
    const totPx = Math.round(tot / mx * 100), nwPx = tot ? Math.round(nw / tot * totPx) : 0, wPx = Math.max(0, totPx - nwPx);
    const open = _openMonths.has(i);
    return `<div class="cal-whc ${open ? 'open' : ''}" data-month="${i}" title="${escapeHtml(m.label)}: ${wd} net working · ${nw} non-working — click to open its calendar">
      <div class="cal-wht">${wd}</div>
      <div class="cal-whcol"><div class="cal-whn" style="height:${nwPx}px"></div><div class="cal-whw" style="height:${wPx}px"></div></div>
      <div class="cal-whl">${escapeHtml(m.label)}${open ? ' ▾' : ''}</div></div>`;
  }).join('');
  const hleg = `<div class="cal-whleg"><span><i class="wsw wsw-w"></i>Working days</span><span><i class="wsw wsw-n"></i>Non-working (weekends + holidays + shutdowns)</span><span>▲ number above bar = <b>net working days</b></span></div>`;
  const detail = _monthDetailHtml();
  const dayLegend = _openMonths.size ? `<div class="cal-legend" style="margin-top:10px">
    <span><i class="dot cs-work"></i>Working</span>
    <span><i class="dot cs-weekend"></i>Weekend</span>
    <span><i class="dot cs-holiday"></i>Holiday</span>
    <span><i class="dot cs-shutdown"></i>Shutdown</span>
    <span><i class="dot cs-special"></i>Special hours</span></div>` : '';
  const proj = _ca.project || {};
  const hidden = proj.hidden_months || 0;
  const dd = _ca.dashboard && _ca.dashboard.data_date;
  const hiddenChip = hidden
    ? `<div class="cal-hidden-note">◀ <b>${hidden} earlier month${hidden === 1 ? '' : 's'}</b> hidden — everything before the data date${dd ? ` (${fmtCalDate(dd)})` : ''}</div>`
    : '';
  return _sec(2, 'Calendar Timeline',
      `<span class="cal-sec-note">working vs non-working days per month · click a month to open its calendar</span>
       <span class="cal-showing">Showing: ${_calPicker()}</span>`) +
    hiddenChip + hleg + `<div class="cal-whist">${bars || '<span class="cal-muted">No months.</span>'}</div>` +
    dayLegend + `<div id="cal-month-detail">${detail}</div>`;
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
      : `<div class="cal-mcell ${statusClass(c.status)}"><span class="cal-dn">${c.d}</span>${c.name ? `<div class="cal-cn">${escapeHtml(c.name)}</div>` : ''}</div>`).join('');
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
     <td><input class="cal-reason" data-key="${escapeHtml(h.key || '')}" value="${escapeHtml(h.reason || '')}" placeholder="name this holiday…"></td></tr>`).join('');
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
  return _sec(5, 'Working Hours Profile') +
    `<div class="cal-note" style="font-style:normal">Your <b>standard working day</b>, used all year — different from the <i>Reduced / Special Working Hours</i> in section 4 (specific dates whose hours differ from this standard; differences under 5 minutes are ignored).</div>
     <div class="cal-hours-grid">${cards}</div>`;
}

// Feature 1 — Calendar Comparison & Usage (merged): each calendar's hours/day, days/week,
// activities assigned, % of activities, and role.
function _comparisonSection(cmp) {
  const dd = (_ca.dashboard && _ca.dashboard.data_date) ? fmtCalDate(_ca.dashboard.data_date) : '';
  const usage = {};
  (_ca.usage || []).forEach(u => { usage[u.name] = u; });
  const rows = (cmp || []).map(c => {
    const u = usage[c.name] || {};
    const roleCls = u.role === 'Default' ? 'def' : (u.role === 'Unused' ? 'warn' : '');
    const acts = u.activities != null ? u.activities : 0;
    const pct = (u.role === 'Unused' || u.pct == null) ? (acts ? `${u.pct}%` : '0%') : `${u.pct}%`;
    return `<tr><td>${escapeHtml(c.name)}${c.is_default ? ' <span class="cal-pill mini def">Default</span>' : ''}</td>
     <td class="num">${c.hours_per_day}</td><td class="num">${c.days_per_week}</td>
     <td class="num">${acts}</td><td class="num">${pct}</td>
     <td class="num">${c.nonworking_days != null ? c.nonworking_days : 0}</td>
     <td>${u.role ? `<span class="cal-pill mini ${roleCls}">${escapeHtml(u.role)}</span>` : ''}</td></tr>`;
  }).join('');
  return _sec(6, 'Calendar Comparison & Usage') +
    `<div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Calendar</th><th class="num">Hours/Day</th><th class="num">Days/Week</th>
      <th class="num">Assigned to</th><th class="num">% of Activities</th>
      <th class="num">Non-Working Days</th><th>Role</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
     <div class="cal-note" style="font-style:normal"><b>% of Activities</b> — share of the schedule's activities on each calendar. <b>Non-Working Days</b> — weekends, holidays and shutdowns still ahead${dd ? `, from the data date (${dd}) to finish` : ''}. <b>Unused</b> calendars carry 0 activities and can be removed.</div>`;
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
      <tbody>${rows}</tbody></table></div>
     <div class="cal-note" style="font-style:normal"><b>Roles:</b> <b>Default</b> — the project's default calendar; new activities are created on it automatically. <b>Non-default</b> — a calendar deliberately assigned to specific activities instead of the default. <b>Unused</b> — defined in the file but no activity uses it.</div>`;
}

// Section 8 — concise summary (no repeated detail).
function _conflictsSection(conflicts) {
  conflicts = conflicts || [];
  if (!conflicts.length) {
    return _sec(7, 'Calendar Conflicts') +
      '<div class="cal-card"><p style="color:var(--success);font-size:13px;margin:0">✓ No calendar conflicts detected — assignments look clean.</p></div>';
  }
  const counts = { mixed_wbs: 0, not_default: 0, unused: 0 };
  conflicts.forEach(c => { counts[c.type] = (counts[c.type] || 0) + 1; });
  const chips = [];
  if (counts.mixed_wbs) chips.push(`<span class="cal-pill warn">${counts.mixed_wbs} WBS with mixed calendars</span>`);
  if (counts.not_default) chips.push(`<span class="cal-pill warn">activities off the default calendar</span>`);
  if (counts.unused) chips.push(`<span class="cal-pill warn">${counts.unused} unused calendar${counts.unused === 1 ? '' : 's'}</span>`);
  const lines = conflicts.map(c => `<li><b>${escapeHtml(c.title)}</b> — ${escapeHtml(c.detail)}</li>`).join('');
  return _sec(7, 'Calendar Conflicts') +
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
       <span class="cal-muted">— free &amp; open · no key · no bill</span>
       <span class="cal-pill ok" style="margin-left:auto">connected ✓</span>`
    : '<span class="cal-muted"><b>Weather source: Open-Meteo</b> (free, open, no key) — will connect when you calculate.</span>';
  const from = _weather && _weather.from_date ? ` · upcoming from cutoff <b>${fmtCalDate(_weather.from_date)}</b>` : '';
  const num = (id, lab, val) =>
    `<div class="thr-f"><label>${lab}</label><input type="number" id="${id}" value="${val == null ? '' : val}" placeholder="${val == null ? 'off' : ''}"></div>`;
  return `<div class="cal-src">${connected}</div>
    <div class="cal-muted" style="font-size:12px;margin:6px 0 10px">Location: <b>${escapeHtml((_pendingLoc && _pendingLoc.name) || '')}</b>${from} · <span class="loc-change" onclick="window.scrollTo(0,0)">change ↑</span></div>
    <div class="cal-wx-method">
      <div class="cal-wx-mh">📡 How the estimate is built — three free Open-Meteo feeds</div>
      <div class="cal-wx-feed"><span class="ic">🛰️</span><div><b>Live forecast</b> — the real daily forecast (rain, heat, wind) for the next ~16 days from the update's cutoff.<span class="cal-pill mini def">Forecast</span></div></div>
      <div class="cal-wx-feed"><span class="ic">📚</span><div><b>Multi-year climate history</b> — beyond ~16 days, each date is drawn from the site's recorded weather over the <b>last 5 years</b> (Open-Meteo ERA5). The day-list follows a <b>typical (representative) year</b> so a fluke year can't skew it; months show the <b>5-year average and range</b>.<span class="cal-pill mini warn">Expected · climate</span></div></div>
      <div class="cal-wx-feed"><span class="ic">🌫️</span><div><b>Air-quality</b> — near-term PM10 / dust concentration, to flag sandstorm days.</div></div>
    </div>
    ${_siteTypePickerHtml()}
    ${_criteriaPanelHtml()}
    <div class="cal-grp" style="margin-top:0"><span class="cal-pill warn">✎ Fine-tune the limits</span>
      <span class="cal-grp-meta">the site type sets these — change any number to match your site (blank = off; switches to “Custom”)</span></div>
    <div class="cal-thr">
      ${num('thr-rain', '🌧 Rain ≥ (mm)', t.rain_mm)}
      ${num('thr-heat', '🌡 Heat ≥ (°C)', t.temp_max_c)}
      ${num('thr-wind', '💨 Wind ≥ (km/h)', t.wind_kmh)}
      <div class="thr-f"><label>🌫 Dust</label><span class="thr-sw"><input type="checkbox" id="thr-dust" ${t.dust ? 'checked' : ''}> count sandstorm days</span></div>
      <button class="cal-btn pri" id="thr-apply">Apply &amp; recalculate</button>
      <span id="thr-status" class="cal-muted" style="font-size:12px"></span>
    </div>
    <div class="cal-note" style="margin-top:8px">Each flagged day below shows the measured value against your limit. Applied to <b>construction</b> activities only; a day already off (weekend / holiday / shutdown) is never double-counted — kept separate from the exact P6 Delay.</div>`;
}

// Site-type picker — one pick loads the limits that fit the work.
function _siteTypePickerHtml() {
  const cards = SITE_TYPE_ORDER.map(key => {
    const st = SITE_TYPES[key];
    return `<div class="cal-site${_siteType === key ? ' sel' : ''}" data-site="${key}">
      <div class="cal-site-ic">${st.icon}</div>
      <div class="cal-site-nm">${escapeHtml(st.label)}</div>
      <div class="cal-site-ds">${escapeHtml(st.blurb)}</div></div>`;
  }).join('');
  const custom = _siteType === 'custom'
    ? `<div class="cal-site sel" data-site="custom"><div class="cal-site-ic">⚙️</div>
        <div class="cal-site-nm">Custom</div><div class="cal-site-ds">your own edited limits</div></div>` : '';
  return `<div class="cal-grp" style="margin-top:2px"><span class="cal-pill def">🏗️ Site type</span>
      <span class="cal-grp-meta">pick what kind of site this is — it loads the stop-work limits that fit this work</span></div>
    <div class="cal-sites">${cards}${custom}</div>`;
}

// The stop-work criteria shown IN FULL — every limit, its value, and what work it stops.
function _criteriaPanelHtml() {
  const st = _siteType;
  const meta = st === 'custom' ? { label: 'Custom limits', icon: '⚙️' }
    : (SITE_TYPES[st] || { label: 'Default limits (Desert / inland)', icon: '🏜️' });
  const rows = buildSiteCriteria(st, _thr()).map(r =>
    `<div class="cal-crit-row">
      <div class="cal-crit-lim ${r.on ? 'on' : 'off'}">${r.icon} ${escapeHtml(r.label)} <b>${escapeHtml(r.value)}</b></div>
      <div class="cal-crit-exp">${escapeHtml(r.explain)}${r.on ? '' : ' <span class="cal-muted">(not counted)</span>'}</div>
    </div>`).join('');
  return `<div class="cal-crit">
    <div class="cal-crit-top"><span class="cal-crit-t">${meta.icon} ${escapeHtml(meta.label)} — what stops work here</span>
      <span class="cal-pill mini def" style="margin-left:auto">criteria in full</span></div>
    <div class="cal-crit-lead">A construction <b>working</b> day between the data date and finish is a <b>lost day</b> when <b>any</b> limit below is met. Days already off (weekend / holiday / shutdown) are never double-counted.</div>
    ${rows}
    <div class="cal-crit-any">⚠️ Any one limit met → that day is a lost construction day. These exact limits are carried into the PDF.</div>
  </div>`;
}

const _PERF_IC = { wind: '💨', heat: '🌡', rain: '🌧', dust: '🌫' };

// "Why this result" — how each limit performed, so a near-zero is never a silent black box.
function _whyResultHtml() {
  const w = _weather;
  if (!w || !w.limit_performance) return '';
  const unit = u => (u ? ' ' + u : '');
  const rows = w.limit_performance.map(p => {
    const ic = `<span class="mk">${_PERF_IC[p.key] || '•'}</span>`;
    if (!p.on) {
      const peak = p.peak != null ? ` — highest seen ${p.peak}${unit(p.unit)}` : '';
      return `<div class="cal-why-row">${ic}<span class="noflag"><b>${escapeHtml(p.label)}</b> — off (not counted)${peak}</span></div>`;
    }
    const flagged = p.flagged || 0;
    const limTxt = p.limit != null ? ` ≥ ${p.limit}${unit(p.unit)}` : '';
    const peak = p.peak != null ? ` · peak ${p.peak}${unit(p.unit)}` : '';
    return `<div class="cal-why-row">${ic}<span class="${flagged ? 'flag' : 'noflag'}">
      <b>${escapeHtml(p.label)}${limTxt} → flagged ${flagged} ${flagged === 1 ? 'day' : 'days'}.</b>${peak}</span></div>`;
  }).join('');
  return `<div class="cal-grp"><span class="cal-pill def">🔎 Why this result</span>
      <span class="cal-grp-meta">how each limit performed over the project window — a near-zero is explained, not hidden</span></div>
    <div class="cal-why">${rows}</div>`;
}

// Source & climate reference — where the bad-weather days come from (shown on import).
function _climateRefHtml() {
  const r = _weather && _weather.climate_reference;
  if (!r) return '';
  const loc = (r.place_name ? escapeHtml(r.place_name) + ' · ' : '') +
    (r.lat != null ? `${(+r.lat).toFixed(2)}°, ${(+r.lon).toFixed(2)}°` : '');
  const yrs = (r.year_start && r.year_end) ? `${r.year_start}–${r.year_end} (${r.years} years)` : `${r.years} years`;
  const row = (k, v) => `<div class="cal-ref-row"><div class="cal-ref-k">${k}</div><div class="cal-ref-v">${v}</div></div>`;
  return `<div class="cal-grp"><span class="cal-pill def">🔗 Where these bad-weather days come from</span>
      <span class="cal-grp-meta">the data source &amp; climate reference — so you can trust and check the numbers</span></div>
    <div class="cal-ref">
      ${row('Climate history', `<b>${escapeHtml(r.history_source)}</b> — <span class="cal-ref-url">${escapeHtml(r.history_url)}</span>`)}
      ${row('History window', `<b>${yrs}</b>, averaged per month`)}
      ${loc ? row('Location', loc) : ''}
      ${row('Live forecast', `${escapeHtml(r.forecast_source)} — <span class="cal-ref-url">${escapeHtml(r.forecast_url)}</span> (next ~16 days)`)}
      ${row('Dust / sandstorm', escapeHtml(r.dust_source))}
      <div class="cal-ref-note">Beyond ~16 days these are <b>climate-based expectations</b> (5-year average for this site) — not a guaranteed forecast. Kept separate from the exact P6 Delay.</div>
    </div>`;
}

// The construction activities a bad-weather day hits (#07).
function _actsCell(d) {
  const names = d.activities || [];
  const extra = (d.activities_count != null ? d.activities_count : names.length) - names.length;
  if (names.length) {
    return escapeHtml(names.join(', ')) + (extra > 0 ? ` <span class="cal-muted">(+${extra} more)</span>` : '');
  }
  if ((d.effect || '').startsWith('Non-working')) {
    return '<span class="cal-muted">No construction activity scheduled</span>';
  }
  return `<span class="cal-muted">${escapeHtml(d.effect || '')}</span>`;
}

// Calendar days between two ISO dates (b − a); 0 if either missing.
function _daysBetween(a, b) {
  if (!a || !b) return 0;
  return Math.round((new Date(b) - new Date(a)) / 86400000);
}

// Feature 2 §1 — Execution Dashboard: Baseline Finish → Forecast Completion → Bad-weather
// Completion, with the variance on each step (schedule's own slip, then what weather adds).
function _weatherDashboard() {
  const d = (_ca && _ca.dashboard) || {};
  const w = _weather;
  const slip = _daysBetween(d.baseline_finish, d.project_finish);   // schedule's own slip (cal. days)
  const wxAdd = w.net_finish_delay || 0;                            // weather adds (working days)
  return _sec(1, 'Execution Dashboard', '<span class="cal-pill warn">Estimate · not a P6 figure</span>') +
    `<div class="cal-flow">
      <div class="cal-step bl"><div class="cal-k">Baseline Finish</div><div class="cal-v">${fmtCalDate(d.baseline_finish)}</div></div>
      <div class="cal-arrow"><div class="cal-alab">Schedule slip</div><div class="cal-avar ${slip > 0 ? 'pos' : 'zero'}">${slip > 0 ? '+' : ''}${slip} d</div><div class="cal-aln">→</div></div>
      <div class="cal-step fc"><div class="cal-k">Forecast Completion</div><div class="cal-v">${fmtCalDate(d.project_finish)}</div></div>
      <div class="cal-arrow"><div class="cal-alab">Weather adds</div><div class="cal-avar ${wxAdd > 0 ? 'pos' : 'zero'}">+${wxAdd} wd</div><div class="cal-aln">→</div></div>
      <div class="cal-step bw"><div class="cal-k">Bad-weather Completion</div><div class="cal-v">${fmtCalDate(w.weather_adjusted_finish)}</div></div>
    </div>
    <div class="cal-note">Reads left → right: the baseline finish, the schedule's own forecast finish, then the weather-adjusted finish. Each arrow shows that step's variance — the schedule's own slip, then, separately, what bad weather adds.</div>`;
}

// Feature 2 §2 — 3-colour monthly histogram: net working (green) / bad-weather (amber) /
// non-working (red) days; the number above each bar is the NET working days that month.
function _weatherHistogram() {
  const h = (_weather && _weather.histogram) || [];
  if (!h.length) return '';
  const H = 130;
  const maxTot = Math.max(1, ...h.map(m => (m.net || 0) + (m.bad || 0) + (m.nonworking || 0)));
  const px = v => Math.round((v || 0) / maxTot * H);
  const bars = h.map(m =>
    `<div class="cal-3bar" title="${escapeHtml(m.label)}: ${m.net} net working · ${m.bad} bad-weather · ${m.nonworking} non-working">
      <div class="cal-3v">${m.net}</div>
      <div class="cal-3col">
        <div class="s-bad" style="height:${px(m.bad)}px"></div>
        <div class="s-nw" style="height:${px(m.nonworking)}px"></div>
        <div class="s-net" style="height:${px(m.net)}px"></div>
      </div>
      <div class="cal-3l">${escapeHtml(m.label)}</div></div>`).join('');
  return _sec(2, 'Calendar Timeline &amp; Statistics') +
    `<div class="cal-3leg"><span><i class="sw sw-net"></i>Net working days</span>
       <span><i class="sw sw-nw"></i>Non-working days</span>
       <span><i class="sw sw-bad"></i>Bad-weather days</span>
       <span>▲ number above bar = <b>net working days</b> (working − bad-weather)</span></div>
     <div class="cal-3hist">${bars}</div>`;
}

function _weatherSection() {
  const dd = (_ca && _ca.dashboard && _ca.dashboard.data_date) ? fmtCalDate(_ca.dashboard.data_date) : '';
  const head = dd
    ? `<div class="cal-ddbanner">📅 All results start from the <b>Data Date · ${dd}</b> — nothing before it. Weather window: data date → finish.</div>`
    : '';
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
  const dashboard = _weatherDashboard();
  const histogram = _weatherHistogram();
  const badSub = (w.climate_avg_total != null && w.climate_avg_total !== w.expected_bad_days_total)
    ? `~${w.climate_avg_total} on the 5-yr average` : '';
  const kpis = `<div class="cal-kpi-grid" style="grid-template-columns:repeat(3,1fr);margin:12px 0">
    ${_tile('Bad-weather days (remaining)', w.expected_bad_days_total, badSub, 'hl-amber')}
    ${_tile('Net weather delay to finish', `+${w.net_finish_delay} wd`, '', 'hl-amber')}
    ${_tile('Weather-adjusted finish', fmtCalDate(w.weather_adjusted_finish))}</div>`;
  // Monthly bars: 5-year AVERAGE (bar) with a whisker for the fewest–most across those years.
  const H = 70;
  const maxHi = Math.max(1, ...(w.monthly || []).map(x => (x.hi != null ? x.hi : x.count)));
  const bars = (w.monthly || []).map(x => {
    const avg = x.avg != null ? x.avg : x.count;
    const lo = x.lo != null ? x.lo : avg, hi = x.hi != null ? x.hi : avg;
    const whisker = (hi > lo)
      ? `<div class="cal-wxbar-rng" style="bottom:${lo / maxHi * H}px;height:${(hi - lo) / maxHi * H}px"></div>` : '';
    return `<div class="cal-wxbar"><div class="cal-wxbar-v">${avg || ''}</div>
      <div class="cal-wxbar-col" style="height:${H}px">
        <div class="cal-wxbar-b" style="height:${Math.max(3, avg / maxHi * H)}px;${avg >= 3 ? 'background:var(--warning)' : ''}"></div>${whisker}</div>
      <div class="cal-wxbar-l">${escapeHtml(x.label)}</div></div>`;
  }).join('');
  const bar = `<div class="cal-card" style="margin-bottom:12px">
    <div class="cal-muted" style="font-size:12px;margin-bottom:10px">Expected bad-weather days per month — <b>5-year average</b> (bar) with the range across those years (whisker) · construction phases only</div>
    <div class="cal-wxbars">${bars || '<span class="cal-muted">No data.</span>'}</div></div>`;
  const dayRows = (w.bad_days || []).slice(0, 200).map(d =>
    `<tr><td>${fmtCalDate(d.date)}</td><td>${escapeHtml(d.day_name)}</td>
      <td>${escapeHtml(d.condition)}</td>
      <td><span class="cal-pill mini ${d.confidence === 'forecast' ? 'def' : 'warn'}">${d.confidence === 'forecast' ? 'Forecast' : 'Expected'}</span></td>
      <td>${_actsCell(d)}</td></tr>`).join('');
  const dayTable = `<div class="cal-grp"><span class="cal-pill special">Upcoming Bad-Weather Days</span>
      <span class="cal-grp-meta">each day shows the measured value, why it counts &amp; the work (by WBS) it hits · next ~16 days = live forecast · beyond = a typical year from the 5-year climate history</span></div>
    <div class="cal-card p0" style="max-height:300px;overflow-y:auto"><table class="cal-table"><thead><tr>
      <th>Date</th><th>Day</th><th>Why it's a lost day (measured)</th><th>Confidence</th><th>Affected work (by WBS)</th></tr></thead>
      <tbody>${dayRows || '<tr><td colspan="5" class="cal-empty">No bad-weather days expected.</td></tr>'}</tbody></table></div>`;
  const msRows = (w.milestones || []).map(m =>
    `<tr><td>${escapeHtml(m.name)}</td><td>${fmtCalDate(m.planned)}</td>
      <td class="num">${m.bad_days_before}</td><td class="num">${m.already_allowed}</td>
      <td class="num"><span class="cal-pill mini ${m.net_delay > 0 ? 'shutdown' : 'def'}">+${m.net_delay} d</span></td>
      <td>${fmtCalDate(m.adjusted)}</td></tr>`).join('');
  const msTable = `<div class="cal-grp"><span class="cal-pill shutdown">Impact on Milestone Completion</span></div>
    <div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Milestone</th><th>Planned completion</th><th class="num">Bad-weather days before it</th>
      <th class="num">Already in calendar</th><th class="num">Net weather delay</th><th>Weather-adjusted completion</th></tr></thead>
      <tbody>${msRows || '<tr><td colspan="6" class="cal-empty">No milestones found.</td></tr>'}</tbody></table></div>
     <div class="cal-note" style="font-style:normal"><b>How to read this table:</b> <b>Bad-weather days before it</b> — expected bad-weather days between the data date and the milestone's planned finish. <b>Already in calendar</b> — of those, the ones landing on a day already off (weekend / holiday / shutdown), so they cost nothing extra. <b>Net weather delay</b> — the rest, hitting real working days (<b>Net = Before − Already in calendar</b>): the actual days weather adds. <i>Example — 6 bad-weather days before finish; 4 already fell on off-days, so only 2 hit working days → +2 working days.</i></div>`;
  const recRows = (w.recovery || []).map(r =>
    `<tr><td>${escapeHtml(r.period)}</td><td class="num"><span class="cal-pill mini shutdown">${r.days} d</span></td>
      <td>${escapeHtml(r.option_longer_days)}</td><td>${escapeHtml(r.option_extra_days)}</td><td>${escapeHtml(r.option_shift)}</td></tr>`).join('');
  const recTable = `<div class="cal-grp"><span class="cal-pill def">Recovery Recommendations</span>
      <span class="cal-grp-meta">advisory — one option per period, computed from the estimated lost hours</span></div>
    <div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Period / milestone</th><th class="num">Days</th><th>Longer days</th><th>Extra working days</th><th>Add shift</th></tr></thead>
      <tbody>${recRows || '<tr><td colspan="5" class="cal-empty">No recovery needed — no net weather delay.</td></tr>'}</tbody></table></div>`;
  const totalBad = w.expected_bad_days_total || 0;
  const causeColor = { Heat: 'var(--danger)', Dust: 'var(--warning)', Rain: 'var(--chart-1)', Wind: 'var(--muted)' };
  const causeRows = (w.by_cause || []).map(c => {
    const off = !!c.off;
    const cnt = off ? 0 : (c.count || 0);
    const pct = (!off && totalBad) ? Math.round(cnt / totalBad * 100) : 0;
    const val = off ? 'off' : `${cnt} ${cnt === 1 ? 'day' : 'days'}${totalBad ? ` · ${pct}%` : ''}`;
    return `<div class="cal-cause"><div class="cal-cause-l">${escapeHtml(c.label)}</div>
      <div class="cal-cause-track"><div class="cal-cause-fill" style="width:${off ? 0 : pct}%;background:${causeColor[c.label] || 'var(--accent)'}"></div></div>
      <div class="cal-cause-n">${val}</div></div>`;
  }).join('');
  const causeCard = (w.by_cause || []).length
    ? `<div class="cal-grp"><span class="cal-pill shutdown">What's causing the lost days — by weather type</span>
        <span class="cal-grp-meta">which condition to plan around (heat → shift hours earlier; rain → drainage)</span></div>
       <div class="cal-card">${causeRows}</div>`
    : '';
  const conclHtml = w.conclusion
    ? `<div class="cal-grp"><span class="cal-pill warn">Weather conclusion</span>
        <span class="cal-grp-meta">auto-generated from the numbers above</span></div>
       <div class="cal-concl" style="border-left:4px solid var(--warning)"><p style="margin:0;font-size:13px;line-height:1.6">${escapeHtml(w.conclusion)}</p></div>`
    : '';
  const note = '<div class="cal-note">Applies to construction activities only (auto-detected), and only to Finish/completion milestones. A forward-looking risk, kept separate from the exact P6 Delay. Needs an internet connection.</div>';
  return head + controls + dashboard + histogram + kpis + _whyResultHtml() + causeCard + dayTable + msTable + recTable + bar + _climateRefHtml() + conclHtml + note;
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
  return _sec(9, 'Executive Conclusion') +
    `<div class="cal-concl"><ul>${items}</ul>
      <div class="cal-note">Generated automatically from the numbers above.</div></div>`;
}

// ── wiring ─────────────────────────────────────────────────────────────────
function _wireCalendar() {
  const picker = document.getElementById('cal-picker');
  if (picker) picker.addEventListener('change', e => { _sel = e.target.value; _openMonths.clear(); _renderCalendarBody(); });

  document.querySelectorAll('#calendar-body .cal-whc').forEach(bar =>
    bar.addEventListener('click', () => {
      const i = +bar.dataset.month;
      if (_openMonths.has(i)) _openMonths.delete(i); else _openMonths.add(i);
      _renderCalendarBody();
    }));

  _wireShutdowns();
}

function _wireWeatherView() {
  _wireLocation();
  _wireSiteTypes();
  _wireWeather();
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
        // Update the pin in place (no full re-render) so the map stays put while fine-tuning.
        _pendingLoc = { lat: +r.lat, lon: +r.lon, name: r.name };
        _updateLocReadout();
        _panMapTo(+r.lat, +r.lon);
        results.innerHTML = '';
      }));
  };
  if (searchBtn) searchBtn.addEventListener('click', doSearch);
  if (q) q.addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });
  if (useBtn) useBtn.addEventListener('click', () => _runWeather(useBtn, statusEl));
  _initMap();
}

// Refresh just the coordinates read-out + enable the Use button (no full re-render).
function _updateLocReadout() {
  const el = document.getElementById('cal-loc-readout');
  if (el) el.innerHTML = _locationReadoutHtml();
  const use = document.getElementById('cal-loc-use');
  if (use && _pendingLoc) use.disabled = false;
}

// Load the vendored Leaflet (local file — ships in the .exe) exactly once.
function _ensureLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (_leafletPromise) return _leafletPromise;
  _leafletPromise = new Promise(resolve => {
    const link = document.createElement('link');
    link.rel = 'stylesheet'; link.href = '/ui/vendor/leaflet/leaflet.css';
    document.head.appendChild(link);
    const s = document.createElement('script');
    s.src = '/ui/vendor/leaflet/leaflet.js';
    s.onload = () => resolve(window.L || null);
    s.onerror = () => resolve(null);
    document.head.appendChild(s);
  });
  return _leafletPromise;
}

function _pinIcon(L) {
  return L.divIcon({ className: 'cal-pin', html: '📍', iconSize: [26, 26], iconAnchor: [13, 24] });
}

// Drop or move the pin, set the pending location, then reverse-geocode a friendly name.
async function _setFromMap(latlng) {
  const lat = +latlng.lat.toFixed(6), lon = +latlng.lng.toFixed(6);
  const fallback = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  _pendingLoc = { lat, lon, name: fallback };
  _updateLocReadout();
  const resp = await reverseGeocode(lat, lon);
  if (resp && resp.ok && resp.name) {
    _pendingLoc = { lat, lon, name: resp.name };
    _updateLocReadout();
  }
}

function _panMapTo(lat, lon) {
  if (!_map || !window.L) return;
  const ll = [+lat, +lon];
  try { _map.invalidateSize(); } catch { /* not visible */ }
  _map.setView(ll, 12);
  _placePin(ll, false);      // search already set the name — don't reverse-geocode over it
}

// Drop or move the location pin. `updateLoc` reverse-geocodes the point into _pendingLoc
// (a map tap); pass false when the caller already set the location (a search result).
function _placePin(latlng, updateLoc = true) {
  const L = window.L;
  if (!_map || !L) return;
  if (!_marker) {
    _marker = L.marker(latlng, { draggable: true, icon: _pinIcon(L) }).addTo(_map);
    _marker.on('dragend', () => _setFromMap(_marker.getLatLng()));
  } else {
    _marker.setLatLng(latlng);
  }
  if (updateLoc) _setFromMap(_marker.getLatLng());
}

async function _initMap() {
  const el = document.getElementById('cal-map');
  if (!el) return;
  const L = await _ensureLeaflet();
  // The body may have re-rendered while Leaflet loaded — bail if this node is gone.
  if (!L || !document.body.contains(el)) {
    if (el && !L) el.innerHTML = '<div class="cal-map-empty">Map needs an internet connection.</div>';
    return;
  }
  if (_mapRO) { try { _mapRO.disconnect(); } catch { /* gone */ } _mapRO = null; }
  if (_map) { try { _map.remove(); } catch { /* stale node */ } _map = null; _marker = null; }
  const hasLoc = _pendingLoc && _pendingLoc.lat != null;
  const center = hasLoc ? [+_pendingLoc.lat, +_pendingLoc.lon] : [24.5, 46.6]; // default: Arabian Peninsula
  _map = L.map(el, { attributionControl: true }).setView(center, hasLoc ? 11 : 5);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '© OpenStreetMap contributors',
  }).addTo(_map);
  if (hasLoc) {
    _marker = L.marker(center, { draggable: true, icon: _pinIcon(L) }).addTo(_map);
    _marker.on('dragend', () => _setFromMap(_marker.getLatLng()));
  }
  // Drop the pin on a tap. Leaflet's own 'click' is swallowed when the press→release moves
  // even a few px — a real trackpad / touch tap is never pixel-perfect — so "clicking a
  // point did nothing". Watch the container's own press→release and drop the pin whenever
  // the movement is small; a genuine pan moves much further. Covers mouse + touch. (#01)
  const cont = _map.getContainer();
  let downXY = null;
  const onDown = ev => {
    if (ev.target.closest('.leaflet-control')) { downXY = null; return; }
    const p = ev.touches ? ev.touches[0] : ev;
    downXY = { x: p.clientX, y: p.clientY };
  };
  const onUp = ev => {
    if (!downXY) return;
    const p = ev.changedTouches ? ev.changedTouches[0] : ev;
    const moved = Math.hypot(p.clientX - downXY.x, p.clientY - downXY.y);
    downXY = null;
    if (moved > 12) return;                                              // a pan, not a tap
    if (ev.target.closest('.leaflet-control') || ev.target.closest('.leaflet-marker-icon')) return;
    const r = cont.getBoundingClientRect();
    _placePin(_map.containerPointToLatLng(L.point(p.clientX - r.left, p.clientY - r.top)));
  };
  cont.addEventListener('mousedown', onDown);
  cont.addEventListener('mouseup', onUp);
  cont.addEventListener('touchstart', onDown, { passive: true });
  cont.addEventListener('touchend', onUp);
  // Leaflet mis-sizes when it inits inside a tab that isn't visible/sized yet (the pin
  // then lands at the edge). Re-measure when the container resizes (tab shown) and on a
  // couple of timed passes, recentring so the pin stays put. (#01)
  const recentre = () => {
    try { _map.invalidateSize(); _map.panTo(_marker ? _marker.getLatLng() : center); } catch { /* hidden */ }
  };
  if (window.ResizeObserver) {
    _mapRO = new ResizeObserver(() => { try { _map.invalidateSize(); } catch { /* hidden */ } });
    _mapRO.observe(el);
  }
  setTimeout(recentre, 80);
  setTimeout(recentre, 400);
}

// Pick a site type → load its preset limits and refresh the criteria panel + inputs.
function _wireSiteTypes() {
  document.querySelectorAll('#weather-body .cal-site').forEach(card =>
    card.addEventListener('click', () => {
      const key = card.dataset.site;
      if (key === 'custom' || !SITE_TYPES[key]) return;   // 'custom' is a state, not a choice
      _siteType = key;
      _thresholds = { ...SITE_TYPES[key].thresholds };
      _renderWeatherBody();                               // fills the limit inputs + criteria panel
    }));
}

// Wire the Weather-Impact "Apply & recalculate" (edited stop-work limits).
function _wireWeather() {
  const applyBtn = document.getElementById('thr-apply');
  if (applyBtn) applyBtn.addEventListener('click', () => {
    _thresholds = _readThresholds();
    _siteType = matchSiteType(_thresholds) || 'custom';   // edited away from a preset → Custom
    _runWeather(applyBtn, document.getElementById('thr-status'));
  });
}

async function _runWeather(btn, statusEl) {
  if (!_pendingLoc) return;
  if (btn) btn.disabled = true;
  if (statusEl) statusEl.textContent = 'Calculating weather…';
  try {
    const resp = await computeWeather(_pendingLoc.lat, _pendingLoc.lon, _pendingLoc.name, _thresholds, _siteType);
    if (resp.ok) {
      _weather = resp.weather;
      _pendingLoc = resp.location || _pendingLoc;
      if (resp.weather && resp.weather.thresholds) _thresholds = resp.weather.thresholds;
      if (resp.offline && statusEl) statusEl.textContent = 'No weather data (offline) — location saved.';
      _renderWeatherBody();
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
    if (resp.ok && resp.calendar_audit) { _ca = resp.calendar_audit; _renderCalendarBody(); }
  });
  // reason inline-edit (both P6 and manual shutdowns) → store per project
  document.querySelectorAll('#calendar-body .cal-reason').forEach(inp =>
    inp.addEventListener('change', async () => {
      const key = inp.dataset.key; if (!key) return;
      const reasons = {}; reasons[key] = inp.value;
      const resp = await saveCalendarSettings({ shutdown_reasons: reasons });
      if (resp.ok && resp.calendar_audit) { _ca = resp.calendar_audit; _renderCalendarBody(); }
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
